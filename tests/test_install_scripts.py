"""install.ps1, uninstall.ps1 and their .cmd wrappers: they parse, expose the documented switches, and their dry runs
change nothing.

The real runs here touch only temporary copies: an uninstall of a copy deletes the copy's fake ``.venv`` and
``models`` (and, after a Y, a temporary data folder), with Ollama hidden from it or faked. The questions about Python
and the GPU are put with fake ``winget``, ``py`` and ``nvidia-smi`` on a bare PATH (`_tools`); a person's answers come
from a console put into the temporary copy (`_answering`), and pip is a fake too (`_fake_venv`). Every copy is
sandboxed before it runs (`_sandbox`, and `_run` refuses one that is not): no Start menu, user environment, free-space
reading or Ollama of this computer, and no Ollama process stopped. A whole install runs on `_whole_install`'s fakes.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from taslation.config import OCR_MODELS, PAGE_MODELS

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ("install.ps1", "uninstall.ps1")
WRAPPERS = ("install.cmd", "uninstall.cmd")
TEXTS = "installer-texts.json"  # install.ps1's questions in other languages
SWITCHES = {"install.ps1": {"Yes", "DryRun"}, "uninstall.ps1": {"Yes", "DryRun"}}
SHELLS = [s for s in ("powershell", "pwsh") if shutil.which(s)]
# Windows PowerShell 5.1 (the documented `powershell -ExecutionPolicy Bypass -File ...`) first.
RUN_SHELL = SHELLS[0] if SHELLS else None

pytestmark = pytest.mark.skipif(not SHELLS, reason="neither powershell nor pwsh is installed")


def _ps(shell: str, command: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True,
                          text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def _parse(shell: str, script: Path) -> dict:
    command = (
        "$t = $null; $e = $null; "
        f"$a = [System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$t, [ref]$e); "
        "$p = @(); if ($a.ParamBlock) { $p = @($a.ParamBlock.Parameters | ForEach-Object { "
        "@{ name = $_.Name.VariablePath.UserPath; type = $_.StaticType.Name } }) }; "
        "$h = Get-Help -Name '" + str(script) + "' -Full; "
        "@{ errors = @($e | ForEach-Object { $_.Message + ' (line ' + $_.Extent.StartLineNumber + ')' }); "
        "params = $p; help = @($h.parameters.parameter | ForEach-Object { $_.name }) } | ConvertTo-Json -Depth 4"
    )
    r = _ps(shell, command)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _run(script: Path, *args: str, env: dict | None = None, timeout: float = 120) -> subprocess.CompletedProcess:
    assert SANDBOXED in script.read_text("ascii")
    # stdin from the null device: the scripts must see "no console to ask" and never wait for an answer
    return subprocess.run([RUN_SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
                          capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                          stdin=subprocess.DEVNULL, env=env,
                          cwd=str(script.parent.parent))  # run from outside the checkout, as a user may


def _run_cmd(script: Path, *args: str, env: dict | None = None, stdin: str | None = "\n",
             timeout: float = 120) -> subprocess.CompletedProcess:
    # the newline answers the wrapper's pause (a double-click would have a person press a key)
    if script.with_suffix(".ps1").exists():
        assert SANDBOXED in script.with_suffix(".ps1").read_text("ascii")
    return subprocess.run(["cmd", "/c", str(script), *args], capture_output=True, encoding="utf-8", errors="replace",
                          timeout=timeout, input=stdin, env=env, cwd=str(script.parent.parent))


START = "# ---------------------------------------------------------------- start\n"
SANDBOXED = "# sandboxed by the tests"


def _override(script: Path, *lines: str) -> None:
    """Puts *lines* into this temporary copy of a script, after its functions and constants and before its first step."""
    text = script.read_bytes().decode("ascii").replace("\r\n", "\n")
    assert text.count(START) == 1
    script.write_bytes(text.replace(START, "\n".join(lines) + "\n" + START).encode("ascii"))


def _sandbox(script: Path, tmp: Path) -> None:
    """This copy off the computer it runs on: `Set-UserEnv` and `Stop-OllamaProcesses` only write down what they would
    do (into ``user-env.txt``), `Get-UserEnv` reads ``FAKE_USER_<name>`` from the process, the shortcut goes into the
    temporary folder, the Ollama it would ask is nobody, any disk has room and any folder is short enough; the data
    folder is TASLATION_STATE_DIR or none, this PC's language FAKE_UI_CULTURE."""
    menu = tmp / "start menu"
    menu.mkdir(exist_ok=True)
    log = tmp / "user-env.txt"
    _override(script, SANDBOXED,
              f"$ShortcutPath = '{menu / 'TASlation.lnk'}'",
              "function Get-StateDir { $v = [Environment]::GetEnvironmentVariable('TASLATION_STATE_DIR'); "
              f"if ($v) {{ return $v }}; return '{tmp / 'no state'}' }}",
              "function Get-UiCulture { return [Environment]::GetEnvironmentVariable('FAKE_UI_CULTURE') }",
              "$OllamaUrl = 'http://127.0.0.1:9'",
              "$MaxRootLength = 100000",
              "function Get-FreeGB([string]$Path) { return 9999.0 }",
              "function Get-UserEnv([string]$Name) { return [Environment]::GetEnvironmentVariable(\"FAKE_USER_$Name\") }",
              f"function Set-UserEnv([string]$Name, [string]$Value) {{ Add-Content -LiteralPath '{log}' \"$Name=$Value\" }}",
              f"function Stop-OllamaProcesses([string]$Folder) {{ Add-Content -LiteralPath '{log}' 'stopped Ollama'; return $false }}")


def _env(tmp: Path, **extra: str) -> dict:
    env = dict(os.environ)
    for key in ("TASLATION_MODELS_DIR", "SELFTRANS_MODELS_DIR", "TASLATION_STATE_DIR", "SELFTRANS_STATE_DIR",
                "PYTHONUTF8", "TASLATION_UPDATING", "TASLATION_UPDATE_PAUSE"):
        env.pop(key, None)
    # no run of install.ps1 here may write the user's environment: a value there is left alone
    env.setdefault("OLLAMA_KV_CACHE_TYPE", "test")
    env.setdefault("LLAMA_ARG_CACHE_RAM", "test")
    env.update(extra)
    return env


def _hide_ollama(env: dict, tmp: Path) -> dict:
    """No ollama on PATH or in the (moved) user install folder, so the uninstaller has nothing to ask Ollama."""
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if "ollama" not in p.lower())
    local = tmp / "localappdata"
    local.mkdir(exist_ok=True)
    env["LOCALAPPDATA"] = str(local)
    return env


def _fake_checkout(tmp: Path, name: str = "checkout") -> Path:
    co = tmp / name
    (co / "taslation").mkdir(parents=True)
    for name in SCRIPTS + WRAPPERS + ("pyproject.toml", TEXTS):
        shutil.copy2(ROOT / name, co / name)
    shutil.copy2(ROOT / "taslation" / "config.py", co / "taslation" / "config.py")
    for name in SCRIPTS:
        _sandbox(co / name, tmp)
    (co / ".venv" / "Scripts").mkdir(parents=True)
    (co / ".venv" / "Scripts" / "python.exe").write_bytes(b"not a real python")
    (co / ".venv" / "pyvenv.cfg").write_text("home = nowhere\n")
    for model, files in (("manga-ocr-charspot-small", ("model.safetensors", "vocab.json", "config.json")),
                         ("manga-ocr-nar-small", ("model.safetensors", "nar_vocabulary_6817.json", "config.json")),
                         ("manga-ocr-base-CPT-flex", ("model.safetensors", "nar_vocabulary_6817.json", "config.json"))):
        (co / "models" / model).mkdir(parents=True)
        for name in files:
            (co / "models" / model / name).write_text("{}")
    (co / "models" / "fonts").mkdir()
    (co / "models" / "fonts" / "OFL.txt").write_text("licence")
    return co


GPU = "Fake GPU, 4096 MiB, 610.88, 7.5"  # what nvidia-smi says of an NVIDIA GPU the GPU build runs on


def _tools(tmp: Path, *, python: bool = True, winget: bool = True, gpu: str | None = GPU,
           ollama: bool = False) -> dict:
    """An environment whose PATH holds only Windows and fake tools, with an empty per-user program folder. The fake
    ``py`` answers once ``py-installed`` exists (the fake ``winget`` makes it and writes its arguments down) and
    refuses ``-m venv``, which ends a real run right there, before any download. A fake ``ollama`` only writes its
    arguments down; the fake ``nvidia-smi`` says *gpu* to any question, or fails (no NVIDIA GPU) for None."""
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    (bin_dir / "py.cmd").write_text(
        '@echo off\nif not exist "%~dp0py-installed" exit /b 1\nif "%2"=="-m" exit /b 5\n'
        'echo 3.13.1\necho C:\\fake\\python.exe\n')
    if python:
        (bin_dir / "py-installed").write_text("")
    if winget:
        (bin_dir / "winget.cmd").write_text('@echo off\necho %*> "%~dp0winget-args.txt"\necho.> "%~dp0py-installed"\n')
    if ollama:
        (bin_dir / "ollama.cmd").write_text('@echo off\necho %*>> "%~dp0ollama-args.txt"\n')
    smi = "@echo off\nexit /b 1\n" if gpu is None else f"@echo off\necho {gpu}\n"  # the real one is in System32
    (bin_dir / "nvidia-smi.cmd").write_text(smi)
    windows = Path(os.environ["SystemRoot"]) / "System32"
    env = _hide_ollama(_env(tmp), tmp)
    env["PATH"] = os.pathsep.join([str(bin_dir), str(windows), str(windows / "WindowsPowerShell" / "v1.0")])
    return env


def _working_python(where: Path) -> None:
    """A python.exe at ``where`` that runs: a copy of this virtual environment's launcher with its pyvenv.cfg."""
    where.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sys.executable, where / "python.exe")
    (where / "pyvenv.cfg").write_text(f"home = {sys.base_prefix}\n")


def _fake_venv(co: Path, tmp: Path, torch: tuple[str, str | None] | None = None) -> Path:
    """Gives the checkout a ``.venv`` whose python runs, with ``torch`` (version, CUDA version; None for none) and a fake
    pip that writes its arguments down in the returned file, agrees to uninstall and refuses the rest, which ends a
    real run there, before any download. Set ``PYTHONPATH`` to the file's folder."""
    _working_python(co / ".venv" / "Scripts")
    fake = tmp / "fake_modules"
    fake.mkdir()
    (fake / "torch.py").write_text(
        f'__version__ = "{torch[0]}"\nclass version:\n    cuda = {torch[1]!r}\n' if torch else "raise ImportError\n")
    (fake / "pip.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        'with open(Path(__file__).with_name("pip-calls.txt"), "a") as f:\n    f.write(" ".join(sys.argv[1:]) + "\\n")\n'
        'if Path(__file__).with_name("no-pip").exists():\n    sys.exit(1)\n'
        'sys.exit(0 if sys.argv[1:2] in (["uninstall"], ["--version"]) else 5)\n')
    return fake / "pip-calls.txt"


def _whole_install(co: Path, tmp: Path, *, doctor: str = "Result: ready\n", doctor_code: int = 0) -> dict:
    """A run that gets to its end: `_fake_venv` with a pip that agrees, a ``taslation`` whose doctor prints *doctor*
    and ends with *doctor_code*, a ``setup_models.py`` that only says one line and writes its arguments down, and a
    fake ``ollama``. The result is the environment; a run writes ``fake_modules/pip-calls.txt``."""
    calls = _fake_venv(co, tmp, ("2.14.1+cpu", None))
    (calls.parent / "pip.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        'with open(Path(__file__).with_name("pip-calls.txt"), "a") as f:\n    f.write(" ".join(sys.argv[1:]) + "\\n")\n'
        'sys.exit(1 if Path(__file__).with_name("no-pip").exists() else 0)\n')
    (calls.parent / "taslation.py").write_text(
        f"import sys\nif __name__ == '__main__':\n    print({doctor!r})\n    sys.exit({doctor_code})\n")
    (co / "setup_models.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        'with open(Path(__file__).with_name("setup-args.txt"), "a") as f:\n    f.write(" ".join(sys.argv[1:]) + "\\n")\n'
        'print("Downloading fonts ...")\n')
    env = _tools(tmp, ollama=True, gpu=None)
    env["PYTHONPATH"] = str(calls.parent)
    return env


class _Ollama(http.server.BaseHTTPRequestHandler):
    models: list[str] = []

    def do_GET(self):
        body = json.dumps({"version": "0", "models": [{"name": m} for m in self.models]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def ollama_server():
    """A stand-in for Ollama's server, for copies told to ask it (`_ollama_at`): nothing asks the real one."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Ollama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def _ollama_at(script: Path, server, *models: str) -> None:
    _Ollama.models = list(models)
    _override(script, f"$OllamaUrl = 'http://127.0.0.1:{server.server_address[1]}'")


PAGE_MODELS_QUESTION = "Download these two models?"
LANGUAGE_QUESTION = "Translate into which language?"


def _answering(script: Path, answers: dict[str, str]) -> None:
    """Gives this temporary copy of a script a console: a question holding a key of ``answers`` gets its value and is
    printed as ``asked: <question> = <answer>``, any other question fails the run (the language is answered with
    Enter, the layout and inpainting models' question with no, unless they are given). Only the copy changes."""
    line = "$Interactive = (-not [Console]::IsInputRedirected) -and [Environment]::UserInteractive"
    text = script.read_bytes().decode("ascii")
    assert text.count(line) == 1
    rules = "".join(f"if ($Prompt.Contains('{question}')) {{ Write-Host \"asked: $Prompt = {answer}\"; return '{answer}' }}; "
                    for question, answer in {LANGUAGE_QUESTION: "", PAGE_MODELS_QUESTION: "n", **answers}.items())
    console = f"$Interactive = $true\r\nfunction Read-Host([string]$Prompt) {{ {rules}throw \"unexpected: $Prompt\" }}"
    script.write_bytes(text.replace(line, console).encode("ascii"))


REMOVE = "Remove TASlation?"
MODEL_NAME = "taslation-plamo3-translate-2b"  # the translator for English, the default target
QWEN_NAME = "qwen3.5:4b"
PLAMO_QUESTION = "Do you agree to the PLaMo Community License"


def _fake_state(tmp: Path) -> Path:
    state = tmp / "state"
    (state / "cache").mkdir(parents=True)
    (state / "cache" / "Book 1.json").write_text("{}")
    (state / "series").mkdir()
    (state / "notice.json").write_text("{}")
    return state


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("name", SCRIPTS)
def test_script_parses_and_has_the_documented_switches(shell, name):
    info = _parse(shell, ROOT / name)
    assert info["errors"] == []
    params = info["params"]
    if isinstance(params, dict):  # ConvertTo-Json unwraps a one-element array
        params = [params]
    assert {p["name"] for p in params} == SWITCHES[name]
    assert {p["type"] for p in params} == {"SwitchParameter"}
    # every switch is documented in the comment-based help (Get-Help lists it with its .PARAMETER text)
    assert set(info["help"]) >= SWITCHES[name]


@pytest.mark.parametrize("name", SCRIPTS + WRAPPERS)
def test_scripts_are_ascii(name):
    # Windows PowerShell 5.1 reads a file without a byte order mark in the ANSI code page, and cmd its own
    data = (ROOT / name).read_bytes()
    assert all(b < 128 for b in data)


@pytest.mark.parametrize("name", WRAPPERS)
def test_wrappers_are_crlf_and_run_their_script_with_every_argument(name):
    data = (ROOT / name).read_bytes()
    assert data.count(b"\n") == data.count(b"\r\n") > 0  # cmd loses labels and lines in a file with bare LF
    text = data.decode("ascii")
    script = name.replace(".cmd", ".ps1")
    assert f'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0{script}" %*' in text
    assert "pause" in text and "exit /b %CODE%" in text


def test_gitattributes_keep_crlf_in_a_zip_of_the_repository():
    rules = (ROOT / ".gitattributes").read_text(encoding="ascii").splitlines()
    assert "*.cmd text eol=crlf" in rules and "*.ps1 text eol=crlf" in rules


def _functions(*names: str, script: str = "install.ps1") -> str:
    """PowerShell that defines these functions as *script* has them, and nothing else of it."""
    wanted = ", ".join(f"'{n}'" for n in names)
    return (
        "$t = $null; $e = $null; "
        f"$a = [System.Management.Automation.Language.Parser]::ParseFile('{ROOT / script}', [ref]$t, [ref]$e); "
        "$fs = $a.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] "
        f"-and @({wanted}) -contains $n.Name }}, $true); foreach ($f in $fs) {{ Invoke-Expression $f.Extent.Text }}; "
    )


def _confirm(answer: str, interactive: bool, default_yes: bool, script: str = "install.ps1") -> bool:
    """Confirm-Choice taken out of a script and run with a console that gives ``answer``."""
    command = (
        _functions("Confirm-Choice", script=script)
        + f"function Read-Host {{ '{answer}' }}; function Write-Info {{ }}; "
        f"$Yes = $false; $DryRun = $false; $Interactive = ${str(interactive).lower()}; "
        f"Confirm-Choice 'Sure?' ${str(default_yes).lower()}"
    )
    r = _ps(RUN_SHELL, command)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip() == "True"


@pytest.mark.parametrize("answer, default_yes, expected", [
    ("", True, True), ("y", True, True), ("YES", True, True), ("n", True, False), ("what", True, False),
    ("", False, False), ("n", False, False), ("y", False, True), ("yes", False, True),
])
def test_a_question_takes_its_answer_from_the_console(answer, default_yes, expected):
    assert _confirm(answer, True, default_yes) is expected


@pytest.mark.parametrize("default_yes", [True, False])
def test_without_a_console_every_question_is_no(default_yes):
    assert _confirm("y", False, default_yes) is False


@pytest.mark.parametrize("script", SCRIPTS)
@pytest.mark.parametrize("answer", ["y", "yes", "\uff59", "\uff39", "\uff59\uff45\uff53", "\u306f\u3044", " \u306f\u3044\u3000"])
def test_what_a_japanese_keyboard_gives_counts_as_yes(script, answer):
    assert _confirm(answer, True, False, script) is True


@pytest.mark.parametrize("script", SCRIPTS)
@pytest.mark.parametrize("answer", ["", "n", "\uff4e", "\u3044\u3044\u3048"])
def test_anything_else_is_no(script, answer):
    assert _confirm(answer, True, False, script) is False


def test_uninstall_dry_run_deletes_nothing(tmp_path):
    co = _fake_checkout(tmp_path)
    state = _fake_state(tmp_path)
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    r = _run(co / "uninstall.ps1", "-DryRun", "-Yes", env=_env(tmp_path, TASLATION_STATE_DIR=str(state)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before
    out = r.stdout
    assert "DRY RUN" in out
    assert f"would: delete the virtual environment ({co / '.venv'}" in out
    assert f"would: delete the OCR model and fonts ({co / 'models'}" in out
    assert "would: delete your data folder" not in out
    assert "This cannot be undone [y/N] n (-Yes keeps this)" in out
    assert "holds your translations, notes and settings" in out
    assert "file(s)" not in out and "pip" not in out  # no listing of the data folder, no word on pip's cache
    assert REMOVE + " [y/N] (dry run: would ask; counted as y)" in out


def test_uninstall_lists_what_goes_and_enter_leaves_everything(tmp_path):
    co = _fake_checkout(tmp_path)
    state = _fake_state(tmp_path)
    _answering(co / "uninstall.ps1", {REMOVE: ""})
    r = _run(co / "uninstall.ps1", env=_hide_ollama(_env(tmp_path, TASLATION_STATE_DIR=str(state)), tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (co / ".venv").is_dir() and (co / "models").is_dir() and (state / "notice.json").is_file()
    out = r.stdout
    assert out.index("This removes:") < out.index("the program files") < out.index("asked: ")
    assert "reading model and fonts" in out and "Start-menu shortcut" in out and "Nothing was removed." in out


def test_uninstall_without_a_console_removes_nothing(tmp_path):
    co = _fake_checkout(tmp_path)
    r = _run(co / "uninstall.ps1", env=_hide_ollama(_env(tmp_path), tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (co / ".venv").is_dir() and (co / "models").is_dir()
    assert REMOVE + " [y/N] n (no console to ask)" in r.stdout


def test_uninstall_keeps_the_data_after_a_y_to_the_first_question_only(tmp_path):
    co = _fake_checkout(tmp_path)
    state = _fake_state(tmp_path)
    _answering(co / "uninstall.ps1", {REMOVE: "y", "This cannot be undone": ""})
    r = _run(co / "uninstall.ps1", env=_hide_ollama(_env(tmp_path, TASLATION_STATE_DIR=str(state)), tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (co / ".venv").exists()
    assert not (co / "models").exists()
    assert (state / "cache" / "Book 1.json").is_file() and (state / "notice.json").is_file()
    assert (co / "uninstall.ps1").is_file() and (co / "taslation" / "config.py").is_file()
    assert f"your data ({state})" in r.stdout  # listed under what was left
    assert "Uninstall Ollama itself" not in r.stdout  # no Ollama here, so no such question


def test_uninstall_yes_keeps_the_data_and_ollama(tmp_path):
    co = _fake_checkout(tmp_path)
    state = _fake_state(tmp_path)
    env = _tools(tmp_path, ollama=True)
    env["TASLATION_STATE_DIR"] = str(state)
    r = _run(co / "uninstall.ps1", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (co / ".venv").exists() and not (co / "models").exists()
    assert (state / "cache" / "Book 1.json").is_file() and (state / "notice.json").is_file()
    assert "This cannot be undone [y/N] n (-Yes keeps this)" in r.stdout
    assert f"your data ({state})" in r.stdout
    assert not (tmp_path / "bin" / "winget-args.txt").exists()
    assert "Other programs using it lose it [y/N] n (-Yes keeps this)" in r.stdout
    assert "Ollama (winget uninstall Ollama.Ollama, or Settings > Apps)" in r.stdout
    assert not (tmp_path / "bin" / "ollama-args.txt").exists()  # the model stays too


def test_uninstall_deletes_the_data_folder_after_a_y(tmp_path):
    co = _fake_checkout(tmp_path)
    state = _fake_state(tmp_path)
    env = _hide_ollama(_env(tmp_path, TASLATION_STATE_DIR=str(state)), tmp_path)
    _answering(co / "uninstall.ps1", {REMOVE: "y", "This cannot be undone": "y"})
    r = _run(co / "uninstall.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not state.exists()
    assert not (co / ".venv").exists() and not (co / "models").exists()
    assert (co / "uninstall.ps1").is_file()
    assert f"your data folder ({state}" in r.stdout


def test_uninstall_keeps_the_data_folder_on_enter(tmp_path):
    co = _fake_checkout(tmp_path)
    state = _fake_state(tmp_path)
    env = _hide_ollama(_env(tmp_path, TASLATION_STATE_DIR=str(state)), tmp_path)
    _answering(co / "uninstall.ps1", {REMOVE: "y", "This cannot be undone": ""})
    r = _run(co / "uninstall.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (state / "cache" / "Book 1.json").is_file()


def test_uninstall_asks_about_the_model_and_then_ollama_itself(tmp_path):
    co = _fake_checkout(tmp_path)
    env = _tools(tmp_path, ollama=True)
    env["TASLATION_STATE_DIR"] = str(tmp_path / "no data here")
    _answering(co / "uninstall.ps1", {REMOVE: "y", "Remove the translation model": "", "Uninstall Ollama itself": "y"})
    r = _run(co / "uninstall.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    question = ("Uninstall Ollama itself with winget too (winget uninstall Ollama.Ollama)? Other programs using it "
                "lose it [y/N] = y")
    assert question in out and out.index("Remove the translation model") < out.index("Uninstall Ollama itself")
    assert (tmp_path / "bin" / "winget-args.txt").read_text().split() == ["uninstall", "--id", "Ollama.Ollama", "--exact"]
    assert not (tmp_path / "bin" / "ollama-args.txt").exists()
    deleted, left = out[out.index("Deleted"):].split("Left in place")
    assert "- Ollama" in deleted
    assert "Ollama's model folder" in left and "ollama rm" not in left  # no such command once Ollama is gone


def test_uninstall_keeps_ollama_on_enter(tmp_path):
    co = _fake_checkout(tmp_path)
    env = _tools(tmp_path, ollama=True)
    env["TASLATION_STATE_DIR"] = str(tmp_path / "no data here")
    _answering(co / "uninstall.ps1", {REMOVE: "y", "Remove the translation model": "", "Uninstall Ollama itself": ""})
    r = _run(co / "uninstall.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (tmp_path / "bin" / "winget-args.txt").exists()
    left = r.stdout[r.stdout.index("Left in place"):]
    assert "Ollama (winget uninstall Ollama.Ollama, or Settings > Apps)" in left and "ollama rm" in left


def test_uninstall_never_deletes_the_checkout_as_a_data_folder(tmp_path):
    co = _fake_checkout(tmp_path)
    env = _hide_ollama(_env(tmp_path, TASLATION_STATE_DIR=str(co)), tmp_path)
    _answering(co / "uninstall.ps1", {REMOVE: "y", "This cannot be undone": "y"})
    r = _run(co / "uninstall.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (co / "uninstall.ps1").is_file() and (co / "pyproject.toml").is_file()
    assert "is not a folder this script deletes" in r.stdout


def test_install_dry_run_changes_nothing(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    shutil.rmtree(co / "models")
    shortcut = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/TASlation.lnk"
    had_shortcut = shortcut.exists()
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    r = _run(co / "install.ps1", "-DryRun", "-Yes", env=_env(tmp_path))
    if "Python is missing" in r.stdout:
        pytest.skip("no Python 3.11+ for the installer to find")
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before
    assert shortcut.exists() == had_shortcut
    out = r.stdout
    assert "[7/7]" in out and "Dry run finished; nothing was changed." in out
    assert "TASlation takes about" in out
    assert "download.pytorch.org/whl/cpu" in out
    assert "[backup]" in out
    assert "(dry run: would ask; counted as y)" in out  # the licence: a dry run goes on to show the rest


def test_install_dry_run_without_switches_asks_nothing(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    env = _hide_ollama(_env(tmp_path), tmp_path)
    r = _run(co / "install.ps1", "-DryRun", env=env)
    if "Python is missing" in r.stdout:
        pytest.skip("no Python 3.11+ for the installer to find")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "download.pytorch.org/whl/cpu" in r.stdout
    assert "https://ollama.com/download" in r.stdout or "dry run: would ask" in r.stdout
    assert not (co / ".venv").exists()


def test_install_offers_python_in_the_plan(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path, python=False))
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "Install Python 3.13 now (about" in out and "[Y/n] (dry run: would ask; counted as y)" in out
    assert ("would: winget install --id Python.Python.3.13 --exact --source winget --scope user "
            "--accept-source-agreements --accept-package-agreements") in out
    assert "a Y also accepts the terms winget shows for it" in out  # the question says what its Y agrees to
    assert "Python 3.13 (to download" in out
    assert "[7/7]" in out


def test_install_without_winget_gives_the_python_org_way(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path, python=False, winget=False))
    assert r.returncode == 1
    assert "https://www.python.org/downloads/windows/" in r.stdout and "Python is missing." in r.stdout
    assert "Install Python 3.13 now" not in r.stdout


def test_install_without_a_console_installs_no_python_unasked(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", env=_tools(tmp_path, python=False))
    assert r.returncode == 1
    assert "[Y/n] n (no console to ask" in r.stdout and "Python is missing." in r.stdout
    assert not (tmp_path / "bin" / "winget-args.txt").exists()


def test_install_finds_the_python_winget_just_installed(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", "-Yes", env=_tools(tmp_path, python=False))
    assert r.returncode == 1  # the fake py ends the run at the virtual environment
    assert "y (-Yes)" in r.stdout
    assert (tmp_path / "bin" / "winget-args.txt").read_text().split() == [
        "install", "--id", "Python.Python.3.13", "--exact", "--source", "winget", "--scope", "user",
        "--accept-source-agreements", "--accept-package-agreements"]
    assert "ok: Python 3.13.1 installed" in r.stdout
    assert "could not create" in r.stdout


def test_a_person_s_yes_accepts_wingets_agreements_so_that_winget_asks_nothing_later(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    _answering(co / "install.ps1", {"Install Python 3.13 now": "", "Install Ollama now": "", PLAMO_QUESTION: ""})  # Enter takes it
    r = _run(co / "install.ps1", env=_tools(tmp_path, python=False, gpu=None))
    assert r.returncode == 1  # the fake py ends the run at the virtual environment
    assert (tmp_path / "bin" / "winget-args.txt").read_text().split() == [
        "install", "--id", "Python.Python.3.13", "--exact", "--source", "winget", "--scope", "user",
        "--accept-source-agreements", "--accept-package-agreements"]
    out = r.stdout
    assert out.index("a Y also accepts the terms winget shows for it") < out.index("asked:   Install Python 3.13 now")


def test_install_yes_accepts_wingets_agreements_for_ollama(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", "-DryRun", "-Yes", env=_tools(tmp_path, gpu=None))
    assert ("winget install --id Ollama.Ollama --exact --source winget --accept-source-agreements "
            "--accept-package-agreements" in r.stdout)


@pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")
def test_install_finds_python_in_the_user_folder_with_nothing_on_the_path(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    env = _tools(tmp_path, python=False)
    exe_dir = Path(env["LOCALAPPDATA"]) / "Programs" / "Python" / "Python313"
    _working_python(exe_dir)
    r = _run(co / "install.ps1", "-DryRun", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Install Python 3.13 now" not in r.stdout
    assert f"{exe_dir / 'python.exe'} -m venv" in r.stdout.replace("\n  ", "")


LICENCE = "Do you agree to the terms of the OCR models?"
STOPPED = "TASlation cannot read pages without the OCR models"


def _without_the_model(tmp: Path) -> Path:
    co = _fake_checkout(tmp)
    shutil.rmtree(co / ".venv")
    shutil.rmtree(co / "models" / "manga-ocr-charspot-small")
    return co


def _nothing_done(co: Path, r) -> None:
    assert r.returncode == 1 and STOPPED in r.stdout and "Nothing was installed." in r.stdout
    assert not (co / ".venv").exists() and "[2/7]" not in r.stdout


def test_install_shows_the_terms_and_a_no_stops_it_with_nothing_done(tmp_path):
    co = _without_the_model(tmp_path)
    _answering(co / "install.ps1", {LICENCE: ""})  # Enter is no
    r = _run(co / "install.ps1", env=_tools(tmp_path))
    assert LICENCE + " [y/N] = " in r.stdout
    assert "NON-COMMERCIAL" in r.stdout and "CC BY-NC-SA 4.0" in r.stdout
    _nothing_done(co, r)


def test_install_goes_on_after_a_yes_to_the_licence(tmp_path):
    co = _without_the_model(tmp_path)
    _answering(co / "install.ps1", {LICENCE: "y", "Install Ollama now": "n"})
    r = _run(co / "install.ps1", env=_tools(tmp_path))
    assert r.returncode == 1 and "could not create" in r.stdout  # the fake py ends the run at the virtual environment
    assert STOPPED not in r.stdout


def test_install_yes_does_not_agree_to_the_licence(tmp_path):
    co = _without_the_model(tmp_path)
    r = _run(co / "install.ps1", "-Yes", env=_tools(tmp_path))
    assert "-Yes does not agree to a licence" in r.stdout
    _nothing_done(co, r)


def test_install_without_a_console_does_not_agree_to_the_licence(tmp_path):
    co = _without_the_model(tmp_path)
    r = _run(co / "install.ps1", env=_tools(tmp_path))
    assert LICENCE + " [y/N] n (no console to ask)" in r.stdout
    _nothing_done(co, r)


@pytest.mark.parametrize("switches", [(), ("-Yes",)], ids=["plain", "with -Yes"])
def test_install_does_not_ask_about_a_model_that_is_there(tmp_path, switches):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", "-DryRun", *switches, env=_tools(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert LICENCE not in r.stdout and "--skip-ocr" in r.stdout


def _old_install(tmp: Path) -> Path:
    """An install from before the three readers: charspot alone."""
    co = _fake_checkout(tmp)
    shutil.rmtree(co / ".venv")
    shutil.rmtree(co / "models" / "manga-ocr-nar-small")
    shutil.rmtree(co / "models" / "manga-ocr-base-CPT-flex")
    return co


def test_the_one_question_names_all_three_models_and_the_download(tmp_path):
    co = _old_install(tmp_path)
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count(LICENCE) == 1 and "--skip-ocr" not in r.stdout
    for model in OCR_MODELS:
        assert model.dirname in r.stdout
    assert f"about {sum(m.mb for m in OCR_MODELS) // 100 * 100} MB" in r.stdout


def test_a_no_on_an_old_install_leaves_it_reading_with_the_model_it_has(tmp_path):
    co = _old_install(tmp_path)
    _answering(co / "install.ps1", {LICENCE: "", "Install Ollama now": "n"})
    r = _run(co / "install.ps1", env=_tools(tmp_path))
    assert "goes on reading with the one model it has" in r.stdout and STOPPED not in r.stdout


def test_the_layout_and_inpainting_models_are_asked_about_and_fetched_on_a_yes(tmp_path):
    co = _without_the_model(tmp_path)
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path))
    assert PAGE_MODELS_QUESTION in r.stdout and "LaMa MIT" in r.stdout
    assert "--agreed" in r.stdout and "--skip-page-models" not in r.stdout


def test_the_size_on_disk_counts_the_models():
    assert re.search(r"\$SizeModels = ([0-9.]+)", (ROOT / "install.ps1").read_text(encoding="utf-8")).group(1) == "1.2"
    assert 1.0 <= sum(m.mb for m in (*OCR_MODELS, *PAGE_MODELS)) / 1000 < 1.15  # (and the fonts)


CPU_TORCH = "install --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cpu"
CUDA_TORCH = "install --disable-pip-version-check --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu126"
CPU_AGAIN = ("install --disable-pip-version-check --force-reinstall --no-deps torch "
             "--index-url https://download.pytorch.org/whl/cpu")
FELL_BACK = "The GPU build did not work on this computer, so the program files come in their CPU build instead."


def test_without_an_nvidia_gpu_the_cpu_build_comes_as_before(tmp_path):
    co = _without_the_model(tmp_path)
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path, gpu=None))
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "would: python -m pip " + CPU_TORCH in out and "torchvision" not in out
    assert "NVIDIA" not in out and "GPU build" not in out and "cu126" not in out
    assert "--agreed" in out  # the person agreed here: setup_models.py does not ask again
    assert PAGE_MODELS_QUESTION + " [y/N] (dry run" in out and "Enter here means yes" not in out


def test_an_nvidia_gpu_gets_the_gpu_build_unasked_and_its_download_is_said_first(tmp_path):
    co = _without_the_model(tmp_path)
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "ok: NVIDIA GPU: Fake GPU, 4096 MiB, driver 610.88" in out
    said = "This computer has an NVIDIA GPU, so the program files come in their GPU build: about 2.5 GB more to download."
    assert said in out and out.index(said) < out.index("No more questions.") < out.index("[3/7] Program files")
    assert "would: python -m pip " + CUDA_TORCH + " (driver 528.33 or newer), check torch.cuda on the GPU" in out
    assert "--force-reinstall --no-deps torch --index-url https://download.pytorch.org/whl/cpu" in out  # (the way back)
    assert "5.0 GB  program files, GPU build (to download)" in out
    assert PAGE_MODELS_QUESTION + " [Y/n] (dry run" in out and "so Enter here means yes" in out
    assert "?" not in out[out.index("[3/7]"):]  # nothing asked about it


@pytest.mark.parametrize("line, said", [
    ("NVIDIA GeForce RTX 5070, 12227 MiB, 610.88, 12.0",
     "come in their GPU build: about 1.9 GB more to download."),  # Blackwell: cu130
    ("Fake GPU, 4096 MiB, 525.60, 7.5",
     "The GPU build needs an NVIDIA driver of version 528.33 or newer, and this one is 525.60: the program files use "
     "their CPU build."),
    ("NVIDIA GeForce RTX 5070, 12227 MiB, 576.02, 12.0",
     "The GPU build needs an NVIDIA driver of version 580.00 or newer, and this one is 576.02"),
    ("NVIDIA Tesla K80, 11441 MiB, 470.82, 3.7",
     "This NVIDIA GPU is older than the GPU build supports: the program files use their CPU build."),
])
def test_the_gpu_and_its_driver_choose_the_build(tmp_path, line, said):
    co = _without_the_model(tmp_path)
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path, gpu=line))
    assert r.returncode == 0, r.stdout + r.stderr
    assert said in r.stdout
    if "GPU build:" in said:
        assert "--index-url https://download.pytorch.org/whl/cu130 (driver 580.00 or newer)" in r.stdout
        assert PAGE_MODELS_QUESTION + " [Y/n]" in r.stdout
    else:
        assert "would: python -m pip " + CPU_TORCH in r.stdout and "cu1" not in r.stdout
        assert PAGE_MODELS_QUESTION + " [y/N]" in r.stdout
    if "driver" in said:
        assert "To use the GPU, update the driver and run install.cmd again." in r.stdout


def test_a_driver_too_old_to_say_its_compute_capability_is_asked_without_it(tmp_path):
    co = _without_the_model(tmp_path)
    env = _tools(tmp_path)
    (tmp_path / "bin" / "nvidia-smi.cmd").write_text(
        '@echo off\nset "a=%*"\nif not "%a:compute_cap=%"=="%a%" exit /b 2\necho Old GPU, 2048 MiB, 472.12\n')
    r = _run(co / "install.ps1", "-DryRun", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "NVIDIA GPU: Old GPU, 2048 MiB, driver 472.12" in r.stdout
    assert "version 528.33 or newer, and this one is 472.12" in r.stdout


def _decide(torch: str, gpu: str | None, from_update: bool = False) -> str:
    """Get-TorchPlan as install.ps1 has it, for a torch of the kind *torch* there ('none', 'cpu', 'cuda') and what
    nvidia-smi says (*gpu*; None: it does not answer): "<build> <action> <uses the GPU> <note> <index>"."""
    text = (ROOT / "install.ps1").read_text(encoding="ascii")
    start = text.index("$TorchCudaBuilds = @(")
    constants = text[start:text.index("})", start) + 2] + "; "
    gpu_value = "$null" if gpu is None else "(ConvertTo-NvidiaGpu '" + gpu + "')"
    command = (_functions("Get-TorchPlan", "Get-CudaBuild", "ConvertTo-NvidiaGpu") + constants
               + f"$p = Get-TorchPlan ([pscustomobject]@{{ Kind = '{torch}'; Version = '' }}) {gpu_value} "
               + f"${str(from_update).lower()}; "
               + "$i = '-'; if ($p.Cuda) { $i = $p.Cuda.Index.Split('/')[-1] }; "
               + "\"$($p.Build) $($p.Action) $($p.UsesGpu) $(if ($p.Note) { $p.Note } else { '-' }) $i\"")
    r = _ps(RUN_SHELL, command)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


TURING = "NVIDIA GeForce GTX 1660 Ti, 6144 MiB, 610.88, 7.5"


@pytest.mark.parametrize("torch, gpu, from_update, decided", [
    ("none", None, False, "cpu install False - -"),  # no NVIDIA GPU, or nvidia-smi failed: as before
    ("none", TURING, False, "cuda install True - cu126"),
    ("none", "Quadro M4000, 8126 MiB, 610.88, 5.2", False, "cuda install True - cu126"),  # Maxwell: the last cu126
    ("none", "RTX PRO 6000, 97887 MiB, 610.88, 12.0", False, "cuda install True - cu130"),  # Blackwell
    ("none", "B200, 183359 MiB, 580.65, 10.0", False, "cuda install True - cu130"),
    ("none", "RTX 5090, 32607 MiB, 576.88, 12.0", False, "cpu install False driver -"),
    ("none", "GTX 1080, 8192 MiB, 528.33, 6.1", False, "cuda install True - cu126"),  # just new enough
    ("none", "GTX 1080, 8192 MiB, 527.56, 6.1", False, "cpu install False driver -"),
    ("none", "GTX 1080, 8192 MiB, 472.12", False, "cpu install False driver -"),  # no compute_cap: the first build
    ("none", "Tesla K40, 11441 MiB, 470.82, 3.5", False, "cpu install False gpu -"),
    ("none", "Some GPU", False, "cuda install True - cu126"),  # what is not said is not held against it
    ("cpu", TURING, False, "cuda replace True - cu126"),  # install.cmd again: the CPU build makes way
    ("cpu", TURING, True, "cpu keep False update cu126"),  # an update keeps it, and says how
    ("cpu", None, False, "cpu keep False - -"),
    ("cpu", None, True, "cpu keep False - -"),
    ("cpu", "GTX 1080, 8192 MiB, 527.56, 6.1", False, "cpu keep False driver -"),
    ("cuda", TURING, False, "cuda keep True - cu126"),  # a CUDA build is kept, as always
    ("cuda", TURING, True, "cuda keep True - cu126"),
    ("cuda", None, False, "cuda keep False - -"),
])
def test_what_the_program_files_get(torch, gpu, from_update, decided):
    assert _decide(torch, gpu, from_update) == decided


@pytest.mark.parametrize("line, parsed", [
    ("NVIDIA GeForce GTX 1660 Ti, 6144 MiB, 610.88, 7.5", "NVIDIA GeForce GTX 1660 Ti|6144|610.88|610.88|7.5"),
    ("  NVIDIA RTX A2000 Laptop GPU , 4096 MiB , 566.03 , 8.6 ", "NVIDIA RTX A2000 Laptop GPU|4096|566.3|566.03|8.6"),
    ("Old GPU, 2048 MiB, 472.12", "Old GPU|2048|472.12|472.12|-"),
    ("Odd GPU, [N/A], [N/A], [N/A]", "Odd GPU|0|-||-"),
    ("", "none"),
])
def test_nvidia_smi_s_line_is_read_field_by_field(line, parsed):
    command = (_functions("ConvertTo-NvidiaGpu") + f"$g = ConvertTo-NvidiaGpu '{line}'; "
               + "if ($null -eq $g) { 'none' } else { \"$($g.Name)|$($g.MemoryMb)|$(if ($g.Driver) { $g.Driver } else { '-' })"
               + "|$($g.DriverText)|$(if ($g.Compute) { $g.Compute } else { '-' })\" }")
    r = _ps(RUN_SHELL, command)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == parsed


def test_the_gpu_is_found_without_any_network():
    text = (ROOT / "install.ps1").read_text(encoding="ascii")
    body = text[text.index("function Find-NvidiaSmi"):text.index("function Get-CudaBuild")]
    for word in ("Invoke-WebRequest", "Invoke-RestMethod", "WebClient", "http", "pip"):
        assert word not in body, word


_TORCH = '''__version__ = "2.14.1+{kind}"


class version:
    cuda = {cuda!r}


class cuda:
    @staticmethod
    def is_available():
        return {usable!r}


class _Tensor:
    def __add__(self, other):
        return self

    def sum(self):
        return self

    def item(self):
        return 4


def ones(*args, **kwargs):
    return _Tensor()
'''


def _torch_install(co: Path, tmp: Path, ollama_server, *, torch: str = "none", gpu: str | None = GPU) -> dict:
    """`_whole_install` on a computer whose nvidia-smi says *gpu*, with *torch* ('none', 'cpu' or 'cuda') in the
    program files and a pip that installs a stand-in torch from the index it is given: the build named by the index
    (cu126 a CUDA 12.6 one), which runs on the GPU unless ``cuda-unusable`` is in fake_modules; ``cuda-pip-fails``
    there fails a GPU build's install. Everything else pip is asked agrees; its calls go to ``pip-calls.txt``."""
    env = _whole_install(co, tmp)
    fake = tmp / "fake_modules"
    (fake / "pip.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "here = Path(__file__).parent\nargs = sys.argv[1:]\n"
        'with open(here / "pip-calls.txt", "a") as f:\n    f.write(" ".join(args) + "\\n")\n'
        'if "torch" in args and "--index-url" in args:\n'
        '    kind = args[args.index("--index-url") + 1].rstrip("/").rsplit("/", 1)[-1]\n'
        '    if kind != "cpu" and (here / "cuda-pip-fails").exists():\n        sys.exit(1)\n'
        '    cuda = None if kind == "cpu" else kind[2:4] + "." + kind[4:]\n'
        '    usable = kind != "cpu" and not (here / "cuda-unusable").exists()\n'
        f'    (here / "torch.py").write_text({_TORCH!r}.format(kind=kind, cuda=cuda, usable=usable))\n'
        "sys.exit(0)\n")
    if torch == "none":
        (fake / "torch.py").write_text("raise ImportError\n")
    else:
        kind = "cpu" if torch == "cpu" else "cu126"
        (fake / "torch.py").write_text(_TORCH.format(kind=kind, cuda=None if torch == "cpu" else "12.6",
                                                     usable=torch != "cpu"))
    smi = "@echo off\nexit /b 1\n" if gpu is None else f"@echo off\necho {gpu}\n"
    (tmp / "bin" / "nvidia-smi.cmd").write_text(smi)
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # the stand-in torch changes within a second
    _ollama_at(co / "install.ps1", ollama_server, MODEL_NAME)
    return env


def _pip_calls(tmp: Path) -> list[str]:
    path = tmp / "fake_modules" / "pip-calls.txt"
    return [line for line in path.read_text().splitlines() if " torch " in f" {line} "] if path.exists() else []


needs_venv = pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")


@needs_venv
def test_a_gpu_gets_the_gpu_build_and_enter_takes_the_page_models(tmp_path, ollama_server):
    co = _fake_checkout(tmp_path)
    env = _torch_install(co, tmp_path, ollama_server)
    _answering(co / "install.ps1", {PAGE_MODELS_QUESTION: ""})
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "asked:   " + PAGE_MODELS_QUESTION + " [Y/n] = " in out
    assert out.index("so Enter here means yes") < out.index("asked:   " + PAGE_MODELS_QUESTION)
    reading = (co / "setup-args.txt").read_text().splitlines()[0]
    assert "--agreed" in reading and "--skip-page-models" not in reading
    assert _pip_calls(tmp_path) == [CUDA_TORCH]
    assert "Downloading the GPU build of the program files (about 2.6 GB)." in out
    assert "ok: program files ready, GPU build" in out and "TASlation is installed." in out
    assert "warning" not in out and FELL_BACK not in out


@needs_venv
def test_without_a_gpu_enter_leaves_the_page_models_out_and_the_cpu_build_comes(tmp_path, ollama_server):
    co = _fake_checkout(tmp_path)
    env = _torch_install(co, tmp_path, ollama_server, gpu=None)
    _answering(co / "install.ps1", {PAGE_MODELS_QUESTION: ""})
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "asked:   " + PAGE_MODELS_QUESTION + " [y/N] = " in out and "Enter here means yes" not in out
    assert "--skip-page-models" in (co / "setup-args.txt").read_text().splitlines()[0]
    assert _pip_calls(tmp_path) == [CPU_TORCH]  # exactly as before
    assert "GPU" not in out and "TASlation is installed." in out


@needs_venv
@pytest.mark.parametrize("switches", [(), ("-Yes",)], ids=["no console", "with -Yes"])
def test_nobody_s_enter_takes_the_page_models_on_a_gpu_either(tmp_path, ollama_server, switches):
    co = _fake_checkout(tmp_path)
    env = _torch_install(co, tmp_path, ollama_server)
    r = _run(co / "install.ps1", *switches, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    answer = "(-Yes does not answer this" if switches else "n (no console to ask)"
    assert PAGE_MODELS_QUESTION + " [Y/n] " + answer in out
    assert "--skip-page-models" in (co / "setup-args.txt").read_text().splitlines()[0]
    assert _pip_calls(tmp_path) == [CUDA_TORCH]  # the GPU build is no question: it comes all the same


@needs_venv
@pytest.mark.parametrize("trouble, cpu", [("cuda-pip-fails", CPU_TORCH), ("cuda-unusable", CPU_AGAIN)])
def test_a_gpu_build_that_fails_or_does_not_run_gives_way_to_the_cpu_build(tmp_path, ollama_server, trouble, cpu):
    """A GPU build that did not install leaves nothing for the CPU build to replace, so that one comes as it always
    did; one that installed and does not run is replaced by it, torch alone."""
    co = _fake_checkout(tmp_path)
    env = _torch_install(co, tmp_path, ollama_server)
    (tmp_path / "fake_modules" / trouble).write_text("")
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert _pip_calls(tmp_path) == [CUDA_TORCH, cpu]
    assert out.count("warning: " + FELL_BACK) == 1 and out.count(FELL_BACK) == 2  # (said, and listed at the end)
    assert "ok: program files ready" in out and "GPU build" not in out.split(FELL_BACK)[-1].split("warning(s)")[0]
    assert "TASlation is installed." in out
    assert "cpu" in (tmp_path / "fake_modules" / "torch.py").read_text()


@pytest.mark.parametrize("record, listed, left", [
    (None, "False", ["sympy"]),  # no torch at all: pip brings the CPU build as always
    (True, "True", ["functorch", "sympy", "torch", "torch-2.14.1+cu126.dist-info", "torchgen"]),  # pip's to replace
    (False, "False", ["sympy"]),  # unpacking stopped half way: no RECORD, so pip could not replace it
], ids=["none", "whole", "half unpacked"])
def test_a_gpu_build_left_half_unpacked_is_taken_out_for_the_cpu_build(tmp_path, record, listed, left):
    """Seen for real: a GPU build whose unpacking stopped (there a path too long; a full disk does the same) leaves
    torch without its RECORD file, and pip then refuses to uninstall it or to put the CPU build over it."""
    site = tmp_path / "venv" / "Lib" / "site-packages"
    (site / "sympy").mkdir(parents=True)
    if record is not None:
        info = site / "torch-2.14.1+cu126.dist-info"
        info.mkdir()
        (info / "METADATA").write_text("Name: torch\n")
        if record:
            (info / "RECORD").write_text("")
        for name in ("torch", "torchgen", "functorch"):
            (site / name / "lib").mkdir(parents=True)
            (site / name / "lib" / "part.dll").write_text("")
    command = (_functions("Clear-HalfInstalledTorch", "Write-Detail")
               + f"$DryRun = $false; $VenvPy = '{tmp_path / 'venv' / 'Scripts' / 'python.exe'}'; Clear-HalfInstalledTorch")
    r = _ps(RUN_SHELL, command)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == listed
    assert sorted(p.name for p in site.iterdir()) == left


@needs_venv
def test_a_cpu_build_on_a_gpu_is_replaced_and_one_that_does_not_download_stays(tmp_path, ollama_server):
    co = _fake_checkout(tmp_path)
    env = _torch_install(co, tmp_path, ollama_server, torch="cpu")
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert ("This computer has an NVIDIA GPU: the CPU build of the program files here is replaced by their GPU build "
            "(about 2.6 GB to download).") in r.stdout
    assert _pip_calls(tmp_path) == [CUDA_TORCH.replace("--no-cache-dir", "--no-cache-dir --force-reinstall --no-deps")]
    assert "ok: program files ready, GPU build" in r.stdout

    (tmp_path / "fake_modules" / "pip-calls.txt").unlink()
    (tmp_path / "fake_modules" / "torch.py").write_text(_TORCH.format(kind="cpu", cuda=None, usable=False))
    (tmp_path / "fake_modules" / "cuda-pip-fails").write_text("")
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(_pip_calls(tmp_path)) == 1 and FELL_BACK in r.stdout  # the CPU build there is kept, not fetched again
    assert "TASlation is installed." in r.stdout


@needs_venv
@pytest.mark.parametrize("variable", ["TASLATION_UPDATING", "TASLATION_UPDATE_PAUSE"],
                         ids=["update.ps1", "an earlier update.cmd"])
def test_an_update_keeps_a_cpu_build_and_says_how_to_get_the_gpu_build(tmp_path, ollama_server, variable):
    co = _fake_checkout(tmp_path)
    env = _torch_install(co, tmp_path, ollama_server, torch="cpu")
    env[variable] = "1"
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert _pip_calls(tmp_path) == [] and "ok: already there; kept" in out
    assert "This computer has an NVIDIA GPU, but the program files here are their CPU build, which an update keeps." in out
    assert "To use the GPU, run install.cmd: it fetches their GPU build (about 2.6 GB)." in out
    assert PAGE_MODELS_QUESTION + " [y/N] n (no console to ask)" in out  # LaMa would not run here by default


@needs_venv
def test_a_cuda_build_there_is_kept_and_makes_yes_the_default(tmp_path, ollama_server):
    co = _fake_checkout(tmp_path)
    env = _torch_install(co, tmp_path, ollama_server, torch="cuda")
    _answering(co / "install.ps1", {PAGE_MODELS_QUESTION: ""})
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _pip_calls(tmp_path) == [] and "asked:   " + PAGE_MODELS_QUESTION + " [Y/n] = " in r.stdout
    assert "--skip-page-models" not in (co / "setup-args.txt").read_text().splitlines()[0]


@pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")
@pytest.mark.parametrize("switches", [(), ("-Yes",)], ids=["plain", "with -Yes"])
def test_install_keeps_a_cuda_build(tmp_path, switches):
    co = _fake_checkout(tmp_path)
    calls = _fake_venv(co, tmp_path, ("2.14.1+cu126", "12.6"))
    env = _tools(tmp_path)
    env["PYTHONPATH"] = str(calls.parent)
    r = _run(co / "install.ps1", "-DryRun", *switches, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CUDA build already installed (torch 2.14.1+cu126); kept" in r.stdout


def test_install_dry_run_counts_the_shortcut_and_says_how_to_start(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Start menu?" not in r.stdout  # it is simply made
    assert "would: create the Start-menu shortcut" in r.stdout
    assert "To start it: open the Start menu and choose TASlation." in r.stdout
    assert "uninstall.cmd" in r.stdout


def _spaced_copy(tmp: Path) -> Path:
    (tmp / "unpacked").mkdir()
    # a Japanese name with a space, no .git in it
    folder = _fake_checkout(tmp / "unpacked", "\u7ffb\u8a33 taslation-main")
    shutil.rmtree(folder / ".venv")
    shutil.rmtree(folder / "models")
    return folder


def test_install_cmd_runs_from_a_folder_with_a_space_and_japanese(tmp_path):
    folder = _spaced_copy(tmp_path)
    before = sorted(p.relative_to(tmp_path) for p in folder.rglob("*"))
    r = _run_cmd(folder / "install.cmd", "-DryRun", env=_tools(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Dry run finished; nothing was changed." in r.stdout and "[7/7]" in r.stdout
    assert r.stdout.rstrip().endswith(". . .")  # the pause keeps the window open
    assert sorted(p.relative_to(tmp_path) for p in folder.rglob("*")) == before


def test_uninstall_cmd_runs_from_a_folder_with_a_space_and_japanese(tmp_path):
    folder = _spaced_copy(tmp_path)
    r = _run_cmd(folder / "uninstall.cmd", "-DryRun", env=_tools(tmp_path), stdin=None)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Left in place" in r.stdout and "winget uninstall Python.Python.3.13" in r.stdout


def test_install_cmd_passes_arguments_and_the_exit_code_on(tmp_path):
    folder = _spaced_copy(tmp_path)
    r = _run_cmd(folder / "install.cmd", "-DryRun", env=_tools(tmp_path, python=False, winget=False))
    assert r.returncode == 1
    assert "DRY RUN" in r.stdout and "Python is missing." in r.stdout


def test_install_cmd_does_not_wait_with_yes(tmp_path):
    folder = _spaced_copy(tmp_path)
    r = _run_cmd(folder / "install.cmd", "-DryRun", "-Yes", env=_tools(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert not r.stdout.rstrip().endswith(". . .")


def test_install_cmd_opened_inside_the_zip_says_to_unpack(tmp_path):
    # Explorer opens a file inside a ZIP alone in a temporary folder
    alone = tmp_path / "alone"
    alone.mkdir()
    shutil.copy2(ROOT / "install.cmd", alone / "install.cmd")
    r = _run_cmd(alone / "install.cmd")
    assert r.returncode == 1 and "Unpack the whole ZIP" in r.stdout


def test_what_the_translator_needs_is_taken_with_enter():
    text = (ROOT / "install.ps1").read_text(encoding="ascii")
    assert "(T 'Install Ollama now (about 3 GB)?') $true" in text
    assert re.search(r"now \(about 3\.3 GB\)\?'\) -f \$model\.Name, \$language\.Name\) \$true", text)


def test_only_one_line_of_each_script_can_write_the_user_environment():
    for name in SCRIPTS:
        lines = [line for line in (ROOT / name).read_text(encoding="ascii").splitlines() if "SetEnvironmentVariable" in line]
        assert len(lines) == 1 and lines[0].startswith("function Set-UserEnv("), name
    assert "setx" not in (ROOT / "install.ps1").read_text(encoding="ascii")  # nothing for the reader to type


# ---- the console call


def _console(tmp: Path, parent: str, *arguments: str) -> tuple[int, float]:
    """`Invoke-Console` on ``python <parent> <arguments>``: its result and how long it took."""
    folder = tmp / "with a space"
    folder.mkdir()
    (folder / "parent.py").write_text(parent)
    quoted = ", ".join("'" + a + "'" for a in (str(folder / "parent.py"), *arguments))
    command = (_functions("Invoke-Console", "Join-Arguments")
               + "function Write-Info { }; $ErrorActionPreference = 'Stop'; "
               + f"$w = [Diagnostics.Stopwatch]::StartNew(); $c = Invoke-Console '{sys.executable}' @({quoted}); "
               + "$w.Stop(); \"$c $($w.Elapsed.TotalSeconds)\"")
    r = _ps(RUN_SHELL, command, timeout=60)
    assert r.returncode == 0, r.stderr
    code, seconds = r.stdout.split()[-2:]
    return int(code), float(seconds.replace(",", "."))


def test_the_console_call_does_not_wait_for_what_a_program_leaves_running(tmp_path):
    # as Ollama's installer leaves the tray app: Start-Process -Wait in Windows PowerShell 5.1 would take the 12 seconds
    code, seconds = _console(tmp_path, (
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(12)'], stdin=subprocess.DEVNULL, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "sys.exit(7)\n"))
    assert code == 7 and seconds < 8


def test_the_console_call_keeps_arguments_whole(tmp_path):
    seen = tmp_path / "seen.json"
    code, _ = _console(tmp_path, (
        "import json, sys\n"
        f"open(r'{seen}', 'w').write(json.dumps(sys.argv[1:]))\n"), "plain", "a b", "C:\\with space\\", 'C:\\x y[backup]')
    assert code == 0
    assert json.loads(seen.read_text()) == ["plain", "a b", "C:\\with space\\", "C:\\x y[backup]"]


# ---- a folder or user name outside the ANSI code page


def _korean_copy(tmp: Path) -> Path:
    return _fake_checkout(tmp, "\ud55c\uae00 \ud3f4\ub354")


@pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")
def test_a_folder_outside_the_code_page_is_not_a_broken_install(tmp_path):
    co = _korean_copy(tmp_path)
    _fake_venv(co, tmp_path, ("2.14.1+cpu", None))
    env = _tools(tmp_path)
    env["PYTHONPATH"] = str(tmp_path / "fake_modules")
    r = _run(co / "install.ps1", "-DryRun", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "does not run" not in r.stdout and "program files found" in r.stdout
    assert str(co) in r.stdout  # and the screen shows the name


@pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")
def test_a_whole_install_in_such_a_folder_gets_to_the_end(tmp_path, ollama_server):
    co = _korean_copy(tmp_path)
    env = _whole_install(co, tmp_path)
    _ollama_at(co / "install.ps1", ollama_server, MODEL_NAME)
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TASlation is installed." in r.stdout


# ---- every question first


def test_every_question_comes_before_the_first_download(tmp_path):
    co = _without_the_model(tmp_path)
    questions = ("Do you agree", "Install Python 3.13 now", "Install Ollama now", PLAMO_QUESTION)
    _answering(co / "install.ps1", {q: "y" for q in questions})
    r = _run(co / "install.ps1", env=_tools(tmp_path, python=False, gpu=None))
    out = r.stdout
    places = [out.index("asked:   " + q) for q in (LANGUAGE_QUESTION, *questions)] + [
        out.index("No more questions."), out.index("[3/7] Program files"), out.index("could not create")]
    assert places == sorted(places)
    assert "minutes, depending on your connection" in out and "You can leave it running." in out
    assert (tmp_path / "bin" / "winget-args.txt").is_file()  # Python comes after the last answer


def test_python_is_not_installed_after_a_no(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    _answering(co / "install.ps1", {"Install Python 3.13 now": "n"})
    r = _run(co / "install.ps1", env=_tools(tmp_path, python=False))
    assert r.returncode == 1 and "Python is missing." in r.stdout and "[2/7]" not in r.stdout
    assert not (tmp_path / "bin" / "winget-args.txt").exists()


# ---- a whole install


READER_NEVER_SEES = (".venv", "winget", "ollama pull", "setup_models", "doctor", "editable", "CUDA", "config.py",
                     "> python", "python.exe", "PyTorch", "backup")


@pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")
def test_a_whole_install_says_nothing_of_its_insides_and_ends_ready(tmp_path, ollama_server):
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path)
    _ollama_at(co / "install.ps1", ollama_server)  # the model is not there yet
    _answering(co / "install.ps1", {PLAMO_QUESTION: "y"})
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert [word for word in READER_NEVER_SEES if word in out] == []
    for title in ("This computer", "Disk space", "Program files", "TASlation and its parts", "Reading model and fonts",
                  "Ollama and the translation model", "Final check"):
        assert title in out
    assert out.index("Final check") < out.index("ok: ready") < out.index("TASlation is installed.")
    assert "Version: 0.1.0, files dated " in out and "Translating is not ready" not in out
    assert (tmp_path / "start menu" / "TASlation.lnk").is_file()
    assert not (tmp_path / "bin" / "ollama-args.txt").exists()  # setup_models.py installs the translator
    reading, translator = (co / "setup_models.py").with_name("setup-args.txt").read_text().splitlines()
    assert "--brief" in reading and "--skip-ocr" in reading
    assert "--skip-page-models" in reading and "They are left out" in out  # a no goes on without them
    assert translator.endswith(f"--translator-for English --brief --plamo-agreed install --ollama-exe {tmp_path / 'bin' / 'ollama.cmd'}")
    assert "-e" in (tmp_path / "fake_modules" / "pip-calls.txt").read_text()


@pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")
def test_what_is_missing_is_all_the_final_check_shows(tmp_path, ollama_server):
    co = _fake_checkout(tmp_path)
    doctor = ("taslation 0.1.0  python 3.13  win32\nConfig file: none\n"
              f"  configured model '{MODEL_NAME}': NOT INSTALLED -> run install.cmd again\nResult: something is missing (see above)")
    env = _whole_install(co, tmp_path, doctor=doctor, doctor_code=1)
    _ollama_at(co / "install.ps1", ollama_server, MODEL_NAME)
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "NOT INSTALLED" in out and "Config file" not in out and "Result:" not in out
    assert "Translating is not ready yet: run install.cmd again." in out
    assert "TASlation is installed." not in out


@pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")
def test_a_no_to_ollama_ends_not_ready_and_points_at_the_installer(tmp_path):
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path, doctor="Ollama: not installed", doctor_code=1)
    (tmp_path / "bin" / "ollama.cmd").unlink()
    _answering(co / "install.ps1", {"Install Ollama now": "n"})
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "Ollama is not installed. To add it, run install.cmd again." in out
    assert "Translating is not ready yet: run install.cmd again." in out
    assert "Download the translation model" not in out and "ollama pull" not in out
    assert not (tmp_path / "bin" / "winget-args.txt").exists()


@pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")
def test_details_are_there_in_a_dry_run(tmp_path, ollama_server):
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path)
    _ollama_at(co / "install.ps1", ollama_server, MODEL_NAME)
    r = _run(co / "install.ps1", "-DryRun", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CPU build already installed" in r.stdout and "for English (the language from built-in)" in r.stdout
    assert "goes to" in r.stdout and "taslation doctor" in r.stdout


# ---- window closed while the program folder was made


def test_a_program_folder_without_pip_is_repaired_before_any_download(tmp_path, ollama_server):
    if sys.prefix == sys.base_prefix:
        pytest.skip("needs a virtual environment's launcher to copy")
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path)
    _ollama_at(co / "install.ps1", ollama_server, MODEL_NAME)
    fake = tmp_path / "fake_modules"
    (fake / "no-pip").write_text("")
    (fake / "ensurepip.py").write_text(
        "from pathlib import Path\nPath(__file__).with_name('no-pip').unlink()\n"
        "Path(__file__).with_name('ensurepip-ran').write_text('')\n")
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (fake / "ensurepip-ran").is_file() and "Repairing them." in r.stdout
    assert "check the network" not in r.stdout.lower() and "TASlation is installed." in r.stdout


def test_a_program_folder_pip_cannot_be_put_into_is_made_again(tmp_path, ollama_server):
    if sys.prefix == sys.base_prefix:
        pytest.skip("needs a virtual environment's launcher to copy")
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path)
    _ollama_at(co / "install.ps1", ollama_server, MODEL_NAME)
    fake = tmp_path / "fake_modules"
    (fake / "no-pip").write_text("")
    (fake / "ensurepip.py").write_text("raise SystemExit(1)\n")
    (co / ".venv" / "leftover").write_text("")
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 1  # the fake py refuses to make it
    assert "could not create" in r.stdout and not (co / ".venv").exists()


# ---- failures


def _low_disk(script: Path) -> None:
    _override(script, "function Get-FreeGB([string]$Path) { return 0.1 }")


@pytest.mark.parametrize("switches", [(), ("-Yes",)], ids=["no console", "with -Yes"])
def test_too_little_disk_stops_before_any_download(tmp_path, switches):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    _low_disk(co / "install.ps1")
    r = _run(co / "install.ps1", *switches, env=_tools(tmp_path, gpu=None))
    assert r.returncode == 1 and "too little disk space" in r.stdout and "[3/7]" not in r.stdout
    assert not (tmp_path / "bin" / "winget-args.txt").exists()


def test_a_person_may_go_on_with_too_little_disk(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    _low_disk(co / "install.ps1")
    _answering(co / "install.ps1", {"Install Ollama now": "", PLAMO_QUESTION: "", "Go on anyway": "y"})
    r = _run(co / "install.ps1", env=_tools(tmp_path, gpu=None))
    assert "[3/7]" in r.stdout and "could not create" in r.stdout  # the fake py ends it


def _short_limit(script: Path, enabled: bool) -> None:
    _override(script, "$MaxRootLength = 5", f"function Test-LongPathsEnabled {{ return ${str(enabled).lower()} }}")


def test_a_long_path_stops_with_a_plain_message(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    _short_limit(co / "install.ps1", False)
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path))
    assert r.returncode == 1 and "path is too long" in r.stdout and "somewhere shorter" in r.stdout


def test_a_long_path_is_fine_with_long_paths_enabled(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    _short_limit(co / "install.ps1", True)
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path))
    assert r.returncode == 0 and "too long" not in r.stdout


def test_the_real_limit_leaves_room_for_the_longest_file():
    """The root, a backslash and the longest file in .venv (154 characters, measured in torch 2.15.0's CPU wheel) stay
    under 260, the length at which Windows without long paths no longer opens a file."""
    text = (ROOT / "install.ps1").read_text(encoding="ascii")
    assert "$MaxRootLength = 100" in text and 100 + 1 + 154 < 260


@pytest.mark.parametrize("nested", ["taslation-main", "taslation-1.0", "copy"])
def test_an_update_copied_one_level_too_deep_is_warned_about(tmp_path, nested):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    (co / nested).mkdir()
    (co / nested / "install.ps1").write_text("")
    (co / nested / "pyproject.toml").write_text("")
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"The folder {nested} inside this one holds another copy" in r.stdout
    assert "choose Replace" in r.stdout


def test_no_nested_copy_no_warning(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path))
    assert "another copy" not in r.stdout


# ---- the KV cache


def _kv_env(env: dict) -> dict:
    env.pop("OLLAMA_KV_CACHE_TYPE", None)
    return env


@pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="needs a virtual environment's launcher to copy")
def test_a_small_gpu_gets_the_setting_with_a_plain_line_and_uninstall_takes_it_back(tmp_path, ollama_server):
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path)
    (tmp_path / "bin" / "nvidia-smi.cmd").write_text("@echo off\necho Fake GPU, 4096 MiB\n")
    _ollama_at(co / "install.ps1", ollama_server, MODEL_NAME)
    r = _run(co / "install.ps1", env=_kv_env(env))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "This GPU has 6 GB or less, so Ollama is set to use less of its memory, and Ollama restarts." in r.stdout
    log = tmp_path / "user-env.txt"
    assert log.read_text().splitlines() == ["OLLAMA_KV_CACHE_TYPE=q8_0", "stopped Ollama"]
    assert (co / ".kv-cache-by-install").is_file()

    log.unlink()
    env["FAKE_USER_OLLAMA_KV_CACHE_TYPE"] = "q8_0"
    r = _run(co / "uninstall.ps1", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert log.read_text().splitlines() == ["OLLAMA_KV_CACHE_TYPE="]
    assert not (co / ".kv-cache-by-install").exists()
    assert "the Ollama setting the install made" in r.stdout


@pytest.mark.parametrize("value, marker", [("q8_0", False), ("q4_0", True)], ids=["not set by the install", "changed since"])
def test_uninstall_leaves_a_setting_that_is_not_the_installs(tmp_path, value, marker):
    co = _fake_checkout(tmp_path)
    if marker:
        (co / ".kv-cache-by-install").write_text("q8_0")
    env = _hide_ollama(_env(tmp_path, FAKE_USER_OLLAMA_KV_CACHE_TYPE=value), tmp_path)
    r = _run(co / "uninstall.ps1", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (tmp_path / "user-env.txt").exists()


def test_a_set_variable_is_left_alone(tmp_path, ollama_server):
    if sys.prefix == sys.base_prefix:
        pytest.skip("needs a virtual environment's launcher to copy")
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path)
    (tmp_path / "bin" / "nvidia-smi.cmd").write_text("@echo off\necho Fake GPU, 4096 MiB\n")
    _ollama_at(co / "install.ps1", ollama_server, MODEL_NAME)
    env = _kv_env(env)
    env["FAKE_USER_OLLAMA_KV_CACHE_TYPE"] = "q4_0"
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (tmp_path / "user-env.txt").exists() and not (co / ".kv-cache-by-install").exists()


def test_the_script_says_what_it_does_to_ollama():
    text = (ROOT / "install.ps1").read_text(encoding="ascii")
    head = " ".join(text[:text.index("[CmdletBinding()]")].split())
    assert "Ollama then restarts once" in head
    assert "on every computer with Ollama it sets LLAMA_ARG_CACHE_RAM=0 for your user." in head
    assert "up to 8 GB of RAM as a cache of earlier requests" in head and "LLAMA_ARG_* variables" in head
    assert "no faster with a GPU, and about 8 % faster without one" in head  # what was measured, both ways
    assert "on an NVIDIA GPU of 6 GB or less it sets OLLAMA_KV_CACHE_TYPE=q8_0 for your user" in head
    assert ".cache-ram-by-install" in head and ".kv-cache-by-install" in head
    assert "uninstall.cmd then clears each variable if it still has that value" in head
    head = " ".join((ROOT / "uninstall.ps1").read_text(encoding="ascii").split("[CmdletBinding()]")[0].split())
    assert "LLAMA_ARG_CACHE_RAM (the file .cache-ram-by-install says so) and it is still 0" in head


# ---- no prompt cache in Ollama's RAM


CACHE_RAM_SAID = (
    "Ollama is set to keep no cache of earlier requests in RAM (LLAMA_ARG_CACHE_RAM=0 for this Windows user), and "
    "Ollama restarts.",
    "Otherwise Ollama keeps up to 8 GB of RAM for that cache. In TASlation's measurements it made translation no "
    "faster with a GPU, and about 8 % faster without one.",
    "It applies to the Ollama this user runs, and to any other program of this user that reads llama.cpp's "
    "LLAMA_ARG_* settings.",
    'To undo it: uninstall.cmd clears it, or delete LLAMA_ARG_CACHE_RAM in "Edit environment variables for your '
    'account" (search the Start menu for that).',
)
CACHE_RAM_DONE = "ok: Ollama keeps no cache of earlier requests in RAM"
CACHE_RAM_MARKER = ".cache-ram-by-install"


def _cache_env(env: dict, **user: str) -> dict:
    """*env* without the guard's LLAMA_ARG_CACHE_RAM (and OLLAMA_KV_CACHE_TYPE): the install's steps run as on a
    computer that has neither; *user* holds what the fake user environment has (`FAKE_USER_<name>`)."""
    env.pop("LLAMA_ARG_CACHE_RAM", None)
    env.pop("OLLAMA_KV_CACHE_TYPE", None)
    env.update({f"FAKE_USER_{name}": value for name, value in user.items()})
    return env


def _user_env_log(tmp: Path) -> list[str]:
    log = tmp / "user-env.txt"
    return log.read_text().splitlines() if log.exists() else []


@needs_venv
@pytest.mark.parametrize("gpu", [None, "Fake GPU, 8192 MiB, 610.88, 7.5"], ids=["no GPU", "a GPU of 8 GB"])
@pytest.mark.parametrize("switches", [(), ("-Yes",)], ids=["no console", "with -Yes"])
def test_every_computer_with_ollama_gets_no_prompt_cache_and_uninstall_takes_it_back(tmp_path, ollama_server, gpu,
                                                                                      switches):
    co = _fake_checkout(tmp_path)
    env = _cache_env(_torch_install(co, tmp_path, ollama_server, torch="cpu" if gpu is None else "cuda", gpu=gpu))
    r = _run(co / "install.ps1", *switches, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    for line in CACHE_RAM_SAID:  # what, for whom, why and how to undo it, before it is done ...
        assert "  " + line in out, line
    assert out.index(CACHE_RAM_SAID[-1]) < out.index(CACHE_RAM_DONE) < out.index("[7/7]")  # ... and done
    assert _user_env_log(tmp_path) == ["LLAMA_ARG_CACHE_RAM=0", "stopped Ollama"]  # (no GPU setting: not a small GPU)
    assert (co / CACHE_RAM_MARKER).read_text().strip() == "0" and not (co / ".kv-cache-by-install").exists()
    assert "TASlation is installed." in out and "warning" not in out

    (tmp_path / "user-env.txt").unlink()
    r = _run(co / "uninstall.ps1", "-Yes", env=_cache_env(env, LLAMA_ARG_CACHE_RAM="0"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _user_env_log(tmp_path) == ["LLAMA_ARG_CACHE_RAM="]  # cleared for the user
    assert not (co / CACHE_RAM_MARKER).exists()
    assert "- the Ollama setting the install made (LLAMA_ARG_CACHE_RAM=0)" in r.stdout


@needs_venv
def test_a_small_gpu_gets_both_settings_and_ollama_restarts_once(tmp_path, ollama_server):
    co = _fake_checkout(tmp_path)
    env = _cache_env(_torch_install(co, tmp_path, ollama_server, torch="cuda", gpu=TURING))
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert _user_env_log(tmp_path) == ["OLLAMA_KV_CACHE_TYPE=q8_0", "LLAMA_ARG_CACHE_RAM=0", "stopped Ollama"]
    assert (co / ".kv-cache-by-install").is_file() and (co / CACHE_RAM_MARKER).is_file()
    said = out.index("This GPU has 6 GB or less, so Ollama is set to use less of its memory, and Ollama restarts.")
    assert said < out.index(CACHE_RAM_SAID[0]) < out.index("ok: Ollama set up for this GPU") < out.index(CACHE_RAM_DONE)

    (tmp_path / "user-env.txt").unlink()
    env = _cache_env(env, LLAMA_ARG_CACHE_RAM="0", OLLAMA_KV_CACHE_TYPE="q8_0")
    r = _run(co / "uninstall.ps1", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _user_env_log(tmp_path) == ["OLLAMA_KV_CACHE_TYPE=", "LLAMA_ARG_CACHE_RAM="]
    assert not (co / ".kv-cache-by-install").exists() and not (co / CACHE_RAM_MARKER).exists()


@needs_venv
@pytest.mark.parametrize("where, value", [("process", "4096"), ("user", "4096"), ("user", "0"), ("process", "0")])
def test_a_cache_setting_already_there_is_left_alone_without_a_word(tmp_path, ollama_server, where, value):
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path)
    _ollama_at(co / "install.ps1", ollama_server, MODEL_NAME)
    env = _cache_env(env, **({"LLAMA_ARG_CACHE_RAM": value} if where == "user" else {}))
    if where == "process":
        env["LLAMA_ARG_CACHE_RAM"] = value
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _user_env_log(tmp_path) == [] and not (co / CACHE_RAM_MARKER).exists()
    assert "LLAMA_ARG_CACHE_RAM" not in r.stdout and "cache of earlier requests" not in r.stdout
    assert "TASlation is installed." in r.stdout


@needs_venv
def test_without_ollama_nothing_is_set(tmp_path):
    co = _fake_checkout(tmp_path)
    env = _cache_env(_whole_install(co, tmp_path))
    (tmp_path / "bin" / "ollama.cmd").unlink()
    r = _run(co / "install.ps1", env=env)
    assert "Install Ollama now (about 3 GB)? [Y/n] n (no console to ask)" in r.stdout
    assert _user_env_log(tmp_path) == [] and not (co / CACHE_RAM_MARKER).exists()
    assert "LLAMA_ARG_CACHE_RAM" not in r.stdout


@pytest.mark.parametrize("ollama", [True, False], ids=["Ollama there", "Ollama to install"])
def test_a_dry_run_plans_the_setting_and_changes_nothing(tmp_path, ollama):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    env = _cache_env(_tools(tmp_path, ollama=ollama, gpu=None))
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    r = _run(co / "install.ps1", "-DryRun", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert f"would: set LLAMA_ARG_CACHE_RAM=0 for this user (and write {co / CACHE_RAM_MARKER})" in out
    assert "detail: so that Ollama keeps no cache of earlier requests in RAM, up to 8 GB otherwise" in out
    assert out.count("would: start Ollama again if it is running (once), so that it reads what was set") == 1
    assert "OLLAMA_KV_CACHE_TYPE" not in out  # (no GPU)
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before
    env["FAKE_USER_LLAMA_ARG_CACHE_RAM"] = "512"
    r = _run(co / "install.ps1", "-DryRun", "-Yes", env=env)
    assert "detail: LLAMA_ARG_CACHE_RAM is set already (512); left as it is" in r.stdout
    assert "would: set LLAMA_ARG_CACHE_RAM" not in r.stdout and "would: start Ollama again" not in r.stdout


@pytest.mark.parametrize("value, marker", [("0", False), ("4096", True)], ids=["not set by the install", "changed since"])
def test_uninstall_leaves_a_cache_setting_that_is_not_the_installs(tmp_path, value, marker):
    co = _fake_checkout(tmp_path)
    if marker:
        (co / CACHE_RAM_MARKER).write_text("0")
    env = _hide_ollama(_env(tmp_path, FAKE_USER_LLAMA_ARG_CACHE_RAM=value), tmp_path)
    r = _run(co / "uninstall.ps1", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _user_env_log(tmp_path) == [] and "LLAMA_ARG_CACHE_RAM" not in r.stdout
    assert not (co / CACHE_RAM_MARKER).exists()  # the marker goes all the same


def test_uninstall_dry_run_says_it_would_clear_the_setting_and_clears_nothing(tmp_path):
    co = _fake_checkout(tmp_path)
    (co / CACHE_RAM_MARKER).write_text("0")
    env = _hide_ollama(_env(tmp_path, FAKE_USER_LLAMA_ARG_CACHE_RAM="0"), tmp_path)
    r = _run(co / "uninstall.ps1", "-DryRun", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "would: clear LLAMA_ARG_CACHE_RAM for this user" in r.stdout
    assert _user_env_log(tmp_path) == [] and (co / CACHE_RAM_MARKER).is_file()


@needs_venv
def test_on_a_japanese_pc_the_setting_is_explained_in_japanese(tmp_path, ollama_server):
    ja = {english: texts["ja"] for english, texts in _texts().items()}
    co = _fake_checkout(tmp_path)
    env = _cache_env(_torch_install(co, tmp_path, ollama_server, torch="cpu", gpu=None))
    env["FAKE_UI_CULTURE"] = "ja-JP"
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    for line in CACHE_RAM_SAID + (CACHE_RAM_DONE.removeprefix("ok: "),):
        assert ja[line] in r.stdout and line not in r.stdout, line
    assert "LLAMA_ARG_CACHE_RAM=0" in ja[CACHE_RAM_SAID[0]] and "8 GB" in ja[CACHE_RAM_SAID[1]] and "8 %" in ja[CACHE_RAM_SAID[1]]
    assert "uninstall.cmd" in ja[CACHE_RAM_SAID[-1]] and "LLAMA_ARG_CACHE_RAM" in ja[CACHE_RAM_SAID[-1]]


def test_ollama_is_given_as_long_as_the_install_gives_it():
    from taslation import ollama_start

    assert ollama_start.START_WAIT_S == 30
    assert "$i -lt 30" in (ROOT / "install.ps1").read_text(encoding="ascii")


# ---- the translator model the language needs


def test_plamo_s_licence_is_shown_and_its_agreement_passed_on(tmp_path):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", "-DryRun", env=_tools(tmp_path, ollama=True, gpu=None))
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "PLaMo Community License" in out and "non-commercial use is free" in out and "article 5" in out
    assert "https://plamo.preferredai.jp/info/plamo-community-license-en" in out
    assert PLAMO_QUESTION + " (PLaMo is then downloaded)? [y/N] (dry run: would ask; counted as y)" in out
    assert "--translator-for English --brief --plamo-agreed install" in out
    assert "translation model PLaMo 3 Translate 2B (to download)" in out


@pytest.mark.parametrize("switches", [(), ("-Yes",)], ids=["no console", "with -Yes"])
def test_nobody_s_yes_agrees_to_plamo_and_the_install_goes_on(tmp_path, switches):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    r = _run(co / "install.ps1", *switches, env=_tools(tmp_path, ollama=True, gpu=None))
    out = r.stdout
    assert PLAMO_QUESTION in out and "PLaMo is left out" in out
    assert "[3/7]" in out  # (the fake py ends it there)
    if switches:
        assert "-Yes does not agree to a licence" in out


def test_a_no_to_plamo_installs_no_translator(tmp_path, ollama_server):
    if sys.prefix == sys.base_prefix:
        pytest.skip("needs a virtual environment's launcher to copy")
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path, doctor="Ollama: model missing", doctor_code=1)
    _ollama_at(co / "install.ps1", ollama_server)
    _answering(co / "install.ps1", {PLAMO_QUESTION: ""})
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert len((co / "setup_models.py").with_name("setup-args.txt").read_text().splitlines()) == 1  # the reading part
    assert "The translation model was not downloaded" in r.stdout


@pytest.mark.parametrize("where", ["ui.json", "toml", "culture"])
def test_turkish_takes_qwen_with_its_own_question(tmp_path, where):
    co = _fake_checkout(tmp_path)
    shutil.rmtree(co / ".venv")
    env = _tools(tmp_path, ollama=True, gpu=None)
    if where == "ui.json":
        state = tmp_path / "state"
        state.mkdir()
        (state / "ui.json").write_text(json.dumps({"translation": {"language": "Turkish"}}), "utf-8")
        env["TASLATION_STATE_DIR"] = str(state)
    elif where == "toml":
        (co / "taslation.toml").write_text('target_language = "Turkish"\n', "utf-8")
    else:
        env["FAKE_UI_CULTURE"] = "tr-TR"
    r = _run(co / "install.ps1", "-DryRun", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert f"Download the translation model {QWEN_NAME} for Turkish now (about 3.3 GB)? [Y/n]" in out
    assert "PLaMo" not in out and "--translator-for Turkish --brief --ollama-exe" in out


def test_a_portuguese_pc_starts_with_qwen():
    command = _functions("Get-TargetLanguage", "Get-TomlValue", "Get-StateDir", "Get-WindowTarget", "Get-LanguageCode") + (
        f"$Root = '{ROOT / 'nowhere'}'; function Get-UiCulture {{ 'pt-BR' }}; "
        "$env:TASLATION_STATE_DIR = 'C:\\nowhere-state'; (Get-TargetLanguage).Name")
    r = _ps(RUN_SHELL, command)
    assert r.stdout.strip() == "Portuguese (Brazil)", r.stderr


def test_the_script_picks_the_translator_as_taslation_does():
    from taslation.translate.models import model_for_language
    from taslation.ui.constants import LANGUAGES

    from taslation.translate.models import PLAMO_CODES, QWEN_LANGUAGES

    text = (ROOT / "install.ps1").read_text(encoding="ascii")
    constants = "".join(line + "; " for line in text.splitlines()
                        if line.startswith(("$SizeLlm =", "$SizePlamo =", "$PlamoName =", "$QwenName =", "$QwenLanguages =")))
    plamo = re.search(r"^\$PlamoLanguages = @\((.*?)\)$", text, re.M | re.S)
    assert plamo, "install.ps1 lists the languages PLaMo writes"
    constants += "$PlamoLanguages = @(" + " ".join(plamo.group(1).split()) + "); "
    # the window's names, the other spellings models.py knows, codes, odd spacing and case, and a language PLaMo lacks
    languages = [*LANGUAGES, *sorted(QWEN_LANGUAGES), *sorted(PLAMO_CODES), "zh-hant", "en", "  Portuguese  (Brazil) ",
                 "TURKISH", "Klingon"]
    names = ", ".join("'" + language.replace("'", "''") + "'" for language in languages)
    command = _functions("Get-Translator") + constants + f"foreach ($l in @({names})) {{ (Get-Translator $l).Name }}"
    r = _ps(RUN_SHELL, command)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == [model_for_language(language).ollama_name for language in languages]


# ---- uninstall: the translation models TASlation installed


def _record(state: Path, *names: str) -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / "translator_models.json").write_text(json.dumps(
        {"installed": {n: {"when": "2026-11-06T00:00:00+00:00", "size_gb": 1.81} for n in names},
         "agreed": {"plamo-community-license": {"when": "2026-11-06T00:00:00+00:00", "where": "install"}}}), "utf-8")


def test_uninstall_asks_only_about_the_models_taslation_installed(tmp_path):
    co = _fake_checkout(tmp_path)
    state = tmp_path / "state"
    _record(state, MODEL_NAME)
    env = _tools(tmp_path, ollama=True)
    env["TASLATION_STATE_DIR"] = str(state)
    _answering(co / "uninstall.ps1", {REMOVE: "y", "This cannot be undone": "", "that TASlation installed": "y",
                                      "Uninstall Ollama itself": ""})
    r = _run(co / "uninstall.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert f"Remove the translation model {MODEL_NAME} that TASlation installed (ollama rm, about 1.8 GB)?" in out
    assert QWEN_NAME not in out  # the person's own model is not asked about
    assert (tmp_path / "bin" / "ollama-args.txt").read_text().split() == ["rm", MODEL_NAME]
    record = json.loads((state / "translator_models.json").read_text("utf-8"))
    assert record["installed"] == {} and "plamo-community-license" in record["agreed"]  # (Python reads it again)


def test_uninstall_with_an_empty_record_asks_about_no_model(tmp_path):
    co = _fake_checkout(tmp_path)
    state = tmp_path / "state"
    _record(state)
    env = _tools(tmp_path, ollama=True)
    env["TASLATION_STATE_DIR"] = str(state)
    r = _run(co / "uninstall.ps1", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TASlation installed no translation model" in r.stdout and "Remove the translation model" not in r.stdout


def test_uninstall_yes_keeps_the_models_taslation_installed(tmp_path):
    co = _fake_checkout(tmp_path)
    state = tmp_path / "state"
    _record(state, MODEL_NAME, QWEN_NAME)
    env = _tools(tmp_path, ollama=True)
    env["TASLATION_STATE_DIR"] = str(state)
    r = _run(co / "uninstall.ps1", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("that TASlation installed") == 2 and not (tmp_path / "bin" / "ollama-args.txt").exists()
    left = r.stdout[r.stdout.index("Left in place"):]
    assert f"ollama rm {MODEL_NAME}" in left and f"ollama rm {QWEN_NAME}" in left


def test_uninstall_reads_the_record_before_the_data_folder_goes(tmp_path):
    co = _fake_checkout(tmp_path)
    state = tmp_path / "state"
    _record(state, MODEL_NAME)
    env = _tools(tmp_path, ollama=True)
    env["TASLATION_STATE_DIR"] = str(state)
    _answering(co / "uninstall.ps1", {REMOVE: "y", "This cannot be undone": "y", "that TASlation installed": "y",
                                      "Uninstall Ollama itself": ""})
    r = _run(co / "uninstall.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not state.exists() and (tmp_path / "bin" / "ollama-args.txt").read_text().split() == ["rm", MODEL_NAME]


# ---- the language first, and the questions in this PC's language


def _texts() -> dict[str, dict[str, str]]:
    return {k: v for k, v in json.loads((ROOT / TEXTS).read_text("utf-8")).items() if not k.startswith("_")}


def _t_calls(text: str | None = None) -> list[str]:
    """The English texts install.ps1 gives `T`, as PowerShell reads them."""
    text = text if text is not None else (ROOT / "install.ps1").read_text(encoding="ascii")
    return [m.replace("''", "'") for m in re.findall(r"(?<![\w$-])T '((?:[^']|'')*)'", text)]


def test_the_file_of_texts_has_every_question_s_text_and_nothing_else():
    from taslation.i18n import UI_LANGUAGES

    texts = _texts()
    assert set(_t_calls()) == set(texts)
    placeholders = re.compile(r"\{\d+(?::[^}]*)?\}")
    for english, translations in texts.items():
        assert translations.get("ja"), english
        assert set(translations) <= set(UI_LANGUAGES) - {"en"}, english  # TASlation's own language codes
        for code, text in translations.items():
            assert sorted(placeholders.findall(text)) == sorted(placeholders.findall(english)), (english, code)


def test_each_text_goes_through_t_in_parentheses():
    text = (ROOT / "install.ps1").read_text(encoding="ascii")
    calls = re.findall(r"(.)T '", text)
    assert calls and set(calls) == {"("}  # (T '...') -f ...: the call ends before its format is applied


def test_the_list_and_the_window_s_first_languages_are_the_window_s():
    from taslation.ui.constants import LANGUAGES, WINDOW_TARGETS

    text = (ROOT / "install.ps1").read_text(encoding="ascii")
    listed = re.search(r"^\$WindowLanguages = @\((.*?)\)$", text, re.M | re.S)
    assert listed and re.findall(r"'([^']*)'", listed.group(1)) == LANGUAGES
    cultures = {**{code: target for code, target in WINDOW_TARGETS.items()}, "en-US": "English", "pt-PT": WINDOW_TARGETS["pt"],
                "zh-CN": WINDOW_TARGETS["zh"], "zh-TW": WINDOW_TARGETS["zh-tw"], "zh-Hant-HK": WINDOW_TARGETS["zh-tw"],
                "de-AT": "German", "ja-JP": "", "": ""}
    names = ", ".join(f"'{c}'" for c in cultures)
    command = _functions("Get-WindowTarget", "Get-LanguageCode") + f"foreach ($c in @({names})) {{ \"$c=$(Get-WindowTarget $c)\" }}"
    r = _ps(RUN_SHELL, command)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == [f"{c}={t}" for c, t in cultures.items()]


def _list_constant(text: str, name: str) -> str:
    found = re.search(r"^\$" + name + r" = @\((.*?)\)$", text, re.M | re.S)
    assert found, name
    return f"${name} = @(" + " ".join(found.group(1).split()) + "); "


def _select(answers: list[str], offered: str = "English", source: str = "built-in", switches: str = "") -> list[str]:
    """`Select-TargetLanguage` with a console that gives *answers* one by one: what it says, and ``chosen: <name> /
    <source>`` last."""
    text = (ROOT / "install.ps1").read_text(encoding="ascii")
    constants = "".join(_list_constant(text, n) for n in ("WindowLanguages", "PlamoLanguages", "QwenLanguages"))
    queue = ", ".join("'" + a.replace("'", "''") + "'" for a in answers) or "'unused'"
    command = (_functions("Select-TargetLanguage", "Find-LanguageName", "T") + constants
               + f"$script:answers = New-Object System.Collections.Queue; foreach ($a in @({queue})) {{ $script:answers.Enqueue($a) }}; "
               + "function Read-Host([string]$Prompt) { $a = $script:answers.Dequeue(); Write-Host \"asked: $Prompt = $a\"; return $a }; "
               + "function Write-Info([string]$Text) { Write-Host \"info: $Text\" }; "
               + f"$Yes = {'$true' if 'Yes' in switches else '$false'}; $DryRun = $false; $Interactive = $true; "
               + f"$o = [pscustomobject]@{{ Name = '{offered}'; Source = '{source}' }}; "
               + "$l = Select-TargetLanguage $o; \"chosen: $($l.Name) / $($l.Source)\"")
    r = _ps(RUN_SHELL, command)
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


@pytest.mark.parametrize("answers, chosen", [
    (["10"], "Turkish / your answer"),
    (["  chinese   (traditional) "], "Chinese (Traditional) / your answer"),
    (["japanese"], "Japanese / your answer"),  # (PLaMo writes it, though the window does not list it)
    ([""], "English / built-in"),
])
def test_the_language_is_a_number_or_a_name_and_enter_takes_the_one_offered(answers, chosen):
    out = _select(answers)
    assert out[-1] == "chosen: " + chosen
    assert any(" 10. Turkish" in line for line in out)  # the numbered list
    assert "asked:   Translate into which language? A number or a name; Enter: English = " + answers[0] in out


def test_an_unknown_answer_is_asked_again_and_three_take_the_one_offered():
    out = _select(["Klingon", "es", "99"], offered="Spanish", source="this PC")
    assert out[-1] == "chosen: Spanish / this PC"
    assert 'info: "Klingon" is not a language TASlation knows. Type its number or its English name.' in out
    assert 'info: "es" is not a language TASlation knows. Type its number or its English name.' in out  # (a code)
    assert "info: Going on with Spanish; the window can change it later." in out


def test_yes_and_the_configuration_ask_nothing():
    out = _select([], switches="Yes")
    assert out == ["info: Translate into which language? A number or a name; Enter: English -> English (-Yes)",
                   "chosen: English / built-in"]
    out = _select([], offered="Turkish", source="taslation.toml")
    assert out == ["info: Translating into Turkish (set in taslation.toml).", "chosen: Turkish / taslation.toml"]


def test_the_language_is_the_first_question(tmp_path):
    co = _without_the_model(tmp_path)
    _answering(co / "install.ps1", {LICENCE: ""})
    r = _run(co / "install.ps1", env=_tools(tmp_path))
    out = r.stdout
    assert out.index("asked:   " + LANGUAGE_QUESTION) < out.index("asked:   " + LICENCE)
    assert "The language you translate into decides the translation model." in out


def test_a_language_answered_decides_the_model_and_the_window_starts_with_it(tmp_path, ollama_server):
    if sys.prefix == sys.base_prefix:
        pytest.skip("needs a virtual environment's launcher to copy")
    co = _fake_checkout(tmp_path)
    env = _whole_install(co, tmp_path)
    fake = tmp_path / "fake_modules"
    (fake / "taslation.py").unlink()  # a package instead, with the save the window's own code makes
    (fake / "taslation").mkdir()
    (fake / "taslation" / "__init__.py").write_text("")
    (fake / "taslation" / "__main__.py").write_text("import sys\nprint('Result: ready')\nsys.exit(0)\n")
    (fake / "taslation" / "i18n.py").write_text(
        "import json\nfrom pathlib import Path\n\n\ndef save_ui_entry(state_dir, name, key, value):\n"
        "    Path(state_dir).mkdir(parents=True, exist_ok=True)\n"
        "    (Path(state_dir) / 'saved.json').write_text(json.dumps([name, key, value]))\n")
    state = tmp_path / "state"
    env["TASLATION_STATE_DIR"] = str(state)
    _ollama_at(co / "install.ps1", ollama_server)
    _answering(co / "install.ps1", {LANGUAGE_QUESTION: "10", "Download the translation model": "y"})
    r = _run(co / "install.ps1", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"Download the translation model {QWEN_NAME} for Turkish now" in r.stdout and PLAMO_QUESTION not in r.stdout
    translator = (co / "setup_models.py").with_name("setup-args.txt").read_text().splitlines()[-1]
    assert "--translator-for Turkish --brief --ollama-exe" in translator and "--plamo-agreed" not in translator
    assert json.loads((state / "saved.json").read_text()) == ["translation", "language", "Turkish"]
    assert "ok: the window will translate into Turkish" in r.stdout


def test_the_language_chosen_is_kept_as_the_window_keeps_it(tmp_path):
    from taslation.i18n import load_ui_table

    state = tmp_path / "state with a space"
    command = (_functions("Save-TargetLanguage", "Invoke-Captured")
               + f"$VenvPy = '{sys.executable}'; Save-TargetLanguage '{state}\\' 'Portuguese (Brazil)'")
    r = _ps(RUN_SHELL, command)
    assert r.returncode == 0 and r.stdout.strip() == "True", r.stdout + r.stderr
    assert load_ui_table(state, "translation") == {"language": "Portuguese (Brazil)"}


def _enter_to_everything(script: Path) -> None:
    """A console in this copy that answers every question with Enter, printing ``asked: <question>``."""
    line = "$Interactive = (-not [Console]::IsInputRedirected) -and [Environment]::UserInteractive"
    text = script.read_bytes().decode("ascii")
    assert text.count(line) == 1
    console = "$Interactive = $true\r\nfunction Read-Host([string]$Prompt) { Write-Host \"asked: $Prompt\"; return '' }"
    script.write_bytes(text.replace(line, console).encode("ascii"))


def test_on_a_japanese_pc_the_questions_are_in_japanese(tmp_path):
    ja = {english: texts["ja"] for english, texts in _texts().items()}
    co = _without_the_model(tmp_path)
    _enter_to_everything(co / "install.ps1")
    env = _tools(tmp_path)
    env["FAKE_UI_CULTURE"] = "ja-JP"
    r = _run(co / "install.ps1", env=env)
    out = r.stdout
    assert r.returncode == 1 and not (co / ".venv").exists() and "[2/7]" not in out  # Enter is no to the licence
    assert "asked:   " + ja["Translate into which language? A number or a name; Enter: {0}"].format("English") in out
    for english in ("This computer", "The questions come first. After them you can leave it running.",
                    "TASlation itself is MIT, but it cannot read pages without these models.",
                    "Installation stopped: TASlation cannot read pages without the OCR models."):
        assert ja[english] in out, english
    assert "asked:   " + ja[LICENCE] + " [y/N]" in out
    assert LICENCE not in out and STOPPED not in out
    assert "manga-ocr-charspot-small" in out and "https://creativecommons.org/licenses/by-nc-sa/4.0/" in out


@pytest.mark.parametrize("culture", ["de-DE", "en-GB", ""])
def test_a_language_the_file_lacks_asks_in_english(tmp_path, culture):
    co = _without_the_model(tmp_path)
    _answering(co / "install.ps1", {LICENCE: ""})
    env = _tools(tmp_path)
    env["FAKE_UI_CULTURE"] = culture
    r = _run(co / "install.ps1", env=env)
    assert LICENCE + " [y/N] = " in r.stdout and STOPPED in r.stdout


def test_without_the_file_of_texts_the_questions_are_in_english(tmp_path):
    co = _without_the_model(tmp_path)
    (co / TEXTS).unlink()
    _answering(co / "install.ps1", {LICENCE: ""})
    env = _tools(tmp_path)
    env["FAKE_UI_CULTURE"] = "ja-JP"
    r = _run(co / "install.ps1", env=env)
    assert LICENCE + " [y/N] = " in r.stdout and STOPPED in r.stdout
