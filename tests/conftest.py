from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from taslation import health, names, protect, viewerparts
from taslation.config import Settings
from taslation.detect import layout
from taslation.ocr.charspot import check_model_dir
from taslation.ollama_start import OllamaStarter
from taslation.render import artwork
from taslation.ui import live, viewers

FIXTURES = Path(__file__).parent / "fixtures"


def ocr_installed() -> bool:
    return not check_model_dir(Settings().ocr_model_dir)


requires_ocr = pytest.mark.skipif(not ocr_installed(), reason="OCR model not downloaded (run setup_models.py)")
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture(autouse=True)
def nothing_starts_ollama(monkeypatch):
    """No test starts a real Ollama, or asks whether one runs, by way of the window's start or a command
    (tests/test_ollama_start.py puts the real thing back, with fakes under it)."""
    monkeypatch.setattr(OllamaStarter, "start", lambda self, cancel=None: None)


@pytest.fixture(autouse=True)
def no_real_window_restored(monkeypatch):
    """No test shows a real minimised window again as a viewer is chosen (the tests' handles are made up; one of them
    could be a real window of this machine); tests/test_minimised_viewer.py patches its own in."""
    monkeypatch.setattr(viewers, "unminimise_window", lambda hwnd, below=None: False)


@pytest.fixture(autouse=True)
def no_enlarged_window_kept(monkeypatch):
    """No test keeps an enlarged window in a state folder, nor puts back one a session before left (some stand-ins'
    settings have the default, real state folder); tests/test_enlarge_recovery.py patches its own in."""
    monkeypatch.setattr(viewers, "keep_enlarged", lambda state_dir, enlarged: None)
    monkeypatch.setattr(viewers, "forget_enlarged", lambda state_dir, hwnd: None)
    monkeypatch.setattr(viewers, "put_back_enlarged", lambda state_dir: 0)


@pytest.fixture(autouse=True)
def no_real_window_asked_to_repaint(monkeypatch):
    """No test asks a real window to paint itself anew, nor counts the windows over one, as the window finds out
    whether a viewer draws while covered (the tests' handles are made up; one of them could be a real window of this
    machine); tests/test_covered_viewer.py patches its own in."""
    monkeypatch.setattr(live, "ask_repaint", lambda hwnd: False)
    monkeypatch.setattr(live, "fully_covered", lambda hwnd: False)


def _real_state_folder(state_dir) -> bool:
    """Whether *state_dir* is (or is in) a state folder of this machine's own: the home folder's, by any of the
    project's names."""
    try:
        folder = Path(state_dir).expanduser().resolve()
    except (OSError, RuntimeError):
        return True
    for name in (".taslation", ".selftrans", ".cleantrans"):
        real = (Path.home() / name).resolve()
        if folder == real or real in folder.parents:
            return True
    return False


@pytest.fixture(autouse=True)
def nothing_learned_of_real_viewers(monkeypatch):
    """Each test starts with nothing learned of the viewers and nothing held back, and none reads or writes what was
    learned in this machine's own state folder (some stand-ins' settings have the default, real state folder: there
    what is learned stays in memory); what a test learned is gone after it."""
    real_use = viewerparts.use
    real_use(None)

    def use(state_dir):
        return real_use(None if state_dir is None or _real_state_folder(state_dir) else state_dir)

    monkeypatch.setattr(viewerparts, "use", use)
    yield
    real_use(None)


@pytest.fixture(autouse=True)
def real_window_settings_left_alone(monkeypatch):
    """No test writes into ui.json of this machine's own state folder (some stand-ins' settings have the default, real
    state folder: a whole-book run that ends there would keep its translation's pace in the reader's own file, as one
    did): there the write does nothing; a test's own folder gets the real thing."""
    from taslation import i18n

    real_save = i18n._save_ui_settings

    def save(state_dir, data):
        if not _real_state_folder(state_dir):
            real_save(state_dir, data)

    monkeypatch.setattr(i18n, "_save_ui_settings", save)


@pytest.fixture(autouse=True)
def real_saved_files_left_alone(monkeypatch):
    """No test protects, or opens to count, the saved files of this machine's own state folder at a start (some
    stand-ins' settings have the default, real state folder): there `protect.migrate` and `protect.survey` find
    nothing; a test's own folder gets the real thing. Nor does a test say a file an earlier test set aside
    (`names.take_set_aside`: the list is the process's)."""
    real_migrate, real_survey = protect.migrate, protect.survey

    def migrate(state_dir):
        return protect.Tally() if _real_state_folder(state_dir) else real_migrate(state_dir)

    def survey(state_dir, check=True):
        return protect.Tally(checked=check) if _real_state_folder(state_dir) else real_survey(state_dir, check)

    monkeypatch.setattr(protect, "migrate", migrate)
    monkeypatch.setattr(protect, "survey", survey)
    names.take_set_aside()
    yield
    names.take_set_aside()


@pytest.fixture(autouse=True)
def classical_unless_asked(request, monkeypatch):
    """A test's pipeline detects and erases the classical way, whatever the models folder holds and whatever GPU this
    machine has (art_erase "auto", the default, runs LaMa where torch has CUDA: here torch's answer is no); one that is
    about the layout and inpainting models is marked ``page_models``, and there torch is asked afresh (or the test
    stands in for its answer)."""
    if request.node.get_closest_marker("page_models") is None:
        monkeypatch.setattr(layout, "available", lambda models_dir: False)
        monkeypatch.setattr(artwork, "available", lambda models_dir, setting="auto", cuda=None: False)
        monkeypatch.setattr(health, "page_models_missing", lambda settings: False)
        monkeypatch.setattr(artwork, "_cuda", False)
    else:
        monkeypatch.setattr(artwork, "_cuda", None)


@pytest.fixture(scope="session")
def sample_page() -> Image.Image:
    return Image.open(FIXTURES / "sample_page.png").convert("RGB")


@pytest.fixture(scope="session")
def sample_page2() -> Image.Image:
    return Image.open(FIXTURES / "sample_page2.png").convert("RGB")


@pytest.fixture(scope="session")
def sample_truth() -> list[dict]:
    with open(FIXTURES / "sample_page.json", encoding="utf-8") as f:
        return json.load(f)["bubbles"]


@pytest.fixture(scope="session")
def sample_truth2() -> list[dict]:
    with open(FIXTURES / "sample_page2.json", encoding="utf-8") as f:
        return json.load(f)["bubbles"]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(state_dir=tmp_path / "state")
    s.validate()
    return s


@pytest.fixture(scope="session")
def tk_root():
    """One hidden Tk root for every dialog test, never mapped: on Windows a Tk root created after another one was
    destroyed now and then fails to read Tcl's own library files."""
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no display ({e})")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def hidden_root(tk_root):
    """The shared hidden root; what a test left on it goes afterwards, and the window language is English again."""
    from taslation.i18n import set_language

    yield tk_root
    for child in tk_root.winfo_children():
        child.destroy()
    set_language("en")
    # Tk objects a test left in reference cycles are collected here, on the Tk thread: collected by a worker
    # thread (the fake Ollama server's), each waits about a second for the main loop.
    import gc

    gc.collect()
