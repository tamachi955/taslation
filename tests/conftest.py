from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from taslation import bookname, health, names, netguard, ollama_start, protect, viewerparts
from taslation.config import Settings
from taslation.detect import layout
from taslation.ocr import place
from taslation.ocr.charspot import check_model_dir
from taslation.ollama_start import OllamaStarter
from taslation.render import artwork
from taslation.ui import live, order, viewers

FIXTURES = Path(__file__).parent / "fixtures"


def ocr_installed() -> bool:
    return not check_model_dir(Settings().ocr_model_dir)


requires_ocr = pytest.mark.skipif(not ocr_installed(), reason="OCR model not downloaded (run setup_models.py)")
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

USUAL_PORT = 11434  # Ollama's usual port: on a person's computer their own server, which no test may reach
_usual_port_tried: list[str] = []


def _usual_port_refused(event: str, args: tuple) -> None:
    """(an audit hook of the whole session: every thread, whatever patches a test made) A connection to Ollama's usual
    port on this computer is refused before it is made - as on a computer where nothing listens there, so that a test
    behaves the same on each - and noted: the test it came in fails (`no_test_reaches_the_usual_port`)."""
    if event != "socket.connect":
        return
    try:
        host, port = args[1][0], args[1][1]
    except (IndexError, TypeError, KeyError):
        return  # (no address of a host and a port: a local pipe's)
    if port == USUAL_PORT and netguard.is_loopback_host(host):
        _usual_port_tried.append(f"{host}:{port}")
        raise ConnectionRefusedError(10061, "refused by tests/conftest.py: no test reaches Ollama's usual port")


sys.addaudithook(_usual_port_refused)


def _installed_ollama() -> frozenset[str]:
    """This computer's own ollama.exe, where `ollama_start.find_ollama` and `translator_install.find_ollama` look -
    found before any test changes the environment (on the runners none: Ollama is not installed there)."""
    import os
    import shutil

    found = []
    programs = os.environ.get("LOCALAPPDATA")
    if programs:
        found.append(Path(programs) / "Programs" / "Ollama" / "ollama.exe")
    on_path = shutil.which("ollama")
    if on_path:
        found.append(Path(on_path))
    return frozenset(_program_key(p) for p in found if p.is_file())


def _program_key(path) -> str:
    try:
        return str(Path(path).resolve()).casefold()
    except (OSError, RuntimeError, TypeError, ValueError):
        return str(path).casefold()


INSTALLED_OLLAMA = _installed_ollama()
_installed_ollama_run: list[str] = []


def _installed_ollama_refused(event: str, args: tuple) -> None:
    """(an audit hook of the whole session, as `_usual_port_refused`) The ollama command installed on this computer is
    never run: as a process of its own it talks to the person's own server on the usual port, which the hook above does
    not see (``ollama serve``, ``pull``, ``rm``, ``create``: the tests give a fake command of their own). Refused before
    the process starts, and noted: the test it came in fails."""
    if event != "subprocess.Popen" or not INSTALLED_OLLAMA:
        return
    try:
        program = _program_of(args[0], args[1])
    except (IndexError, TypeError, StopIteration):
        return
    if program and _program_key(program) in INSTALLED_OLLAMA:
        _installed_ollama_run.append(program)
        raise PermissionError(13, "refused by tests/conftest.py: no test runs this computer's own ollama command")


def _program_of(executable, argv) -> str | None:
    """The program a ``subprocess.Popen`` of *executable* and *argv* runs (a bare name: as the PATH finds it)."""
    import os
    import shutil

    program = executable
    if not program:
        if isinstance(argv, (str, bytes)):
            line = (argv.decode("utf-8", "replace") if isinstance(argv, bytes) else argv).strip()
            program = line[1:].split('"', 1)[0] if line.startswith('"') else line.split(" ", 1)[0]
        else:
            program = next(iter(argv))
    program = os.fsdecode(program) if isinstance(program, (bytes, os.PathLike)) else str(program)
    if program and not os.path.dirname(program):
        program = shutil.which(program) or program
    return program or None


sys.addaudithook(_installed_ollama_refused)


@pytest.fixture(autouse=True)
def no_test_reaches_the_usual_port():
    """No test - nor the code it runs, on any thread - reaches the server on Ollama's usual port: on the developer's
    computer that is the person's own (`_usual_port_refused` refuses it; the test that tried fails here), nor runs
    the ollama command installed on this computer, which would talk to it (`_installed_ollama_refused`)."""
    before, before_run = len(_usual_port_tried), len(_installed_ollama_run)
    yield
    tried = sorted(set(_usual_port_tried[before:]))
    if tried:
        pytest.fail(f"the test tried Ollama's usual port on this computer ({', '.join(tried)}): use a fake server on a "
                    "port of its own (tests/fake_ollama.py) or a closed one")
    ran = sorted(set(_installed_ollama_run[before_run:]))
    if ran:
        pytest.fail(f"the test ran this computer's own ollama command ({', '.join(ran)}): give it a fake one "
                    "(tests/fake_ollama_cli.py)")


@pytest.fixture(autouse=True)
def network_guard_as_it_was():
    """The network guard (`netguard.install`, the process's own) as it was before each test: a test that leaves it
    on would block a later test's fake server on its own port, by the order the tests run in, which differs between
    a whole run here and the runners' parts of it; one that turned it off gets it back."""
    was = _guard_now()
    yield
    _guard_back(was)


def _guard_now() -> tuple[bool, frozenset[int] | None]:
    state = netguard.state()
    return netguard.is_installed(), state.allowed_ports if state is not None else None


def _guard_back(was: tuple[bool, frozenset[int] | None]) -> None:
    on, ports = was
    if netguard.is_installed() and not on:
        netguard.uninstall()
    elif on and ports is not None:
        netguard.install(ports, audit_hook=False)


@pytest.fixture(autouse=True)
def nothing_starts_ollama(monkeypatch):
    """No test starts a real Ollama, or asks whether one runs, by way of the window's start or a command, and none
    stops a process or changes its priority: the start, the request to stop, the termination, the stop itself and a
    change of priority class fail the test where a test reaches them (tests/test_ollama_start.py and
    tests/test_server_yields.py put the real thing back, with fakes under it). What a test claimed, and a server it
    lowered (`ollama_start.yield_server`), is forgotten after it, so that nothing is stopped at the interpreter's
    exit."""

    def refused(what):
        def fail(*_args, **_kwargs):
            pytest.fail(f"a test reached the real {what} of Ollama (tests/conftest.py)")
        return fail

    monkeypatch.setattr(OllamaStarter, "start", lambda self, cancel=None: None)
    monkeypatch.setattr(ollama_start, "launch", refused("start"))
    monkeypatch.setattr(ollama_start, "ask_to_stop", refused("request to stop"))
    monkeypatch.setattr(ollama_start, "terminate", refused("termination"))
    monkeypatch.setattr(ollama_start, "stop_server", refused("stop"))
    monkeypatch.setattr(ollama_start, "set_priority_class", refused("change of priority"))
    monkeypatch.setattr(ollama_start, "_yielded", {})
    monkeypatch.setattr(ollama_start, "_setups", {})  # (nor what a server a test started got: `setup_of`)
    yield
    ollama_start._claims.clear()


@pytest.fixture(autouse=True)
def no_real_window_restored(monkeypatch):
    """No test shows a real minimised window again as a viewer is chosen (the tests' handles are made up; one of them
    could be a real window of this machine); tests/test_minimised_viewer.py patches its own in."""
    monkeypatch.setattr(viewers, "unminimise_window", lambda hwnd, below=None: False)


@pytest.fixture(autouse=True)
def no_enlarged_window_kept(monkeypatch):
    """No test puts back a window an earlier version left enlarged (some stand-ins' settings have the default, real
    state folder); tests/test_enlarge_recovery.py patches its own in."""
    monkeypatch.setattr(viewers, "put_back_enlarged", lambda state_dir: 0)


@pytest.fixture(autouse=True)
def no_real_window_asked_to_repaint(monkeypatch):
    """No test asks a real window to paint itself anew, nor counts the windows over one, as the window finds out
    whether a viewer draws while covered (the tests' handles are made up; one of them could be a real window of this
    machine); tests/test_covered_viewer.py patches its own in."""
    monkeypatch.setattr(live, "ask_repaint", lambda hwnd: False)
    monkeypatch.setattr(live, "fully_covered", lambda hwnd: False)


@pytest.fixture(autouse=True)
def no_real_window_reordered(monkeypatch):
    """No test puts a real window in another place in the order of the windows, nor counts the windows over one, as
    the window keeps the viewer under its own (`ui.order`: the tests' handles are made up; one of them could be a real
    window of this machine); tests/test_window_order.py patches its own in."""
    monkeypatch.setattr(order, "keep_viewer_under", lambda viewer, own, between=None: "")
    monkeypatch.setattr(order, "fully_covered", lambda hwnd, opaque=False: False)


@pytest.fixture(autouse=True)
def no_real_button_read(monkeypatch):
    """No test reads the mouse's real button (`capture.seethrough.button_down`: a press of the person's own on this
    machine while the tests run would hold the follow and the side panes as a page dragged in the viewer does); the
    tests that want a press held patch their own in."""
    from taslation.capture import seethrough as overlay

    monkeypatch.setattr(overlay, "button_down", lambda: False)


@pytest.fixture(autouse=True)
def no_real_hot_key(monkeypatch):
    """No test takes the Insert key of this machine (`capture.seethrough.SeeThrough._key_tick` holds it only while
    the viewer is in front: `viewer_in_front`, here never - a window of the tests' that happened to be in front would
    have Insert taken from the person's own programs while the tests run); the tests of the key patch their own."""
    from taslation.capture import seethrough as overlay

    monkeypatch.setattr(overlay, "viewer_in_front", lambda viewer: False)


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
def no_real_book_names_remembered(monkeypatch):
    """Each test starts with no book's name remembered as the reader's fields split it (`bookname.remember`), and
    none reads what this machine's own state folder remembers (some stand-ins' settings have the default, real state
    folder: there what is remembered stays in memory); what a test remembered is gone after it."""
    real_use = bookname.use
    real_use(None)

    def use(state_dir):
        return real_use(None if state_dir is None or _real_state_folder(state_dir) else state_dir)

    monkeypatch.setattr(bookname, "use", use)
    yield
    real_use(None)


@pytest.fixture(autouse=True)
def real_window_settings_left_alone(monkeypatch):
    """No test writes into ui.json of this machine's own state folder (some stand-ins' settings have the default, real
    state folder: a test that writes there would change the reader's own file, as one did): there the write does
    nothing; a test's own folder gets the real thing."""
    from taslation import i18n

    real_save = i18n._save_ui_settings

    def save(state_dir, data):
        if not _real_state_folder(state_dir):
            real_save(state_dir, data)

    monkeypatch.setattr(i18n, "_save_ui_settings", save)


@pytest.fixture(autouse=True)
def real_settings_file_left_alone(monkeypatch):
    """No test writes a settings file in this machine's own state folder or in the checkout by way of
    `config.write_settings` (the View menu's choice of what the page shows writes it, and some stand-ins' settings
    have the default, real state folder): there the write does nothing; a test's own file gets the real thing."""
    from taslation import config

    real_write = config.write_settings
    checkout = Path(__file__).resolve().parents[1]

    def write(path, values, example=None):
        target = Path(path)
        try:
            folder = target.expanduser().resolve().parent
        except (OSError, RuntimeError):
            return target
        if _real_state_folder(folder) or folder == checkout or checkout in folder.parents:
            return target
        return real_write(path, values, example)

    monkeypatch.setattr(config, "write_settings", write)


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


@pytest.fixture(autouse=True)
def no_real_gpu_measured_for_the_ocr(monkeypatch):
    """What runs on the GPU is never judged on this machine's GPU or its Ollama: the judgement's facts
    (`ocr.place.gather`: NVML, /api/ps) are none - as without an NVIDIA GPU: no start's dialog, "auto" keeps the OCR
    readers on the CPU wherever torch has CUDA -, and each test starts with no session's plan and no failure
    (`place.reset`); a test of the judgement gives its own facts. The translation model is counted as on a server with
    a q8_0 KV cache and no full-size window cache (`ocr.place.server_cache`: never this machine's variables or its
    NVML), unless a test says otherwise."""
    place.reset()
    monkeypatch.setattr(place, "gather", lambda settings, memory=None, own=None, ask=True: None)
    monkeypatch.setattr(place, "server_cache", lambda settings: ("q8_0", False))
    yield
    place.reset()


@pytest.fixture
def gpu_dialog_allowed():
    """A test that shows the start's dialog on the GPU's memory on purpose (tests/test_gpu_short_dialog.py)."""
    return True


@pytest.fixture(autouse=True)
def no_gpu_dialog_unless_asked(request, monkeypatch):
    """The start's dialog on the GPU's memory (`ui.dialogs.gpu_short`) never comes up in a test that does not ask for
    it (`gpu_dialog_allowed`): one that would show it fails, whatever thread or callback made it."""
    if "gpu_dialog_allowed" in request.fixturenames:
        yield
        return
    from taslation.ui.dialogs import gpu_short

    shown: list[int] = []

    def refused(self, *args, **kwargs):
        shown.append(1)
        raise RuntimeError("the start's GPU dialog came up in a test that does not ask for it")

    monkeypatch.setattr(gpu_short.GpuShortDialog, "__init__", refused)
    yield
    assert not shown, "the start's dialog on the GPU's memory came up in a test that does not ask for it"


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
    # the tests count the model's requests on pages whose lines repeat (`helpers.FakeOcr` goes round six short lines):
    # line reuse, on by default, would answer the repeats itself. tests/test_linememo.py turns it on for its own
    s.reuse_lines = False
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


def pytest_collection_modifyitems(config, items):
    """A parallel job runs only its part of a test file divided between jobs (`TASLATION_TEST_SPLIT`, as
    tools/test_shards.py gives it: FILE:I/N keeps the file's tests whose number in collection order leaves I when
    divided by N). Without the variable every test runs."""
    import os

    spec = os.environ.get("TASLATION_TEST_SPLIT", "")
    if not spec:
        return
    import importlib.util

    tool_spec = importlib.util.spec_from_file_location("test_shards_tool",
                                                       Path(__file__).resolve().parent.parent / "tools" / "test_shards.py")
    tool = importlib.util.module_from_spec(tool_spec)
    tool_spec.loader.exec_module(tool)
    seen: dict[str, int] = {}
    keep, drop = [], []
    for item in items:
        name = Path(str(item.fspath)).name
        index = seen.get(name, 0)
        seen[name] = index + 1
        (keep if tool.kept(spec, name, index) else drop).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep
