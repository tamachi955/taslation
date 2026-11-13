"""Where the window stands: a viewer changed, closed or kept during a run, the page a tool would act on, the lines that
say why nothing happened, the "To:" box kept between starts, the keys left with the page. The window's parts are borrowed
onto stand-ins; a hidden root where a real widget is wanted. No window of the reader's, no key."""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation.annotations import GlossaryStore
from taslation.cache import CacheStore
from taslation.capture import Enlarged, WindowInfo
from taslation.i18n import ui_settings_path
from taslation.regions import PageResult, TextRegion
from taslation.ui import app as app_mod
from taslation.ui import constants, live, reading, translator, viewers
from taslation.ui.dialogs import caches, glossary
from taslation.ui.dialogs.review import ReviewDialog
from taslation.ui.status import StatusMixin

A = app_mod.App
BOOK_A = WindowInfo(hwnd=1, title="Book A", class_name="Reader", pid=1, rect=(0, 0, 800, 600))
BOOK_B = WindowInfo(hwnd=2, title="Book B", class_name="Reader", pid=2, rect=(0, 0, 800, 600))
TAB_B = WindowInfo(hwnd=1, title="Book B", class_name="Reader", pid=1, rect=(0, 0, 800, 600))


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Box:
    """Stands in for the viewer list: what it shows, by index or as text."""

    def __init__(self):
        self.index, self.text = -1, None

    def current(self, index=None):
        if index is None:
            return self.index
        self.index, self.text = index, None

    def set(self, text):
        self.index, self.text = -1, text


class Chooser:
    """What choosing a viewer uses, down to the area it reads."""

    _on_window_selected = A._on_window_selected
    _learn_viewer = A._learn_viewer
    _title_book = A._title_book
    _enlarge_first = lambda self, then=None: True  # (the window enlarged: tests/test_enlarge.py)
    _learn_covered_soon = lambda self: None  # (whether the viewer draws while covered: tests/test_covered_viewer.py)
    _warm_page_models = A._warm_page_models
    _show_chosen = A._show_chosen
    _viewer_gone = A._viewer_gone
    _current_window = A._current_window
    set_area = A.set_area
    forward_key = A.forward_key
    _key_viewer = A._key_viewer
    _hand_over = A._hand_over
    _pass_on = A._pass_on
    _book_key = A._book_key

    def __init__(self, windows, selected=None, book="", edited=False, given=False):
        self.windows = list(windows)
        self.window_box = Box()
        self.selected = selected
        if selected is not None:
            self.window_box.index = next(i for i, w in enumerate(self.windows) if w.hwnd == selected.hwnd)
        self.book_var = Var(book)
        self._book_edited, self._book_given = edited, given
        self._book_scanned = True
        self._book_before = ""
        self.window_query = ""
        self.busy = False
        self.batch = None
        self._batching = False
        self.reading = self._reading_at_start = False
        self.profiles = SimpleNamespace(margins_for=lambda win, large=False: self.hand)
        self.hand = None
        self.settings = SimpleNamespace(margins=(0, 0, 0, 0))
        self.said, self.left, self.watching, self.followed = [], [], [], 0

    def say(self, key, **values):
        self.said.append(key)

    def status(self, line):
        self.said.append(line() if callable(line) else line)

    def after(self, ms, func):
        self.watching.append(func)

    def _viewer_left(self):
        self.left.append(self.selected)

    def _found_margins(self):
        return (5, 6, 7, 8)

    def _set_covered(self, covered):
        pass

    def _redisplay(self):
        pass

    def _follow_viewer(self):
        self.followed += 1

    def _watch_windows(self):
        pass

    def refresh_windows(self, select=None):
        pass

    def pick(self, window):
        self.window_box.index = self.windows.index(window)
        self._on_window_selected()


@pytest.fixture
def gone(monkeypatch):
    """The windows that are still there; the rest were closed."""
    alive = {1, 2}
    for module in (viewers, live, reading):
        monkeypatch.setattr(module, "window_exists", lambda hwnd: hwnd in alive)
    return alive


# ------------------------------------------------------------------ the book's name goes with the viewer
def test_choosing_another_viewer_does_not_keep_the_old_book(gone):
    w = Chooser([BOOK_A, BOOK_B], selected=BOOK_A, book="My name for A", edited=True)
    w.pick(BOOK_B)
    assert w.book_var.get() == "Book B" and not w._book_edited and w.left == [BOOK_A]


def test_a_tab_that_shows_another_book_takes_its_name(gone):
    w = Chooser([TAB_B], selected=BOOK_A, book="My name for A", edited=True)
    w.pick(TAB_B)
    assert w.book_var.get() == "Book B" and not w._book_edited and not w.left  # the same window stays enlarged


def test_the_same_viewer_chosen_again_keeps_the_name_typed(gone):
    w = Chooser([BOOK_A], selected=BOOK_A, book="My name for A", edited=True)
    w.pick(BOOK_A)
    assert w.book_var.get() == "My name for A" and w._book_edited


def test_a_book_given_at_the_command_line_stays_with_every_viewer(gone):
    w = Chooser([BOOK_A, BOOK_B], selected=BOOK_A, book="Given", edited=True, given=True)
    w.pick(BOOK_B)
    assert w.book_var.get() == "Given" and w._book_edited


def test_the_book_opened_again_keeps_the_name_typed(gone):
    reopened = WindowInfo(hwnd=2, title=BOOK_A.title, class_name="Reader", pid=2, rect=(0, 0, 800, 600))
    w = Chooser([BOOK_A], selected=BOOK_A, book="My name for A", edited=True)
    gone.discard(1)
    w._viewer_gone()
    w.windows = [reopened]
    w.pick(reopened)
    assert w.book_var.get() == "My name for A" and w._book_edited


def test_another_book_opened_after_the_viewer_was_closed_is_not_the_old_one(gone):
    w = Chooser([BOOK_A], selected=BOOK_A, book="My name for A", edited=True)
    gone.discard(1)
    w._viewer_gone()
    w.windows = [BOOK_B]
    w.pick(BOOK_B)
    assert w.book_var.get() == "Book B" and not w._book_edited


@pytest.mark.parametrize("before,after,edited", [("Book", "Book", False), ("Book", "Book 2", True)])
def test_only_a_key_that_changes_the_book_box_makes_it_the_readers(before, after, edited):
    w = Chooser([], book=before)
    w._book_key(SimpleNamespace(type=tk.EventType.KeyPress))
    w.book_var.set(after)
    w._book_key(SimpleNamespace(type=tk.EventType.KeyRelease))
    assert w._book_edited is edited and w._book_scanned is not edited


# ------------------------------------------------------------------ the viewer closed
def test_a_viewer_closed_is_said_and_watched_for_again(gone):
    w = Chooser([BOOK_A], selected=BOOK_A, book="Book A")
    w._waiting = True
    w._viewer_gone()  # still there: nothing
    assert w.selected is BOOK_A and not w.said
    gone.discard(1)
    w._viewer_gone()
    assert w.selected is None and w.left == [BOOK_A] and w.followed == 1 and not w._waiting
    assert w.said == [constants.VIEWER_CLOSED] and w.watching == [w._watch_windows] and w.window_box.text == ""
    w._viewer_gone()  # said once
    assert w.said == [constants.VIEWER_CLOSED]


def test_a_viewer_closed_during_a_run_waits_for_the_end_of_the_run(gone):
    w = Chooser([BOOK_A], selected=BOOK_A)
    w._batching = True
    gone.discard(1)
    w._viewer_gone()
    assert w.selected is BOOK_A and not w.said and not w.left


def test_a_key_or_a_request_finds_the_viewer_closed(gone, monkeypatch):
    shown = []
    monkeypatch.setattr(caches, "tell", lambda *a, **k: shown.append(a))
    w = Chooser([BOOK_A], selected=BOOK_A)
    gone.discard(1)
    w._book_in_front = lambda: False
    w.forward_key("Right")
    assert w.selected is None and w.said == [constants.VIEWER_CLOSED]
    w = Chooser([BOOK_A], selected=BOOK_A)
    assert w._current_window() is None and w.said == [constants.VIEWER_CLOSED] and len(shown) == 1


class Looks:
    """The looks at the viewer, which find it closed."""

    _poll = A._poll
    _look = A._look
    _take_notes = A._take_notes

    def __init__(self):
        self.selected = BOOK_A
        self.busy = False
        self.batch = None
        self._batching = False
        self.gone = 0
        self.settings = SimpleNamespace(auto_interval_ms=500, settle_ms=100)
        self.following = SimpleNamespace(look_at=None, owner="other",
                                         events=SimpleNamespace(take=lambda: [("closed", 1)], viewer=1))

    _black_open = lambda self: False

    def _follower(self):
        return self.following

    def _viewer_gone(self):
        self.gone += 1
        self.selected = None


def test_every_look_at_the_viewer_finds_it_closed(gone):
    gone.discard(1)
    for look in ("_poll", "_look"):
        w = Looks()
        getattr(w, look)()
        assert w.gone == 1
    w = Looks()
    w._take_notes(w.following)
    assert w.gone == 1 and w.following.look_at is None
    w = Looks()
    w._batching = True  # during a run: looked at again until it has ended
    w._look()
    assert w.gone == 0 and w.following.look_at is not None


# ------------------------------------------------------------------ what waits for the end of a run
def test_the_viewer_list_stays_during_a_run(gone):
    w = Chooser([BOOK_A, BOOK_B], selected=BOOK_A, book="Book A")
    w._batching = True
    w.pick(BOOK_B)
    assert w.selected is BOOK_A and w.window_box.current() == 0 and not w.left and w.book_var.get() == "Book A"
    assert w.said == ["The viewer cannot be changed during a run: press Stop first."]


def test_the_viewer_chosen_again_during_a_job_keeps_the_area_it_reads(gone):
    """A language switch chooses the same viewer again: a hand-set area must not replace the panel found inside it."""
    w = Chooser([BOOK_A], selected=BOOK_A)
    w.hand = (0, 85, 0, 0)
    w.settings.margins = (100, 120, 100, 40)  # the page panel found inside the reader's area
    for running in ("batch", "busy"):
        w.batch, w.busy = ("reader", False) if running == "batch" else (None, True)
        w.pick(BOOK_A)
        assert w.settings.margins == (100, 120, 100, 40) and not w.said
    w.batch, w.busy = None, False
    w.pick(BOOK_A)
    assert w.settings.margins == (0, 85, 0, 0)  # no job: as it always did


def test_set_area_waits_for_the_end_of_a_run(gone):
    w = Chooser([BOOK_A], selected=BOOK_A)
    w._batching = True
    w._enlarging = {"then": "the batch's start"}
    w.set_area()
    assert w.said == ["The area cannot be changed during a run: press Stop first."]
    assert w._enlarging["then"] == "the batch's start"  # the run's start is not dropped: the window cannot hang on it


def _store(tmp_path, *books):
    store = CacheStore(tmp_path / "cache")
    for book in books:
        cache = store.open(book, "m", "English")
        cache.set_details(title=book)
        cache.save()
    return store


def test_the_cache_a_run_reads_cannot_be_deleted(hidden_root, tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(caches, "ask", lambda *a, **k: asked.append(a) or True)
    store = _store(tmp_path, "Book")
    d = caches.CachesDialog(hidden_root, store, in_use=lambda book: book == "Book")
    d.withdraw()
    item = d.tree.get_children()[0]
    d.tree.selection_set(item)
    d._delete()
    assert d.backup_var.get() == "Book is being read by a run: press Stop first." and not asked
    assert d.tree.selection() == (item,) and store.list()
    d.destroy()


def test_delete_with_nothing_selected_says_so(hidden_root, tmp_path):
    d = caches.CachesDialog(hidden_root, _store(tmp_path, "Book"))
    d.withdraw()
    d._delete()
    assert d.backup_var.get() == "Select one in the list first."
    d.destroy()


# ------------------------------------------------------------------ the page a tool acts on
class Tools:
    """Translator mode's tools for the page on show."""

    toggle_order = A.toggle_order
    toggle_skip = A.toggle_skip
    retranslate_page = A.retranslate_page
    open_review = A.open_review
    _page_to_work_on = A._page_to_work_on
    _end_order = A._end_order
    _on_release = A._on_release

    def __init__(self, result=None, on_show=True, kept=True):
        self.last_result = result
        self.pipeline = SimpleNamespace(is_skipped=lambda r: False, set_page_skip=lambda r, skip: kept,
                                        set_reading_order=lambda r, order: kept, forget_page=lambda r: 1)
        self.on_show = on_show
        self.busy = self.reading = False
        self._ordering = self._review = None
        self._drag_start = self._drag_rect = self._grip = self._grip_start = None
        self.role_var = Var("translator")
        self.said, self.read, self.clicks = [], [], []
        self.editing = False

    def _result_on_show(self):
        return self.on_show

    def _editing(self):
        return self.editing

    def say(self, key, **values):
        self.said.append(key)

    def _label_order(self, text):
        pass

    def _redisplay(self):
        pass

    def _start_translate(self, image, complete=None):
        self.read.append(image)

    def _forward_click(self, event):
        self.clicks.append(event)


def test_the_page_tools_with_no_page_say_what_to_do(monkeypatch):
    for tool in ("toggle_order", "toggle_skip", "retranslate_page", "open_review"):
        w = Tools()
        getattr(w, tool)()
        assert w.said == ["Translate a page first: press F5."]


@pytest.mark.parametrize("tool", ["toggle_order", "toggle_skip", "retranslate_page"])
def test_a_tool_never_acts_on_a_page_that_is_not_on_show(tool, monkeypatch):
    monkeypatch.setattr(caches, "ask", lambda *a, **k: True)
    w = Tools(SimpleNamespace(original="the last result"), on_show=False)
    getattr(w, tool)()
    assert w.said == ["Translate this page first: press F5."] and not w.read and w._ordering is None


def test_skip_and_finish_order_under_a_generic_name_say_so():
    w = Tools(SimpleNamespace(original="page", units=[]), kept=False)
    w.toggle_skip()
    assert w.said == ["Give the book a name first (the Book field)."] and not w.read
    w.said.clear()
    w._ordering = ["a region"]
    w.toggle_order()
    assert w.said == ["Give the book a name first (the Book field)."] and w._ordering is None


def test_a_click_that_is_not_taslations_own_goes_to_the_viewer_in_either_role():
    w = Tools(SimpleNamespace(original="page"), on_show=False)
    w._drag_start = (10, 10)
    w._on_release(SimpleNamespace(x=10, y=10))
    assert len(w.clicks) == 1 and not w.said  # the Translator, a page not translated on show: it goes on
    w.role_var.set("reader")
    w._drag_start = (10, 10)
    w._on_release(SimpleNamespace(x=10, y=10))
    assert len(w.clicks) == 2  # the reader's clicks go on as ever
    w.role_var.set("translator")
    w.reading, w._drag_start = True, (10, 10)
    w._on_release(SimpleNamespace(x=10, y=10))
    assert len(w.clicks) == 3  # and so do those on the reading window
    w.reading, w.editing, w._drag_start = False, True, (10, 10)
    w._on_release(SimpleNamespace(x=10, y=10))
    assert len(w.clicks) == 3  # the translated page on show: the click is TASlation's (its text areas)
    w.editing, w._drag_start = False, (10, 10)
    w._on_release(SimpleNamespace(x=60, y=80))
    assert len(w.clicks) == 3  # a drag is no click


def test_edit_with_nothing_selected_says_so(hidden_root):
    region = SimpleNamespace(order=0)
    edited = []
    d = ReviewDialog(hidden_root, [(region, "why", "text")], on_edit=edited.append)
    d.withdraw()
    d._edit()
    assert d.hint_var.get() == "Select one in the list first." and not edited
    d.tree.selection_set("0")
    d._edit()
    assert d.hint_var.get() == "" and edited == [region]
    d.destroy()


def test_the_editor_refuses_a_region_of_a_page_gone():
    class Opener:
        _open_editor = A._open_editor
        last_result = SimpleNamespace(regions=[])
        pipeline = None
        said: list[str] = []

        def say(self, key, **values):
            self.said.append(key)

    w = Opener()
    w._open_editor(SimpleNamespace())
    assert w.said == [translator.NO_REGION]


def _region(box=(0, 0, 40, 40), status="translated"):
    x0, y0, x1, y1 = box
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), box, status=status)


def test_regions_alike_are_told_apart_by_identity_on_the_overlay():
    """Two regions with the same box, as a page read again gives: `==` would reach their masks and raise."""
    class Overlay:
        _overlay_items = A._overlay_items
        _page_regions = A._page_regions
        _noted_regions = A._noted_regions
        role_var = Var("translator")
        reading = False

    first, second, third = _region(), _region(), _region()
    third.reader_note = "a note"
    w = Overlay()
    w.last_result = SimpleNamespace(regions=[second, third])
    w._ordering = [first]
    labels = [label for _box, _colour, label in w._overlay_items()]
    assert labels == ["?", "? †1"]
    w._ordering = [third]
    assert [label for _box, _colour, label in w._overlay_items()] == ["?", "1 †1"]


# ------------------------------------------------------------------ the "To:" box
def test_the_first_start_takes_the_windows_language_and_it_is_kept(tmp_path):
    assert app_mod.first_target(tmp_path, "English", "fr", True) == "French"
    assert app_mod.first_target(tmp_path, "English", "de", False) == "French"  # kept from then on


def test_a_window_language_not_in_the_list_stays_with_the_default(tmp_path):
    assert app_mod.first_target(tmp_path, "English", "ja", True) == "English"
    assert not ui_settings_path(tmp_path).exists()


def test_a_later_start_with_nothing_chosen_keeps_the_default(tmp_path):
    assert app_mod.first_target(tmp_path, "English", "fr", False) == "English"


def test_the_language_given_on_the_command_line_wins(tmp_path):
    app_mod.first_target(tmp_path, "English", "fr", True)
    assert app_mod.first_target(tmp_path, "Korean", "fr", False) == "Korean"


def test_the_language_chosen_is_kept_for_the_next_start(tmp_path):
    class Target:
        _target_chosen = A._target_chosen
        settings = SimpleNamespace(state_dir=tmp_path)
        lang_var = Var("Klingon")
        _target_kept = "English"

    w = Target()
    w._target_chosen()
    assert json.loads(Path(ui_settings_path(tmp_path)).read_text(encoding="utf-8"))["translation"]["language"] == "Klingon"
    assert app_mod.first_target(tmp_path, "English", "en", False) == "Klingon"
    w.lang_var.set("  ")  # the box emptied: what was kept stays
    w._target_chosen()
    assert app_mod.first_target(tmp_path, "English", "en", False) == "Klingon"


# ------------------------------------------------------------------ the keys and the page
class Focus:
    _after_control = A._after_control
    _focus_page = A._focus_page
    _edit_key = A._edit_key

    def __init__(self, focus):
        self.focus = focus
        self.canvas = SimpleNamespace(focus_set=lambda: self.taken.append(1))
        self.taken, self.idle = [], []

    def focus_get(self):
        if isinstance(self.focus, Exception):
            raise self.focus
        return self.focus

    def after_idle(self, func):
        self.idle.append(func)
        func()


def test_a_control_of_the_window_gives_the_keys_back_to_the_page():
    w = Focus(None)
    own = SimpleNamespace(winfo_toplevel=lambda: w)
    w.focus = own
    w._after_control(SimpleNamespace(widget=own))
    assert w.taken == [1]


def test_a_dialog_keeps_the_keys_it_has():
    w = Focus(SimpleNamespace(winfo_toplevel=lambda: "a dialog"))
    w._after_control(SimpleNamespace(widget=SimpleNamespace(winfo_toplevel=lambda: w)))
    assert not w.taken
    w._after_control(SimpleNamespace(widget=SimpleNamespace(winfo_toplevel=lambda: "a dialog")))  # a dialog's own button
    assert not w.idle or len(w.idle) == 1
    w = Focus(KeyError("popdown"))  # a list's popdown has no widget of Tkinter's
    w._focus_page()
    assert not w.taken


def test_a_control_its_command_took_away_gives_the_keys_back_too():
    w = Focus(None)
    w._after_control(SimpleNamespace(widget="a path of a widget gone"))
    assert w.taken == [1]


def test_ctrl_z_in_a_box_leaves_the_pages_edits_alone(hidden_root):
    w = Focus(None)
    steps = []
    entry, box = ttk.Entry(hidden_root), ttk.Combobox(hidden_root)
    w._edit_key(SimpleNamespace(widget=entry), lambda: steps.append("undo"))
    w._edit_key(SimpleNamespace(widget=box), lambda: steps.append("undo"))
    assert not steps
    w._edit_key(SimpleNamespace(widget=ttk.Frame(hidden_root)), lambda: steps.append("undo"))
    assert steps == ["undo"]


# ------------------------------------------------------------------ what waits, and what is said
def test_reading_mode_refuses_a_queued_batch():
    class Entering:
        enter_reading = A.enter_reading
        reading = _batching = False
        selected = BOOK_A
        _queued = ("batch", ())
        said: list[str] = []
        notes: list[str] = []
        canvas = SimpleNamespace(set_note=lambda text, ms: Entering.notes.append(text))

        def say(self, key, **values):
            self.said.append(key)

        def _enlarge_first(self, then):
            raise AssertionError("the reading window must not start")

    w = Entering()
    w.enter_reading()
    assert w.said == ["Reading mode waits for the whole-book run to finish (Stop ends it)."] and len(w.notes) == 1


def test_the_batch_dialog_says_why_it_does_not_open_while_busy():
    class Busy:
        open_batch_dialog = A.open_batch_dialog
        busy = True
        said: list[str] = []

        def say(self, key, **values):
            self.said.append(key)

    w = Busy()
    w.open_batch_dialog()
    assert w.said == ["A job is running: wait for it to end, or press Stop."]


def test_closing_puts_the_enlarged_window_back_with_no_key_and_no_box(monkeypatch):
    class Closing:
        _restore_enlarged = A._restore_enlarged
        _keep_enlarged = A._keep_enlarged  # (kept for the next start: tests/test_enlarge_recovery.py)

        def __init__(self):
            self.said = []
            self._enlarged = Enlarged(1, (100, 100, 900, 700), (0, 0, 1920, 1032))

        def say(self, line, /, **values):
            self.said.append(line)

    boxes, restored = [], []
    monkeypatch.setattr(viewers, "restore_window", lambda enlarged: restored.append(enlarged.hwnd) or False)
    monkeypatch.setattr(caches, "tell", lambda _parent, text, **_k: boxes.append(text))
    w = Closing()
    w._restore_enlarged()
    assert restored == [1] and w._enlarged is None and not boxes and not w.said  # (one the reader resized stays)
    w._restore_enlarged()
    assert restored == [1]


def test_close_saves_the_style_guide_as_it_stands(hidden_root, tmp_path):
    store = GlossaryStore(tmp_path / "glossary")
    changes = []
    d = glossary.GlossaryDialog(hidden_root, store, "Series", "English", on_change=lambda: changes.append(1))
    d.withdraw()
    d._close()
    assert not changes  # nothing changed: nothing written
    d = glossary.GlossaryDialog(hidden_root, store, "Series", "English", on_change=lambda: changes.append(1))
    d.withdraw()
    d.tone_var.set("dry")
    d._close()
    assert changes == [1] and not d.winfo_exists()
    assert store.open("Series", "English").style.tone == "dry"


def test_a_language_switch_asks_before_it_closes_a_form(monkeypatch):
    class Switch:
        _on_ui_language = A._on_ui_language
        ui_lang_var = Var("de")
        rebuilt = 0

        def _open_forms(self):
            return ["the series sheet"]

        def _rebuild_ui(self):
            self.rebuilt += 1

    monkeypatch.setattr(caches, "ask", lambda *a, **k: False)
    w = Switch()
    w._on_ui_language()
    assert w.rebuilt == 0 and w.ui_lang_var.get() == "en"  # the choice is back on the language the window has


def _enlarged(changed=True):
    return SimpleNamespace(hwnd=1, changed=changed, given=None)


class Settling:
    _enlarge_done = A._enlarge_done
    _keep_enlarged = A._keep_enlarged  # (kept for the next start: tests/test_enlarge_recovery.py)
    _learn_covered_soon = lambda self: None  # (whether the viewer draws while covered: tests/test_covered_viewer.py)
    reading = False
    selected = BOOK_A

    def __init__(self, enlarged):
        self._enlarged = enlarged
        self.said, self.notes = [], []
        self.canvas = SimpleNamespace(set_note=lambda text, ms: self.notes.append(text))
        self._auto_last = self._auto_candidate = None

    def say(self, key, **values):
        self.said.append(key)

    _forget_page_area = _sync_area = _apply_found_margins = lambda self: None
    _look_afresh = lambda self, frame, thumb: None

    def settled(self):
        self._enlarging = {"enlarged": self._enlarged, "then": None}
        self._enlarge_done()


def test_a_window_that_jumps_is_explained_once(monkeypatch):
    monkeypatch.setattr(viewers, "window_rect", lambda hwnd: (0, 0, 1, 1))
    w = Settling(_enlarged())
    w.settled()
    w.settled()
    assert w.said == [viewers.ENLARGED] and w.notes == [viewers.ENLARGED]
    w = Settling(_enlarged(changed=False))  # one of a fixed size says that, not this
    w.settled()
    assert w.said == [viewers.KEPT_ITS_SIZE]


def test_a_page_partly_translated_says_what_is_left(hidden_root):
    page = Image.new("RGB", (40, 40), "white")
    regions = [_region(), _region(status="untranslated"), _region(status="untranslated")]
    result = PageResult(image=page, original=page, regions=regions, fingerprints=["f"], cache_misses=1)
    assert StatusMixin._summary(result).endswith("2 line(s) not translated yet: press F5.")
    regions[1:] = []
    assert "not translated yet" not in StatusMixin._summary(result)
