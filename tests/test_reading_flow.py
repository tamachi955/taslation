"""The full screen's ways out and what it changes: the faint close button at the top edge (a click on it leaves the
full screen, the page's other pointer handling stays bound), Auto turned on by the Reader's full screen and off by a
whole-book run said once a session, the Translator's full screen keeping Auto as set and following a role change, its
notes long enough to read, and a book read on the full screen under a name that names no book named once on leaving.
Parts of the App are borrowed onto stand-ins on the shared hidden root (never mapped); Windows' side is a fake."""
from __future__ import annotations

import queue
from types import SimpleNamespace

from test_enlarge import _batch_window, desk  # noqa: F401 - desk is test_enlarge's fixture
from test_reading_messages import Reading
from test_start_flow import _frame, flow  # noqa: F401 - flow is test_start_flow's fixture

from taslation.ui import app as app_mod
from taslation.ui.constants import (FULL_SCREEN_TRANSLATOR, KEPT_FROM_NOW, NOTE_MS_PER_CHAR, READING_MODE,
                                    READING_MODE_AUTO, READING_NOTE_MS, RUN_AUTO_OFF, TRANSLATOR_NOTE_MAX_MS)
from taslation.ui.reading import TOP_BAND_PX, TOP_EDGE_PX

A = app_mod.App


def _reading(root, auto=False):
    w = Reading(root)
    w._manual_area = True  # an area of the reader's: Set area... is not offered first
    w.auto_var.set(auto)
    return w


def _bound(widget, sequence):
    """How many callbacks *sequence* has on *widget*."""
    return str(widget.bind(sequence)).count("if {")


# ------------------------------------------------------------------ the close button at the top edge
def test_the_close_button_shows_at_the_top_edge_and_goes_further_down(hidden_root):
    w = _reading(hidden_root)
    w._top_edge_moved(SimpleNamespace(y=0))  # not in reading mode: nothing
    assert getattr(w, "_close_button", None) is None
    w.enter_reading()
    w._top_edge_moved(SimpleNamespace(y=TOP_EDGE_PX + 40))  # on the page: nothing yet
    assert getattr(w, "_close_button", None) is None
    w._top_edge_moved(SimpleNamespace(y=0))
    button = w._close_button
    assert button.place_info() and str(button.cget("text")).endswith("Leave full screen (F11)")
    w._top_edge_moved(SimpleNamespace(y=TOP_BAND_PX // 2))  # on its way down to the button: it stays
    assert button.place_info()
    w._top_edge_moved(SimpleNamespace(y=TOP_BAND_PX + 1))
    assert not button.place_info()
    w._top_edge_moved(SimpleNamespace(y=TOP_EDGE_PX))
    assert button.place_info() and w._close_button is button  # the same button again
    w.winfo_containing = lambda x, y: button  # the pointer off the page onto the button: it stays
    w._top_edge_left(SimpleNamespace(x_root=5, y_root=5))
    assert button.place_info()
    w.winfo_containing = lambda x, y: None  # ... anywhere else: it goes
    w._top_edge_left(SimpleNamespace(x_root=5, y_root=5))
    assert not button.place_info()
    w._top_edge_moved(SimpleNamespace(y=0))
    w.leave_reading()
    assert not button.place_info()  # out of reading mode with it


def test_a_click_on_the_close_button_leaves_reading_mode_and_the_pages_pointer_handling_stays(hidden_root):
    w = _reading(hidden_root)
    w.canvas.bind("<Motion>", lambda _e: None)  # the Translator role's own (App._build_ui binds `_on_motion`)
    for _cycle in range(2):
        w.enter_reading()
        assert _bound(w.canvas, "<Motion>") == 2 and _bound(w.canvas, "<Leave>") == 1  # added once, beside it
        w._top_edge_moved(SimpleNamespace(y=0))
        assert _bound(w._close_button, "<ButtonRelease-1>") == 1  # the click: `_close_clicked`
        w._close_clicked()
        assert not w.reading and w.attrs["-fullscreen"] is False


# ------------------------------------------------------------------ Auto turned on or off for the reader
def test_reading_mode_says_once_a_session_that_it_turned_auto_on(hidden_root):
    w = _reading(hidden_root)
    w.enter_reading()
    assert w.auto_var.get() and w.status_var.get() == READING_MODE_AUTO and w.canvas.note == READING_MODE_AUTO
    w.leave_reading()
    assert not w.auto_var.get() and w.status_var.get().startswith("Viewer: ")  # Auto off again, the normal line
    w.enter_reading()
    assert w.auto_var.get() and w.status_var.get() == READING_MODE  # said once
    w.leave_reading()
    w = _reading(hidden_root, auto=True)  # Auto on already: nothing to say
    w.enter_reading()
    assert w.status_var.get() == READING_MODE
    w.leave_reading()
    assert w.auto_var.get()


# ------------------------------------------------------------------ the full screen in the Translator role
class Roles(Reading):
    """`Reading` with the role switch of the App (`_on_role_changed`); what it starts is recorded."""

    _on_role_changed = A._on_role_changed

    def __init__(self, root):
        super().__init__(root)
        self._manual_area = True
        self.book_var = SimpleNamespace(get=lambda: "")  # (no book: no role kept for one)
        self.completed = 0

    def _sync_tools(self):
        pass

    def _close_find(self):
        pass

    def _complete_on_show(self):
        self.completed += 1


def test_the_translator_s_full_screen_keeps_auto_as_set_and_says_what_the_pointer_does(hidden_root):
    for auto in (False, True):
        w = _reading(hidden_root, auto=auto)
        w.role_var.set("translator")
        w.enter_reading()
        assert w.reading and w.auto_var.get() is auto  # Auto as the person set it: never turned on for them
        assert w.status_var.get() == FULL_SCREEN_TRANSLATOR == w.canvas.note
        w.leave_reading()
        assert not w.reading and w.auto_var.get() is auto and w.status_var.get().startswith("Viewer: ")
    assert not getattr(w, "_reading_auto_told", False)  # the Reader's line about Auto never said for it


def test_the_full_screen_follows_a_role_change_and_leaving_gives_auto_back(hidden_root):
    w = Roles(hidden_root)
    w.enter_reading()  # the Reader's: Auto on while it lasts
    assert w.auto_var.get() and w.status_var.get() == READING_MODE_AUTO
    w.role_var.set("translator")  # a book's start sets the role (`_apply_role`): the full screen follows
    w._on_role_changed(chosen=False)
    assert w.reading and not w.auto_var.get() and w.status_var.get() == FULL_SCREEN_TRANSLATOR
    assert w.completed == 1  # the regions a Reader's page from the cache never read are read for the Translator
    w.role_var.set("reader")
    w._on_role_changed(chosen=False)
    assert w.reading and w.auto_var.get() and w.status_var.get() == READING_MODE  # (Auto said once a session)
    w.leave_reading()
    assert not w.auto_var.get()  # as the person had it before the full screen


def test_the_translator_s_notes_stay_long_enough_to_read_and_the_reader_s_as_ever(hidden_root):
    w = _reading(hidden_root)
    w.enter_reading()
    short, long = "Saved.", "x" * 400
    assert w._note_ms(short) == w._note_ms(long) == READING_NOTE_MS  # the Reader's: a few seconds
    w.role_var.set("translator")
    assert w._note_ms(short) == READING_NOTE_MS  # a short line: as long as the Reader's
    assert w._note_ms("y" * 100) == 100 * NOTE_MS_PER_CHAR > READING_NOTE_MS  # longer by its length
    assert w._note_ms(long) == TRANSLATOR_NOTE_MAX_MS  # and never more than this
    w.say("Translate a page first: press F5.")  # what the window's status line says, on the page
    assert w.canvas.note == "Translate a page first: press F5." and w.canvas._note_job is not None
    w.leave_reading()


def _run_window(hidden_root, tmp_path):
    w = _batch_window(hidden_root, tmp_path)
    w._auto_switched = lambda: A._auto_switched(w)
    w.auto_var.trace_add("write", lambda *_a: w._auto_switched())  # as App._build_ui has it
    w.idle = []
    w.after_idle = w.idle.append
    return w


def _idle(w):
    while w.idle:
        w.idle.pop(0)()


def test_a_whole_book_run_says_once_a_session_that_it_turned_auto_off(hidden_root, tmp_path, desk):
    w = _run_window(hidden_root, tmp_path)
    w.auto_var.set(True)  # the reader's own: nothing said
    assert w.idle == []
    w._start_batch(w.selected, 0, True)
    assert not w.auto_var.get() and w.status_var.get() == "Whole-book run starting..."
    _idle(w)
    assert w.status_var.get() == RUN_AUTO_OFF  # in place of the run's first line
    w._batching = False  # the run ended: Auto back on (`jobs._batch_done`), nothing said here
    w.auto_var.set(True)
    assert w.idle == []
    w._start_batch(w.selected, 0, True)  # the next run: said once a session
    _idle(w)
    assert w.status_var.get() == "Whole-book run starting..."


def test_a_run_with_auto_off_before_says_nothing_of_it(hidden_root, tmp_path, desk):
    w = _run_window(hidden_root, tmp_path)
    w._start_batch(w.selected, 0, True)
    _idle(w)
    assert w.status_var.get() == "Whole-book run starting..." and not getattr(w, "_run_auto_told", False)


# ------------------------------------------------------------------ a book with no name read in reading mode
def _read_in_reading_mode(flow, pages=2):
    flow.reading = True
    asked = len(flow.dialogs)
    for n in range(pages):
        flow._on_new_page(_frame(ink=(40 + n, 30, 80, 70)), None)  # translated page by page, no dialog
    assert len(flow.dialogs) == asked and flow._unkept_reading == pages
    flow._jobs = queue.Queue()  # (the page jobs: not run here)
    flow.busy = False
    flow.reading = False
    flow.after_idle = lambda func: func()


def test_leaving_reading_mode_asks_once_for_the_name_of_a_book_kept_nowhere(flow, monkeypatch):
    monkeypatch.setattr(type(flow), "_ask_name_after_reading", A._ask_name_after_reading, raising=False)
    assert flow.book_var.get() == "Yomizuq"  # the viewer's name: names no book
    _read_in_reading_mode(flow)
    flow._ask_name_after_reading()
    d = flow.asked()
    assert d is not None and d.generic and flow._unkept_reading == 0
    d.on_answer("page", "Star Road 1")
    assert flow.book_var.get() == "Star Road 1"
    assert flow.status_var.get() == KEPT_FROM_NOW.format(book="Star Road 1")
    flow.book_var.set("Yomizuq")  # the next time in this session, for this viewer: not asked again
    _read_in_reading_mode(flow)
    flow._ask_name_after_reading()
    assert len(flow.dialogs) == 1


def test_nothing_is_asked_when_the_book_has_a_name_or_nothing_was_read(flow, monkeypatch):
    monkeypatch.setattr(type(flow), "_ask_name_after_reading", A._ask_name_after_reading, raising=False)
    flow.after_idle = lambda func: func()
    flow._ask_name_after_reading()  # nothing read in reading mode
    assert flow.dialogs == []
    _read_in_reading_mode(flow)
    flow.book_var.set("Star Road 1")  # named meanwhile
    flow._ask_name_after_reading()
    assert flow.asked() is None
    flow.book_var.set("Yomizuq")
    _read_in_reading_mode(flow)
    flow.settings.cache_enabled = False  # nothing would be kept under a name either
    flow._ask_name_after_reading()
    assert flow.asked() is None
