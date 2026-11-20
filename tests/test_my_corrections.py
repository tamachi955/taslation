"""The translations a person wrote (`CachedBubble.edited`): marked by the region editor's Save and by Find and replace
(Ctrl+Z takes the mark back with the text), cleared by the model's answer to Ask again saved as it came, left as they
are by a spelling made consistent (the series sheet's "Apply to the n lines", a name's fix); kept through a merging
save, a refresh, a backup's export and import and a file of an earlier version; kept by "Translate again" and by a
whole-book run that translates again unless the person asks for them to go too; listed in "My corrections" (from the
cache alone: a row selected sends nothing to the viewer) and by `taslation review --corrections`. Invented lines."""
from __future__ import annotations

import argparse
import random

import pytest
from helpers import EN_TEXTS, FakeOcr, read_book, store_json
from test_batch import _fake_viewer
from test_find_replace import Window as FindWindow
from test_translator_mode import Window

from taslation import cli
from taslation.batch import BatchReader
from taslation.cache import CachedBubble, CachedPage, CacheStore, TextEdit
from taslation.capture import windows as capture_windows
from taslation.fingerprint import FINGERPRINT_HEX_LEN
from taslation.i18n import set_language
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui.dialogs import caches
from taslation.ui.dialogs import corrections as corrections_mod
from taslation.ui.dialogs.corrections import CorrectionsDialog
from taslation.ui.replace import Query
from taslation.ui.sheet_changes import rename_edits

TYPED = "Typed by the person."
ANSWER = "The model's other try."
BOX = (0.1, 0.1, 0.3, 0.2)
BOX2 = (0.5, 0.1, 0.7, 0.2)


def fingerprint(seed: int) -> str:
    return f"{random.Random(seed).getrandbits(FINGERPRINT_HEX_LEN * 4):0{FINGERPRINT_HEX_LEN}x}"


def marks(cache) -> dict[str, bool]:
    return {b.text: b.edited for p in cache.pages for b in p.bubbles}


def marked_on_disk(cache) -> list[str]:
    return [b["text"] for p in store_json(cache.path)["pages"] for b in p["bubbles"] if b.get("edited") is True]


def _pipeline(settings, book="Book"):
    cache = CacheStore(settings.cache_dir).open(book, "m")
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)


@pytest.fixture
def window(settings, sample_page):
    p = _pipeline(settings)
    return Window(p, p.process(sample_page, complete=True))


def _data(region, **changed):
    data = {"text": region.translated_text, "speaker": "", "kind": "", "continues": False, "note": "",
            "reader_note": "", "source": region.source_text}
    data.update(changed)
    return data


# ------------------------------------------------------------------ the mark in the file
def test_the_mark_is_written_only_when_set_and_a_file_without_it_reads_as_none():
    bubble = CachedBubble(box=BOX, text="A line.")
    assert "edited" not in bubble.to_json()
    bubble.edited = True
    assert bubble.to_json()["edited"] is True and CachedBubble.from_json(bubble.to_json()).edited
    assert CachedBubble.from_json({"box": list(BOX), "text": "An earlier version's line."}).edited is False
    assert CachedBubble.from_json({"box": list(BOX), "text": "x", "edited": "yes"}).edited is False  # True alone is
    later = CachedBubble.from_json({"box": list(BOX), "text": "x", "edited": True, "a_later_field": [1]})
    assert later.edited and later.text == "x"  # a later version's field is passed over


def test_the_mark_survives_a_merging_save_a_refresh_and_a_backup(settings, tmp_path):
    store = CacheStore(settings.cache_dir)
    mine, theirs = store.open("Merge", "m"), store.open("Merge", "m")  # the window, and a run in another process
    mine.add(CachedPage(fingerprint(0), 0.7, [CachedBubble(BOX, TYPED, edited=True), CachedBubble(BOX2, "Model's.")],
                        seq=0))
    mine.save()
    theirs.add(CachedPage(fingerprint(1), 0.7, [CachedBubble(BOX, "Another page.")], seq=1))
    theirs.save()  # merges what the window saved
    assert marked_on_disk(theirs) == [TYPED]
    assert [(r.page, r.text, r.bubble) for r in store.open("Merge", "m").corrections()] == [(1, TYPED, 0)]
    assert mine.refresh() and [r.text for r in mine.corrections()] == [TYPED]
    pytest.importorskip("cryptography")
    from taslation import backup

    out = tmp_path / "merge.tascache"
    backup.export_cache(store, "Merge", out, "correct horse battery staple")
    store.delete("Merge")
    assert backup.import_cache(store, out, "correct horse battery staple") == ("Merge", 2)
    assert [r.text for r in store.open("Merge", "m").corrections()] == [TYPED]


def test_corrections_come_page_by_page_and_a_page_without_a_place_last(settings):
    cache = CacheStore(settings.cache_dir).open("Order", "m")
    cache.pages = [CachedPage(fingerprint(3), 0.7, [CachedBubble(BOX, "Placeless.", edited=True)], seq=-1),
                   CachedPage(fingerprint(2), 0.7, [CachedBubble(BOX, "Third, second line.", edited=True),
                                                    CachedBubble(BOX2, "Model's.")], seq=4),
                   CachedPage(fingerprint(1), 0.7, [CachedBubble(BOX, "Model's."),
                                                    CachedBubble(BOX2, "First.", edited=True)], seq=0)]
    rows = cache.corrections()
    assert [(r.page, r.bubble, r.text) for r in rows] == [(1, 1, "First."), (5, 0, "Third, second line."),
                                                          (0, 0, "Placeless.")]
    assert rows[0].fingerprint == fingerprint(1) and rows[0].box == BOX2


# ------------------------------------------------------------------ what marks it, what clears it
def test_the_editor_marks_what_it_saves_and_ask_again_taken_as_it_came_clears_it(window):
    w = window
    cache = w.pipeline.cache
    region = w.last_result.regions[0]
    model = region.translated_text
    w._edit_region(region, _data(region, speaker="Mio"), w.last_result)  # no new translation: no mark
    assert not cache.corrections()
    w._edit_region(region, _data(region, text=TYPED), w.last_result)
    assert marks(cache)[TYPED] and marked_on_disk(cache) == [TYPED]
    w.undo_edit()
    assert marks(cache)[model] is False and not marked_on_disk(cache)
    w.redo_edit()
    assert marks(cache)[TYPED] and w.pipeline.corrections_on(w.last_result) == 1
    w._edit_region(region, _data(region, text=ANSWER, asked=True), w.last_result)  # Ask again's answer, as it came
    assert marks(cache)[ANSWER] is False and not cache.corrections()
    w._edit_region(region, _data(region, text=ANSWER + " Really.", asked=False), w.last_result)  # changed after it
    assert [r.text for r in cache.corrections()] == [ANSWER + " Really."]


def test_find_and_replace_marks_what_it_changes_and_undo_gives_each_line_its_mark_back(settings):
    store = CacheStore(settings.cache_dir)
    cache = store.open("Book", "m")
    cache.pages = [CachedPage(fingerprint(0), 0.7, [CachedBubble(BOX, "Anna runs."),
                                                     CachedBubble(BOX2, "Anna waits.", edited=True)], seq=0),
                   CachedPage(fingerprint(1), 0.7, [CachedBubble(BOX, "Nobody here.")], seq=1)]
    cache.dirty = True
    cache.save()
    w = FindWindow(cache, store)
    assert w._replace_in_book(Query("Anna", True, True), "Hana", None)
    assert marks(cache) == {"Hana runs.": True, "Hana waits.": True, "Nobody here.": False}
    assert sorted(marked_on_disk(cache)) == ["Hana runs.", "Hana waits."]
    w.undo_edit()
    assert marks(cache) == {"Anna runs.": False, "Anna waits.": True, "Nobody here.": False}
    assert marked_on_disk(cache) == ["Anna waits."]
    w.redo_edit()
    assert marks(cache) == {"Hana runs.": True, "Hana waits.": True, "Nobody here.": False}


def test_a_spelling_made_consistent_leaves_each_mark_as_it_was(settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    cache.pages = [CachedPage(fingerprint(0), 0.7, [CachedBubble(BOX, "Anna runs."),
                                                     CachedBubble(BOX2, "Anna waits.", edited=True)], seq=0)]
    made = cache.put_texts(rename_edits(cache, [("Anna", "Hanna")]))  # the sheet's "Apply to the n lines"
    assert marks(cache) == {"Hanna runs.": False, "Hanna waits.": True}
    cache.put_texts([e.undone() for e in reversed(made)])
    assert marks(cache) == {"Anna runs.": False, "Anna waits.": True}
    cache.put_texts([TextEdit(fingerprint(0), BOX, "Anna runs.", "Ana runs."),  # a name's fix (`name_check`)
                     TextEdit(fingerprint(0), BOX2, "Anna waits.", "Ana waits.")])
    assert cache.rename([("Ana", "Anne")]) == 2  # `taslation glossary apply`
    assert marks(cache) == {"Anne runs.": False, "Anne waits.": True}


def test_a_moved_region_keeps_its_mark(window):
    w = window
    region = w.last_result.regions[0]
    w._edit_region(region, _data(region, text=TYPED), w.last_result)
    x0, y0, x1, y1 = region.bbox
    w.pipeline.ocr = FakeOcr([region.source_text])  # the same reading in the box grown round it
    w._move_region(region, (x0 - 2, y0 - 2, x1 + 2, y1 + 2))
    assert region.translated_text == TYPED and [r.text for r in w.pipeline.cache.corrections()] == [TYPED]


# ------------------------------------------------------------------ translated again
def test_translate_again_keeps_the_corrected_lines_and_puts_the_page_back_when_nothing_is_new(settings, sample_page):
    p = _pipeline(settings)
    result = p.process(sample_page, complete=True)
    p.set_translation(result, result.regions[1], TYPED)
    seq = p.cache.pages[0].seq
    whole = sorted(b.text for b in p.cache.pages[0].bubbles)
    assert p.corrections_on(result) == 1
    held = p.pages_of(result)
    assert p.forget_page(result, keep_edited=True) == 1
    [kept] = p.cache.pages
    assert kept.incomplete and kept.seq == seq and [(b.text, b.edited) for b in kept.bubbles] == [(TYPED, True)]
    p.restore_pages(held)  # nothing was translated anew: the page as it was
    assert sorted(b.text for b in p.cache.pages[0].bubbles) == whole and not p.cache.pages[0].incomplete
    p.forget_page(result)  # the box ticked: theirs go too
    assert not p.cache.pages and p.corrections_on(result) == 0


def test_a_run_that_translates_again_keeps_the_corrected_lines_unless_told(settings, sample_page):
    p = _pipeline(settings)
    result = p.process(sample_page, complete=True)
    region = result.regions[1]
    p.set_translation(result, region, TYPED)
    scan = p.scan(sample_page, skip_cached=True, fresh=True)
    unit = scan.units[0]
    assert TYPED in [b.text for b in unit.kept] and region.source_text not in [r.source_text for r in unit.japanese()]
    p.commit_unit(unit, {i: "New." for i in range(len(unit.japanese()))})
    assert marked_on_disk(p.cache) == [TYPED]
    replaced = p.scan(sample_page, skip_cached=True, fresh=True, keep_edited=False).units[0]
    assert TYPED not in [b.text for b in replaced.kept]
    assert region.source_text in [r.source_text for r in replaced.japanese()]


@pytest.mark.parametrize("replace", [False, True])
def test_a_whole_book_run_passes_the_choice_on(replace, settings, sample_page, sample_page2, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    p = _pipeline(settings, "Run")
    asked: list[object] = []
    real = p.scan
    p.scan = lambda *a, **k: asked.append(k.get("keep_edited")) or real(*a, **k)
    read_book(BatchReader(p, hwnd=1, settings=settings, context_mode=True, retranslate=True,
                          replace_corrections=replace))
    assert asked and set(asked) == {not replace}


def test_the_command_line_flag_goes_with_retranslate(settings):
    parser = cli.build_parser()
    args = parser.parse_args(["batch", "--window", "Yomizuq", "--retranslate", "--replace-corrections"])
    assert args.retranslate and args.replace_corrections
    assert parser.parse_args(["batch", "--window", "Yomizuq"]).replace_corrections is False
    with pytest.raises(SystemExit, match="goes with --retranslate"):
        cli.cmd_batch(parser.parse_args(["batch", "--window", "Yomizuq", "--replace-corrections"]), settings)


def test_review_lists_the_corrections(settings, capsys):
    cache = CacheStore(settings.cache_dir).open("Some Book", "m", "English")
    cache.add(CachedPage(fingerprint(0), 0.7, [CachedBubble(BOX, "Fine."), CachedBubble(BOX2, TYPED, edited=True)],
                         seq=0))
    cache.add(CachedPage(fingerprint(1), 0.7, [CachedBubble(BOX, ANSWER, flags=["long"])], seq=1))
    cache.save()
    assert cli.cmd_review(argparse.Namespace(book="Some Book", language="", corrections=True), settings) == 0
    out = capsys.readouterr().out
    assert f"page 1 bubble 2: corrected\n    {TYPED}" in out and "1 of 3 cached translation(s) corrected by you" in out
    assert "Fine." not in out and ANSWER not in out
    assert cli.cmd_review(argparse.Namespace(book="Nothing Kept", language="", corrections=True), settings) == 0
    assert "no cached translations for 'Nothing Kept'" in capsys.readouterr().out
    assert cli.build_parser().parse_args(["review", "--book", "B", "--corrections"]).corrections


# ------------------------------------------------------------------ the question of "Translate again"
@pytest.mark.parametrize("tick", [False, True])
def test_the_question_has_a_box_to_tick(tick, hidden_root, monkeypatch):
    monkeypatch.setattr(caches, "foreground_window", lambda: 0)
    made: list[caches.WarningBox] = []
    press = ["go"]

    class Box(caches.WarningBox):
        """Never waited for on the screen: the box ticked or not, then the button *press* names."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.withdraw()
            made.append(self)
            self.seen = str(self.choice_box.cget("text")), self.choice_var.get()  # unticked at first
            self.choice_var.set(tick)
            self.after(30, (self.continue_btn if press[0] == "go" else self.cancel_btn).invoke)

    monkeypatch.setattr(caches, "WarningBox", Box)
    assert caches.ask_choice(hidden_root, "Again?", "Replace mine too", "Translate again", "Cancel") == (True, tick)
    assert made[-1].seen == ("Replace mine too", False)
    press[0] = "stay"
    assert caches.ask_choice(hidden_root, "Again?", "Replace mine too") == (False, False)  # Cancel: nothing chosen
    plain = Box.__mro__[1](hidden_root, "TASlation", "No box.")  # (the box of `ask`, with nothing to tick)
    plain.withdraw()
    assert plain.choice_box is None
    plain._continue()
    assert plain.answer and not plain.chosen


# ------------------------------------------------------------------ "My corrections"
class Listing(FindWindow):
    """Find and replace's stand-in window, with "My corrections" and its refresh on the "find" event."""

    _corrections = None
    open_corrections = app_mod.App.open_corrections
    _open_book_list = app_mod.App._open_book_list
    _correction_rows = app_mod.App._correction_rows
    _refresh_corrections = app_mod.App._refresh_corrections

    def _post(self, kind, **data):
        super()._post(kind, **data)
        if kind == "find":
            self._refresh_corrections()


@pytest.fixture
def no_keys(monkeypatch):
    """Whatever would reach a window of another program: a key or a click."""
    sent: list[str] = []
    for name in ("post_key", "post_click", "_send_key"):
        monkeypatch.setattr(capture_windows, name, lambda *a, name=name, **k: sent.append(name))
    return sent


def test_the_list_shows_the_corrections_and_a_row_selected_only_says_its_page(hidden_root, settings, no_keys):
    set_language("en")
    store = CacheStore(settings.cache_dir)
    cache = store.open("Book", "m")
    cache.pages = [CachedPage(fingerprint(0), 0.7, [CachedBubble(BOX, "Model's."),
                                                     CachedBubble(BOX2, "Two\nlines.", edited=True)], seq=2),
                   CachedPage(fingerprint(1), 0.7, [CachedBubble(BOX, TYPED, edited=True)], seq=-1)]
    w = Listing(cache, store)
    d = CorrectionsDialog(hidden_root, w._correction_rows)
    try:
        d.withdraw()
        rows = d.tree.get_children()
        assert [(d.tree.item(i, "text"), d.tree.set(i, "text")) for i in rows] == [("3", "Two lines."), ("?", TYPED)]
        assert d.line_var.get() == "2 translation(s) you corrected." and d.tree.winfo_manager()
        d.tree.selection_set(rows[0])
        d.update()
        assert d.line_var.get() == "On page 3. Turn to it in your viewer: nothing is sent to it from here."
        d.tree.selection_set(rows[1])
        d.update()
        assert d.line_var.get() == corrections_mod.PLACE_UNKNOWN
        cache.pages[1].bubbles[0].edited = False  # (a change of the translations meanwhile)
        d.tree.selection_set(rows[0])
        d.fill()
        assert len(d.tree.get_children()) == 1 and d.tree.selection() == ("0",)  # the row selected stays so
        cache.pages[0].bubbles[1].edited = False
        d.fill()
        assert not d.tree.get_children() and d.empty.winfo_manager() and not d.tree.winfo_manager()
        assert str(d.empty.cget("text")) == corrections_mod.EMPTY
        w.book_var.set("")
        d.fill()
        assert str(d.empty.cget("text")) == corrections_mod.NO_BOOK
    finally:
        d.destroy()
    assert no_keys == []


def test_the_list_opens_the_book_s_cache_when_another_is_open_and_follows_a_replacement(hidden_root, settings,
                                                                                         no_keys, monkeypatch):
    set_language("en")
    store = CacheStore(settings.cache_dir)
    other = store.open("Other", "m")
    book = store.open("Book", "m")
    book.add(CachedPage(fingerprint(0), 0.7, [CachedBubble(BOX, "Anna runs.")], seq=0))
    book.save()
    w = Listing(other, store)  # the window's cache is another book's: the Book field names "Book"
    made: list[CorrectionsDialog] = []

    def dialog(_master, rows_of):  # (over the hidden root: the stand-in window is no Tk window)
        d = CorrectionsDialog(hidden_root, rows_of)
        d.withdraw()
        made.append(d)
        return d

    monkeypatch.setattr(corrections_mod, "CorrectionsDialog", dialog)
    w.open_corrections()
    d = made[-1]
    try:
        assert w.pipeline.cache.book == "Book" and not d.tree.get_children()  # opened in the worker, then listed
        assert str(d.empty.cget("text")) == corrections_mod.EMPTY
        assert w._replace_in_book(Query("Anna", True, True), "Hana", None)
        assert [d.tree.set(i, "text") for i in d.tree.get_children()] == ["Hana runs."]
        w.undo_edit()
        assert not d.tree.get_children()
        w.open_corrections()  # asked for again: the same list, brought to the front
        assert w._corrections is d and len(made) == 1
    finally:
        d.destroy()
    assert no_keys == []
