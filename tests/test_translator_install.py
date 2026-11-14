"""The translator model's install (`taslation.translator_install`, setup_models.py --translator-for): one GGUF from a
fake Hugging Face, checked, imported into a fake ollama command line (`fake_ollama_cli`) and deleted; Qwen pulled;
the record of what TASlation installed and agreed to; the switch a language change needs, which never counts a model
the person had before as TASlation's; a stopped or failed install leaving nothing behind."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import fake_ollama_cli
import pytest

from taslation import translator_install as ti
from taslation.translate.models import PLAMO, QWEN, model_for_language

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("setup_models_translator", ROOT / "setup_models.py")
setup_models = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup_models)

GGUF = b"GGUF" + bytes(range(256)) * 40  # a small stand-in for the model file
LICENCES = {"LICENSE/en": b"PLaMo Community License Agreement\n", "LICENSE/ja": "PLaMoコミュニティ\n".encode()}

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the fake ollama is a .cmd")


class _Answer(io.BytesIO):
    status = 200

    def __init__(self, data: bytes, pieces: list[int] | None = None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
        self.read_sizes = pieces

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def hf(monkeypatch):
    """A fake Hugging Face for setup_models.py: the pinned repository's licence texts and GGUF, the pins set to them."""
    files = {ti.plamo_url(path): data for path, data in LICENCES.items()}
    files[ti.plamo_url(ti.PLAMO_FILE)] = GGUF
    asked: list[str] = []
    monkeypatch.setattr(ti, "PLAMO_SHA256", hashlib.sha256(GGUF).hexdigest())
    monkeypatch.setattr(ti, "PLAMO_BYTES", len(GGUF))
    monkeypatch.setattr(ti, "PLAMO_LICENCE_FILES", tuple(
        (path, hashlib.sha256(data).hexdigest(), name) for (path, _sha, name), data in
        zip(ti.PLAMO_LICENCE_FILES, LICENCES.values())))
    monkeypatch.setattr(ti, "free_gb", lambda path: 999.0)

    def urlopen(request, timeout=None):
        url = getattr(request, "full_url", request)
        asked.append(url)
        if url not in files:
            raise OSError(f"404 {url}")
        return _Answer(files[url])

    monkeypatch.setattr(setup_models.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(setup_models, "_progress", False)
    return {"files": files, "asked": asked}


@pytest.fixture
def ollama(tmp_path, monkeypatch):
    """A fake ollama.cmd with no model; ``.state`` its file, ``.set(models, **extra)`` starts it over."""
    state = tmp_path / "ollama.json"

    class Fake:
        exe = str(fake_ollama_cli.make(tmp_path / "bin", state))

        @staticmethod
        def set(models=(), **extra):
            fake_ollama_cli.make(tmp_path / "bin", state, list(models), **extra)

        @staticmethod
        def read():
            return fake_ollama_cli.read(state)

    monkeypatch.setenv("FAKE_OLLAMA_STATE", str(state))
    monkeypatch.setattr(ti, "find_ollama", lambda: Fake.exe)
    return Fake


def _install(tmp_path, language="English", agreed="window", cancel=None):
    return setup_models.install_translator(language, tmp_path / "models", tmp_path / "state", None, None, agreed,
                                           cancel)


# ---- the pins and the Modelfile


def test_the_pins_are_the_repository_s_default_file():
    assert ti.PLAMO_REPO == "pfnet/plamo-3-translate-2b-GGUF" and ti.PLAMO_FILE == "plamo-3-translate-2b-Q4_K_M.gguf"
    assert len(ti.PLAMO_REVISION) == 40 and len(ti.PLAMO_SHA256) == 64
    assert round(ti.PLAMO_BYTES / 1e9, 1) == PLAMO.size_gb == 1.8
    assert ti.plamo_url("LICENSE/en") == f"https://huggingface.co/{ti.PLAMO_REPO}/resolve/{ti.PLAMO_REVISION}/LICENSE/en"


def test_the_modelfile_sets_the_context_and_the_stops_and_no_template():
    text = ti.modelfile_text()
    assert text.splitlines() == [f"FROM ./{ti.PLAMO_FILE}", "PARAMETER num_ctx 16384",
                                 'PARAMETER stop "<|plamo:tag|>"', 'PARAMETER stop "<|plamo:bos|>"']
    assert "TEMPLATE" not in text


def test_the_pin_is_the_revision_checked_on_2026_11_14():
    """The file and the licence texts of revision 4f672106 (2026-11-09), downloaded whole and hashed: the revision
    pinned before, f2b4599d, is refused by Hugging Face's storage since then."""
    assert ti.PLAMO_REVISION == "4f672106b847200bfdc0f6af6c321cd94eba1aed"
    assert ti.PLAMO_SHA256 == "1ffd9073afcc70e35ccc942428aa2b73d7aa2b9ea779bf504b775369e0276c13"
    assert ti.PLAMO_BYTES == 1_807_203_040
    assert dict((path, sha) for path, sha, _name in ti.PLAMO_LICENCE_FILES) == {
        "LICENSE/en": "ca0c5e90f6de6799fc2d2d4f2b2647cc088444c19f286f689e525d4ad28f9ed6",
        "LICENSE/ja": "7dd74339bbf9a39fe33e271a89657aacf06f452b082fcb1273fb792b8d6b7db2"}
    assert ti.PLAMO_LICENCE_REVISED == "November 9, 2026"


def test_the_terms_say_what_matters_in_plain_words():
    terms = ti.PLAMO_TERMS
    for words in ("non-commercial use is free", "18 or older", "PLaMo's output", "article 5", "without any warranty",
                  *ti.PLAMO_LICENCE_URLS):
        assert words in terms


def test_the_terms_are_the_revised_licence_s_with_its_articles():
    terms = " ".join(ti.PLAMO_TERMS.split())  # (its lines joined)
    assert f"as revised on {ti.PLAMO_LICENCE_REVISED}" in terms
    for words in ("registering with PFN first (article 3)", "guardian's consent (article 2)",
                  "the rights to what you put into it and to what comes out of it",
                  "no rights to other people's works (article 9)", "without a note that it is PLaMo's output",
                  "a book or another long publication must say that PLaMo was used",
                  "models trained on it fall under this licence (article 5)", "not to publish translations at all",
                  "your responsibility (article 7)"):
        assert words in terms, words
    assert "only with a clear note" not in terms  # (the text before the revision)


def test_install_ps1_shows_the_same_revision_and_knows_the_refusal_s_exit_code():
    install = (ROOT / "install.ps1").read_text("ascii")
    assert f"as revised on {ti.PLAMO_LICENCE_REVISED}:" in install and "(article 9)" in install
    assert f"$RefusedCode = {ti.REFUSED}" in install


# ---- the install


def test_plamo_is_downloaded_checked_imported_and_its_gguf_deleted(tmp_path, hf, ollama):
    assert _install(tmp_path) == 0
    folder = tmp_path / "models" / ti.PLAMO_DIRNAME
    assert not (folder / ti.PLAMO_FILE).exists() and not list(folder.glob("*.part"))  # the GGUF is gone: disk is the point
    assert (folder / "Modelfile").read_text("utf-8") == ti.modelfile_text()
    assert (folder / "PLaMo-Community-License-en.txt").read_bytes() == LICENCES["LICENSE/en"]
    state = ollama.read()
    assert state["models"] == [PLAMO.ollama_name + ":latest"]
    assert state["created"][PLAMO.ollama_name] == ti.modelfile_text()
    assert ["create", PLAMO.ollama_name, "-f", str(folder / "Modelfile")] in state["calls"]
    assert all(u.startswith(f"https://huggingface.co/{ti.PLAMO_REPO}/resolve/{ti.PLAMO_REVISION}/") for u in hf["asked"])
    record = ti.load_record(tmp_path / "state")
    assert PLAMO.ollama_name in record["installed"] and record["agreed"][ti.PLAMO_LICENCE]["where"] == "window"
    assert ti.has_agreed(tmp_path / "state")


def test_a_gguf_that_fails_its_checksum_is_removed_and_nothing_imported(tmp_path, hf, ollama, monkeypatch):
    monkeypatch.setattr(ti, "PLAMO_SHA256", "0" * 64)
    assert _install(tmp_path) == 1
    folder = tmp_path / "models" / ti.PLAMO_DIRNAME
    assert not list(folder.glob("*.gguf")) and not list(folder.glob("*.part"))
    assert ollama.read()["models"] == [] and not any(c[0] == "create" for c in ollama.read()["calls"])
    assert PLAMO.ollama_name not in ti.load_record(tmp_path / "state")["installed"]


def test_a_short_download_leaves_no_part_file(tmp_path, hf, ollama, monkeypatch):
    monkeypatch.setattr(ti, "PLAMO_BYTES", len(GGUF) + 10)
    assert _install(tmp_path) == 1
    assert not list((tmp_path / "models" / ti.PLAMO_DIRNAME).glob("*.part"))


def test_a_failed_import_leaves_neither_the_gguf_nor_a_model(tmp_path, hf, ollama):
    ollama.set(fail=["create"])
    assert _install(tmp_path) == 1
    assert not list((tmp_path / "models" / ti.PLAMO_DIRNAME).glob("*.gguf"))
    assert ollama.read()["models"] == []


def test_a_stopped_download_leaves_nothing(tmp_path, hf, ollama, monkeypatch):
    cancel = threading.Event()
    real = setup_models._report

    def report(phase, done=0, total=0, **extra):
        if phase == "download" and done:
            cancel.set()  # the window's Cancel, after the first piece
        real(phase, done, total, **extra)

    monkeypatch.setattr(setup_models, "_report", report)
    monkeypatch.setattr(ti, "PLAMO_BYTES", len(GGUF))
    big = GGUF * 3
    hf["files"][ti.plamo_url(ti.PLAMO_FILE)] = big
    monkeypatch.setattr(ti, "PLAMO_BYTES", len(big))
    monkeypatch.setattr(setup_models.urllib.request, "urlopen",
                        lambda request, timeout=None: _Pieces(hf["files"][request.full_url]))
    assert _install(tmp_path, cancel=cancel) == ti.CANCELLED
    folder = tmp_path / "models" / ti.PLAMO_DIRNAME
    assert not list(folder.glob("*.part")) and not list(folder.glob("*.gguf"))
    assert ollama.read()["models"] == []


class _Pieces(_Answer):
    def read(self, n=-1):
        return super().read(min(n, 1000) if n and n > 0 else 1000)


def test_plamo_already_there_is_left_as_it_is_and_counted_as_taslation_s(tmp_path, hf, ollama):
    ollama.set([PLAMO.ollama_name + ":latest"])
    assert _install(tmp_path) == 0
    assert hf["asked"] == [] and [c[0] for c in ollama.read()["calls"]] == ["list"]
    assert ti.installed_by_taslation(tmp_path / "state", PLAMO.ollama_name)


def test_without_an_agreement_a_console_without_a_person_downloads_nothing(tmp_path, hf, ollama, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert _install(tmp_path, agreed=None) == 1
    out = capsys.readouterr().out
    assert "PLaMo Community License" in out and "Not agreed" in out
    assert hf["asked"] == [] and not ti.has_agreed(tmp_path / "state")


def test_an_agreement_recorded_before_is_not_asked_again(tmp_path, hf, ollama):
    ti.record_agreement(tmp_path / "state", "install")
    assert _install(tmp_path, agreed=None) == 0


def test_a_changed_licence_is_asked_about_again(tmp_path, monkeypatch):
    ti.record_agreement(tmp_path, "install")
    assert ti.has_agreed(tmp_path)
    monkeypatch.setattr(ti, "PLAMO_LICENCE_FILES", (("LICENSE/en", "1" * 64, "x.txt"),))
    assert not ti.has_agreed(tmp_path)


def _refusing(hf, monkeypatch, code: int, url: str) -> None:
    """The fake Hugging Face answers *url* with the HTTP error *code*, as its storage did for the old revision's file."""
    import urllib.error

    answer = setup_models.urllib.request.urlopen

    def urlopen(request, timeout=None):
        if getattr(request, "full_url", request) == url:
            hf["asked"].append(url)
            raise urllib.error.HTTPError(url, code, "Forbidden", {}, None)
        return answer(request, timeout)

    monkeypatch.setattr(setup_models.urllib.request, "urlopen", urlopen)


@pytest.mark.parametrize("code", sorted(ti.REFUSED_HTTP))
def test_a_file_the_server_refuses_ends_with_its_own_code_and_no_advice_to_try_again(tmp_path, hf, ollama, monkeypatch,
                                                                                     capsys, code):
    _refusing(hf, monkeypatch, code, ti.plamo_url(ti.PLAMO_FILE))
    assert _install(tmp_path) == ti.REFUSED
    out = capsys.readouterr().out
    assert f"(HTTP {code})" in out and "Running this again will not help: update TASlation" in out
    assert "issues page" in out and "check the network" not in out
    assert hf["asked"].count(ti.plamo_url(ti.PLAMO_FILE)) == 1  # not tried again
    folder = tmp_path / "models" / ti.PLAMO_DIRNAME
    assert not list(folder.glob("*.part")) and not list(folder.glob("*.gguf")) and ollama.read()["models"] == []


def test_a_dropped_connection_still_says_to_check_the_network(tmp_path, hf, ollama, monkeypatch, capsys):
    monkeypatch.setattr(setup_models, "RETRIES", 0)
    _refusing(hf, monkeypatch, 503, ti.plamo_url(ti.PLAMO_FILE))  # (a 5xx is no refusal: tried again, then 1)
    assert _install(tmp_path) == 1
    out = capsys.readouterr().out
    assert "check the network and the disk space" in out and "will not help" not in out


def test_the_reading_model_refused_ends_the_script_with_the_same_code(tmp_path, monkeypatch, capsys):
    import urllib.error

    def refused(model, models_dir):
        raise urllib.error.HTTPError("https://huggingface.co/x", 403, "Forbidden", {}, None)

    monkeypatch.setattr(setup_models, "download_ocr", refused)
    monkeypatch.chdir(tmp_path)
    assert setup_models.main(["--agreed", "--skip-page-models", "--models-dir", str(tmp_path / "models")]) == ti.REFUSED
    out = capsys.readouterr().out
    assert "(HTTP 403)" in out and "will not help" in out and "Check the network" not in out


def test_the_window_s_runner_reads_the_refusal(tmp_path):
    script = tmp_path / "setup_models.py"
    script.write_text("import sys\nprint('refused', flush=True)\n"
                      f"sys.exit({ti.REFUSED})\n", "utf-8")
    installer = ti.Installer("English", tmp_path / "models", tmp_path / "state", script=script, python=sys.executable)
    assert installer.run().state == "refused"


def test_too_little_disk_downloads_nothing(tmp_path, hf, ollama, monkeypatch):
    monkeypatch.setattr(ti, "free_gb", lambda path: 0.5)
    assert _install(tmp_path) == ti.NO_ROOM
    assert hf["asked"] == []


@pytest.mark.parametrize("language", ["Turkish", "Portuguese (Brazil)"])
def test_qwen_is_pulled_for_its_two_languages_and_recorded(tmp_path, hf, ollama, language):
    assert _install(tmp_path, language) == 0
    assert ollama.read()["models"] == [QWEN.ollama_name] and hf["asked"] == []
    assert ["pull", QWEN.ollama_name] in ollama.read()["calls"]
    assert ti.installed_by_taslation(tmp_path / "state", QWEN.ollama_name)


def test_a_qwen_the_person_had_is_not_counted_as_taslation_s(tmp_path, hf, ollama):
    ollama.set([QWEN.ollama_name])
    assert _install(tmp_path, "Turkish") == 0
    assert not ti.installed_by_taslation(tmp_path / "state", QWEN.ollama_name)
    assert [c[0] for c in ollama.read()["calls"]] == ["list"]


def test_ollama_down_or_missing_says_so(tmp_path, hf, ollama, monkeypatch, capsys):
    ollama.set(down=True)
    assert _install(tmp_path) == 1 and "does not answer" in capsys.readouterr().out
    monkeypatch.setattr(ti, "find_ollama", lambda: None)
    assert _install(tmp_path) == 1 and "ollama.com" in capsys.readouterr().out


def test_the_progress_lines_round_trip(tmp_path, hf, ollama, monkeypatch, capsys):
    monkeypatch.setattr(setup_models, "_progress", True)
    assert _install(tmp_path) == 0
    seen = [ti.parse_progress(line) for line in capsys.readouterr().out.splitlines()]
    phases = [d["phase"] for d in seen if d]
    assert phases[0] == "download" and "check" in phases and "import" in phases and phases[-1] == "done"
    last = [d for d in seen if d and d["phase"] == "download"][-1]
    assert last["done"] == last["total"] == len(GGUF)
    assert ti.parse_progress("Downloading x ...") is None and ti.parse_progress(ti.PROGRESS_PREFIX + "{") is None


def test_the_command_line_of_setup_models_installs_only_the_translator(tmp_path, hf, ollama, monkeypatch):
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.chdir(tmp_path)  # no taslation.toml of the checkout
    monkeypatch.setattr(setup_models, "download_ocr", lambda *a: pytest.fail("OCR models fetched"))
    assert setup_models.main(["--translator-for", "English", "--plamo-agreed", "--models-dir",
                              str(tmp_path / "models"), "--ollama-exe", ollama.exe]) == 0
    assert ti.load_record(tmp_path / "state")["agreed"][ti.PLAMO_LICENCE]["where"] == "install"


# ---- the record and the switch


def test_the_switch_names_what_to_download_and_what_to_free(tmp_path):
    assert ti.plan("English", None, tmp_path) is None  # Ollama does not answer: nothing to say
    assert ti.plan("English", [PLAMO.ollama_name + ":latest"], tmp_path) is None
    s = ti.plan("Turkish", [PLAMO.ollama_name + ":latest", "gemma3:4b"], tmp_path)
    assert s.needed == QWEN and s.unneeded == PLAMO and s.ours and s.freed_gb == PLAMO.size_gb
    s = ti.plan("English", [QWEN.ollama_name], tmp_path)
    assert s.needed == PLAMO and s.unneeded == QWEN and not s.ours  # the person's own qwen
    ti.mark_installed(tmp_path, QWEN)
    assert ti.plan("French", [QWEN.ollama_name], tmp_path).ours
    s = ti.plan("German", ["gemma3:4b"], tmp_path)
    assert s.needed == PLAMO and s.unneeded is None and s.freed_gb == 0


def test_the_record_survives_a_broken_file_and_forgets(tmp_path):
    ti.record_path(tmp_path).write_text("not json", "utf-8")
    assert ti.load_record(tmp_path) == {"installed": {}, "agreed": {}}
    ti.mark_installed(tmp_path, QWEN)
    assert ti.installed_by_taslation(tmp_path, "qwen3.5:4b")
    ti.forget(tmp_path, "qwen3.5:4b")
    assert not ti.installed_by_taslation(tmp_path, "qwen3.5:4b")
    assert ti.installed_by_taslation(tmp_path, PLAMO.ollama_name + ":latest")  # only TASlation gives that name


def test_remove_model_forgets_it(tmp_path, ollama):
    ollama.set([QWEN.ollama_name])
    ti.mark_installed(tmp_path, QWEN)
    assert ti.remove_model(ollama.exe, QWEN.ollama_name, tmp_path)
    assert ollama.read()["models"] == [] and not ti.installed_by_taslation(tmp_path, QWEN.ollama_name)


def test_the_two_languages_of_qwen():
    assert model_for_language("Turkish") == QWEN and model_for_language("Portuguese (Brazil)") == QWEN
    assert model_for_language("English") == PLAMO and model_for_language("Portuguese") == QWEN


def test_a_watched_command_is_ended_at_once_on_cancel():
    cancel = threading.Event()
    seen: list[str] = []
    threading.Timer(0.5, cancel.set).start()
    started = time.monotonic()
    code = ti.run_watched([sys.executable, "-c", "import time\nprint('5%', flush=True)\ntime.sleep(30)"], cancel,
                          seen.append)
    assert code is None and time.monotonic() - started < 10 and seen == ["5%"]
    assert ti.percent_of("pulling 4f2b: 45% |###| 1.5 GB") == 0.45 and ti.percent_of("pulling manifest") is None


# ---- the window's runner


def test_the_installer_runs_setup_models_and_reads_its_progress(tmp_path, ollama):
    """`Installer` runs a stand-in setup_models.py (the real one would go to Hugging Face): its command, its progress
    lines, and its end."""
    script = tmp_path / "setup_models.py"
    script.write_text(
        "import json, sys\n"
        f"open(r'{tmp_path / 'args.json'}', 'w').write(json.dumps(sys.argv[1:]))\n"
        "for i in (0, 50, 100):\n"
        f"    print({ti.PROGRESS_PREFIX!r} + json.dumps({{'phase': 'download', 'done': i, 'total': 100}}), flush=True)\n"
        "print('a line for people', flush=True)\n"
        f"print({ti.PROGRESS_PREFIX!r} + json.dumps({{'phase': 'done'}}), flush=True)\n", "utf-8")
    seen: list[dict] = []
    installer = ti.Installer("English", tmp_path / "models", tmp_path / "state", on_progress=seen.append, script=script,
                             python=sys.executable)
    assert installer.run().state == "done"
    assert [d.get("done") for d in seen] == [0, 50, 100, None] and seen[-1]["phase"] == "done"
    args = json.loads((tmp_path / "args.json").read_text())
    assert args[:4] == ["--translator-for", "English", "--plamo-agreed", "window"] and "--progress" in args


def test_a_stopped_installer_cleans_what_its_process_left(tmp_path, ollama, monkeypatch):
    """A setup_models.py that does not stop when told: its process is ended, and what it left (a .part file, the model
    it got into Ollama just then) is removed."""
    monkeypatch.setattr(ti, "CANCEL_WAIT_S", 0.5)
    folder = tmp_path / "models" / ti.PLAMO_DIRNAME
    script = tmp_path / "setup_models.py"
    script.write_text(
        "import json, sys, time\nfrom pathlib import Path\n"
        f"Path(r'{folder}').mkdir(parents=True, exist_ok=True)\n"
        f"Path(r'{folder / (ti.PLAMO_FILE + '.part')}').write_bytes(b'half')\n"
        f"print({ti.PROGRESS_PREFIX!r} + json.dumps({{'phase': 'download', 'done': 1, 'total': 9}}), flush=True)\n"
        "time.sleep(30)\n", "utf-8")
    seen: list[dict] = []
    installer = ti.Installer("English", tmp_path / "models", tmp_path / "state", on_progress=seen.append, script=script,
                             python=sys.executable)

    def stop_soon(data):
        seen.append(data)
        ollama.set([PLAMO.ollama_name + ":latest"])  # as if the import had just gone through
        threading.Timer(0.2, installer.cancel).start()

    installer.on_progress = stop_soon
    started = time.monotonic()
    assert installer.run().state == "cancelled" and time.monotonic() - started < 15
    assert not list(folder.glob("*.part"))
    assert ollama.read()["models"] == []  # not there before: removed


def test_the_window_runs_setup_models_with_a_console_python(monkeypatch, tmp_path):
    pythonw = tmp_path / "pythonw.exe"
    pythonw.write_bytes(b"")
    (tmp_path / "python.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(pythonw))
    assert ti._console_python() == str(tmp_path / "python.exe")


def test_nothing_here_uses_the_network():
    text = Path(ti.__file__).read_text("utf-8")
    assert "urllib" not in text and "http.client" not in text and "socket" not in text


def test_subprocess_is_never_given_a_shell():
    text = Path(ti.__file__).read_text("utf-8")
    assert "shell=True" not in text and subprocess  # (the names of models and paths go as arguments)


def test_the_credit_and_the_disclosures_are_where_the_licence_asks():
    third = (ROOT / "docs" / "THIRD_PARTY.md").read_text("utf-8")
    assert ti.CREDIT == "Built with PLaMo" and ti.CREDIT in third
    for name in ("README.md", "README.ja.md"):  # the English README and its Japanese original
        readme = (ROOT / name).read_text("utf-8")
        assert ti.CREDIT in readme, name
        assert "1.8 GB" in readme and "3.3 GB" in readme, name
    for words in ("PLaMo 3 NICT", "NICT", "Preferred Networks", "not stated", ti.PLAMO_REVISION[:8], PLAMO.ollama_name,
                  "Apache-2.0", "article 5", *ti.PLAMO_LICENCE_URLS):
        assert words in third, words


def test_ollama_model_without_a_name_installs_the_language_s_model_never_pulls_auto(tmp_path, monkeypatch):
    """``--ollama-model`` alone (or ``auto``, the setting's default) is the translator model the target language needs
    (`install_translator`), never ``ollama pull auto``; a name is pulled as before."""
    calls: list[tuple] = []
    monkeypatch.setattr(setup_models, "_settings_for_translator", lambda: (tmp_path / "state", None, "Turkish"))
    monkeypatch.setattr(setup_models, "install_translator", lambda language, *a, **k: calls.append(("install", language)) or 0)
    monkeypatch.setattr(setup_models, "pull_ollama", lambda name: calls.append(("pull", name)))
    common = ["--models-dir", str(tmp_path / "models"), "--skip-ocr", "--skip-page-models"]
    for extra in (["--ollama-model"], ["--ollama-model", "auto"], ["--ollama-model", "gemma3:4b"]):
        assert setup_models.main(common + extra) == 0
    assert calls == [("install", "Turkish"), ("install", "Turkish"), ("pull", "gemma3:4b")]


def test_plan_offers_nothing_for_a_model_of_the_person_s_own():
    assert ti.plan("English", ["gemma3:4b"], Path("unused"), "gemma3:4b") is None
    assert ti.plan("English", ["gemma3:4b"], Path("unused"), "auto").needed == PLAMO
    assert ti.plan("English", [], Path("unused"), QWEN.ollama_name).needed == QWEN  # a known model named by hand
