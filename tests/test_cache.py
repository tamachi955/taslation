from __future__ import annotations

import json

from helpers import store_json

from taslation import viewerparts
from taslation.cache import (
    BookCache,
    CacheStore,
    CachedBubble,
    CachedPage,
    book_key_from_title,
    slugify,
    viewer_key_from_title,
)

FP_A = "a" * 80
FP_B = "b" * 80


def _page(fp: str, seq: int = -1) -> CachedPage:
    return CachedPage(fingerprint=fp, aspect=0.71, seq=seq,
                      bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.4), text="Hello", poly=[(0.1, 0.1), (0.3, 0.1), (0.3, 0.4)])])


def test_roundtrip_and_lookup(tmp_path):
    store = CacheStore(tmp_path / "cache")
    cache = store.open("My Book", "qwen2.5:7b")
    cache.add(_page(FP_A))
    cache.add(_page(FP_B))
    cache.save()
    loaded = BookCache.load(cache.path)
    assert len(loaded) == 2 and loaded.bubble_count == 2
    assert [p.seq for p in loaded.pages] == [0, 1]
    hit = loaded.lookup(FP_A, 0.71, max_distance=10)
    assert hit is not None and hit[0].fingerprint == FP_A and hit[1] == 0
    # a few flipped bits still match; a different aspect does not
    near = "a" * 79 + "b"
    assert loaded.lookup(near, 0.71, max_distance=10) is not None
    assert loaded.lookup(FP_A, 1.5, max_distance=10) is None
    assert loaded.lookup("c" * 80, 0.71, max_distance=10) is None


def test_near_duplicate_replaces_instead_of_growing(tmp_path):
    cache = CacheStore(tmp_path).open("b", "m")
    cache.add(_page(FP_A))
    again = _page("a" * 79 + "b")
    cache.add(again)
    assert len(cache) == 1 and cache.pages[0].seq == 0


def test_file_contains_only_text_and_geometry(tmp_path):
    cache = CacheStore(tmp_path).open("b", "m")
    cache.add(_page(FP_A))
    cache.save()
    data = store_json(cache.path)
    assert data["schema"] == 1
    assert set(data["pages"][0].keys()) == {"fp", "aspect", "seq", "bubbles"}
    assert set(data["pages"][0]["bubbles"][0].keys()) == {"box", "text", "poly"}
    assert set(data.keys()) == {"schema", "app", "note", "book", "model", "language", "created", "updated", "pages"}
    assert len(json.dumps(data)) < 2000  # text and a handful of numbers, nothing pixel-sized


def test_bad_page_entries_are_skipped_and_languages_are_separate(tmp_path):
    store = CacheStore(tmp_path)
    cache = store.open("Book", "m")
    cache.add(_page(FP_A))
    cache.save()
    data = store_json(cache.path)
    data["pages"].append({"fp": "not-hex", "aspect": 0.7, "seq": 5, "bubbles": []})
    cache.path.write_text(json.dumps(data), encoding="utf-8")
    assert len(store.open("Book", "m")) == 1
    german = store.open("Book", "m", "German")
    assert german.path != cache.path and len(german) == 0
    german.add(_page(FP_B))
    german.save()
    assert store.delete("Book")
    assert not cache.path.exists() and not german.path.exists()


def test_store_list_delete_and_corrupt_file(tmp_path):
    store = CacheStore(tmp_path)
    cache = store.open("Some Book", "m")
    cache.add(_page(FP_A))
    cache.save()
    assert store.list()[0]["book"] == "Some Book"
    store.path_for("Broken").write_text("{not json", encoding="utf-8")
    assert len(store.open("Broken", "m")) == 0  # corrupt file is set aside, not fatal
    assert store.delete("Some Book")
    assert not store.delete("Some Book")


def _learned(*parts: str) -> None:
    """*parts* are viewers' parts, as choosing their windows teaches (tests/test_viewer_parts.py). The viewers named in
    these tests are invented."""
    viewerparts.change(lambda memory: memory.learn(parts))


def test_book_key_from_window_titles():
    # nothing learned on this computer: only what a browser adds goes
    assert book_key_from_title("ワンダフル物語 1巻 - Yomizuq") == "ワンダフル物語 1巻 - Yomizuq"
    assert book_key_from_title("ある本 - FOLIO☆QAT - Google Chrome") == "ある本 - FOLIO☆QAT"
    _learned("Yomizuq", "FOLIO☆QAT")
    assert book_key_from_title("ワンダフル物語 1巻 - Yomizuq") == "ワンダフル物語 1巻"  # a viewer's part after the book
    assert book_key_from_title("Yomizuq - My Book") == "My Book"  # and before it
    assert book_key_from_title("ある本 - FOLIO☆QAT - Google Chrome") == "ある本"
    assert book_key_from_title("ある本 | FOLIO☆QAT") == "ある本" and book_key_from_title("ある本｜FOLIO☆QAT") == "ある本"
    assert book_key_from_title("ある本 - folio☆qat - page 12") == "ある本"  # letter case; a page number at the end
    assert book_key_from_title("ある本 - Yomizuq\u200b - Microsoft\u200b Edge") == "ある本"  # zero-width spaces
    assert book_key_from_title("Yomizuq - Google Chrome") == "Yomizuq"  # nothing but the viewer: names no book
    assert book_key_from_title("Yomizuq の使い方 - Google Chrome") == "Yomizuq の使い方"  # its name in a longer segment
    assert book_key_from_title("   ") == "untitled"
    assert slugify("ある本/1巻: 第1話") == "ある本_1巻_第1話"


def test_a_windows_device_name_is_never_a_file_name(tmp_path):
    """A file called CON, NUL, COM1 ... opens the device on Windows (on Windows 10 with any extension too): what is
    written to it is gone. The name gets a "_" in front; anything longer stays as it was."""
    for name in ("CON", "con", "Nul", "AUX", "PRN", "COM1", "com9", "LPT1", "LPT9", "COM0", "LPT²"):
        assert slugify(name) == "_" + name, name
    assert slugify(" .nul. ") == "_nul"  # what is left once the dots and spaces go
    for name, slug in (("CONSOLE", "CONSOLE"), ("COM10", "COM10"), ("LPT", "LPT"), ("NUL 1", "NUL_1"),
                       ("AUX-1", "AUX-1"), ("con_tent", "con_tent")):
        assert slugify(name) == slug, name
    store = CacheStore(tmp_path)
    cache = store.open("NUL", "m")
    cache.add(_page(FP_A))
    cache.save()
    assert cache.path.name == "_NUL.json" and len(store.open("NUL", "m")) == 1
    assert [b["book"] for b in store.list()] == ["NUL"] and store.delete("NUL")
    assert store.path_for("Book", "Aux").name == "Book._aux.json"


def test_viewer_key_from_window_titles():
    assert viewer_key_from_title("ある本 - FOLIO☆QAT - Google Chrome") == "Google Chrome"  # nothing learned yet
    _learned("Yomizuq", "FOLIO☆QAT")
    assert viewer_key_from_title("ある本 - FOLIO☆QAT - Google Chrome") == "FOLIO☆QAT - Google Chrome"
    assert viewer_key_from_title("別の本 - FOLIO☆QAT - Google Chrome") == "FOLIO☆QAT - Google Chrome"
    assert viewer_key_from_title("ワンダフル物語 1巻 - Yomizuq") == "Yomizuq"
    assert viewer_key_from_title("Yomizuq") == "Yomizuq"
    assert viewer_key_from_title("Yomizuq - Google Chrome") == "Google Chrome"  # as the tables of names had it
    assert viewer_key_from_title("Fake Viewer - Test Book") == "Fake Viewer - Test Book"


def test_what_a_browser_adds_to_the_title_is_no_book():
    from taslation.bookid import generic_book_name

    viewer = "Yomizuq"  # a browser-based viewer, as this computer learned it
    assert not generic_book_name(book_key_from_title(f"{viewer} - Personal - Microsoft Edge"))  # not learned yet
    _learned(viewer)
    for profile in ("個人", "Personal", "Work", "Profile 1"):
        assert book_key_from_title(f"{viewer} - {profile} - Microsoft Edge") == viewer
        assert generic_book_name(book_key_from_title(f"{viewer} - {profile} - Microsoft Edge"))
        assert book_key_from_title(f"ある本 - {profile} - Microsoft Edge") == "ある本"
    assert book_key_from_title("ある本 - 個人 - Microsoft\u200b Edge") == "ある本"  # as the real title spells it
    assert book_key_from_title("ある本 - Profile 2 - Google Chrome") == "ある本"
    assert book_key_from_title("ある本 — Mozilla Firefox") == "ある本"
    assert book_key_from_title("Work - Microsoft Edge") == "Work"  # a tab of that name: no profile before it
    assert book_key_from_title("ある本 - Personal") == "ある本 - Personal"  # no browser named: all of it
    assert viewer_key_from_title("ある本 - 個人 - Microsoft Edge") == "個人 - Microsoft Edge"
    assert viewer_key_from_title("別の本 - 個人 - Microsoft Edge") == "個人 - Microsoft Edge"
