"""The export that takes everything to another computer of the reader's: a book's translations with its page
information and the series sheet it reads, several books in one file (a series, the whole library), and an import
that lists what a file holds, keeps the reader's corrections, page information and sheet values unless they take the
file's, and leaves a copy of every file it changes. Files of an earlier version (one cache alone) still import."""
from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("cryptography")

from taslation import backup  # noqa: E402
from taslation.annotations import (  # noqa: E402
    AnnotationStore, BookAnnotations, BookArea, CharacterSheet, Glossary, GlossaryStore,
)
from taslation.cache import BookCache, CacheStore, CachedBubble, CachedPage  # noqa: E402
from taslation.cli import main  # noqa: E402
from taslation.rename import Stores  # noqa: E402
from helpers import store_json  # noqa: E402

PASSPHRASE = "correct horse battery staple"
MODEL = "unusual-model:7b-test"
SERIES = "Lantern Quay"
VOL1, VOL2, OTHER = f"{SERIES} 1", f"{SERIES} 2", "Pebble Harbor 1"
FP_A, FP_B, FP_C, FP_D = "a" * 80, "b" * 80, "c" * 80, "d" * 80
BOX_1, BOX_2 = (0.1, 0.1, 0.3, 0.2), (0.5, 0.5, 0.7, 0.6)
PAGE_LINE = "ここは秘密の部屋だ"  # a line of the book: read from the page, never kept, so never in an export
TERM, NAME = "花子", "灯台守"  # Japanese the reader wrote into the series sheet: it holds them, so does an export


@pytest.fixture(autouse=True)
def _quicker_keys(monkeypatch):
    monkeypatch.setitem(backup.KDF, "n", 2 ** 14)


def _stores(root) -> Stores:
    return Stores(CacheStore(root / "cache"), AnnotationStore(root / "annotations"), GlossaryStore(root / "glossary"))


def _bubble(box, text: str, edited: bool = False) -> CachedBubble:
    return CachedBubble(box=box, text=text, edited=edited)


def _cache(stores: Stores, book: str, *pages: CachedPage, language: str = "English") -> BookCache:
    cache = stores.cache.open(book, MODEL, language)
    for page in pages:
        cache.add(page)
    cache.save()
    return cache


def _page(fp: str, *bubbles: CachedBubble, seq: int = -1) -> CachedPage:
    return CachedPage(fingerprint=fp, aspect=0.71, seq=seq, bubbles=list(bubbles))


def _marks(stores: Stores, book: str, speaker: str = "Hanako") -> BookAnnotations:
    ann = stores.annotations.open(book)
    ann.add_box(FP_A, 0.71, (0.8, 0.8, 0.9, 0.9), "ignore")
    ann.add_box(FP_A, 0.71, (0.2, 0.6, 0.3, 0.7), "add")
    ann.page(FP_A, 0.71).set_note(BOX_1, speaker=speaker, kind="shout", note="a pun on her name")
    ann.set_settings({"text_scale": 1.2, "detect_dark_bubbles": True})
    ann.reading_direction = "ltr"
    ann.add_area(BookArea.around((0.02, 0.95, 0.1, 0.99), "right", 0.71))
    ann.record_sequence(FP_A, 0.71)
    ann.record_sequence(FP_B, 0.71)
    ann.save()
    return ann


def _sheet(stores: Stores, series: str = SERIES, rendering: str = "Hanako", language: str = "English") -> Glossary:
    sheet = stores.sheets.open(series, language)
    sheet.set(TERM, rendering, "the heroine")
    sheet.set_character(CharacterSheet(name=NAME, rendering="the Lighthouse Keeper", pronoun="わし", role="mentor"))
    sheet.style.honorifics = "keep"
    sheet.save()
    return sheet


def _texts(cache: BookCache) -> dict[str, list[str]]:
    return {p.fingerprint: [b.text for b in p.bubbles] for p in cache.pages}


def _body(data: dict) -> dict:
    return {k: v for k, v in data.items() if k != "updated"}


def _strings(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*(_strings(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_strings(v) for v in value)) if value else set()
    return set()


def _payload(path) -> dict:
    return json.loads(backup.decrypt(path.read_bytes(), PASSPHRASE))


def _files(*folders) -> dict[str, bytes]:
    return {f"{folder.name}/{p.name}": p.read_bytes() for folder in folders if folder.is_dir() for p in folder.iterdir()}


# ------------------------------------------------------------------ the parts, there and back
def test_a_book_goes_with_its_page_information_and_its_series_sheet(tmp_path):
    home, laptop = _stores(tmp_path / "home"), _stores(tmp_path / "laptop")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Hello, Hanako!", edited=True)), _page(FP_B, _bubble(BOX_2, "Run!")))
    marks, sheet = _marks(home, VOL1), _sheet(home)
    out = tmp_path / "vol1.stcache"
    done = backup.export_books(home, [(VOL1, "English")], out, PASSPHRASE)
    assert (done.books, done.pages, done.annotations, done.sheets, done.left_out) == (1, 2, 1, 1, 0)
    assert backup.export_cache(home, VOL1, out, PASSPHRASE) == 2  # the one-book call: the same file

    opened = backup.open_export(out, PASSPHRASE)
    assert opened.version == 2
    (held,) = opened.held
    assert (held.book, held.language, held.pages, held.bubbles, held.corrections, held.annotations, held.sheet) == (
        VOL1, "English", 2, 2, 1, True, SERIES)
    result = backup.apply_import(laptop, opened)
    assert (result.added, result.replaced, result.kept, result.annotations_added, result.sheets_added) == (2, 0, 0, 1, 1)
    brought = laptop.cache.open(VOL1, MODEL)
    assert _texts(brought) == {FP_A: ["Hello, Hanako!"], FP_B: ["Run!"]}
    assert [b.edited for p in brought.pages for b in p.bubbles] == [True, False]  # a correction stays one
    there = laptop.annotations.open(VOL1)
    assert _body(there.to_json()) == _body(marks.to_json())  # regions, notes, settings, direction, areas, sequence
    assert there.reading_direction == "ltr" and there.settings == {"text_scale": 1.2, "detect_dark_bubbles": True}
    assert there.page(FP_A, 0.71).note_at(BOX_1).speaker == "Hanako"
    joined = laptop.sheets.open(SERIES, "English")
    assert _body(joined.to_json()) == _body(sheet.to_json())
    # saved as every file of the stores is: protected again on this computer, readable through the stores
    for path in (laptop.cache.path_for(VOL1), laptop.annotations.path_for(VOL1), laptop.sheets.path_for(SERIES)):
        assert not path.read_bytes().lstrip().startswith(b"{")
        assert store_json(path)["schema"] == 1


def test_a_cache_store_alone_exports_and_imports_the_caches_alone(tmp_path):
    home = _stores(tmp_path / "home")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Line")))
    _marks(home, VOL1)
    _sheet(home)
    out = tmp_path / "x.stcache"
    assert backup.export_cache(home.cache, VOL1, out, PASSPHRASE) == 1
    data = _payload(out)
    assert data["annotations"] == data["sheets"] == [] and set(data["books"][0]) == {"cache"}
    laptop = _stores(tmp_path / "laptop")
    backup.export_books(home, [(VOL1, "English")], out, PASSPHRASE)
    assert backup.import_cache(laptop.cache, out, PASSPHRASE) == (VOL1, 1)  # the caches alone
    assert not laptop.annotations.annotations_dir.exists() and not laptop.sheets.glossary_dir.exists()


def test_an_export_of_an_earlier_version_still_imports(tmp_path):
    """Version 1 of the payload: one cache file's JSON as it is (what TASlation wrote until 2026-11-16)."""
    home = _stores(tmp_path / "home")
    cache = _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "From before")))
    old = tmp_path / "old.stcache"
    old.write_bytes(backup.encrypt(json.dumps(cache.to_json(), ensure_ascii=False).encode("utf-8"), PASSPHRASE))
    opened = backup.open_export(old, PASSPHRASE)
    assert opened.version == 1 and [(h.book, h.pages, h.annotations, h.sheet) for h in opened.held] == [
        (VOL1, 1, False, "")]
    laptop = _stores(tmp_path / "laptop")
    assert backup.import_cache(laptop, old, PASSPHRASE) == (VOL1, 1)
    assert _texts(laptop.cache.open(VOL1, MODEL)) == {FP_A: ["From before"]}


def test_a_bundle_is_what_the_version_before_refuses_as_a_newer_one(tmp_path):
    """The version before reads the payload as a cache and refuses a ``schema`` above 1 with "the file holds the cache
    of a newer version of TASlation" (`UnreadableExport`); a bundle of a later version is refused so here."""
    home = _stores(tmp_path / "home")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Line")))
    out = tmp_path / "x.stcache"
    backup.export_cache(home, VOL1, out, PASSPHRASE)
    data = _payload(out)
    assert type(data["schema"]) is int and data["schema"] > 1 and "pages" not in data
    later = tmp_path / "later.stcache"
    later.write_bytes(backup.encrypt(json.dumps({**data, "schema": 3}).encode("utf-8"), PASSPHRASE))
    with pytest.raises(backup.UnreadableExport, match="newer version"):
        backup.open_export(later, PASSPHRASE)


# ------------------------------------------------------------------ the reader's own, kept
def test_the_readers_corrections_stay_unless_the_file_is_taken_as_it_is(tmp_path):
    home, laptop = _stores(tmp_path / "home"), _stores(tmp_path / "laptop")
    _cache(home, VOL1,
           _page(FP_A, _bubble(BOX_1, "Machine line A"), _bubble(BOX_2, "Machine line B")),
           _page(FP_B, _bubble(BOX_1, "Their correction", edited=True)),
           _page(FP_C, _bubble(BOX_2, "Only a second line here")),
           _page(FP_D, _bubble(BOX_1, "A new page")))
    out = tmp_path / "x.stcache"
    backup.export_cache(home, VOL1, out, PASSPHRASE)
    _cache(laptop, VOL1,
           _page(FP_A, _bubble(BOX_1, "My correction A", edited=True), _bubble(BOX_2, "Machine line B")),
           _page(FP_B, _bubble(BOX_1, "My correction B", edited=True)),
           _page(FP_C, _bubble(BOX_1, "My line the file lacks", edited=True)))
    before = laptop.cache.path_for(VOL1).read_bytes()
    opened = backup.open_export(out, PASSPHRASE)
    plan = backup.plan_import(laptop, opened)
    (book,) = plan.books
    assert book.exists and (book.added, book.replaced, book.kept, book.replaced_as_is) == (1, 2, 2, 3)
    assert laptop.cache.path_for(VOL1).read_bytes() == before  # a plan writes nothing

    result = backup.apply_import(laptop, opened)
    assert (result.added, result.replaced, result.kept) == (1, 2, 2)  # FP_A stays as it is here
    merged = laptop.cache.open(VOL1, MODEL)
    assert _texts(merged) == {
        FP_A: ["My correction A", "Machine line B"],  # mine, where the file's line is the model's
        FP_B: ["Their correction"],  # a person's on both computers: the file's
        FP_C: ["Only a second line here", "My line the file lacks"],  # the file has no line there: mine is added
        FP_D: ["A new page"]}
    assert [b.edited for b in merged.pages[0].bubbles] == [True, False]

    result = backup.apply_import(laptop, backup.open_export(out, PASSPHRASE), keep_corrections=False)
    assert result.kept == 0 and result.replaced == 2  # the corrections kept the first time go now
    assert _texts(laptop.cache.open(VOL1, MODEL)) == {
        FP_A: ["Machine line A", "Machine line B"], FP_B: ["Their correction"], FP_C: ["Only a second line here"],
        FP_D: ["A new page"]}
    copies = sorted(laptop.cache.cache_dir.glob("*.before-import.*.json"))
    assert copies and copies[0].read_bytes() == before


def test_page_information_here_is_kept_unless_the_file_is_taken(tmp_path, monkeypatch):
    real_strftime = time.strftime
    monkeypatch.setattr(time, "strftime", lambda fmt, *a: real_strftime(fmt.replace("%H%M%S", "120000"), *a))
    home, laptop = _stores(tmp_path / "home"), _stores(tmp_path / "laptop")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Line")))
    theirs = _marks(home, VOL1, speaker="Hanako")
    out = tmp_path / "x.stcache"
    backup.export_cache(home, VOL1, out, PASSPHRASE)
    mine = _marks(laptop, VOL1, speaker="The Keeper")  # my own here, not the file's
    mine_bytes = laptop.annotations.path_for(VOL1).read_bytes()
    plan = backup.plan_import(laptop, backup.open_export(out, PASSPHRASE))
    assert [(m.book, m.state) for m in plan.annotations] == [(VOL1, "differs")] and plan.differing
    result = backup.apply_import(laptop, backup.open_export(out, PASSPHRASE))  # by default: mine stays
    assert (result.annotations_kept, result.annotations_taken) == (1, 0)
    assert laptop.annotations.path_for(VOL1).read_bytes() == mine_bytes
    result = backup.apply_import(laptop, backup.open_export(out, PASSPHRASE), take_annotations=True)
    assert result.annotations_taken == 1
    assert _body(laptop.annotations.open(VOL1).to_json()) == _body(theirs.to_json())
    (copy,) = laptop.annotations.annotations_dir.glob("*.before-import.*.json")
    assert copy.read_bytes() == mine_bytes  # what was mine, kept beside
    assert [a["book"] for a in laptop.annotations.list()] == [VOL1]  # a copy is no book's file of its own
    plan = backup.plan_import(laptop, backup.open_export(out, PASSPHRASE))
    assert [m.state for m in plan.annotations] == ["same"]  # as the file has it now: nothing to ask
    assert mine.book == VOL1


def test_the_series_sheet_joins_the_one_here_as_a_rename_joins_them(tmp_path):
    home, laptop = _stores(tmp_path / "home"), _stores(tmp_path / "laptop")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Line")))
    theirs = _sheet(home, rendering="Hana")
    theirs.set("港", "the Quay")  # what the sheet here lacks
    theirs.save()
    out = tmp_path / "x.stcache"
    backup.export_cache(home, VOL1, out, PASSPHRASE)
    _sheet(laptop, rendering="Hanako")  # here the heroine is spelt otherwise
    before = laptop.sheets.path_for(SERIES).read_bytes()
    opened = backup.open_export(out, PASSPHRASE)
    plan = backup.plan_import(laptop, opened)
    (sheet,) = plan.sheets
    assert sheet.state == "join" and sheet.review.terms == 1
    ((key, _sheet_plan, conflict),) = plan.keyed()
    assert (conflict.area, conflict.key, conflict.mine, conflict.theirs) == ("term", TERM, ("Hanako", "the heroine"),
                                                                             ("Hana", "the heroine"))
    assert key == (SERIES, "english", "term", TERM, "", "")
    result = backup.apply_import(laptop, opened)  # no answer: the sheet here keeps its value
    assert (result.sheets_joined, result.sheet_terms, result.sheet_taken, result.sheet_kept) == (1, 1, 0, 1)
    here = laptop.sheets.open(SERIES, "English")
    assert here.get(TERM).rendering == "Hanako" and here.get("港").rendering == "the Quay"
    (copy,) = laptop.sheets.glossary_dir.glob("*.before-import.*.json")
    assert copy.read_bytes() == before
    result = backup.apply_import(laptop, backup.open_export(out, PASSPHRASE), answers={key: True})
    assert result.sheet_taken == 1 and laptop.sheets.open(SERIES, "English").get(TERM).rendering == "Hana"
    assert [s["series"] for s in laptop.sheets.list()] == [SERIES]


# ------------------------------------------------------------------ several books in one file
def test_a_series_and_the_whole_library_in_one_file_and_an_import_of_some_of_it(tmp_path):
    home, laptop = _stores(tmp_path / "home"), _stores(tmp_path / "laptop")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Volume one")))
    _cache(home, VOL2, _page(FP_B, _bubble(BOX_1, "Volume two")), _page(FP_C, _bubble(BOX_1, "And more")))
    _cache(home, VOL2, _page(FP_B, _bubble(BOX_1, "Tome deux")), language="French")
    _cache(home, OTHER, _page(FP_D, _bubble(BOX_1, "Another series")))
    _marks(home, VOL1)
    _sheet(home)
    _sheet(home, language="French", rendering="Hanako-fr")
    out = tmp_path / "library.stcache"
    everything = [(b["book"], b["language"]) for b in home.cache.list()]
    done = backup.export_books(home, everything, out, PASSPHRASE)
    assert (done.books, done.pages, done.annotations, done.sheets) == (4, 5, 1, 2)
    data = _payload(out)
    sheets = [(s["series"], s["language"]) for s in data["sheets"]]
    assert sorted(sheets) == [(SERIES, "English"), (SERIES, "French")]  # one per series and language, shared
    assert [e.get("sheet") for e in data["books"]].count(sheets.index((SERIES, "English"))) == 2

    opened = backup.open_export(out, PASSPHRASE)
    assert sorted((h.book, h.language, h.pages) for h in opened.held) == [
        (VOL1, "English", 1), (VOL2, "English", 2), (VOL2, "French", 1), (OTHER, "English", 1)]
    chosen = [h.index for h in opened.held if h.book == VOL2 and h.language == "English"]
    plan = backup.plan_import(laptop, opened, chosen)
    assert [b.held.book for b in plan.books] == [VOL2] and not plan.annotations and len(plan.sheets) == 1
    assert backup.plan_import(laptop, opened).only(chosen).books[0].held.book == VOL2
    backup.apply_import(laptop, opened, chosen)
    assert [(b["book"], b["language"]) for b in laptop.cache.list()] == [(VOL2, "English")]
    assert [(s["series"], s["language"]) for s in laptop.sheets.list()] == [(SERIES, "English")]
    assert not laptop.annotations.list()  # volume 1's page information stays in the file
    backup.apply_import(laptop, backup.open_export(out, PASSPHRASE))
    assert len(laptop.cache.list()) == 4 and [a["book"] for a in laptop.annotations.list()] == [VOL1]


def test_the_caps_of_one_file(tmp_path, monkeypatch):
    home, laptop = _stores(tmp_path / "home"), _stores(tmp_path / "laptop")
    for book in (VOL1, VOL2, OTHER):
        _cache(home, book, _page(FP_A, _bubble(BOX_1, "Line")), _page(FP_B, _bubble(BOX_2, "Line")))
    books = [(b["book"], b["language"]) for b in home.cache.list()]
    out = tmp_path / "x.stcache"
    backup.export_books(home, books, out, PASSPHRASE)
    for name, cap, said in (("MAX_BOOKS", 2, "more than 2 books"), ("MAX_TOTAL_PAGES", 5, "more than 5 pages")):
        with monkeypatch.context() as m:
            m.setattr(backup, name, cap)
            with pytest.raises(backup.TooLarge, match=said):
                backup.export_books(home, books, tmp_path / "y.stcache", PASSPHRASE)
            assert not (tmp_path / "y.stcache").exists()
            with pytest.raises(backup.TooLarge, match="nothing was imported"):
                backup.open_export(out, PASSPHRASE)
    with monkeypatch.context() as m:
        m.setattr(backup, "MAX_PAYLOAD", 2000)
        with pytest.raises(backup.TooLarge, match="export fewer at a time"):
            backup.export_books(home, books, tmp_path / "y.stcache", PASSPHRASE)
    backup.apply_import(laptop, backup.open_export(out, PASSPHRASE))
    assert len(laptop.cache.list()) == 3


# ------------------------------------------------------------------ nothing of the page, nothing hostile
def test_the_file_holds_nothing_the_saved_files_do_not(tmp_path):
    """No line read from a page is ever kept, so none is in an export: what the decrypted payload holds is what the
    source files hold (their own strings: translations, the reader's notes and speakers, the sheet's Japanese terms
    as the reader wrote them), and the payload's own few words."""
    home = _stores(tmp_path / "home")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "This is the secret room.", edited=True)))
    _marks(home, VOL1)
    _sheet(home)
    out = tmp_path / "x.stcache"
    backup.export_cache(home, VOL1, out, PASSPHRASE)
    payload = backup.decrypt(out.read_bytes(), PASSPHRASE).decode("utf-8")
    assert PAGE_LINE not in payload and json.dumps(PAGE_LINE) not in payload
    sources = set()
    for path in (home.cache.path_for(VOL1), home.annotations.path_for(VOL1), home.sheets.path_for(SERIES)):
        sources |= _strings(store_json(path))
    found = _strings(json.loads(payload))
    assert found - sources == {"taslation", "export", backup.PAYLOAD_NOTE} - sources
    assert {TERM, NAME, "わし", "Hanako", "a pun on her name", "This is the secret room."} <= found


def _sealed(tmp_path, payload: dict):
    path = tmp_path / "crafted.stcache"
    path.write_bytes(backup.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"), PASSPHRASE))
    return path


CACHE = {"schema": 1, "book": VOL1, "model": MODEL, "language": "English",
         "pages": [{"fp": FP_B, "aspect": 0.7, "seq": 0, "bubbles": [{"box": [0.1, 0.1, 0.2, 0.2], "text": "Theirs"}]}]}
MARKS = {"schema": 1, "kind": "annotations", "book": VOL1, "pages": [], "settings": {}, "sequence": [],
         "reading_direction": "rtl"}
SHEET = {"schema": 1, "kind": "glossary", "series": SERIES, "language": "English", "entries": [], "characters": [],
         "style": {"honorifics": "keep"}}


def _bundle(*books, marks=(MARKS,), sheets=(SHEET,)) -> dict:
    return {"schema": 2, "books": list(books), "annotations": list(marks), "sheets": list(sheets)}


@pytest.mark.parametrize("payload", [
    pytest.param(_bundle(), id="no-book"),
    pytest.param(_bundle({"cache": CACHE, "annotations": 1}), id="no-such-page-information"),
    pytest.param(_bundle({"cache": CACHE, "sheet": True}), id="a-sheet-index-not-a-number"),
    pytest.param(_bundle({"cache": CACHE, "annotations": 0}, marks=({**MARKS, "book": OTHER},)),
                 id="another-books-page-information"),
    pytest.param(_bundle({"cache": CACHE, "sheet": 0}, sheets=({**SHEET, "language": "French"},)),
                 id="a-sheet-of-another-language"),
    pytest.param(_bundle({"cache": CACHE}, {"cache": CACHE}), id="a-book-twice"),
    pytest.param(_bundle({"cache": CACHE, "annotations": 0},
                         marks=({**MARKS, "pages": [{"fp": FP_A, "aspect": float("nan"), "add": [], "ignore": []}]},)),
                 id="a-number-not-finite"),
    pytest.param(_bundle({"cache": CACHE}, marks=({**MARKS, "kind": "glossary"},)), id="page-information-of-another-kind"),
    pytest.param(_bundle({"cache": CACHE}, sheets=({**SHEET, "series": " \x1b "},)), id="a-sheet-of-no-series"),
    pytest.param(_bundle({"cache": CACHE}, marks=({**MARKS, "pages": {"0": {}}},)), id="pages-not-a-list"),
    pytest.param(_bundle({"cache": {**CACHE, "schema": 2}}), id="a-cache-of-a-newer-version"),
    pytest.param(_bundle({"cache": CACHE}, marks=({**MARKS, "schema": 2},)), id="page-information-of-a-newer-version"),
    pytest.param({"schema": 2, "books": "all"}, id="books-not-a-list"),
])
def test_hostile_bundles_are_refused_and_nothing_is_written(tmp_path, payload):
    laptop = _stores(tmp_path / "laptop")
    _cache(laptop, VOL1, _page(FP_A, _bubble(BOX_1, "Mine")))
    _marks(laptop, VOL1)
    _sheet(laptop)
    folders = (laptop.cache.cache_dir, laptop.annotations.annotations_dir, laptop.sheets.glossary_dir)
    before = _files(*folders)
    with pytest.raises(backup.BackupError):
        backup.import_cache(laptop, _sealed(tmp_path, payload), PASSPHRASE)
    assert _files(*folders) == before


def test_control_characters_in_page_information_and_sheets_are_dropped(tmp_path):
    evil = "\x1b]0;owned\x07\x9b"
    payload = _bundle({"cache": CACHE, "annotations": 0, "sheet": 0},
                      marks=({**MARKS, "settings": {"erase_mode": "outline" + evil}},),
                      sheets=({**SHEET, "series": SERIES + evil, "entries": [{"term": TERM + evil, "rendering": "H"}]},))
    laptop = _stores(tmp_path / "laptop")
    backup.import_cache(laptop, _sealed(tmp_path, payload), PASSPHRASE)
    assert laptop.annotations.open(VOL1).settings == {"erase_mode": "outline]0;owned"}
    (listed,) = laptop.sheets.list()
    assert listed["series"] == SERIES + "]0;owned" and laptop.sheets.open(listed["series"]).get(TERM + "]0;owned")


def test_a_file_that_cannot_be_read_here_is_left_out_and_counted(tmp_path):
    home = _stores(tmp_path / "home")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Line")))
    _sheet(home)
    home.annotations.annotations_dir.mkdir(parents=True)
    home.annotations.path_for(VOL1).write_bytes(b"not a file of page information")
    out = tmp_path / "x.stcache"
    done = backup.export_books(home, [(VOL1, "English")], out, PASSPHRASE)
    assert (done.annotations, done.sheets, done.left_out) == (0, 1, 1)
    assert home.annotations.path_for(VOL1).read_bytes() == b"not a file of page information"  # never set aside


def test_an_import_never_writes_into_another_series_sheet(tmp_path, monkeypatch):
    """Both file names of the series' sheet hold other series (two names with one hash, made so here): refused before
    anything is written, as for a cache."""
    from taslation import names

    home = _stores(tmp_path / "home")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Line")))
    _sheet(home, series="Pebble Harbor")
    home_sheet = home.sheets
    monkeypatch.setattr("taslation.notes.sheet_key", lambda sheets, book: "Pebble Harbor")
    out = tmp_path / "x.stcache"
    assert backup.export_books(home, [(VOL1, "English")], out, PASSPHRASE).sheets == 1
    monkeypatch.undo()
    laptop = _stores(tmp_path / "laptop")
    monkeypatch.setattr(names, "name_hash", lambda _name: "00000000")
    _sheet(laptop, series="Pebble:Harbor")
    _sheet(laptop, series="Pebble?Harbor")
    folders = (laptop.cache.cache_dir, laptop.sheets.glossary_dir)
    before = _files(*folders)
    with pytest.raises(backup.NameClash):
        backup.import_cache(laptop, out, PASSPHRASE)
    assert _files(*folders) == before and home_sheet


# ------------------------------------------------------------------ the command line
@pytest.fixture
def cli(tmp_path, monkeypatch):
    from taslation import netguard

    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(backup.PASSPHRASE_ENV, PASSPHRASE)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: pytest.fail("asked for a passphrase"))
    yield tmp_path
    netguard.uninstall()


def test_the_commands_export_a_series_or_everything_and_import_some_of_it(cli, monkeypatch, capsys):
    home = _stores(cli / "state")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Volume one")))
    _cache(home, VOL2, _page(FP_B, _bubble(BOX_1, "Volume two")))
    _cache(home, VOL2, _page(FP_B, _bubble(BOX_1, "Tome deux")), language="French")
    _cache(home, OTHER, _page(FP_C, _bubble(BOX_1, "Another")))
    _marks(home, VOL1)
    _sheet(home)
    series, everything = cli / "series.stcache", cli / "all.stcache"
    assert main(["cache", "export", "--series", SERIES, "--out", str(series)]) == 0
    line = capsys.readouterr().out.strip()
    assert line == (f"exported 2 book(s): 2 page(s) with 1 book(s) of page information and 1 series sheet(s) to "
                    f"{series}")
    assert sorted(h.book for h in backup.open_export(series, PASSPHRASE).held) == [VOL1, VOL2]
    assert main(["cache", "export", "--all", "--out", str(everything)]) == 0
    assert "exported 4 book(s): 4 page(s)" in capsys.readouterr().out
    assert main(["cache", "export", VOL1, "--out", str(cli / "one.stcache")]) == 0
    assert capsys.readouterr().out.strip() == (f"exported {VOL1!r}: 1 page(s) with its page information and its "
                                               f"series sheet to {cli / 'one.stcache'}")
    for argv, said in ((["cache", "export", VOL1, "--all", "--out", str(cli / "z.stcache")], "--series NAME or --all"),
                       (["cache", "export", "--series", "Nothing Here", "--out", str(cli / "z.stcache")],
                        "no cached volume of the series 'Nothing Here'")):
        with pytest.raises(SystemExit, match=said):
            main(argv)

    monkeypatch.setenv("TASLATION_STATE_DIR", str(cli / "laptop"))  # the reader's other computer
    assert main(["cache", "import", str(everything), "--list"]) == 0
    listed = capsys.readouterr().out.strip().splitlines()
    assert len(listed) == 4 and f"{VOL1!r} in English: 1 page(s), 1 bubble(s), with its page information, with the " \
                                f"series sheet of {SERIES!r}" in listed
    assert not (cli / "laptop" / "cache").exists()  # a list writes nothing
    assert main(["cache", "import", str(everything), "--book", VOL2]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert sorted(lines[:2]) == [f"imported 1 page(s) into {VOL2!r} in English (merged: 1 added, 0 replaced, 0 of your correction(s) "
                     f"kept) from {everything}",
                     f"imported 1 page(s) into {VOL2!r} in French (merged: 1 added, 0 replaced, 0 of your correction(s) "
                     f"kept) from {everything}"]
    assert lines[2:] == ["series sheets: 1 added, 0 joined yours (0 item(s) added, 0 taken from the file, 0 kept as "
                         "yours)"]
    laptop = _stores(cli / "laptop")
    assert sorted((b["book"], b["language"]) for b in laptop.cache.list()) == [(VOL2, "English"), (VOL2, "French")]
    with pytest.raises(SystemExit, match="holds no book 'Nothing'"):
        main(["cache", "import", str(everything), "--book", "Nothing"])


def test_the_command_keeps_yours_unless_told_to_take_the_file(cli, monkeypatch, capsys):
    home = _stores(cli / "home")
    _cache(home, VOL1, _page(FP_A, _bubble(BOX_1, "Theirs")))
    _marks(home, VOL1, speaker="Hanako")
    _sheet(home, rendering="Hana")
    out = cli / "x.stcache"
    backup.export_cache(home, VOL1, out, PASSPHRASE)
    here = _stores(cli / "state")
    _cache(here, VOL1, _page(FP_A, _bubble(BOX_1, "Mine", edited=True)))
    _marks(here, VOL1, speaker="The Keeper")
    _sheet(here, rendering="Hanako")
    assert main(["cache", "import", str(out)]) == 0
    captured = capsys.readouterr()
    assert "keeps 1 of your correction(s)" in captured.err and "yours stays (--take-file" in captured.err
    assert "kept as yours (--take-file takes the file's)" in captured.out
    assert _texts(here.cache.open(VOL1, MODEL)) == {FP_A: ["Mine"]}
    assert here.annotations.open(VOL1).page(FP_A, 0.71).note_at(BOX_1).speaker == "The Keeper"
    assert here.sheets.open(SERIES).get(TERM).rendering == "Hanako"
    assert main(["cache", "import", str(out), "--take-file"]) == 0
    assert "1 taken from the file" in capsys.readouterr().out
    assert _texts(here.cache.open(VOL1, MODEL)) == {FP_A: ["Theirs"]}
    assert here.annotations.open(VOL1).page(FP_A, 0.71).note_at(BOX_1).speaker == "Hanako"
    assert here.sheets.open(SERIES).get(TERM).rendering == "Hana"
