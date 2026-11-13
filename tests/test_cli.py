from __future__ import annotations

import io
import sys
from types import SimpleNamespace

import pytest
from conftest import FIXTURES, requires_ocr

from taslation import cli, netguard
from taslation.cli import main

BOOK = "A book of my own, volume 1"
PASSPHRASE = "correct horse battery staple"


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    yield
    netguard.uninstall()


class _Unread:
    """A stdin that fails the test when it is read: nothing may be asked."""

    def readline(self, *_args):
        pytest.fail("read from stdin")

    read = readline


def _paragraph(text: str) -> str:
    return " ".join(text.split())


def _files(folder) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in folder.iterdir()}


@pytest.fixture
def cached(tmp_path, monkeypatch):
    """A cached book in the command line's state folder, the passphrase in the environment (a cheap key), and
    neither getpass nor stdin read unless a test gives them an answer."""
    pytest.importorskip("cryptography")
    from taslation import backup
    from taslation.cache import CacheStore, CachedBubble, CachedPage

    monkeypatch.setitem(backup.KDF, "n", 2 ** 14)
    monkeypatch.setenv(backup.PASSPHRASE_ENV, PASSPHRASE)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: pytest.fail("asked for a passphrase"))
    monkeypatch.setattr("sys.stdin", _Unread())
    store = CacheStore(tmp_path / "state" / "cache")
    cache = store.open(BOOK, "qwen3.5:4b", "English")
    cache.add(CachedPage(fingerprint="a" * 80, aspect=0.7, seq=0,
                         bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text="Line")]))
    cache.save()
    return store


def test_cache_export_and_import_say_what_the_file_is_for_before_the_passphrase(cached, tmp_path, monkeypatch, capsys):
    """The note on stderr, a paragraph that starts with "Note:", printed before the passphrase is asked for; nothing
    is asked but the passphrase (stdin is never read), and stdout keeps its one line of result."""
    from taslation import backup

    monkeypatch.delenv(backup.PASSPHRASE_ENV)
    said: list[str] = []

    def typed(*_args, **_kwargs):
        said.append(capsys.readouterr().err)  # what stderr held when the passphrase was asked for
        return PASSPHRASE

    monkeypatch.setattr("getpass.getpass", typed)
    out = tmp_path / "mine.stcache"
    for argv, note, result in ((["cache", "export", BOOK, "--out", str(out)], cli.EXPORT_NOTE, "exported"),
                               (["cache", "import", str(out)], cli.IMPORT_NOTE, "imported")):
        said.clear()
        assert main(argv) == 0
        captured = capsys.readouterr()
        assert said[0].startswith("Note: ") and _paragraph(said[0]) == note  # before the passphrase, all of it
        assert all(len(line) <= cli.NOTE_WIDTH for line in said[0].splitlines()) and "\n\n" in said[0]
        assert "Continue?" not in "".join(said) + captured.err
        assert captured.out.startswith(result) and captured.out.count("\n") == 1  # the one line of result
    assert cli.EXPORT_NOTE.startswith("Note: This file will contain the translated text of the book.")
    assert cli.IMPORT_NOTE.startswith("Note: Import only a file you made yourself")


def test_a_refused_cache_export_or_import_prints_no_note(cached, tmp_path, capsys):
    out = tmp_path / "there.stcache"
    out.write_text("a file of the reader's", encoding="utf-8")
    for argv, error in ((["cache", "export", "Never translated", "--out", str(tmp_path / "x.stcache")], "no cache for"),
                        (["cache", "export", BOOK, "--out", str(out)], "exists; pass --force"),
                        (["cache", "import", str(tmp_path / "missing.stcache")], "not found")):
        with pytest.raises(SystemExit, match=error):
            main(argv)
        assert "Note:" not in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "a file of the reader's"


@pytest.mark.parametrize("answer", ["n\n", "\n", "", "nope\n"], ids=["n", "enter", "end-of-input", "nope"])
def test_confirm_asks_and_anything_but_yes_exits_1_with_nothing_touched(cached, tmp_path, monkeypatch, capsys, answer):
    from taslation import backup

    made = tmp_path / "made-earlier.stcache"
    backup.export_cache(cached, BOOK, made, PASSPHRASE, "English")
    monkeypatch.delenv(backup.PASSPHRASE_ENV)  # and getpass fails the test: the passphrase is never asked for
    files, made_bytes = _files(cached.cache_dir), made.read_bytes()
    out = tmp_path / "new.stcache"
    for argv, note, cancelled in ((["cache", "export", BOOK, "--out", str(out), "--confirm"], cli.EXPORT_NOTE,
                                   "cancelled: nothing was exported"),
                                  (["cache", "import", str(made), "--confirm", "--replace"], cli.IMPORT_NOTE,
                                   "cancelled: nothing was imported")):
        monkeypatch.setattr("sys.stdin", io.StringIO(answer))
        assert main(argv) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("Note: ") and _paragraph(captured.err).startswith(note + " Continue? [y/N]")
        assert captured.err.rstrip().endswith(cancelled)
        if not answer:  # the input ended without a line: the answer's line is ended for it
            assert captured.err.rstrip().endswith("Continue? [y/N] \n" + cancelled)
        assert not out.exists() and _files(cached.cache_dir) == files and made.read_bytes() == made_bytes


def test_confirm_and_yes_go_on_to_the_passphrase(cached, tmp_path, monkeypatch, capsys):
    out = tmp_path / "mine.stcache"
    for answer in ("y\n", "Yes\n", " YES \n"):
        monkeypatch.setattr("sys.stdin", io.StringIO(answer))
        assert main(["cache", "export", BOOK, "--out", str(out), "--force", "--confirm"]) == 0
        captured = capsys.readouterr()
        assert "Continue? [y/N]" in captured.err and captured.out.startswith("exported") and out.is_file()
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
    assert main(["cache", "import", str(out), "--confirm"]) == 0
    assert "merged" in capsys.readouterr().out
    assert cli.build_parser().parse_args(["cache", "export", BOOK]).confirm is False  # off unless asked for


def test_cache_list_empty(capsys):
    assert main(["cache", "list"]) == 0
    assert "no caches" in capsys.readouterr().out


def _review_book(tmp_path, language: str) -> None:
    from taslation.cache import CacheStore, CachedBubble, CachedPage
    from taslation.config import Settings

    cache = CacheStore(tmp_path / "state" / "cache").open(BOOK, Settings().ollama_model, language)
    cache.add(CachedPage(fingerprint="a" * 80, aspect=0.7, seq=0, bubbles=[
        CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text="Line", flags=["rendering"])]))
    cache.save()


def test_review_takes_the_configured_language_when_none_is_given(tmp_path, capsys):
    _review_book(tmp_path, "English")
    assert main(["review", "--book", BOOK]) == 0
    assert "1 of 1 cached translation(s) flagged" in capsys.readouterr().out
    assert main(["--language", "German", "review", "--book", BOOK]) == 0  # before the command, too
    assert f"no cached translations for {BOOK!r} in German; it has some in English (--language)" in capsys.readouterr().out
    assert main(["review", "--book", BOOK, "--language", "English"]) == 0
    assert "1 of 1 cached translation(s) flagged" in capsys.readouterr().out


def test_review_says_which_languages_a_book_has_when_it_has_none_in_this_one(tmp_path, capsys):
    _review_book(tmp_path, "German")
    _review_book(tmp_path, "French")
    assert main(["review", "--book", BOOK]) == 0
    assert f"no cached translations for {BOOK!r} in English; it has some in French, German (--language)" in (
        capsys.readouterr().out)
    assert main(["review", "--book", "Never translated"]) == 0
    assert capsys.readouterr().out.strip() == "no cached translations for 'Never translated'"


def test_cache_path(capsys, tmp_path):
    assert main(["cache", "path"]) == 0
    assert str(tmp_path) in capsys.readouterr().out


def test_non_loopback_ollama_url_is_a_config_error(capsys):
    assert main(["--ollama-url", "http://example.com:11434", "cache", "list"]) == 2
    assert "loopback" in capsys.readouterr().err


def test_bad_port_is_a_config_error(capsys):
    assert main(["--ollama-url", "http://127.0.0.1:abc", "cache", "list"]) == 2
    assert "port" in capsys.readouterr().err


def test_guard_is_installed_by_main():
    main(["cache", "list"])
    assert netguard.is_installed()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_command(capsys):
    assert main(["windows"]) == 0


def test_doctor_runs(capsys):
    rc = main(["doctor"])
    out = capsys.readouterr().out
    assert rc in (0, 1)
    assert "Network guard: ON" in out


def test_the_window_starts_with_auto_on_unless_told_otherwise(monkeypatch):
    from taslation import cli

    parser = cli.build_parser()
    assert parser.parse_args(["gui"]).auto is True and parser.parse_args(["gui", "--auto"]).auto is True
    assert parser.parse_args(["gui", "--no-auto"]).auto is False
    assert parser.parse_args(["gui", "--reading"]).reading and not parser.parse_args(["gui"]).reading
    seen = []
    monkeypatch.setitem(cli.COMMANDS, "gui", lambda args, settings: seen.append(args) or 0)
    assert main([]) == 0 and main(["gui", "--no-auto", "--reading"]) == 0
    assert (seen[0].auto, seen[0].reading) == (True, False) and (seen[1].auto, seen[1].reading) == (False, True)


@requires_ocr
def test_translate_echo_on_sample_page(capsys):
    rc = main(["translate", str(FIXTURES / "sample_page.png"), "--translator", "echo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "translated" in out


# ------------------------------------------------------------------ the book's name from the window's title
class Reached(Exception):
    """The command got as far as its pipeline (nothing is read or loaded here)."""


@pytest.fixture
def viewer(monkeypatch, tmp_path):
    """The window the command picks (the test's), a capture of it, and the book the pipeline would be built for; the
    (invented) viewer it shows is one this computer learned (tests/test_viewer_parts.py)."""
    from PIL import Image

    from taslation import capture, viewerparts
    from taslation.capture import WindowInfo

    viewerparts.use(tmp_path / "state")  # the command's state folder (`state_folder`)
    viewerparts.change(lambda memory: memory.learn(["Yomizuq"]))
    state = SimpleNamespace(title="Yomizuq - Google Chrome", books=[])

    def build(settings, translator_kind="ollama", book=None, with_ocr=True, series=None, **_kwargs):
        state.books.append(book)
        raise Reached

    monkeypatch.setattr(cli, "_pick_window", lambda query, wait=0.0: WindowInfo(
        hwnd=1, title=state.title, class_name="Chrome_WidgetWin_1", pid=1, rect=(0, 0, 100, 100)))
    monkeypatch.setattr(capture, "enable_dpi_awareness", lambda: None)
    monkeypatch.setattr(capture, "capture_window", lambda hwnd, *a, **k: Image.new("RGB", (100, 100), "white"))
    monkeypatch.setattr(cli, "build_pipeline", build)
    return state


@pytest.mark.parametrize("command", ["batch", "read"])
def test_batch_and_read_refuse_a_window_title_that_names_no_book_unless_given_one(viewer, command):
    with pytest.raises(SystemExit) as refused:  # a browser-based viewer's tab names the viewer, whatever book it shows
        main([command, "--window", "Yomizuq"])
    assert refused.value.code == ("error: the window is titled 'Yomizuq - Google Chrome', which names no book; pass "
                                  "--book NAME")
    assert viewer.books == []  # nothing was read under it
    with pytest.raises(Reached):
        main([command, "--window", "Yomizuq", "--book", "Star Road 1"])
    assert viewer.books == ["Star Road 1"]
    with pytest.raises(SystemExit) as refused:  # nor a --book that names none
        main([command, "--window", "Yomizuq", "--book", " yomizuq"])
    assert refused.value.code == "error: --book ' yomizuq' names no book; pass the book's own name"
    viewer.title = "Star Road 2 - Google Chrome"  # a title that names the book: its name, as before
    with pytest.raises(Reached):
        main([command, "--window", "Star"])
    assert viewer.books == ["Star Road 1", "Star Road 2"]


def test_annotations_list_counts_what_each_book_has_and_never_its_text(tmp_path, capsys):
    import json

    from taslation.annotations import AnnotationStore

    assert main(["annotations", "list"]) == 0
    assert capsys.readouterr().out.startswith("no annotations in ")
    store = AnnotationStore(tmp_path / "state" / "annotations")
    ann = store.open(BOOK)
    fp1, fp2, fp3 = "1" * 80, "2" * 80, "3" * 80
    ann.add_box(fp1, 0.7, (0.1, 0.1, 0.2, 0.2))
    ann.add_box(fp1, 0.7, (0.5, 0.5, 0.6, 0.6))
    ann.add_box(fp2, 0.7, (0.1, 0.1, 0.3, 0.3), kind="ignore")
    ann.page(fp2, 0.7).set_note((0.1, 0.1, 0.3, 0.3), speaker="Secret Speaker", note="a secret remark")
    ann.page(fp2, 0.7).order = [(0.1, 0.1, 0.3, 0.3), (0.5, 0.5, 0.6, 0.6)]
    ann.page(fp3, 0.7).skip = True
    ann.save()
    assert main(["annotations", "list"]) == 0
    out = capsys.readouterr().out
    assert (f"{BOOK!r}: 3 page(s) with rectangles or facts; rectangles 2 add, 1 ignore; 1 note(s), 1 skipped page(s), "
            "1 reading order(s); updated ") in out
    assert str(ann.path) in out and "secret" not in out.lower()
    assert main(["annotations", "list", "--json"]) == 0
    raw = capsys.readouterr().out
    (entry,) = json.loads(raw)
    assert (entry["book"], entry["pages"], entry["add"], entry["ignore"], entry["boxes"]) == (BOOK, 3, 2, 1, 3)
    assert (entry["region_notes"], entry["skipped"], entry["orders"], entry["file"]) == (1, 1, 1, str(ann.path))
    assert "secret" not in raw.lower()


def _windowless(monkeypatch):
    """As `pythonw` runs from the Start menu: no stderr, and message boxes written down instead of shown."""
    boxes = []
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(cli, "_complain", lambda text, details=False: boxes.append(text))
    return boxes


def test_a_window_that_cannot_open_says_so_in_a_box(monkeypatch):
    def fail(args, settings):
        raise RuntimeError("no display")

    boxes = _windowless(monkeypatch)
    monkeypatch.setattr(cli, "cmd_gui", fail)
    assert cli.main(["gui"]) == 1
    assert len(boxes) == 1 and "TASlation could not start." in boxes[0] and "no display" in boxes[0]
    assert "install.cmd" in boxes[0]


def test_a_settings_mistake_says_so_in_a_box(monkeypatch):
    def fail(args):
        raise cli.ConfigError("bad line 3")

    boxes = _windowless(monkeypatch)
    monkeypatch.setattr(cli, "load_settings", fail)
    assert cli.main(["gui"]) == 2
    assert boxes == ["config error: bad line 3"]


def test_with_a_console_the_traceback_stays(monkeypatch):
    def fail(args, settings):
        raise RuntimeError("no display")

    monkeypatch.setattr(cli, "cmd_gui", fail)
    with pytest.raises(RuntimeError):
        cli.main(["gui"])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows message box")
def test_no_stderr_means_the_message_box(monkeypatch):
    import ctypes

    seen = []
    monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", lambda owner, text, title, flags: seen.append((text, title)))
    monkeypatch.setattr(sys, "stderr", None)
    cli._complain("what went wrong")
    assert seen == [("what went wrong", "TASlation")]


def test_stderr_means_no_box(monkeypatch, capsys):
    import ctypes

    monkeypatch.setattr(ctypes, "windll", None, raising=False)  # would fail if it were reached
    cli._complain("what went wrong")
    assert "what went wrong" in capsys.readouterr().err


def test_the_help_names_the_models_the_default_chooses_and_no_old_one():
    from taslation.translate.models import PLAMO, QWEN

    text = " ".join(cli.build_parser().format_help().split())
    assert '"auto": the target language chooses' in text
    assert PLAMO.display_name in text and QWEN.display_name in text
    for old in ("Shisa", "qwen3:4b", "TranslateGemma", "Index-Translate"):
        assert old not in text
