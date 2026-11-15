"""What the page and a bubble under the pointer show while reading, and how (`ui.hover`, `ui.zoom`, `ui.in_place`),
and a bubble's Japanese and translation at hand (`ui.bubble_text`): the two settings and their four combinations - the
translation or the original on the page, a panel beside the bubble or the bubble itself -, with Show original and
`bubble_zoom`; the patch of a bubble shown in its place; the View menu, the keys, the Settings dialog and the settings
file; the Japanese shown, read on demand for a page from the cache and copied, and nothing put on the clipboard but by
a copy; the hot keys over a full-screen viewer. Parts of the App are borrowed onto a stand-in on the shared hidden
root, which is never mapped: no real window is selected or touched, the popup is made but not shown (`zoom.reveal`),
the clipboard is the stand-in's own, and nothing of a page is written anywhere."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation import config
from taslation.config import ConfigError, Settings
from taslation.i18n import FEATURE_LANGUAGES
from taslation.locales.features import bubble_panel, settings_dialog as settings_texts
from taslation.regions import PageResult, TextRegion
from taslation.ui import app as app_mod
from taslation.ui import bubble_text, hover, in_place, overbook, zoom
from taslation.ui.bubble_text import BubbleTextMixin, hotkey_code, text_hotkeys
from taslation.ui.dialogs import settings as settings_dialog
from taslation.ui.dialogs.review import NOT_READ, READING, SelectableLine
from taslation.ui.hover import HoverChoiceMixin, original_idle, reveal_wanted, reverse_on
from taslation.ui.in_place import REVEAL_HOLD_PX, InPlaceMixin, lettering_patch, own_pixels, reach
from taslation.ui.live import LiveViewMixin
from taslation.ui.preview import ImageCanvas, patch_picture
from taslation.ui.progress import Filling
from taslation.ui.shortcuts import Keymap
from taslation.ui.translator import TranslatorMixin
from taslation.ui.zoom import FILL_WAIT, ZOOM_DELAY_MS, ZOOM_REST_MS, BubbleZoomMixin

WORK = (0, 0, 1920, 1040)
INK, PAPER, SET = (0, 0, 0), (255, 255, 255), (60, 60, 60)  # the Japanese, the bubble's paper, the translation
JAPANESE = "テストの一行"  # (made up for the tests)


# ------------------------------------------------------------------ the settings and the choices (no Tk)
def test_the_settings_start_with_the_translation_on_the_page_and_a_panel_and_take_nothing_else():
    s = Settings()
    assert (s.hover_shows, s.hover_reveal, s.bubble_zoom) == ("original", "panel", True)
    for key, value in (("hover_shows", "both"), ("hover_reveal", "tooltip")):
        with pytest.raises(ConfigError):
            Settings(**{key: value}).validate()
    Settings(hover_shows="translation", hover_reveal="in_place").validate()


def test_the_choices_count_in_reading_mode_and_the_reader_role_alone():
    def window(shows="original", reveal="panel", role="reader", reading=False, zoom_on=True):
        settings = SimpleNamespace(hover_shows=shows, hover_reveal=reveal, bubble_zoom=zoom_on)
        return SimpleNamespace(settings=settings, role_var=SimpleNamespace(get=lambda: role), reading=reading)

    assert hover.hover_shows(window(shows="x")) == "original" and hover.hover_reveal(window(reveal="x")) == "panel"
    assert hover.other_side("original") == "translation" and hover.other_reveal("panel") == "in_place"
    assert reverse_on(window("translation")) and not reverse_on(window("translation", role="translator"))
    assert reverse_on(window("translation", role="translator", reading=True))  # the reading window edits nothing
    assert reveal_wanted(window(), "panel") and not reveal_wanted(window(), "in_place")
    assert reveal_wanted(window(reveal="in_place"), "in_place")
    assert not reveal_wanted(window(zoom_on=False), "panel")  # the translation on the page: bubble_zoom counts ...
    assert not reveal_wanted(window(reveal="in_place", zoom_on=False), "in_place")
    assert reveal_wanted(window("translation", zoom_on=False), "panel")  # ... with the original on the page it does not
    assert not reveal_wanted(window(role="translator"), "panel")  # the Translator's pointer edits the regions
    assert original_idle(window("translation")) and not original_idle(window("translation", reading=True,
                                                                             role="translator"))


def test_every_new_line_of_the_window_is_in_every_language():
    keys = [label for _v, label in hover.HOVER_LABELS + hover.REVEAL_LABELS]
    keys += [*hover.HOVER_TIPS, *hover.REVEAL_TIPS, *hover.CHOSEN.values(), hover.ZOOM_OFF, hover.NOT_KEPT,
             zoom.ZOOM_HINT, zoom.FILL_WAIT, bubble_text.NO_BUBBLE, bubble_text.NO_TRANSLATION, bubble_text.NOT_HERE,
             bubble_text.JAPANESE_COPIED, bubble_text.TRANSLATION_COPIED, bubble_text.COPY_JAPANESE,
             bubble_text.COPY_TRANSLATION]
    for key in keys:
        assert set(bubble_panel.TEXTS[key]) == set(FEATURE_LANGUAGES), key
    for row in settings_dialog.EXTRA_ROWS[:3]:
        assert row.key in ("hover_shows", "hover_reveal", "bubble_zoom")
        for key in (row.label, row.tip, *(label for _v, label in row.choices)):
            assert set(settings_texts.TEXTS[key]) == set(FEATURE_LANGUAGES), key
    assert "no native review" in bubble_panel.__doc__


# ------------------------------------------------------------------ the patch of a bubble in its place (no Tk)
def test_a_bubble_s_patch_is_what_differs_there_on_its_own_pixels_alone():
    original = Image.new("RGB", (200, 100), PAPER)
    lettered = original.copy()
    lettered.paste(SET, (20, 20, 40, 40))  # this bubble's translation ...
    lettered.paste(SET, (62, 20, 90, 40))  # ... and its neighbour's, within its reach
    mine, theirs = (10, 10, 50, 50), (60, 10, 100, 50)
    assert reach(mine, original.size) == (0, 0, 70, 70)
    owned = own_pixels(mine, [theirs], (0, 0, 70, 70))
    assert owned[30, 30] and owned[30, 54] and not owned[30, 60]  # (row, column): nearer the neighbour from x 56 on
    box, picture = lettering_patch(original, lettered, mine, [theirs])
    assert box == (20, 20, 40, 40) and picture.mode == "RGBA" and picture.getpixel((5, 5)) == (*SET, 255)
    frame = Image.new("RGB", (200, 100), (200, 0, 0))  # the other way: the pixels of the viewer's frame
    box, picture = lettering_patch(original, lettered, mine, [theirs], frame)
    assert box == (20, 20, 40, 40) and picture.getpixel((5, 5)) == (200, 0, 0, 255)
    assert lettering_patch(original, original.copy(), mine, []) is None  # nothing differs
    assert lettering_patch(original, lettered.resize((100, 50)), mine, []) is None  # not one page


def test_a_patch_drawn_over_the_picture_is_the_picture_lettered_there():
    rng = np.random.default_rng(7)
    page = Image.fromarray(rng.integers(0, 255, (300, 400, 3), dtype=np.uint8))
    lettered = page.copy()
    lettered.paste(SET, (120, 80, 200, 160))
    patch = lettering_patch(page, lettered, (110, 70, 210, 170), [])
    fit = ((0, 0, 400, 300), (400, 300), (200, 150), (10, 5))  # the whole page at half size, 10 and 5 px in
    (cx, cy), picture = patch_picture(page, patch, fit)
    whole = np.asarray(lettered.resize((200, 150), Image.LANCZOS), dtype=int)
    x, y = cx - 10, cy - 5
    part = whole[y:y + picture.height, x:x + picture.width]
    assert np.abs(np.asarray(picture.convert("RGB"), dtype=int) - part).max() <= 1  # its edges meet the picture


# ------------------------------------------------------------------ the window, on a stand-in
def _region(x0, y0, x1, y1, text, font_size, tag="", status="translated", source=""):
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), (x0, y0, x1, y1),
                      translated_text=text, font_size=font_size, status=status, tag=tag, source_text=source)


def _result():
    """An 800 x 600 page: a narrow bubble (a thought, lettered small: hard to read at half size), a wide one (a shout)
    and one read and left without a translation; on the translated page the first two erased and set."""
    original = Image.new("RGB", (800, 600), PAPER)
    for box in ((120, 120, 180, 280), (420, 120, 680, 180), (310, 410, 350, 450)):
        original.paste(INK, box)
    image = original.copy()
    for erased, written in (((120, 120, 180, 280), (130, 150, 170, 250)), ((420, 120, 680, 180), (430, 130, 600, 170))):
        image.paste(PAPER, erased)
        image.paste(SET, written)
    regions = [_region(100, 100, 200, 300, "A *small* thought.", 18, tag="thought"),
               _region(400, 100, 700, 200, "A WIDE SHOUT.", 40, tag="shout"),
               _region(300, 400, 360, 460, "", 0, status="untranslated")]
    return PageResult(image=image, original=original, regions=regions)


class Pipeline:
    """The reading model's stand-in: `Pipeline.read_source` reads the region's Japanese into the region (memory)."""

    ocr = object()

    def __init__(self):
        self.read = []

    def read_source(self, result, region):
        self.read.append(region)
        region.source_text = JAPANESE
        return JAPANESE


class Window(BubbleZoomMixin, InPlaceMixin, HoverChoiceMixin, BubbleTextMixin, tk.Toplevel):
    """The page of the window (400 x 300 canvas pixels: the 800 x 600 page at half size) and what the two settings
    use: the live view's picture and redraw, the region editor's way of reading a region's Japanese."""

    _redisplay = LiveViewMixin._redisplay
    _picture = LiveViewMixin._picture
    _result_on_show = LiveViewMixin._result_on_show
    _lettered = LiveViewMixin._lettered
    _lettering = LiveViewMixin._lettering
    _page_regions = LiveViewMixin._page_regions
    _read_source = TranslatorMixin._read_source
    _source_read = TranslatorMixin._source_read

    def __init__(self, root, settings):
        super().__init__(root)
        self.withdraw()
        self.settings = settings
        self.keymap = Keymap()
        self.role_var = tk.StringVar(self, value="reader")
        self.original_var = tk.BooleanVar(self, value=False)
        self.hover_var = tk.StringVar(self, value=settings.hover_shows)
        self.reveal_var = tk.StringVar(self, value=settings.hover_reveal)
        self.reading, self._viewer_hidden, self.selected = False, False, SimpleNamespace(hwnd=0)
        self._fill = self._run_view = self._live = None
        self._lettered_memo = self._mask_memo = None
        self.pipeline = Pipeline()
        self._jobs = SimpleNamespace(put=self.jobs_put)
        self.jobs: list = []
        self.later: list[tuple[int, object]] = []
        self.said: list[str] = []
        self.clipboard: list[tuple] = []
        self.canvas = ImageCanvas(self)
        self.canvas.trim = False
        self.canvas.winfo_width, self.canvas.winfo_height = (lambda: 400), (lambda: 300)
        self.canvas.winfo_rootx, self.canvas.winfo_rooty = (lambda: 1000), (lambda: 100)
        menu = tk.Menu(self, tearoff=0)
        menu.add_checkbutton(label="Show original", variable=self.original_var)
        self._original_entry = (menu, 0)
        self.pointer = (0, 0)
        self.last_result = _result()
        self._redisplay()
        self._watch_bubbles()

    # the window's surroundings
    def _same_page(self, result, live):
        return live is result.original or live.size == result.original.size

    def _overlay_items(self):
        return []

    def say(self, key, **_values):
        self.said.append(key)

    def clipboard_clear(self, **_kw):  # (the stand-in's own: the system's clipboard is never touched)
        self.clipboard.append(("clear",))

    def clipboard_append(self, text, **_kw):
        self.clipboard.append(("append", text))

    def jobs_put(self, job):
        self.jobs.append(job)

    def winfo_pointerxy(self):
        return self.pointer

    def after(self, ms, func=None, *args):
        self._jobs_made = getattr(self, "_jobs_made", 0) + 1
        job = f"after#{self._jobs_made}"
        self.later.append((ms, func, job))
        return job

    def after_cancel(self, job):
        self.later = [item for item in self.later if item[2] != job]

    # the test's hands
    def point(self, x, y):
        """The pointer at the page point (x, y) (page pixels): its motion there, its screen point kept."""
        cx, cy = self.canvas.from_image_coords(x, y)
        self.pointer = (1000 + cx, 100 + cy)
        self._bubbles_motion(SimpleNamespace(x=cx, y=cy))

    def due(self, name):
        """The callback put off last under *name*, now."""
        for i in range(len(self.later) - 1, -1, -1):
            func = self.later[i][1]
            if getattr(func, "__name__", "") == name:
                del self.later[i]
                func()
                return
        raise AssertionError(f"nothing put off as {name}: {[getattr(f, '__name__', f) for _ms, f, _j in self.later]}")

    def delays(self, name):
        return [ms for ms, f, _job in self.later if getattr(f, "__name__", "") == name]

    def shown_at(self, x, y):
        """The page's pixel at (x, y) as the window shows it: the picture, and over it a bubble shown in its place."""
        patch = self.canvas.patch
        if patch is not None:
            (x0, y0, x1, y1), picture = patch
            if x0 <= x < x1 and y0 <= y < y1 and picture.getpixel((x - x0, y - y0))[3]:
                return picture.getpixel((x - x0, y - y0))[:3]
        return self.canvas._image.convert("RGB").getpixel((x, y))


@pytest.fixture
def make(hidden_root, monkeypatch, tmp_path):
    monkeypatch.setattr(zoom, "reveal", lambda popup: None)
    monkeypatch.setattr(zoom.layout, "work_area", lambda widget, x=None, y=None: WORK)

    def no_file(*_a, **_k):
        raise AssertionError("nothing of the page is written anywhere")

    monkeypatch.setattr(Image.Image, "save", no_file)

    def made(shows="original", reveal="panel"):
        settings = Settings(state_dir=tmp_path / "state", config_path=tmp_path / "taslation.toml",
                            hover_shows=shows, hover_reveal=reveal)
        return Window(hidden_root, settings)

    return made


def _labels(widget, cls="Label"):
    found, stack = [], [widget]
    while stack:
        item = stack.pop()
        if item.winfo_class() == cls:
            found.append(item)
        stack.extend(item.winfo_children())
    return found


# ------------------------------------------------------------------ the four combinations
def test_translation_on_the_page_and_a_panel_the_original_beside_the_bubble(make):
    w = make("original", "panel")
    assert w.shown_at(150, 200) == SET and w.shown_at(125, 130) == PAPER  # the page translated
    w.point(150, 200)
    assert w.delays("_zoom_due") == [ZOOM_DELAY_MS] and w.delays("_reveal_due") == []  # (hard to read where it is)
    w.due("_zoom_due")
    popup = w._zoom_popup
    labels = _labels(popup)
    picture = next(lbl for lbl in labels if str(lbl.cget("image")))
    assert (picture.image.width(), picture.image.height()) == (150, 300)  # the original, from memory, enlarged
    assert "A small thought." in [str(lbl.cget("text")) for lbl in labels]
    assert w.canvas.patch is None and w.shown_at(150, 200) == SET  # the page does not change
    w.point(550, 150)  # the wide bubble reads well: its panel after the longer rest
    assert w._zoom_popup is None and w.delays("_zoom_due") == [ZOOM_REST_MS]


def test_translation_on_the_page_and_the_bubble_itself_the_original_lettering_in_its_place(make):
    w = make("original", "in_place")
    w.point(150, 200)
    assert w.delays("_reveal_due") == [ZOOM_DELAY_MS] and w.delays("_zoom_due") == []  # no panel in this way
    w.due("_reveal_due")
    assert w._zoom_popup is None and w.canvas.patch is not None
    assert w.shown_at(125, 130) == INK and w.shown_at(150, 200) == INK  # the Japanese where it is, as the viewer has it
    assert w.shown_at(550, 150) == SET  # the other bubble stays translated: one bubble at a time
    w.point(200 + REVEAL_HOLD_PX, 200)  # just off the box (3 canvas px), within the hold: it stays
    assert w.canvas.patch is not None
    w.point(200 + 4 * REVEAL_HOLD_PX, 200)  # beyond it: it goes
    assert w.canvas.patch is None
    w.point(150, 200)
    w.due("_reveal_due")
    w.point(550, 150)  # onto the other bubble: the first goes back at once, this one after the longer rest
    assert w.canvas.patch is None and w.shown_at(150, 200) == SET and w.delays("_reveal_due") == [ZOOM_REST_MS]
    w.due("_reveal_due")
    assert w.shown_at(425, 125) == INK
    w.point(750, 550)  # the bare page
    assert w.canvas.patch is None and w.later == []


def test_original_on_the_page_and_a_panel_the_translation_alone_in_the_faces_of_its_kind(make):
    w = make("translation", "panel")
    assert w.shown_at(150, 200) == INK and w.shown_at(125, 130) == INK  # the page as the viewer shows it
    w.point(150, 200)
    assert w.delays("_zoom_due") == [ZOOM_DELAY_MS]
    w.due("_zoom_due")
    labels = _labels(w._zoom_popup)
    assert not any(str(lbl.cget("image")) for lbl in labels)  # no picture: the original is on the page
    assert "A small thought." in [str(lbl.cget("text")) for lbl in labels]
    assert w._zoom_font.cget("slant") == "italic" and w._zoom_font.cget("weight") == "normal"  # a thought
    assert w.canvas.patch is None
    w.point(550, 150)
    assert w.delays("_zoom_due") == [ZOOM_DELAY_MS]  # every bubble soon: the page does not show its translation
    w.due("_zoom_due")
    assert w._zoom_font.cget("weight") == "bold" and w._zoom_font.cget("slant") == "roman"  # a shout


def test_original_on_the_page_and_the_bubble_itself_erased_and_set_as_the_translated_page_has_it(make):
    w = make("translation", "in_place")
    w.point(150, 200)
    assert w.delays("_reveal_due") == [ZOOM_DELAY_MS] and w.delays("_zoom_due") == []
    w.due("_reveal_due")
    assert w._zoom_popup is None
    translated = w.last_result.image
    for xy in ((125, 130), (150, 200), (175, 275), (110, 110)):  # the erase and the lettering, pixel for pixel
        assert w.shown_at(*xy) == translated.getpixel(xy), xy
    assert w.shown_at(425, 125) == INK  # the other bubble as the viewer has it
    w._bubbles_away()  # a click on the page (it goes on to the viewer) or the wheel
    assert w.canvas.patch is None and w.shown_at(150, 200) == INK


def test_a_change_of_either_choice_shows_at_once_and_is_kept_in_the_settings_file(make, tmp_path):
    w = make("original", "panel")
    w.point(150, 200)
    w.due("_zoom_due")
    assert w._zoom_popup is not None
    w.set_hover_reveal("in_place")  # (the View menu's way: saved)
    assert w._zoom_popup is None and w.reveal_var.get() == "in_place" and w.said[-1] == hover.CHOSEN[
        ("hover_reveal", "in_place")]
    w.flip_hover_shows()  # (its key's way)
    assert w.settings.hover_shows == "translation" and w.hover_var.get() == "translation"
    assert w.shown_at(150, 200) == INK  # the page on show as the viewer has it, nothing translated again
    assert w.jobs == [] and w.pipeline.read == []
    assert str(w._original_entry[0].entrycget(0, "state")) == "disabled"  # Show original has nothing to do
    kept = Settings.from_toml(tmp_path / "taslation.toml")
    assert (kept.hover_shows, kept.hover_reveal) == ("translation", "in_place")
    w.flip_hover_reveal()
    w.set_hover_shows("original")
    assert w.shown_at(150, 200) == SET and str(w._original_entry[0].entrycget(0, "state")) == "normal"
    kept = Settings.from_toml(tmp_path / "taslation.toml")
    assert (kept.hover_shows, kept.hover_reveal) == ("original", "panel")


def test_show_original_and_bubble_zoom_with_the_translation_on_the_page(make):
    w = make("original", "in_place")
    w.original_var.set(True)  # View > Show original: the whole page as the viewer has it, nothing to show in place
    w._redisplay()
    assert w.shown_at(150, 200) == INK
    w.point(150, 200)
    assert w.later == []
    w.original_var.set(False)
    w._redisplay()
    w.settings.bubble_zoom = False  # nothing under the pointer, either way
    w.point(550, 150)
    assert w.later == []
    w.set_hover_reveal("panel", save=False)
    w.point(150, 200)
    assert w.later == []


def test_the_translator_role_keeps_its_page_and_its_pointer(make):
    for shows, reveal in (("original", "panel"), ("original", "in_place"), ("translation", "panel"),
                          ("translation", "in_place")):
        w = make(shows, reveal)
        w.role_var.set("translator")
        w._redisplay()
        assert w.shown_at(150, 200) == SET, (shows, reveal)  # the translated page, whatever is chosen
        w.point(150, 200)
        assert w.later == [], (shows, reveal)
        w.reading = True  # ... but reading mode shows as the choices say
        w._redisplay()
        assert w.shown_at(150, 200) == (INK if shows == "translation" else SET), (shows, reveal)
        w.point(155, 205)
        assert w.later, (shows, reveal)


def test_a_bubble_in_its_place_goes_with_a_key_esc_and_its_page(make):
    w = make("translation", "in_place")
    w.point(150, 200)
    w.due("_reveal_due")
    assert w._zoom_escape() == "break" and w.canvas.patch is None  # Esc: taken for it while it shows ...
    assert w._zoom_escape() is None  # ... then the window's as ever
    w.point(550, 150)
    w.due("_reveal_due")
    w._bubbles_left()  # a key, or the pointer off the page
    assert w.canvas.patch is None
    w.point(150, 200)
    w.due("_reveal_due")
    w.last_result = _result()  # the page turned in the viewer, or read again
    w.due("_reveal_watch")
    assert w.canvas.patch is None and w._reveal_shown is None
    w.point(150, 200)
    w.due("_reveal_due")
    w.pointer = (0, 0)  # the pointer off the page without a motion on it (onto another window)
    w.due("_reveal_watch")
    assert w.canvas.patch is None


def test_a_page_being_translated_with_the_original_on_the_page(make):
    w = make("translation", "panel")
    result = w.last_result
    fill = Filling(frame=result.original, base=result.original, boxes=[r.bbox for r in result.regions])
    w._fill = fill
    w._redisplay()
    assert w.canvas.outlines == [] and w.shown_at(150, 200) == INK  # as the viewer shows it, no outlines
    w.point(150, 200)
    w.due("_zoom_due")
    labels = [str(lbl.cget("text")) for lbl in _labels(w._zoom_popup)]
    assert FILL_WAIT in labels and _labels(w._zoom_popup, "TProgressbar")  # a running bar while it is translated
    w._zoom_hide()
    w.set_hover_reveal("in_place", save=False)
    w.point(150, 200)
    w.due("_reveal_due")
    assert w.canvas.outlines == [(tuple(result.regions[0].bbox), *fill.outlines()[0][1:])]  # its outline alone
    fill.letter(0, (100, 100), result.image.crop((100, 100, 200, 300)), "A small thought.")
    w.due("_reveal_watch")
    w._redisplay()  # (the page filling in is drawn again as its regions are lettered)
    assert w.canvas.outlines == [] and w.shown_at(150, 200) == SET  # its lettering in its place
    assert w.shown_at(425, 125) == INK


def test_with_the_translation_on_the_page_a_page_filling_in_shows_its_outlines_as_ever(make):
    w = make("original", "in_place")
    result = w.last_result
    w._fill = Filling(frame=result.original, base=result.original, boxes=[r.bbox for r in result.regions])
    w._redisplay()
    assert len(w.canvas.outlines) == 3
    w.point(150, 200)
    assert w.later == []  # nothing under the pointer until the page is translated


# ------------------------------------------------------------------ a bubble's Japanese and translation
def test_the_key_pins_the_panel_with_the_japanese_to_select_in_either_way(make, caplog):
    caplog.set_level(logging.DEBUG)
    for shows, reveal in (("original", "panel"), ("original", "in_place"), ("translation", "panel"),
                          ("translation", "in_place")):
        w = make(shows, reveal)
        w.last_result.regions[0].source_text = JAPANESE  # read in this session
        w.point(150, 200)
        w.show_japanese()
        assert w._zoom_pinned and w.canvas.patch is None, (shows, reveal)
        line = next(widget for widget in _labels(w._zoom_popup, "Text") if isinstance(widget, SelectableLine))
        assert line.get("1.0", "end-1c") == JAPANESE
        assert str(line.cget("state")) == "disabled"  # to select, never to edit
        w.point(750, 550)  # the pointer leaves the bubble (for the panel): it stays
        assert w._zoom_popup is not None and w.later[-1][1].__name__ != "_zoom_due"
        w.point(150, 200)
        w.show_japanese()  # the key again on that bubble
        assert w._zoom_popup is None
        assert w.clipboard == []  # nothing on the clipboard but by a copy
    assert JAPANESE not in caplog.text


def test_copying_puts_the_text_on_the_clipboard_then_and_only_then(make, caplog):
    caplog.set_level(logging.DEBUG)
    w = make()
    region = w.last_result.regions[0]
    region.source_text = JAPANESE
    w.point(150, 200)
    w.due("_zoom_due")
    assert w.clipboard == []
    w.copy_translation()
    assert w.clipboard == [("clear",), ("append", "A small thought.")]  # without the lettering's marks
    assert w.said[-1] == bubble_text.TRANSLATION_COPIED
    w.copy_japanese()
    assert w.clipboard[-1] == ("append", JAPANESE) and w.said[-1] == bubble_text.JAPANESE_COPIED
    assert all(JAPANESE not in said for said in w.said) and JAPANESE not in caplog.text
    w.point(330, 430)  # a bubble read and left without a translation: its Japanese, but no translation
    w.copy_translation()
    assert w.said[-1] == bubble_text.NO_TRANSLATION and len(w.clipboard) == 4
    w.point(750, 550)
    w._zoom_hide()
    w.copy_japanese()
    assert w.said[-1] == bubble_text.NO_BUBBLE and len(w.clipboard) == 4
    w.role_var.set("translator")  # the region editor has the Japanese there
    w.point(150, 200)
    w.copy_japanese()
    assert w.said[-1] == bubble_text.NOT_HERE and len(w.clipboard) == 4


def test_a_page_from_the_cache_has_its_japanese_read_on_demand_and_kept_in_memory_alone(make, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    w = make("translation", "in_place")
    region = w.last_result.regions[0]
    assert region.source_text == ""  # the cache keeps no Japanese
    w.point(150, 200)
    w.show_japanese()
    labels = [str(lbl.cget("text")) for lbl in _labels(w._zoom_popup)]
    assert READING in labels and _labels(w._zoom_popup, "TProgressbar")  # read in the worker, a running bar meanwhile
    w.copy_japanese()  # asked again while it is read: one reading serves both
    assert w.said[-1] == READING and len(w.jobs) == 1 and w.clipboard == []
    w.jobs.pop()()  # (the worker)
    assert w.pipeline.read == [region] and region.source_text == JAPANESE  # with the region, in memory
    w.due("<lambda>")  # the reading looked for
    line = next(widget for widget in _labels(w._zoom_popup, "Text") if isinstance(widget, SelectableLine))
    assert line.get("1.0", "end-1c") == JAPANESE
    assert w.clipboard == [("clear",), ("append", JAPANESE)]
    w.copy_japanese()  # from memory now: no reading again
    assert w.jobs == [] and len(w.pipeline.read) == 1
    assert list(tmp_path.rglob("*")) == [] and JAPANESE not in caplog.text  # nothing written, nothing logged


def test_without_the_reading_model_the_panel_and_the_status_line_say_so(make):
    w = make()
    w.pipeline = None
    w.point(150, 200)
    w.copy_japanese()
    assert w.said[-1] == NOT_READ["no-ocr"] and w.clipboard == []


def test_the_keys_of_the_bubble_s_text_and_their_hot_keys():
    assert hotkey_code("F2") == (0, 0x71) and hotkey_code("Shift-F2") == (4, 0x71)
    assert hotkey_code("Control-F2") == (2, 0x71) and hotkey_code("Alt-j") == (1, ord("J"))
    assert hotkey_code("Left") is None  # (a page key is the viewer's: never one of them)
    assert text_hotkeys(Keymap()) == {"show_japanese": (0, 0x71), "copy_japanese": (4, 0x71),
                                      "copy_translation": (2, 0x71)}
    assert text_hotkeys(Keymap().with_key("show_japanese", None)) == {"copy_japanese": (4, 0x71),
                                                                       "copy_translation": (2, 0x71)}


class HotKeys:
    def __init__(self):
        self.codes: dict[str, tuple[int, int]] = {}
        self.pressed: list[str] = []

    @property
    def registered(self):
        return frozenset(self.codes)

    def register(self, name, vk, mods=0):
        self.codes[name] = (mods, vk)
        return True

    def unregister(self, name):
        self.codes.pop(name, None)

    def take(self):
        pressed, self.pressed = self.pressed, []
        return [name for name in pressed if name in self.codes]


class Over(overbook.OverBookMixin):
    """What `_over_keys` uses: the mode on over the viewer, which is in front."""

    def __init__(self, root):
        self._over_on, self.reading = True, False
        self.role_var = tk.StringVar(root, value="reader")
        self._over_hotkeys = HotKeys()
        self.keymap = Keymap()
        self.on_page, self._zoom_pinned = False, False
        self.done: list[str] = []

    def _over_owner(self):
        return "viewer"

    def _pointer_on_page(self):
        return (10, 10) if self.on_page else None

    def copy_translation(self):
        self.done.append("copy_translation")


def test_over_the_full_screen_viewer_the_keys_are_taslation_s_only_while_the_pointer_is_on_its_page(hidden_root):
    w = Over(hidden_root)
    w._over_keys()
    assert w._over_hotkeys.registered == {"F5"}  # the pointer elsewhere: the viewer keeps F2 and the rest
    w.on_page = True
    w._over_keys()
    assert w._over_hotkeys.codes == {"F5": (0, overbook.OVER_HOTKEYS["F5"]), "show_japanese": (0, 0x71),
                                     "copy_japanese": (4, 0x71), "copy_translation": (2, 0x71)}
    w._over_hotkeys.pressed = ["copy_translation"]
    w._over_keys()
    assert w.done == ["copy_translation"]
    w.on_page, w._zoom_pinned = False, True  # a pinned panel keeps them, the pointer gone to it
    w._over_keys()
    assert "copy_japanese" in w._over_hotkeys.registered
    w._zoom_pinned = False
    w.role_var.set("translator")  # not in the Translator role's normal window
    w.on_page = True
    w._over_keys()
    assert w._over_hotkeys.registered == {"F5"}


# ------------------------------------------------------------------ the menu, the keys and the Settings dialog
def test_the_keys_and_the_settings_dialog_set_the_choices_as_the_view_menu_does(hidden_root):
    done = []
    w = SimpleNamespace(settings=SimpleNamespace(),
                        set_hover_shows=lambda v, save=True: done.append(("shows", v, save)),
                        set_hover_reveal=lambda v, save=True: done.append(("reveal", v, save)))
    app_mod.App._settings_saved(w, {"hover_shows": "translation", "hover_reveal": "in_place"})
    assert done == [("shows", "translation", False), ("reveal", "in_place", False)]  # (the dialog wrote the file)
    assert (w.settings.hover_shows, w.settings.hover_reveal) == ("translation", "in_place")
    rows = {row.key: row for row in settings_dialog.EXTRA_ROWS}
    assert [v for v, _l in rows["hover_reveal"].choices] == ["panel", "in_place"]
    assert {"hover_shows", "hover_reveal"} <= set(settings_dialog.KEYS)
    from taslation.ui.shortcuts import BY_NAME

    assert BY_NAME["hover_reveal"].keys == () and BY_NAME["hover_shows"].keys == ()  # no key at first
