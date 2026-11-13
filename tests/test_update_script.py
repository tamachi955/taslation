"""update.ps1 and update.cmd: a newer copy - a ZIP or a folder the person gives - copied over an installed folder,
the person's files kept, then install.ps1 run; nothing fetched. Every run here is on temporary folders, with a stand-in
install.ps1 in the new copy that only writes down that it ran."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHELLS = [s for s in ("powershell", "pwsh") if shutil.which(s)]
RUN_SHELL = SHELLS[0] if SHELLS else None

pytestmark = pytest.mark.skipif(not SHELLS, reason="neither powershell nor pwsh is installed")

INSTALL_STAND_IN = (
    "param([switch]$Yes, [switch]$DryRun)\r\n"
    "Set-Content -LiteralPath (Join-Path $PSScriptRoot 'install-ran.txt') -Value \"install ran yes=$Yes\"\r\n"
    "Set-Content -LiteralPath (Join-Path $PSScriptRoot 'install-env.txt') -Value \"updating=$env:TASLATION_UPDATING\"\r\n"
    "exit 3\r\n")


def _project(version: str) -> str:
    text = (ROOT / "pyproject.toml").read_text("utf-8")
    start = text.index('version = "')
    end = text.index('"', start + len('version = "'))
    return text[:start] + f'version = "{version}' + text[end:]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    return path


def _installed(tmp: Path) -> Path:
    """An installed folder with a space in its name: this checkout's update scripts, an old program, the person's
    taslation.toml, .venv, models and install marker."""
    here = tmp / "TASlation here"
    for name in ("update.ps1", "update.cmd"):
        _write(here / name, "")
        shutil.copy2(ROOT / name, here / name)
    _write(here / "install.ps1", INSTALL_STAND_IN.replace("install ran", "OLD install ran"))
    _write(here / "pyproject.toml", _project("0.1.0"))
    _write(here / "taslation" / "__init__.py", "old\n")
    _write(here / "taslation" / "kept.py", "old\n")
    _write(here / "taslation" / "old_module.py", "gone in the new version\n")
    _write(here / "taslation.toml", "min_font_size = 10\n")
    _write(here / ".venv" / "Scripts" / "python.exe", "not a real python")
    _write(here / "models" / "fonts" / "OFL.txt", "licence")
    _write(here / ".kv-cache-by-install", "q8_0")
    _write(here / "README.md", "old readme\n")
    _write(here / "my notes.txt", "the person's own file\n")
    return here


def _new_copy(tmp: Path, top: str | None = "taslation-main") -> Path:
    """A newer copy as GitHub's ZIP unpacks (inside *top*), with a few things that must not be copied."""
    outer = tmp / "download"
    new = outer / top if top else outer
    _write(new / "install.ps1", INSTALL_STAND_IN)
    shutil.copy2(ROOT / "update.ps1", _write(new / "update.ps1", ""))
    _write(new / "update.cmd", "")
    shutil.copy2(ROOT / "update.cmd", new / "update.cmd")
    _write(new / "pyproject.toml", _project("0.2.0"))
    _write(new / "taslation" / "__init__.py", "new\n")
    _write(new / "taslation" / "kept.py", "new\n")
    _write(new / "taslation" / "new_module.py", "new\n")
    _write(new / "taslation" / "sub" / "deep.py", "new\n")
    _write(new / "taslation" / "__pycache__" / "kept.cpython-313.pyc", "cache")
    _write(new / "README.md", "new readme\n")
    _write(new / "taslation.toml", "min_font_size = 99\n")  # (another person's: never copied)
    _write(new / "models" / "should-not-come.txt", "x")
    return outer


def _zip(folder: Path, dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w") as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(folder).as_posix())
    return dest


def _env(tmp: Path, **extra: str) -> dict:
    env = dict(os.environ)
    temp = tmp / "temp"
    temp.mkdir(exist_ok=True)
    env.update(TMP=str(temp), TEMP=str(temp), USERPROFILE=str(tmp / "home"))
    env.pop("TASLATION_UPDATE_PAUSE", None)
    env.update(extra)
    return env


def _run(script: Path, *args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([RUN_SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
                          capture_output=True, encoding="utf-8", errors="replace", timeout=120,
                          stdin=subprocess.DEVNULL, env=env, cwd=str(script.parent.parent))


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def _updated(here: Path) -> None:
    """What every update leaves: the new program, the person's files as they were, nothing that must not come."""
    assert (here / "taslation" / "__init__.py").read_text() == "new\n"
    assert (here / "taslation" / "kept.py").read_text() == "new\n"
    assert (here / "taslation" / "sub" / "deep.py").read_text() == "new\n"
    assert not (here / "taslation" / "old_module.py").exists()  # the program folder is the new one's
    assert not (here / "taslation" / "__pycache__").exists()
    assert (here / "README.md").read_text() == "new readme\n" and 'version = "0.2.0"' in (here / "pyproject.toml").read_text()
    assert (here / "taslation.toml").read_text() == "min_font_size = 10\n"
    assert (here / ".venv" / "Scripts" / "python.exe").read_text() == "not a real python"
    assert (here / "models" / "fonts" / "OFL.txt").is_file() and not (here / "models" / "should-not-come.txt").exists()
    assert (here / ".kv-cache-by-install").read_text() == "q8_0" and (here / "my notes.txt").is_file()


# ---- the scripts themselves


def _parse(shell: str, script: Path) -> dict:
    command = (
        "$t = $null; $e = $null; "
        f"$a = [System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$t, [ref]$e); "
        "$p = @($a.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath }); "
        "$h = Get-Help -Name '" + str(script) + "' -Full; "
        "@{ errors = @($e | ForEach-Object { $_.Message }); params = $p; "
        "help = @($h.parameters.parameter | ForEach-Object { $_.name }) } | ConvertTo-Json -Depth 4"
    )
    r = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True,
                       timeout=60, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("shell", SHELLS)
def test_the_script_parses_and_documents_its_switches(shell):
    info = _parse(shell, ROOT / "update.ps1")
    assert info["errors"] == []
    assert set(info["params"]) == {"From", "Yes", "DryRun"} and set(info["help"]) >= {"From", "Yes", "DryRun"}


@pytest.mark.parametrize("name", ["update.ps1", "update.cmd"])
def test_the_scripts_are_ascii_with_windows_line_ends(name):
    data = (ROOT / name).read_bytes()
    assert all(b < 128 for b in data) and data.count(b"\n") == data.count(b"\r\n") > 0


def test_the_wrapper_reads_nothing_of_itself_after_the_copy():
    lines = (ROOT / "update.cmd").read_text("ascii").splitlines()
    assert lines[-1] == 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %* & call exit /b %%ERRORLEVEL%%'


def test_the_script_uses_no_network():
    text = (ROOT / "update.ps1").read_text("ascii")
    for word in ("Invoke-WebRequest", "Invoke-RestMethod", "WebClient", "http://", "https://", "Start-BitsTransfer",
                 "winget", "curl"):
        assert word not in text, word


# ---- updates


def test_an_update_from_a_folder_keeps_what_is_the_person_s_and_runs_the_new_install(tmp_path):
    here = _installed(tmp_path)
    source = _new_copy(tmp_path)
    r = _run(here / "update.ps1", "-From", str(source), "-Yes", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr  # install.ps1's own exit code
    _updated(here)
    assert (here / "install-ran.txt").read_text().strip() == "install ran yes=True"  # the new one, with -Yes
    # told that it runs in an update: it keeps the program files' PyTorch as it is (no GPU build fetched unasked)
    assert (here / "install-env.txt").read_text().strip() == "updating=1"
    out = r.stdout
    assert "this one: 0.1.0, files dated " in out and "the new:  0.2.0, files dated " in out
    assert "Update this TASlation to 0.2.0" in out and "1 program files the new version no longer has" in out
    assert (source / "taslation-main" / "README.md").read_text() == "new readme\n"  # the source is left as it was


def test_an_update_from_the_zip_unpacks_it_into_a_temporary_folder_removed_after(tmp_path):
    here = _installed(tmp_path)
    archive = _zip(_new_copy(tmp_path), tmp_path / "taslation-main.zip")
    env = _env(tmp_path)
    r = _run(here / "update.ps1", "-From", str(archive), "-Yes", env=env)
    assert r.returncode == 3, r.stdout + r.stderr
    _updated(here)
    assert list(Path(env["TMP"]).iterdir()) == []


def test_a_copy_without_a_top_folder_is_found_too(tmp_path):
    here = _installed(tmp_path)
    r = _run(here / "update.ps1", "-From", str(_new_copy(tmp_path, top=None)), "-Yes", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    _updated(here)


def test_a_dry_run_changes_nothing_and_runs_nothing(tmp_path):
    here = _installed(tmp_path)
    source = _new_copy(tmp_path)
    before = _snapshot(here)
    r = _run(here / "update.ps1", "-From", str(source), "-DryRun", env=_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _snapshot(here) == before
    assert "would: copy README.md" in r.stdout and "would: delete taslation\\old_module.py" in r.stdout
    assert "would: copy taslation.toml" not in r.stdout and "models" not in r.stdout.split("Kept as they are")[0]


@pytest.mark.parametrize("what", ["not taslation", "this folder", "missing", "no -From"])
def test_what_is_no_new_copy_changes_nothing(tmp_path, what):
    here = _installed(tmp_path)
    args: list[str] = ["-Yes"]
    if what == "not taslation":
        other = _write(tmp_path / "other" / "readme.txt", "x").parent
        args += ["-From", str(other)]
    elif what == "this folder":
        args += ["-From", str(here)]
    elif what == "missing":
        args += ["-From", str(tmp_path / "nowhere.zip")]
    before = _snapshot(here)
    r = _run(here / "update.ps1", *args, env=_env(tmp_path))
    assert r.returncode == 1 and _snapshot(here) == before
    expected = {"not taslation": "holds no TASlation", "this folder": "that is this folder itself",
                "missing": "there is no file or folder", "no -From": "Give the new copy with -From"}[what]
    assert expected in r.stdout


def test_an_older_copy_is_said_to_be_and_without_a_console_nothing_happens(tmp_path):
    here = _installed(tmp_path)
    source = _new_copy(tmp_path)
    for path in (source / "taslation-main" / "taslation").rglob("*.py"):
        os.utime(path, (946684800, 946684800))  # 2000-01-01
    before = _snapshot(here)
    r = _run(here / "update.ps1", "-From", str(source), env=_env(tmp_path))
    assert r.returncode == 1 and _snapshot(here) == before
    assert "The new copy is OLDER than this one." in r.stdout and "[y/N] n (no console to ask)" in r.stdout


def _console(script: Path, answers: dict[str, str]) -> None:
    """This copy of update.ps1 with a console that answers the questions holding a key of *answers*."""
    line = "$Interactive = (-not [Console]::IsInputRedirected) -and [Environment]::UserInteractive"
    text = script.read_bytes().decode("ascii")
    assert text.count(line) == 1
    rules = "".join(f"if ($Prompt.Contains('{q}')) {{ Write-Host \"asked: $Prompt = {a}\"; return '{a}' }}; "
                    for q, a in answers.items())
    console = f"$Interactive = $true\r\nfunction Read-Host([string]$Prompt) {{ {rules}throw \"unexpected: $Prompt\" }}"
    script.write_bytes(text.replace(line, console).encode("ascii"))


def test_asked_it_offers_the_newest_zip_in_downloads_and_enter_takes_it(tmp_path):
    here = _installed(tmp_path)
    downloads = tmp_path / "home" / "Downloads"
    downloads.mkdir(parents=True)
    _zip(_new_copy(tmp_path), downloads / "taslation-main.zip")
    _console(here / "update.ps1", {"Where is the new TASlation?": "", "Update this TASlation": ""})
    r = _run(here / "update.ps1", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    assert f"Enter: {downloads / 'taslation-main.zip'}" in r.stdout
    _updated(here)
    assert (here / "install-ran.txt").read_text().strip() == "install ran yes=False"


def test_a_path_dragged_into_the_window_comes_in_quotes(tmp_path):
    here = _installed(tmp_path)
    source = _new_copy(tmp_path)
    _console(here / "update.ps1", {"Where is the new TASlation?": f'"{source}"', "Update this TASlation": "y"})
    r = _run(here / "update.ps1", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    _updated(here)


def test_a_no_changes_nothing(tmp_path):
    here = _installed(tmp_path)
    source = _new_copy(tmp_path)
    _console(here / "update.ps1", {"Update this TASlation": "n"})
    before = _snapshot(here)
    r = _run(here / "update.ps1", "-From", str(source), env=_env(tmp_path))
    assert r.returncode == 1 and _snapshot(here) == before and "Nothing was changed." in r.stdout


def test_the_wrapper_passes_arguments_and_the_exit_code_and_survives_its_own_copy(tmp_path):
    here = _installed(tmp_path)
    source = _new_copy(tmp_path)
    new_cmd = source / "taslation-main" / "update.cmd"  # a new update.cmd of another length: cmd must read none of it
    new_cmd.write_bytes(b"@echo off\r\n" + b"rem " + b"x" * 300 + b"\r\n" + b"echo READ THE NEW FILE\r\n" + new_cmd.read_bytes())
    r = subprocess.run(["cmd", "/c", str(here / "update.cmd"), "-From", str(source), "-Yes"], capture_output=True,
                       encoding="utf-8", errors="replace", timeout=120, input="\n", env=_env(tmp_path),
                       cwd=str(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    assert "READ THE NEW FILE" not in r.stdout and "is not recognized" not in r.stdout + r.stderr
    assert (here / "update.cmd").read_bytes() == new_cmd.read_bytes()
    _updated(here)
