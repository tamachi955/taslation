"""A viewer that is no browser - an image viewer showing a folder of page images, its window titled with the file it
shows ("000.jpg", then "001.jpg") - stays the book while its window is there and shown, whatever its title; only a
browser window (whose title is its active tab's) goes by the title. Its profile (keys, area) is kept by the window's
class, so what was set for "000.jpg" is found for "001.jpg"; and while it is hidden or minimised the waiting line says
so without a word about tabs."""
from __future__ import annotations

import json
import threading

from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image
from test_batch import FakeViewer
from test_reading_messages import WAITING, Keys

from taslation import batch as batch_mod
from taslation import i18n
from taslation.batch import BatchReader
from taslation.cache import CacheStore, viewer_key_from_title
from taslation.capture import WindowInfo, still_the_book
from taslation.config import Settings
from taslation.message_texts import catalog
from taslation.messages import Message, render
from taslation.pagekeys import (BUILTIN_PRESETS, PageKeys, Profiles, names_a_file, profile_names, viewer_key,
                                viewer_title)
from taslation.translate import DictTranslator
from taslation.ui import reading, viewers

PHOTOS = "WinUIDesktopWin32WindowClass"  # the class of the image viewer of the incident
IMAGES = WindowInfo(hwnd=11, title="000.jpg", class_name=PHOTOS, pid=11, rect=(0, 0, 1200, 900))
CHROME = WindowInfo(hwnd=12, title="Star Road 1 - FOLIO☆QAT - Google Chrome", class_name="Chrome_WidgetWin_1",
                    pid=12, rect=(0, 0, 1200, 900))
HIDDEN = "Waiting: the viewer's window is hidden or minimised; bring it back."
HIDDEN_JA = "待機中: ビューアのウィンドウが非表示か最小化されています。元に戻してください。"


def _as(win: WindowInfo, title: str) -> WindowInfo:
    return WindowInfo(win.hwnd, title, win.class_name, win.pid, win.rect)


# ------------------------------------------------------------------ the rule
def test_a_window_that_is_no_browser_stays_the_book_whatever_its_title():
    assert still_the_book(IMAGES, "001.jpg")  # the incident: the first page turn renamed the window
    assert still_the_book(IMAGES, "page 12 of 200")
    assert still_the_book(IMAGES, "")  # (a title that is gone for a moment)
    assert not still_the_book(IMAGES, "000.jpg", shown=False)  # hidden or minimised: not the book until it is back


def test_a_browser_window_goes_by_its_title_as_before():
    assert still_the_book(CHROME, CHROME.title)
    assert still_the_book(CHROME, "Star Road 1 - page 2 | FOLIO☆QAT - Google Chrome")  # the same book's page
    assert not still_the_book(CHROME, "ホーム / X - Google Chrome")  # another tab
    assert not still_the_book(CHROME, "001.jpg - Google Chrome")
    assert still_the_book(CHROME, CHROME.title, shown=False)  # (its visibility was never asked: as before)
    unknown = WindowInfo(hwnd=13, title="Book - Browser", class_name="", pid=13, rect=(0, 0, 10, 10))
    assert not still_the_book(unknown, "Other tab - Browser")  # a class not known: the title rule, as before


class Front:
    """What `_book_in_front` uses."""

    _book_in_front = viewers.ViewerMixin._book_in_front
    _viewer_retitled = viewers.ViewerMixin._viewer_retitled

    def __init__(self, selected):
        self.selected, self.window_query = selected, ""


def test_the_chosen_image_viewer_is_in_front_while_its_title_changes(monkeypatch):
    titles = {IMAGES.hwnd: "001.jpg", CHROME.hwnd: "ホーム / X - Google Chrome"}
    shown = {IMAGES.hwnd: True, CHROME.hwnd: True}
    monkeypatch.setattr(viewers, "window_exists", lambda hwnd: hwnd in titles)
    monkeypatch.setattr(viewers, "window_title", lambda hwnd: titles[hwnd])
    monkeypatch.setattr(viewers, "window_shown", lambda hwnd: shown[hwnd])
    assert Front(IMAGES)._book_in_front()
    titles[IMAGES.hwnd] = "002.jpg"
    assert Front(IMAGES)._book_in_front()
    shown[IMAGES.hwnd] = False  # minimised
    assert not Front(IMAGES)._book_in_front()
    assert not Front(CHROME)._book_in_front()  # the browser shows another tab: waiting, as before
    titles[CHROME.hwnd] = CHROME.title
    assert Front(CHROME)._book_in_front()
    del titles[IMAGES.hwnd]  # closed
    assert not Front(IMAGES)._book_in_front()


# ------------------------------------------------------------------ the batch
class FileTitledViewer(FakeViewer):
    """An image viewer: its window's title is the file it shows, "000.jpg" for the first page, "001.jpg" after one
    turn; for its first *hidden_polls* looks its window is minimised."""

    def __init__(self, pages: list[Image.Image], hidden_polls: int = 0):
        super().__init__(pages)
        self.hidden_polls = hidden_polls
        self.titles: list[str] = []

    def title(self, hwnd):
        self.titles.append(f"{self.index:03d}.jpg")
        return self.titles[-1]

    def shown(self, hwnd):
        self.hidden_polls -= 1
        return self.hidden_polls < 0


def _batch(viewer, settings, monkeypatch, class_name=PHOTOS):
    monkeypatch.setattr(batch_mod, "capture_window", viewer.capture)
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(batch_mod, "window_title", viewer.title)
    monkeypatch.setattr(batch_mod, "window_shown", viewer.shown)
    monkeypatch.setattr(batch_mod, "window_class", lambda hwnd: class_name)
    settings.settle_ms = 10
    settings.page_turn_wait_ms = 300
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    pipeline = batch_mod.Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    messages: list[str] = []
    reader = BatchReader(pipeline, hwnd=IMAGES.hwnd, settings=settings, title="000.jpg",
                         context_mode=False, on_progress=lambda p, r: messages.append(str(p.message)))
    reader.wait_poll_s = 0.01
    return reader, messages, cache


def _pages(sample_page, sample_page2):
    return [sample_page, sample_page2, sample_page.transpose(Image.FLIP_LEFT_RIGHT)]


def test_a_whole_book_run_in_an_image_viewer_goes_on_after_the_first_page_turn(sample_page, sample_page2, settings,
                                                                                 monkeypatch):
    viewer = FileTitledViewer(_pages(sample_page, sample_page2))
    reader, messages, cache = _batch(viewer, settings, monkeypatch)
    progress = read_book(reader)
    assert progress.finished and progress.pages == 3, progress
    assert "001.jpg" in viewer.titles and "002.jpg" in viewer.titles  # it was renamed with every page
    assert not any(m.startswith("Waiting") for m in messages)  # never waiting for "another tab"
    assert reader.viewer_class == PHOTOS and len(cache) == 3


def test_the_same_window_taken_for_a_browser_would_have_waited(sample_page, sample_page2, settings, monkeypatch):
    viewer = FileTitledViewer(_pages(sample_page, sample_page2))
    reader, messages, _cache = _batch(viewer, settings, monkeypatch, class_name="Chrome_WidgetWin_1")
    say = reader.on_progress

    def stop_when_waiting(progress, result):
        say(progress, result)
        if messages[-1].startswith("Waiting"):
            threading.Timer(0.05, reader.stop).start()

    reader.on_progress = stop_when_waiting
    progress = read_book(reader)
    assert progress.pages <= 1 and viewer.titles[-1] == "001.jpg"  # the browser's rule, unchanged
    assert any(m.startswith("Waiting: the viewer window shows '001.jpg' now, not the book") for m in messages)


def test_a_minimised_image_viewer_is_waited_for_with_its_own_line(sample_page, sample_page2, settings, monkeypatch):
    viewer = FileTitledViewer(_pages(sample_page, sample_page2), hidden_polls=3)
    reader, messages, _cache = _batch(viewer, settings, monkeypatch)
    progress = read_book(reader)
    assert progress.finished and progress.pages == 3, progress
    waiting = [m for m in messages if m.startswith("Waiting")]
    assert waiting == ["Waiting: the viewer's window is hidden or minimised; bring it back"]
    assert not any("tab" in m for m in messages) and any("back; carrying on" in m for m in messages)
    assert render(Message("batch.waiting_viewer_hidden"), catalog("ja")) == HIDDEN_JA.rstrip("。")


# ------------------------------------------------------------------ the profile: keys and area by the window's class
def test_a_file_name_title_keys_the_profile_on_the_window_class():
    assert names_a_file("000.jpg") and names_a_file("Scan_0012.PNG") and names_a_file("cover.webp")
    assert names_a_file("12") and names_a_file("12 / 200")
    assert not names_a_file("Yomizuq") and not names_a_file("notes.txt") and not names_a_file("")
    assert profile_names(IMAGES) == ("000.jpg", PHOTOS)  # the old whole-title entry first, then the class
    assert profile_names(_as(IMAGES, "001.jpg")) == ("001.jpg", PHOTOS)
    assert profile_names("000.jpg") == ("000.jpg",)  # a title alone, as before
    assert profile_names(_as(IMAGES, "page01.png - Photos")) == ("page01.png - Photos", "Photos")  # as before
    assert profile_names(_as(IMAGES, "My Reader")) == ("My Reader",)  # a viewer's own name: as before
    assert profile_names(CHROME) == profile_names(CHROME.title)  # a browser: as before
    assert profile_names(_as(CHROME, "001.jpg")) == ("001.jpg",)  # (a browser's tab: never its class)
    assert viewer_key(IMAGES) == viewer_key(_as(IMAGES, "001.jpg")) == PHOTOS  # the in-memory tables, the same
    assert viewer_key(CHROME) == viewer_key_from_title(CHROME.title)


def test_keys_and_area_set_for_000_are_found_for_001(tmp_path):
    settings = Settings(state_dir=tmp_path)
    p = Profiles(tmp_path / "profiles.json")
    p.set_keys(IMAGES, BUILTIN_PRESETS["left-to-right"])
    p.set_margins(IMAGES, (0, 40, 0, 0))
    again = Profiles(p.path)
    assert list(again.data) == [PHOTOS]
    for name in ("001.jpg", "002.jpg", "123.JPEG"):
        assert again.keys_for(_as(IMAGES, name), settings) == BUILTIN_PRESETS["left-to-right"]
        assert again.margins_for(_as(IMAGES, name)) == (0, 40, 0, 0)
        assert again.own_keys(_as(IMAGES, name))["next"] == "Right"
    # the Page keys dialog takes the viewer as its title: a title that knows its window's class
    title = viewer_title(_as(IMAGES, "005.jpg"))
    assert title == "005.jpg" and "Viewer: {title}".format(title=title) == "Viewer: 005.jpg"
    assert again.keys_for(title, settings).next == "Right" and again.key_of(title) == PHOTOS
    assert again.margins_for("001.jpg") is None  # a title alone has no class: as before


def test_a_profile_kept_under_the_file_name_before_is_found_first(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"000.jpg": {"margins": [0, 85, 0, 0]}}), encoding="utf-8")
    p = Profiles(path)
    assert p.margins_for(IMAGES) == (0, 85, 0, 0)  # the old entry, looked up first
    assert p.margins_for(_as(IMAGES, "001.jpg")) is None  # another file: the class, which has none yet
    p.set_keys(_as(IMAGES, "001.jpg"), PageKeys("Right", "Left"))
    assert sorted(json.loads(path.read_text(encoding="utf-8"))) == sorted(["000.jpg", PHOTOS])


# ------------------------------------------------------------------ the waiting line
class ImageKeys(Keys):
    def __init__(self, root):
        super().__init__(root)
        self.selected, self.in_front = IMAGES, False


def test_the_waiting_line_for_an_image_viewer_says_nothing_of_tabs(hidden_root, monkeypatch):
    sent = []
    monkeypatch.setattr(reading, "post_key", lambda hwnd, key: sent.append(key))
    monkeypatch.setattr(reading, "window_exists", lambda hwnd: True)
    w = ImageKeys(hidden_root)
    w.forward_key("Right")  # minimised: the key is not sent
    assert not sent and w.status_var.get() == HIDDEN
    i18n.set_language("ja")
    try:
        w.forward_key("Right")
        assert w.status_var.get() == HIDDEN_JA
    finally:
        i18n.set_language("en")
    w.selected = CHROME  # a browser window keeps its line about the tab
    w.forward_key("Right")
    assert w.status_var.get() == WAITING


def test_choosing_the_image_viewer_on_another_file_says_its_area_and_keys(hidden_root, tmp_path):
    from test_page_keys import Viewer

    w = Viewer(hidden_root, tmp_path)
    w.profiles.set_keys(IMAGES, BUILTIN_PRESETS["left-to-right"])  # set while it showed 000.jpg
    w.profiles.set_margins(IMAGES, (0, 85, 0, 0))
    w.windows = [_as(IMAGES, "001.jpg")]  # chosen again on the next file
    w._on_window_selected()
    assert w.selected.title == "001.jpg" and w.settings.margins == (0, 85, 0, 0)
    assert w.status_var.get() == ("Viewer: 001.jpg  (area set)  Page keys: "
                                  "→ next page, ← previous page.")
    assert w._page_keys().next == "Right"
