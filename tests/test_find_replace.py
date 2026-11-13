"""Find and replace across the book: the matching rules, the change on the cache (text only), one undo across pages, a
merging save, the page on show lettered again, the series sheet asked once, and the window. Synthetic lines only."""
from __future__ import annotations

import inspect
import random
import time
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr

from taslation.annotations import CharacterSheet, GlossaryEntry
from taslation.cache import BookCache, CachedBubble, CachedPage, CacheStore, TextEdit
from taslation.config import Settings
from taslation.fingerprint import FINGERPRINT_HEX_LEN
from taslation.i18n import CATALOGS, set_language
from taslation.locales.features import find_replace as texts
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import jobs as jobs_mod  # (the name check the window uses)
from taslation.ui.dialogs.find_replace import MAX_ROWS, REFRESH_MS, FindReplaceDialog
from taslation.ui.history import BookStep, EditHistory, Step
from taslation.ui.replace import Query, around, find_hits, reletter, replacements, sheet_rendering

BOX = (0.1, 0.1, 0.3, 0.2)


def tip_of(widget):
    """The tooltip given to *widget* with `tooltip.tip` (None when it has none)."""
    return getattr(widget, "_tooltip", None)


def fingerprint(seed: int) -> str:
    return f"{random.Random(seed).getrandbits(FINGERPRINT_HEX_LEN * 4):0{FINGERPRINT_HEX_LEN}x}"


def bubble(text: str, y: float = 0.1, **kept) -> CachedBubble:
    return CachedBubble(box=(0.1, y, 0.3, y + 0.1), text=text, **kept)


def page(seed: int, *bubbles: CachedBubble, **kept) -> CachedPage:
    return CachedPage(fingerprint=fingerprint(seed), aspect=0.7, bubbles=list(bubbles), seq=seed, **kept)


@pytest.fixture
def store(tmp_path):
    return CacheStore(tmp_path / "cache")


@pytest.fixture
def cache(store):
    c = store.open("Book", "m")
    c.pages = [page(0, bubble("Anna runs."), bubble("Where is Anna? Anna!", 0.3)),
               page(1, bubble("Annabel waits.")),
               page(2, bubble("ANNA sleeps.", flags=["revised"], note="a remark"), incomplete=True),
               page(3, bubble("Nothing here."))]
    c.dirty = True
    c.save()
    return c


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Jobs:
    def put(self, job):
        job()


class Window:
    """The parts of the App that find and replace uses."""

    _find = None
    _find_asked = None
    _batching = False
    batch = None
    open_find_replace = app_mod.App.open_find_replace
    _find_kept = app_mod.App._find_kept
    _close_find = app_mod.App._close_find
    _refresh_find = app_mod.App._refresh_find
    _book_text_changed = app_mod.App._book_text_changed
    _book_cache = app_mod.App._book_cache
    _find_hits = app_mod.App._find_hits
    _replace_in_book = app_mod.App._replace_in_book
    _stored = app_mod.App._stored
    _carry_replacement = app_mod.App._carry_replacement
    undo_edit = app_mod.App.undo_edit
    redo_edit = app_mod.App.redo_edit
    _step_through = app_mod.App._step_through
    _record = app_mod.App._record
    _on_role_changed = app_mod.App._on_role_changed

    def __init__(self, cache, store, result=None, pipeline=None):
        self.store = store
        self.pipeline = pipeline or SimpleNamespace(
            cache=cache, annotations=None, last=None, check_sheet=lambda: None, rerender=lambda r: None,
            settings=SimpleNamespace(fingerprint_max_distance=36, match_min_iou=0.3))
        self.settings = Settings()
        self.last_result = result
        self.history = EditHistory()
        self.role_var, self.book_var, self.lang_var, self.model_var = Var("translator"), Var("Book"), Var("English"), Var("m")
        self.reading = self.busy = False
        self._ordering = self._chosen_region = None
        self.events: list[tuple[str, dict]] = []
        self.said: list[str] = []
        self.lines: list[str] = []
        self._jobs = Jobs()

    def _post(self, kind, **data):
        self.events.append((kind, data))
        if kind == "translate_done":
            self.busy = False
        elif kind == "find":
            self._book_text_changed(data.get("lines", ()))

    def _go_busy(self):
        self.busy = True

    def say(self, key, **values):
        self.said.append(key)

    def status(self, render):
        self.lines.append(render())

    def _result_on_show(self):
        return True

    def _sync_tools(self):
        pass

    def _redisplay(self):
        pass

    def _ensure_cache(self, book, model, language):
        self.pipeline.cache = self.store.open(book, model, language)
        return True

    # what the tests look at
    def kinds(self):
        return [k for k, _d in self.events]


@pytest.fixture
def window(cache, store):
    return Window(cache, store)


def texts_of(cache):
    return [b.text for p in sorted(cache.pages, key=lambda p: p.seq) for b in p.bubbles]


def on_disk(store, language="English"):
    return texts_of(store.open("Book", "m", language))


# ------------------------------------------------------------------ the matching rules
def spots(text, **options):
    rx = Query(options.pop("find"), **options).pattern()
    return [text[m.start():m.end()] for m in rx.finditer(text)]


def test_the_search_ignores_case_and_takes_parts_of_words_unless_told():
    assert spots("Anna, ANNA, Annabel", find="anna") == ["Anna", "ANNA", "Anna"]
    assert spots("Anna, ANNA, Annabel", find="Anna", match_case=True) == ["Anna", "Anna"]
    assert spots("Anna, ANNA, Annabel", find="anna", whole_word=True) == ["Anna", "ANNA"]
    assert spots("Anna, ANNA, Annabel", find="Anna", match_case=True, whole_word=True) == ["Anna"]


def test_a_word_ends_at_punctuation_and_not_at_a_digit_or_a_letter_of_any_script_with_spaces():
    assert spots("Ann-san, Ann's (Ann) Ann.", find="Ann", whole_word=True) == ["Ann"] * 4
    assert spots("Ann2 2Ann Anné éAnn", find="Ann", whole_word=True) == []
    assert spots("Иван Иванов", find="Иван", whole_word=True) == ["Иван"]


def test_whole_word_says_nothing_beside_a_script_without_spaces():
    assert spots("アンナは走る", find="アンナ", whole_word=True) == ["アンナ"]
    assert spots("Annaは走る", find="Anna", whole_word=True) == ["Anna"]
    assert spots("李明说", find="李明", whole_word=True) == ["李明"]
    assert spots("안나는 달린다", find="안나", whole_word=True) == ["안나"]
    assert spots("แอนนาวิ่ง", find="แอนนา", whole_word=True) == ["แอนนา"]


def test_what_is_typed_is_taken_literally():
    assert spots("a.b axb (x) [y] \\d", find="a.b") == ["a.b"]
    assert spots("a.b (x) [y] \\d", find="(x)") == ["(x)"]
    assert spots("a.b (x) [y] \\d", find="\\d") == ["\\d"]
    assert spots("wait... what", find="...", whole_word=True) == ["..."]


def test_an_empty_find_looks_for_nothing(cache):
    assert Query("").pattern() is None and find_hits(cache, Query("")) == []


def test_no_match(cache):
    assert find_hits(cache, Query("zzz")) == []
    assert replacements([], "x") == ([], 0)


def test_matches_come_in_page_order_with_their_place(cache):
    cache.pages.reverse()
    hits = find_hits(cache, Query("Anna", True))
    assert [(h.page, h.bubble, h.start) for h in hits] == [(1, 0, 0), (1, 1, 9), (1, 1, 15), (2, 0, 0)]
    assert around(hits[1]) == "Where is «Anna»? Anna!"


def test_the_line_around_a_match_is_one_line_and_cut_at_both_ends():
    text = "x" * 100 + " Anna\nspeaks " + "y" * 100
    hit = find_hits(SimpleNamespace(pages=[page(0, bubble(text))]), Query("Anna"))[0]
    line = around(hit, 8)
    assert line == "...xxxxxxx «Anna» speaks..." and "\n" not in line


# ------------------------------------------------------------------ the change, on the cache
def test_replace_all_in_one_step_writes_the_file_and_changes_only_the_text(window, cache, store):
    before = cache.to_json()
    assert window._replace_in_book(Query("Anna", False, True), "Hana", None)
    assert texts_of(cache) == ["Hana runs.", "Where is Hana? Hana!", "Annabel waits.", "Hana sleeps.", "Nothing here."]
    assert on_disk(store) == texts_of(cache)
    after = cache.to_json()
    for old, new in zip(before["pages"], after["pages"]):
        assert {k: v for k, v in old.items() if k != "bubbles"} == {k: v for k, v in new.items() if k != "bubbles"}
        for a, b in zip(old["bubbles"], new["bubbles"]):
            assert {k: v for k, v in a.items() if k != "text"} == {k: v for k, v in b.items() if k != "text"}
    assert not window.busy and window.history.done[-1].state == "done"
    assert window.lines == ["Replaced in 3 text area(s) on 2 page(s). Ctrl+Z takes it back."]


def test_flags_note_and_the_page_mark_stay(window, cache, store):
    window._replace_in_book(Query("ANNA", True), "HANA", None)
    saved = store.open("Book", "m").pages[2]
    assert saved.incomplete and saved.bubbles[0].text == "HANA sleeps."
    assert saved.bubbles[0].flags == ["revised"] and saved.bubbles[0].note == "a remark"


def test_replace_selected_takes_only_the_lines_picked(window, cache, store):
    hits = find_hits(cache, Query("Anna", True))
    window._replace_in_book(Query("Anna", True), "Hana", {hits[2].key})
    assert texts_of(cache)[1] == "Where is Anna? Hana!" and texts_of(cache)[0] == "Anna runs."
    assert on_disk(store)[1] == "Where is Anna? Hana!"


def test_nothing_is_written_until_replace(window, cache, store):
    stamp = cache.stamp
    window._find_hits(Query("Anna"))
    assert cache.stamp == stamp and not cache.dirty and not cache.touched and not window.history.done


def test_a_line_that_would_be_left_empty_stays_and_that_is_said(window, cache):
    cache.pages[3].bubbles[0].text = "Anna"
    window._replace_in_book(Query("Anna", True, True), "", None)
    assert texts_of(cache)[-1] == "Anna" and texts_of(cache)[0] == "runs."
    assert "1 text area(s) stay as they were: a translation cannot be left empty." in window.lines[-1]


def test_a_replacement_that_changes_nothing_is_no_step(window, cache):
    window._replace_in_book(Query("Anna", True), "Anna", None)
    assert window.lines == ["Nothing was changed."] and len(window.history) == 0
    assert window.history.book_step(("", "Book", "English")) is None


def test_put_texts_passes_over_a_bubble_that_changed_or_a_page_gone(cache):
    edits = [TextEdit(cache.pages[0].fingerprint, cache.pages[0].bubbles[0].box, "Not this.", "x"),
             TextEdit(fingerprint(99), BOX, "Anna runs.", "x")]
    assert cache.put_texts(edits) == [] and not cache.touched
    box = cache.pages[0].bubbles[0].box
    near = (box[0] + 0.0004, *box[1:])  # a saved file keeps four decimals
    assert cache.put_texts([TextEdit(cache.pages[0].fingerprint, near, "Anna runs.", "x")])
    assert cache.pages[0].bubbles[0].text == "x" and cache.dirty


def test_a_merging_save_keeps_it_and_what_another_process_saved(window, cache, store):
    other = BookCache.load(cache.path)
    other.add(page(7, bubble("Saved by the other process.")))
    other.save()
    window._replace_in_book(Query("Anna", True, True), "Hana", None)
    merged = store.open("Book", "m")
    assert len(merged) == 5 and texts_of(merged)[0] == "Hana runs." and "Saved by the other process." in texts_of(merged)
    cache.add(page(8, bubble("Later.")))  # a later save loses neither
    cache.save()
    assert texts_of(store.open("Book", "m"))[0] == "Hana runs."


def test_a_page_added_by_another_process_while_the_edit_waited_is_merged_too(cache, store):
    other = BookCache.load(cache.path)
    edits, _left = replacements(find_hits(cache, Query("Annabel")), "Bel")
    assert cache.put_texts(edits)
    other.add(page(7, bubble("Another.")))
    other.save()
    cache.save()
    assert {"Bel waits.", "Another."} <= set(texts_of(store.open("Book", "m")))


def test_a_file_that_cannot_be_written_is_said_and_the_change_stays_in_memory(window, cache, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError("locked")

    monkeypatch.setattr(cache, "save", refuse)
    window._replace_in_book(Query("Annabel"), "Bel", None)
    assert texts_of(cache)[2] == "Bel waits." and window.lines == ["Could not save the change: locked"]
    assert not window.busy and cache.touched


def test_it_waits_while_a_page_or_a_batch_is_at_work(window, cache):
    window.busy = True
    assert not window._replace_in_book(Query("Anna"), "Hana", None)
    window.busy, window._batching = False, True
    assert not window._replace_in_book(Query("Anna"), "Hana", None)
    assert window.said == ["TASlation is at work on a page. Try again when it is done."] * 2
    assert texts_of(cache)[0] == "Anna runs." and not window.history.done


# ------------------------------------------------------------------ undo across pages
def test_undo_takes_it_back_on_every_page_as_one_step_and_redo_makes_it_again(window, cache, store):
    before = texts_of(cache)
    window._replace_in_book(Query("Anna", True, True), "Hana", None)
    replaced = texts_of(cache)
    window.undo_edit()
    assert texts_of(cache) == before == on_disk(store)
    assert window.lines[-1] == "Replacement taken back in 2 text area(s)." and not window.busy
    window.redo_edit()
    assert texts_of(cache) == replaced == on_disk(store)
    assert window.lines[-1] == "Replacement made again in 2 text area(s)."
    window.undo_edit()
    window.undo_edit()  # nothing left
    assert texts_of(cache) == before and window.said[-1] == "Nothing to undo."


def test_undo_keeps_flags_too(window, cache, store):
    window._replace_in_book(Query("ANNA", True), "HANA", None)
    window.undo_edit()
    saved = store.open("Book", "m").pages[2]
    assert saved.bubbles[0].text == "ANNA sleeps." and saved.incomplete
    assert saved.bubbles[0].flags == ["revised"] and saved.bubbles[0].note == "a remark"


def test_undo_works_while_no_page_is_on_show_and_holds_no_page(window, cache):
    window._replace_in_book(Query("Anna"), "Hana", None)
    step = window.history.done[-1]
    assert isinstance(step, BookStep) and step.result is None and step.units == [] and step.touched == []
    window.last_result = None
    window.undo_edit()
    assert texts_of(cache)[0] == "Anna runs."


def test_a_line_changed_since_stays_when_it_is_taken_back(window, cache):
    window._replace_in_book(Query("Anna", True, True), "Hana", None)
    cache.pages[0].bubbles[0].text = "Translated again."
    window.undo_edit()
    assert texts_of(cache)[0] == "Translated again." and texts_of(cache)[1] == "Where is Anna? Anna!"


def test_only_the_newest_change_on_the_book_is_taken_back_so():
    history = EditHistory()
    who = ("", "Book", "English")
    a, b = [(fingerprint(0), 0.7)], [(fingerprint(1), 0.7)]
    older = history.record(_done(Step("edit", None, who, a)))
    wide = history.record(_done(BookStep(who)))
    assert history.book_step(who) is wide and history.last(a, who) is None  # the replacement goes first
    assert history.book_step(("", "Other", "English")) is None
    newer = history.record(_done(Step("edit", None, who, b)))
    assert history.book_step(who) is None  # a change after it: that one first, on its page
    assert history.last(b, who) is newer and history.last(a, who) is None
    history.taken_back(newer)
    assert history.book_step(who) is wide
    history.taken_back(wide)
    assert history.last(a, who) is older


def _done(step):
    step.state = "done"
    return step


def test_a_new_change_ends_the_redo_of_a_replacement_and_a_replacement_every_redo():
    history = EditHistory()
    who = ("", "Book", "English")
    a = [(fingerprint(0), 0.7)]
    wide = _done(BookStep(who))
    history.undone.append(wide)
    history.record(_done(Step("edit", None, who, a)))
    assert history.undone == []
    page_step_undone = _done(Step("edit", None, who, a))
    history.undone.append(page_step_undone)
    history.record(_done(BookStep(who)))
    assert history.undone == []


def test_a_replacement_after_an_edit_goes_back_first_on_any_page(window, cache):
    window.history.record(_done(Step("edit", None, ("", "Book", "English"), [(fingerprint(0), 0.7)])))
    window._replace_in_book(Query("Annabel"), "Bel", None)
    window.undo_edit()
    assert texts_of(cache)[2] == "Annabel waits." and len(window.history.undone) == 1


# ------------------------------------------------------------------ the page on show, with the real pipeline
@pytest.fixture
def real(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)
    result = pipeline.process(sample_page, complete=True)
    cache.add(page(40, bubble(result.translated[0].translated_text + " Elsewhere")))
    cache.save()
    return Window(cache, CacheStore(settings.cache_dir), result, pipeline), result, cache


def test_the_page_on_show_is_lettered_at_once_and_undo_brings_its_picture_back(real):
    w, result, cache = real
    region = result.translated[0]
    region.flags = ["revised"]
    old = region.translated_text
    picture = np.asarray(result.image).copy()
    w._replace_in_book(Query(old), "ZZZZ", None)
    assert region.translated_text == "ZZZZ" and w.kinds().count("result") == 1
    assert not np.array_equal(picture, np.asarray(result.image))
    assert region.flags == ["revised"]  # the text is all that changes
    assert texts_of(cache)[-1] == "ZZZZ Elsewhere"  # the other page: from the cache when it is next shown
    w.undo_edit()
    assert region.translated_text == old and texts_of(cache)[-1] == old + " Elsewhere"
    assert np.array_equal(picture, np.asarray(result.image))


def test_a_page_with_no_match_is_not_lettered_again(real):
    w, result, cache = real
    image = result.image
    w._replace_in_book(Query("Elsewhere"), "There", None)
    assert result.image is image and "result" not in w.kinds()
    assert reletter(w.pipeline, result, [TextEdit(fingerprint(1), BOX, "a", "b")]) is False


# ------------------------------------------------------------------ the series sheet
def sheet():
    return SimpleNamespace(entries=[GlossaryEntry("x", "Anna")], characters=[CharacterSheet("y", "Ben")])


def test_the_sheet_is_found_by_its_own_spelling():
    assert sheet_rendering(sheet(), Query("anna")) == "Anna" and sheet_rendering(sheet(), Query("ben")) == "Ben"
    assert sheet_rendering(sheet(), Query("anna", True)) is None
    assert sheet_rendering(sheet(), Query("Ann")) is None
    assert sheet_rendering(None, Query("Anna")) is None


def test_a_name_replaced_everywhere_is_offered_once_after_the_window_is_free(window, cache):
    window.pipeline.check_sheet = sheet
    window._replace_in_book(Query("anna", False, True), "Hana", None)
    assert [d["changes"] for k, d in window.events if k == "propose"] == [[("Anna", "Hana")]]
    assert window.kinds()[-2:] == ["translate_done", "propose"]


def test_part_of_the_lines_or_another_word_asks_nothing(window, cache):
    window.pipeline.check_sheet = sheet
    hits = find_hits(cache, Query("Anna", True, True))
    window._replace_in_book(Query("Anna", True, True), "Hana", {hits[0].key})
    window._replace_in_book(Query("Annabel"), "Bel", None)
    window._replace_in_book(Query("sleeps"), "", None)
    assert "propose" not in window.kinds()


# ------------------------------------------------------------------ the language and the book
def test_it_works_on_the_cache_of_the_language_chosen(window, cache, store):
    french = store.open("Book", "m", "French")
    french.add(page(0, bubble("Anna court.")))
    french.save()
    window.lang_var.set("French")
    hits, note = window._find_hits(Query("Anna"))
    assert hits == [] and note and window.pipeline.cache.language == "French"  # opened in the worker: then looked again
    hits, note = window._find_hits(Query("Anna"))
    assert [h.text for h in hits] == ["Anna court."] and note == ""
    window._replace_in_book(Query("Anna"), "Hana", None)
    assert on_disk(store, "French") == ["Hana court."] and on_disk(store)[0] == "Anna runs."


def test_undo_goes_with_the_language_it_was_made_in(window, cache, store):
    window._replace_in_book(Query("Annabel"), "Bel", None)
    window.lang_var.set("French")
    window._find_hits(Query("Anna"))
    window.undo_edit()
    assert window.said[-1] == "Nothing to undo on this page." and on_disk(store)[2] == "Bel waits."


def test_the_cache_of_another_language_is_not_touched_while_the_boxes_differ(window, cache):
    window.lang_var.set("French")
    assert window._replace_in_book(Query("Anna"), "Hana", None) is False
    assert texts_of(cache)[0] == "Anna runs."


def test_a_book_with_no_name_or_no_pages_says_so(window, store):
    window.book_var.set("")
    assert window._find_hits(Query("Anna")) == ([], "Give the book a name first (the Book field).")
    window.book_var.set("New book")
    assert window._find_hits(Query("Anna")) == ([], "Nothing is kept for this book in English yet.")
    assert window._find_hits(Query("Anna"))[0] == [] and window.pipeline.cache.book == "New book"
    window.pipeline = None
    assert window._find_hits(Query("Anna")) == ([], "Starting...")


def test_a_generic_name_asks_for_a_name_as_the_rest_of_the_window_does(window):
    window.book_var.set("untitled")
    assert jobs_mod.generic_book_name("untitled")
    assert window._find_hits(Query("Anna")) == ([], "Give the book a name first (the Book field).")


# ------------------------------------------------------------------ the window
@pytest.fixture
def opened(hidden_root, window):
    d = FindReplaceDialog(hidden_root, window._find_hits, window._replace_in_book, window.undo_edit, window.redo_edit)
    d.update_idletasks()
    window._find = d
    return d


def test_the_list_follows_what_is_typed_and_counts(opened, cache):
    d = opened
    assert d.count_var.get() == "" and str(d.all_btn.cget("state")) == "disabled"
    assert str(d.selected_btn.cget("state")) == "disabled"
    d.find_var.set("Anna")
    assert d._due is not None
    d.update_list()
    assert d.count_var.get() == "5 match(es) on 3 page(s)."
    assert [d.tree.item(i, "values")[0] for i in d.tree.get_children()] == ["1", "1", "1", "2", "3"]
    assert d.tree.item("1", "values")[1] == "Where is «Anna»? Anna!"
    d.word_var.set(True)
    d.update_list()
    assert d.count_var.get() == "4 match(es) on 2 page(s)."
    d.case_var.set(True)
    d.update_list()
    assert d.count_var.get() == "3 match(es) on 1 page(s)."
    d.find_var.set("zzz")
    d.update_list()
    assert d.count_var.get() == "No match." and not d.tree.get_children()
    d.find_var.set("")
    d.update_list()
    assert d.count_var.get() == "" and not d.tree.get_children()


def test_typing_searches_once_after_the_last_key(opened, monkeypatch):
    d = opened
    calls = []
    d.search = lambda q: (calls.append(q) or ([], ""))
    for text in ("A", "An", "Ann"):
        d.find_var.set(text)
    assert not calls and d._due is not None
    deadline = time.monotonic() + 5 * REFRESH_MS / 1000 + 2
    while not calls and time.monotonic() < deadline:
        d.update()
    assert [q.text for q in calls] == ["Ann"]


def test_the_window_blocks_nothing(opened, hidden_root):
    assert opened.grab_current() is None
    assert "grab_set" not in inspect.getsource(FindReplaceDialog)


def test_a_selected_line_and_the_buttons(opened, cache, store):
    d = opened
    d.find_var.set("Anna")
    d.case_var.set(True)
    d.update_list()
    d.tree.selection_set("2")
    d.update()
    assert str(d.selected_btn.cget("state")) == "normal"
    d.replace_var.set("Hana")
    assert on_disk(store)[1] == "Where is Anna? Anna!"
    d.replace_selected()
    assert on_disk(store)[1] == "Where is Anna? Hana!"
    d.update_list()
    assert d.count_var.get() == "3 match(es) on 2 page(s)."
    d.replace_all()
    assert "Anna" not in " ".join(on_disk(store)[:3])
    d.update_list()
    assert d.count_var.get() == "No match."


def test_the_selection_stays_when_the_list_is_looked_at_again(opened, cache):
    d = opened
    d.find_var.set("Anna")
    d.update_list()
    d.tree.selection_set("3")
    rows = d.rows
    d.update_list()  # as the window does on every focus: nothing changed, nothing built anew
    assert d.rows is rows and d.tree.selection() == ("3",)
    cache.pages[0].bubbles[0].text = "Anna walks."
    d.update_list()
    assert d.rows is not rows and d.tree.selection() == ("3",) and d.tree.item("0", "values")[1] == "«Anna» walks."


def test_ctrl_z_and_ctrl_y_work_in_the_window(hidden_root, window, cache):
    d = FindReplaceDialog(hidden_root, window._find_hits, window._replace_in_book, window.undo_edit, window.redo_edit)
    window._find = d
    d.find_var.set("Annabel")
    d.replace_var.set("Bel")
    d.update_list()
    d.replace_all()
    assert texts_of(cache)[2] == "Bel waits."
    assert d.bind("<Control-z>") and d.bind("<Control-y>")  # a dialog's keys do not reach the main window
    d.tk.eval(f"event generate {d} <Control-KeyPress-z>")
    d.update()
    d.destroy()


def test_a_book_of_2000_lines_is_searched_listed_and_replaced_without_delay(hidden_root, store, monkeypatch):
    cache = store.open("Long", "m")
    cache.pages = [page(i, *[bubble(f"Line {j} of Anna and of the others, with Anna twice.", j / 11) for j in range(10)])
                   for i in range(200)]
    cache.dirty = True
    cache.save()
    window = Window(cache, store)
    window.book_var.set("Long")
    d = FindReplaceDialog(hidden_root, window._find_hits, window._replace_in_book, window.undo_edit, window.redo_edit)
    d.find_var.set("a")  # thousands of matches: the worst a key can do
    start = time.perf_counter()
    d.update_list()
    d.update_idletasks()
    listed = time.perf_counter() - start
    assert len(d.hits) >= 10_000 and len(d.tree.get_children()) == MAX_ROWS
    assert "The first 500 are listed; Replace all takes every one." in d.count_var.get()
    d.find_var.set("Anna")
    start = time.perf_counter()
    d.update_list()
    d.replace_var.set("Hana")
    d.replace_all()
    replaced = time.perf_counter() - start
    assert all("Hana" in t and "Anna" not in t for t in texts_of(cache)) and len(texts_of(cache)) == 2000
    assert listed < 1.0 and replaced < 2.0, (listed, replaced)
    d.destroy()


def test_odd_characters_go_through_the_list(hidden_root, store, window, cache):
    cache.pages[3].bubbles[0].text = 'A {brace "quote\\ [x] $y'
    d = FindReplaceDialog(hidden_root, window._find_hits, window._replace_in_book, window.undo_edit, window.redo_edit)
    d.find_var.set("{brace")
    d.update_list()
    assert d.tree.item("0", "values")[1] == 'A «{brace» "quote\\ [x] $y'
    d.destroy()


def test_the_windows_event_reaches_the_dialog(window, opened):
    opened.find_var.set("Annabel")
    app_mod.App._handle_event(window, "find", {"lines": [("Nothing was changed.", {})]})
    assert window.lines == ["Nothing was changed."] and opened.said_var.get() == "Nothing was changed."
    assert opened._due is not None


def test_every_control_says_what_it_does(hidden_root, opened):
    d = opened
    for control in (d.find_entry, d.replace_entry, d.selected_btn, d.all_btn):
        assert tip_of(control) is not None and tip_of(control).text


def test_a_language_switch_builds_it_anew_with_what_it_showed(hidden_root, window, opened):
    d = opened
    d.find_var.set("Anna")
    d.replace_var.set("Hana")
    d.case_var.set(True)
    d.word_var.set(True)
    kept = window._find_kept()
    assert window._find is None and kept["find"] == "Anna" and kept["replace"] == "Hana" and kept["case"] and kept["word"]
    d.destroy()
    set_language("ja")
    again = FindReplaceDialog(hidden_root, window._find_hits, window._replace_in_book, window.undo_edit, window.redo_edit,
                              kept)
    assert again.title() == "検索と置換" and again.find_var.get() == "Anna" and again.case_var.get()
    assert again.count_var.get().startswith("1 ページに 3 件")
    source = inspect.getsource(app_mod.App._rebuild_ui)
    assert source.index("self._find_kept()") < source.index("child.destroy()") < source.index("self.open_find_replace(")
    again.destroy()


def test_leaving_the_translator_role_closes_it(hidden_root, window, opened):
    window.role_var.set("reader")
    window._on_role_changed()
    assert window._find is None and not opened.winfo_exists()
    window.open_find_replace()  # only in the translator role
    assert window._find is None


def test_a_finished_replacement_is_said_in_the_window(hidden_root, window, opened):
    d = opened
    d.find_var.set("Annabel")
    d.replace_var.set("Bel")
    d.update_list()
    d.replace_all()
    assert d.said_var.get() == "Replaced in 1 text area(s) on 1 page(s). Ctrl+Z takes it back."


# ------------------------------------------------------------------ the strings
def test_every_string_is_in_every_language_and_nothing_of_a_book_is_named():
    assert len(texts.TEXTS) >= 20
    for key in texts.TEXTS:
        for code, catalog in CATALOGS.items():
            if code != "en":
                assert catalog[key].strip(), (code, key)
