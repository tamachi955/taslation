"""Books kept under spellings of their names from before the Series and Volume fields ("Some Title 3巻", "見本の物語
第一巻", "見本の物語（２）"): found under the one spelling the two fields make (`cache.CacheStore.kept_name`,
`bookid.identity_of`, a window title's name: `viewerparts.book_for_title`), read and written under their old names
until renamed; the series sheet an older parser kept for one book alone found too (`notes.sheet_key`), and moved with
the book when it is renamed to the one spelling (`rename.rename_book`), while another series' sheet stays where it
is. Nothing is renamed by itself. Temp folders only; invented titles."""
from __future__ import annotations

import pytest

from taslation import viewerparts
from taslation.annotations import AnnotationStore, GlossaryStore
from taslation.bookid import identity_of
from taslation.bookname import split_name
from taslation.cache import CacheStore, CachedBubble, CachedPage
from taslation.notes import legacy_series_key, series_key, sheet_key
from taslation.rename import Stores, moving_series, rename_book


@pytest.fixture
def stores(tmp_path) -> Stores:
    return Stores(CacheStore(tmp_path / "cache"), AnnotationStore(tmp_path / "annotations"),
                  GlossaryStore(tmp_path / "glossary"))


def _cache(store: CacheStore, book: str, pages: int, language: str = "English", details=None) -> None:
    cache = store.open(book, "m", language)
    for i in range(pages):
        cache.add(CachedPage(fingerprint=f"{book}{i}".encode("utf-8").hex()[:80].ljust(80, "0"), aspect=0.7, seq=i,
                             bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text=f"line {i}")]))
    if details:
        cache.set_details(**details)
    cache.save()


def _sheet(stores: Stores, series: str, term: str = "星", rendering: str = "Star") -> None:
    sheet = stores.sheets.open(series, "English")
    sheet.set(term, rendering)
    sheet.save()


OLD_SPELLINGS = {  # a book's old spelling -> the one its two fields make
    "Some Title 3巻": "Some Title 3",
    "見本の物語 第一巻": "見本の物語 1",
    "見本の物語（２）": "見本の物語 2",
    "Other Tale Vol. 4": "Other Tale 4",
    "Another Tale 上巻": "Another Tale 上",
    "Last Tale ⑤": "Last Tale 5",
}


def test_caches_kept_under_old_spellings_are_found_under_the_one_spelling(stores):
    for old in OLD_SPELLINGS:
        _cache(stores.cache, old, 2)
    _cache(stores.cache, "Gate 51", 1)
    for old, standard in OLD_SPELLINGS.items():
        assert split_name(old).name == standard
        assert stores.cache.kept_name(standard) == old, standard  # read and written under the old name, as kept
        assert stores.cache.kept_name(old) == old
    assert stores.cache.kept_name("見本の物語 3") == "見本の物語 3"  # nothing kept: the one spelling
    assert stores.cache.kept_name("Gate 51") == "Gate 51" and stores.cache.kept_name("") == ""
    # two spellings of one book: the one with the most pages; a cache under the one spelling itself comes first
    _cache(stores.cache, "Some Title (3)", 5)
    assert stores.cache.kept_name("Some Title 3") == "Some Title (3)"
    _cache(stores.cache, "Some Title 3", 1)
    assert stores.cache.kept_name("Some Title 3") == "Some Title 3"
    # nothing was renamed by itself
    assert {e["book"] for e in stores.cache.list()} == {*OLD_SPELLINGS, "Gate 51", "Some Title (3)", "Some Title 3"}


def test_a_colophons_details_kept_under_an_old_spelling_are_found(stores):
    details = {"title": "見本の物語", "volume": "1", "isbn": "978-4-06-123456-7"}
    _cache(stores.cache, "見本の物語 第一巻", 1, details=details)
    assert identity_of(stores.cache, "見本の物語 1", "English")["isbn"] == details["isbn"]
    assert identity_of(stores.cache, "見本の物語 2", "English") == {}


def test_a_window_title_gives_the_one_spelling_or_the_old_one_its_files_are_kept_under(stores, tmp_path):
    viewerparts.use(tmp_path / "state")
    _cache(stores.cache, "Some Title 3巻", 2)
    assert viewerparts.book_for_title("Some Title 第3巻 - Google Chrome", stores.cache) == "Some Title 3巻"
    assert viewerparts.book_for_title("Some Title 3巻 - Google Chrome", stores.cache) == "Some Title 3巻"
    assert viewerparts.book_for_title("Other Tale 第2巻 - Google Chrome", stores.cache) == "Other Tale 2"
    assert viewerparts.book_for_title("見本の物語（上） - Google Chrome", stores.cache) == "見本の物語 上"


def test_a_sheet_an_older_parser_kept_for_one_book_alone_is_found_and_moves_with_the_rename(stores):
    old = "見本の物語 第一巻"
    assert legacy_series_key(old) == old and series_key(old) == "見本の物語"
    _cache(stores.cache, old, 2)
    _sheet(stores, old, "星", "Star")  # what the parser before 2026-11-15 kept the sheet under
    assert sheet_key(stores.sheets, old) == old  # read as kept, until the book is renamed
    assert moving_series(stores.sheets, old) == old
    result = rename_book(stores, old, "見本の物語 1", "English")
    assert result.series_moved and (result.old_series, result.new_series) == (old, "見本の物語")
    assert [(e["series"], e["entries"]) for e in stores.sheets.list()] == [("見本の物語", 1)]
    assert stores.sheets.open("見本の物語", "English").get("星").rendering == "Star"
    assert [e["book"] for e in stores.cache.list()] == ["見本の物語 1"] and stores.cache.kept_name("見本の物語 1") == (
        "見本の物語 1")
    assert sheet_key(stores.sheets, "見本の物語 1") == sheet_key(stores.sheets, "見本の物語 2") == "見本の物語"


def test_a_book_renamed_to_the_one_spelling_keeps_its_series_sheet_where_it_is(stores):
    _cache(stores.cache, "Some Title 3巻", 2)
    _sheet(stores, "Some Title")
    assert sheet_key(stores.sheets, "Some Title 3巻") == "Some Title"
    result = rename_book(stores, "Some Title 3巻", "Some Title 3", "English")
    assert not result.series_moved and result.caches == 1
    assert [e["series"] for e in stores.sheets.list()] == ["Some Title"]
    assert stores.cache.kept_name("Some Title 3") == "Some Title 3"


def test_another_series_sheet_the_old_parser_shared_stays_for_its_own_books(stores):
    _sheet(stores, "Some Title")  # the plain edition's sheet; the old parser read 完全版 books with it too
    book = "Some Title 完全版 第3巻"
    assert legacy_series_key(book) == "Some Title" and series_key(book) == "Some Title 完全版"
    _cache(stores.cache, book, 1)
    assert sheet_key(stores.sheets, book) == "Some Title"  # read as before while the edition has no sheet of its own
    assert moving_series(stores.sheets, book) == "Some Title 完全版"  # but never taken away by a rename
    result = rename_book(stores, book, "Some Title 完全版 3", "English")
    assert not result.series_moved and [e["series"] for e in stores.sheets.list()] == ["Some Title"]
    _sheet(stores, "Some Title 完全版", "月", "Moon")
    assert sheet_key(stores.sheets, "Some Title 完全版 3") == "Some Title 完全版"
