"""update.ps1 and update.cmd: a newer copy - a ZIP or a folder the person gives, or one downloaded from GitHub after a
yes - copied over an installed folder, the files it replaces kept in .previous for -Back, the person's files kept, then
install.ps1 run. Every run here is on temporary folders, with a stand-in install.ps1 in the new copy that only writes
down that it ran; the asking program is a stand-in check_update.py that answers from a file and copies a ZIP the test
made (the real one is tests/test_check_update.py's), run by a copy of this virtual environment's launcher: nothing
here uses the network."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
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
    taslation.toml, .venv, models and the install's markers."""
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
    _write(here / ".cache-ram-by-install", "0")
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
    _write(new / ".kv-cache-by-install", "another install's")  # (markers of the folder it was copied from)
    _write(new / ".cache-ram-by-install", "another install's")
    _write(new / ".github" / "workflows" / "install-check.yml", "x")  # (a clone's: the repository's checks)
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
    assert (here / ".cache-ram-by-install").read_text() == "0"
    assert not (here / ".github").exists()


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
    switches = {"From", "Yes", "DryRun", "Download", "Version", "WaitFor", "Restart", "Confirmed", "Back"}
    assert set(info["params"]) == switches and set(info["help"]) >= switches


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
    assert "by-install" not in r.stdout  # neither marker of the install


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


# ---- the earlier version kept, and -Back


def _note(here: Path) -> list[str]:
    return (here / ".previous" / "previous-version.txt").read_text("utf-8-sig").splitlines()


def test_the_files_an_update_replaces_are_kept_in_previous_with_a_note(tmp_path):
    here = _installed(tmp_path)
    before = _snapshot(here)
    source = _new_copy(tmp_path)
    _write(source / "taslation-main" / "NEW_FILE.txt", "new top-level file\n")
    r = _run(here / "update.ps1", "-From", str(source), "-Yes", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    _updated(here)
    replaced = ("README.md", "install.ps1", "pyproject.toml", "taslation/__init__.py", "taslation/kept.py",
                "taslation/old_module.py", "update.cmd", "update.ps1")
    assert _snapshot(here / ".previous" / "files") == {rel: before[rel] for rel in replaced}
    note = _note(here)
    assert note[0].startswith("TASlation 0.1.0, files dated ") and "before the update to 0.2.0." in note[0]
    assert {"version: 0.1.0", "to: 0.2.0", "added: NEW_FILE.txt", "added: taslation\\new_module.py",
            "added: taslation\\sub\\deep.py"} <= set(note)
    assert "The 8 files it replaces or deletes are kept in the folder .previous first" in r.stdout
    assert "ok: 8 files of 0.1.0 kept in .previous" in r.stdout
    # the installation stopped (the stand-in ends with 3): the last lines say how to go back
    lines = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    assert lines[-3:] == ["To go back to TASlation 0.1.0, close this window and run this in a Command Prompt:",
                          f'"{here / "update.cmd"}" -Back', "It puts back the program files kept in the folder .previous."]


def test_back_puts_the_earlier_version_back_and_removes_what_the_update_added(tmp_path):
    here = _installed(tmp_path)
    before = _snapshot(here)
    source = _new_copy(tmp_path)
    _write(source / "taslation-main" / "NEW_FILE.txt", "new top-level file\n")
    assert _run(here / "update.ps1", "-From", str(source), "-Yes", env=_env(tmp_path)).returncode == 3
    r = _run(here / "update.ps1", "-Back", "-Yes", env=_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    after = _snapshot(here)
    for written in ("install-ran.txt", "install-env.txt"):  # (what the new version's install stand-in wrote)
        after.pop(written)
    assert after == before  # the program as it was, and the person's files as they were
    assert not (here / ".previous").exists() and not (here / "taslation" / "sub").exists()
    out = r.stdout
    assert "kept:     0.1.0, kept on " in out and "before the update to 0.2.0" in out
    assert "8 files to put back; 3 files that update added to delete." in out
    assert "Go back to TASlation 0.1.0? [Y/n] y (-Yes)" in out and "TASlation is back at 0.1.0." in out
    assert "What the newer version's installation added to .venv stays." in out
    again = _run(here / "update.ps1", "-Back", "-Yes", env=_env(tmp_path))
    assert again.returncode == 1 and "no earlier version is kept here" in again.stdout


def test_back_in_a_dry_run_lists_and_changes_nothing(tmp_path):
    here = _installed(tmp_path)
    assert _run(here / "update.ps1", "-From", str(_new_copy(tmp_path)), "-Yes", env=_env(tmp_path)).returncode == 3
    before = _snapshot(here)
    r = _run(here / "update.ps1", "-Back", "-DryRun", env=_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _snapshot(here) == before
    assert "would: put back taslation\\old_module.py" in r.stdout and "would: delete taslation\\new_module.py" in r.stdout
    assert "would: remove the folder .previous" in r.stdout


def test_the_same_version_again_leaves_the_earlier_one_kept(tmp_path):
    here = _installed(tmp_path)
    source = _new_copy(tmp_path)
    assert _run(here / "update.ps1", "-From", str(source), "-Yes", env=_env(tmp_path)).returncode == 3
    kept = _snapshot(here / ".previous")
    r = _run(here / "update.ps1", "-From", str(source), "-Yes", env=_env(tmp_path))  # (an update that stopped, again)
    assert r.returncode == 3, r.stdout + r.stderr
    assert _snapshot(here / ".previous") == kept and "version: 0.1.0" in _note(here)
    assert "the same version as this one: the earlier version kept in .previous, if any, stays as it is" in r.stdout


def test_a_dry_run_lists_the_new_steps(tmp_path):
    here = _installed(tmp_path)
    r = _run(here / "update.ps1", "-From", str(_new_copy(tmp_path)), "-DryRun", "-Restart", "-WaitFor", "4242",
             env=_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "would: wait up to 60 seconds for TASlation (process 4242) to close" in out
    assert "would: keep the 8 files it replaces or deletes in .previous, with a note of 0.1.0 and of the 2 files it adds" in out
    assert out.index("would: keep the 8 files") < out.index("would: copy README.md") < out.index("would: run install.ps1")
    assert out.index("would: run install.ps1") < out.index("would: start TASlation again when the installation got to its end")
    assert not (here / ".previous").exists()


@pytest.mark.parametrize("way", ["-Download", "-Back"])
def test_a_git_clone_is_neither_updated_from_github_nor_taken_back(tmp_path, way):
    here = _installed(tmp_path)
    (here / ".git").mkdir()
    _with_github(tmp_path, here)
    before = _snapshot(here)
    r = _run(here / "update.ps1", way, "-Yes", env=_env(tmp_path))
    assert r.returncode == 1 and _snapshot(here) == before
    assert "this folder is a git clone" in r.stdout and ("git pull" in r.stdout or "git checkout" in r.stdout)
    assert not (here / "check-calls.txt").exists()


@pytest.mark.parametrize("args, said", [
    (["-Version", "0.2.0"], "-Version goes with -Download."),
    (["-Download", "-Version", "0.2"], "-Version must be written X.Y.Z (digits only), not 0.2."),
    (["-Download", "-Version", "v0.2.0"], "-Version must be written X.Y.Z (digits only), not v0.2.0."),
    (["-Download", "-Back"], "give one of -From, -Download and -Back."),
])
def test_switches_that_do_not_go_together_change_nothing(tmp_path, args, said):
    here = _installed(tmp_path)
    before = _snapshot(here)
    r = _run(here / "update.ps1", *args, "-Yes", env=_env(tmp_path))
    assert r.returncode == 1 and _snapshot(here) == before and said in r.stdout


def test_confirmed_asks_nothing_more(tmp_path):
    here = _installed(tmp_path)
    _console(here / "update.ps1", {})  # (any question would fail the run)
    r = _run(here / "update.ps1", "-From", str(_new_copy(tmp_path)), "-Confirmed", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    _updated(here)
    assert "Update this TASlation" not in r.stdout
    assert (here / "install-ran.txt").read_text().strip() == "install ran yes=False"  # install.ps1 still asks its own


# ---- -WaitFor


def _sleeper(seconds: float) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-I", "-c", f"import time; time.sleep({seconds})"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_wait_for_waits_until_taslation_has_closed(tmp_path):
    here = _installed(tmp_path)
    closing = _sleeper(2)
    try:
        began = time.monotonic()
        r = _run(here / "update.ps1", "-From", str(_new_copy(tmp_path)), "-Yes", "-WaitFor", str(closing.pid),
                 env=_env(tmp_path))
        assert r.returncode == 3, r.stdout + r.stderr
        assert closing.poll() is not None and time.monotonic() - began >= 1.5
        assert f"Waiting for TASlation (process {closing.pid}) to close ..." in r.stdout
        _updated(here)
    finally:
        closing.kill()


def test_wait_for_gives_up_after_its_time_and_changes_nothing(tmp_path):
    here = _installed(tmp_path)
    script = here / "update.ps1"
    text = script.read_bytes().decode("ascii")
    assert text.count("$WaitForS = 60 ") == 1
    script.write_bytes(text.replace("$WaitForS = 60 ", "$WaitForS = 1 ").encode("ascii"))
    before = _snapshot(here)
    closing = _sleeper(30)
    try:
        r = _run(script, "-From", str(_new_copy(tmp_path)), "-Yes", "-WaitFor", str(closing.pid), env=_env(tmp_path))
        assert r.returncode == 1 and _snapshot(here) == before
        assert f"TASlation (process {closing.pid}) did not close within 1 seconds." in r.stdout
    finally:
        closing.kill()


# ---- from GitHub, with a stand-in check_update.py

STAND_IN_CHECK = """import json, shutil, sys
from pathlib import Path
here = Path(__file__).resolve().parent
plan = json.loads((here / "stand-in-plan.json").read_text("utf-8"))
with open(here / "check-calls.txt", "a", encoding="utf-8") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1] == "check":
    print(json.dumps(plan["check"]))
    sys.exit(plan["check_code"])
version = sys.argv[sys.argv.index("--version") + 1]
to = Path(sys.argv[sys.argv.index("--to") + 1])
print("Downloading TASlation " + version + " from GitHub ...", file=sys.stderr)
if not plan["zip"]:
    print("Not downloaded: GitHub has no ZIP of that version (HTTP 404).", file=sys.stderr)
    sys.exit(20)
shutil.copy2(plan["zip"], to / ("taslation-" + version + ".zip"))
print(to / ("taslation-" + version + ".zip"))
"""

CHANGES = "0.2.0 - 2026-11-25\nUpdates\n\n* Help > Check for updates..."


def _venv_python(here: Path) -> None:
    """A .venv whose python.exe and pythonw.exe run: copies of this virtual environment's launchers."""
    scripts = here / ".venv" / "Scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sys.executable, scripts / "python.exe")
    shutil.copy2(Path(sys.executable).with_name("pythonw.exe"), scripts / "pythonw.exe")
    (here / ".venv" / "pyvenv.cfg").write_text(f"home = {sys.base_prefix}\n")


def _with_github(tmp: Path, here: Path, *, result: str = "newer", newest: str = "0.2.0", zip_holds: str = "0.2.0",
                 download: bool = True, reason: str = "", install_code: int = 3, prepare=None) -> Path:
    """*here* with a Python that runs and a stand-in check_update.py that answers *result* for *newest* and, when
    *download*, gives a ZIP of `_new_copy` holding *zip_holds* (its install.ps1 stand-in ends with *install_code*;
    *prepare* is given the new copy's folder before it is packed). The new copy's folder."""
    if sys.prefix == sys.base_prefix:
        pytest.skip("needs a virtual environment's launcher to copy")
    _venv_python(here)
    source = _new_copy(tmp)
    new = source / "taslation-main"
    _write(new / "pyproject.toml", _project(zip_holds))
    _write(new / "install.ps1", INSTALL_STAND_IN.replace("exit 3", f"exit {install_code}"))
    if prepare is not None:
        prepare(new)
    archive = _zip(source, tmp / "from-github.zip")
    _write(here / "check_update.py", STAND_IN_CHECK)
    code = {"newer": 10, "up to date": 0, "could not ask": 20}[result]
    answer = {"result": result, "installed": "0.1.0", "newest": newest if result != "could not ask" else "",
              "date": "2026-11-25", "newer": result == "newer", "changes": CHANGES if result == "newer" else "",
              "reason": reason}
    _write(here / "stand-in-plan.json", json.dumps({"check": answer, "check_code": code,
                                                    "zip": str(archive) if download else ""}))
    return new


def _calls(here: Path) -> list[str]:
    path = here / "check-calls.txt"
    return path.read_text("utf-8").splitlines() if path.exists() else []


def _program_updated(here: Path) -> None:
    """`_updated` for a folder whose .venv runs (`_venv_python`)."""
    assert (here / "taslation" / "__init__.py").read_text() == "new\n"
    assert not (here / "taslation" / "old_module.py").exists() and (here / "taslation" / "sub" / "deep.py").is_file()
    assert 'version = "0.2.0"' in (here / "pyproject.toml").read_text()
    assert (here / "taslation.toml").read_text() == "min_font_size = 10\n"
    assert (here / ".venv" / "pyvenv.cfg").is_file() and (here / "models" / "fonts" / "OFL.txt").is_file()


def test_download_shows_what_changed_asks_and_updates_from_the_zip(tmp_path):
    here = _installed(tmp_path)
    _with_github(tmp_path, here)
    env = _env(tmp_path)
    r = _run(here / "update.ps1", "-Download", "-Yes", env=env)
    assert r.returncode == 3, r.stdout + r.stderr
    _program_updated(here)
    out = r.stdout
    assert "this one:   0.1.0" in out and "the newest: 0.2.0, of 2026-11-25" in out
    assert "What changed since this one:\n    0.2.0 - 2026-11-25\n    Updates\n" in out.replace("\r\n", "\n")
    assert "Update this TASlation from 0.1.0 to 0.2.0? [Y/n] y (-Yes)" in out
    assert out.index("What changed") < out.index("Update this TASlation from") < out.index("Downloading TASlation 0.2.0")
    assert "Downloading TASlation 0.2.0 from GitHub ..." in r.stderr  # (check_update.py's progress, on stderr)
    check, download = _calls(here)
    assert check == "check" and download.startswith("download --version 0.2.0 --to ")
    # the installation stopped (the stand-in ends with 3): the ZIP stays for the next run, and its place is said
    folder = Path(download.split(" --to ", 1)[1])
    assert folder.parent == Path(env["TMP"]) and folder.name.startswith("taslation-download-")
    assert f"The ZIP downloaded from GitHub is kept for that: {folder / 'taslation-0.2.0.zip'}" in out
    assert (folder / "taslation-0.2.0.zip").is_file()
    assert "version: 0.1.0" in _note(here) and "To go back to TASlation 0.1.0" in out


def test_a_whole_update_from_github_leaves_no_download_behind(tmp_path):
    here = _installed(tmp_path)
    _with_github(tmp_path, here, install_code=0)
    env = _env(tmp_path)
    r = _run(here / "update.ps1", "-Download", "-Yes", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    _program_updated(here)
    assert list(Path(env["TMP"]).iterdir()) == [] and "To go back" not in r.stdout


def test_the_window_s_command_line_downloads_the_named_version_without_asking_github_which(tmp_path):
    here = _installed(tmp_path)
    _with_github(tmp_path, here, install_code=0)
    _console(here / "update.ps1", {})  # (any question would fail the run)
    r = _run(here / "update.ps1", "-Download", "-Version", "0.2.0", "-WaitFor", "0", "-Confirmed", env=_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    _program_updated(here)
    assert len(_calls(here)) == 1 and _calls(here)[0].startswith("download --version 0.2.0 --to ")


@pytest.mark.parametrize("result, reason, said", [
    ("up to date", "", "This TASlation is the newest version. Nothing was changed."),
    ("could not ask", "GitHub did not answer in time.",
     "GitHub could not be asked: GitHub did not answer in time. Download the ZIP yourself and give it to update.cmd."),
])
def test_nothing_newer_or_nobody_to_ask_changes_nothing(tmp_path, result, reason, said):
    here = _installed(tmp_path)
    _with_github(tmp_path, here, result=result, reason=reason)
    before = _snapshot(here)
    r = _run(here / "update.ps1", "-Download", "-Yes", env=_env(tmp_path))
    assert r.returncode == (0 if result == "up to date" else 1), r.stdout + r.stderr
    after = _snapshot(here)
    after.pop("check-calls.txt")
    assert after == before and _calls(here) == ["check"] and said in r.stdout


@pytest.mark.parametrize("version", ["0.1.0", "0.0.9"])
def test_a_version_not_newer_is_never_downloaded(tmp_path, version):
    here = _installed(tmp_path)
    _with_github(tmp_path, here)
    before = _snapshot(here)
    r = _run(here / "update.ps1", "-Download", "-Version", version, "-Yes", env=_env(tmp_path))
    assert r.returncode == 1 and _snapshot(here) == before and _calls(here) == []
    assert f"TASlation {version} is not newer than this one (0.1.0): there is nothing to update." in r.stdout


def test_a_zip_that_holds_another_version_is_not_copied(tmp_path):
    here = _installed(tmp_path)
    _with_github(tmp_path, here, zip_holds="0.3.0")
    before = _snapshot(here)
    env = _env(tmp_path)
    r = _run(here / "update.ps1", "-Download", "-Version", "0.2.0", "-Yes", env=env)
    assert r.returncode == 1, r.stdout + r.stderr
    after = _snapshot(here)
    after.pop("check-calls.txt")
    assert after == before and "the ZIP from GitHub holds version 0.3.0, not 0.2.0 as GitHub said." in r.stdout
    assert list(Path(env["TMP"]).iterdir()) == []


def test_a_download_that_fails_changes_nothing_and_leaves_nothing(tmp_path):
    here = _installed(tmp_path)
    _with_github(tmp_path, here, download=False)
    before = _snapshot(here)
    env = _env(tmp_path)
    r = _run(here / "update.ps1", "-Download", "-Yes", env=env)
    assert r.returncode == 1, r.stdout + r.stderr
    after = _snapshot(here)
    after.pop("check-calls.txt")
    assert after == before and list(Path(env["TMP"]).iterdir()) == []
    assert "the ZIP did not download (what went wrong is said above)" in r.stdout
    assert "Not downloaded: GitHub has no ZIP of that version (HTTP 404)." in r.stderr


def test_without_a_python_that_runs_download_says_so(tmp_path):
    here = _installed(tmp_path)  # (its .venv's python.exe is no program)
    _write(here / "check_update.py", STAND_IN_CHECK)
    r = _run(here / "update.ps1", "-Download", "-Yes", env=_env(tmp_path))
    assert r.returncode == 1 and "which does not run here. Download the ZIP yourself" in r.stdout


def test_a_dry_run_of_download_asks_github_nothing(tmp_path):
    here = _installed(tmp_path)
    _with_github(tmp_path, here)
    before = _snapshot(here)
    r = _run(here / "update.ps1", "-Download", "-DryRun", "-Restart", env=_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _snapshot(here) == before and _calls(here) == []
    out = r.stdout
    for step in ("would: ask GitHub for the newest version: .venv\\Scripts\\python.exe -I check_update.py check",
                 "would: ask: Update this TASlation from 0.1.0 to <that version>?",
                 "would: download its ZIP into a temporary folder", "would: keep the files the update replaces",
                 "would: start TASlation again when the installation got to its end"):
        assert step in out, step


# ---- the double-click's first question


def test_double_clicked_it_first_offers_github_and_a_yes_goes_there(tmp_path):
    here = _installed(tmp_path)
    _with_github(tmp_path, here)
    _console(here / "update.ps1", {"Look on GitHub for the newest version and download it?": "y",
                                   "Update this TASlation from": ""})
    r = _run(here / "update.ps1", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    _program_updated(here)
    assert "asked:   Look on GitHub for the newest version and download it? [y/N] = y" in r.stdout
    assert "asked:   Update this TASlation from 0.1.0 to 0.2.0? [Y/n] = " in r.stdout
    assert (here / "install-ran.txt").read_text().strip() == "install ran yes=False"


def test_double_clicked_a_no_goes_on_as_before(tmp_path):
    here = _installed(tmp_path)
    _with_github(tmp_path, here)
    source = _new_copy(tmp_path / "by hand")
    _console(here / "update.ps1", {"Look on GitHub": "", "Where is the new TASlation?": str(source),
                                   "Update this TASlation to": "y"})
    r = _run(here / "update.ps1", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    assert _calls(here) == [] and "asked:   Where is the new TASlation?" in r.stdout


def test_double_clicked_without_a_python_that_runs_it_goes_on_as_before(tmp_path):
    here = _installed(tmp_path)  # (its .venv's python.exe is no program)
    _write(here / "check_update.py", STAND_IN_CHECK)
    source = _new_copy(tmp_path)
    _console(here / "update.ps1", {"Where is the new TASlation?": str(source), "Update this TASlation to": "y"})
    r = _run(here / "update.ps1", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    assert "Looking on GitHub needs the program files' Python (.venv), which does not run here" in r.stdout
    _updated(here)


# ---- -Restart


def _startable(new: Path, *, ends_with: int | None = None) -> None:
    """The new copy's package as one that starts: ``-m taslation gui`` writes its arguments into started.txt beside
    it, then stays a few seconds (or ends at once with *ends_with*)."""
    _write(new / "taslation" / "__init__.py", "# new\n")
    tail = f"sys.exit({ends_with})\n" if ends_with is not None else "time.sleep(4)\n"
    _write(new / "taslation" / "__main__.py",
           "import sys, time\nfrom pathlib import Path\n"
           "Path(__file__).resolve().parent.parent.joinpath('started.txt').write_text(' '.join(sys.argv[1:]))\n" + tail)


def _quick_watch(script: Path) -> None:
    text = script.read_bytes().decode("ascii")
    assert text.count("$StartWatchS = 10 ") == 1
    script.write_bytes(text.replace("$StartWatchS = 10 ", "$StartWatchS = 2 ").encode("ascii"))


def _wait_for(path: Path, seconds: float = 10) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if path.exists():
            return True
        time.sleep(0.1)
    return path.exists()


def test_restart_starts_taslation_as_its_shortcut_does_once_the_installation_got_to_its_end(tmp_path):
    here = _installed(tmp_path)
    _with_github(tmp_path, here, install_code=0, prepare=_startable)
    _quick_watch(here / "update.ps1")
    r = _run(here / "update.ps1", "-Download", "-Version", "0.2.0", "-Confirmed", "-Restart", env=_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _wait_for(here / "started.txt") and (here / "started.txt").read_text() == "gui"
    assert "ok: TASlation started" in r.stdout


def test_a_taslation_that_ends_at_once_says_how_to_go_back(tmp_path):
    here = _installed(tmp_path)
    source = _new_copy(tmp_path)
    new = source / "taslation-main"
    _venv_python(here)
    _startable(new, ends_with=4)
    _write(new / "install.ps1", INSTALL_STAND_IN.replace("exit 3", "exit 0"))
    _quick_watch(here / "update.ps1")
    r = _run(here / "update.ps1", "-From", str(source), "-Yes", "-Restart", env=_env(tmp_path))
    assert r.returncode == 1, r.stdout + r.stderr
    assert _wait_for(here / "started.txt")
    assert "TASlation did not start: it ended at once (exit code 4)." in r.stdout
    assert "To go back to TASlation 0.1.0, close this window and run this in a Command Prompt:" in r.stdout


def test_restart_starts_nothing_after_an_installation_that_stopped(tmp_path):
    here = _installed(tmp_path)
    source = _new_copy(tmp_path)
    _venv_python(here)
    _startable(source / "taslation-main")
    r = _run(here / "update.ps1", "-From", str(source), "-Yes", "-Restart", env=_env(tmp_path))
    assert r.returncode == 3, r.stdout + r.stderr
    assert "TASlation is not started again: the installation did not get to its end." in r.stdout
    time.sleep(1)
    assert not (here / "started.txt").exists()
