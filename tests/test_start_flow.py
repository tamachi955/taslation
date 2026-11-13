"""Before and around a whole-book scan: the names a window's title gives that name no book, the start dialog, the
setup check before the scan (nothing is scanned with a problem), the setup banner (checked
again off the Tk thread until fixed), every Message in the window's language, the scan band (the page, the bubbles
and the time left; the summary), Stop that cancels a page translation (and a new
page that does), the slow model's badge, and no busy title for a page from the cache. Parts of the App are borrowed
onto a stand-in on a withdrawn window of the shared hidden root."""
from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from types import SimpleNamespace

import pytest
from PIL import Image

from taslation.ui.constants import APP_TITLE, BOOK_READ_PAGES, READER_AFTER_RUN
from taslation import health, i18n
from taslation.annotations import AnnotationStore, GlossaryStore
from taslation.bookid import last_name
from taslation.cache import CacheStore, CachedBubble, CachedPage
from taslation.capture import WindowInfo
from taslation.config import Settings
from taslation.i18n import load_ui_language, save_ui_language, set_language
from taslation.messages import Cancelled, Message
from taslation.pagekeys import opposite_key
from taslation.regions import PageResult
from taslation import viewerparts
from taslation.ui import app as app_mod
from taslation.ui import banner, jobs, progress, taskbar, trouble
from taslation.ui.dialogs import caches
from taslation.ui.dialogs.batch import BatchDialog
from taslation.ui.dialogs.start import StartDialog, generic_book_name
from taslation.ui.preview import ImageCanvas
from taslation.ui.live import BlackViewerMixin

from conftest import FIXTURES

VIEWER = WindowInfo(hwnd=7, title="Yomizuq - Google Chrome", class_name="Chrome_WidgetWin_1", pid=7, rect=(0, 0, 800, 600))
URL = "http://127.0.0.1:11434"
DOWN = Message("health.ollama_down", url=URL)
OTHER = Message("health.other_model", wanted="qwen3.5:4b", used="gemma3:4b")
SLOW_JA = "翻訳プログラムの応答が遅れています（読み込み中かもしれません）。「停止」でこのページを取り消せます。"


def _frame(ink=(40, 30, 80, 70), size=(200, 150)):
    page = Image.new("RGB", size, "white")
    page.paste((20, 20, 20), ink)
    return page


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


A = app_mod.App


def button_texts(band) -> list[str]:
    """The labels of *band*'s buttons, left to right."""
    return [str(b.cget("text")) for b in band.buttons]


class TaskbarSeen:
    """A stand-in for ITaskbarList3: what the button was given."""

    def __init__(self):
        self.shown = []

    def set(self, hwnd, state, fraction):
        self.shown.append((state, round(fraction, 3)))


class Flow(BlackViewerMixin, tk.Toplevel):
    _raise_for_key = lambda self, hwnd: None  # (the viewer raised for a look: tests/test_wgc.py)

    """The parts of the App that a book's start, the setup checks and their banner, the scan band, Stop, a slow
    model and the busy signs use. What it would start elsewhere (a batch, Auto's next look) is recorded; `after`
    keeps its callbacks for the test to run."""

    _enlarge_first = lambda self, then=None: True  # (the window enlarged: tests/test_enlarge.py)
    _init_flow_state = A._init_flow_state
    _handle_event = A._handle_event
    _warn_unasked = A._warn_unasked
    _on_page_event = A._on_page_event
    _batch_done = A._batch_done
    _take_models = A._take_models
    _choose_model = A._choose_model
    _set_health = A._set_health
    _health_tick = A._health_tick
    _check_in_background = A._check_in_background
    _check_setup = A._check_setup
    _load_ocr_if_due = A._load_ocr_if_due
    _preflight = A._preflight
    _ollama_back = A._ollama_back
    _name_needed = A._name_needed
    _left_readings = A._left_readings
    _begin_book = A._begin_book
    _after_preflight = A._after_preflight
    _hold_scan = A._hold_scan
    _ask_book = A._ask_book

    def _recognised(self, *frames):
        """What the start dialog offers and what it says of it, all on the calling thread (the dialog itself waits
        for the worker: `_recognise_then`)."""
        request = self._recognition(*frames)
        return self._recognition_hint(request, jobs.recognised_books(request) if request.cached else None)

    _recognition = A._recognition
    _recognise_then = A._recognise_then
    _recognition_hint = A._recognition_hint
    _ask_name = A._ask_name
    _remember_viewer_name = A._remember_viewer_name
    _resume_start = A._resume_start
    _book_answer = A._book_answer
    _translate_pending = A._translate_pending
    _offer_colophon = A._offer_colophon
    _colophon_answer = A._colophon_answer
    _plan_rename = A._plan_rename
    _rename_book = A._rename_book
    _follow_rename = A._follow_rename
    _book_renamed = A._book_renamed
    _book_named = A._book_named
    _title_book = A._title_book
    _carry_colophon = A._carry_colophon
    _kept_under = A._kept_under
    _keep_details = A._keep_details
    _look_for_colophon = A._look_for_colophon
    translate_now = A.translate_now
    open_batch_dialog = A.open_batch_dialog
    open_glossary = A.open_glossary
    open_book_settings = A.open_book_settings
    _after_book_settings = A._after_book_settings
    _set_stop = A._set_stop
    _sync_stop = A._sync_stop
    stop_batch = A.stop_batch
    _stop_asks = A._stop_asks
    _run_pages = A._run_pages
    _ask_stop = A._ask_stop
    finish_reading = A.finish_reading
    translate_readings = A.translate_readings
    _held_readings = A._held_readings
    _show_taskbar = A._show_taskbar
    _pace = A._pace
    _keep_pace = A._keep_pace
    _book_start = A._book_start
    _keep_book_start = A._keep_book_start
    _queue = A._queue
    _run_queued = A._run_queued
    _start_translate = A._start_translate
    _job_translate = A._job_translate
    _job_batch = A._job_batch
    _use_model = A._use_model
    _loaded_line = A._loaded_line
    _area_of = A._area_of
    _turned_from_job = A._turned_from_job
    _watch_page = A._watch_page
    _follows_events = A._follows_events
    _say_waiting = A._say_waiting
    scan_mode = A.scan_mode
    close_band = A.close_band
    _page_keys = A._page_keys
    _on_new_page = A._on_new_page
    _book_read = A._book_read
    _all_cached = A._all_cached
    _completes = A._completes
    _warm_page_models = A._warm_page_models
    _reader_after_run = A._reader_after_run
    _post = A._post
    say = A.say
    status = A.status
    _summary = staticmethod(A._summary)
    _page_line = A._page_line
    _build_strips = A._build_strips
    _place_strip = A._place_strip
    _show_banner = A._show_banner
    _close_cpu_line = A._close_cpu_line
    _watch_trouble = A._watch_trouble
    restart_translator = A.restart_translator
    download_model = A.download_model
    _model_state = A._model_state
    _band_view = A._band_view
    _show_band = A._show_band
    _go_busy = A._go_busy
    _set_busy = A._set_busy
    _flush_busy = A._flush_busy
    _show_busy_signs = A._show_busy_signs
    _show_progress = A._show_progress
    _busy_text = A._busy_text
    _hide_busy = A._hide_busy

    def __init__(self, root, tmp_path):
        super().__init__(root)
        self.withdraw()
        self._init_flow_state()
        self.settings = Settings(state_dir=tmp_path / "state", scan_mode="book")
        viewerparts.change(lambda memory: memory.learn(LEARNED))  # this computer knows the viewers (`viewers_learned`)
        self.settings.settle_ms = 0
        self.taskbar_seen = TaskbarSeen()  # the taskbar button's bar, as the window would show it
        self._taskbar = taskbar.TaskbarProgress(lambda: 1, factory=lambda: self.taskbar_seen)
        self.store = CacheStore(self.settings.cache_dir)
        self.annotation_store = AnnotationStore(self.settings.annotations_dir)
        self.glossary_store = GlossaryStore(self.settings.glossary_dir)
        self.profiles = SimpleNamespace(data={}, path=tmp_path / "state" / "profiles.json")
        self.premises_changed: list[tuple] = []
        self._live = None
        self.canvas = ImageCanvas(self)
        self.canvas.winfo_width, self.canvas.winfo_height = (lambda: 400), (lambda: 300)
        for name, value in (("status_var", ""), ("book_var", "Yomizuq"), ("model_var", "qwen3.5:4b"),
                            ("lang_var", "English"), ("role_var", "reader")):
            setattr(self, name, tk.StringVar(self, value=value))
        self.auto_var = tk.BooleanVar(self, value=True)
        self.translate_btn, self.batch_btn, self.stop_btn, self.model_box = {}, {}, {}, {}
        self.progress_bar = Bar()
        self.ready, self.busy, self.reading, self.batch, self.pipeline = True, False, False, None, None
        self.selected = VIEWER
        self._book_scanned = self._book_edited = self._resume_auto = self._scan_waits_told = False
        self._batching = self._busy_shown = self._bar_shown = self._fill_dirty = False
        self._queued = self._fill = self.last_result = self._auto_last = self._auto_candidate = None
        self._job_frame = self._job_thumb = self._status_render = self._status_key = None
        self._chosen_region = self._grip_box = self._review = None
        self._progress, self._busy_since, self._models = "", 0.0, []
        self._events: queue.Queue = queue.Queue()
        self._jobs: queue.Queue = queue.Queue()
        self.titles: list[str] = []
        self.batches: list[tuple] = []
        self.ticks = 0
        self.uncached = True
        self.frame = _frame()
        self.later: list = []
        self._build_strips()

    # what the stand-in does not do itself
    def title(self, text=None):  # recorded (Tk names the window once as it is made: before __init__ has run)
        if text is not None:
            self.__dict__.setdefault("titles", []).append(text)

    def after(self, ms, func=None, *args):
        self.later.append((ms, func))
        return f"after#{len(self.later)}"

    def after_cancel(self, _id):
        pass

    def run_later(self, limit=500):
        """Run what was put off with `after`, in order, until nothing is left (at most *limit* callbacks)."""
        for _ in range(limit):
            if not self.later:
                return
            _ms, func = self.later.pop(0)
            func()
        raise AssertionError("still running")

    def _start_batch(self, *options):
        self.batches.append(options)

    def _tick(self):
        self.ticks += 1

    def _page_uncached(self, image):
        return self.uncached

    def _capture(self, hwnd):
        return self.frame

    def _book_in_front(self):
        return True

    def _current_window(self):
        return self.selected

    def _capture_failed(self, error):
        raise AssertionError(f"no capture fails here: {error}")

    def _premises_changed(self, book, language):
        self.premises_changed.append((book, language))

    def _own_hwnd(self):
        return None

    def _show_live(self, image, thumb=None):
        pass

    def _redisplay(self):
        pass

    def _show_notes(self):
        pass

    def _apply_found_margins(self):
        pass

    def _settle_live(self, result):
        pass

    def _sync_guard(self):
        pass

    def _area_hint_due(self):
        return False

    def _font_note(self):
        return ""

    def _ensure_cache(self, book, model, language):
        return True  # the book's stores are open

    def run_jobs(self):
        """The worker's jobs now, then the events they posted (as the event pump takes them)."""
        while not self._jobs.empty():
            self._jobs.get()()
        self.pump()

    def asked(self):
        """The start dialog once what it waits for is in: the set-up check (whole-book mode) and the book on screen
        recognised (`_recognise_then`), both in the worker, with their events; the last dialog (None: none)."""
        for _ in range(4):
            if not (self._checks or self._recognising):
                break
            self.run_jobs()
        return self.dialogs[-1] if self.dialogs else None

    def pump(self):
        while not self._events.empty():
            kind, data = self._events.get()
            self._handle_event(kind, data)


@pytest.fixture
def flow(hidden_root, tmp_path, monkeypatch):
    """A stand-in window, and a start dialog that is recorded instead of shown (answered by the test)."""
    dialogs = []

    class Recorded:
        def __init__(self, master, name, generic, ask, on_answer, matches=(), hint="", default="page"):
            self.name, self.generic, self.ask, self.on_answer = name, generic, ask, on_answer
            self.default = default
            self.matches, self.hint = list(matches), hint
            dialogs.append(self)

    monkeypatch.setattr(jobs, "StartDialog", Recorded)
    w = Flow(hidden_root, tmp_path)
    w.dialogs = dialogs
    yield w
    set_language("en")


LEARNED = ("Yomizuq", "FOLIO☆QAT", "Yomizuq Cloud Reader")  # invented viewers, as this computer learned them


@pytest.fixture(autouse=True)
def viewers_learned():
    """This computer has learned the viewers of `LEARNED` (how: tests/test_viewer_parts.py): their names name no
    book, as a browser's never does."""
    viewerparts.change(lambda memory: memory.learn(LEARNED))


def _no_problems(monkeypatch, problems=()):
    asked = []
    monkeypatch.setattr(jobs, "preflight", lambda settings, model=None: asked.append(settings) or list(problems))
    return asked


# ------------------------------------------------------------------ names, keys, numbers, remembered choices
def test_generic_names_name_no_book():
    for name in ("untitled", "", "  ", "Google Chrome", "Microsoft Edge", "Microsoft\u200b Edge", "Firefox",
                 "Mozilla Firefox", "New Tab", "Yomizuq for PC"):  # on any computer (a program "for PC")
        assert generic_book_name(name), name
    for name in ("Yomizuq", "yomizuq", "FOLIO☆QAT", "Yomizuq Cloud Reader", "Yomizuq - FOLIO☆QAT", "YOMIZUQ\u200b"):
        assert generic_book_name(name), name  # the viewers this computer learned (`viewers_learned`)
    for name in ("見本の冒険 1", "My Story 2巻", "Yomizuq Reader's Guide", "Edge of the Pebble Sea", "Brave Story 1",
                 "Brave Story 1 - Yomizuq", "Opera Night"):
        assert not generic_book_name(name), name
    viewerparts.use(None)  # nothing learned: a viewer's name is a name like any other
    assert not generic_book_name("Yomizuq") and not generic_book_name("FOLIO☆QAT")
    assert generic_book_name("Google Chrome") and generic_book_name("")


def test_the_opposite_key_and_the_numbers_of_the_band():
    assert opposite_key("Left") == "Right" and opposite_key("right") == "Left"
    assert opposite_key("PageDown") == "PageUp" and opposite_key("Space") is None
    assert opposite_key("") is None and opposite_key(None) is None
    assert banner.group_digits(1900, "en") == "1,900" and banner.group_digits(1900, "ja") == "1,900"
    assert banner.group_digits(1900, "de") == "1.900" and banner.group_digits(1900, "fr") == "1 900"
    assert banner.group_digits(1900, "es") == "1900" and banner.group_digits(19000, "es") == "19.000"
    assert banner.group_digits(23, "en") == "23" and banner.group_digits(1234567, "ru") == "1 234 567"
    assert banner.duration_text(35 * 60) == "35 min" and banner.duration_text(10) == "1 min"
    assert banner.duration_text(65 * 60) == "1 h 5 min"
    set_language("ja")
    try:
        assert banner.duration_text(35 * 60) == "35分" and banner.duration_text(125 * 60) == "2時間5分"
    finally:
        set_language("en")


def test_an_old_kept_answer_stays_in_ui_json_and_means_nothing(tmp_path):
    (tmp_path / "ui.json").write_text('{"whole_book": "page"}', encoding="utf-8")  # "Don't ask again", once
    save_ui_language(tmp_path, "de")
    assert json.loads((tmp_path / "ui.json").read_text(encoding="utf-8")) == {"whole_book": "page", "language": "de"}
    assert load_ui_language(tmp_path) == "de"
    (tmp_path / "ui.json").write_text("[1, 2]", encoding="utf-8")  # not ours: nothing, and it is not kept
    assert load_ui_language(tmp_path) is None
    save_ui_language(tmp_path, "ja")
    assert json.loads((tmp_path / "ui.json").read_text(encoding="utf-8")) == {"language": "ja"}


# ------------------------------------------------------------------ the start dialog
def test_the_start_dialog_asks_for_a_name_when_the_title_gives_none(hidden_root):
    answers = []
    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=True, on_answer=lambda *a: answers.append(a))
    d.withdraw()
    start, page = d.buttons
    assert d.name_var.get() == "" and str(start.cget("state")) == "disabled" == str(page.cget("state"))
    d._answer("start")  # no name: nothing happens
    assert not answers and d.winfo_exists()
    d.name_var.set("  見本の冒険   1 ")
    assert str(start.cget("state")) == "normal" and str(start.cget("text")) == "Start"
    assert str(page.cget("text")) == "Page by page instead"
    d._answer("start")
    assert answers == [("start", "見本の冒険 1")] and not d.winfo_exists()

    d = StartDialog(hidden_root, "My Story 2", generic=False, ask=True, on_answer=lambda *a: answers.append(a))
    d.withdraw()
    assert d.name_var.get() == "My Story 2" and str(d.buttons[0].cget("state")) == "normal"
    d._close()  # Esc or the close button: no answer
    assert answers[-1] == (None, "My Story 2")

    set_language("ja")
    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=False, on_answer=lambda *a: answers.append(a))
    d.withdraw()
    texts = [str(w.cget("text")) for w in d.winfo_children()[0].winfo_children() if w.winfo_class() == "TLabel"]
    assert "".join(texts[0].split("\n")).startswith("この本の名前は何ですか？")
    assert [str(b.cget("text")) for b in d.buttons] == ["OK"]  # the name alone
    d.name_var.set("鋼の錬金術師 3")
    d._answer(d.default)  # what Enter does
    assert answers[-1] == ("ok", "鋼の錬金術師 3")


def test_the_batch_dialog_has_no_choice_but_how_far_and_presses_nothing(hidden_root, tmp_path):
    started = []
    d = BatchDialog(hidden_root, VIEWER, Settings(state_dir=tmp_path), on_start=started.append)
    d.withdraw()
    assert not [w for w in _widgets(d) if w.winfo_class() in ("TCheckbutton", "TEntry")]
    assert not hasattr(d, "key_line") and "reads better" in str(d.size_line.cget("text")).replace("\n", " ")
    next(w for w in _widgets(d) if w.winfo_class() == "TButton" and str(w.cget("text")) == "Start").invoke()
    assert started == [(VIEWER, Settings().batch_max_pages, True)]  # read, then translated

    # taken off in the config file: the dialog goes by it, as the start of a book does
    d = BatchDialog(hidden_root, VIEWER, Settings(state_dir=tmp_path, context_mode=False), on_start=started.append)
    d.withdraw()
    next(w for w in _widgets(d) if w.winfo_class() == "TButton" and str(w.cget("text")) == "Start").invoke()
    assert started[-1][1:] == (Settings().batch_max_pages, False)


TERMS_EN = "A store's terms of use are a contract between you and the store. In a whole-book run TASlation turns no page: it reads only the pages you turn yourself. That does not settle what your store's terms allow, so check them and use this mode knowing that."
TERMS_JA = 'ストアの利用規約は、あなたとストアの契約です。1冊まるごと読むときも TASlation はページをめくらず、あなたがめくったページだけを読み取ります。ただし、それでストアの規約上問題がないと決まるわけではありません。規約を確認し、そのことを承知のうえで使ってください。'


def _label_texts(top):
    """The dialog's labels as read, their lines joined again (`break_lines` wraps them: a space at an English break)."""
    texts = [str(w.cget("text")) for w in _widgets(top) if w.winfo_class() == "TLabel"]
    return [" ".join(t.split("\n")) for t in texts], ["".join(t.split("\n")) for t in texts]


def test_page_by_page_is_the_default_and_whole_book_mode_an_opt_in():
    from pathlib import Path

    from taslation.cli import build_parser

    assert Settings().scan_mode == "page" and Settings(scan_mode="book").scan_mode == "book"
    assert Settings.from_toml(Path(__file__).resolve().parent.parent / "taslation.toml.example").scan_mode == "page"
    assert build_parser().parse_args(["gui"]).mode is None  # the setting's: page by page
    assert build_parser().parse_args(["gui", "--mode", "book"]).mode == "book"
    for setting in ("book", "page"):  # the settings say, `gui --mode book` among them: the window has no choice of it
        assert app_mod.App.scan_mode(SimpleNamespace(settings=Settings(scan_mode=setting))) == setting


def test_the_whole_book_question_says_what_a_stores_terms_make_of_it(hidden_root):
    for code, note in (("en", TERMS_EN), ("ja", TERMS_JA)):
        set_language(code)
        try:
            for generic in (False, True):
                d = StartDialog(hidden_root, "Yomizuq" if generic else "My Story 2", generic=generic, ask=True,
                                on_answer=lambda *a: None)
                d.withdraw()
                spaced, joined = _label_texts(d)
                assert note in (spaced if code == "en" else joined), (code, generic)
                labels = [w for w in d.winfo_children()[0].winfo_children() if w.winfo_class() == "TLabel"]
                assert labels[-1] is d.terms_label  # under the question
                question = "".join(str(labels[-2].cget("text")).split("\n"))
                assert question.startswith("Read the whole book first?" if code == "en" else "先に本全体を読みますか？")
                # the one box there is, with a generic title, is the colophon's
                assert len([w for w in _widgets(d) if w.winfo_class() == "TCheckbutton"]) == (1 if generic else 0)
                d.destroy()
            d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=False, on_answer=lambda *a: None)
            d.withdraw()  # the name alone (page-by-page mode): no question, no note
            assert note not in _label_texts(d)[0] and note not in _label_texts(d)[1]
            d.destroy()
        finally:
            set_language("en")


def test_the_batch_dialog_says_it_above_start(hidden_root, tmp_path):
    for code, note in (("en", TERMS_EN), ("ja", TERMS_JA)):
        set_language(code)
        try:
            d = BatchDialog(hidden_root, VIEWER, Settings(state_dir=tmp_path), on_start=lambda options: None)
            d.withdraw()
            spaced, joined = _label_texts(d)
            assert (note in spaced) if code == "en" else (note in joined), code
            assert max(len(line) for line in str(d.terms_label.cget("text")).split("\n")) < len(note)  # wrapped
            d.destroy()
        finally:
            set_language("en")


def _widgets(top):
    found, stack = [], [top]
    while stack:
        w = stack.pop()
        found.append(w)
        stack.extend(w.winfo_children())
    return found


# ------------------------------------------------------------------ a book's start
def test_whole_book_mode_checks_the_setup_then_asks_then_reads_the_whole_book(flow, monkeypatch):
    asked = _no_problems(monkeypatch)
    page = _frame()
    flow._on_new_page(page, "thumb")
    assert flow._start_pending == (page, "thumb") and not flow.dialogs and not asked  # the check runs in the worker
    later = _frame(ink=(100, 30, 150, 70))
    flow._on_new_page(later, "later")  # a page turned meanwhile waits for the start, nothing else happens
    assert flow._start_pending == (later, "later") and flow._jobs.qsize() == 1
    flow.run_jobs()
    assert len(asked) == 1 and not flow.dialogs and flow._jobs.qsize() == 1  # the page recognised in the worker
    flow.run_jobs()
    assert len(flow.dialogs) == 1
    d = flow.dialogs[0]
    assert d.generic and d.ask and d.name == "Yomizuq"
    d.on_answer("start", "見本の冒険 1")
    assert flow.book_var.get() == "見本の冒険 1" and flow._book_edited and flow._book_scanned
    assert flow._resume_auto and flow._start_pending is None
    assert flow.batches == [(VIEWER, 0, True)]
    flow._on_new_page(page, "thumb")  # decided for this book: Auto's pages are translated as they come
    assert flow.busy and flow._jobs.qsize() == 1 and len(flow.dialogs) == 1


def _translated_pages(flow, book, count):
    cache = flow.store.open(book, flow.model_var.get(), "English")
    for i in range(count):
        cache.add(CachedPage(f"{i:02x}" * 40, 0.7, [CachedBubble((0.1, 0.1, 0.2, 0.2), f"Line {i}")], seq=i))
    cache.save()


def test_a_book_read_already_translates_a_page_it_lacks_as_a_page_with_no_start_dialog(flow, monkeypatch):
    """Reopening a book read through: the cover (lines, none translated) or a page skipped is not in the cache, yet
    no whole-book start is offered over the translated pages - the page is translated as a page."""
    asked = _no_problems(monkeypatch)
    flow.book_var.set("My Story 2")
    _translated_pages(flow, "My Story 2", BOOK_READ_PAGES)
    flow._on_new_page(_frame(), None)
    assert flow.busy and flow._jobs.qsize() == 1 and not flow.dialogs and not asked and flow._start_pending is None
    assert not flow.batches


def test_a_book_with_only_a_few_pages_translated_is_offered_the_whole_book_start(flow, monkeypatch):
    _no_problems(monkeypatch)
    flow.book_var.set("My Story 2")
    _translated_pages(flow, "My Story 2", 3)  # a cover and a page or two tried with F5
    flow._on_new_page(_frame(), None)
    d = flow.asked()
    assert d is not None and d.ask and not d.generic
    flow.settings.cache_enabled = False  # nothing can be told: offered as ever
    assert not flow._book_read()


def test_a_setup_problem_stops_the_scan_and_the_window_goes_page_by_page(flow, monkeypatch):
    _no_problems(monkeypatch, [DOWN, OTHER])
    set_language("ja")
    flow._on_new_page(_frame(), None)
    flow.run_jobs()
    assert not flow.dialogs and not flow.batches  # nothing is scanned
    assert flow.busy and flow._jobs.qsize() == 1  # this page is translated as it is
    held = "まだ1冊まるごとは読み取りません。先にページの上の表示に従って問題を解決してください。それまでは1ページずつ翻訳します。"
    lines = flow.setup_banner.texts()  # the problems, then why the window goes page by page (it stays there)
    assert lines == [progress.rendered(DOWN), trouble.setup_line(OTHER), held]  # (Download model: not install.cmd)
    assert lines[0].startswith("翻訳プログラムが動いていないため")
    colours = [str(label.cget("bg")) for label in flow.setup_banner.labels]
    assert colours == [banner.PROBLEM_COLOURS[0], banner.NOTICE_COLOURS[0], banner.NOTICE_COLOURS[0]]
    assert flow.setup_banner.winfo_manager() == "pack" and not flow._book_scanned  # asked again once fixed
    flow._handle_event("health", {"problems": [OTHER], "checked": True})  # Ollama runs now
    assert flow.setup_banner.texts() == [trouble.setup_line(OTHER)] and not flow._scan_held


def test_the_notice_alone_does_not_stop_the_scan(flow, monkeypatch):
    _no_problems(monkeypatch, [OTHER])
    flow._on_new_page(_frame(), None)
    flow.asked()
    assert len(flow.dialogs) == 1 and flow.setup_banner.texts() == [trouble.setup_line(OTHER)]


def test_whole_book_mode_asks_for_every_book_and_ignores_an_old_kept_answer(flow, monkeypatch):
    _no_problems(monkeypatch)
    ui = flow.settings.state_dir / "ui.json"
    ui.parent.mkdir(parents=True, exist_ok=True)
    ui.write_text('{"whole_book": "page"}', encoding="utf-8")  # "Don't ask again", once
    flow._on_new_page(_frame(), None)
    d = flow.asked()
    assert d.ask and d.generic
    d.on_answer("page", "My Story 2")
    assert flow.busy and not flow.batches and flow.book_var.get() == "My Story 2"  # this page, as it is
    flow._handle_event("translate_done", {})
    flow._jobs = queue.Queue()

    # the next book (its name typed into the Book box): asked again
    flow.book_var.set("My Story 3")
    flow._on_new_page(_frame(), None)
    flow.run_jobs()
    assert len(flow.dialogs) == 2 and flow.dialogs[-1].ask and not flow.dialogs[-1].generic
    flow.dialogs[-1].on_answer("page", "My Story 3")
    flow._handle_event("translate_done", {})
    flow._jobs = queue.Queue()
    assert flow._book_scanned and flow._scanned_book == "My Story 3"

    # a book whose tab title gives only the viewer's name: the name and the question, an old "start" or not
    ui.write_text('{"whole_book": "start"}', encoding="utf-8")
    flow.book_var.set("Yomizuq")
    flow._book_edited = False
    flow._on_new_page(_frame(), None)
    d = flow.asked()
    assert len(flow.dialogs) == 3 and d.generic and d.ask
    d.on_answer("start", "Vagabond 4")
    assert flow.book_var.get() == "Vagabond 4" and flow.batches == [(VIEWER, 0, True)]


def test_page_by_page_mode_asks_only_for_a_missing_name(flow, monkeypatch):
    asked = _no_problems(monkeypatch)
    flow.settings.scan_mode = "page"
    flow.book_var.set("My Story 2")  # a real name: the page is translated at once
    flow._on_new_page(_frame(), None)
    assert flow.busy and not flow.dialogs and not asked
    flow._handle_event("translate_done", {})
    flow._jobs = queue.Queue()
    flow.book_var.set("Yomizuq")
    flow._on_new_page(_frame(), None)
    assert flow._jobs.qsize() == 1 and not flow.dialogs  # the page recognised in the worker first
    flow.run_jobs()
    assert not flow._jobs.qsize() and len(flow.dialogs) == 1 and not flow.dialogs[0].ask and not asked
    flow.dialogs[0].on_answer("ok", "Vagabond 4")
    assert flow.book_var.get() == "Vagabond 4" and flow.busy and not flow.batches and not flow._book_scanned


def test_closing_the_start_dialog_reads_nothing_and_asks_again(flow, monkeypatch):
    _no_problems(monkeypatch)
    flow._on_new_page(_frame(), None)
    flow.asked()
    flow.dialogs[0].on_answer(None, "")
    assert not flow.busy and not flow.batches and flow.book_var.get() == "Yomizuq" and flow._start_pending is None
    assert flow.status_var.get().startswith("Nothing was read yet: TASlation asks again at the next page.")
    flow._on_new_page(_frame(), None)
    flow.asked()
    assert len(flow.dialogs) == 2


def test_the_scan_checks_the_setup_again_and_does_not_start_with_a_problem(flow, monkeypatch):
    _no_problems(monkeypatch, [Message("health.ocr_missing", path="/models/manga-ocr")])
    monkeypatch.setattr(jobs, "BatchReader", lambda *a, **k: pytest.fail("no batch may start"))
    flow._batching, flow.busy, flow._resume_auto = True, True, True
    flow._auto_before_batch = True
    flow.auto_var.set(False)
    flow._job_batch(VIEWER.hwnd, "Book", "m", "English", 0, True, True)
    kinds = [kind for kind, _data in list(flow._events.queue)]
    assert kinds == ["health", "batch_refused"]
    flow.pump()
    assert not flow._batching and not flow.busy and flow.auto_var.get() and not flow._resume_auto
    assert flow.setup_banner.texts()[0].startswith("The part that reads Japanese is missing") and flow._band is None
    assert flow.setup_banner.texts()[1].startswith("The whole book is not read yet")
    assert flow.status_var.get().startswith("The whole book is not read yet")


# ------------------------------------------------------------------ a book's files that cannot be opened now
class Locked:
    """A store whose book file exists but cannot be opened now (locked, no permission) - or holds another book's."""

    def __init__(self, error=None):
        self.error = error or PermissionError(13, "Permission denied", "C:/state/cache/Book.json")

    def open(self, *_args):
        raise self.error

    def load(self, *_args):
        return []


class Opens:
    def open(self, *args):
        return SimpleNamespace(name=args, format=lambda: "sheet")

    def load(self, *_args):
        return []


class BookState:
    """A pipeline's book state, as `_ensure_cache` and `_job_refresh_premises` hand it over."""

    def __init__(self):
        self.cache, self.ocr = None, object()
        self.glossary, self.glossary_text, self.annotations = "old sheet", "old", "old marks"

    def set_cache(self, cache):
        self.cache = cache

    def reset_context(self):
        pass

    def set_annotations(self, annotations):
        self.annotations = annotations

    def process(self, *args, **kwargs):
        raise AssertionError("nothing may be translated")


def test_a_book_file_that_cannot_be_opened_is_said_and_nothing_is_read(flow, monkeypatch):
    flow._ensure_cache = A._ensure_cache.__get__(flow)  # the real one, not the stand-in's
    flow._job_refresh_premises = A._job_refresh_premises.__get__(flow)
    flow.pipeline, flow.translator = BookState(), SimpleNamespace(model="", target_language="English")
    flow.store, flow.annotation_store, flow.glossary_store = Locked(), Opens(), Opens()
    flow._job_translate(_frame(), "Book", "m", "English")  # a page: nothing translated, the status line says why
    assert [kind for kind, _data in list(flow._events.queue)] == ["status", "translate_done"]
    set_language("ja")
    flow.pump()
    assert flow.status_var.get().startswith("Book 用に TASlation が保存しているファイルを開けません: [Errno 13]")
    assert "何も翻訳していません" in flow.status_var.get() and flow.pipeline.cache is None
    set_language("en")
    assert flow._status_render().startswith("Could not open the files TASlation keeps for Book: [Errno 13]")

    _no_problems(monkeypatch)  # a whole-book scan: refused before the first page is turned, not asked again
    monkeypatch.setattr(jobs, "BatchReader", lambda *a, **k: pytest.fail("no batch may start"))
    flow._batching = flow.busy = flow._resume_auto = flow._book_scanned = True
    flow._job_batch(VIEWER.hwnd, "Book", "m", "English", 0, True, True)
    assert [kind for kind, _data in list(flow._events.queue)] == ["health", "status", "batch_refused"]
    flow.pump()
    assert not flow._batching and not flow.busy and flow._book_scanned and not flow._scan_held
    assert flow.status_var.get().startswith("Could not open the files TASlation keeps for Book:")
    assert flow.setup_banner.texts() == []

    flow.store = Opens()  # the premises after a change in the series sheet: another book's file in the way
    flow.glossary_store = Locked(FileExistsError("glossary.json holds the sheet of 'Other', not that of 'Book'"))
    flow._job_refresh_premises("Book", "English")
    flow.pump()
    assert flow.pipeline.glossary == "old sheet" and flow.pipeline.annotations == "old marks"  # kept as it was
    assert flow.status_var.get() == ("Could not open the files TASlation keeps for Book: glossary.json holds the sheet "
                                     "of 'Other', not that of 'Book'. The translations go on with the book's premises "
                                     "as they were.")
    flow.glossary_store = Opens()
    flow._job_refresh_premises("Book", "English")
    assert flow.pipeline.glossary_text == "sheet" and flow.pipeline.annotations.name == ("Book",)


# ------------------------------------------------------------------ the setup banner
def test_the_banner_is_checked_again_off_the_tk_thread_until_fixed(flow, monkeypatch):
    seen = []

    def check(settings, model=None, url=None, timeout=1.0, language=None):
        seen.append(threading.current_thread() is threading.main_thread())
        return [] if len(seen) > 1 else [DOWN]

    monkeypatch.setattr(health, "check", check)
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: ["qwen3.5:4b"])
    flow._handle_event("health", {"problems": [DOWN]})
    assert flow.setup_banner.texts() == [str(DOWN)] and [ms for ms, _f in flow.later] == [jobs.HEALTH_RECHECK_MS]
    for _attempt in range(2):
        _ms, tick = flow.later.pop(0)
        tick()  # the check starts in a thread of its own; its result comes as an event
        deadline = time.monotonic() + 5
        while flow._events.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        flow.pump()
    assert seen == [False, False]  # never on the Tk thread
    assert flow.setup_banner.texts() == [] and flow.setup_banner.winfo_manager() == ""  # fixed: the line has gone
    assert not flow.later and flow._models == ["qwen3.5:4b"]  # no more checks; Ollama's models are known


def test_the_banner_speaks_the_windows_language_and_says_it_again_after_a_switch(flow):
    set_language("ja")
    flow._handle_event("health", {"problems": [DOWN]})
    assert flow.setup_banner.texts()[0].startswith("翻訳プログラムが動いていないため")
    set_language("de")
    flow._show_banner()  # what _rebuild_ui does
    assert flow.setup_banner.texts()[0].startswith("Das Übersetzungsprogramm läuft nicht,")


# ------------------------------------------------------------------ Messages in the window's language
def test_every_message_in_the_status_line_is_in_the_windows_language(flow):
    set_language("ja")
    flow.say(Message("batch.scanning_page", page=3))
    assert flow.status_var.get() == "3 ページ目を読み取り中..."
    set_language("de")
    assert flow._status_render() == "Seite 3 wird eingelesen..."  # said again after a switch
    flow.say("Viewer: {error}", error=jobs.CaptureError(Message("viewer.closed")))  # an error's Message too
    assert flow.status_var.get() == i18n.tr("Viewer: {error}").format(error="das Viewer-Fenster wurde geschlossen")
    set_language("ja")
    assert progress.stage_of(Message("pipeline.stage_reading", done=1, total=3)) == "3 行を読み取り中"
    assert progress.busy_line(Message("pipeline.stage_translating", bubbles=5, translator="t"), 3, filled=2) == (
        "翻訳中... 5 行中 2 行完了（3 秒）")
    assert progress.reads_page(Message("pipeline.stage_translating", bubbles=2, translator="t"))
    assert not progress.reads_page(Message("pipeline.stage_finding"))
    assert progress.progress_line(Message("pipeline.stage_rendering")) == "写植中..."
    assert progress.progress_line(Message("pipeline.no_translator")) == "翻訳エンジンが設定されていません"
    assert progress.busy_line(Message("ollama.slow", seconds=20), 25) == SLOW_JA


def test_the_page_summary_reads_as_the_review_asked(flow):
    from taslation.regions import PageResult

    result = PageResult(image=_frame(), original=_frame(), regions=[])
    result.fingerprints, result.cache_hits, result.cache_misses = ["a" * 16], 1, 0
    result.timings = {"render": 0.1}
    result.regions = []
    set_language("ja")
    assert flow._summary(result) == "このページに文字はありません。"
    result.cache_misses = 1
    result.error = Message("ollama.unreachable", url=URL)
    assert flow._summary(result) == ("0 行を翻訳しました（0 秒）。 - "
                                     "TASlation から翻訳プログラムに接続できませんでした。少し待って F5 を押してください。プログラムは自動で起動します。")
    result.fingerprints = []
    assert flow._summary(result) == "ビューアにページが見つかりません。本が開いているか確かめるか、「範囲設定...」（ページメニュー）を使ってください。"
    set_language("en")
    result.fingerprints, result.error, result.cache_misses = ["a" * 16], "", 1
    result.regions = [SimpleNamespace(flags=("short",), status="translated", translated_text="Hi")]
    assert "worth a look" in flow._summary(result)
    assert flow.role_var.get() == "reader" and "worth a look" not in flow._page_line(result)  # the Translator role's business
    flow.role_var.set("translator")
    assert "worth a look" in flow._page_line(result)
    flow.role_var.set("reader")


# ------------------------------------------------------------------ the scan band
def _batch_event(flow, message, phase, pages=0, translated=0, found=0, checked=0, waiting=None, queued=0):
    p = SimpleNamespace(message=message, phase=phase, pages=pages, translated=translated, found=found, checked=checked,
                        waiting=waiting, queued=queued)
    flow._handle_event("batch", {"progress": p, "result": None, "message": message, "phase": phase, "pages": pages,
                                 "translated": translated, "found": found, "checked": checked, "waiting": waiting,
                                 "queued": queued})


def test_the_band_says_which_page_is_read_then_the_bubbles_and_the_time_left(flow, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(jobs.time, "monotonic", lambda: clock[0])
    set_language("ja")
    flow._scan = banner.ScanState(context=True)
    _batch_event(flow, Message("batch.scanning_page", page=23), "read", pages=22)
    assert flow.scan_band.texts()[0].startswith("めくったページを読み取っています。読み取り済み: 22、待ち: 0。")
    assert button_texts(flow.scan_band) == ["読み終えた", "停止"] and flow.scan_band.winfo_manager() == "pack"
    assert flow.status_var.get() == "23 ページ目を読み取り中..."
    covered = Message("batch.waiting_covered")
    _batch_event(flow, covered, "read", pages=23, waiting=covered)  # waiting for the reader: what to do
    assert flow.scan_band.texts() == [progress.rendered(covered)]
    read = Message("batch.read_page", page=24, lines=10, pages=24, bubbles=240, cached=0, seconds=300.0, dropped=0)
    _batch_event(flow, read, "read", pages=24, found=240, waiting=covered)  # ... as long as it lasts
    assert flow.scan_band.texts() == [progress.rendered(covered)]
    _batch_event(flow, read, "read", pages=24, found=240, queued=3)
    assert flow.scan_band.texts()[0].startswith("めくったページを読み取っています。読み取り済み: 24、待ち: 3。")
    read_all = "全ページを読み取りました。これから翻訳します。この間はビューアを操作しません。"
    _batch_event(flow, Message("batch.pages_read", pages=190, bubbles=1900), "read", pages=190, found=1900)
    assert flow.scan_band.texts() == [read_all] and button_texts(flow.scan_band) == ["停止"]
    _batch_event(flow, Message("batch.translating_chunk", chunk=1, chunks=19, bubbles=100), "translate", pages=190,
                 found=1900)
    assert flow.scan_band.texts() == ["翻訳中: 全1,900行中0行。この間はビューアを操作しません。"]
    assert flow.scan_band.fraction() == 0.0
    clock[0] += 420.0  # the first lines done: the model has loaded, the rate is measured from here
    _batch_event(flow, Message("batch.translated_chunk", chunk=4, chunks=19, bubbles=400, seconds=420.0), "translate",
                 pages=190, translated=400, found=1900, checked=400)
    assert flow.scan_band.texts() == ["翻訳中: 全1,900行中400行。この間はビューアを操作しません。"]
    clock[0] += 420.0  # 400 more lines in 7 minutes: 1,100 more take about 19 minutes
    wall = 1_800_000_000.0
    monkeypatch.setattr(banner.time, "time", lambda: wall)
    at = banner.time.strftime("%H:%M", banner.time.localtime(wall + 1100 / (400 / 420)))
    _batch_event(flow, Message("batch.translated_chunk", chunk=8, chunks=19, bubbles=800, seconds=840.0), "translate",
                 pages=190, translated=800, found=1900, checked=800)
    assert flow.scan_band.texts() == [f"翻訳中: 全1,900行中800行（残り約19分、{at}ごろ終了）。この間はビューアを操作しません。"]
    assert abs(flow.scan_band.fraction() - 800 / 1900) < 0.001
    set_language("en")
    flow._show_band()  # after a language switch
    assert flow.scan_band.texts() == [f"Translating: 800 of 1,900 lines, about 19 min left (done at about {at}). The "
                                      "viewer is not used during this step."]
    flow._batching = True
    asked = []
    monkeypatch.setattr(jobs, "ask_stop", lambda master, text, choices: asked.append(choices) or "stop")
    flow.scan_band.press("Stop")  # the band's Stop asks first (190 pages read), then stops the batch (at once: its
    assert [a for a, _label in asked[0]] == ["keep", "stop"]  # reader not made yet); translating: keep or stop
    assert flow._batch_stop_asked and flow.status_var.get() == "Stopping the whole-book run..."


def test_the_band_follows_a_page_by_page_scan(flow):
    flow._scan = banner.ScanState(context=False)
    _batch_event(flow, Message("batch.translated_page", page=4, bubbles=6, seconds=12.0, error=""), "translate",
                 pages=3, translated=20)
    assert flow.scan_band.texts()[0].startswith("Translating the pages you turn. Done: 3. Waiting: 0.")
    assert button_texts(flow.scan_band) == ["Finished reading", "Stop"]


def test_after_the_scan_the_band_sums_it_up_and_only_closes(flow):
    set_language("ja")
    flow._scan = banner.ScanState(context=True)
    flow._batching = flow.busy = flow._resume_auto = True
    flow.auto_var.set(False)
    summary = Message("batch.finished", pages=3, bubbles=12, seconds=40.0, minutes=1, failed=0, error="",
                      reason=Message("batch.finished_reading"))
    flow._handle_event("batch_done", {"progress": SimpleNamespace(summary=summary, reason="")})
    assert flow.scan_band.texts() == [progress.rendered(summary), "「自動: ページ送りに追従」が再び ON になりました。"]
    assert flow.scan_band.texts()[0].endswith(" - 読み終えました。")
    assert button_texts(flow.scan_band) == ["閉じる"] and flow.stop_btn["state"] == "disabled"
    assert flow.auto_var.get() and flow._auto_last is None and not flow._batching and not flow.busy
    assert flow.status_var.get() == progress.rendered(summary)

    flow.scan_band.press("閉じる")
    assert flow._band is None and flow.scan_band.winfo_manager() == ""


def test_a_run_that_translated_the_book_switches_to_reader_mode_and_the_band_says_so(flow):
    """The first whole-book run of a book opened in translator mode (no translations yet): once it has finished with
    the book translated, the window is in reader mode, said in the band (the status line soon says other things)."""
    roles = []
    flow._on_role_changed = lambda chosen=True: roles.append((flow.role_var.get(), chosen))
    flow.book_var.set("My Story 2")
    flow.role_var.set("translator")
    flow._batch_for = ("My Story 2", flow.model_var.get(), "English")
    _translated_pages(flow, "My Story 2", 30)
    summary = Message("batch.finished", pages=31, bubbles=253, seconds=300.0, minutes=5, failed=0, error="",
                      reason=Message("batch.finished_reading"))
    flow._handle_event("batch_done", {"progress": SimpleNamespace(summary=summary, reason="")})
    assert flow.role_var.get() == "reader" and roles == [("reader", False)]
    assert flow.scan_band.texts()[-1] == READER_AFTER_RUN and flow.status_var.get() == READER_AFTER_RUN

    # a run stopped before its end leaves the role as it is
    flow.role_var.set("translator")
    stopped = Message("batch.stopped", page=3, pages=3, bubbles=12, seconds=40.0)
    flow._handle_event("batch_done", {"progress": SimpleNamespace(summary=stopped, reason="")})
    assert flow.role_var.get() == "translator" and READER_AFTER_RUN not in flow.scan_band.texts()


def _cached_page(flow, image, incomplete=False):
    import numpy as np
    from taslation import fingerprint as fp

    cache = flow.store.open(flow.book_var.get(), flow.model_var.get(), "English")
    for unit in fp.analyze(np.asarray(image.convert("RGB")), flow.settings.margins):
        cache.add(CachedPage(unit.fingerprint, unit.aspect, [CachedBubble((0.1, 0.1, 0.2, 0.2), "A line")],
                             incomplete=incomplete))
    cache.save()


def test_in_translator_mode_a_cached_page_is_taken_at_its_first_frame_and_completed_unless_a_run_read_it(flow):
    """Translator mode takes a page the cache holds whole at its first frame too, drawn from the cache alone, and
    completes it from what it reads once the frame has settled (`_completes`; tests/test_follow.py) - except for a
    book a whole-book run finished reading in this session: the run read every region of its pages."""
    flow.book_var.set("My Story 2")
    page = Image.open(FIXTURES / "sample_page.png")
    _cached_page(flow, page)
    assert flow._all_cached(page) and not flow._completes()
    flow.role_var.set("translator")
    assert flow._all_cached(page) and flow._completes()  # drawn at once, completed from what it reads after
    flow._run_read = ("My Story 2", flow.model_var.get(), "English")  # a run of this book finished in this session
    assert flow._all_cached(page) and not flow._completes()
    flow._run_read = ("Other Book", flow.model_var.get(), "English")
    assert flow._completes()
    flow._run_read = ("My Story 2", flow.model_var.get(), "English")
    _cached_page(flow, page, incomplete=True)  # a page that lacks a translation is completed in any mode, settled
    assert not flow._all_cached(page)


def test_the_page_models_are_warmed_once_a_viewer_and_the_pipeline_are_there(flow):
    warmed = []
    flow.pipeline = SimpleNamespace(warm_page_models=lambda: warmed.append(1))
    flow._warm_page_models()
    assert warmed == [1]
    flow.selected = None
    flow._warm_page_models()
    flow.selected = VIEWER
    flow.pipeline = None  # not made yet: nothing
    flow._warm_page_models()
    assert warmed == [1]


# ------------------------------------------------------------------ Stop, a new page, a slow model, no flicker
class Waiting:
    """A pipeline whose page takes until it is cancelled (or 10 s)."""

    def __init__(self):
        self.started = threading.Event()
        self.slow_after = 0.0

    def process(self, image, *, progress=None, complete=False, events=None, cancel=None, on_slow=None):
        progress(Message("pipeline.stage_translating", bubbles=3, translator="t"))
        if on_slow is not None:
            on_slow(20.0)
        self.started.set()
        if cancel is not None and cancel.wait(10):
            raise Cancelled()
        raise AssertionError("not cancelled")


def test_stop_cancels_the_page_being_translated(flow):
    flow.pipeline = Waiting()
    flow.translator = SimpleNamespace(model="")
    flow._start_translate(_frame())
    assert flow.stop_btn["state"] == "normal" and flow._page_cancel is not None  # Stop works during a page
    worker = threading.Thread(target=flow._jobs.get())
    worker.start()
    assert flow.pipeline.started.wait(5)
    set_language("ja")
    flow.pump()  # the stage, then the slow model: the badge says so, and that Stop cancels this page
    assert flow._busy_text() == SLOW_JA and flow.status_var.get() == SLOW_JA and flow._busy_shown
    started = time.monotonic()
    flow.stop_batch()
    worker.join(5)
    assert time.monotonic() - started < 2 and not worker.is_alive()
    assert [kind for kind, _data in list(flow._events.queue)] == ["page_cancelled", "translate_done"]
    flow.pump()
    assert not flow.busy and flow.stop_btn["state"] == "disabled" and flow._page_cancel is None
    assert flow.status_var.get().startswith("停止しました: このページは翻訳していません")


def test_a_new_page_seen_by_auto_cancels_the_page_and_is_taken_next(flow, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(jobs.time, "monotonic", lambda: clock[0])
    flow.settings.margins = (0, 0, 0, 0)
    page = _frame()
    flow._start_translate(page)
    cancel = flow._page_cancel
    flow._watch_page()  # too soon: no look
    clock[0] += 1.0
    flow.frame = page.copy()  # the same page (another capture): nothing happens
    flow._watch_page()
    assert not cancel.is_set() and flow._watch_candidate is None
    flow.frame = _frame(ink=(120, 80, 170, 130))  # turned in the viewer
    clock[0] += 1.0
    flow._watch_page()
    assert not cancel.is_set() and flow._watch_candidate is not None  # once: it may still be turning
    clock[0] += 1.0
    flow._watch_page()
    assert cancel.is_set() and flow._cancel_why == "page" and flow._queued == ("auto", ())
    assert flow._auto_candidate is not None  # Auto takes it at once once the job is gone
    flow._handle_event("page_cancelled", {})
    flow._handle_event("translate_done", {})
    assert flow.ticks == 1 and flow._queued is None  # Auto looked again at once
    assert not flow.status_var.get().startswith("Stopped")  # not a Stop

    flow.auto_var.set(False)  # without Auto a turned page cancels nothing
    flow._start_translate(page)
    clock[0] += 5.0
    flow._watch_page()
    clock[0] += 5.0
    flow._watch_page()
    assert not flow._page_cancel.is_set()


def test_the_title_names_the_pass_a_whole_book_run_is_in(flow):
    flow._scan = banner.ScanState(context=True)
    flow.busy = True
    flow._busy_since = 0.0
    flow._flush_busy(1.0)  # the run has gone on for a while: the title shows it
    assert flow.titles[-1] == "TASlation - reading..."  # the reading pass: nothing is translated yet
    _batch_event(flow, Message("batch.read_page", page=1, lines=3, pages=1, bubbles=3, cached=0, seconds=2.0, dropped=0), "read", pages=1)
    assert flow.titles[-1] == "TASlation - reading..."
    _batch_event(flow, Message("batch.translated_chunk", chunk=1, chunks=2, bubbles=6, seconds=12.0), "translate",
                 pages=3, translated=6)
    assert flow.titles[-1] == "TASlation - translating..."


def test_a_page_from_the_cache_shows_no_busy_title_and_no_badge(flow):
    from taslation.regions import PageResult

    flow._start_translate(_frame())
    for message in (Message("pipeline.stage_finding"), Message("pipeline.stage_rendering")):
        flow._handle_event("progress", {"text": message})
    flow._flush_busy(flow._busy_since + 0.1)
    result = PageResult(image=_frame(), original=_frame(), regions=[])
    flow._handle_event("result", {"result": result})
    flow._handle_event("translate_done", {})
    flow._flush_busy(flow._busy_since + 1.0)
    assert "TASlation - translating..." not in flow.titles and not flow.progress_bar.shown
    assert not flow.canvas.find_withtag("busy") and not flow._busy_shown
    flow._start_translate(_frame())  # a page that takes longer: the signs come after 0.3 s
    flow._flush_busy(flow._busy_since + 0.3)
    assert flow.titles[-1] == "TASlation - translating..." and flow.progress_bar.shown
    assert flow.translate_btn["state"] == "disabled"
    flow._handle_event("translate_done", {})
    assert flow.titles[-1] == APP_TITLE and flow.translate_btn["state"] == "normal"


# ------------------------------------------------------------------ the book's name: recognised, asked for, never generic
from test_bookid import DUP, DUP_TOO, _cache, _page  # noqa: E402  (the synthetic pages and caches)
from test_bookid import _frame as _viewer  # noqa: E402

from taslation.annotations import Conflict, StyleGuide  # noqa: E402
from taslation.bookid import identity_of  # noqa: E402
from taslation.colophon import Colophon  # noqa: E402
from taslation.notes import series_key  # noqa: E402
from taslation.rename import RenamePlan, SheetJoin  # noqa: E402
from taslation.ui.dialogs.rename_review import RenameReviewDialog  # noqa: E402
from taslation.ui.dialogs.start import ColophonOffer  # noqa: E402
from taslation.ui.live import Following  # noqa: E402

COLOPHON = Colophon(title="見本の物語", volume="3", author="仮野みのり", publisher="株式会社見本出版",
                    date="2024年5月10日", isbn="978-4-06-123456-7", confidence=0.9)


def _said(dialog, text: str) -> bool:
    """Whether one of the dialog's labels says *text* (however its lines were broken)."""
    return "".join(text.split()) in ["".join(str(w.cget("text")).split()) for w in _widgets(dialog)
                                     if w.winfo_class() == "TLabel"]


def test_the_start_dialog_fills_in_a_recognised_name_or_offers_several(hidden_root):
    answers = []
    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=True, on_answer=lambda *a: answers.append(a),
                    matches=["Yomizuq", "Star Road 1"], hint="recognised")  # a generic name is never offered
    d.withdraw()
    assert d.name_var.get() == "Star Road 1" and str(d.buttons[0].cget("state")) == "normal"
    assert _said(d, "Recognised as Star Road 1 from a page already translated; change it if that is wrong.")
    d.name_var.set("yomizuq ")  # a name that names no book is never taken
    assert str(d.buttons[0].cget("state")) == "disabled"
    d._answer("start")
    assert not answers
    d.name_var.set("Star Road 1")
    d._answer("start")
    assert answers == [("start", "Star Road 1")]

    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=False, on_answer=lambda *a: answers.append(a),
                    matches=["Star Road 1", "Star Road 2"], hint="several")
    d.withdraw()
    assert d.entry.winfo_class() == "TCombobox" and tuple(d.entry.cget("values")) == ("Star Road 1", "Star Road 2")
    assert d.name_var.get() == "" and str(d.buttons[0].cget("state")) == "disabled"  # several: the reader picks
    assert _said(d, "Pages already translated in several books look like this one: pick the book in the list, or type "
                    "its name.")
    d.name_var.set("Star Road 2")
    d._answer(d.default)
    assert answers[-1] == ("ok", "Star Road 2")

    set_language("ja")
    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=False, on_answer=lambda *a: answers.append(a),
                    matches=["見本の物語 3"], hint="colophon")
    d.withdraw()
    assert d.name_var.get() == "見本の物語 3" and _said(d, "本の最後のページによると、この本は『見本の物語 3』です。違っていれば変更してください。")
    assert not [w for w in _widgets(d) if w.winfo_class() == "TCheckbutton"]  # the colophon gave the name already
    d.destroy()
    set_language("en")
    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=False, on_answer=lambda *a: answers.append(a))
    d.withdraw()  # nothing recognised: empty and required, as before
    assert d.name_var.get() == "" and d.entry.winfo_class() == "TEntry" and d.hint_label is None


def test_a_books_start_offers_the_books_whose_caches_hold_its_page(flow, monkeypatch):
    _no_problems(monkeypatch)
    _cache(flow.store, "Star Road 1", [_page(1), _page(2), DUP])
    _cache(flow.store, "Star Road 2", [_page(11), DUP_TOO])
    _cache(flow.store, "Yomizuq", [_page(3)])  # kept before the name was asked for: never offered
    flow._on_new_page(_viewer(_page(2), noise=3.0), None)
    d = flow.asked()
    assert d.generic and d.ask and d.matches == ["Star Road 1"] and d.hint == "recognised"
    d.on_answer("page", "Star Road 1")
    assert flow.book_var.get() == "Star Road 1" and flow.busy
    flow._handle_event("translate_done", {})
    flow._jobs = queue.Queue()

    flow.settings.scan_mode = "page"  # a near-duplicate page in two books: both offered, the exact one first
    flow.book_var.set("Yomizuq")
    flow._on_new_page(_viewer(DUP), None)
    d = flow.asked()
    assert not d.ask and d.matches == ["Star Road 1", "Star Road 2"] and d.hint == "several"
    d.on_answer(None, "")
    flow._live = _viewer(_page(11))  # the frame on show counts too
    flow._on_new_page(_viewer(_page(3)), None)
    assert flow.asked().matches == ["Star Road 2"]
    flow.dialogs[-1].on_answer(None, "")
    flow._live = None
    flow._on_new_page(_viewer(_page(55)), None)  # in no cache: the name given last time with this viewer
    assert flow.asked().matches == ["Star Road 1"] and flow.dialogs[-1].hint == "last"
    flow.dialogs[-1].on_answer(None, "")
    flow.selected = WindowInfo(hwnd=8, title="Yomizuq", class_name="YomizuqWindow", pid=8, rect=(0, 0, 800, 600))
    flow._on_new_page(_viewer(_page(56)), None)  # another viewer, no name given there yet: empty and required
    assert flow.asked().matches == [] and flow.dialogs[-1].hint == ""


def test_the_start_dialog_waits_for_the_book_recognised_in_the_worker(flow, monkeypatch):
    """Fingerprinting the frames in every area and looking through the caches (some 150 ms for two full-HD frames
    against 2,000 cached pages) runs in the worker: the dialog opens once the books are in. A page turned and F5
    meanwhile wait for it; a name typed into the Book box meanwhile is the dialog's, not the recognised one; a
    window rebuilt meanwhile opens nothing; with the cache off the dialog opens at once."""
    _no_problems(monkeypatch)
    _cache(flow.store, "Star Road 1", [_page(1), _page(2)])
    flow.settings.scan_mode = "page"
    flow._on_new_page(_viewer(_page(2)), None)
    assert not flow.dialogs and isinstance(flow._start_dialog, jobs.Recognising) and flow._jobs.qsize() == 1
    flow._on_new_page(_viewer(_page(1)), "later")  # a page turned meanwhile waits for the start
    flow.translate_now()  # F5 meanwhile: the start's dialog is coming
    assert flow._jobs.qsize() == 1 and not flow.dialogs and flow._start_pending[1] == "later"
    worker = threading.Thread(target=flow._jobs.get())  # the worker's part, off the Tk thread
    worker.start()
    worker.join()
    assert not flow.dialogs and [kind for kind, _data in list(flow._events.queue)] == ["recognised"]
    flow.pump()
    d = flow.dialogs[-1]
    assert len(flow.dialogs) == 1 and d.generic and d.matches == ["Star Road 1"] and d.hint == "recognised"
    d.on_answer(None, "")

    flow._on_new_page(_viewer(_page(2)), None)
    flow.book_var.set("My Story 2")  # typed while the page is recognised
    d = flow.asked()
    assert len(flow.dialogs) == 2 and not d.generic and d.name == "My Story 2" and d.matches == [] and d.hint == ""
    d.on_answer("ok", "My Story 2")
    assert flow.book_var.get() == "My Story 2" and last_name(flow.settings.state_dir, VIEWER.title) == "My Story 2"
    flow._handle_event("translate_done", {})
    flow._jobs = queue.Queue()

    flow.book_var.set("Yomizuq")
    flow._on_new_page(_viewer(_page(2)), None)
    flow._start_dialog = flow._start_pending = None  # the window rebuilt (a language switch: App._rebuild_ui)
    flow.run_jobs()
    assert len(flow.dialogs) == 2 and flow._start_dialog is None and not flow._recognising

    flow.settings.cache_enabled = False  # nothing to look through: at once, with the viewer's last name
    flow._on_new_page(_viewer(_page(2)), None)
    assert len(flow.dialogs) == 3 and flow._jobs.empty() and flow.dialogs[-1].matches == ["My Story 2"]
    assert flow.dialogs[-1].hint == "last"


def test_the_name_last_given_in_a_viewer_is_offered_when_nothing_is_recognised(flow, monkeypatch):
    """The capture area changed since the book was read (no page recognised): the name given last time in this
    viewer is filled in, said as such; recognised books and the colophon's name come first; every name given for a
    title that names none is the viewer's last name from then on (in ui.json, by viewer)."""
    _no_problems(monkeypatch)
    state = flow.settings.state_dir
    flow.settings.scan_mode = "page"
    flow._on_new_page(_viewer(_page(60)), None)  # nothing kept yet: empty and required
    d = flow.asked()
    assert d.matches == [] and d.hint == ""
    d.on_answer("ok", "  Star   Road 3 ")
    assert flow.book_var.get() == "Star Road 3"
    assert json.loads((state / "ui.json").read_text(encoding="utf-8"))["last_book"] == {"Google Chrome": "Star Road 3"}
    flow._handle_event("translate_done", {})
    flow._jobs = queue.Queue()

    flow.book_var.set("Yomizuq")  # minutes later, the capture area changed: no page of the book is recognised
    flow._on_new_page(_viewer(_page(61)), None)
    d = flow.asked()
    assert d.generic and d.matches == ["Star Road 3"] and d.hint == "last"
    d.on_answer(None, "")
    _cache(flow.store, "Star Road 2", [_page(62)])  # a page recognised: that book, not the last name
    flow._on_new_page(_viewer(_page(62)), None)
    assert flow.asked().matches == ["Star Road 2"] and flow.dialogs[-1].hint == "recognised"
    flow.dialogs[-1].on_answer(None, "")
    flow._colophon_found = ("Yomizuq", "m", "English", COLOPHON)  # a colophon read under "Yomizuq": its name
    assert flow._recognised(_viewer(_page(63))) == (["見本の物語 3"], "colophon")
    flow._colophon_found = None
    flow.settings.cache_enabled = False  # no caches to look at: the last name all the same
    assert flow._recognised(_viewer(_page(62))) == (["Star Road 3"], "last")
    flow.settings.cache_enabled = True

    flow.translate_now()  # F5 asks for the name with the last one filled in; the name given is the last one now
    prompt = flow.asked()
    assert not prompt.ask and prompt.matches == ["Star Road 3"] and prompt.hint == "last"
    prompt.on_answer("ok", "Star Road 4")
    assert flow.book_var.get() == "Star Road 4"
    assert json.loads((state / "ui.json").read_text(encoding="utf-8"))["last_book"] == {"Google Chrome": "Star Road 4"}
    flow._handle_event("translate_done", {})
    flow._jobs = queue.Queue()

    # a title that names the book: its name is not asked for, and not kept as the viewer's last name
    flow.settings.scan_mode = "book"
    flow.book_var.set("My Story 2")
    flow._on_new_page(_viewer(_page(64)), None)
    d = flow.asked()
    assert d.ask and not d.generic
    d.on_answer("page", "My Story 2")
    assert json.loads((state / "ui.json").read_text(encoding="utf-8"))["last_book"] == {"Google Chrome": "Star Road 4"}
    # nor offered while the title names a book (the Book box emptied by hand)
    from taslation.bookid import remember_name

    flow.selected = WindowInfo(hwnd=9, title="Star Road 9 - FOLIO☆QAT - Google Chrome", class_name="Chrome_WidgetWin_1",
                               pid=9, rect=(0, 0, 800, 600))
    remember_name(state, flow.selected.title, "Star Road 8")
    flow.book_var.set("")
    assert flow._recognised(_viewer(_page(65))) == ([], "")


def test_the_start_dialog_says_the_name_is_the_one_read_last_time_with_the_viewer(hidden_root):
    answers = []
    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=False, on_answer=lambda *a: answers.append(a),
                    matches=["Star Road 3"], hint="last")
    d.withdraw()
    assert d.name_var.get() == "Star Road 3" and str(d.buttons[0].cget("state")) == "normal"
    assert _said(d, "Last time with this viewer: Star Road 3 - change it if that is wrong.")
    d._answer(d.default)
    assert answers == [("ok", "Star Road 3")]
    set_language("ja")
    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=True, on_answer=lambda *a: answers.append(a),
                    matches=["見本の物語 3"], hint="last")
    d.withdraw()
    assert d.name_var.get() == "見本の物語 3"
    assert _said(d, "このビューアで前回読んだ本: 見本の物語 3。違う本なら書き換えてください。")
    d.destroy()


def test_the_openers_ask_for_the_name_first_and_go_on_with_it(flow, monkeypatch):
    opened = []
    monkeypatch.setattr(app_mod, "GlossaryDialog", lambda master, store, series, language, **kw: opened.append(
        ("sheet", series, language)))
    monkeypatch.setattr(app_mod, "BookSettingsDialog", lambda master, pipeline, on_change: opened.append(
        ("settings", pipeline.annotations.book)))
    told = []
    monkeypatch.setattr(caches, "tell", lambda _parent, text, **_k: told.append(text))
    _cache(flow.store, "Star Road 1", [_page(1)], isbn="978-4-06-123456-7", title="Star Road", volume="1")
    flow._live = _viewer(_page(1))

    flow.open_glossary()  # "Yomizuq": the name first, nothing opened
    assert not opened and not flow.dialogs  # the page recognised in the worker first
    prompt = flow.asked()
    assert len(flow.dialogs) == 1
    assert prompt.generic and not prompt.ask and prompt.matches == ["Star Road 1"] and prompt.hint == "recognised"
    prompt.on_answer("ok", "Star Road 1")
    assert opened == [("sheet", "Star Road", "English")] and flow.book_var.get() == "Star Road 1"
    flow.open_glossary()  # a real name now: at once
    assert opened == [("sheet", "Star Road", "English")] * 2 and len(flow.dialogs) == 1

    flow.book_var.set("Yomizuq")
    flow.open_glossary()
    flow.asked().on_answer(None, "")  # closed: nothing opened, and the status line says why
    assert len(opened) == 2 and flow.book_var.get() == "Yomizuq"
    assert flow.status_var.get() == "Give the book a name first (the Book field)."
    flow.open_glossary()
    flow.asked().on_answer("ok", "yomizuq")  # (the dialog takes no such name; neither does the prompt)
    assert len(opened) == 2 and flow.book_var.get() == "Yomizuq"

    flow.open_book_settings()
    flow.asked().on_answer("ok", "Star Road 2")
    assert told == ["Translate a page first (the book needs a name)."] and len(opened) == 2  # no page of it yet
    flow.pipeline = SimpleNamespace(annotations=SimpleNamespace(book="Star Road 2"))
    flow.open_book_settings()
    assert opened[-1] == ("settings", "Star Road 2")
    flow.pipeline.annotations.book = "Star Road 1"  # another book's settings are never shown under this name
    flow.open_book_settings()
    assert len(told) == 2 and opened[-1] == ("settings", "Star Road 2")


def test_f5_and_the_batchs_start_ask_for_the_name_first(flow, monkeypatch):
    flow.translate_now()
    flow.asked()
    assert not flow.busy and len(flow.dialogs) == 1 and not flow.dialogs[0].ask  # the name first, nothing read
    flow.dialogs[0].on_answer("ok", "Star Road 1")
    assert flow.busy and flow.book_var.get() == "Star Road 1" and flow._jobs.qsize() == 1  # then the page
    flow._handle_event("translate_done", {})
    flow._jobs = queue.Queue()

    starts = []
    monkeypatch.setattr(jobs, "BatchDialog", lambda master, win, settings, on_start, carried_on="": starts.append(on_start))
    flow.book_var.set("Yomizuq")
    flow.open_batch_dialog()
    options = (VIEWER, 0, True, True)
    starts[0](options)  # Start: the name first, no batch yet
    flow.asked()
    assert not flow.batches and len(flow.dialogs) == 2
    flow.dialogs[-1].on_answer(None, "")
    assert not flow.batches  # closed: no batch
    starts[0](options)
    flow.asked().on_answer("ok", "Star Road 2")
    assert flow.batches == [options] and flow.book_var.get() == "Star Road 2"

    # Auto's page while the name is asked for waits, and the book's start goes on once it is given
    _no_problems(monkeypatch)
    flow.book_var.set("Yomizuq")
    flow.translate_now()
    flow._on_new_page(_frame(), "thumb")  # while the page is recognised for the name, too
    assert len(flow.dialogs) == 3 and flow._start_pending is not None and flow._start_whole is True
    flow.asked()
    assert len(flow.dialogs) == 4 and flow._start_pending is not None and flow._start_whole is True
    flow.dialogs[-1].on_answer("ok", "Star Road 3")
    assert flow._jobs.qsize() == 2  # the book's setup check, then the page F5 asked for
    flow._jobs.get()()
    flow.pump()
    d = flow.dialogs[-1]
    assert len(flow.dialogs) == 5 and d.ask and not d.generic and d.name == "Star Road 3"  # the whole-book question


def test_a_name_that_names_no_book_reaches_no_store(flow, monkeypatch, tmp_path):
    flow._ensure_cache = A._ensure_cache.__get__(flow)  # the real one
    flow._job_refresh_premises = A._job_refresh_premises.__get__(flow)
    flow.pipeline, flow.translator = BookState(), SimpleNamespace(model="", target_language="English")
    flow.pipeline.cache = "the previous book's cache"
    assert flow._ensure_cache("Yomizuq", "m", "English")  # the page is still translated ...
    assert flow.pipeline.cache is None and flow.pipeline.annotations is None and flow.pipeline.glossary is None
    assert flow.pipeline.glossary_text == ""  # ... with nobody's premises
    flow._job_refresh_premises("Yomizuq", "English")
    monkeypatch.setattr(jobs, "BatchReader", lambda *a, **k: pytest.fail("no batch for a name that names no book"))
    flow._batching = flow.busy = True
    flow._job_batch(VIEWER.hwnd, "Yomizuq", "m", "English", 0, True, True)
    assert [kind for kind, _data in list(flow._events.queue)] == ["status", "batch_refused"]
    flow.pump()
    assert not flow._batching and flow.status_var.get() == "Give the book a name first (the Book field)."
    state = tmp_path / "state"
    assert not any(p.is_file() for p in state.rglob("*.json") if p.name != "ui.json")  # nothing kept


class Offers:
    def __init__(self):
        self.made = []

    def __call__(self, master, title, volume, on_answer):
        self.made.append((title, volume, on_answer))


def test_the_colophons_name_is_offered_once_and_used_when_nothing_is_kept_yet(flow, monkeypatch):
    offers = Offers()
    monkeypatch.setattr(jobs, "ColophonOffer", offers)
    event = {"colophon": COLOPHON, "book": "Yomizuq", "model": "m", "language": "English"}
    flow.reading = True  # read behind the reading window: offered once it is left
    flow._handle_event("colophon", event)
    assert not offers.made and flow._colophon_found is not None
    flow.reading = False
    flow._handle_event("translate_done", {})
    assert [(t, v) for t, v, _answer in offers.made] == [("見本の物語", "3")]
    offers.made[0][2](True)  # Use
    assert flow.book_var.get() == "見本の物語 3" and flow._book_edited
    assert flow.status_var.get() == "This book is now called 見本の物語 3."
    assert last_name(flow.settings.state_dir, flow.selected.title) == "見本の物語 3"  # the viewer's last book too
    flow.run_jobs()  # the colophon's details in the new name's cache
    assert identity_of(flow.store, "見本の物語 3", "English") == COLOPHON.details()
    flow.book_var.set("Yomizuq")
    flow._handle_event("colophon", event)  # once per book
    assert len(offers.made) == 1

    # a typed name with nothing kept under it yet: offered; Keep keeps the name and the details go to its cache
    flow.book_var.set("my star book")
    flow._handle_event("colophon", {**event, "book": "my star book"})
    offers.made[-1][2](False)
    flow.run_jobs()
    assert flow.book_var.get() == "my star book" and identity_of(flow.store, "my star book")["isbn"] == COLOPHON.isbn
    flow._colophon_asked.clear()  # a later session: the cache's header says it was offered
    flow._handle_event("colophon", {**event, "book": "my star book"})
    assert len(offers.made) == 2


def _offers(monkeypatch) -> list:
    """The colophon's offers as the window makes them, each withdrawn at once (the test answers them)."""
    made = []

    def offer(master, title, volume, on_answer):
        dialog = ColophonOffer(master, title, volume, on_answer)
        dialog.withdraw()
        made.append(dialog)
        return dialog

    monkeypatch.setattr(jobs, "ColophonOffer", offer)
    return made


def _question(offer) -> str:
    return "".join(str(offer.label.cget("text")).split())


def _keep_book(flow, book: str, page) -> None:
    """Files kept under *book*: its cache (one page), its annotations, its series' sheet."""
    _cache(flow.store, book, [page])
    marks = flow.annotation_store.open(book)
    marks.add_box("c" * 80, 0.7, (0.1, 0.1, 0.3, 0.2), "add")
    marks.save()
    sheet = flow.glossary_store.open(series_key(book), "English")
    sheet.set("星", "Star")
    sheet.save()


MOVED = ("This book is now called 見本の物語 3. Moved along: 1 translation file(s), 1 file(s) of page marks, 1 series "
         "sheet file(s).")


def test_with_files_kept_under_the_name_the_colophon_offers_to_rename_them_and_use_moves_them(flow, monkeypatch):
    made = _offers(monkeypatch)
    _keep_book(flow, "Star Road 3", _page(1))  # the whole book translated under the name typed at the start
    flow.book_var.set("Star Road 3")
    flow._batch_for = ("Star Road 3", "m", "English")
    flow._book_scanned, flow._scanned_book = True, "Star Road 3"
    summary = Message("batch.scan_ended")
    flow._handle_event("batch_done", {"progress": SimpleNamespace(summary=summary, reason="",
                                                                    colophon=COLOPHON)})
    assert len(made) == 1 and flow._start_dialog is made[0] and flow.book_var.get() == "Star Road 3"
    assert _question(made[0]) == "".join("The last page of the book says this is 見本の物語 (3). Rename Star Road 3 to it? Its "
                                         "translations, notes and sheet move along.".split())
    made[0].buttons[0].invoke()  # Use
    assert flow.busy and flow._start_dialog is None and flow.book_var.get() == "Star Road 3"  # nothing moved yet
    assert flow.status_var.get() == "Renaming Star Road 3 to 見本の物語 3..."
    flow.run_jobs()  # the files move in the worker; the Book box follows once they have
    assert not flow.busy and flow.book_var.get() == "見本の物語 3" and flow._book_edited
    assert flow._scanned_book == "見本の物語 3" and flow.status_var.get() == MOVED
    assert last_name(flow.settings.state_dir, flow.selected.title) == "見本の物語 3"  # the viewer's last book too
    assert [(e["book"], e["pages"]) for e in flow.store.list()] == [("見本の物語 3", 1)]
    assert identity_of(flow.store, "見本の物語 3", "English") == COLOPHON.details()
    assert [e["book"] for e in flow.annotation_store.list()] == ["見本の物語 3"]
    assert [e["series"] for e in flow.glossary_store.list()] == ["見本の物語"]
    set_language("ja")
    assert flow._status_render().startswith("この本の書名を『見本の物語 3』にしました。一緒に移したもの: 訳文ファイル 1 件")
    set_language("en")
    # once per book: the colophon read again under its name offers nothing, says nothing
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "見本の物語 3", "model": "m", "language": "English"})
    flow.run_jobs()
    assert len(made) == 1 and flow.status_var.get() == MOVED
    # the Book box has the colophon's name written otherwise: nothing offered or said, the details kept under it
    flow.book_var.set("見本の物語３")
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "見本の物語３", "model": "m", "language": "English"})
    flow.run_jobs()
    assert len(made) == 1 and flow.status_var.get() == MOVED
    assert identity_of(flow.store, "見本の物語３")["publisher"] == "株式会社見本出版"
    # read for a name the Book box no longer holds: nothing
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Other", "model": "m", "language": "English"})
    assert len(made) == 1


def test_keep_leaves_the_name_and_the_book_its_files(flow, monkeypatch):
    made = _offers(monkeypatch)
    _keep_book(flow, "Star Road 3", _page(1))
    flow.book_var.set("Star Road 3")
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Star Road 3", "model": "m", "language": "English"})
    made[0].buttons[1].invoke()  # Keep
    flow.run_jobs()
    assert flow.book_var.get() == "Star Road 3" and [e["book"] for e in flow.store.list()] == ["Star Road 3"]
    assert identity_of(flow.store, "Star Road 3", "English") == COLOPHON.details()  # never offered again
    flow._colophon_asked.clear()  # a later session
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Star Road 3", "model": "m", "language": "English"})
    assert len(made) == 1


def test_a_rename_that_cannot_be_made_says_why_and_the_book_keeps_its_name(flow, monkeypatch):
    made = _offers(monkeypatch)
    _keep_book(flow, "Star Road 3", _page(1))
    _cache(flow.store, "見本の物語 3", [_page(2)])  # the colophon's name has translations of its own already
    state = flow.settings.state_dir
    before = {p: p.read_bytes() for p in state.rglob("*.json")}
    flow.book_var.set("Star Road 3")
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Star Road 3", "model": "m", "language": "English"})
    made[0].buttons[0].invoke()  # Use
    flow.run_jobs()
    assert not flow.busy and flow.book_var.get() == "Star Road 3"
    target = flow.store.path_for("見本の物語 3")
    assert flow.status_var.get() == (f"Star Road 3 was not renamed: {target} is in the way. Move it out of "
                                     f"{target.parent}, then try again.")
    # nothing moved, and nothing of the colophon kept: its name is offered again in a later session
    assert {p: p.read_bytes() for p in state.rglob("*.json")} == before
    flow._colophon_asked.clear()
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Star Road 3", "model": "m", "language": "English"})
    assert len(made) == 2


def test_an_old_cache_kept_under_the_viewers_name_is_renamed_and_the_start_that_waited_goes_on(flow, monkeypatch):
    made = _offers(monkeypatch)
    _cache(flow.store, "Yomizuq", [_page(3), _page(4)])  # kept before the name was asked for
    flow.settings.scan_mode = "page"
    flow.reading = True  # read behind the reading window: offered once it is left
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Yomizuq", "model": "m", "language": "English"})
    flow.reading = False
    flow._start_pending, flow._start_whole = (_viewer(_page(70)), None), False  # a book's start waits meanwhile
    flow._handle_event("translate_done", {})
    assert _question(made[0]) == "".join("The last page of the book says this is 見本の物語 (3). Rename Yomizuq to it? Its "
                                         "translations, notes and sheet move along.".split())
    made[0].buttons[0].invoke()
    assert flow._start_pending is not None  # the start waits for the files to move
    flow.run_jobs()
    assert flow.book_var.get() == "見本の物語 3" and [e["book"] for e in flow.store.list()] == ["見本の物語 3"]
    assert flow._start_pending is None and flow.ticks == 1  # then went on: Auto takes the page under the new name
    assert flow.status_var.get().startswith("This book is now called 見本の物語 3. Moved along: 1 translation file(s), 0 ")


def test_the_pipeline_takes_the_renamed_files(flow, monkeypatch, tmp_path):
    _keep_book(flow, "Star Road 3", _page(1))
    flow._ensure_cache = A._ensure_cache.__get__(flow)  # the real one
    flow._job_refresh_premises = A._job_refresh_premises.__get__(flow)
    flow.pipeline, flow.translator = BookState(), SimpleNamespace(model="", target_language="English")
    assert flow._ensure_cache("Star Road 3", "m", "English") and flow.pipeline.cache.book == "Star Road 3"
    old = flow.pipeline.cache.path
    flow._rename_book("Star Road 3", "見本の物語 3", "m", "English", COLOPHON)
    flow.run_jobs()
    cache = flow.pipeline.cache
    assert cache.book == "見本の物語 3" and cache.path != old and cache.path.is_file() and not old.exists()
    assert flow.pipeline.annotations.book == "見本の物語 3" and flow.pipeline.glossary.series == "見本の物語"
    cache.save()  # a save of the pipeline's cache writes the new name's file, never the old one again
    assert not old.exists() and [e["book"] for e in flow.store.list()] == ["見本の物語 3"]


# ------------------------------------------------------------------ a rename onto a series with a sheet of its own
def _reviews(monkeypatch) -> list:
    """The rename's reviews as the window opens them, each withdrawn at once (the test answers them)."""
    made = []

    def review(master, plan, on_apply, on_cancel=None):
        dialog = RenameReviewDialog(master, plan, on_apply, on_cancel)
        dialog.withdraw()
        made.append(dialog)
        return dialog

    monkeypatch.setattr(jobs, "RenameReviewDialog", review)
    return made


def _the_colophons_series(flow, says_otherwise: bool = True) -> None:
    """The series the colophon's name gives (見本の物語) has a sheet of its own already (its volume 1 was
    renamed before): a term of its own and, *says_otherwise*, 星 rendered otherwise than this book's sheet and
    honorifics kept where this book's sheet drops them (which adds a term of its own too)."""
    sheet = flow.glossary_store.open("見本の物語", "English")
    sheet.set("月", "Moon")
    if says_otherwise:
        sheet.set("星", "Stardust")
        sheet.style = StyleGuide(honorifics="keep")
        book = flow.glossary_store.open("Star Road", "English")  # this book's (`_keep_book`: 星 is Star)
        book.set("空", "Sky")
        book.style = StyleGuide(honorifics="drop")
        book.save()
    sheet.save()


JOINED = (" The series sheet joined the sheet of 見本の物語: 1 added, 1 taken from this book, 1 kept as the series had "
          "them.")


def test_in_the_reader_role_a_sheet_that_says_otherwise_joins_as_the_review_would_start_with(flow, monkeypatch):
    made, reviews = _offers(monkeypatch), _reviews(monkeypatch)
    _keep_book(flow, "Star Road 3", _page(1))
    _the_colophons_series(flow)
    flow.book_var.set("Star Road 3")
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Star Road 3", "model": "m", "language": "English"})
    assert flow.role_var.get() == "reader"
    made[0].buttons[0].invoke()  # Use: no table for a reader
    assert not reviews and flow._start_dialog is None and flow.busy
    flow.run_jobs()
    flow.pump()
    assert flow.book_var.get() == "見本の物語 3"
    sheet = flow.glossary_store.open("見本の物語", "English")
    assert sheet.get("星").rendering == "Stardust" and sheet.style.honorifics == "keep"  # each row's default: the series'


def test_a_sheet_that_says_otherwise_than_the_new_series_is_reviewed_then_joins_it(flow, monkeypatch):
    made, reviews = _offers(monkeypatch), _reviews(monkeypatch)
    flow.role_var.set("translator")
    _keep_book(flow, "Star Road 3", _page(1))
    _the_colophons_series(flow)
    flow.book_var.set("Star Road 3")
    flow.settings.scan_mode = "page"
    flow._start_pending, flow._start_whole = (_viewer(_page(70)), None), False  # a book's start waits meanwhile
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Star Road 3", "model": "m", "language": "English"})
    made[0].buttons[0].invoke()  # Use: the review first, nothing renamed yet
    assert len(reviews) == 1 and flow._start_dialog is reviews[0] and not flow.busy and flow._jobs.empty()
    review = reviews[0]
    assert review.title() == "Renaming Star Road 3 to 見本の物語 3"
    assert dict((what, (series, book)) for what, series, book in review.rows) == {
        "Term: 星": ("Stardust", "Star"), "Style guide: Honorifics": ("keep", "drop")}
    assert flow._start_pending is not None  # the start waits for the answer
    dict(review.choices)[("term", "星", "", "")].set("theirs")  # this book's rendering of 星; the policy the series'
    review.apply()  # Rename
    assert flow._start_dialog is None and flow.busy and flow.status_var.get() == "Renaming Star Road 3 to 見本の物語 3..."
    flow.run_jobs()
    assert flow.book_var.get() == "見本の物語 3" and flow.status_var.get() == MOVED + JOINED
    sheet = flow.glossary_store.open("見本の物語", "English")
    assert [(e.term, e.rendering) for e in sheet.entries] == [("月", "Moon"), ("星", "Star"), ("空", "Sky")]
    assert sheet.style.honorifics == "keep"
    assert [e["series"] for e in flow.glossary_store.list()] == ["見本の物語"]  # the book's old sheet is gone
    assert flow._start_pending is None and flow.ticks == 1  # then the start went on: Auto takes the page
    set_language("ja")
    try:
        assert flow._status_render().endswith(
            "シリーズ設定を『見本の物語』のシリーズ設定に統合しました: 追加 1 件、この本の方を採用 1 件、シリーズの方のまま 1 件。")
    finally:
        set_language("en")


def test_cancel_in_the_review_keeps_the_name_and_a_start_that_waits_goes_on(flow, monkeypatch):
    made, reviews = _offers(monkeypatch), _reviews(monkeypatch)
    flow.role_var.set("translator")
    _keep_book(flow, "Star Road 3", _page(1))
    _the_colophons_series(flow)
    state = flow.settings.state_dir
    before = {p: p.read_bytes() for p in state.rglob("*.json")}
    flow.book_var.set("Star Road 3")
    event = {"colophon": COLOPHON, "book": "Star Road 3", "model": "m", "language": "English"}
    flow._handle_event("colophon", event)
    made[0].buttons[0].invoke()  # Use
    reviews[0].cancel()
    assert flow._start_dialog is None and not flow.busy and flow._jobs.empty()
    assert flow.book_var.get() == "Star Road 3"
    assert flow.status_var.get() == "Star Road 3 keeps its name; the name on the last page of the book is offered again next time."
    assert {p: p.read_bytes() for p in state.rglob("*.json")} == before  # nothing moved, nothing of the colophon kept
    assert COLOPHON.name not in flow._colophon_asked
    set_language("ja")
    try:
        assert flow._status_render() == "『Star Road 3』の名前はそのままです。本の最後のページの名前は、次回もう一度確認します。"
    finally:
        set_language("en")
    flow._colophon_asked.clear()  # a later session: offered again; this time a book's start waits meanwhile
    flow.settings.scan_mode = "page"
    flow._start_pending, flow._start_whole = (_viewer(_page(70)), None), False
    flow._handle_event("colophon", event)
    made[1].buttons[0].invoke()
    assert flow._start_pending is not None
    assert reviews[1].bind("<Escape>") and reviews[1].protocol("WM_DELETE_WINDOW")  # Esc and closing it cancel too
    reviews[1].cancel()
    assert flow._start_pending is None and flow.busy  # the start went on: the page is translated under the old name
    assert flow.book_var.get() == "Star Road 3" and [e["book"] for e in flow.store.list()] == ["Star Road 3"]


def test_with_nothing_to_answer_the_sheet_joins_at_once_and_is_said(flow, monkeypatch):
    made, reviews = _offers(monkeypatch), _reviews(monkeypatch)
    _keep_book(flow, "Star Road 3", _page(1))
    _the_colophons_series(flow, says_otherwise=False)  # the series' sheet has a term of its own, nothing else
    flow.book_var.set("Star Road 3")
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Star Road 3", "model": "m", "language": "English"})
    made[0].buttons[0].invoke()  # Use: no review, the rename at once
    assert not reviews and flow.busy
    flow.run_jobs()
    assert flow.status_var.get() == MOVED + (" The series sheet joined the sheet of 見本の物語: 1 added, 0 taken from "
                                             "this book, 0 kept as the series had them.")
    sheet = flow.glossary_store.open("見本の物語", "English")
    assert [(e.term, e.rendering) for e in sheet.entries] == [("月", "Moon"), ("星", "Star")]


@pytest.mark.parametrize("held", ["cache", "marks"])
def test_the_pipeline_takes_the_joined_sheet(flow, held):
    _keep_book(flow, "Star Road 3", _page(1))
    _the_colophons_series(flow, says_otherwise=False)
    flow._ensure_cache = A._ensure_cache.__get__(flow)  # the real ones
    flow._job_refresh_premises = A._job_refresh_premises.__get__(flow)
    flow.pipeline, flow.translator = BookState(), SimpleNamespace(model="", target_language="English")
    assert flow._ensure_cache("Star Road 3", "m", "English")
    if held == "marks":  # the pipeline holds the book's annotations alone
        flow.pipeline.cache = None
    flow._rename_book("Star Road 3", "見本の物語 3", "m", "English", COLOPHON)
    flow.run_jobs()
    glossary = flow.pipeline.glossary
    assert glossary.series == "見本の物語" and [e.term for e in glossary.entries] == ["月", "星"]
    assert "月 = Moon" in flow.pipeline.glossary_text and "星 = Star" in flow.pipeline.glossary_text


def test_the_rename_review_shows_both_values_answers_once_and_speaks_the_windows_language(hidden_root):
    term = Conflict("term", key="星", mine=("Stardust", ""), theirs=("Star", "a note"))
    policy = Conflict("style", key="honorifics", mine="keep", theirs="drop")
    plan = RenamePlan("Star Road 3", "見本の物語 3", "Star Road", "見本の物語",
                      sheets=[SheetJoin("English", 2, [term, policy])])
    applied, cancelled = [], []
    d = RenameReviewDialog(hidden_root, plan, on_apply=applied.append, on_cancel=lambda: cancelled.append(1))
    d.withdraw()
    assert d.rows == [("Term: 星", "Stardust", "Star (a note)"), ("Style guide: Honorifics", "keep", "drop")]
    headings = [str(w.cget("text")) for w in d.list_canvas.winfo_children()[0].winfo_children()[:3]]
    assert headings == ["What", "Series sheet", "This book's sheet"]
    assert (d.apply_btn.cget("text"), d.cancel_btn.cget("text")) == ("Rename", "Cancel")
    d.set_all(True)
    dict(d.choices)[("style", "honorifics", "", "")].set("mine")
    d.apply()
    d.apply()
    d.cancel()  # answered once
    assert applied == [{("term", "星", "", ""): True, ("style", "honorifics", "", ""): False}] and not cancelled
    assert not d.winfo_exists()
    # the sheets of two languages: each row says which, its answer goes under the language
    german = Conflict("term", key="星", mine=("Sternenstaub", ""), theirs=("Stern", ""))
    plan.sheets.append(SheetJoin("German", 0, [german]))
    set_language("ja")
    try:
        d = RenameReviewDialog(hidden_root, plan, on_apply=applied.append, on_cancel=lambda: cancelled.append(1))
        d.withdraw()
        assert d.title() == "『Star Road 3』を『見本の物語 3』に変更" and d.apply_btn.cget("text") == "書名を変更"
        headings = [str(w.cget("text")) for w in d.list_canvas.winfo_children()[0].winfo_children()[:3]]
        assert headings == ["項目", "シリーズ設定", "この本の設定"]
        assert [what for what, _series, _book in d.rows] == ["用語: 星 (English)", "文体ガイド: 敬称 (English)",
                                                              "用語: 星 (German)"]
        assert str(d.intro.cget("text")).startswith("『見本の物語』のシリーズ設定はすでにあります。")
        d.cancel()
        d.cancel()
        assert cancelled == [1] and len(applied) == 1
    finally:
        set_language("en")
    assert sorted(dict(d.choices)) == [("english", "style", "honorifics", "", ""), ("english", "term", "星", "", ""),
                                       ("german", "term", "星", "", "")]


def test_under_a_name_that_names_no_book_every_page_counts_as_uncached(flow, monkeypatch):
    _no_problems(monkeypatch)
    flow._page_uncached = A._page_uncached.__get__(flow)  # the real one
    _cache(flow.store, "Yomizuq", [_page(3)])  # an old cache kept under "Yomizuq" holds the page
    _cache(flow.store, "Star Road 1", [_page(1)])
    assert flow.book_var.get() == "Yomizuq" and flow._page_uncached(_viewer(_page(3)))
    flow.book_var.set("")
    assert flow._page_uncached(_viewer(_page(3)))
    flow.book_var.set("Star Road 1")
    assert not flow._page_uncached(_viewer(_page(1))) and flow._page_uncached(_viewer(_page(3)))
    flow.book_var.set("Yomizuq")
    flow._on_new_page(_viewer(_page(3)), None)  # the book's start, though the old cache has the page
    flow.asked()
    assert len(flow.dialogs) == 1 and flow.dialogs[0].generic


def test_with_follow_by_events_a_page_is_watched_for_only_while_the_viewer_is_in_front(flow, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(jobs.time, "monotonic", lambda: clock[0])
    captured = []
    flow._capture = lambda hwnd: captured.append(hwnd) or flow.frame
    flow._following = Following(mode="events", owner="own")
    flow._start_translate(_frame())
    for owner in ("own", "other"):  # TASlation in front: its own operations are followed, and cancel the job
        flow._following.owner = owner  # neither in front: nothing to look at
        clock[0] += 5.0
        flow._watch_page()
    assert not captured and not flow._page_cancel.is_set()
    flow._following.owner = "viewer"  # the viewer in front: the pages turned there are looked for, as before
    clock[0] += 5.0
    flow._watch_page()
    assert captured == [VIEWER.hwnd]
    flow._following = Following(mode="poll")  # polling: as before
    clock[0] += 5.0
    flow._watch_page()
    assert len(captured) == 2


def test_f5_while_the_browser_shows_another_tab_says_the_live_views_line(flow):
    flow.book_var.set("Star Road 1")
    flow._book_in_front = lambda: False
    flow.translate_now()
    assert not flow.busy and flow._jobs.empty()
    assert flow.status_var.get() == ("Waiting: the browser shows another tab. Bring the book's tab back, or drag that tab out into a window of its own.")


def test_a_colophon_read_under_a_generic_name_names_the_book_at_its_start(flow, monkeypatch):
    _no_problems(monkeypatch)
    flow.reading = True
    flow._handle_event("colophon", {"colophon": COLOPHON, "book": "Yomizuq", "model": "m", "language": "English"})
    flow.reading = False
    flow._on_new_page(_viewer(_page(70)), None)  # the start dialog comes first: the colophon's name filled in
    d = flow.asked()
    assert d.matches == ["見本の物語 3"] and d.hint == "colophon"
    d.on_answer("page", "見本の物語 3")
    assert flow._jobs.qsize() == 2  # the colophon's details kept under the name, then the page translated
    flow._jobs.get()()
    assert identity_of(flow.store, "見本の物語 3")["isbn"] == COLOPHON.isbn and flow._colophon_found is None
    # a cache that has the colophon's ISBN names the book whatever the pages say
    _cache(flow.store, "Star Road (my name)", [_page(71)], isbn="9784061234567")
    flow._handle_event("translate_done", {})
    flow._jobs = queue.Queue()
    flow.book_var.set("Yomizuq")
    flow._colophon_found = ("Yomizuq", "m", "English", COLOPHON)
    assert flow._recognised(_viewer(_page(1))) == (["Star Road (my name)", "見本の物語 3"], "several")


def test_a_page_with_no_text_to_translate_is_read_as_a_colophon(flow, monkeypatch):
    offers = Offers()
    monkeypatch.setattr(jobs, "ColophonOffer", offers)
    looked, read = [], []
    monkeypatch.setattr(jobs, "colophon_precheck", lambda image, margins: looked.append(image) or True)
    monkeypatch.setattr(jobs, "find_colophon", lambda image, ocr, margins: read.append(image) or COLOPHON)
    flow.pipeline = SimpleNamespace(ocr=object())
    texted = SimpleNamespace(units=[SimpleNamespace(index=0)], regions=[SimpleNamespace(unit=0, status="translated")])
    flow._look_for_colophon(_frame(), texted, "Yomizuq", "m", "English")
    assert not looked and flow._jobs.empty()  # a page with text to translate is no colophon
    bare = SimpleNamespace(units=[SimpleNamespace(index=0), SimpleNamespace(index=1)],
                           regions=[SimpleNamespace(unit=0, status="translated"), SimpleNamespace(unit=1, status="dropped")])
    page = _frame()
    flow._look_for_colophon(page, bare, "Yomizuq", "m", "English")
    assert looked == [page] and flow._jobs.qsize() == 1 and not read  # the OCR in a job of its own
    flow.run_jobs()
    assert read == [page] and [(t, v) for t, v, _a in offers.made] == [("見本の物語", "3")]
    flow._look_for_colophon(page, bare, "Yomizuq", "m", "English")  # found: no other page of the book is read
    assert len(looked) == 1 and flow._jobs.empty()


def test_the_colophon_box_rests_the_name_field_and_a_temporary_name_holds_the_book(hidden_root):
    answers = []
    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=False, on_answer=lambda *a: answers.append(a))
    d.withdraw()
    ok = d.buttons[0]
    assert str(ok.cget("state")) == "disabled" and str(d.entry.cget("state")) == "normal"
    d.from_colophon.set(True)
    d._sync()
    assert str(d.entry.cget("state")) == "disabled" and str(ok.cget("state")) == "normal"
    assert not generic_book_name(d.name())
    d.from_colophon.set(False)
    d._sync()
    assert str(d.entry.cget("state")) == "normal" and str(ok.cget("state")) == "disabled"
    d.from_colophon.set(True)
    d._sync()
    d._answer("ok")
    assert answers[0][0] == "ok" and answers[0][1].startswith("Untitled book 20")


# ------------------------------------------------------------------ a run's end, its start, what waits for it
def _ended(summary="batch.scan_ended"):
    return SimpleNamespace(summary=Message(summary), reason="", colophon=None)


def test_auto_comes_back_after_a_run_started_from_the_dialog(flow):
    flow.auto_var.set(True)
    flow._auto_before_batch = bool(flow.auto_var.get())  # as `_start_batch` notes it, then turns Auto off
    flow.auto_var.set(False)
    flow._auto_last = object()
    flow._batch_done(_ended())
    assert flow.auto_var.get() is True and flow._auto_last is None and flow._band["resumed"] is True
    assert flow._auto_before_batch is None
    flow._auto_before_batch = False  # Auto was off before the run: it stays off, and nothing says it is on
    flow.auto_var.set(False)
    flow._batch_done(_ended())
    assert flow.auto_var.get() is False and flow._band["resumed"] is False


def test_a_head_of_the_batch_that_fails_leaves_no_run_behind(flow, monkeypatch):
    def boom(_settings):
        raise RuntimeError("no such thing")

    monkeypatch.setattr(jobs, "preflight", boom)
    flow.busy, flow._batching = True, True
    flow.book_var.set("Book")
    flow._job_batch(1, "Book", "m", "English", 0, True, True)
    flow.pump()
    assert not flow.busy and not flow._batching and flow.batch is None
    assert flow.status_var.get() == "Could not start the batch: RuntimeError: no such thing"


def test_stop_cancels_a_queued_batch_and_the_stop_button_says_it_can(flow):
    flow.ready, flow.busy = True, True  # a page runs: the batch waits behind it
    flow._page_cancel = None
    flow._queue("batch", "options")
    assert flow.stop_btn["state"] == "normal"
    flow._resume_auto = True
    flow.stop_batch()
    assert flow._queued is None and not flow._resume_auto and flow.stop_btn["state"] == "disabled"
    assert flow.status_var.get() == "The batch that was waiting is cancelled."
    flow.busy = False
    flow._run_queued()
    assert not flow.batches


class _Boom:
    def __init__(self, *_args):
        raise RuntimeError("the model file is damaged")


def test_an_ocr_model_that_fails_to_load_is_said_and_not_tried_for_ever(flow, monkeypatch):
    import taslation.ocr as ocr

    monkeypatch.setattr(ocr, "Readers", _Boom)
    flow.ready = True
    flow.pipeline = SimpleNamespace(ocr=None)
    flow._job_load_ocr = app_mod.App._job_load_ocr.__get__(flow)
    flow._load_ocr_if_due()
    assert flow._ocr_loading
    flow._jobs.get()()
    flow.pump()
    assert not flow._ocr_loading and flow.status_var.get().startswith("Could not load the OCR model: RuntimeError")
    flow._load_ocr_if_due()  # it stays as it is: not loaded again with every look at the setup
    assert not flow._ocr_loading and flow._jobs.empty()


def test_the_start_goes_on_when_the_ocr_model_fails_to_load(flow, monkeypatch):
    import taslation.ocr as ocr
    import taslation.ocr.charspot as charspot

    monkeypatch.setattr(ocr, "Readers", _Boom)
    monkeypatch.setattr(charspot, "import_libraries", lambda: None)
    monkeypatch.setattr(caches, "tell", lambda *a, **k: None)
    flow._check_setup = lambda: ([], None)
    flow._start_keep_alive = lambda: None
    flow._revive_ollama = lambda cancel=None: False
    flow._job_init = app_mod.App._job_init.__get__(flow)
    flow._job_init()
    flow.pump()
    assert flow.ready and flow.pipeline is not None and flow.pipeline.ocr is None and flow._ocr_failed
    assert not flow._ocr_loading  # (and it is not loaded again: said once)


def test_the_stale_order_goes_when_another_page_comes(flow):
    page = Image.new("RGB", (64, 64), "white")
    first = PageResult(image=page, original=page, regions=[])
    flow.last_result, flow._ordering = first, ["a region of the first page"]
    flow._chosen_region = None
    labels = []
    flow._label_order = labels.append
    flow._end_order = app_mod.App._end_order.__get__(flow)
    flow._handle_event("result", {"result": first})  # the same page lettered again: the order goes on
    assert flow._ordering == ["a region of the first page"]
    second = PageResult(image=page, original=page, regions=[])
    flow._handle_event("result", {"result": second})
    assert flow._ordering is None and labels == ["Reading order"]
    assert flow.status_var.get() == "Reading order cancelled: another page came."
    flow._ordering = ["a region of the second page"]
    app_mod.App._batch_page(flow, page)
    assert flow._ordering is None and flow.last_result is None


def test_a_save_on_another_page_leaves_the_page_on_show(flow):
    page = Image.new("RGB", (64, 64), "white")
    opened_on = SimpleNamespace(original=page, image=page, regions=[], units=[])
    on_show = SimpleNamespace(original=page, image=page, regions=[], units=[])
    flow.last_result = on_show
    flow._handle_event("result", {"result": opened_on, "edited": True})
    assert flow.last_result is on_show and flow.status_var.get() == "Saved on the page the editor was opened on."
