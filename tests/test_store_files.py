"""One file per exact name in the reader's other stores too (annotations, series sheet), as in
the cache: two names that give one file name (punctuation, letter case on Windows, the 120-character cut, an
all-symbol title) get a file each, the first keeping the plain name; deleting one leaves the other, and a delete
never takes the files of another name, not even one that only starts the same ("Pennant" for "Pe").

In every store, the cache included, a file that cannot be read (damaged, of another kind, or written by a newer
TASlation) is never written over: it is kept beside as <stem>.unreadable-<date>.json, one line on stderr says so
without anything the file holds, and a fresh one is started; such copies are no store's files, and go with their
name's files when it is deleted."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest

from taslation import cache as cache_module
from taslation import names
from taslation.annotations import AnnotationStore, GlossaryStore
from taslation.cache import CacheStore, CachedBubble, CachedPage
from taslation.names import file_names

LONG = "x" * 125  # past the 120 characters a file name keeps
SECRET = "LINE-OF-THE-BOOK"  # stands for what a file holds: never on stderr
COPY = re.compile(r".+\.unreadable-[0-9]{8}-[0-9]{6}(?:-[0-9]+)?\.json")


class Annotations:
    """The reader's annotations: one file per book, no languages; a mark is a page (its fingerprint)."""

    languages, name_field, list_field, kind = False, "book", "pages", "annotations"

    def __init__(self, folder):
        self.store = AnnotationStore(folder)

    def open(self, name, language="English"):
        return self.store.open(name)

    @staticmethod
    def mark(obj, mark):
        obj.add_box(mark * 80, 0.7, (0.1, 0.1, 0.3, 0.2), "add")

    def marks(self, name, language="English"):
        return {p.fingerprint[0] for p in self.store.open(name).pages}

    def path_for(self, name, language="English"):
        return self.store.path_for(name)

    def file_names(self, name, language="English"):
        return file_names(name, None)

    def listed(self):
        return sorted((e["book"], os.path.basename(e["file"])) for e in self.store.list())

    @staticmethod
    def raw(mark):
        """A file that records no book (written by hand, say)."""
        return {"schema": 1, "kind": "annotations",
                "pages": [{"fp": mark * 80, "aspect": 0.7, "add": [[0.1, 0.1, 0.3, 0.2]], "ignore": []}]}

    def save(self, name, mark, language="English"):
        obj = self.open(name, language)
        self.mark(obj, mark)
        obj.save()
        return obj.path

    def delete(self, name):
        return self.store.delete(name)

    def unreadable(self, how, name, language="English"):
        """The text of a file of *name* this version cannot read, *how*: not JSON, not a JSON object, a JSON object
        of the wrong structure (its list a number), of another kind, or of a newer schema; each holds SECRET."""
        if how == "not-json":  # cut short
            return json.dumps({"schema": 1, self.name_field: name, "note": SECRET, self.list_field: []})[:-9]
        if how == "not-object":
            return json.dumps([SECRET, name])
        data = {"schema": 2 if how == "newer" else 1, self.name_field: name, "note": SECRET, self.list_field: []}
        if self.languages:
            data["language"] = language
        if self.kind:
            data["kind"] = "taslation-premises" if how == "another-kind" else self.kind
        if how == "wrong-structure":
            data[self.list_field] = 5
        return json.dumps(data)


class Sheets(Annotations):
    """The series sheet: one file per series and language; a mark is a glossary entry's rendering."""

    languages, name_field, list_field, kind = True, "series", "entries", "glossary"

    def __init__(self, folder):
        self.store = GlossaryStore(folder)

    def open(self, name, language="English"):
        return self.store.open(name, language)

    @staticmethod
    def mark(obj, mark):
        obj.set("用語" + mark, mark)

    def marks(self, name, language="English"):
        return {e.rendering for e in self.store.open(name, language).entries}

    def path_for(self, name, language="English"):
        return self.store.path_for(name, language)

    def file_names(self, name, language="English"):
        return file_names(name, language)

    def listed(self):
        return sorted((e["series"], os.path.basename(e["file"])) for e in self.store.list())

    @staticmethod
    def raw(mark):
        return {"schema": 1, "kind": "glossary", "entries": [{"term": "用語" + mark, "rendering": mark}]}


class Caches(Sheets):
    """The translation cache: one file per book and language; a mark is a page (its fingerprint, so a hex digit)."""

    name_field, list_field, kind = "book", "pages", None

    def __init__(self, folder):
        self.store = CacheStore(folder)

    def open(self, name, language="English"):
        return self.store.open(name, "m", language)

    @staticmethod
    def mark(obj, mark):
        obj.add(CachedPage(fingerprint=mark * 80, aspect=0.7, bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text="")],
                           seq=-1))

    def marks(self, name, language="English"):
        return {p.fingerprint[0] for p in self.open(name, language).pages}

    def listed(self):
        return sorted((e["book"], os.path.basename(e["file"])) for e in self.store.list())


STORES = [pytest.param(Annotations, id="annotations"), pytest.param(Sheets, id="sheet")]
IN_LANGUAGES = [pytest.param(Annotations, "English", id="annotations"),
                pytest.param(Sheets, "English", id="sheet"), pytest.param(Sheets, "German", id="sheet-German")]
WITH_THE_CACHE = [*IN_LANGUAGES, pytest.param(Caches, "English", id="cache"),
                  pytest.param(Caches, "German", id="cache-German")]


def _ignores_case(folder) -> bool:
    """True on a file system that ignores letter case (Windows, macOS)."""
    probe = folder / "Case-Probe.txt"
    probe.write_text("x", encoding="utf-8")
    try:
        return (folder / "case-probe.txt").exists()
    finally:
        probe.unlink()


@pytest.mark.parametrize("first, second", [
    ("Pebble:Harbor 1", "Pebble Harbor 1"), ("QUILLPOND 1", "Quillpond 1"), (LONG + " vol 1", LONG + " vol 2"), ("!!!", "???"),
], ids=["punctuation", "letter-case", "cut", "all-symbols"])
@pytest.mark.parametrize("kind, language", IN_LANGUAGES)
def test_names_that_give_one_file_name_get_a_file_each(tmp_path_factory, kind, language, first, second):
    """The first name keeps the plain file name, the second gets it with its name's hash; each reads its own data
    only, the list shows both, and deleting one leaves the other."""
    folder = tmp_path_factory.mktemp("s")  # a short folder: 120 characters of name and the hash fit
    store = kind(folder)
    a, b = store.save(first, "a", language), store.save(second, "b", language)
    plain, hashed = store.file_names(second, language)
    mine = store.file_names(first, language)[0]
    shared = mine == plain or (_ignores_case(folder) and mine.lower() == plain.lower())
    assert a.name == mine and b.name == (hashed if shared else plain) and a != b
    assert store.marks(first, language) == {"a"} and store.marks(second, language) == {"b"}
    assert store.listed() == sorted([(first, a.name), (second, b.name)])
    assert store.delete(second)
    assert not b.exists() and store.listed() == [(first, a.name)] and store.marks(first, language) == {"a"}


@pytest.mark.parametrize("kind, language", IN_LANGUAGES)
def test_the_hashed_file_survives_the_deletion_of_the_plain_one(tmp_path, kind, language):
    """Deleting the name that had the plain file never sends the other back to it (its data is where it is), and a
    third name that gives the same file name takes the free plain name."""
    store = kind(tmp_path)
    store.save("Pebble:Harbor 1", "a", language)
    second = store.save("Pebble Harbor 1", "b", language)
    assert second.name == store.file_names("Pebble Harbor 1", language)[1]
    assert store.delete("Pebble:Harbor 1") and not (tmp_path / store.file_names("Pebble:Harbor 1", language)[0]).exists()
    assert store.path_for("Pebble Harbor 1", language) == second and store.marks("Pebble Harbor 1", language) == {"b"}
    assert store.save("Pebble Harbor 1", "c", language) == second
    third = store.save("Pebble_Harbor 1", "d", language)
    assert third.name == store.file_names("Pebble_Harbor 1", language)[0]
    assert [name for name, _file in store.listed()] == ["Pebble Harbor 1", "Pebble_Harbor 1"]
    assert store.marks("Pebble Harbor 1", language) == {"b", "c"} and store.marks("Pebble_Harbor 1", language) == {"d"}


@pytest.mark.parametrize("kind", STORES)
def test_delete_takes_only_the_names_own_files(tmp_path, kind):
    """Deleting "Pe" used to delete every file whose name starts with "Pe": the files of "Pennant" and "Pe Harbor"
    too. Now only the files that record "Pe" go (in every language), with what a stopped save left beside them; a
    file that cannot be read goes only under one of the name's own file names."""
    store = kind(tmp_path)
    for name in ("Pe", "Pennant", "Pe Harbor"):
        store.save(name, "a")
    if kind.languages:
        store.save("Pe", "b", "German")
    unreadable = '{"schema": 1, "' + kind.name_field + '": "Pe'  # cut short: whose it is cannot be read
    for name in (store.file_names("Pe")[1], "Pe.french.json", "Pe_old.json", "Pennant.german.json"):
        (tmp_path / name).write_text(unreadable, encoding="utf-8")
    for name in ("Pe.json.k3j5h2.tmp", "Pennant.json.q8r7s6.tmp"):  # what saves that stopped halfway left
        (tmp_path / name).write_text(unreadable, encoding="utf-8")
    assert store.delete("Pe") and not store.delete("Pe")
    kept = ["Pe_Harbor.json", "Pe_old.json", "Pennant.german.json", "Pennant.json", "Pennant.json.q8r7s6.tmp"]
    if not kind.languages:  # no language part in this store's file names: not one of the book's own
        kept.append("Pe.french.json")
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(kept)
    assert store.marks("Pennant") == {"a"} and store.marks("Pe Harbor") == {"a"} and store.marks("Pe") == set()


@pytest.mark.parametrize("kind", STORES)
def test_a_file_that_records_no_name_belongs_to_the_first_that_opens_it(tmp_path, kind):
    """Every file these stores write records its name; one that does not (written by hand) is the file of the first
    name that opens it under its file name, which the next save records in it. Another name with that file name
    then gets a file of its own."""
    store = kind(tmp_path)
    plain = tmp_path / store.file_names("Pebble:Harbor 1")[0]
    plain.write_text(json.dumps(store.raw("e")), encoding="utf-8")
    assert store.path_for("Pebble:Harbor 1") == plain and store.marks("Pebble:Harbor 1") == {"e"}
    assert store.save("Pebble:Harbor 1", "a") == plain
    assert json.loads(plain.read_text(encoding="utf-8"))[kind.name_field] == "Pebble:Harbor 1"
    other = store.save("Pebble Harbor 1", "b")
    assert other.name == store.file_names("Pebble Harbor 1")[1]
    assert store.marks("Pebble:Harbor 1") == {"a", "e"} and store.marks("Pebble Harbor 1") == {"b"}


@pytest.mark.parametrize("kind", [pytest.param(Annotations, id="annotations"), pytest.param(Sheets, id="sheet")])
def test_two_names_opened_before_either_was_saved(tmp_path, kind):
    """Opened while the file was free (the app and a batch run), both start on the plain name: the later save finds
    the other name there and moves to its own file instead of writing over it."""
    store = kind(tmp_path)
    first, second = store.open("Pebble:Harbor 1"), store.open("Pebble Harbor 1")
    assert first.path == second.path
    for obj, mark in ((first, "a"), (second, "b"), (first, "c"), (second, "d")):
        store.mark(obj, mark)
        obj.save()
    assert first.path.name == store.file_names("Pebble:Harbor 1")[0] and second.path.name == store.file_names("Pebble Harbor 1")[1]
    assert store.marks("Pebble:Harbor 1") == {"a", "c"} and store.marks("Pebble Harbor 1") == {"b", "d"}


@pytest.mark.parametrize("kind", STORES)
def test_a_file_of_another_name_is_never_read_or_written_as_this_ones(tmp_path, kind, monkeypatch):
    """Had another process written the file between path_for and the read, it is never taken for this name's."""
    store = kind(tmp_path)
    mine = store.save("Pebble:Harbor 1", "a")
    before = mine.read_bytes()
    monkeypatch.setattr(type(store.store), "path_for", lambda self, name, language="English": mine)
    with pytest.raises(FileExistsError, match="holds the .* of 'Pebble:Harbor 1', not that of 'Pebble Harbor 1'"):
        store.save("Pebble Harbor 1", "b")
    assert mine.read_bytes() == before


@pytest.mark.parametrize("kind", STORES)
def test_two_names_with_one_hash_are_refused(tmp_path, kind, monkeypatch):
    """Both file names a name can have hold other names only for two names with the same hash (made so here)."""
    monkeypatch.setattr(names, "name_hash", lambda _name: "00000000")
    store = kind(tmp_path)
    store.save("Pebble:Harbor 1", "a")
    assert store.save("Pebble?Harbor 1", "b").name == "Pebble_Harbor_1-00000000.json"
    with pytest.raises(FileExistsError, match=r"'Pebble:Harbor 1'.*'Pebble\?Harbor 1'"):
        store.path_for("Pebble Harbor 1")
    assert store.marks("Pebble:Harbor 1") == {"a"} and store.marks("Pebble?Harbor 1") == {"b"}  # the two that have files go on


# --- a file a store cannot read ---------------------------------------------------------------------------------

def _copies(folder) -> dict[str, str]:
    """The copies set aside in *folder*, by name, with what they hold."""
    return {p.name: p.read_text(encoding="utf-8") for p in folder.iterdir() if COPY.fullmatch(p.name)}


def _same_second(monkeypatch) -> None:
    """Every copy is dated 2026-10-30 12:00:00, as two set aside within one second are."""
    real = time.strftime

    def strftime(fmt, *args):
        return "20261030-120000" if fmt == "%Y%m%d-%H%M%S" else real(fmt, *args)

    monkeypatch.setattr(time, "strftime", strftime)


DAMAGE = [("not-json", "damaged: not JSON"), ("not-object", "damaged: not a JSON object"),
          ("wrong-structure", names.DAMAGED), ("another-kind", "another kind of file"), ("newer", names.NEWER)]


def _damage_cases():
    """Each store with each way a file of it cannot be read, and the reason given; another kind only in the stores
    whose files say their kind."""
    for store in WITH_THE_CACHE:
        kind, language = store.values
        for how, reason in DAMAGE:
            if how == "another-kind" and not kind.kind:
                continue
            if how == "wrong-structure" and kind is Caches:
                reason = "damaged: no list of pages"
            yield pytest.param(kind, language, how, reason, id=f"{store.id}-{how}")


@pytest.mark.parametrize("kind, language, how, reason", list(_damage_cases()))
def test_a_file_that_cannot_be_read_is_kept_and_a_fresh_one_started(tmp_path, capsys, kind, language, how, reason):
    """It used to be replaced by a fresh one at the next save: a translator's hand corrections, minutes of model
    time. Now it is moved aside before anything is written, one line on stderr says where (nothing it holds), and
    the plain name starts afresh; the copy is never written over, and no store takes it for the name's file."""
    store = kind(tmp_path)
    plain = tmp_path / store.file_names("Pe", language)[0]
    content = store.unreadable(how, "Pe", language)
    plain.write_text(content, encoding="utf-8")
    assert store.marks("Pe", language) == set()  # read as nothing: a fresh one
    copies = _copies(tmp_path)
    assert list(copies.values()) == [content] and not plain.exists()
    copy = tmp_path / next(iter(copies))
    assert copy.name.startswith(plain.stem + ".unreadable-") and names.is_copy(copy)
    err = capsys.readouterr().err
    assert err == f"{plain} could not be read ({reason}); kept as {copy}\n" and SECRET not in err
    assert store.path_for("Pe", language) == plain  # the copy is never the name's file
    assert store.save("Pe", "a", language) == plain and store.marks("Pe", language) == {"a"}
    assert _copies(tmp_path) == copies and capsys.readouterr().err == ""  # kept as it was, said once


@pytest.mark.parametrize("kind, language", WITH_THE_CACHE)
def test_two_in_a_row_get_two_dated_copies(tmp_path, monkeypatch, kind, language):
    """A copy is never written over, not even by one set aside in the same second."""
    _same_second(monkeypatch)
    store = kind(tmp_path)
    plain = tmp_path / store.file_names("Pe", language)[0]
    first, second = store.unreadable("not-json", "Pe", language), store.unreadable("newer", "Pe", language)
    plain.write_text(first, encoding="utf-8")
    assert store.marks("Pe", language) == set()
    store.save("Pe", "a", language)
    plain.write_text(second, encoding="utf-8")  # damaged again (or a newer TASlation wrote it)
    assert store.marks("Pe", language) == set()
    assert _copies(tmp_path) == {f"{plain.stem}.unreadable-20261030-120000.json": first,
                                 f"{plain.stem}.unreadable-20261030-120000-2.json": second}


@pytest.mark.parametrize("kind, language", WITH_THE_CACHE)
def test_the_list_shows_no_copy(tmp_path, kind, language):
    """Not even one that can be read: a copy of a newer TASlation's file, one a reader mended by hand without
    renaming it, one that records no name, a cache set aside as .corrupt.json by an earlier version."""
    store = kind(tmp_path)
    plain = tmp_path / store.file_names("Pe", language)[0]
    for how in ("newer", "not-json"):
        plain.write_text(store.unreadable(how, "Pe", language), encoding="utf-8")
        store.marks("Pe", language)
    good = store.save("Pe", "a", language)
    (tmp_path / f"{good.stem}.unreadable-19990101-000000.json").write_bytes(good.read_bytes())  # mended by hand
    (tmp_path / f"{good.stem}.corrupt.json").write_bytes(good.read_bytes())
    if kind is not Caches:
        (tmp_path / f"{good.stem}.unreadable-19990101-000001.json").write_text(json.dumps(store.raw("e")),
                                                                               encoding="utf-8")
    assert store.listed() == [("Pe", plain.name)] and store.marks("Pe", language) == {"a"}
    assert len(_copies(tmp_path)) == (3 if kind is Caches else 4)


@pytest.mark.parametrize("kind, language", WITH_THE_CACHE)
def test_delete_takes_the_copies_with_the_names_files(tmp_path, kind, language):
    """Damaged copies go as the name's own file names do; readable ones because they record the name. The copies of
    another name that starts the same stay, with that name's files."""
    store = kind(tmp_path)
    for name in ("Pe", "Pe Harbor"):
        plain = tmp_path / store.file_names(name, language)[0]
        for how in ("not-json", "newer", "not-object"):
            plain.write_text(store.unreadable(how, name, language), encoding="utf-8")
            store.marks(name, language)
        store.save(name, "a", language)
    (tmp_path / store.file_names("Pe", language)[0].replace(".json", ".corrupt.json")).write_text("{", encoding="utf-8")
    assert len(_copies(tmp_path)) == 6 and store.delete("Pe") and not store.delete("Pe")
    left = sorted(p.name for p in tmp_path.iterdir())
    assert len(left) == 4 and all(name.startswith("Pe_Harbor") for name in left)
    assert store.marks("Pe Harbor", language) == {"a"} and store.marks("Pe", language) == set()


@pytest.mark.parametrize("how", ["not-json", "newer"])
@pytest.mark.parametrize("kind, language", WITH_THE_CACHE)
def test_a_save_never_writes_over_a_file_written_meanwhile_that_it_cannot_read(tmp_path, capsys, kind, language,
                                                                               how):
    """Opened while there was no file (or a good one), saved after another process left one this version cannot
    read there (a newer TASlation, say): that one is set aside first."""
    store = kind(tmp_path)
    obj = store.open("Pe", language)
    plain = tmp_path / store.file_names("Pe", language)[0]
    content = store.unreadable(how, "Pe", language)
    plain.write_text(content, encoding="utf-8")
    store.mark(obj, "a")
    obj.save()
    assert obj.path == plain and list(_copies(tmp_path).values()) == [content]
    assert "could not be read" in capsys.readouterr().err
    assert store.marks("Pe", language) == {"a"}


@pytest.mark.parametrize("kind, language", WITH_THE_CACHE)
def test_a_file_that_cannot_be_opened_is_neither_moved_nor_written_over(tmp_path, monkeypatch, kind, language):
    """A file the system will not open now (another program holds it, the permissions) may be perfectly good: it is
    not set aside, and nothing is written over it; the save says so (an OSError)."""
    store = kind(tmp_path)
    path = store.save("Pe", "a", language)
    before = path.read_bytes()
    real = names.load_object

    def locked(p):
        if Path(p) == path:
            raise PermissionError(13, "The process cannot access the file", str(p))
        return real(p)

    monkeypatch.setattr(names, "load_object", locked)
    monkeypatch.setattr(cache_module, "load_object", locked)
    with pytest.raises(PermissionError):
        store.save("Pe", "b", language)
    assert path.read_bytes() == before and not _copies(tmp_path)


@pytest.mark.parametrize("kind, language", WITH_THE_CACHE)
def test_a_file_that_cannot_be_moved_aside_is_not_written_over(tmp_path, monkeypatch, kind, language):
    store = kind(tmp_path)
    plain = tmp_path / store.file_names("Pe", language)[0]
    content = store.unreadable("not-json", "Pe", language)
    plain.write_text(content, encoding="utf-8")

    def refused(_source, _target):
        raise PermissionError(13, "The process cannot access the file")

    monkeypatch.setattr(names, "_move_new", refused)
    with pytest.raises(PermissionError):
        store.save("Pe", "a", language)
    assert plain.read_text(encoding="utf-8") == content and not _copies(tmp_path)


def test_no_language_gives_the_name_of_a_copy():
    """A copy is never the file of a name in some language: the language part of a file name is never a copy's."""
    for language in ("unreadable-20261030-120000", "Unreadable-20261030-120000-2", "corrupt"):
        plain, hashed = file_names("Pe", language)
        assert not names.is_copy(Path(plain)) and not names.is_copy(Path(hashed)), language
        assert plain.startswith("Pe._"), language
    assert file_names("Pe", "German") == ("Pe.german.json", f"Pe-{names.name_hash('Pe')}.german.json")
    assert names.is_copy(Path("Pe.german.unreadable-20261030-120000-2.json")) and names.is_copy(Path("Pe.corrupt.json"))
    assert not names.is_copy(Path("Pe.json")) and not names.is_copy(Path("Pe.before-import.20261030-120000.json"))
