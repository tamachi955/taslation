"""Renaming a book (`taslation.rename`): everything kept under the old name - the cache in every language, the reader's
annotations and, when the series changes, the series sheet in every language - moves to the new name through the
stores' own naming, the old files deleted with the copies kept beside them; the moved cache keeps its details and takes
the colophon's. Nothing is ever written over: a target that exists, or an old file that cannot be read, refuses the
rename and nothing changes; a write that fails takes back what was written. Where the new series has a sheet in a
language already, the book's joins it (`plan_rename` says what would join and refuses what `rename_book` refuses):
additions taken over, each conflict kept as the series had it unless answered by its key; a failed write gives a joined
file its bytes back. A series that stays keeps its sheet where it is; a name that names no book is refused. Temp
folders only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from taslation import protect
from taslation import rename as rename_mod
from taslation import viewerparts
from taslation.annotations import AnnotationStore, CharacterSheet, GlossaryStore, StyleGuide
from taslation.bookid import identity_of
from taslation.cache import CacheStore, CachedBubble, CachedPage
from taslation.config import Settings
from taslation.names import file_names
from taslation.notes import series_key
from taslation.rename import RenameRefused, RenameResult, Stores, conflict_key, plan_rename, rename_book
from helpers import store_json

OLD, NEW = "my star book 3", "見本の物語 3"
COLOPHON = {"title": "見本の物語", "volume": "3", "author": "仮野みのり", "publisher": "株式会社見本出版",
            "isbn": "978-4-06-123456-7"}


@pytest.fixture(autouse=True)
def viewers_learned():
    """This computer has learned two (invented) viewers (how: tests/test_viewer_parts.py): their names name no book."""
    viewerparts.change(lambda memory: memory.learn(["Yomizuq", "FOLIO☆QAT"]))


@pytest.fixture
def stores(tmp_path) -> Stores:
    return Stores(CacheStore(tmp_path / "cache"), AnnotationStore(tmp_path / "annotations"),
                  GlossaryStore(tmp_path / "glossary"))


def _keep(stores: Stores, book: str, languages=("English", "German"), details=None) -> None:
    """What a reader keeps of *book*: its cache in *languages* (two pages), its annotations, and its series' sheet
    in each language."""
    for language in languages:
        cache = stores.cache.open(book, "m", language)
        for mark in "ab":
            cache.add(CachedPage(fingerprint=mark * 80, aspect=0.7, seq=-1,
                                 bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text=f"{language} {mark}")]))
        if details:
            cache.set_details(**details)
        cache.save()
    ann = stores.annotations.open(book)
    ann.add_box("c" * 80, 0.7, (0.1, 0.1, 0.3, 0.2), "add")
    ann.reading_direction = "rtl"
    ann.save()
    series = series_key(book)
    for language in languages:
        sheet = stores.sheets.open(series, language)
        sheet.set("星", f"Star ({language})")
        sheet.save()


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_a_book_and_its_series_move_to_the_new_name(stores, tmp_path):
    _keep(stores, OLD, details={"publisher": "Pub", "author": "someone"})
    old_cache = stores.cache.path_for(OLD)
    copy = old_cache.with_name(old_cache.stem + ".unreadable-20261030-101010.json")  # set aside from the old cache
    copy.write_text("{not json", encoding="utf-8")
    leftover = old_cache.with_name(old_cache.name + ".k3x9q.tmp")  # what a save that stopped halfway left
    leftover.write_bytes(b"{")
    result = rename_book(stores, OLD, NEW, "English", details=COLOPHON)
    assert isinstance(result, RenameResult) and result.old == OLD and result.new == NEW
    assert (result.caches, result.annotations, result.sheets) == (2, 1, 2) and result.files == 5
    assert result.series_moved and (result.old_series, result.new_series) == ("my star book", "見本の物語")
    assert result.left == []
    # the caches in both languages: the new name in the header, the pages kept, the colophon's details taken in
    assert sorted((e["book"], e["language"], e["pages"]) for e in stores.cache.list()) == [
        (NEW, "English", 2), (NEW, "German", 2)]
    for language in ("English", "German"):
        cache = stores.cache.open(NEW, "m", language)
        assert cache.path.name == file_names(NEW, language)[0]
        assert sorted(b.text for p in cache.pages for b in p.bubbles) == [f"{language} a", f"{language} b"]
        assert cache.details == COLOPHON  # its own details, the colophon's over them
        data = store_json(cache.path)
        assert data["book"] == NEW and list(data)[-1] == "pages"  # the header first, as a save writes it
    assert identity_of(stores.cache, NEW, "English") == COLOPHON
    # the annotations, the sheet in both languages
    ann = stores.annotations.open(NEW)
    assert ann.box_count == 1 and ann.reading_direction == "rtl" and ann.path.name == file_names(NEW)[0]
    assert sorted((e["series"], e["language"], e["entries"]) for e in stores.sheets.list()) == [
        ("見本の物語", "English", 1), ("見本の物語", "German", 1)]
    assert stores.sheets.open("見本の物語", "German").get("星").rendering == "Star (German)"
    # nothing is left under the old name: no file, no copy, no leftover
    assert not copy.exists() and not leftover.exists()
    assert not any(p.name.startswith("my_star_book") for p in tmp_path.rglob("*"))
    assert stores.annotations.list()[0]["book"] == NEW


@pytest.mark.parametrize("taken", ["cache", "annotations"])
def test_a_rename_onto_files_that_exist_is_refused_and_nothing_changes(stores, tmp_path, taken):
    _keep(stores, OLD)
    if taken == "cache":  # the new name has a cache of its own already (in one of the languages)
        other = stores.cache.open(NEW, "m", "German")
        other.add(CachedPage(fingerprint="d" * 80, aspect=0.7, seq=-1, bubbles=[]))
        other.save()
        path = other.path
    else:
        ann = stores.annotations.open(NEW)
        ann.add_box("d" * 80, 0.7, (0.1, 0.1, 0.3, 0.2), "add")
        ann.save()
        path = ann.path
    before = _files(tmp_path)
    for attempt in (lambda: plan_rename(stores, OLD, NEW), lambda: rename_book(stores, OLD, NEW, "English", COLOPHON)):
        with pytest.raises(RenameRefused) as refused:  # the plan refuses what the rename refuses
            attempt()
        assert "exists already" in str(refused.value) and str(path) in str(refused.value)
    assert _files(tmp_path) == before  # nothing written, nothing deleted


SERIES = "見本の物語"
MISSING = ("term", "空", "", "")  # an answer for a conflict that is not there: nothing


def _series_sheet(stores: Stores, language: str = "English", star: str = "Stardust") -> Path:
    """The new series' own sheet in *language*, kept before the rename (its file has a header field of its own and
    an old ``updated``): 星 rendered otherwise than the book's sheet, a term of its own, ピヨ, two policies."""
    sheet = stores.sheets.open(SERIES, language)
    sheet.set("星", star)
    sheet.set("月", "Moon")
    sheet.set_character(CharacterSheet(name="ピヨ", rendering="Piyo", pronoun="私"))
    sheet.style = StyleGuide(honorifics="keep", tone="light")
    sheet.save()
    data = store_json(sheet.path)
    sheet.path.write_text(json.dumps({**data, "updated": "2020-01-01T00:00:00", "shared_by": "a friend"},
                                     ensure_ascii=False), encoding="utf-8")
    return sheet.path


def _book_sheet(stores: Stores, language: str = "English") -> None:
    """More on the book's own sheet in *language* (beside 星, `_keep`): a term, ピヨ with another first person and a
    fact the series' lacks, another honorifics policy and a house rule."""
    sheet = stores.sheets.open(series_key(OLD), language)
    sheet.set("空", "Sky")
    sheet.set_character(CharacterSheet(name="ピヨ", rendering="Piyo", pronoun="僕", gender="female"))
    sheet.style = StyleGuide(honorifics="drop", rules=["Short SFX."])
    sheet.save()


@pytest.mark.parametrize("answers", [None, {("term", "星", "", ""): True, MISSING: True}])
def test_the_books_sheet_joins_the_sheet_the_new_series_has_already(stores, tmp_path, answers):
    _keep(stores, OLD)  # its sheet in English and German
    _book_sheet(stores)
    target = _series_sheet(stores)  # the new series has a sheet in English only: German moves as it is
    before = _files(tmp_path)
    plan = plan_rename(stores, OLD, NEW)
    assert _files(tmp_path) == before  # the plan writes nothing
    assert plan.series_moved and [(s.language, s.added) for s in plan.sheets] == [("English", 3)]
    assert sorted(conflict_key(c) for c in plan.conflicts) == [
        ("character", "ピヨ", "pronoun", ""), ("style", "honorifics", "", ""), ("term", "星", "", "")]
    assert not any(c.take for c in plan.conflicts)  # the series' value unless answered otherwise
    star = next(c for c in plan.conflicts if c.area == "term")
    assert (star.mine, star.theirs) == (("Stardust", ""), ("Star (English)", ""))  # mine: the series' sheet
    assert [key for key, _language, _c in plan.keyed()] == [conflict_key(c) for c in plan.conflicts]
    result = rename_book(stores, OLD, NEW, "English", answers=answers)
    taken = 1 if answers else 0
    assert (result.sheets, result.sheets_merged, result.added, result.taken, result.kept) == (2, 1, 3, taken, 3 - taken)
    assert result.files == 5 and result.left == []
    sheet = stores.sheets.open(SERIES, "English")
    assert sheet.path == target  # written in place of the series' file
    assert sheet.get("星").rendering == ("Star (English)" if answers else "Stardust")
    assert (sheet.get("月").rendering, sheet.get("空").rendering) == ("Moon", "Sky")  # its own, and the book's added
    piyo = sheet.get_character("ピヨ")
    assert (piyo.pronoun, piyo.gender) == ("私", "female")  # the series' first person kept, the fact it lacked added
    assert (sheet.style.honorifics, sheet.style.tone, sheet.style.rules) == ("keep", "light", ["Short SFX."])
    data = store_json(target)
    assert (data["series"], data["language"], data["shared_by"], data["kind"]) == (SERIES, "English", "a friend",
                                                                                  "glossary")
    assert data["updated"] != "2020-01-01T00:00:00"
    assert stores.sheets.open(SERIES, "German").get("星").rendering == "Star (German)"  # moved as it was
    assert sorted((e["series"], e["language"], e["entries"]) for e in stores.sheets.list()) == [
        (SERIES, "English", 3), (SERIES, "German", 1)]
    assert not any(p.name.startswith("my_star_book") for p in (tmp_path / "glossary").iterdir())  # the book's: gone


@pytest.mark.parametrize("answers, english, german", [
    ({("english", "term", "星", "", ""): True}, "Star (English)", "Sternenstaub"),  # for the English sheet alone
    ({("term", "星", "", ""): True}, "Star (English)", "Star (German)"),  # in every sheet
    ({("term", "星", "", ""): True, ("german", "term", "星", "", ""): False}, "Star (English)", "Sternenstaub"),
    ({}, "Stardust", "Sternenstaub"),
])
def test_each_languages_sheet_joins_on_its_own_and_an_answer_can_name_the_language(stores, answers, english, german):
    _keep(stores, OLD)
    _series_sheet(stores, "English")
    _series_sheet(stores, "German", star="Sternenstaub")
    plan = plan_rename(stores, OLD, NEW)
    assert sorted(s.language for s in plan.sheets) == ["English", "German"]
    assert sorted(key for key, _language, _c in plan.keyed()) == [  # conflicts in two languages: keyed with them
        ("english", "term", "星", "", ""), ("german", "term", "星", "", "")]
    result = rename_book(stores, OLD, NEW, answers=answers)
    assert result.sheets_merged == 2 and result.taken + result.kept == 2
    assert stores.sheets.open(SERIES, "English").get("星").rendering == english
    assert stores.sheets.open(SERIES, "German").get("星").rendering == german


@pytest.mark.parametrize("what", ["newer sheet", "sheet of no series"])
def test_a_sheet_of_the_new_series_that_cannot_be_read_refuses_the_rename(stores, tmp_path, what):
    _keep(stores, OLD, languages=("English",))
    folder = tmp_path / "glossary"
    path = folder / file_names(SERIES, "English")[0]
    if what == "newer sheet":  # written by a newer TASlation: never written over unread
        content = json.dumps({"schema": 99, "kind": "glossary", "series": SERIES, "language": "English"})
    else:  # whose it is cannot be told: in the way
        content = json.dumps({"schema": 1, "kind": "glossary", "entries": [{"term": "月", "rendering": "Moon"}]})
    folder.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    before = _files(tmp_path)
    expected = "cannot be read" if "newer" in what else "is in the way of"
    for attempt in (lambda: plan_rename(stores, OLD, NEW), lambda: rename_book(stores, OLD, NEW)):
        with pytest.raises(RenameRefused, match=expected) as refused:
            attempt()
        assert str(path) in str(refused.value)
    assert _files(tmp_path) == before


def test_a_write_that_fails_gives_a_joined_sheet_its_bytes_back(stores, tmp_path, monkeypatch):
    _keep(stores, OLD)
    _book_sheet(stores)
    joined = {_series_sheet(stores), _series_sheet(stores, "German", star="Sternenstaub")}  # both languages join
    before = _files(tmp_path)
    real, calls = rename_mod.write_atomic, []

    def failing(path, data):
        calls.append(Path(path))
        if Path(path) in joined and len({c for c in calls if c in joined}) == 2 and calls.count(Path(path)) == 1:
            raise OSError(28, "No space left on device", str(path))  # the second joined sheet, first written
        real(path, data)

    monkeypatch.setattr(rename_mod, "write_atomic", failing)
    with pytest.raises(OSError, match="No space left"):
        rename_book(stores, OLD, NEW, answers={("term", "星", "", ""): True})
    first = next(c for c in calls if c in joined)
    assert calls.count(first) == 2  # the first joined sheet written, then its old bytes again
    # everything as it was: the series' sheet (its old bytes, written back protected), the new files gone
    assert set(_files(tmp_path)) == set(before)
    assert ({k: protect.readable(v) for k, v in _files(tmp_path).items()}
            == {k: protect.readable(v) for k, v in before.items()})
    assert protect.is_protected(first.read_bytes())


def test_a_file_in_the_way_or_an_old_file_that_cannot_be_read_refuses_the_rename(stores, tmp_path):
    _keep(stores, OLD)
    in_the_way = stores.cache.path_for(NEW)
    in_the_way.write_text("{damaged", encoding="utf-8")  # never written over, whatever it holds
    before = _files(tmp_path)
    with pytest.raises(RenameRefused, match="is in the way of the cache of"):
        rename_book(stores, OLD, NEW)
    assert _files(tmp_path) == before
    in_the_way.unlink()
    german = stores.cache.path_for(OLD, "German")  # written by a newer TASlation: never deleted unread
    german.write_text(json.dumps({"schema": 99, "book": OLD, "language": "German", "pages": []}), encoding="utf-8")
    before = _files(tmp_path)
    with pytest.raises(RenameRefused, match="cannot be read"):
        rename_book(stores, OLD, NEW)
    assert _files(tmp_path) == before


def test_a_series_that_stays_keeps_its_sheet_where_it_is(stores, tmp_path):
    old, new = "Star Road 第3巻", "Star Road 3"
    assert series_key(old) == series_key(new) == "Star Road"
    _keep(stores, old)
    sheets = _files(tmp_path / "glossary")
    result = rename_book(stores, old, new)
    assert (result.caches, result.annotations, result.sheets) == (2, 1, 0)
    assert not result.series_moved
    assert _files(tmp_path / "glossary") == sheets  # the sheet in place, not a byte changed
    assert [e["book"] for e in stores.annotations.list()] == [new]
    assert {e["book"] for e in stores.cache.list()} == {new}


@pytest.mark.parametrize("name", ["Yomizuq", " yomizuq ", "", "   ", "Google Chrome", "untitled", "FOLIO☆QAT"])
def test_a_name_that_names_no_book_is_refused(stores, tmp_path, name):
    _keep(stores, OLD, languages=("English",))
    before = _files(tmp_path)
    with pytest.raises(RenameRefused, match="names no book"):
        rename_book(stores, OLD, name)
    with pytest.raises(RenameRefused, match="is called 'my star book 3' already"):
        rename_book(stores, OLD, OLD)
    with pytest.raises(RenameRefused, match="no book to rename"):
        rename_book(stores, " ", NEW)
    assert _files(tmp_path) == before


def test_an_old_cache_kept_under_a_name_that_names_no_book_can_be_renamed(stores):
    _keep(stores, "Yomizuq", languages=("English",))  # kept before the name was asked for
    result = rename_book(stores, "Yomizuq", NEW, "English", details=COLOPHON)
    assert (result.caches, result.annotations, result.sheets) == (1, 1, 1)
    assert [e["book"] for e in stores.cache.list()] == [NEW] and [e["series"] for e in stores.sheets.list()] == ["見本の物語"]


def test_a_name_that_gives_the_same_file_name_is_written_in_place(stores, tmp_path):
    _keep(stores, "Pebble Harbor 1", languages=("English",))
    path = stores.cache.path_for("Pebble Harbor 1")
    result = rename_book(stores, "Pebble Harbor 1", "Pebble:Harbor 1")
    assert result.caches == 1 and result.left == []
    assert stores.cache.path_for("Pebble:Harbor 1") == path and store_json(path)["book"] == "Pebble:Harbor 1"
    assert [e["book"] for e in stores.cache.list()] == ["Pebble:Harbor 1"]
    assert [e["book"] for e in stores.annotations.list()] == ["Pebble:Harbor 1"]
    assert [e["series"] for e in stores.sheets.list()] == ["Pebble:Harbor"]  # its own series now, in the same file
    assert sorted(p.name for p in (tmp_path / "cache").iterdir()) == [path.name]


def test_a_book_beside_another_with_the_same_file_name_gets_the_hashed_one(stores, tmp_path):
    _keep(stores, "Pebble Harbor 1", languages=("English",))
    _keep(stores, "Other", languages=("English",))
    rename_book(stores, "Other", "Pebble:Harbor 1")  # "Pebble Harbor 1" keeps the plain file name
    assert stores.cache.path_for("Pebble Harbor 1").name == "Pebble_Harbor_1.json"
    assert stores.cache.path_for("Pebble:Harbor 1").name == file_names("Pebble:Harbor 1", "English")[1]
    assert sorted(e["book"] for e in stores.cache.list()) == ["Pebble Harbor 1", "Pebble:Harbor 1"]


@pytest.mark.parametrize("old, new, in_place", [("Pebble Harbor 1", "Pebble:Harbor 1", True), (OLD, NEW, False)])
def test_a_write_that_fails_takes_back_what_was_written(stores, tmp_path, monkeypatch, old, new, in_place):
    _keep(stores, old)  # the same file names (written in place) or others (new files)
    before = _files(tmp_path)
    real, calls = rename_mod.write_atomic, []

    def failing(path, data):
        calls.append(path)
        if len(calls) == 5:
            raise OSError(28, "No space left on device", str(path))
        real(path, data)

    monkeypatch.setattr(rename_mod, "write_atomic", failing)
    with pytest.raises(OSError, match="No space left"):
        rename_book(stores, old, new)
    # the four written before were taken back: the old bytes written again in place, the new files deleted
    assert len(calls) == (9 if in_place else 5)
    assert _files(tmp_path) == before


def test_an_old_file_that_cannot_be_deleted_stays_and_is_named(stores, monkeypatch):
    _keep(stores, OLD, languages=("English",))
    held = stores.annotations.path_for(OLD)
    real = Path.unlink

    def unlink(self, missing_ok=False):
        if self == held:
            raise PermissionError(13, "The process cannot access the file", str(self))
        return real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    result = rename_book(stores, OLD, NEW)
    assert result.left == [str(held)] and held.exists()
    assert [e["book"] for e in stores.cache.list()] == [NEW]  # the rest went


def test_the_colophons_details_go_where_the_window_looks_for_them(stores):
    ann = stores.annotations.open(OLD)  # nothing but the annotations kept: no cache to take the details
    ann.add_box("c" * 80, 0.7, (0.1, 0.1, 0.3, 0.2), "add")
    ann.save()
    result = rename_book(stores, OLD, NEW, "English", details={**COLOPHON, "date": "2024年5月10日", "isbn": ""})
    assert (result.caches, result.annotations) == (0, 1)
    assert identity_of(stores.cache, NEW, "English") == {k: v for k, v in COLOPHON.items() if k != "isbn"}
    assert rename_book(stores, NEW, "見本の物語 第3巻").caches == 1  # the cache made for them moves like any other


def test_a_sheet_that_records_no_series_moves_under_its_english_file_name(stores, tmp_path):
    folder = tmp_path / "glossary"
    folder.mkdir()
    written_by_hand = {"schema": 1, "kind": "glossary", "entries": [{"term": "星", "rendering": "Star"}]}
    (folder / file_names("my star book", "English")[0]).write_text(json.dumps(written_by_hand), encoding="utf-8")
    result = rename_book(stores, OLD, NEW)
    assert result.sheets == 1
    moved = stores.sheets.list()
    assert [(e["series"], e["entries"]) for e in moved] == [("見本の物語", 1)]
    assert store_json(Path(moved[0]["file"]))["series"] == "見本の物語"


def test_the_stores_of_the_settings(tmp_path):
    settings = Settings(state_dir=tmp_path / "state")
    stores = Stores.of(settings)
    assert stores.cache.cache_dir == settings.cache_dir
    assert stores.annotations.annotations_dir == settings.annotations_dir
    assert stores.sheets.glossary_dir == settings.glossary_dir
