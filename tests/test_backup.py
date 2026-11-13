"""The encrypted export of a translation cache: the format, a wrong passphrase or a changed byte refused, nothing
readable in the file, and `taslation cache export/import` merging or replacing through the cache store."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import zlib

import pytest

pytest.importorskip("cryptography")

from taslation import backup, netguard  # noqa: E402
from taslation.cache import BookCache, CacheStore, CachedBubble, CachedPage, cache_names  # noqa: E402
from taslation.cli import main  # noqa: E402

PASSPHRASE = "correct horse battery staple"
BOOK = "秘密の本 Secret Volume 3"
MODEL = "unusual-model:7b-test"
LANGUAGE = "Klingon"
FP_A, FP_B, FP_C = "a" * 80, "b" * 80, "c" * 80


@pytest.fixture(autouse=True)
def _quicker_keys(request, monkeypatch):
    """The format's scrypt cost (0.4 s a key) where the format is checked; a cheaper one for the rest."""
    if request.node.name != "test_round_trip_and_the_format":
        monkeypatch.setitem(backup.KDF, "n", 2 ** 14)


def _page(fp: str, *texts: str, seq: int = -1) -> CachedPage:
    return CachedPage(fingerprint=fp, aspect=0.71, seq=seq,
                      bubbles=[CachedBubble(box=(0.1 * (i + 1), 0.1, 0.1 * (i + 1) + 0.05, 0.2), text=t)
                               for i, t in enumerate(texts)])


def _texts(cache: BookCache) -> dict[str, list[str]]:
    return {p.fingerprint: [b.text for b in p.bubbles] for p in cache.pages}


def test_round_trip_and_the_format():
    payload = json.dumps({"book": BOOK, "pages": []}, ensure_ascii=False).encode("utf-8")
    blob = backup.encrypt(payload, PASSPHRASE)
    assert backup.decrypt(blob, PASSPHRASE) == payload
    first, rest = blob.split(b"\n", 1)
    assert first == b"TASLATION-CACHE-1"
    header = json.loads(rest)
    assert set(header) == {"kdf", "salt", "nonce", "data"}
    assert header["kdf"] == {"name": "scrypt", "n": 131072, "r": 8, "p": 1}
    assert len(base64.b64decode(header["salt"])) == 16 and len(base64.b64decode(header["nonce"])) == 12
    again = json.loads(backup.encrypt(payload, PASSPHRASE).split(b"\n", 1)[1])
    assert again["salt"] != header["salt"] and again["nonce"] != header["nonce"] and again["data"] != header["data"]


def test_wrong_passphrase_is_refused():
    blob = backup.encrypt(b"payload", PASSPHRASE)
    with pytest.raises(backup.BackupError, match="wrong passphrase"):
        backup.decrypt(blob, PASSPHRASE + "!")
    # the same words typed in another Unicode form are the same passphrase
    assert backup.decrypt(backup.encrypt(b"x", "Café au lait noir"), "Café au lait noir") == b"x"


def _changed(blob: bytes, field: str, change) -> bytes:
    first, rest = blob.split(b"\n", 1)
    header = json.loads(rest)
    header[field] = change(header[field])
    return first + b"\n" + json.dumps(header).encode("ascii")


def _flip(text: str) -> str:
    raw = bytearray(base64.b64decode(text))
    raw[len(raw) // 2] ^= 0x01
    return base64.b64encode(bytes(raw)).decode("ascii")


def test_a_changed_byte_is_refused():
    blob = backup.encrypt(b"payload " * 50, PASSPHRASE)
    for field in ("data", "nonce", "salt"):
        with pytest.raises(backup.BackupError):
            backup.decrypt(_changed(blob, field, _flip), PASSPHRASE)
    with pytest.raises(backup.BackupError):  # the header is authenticated too
        backup.decrypt(_changed(blob, "kdf", lambda kdf: {**kdf, "comment": "x"}), PASSPHRASE)
    for kdf in ({"name": "scrypt", "n": 2 ** 30, "r": 8, "p": 1}, {"name": "pbkdf2", "n": 2, "r": 1, "p": 1},
                {"name": "scrypt", "n": 1000, "r": 8, "p": 1}, {"name": "scrypt", "n": 16384, "r": True, "p": 1},
                {"name": "scrypt", "n": 2 ** 20, "r": 1, "p": 1}):  # the last within bounds, but OpenSSL refuses it
        with pytest.raises(backup.BackupError, match="damaged"):  # refused before any key is derived
            backup.decrypt(_changed(blob, "kdf", lambda _old, kdf=kdf: kdf), PASSPHRASE)
    mid = len(blob) - 40
    with pytest.raises(backup.BackupError):
        backup.decrypt(blob[:mid] + bytes([blob[mid] ^ 0x02]) + blob[mid + 1:], PASSPHRASE)
    for junk in (b"", b"PK\x03\x04 a zip file", b"TASLATION-CACHE-1\nnot json", blob[:60]):
        with pytest.raises(backup.BackupError):
            backup.decrypt(junk, PASSPHRASE)


def test_short_passphrase_is_refused(tmp_path):
    with pytest.raises(backup.BackupError, match="at least 12 characters"):
        backup.encrypt(b"payload", "eleven char")
    backup.check_passphrase("twelve chars")
    store = CacheStore(tmp_path)
    with pytest.raises(backup.BackupError, match="at least 12 characters"):
        backup.export_cache(store, BOOK, tmp_path / "out.stcache", "short")


def _cache(store: CacheStore, *pages: CachedPage, book: str = BOOK, language: str = LANGUAGE) -> BookCache:
    cache = store.open(book, MODEL, language)
    for page in pages:
        cache.add(page)
    cache.save()
    return cache


def test_the_file_shows_nothing_of_the_book(tmp_path):
    store = CacheStore(tmp_path / "cache")
    _cache(store, _page(FP_A, "Hello there, Mister Tanaka"), _page(FP_B, "Run!"))
    out = tmp_path / "backup.stcache"
    assert backup.export_cache(store, BOOK, out, PASSPHRASE, LANGUAGE) == 2
    blob = out.read_bytes()
    for secret in (BOOK, "秘密", "Secret Volume", MODEL, LANGUAGE, "Tanaka", "Hello there", FP_A[:16]):
        assert secret.encode("utf-8") not in blob, secret
        assert json.dumps(secret).encode("ascii") not in blob, secret  # nor as escaped JSON
    data = json.loads(backup.decrypt(blob, PASSPHRASE))
    assert data["book"] == BOOK and data["model"] == MODEL and data["language"] == LANGUAGE
    with pytest.raises(backup.BackupError, match="no cache for"):
        backup.export_cache(store, "Another book", out, PASSPHRASE)
    source = store.path_for(BOOK, LANGUAGE)
    with pytest.raises(backup.BackupError, match="the cache itself"):
        backup.export_cache(store, BOOK, source, PASSPHRASE, LANGUAGE)
    assert BookCache.load(source).book == BOOK  # untouched


def test_import_merges_like_a_save_or_replaces(tmp_path):
    home, other = CacheStore(tmp_path / "home"), CacheStore(tmp_path / "other")
    _cache(home, _page(FP_A, "Corrected line"), _page(FP_B, "Second page"))
    out = tmp_path / "backup.stcache"
    backup.export_cache(home, BOOK, out, PASSPHRASE, LANGUAGE)
    _cache(other, _page(FP_A, "Old machine translation"), _page(FP_C, "Only on the other computer"))
    assert backup.import_cache(other, out, PASSPHRASE) == (BOOK, 2)
    merged = other.open(BOOK, MODEL, LANGUAGE)
    assert _texts(merged) == {FP_A: ["Corrected line"], FP_B: ["Second page"], FP_C: ["Only on the other computer"]}
    seqs = [p.seq for p in merged.pages]
    assert len(seqs) == len(set(seqs))
    assert backup.import_cache(other, out, PASSPHRASE, replace=True) == (BOOK, 2)
    assert _texts(other.open(BOOK, MODEL, LANGUAGE)) == {FP_A: ["Corrected line"], FP_B: ["Second page"]}
    with pytest.raises(backup.BackupError, match="wrong passphrase"):
        backup.import_cache(other, out, "not the passphrase")


def test_a_merging_import_brings_the_colophons_details_to_a_cache_that_has_none(tmp_path):
    home = CacheStore(tmp_path / "home")
    cache = _cache(home, _page(FP_A, "Corrected line"))
    colophon = {"title": "秘密の本", "volume": "3", "author": "誰か", "publisher": "株式会社見本出版",
                "isbn": "978-4-06-123456-7"}
    cache.set_details(**colophon)
    cache.save()
    out = tmp_path / "backup.stcache"
    backup.export_cache(home, BOOK, out, PASSPHRASE, LANGUAGE)
    other = CacheStore(tmp_path / "other")  # a cache of the book without them, on the other computer
    _cache(other, _page(FP_B, "Only on the other computer"))
    assert backup.import_cache(other, out, PASSPHRASE) == (BOOK, 1)
    merged = other.open(BOOK, MODEL, LANGUAGE)
    assert merged.details == colophon and set(_texts(merged)) == {FP_A, FP_B}
    fresh = CacheStore(tmp_path / "fresh")  # no cache of it there yet: the same
    backup.import_cache(fresh, out, PASSPHRASE)
    assert fresh.open(BOOK, MODEL, LANGUAGE).details == colophon
    mine = CacheStore(tmp_path / "mine")  # a cache with details of its own keeps them as they are
    kept = _cache(mine, _page(FP_C, "Mine"))
    kept.set_details(title="My own title")
    kept.save()
    backup.import_cache(mine, out, PASSPHRASE)
    assert mine.open(BOOK, MODEL, LANGUAGE).details == {"title": "My own title"}


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """`taslation` with its state under tmp_path, the passphrase from the environment, getpass never reached."""
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(backup.PASSPHRASE_ENV, PASSPHRASE)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: pytest.fail("asked for a passphrase"))
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    netguard.uninstall()


def test_cache_export_and_import_commands(cli, monkeypatch, capsys):
    home = CacheStore(cli / "state" / "cache")
    _cache(home, _page(FP_A, "Corrected line"), _page(FP_B, "Second page"), language="English")
    out = cli / "vol3.stcache"
    assert main(["cache", "export", BOOK, "--out", str(out)]) == 0
    line = capsys.readouterr().out.strip()
    assert "\n" not in line and BOOK in line and "2 page(s)" in line and str(out) in line
    assert "Corrected line" not in line

    monkeypatch.setenv("TASLATION_STATE_DIR", str(cli / "laptop"))  # the reader's other computer
    laptop = CacheStore(cli / "laptop" / "cache")
    _cache(laptop, _page(FP_A, "Old machine translation"), _page(FP_C, "Only here"), language="English")
    assert main(["cache", "import", str(out)]) == 0
    line = capsys.readouterr().out.strip()
    assert "\n" not in line and BOOK in line and "2 page(s)" in line and "merged" in line
    assert _texts(laptop.open(BOOK, MODEL)) == {FP_A: ["Corrected line"], FP_B: ["Second page"], FP_C: ["Only here"]}
    assert main(["cache", "import", str(out), "--replace"]) == 0
    assert "replacing" in capsys.readouterr().out
    assert _texts(laptop.open(BOOK, MODEL)) == {FP_A: ["Corrected line"], FP_B: ["Second page"]}
    assert main(["cache", "list"]) == 0 and BOOK in capsys.readouterr().out  # the other commands stay

    monkeypatch.setenv(backup.PASSPHRASE_ENV, "a wrong passphrase")
    with pytest.raises(SystemExit, match="wrong passphrase"):
        main(["cache", "import", str(out)])
    monkeypatch.setenv(backup.PASSPHRASE_ENV, "too short")
    with pytest.raises(SystemExit, match="at least 12 characters"):
        main(["cache", "export", BOOK, "--out", str(out), "--force"])
    with pytest.raises(SystemExit, match="--out"):
        main(["cache", "export", BOOK])
    with pytest.raises(SystemExit, match="no cache for"):
        main(["cache", "export", "Never translated", "--out", str(out)])


def test_the_passphrase_is_typed_twice_without_the_environment(cli, monkeypatch, capsys):
    _cache(CacheStore(cli / "state" / "cache"), _page(FP_A, "Line"), language="English")
    monkeypatch.delenv(backup.PASSPHRASE_ENV)
    typed = iter([PASSPHRASE, PASSPHRASE + "x"])
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: next(typed))
    with pytest.raises(SystemExit, match="differ"):
        main(["cache", "export", BOOK, "--out", str(cli / "x.stcache")])
    typed = iter([PASSPHRASE, PASSPHRASE])
    assert main(["cache", "export", BOOK, "--out", str(cli / "x.stcache")]) == 0
    typed = iter([PASSPHRASE])  # once to import
    assert main(["cache", "import", str(cli / "x.stcache")]) == 0


def test_without_the_library_one_line_says_what_to_install(cli, monkeypatch):
    _cache(CacheStore(cli / "state" / "cache"), _page(FP_A, "Line"), language="English")
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.ciphers.aead", None)  # import fails
    for argv in (["cache", "export", BOOK, "--out", str(cli / "x.stcache")], ["cache", "import", "x.stcache"]):
        with pytest.raises(SystemExit) as raised:
            main(argv)
        message = str(raised.value.code)
        assert "pip install cryptography" in message and "\n" not in message
    assert not (cli / "x.stcache").exists()


def test_the_passphrase_dialog(hidden_root):
    from taslation.ui.app import PassphraseDialog

    d = PassphraseDialog(hidden_root, confirm=True)
    assert len(d.entries) == 2 and all(str(e.cget("show")) == "*" for e in d.entries)
    assert str(d.ok_btn.cget("state")) == "disabled"
    for first, second, ok in (("eleven char", "eleven char", False), (PASSPHRASE, PASSPHRASE + "!", False),
                              (PASSPHRASE, PASSPHRASE, True)):
        d.vars[0].set(first)
        d.vars[1].set(second)
        assert (str(d.ok_btn.cget("state")) == "normal") is ok
    d._ok()
    assert d.passphrase == PASSPHRASE
    d = PassphraseDialog(hidden_root, confirm=False)
    assert len(d.entries) == 1
    d.vars[0].set("short")
    d._ok()  # not long enough: the dialog stays
    assert d.passphrase is None and d.winfo_exists()
    d.destroy()


def test_the_caches_dialog_exports_and_imports(tmp_path, monkeypatch, hidden_root):
    from taslation.ui import app
    from taslation.ui.dialogs import caches

    home, other = CacheStore(tmp_path / "home"), CacheStore(tmp_path / "other")
    _cache(home, _page(FP_A, "Corrected line"))
    _cache(other, _page(FP_C, "Only here"))
    out = tmp_path / "picked.stcache"
    monkeypatch.setattr(app.CachesDialog, "_before", lambda _self, title, text: True)  # the warning: Continue
    monkeypatch.setattr(caches.filedialog, "asksaveasfilename", lambda **_k: str(out))
    monkeypatch.setattr(caches.filedialog, "askopenfilename", lambda **_k: str(out))
    monkeypatch.setattr(app.CachesDialog, "_passphrase", lambda _self, confirm: PASSPHRASE)
    statuses: list[str] = []
    d = app.CachesDialog(hidden_root, home, on_status=statuses.append)
    d.withdraw()
    assert str(d.export_btn.cget("state")) == "disabled"  # nothing selected yet
    d.tree.selection_set(d.tree.get_children()[0])
    d._sync_buttons()
    assert str(d.export_btn.cget("state")) == "normal"
    d._export()
    assert out.is_file() and statuses[-1] == app._("Exported {book} to {path}").format(book=BOOK, path=out)
    d.destroy()
    changed: list[str] = []
    d = app.CachesDialog(hidden_root, other, on_changed=changed.append, on_status=statuses.append)
    d.withdraw()
    d._import()
    assert changed == [BOOK] and statuses[-1] == app._("Imported {pages} page(s) into {book}").format(pages=1, book=BOOK)
    assert _texts(other.open(BOOK, MODEL, LANGUAGE)) == {FP_A: ["Corrected line"], FP_C: ["Only here"]}
    warnings: list[str] = []
    from taslation.ui.dialogs import caches
    monkeypatch.setattr(caches, "tell", lambda _parent, text, **_k: warnings.append(text))
    monkeypatch.setattr(app.CachesDialog, "_passphrase", lambda _self, confirm: "not the passphrase")
    d._import()
    assert warnings == [app._("Wrong passphrase or damaged file.")] == statuses[-1:]
    d.destroy()


# --- what an adversary can put in a file ----------------------------------------------------------------------

DEFAULT_KDF = {"name": "scrypt", "n": 2 ** 17, "r": 8, "p": 1}


def _header(kdf, **fields) -> bytes:
    """A file with *kdf* in its header and junk for a ciphertext: what anyone can make without a passphrase."""
    obj = {"kdf": kdf, "salt": base64.b64encode(b"s" * 16).decode(), "nonce": base64.b64encode(b"n" * 12).decode(),
           "data": base64.b64encode(b"d" * 48).decode(), **fields}
    return backup.MAGIC + b"\n" + json.dumps(obj).encode("ascii")


def _seal(packed: bytes, passphrase: str = PASSPHRASE) -> bytes:
    """An export file around *packed* exactly (no compression, no checks): what someone who knows the passphrase
    the reader will type can make."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt, nonce = os.urandom(16), os.urandom(12)
    header = {"kdf": dict(backup.KDF), "salt": base64.b64encode(salt).decode(), "nonce": base64.b64encode(nonce).decode()}
    sealed = AESGCM(backup._key(passphrase, salt, header["kdf"])).encrypt(nonce, packed, backup._associated(header))
    return backup.MAGIC + b"\n" + json.dumps({**header, "data": base64.b64encode(sealed).decode()}).encode("ascii")


def test_a_hostile_header_costs_no_key(monkeypatch):
    """scrypt parameters that would take gigabytes or many seconds (or overflow on Windows), and fields an export
    does not have, are refused before any key is derived."""
    monkeypatch.setattr(backup.hashlib, "scrypt", lambda *_a, **_k: pytest.fail("a key was derived"))
    for kdf in ({**DEFAULT_KDF, "n": 2 ** 20},  # 1 GiB
                {**DEFAULT_KDF, "n": 2, "r": 2 ** 22},  # within the old cap; OverflowError on Windows
                {**DEFAULT_KDF, "n": 4, "r": 2 ** 21},  # within the old cap: 2 GiB and 10 s
                {**DEFAULT_KDF, "n": 2, "r": 1, "p": 2 ** 22},  # within the old cap: 16 s of PBKDF2
                {**DEFAULT_KDF, "n": 2 ** 18, "r": 16},  # 512 MiB
                {**DEFAULT_KDF, "comment": "x"}, {**DEFAULT_KDF, "n": 2.0 ** 17}, {**DEFAULT_KDF, "n": "131072"},
                {**DEFAULT_KDF, "p": 0}, ["scrypt", 2 ** 17, 8, 1]):
        with pytest.raises(backup.BackupError, match="damaged"):
            backup.decrypt(_header(kdf), PASSPHRASE)
    for fields in ({"title": BOOK}, {"salt": base64.b64encode(b"s" * 4096).decode()},
                   {"nonce": base64.b64encode(b"n" * 16).decode()}, {"data": "not base64!"}):
        with pytest.raises(backup.BackupError, match="damaged"):
            backup.decrypt(_header(DEFAULT_KDF, **fields), PASSPHRASE)
    for kdf in (DEFAULT_KDF, {**DEFAULT_KDF, "n": 2 ** 18}, {**DEFAULT_KDF, "r": 16}):  # up to twice the cost is read
        assert backup._parse(_header(kdf))[0]["kdf"] == kdf


def test_what_the_tag_covers_is_checked_too(monkeypatch):
    """Someone who knows the passphrase can still send a bomb: unpacking stops at the cap, and a stream with bytes
    after it or no stream at all is refused; an export never writes a file its import would refuse."""
    monkeypatch.setattr(backup, "MAX_PAYLOAD", 1 << 20)
    bomb = _seal(zlib.compress(b"\0" * (4 << 20), 9))
    assert len(bomb) < 20_000
    with pytest.raises(backup.BackupError, match="larger"):
        backup.decrypt(bomb, PASSPHRASE)
    assert backup.decrypt(_seal(zlib.compress(b"\0" * (1 << 20))), PASSPHRASE) == b"\0" * (1 << 20)  # at the cap
    with pytest.raises(backup.BackupError, match="damaged"):
        backup.decrypt(_seal(zlib.compress(b"{}") + b"more"), PASSPHRASE)
    with pytest.raises(backup.BackupError, match="damaged"):
        backup.decrypt(_seal(b"not zlib at all"), PASSPHRASE)
    with pytest.raises(backup.BackupError, match="cannot be exported"):
        backup.encrypt(b"x" * ((1 << 20) + 1), PASSPHRASE)


def test_a_file_larger_than_any_export_is_not_read(tmp_path, monkeypatch):
    path = tmp_path / "big.stcache"
    path.write_bytes(backup.encrypt(b"x" * 1000, PASSPHRASE))
    monkeypatch.setattr(backup, "MAX_FILE", path.stat().st_size - 1)
    store = CacheStore(tmp_path / "cache")
    with pytest.raises(backup.BackupError, match="larger than any export"):
        backup.import_cache(store, path, PASSPHRASE)
    assert not store.cache_dir.exists()


def _crafted(tmp_path, content):
    """An export file, sealed with PASSPHRASE, of *content* (bytes as they are, anything else as JSON; Python's
    JSON writes NaN and Infinity and reads them back)."""
    raw = content if isinstance(content, bytes) else json.dumps(content).encode("utf-8")
    path = tmp_path / "crafted.stcache"
    path.write_bytes(_seal(zlib.compress(raw)))
    return path


GOOD_PAGE = {"fp": FP_B, "aspect": 0.7, "seq": 0, "bubbles": [{"box": [0.1, 0.1, 0.2, 0.2], "text": "Theirs"}]}


def _crafted_cache(**changes) -> dict:
    return {"schema": 1, "book": BOOK, "model": MODEL, "language": "English", "pages": [GOOD_PAGE], **changes}


@pytest.mark.parametrize("content", [
    pytest.param(b"[" * 100_000 + b"]" * 100_000, id="nested-too-deep"),  # was a RecursionError, uncaught
    pytest.param(b"\xff\xfe not UTF-8", id="not-utf8"), pytest.param(b"[]", id="a-list"),
    pytest.param(b"null", id="null"), pytest.param(_crafted_cache(schema=2), id="schema-2"),
    pytest.param(_crafted_cache(pages=5), id="pages-a-number"),
    pytest.param(_crafted_cache(pages={"0": GOOD_PAGE}), id="pages-a-dict"),
    pytest.param(_crafted_cache(book=["not", "a", "name"]), id="book-a-list"),
    pytest.param(_crafted_cache(book=""), id="book-empty"), pytest.param(_crafted_cache(book=" \x1b "), id="book-controls"),
    pytest.param(_crafted_cache(book="x" * 5000), id="book-too-long"),
    pytest.param(_crafted_cache(language=3), id="language-a-number"),
    pytest.param(_crafted_cache(pages=[GOOD_PAGE, {**GOOD_PAGE, "fp": "zz"}]), id="a-page-unreadable"),
    pytest.param(_crafted_cache(pages=[{**GOOD_PAGE, "seq": float("inf")}]), id="seq-infinite"),  # was OverflowError
    pytest.param(_crafted_cache(pages=[{**GOOD_PAGE, "aspect": float("nan")}]), id="aspect-nan"),
    pytest.param(_crafted_cache(pages=[{**GOOD_PAGE, "bubbles": [{"box": [float("nan"), 0, 1, 1], "text": "x"}]}]),
                 id="box-nan"),
    pytest.param(_crafted_cache(pages=[{**GOOD_PAGE, "bubbles": [{"box": [0, 0, 1e300, 1], "text": "x"}]}]),
                 id="box-huge"),
    pytest.param(_crafted_cache(pages=[{**GOOD_PAGE, "bubbles": [{"box": [0, 0, 1, 1], "poly": [[0, float("-inf")]]}]}]),
                 id="poly-infinite"),
])
@pytest.mark.parametrize("replace", [False, True])
def test_hostile_content_is_refused_and_nothing_is_written(tmp_path, content, replace):
    store = CacheStore(tmp_path / "cache")
    _cache(store, _page(FP_A, "Mine"), language="English")
    before = {p.name: p.read_bytes() for p in store.cache_dir.iterdir()}
    with pytest.raises(backup.BackupError):
        backup.import_cache(store, _crafted(tmp_path, content), PASSPHRASE, replace=replace)
    assert {p.name: p.read_bytes() for p in store.cache_dir.iterdir()} == before


def test_control_characters_never_reach_a_terminal(tmp_path):
    """`taslation cache list` and `review` print the names and translations; what an import brings has no escape
    sequences left (newlines in a translation stay)."""
    evil = "\x1b]0;owned\x07\x1b[2J\x9b"
    content = _crafted_cache(book="Book" + evil, model="m" + evil, language="English" + evil, updated=evil, pages=[
        {**GOOD_PAGE, "bubbles": [{"box": [0.1, 0.1, 0.2, 0.2], "text": "Hi\n" + evil + "there", "note": evil,
                                   "flags": [evil, "small"]}]}])
    store = CacheStore(tmp_path / "cache")
    book, pages = backup.import_cache(store, _crafted(tmp_path, content), PASSPHRASE)
    assert (book, pages) == ("Book]0;owned[2J", 1)
    cache = store.open(book, MODEL, "English]0;owned[2J")
    assert cache.model == "m]0;owned[2J" and cache.language == "English]0;owned[2J" and cache.updated != evil
    bubble = cache.pages[0].bubbles[0]
    assert bubble.text == "Hi\n]0;owned[2Jthere" and bubble.note == "]0;owned[2J"
    assert bubble.flags == ["]0;owned[2J", "small"]
    assert not any(ch in path.read_text(encoding="utf-8") for path in store.cache_dir.iterdir() for ch in "\x1b\x07\x9b")


def _files(store: CacheStore) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in store.cache_dir.iterdir()}


def test_an_import_never_writes_into_another_books_cache(cli):
    """Two names can give one file name ("Pebble:Harbor 1" and "Pebble Harbor 1"; on Windows "QUILLPOND 1" and "Quillpond 1" too):
    the imported book gets a file of its own, and the other book's cache is neither merged into nor replaced, nor
    even copied."""
    home, here = CacheStore(cli / "home"), CacheStore(cli / "state" / "cache")  # here: the command line's
    _cache(home, _page(FP_B, "Theirs"), book="Pebble Harbor 1", language="English")
    out = cli / "x.stcache"
    backup.export_cache(home, "Pebble Harbor 1", out, PASSPHRASE)
    _cache(here, _page(FP_A, "Mine"), book="Pebble:Harbor 1", language="English")
    mine = here.path_for("Pebble:Harbor 1")
    original = mine.read_bytes()
    for replace in (False, True):
        assert backup.import_cache(here, out, PASSPHRASE, replace=replace) == ("Pebble Harbor 1", 1)
        assert mine.read_bytes() == original
    theirs = here.path_for("Pebble Harbor 1")
    assert theirs != mine and theirs.name == cache_names("Pebble Harbor 1")[1]
    assert _texts(here.open("Pebble Harbor 1", MODEL)) == {FP_B: ["Theirs"]}
    assert _texts(here.open("Pebble:Harbor 1", MODEL)) == {FP_A: ["Mine"]}
    assert not list(here.cache_dir.glob(mine.stem + ".before-import.*"))  # nothing of mine needed a copy
    assert main(["cache", "import", str(out), "--replace"]) == 0 and mine.read_bytes() == original
    assert sorted(b["book"] for b in here.list()) == ["Pebble Harbor 1", "Pebble:Harbor 1"]


def test_an_import_of_quillpond_never_touches_the_cache_of_QUILLPOND(tmp_path):
    """Only the letter case tells the names apart: one file name on Windows and macOS, two elsewhere; either way the
    imported book gets its own file and the other's stays byte for byte as it was."""
    home, here = CacheStore(tmp_path / "home"), CacheStore(tmp_path / "here")
    _cache(home, _page(FP_B, "Theirs"), book="Quillpond 1", language="English")
    out = tmp_path / "x.stcache"
    backup.export_cache(home, "Quillpond 1", out, PASSPHRASE)
    _cache(here, _page(FP_A, "Mine"), book="QUILLPOND 1", language="English")
    before = _files(here)
    for replace in (False, True):
        assert backup.import_cache(here, out, PASSPHRASE, replace=replace) == ("Quillpond 1", 1)
        after = _files(here)
        assert {name: after.get(name) for name in before} == before
    assert _texts(here.open("QUILLPOND 1", MODEL)) == {FP_A: ["Mine"]}
    assert _texts(here.open("Quillpond 1", MODEL)) == {FP_B: ["Theirs"]}
    assert sorted(b["book"] for b in here.list()) == ["QUILLPOND 1", "Quillpond 1"]


def test_an_import_whose_book_has_no_free_file_name_writes_nothing(cli, monkeypatch):
    """Both file names the book can have hold other books only for two names with the same hash (made so here):
    the import is refused with a NameClash, an OSError the window shows, and the command line says why."""
    from taslation import names

    monkeypatch.setattr(names, "name_hash", lambda _book: "00000000")
    home, here = CacheStore(cli / "home"), CacheStore(cli / "state" / "cache")
    _cache(home, _page(FP_B, "Theirs"), book="Pebble Harbor 1", language="English")
    out = cli / "x.stcache"
    backup.export_cache(home, "Pebble Harbor 1", out, PASSPHRASE)
    _cache(here, _page(FP_A, "Mine"), book="Pebble:Harbor 1", language="English")
    _cache(here, _page(FP_C, "A third"), book="Pebble?Harbor 1", language="English")
    before = _files(here)
    for replace in (False, True):
        with pytest.raises(backup.NameClash, match="holds the cache of 'Pebble:Harbor 1'") as raised:
            backup.import_cache(here, out, PASSPHRASE, replace=replace)
        assert isinstance(raised.value, OSError) and not isinstance(raised.value, backup.BackupError)
        assert _files(here) == before  # not even a copy
    with pytest.raises(SystemExit, match="^error: .*holds the cache of 'Pebble:Harbor 1'"):
        main(["cache", "import", str(out), "--replace"])
    with pytest.raises(SystemExit, match="no cache for 'Pebble Harbor 1'"):  # an export of it finds no cache either
        main(["cache", "export", "Pebble Harbor 1", "--out", str(cli / "y.stcache")])
    # the safety net: a file of another book where path_for pointed (another process wrote it meanwhile)
    monkeypatch.setattr(CacheStore, "path_for", lambda self, book, language="English": self.cache_dir / "Pebble_Harbor_1.json")
    with pytest.raises(backup.NameClash, match="move that file elsewhere first"):
        backup.import_cache(here, out, PASSPHRASE)
    assert _files(here) == before


def test_an_import_keeps_a_copy_of_what_it_changes(tmp_path, monkeypatch):
    real_strftime = time.strftime
    monkeypatch.setattr(time, "strftime", lambda fmt, *a: real_strftime(fmt.replace("%H%M%S", "120000"), *a))
    home, other = CacheStore(tmp_path / "home"), CacheStore(tmp_path / "other")
    _cache(home, _page(FP_A, "From the backup"))
    out = tmp_path / "x.stcache"
    backup.export_cache(home, BOOK, out, PASSPHRASE, LANGUAGE)
    _cache(other, _page(FP_A, "A later correction"), _page(FP_C, "Only here"))
    original = other.path_for(BOOK, LANGUAGE).read_bytes()
    assert backup.import_cache(other, out, PASSPHRASE, replace=True) == (BOOK, 1)
    backup.import_cache(other, out, PASSPHRASE)  # again in the same second: the first copy is not written over
    copies = list(other.cache_dir.glob("*.before-import.*.json"))
    assert len(copies) == 1 and copies[0].read_bytes() == original
    assert [b["book"] for b in other.list()] == [BOOK]  # a copy is no cache of its own
    assert other.delete(BOOK) and not list(other.cache_dir.glob("*.json"))  # and goes with the book


def test_an_import_over_the_caps_is_refused_and_nothing_is_written(tmp_path):
    """A file of the size cap holds some 500,000 minimal pages, far more than one book's cache: more than MAX_PAGES
    pages, or a page of more than MAX_BUBBLES_PER_PAGE bubbles, is refused before any page is read; the caps
    themselves are imported."""
    assert (backup.MAX_PAGES, backup.MAX_BUBBLES_PER_PAGE) == (5000, 500)
    store = CacheStore(tmp_path / "cache")
    _cache(store, _page(FP_A, "Mine"), language="English")
    before = _files(store)
    pages = [{"fp": f"{i:080x}", "aspect": 0.7, "seq": i, "bubbles": []} for i in range(backup.MAX_PAGES + 1)]
    bubble = {"box": [0.1, 0.1, 0.2, 0.2], "text": "x"}
    crowded = {**GOOD_PAGE, "bubbles": [bubble] * (backup.MAX_BUBBLES_PER_PAGE + 1)}
    for content, refusal in ((_crafted_cache(pages=pages), "more pages than one book's cache (at most 5000)"),
                             (_crafted_cache(pages=[GOOD_PAGE, crowded]), "more bubbles than TASlation reads")):
        for replace in (False, True):
            with pytest.raises(backup.TooLarge) as raised:
                backup.import_cache(store, _crafted(tmp_path, content), PASSPHRASE, replace=replace)
            assert refusal in str(raised.value) and "nothing was imported" in str(raised.value)
            assert _files(store) == before
    full = _crafted_cache(pages=[{**GOOD_PAGE, "bubbles": [bubble] * backup.MAX_BUBBLES_PER_PAGE}])
    assert backup.import_cache(store, _crafted(tmp_path, full), PASSPHRASE) == (BOOK, 1)
    assert backup.import_cache(store, _crafted(tmp_path, _crafted_cache(pages=pages[:-1])), PASSPHRASE,
                               replace=True) == (BOOK, backup.MAX_PAGES)  # a replace: no page compared


def test_an_export_over_the_caps_is_refused(tmp_path, monkeypatch):
    """An export never writes a file its import would refuse."""
    store = CacheStore(tmp_path / "cache")
    _cache(store, _page(FP_A, "One", "Two"), _page(FP_B, "Three"))
    out = tmp_path / "x.stcache"
    for pages, bubbles in ((1, 500), (5000, 1)):
        monkeypatch.setattr(backup, "MAX_PAGES", pages)
        monkeypatch.setattr(backup, "MAX_BUBBLES_PER_PAGE", bubbles)
        with pytest.raises(backup.TooLarge, match="cannot be exported"):
            backup.export_cache(store, BOOK, out, PASSPHRASE, LANGUAGE)
        assert not out.exists()
    monkeypatch.setattr(backup, "MAX_BUBBLES_PER_PAGE", 2)
    assert backup.export_cache(store, BOOK, out, PASSPHRASE, LANGUAGE) == 2


def _split(text: str) -> str:
    """*text* the way getpass on Windows reads it: one UTF-16 unit at a time, a character outside the BMP in halves."""
    raw = text.encode("utf-16-le")
    return "".join(chr(int.from_bytes(raw[i:i + 2], "little")) for i in range(0, len(raw), 2))


def test_a_passphrase_outside_the_bmp_gives_the_same_key_however_it_was_typed():
    whole = "\U00020bb7野家の牛丼が大好きです"  # the first character is outside the BMP
    halves = _split(whole)
    assert halves != whole and len(halves) == len(whole) + 1
    blob = backup.encrypt(b"x", whole)
    assert backup.decrypt(blob, halves) == b"x" and backup.decrypt(backup.encrypt(b"y", halves), whole) == b"y"
    broken = "correct horse battery \ud83c"  # half a character: no key, and nothing of the passphrase in the error
    for call in (lambda: backup.check_passphrase(broken), lambda: backup.encrypt(b"x", broken),
                 lambda: backup.decrypt(blob, broken)):
        with pytest.raises(backup.BackupError, match="broken character") as raised:
            call()
        assert "horse" not in str(raised.value) and "\ud83c" not in str(raised.value)
        assert raised.value.__context__ is None and raised.value.__cause__ is None


def test_the_command_line_reads_such_a_passphrase(cli, monkeypatch):
    _cache(CacheStore(cli / "state" / "cache"), _page(FP_A, "Line"), language="English")
    whole = "\U00020bb7野家 correct horse"
    monkeypatch.delenv(backup.PASSPHRASE_ENV)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: _split(whole))
    assert main(["cache", "export", BOOK, "--out", str(cli / "x.stcache")]) == 0
    monkeypatch.setenv(backup.PASSPHRASE_ENV, whole)  # the environment and the window give it whole
    assert main(["cache", "import", str(cli / "x.stcache")]) == 0


def test_a_full_width_space_is_an_ordinary_space():
    """A Japanese input method in full-width mode types U+3000 for the space bar: the same key as U+0020, and so is
    a no-break space (every Unicode Zs character maps to U+0020, as in RFC 8265's OpaqueString)."""
    ideographic = PASSPHRASE.replace(" ", "　")
    assert ideographic != PASSPHRASE
    assert backup.decrypt(backup.encrypt(b"x", ideographic), PASSPHRASE) == b"x"
    assert backup.decrypt(backup.encrypt(b"y", PASSPHRASE), ideographic) == b"y"
    assert backup.decrypt(backup.encrypt(b"z", PASSPHRASE), PASSPHRASE.replace(" ", " ")) == b"z"
    with pytest.raises(backup.WrongPassphrase):
        backup.decrypt(backup.encrypt(b"x", PASSPHRASE), PASSPHRASE.replace(" ", ""))  # no space is not a space
    backup.check_passphrase("eleven　chars")  # twelve characters, the space one of them
    with pytest.raises(backup.BackupError, match="at least 12 characters"):
        backup.check_passphrase("eleven　char")


@pytest.mark.parametrize("broken", [
    "correct horse\tbattery staple", "correct horse battery staple\r", "correct horse battery staple\n",
    "correct\x00horse battery staple", "correct horse \x1b[2J battery", "correct horse battery\x85staple",
], ids=["tab", "carriage-return", "line-feed", "nul", "escape", "c1-control"])
def test_a_control_character_is_refused_and_the_error_never_holds_the_passphrase(broken):
    blob = backup.encrypt(b"x", PASSPHRASE)
    for call in (lambda: backup.check_passphrase(broken), lambda: backup.encrypt(b"x", broken),
                 lambda: backup.decrypt(blob, broken)):
        with pytest.raises(backup.BrokenPassphrase, match="control character") as raised:
            call()
        assert not any("horse" in str(arg) or "staple" in str(arg) for arg in raised.value.args)
        assert raised.value.__context__ is None and raised.value.__cause__ is None


def test_each_kind_of_refusal_has_its_class(tmp_path, monkeypatch):
    """A window can show a fitting message by class, without reading the English sentence; the command line still
    prints the sentence. A damaged file stays a plain BackupError."""
    assert {"WrongPassphrase", "BrokenPassphrase", "UnreadableExport", "TooLarge"} <= set(backup.__all__)
    blob = backup.encrypt(b"payload", PASSPHRASE)
    with pytest.raises(backup.WrongPassphrase, match="^wrong passphrase or damaged file$"):
        backup.decrypt(blob, PASSPHRASE + "!")
    with pytest.raises(backup.WrongPassphrase):  # a changed byte: the tag cannot tell it from a wrong passphrase
        backup.decrypt(_changed(blob, "data", _flip), PASSPHRASE)
    with pytest.raises(backup.BrokenPassphrase, match="broken character"):
        backup.decrypt(blob, "correct horse battery \ud83c")
    store = CacheStore(tmp_path / "cache")
    for content in (_crafted_cache(pages=[GOOD_PAGE, {**GOOD_PAGE, "fp": "zz"}]), _crafted_cache(schema=2),
                    {"schema": 7, "volumes": {}}):
        with pytest.raises(backup.UnreadableExport, match="newer") as raised:
            backup.import_cache(store, _crafted(tmp_path, content), PASSPHRASE)
        assert "nothing was imported" in str(raised.value)
    with pytest.raises(backup.UnreadableExport, match="newer version of TASlation"):  # a later format's first line
        backup.decrypt(b"TASLATION-CACHE-2\n" + blob.split(b"\n", 1)[1], PASSPHRASE)
    for damaged in (b"TASLATION-CACHE-1\nnot json", b"TASLATION-CACHE-0\n{}", b"PK\x03\x04 a zip file",
                    _changed(blob, "kdf", lambda kdf: {**kdf, "comment": "x"}), _seal(b"not zlib at all")):
        with pytest.raises(backup.BackupError) as raised:
            backup.decrypt(damaged, PASSPHRASE)
        assert type(raised.value) is backup.BackupError, raised.value
    for content in (b"not json", _crafted_cache(schema="2"), _crafted_cache(book="")):
        with pytest.raises(backup.BackupError) as raised:
            backup.import_cache(store, _crafted(tmp_path, content), PASSPHRASE)
        assert type(raised.value) is backup.BackupError, raised.value
    monkeypatch.setattr(backup, "MAX_PAYLOAD", 1 << 20)
    with pytest.raises(backup.TooLarge, match="larger than TASlation unpacks"):
        backup.decrypt(_seal(zlib.compress(b"\0" * (2 << 20), 9)), PASSPHRASE)
    with pytest.raises(backup.TooLarge, match="cannot be exported"):
        backup.encrypt(b"x" * ((1 << 20) + 1), PASSPHRASE)
    path = tmp_path / "x.stcache"
    path.write_bytes(blob)
    monkeypatch.setattr(backup, "MAX_FILE", len(blob) - 1)
    with pytest.raises(backup.TooLarge, match="larger than any export"):
        backup.import_cache(store, path, PASSPHRASE)
    assert not store.cache_dir.exists()


def test_cache_export_never_writes_over_a_file_without_force(cli, monkeypatch):
    """Refused before the passphrase is asked for; the exit status is 1, as for every other error."""
    _cache(CacheStore(cli / "state" / "cache"), _page(FP_A, "Line"), language="English")
    out = cli / "notes.txt"
    out.write_text("a file of the reader's", encoding="utf-8")
    monkeypatch.delenv(backup.PASSPHRASE_ENV)  # and getpass fails the test
    with pytest.raises(SystemExit) as raised:
        main(["cache", "export", BOOK, "--out", str(out)])
    assert raised.value.code == f"error: {out} exists; pass --force to overwrite"
    assert out.read_text(encoding="utf-8") == "a file of the reader's"
    env = {**os.environ, backup.PASSPHRASE_ENV: PASSPHRASE, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, "-m", "taslation", "cache", "export", BOOK, "--out", str(out)],
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    assert proc.returncode == 1 and f"error: {out} exists; pass --force to overwrite" in proc.stderr
    assert out.read_text(encoding="utf-8") == "a file of the reader's"
    monkeypatch.setenv(backup.PASSPHRASE_ENV, PASSPHRASE)
    assert main(["cache", "export", BOOK, "--out", str(out), "--force"]) == 0
    assert out.read_bytes().startswith(backup.MAGIC + b"\n")
    assert main(["cache", "import", str(out)]) == 0


def test_the_export_appears_whole_or_not_at_all(tmp_path, monkeypatch):
    store = CacheStore(tmp_path / "cache")
    _cache(store, _page(FP_A, "Line"))
    out = tmp_path / "x.stcache"
    stray = tmp_path / "x.stcache.tmp"
    stray.write_text("a file of the reader's", encoding="utf-8")  # the temporary name exports used to take
    backup.export_cache(store, BOOK, out, PASSPHRASE, LANGUAGE)
    assert stray.read_text(encoding="utf-8") == "a file of the reader's"
    if os.name == "posix":
        assert out.stat().st_mode & 0o777 == 0o600
    names, previous = sorted(p.name for p in tmp_path.iterdir()), out.read_bytes()

    def full(*_args):
        raise OSError(28, "No space left on device")

    with monkeypatch.context() as m:
        m.setattr(os, "replace", full)
        with pytest.raises(OSError, match="No space"):
            backup.export_cache(store, BOOK, out, PASSPHRASE, LANGUAGE)
    assert out.read_bytes() == previous and sorted(p.name for p in tmp_path.iterdir()) == names  # no temporary left
    with pytest.raises(backup.BackupError, match="cache folder"):
        backup.export_cache(store, BOOK, store.cache_dir / "Another book.json", PASSPHRASE, LANGUAGE)


def test_export_and_import_never_touch_the_network(tmp_path):
    """Under the network guard (every attempt raises), not even a loopback call is made."""
    state = netguard.install(11434)
    netguard.record_allowed(True)
    blocked = len(state.blocked)
    try:
        store = CacheStore(tmp_path / "cache")
        _cache(store, _page(FP_A, "Line"))
        out = tmp_path / "x.stcache"
        backup.export_cache(store, BOOK, out, PASSPHRASE, LANGUAGE)
        assert backup.import_cache(CacheStore(tmp_path / "other"), out, PASSPHRASE) == (BOOK, 1)
        assert state.allowed == [] and len(state.blocked) == blocked
    finally:
        netguard.record_allowed(False)
        netguard.uninstall()
