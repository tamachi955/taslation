"""A change across the series from the window: the other volumes found as `taslation glossary apply` finds them,
counted volume by volume before anything is written, changed and saved at once with a copy of each file kept beside
it, Ctrl+Z on the book in the window only; Find and replace's "Look in:" (This book whenever it opens) and the series
sheet's offer with its box for the other volumes. Invented books and synthetic lines only."""
from __future__ import annotations

import pytest
from helpers import FakeOcr
from test_find_replace import Window as FindWindow
from test_find_replace import bubble, page, texts_of
from test_sheet_changes import TEXTS, Renames

from taslation.annotations import BookAnnotations
from taslation.cache import CacheStore
from taslation.i18n import CATALOGS, set_language
from taslation.locales.features import series_scope as texts
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import replace, series_scope, translator
from taslation.ui.dialogs import caches
from taslation.ui.dialogs import find_replace as dialog
from taslation.ui.replace import Query
from taslation.ui.series_scope import VolumeCount, change_volumes, count_in_volumes, series_volumes, volume_lines

FIRST, SECOND, TENTH = "Pebble Harbor 1", "Pebble Harbor 2", "Pebble Harbor 10"


def _book(store, name, *pages, language="English"):
    cache = store.open(name, "m", language)
    cache.pages = list(pages)
    cache.dirty = True
    cache.save()
    return cache


@pytest.fixture
def store(tmp_path):
    store = CacheStore(tmp_path / "cache")
    _book(store, SECOND, page(0, bubble("Anna sails."), bubble("Anna? Anna!", 0.3)), page(1, bubble("No one.")))
    _book(store, TENTH, page(0, bubble("Bel waits.")))
    _book(store, "Pebble Harbor 3", page(0, bubble("Anna nage.")), language="French")  # another language
    _book(store, "Quillpond 2", page(0, bubble("Anna is elsewhere.")))  # another series
    return store


@pytest.fixture
def cache(store):
    return _book(store, FIRST, page(0, bubble("Anna runs.")), page(1, bubble("Where is Anna?")))


class SeriesWindow(FindWindow):
    _replace_in_series = app_mod.App._replace_in_series


@pytest.fixture
def window(cache, store):
    w = SeriesWindow(cache, store)
    w.book_var.set(FIRST)
    return w


def _answer(monkeypatch, yes):
    asked = []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append((text, a)) or yes)
    return asked


def _copies(store):
    return sorted(p.name for p in store.cache_dir.glob("*.before-replace.*.json"))


def _texts(store, name, language="English"):
    return texts_of(store.open(name, "m", language))


# ------------------------------------------------------------------ the volumes
def test_the_other_volumes_are_those_of_the_series_in_the_language_in_volume_order(store, cache):
    assert series_volumes(store, FIRST, "English") == [SECOND, TENTH]  # 10 after 2; not the book itself
    assert series_volumes(store, FIRST, " english") == [SECOND, TENTH]  # the language by its key
    assert series_volumes(store, FIRST, "French") == ["Pebble Harbor 3"]
    assert series_volumes(store, "Quillpond 1", "English") == ["Quillpond 2"]
    assert series_volumes(store, "Elsewhere 1", "English") == []


def test_the_count_per_volume_writes_nothing(store, cache):
    edits_of = lambda volume: replace.replacements(replace.find_hits(volume, Query("Anna")), "Hana")[0]  # noqa: E731
    before = {name: _texts(store, name) for name in (SECOND, TENTH)}
    assert count_in_volumes(store, [SECOND, TENTH], "English", edits_of) == [VolumeCount(SECOND, 2),
                                                                              VolumeCount(TENTH, 0)]
    assert {name: _texts(store, name) for name in (SECOND, TENTH)} == before and not _copies(store)
    lines = volume_lines([VolumeCount(SECOND, 2), VolumeCount(TENTH, 0, "damaged")])
    assert lines == f"  {SECOND}: 2 line(s)\n  {TENTH}: could not be opened (damaged)"
    many = volume_lines([VolumeCount(f"Pebble Harbor {i}", 1) for i in range(2, 20)], most=3)
    assert many.splitlines()[-1] == "  15 more volume(s): 15 line(s)" and len(many.splitlines()) == 4


def test_a_volume_whose_copy_cannot_be_written_is_left_as_it_was(store, cache, monkeypatch):
    def refuse(_path):
        raise OSError("disk full")

    monkeypatch.setattr(series_scope, "keep_copy", refuse)
    edits_of = lambda volume: replace.replacements(replace.find_hits(volume, Query("Anna")), "Hana")[0]  # noqa: E731
    done = change_volumes(store, [SECOND], "English", edits_of)
    assert done == [VolumeCount(SECOND, 0, "disk full")] and _texts(store, SECOND)[0] == "Anna sails."
    assert series_scope.changed_lines(done) == [(series_scope.VOLUME_LEFT, {"book": SECOND, "error": "disk full"})]


# ------------------------------------------------------------------ Replace all in every volume
def test_replace_all_volumes_asks_with_each_count_and_changes_them_on_disk(window, cache, store, monkeypatch):
    asked = _answer(monkeypatch, True)
    assert window._replace_in_series(Query("Anna"), "Hana")
    (text, buttons), = asked
    counts = [VolumeCount(SECOND, 2), VolumeCount(TENTH, 0)]
    assert text == replace.SERIES_QUESTION.format(find="Anna", replace="Hana", n=2, volumes=volume_lines(counts))
    assert buttons == (replace.REPLACE_EVERYWHERE, "Cancel")
    assert _texts(store, FIRST) == ["Hana runs.", "Where is Hana?"]
    assert _texts(store, SECOND) == ["Hana sails.", "Hana? Hana!", "No one."]  # saved at once
    assert all(b.edited for b in store.open(SECOND, "m").pages[0].bubbles)  # the person's change, as in this book
    assert _texts(store, TENTH) == ["Bel waits."] and _texts(store, "Quillpond 2") == ["Anna is elsewhere."]
    assert _texts(store, "Pebble Harbor 3", "French") == ["Anna nage."]
    copy, = _copies(store)  # one for the volume that changed, none for the one with nothing to change
    assert copy.startswith(store.path_for(SECOND).stem + ".before-replace.")
    assert sorted(entry["book"] for entry in store.list()) == sorted(
        [FIRST, SECOND, TENTH, "Pebble Harbor 3", "Quillpond 2"])  # the copy is no book of its own
    assert window.lines[-1].endswith(series_scope.VOLUMES_SAVED.format(n=2, volumes=1))
    assert "Replaced in 2 text area(s) on 2 page(s)." in window.lines[-1]


def test_ctrl_z_takes_back_this_book_only(window, cache, store, monkeypatch):
    _answer(monkeypatch, True)
    window._replace_in_series(Query("Anna"), "Hana")
    window.undo_edit()
    assert _texts(store, FIRST) == ["Anna runs.", "Where is Anna?"] == texts_of(cache)
    assert _texts(store, SECOND)[0] == "Hana sails."  # beyond Ctrl+Z, as the question said
    window.redo_edit()
    assert texts_of(cache)[0] == "Hana runs."


def test_cancel_changes_nothing_anywhere(window, cache, store, monkeypatch):
    asked = _answer(monkeypatch, False)
    window._replace_in_series(Query("Anna"), "Hana")
    assert asked and not window.history.done and not _copies(store)
    assert _texts(store, FIRST)[0] == "Anna runs." and _texts(store, SECOND)[0] == "Anna sails."


def test_a_match_in_another_volume_only_is_asked_and_said(window, cache, store, monkeypatch):
    asked = _answer(monkeypatch, True)
    window._replace_in_series(Query("sails"), "rows")
    (text, _buttons), = asked
    assert f"{SECOND}: 1 line(s)" in text
    assert _texts(store, SECOND)[0] == "Anna rows." and _texts(store, FIRST)[0] == "Anna runs."
    assert window.lines[-1] == series_scope.VOLUMES_SAVED.format(n=1, volumes=1)  # not "Nothing was changed."


def test_no_match_anywhere_and_no_other_volume_are_said(window, cache, store, monkeypatch, tmp_path):
    asked = _answer(monkeypatch, True)
    window._replace_in_series(Query("zzz"), "y")
    assert not asked and window.lines[-1] == replace.NO_MATCH_ANYWHERE and not window.history.done
    alone = CacheStore(tmp_path / "alone")
    single = _book(alone, "Lantern Road 1", page(0, bubble("Anna runs.")))
    w = SeriesWindow(single, alone)
    w.book_var.set("Lantern Road 1")
    w._replace_in_series(Query("Anna"), "Hana")
    assert not asked and _texts(alone, "Lantern Road 1") == ["Hana runs."]  # this book's Replace all
    assert w.lines[-1].endswith(replace.NO_OTHER_VOLUMES.format(language="English"))


def test_it_waits_while_a_page_is_at_work(window, monkeypatch):
    asked = _answer(monkeypatch, True)
    window.busy = True
    assert not window._replace_in_series(Query("Anna"), "Hana")
    assert not asked and window.said[-1] == "TASlation is at work on a page. Try again when it is done."


# ------------------------------------------------------------------ the window's "Look in:"
def _dialog(root, window, **kwargs):
    calls = []
    d = dialog.FindReplaceDialog(root, window._find_hits, lambda q, t, picked: calls.append(("book", t, picked)),
                                 window.undo_edit, window.redo_edit,
                                 on_replace_series=lambda q, t: calls.append(("series", t, q.text)), **kwargs)
    d.withdraw()
    return d, calls


def test_look_in_is_this_book_whenever_the_window_opens(hidden_root, window):
    d, calls = _dialog(hidden_root, window)
    assert d.scope_var.get() == dialog.BOOK and not d.series and d.scope_row is not None
    d.find_var.set("Anna")
    d.replace_var.set("Hana")
    d.update_list()
    d.replace_all()
    assert calls == [("book", "Hana", None)]
    d.scope_var.set(dialog.SERIES)
    d.update_list()
    assert d.series and dialog.SERIES_NOTE in d.count_var.get()
    d.replace_all()
    assert calls[-1] == ("series", "Hana", "Anna")
    d.find_var.set("sails")  # only in another volume: Replace all can still ask
    d.update_list()
    assert d.count_var.get() == "No match. " + dialog.SERIES_NOTE and str(d.all_btn.cget("state")) == "normal"
    kept = d.kept()
    assert kept["scope"] == dialog.SERIES
    d.destroy()
    again, _calls = _dialog(hidden_root, window, kept=kept)  # a language switch keeps it
    assert again.scope_var.get() == dialog.SERIES
    again.destroy()
    fresh, _calls = _dialog(hidden_root, window)  # opened anew: this book
    assert fresh.scope_var.get() == dialog.BOOK
    fresh.destroy()


def test_without_a_series_callback_there_is_no_choice(hidden_root, window):
    d = dialog.FindReplaceDialog(hidden_root, window._find_hits, window._replace_in_book, window.undo_edit,
                                 window.redo_edit, {"scope": dialog.SERIES})
    d.withdraw()
    assert d.scope_row is None and d.scope_var.get() == dialog.BOOK and not d.series
    d.destroy()


def test_the_choices_say_what_they_do(hidden_root, window):
    d, _calls = _dialog(hidden_root, window)
    choices = [w for w in d.scope_row.winfo_children()]
    assert len(choices) == 3 and all(getattr(w, "_tooltip", None) is not None for w in choices)
    d.destroy()
    set_language("ja")  # (the hidden root's fixture puts English back)
    d, _calls = _dialog(hidden_root, window)
    assert [w.cget("text") for w in d.scope_row.winfo_children()] == ["対象:", "この本", "シリーズの全巻"]
    d.destroy()


def test_the_app_window_passes_the_series_replacement():
    import inspect

    assert "on_replace_series=self._replace_in_series" in inspect.getsource(app_mod.App.open_find_replace)


# ------------------------------------------------------------------ the series sheet's offer
@pytest.fixture
def sheet_window(sample_page, settings):
    store = CacheStore(settings.cache_dir)
    cache = store.open(FIRST, "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", FIRST)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(TEXTS, default="ok"), cache=cache,
                        annotations=ann)
    result = pipeline.process(sample_page, complete=True)
    _book(store, SECOND, page(7, bubble("Piyo is here."), bubble("Nowa and Piyoko.", 0.3)))
    return Renames(pipeline, result), store  # (no store of its own: the one of the cache's folder)


def test_the_offer_names_the_other_volumes_and_its_box_takes_them(sheet_window, monkeypatch):
    w, store = sheet_window
    start = w.lines()
    asked = []
    monkeypatch.setattr(caches, "ask_choice",
                        lambda _parent, text, choice, yes, no, **k: asked.append((text, choice, yes, no)) or (True, True))
    w._offer_sheet_renames([("Piyo", "Pyo")], FIRST, "English")
    (text, choice, yes, no), = asked
    assert text == (translator.SHEET_OFFER.format(n=2, changes="Piyo → Pyo") + "\n\n"
                    + translator.SHEET_OTHERS_TOO.format(volumes=volume_lines([VolumeCount(SECOND, 1)])))
    assert (choice, yes, no) == (series_scope.ALL_VOLUMES, translator.SHEET_GIVE, translator.SHEET_LEAVE)
    assert sum("Pyo" in t for t in w.lines()) == 2
    assert _texts(store, SECOND) == ["Pyo is here.", "Nowa and Piyoko."]  # saved at once, whole words
    assert not any(b.edited for b in store.open(SECOND, "m").pages[0].bubbles)  # the sheet's change, not a correction
    assert len(_copies(store)) == 1
    assert w.said[-2:] == [translator.SHEET_APPLIED, series_scope.VOLUMES_SAVED]
    w.undo_edit()
    assert w.lines() == start and _texts(store, SECOND)[0] == "Pyo is here."  # this book only


def test_unticked_the_offer_changes_this_book_only(sheet_window, monkeypatch):
    w, store = sheet_window
    monkeypatch.setattr(caches, "ask_choice", lambda *a, **k: (True, False))
    w._offer_sheet_renames([("Piyo", "Pyo")], FIRST, "English")
    assert sum("Pyo" in t for t in w.lines()) == 2
    assert _texts(store, SECOND)[0] == "Piyo is here." and not _copies(store)


def test_a_rendering_only_other_volumes_have_is_offered_for_them(sheet_window, monkeypatch):
    w, store = sheet_window
    asked = []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append((text, a)) or True)
    w._offer_sheet_renames([("Nowa", "Nowe")], FIRST, "English")
    (text, buttons), = asked
    assert text == translator.SHEET_OTHERS_ONLY.format(changes="Nowa → Nowe",
                                                       volumes=volume_lines([VolumeCount(SECOND, 1)]))
    assert buttons == (translator.SHEET_APPLY.format(n=1), translator.SHEET_LEAVE)
    assert _texts(store, SECOND)[1] == "Nowe and Piyoko." and w.said[-1] == series_scope.VOLUMES_SAVED
    assert "Nothing was changed." not in w.said


# ------------------------------------------------------------------ the strings
def test_every_string_is_in_every_language():
    keys = [series_scope.THIS_BOOK, series_scope.ALL_VOLUMES, series_scope.VOLUME_LINE,
            series_scope.VOLUME_UNREADABLE, series_scope.MORE_VOLUMES, series_scope.VOLUMES_SAVED,
            series_scope.VOLUME_LEFT, dialog.LOOK_IN, dialog.SCOPE_TIP, dialog.SERIES_NOTE, replace.COUNTING,
            replace.SERIES_QUESTION, replace.REPLACE_EVERYWHERE, replace.NO_MATCH_ANYWHERE, replace.NO_OTHER_VOLUMES,
            translator.SHEET_OTHERS_TOO, translator.SHEET_GIVE, translator.SHEET_OTHERS_ONLY]
    assert sorted(keys) == sorted(texts.TEXTS)
    for key in keys:
        for code, catalog in CATALOGS.items():
            if code != "en":
                assert catalog[key].strip(), (code, key)
