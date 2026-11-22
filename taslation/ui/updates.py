"""Looking for a new version from the window, and updating to it with one click.

TASlation's own process never asks the network: it starts the program files' ``check_update.py`` (a program of its
own, beside setup_models.py, outside the offline guard) as a process of its own, without a console window and below
normal priority, and reads the one line of JSON it prints (`Check`, `parse_answer`). That happens only

* when the reader chooses Help > Check for updates... (`dialogs.updates.UpdateDialog`; chosen again within
  `RECENT_S` of an answer that was no failure, that answer is shown again and nothing is asked: `remember`,
  `recent`, in the window's memory only), and
* at the window's start, for who turned it on (``update_check = "daily"``: the installer asks, Tools > Settings... and
  the dialog change it), at most once a day (`start_check_due`), no sooner than `START_DELAY_MS` after the window is
  ready and only while nothing is read or translated (`idle`), never in a git clone. A newer version found then is
  named in the Help menu's item (`menu_label`) and in one quiet status line (`_say_quietly`: the status bar only,
  nothing on the full screen's page, no dialog, no focus taken); a failure says nothing.

The state file (`STATE_FILE` in the state folder) keeps the time of the last look, whoever asked for it, and the
newest version seen with its date: nothing else (`load_state`, `save_state`).

Update now (`update_now`) starts update.cmd in a console window of its own (`update_command`: ``-Download -Version
X.Y.Z -WaitFor <this process> -Confirmed -Restart``; the environment as Windows keeps it for the user, not the
offline guard's: `update_env`), and closes the window as closing does; when update.cmd cannot be started the window
says so and stays open. update.ps1 then waits for this
process to end, downloads that version's ZIP with check_update.py, runs the update and starts TASlation again.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..config import REPO_DIR
from ..i18n import _

LOG = logging.getLogger(__name__)

STATE_FILE = "update-check.json"  # in the state folder: {"checked": epoch seconds, "newest": "X.Y.Z", "date": ...}
DAY_S = 24 * 3600.0  # the start's look comes at most this often
START_DELAY_MS = 30_000  # ... and no sooner than this after the window is ready
BUSY_RETRY_MS = 30_000  # while something is read or translated, the start's look waits this long and tries again
QUIET_RETRY_MS = 2_000  # the quiet line waits so long while the status line is the work's
POLL_MS = 200  # how often the window looks whether the asking program has answered
CHECK_WAIT_S = 20.0  # the asking program ends itself after 10 s (its CHECK_TOTAL_S); this long, it is ended
CHANGES_CAP = 6000  # characters of the changes shown (check_update.py's cap)
RECENT_S = 60.0  # Help > Check for updates... chosen again this soon after an answer shows it again, asking nothing
TEST_BASE: str | None = None  # tests only: the loopback address check_update.py asks instead (its --base)
_clock = time.monotonic  # (`recent`'s clock; the tests set their own)

_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
RESULTS = ("newer", "up to date", "could not ask")

# the environment variables the offline guard sets or clears in this process (`netguard.OFFLINE_ENV`, `PROXY_ENV`);
# update.cmd gets them as Windows keeps them for the user, so that pip and the downloads run as they do from a
# double-click
GUARD_VARIABLES = (
    "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN", "DISABLE_TELEMETRY", "DO_NOT_TRACK", "NO_PROXY", "no_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY", "http_proxy", "https_proxy", "all_proxy", "ftp_proxy",
)


# ---------------------------------------------------------------- versions, the program files and the state file
def version_of(text: Any) -> tuple[int, int, int] | None:
    """*text* as (X, Y, Z) when it is exactly ``X.Y.Z``, else None (as check_update.py and update.ps1 read one)."""
    if not isinstance(text, str) or _VERSION.fullmatch(text) is None:
        return None
    x, y, z = text.split(".")
    return int(x), int(y), int(z)


def installed_version() -> str:
    """The version of the program files that run."""
    from .. import errorlog

    return errorlog.program_version()


def program_root(root: Path | str | None = None) -> Path:
    """*root*, else the folder of the program files that run (where update.cmd and check_update.py are)."""
    return Path(REPO_DIR if root is None else root)


def is_clone(root: Path | None = None) -> bool:
    """Whether the program files are a git clone (git updates those, not GitHub's ZIP)."""
    return (program_root(root) / ".git").exists()


def state_path(state_dir: Path | str) -> Path:
    return Path(state_dir) / STATE_FILE


def load_state(state_dir: Path | str) -> dict[str, Any]:
    """The state file: ``checked`` (seconds since the epoch, 0.0 when never), ``newest`` and ``date`` ("" when
    unknown); what is not of that form is taken as not there."""
    state: dict[str, Any] = {"checked": 0.0, "newest": "", "date": ""}
    try:
        data = json.loads(state_path(state_dir).read_text("utf-8"))
    except (OSError, ValueError):
        return state
    if not isinstance(data, dict):
        return state
    checked = data.get("checked")
    if isinstance(checked, (int, float)) and not isinstance(checked, bool) and checked == checked:  # (not NaN)
        state["checked"] = float(checked)
    if version_of(data.get("newest")) is not None:
        state["newest"] = data["newest"]
        if isinstance(data.get("date"), str) and _DATE.fullmatch(data["date"]):
            state["date"] = data["date"]
    return state


def save_state(state_dir: Path | str, checked: float, newest: str = "", date: str = "") -> None:
    """The time of a look and, when it got an answer, the newest version with its date (else the newest seen
    before stays). Never raises: a look that cannot be noted only comes again sooner."""
    from ..atomic import write_atomic

    state = load_state(state_dir)
    state["checked"] = float(checked)
    if version_of(newest) is not None:
        state["newest"], state["date"] = newest, date if _DATE.fullmatch(date or "") else ""
    try:
        Path(state_dir).mkdir(parents=True, exist_ok=True)
        write_atomic(state_path(state_dir), (json.dumps(state, indent=2) + "\n").encode("utf-8"))
    except OSError as e:
        LOG.warning("the time of the look for a new version was not kept: %s", e.strerror or type(e).__name__)


def newer_known(state: dict[str, Any], installed: str) -> tuple[str, str] | None:
    """(version, date) of a newer version than *installed* that the state file names, else None."""
    newest, mine = version_of(state.get("newest")), version_of(installed)
    if newest is None or mine is None or newest <= mine:
        return None
    return state["newest"], state.get("date", "")


def start_check_due(settings: Any, state: dict[str, Any], now: float, root: Path | None = None) -> bool:
    """Whether the start's look is due: turned on (``update_check = "daily"``), not a git clone, and the last look,
    whoever asked for it, a day ago or more (a time ahead of the clock counts as none)."""
    if getattr(settings, "update_check", "off") != "daily" or is_clone(root):
        return False
    since = now - float(state.get("checked", 0.0) or 0.0)
    return not 0.0 <= since < DAY_S


# ---------------------------------------------------------------- the asking program
def check_script(root: Path | None = None) -> Path:
    return program_root(root) / "check_update.py"


def console_python() -> str:
    """The Python of the program files, as python.exe rather than the window's pythonw.exe (whose output could not be
    read)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").is_file():
        return str(exe.parent / "python.exe")
    return str(exe)


def check_command(root: Path | None = None) -> list[str]:
    """check_update.py's ``check``, isolated from the user's Python settings and folders (-I)."""
    command = [console_python(), "-I", str(check_script(root))]
    if TEST_BASE is not None:
        command += ["--base", TEST_BASE]
    return [*command, "check"]


def _quiet_flags() -> int:
    """No console window; below normal priority, so that a page read meanwhile is never slower for it."""
    if sys.platform != "win32":
        return 0
    return subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS


def failed(reason: str, installed: str = "") -> dict[str, Any]:
    return {"result": "could not ask", "installed": installed, "installed_date": "", "newest": "", "date": "",
            "newer": False, "changes": "", "reason": reason}


def parse_answer(output: str, installed: str = "") -> dict[str, Any]:
    """The asking program's last line of output as its answer, every field checked (versions ``X.Y.Z``, dates
    ``YYYY-MM-DD``, the changes plain text of at most `CHANGES_CAP` characters); anything else is "could not ask"."""
    lines = [line for line in (output or "").splitlines() if line.strip()]
    try:
        data = json.loads(lines[-1]) if lines else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or data.get("result") not in RESULTS:
        return failed("The answer could not be read.", installed)
    if data["result"] == "could not ask":
        reason = data.get("reason")
        return failed(reason if isinstance(reason, str) else "", installed)
    mine, newest = data.get("installed"), data.get("newest")
    if version_of(mine) is None or version_of(newest) is None:
        return failed("The answer could not be read.", installed)
    newer = version_of(newest) > version_of(mine)
    if newer != (data["result"] == "newer"):
        return failed("The answer could not be read.", installed)
    dates = [data.get(k) if isinstance(data.get(k), str) and _DATE.fullmatch(data.get(k)) else ""
             for k in ("installed_date", "date")]
    changes = data.get("changes") if isinstance(data.get("changes"), str) else ""
    changes = "".join(c for c in changes if c == "\n" or c == "\t" or c.isprintable())[:CHANGES_CAP]
    return {"result": data["result"], "installed": mine, "installed_date": dates[0], "newest": newest,
            "date": dates[1], "newer": newer, "changes": changes if newer else "", "reason": ""}


class Check:
    """One run of ``check_update.py check`` in a process of its own (`check_command`, `_quiet_flags`), waited for on
    a thread of its own: ``answer`` is its answer (`parse_answer`) once it is there, None until then. It is ended
    after `CHECK_WAIT_S`, and at once by `cancel`. Nothing of TASlation's process goes into it but the folder of the
    program files."""

    def __init__(self, root: Path | None = None, wait_s: float = CHECK_WAIT_S):
        self.root, self.wait_s = program_root(root), wait_s
        self.answer: dict[str, Any] | None = None
        self.installed = installed_version()
        self._proc: subprocess.Popen | None = None
        self._cancelled = threading.Event()
        self._thread = threading.Thread(target=self._run, name="update-check", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if not check_script(self.root).is_file():
            self.answer = failed("check_update.py is not in the TASlation folder.", self.installed)
            return
        try:
            self._proc = subprocess.Popen(check_command(self.root), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, cwd=str(self.root), creationflags=_quiet_flags())
        except OSError as e:
            self.answer = failed(f"check_update.py could not be started ({e.strerror or type(e).__name__}).",
                                 self.installed)
            return
        try:
            out, _err = self._proc.communicate(timeout=self.wait_s)
        except subprocess.TimeoutExpired:
            self._end()
            self.answer = failed("GitHub did not answer in time.", self.installed)
            return
        if self._cancelled.is_set():
            return
        self.answer = parse_answer(out.decode("utf-8", "replace"), self.installed)

    def _end(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(5)
            except (OSError, subprocess.SubprocessError):
                pass

    def cancel(self) -> None:
        """The answer is not wanted any more: the program is ended."""
        self._cancelled.set()
        self._end()

    @property
    def done(self) -> bool:
        return self.answer is not None


def watch(window: Any, check: Check, on_answer: Callable[[dict[str, Any]], None]) -> None:
    """*on_answer* with *check*'s answer on Tk's thread, once it is there (looked at every `POLL_MS`)."""
    def poll() -> None:
        if check._cancelled.is_set():
            return
        if check.answer is None:
            window.after(POLL_MS, poll)
            return
        on_answer(check.answer)

    window.after(POLL_MS, poll)


def noted(window: Any, answer: dict[str, Any], now: float | None = None) -> None:
    """A look's answer, whoever asked for it: its time in the state file, and the newest version when it got one; a
    newer version from then on in the Help menu's item."""
    stamp = time.time() if now is None else now
    if answer.get("result") == "could not ask":
        save_state(window.settings.state_dir, stamp)
        return
    save_state(window.settings.state_dir, stamp, answer.get("newest", ""), answer.get("date", ""))
    window._update_known = newer_known(load_state(window.settings.state_dir), installed_version())
    relabel(window)


# ---------------------------------------------------------------- the window's side
def setup(window: Any) -> None:
    """At the window's start: a newer version an earlier look found, named in the Help menu at once (no request)."""
    window._update_known = newer_known(load_state(window.settings.state_dir), installed_version())
    window._update_planned = False
    window._update_check = None
    window._update_recent = None  # (`remember`)


def menu_label(window: Any) -> str:
    """Help > Check for updates..., with the newer version when one is known."""
    known = getattr(window, "_update_known", None)
    if known:
        return _("Check for updates... ({version} is available)").format(version=known[0])
    return _("Check for updates...")


def relabel(window: Any) -> None:
    entry = getattr(window, "_update_entry", None)
    if entry is None:
        return
    menu, index = entry
    try:
        menu.entryconfigure(index, label=menu_label(window))
    except Exception:  # noqa: BLE001 - the menu is being rebuilt or gone
        pass


def idle(window: Any) -> bool:
    """Whether nothing is read or translated just now: the window is ready, no page job, no page waiting."""
    jobs = getattr(window, "_jobs", None)
    return bool(getattr(window, "ready", False) and not getattr(window, "busy", False)
                and getattr(window, "_queued", None) is None and (jobs is None or jobs.empty()))


def on_ready(window: Any, now: float | None = None) -> None:
    """The window is ready: the start's look planned, once, when it is due (`start_check_due`)."""
    if getattr(window, "_update_planned", True):
        return
    window._update_planned = True
    stamp = time.time() if now is None else now
    if start_check_due(window.settings, load_state(window.settings.state_dir), stamp):
        window.after(START_DELAY_MS, lambda: _start_when_idle(window))


def _start_when_idle(window: Any) -> None:
    """(Tk) The start's look, once nothing is read or translated; due still (a look from the dialog meanwhile
    counts)."""
    try:
        if not window.winfo_exists():
            return
    except Exception:  # noqa: BLE001 - the window is gone
        return
    if getattr(window, "_update_check", None) is not None:
        return
    if not idle(window):
        window.after(BUSY_RETRY_MS, lambda: _start_when_idle(window))
        return
    if not start_check_due(window.settings, load_state(window.settings.state_dir), time.time()):
        return
    check = Check()
    window._update_check = check
    watch(window, check, lambda answer: _start_check_done(window, answer))


def _start_check_done(window: Any, answer: dict[str, Any]) -> None:
    """(Tk) The start's look answered: noted; a newer version named in the Help menu and in one quiet line; a failure
    says nothing."""
    window._update_check = None
    noted(window, answer)
    if answer.get("result") == "newer" and getattr(window, "_update_known", None):
        _say_quietly(window, window._update_known[0])


def quiet_line(version: str) -> str:
    return _("TASlation {version} is available: Help > Check for updates...").format(version=version)


def _say_quietly(window: Any, version: str) -> None:
    """(Tk) The newer version in the status line, once, while nothing is read or translated (the line of the work
    stays the work's): only the status bar's line, which the full screen does not show."""
    try:
        if not window.winfo_exists():
            return
    except Exception:  # noqa: BLE001
        return
    if not idle(window):
        window.after(QUIET_RETRY_MS, lambda: _say_quietly(window, version))
        return
    render = lambda: quiet_line(version)  # noqa: E731 - said again after a language switch
    window.status_var.set(render())
    window._status_render, window._status_key, window._status_page = render, None, None


def remember(window: Any, answer: dict[str, Any]) -> None:
    """The dialog's answer, kept in the window's memory only (never on disk) for `recent`; a failure is not kept, so
    that it can be asked again at once."""
    window._update_recent = None if answer.get("result") == "could not ask" else (_clock(), dict(answer))


def recent(window: Any) -> dict[str, Any] | None:
    """The answer the dialog got less than `RECENT_S` ago, when it was no failure: shown again with no new request."""
    kept = getattr(window, "_update_recent", None)
    if kept is None or _clock() - kept[0] >= RECENT_S:
        return None
    return dict(kept[1])


def stop(window: Any) -> None:
    """The window closes: a look under way is ended."""
    check = getattr(window, "_update_check", None)
    if check is not None:
        window._update_check = None
        check.cancel()


# ---------------------------------------------------------------- Update now
def update_env(base: dict[str, str] | None = None, stored: Callable[[str], str | None] | None = None) -> dict[str, str]:
    """The environment update.cmd gets: this process's, with the variables the offline guard set or cleared
    (`GUARD_VARIABLES`) as Windows keeps them for the user or the computer (`ollama_start.stored_value`)."""
    if stored is None:
        from ..ollama_start import stored_value as stored
    env = dict(os.environ if base is None else base)
    for name in GUARD_VARIABLES:
        value = stored(name)
        if value:
            env[name] = value
        else:
            env.pop(name, None)
    return env


def update_command(version: str, pid: int, root: Path | None = None) -> str:
    """The command line that runs update.cmd for *version*, as cmd.exe takes it: the whole of it between one pair of
    quotes (/s), the script's path in its own."""
    if version_of(version) is None:
        raise ValueError(f"not a version: {version!r}")
    shell = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "cmd.exe"
    script = program_root(root) / "update.cmd"
    return (f'"{shell}" /d /s /c ""{script}" -Download -Version {version} -WaitFor {int(pid)} -Confirmed -Restart"')


def launch_update(version: str, root: Path | None = None, pid: int | None = None,
                  popen: Callable[..., Any] = subprocess.Popen) -> str | None:
    """update.cmd started for *version* in a console window of its own, outside any job of this process, so that it
    outlives the window: None, or what went wrong as one sentence."""
    root = program_root(root)
    if is_clone(root):
        return _("This TASlation is a git clone: update it with git.")
    for name in ("update.cmd", "update.ps1", "check_update.py"):
        if not (root / name).is_file():
            return _("{file} is not in the TASlation folder.").format(file=name)
    line = update_command(version, os.getpid() if pid is None else pid, root)
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    env = update_env()
    error: OSError | None = None
    for extra in ((breakaway, 0) if breakaway else (0,)):
        try:
            popen(line, cwd=str(root), env=env, creationflags=flags | extra, close_fds=True)
            return None
        except OSError as e:  # (a job that lets no process go: started inside it, which ends only with the window's)
            error = e
    reason = (error.strerror if error is not None else "") or type(error).__name__
    return _("update.cmd could not be started ({reason}).").format(reason=reason)


def update_now(window: Any, version: str, launch: Callable[..., str | None] = launch_update) -> bool:
    """Update now: update.cmd started (`launch_update`); the window closed as closing closes it. Whether it closed:
    when update.cmd could not be started the window says so and stays open."""
    from .dialogs.caches import tell

    problem = launch(version)
    if problem is not None:
        tell(window, _("The update did not start: {reason} TASlation stays open.").format(reason=problem))
        return False
    stop(window)
    window._on_close()
    return True
