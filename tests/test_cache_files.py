"""The cache file on disk: written whole or not at all, never through a temporary file another process may be
writing, a save waiting a moment for a reader on Windows, an entry no pipeline wrote (a hand edit, an import)
skipped instead of breaking the app, and one file per book even when two names give the same file name."""
from __future__ import annotations

import json
import os
import shutil
import threading

import pytest

from conftest import windows_only
from taslation import atomic, names
from taslation.cache import BookCache, CacheStore, CachedBubble, CachedPage, cache_names, stored_book

FP_A, FP_B, FP_C, FP_D = "a" * 80, "b" * 80, "c" * 80, "d" * 80


def _page(fp: str) -> CachedPage:
    return CachedPage(fingerprint=fp, aspect=0.71, seq=-1, bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.4), text="Hello")])


def _saved(tmp_path) -> BookCache:
    cache = CacheStore(tmp_path).open("b", "m")
    cache.add(_page(FP_A))
    cache.save()
    return cache


def test_a_save_never_writes_through_a_shared_temporary_file(tmp_path):
    cache = _saved(tmp_path)
    stray = tmp_path / "b.json.tmp"  # the one name every save used to take: another process may be halfway through it
    stray.write_text("another process, halfway", encoding="utf-8")
    cache.add(_page(FP_B))
    cache.save()
    assert stray.read_text(encoding="utf-8") == "another process, halfway"
    assert len(BookCache.load(cache.path)) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.json", "b.json.tmp"]


def test_a_save_that_fails_halfway_leaves_the_old_file(tmp_path, monkeypatch):
    cache = _saved(tmp_path)
    before = cache.path.read_bytes()

    def crash(_fd):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "fsync", crash)
    cache.add(_page(FP_B))
    with pytest.raises(OSError, match="Input/output"):
        cache.save()
    assert cache.path.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ["b.json"]
    assert cache.dirty and FP_B in cache.touched  # kept for the next save


def test_a_save_tries_again_while_windows_refuses_the_swap(tmp_path, monkeypatch):
    cache = _saved(tmp_path)
    real, calls = os.replace, []

    def busy(src, dst):
        calls.append(dst)
        if len(calls) < 3:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        real(src, dst)

    monkeypatch.setattr(atomic, "REPLACE_PAUSE", 0)
    monkeypatch.setattr(os, "replace", busy)
    cache.add(_page(FP_B))
    cache.save()
    assert len(calls) == 3 and len(BookCache.load(cache.path)) == 2

    def always(_src, _dst):
        raise PermissionError(13, "in use")

    monkeypatch.setattr(os, "replace", always)
    before = cache.path.read_bytes()
    cache.add(_page("c" * 80))
    with pytest.raises(PermissionError):
        cache.save()
    assert cache.path.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ["b.json"]


@windows_only
def test_a_save_while_another_process_reads_the_file(tmp_path):
    """Windows refuses to replace a file that is open (the app reading it while a batch run saves): the save waits."""
    cache = _saved(tmp_path)
    reader = open(cache.path, "rb")
    threading.Timer(0.15, reader.close).start()
    cache.add(_page(FP_B))
    cache.save()
    assert reader.closed and len(BookCache.load(cache.path)) == 2


@pytest.mark.parametrize("page", [
    {"fp": FP_B, "seq": float("inf")},
    {"fp": FP_B, "aspect": float("nan")},
    {"fp": FP_B, "bubbles": [{"box": [float("nan"), 0, 1, 1], "text": "x"}]},
    {"fp": FP_B, "bubbles": [{"box": [0, 0, float("inf"), 1], "text": "x"}]},
    {"fp": FP_B, "bubbles": [{"box": [0, 0, 1e300, 1], "text": "x"}]},
    {"fp": FP_B, "bubbles": [{"box": [0, 0, 1, 1], "poly": [[0, 0], [1, float("nan")], [1, 1]]}]},
], ids=["seq-infinite", "aspect-nan", "box-nan", "box-infinite", "box-huge", "poly-nan"])
def test_a_number_no_pipeline_writes_skips_that_page(tmp_path, page):
    """Drawing such a bubble would fail (int(round(nan)), int(round(inf))); an infinite seq used to stop the load."""
    path = tmp_path / "b.json"
    good = {"fp": FP_A, "aspect": 0.7, "seq": 0, "bubbles": [{"box": [0.1, 0.1, 0.2, 0.2], "text": "kept"}]}
    path.write_text(json.dumps({"schema": 1, "book": "b", "pages": [good, page]}), encoding="utf-8")
    loaded = BookCache.load(path)
    assert [p.fingerprint for p in loaded.pages] == [FP_A]


def test_a_cache_without_a_list_of_pages_counts_as_damaged(tmp_path):
    """It used to raise TypeError, which `CacheStore.open` (and the app) did not expect."""
    store = CacheStore(tmp_path)
    store.path_for("b").write_text(json.dumps({"schema": 1, "book": "b", "pages": 5}), encoding="utf-8")
    with pytest.raises(ValueError):
        BookCache.load(store.path_for("b"))
    cache = store.open("b", "m")  # set aside as b.unreadable-<date>.json, a fresh cache instead
    assert len(cache) == 0 and len(list(tmp_path.glob("b.unreadable-*.json"))) == 1


def test_deleting_a_book_deletes_what_a_stopped_save_left(tmp_path):
    """A temporary file left by a save that stopped halfway holds the book's text too; another book's stays."""
    store = CacheStore(tmp_path)
    for book in ("b", "b x"):
        cache = store.open(book, "m")
        cache.add(_page(FP_A))
        cache.save()
    for name in ("b.json.k3j5h2.tmp", "b.json.tmp", "b_x.json.q8r7s6.tmp"):
        (tmp_path / name).write_text('{"schema": 1, "book": "b", "pag', encoding="utf-8")
    assert store.delete("b")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b_x.json", "b_x.json.q8r7s6.tmp"]


def test_ordinary_positions_still_load(tmp_path):
    """Positions a little outside the page (a bubble over the gutter of a spread) are no damage."""
    path = tmp_path / "b.json"
    page = {"fp": FP_A, "aspect": 1.42, "seq": 3, "bubbles": [
        {"box": [-0.4, 0.1, 1.3, 0.2], "text": "x", "poly": [[-0.4, 0.1], [1.3, 0.1], [1.3, 0.2]]}]}
    path.write_text(json.dumps({"schema": 1, "book": "b", "pages": [page]}), encoding="utf-8")
    loaded = BookCache.load(path)
    assert loaded.pages[0].bubbles[0].box == (-0.4, 0.1, 1.3, 0.2) and loaded.pages[0].seq == 3


# --- two names, one file name ---------------------------------------------------------------------------------

def _book(store: CacheStore, book: str, fp: str, language: str = "English") -> BookCache:
    cache = store.open(book, "m", language)
    cache.add(_page(fp))
    cache.save()
    return cache


def _fingerprints(cache: BookCache) -> set[str]:
    return {p.fingerprint for p in cache.pages}


def _ignores_case(folder) -> bool:
    """True on a file system that ignores letter case (Windows, macOS)."""
    probe = folder / "Case-Probe.txt"
    probe.write_text("x", encoding="utf-8")
    try:
        return (folder / "case-probe.txt").exists()
    finally:
        probe.unlink()


LONG = "x" * 125  # past the 120 characters a file name keeps


@pytest.mark.parametrize("first, second", [
    ("Pebble:Harbor 1", "Pebble Harbor 1"), ("QUILLPOND 1", "Quillpond 1"), (LONG + " vol 1", LONG + " vol 2"), ("!!!", "???"),
], ids=["punctuation", "letter-case", "cut", "all-symbols"])
@pytest.mark.parametrize("language", ["English", "German"])
def test_names_that_give_one_file_name_get_a_file_each(tmp_path_factory, first, second, language):
    """The first book keeps the plain name; the second gets the plain name with its name's hash. Each opens its
    own pages, the list shows both and no copy, and deleting one leaves the other."""
    tmp_path = tmp_path_factory.mktemp("c")  # a short folder: 120 characters of name and a dated copy's suffix fit
    store = CacheStore(tmp_path)
    a, b = _book(store, first, FP_A, language), _book(store, second, FP_B, language)
    plain, hashed = cache_names(second, language)
    shared = cache_names(first, language)[0] == plain or (_ignores_case(tmp_path) and
                                                         cache_names(first, language)[0].lower() == plain.lower())
    assert a.path.name == cache_names(first, language)[0]
    assert b.path.name == (hashed if shared else plain) and a.path != b.path
    assert _fingerprints(store.open(first, "m", language)) == {FP_A}
    assert _fingerprints(store.open(second, "m", language)) == {FP_B}
    shutil.copy(b.path, b.path.with_suffix(".before-import.20261030-120000.json"))  # a copy is no cache of its own
    shutil.copy(a.path, a.path.with_suffix(".before-apply.20261030-120000.json"))
    listed = sorted((e["book"], os.path.basename(e["file"]), e["language"]) for e in store.list())
    assert listed == sorted([(first, a.path.name, language), (second, b.path.name, language)])
    assert store.delete(second)
    assert [e["book"] for e in store.list()] == [first] and not b.path.exists()
    assert not list(tmp_path.glob("*.before-import.*")) and len(list(tmp_path.glob("*.before-apply.*"))) == 1
    assert _fingerprints(store.open(first, "m", language)) == {FP_A}


def test_a_book_keeps_its_file_when_the_plain_name_comes_free(tmp_path):
    """Deleting the book that had the plain name never sends the other one back to it (its pages are where they
    are), and a third name that gives the same file name takes the free plain name."""
    store = CacheStore(tmp_path)
    _book(store, "Pebble:Harbor 1", FP_A)
    second = _book(store, "Pebble Harbor 1", FP_B)
    assert store.delete("Pebble:Harbor 1")
    assert store.path_for("Pebble Harbor 1") == second.path and _fingerprints(store.open("Pebble Harbor 1", "m")) == {FP_B}
    third = _book(store, "Pebble_Harbor 1", FP_C)
    assert third.path.name == cache_names("Pebble_Harbor 1")[0]
    assert sorted(e["book"] for e in store.list()) == ["Pebble Harbor 1", "Pebble_Harbor 1"]


def test_open_never_reads_another_books_file_as_its_own(tmp_path, monkeypatch):
    store = CacheStore(tmp_path)
    mine = _book(store, "Pebble:Harbor 1", FP_A)
    other = store.open("Pebble Harbor 1", "m")
    assert other.book == "Pebble Harbor 1" and len(other) == 0 and other.path != mine.path
    assert stored_book(mine.path) == ("Pebble:Harbor 1", "english")
    assert stored_book(tmp_path / "none.json") is None
    # had another process written the file between path_for and the read, open says so instead of reading it
    monkeypatch.setattr(CacheStore, "path_for", lambda self, book, language="English": mine.path)
    with pytest.raises(FileExistsError, match="holds the cache of 'Pebble:Harbor 1'"):
        store.open("Pebble Harbor 1", "m")
    assert _fingerprints(BookCache.load(mine.path)) == {FP_A}


def test_two_names_with_one_hash_are_refused(tmp_path, monkeypatch):
    """Both file names a book can have hold other books only for two names with the same hash (made so here)."""
    monkeypatch.setattr(names, "name_hash", lambda _book: "00000000")
    store = CacheStore(tmp_path)
    _book(store, "Pebble:Harbor 1", FP_A)
    assert _book(store, "Pebble?Harbor 1", FP_B).path.name == "Pebble_Harbor_1-00000000.json"
    with pytest.raises(FileExistsError, match="'Pebble:Harbor 1'.*'Pebble\\?Harbor 1'"):
        store.path_for("Pebble Harbor 1")
    assert _fingerprints(store.open("Pebble?Harbor 1", "m")) == {FP_B}  # the two that have files go on


def test_two_new_books_with_one_file_name_saved_at_once(tmp_path):
    """Opened before either was saved (the app and a batch run), both start on the plain name: the later save finds
    the other book there and moves to its own file instead of merging into it."""
    store = CacheStore(tmp_path)
    first, second = store.open("Pebble:Harbor 1", "m"), store.open("Pebble Harbor 1", "m")
    assert first.path == second.path
    first.add(_page(FP_A))
    first.save()
    second.add(_page(FP_B))
    assert second.refresh() is False and _fingerprints(second) == {FP_B}  # never the other book's pages
    second.save()
    assert second.path.name == cache_names("Pebble Harbor 1")[1]
    assert _fingerprints(BookCache.load(first.path)) == {FP_A} and _fingerprints(BookCache.load(second.path)) == {FP_B}
    first.add(_page(FP_C))
    first.save()
    second.add(_page(FP_D))
    second.save()
    assert _fingerprints(store.open("Pebble:Harbor 1", "m")) == {FP_A, FP_C}
    assert _fingerprints(store.open("Pebble Harbor 1", "m")) == {FP_B, FP_D}


def test_the_copies_an_earlier_version_set_aside_are_still_copies(tmp_path):
    """Earlier versions moved a cache they could not read to <file>.corrupt.json (over an earlier one): such a copy
    is never listed, nor read as a cache, even when it can be read, and goes with its book."""
    store = CacheStore(tmp_path)
    mine = _book(store, "b", FP_A)
    german = _book(store, "b", FP_B, "German")
    shutil.copy(mine.path, tmp_path / "b.corrupt.json")
    shutil.copy(german.path, tmp_path / "b.german.corrupt.json")
    (tmp_path / "b_x.corrupt.json").write_text('{"schema": 1, "book": "b x", "pag', encoding="utf-8")  # another book's
    assert sorted((e["book"], e["language"]) for e in store.list()) == [("b", "English"), ("b", "German")]
    assert store.path_for("b") == mine.path and _fingerprints(store.open("b", "m")) == {FP_A}
    assert store.delete("b")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b_x.corrupt.json"]


def test_delete_takes_an_unreadable_file_only_under_the_books_own_names(tmp_path):
    store = CacheStore(tmp_path)
    _book(store, "Pebble:Harbor 1", FP_A)
    for book in ("Pebble Harbor 1", "Pebble?Harbor 1"):
        (tmp_path / cache_names(book)[1]).write_text('{"schema": 1, "book": "Pebble', encoding="utf-8")
    assert store.delete("Pebble Harbor 1")
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["Pebble_Harbor_1.json", cache_names("Pebble?Harbor 1")[1]])


@windows_only
def test_a_file_whose_name_has_other_letter_case_is_still_listed(tmp_path):
    """Windows gives a replaced file the letter case of the name it was replaced through (an earlier version saved
    one book's cache through another's name): the list still shows it, and path_for finds it."""
    store = CacheStore(tmp_path)
    (tmp_path / "pebble_harbor_1.json").write_text(json.dumps({"schema": 1, "book": "Pebble:Harbor 1", "pages": []}),
                                             encoding="utf-8")
    assert [e["book"] for e in store.list()] == ["Pebble:Harbor 1"]
    assert store.path_for("Pebble:Harbor 1").is_file()
