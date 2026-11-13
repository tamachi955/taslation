"""The saved files with text of a book, protected at rest for this Windows user with Windows DPAPI
(`taslation.protect`): the format, nothing of the book readable on disk (UTF-8 nor UTF-16), an earlier version's plain file read and saved
protected, the start's conversion (counts, a file that fails left as it was), a file this user cannot open here set
aside and never written over, no plain temporary file, no plain file where there is no DPAPI, the encrypted export and
an export of TASlation 0.1.0, recognising books by their protected caches, and the commands. Real DPAPI, temporary
state folders only."""
from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import FIXTURES, requires_ocr

from taslation import atomic, cli, names, netguard, protect
from taslation.annotations import AnnotationStore, GlossaryStore
from taslation.cache import BookCache, CachedBubble, CachedPage, CacheStore, stored_book
from taslation.cli import main
from taslation.messages import Message

pytestmark = pytest.mark.skipif(not protect.available(), reason="Windows data protection (DPAPI) only")

BOOK = "秘密の港 Pebble Harbor 1"
SERIES = "秘密の港 Pebble Harbor"
MODEL = "fixture-model:1b"
LINES = ("Mister Quillpond, the tide is coming in!", "Run to the lighthouse")
NOTE_TEXT = "Quillpond speaks like an old sailor"
TERM, RENDERING = "灯台守", "Lighthouse Keeper Ospry"
FP_A, FP_B = "a" * 80, "b" * 80
PASSPHRASE = "correct horse battery staple"


def _page(fp: str, *texts: str, seq: int = 0) -> CachedPage:
    return CachedPage(fingerprint=fp, aspect=0.71, seq=seq,
                      bubbles=[CachedBubble(box=(0.1 * (i + 1), 0.1, 0.1 * (i + 1) + 0.05, 0.2), text=t)
                               for i, t in enumerate(texts)])


def _cache(store: CacheStore, book: str = BOOK, language: str = "English") -> BookCache:
    cache = store.open(book, MODEL, language)
    cache.add(_page(FP_A, *LINES, seq=0))
    cache.add(_page(FP_B, "A second page", seq=1))
    cache.save()
    return cache


def _texts(cache: BookCache) -> dict[str, list[str]]:
    return {p.fingerprint: [b.text for b in p.bubbles] for p in cache.pages}


def _plain_cache_file(path: Path, book: str = BOOK, language: str = "English") -> bytes:
    """A cache file as TASlation 0.1.0 wrote it: its JSON in UTF-8, nothing protected."""
    cache = BookCache(path, book, MODEL, language)
    cache.add(_page(FP_A, *LINES, seq=0))
    raw = json.dumps(cache.to_json(), ensure_ascii=False, indent=1).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _secrets_absent(data: bytes, *secrets: str) -> None:
    for secret in secrets:
        for form in (secret.encode("utf-8"), secret.encode("utf-16-le"), json.dumps(secret).encode("ascii"),
                     json.dumps(secret)[1:-1].encode("utf-16-le")):
            assert form not in data, secret


def _sealed_elsewhere(data: bytes, monkeypatch) -> bytes:
    """*data* protected as by another Windows user or another computer: under another entropy, which this user's
    DPAPI refuses as it refuses another user's key (ERROR_INVALID_DATA)."""
    with monkeypatch.context() as m:
        m.setattr(protect, "ENTROPY", b"another user's key")
        return protect.seal(data)


@pytest.fixture
def state(tmp_path) -> Path:
    folder = tmp_path / "state"
    folder.mkdir()
    return folder


# ------------------------------------------------------------------ the format
def test_seal_and_open_round_trip_and_the_format():
    payload = json.dumps({"book": BOOK, "pages": [{"text": LINES[0]}]}, ensure_ascii=False).encode("utf-8")
    sealed = protect.seal(payload)
    assert protect.is_protected(sealed) and not protect.is_protected(payload)
    first, note, blob = sealed.split(b"\n", 2)
    assert first == b"TASLATION-PROTECTED-1" and note + b"\n" == protect.NOTE and b"Not JSON" in note
    assert all(32 <= c < 127 for c in note)  # what an editor shows: plain ASCII words
    assert protect.open_(sealed) == payload == protect.readable(sealed)
    assert protect.readable(payload) == payload  # a plain file: as it is
    assert protect.protected(sealed) == sealed  # a protected file is never sealed twice
    assert protect.seal(payload) != sealed  # a new salt each time
    _secrets_absent(sealed, BOOK, "秘密の港", "Pebble Harbor", LINES[0], "Quillpond")
    with pytest.raises(protect.CannotOpen, match="not a protected file"):
        protect.open_(payload)


def test_a_changed_byte_another_key_or_a_newer_version_cannot_be_opened(monkeypatch):
    sealed = protect.seal(b'{"schema": 1}')
    middle = len(sealed) - 30
    for damaged in (sealed[:middle] + bytes([sealed[middle] ^ 0x01]) + sealed[middle + 1:],  # in the blob
                    sealed[:-1],  # cut short
                    protect.HEADER + protect.NOTE,  # no blob at all
                    protect.HEADER + b"no end to the note line" * 300,
                    b"TASLATION-PROTECTED-x\n" + sealed.split(b"\n", 1)[1]):
        with pytest.raises(protect.CannotOpen) as raised:
            protect.open_(damaged)
        assert not isinstance(raised.value, protect.Newer)
    elsewhere = _sealed_elsewhere(b'{"schema": 1}', monkeypatch)
    with pytest.raises(protect.CannotOpen) as raised:
        protect.open_(elsewhere)
    assert raised.value.reason == protect.NOT_HERE and raised.value.code == 0x0D  # ERROR_INVALID_DATA
    with pytest.raises(protect.Newer):
        protect.open_(b"TASLATION-PROTECTED-2\n" + sealed.split(b"\n", 1)[1])


def test_where_there_is_no_dpapi_nothing_is_written_in_plain_text(state, monkeypatch, capsys):
    store = CacheStore(state / "cache")
    sealed = protect.seal(b'{"schema": 1}')
    monkeypatch.setattr(protect, "_crypt", lambda: None)
    assert not protect.available()
    cache = store.open(BOOK, MODEL)
    cache.add(_page(FP_A, *LINES))
    with pytest.raises(OSError, match="cannot protect saved files"):
        cache.save()
    assert not (state / "cache").exists() or not list((state / "cache").iterdir())  # no file, no temporary one
    with pytest.raises(protect.CannotOpen, match="cannot open protected files"):
        protect.open_(sealed)
    assert protect.migrate(state).protected == 0
    with pytest.raises(SystemExit, match="cannot protect saved files"):
        cli._protect_files(SimpleNamespace(state_dir=state))


# ------------------------------------------------------------------ the stores
def test_saved_caches_annotations_and_sheets_hold_nothing_readable(state):
    cache = _cache(CacheStore(state / "cache"))
    annotations = AnnotationStore(state / "annotations").open(BOOK)
    annotations.page(FP_A, 0.71).set_note((0.1, 0.1, 0.2, 0.2), speaker="Quillpond", note=NOTE_TEXT)
    annotations.save()
    sheet = GlossaryStore(state / "glossary").open(SERIES)
    sheet.set(TERM, RENDERING, "the old keeper")
    sheet.save()
    for path in (cache.path, annotations.path, sheet.path):
        data = path.read_bytes()
        assert path.suffix == ".json" and protect.is_protected(data), path
        _secrets_absent(data, BOOK, SERIES, "秘密の港", "Pebble Harbor", *LINES, "Quillpond", NOTE_TEXT, TERM,
                        RENDERING, FP_A[:16])
    assert _texts(CacheStore(state / "cache").open(BOOK, MODEL)) == {FP_A: list(LINES), FP_B: ["A second page"]}
    again = AnnotationStore(state / "annotations").open(BOOK)
    assert again.page(FP_A, 0.71).notes[0].note == NOTE_TEXT
    assert GlossaryStore(state / "glossary").open(SERIES).format(limit_chars=10000).count(RENDERING) == 1
    assert [b["book"] for b in CacheStore(state / "cache").list()] == [BOOK]
    assert [b["book"] for b in AnnotationStore(state / "annotations").list()] == [BOOK]
    assert [s["series"] for s in GlossaryStore(state / "glossary").list()] == [SERIES]
    assert not [p for p in state.rglob("*") if p.name.endswith(".tmp")]


def test_an_earlier_versions_plain_file_is_read_and_saved_protected(state):
    store = CacheStore(state / "cache")
    path = store.path_for(BOOK)
    _plain_cache_file(path)
    assert stored_book(path) == (BOOK, "english")
    assert [i.book for i in store.identities()] == [BOOK] and store.page_count(BOOK) == 1
    cache = store.open(BOOK, MODEL)
    assert _texts(cache) == {FP_A: list(LINES)}
    cache.add(_page(FP_B, "New", seq=1))
    cache.save()
    assert protect.is_protected(path.read_bytes())
    assert _texts(store.open(BOOK, MODEL)) == {FP_A: list(LINES), FP_B: ["New"]}
    identities = store.identities()  # read again: the file changed
    assert [(i.book, len(i.pages)) for i in identities] == [(BOOK, 2)] and store.page_count(BOOK) == 2


def test_recognising_a_book_reads_its_protected_cache(state):
    """What `bookid.recognise` reads (tests/test_bookid.py recognises books by their caches, all protected now)."""
    _cache(CacheStore(state / "cache"))
    store = CacheStore(state / "cache")
    assert [(i.book, sorted(fp for fp, _a in i.pages)) for i in store.identities()] == [(BOOK, [FP_A, FP_B])]
    assert store.page_count(BOOK) == 2 and stored_book(store.path_for(BOOK)) == (BOOK, "english")


def test_no_plain_temporary_file_is_ever_written(state, monkeypatch):
    seen: list[bytes] = []
    real_replace = os.replace

    def replace(src, dst):
        with open(src, "rb") as f:
            seen.append(f.read())
        return real_replace(src, dst)

    monkeypatch.setattr(atomic.os, "replace", replace)
    _plain_cache_file(CacheStore(state / "cache").path_for(BOOK))
    os.utime(CacheStore(state / "cache").path_for(BOOK), (time.time() - 5, time.time() - 5))
    protect.migrate(state)  # the conversion of a plain file
    _cache(CacheStore(state / "cache"), book="Another book")  # a save
    sheet = GlossaryStore(state / "glossary").open(SERIES)
    sheet.set(TERM, RENDERING)
    sheet.save()
    assert len(seen) >= 3
    for data in seen:
        assert protect.is_protected(data)
        _secrets_absent(data, BOOK, *LINES, TERM, RENDERING)


# ------------------------------------------------------------------ the start's conversion
def test_the_start_protects_plain_files_and_leaves_one_that_fails(state, monkeypatch, caplog):
    monkeypatch.setattr(atomic, "REPLACE_PAUSE", 0.0)
    cache_raw = _plain_cache_file(state / "cache" / "Pebble_Harbor_1.json")
    held_raw = _plain_cache_file(state / "cache" / "Held.json", book="Held book")
    for folder, name in (("annotations", "Pebble_Harbor_1.json"), ("glossary", "Pebble_Harbor.json"),
                         ("series", "Pebble_Harbor.json")):
        (state / folder).mkdir(exist_ok=True)
        (state / folder / name).write_text(json.dumps({"schema": 1, "book": BOOK, "note": NOTE_TEXT}),
                                           encoding="utf-8")
    old_tmp = state / "cache" / "Pebble_Harbor_1.json.abc.tmp"
    young_tmp = state / "cache" / "Pebble_Harbor_1.json.def.tmp"
    for leftover in (old_tmp, young_tmp):
        leftover.write_bytes(cache_raw[:100])
    hour_ago = time.time() - 3600
    os.utime(old_tmp, (hour_ago, hour_ago))
    (state / "ui.json").write_text('{"last_book": {"viewer": "Pebble Harbor 1"}}', encoding="utf-8")
    other_user = _sealed_elsewhere(b'{"schema": 1}', monkeypatch)
    (state / "glossary" / "Theirs.json").write_bytes(other_user)

    caplog.set_level(logging.INFO, logger="taslation.protect")
    protect.LOG.addHandler(caplog.handler)  # (whether or not the package's logger passes records on)
    try:
        with open(state / "cache" / "Held.json", "rb"):  # another program holds it: Windows refuses the swap
            tally = protect.migrate(state)
    finally:
        protect.LOG.removeHandler(caplog.handler)
    assert (tally.protected, tally.plain, tally.sealed) == (5, 2, 1)  # the held file and the young leftover
    assert (state / "cache" / "Held.json").read_bytes() == held_raw  # left exactly as it was
    assert young_tmp.read_bytes() == cache_raw[:100]
    assert (state / "glossary" / "Theirs.json").read_bytes() == other_user  # never touched
    assert (state / "ui.json").read_text(encoding="utf-8").startswith("{")  # not a store's file
    for path in (state / "cache" / "Pebble_Harbor_1.json", old_tmp, state / "series" / "Pebble_Harbor.json"):
        assert protect.is_protected(path.read_bytes()), path
    assert protect.read(state / "cache" / "Pebble_Harbor_1.json") == cache_raw  # the same bytes inside
    assert sorted(p.name for p in (state / "cache").iterdir()) == sorted(
        ["Held.json", "Pebble_Harbor_1.json", old_tmp.name, young_tmp.name])  # no temporary file of its own left
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "5 protected now" in logged and "2 left plain" in logged
    assert "Pebble" not in logged and "Held" not in logged and "Quillpond" not in logged

    found = protect.survey(state)
    assert (found.plain, found.sealed, found.opened, found.not_here) == (2, 6, 5, 1)
    assert protect.migrate(state).protected == 1  # the next start: the held file now
    assert protect.read(state / "cache" / "Held.json") == held_raw
    assert protect.migrate(state).protected == 0 and protect.survey(state).plain == 1  # the young leftover


def test_the_window_start_says_what_it_did(state, monkeypatch):
    from taslation.ui.app import protect_saved_files
    from taslation.ui.jobs import SAVED_FILES, JobsMixin

    _plain_cache_file(CacheStore(state / "cache").path_for(BOOK))
    (state / "annotations").mkdir()
    (state / "annotations" / "Theirs.json").write_bytes(_sealed_elsewhere(b'{"schema": 1}', monkeypatch))
    done = protect_saved_files(state)
    assert done is not None and (done.protected, done.sealed) == (1, 1)

    class Window:
        _tell_protection = JobsMixin._tell_protection
        _tell_not_here = JobsMixin._tell_not_here
        _watch_set_aside = JobsMixin._watch_set_aside

        def __init__(self):
            self.settings = SimpleNamespace(state_dir=state)
            self._protection = done
            self.posted: list[tuple[str, dict]] = []
            self.told: list[str] = []

        def _post(self, kind, **data):
            self.posted.append((kind, data))

        def _warn_unasked(self, text, said=False):
            self.told.append(text)

    window = Window()
    loaded: list[Message] = []
    window._tell_protection(loaded)
    assert [m.code for m in loaded] == ["store.protected"] and loaded[0].params["files"] == 1
    assert window.posted == [("not_here", {"files": 1})]
    window._tell_not_here(1)
    assert len(window.told) == 1 and "export them where they were saved" in window.told[0]
    window._tell_not_here(1)  # the next start, the same file: no box again
    assert len(window.told) == 1
    from taslation.i18n import load_ui_table

    assert load_ui_table(state, SAVED_FILES) == {"not_here": "1"}
    window._tell_not_here(0)
    assert load_ui_table(state, SAVED_FILES) == {} and len(window.told) == 1

    # a store of the window sets aside a book's file it cannot open: said once, with where it is kept
    store = CacheStore(state / "cache")
    path = store.path_for(BOOK)
    path.write_bytes(_sealed_elsewhere(path.read_bytes(), monkeypatch))
    store.open(BOOK, MODEL)
    window._watch_set_aside()
    assert len(window.told) == 2 and ".unreadable-" in window.told[1] and "Import..." in window.told[1]
    window._watch_set_aside()
    assert len(window.told) == 2


# ------------------------------------------------------------------ a file this Windows user cannot open here
@pytest.mark.parametrize("kind", ["elsewhere", "damaged", "newer"])
def test_a_file_that_cannot_be_opened_here_is_set_aside_and_never_written_over(state, monkeypatch, capsys, kind):
    store = CacheStore(state / "cache")
    _cache(store)
    path = store.path_for(BOOK)
    inside = protect.read(path)
    if kind == "elsewhere":
        theirs = _sealed_elsewhere(inside, monkeypatch)
    elif kind == "damaged":
        sealed = path.read_bytes()
        theirs = sealed[:-20] + bytes([sealed[-20] ^ 0x01]) + sealed[-19:]
    else:
        theirs = b"TASLATION-PROTECTED-2\n" + path.read_bytes().split(b"\n", 1)[1]
    path.write_bytes(theirs)
    names.take_set_aside()
    capsys.readouterr()

    assert [b["book"] for b in store.list()] == [] and store.identities() == []
    fresh = store.open(BOOK, MODEL)  # the book starts afresh ...
    assert len(fresh) == 0
    copies = list((state / "cache").glob("*.unreadable-*.json"))
    assert len(copies) == 1 and copies[0].read_bytes() == theirs  # ... the file kept, the very bytes
    said = capsys.readouterr().err
    reason = names.NEWER if kind == "newer" else protect.NOT_HERE
    assert reason in said and str(copies[0]) in said
    taken = names.take_set_aside()
    if kind == "newer":
        assert taken == [] and names.NOT_HERE_ADVICE not in said
    else:
        assert [t.copy for t in taken] == copies and names.NOT_HERE_ADVICE in said
    fresh.add(_page(FP_B, "Translated here"))
    fresh.save()
    assert copies[0].read_bytes() == theirs and _texts(store.open(BOOK, MODEL)) == {FP_B: ["Translated here"]}
    assert protect.migrate(state).protected == 0 and copies[0].read_bytes() == theirs
    found = protect.survey(state)
    assert (found.not_here, found.newer) == ((0, 1) if kind == "newer" else (1, 0))
    assert store.delete(BOOK) and not copies[0].exists()  # deleting the book takes the copy with it


def test_annotations_and_sheets_of_another_user_are_set_aside_too(state, monkeypatch, capsys):
    annotations = AnnotationStore(state / "annotations").open(BOOK)
    annotations.page(FP_A, 0.71).set_note((0.1, 0.1, 0.2, 0.2), note=NOTE_TEXT)
    annotations.save()
    sheet = GlossaryStore(state / "glossary").open(SERIES)
    sheet.set(TERM, RENDERING)
    sheet.save()
    for path in (annotations.path, sheet.path):
        path.write_bytes(_sealed_elsewhere(protect.read(path), monkeypatch))
    names.take_set_aside()
    assert len(AnnotationStore(state / "annotations").open(BOOK).pages) == 0
    assert len(GlossaryStore(state / "glossary").open(SERIES)) == 0
    assert len(names.take_set_aside()) == 2
    assert len(list(state.rglob("*.unreadable-*.json"))) == 2
    assert capsys.readouterr().err.count(protect.NOT_HERE) == 2


# ------------------------------------------------------------------ the encrypted export
def test_export_and_import_move_a_protected_cache_and_an_export_of_0_1_0_imports(tmp_path, monkeypatch):
    backup = pytest.importorskip("taslation.backup")
    pytest.importorskip("cryptography")
    monkeypatch.setitem(backup.KDF, "n", 2 ** 14)
    home, laptop = CacheStore(tmp_path / "home" / "cache"), CacheStore(tmp_path / "laptop" / "cache")
    _cache(home)
    out = tmp_path / "vol1.stcache"
    assert backup.export_cache(home, BOOK, out, PASSPHRASE) == 2
    blob = out.read_bytes()
    assert blob.startswith(backup.MAGIC + b"\n") and not protect.is_protected(blob)  # the portable format, as before
    _secrets_absent(blob, BOOK, *LINES)
    _plain_cache_file(laptop.path_for(BOOK))  # what an earlier version left there
    assert backup.import_cache(laptop, out, PASSPHRASE) == (BOOK, 2)
    target = laptop.path_for(BOOK)
    assert protect.is_protected(target.read_bytes())
    assert _texts(laptop.open(BOOK, MODEL)) == {FP_A: list(LINES), FP_B: ["A second page"]}
    kept = list(target.parent.glob("*.before-import.*.json"))
    assert len(kept) == 1 and protect.is_protected(kept[0].read_bytes())  # the copy before it: protected too
    assert BookCache.load(kept[0]).book == BOOK

    # written by TASlation 0.1.0's own code (commit 15fed7a), exported from the plain cache it saved; invented lines
    # (not named .stcache, which .gitignore keeps out of the repository as a reader's own export)
    old = FIXTURES / "export-0.1.0.export"
    fresh = CacheStore(tmp_path / "fresh" / "cache")
    assert backup.import_cache(fresh, old, "fixture passphrase of 0.1.0") == ("Pebble Harbor 1", 2)
    imported = fresh.path_for("Pebble Harbor 1")
    assert protect.is_protected(imported.read_bytes())
    texts = _texts(fresh.open("Pebble Harbor 1", ""))
    assert texts == {"d" * 80: ["A line from the earlier version", "Another one"], "e" * 80: ["Its second page"]}


# ------------------------------------------------------------------ the commands
@pytest.fixture
def cli_state(tmp_path, monkeypatch):
    """`taslation` with its state folder under tmp_path, the passphrase in the environment (a cheap key)."""
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(atomic, "REPLACE_PAUSE", 0.0)
    yield tmp_path / "state"
    netguard.uninstall()


def test_every_store_command_reads_and_writes_protected_files(cli_state, monkeypatch, capsys):
    backup = pytest.importorskip("taslation.backup")
    pytest.importorskip("cryptography")
    monkeypatch.setitem(backup.KDF, "n", 2 ** 14)
    monkeypatch.setenv(backup.PASSPHRASE_ENV, PASSPHRASE)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: pytest.fail("asked for a passphrase"))
    store = CacheStore(cli_state / "cache")
    path = store.path_for(BOOK)
    _plain_cache_file(path)  # an earlier version's

    assert main(["cache", "list"]) == 0  # the start protects it first, and says so on stderr
    out, err = capsys.readouterr()
    assert BOOK in out and "Protected 1 saved file:" in err and "Pebble" not in err
    assert protect.is_protected(path.read_bytes())
    assert main(["review", "--book", BOOK]) == 0
    assert "0 of 2 cached translation(s) flagged" in capsys.readouterr().out

    assert main(["glossary", "set", SERIES, "クイルポンド", "Quillpond", "--note", "the captain"]) == 0
    sheet = GlossaryStore(cli_state / "glossary").path_for(SERIES)
    assert protect.is_protected(sheet.read_bytes())
    assert main(["glossary", "show", SERIES]) == 0 and "Quillpond" in capsys.readouterr().out
    assert main(["glossary", "list"]) == 0 and SERIES in capsys.readouterr().out
    assert main(["glossary", "apply", SERIES, "--book", BOOK, "--rename", "Quillpond=Quilpond"]) == 0
    assert "1 cached bubble(s) changed" in capsys.readouterr().out
    before = list(path.parent.glob("*.before-apply.*.json"))
    assert len(before) == 1 and protect.is_protected(before[0].read_bytes())
    assert protect.is_protected(path.read_bytes()) and "Mister Quilpond" in _texts(store.open(BOOK, MODEL))[FP_A][0]

    annotations = AnnotationStore(cli_state / "annotations").open(BOOK)
    annotations.page(FP_A, 0.71).set_note((0.1, 0.1, 0.2, 0.2), note=NOTE_TEXT)
    annotations.save()
    assert main(["annotations", "list"]) == 0 and "1 note(s)" in capsys.readouterr().out

    out_file = cli_state.parent / "vol1.stcache"
    assert main(["cache", "export", BOOK, "--out", str(out_file)]) == 0
    assert main(["cache", "delete", BOOK]) == 0 and "deleted" in capsys.readouterr().out
    assert not path.exists()
    assert main(["cache", "import", str(out_file)]) == 0
    assert protect.is_protected(path.read_bytes()) and len(store.open(BOOK, MODEL)) == 1
    capsys.readouterr()

    assert main(["cache", "protect"]) == 0
    lines = capsys.readouterr().out.splitlines()
    n = len(protect.store_files(cli_state))  # the cache, the series sheet, the annotations
    assert n >= 3 and lines[0] == (f"{n} saved file(s) with text of a book: {n} protected for this Windows user on "
                                   "this computer, 0 plain")
    assert f"opened here: {n} of {n} protected file(s)" in lines
    for line in lines:
        assert "Pebble" not in line and "Quillpond" not in line


def test_cache_protect_and_list_say_what_cannot_be_opened_here(cli_state, monkeypatch, capsys):
    store = CacheStore(cli_state / "cache")
    _plain_cache_file(store.path_for(BOOK))
    other = store.path_for("Copied from elsewhere")
    other.write_bytes(_sealed_elsewhere(b'{"schema": 1, "book": "x", "pages": []}', monkeypatch))
    assert main(["cache", "protect"]) == 0
    out = capsys.readouterr().out
    assert "2 saved file(s) with text of a book: 2 protected" in out and "protected now: 1 file(s)" in out
    assert "opened here: 0 of 1 protected file(s)" in out
    assert "cannot be opened here: 1 file(s)" in out and names.NOT_HERE_ADVICE in out
    assert main(["cache", "list"]) == 0
    out, err = capsys.readouterr()
    assert BOOK in out and "Copied from elsewhere" not in out
    assert "note: 1 saved file(s) cannot be opened by this Windows user" in err and "import the export here" in err
    assert protect.is_protected(other.read_bytes()) and protect.survey(cli_state).not_here == 1

    held = store.path_for("Held")
    _plain_cache_file(held, book="Held")
    with open(held, "rb"):
        assert main(["cache", "protect"]) == 1  # a file left in plain text
        out = capsys.readouterr().out
    assert "not protected yet: 1 file(s)" in out
    with open(held, "rb"):
        assert main(["cache", "list"]) == 0
    assert "could not be protected yet" in capsys.readouterr().err


def test_the_audit_reports_plain_files_left(cli_state, capsys):
    settings = SimpleNamespace(state_dir=cli_state)
    _plain_cache_file(CacheStore(cli_state / "cache").path_for(BOOK))
    cli._audit_saved_files(settings)
    out = capsys.readouterr().out
    assert "--- saved files (at rest) ---" in out and "1 saved file(s) with text of a book: 0 protected" in out
    assert "not protected yet: 1 file(s)" in out and "Pebble" not in out
    protect.migrate(cli_state)
    cli._audit_saved_files(settings)
    out = capsys.readouterr().out
    assert "1 protected for this Windows user on this computer, 0 plain" in out
    assert "plain files with text of a book: none" in out


@requires_ocr
def test_the_audit_command_ends_with_the_saved_files(cli_state, capsys):
    _plain_cache_file(CacheStore(cli_state / "cache").path_for(BOOK))
    assert main(["audit", str(FIXTURES / "sample_page.png"), "--translator", "none"]) == 0
    out = capsys.readouterr().out
    assert out.index("--- network audit ---") < out.index("--- saved files (at rest) ---")
    assert "0 protected for this Windows user on this computer, 1 plain" in out  # the audit changes nothing


def test_the_real_state_folder_is_never_converted_by_a_test():
    """The guard in conftest.py: a start with the machine's own state folder converts and counts nothing."""
    real = Path.home() / ".taslation"
    assert protect.migrate(real) == protect.Tally()
    assert protect.survey(real).files == 0
