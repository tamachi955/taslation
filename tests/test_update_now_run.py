"""Update now from end to end, for real: the command line `taslation.ui.updates.update_command` builds, started by
`launch_update` through cmd.exe as the window starts it, with `update_env()` as its environment. The only change to
what the window does: CREATE_NEW_CONSOLE is replaced by CREATE_NO_WINDOW, so that no window comes on the screen, and
the hidden console's input is empty and its output goes to a file the test reads (a console nobody sees would wait for
Enter at the end for ever).

The program folder is a scratch one whose path has a space, a parenthesis and an ampersand in it, holding this
checkout's top-level program files with a lower version in pyproject.toml, a .venv made by ``python -m venv`` with
nothing installed into it, and no .git. The newer version is a ZIP the test makes: its install.ps1 is a stand-in that
writes down that it ran and ends with 0, and its package is a stand-in whose ``-m taslation gui`` writes a marker and
stays a few seconds. The asking program in the program folder is tests/test_update_script.py's stand-in
check_update.py, which copies that ZIP: nothing here uses the network. A process of the .venv's Python stands in for the
window that closes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_update_script import INSTALL_STAND_IN, STAND_IN_CHECK, _project, _snapshot, _write, _zip

from taslation.ui import updates

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"),
                                reason="update.cmd runs update.ps1 with Windows PowerShell")

# the program files at the top of the repository (and of GitHub's ZIP) that an installation holds
PROGRAM_FILES = ("check_update.py", "install.cmd", "install.ps1", "installer-texts.json", "pyproject.toml",
                 "setup_models.py", "taslation.toml.example", "uninstall.cmd", "uninstall.ps1", "update.cmd",
                 "update.ps1", "LICENSE", "README.md")
OLD, NEW = "0.1.0", "0.2.0"

# the new version's ``-m taslation gui``: what it was started with, where and with which of update.cmd's variables
GUI_STAND_IN = """import json, os, sys, time
from pathlib import Path
here = Path(__file__).resolve().parent.parent
seen = {name: os.environ.get(name, "") for name in ("TASLATION_UPDATING", "TASLATION_UPDATE_PAUSE")}
(here / "started.txt").write_text(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd(), "env": seen}))
time.sleep(3)
(here / "ended.txt").write_text("ended")
"""

# the closing window: it ends once the file *close* is there (the test's word), at the latest *seconds* later, and
# writes down when
WINDOW_STAND_IN = """import os, sys, time
end = time.monotonic() + float(sys.argv[1])
while time.monotonic() < end and not os.path.exists(sys.argv[3]):
    time.sleep(0.05)
open(sys.argv[2], 'w').write(repr(time.time()))
"""


def _program_folder(tmp: Path) -> Path:
    app = tmp / "TAS (test) & co" / "app"
    for name in PROGRAM_FILES:
        _write(app / name, "")
        shutil.copy2(ROOT / name, app / name)
    _write(app / "pyproject.toml", _project(OLD))
    _write(app / "check_update.py", STAND_IN_CHECK)
    _write(app / "taslation" / "__init__.py", "old\n")
    _write(app / "taslation" / "old_module.py", "gone in the new version\n")
    _write(app / "taslation.toml", "min_font_size = 10\n")
    made = subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(app / ".venv")], capture_output=True,
                          text=True, timeout=180, stdin=subprocess.DEVNULL)
    assert made.returncode == 0, made.stdout + made.stderr
    assert (app / ".venv" / "Scripts" / "python.exe").is_file() and (app / ".venv" / "Scripts" / "pythonw.exe").is_file()
    return app


def _newer_zip(tmp: Path, app: Path) -> Path:
    build = tmp / "build"
    new = build / f"taslation-{NEW}"
    for name in PROGRAM_FILES:
        _write(new / name, "")
        shutil.copy2(ROOT / name, new / name)
    _write(new / "pyproject.toml", _project(NEW))
    _write(new / "install.ps1", INSTALL_STAND_IN.replace("exit 3", "exit 0"))
    _write(new / "taslation" / "__init__.py", "# new\n")
    _write(new / "taslation" / "__main__.py", GUI_STAND_IN)
    _write(new / "taslation" / "new_module.py", "new\n")
    archive = _zip(build, tmp / "from-github.zip")
    answer = {"result": "newer", "installed": OLD, "newest": NEW, "date": "2026-11-25", "newer": True,
              "changes": f"{NEW} - 2026-11-25\n* Update now.", "reason": ""}
    _write(app / "stand-in-plan.json", json.dumps({"check": answer, "check_code": 10, "zip": str(archive)}))
    return archive


def _window(app: Path, seconds: float, closed: Path) -> subprocess.Popen:
    """The window that closes: it ends when `_close` tells it to (at the latest *seconds* later), writing *closed*."""
    script = _write(app.parent / "window-stand-in.py", WINDOW_STAND_IN)
    return subprocess.Popen([str(app / ".venv" / "Scripts" / "python.exe"), "-I", str(script), str(seconds),
                             str(closed), str(_close_word(closed))], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _close_word(closed: Path) -> Path:
    return closed.with_name(closed.stem + "-close-now")


def _close(closed: Path) -> None:
    """The window of `_window` told to close (as the window closes itself once Update now started update.cmd)."""
    _close_word(closed).write_text("close")


def _said(log: Path, text: str, seconds: float) -> bool:
    """Whether update.cmd's console output (*log*, written as it runs) says *text* within *seconds*."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if log.is_file() and text in log.read_bytes().decode("utf-8", "replace"):
            return True
        time.sleep(0.1)
    return False


def _scratch_env(monkeypatch, tmp: Path) -> Path:
    temp = tmp / "temp"
    temp.mkdir()
    for name in ("TEMP", "TMP"):
        monkeypatch.setenv(name, str(temp))
    monkeypatch.setenv("USERPROFILE", str(tmp / "home"))
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp / "state"))
    for name in ("TASLATION_UPDATING", "TASLATION_UPDATE_PAUSE"):
        monkeypatch.delenv(name, raising=False)
    return temp


def _ours(temp: Path) -> list[str]:
    return sorted(p.name for p in temp.iterdir() if p.name.lower().startswith("taslation"))


def _outside() -> dict[str, tuple[int, int]]:
    """This checkout's files (but .git and Python's caches): what the run must not write to."""
    found = {}
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] == ".git" or "__pycache__" in rel.parts or not path.is_file():
            continue
        stat = path.stat()
        found[rel.as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return found


class Launcher:
    """`launch_update`'s *popen*: what the window starts, with CREATE_NEW_CONSOLE replaced by CREATE_NO_WINDOW and
    the hidden console's input empty and output in *log*."""

    def __init__(self, log: Path):
        self.log = log
        self.started: list[subprocess.Popen] = []
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, line: str, **kwargs):
        self.calls.append((line, dict(kwargs)))
        kwargs["creationflags"] = (kwargs["creationflags"] & ~subprocess.CREATE_NEW_CONSOLE) | subprocess.CREATE_NO_WINDOW
        out = open(self.log, "wb")
        try:
            process = subprocess.Popen(line, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, **kwargs)
        finally:
            out.close()
        self.started.append(process)
        return process

    def finish(self, timeout: float = 240) -> tuple[int, str]:
        process = self.started[0]
        try:
            process.wait(timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
            raise
        return process.returncode, self.log.read_bytes().decode("utf-8", "replace")


def _wait_for(path: Path, seconds: float) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end and not path.exists():
        time.sleep(0.1)
    return path.exists()


def test_update_now_runs_update_cmd_from_end_to_end_and_starts_the_new_version(tmp_path, monkeypatch):
    temp = _scratch_env(monkeypatch, tmp_path)
    app = _program_folder(tmp_path)
    _newer_zip(tmp_path, app)
    outside = _outside()
    closed = tmp_path / "window-closed.txt"
    window = _window(app, 90, closed)
    launcher = Launcher(tmp_path / "update-console.txt")
    try:
        assert updates.launch_update(NEW, root=app, pid=window.pid, popen=launcher) is None
        line, kwargs = launcher.calls[0]
        assert line == updates.update_command(NEW, window.pid, app)
        assert kwargs["cwd"] == str(app) and kwargs["creationflags"] & subprocess.CREATE_NEW_CONSOLE
        # the window closes only once update.ps1 said it waits for it (closed before update.ps1 looks, the window
        # is no longer there to wait for: update.ps1 rightly says nothing of it, which a slow computer showed)
        waiting = f"Waiting for TASlation (process {window.pid}) to close ..."
        assert _said(launcher.log, waiting, 60), launcher.log.read_bytes().decode("utf-8", "replace")
        assert window.poll() is None
        time.sleep(1.0)  # (update.ps1 waits on: nothing is kept or copied while the window is open)
        assert not (app / ".previous").exists() and window.poll() is None
        _close(closed)
        code, out = launcher.finish()
        assert code == 0, out
        # the window was waited for: it closed before the old version was kept and the new one copied
        assert out.count(waiting) == 1
        assert window.poll() is not None and closed.is_file()
        note = app / ".previous" / "previous-version.txt"
        assert note.stat().st_mtime >= float(closed.read_text()) - 0.01
        assert out.index("Waiting for TASlation") < out.index("Copying")
        # the old version kept for update.cmd -Back, the new one in place, the person's file as it was
        lines = note.read_text("utf-8-sig").splitlines()
        assert f"version: {OLD}" in lines and f"to: {NEW}" in lines and "added: taslation\\new_module.py" in lines
        assert (app / ".previous" / "files" / "taslation" / "__init__.py").read_text() == "old\n"
        assert (app / ".previous" / "files" / "taslation" / "old_module.py").is_file()
        assert (app / "taslation" / "__init__.py").read_text() == "# new\n"
        assert (app / "taslation" / "new_module.py").is_file() and not (app / "taslation" / "old_module.py").exists()
        assert f'version = "{NEW}"' in (app / "pyproject.toml").read_text("utf-8")
        assert (app / "check_update.py").read_bytes() == (ROOT / "check_update.py").read_bytes()  # (the new one's)
        assert (app / "taslation.toml").read_text() == "min_font_size = 10\n"
        # the new version's installation ran as an update's
        assert (app / "install-ran.txt").read_text().strip() == "install ran yes=False"
        assert (app / "install-env.txt").read_text().strip() == "updating=1"
        # the new version started again, as its shortcut starts it, without update.cmd's variables
        assert _wait_for(app / "started.txt", 20), out
        started = json.loads((app / "started.txt").read_text())
        assert started["args"] == ["gui"] and Path(started["cwd"]) == app
        assert started["env"] == {"TASLATION_UPDATING": "", "TASLATION_UPDATE_PAUSE": ""}
        assert "ok: TASlation started" in out
        assert _wait_for(app / "ended.txt", 20)
        # nothing left in the temporary folder, nothing written outside the scratch folders
        assert _ours(temp) == [], out
        home = tmp_path / "home"  # (the profile the run saw: Windows may make empty folders in it, no file)
        assert [p for p in home.rglob("*") if p.is_file()] == [] and not (tmp_path / "state").exists()
        assert _outside() == outside
    finally:
        window.kill()
        _wait_for(app / "ended.txt", 10)
        time.sleep(0.5)  # (the restarted stand-in's launcher ends a moment after it)


def test_update_now_changes_nothing_when_the_window_does_not_close(tmp_path, monkeypatch):
    temp = _scratch_env(monkeypatch, tmp_path)
    app = _program_folder(tmp_path)
    _newer_zip(tmp_path, app)
    script = app / "update.ps1"
    text = script.read_bytes().decode("ascii")
    assert text.count("$WaitForS = 60 ") == 1
    script.write_bytes(text.replace("$WaitForS = 60 ", "$WaitForS = 2 ").encode("ascii"))
    before = _snapshot(app)
    window = _window(app, 120, tmp_path / "window-closed.txt")
    launcher = Launcher(tmp_path / "update-console.txt")
    try:
        assert updates.launch_update(NEW, root=app, pid=window.pid, popen=launcher) is None
        began = time.monotonic()
        code, out = launcher.finish()
        assert code == 1, out
        assert f"TASlation (process {window.pid}) did not close within 2 seconds." in out
        assert time.monotonic() - began >= 1.5 and window.poll() is None
        assert _snapshot(app) == before and not (app / ".previous").exists() and not (app / "started.txt").exists()
        assert _ours(temp) == [] and "Downloading" not in out
    finally:
        window.kill()
        window.wait(10)
