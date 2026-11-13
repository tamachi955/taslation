"""The error log (``<state dir>/log.txt``) and Copy details: what went wrong and on what, and never what is read - no
page text, OCR text or translation, no book or window title, no path under the reader's profile but the state folder's
by name. A failing page job of the window is logged without its dialogue or its title."""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
import threading
import time
import tkinter
from tkinter import ttk
from pathlib import Path
from types import SimpleNamespace

import pytest

from taslation import cli, errorlog
from taslation.config import Settings
from taslation.i18n import set_language
from taslation.ui import copy_details
from taslation.ui.dialogs import about, caches
from taslation.ui.jobs import JobsMixin

DIALOGUE = "先輩、明日も来てくれますか？"
ENGLISH = "Senpai, will you come tomorrow too?"
TITLE = "My Secret Book Title"
CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def log_setup(tmp_path, monkeypatch):
    """The log of a window session in a scratch state folder (Ollama is not asked: a stand-in answers)."""
    monkeypatch.setattr(errorlog, "ollama_line", lambda port=None: "Ollama 0.0-test")
    settings = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models")
    path = errorlog.setup(settings, force=True)
    yield settings, path
    errorlog.shutdown()


def _read(path: Path) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in sorted(path.parent.glob(path.name + "*")))


# ------------------------------------------------------------------ scrubbing
def test_paths_are_named_by_their_folder_and_nothing_after_it(tmp_path):
    state, models = tmp_path / "state", tmp_path / "models"
    errorlog.set_roots(state, models)
    try:
        assert errorlog.scrub(f"cannot read {state / 'cache' / (TITLE + '.json')}") == "cannot read <state dir>\\\u2026"
        assert errorlog.scrub(f"no file {models / 'lama' / 'big-lama.safetensors'}") == "no file <models>\\\u2026"
        assert errorlog.scrub(f"bad '{Path.home() / 'Books' / TITLE}'") == "bad '<home>\\\u2026'"
        for path in (f"D:\\Books\\{TITLE}\\p1.png", f"D:/Books/{TITLE}/p1.png", f"\\\\nas\\books\\{TITLE}.cbz",
                     f"file:///D:/Books/{TITLE}.cbz", f"/home/someone/{TITLE}.cbz", f"~/Books/{TITLE}.cbz"):
            out = errorlog.scrub(f"could not open {path}")
            assert out == "could not open <path>" and TITLE not in out
        program = errorlog.scrub(f'File "{ROOT / "taslation" / "ui" / "jobs.py"}", line 3')
        assert program.replace("/", "\\") == 'File "<program>\\taslation\\ui\\jobs.py", line 3'
    finally:
        errorlog.set_roots()


def test_quoted_strings_go_unless_the_code_names_them_and_text_beyond_ascii_goes():
    assert errorlog.scrub(f"KeyError: '{DIALOGUE}'") == "KeyError: '\u2026'"
    assert errorlog.scrub(f"invalid literal for int(): {ENGLISH!r}") == "invalid literal for int(): '\u2026'"
    assert errorlog.scrub("KeyError: 'translated_text'", {"translated_text"}) == "KeyError: 'translated_text'"
    assert errorlog.scrub("No module named 'cv2'", {"cv2"}) == "No module named 'cv2'"
    assert errorlog.scrub("TypeError: 'NoneType' object is not callable") == "TypeError: 'NoneType' object is not callable"
    assert errorlog.scrub("can't do it") == "can't do it"  # an apostrophe is no quote
    assert errorlog.scrub(f"lettered {DIALOGUE} here") == "lettered \u2026 here"
    assert len(errorlog.scrub("x" * 1000)) == errorlog.MAX_LINE + 1


def test_tracebacks_name_files_in_the_program_and_keep_no_value(tmp_path):
    def letter(line, book):
        raise ValueError(f"could not letter {line!r} of {book!r} at {tmp_path / book / 'p1.png'}")

    try:
        try:
            letter(DIALOGUE, TITLE)
        except ValueError as e:
            raise RuntimeError("the page failed") from e
    except RuntimeError as e:
        text = errorlog.safe_traceback(e)
    assert 'File "tests/test_errorlog.py", line' in text.replace("\\", "/")
    assert "RuntimeError: the page failed" in text and "ValueError: could not letter '\u2026' of '\u2026' at" in text
    assert "raise ValueError(f\"could not letter {line!r}" in text  # the program's code, as it is
    assert DIALOGUE not in text and TITLE not in text and str(tmp_path) not in text and not CJK.search(text)
    assert errorlog.program_name("C:\\x\\.venv\\Lib\\site-packages\\torch\\nn\\module.py") == "site-packages/torch/nn/module.py"
    assert errorlog.program_name(f"D:\\{TITLE}\\x.py") == "x.py"
    assert errorlog.program_name("D:\\x\\先輩.py") == "<path>"
    assert errorlog.program_name("<frozen importlib._bootstrap>") == "<frozen importlib._bootstrap>"


# ------------------------------------------------------------------ the log file
class _Stop(BaseException):
    """Ends the worker loop of the test (it runs until the window closes)."""


class _Jobs:
    def __init__(self, jobs):
        self._jobs = list(jobs)

    def get(self):
        if not self._jobs:
            raise _Stop
        return self._jobs.pop(0)


def test_a_failing_page_job_logs_what_failed_and_no_dialogue_title_or_path(log_setup, tmp_path):
    settings, path = log_setup
    viewer_title = f"{TITLE} - a viewer"
    page = tmp_path / "Books" / TITLE / "p001.png"

    def translate(line):
        raise ValueError(f"the translator choked on {line!r} ({ENGLISH!r}) of {viewer_title!r} in {page}")

    def page_job():
        for line in (DIALOGUE,):
            translate(line)

    posted = []
    window = SimpleNamespace(_jobs=_Jobs([page_job]), _post=lambda kind, **data: posted.append((kind, data)))
    with pytest.raises(_Stop):
        JobsMixin._worker_loop(window)
    assert [kind for kind, _data in posted] == ["error", "idle"]
    errorlog.shutdown()  # (the file closed: written whole)
    text = _read(path)
    assert "ERROR taslation.ui.jobs: a job of the window failed" in text
    assert "ValueError: the translator choked on '\u2026' ('\u2026') of '\u2026' in <home>\\\u2026" in text
    assert "taslation/ui/jobs.py" in text.replace("\\", "/")
    for private in (DIALOGUE, ENGLISH, TITLE, "Secret", "Senpai", str(tmp_path), "Books", "p001"):
        assert private not in text, private
    assert not CJK.search(text)
    assert errorlog.last_error() is None  # (gone with the session)


def test_the_log_starts_with_the_environment_and_the_changed_settings_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(errorlog, "ollama_line", lambda port=None: "Ollama 0.0-test")
    settings = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", min_font_size=10,
                        font_path=str(tmp_path / "fonts" / "mine.ttf"), target_language="Japanese")
    path = errorlog.setup(settings, force=True)
    try:
        assert path == tmp_path / "state" / "log.txt"
        handler = next(h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler))
        assert (handler.maxBytes, handler.backupCount) == (errorlog.MAX_BYTES, errorlog.BACKUPS)
        assert errorlog.setup(settings, force=True) == path  # once
        assert sum(isinstance(h, logging.handlers.RotatingFileHandler) for h in logging.getLogger().handlers) == 1
    finally:
        errorlog.shutdown()
    text = path.read_text(encoding="utf-8")
    assert f"TASlation {errorlog.program_version()}" in text and "Python " in text and "Tk " in text
    assert "min_font_size = 10" in text and "font_path = (set)" in text and "target_language = Japanese" in text
    assert "mine.ttf" not in text and str(tmp_path) not in text


def test_under_pytest_nothing_is_written_unless_asked(tmp_path):
    settings = Settings(state_dir=tmp_path / "state")
    assert errorlog.setup(settings) is None
    assert not (tmp_path / "state").exists() and "sys" not in errorlog._hooks
    errorlog.shutdown()


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_what_nobody_caught_is_logged_from_threads_and_tk_callbacks(log_setup, hidden_root, capsys):
    settings, path = log_setup

    def fail():
        raise RuntimeError(f"lost {TITLE!r}")

    thread = threading.Thread(target=fail)
    thread.start()
    thread.join()
    try:
        raise LookupError(f"no {DIALOGUE}")
    except LookupError:
        kind, value, tb = sys.exc_info()
    tkinter.Tk.report_callback_exception(hidden_root, kind, value, tb)
    capsys.readouterr()
    errorlog.shutdown()
    text = _read(path)
    assert "an error nobody caught in a thread" in text and "RuntimeError: lost '\u2026'" in text
    assert "an error in a window callback" in text and "LookupError: no \u2026" in text
    assert TITLE not in text and DIALOGUE not in text
    assert tkinter.Tk.report_callback_exception is not None and "tk" not in errorlog._hooks


# ------------------------------------------------------------------ Copy details
def test_the_details_hold_the_environment_the_settings_and_the_last_error(log_setup, tmp_path):
    settings, _path = log_setup
    settings.uppercase = True
    settings.config_path = tmp_path / "taslation.toml"
    try:
        raise KeyError(TITLE)
    except KeyError:
        logging.getLogger("taslation.ui.jobs").exception("a job of the window failed")
    text = errorlog.details_text(settings)
    assert text.startswith("TASlation details for a report (no text, titles or file names from your books):")
    assert "Ollama 0.0-test" in text and "uppercase = True" in text and "translation into English" in text
    assert "Settings file: <home>\\\u2026 (taslation.toml)" in text or "Settings file: <path> (taslation.toml)" in text
    assert "Last error (" in text and "KeyError: '\u2026'" in text
    assert TITLE not in text and str(tmp_path) not in text


def test_without_an_error_the_details_say_so():
    assert errorlog.details_text(Settings(), ollama=False).endswith("Last error: none in this session")


def test_ollama_s_version_is_asked_on_this_computer_without_a_proxy(monkeypatch):
    import io
    import urllib.request

    asked = []

    class Opener:
        def open(self, url, timeout):
            asked.append((url, timeout))
            return io.BytesIO(b'{"version": "0.40.0"}')

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: asked.append(handlers) or Opener())
    assert errorlog.ollama_line(11434) == "Ollama 0.40.0"
    assert isinstance(asked[0][0], urllib.request.ProxyHandler) and asked[1] == (
        "http://127.0.0.1:11434/api/version", errorlog.OLLAMA_TIMEOUT_S)

    class Down:
        def open(self, url, timeout):
            raise OSError("refused")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Down())
    assert errorlog.ollama_line(11500) == "Ollama: not answering on localhost:11500"


def test_about_copies_the_details(hidden_root, tmp_path, monkeypatch):
    copied = []
    monkeypatch.setattr(copy_details, "put_on_clipboard", lambda widget, text: copied.append(text))
    monkeypatch.setattr(errorlog, "ollama_line", lambda port=None: "Ollama 0.0-test")
    monkeypatch.setattr(about, "place_window", lambda win, parent=None: None)
    d = about.AboutDialog(hidden_root, tmp_path, root=ROOT)
    assert str(d.details_btn.cget("text")) == "Copy details"
    d.details_btn.invoke()
    assert len(copied) == 1 and copied[0].startswith("TASlation details for a report")
    assert str(d.details_btn.cget("text")) == "Copied"
    set_language("ja")
    d = about.AboutDialog(hidden_root, tmp_path, root=ROOT)
    assert str(d.details_btn.cget("text")) == "詳細をコピー"


def test_about_shows_the_date_the_installer_and_the_update_print(hidden_root, tmp_path, monkeypatch):
    package = tmp_path / "taslation"
    for name, when in (("__init__.py", 1_700_000_000), ("ui/deep/newest.py", 1_760_000_000), ("notes.txt", 1_790_000_000)):
        (package / name).parent.mkdir(parents=True, exist_ok=True)
        (package / name).write_text("x")
        os.utime(package / name, (when, when))
    assert errorlog.release_date(package) == time.strftime("%Y-%m-%d", time.localtime(1_760_000_000))  # .py files only
    assert errorlog.release_date(tmp_path / "empty") == ""
    monkeypatch.setattr(about, "place_window", lambda win, parent=None: None)
    monkeypatch.setattr(errorlog, "release_date", lambda package=None: "2026-11-11")
    d = about.AboutDialog(hidden_root, tmp_path, root=ROOT)
    assert d.date_text == "Program files dated 2026-11-11"
    assert any(str(w.cget("text")) == d.date_text for w in _all_labels(d))
    d.destroy()
    monkeypatch.setattr(errorlog, "release_date", lambda package=None: "")
    d = about.AboutDialog(hidden_root, tmp_path, root=ROOT)
    assert d.date_text == "" and not any("dated" in str(w.cget("text")) for w in _all_labels(d))
    d.destroy()
    set_language("ja")
    monkeypatch.setattr(errorlog, "release_date", lambda package=None: "2026-11-11")
    d = about.AboutDialog(hidden_root, tmp_path, root=ROOT)
    assert d.date_text == "プログラムの日付 2026-11-11"
    d.destroy()
    set_language("en")


def _all_labels(widget):
    for child in widget.winfo_children():
        if isinstance(child, ttk.Label):
            yield child
        yield from _all_labels(child)


def test_an_error_box_gets_copy_details_and_a_question_or_a_note_does_not(hidden_root, monkeypatch):
    monkeypatch.setattr(caches, "place_window", lambda win, parent=None: None)
    copied = []
    monkeypatch.setattr(copy_details, "put_on_clipboard", lambda widget, text: copied.append(text))
    monkeypatch.setattr(errorlog, "ollama_line", lambda port=None: "Ollama 0.0-test")
    error = caches.WarningBox(hidden_root, "TASlation", "Something went wrong on this page.", alone=True)
    question = caches.WarningBox(hidden_root, "TASlation", "Delete?", icon="question")
    note = caches.WarningBox(hidden_root, "TASlation", "Translate a page first.", alone=True, icon="info")
    assert copy_details.is_error_box(error) and not copy_details.is_error_box(question)
    assert not copy_details.is_error_box(note) and not copy_details.is_error_box(hidden_root)
    button = copy_details.add_to_error_box(error)
    assert button is not None and copy_details.add_to_error_box(error) is None  # once
    assert button.master is error.continue_btn.master and button.winfo_manager() == "pack"
    assert copy_details.add_to_error_box(question) is None and copy_details.add_to_error_box(note) is None
    button.invoke()
    assert len(copied) == 1 and str(button.cget("text")) == "Copied"
    before = hidden_root.bind_class("Toplevel", "<Map>")
    try:
        copy_details.watch_error_boxes(hidden_root)
        assert hidden_root.bind_class("Toplevel", "<Map>") != before
    finally:
        hidden_root.bind_class("Toplevel", "<Map>", before)


# ------------------------------------------------------------------ the command line
def test_the_window_s_start_sets_up_the_log_and_other_commands_do_not(tmp_path, monkeypatch):
    from taslation import netguard

    made = []
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(errorlog, "setup", lambda settings, force=False: made.append(settings.state_dir))
    monkeypatch.setitem(cli.COMMANDS, "gui", lambda args, settings: 0)
    monkeypatch.setitem(cli.COMMANDS, "doctor", lambda args, settings: 0)
    try:
        assert cli.main(["gui"]) == 0 and made == [tmp_path / "state"]
        assert cli.main(["doctor"]) == 0 and len(made) == 1
    finally:
        netguard.uninstall()


def test_a_start_that_fails_is_logged_and_its_box_offers_the_details(monkeypatch, caplog):
    import ctypes

    def fail(args, settings):
        raise RuntimeError("no display")

    monkeypatch.setattr(cli, "cmd_gui", fail)
    with caplog.at_level(logging.ERROR, logger="taslation"):
        with pytest.raises(RuntimeError):
            cli._gui(SimpleNamespace(), Settings())
    assert "the window could not start" in caplog.text
    if sys.platform != "win32":
        return
    seen, copied = [], []
    monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", lambda owner, text, title, flags: seen.append(flags) or 6)
    monkeypatch.setattr(errorlog, "copy_to_clipboard", copied.append)
    monkeypatch.setattr(errorlog, "details_text", lambda: "the details")
    monkeypatch.setattr(sys, "stderr", None)
    cli._complain("TASlation could not start.", details=True)
    assert seen == [0x10 | 0x4] and copied == ["the details"]
    cli._complain("config error: x")
    assert seen[-1] == 0x10 and copied == ["the details"]
