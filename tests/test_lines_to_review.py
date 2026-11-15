"""Translator mode's "Lines to review": every line of the book worth a look (flagged as it was translated, or with a
note for the reader), page by page, built from the cache alone (`dialogs.review_list`), the reasons in the words of
"Review this page" with the checks of the lettering of the page on show, narrowed to one reason or sorted by it, a
row selected only saying its page (nothing is sent to the viewer); the list made again after a page's result and a
change of the translations; and the page strip's pennant on a page with such lines (`strip.mark_pages_to_review`),
which says it by its shape and its "!" as well as its colour. Invented lines."""
from __future__ import annotations

import random
import time
from types import SimpleNamespace

import pytest
from fake_strip import FakeRun
from helpers import EN_TEXTS, FakeOcr
from test_find_replace import Window as FindWindow
from test_page_strip import Window as StripWindow
from test_page_strip import _click, no_way_to_the_viewer  # noqa: F401 - (a fixture)
from test_translator_mode import Window as TranslatorWindow

from taslation.cache import CachedBubble, CachedPage, CacheStore
from taslation.capture import windows as capture_windows
from taslation.fingerprint import FINGERPRINT_HEX_LEN
from taslation.i18n import CATALOGS, set_language
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import strip as strip_mod
from taslation.ui.dialogs import page_list
from taslation.ui.dialogs import review_list as review_mod
from taslation.ui.dialogs.review_list import (LinesToReviewDialog, book_lines, lines_on_page, reason_words,
                                              with_lettering, worth_a_look)
from taslation.ui.strip import CELL_W, REVIEW_TAG, mark_pages_to_review, page_tip

A = app_mod.App
BOX = (0.1, 0.1, 0.3, 0.2)
BOX2 = (0.5, 0.1, 0.7, 0.2)


def fingerprint(seed: int) -> str:
    return f"{random.Random(seed).getrandbits(FINGERPRINT_HEX_LEN * 4):0{FINGERPRINT_HEX_LEN}x}"


def _book(settings, name="Book"):
    store = CacheStore(settings.cache_dir)
    cache = store.open(name, "m")
    cache.pages = [CachedPage(fingerprint(0), 0.7, [CachedBubble(BOX, "Fine."),
                                                     CachedBubble(BOX2, "Far too\nlong a line.", flags=["long"])], seq=2),
                   CachedPage(fingerprint(1), 0.7, [CachedBubble(BOX, "Tiny.", flags=["small", "ocr"]),
                                                     CachedBubble(BOX2, "A pun.", note="A play on a name.")], seq=0),
                   CachedPage(fingerprint(2), 0.7, [CachedBubble(BOX, "Placeless.", flags=["revised"])], seq=-1)]
    cache.dirty = True
    cache.save()
    return store, cache


@pytest.fixture
def no_keys(monkeypatch):
    """Whatever would reach a window of another program: a key, a click, a mouse move."""
    sent: list[str] = []
    for name in ("post_key", "post_click", "_send_key", "_send_mouse"):
        monkeypatch.setattr(capture_windows, name, lambda *a, name=name, **k: sent.append(name))
    return sent


# ------------------------------------------------------------------ the rows
def test_the_lines_come_page_by_page_with_their_reasons_and_a_page_without_a_place_last(settings):
    _store, cache = _book(settings)
    rows = book_lines(cache)
    assert [(r.page, r.bubble, r.text, r.codes) for r in rows] == [
        (1, 0, "Tiny.", ("small", "ocr")), (1, 1, "A pun.", ("note",)), (3, 1, "Far too\nlong a line.", ("long",)),
        (0, 0, "Placeless.", ("revised",))]  # numbered as `taslation review` and "My corrections" number pages
    assert rows[0].fingerprint == fingerprint(1) and rows[2].box == BOX2
    assert worth_a_look(CachedBubble(BOX, "Fine.")) == () and lines_on_page(cache.pages[1]) == 2
    assert worth_a_look(CachedBubble(BOX, "x", flags=["long", "long"], note="  ")) == ("long",)


def test_the_reasons_are_said_as_the_page_review_says_them_in_the_windows_language():
    assert reason_words("small") == "set under the readable size"
    assert reason_words("note") == "note for the reader"
    assert reason_words("tight") == "letters touch the bubble's edge"  # a check of the lettering
    assert reason_words("revised") == "revised"  # a code of an earlier version: as it is
    set_language("ja")
    try:
        assert reason_words("small") == CATALOGS["ja"]["set under the readable size"]
        assert reason_words("tight") == CATALOGS["ja"]["letters touch the bubble's edge"]
        assert reason_words("note") == CATALOGS["ja"]["note for the reader"]
    finally:
        set_language("en")


def _pipeline(settings, book="Book"):
    cache = CacheStore(settings.cache_dir).open(book, "m")
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)


def test_the_page_on_show_adds_what_the_checks_of_its_lettering_found(settings, sample_page):
    p = _pipeline(settings)
    result = p.process(sample_page, complete=True)
    for b in p.cache.pages[0].bubbles:
        b.flags = []
    first, second, third = result.regions[:3]
    first.letter_flags = ("tight", "no-fit")
    second.letter_flags = ("hyphenated", "not-a-check")
    third.letter_flags, third.status = ("tight",), "dropped"  # dropped: never one, as on the page review
    p.cache.pages[0].bubbles[[b.text for b in p.cache.pages[0].bubbles].index(second.translated_text)].flags = ["long"]
    assert book_lines(p.cache)[0].codes == ("long",)
    rows = with_lettering(book_lines(p.cache), p.cache, result, p.settings)
    assert {r.text: r.codes for r in rows} == {first.translated_text: ("tight", "no-fit"),
                                               second.translated_text: ("long", "hyphenated")}
    assert all(r.page == 1 for r in rows) and with_lettering(rows, p.cache, None, p.settings) == rows

    class Shown(TranslatorWindow):  # the window: the page on show is a page of the book's cache
        _book_cache = A._book_cache
        _review_list_rows = A._review_list_rows

    w = Shown(p, result)
    assert {r.text for r in w._review_list_rows()} == {first.translated_text, second.translated_text}
    w.book_var.set("Another")
    assert w._review_list_rows() == []  # (another book in the boxes: its cache is opened first)
    w.book_var.set("")
    assert w._review_list_rows() is None


# ------------------------------------------------------------------ the list
def _texts(d):
    return [(d.tree.item(i, "text"), d.tree.set(i, "why"), d.tree.set(i, "text")) for i in d.tree.get_children()]


def test_the_list_says_why_narrows_to_a_reason_sorts_and_a_row_selected_only_says_its_page(hidden_root, settings,
                                                                                         no_keys):
    set_language("en")
    _store, cache = _book(settings)
    d = LinesToReviewDialog(hidden_root, lambda: book_lines(cache))
    try:
        d.withdraw()
        assert _texts(d) == [("1", "set under the readable size; TASlation may have misread the Japanese", "Tiny."),
                             ("1", "note for the reader", "A pun."),
                             ("3", "far longer than the Japanese", "Far too long a line."),
                             ("?", "revised", "Placeless.")]
        assert d.line_var.get() == "4 line(s) worth a look."
        assert list(d.reason_box.cget("values")) == [
            "All reasons", "far longer than the Japanese (1)", "note for the reader (1)", "revised (1)",
            "set under the readable size (1)", "TASlation may have misread the Japanese (1)"]
        d.choose_reason(1)
        assert [t[2] for t in _texts(d)] == ["Far too long a line."]
        assert d.line_var.get() == "1 of 4 line(s) worth a look." and d.reason_var.get().startswith("far longer")
        d.choose_reason(0)
        d.sort_by("why")
        assert [t[2] for t in _texts(d)] == ["Far too long a line.", "A pun.", "Placeless.", "Tiny."]
        d.sort_by("page")
        rows = d.tree.get_children()
        d.tree.selection_set(rows[2])
        d.update()
        assert d.line_var.get() == "On page 3. Turn to it in your viewer: nothing is sent to it from here."
        d.tree.selection_set(rows[3])
        d.update()
        assert d.line_var.get() == page_list.PLACE_UNKNOWN
        d.tree.selection_set(rows[2])
        cache.pages[1].bubbles[0].flags = []  # (looked at in the editor meanwhile)
        d.fill()
        assert len(d.tree.get_children()) == 3 and d.tree.set(d.tree.selection()[0], "text") == "Far too long a line."
        d.choose_reason(d.reason_codes.index("long") + 1)
        cache.pages[0].bubbles[1].flags = []
        d.fill()  # the reason's last line went: every reason again
        assert d.reason == "" and d.reason_var.get() == "All reasons" and len(d.tree.get_children()) == 2
        for page in cache.pages:
            for b in page.bubbles:
                b.flags, b.note = [], ""
        d.fill()
        assert not d.tree.get_children() and d.empty.winfo_manager() and not d.tree.winfo_manager()
        assert str(d.empty.cget("text")) == review_mod.EMPTY and d.line_var.get() == ""
        d.rows_of = lambda: None
        d.fill()
        assert str(d.empty.cget("text")) == page_list.PageListDialog.NO_BOOK
    finally:
        d.destroy()
    assert no_keys == []


class Listing(FindWindow):
    """Find and replace's stand-in window with the two lists of the book's lines and their refresh on "find"."""

    _corrections = _to_review = None
    open_corrections = A.open_corrections
    open_lines_to_review = A.open_lines_to_review
    _open_book_list = A._open_book_list
    _correction_rows = A._correction_rows
    _review_list_rows = A._review_list_rows
    _refresh_corrections = A._refresh_corrections

    def _post(self, kind, **data):
        super()._post(kind, **data)
        if kind == "find":
            self._refresh_corrections()


def test_the_window_opens_the_books_cache_and_makes_the_list_again_after_a_change(hidden_root, settings, no_keys,
                                                                                 monkeypatch):
    set_language("en")
    store, book = _book(settings)
    other = store.open("Other", "m")
    w = Listing(other, store)  # the window's cache is another book's: the Book field names "Book"
    made: list[LinesToReviewDialog] = []

    def dialog(_master, rows_of):  # (over the hidden root: the stand-in window is no Tk window)
        d = LinesToReviewDialog(hidden_root, rows_of)
        d.withdraw()
        made.append(d)
        return d

    monkeypatch.setattr(review_mod, "LinesToReviewDialog", dialog)
    w.open_lines_to_review()
    d = made[-1]
    try:
        assert w.pipeline.cache.book == "Book" and len(d.tree.get_children()) == 4  # opened in the worker, then listed
        w.pipeline.cache.pages[1].bubbles[1].note = ""
        w._post("find")  # a change of the translations (an edit, a replacement), or a page's result
        assert [d.tree.set(i, "text") for i in d.tree.get_children()] == ["Tiny.", "Far too long a line.",
                                                                          "Placeless."]
        w.open_lines_to_review()  # asked for again: the same list, brought to the front
        assert w._to_review is d and len(made) == 1
    finally:
        d.destroy()
    assert no_keys == []


def test_the_lists_strings_are_in_every_language():
    keys = [review_mod.TITLE, review_mod.EMPTY, review_mod.COUNTED, review_mod.FILTERED, review_mod.SHOW,
            review_mod.ALL_REASONS, review_mod.SHOW_TIP, review_mod.EXPLAIN, review_mod.NOTE_WORDS, strip_mod.REVIEW_LINE,
            "Lines to review...", "List the lines of the whole book that are worth a look, page by page."]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(k in catalog for k in keys), (code, [k for k in keys if k not in catalog])


# ------------------------------------------------------------------ the page strip
class Strip(StripWindow):
    """The strip's stand-in window with the pipeline's cache and the status line."""

    def __init__(self, master, batch, cache):
        super().__init__(master, batch=batch)
        self.pipeline = SimpleNamespace(cache=cache, settings=SimpleNamespace(fingerprint_max_distance=6))

    def status(self, render):
        self.lines.append(render())


def _run_cache(settings, name="Book"):
    cache = CacheStore(settings.cache_dir).open(name, "m")
    run_fp = lambda seq: f"{seq:080x}"  # noqa: E731 - (as the fake run gives them)
    cache.pages = [CachedPage(run_fp(1), 0.7, [CachedBubble(BOX, "Fine.")], seq=0),
                   CachedPage(run_fp(2), 0.7, [CachedBubble(BOX, "Tiny.", flags=["small"]),
                                               CachedBubble(BOX2, "Long.", flags=["long"])], seq=1),
                   CachedPage(run_fp(3), 0.7, [CachedBubble(BOX, "A pun.", note="A play on a name.")], seq=2)]
    return cache


def _marks(w):
    c = w.page_strip.canvas
    return {seq: sorted(c.type(i) for i in c.find_withtag(f"p{seq}") if i in c.find_withtag(REVIEW_TAG))
            for seq in w._strip_model.order}


def test_the_strip_marks_the_pages_with_lines_worth_a_look_by_shape_and_mark_too(hidden_root, settings,
                                                                                no_way_to_the_viewer):
    set_language("en")
    run = FakeRun(lambda kind, data: None, pages=4, skip_every=99)
    cache = _run_cache(settings)
    w = Strip(hidden_root, run, cache)
    run.post = lambda kind, data: A._handle_event(w, kind, data) if kind in ("page_stage", "batch_memory") else None
    for seq in range(1, 5):
        run.read_page(seq)
    assert {seq: cell.review for seq, cell in w._strip_model.pages.items()} == {1: 0, 2: 0, 3: 0, 4: 0}
    run.translate_all()  # each page's lines are in the cache once its translation is done
    assert {seq: cell.review for seq, cell in w._strip_model.pages.items()} == {1: 0, 2: 2, 3: 1, 4: 0}
    assert _marks(w) == {1: [], 2: ["polygon", "text"], 3: ["polygon", "text"], 4: []}
    c = w.page_strip.canvas
    assert {c.itemcget(i, "text") for i in c.find_withtag(REVIEW_TAG) if c.type(i) == "text"} == {"!"}
    w.page_strip.canvas.xview_moveto(0)
    tip = w.page_strip.text_at(CELL_W + CELL_W // 2, 20)
    assert tip == page_tip(2, False, 2) and "2 line(s) on this page are worth a look" in tip
    assert w.page_strip.text_at(CELL_W // 2, 20) == page_tip(1)  # no line to look at: the tip as it was
    drawn = w.drawn
    _click(w, 3)
    assert w.lines[-1] == page_tip(3, False, 1) and w.drawn == drawn  # said, and nothing shown
    cache.pages[1].bubbles[0].flags = []  # looked at in the editor: the window's refresh marks it again
    mark_pages_to_review(w)
    assert w._strip_model.pages[2].review == 1
    cache.pages[1].bubbles[1].flags = []
    w.page_strip.redraw()
    mark_pages_to_review(w)
    assert _marks(w)[2] == []
    w.pipeline.cache = _run_cache(settings, "Other")  # another book's cache now: its pages are not these
    mark_pages_to_review(w)
    assert [w._strip_model.pages[s].review for s in (1, 2, 3, 4)] == [0, 0, 1, 0]


def test_an_open_list_is_made_again_once_the_runs_pages_are_translated(hidden_root, settings, monkeypatch):
    run = FakeRun(lambda kind, data: None, pages=2, skip_every=99)
    cache = _run_cache(settings)
    w = Strip(hidden_root, run, cache)
    filled: list[int] = []
    w._to_review = SimpleNamespace(winfo_exists=lambda: True, fill=lambda: filled.append(1))
    monkeypatch.setattr(strip_mod, "REVIEW_REFRESH_MS", 1)
    run.post = lambda kind, data: A._handle_event(w, kind, data) if kind == "page_stage" else None
    for seq in (1, 2):
        run.read_page(seq)
    run.translate_all()
    deadline = time.monotonic() + 2
    while not filled and time.monotonic() < deadline:
        hidden_root.update()
    assert filled == [1]  # once for the group of pages translated together
