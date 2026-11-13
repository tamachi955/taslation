"""What can be taken back or is asked before it goes: the saved translations of one book in one language deleted to
the Recycle Bin after a question with Keep them focused, the series sheet's Remove selected asked and its last change
undone, Book settings' Clear all asked and undone. Translator mode's Skip page, reading order and Translate again are
undone in tests/test_translator_mode.py."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from taslation import recycle
from taslation.annotations import GlossaryStore
from taslation.cache import CacheStore, cache_names
from taslation.config import Settings
from taslation.i18n import CATALOGS
from taslation.ui.dialogs import book_settings, caches, glossary


def _store(tmp_path, *caches_of):
    store = CacheStore(tmp_path / "cache")
    for book, language in caches_of:
        cache = store.open(book, "m", language)
        cache.set_details(title=book)
        cache.save()
    return store


def _files(store):
    return sorted(p.name for p in store.cache_dir.glob("*.json"))


# ------------------------------------------------------------------ the cache of one language
def test_delete_of_one_language_leaves_the_others(tmp_path):
    store = _store(tmp_path, ("Book", "English"), ("Book", "French"), ("Bookish", "French"))
    every = _files(store)
    assert len(every) == 3
    assert store.delete("Book", "French")
    assert sorted(b["language"] for b in store.list() if b["book"] == "Book") == ["English"]
    assert [b["book"] for b in store.list() if b["language"] == "French"] == ["Bookish"]
    assert not store.delete("Book", "French")  # nothing left of it
    assert store.delete("Book", "English") and [b["book"] for b in store.list()] == ["Bookish"]


def test_an_unreadable_file_goes_only_under_its_own_language(tmp_path):
    store = _store(tmp_path, ("Book", "English"))
    french = store.cache_dir / cache_names("Book", "French")[0]
    french.write_text("{ damaged", encoding="utf-8")
    copy = store.cache_dir / (cache_names("Book", "French")[0][:-len(".json")] + ".corrupt.json")
    copy.write_text("{ damaged too", encoding="utf-8")
    assert sorted(p.name for p in store.files_of("Book", "French")) == sorted([french.name, copy.name])
    assert [p.name for p in store.files_of("Book", "English")] == [cache_names("Book", "English")[0]]
    assert store.delete("Book", "French") and not french.exists() and not copy.exists()
    assert [b["language"] for b in store.list()] == ["English"]


def test_delete_to_the_recycle_bin_hands_it_the_files_and_its_refusal_keeps_them(tmp_path):
    store = _store(tmp_path, ("Book", "English"), ("Book", "German"))
    handed = []

    def bin_(paths):
        handed.extend(p.name for p in paths)
        for p in paths:
            p.unlink()

    assert store.delete("Book", "German", recycle=bin_)
    assert handed == [cache_names("Book", "German")[0]]
    before = _files(store)

    def refuses(paths):
        raise recycle.NoRecycleBin("no bin")

    with pytest.raises(OSError):
        store.delete("Book", "English", recycle=refuses)
    assert _files(store) == before  # nothing deleted for good


def test_the_recycle_bin_passes_missing_files_by_and_moves_nothing_without_one(tmp_path, monkeypatch):
    assert recycle.to_recycle_bin([tmp_path / "not there.json"]) == []
    kept = tmp_path / "kept.json"
    kept.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recycle, "available", lambda: False)
    with pytest.raises(recycle.NoRecycleBin):
        recycle.to_recycle_bin([kept])
    assert kept.exists()
    monkeypatch.setattr(recycle, "available", lambda: True)
    monkeypatch.setattr(recycle, "_has_bin", lambda path: False)  # a network share
    with pytest.raises(recycle.NoRecycleBin):
        recycle.to_recycle_bin([kept])
    assert kept.exists()
    assert recycle.FLAGS & recycle.FOF_ALLOWUNDO and recycle.FLAGS & recycle.FOF_WANTNUKEWARNING


# ------------------------------------------------------------------ the Saved translations dialog
def _dialog(hidden_root, store, monkeypatch, answer=True):
    asked = []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append((text, a, k)) or answer)
    d = caches.CachesDialog(hidden_root, store, on_changed=lambda book: None)
    d.withdraw()
    return d, asked


def _select(d, book, language):
    item = next(i for i, b in d._entries.items() if b["book"] == book and b["language"] == language)
    d.tree.selection_set(item)


def test_delete_asks_what_goes_with_keep_focused_and_takes_the_rows_language_alone(hidden_root, tmp_path, monkeypatch):
    store = _store(tmp_path, ("Book", "English"), ("Book", "French"))
    d, asked = _dialog(hidden_root, store, monkeypatch)
    binned = []
    d.recycle = lambda paths: [binned.append(p.name) or p.unlink() for p in paths]
    _select(d, "Book", "French")
    d._delete()
    (text, buttons, options), = asked
    assert text == caches.DELETE_QUESTION.format(book="Book", language="French")
    assert buttons == ("Delete", "Keep them") and options == {"no_first": True}
    assert len(binned) == 1 and [b["language"] for b in store.list()] == ["English"]
    assert d.backup_var.get() == caches.IN_THE_BIN.format(book="Book", language="French")
    d.destroy()


def test_keep_them_deletes_nothing(hidden_root, tmp_path, monkeypatch):
    store = _store(tmp_path, ("Book", "English"))
    d, asked = _dialog(hidden_root, store, monkeypatch, answer=False)
    d.recycle = lambda paths: pytest.fail("nothing is to go")
    _select(d, "Book", "English")
    d._delete()
    assert asked and len(store.list()) == 1
    d.destroy()


def test_a_file_the_recycle_bin_does_not_take_stays_and_the_dialog_says_so(hidden_root, tmp_path, monkeypatch):
    store = _store(tmp_path, ("Book", "English"))
    d, _asked = _dialog(hidden_root, store, monkeypatch)
    told = []
    monkeypatch.setattr(caches, "tell", lambda _parent, text, **_k: told.append(text))
    d.recycle = lambda paths: (_ for _ in ()).throw(recycle.NoRecycleBin("no bin"))
    _select(d, "Book", "English")
    d._delete()
    assert told == [caches.NOT_DELETED.format(book="Book", language="English")] and len(store.list()) == 1
    d.destroy()


# ------------------------------------------------------------------ the series sheet
def _sheet(hidden_root, tmp_path, monkeypatch, answer=True):
    store = GlossaryStore(tmp_path / "glossary")
    sheet = store.open("Series", "English")
    sheet.set("ピヨ", "Piyo")
    sheet.set("魔法", "magic")
    sheet.save()
    asked = []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append((text, a, k)) or answer)
    changes = []
    d = glossary.GlossaryDialog(hidden_root, store, "Series", "English", on_change=lambda: changes.append(1))
    d.withdraw()
    return store, d, asked, changes


def test_remove_selected_asks_naming_what_goes(hidden_root, tmp_path, monkeypatch):
    store, d, asked, changes = _sheet(hidden_root, tmp_path, monkeypatch, answer=False)
    d.tree.selection_set(d.tree.get_children())
    d._remove()
    (text, buttons, options), = asked
    assert text == glossary.REMOVE_QUESTIONS["terms"].format(n=2, names="ピヨ, 魔法")
    assert buttons == ("Remove selected", "Keep them") and options == {"no_first": True}
    assert not changes and len(store.open("Series", "English").entries) == 2
    asked.clear()
    d.tree.selection_set(())
    d._remove()  # nothing selected: nothing asked, nothing written
    assert not asked and not changes
    d.destroy()


def test_undo_puts_back_the_sheet_before_the_last_change(hidden_root, tmp_path, monkeypatch):
    store, d, _asked, changes = _sheet(hidden_root, tmp_path, monkeypatch)
    assert str(d.undo_btn.cget("state")) == "disabled"
    d.tree.selection_set(d.tree.get_children()[0])
    d._remove()
    assert [e.term for e in store.open("Series", "English").entries] == ["魔法"]
    assert str(d.undo_btn.cget("state")) == "normal"
    d.undo()
    assert [(e.term, e.rendering) for e in store.open("Series", "English").entries] == [("ピヨ", "Piyo"), ("魔法", "magic")]
    assert str(d.undo_btn.cget("state")) == "disabled" and changes == [1, 1]
    d.tone_var.set("dry")
    d._set_style()
    d.undo()  # the style guide's fields follow
    assert d.tone_var.get() == "" and store.open("Series", "English").style.tone == ""
    d._set_style()  # unchanged: no step for Undo
    assert str(d.undo_btn.cget("state")) == "disabled"
    d.destroy()


def test_the_names_a_question_lists_are_bounded():
    assert glossary.shown_names(["a", "b"]) == "a, b"
    assert glossary.shown_names([str(i) for i in range(8)]) == "0, 1, 2, 3, 4, ..."


# ------------------------------------------------------------------ Book settings
class Annotations:
    def __init__(self, settings):
        self.settings = dict(settings)


def _book(hidden_root, monkeypatch, current, answer=True):
    asked, changes = [], []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append((text, a, k)) or answer)
    ann = Annotations(current)

    def set_book_settings(values):
        ann.settings = dict(values or {})
        return ann.settings

    pipeline = SimpleNamespace(annotations=ann, _base_settings=Settings(), set_book_settings=set_book_settings)
    d = book_settings.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: changes.append(1))
    d.withdraw()
    return d, ann, asked, changes


def test_clear_all_asks_and_undo_puts_the_choices_back(hidden_root, monkeypatch):
    d, ann, asked, changes = _book(hidden_root, monkeypatch, {"translate_sfx": False, "white_threshold": 200})
    d._clear()
    (text, buttons, options), = asked
    assert text == book_settings.CLEAR_QUESTION.format(n=2)
    assert buttons == ("Clear all", "Keep them") and options == {"no_first": True}
    assert ann.settings == {} and changes == [1] and d.winfo_exists()  # the dialog stays, with Undo
    assert d.choices["translate_sfx"].get() is Settings().translate_sfx
    assert d.said_var.get() == book_settings.CLEARED and str(d.undo_btn.cget("state")) == "normal"
    d._undo()
    assert ann.settings == {"translate_sfx": False, "white_threshold": 200} and changes == [1, 1]
    assert d.choices["translate_sfx"].get() is False and str(d.undo_btn.cget("state")) == "disabled"
    d.destroy()


def test_clear_all_kept_or_with_nothing_to_clear_changes_nothing(hidden_root, monkeypatch):
    d, ann, asked, changes = _book(hidden_root, monkeypatch, {"translate_sfx": False}, answer=False)
    d._clear()
    assert asked and ann.settings == {"translate_sfx": False} and not changes
    d.destroy()
    d, ann, asked, changes = _book(hidden_root, monkeypatch, {})
    d._clear()
    assert not asked and not changes and d.said_var.get() == book_settings.NOTHING_TO_CLEAR
    d.destroy()


def test_the_new_lines_are_in_every_language():
    keys = [caches.DELETE_QUESTION, caches.NOT_DELETED, caches.IN_THE_BIN, *glossary.REMOVE_QUESTIONS.values(),
            glossary.UNDO_TIP, book_settings.CLEAR_QUESTION, book_settings.NOTHING_TO_CLEAR, book_settings.CLEARED,
            book_settings.UNDONE, book_settings.UNDO_TIP]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(k in catalog for k in keys), (code, [k for k in keys if k not in catalog])
