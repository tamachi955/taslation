"""The whole-book start dialog: Enter answers page by page (the lighter choice), the answer is kept per book - a
book read page by page is not asked about again, a book read whole is asked about with Start as Enter's answer - and
closing the dialog ("not now") is page by page for that book until TASlation closes."""
from __future__ import annotations

import json
import queue

import pytest
from test_start_flow import Flow, _frame, _no_problems

from taslation.i18n import set_language
from taslation.ui import jobs
from taslation.ui.dialogs.start import StartDialog

BOOK = "My Story 2"


# ------------------------------------------------------------------ the dialog
def test_enter_answers_page_by_page_unless_the_book_was_read_whole_before(hidden_root):
    answers = []
    d = StartDialog(hidden_root, BOOK, generic=False, ask=True, on_answer=lambda *a: answers.append(a))
    d.withdraw()
    start, page = d.buttons
    assert d.default == "page" and str(page.cget("default")) == "active" and str(start.cget("default")) == "normal"
    assert d.bind("<Return>")  # Enter answers the default
    d._answer(d.default)
    assert answers == [("page", BOOK)]
    d = StartDialog(hidden_root, BOOK, generic=False, ask=True, on_answer=lambda *a: answers.append(a),
                    default="start")
    d.withdraw()
    start, page = d.buttons
    assert d.default == "start" and str(start.cget("default")) == "active"
    d._answer(d.default)
    assert answers[-1] == ("start", BOOK)


# ------------------------------------------------------------------ the answer kept per book
@pytest.fixture
def flow(hidden_root, tmp_path, monkeypatch):
    dialogs = []

    class Recorded:
        def __init__(self, master, name, generic, ask, on_answer, matches=(), hint="", default="page"):
            self.name, self.generic, self.ask, self.on_answer, self.default = name, generic, ask, on_answer, default
            dialogs.append(self)

    monkeypatch.setattr(jobs, "StartDialog", Recorded)
    _no_problems(monkeypatch)
    made = []

    def window():
        w = Flow(hidden_root, tmp_path)  # (the same state folder: TASlation opened again)
        w.dialogs = dialogs
        w.book_var.set(BOOK)
        made.append(w)
        return w

    yield window
    set_language("en")


def _first_page(w):
    w._on_new_page(_frame(), None)
    return w.asked()


def _kept(w):
    data = json.loads((w.settings.state_dir / "ui.json").read_text(encoding="utf-8"))
    return data.get(jobs.BOOK_STARTS, {})


def test_a_book_read_page_by_page_is_not_asked_about_again(flow):
    w = flow()
    d = _first_page(w)
    assert d is not None and d.ask and not d.generic and d.default == "page"
    d.on_answer("page", BOOK)
    assert _kept(w) == {BOOK: "page"} and w.busy and not w.batches
    w = flow()  # opened again
    assert _first_page(w) is d  # no new dialog ...
    assert w.busy and not w.batches  # ... the page is translated as it is
    assert w.status_var.get().startswith("This book is translated page by page, as you chose before.")


def test_a_book_read_whole_is_asked_about_with_start_first(flow):
    w = flow()
    _first_page(w).on_answer("start", BOOK)
    assert _kept(w) == {BOOK: "start"}
    w = flow()
    d = _first_page(w)
    assert d.ask and d.default == "start" and not w.batches  # asked: a run never starts without the reader's go
    w.book_var.set("My Story 3")  # another book: the lighter answer first
    w._book_scanned, w._start_pending, w._start_dialog = False, None, None
    w._jobs = queue.Queue()
    w.busy = False
    assert _first_page(w).default == "page"


def test_not_now_lasts_for_the_session_and_is_not_kept(flow):
    w = flow()
    d = _first_page(w)
    d.on_answer(None, BOOK)  # the dialog closed
    assert w.busy and not w.batches  # this page translated page by page
    assert w._book_scanned and w._scanned_book == BOOK
    assert w.status_var.get().startswith("Not now: this book is translated page by page until you close TASlation.")
    assert not (w.settings.state_dir / "ui.json").exists() or _kept(w) == {}
    w._handle_event("translate_done", {})
    w._jobs = queue.Queue()
    count = len(w.dialogs)
    w._on_new_page(_frame(), None)  # the next page of the book: not asked again
    w.asked()
    assert len(w.dialogs) == count
    w = flow()  # opened again: asked again
    assert _first_page(w) is not None and len(w.dialogs) == count + 1
