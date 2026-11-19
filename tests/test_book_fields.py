"""The book's name as two fields, Series and Volume (`ui.book_fields.BookFields`), wherever the window shows or asks
for it: bound both ways to one name (a name set from elsewhere split into the fields, the fields making the name in
one spelling), a volume refused with a line that says why, leaving one field for the other not leaving the fields;
the toolbar's Book group, the start dialog, the colophon's offer, the offer to rename a book kept under an older
spelling, the rename review's line and the cache list's columns. On withdrawn windows of the shared hidden root
only: no real window is touched. Invented titles only."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pytest

from taslation.cache import CacheStore
from taslation.i18n import set_language
from taslation.rename import RenamePlan
from taslation.ui import book_fields
from taslation.ui.book_fields import BookFields, kept_name, parts_line, refused_line
from taslation.ui.dialogs import caches
from taslation.ui.dialogs.caches import CachesDialog
from taslation.ui.dialogs.rename_review import RenameReviewDialog
from taslation.ui.dialogs.start import ColophonOffer, StandardNameOffer, StartDialog


def _fields(root, **kwargs):
    name = tk.StringVar(root)
    frame = ttk.Frame(root)
    fields = BookFields(frame, name, series_chars=20, **kwargs)
    fields.pack()
    return name, fields


def test_a_name_set_from_elsewhere_is_split_and_the_fields_make_the_name(hidden_root):
    name, fields = _fields(hidden_root)
    name.set("見本の物語 第3巻")  # a viewer's title, a cache kept before
    assert (fields.series_var.get(), fields.volume_var.get()) == ("見本の物語", "3")
    assert name.get() == "見本の物語 第3巻"  # the name as it was set: the fields only show it
    fields.series_var.set("見本の物語 完全版")  # typed: the name follows at once, in one spelling
    assert name.get() == "見本の物語 完全版 3"
    fields.volume_var.set("第")  # no volume yet: the name stays the last one the fields made
    assert name.get() == "見本の物語 完全版 3"
    fields.volume_var.set("第四巻")
    assert name.get() == "見本の物語 完全版 4" and fields.volume_var.get() == "第四巻"  # as typed until left
    fields.volume_var.set("")  # a book of one volume
    assert name.get() == "見本の物語 完全版"
    name.set("Some Title (10.5)")
    assert (fields.series_var.get(), fields.volume_var.get()) == ("Some Title", "10.5")
    name.set("")
    assert (fields.series_var.get(), fields.volume_var.get()) == ("", "")


def test_leaving_the_fields_keeps_the_volume_in_its_spelling_or_refuses_it(hidden_root):
    committed, refused = [], []
    name, fields = _fields(hidden_root, resolve=lambda n: {"Some Title 3": "Some Title 3巻"}.get(n, n),
                           on_commit=committed.append, on_refused=refused.append)
    fields.series_var.set("  Some   Title ")
    fields.volume_var.set("③")
    assert fields.commit()
    assert (fields.series_var.get(), fields.volume_var.get()) == ("Some Title", "3")
    assert name.get() == "Some Title 3巻" and committed == ["Some Title 3巻"]  # what *resolve* found kept
    fields.volume_var.set("完全版")  # an edition: refused, and the volume before comes back
    assert not fields.commit()
    assert refused == ["完全版"] and fields.volume_var.get() == "3" and name.get() == "Some Title 3巻"
    assert committed == ["Some Title 3巻"]
    assert refused_line("完全版") == ("完全版 is not a volume: the Volume field takes a number (3, 10.5) or 上, 中, 下, "
                                      "前編, 後編. An edition such as 完全版 belongs to the series.")
    assert fields.volume.bind("<Return>") and fields.series.bind("<KP_Enter>")  # Enter leaves the fields too


def test_leaving_one_field_for_the_other_is_not_leaving_the_fields(hidden_root, monkeypatch):
    committed = []
    name, fields = _fields(hidden_root, on_commit=committed.append)
    fields.series_var.set("Some Title")
    monkeypatch.setattr(fields, "focus_get", lambda: fields.volume)
    fields._left()
    assert committed == []
    monkeypatch.setattr(fields, "focus_get", lambda: None)  # the keys went elsewhere
    fields._left()
    assert committed == ["Some Title"]


def test_the_readers_split_is_remembered_as_the_fields_are_left(hidden_root):
    from taslation.bookname import split_name
    from taslation.notes import series_key

    name, fields = _fields(hidden_root)
    fields.series_var.set("Gate 51")  # a series whose name ends in a number, and no volume
    assert fields.commit() and name.get() == "Gate 51"
    assert split_name("Gate 51") == ("Gate 51", "") and series_key("Gate 51") == "Gate 51"
    name.set("Gate 51")
    assert (fields.series_var.get(), fields.volume_var.get()) == ("Gate 51", "")


def test_a_list_of_whole_names_splits_the_one_picked(hidden_root):
    name, fields = _fields(hidden_root, matches=["Star Road 1", "Star Road 2"])
    assert fields.series.winfo_class() == "TCombobox"
    fields.series_var.set("Star Road 2")
    fields.series.event_generate("<<ComboboxSelected>>")
    assert (fields.series_var.get(), fields.volume_var.get(), name.get()) == ("Star Road", "2", "Star Road 2")


def test_the_window_keeps_a_name_in_the_one_spelling_or_the_older_one_its_files_are_under(tmp_path):
    from types import SimpleNamespace

    store = CacheStore(tmp_path / "cache")
    window = SimpleNamespace(store=store)
    assert kept_name(window, " Other Tale  第2巻 ") == "Other Tale 2"
    cache = store.open("Some Title 3巻", "m", "English")
    cache.save()
    assert kept_name(window, "Some Title 第3巻") == "Some Title 3巻" == kept_name(window, "Some Title 3")
    assert kept_name(SimpleNamespace(), "Some Title 第3巻") == "Some Title 3"  # no store: the one spelling
    assert kept_name(window, "Google Chrome") == "Google Chrome"  # a name that names no book, as it is


# ------------------------------------------------------------------ the toolbar
def _toolbar_fields(bar) -> BookFields:
    stack = [bar]
    while stack:
        w = stack.pop()
        if isinstance(w, BookFields):
            return w
        stack.extend(w.winfo_children())
    raise AssertionError("no Series and Volume fields in the toolbar")


def test_the_toolbar_shows_the_books_name_as_series_and_volume(hidden_root):
    from test_window_layout import Bars

    w = Bars(hidden_root)
    try:
        fields = _toolbar_fields(w.build("en"))
        assert (fields.series_label.cget("text"), fields.volume_label.cget("text")) == ("Series:", "Vol.:")
        w.book_var.set("見本の物語 下巻")
        assert (fields.series_var.get(), fields.volume_var.get()) == ("見本の物語", "下")
        fields.volume_var.set("2")
        assert w.book_var.get() == "見本の物語 2"
        w.book_var.set("見本の物語 1")
        fields = _toolbar_fields(w.build("ja"))  # a language switch builds the toolbar anew: the name stays split
        assert (fields.series_label.cget("text"), fields.volume_label.cget("text")) == ("シリーズ:", "巻:")
        assert (fields.series_var.get(), fields.volume_var.get()) == ("見本の物語", "1")
    finally:
        set_language("en")
        w.destroy()


# ------------------------------------------------------------------ the dialogs
def test_the_start_dialog_asks_for_the_series_and_the_volume(hidden_root):
    answers = []
    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=False, on_answer=lambda *a: answers.append(a))
    d.withdraw()
    assert d.entry is d.fields.series and d.fields.volume.winfo_class() == "TEntry"
    assert (d.fields.series_label.cget("text"), d.fields.volume_label.cget("text")) == ("Series:", "Volume:")
    d.fields.series_var.set("見本の物語")
    d.fields.volume_var.set("special")  # no volume: no answer, a line says why
    d._answer(d.default)
    assert not answers and d.winfo_exists() and d.refused_label.winfo_manager() == "pack"
    assert "".join(str(d.refused_label.cget("text")).split()) == "".join(refused_line("special").split())
    d.fields.volume_var.set("第三巻")
    d._answer(d.default)
    assert answers == [("ok", "見本の物語 3")] and not d.winfo_exists()

    d = StartDialog(hidden_root, "Star Road 第2巻", generic=False, ask=True, on_answer=lambda *a: answers.append(a))
    d.withdraw()  # a name the title gives: in its two fields, answered in the one spelling
    assert (d.fields.series_var.get(), d.fields.volume_var.get()) == ("Star Road", "2")
    d._answer("start")
    assert answers[-1] == ("start", "Star Road 2")

    d = StartDialog(hidden_root, "Yomizuq", generic=True, ask=False, on_answer=lambda *a: answers.append(a),
                    matches=["Star Road 1", "Star Road 2"], hint="several")
    d.withdraw()
    d.fields.series_var.set("Star Road 2")
    d.entry.event_generate("<<ComboboxSelected>>")
    assert (d.fields.series_var.get(), d.fields.volume_var.get()) == ("Star Road", "2")
    d.from_colophon.set(True)  # the colophon is to give the name: both fields rest
    d._sync()  # (what the tick does)
    assert str(d.fields.series.cget("state")) == str(d.fields.volume.cget("state")) == "disabled"
    d.destroy()


def test_the_colophons_offer_shows_its_name_in_the_two_fields_for_the_reader_to_correct(hidden_root):
    answers = []
    d = ColophonOffer(hidden_root, "見本の物語", "3", lambda *a: answers.append(a))
    d.withdraw()
    assert (d.fields.series_var.get(), d.fields.volume_var.get(), d.name()) == ("見本の物語", "3", "見本の物語 3")
    d.fields.volume_var.set("限定版")
    d._answer(True)  # Use waits for a volume
    assert not answers and d.refused_label.winfo_manager() == "pack"
    d.fields.volume_var.set("第4巻")
    d.buttons[0].invoke()  # Use
    assert answers == [(True, "見本の物語 4")]
    d = ColophonOffer(hidden_root, "見本の物語", "特装版", lambda *a: answers.append(a))
    d.withdraw()  # a "volume" that is an edition: in the series
    assert (d.fields.series_var.get(), d.fields.volume_var.get()) == ("見本の物語 特装版", "")
    d.buttons[1].invoke()  # Keep
    assert answers[-1] == (False, None)


def test_a_book_under_an_older_spelling_is_offered_the_one_spelling(hidden_root):
    answers = []
    d = StandardNameOffer(hidden_root, "Some Title 3巻", "Some Title 3", answers.append)
    d.withdraw()
    text = "".join(str(d.label.cget("text")).split())
    assert text == "".join(("This book's files are kept under Some Title 3巻, a spelling from before the Series and "
                            "Volume fields. Rename the book to Some Title 3? Its translations, notes and sheet move "
                            "along; until then everything is found under the old name.").split())
    assert [b.cget("text") for b in d.buttons] == ["Rename", "Not now"]
    d.buttons[1].invoke()
    d._answer(True)  # answered once
    assert answers == [False] and not d.winfo_exists()
    set_language("ja")
    try:
        d = StandardNameOffer(hidden_root, "見本の物語 第一巻", "見本の物語 1", answers.append)
        d.withdraw()
        assert [b.cget("text") for b in d.buttons] == ["書名を変更", "今はしない"]
        assert "".join(str(d.label.cget("text")).split()).startswith("この本のファイルは『見本の物語第一巻』という")
        d.buttons[0].invoke()
        assert answers == [False, True]
    finally:
        set_language("en")


def test_the_rename_review_says_the_new_names_series_and_volume(hidden_root):
    for new, line in (("見本の物語 3", "The new name: Series 見本の物語, volume 3"),
                      ("見本の物語 外伝", "The new name: Series 見本の物語 外伝, no volume")):
        d = RenameReviewDialog(hidden_root, RenamePlan("Some Title 3巻", new, "Some Title", "見本の物語"),
                               on_apply=lambda answers: None)
        d.withdraw()
        assert str(d.name_line.cget("text")) == line
        d.destroy()
    assert parts_line("Some Title 下巻") == "Series Some Title, volume 下"


def test_the_cache_list_shows_each_book_as_series_and_volume_and_deletes_by_its_kept_name(hidden_root, tmp_path,
                                                                                            monkeypatch):
    store = CacheStore(tmp_path / "cache")
    for book in ("見本の物語 第3巻", "Some Title"):
        store.open(book, "m", "English").save()
    d = CachesDialog(hidden_root, store)
    d.withdraw()
    rows = sorted((d.tree.item(item, "text"), d.tree.set(item, "volume")) for item in d.tree.get_children())
    assert rows == [("Some Title", ""), ("見本の物語", "3")]
    assert (d.tree.heading("#0", "text"), d.tree.heading("volume", "text")) == ("Series", "Volume")
    asked = []
    monkeypatch.setattr(caches, "ask", lambda parent, text, *a, **k: asked.append(text) or False)
    item = next(i for i in d.tree.get_children() if d.tree.item(i, "text") == "見本の物語")
    d.tree.selection_set(item)
    d._delete()  # the question names the book by the name its files are kept under
    assert len(asked) == 1 and "見本の物語 第3巻" in asked[0]
    assert {e["book"] for e in store.list()} == {"見本の物語 第3巻", "Some Title"}  # Keep them: nothing deleted
    d.destroy()


@pytest.mark.parametrize("code", ["ja", "de", "ko"])
def test_the_fields_speak_the_windows_language(hidden_root, code):
    set_language(code)
    try:
        name, fields = _fields(hidden_root)
        labels = (fields.series_label.cget("text"), fields.volume_label.cget("text"))
        assert labels == {"ja": ("シリーズ:", "巻:"), "de": ("Serie:", "Band:"), "ko": ("시리즈:", "권:")}[code]
        assert "完全版" in refused_line("完全版")
    finally:
        set_language("en")


def test_the_offer_waits_while_the_window_is_at_work_and_names_no_book_offers_nothing():
    from types import SimpleNamespace

    asked = []
    window = SimpleNamespace(reading=False, _start_dialog=None, _batching=False, batch=None, busy=True,
                             book_var=SimpleNamespace(get=lambda: "Some Title 3巻"), _kept_under=asked.append)
    book_fields.offer_standard_name(window)  # a page being translated: later
    window.busy = False
    window.book_var = SimpleNamespace(get=lambda: "Yomizuq Cloud Reader")
    book_fields.offer_standard_name(window)
    window.book_var = SimpleNamespace(get=lambda: "Some Title 3")  # the one spelling already
    book_fields.offer_standard_name(window)
    assert asked == []


def test_the_lines_that_ask_for_the_books_name_point_at_the_series_field_in_every_language():
    """A change kept nowhere for want of a name says where the name goes: the Series field the toolbar shows (the
    volume beside it), in every language with that field's own label; no line names the Book field the toolbar no
    longer has."""
    from taslation.i18n import CATALOGS
    from taslation.ui import book_areas, formats, selection
    from taslation.ui.dialogs import corrections, page_list

    lines = {book_areas.NO_BOOK, formats.NO_BOOK, selection.NAME_FIRST, corrections.NO_BOOK,
             page_list.PageListDialog.NO_BOOK, "Could not keep the translation: give the book a name first (its series "
             "in the Series field, and its volume beside it if it has one).", "Choose the book first (its series in the "
             "Series field, and its volume beside it if it has one)."}
    assert len(lines) == 5 and all("Series field" in line and "volume beside it" in line for line in lines)
    for code, catalog in CATALOGS.items():
        assert not [key for key in catalog if "Book field" in key or "Book box" in key], code
        if code == "en":
            continue
        series = catalog["Series:"].rstrip(":： ")
        for line in lines:
            assert series in catalog[line], (code, line)
