"""Looking for a new version from the window (`taslation.ui.updates`, `taslation.ui.dialogs.updates`): the state file
and the once-a-day rule with a made-up clock, the asking program's answer read and checked, the real check_update.py
asked by the window's code against a small HTTP server on 127.0.0.1 with the offline guard in this process (nothing
blocked, nothing allowed: the window's process connects nowhere), the start's look that waits while a page is read and
says a newer version only in the Help menu and one quiet status line, the dialog's three answers and its box, and
Update now: update.cmd's command line, its console of its own, the environment the guard changed given back, the
window closed only once it started. Nothing here reaches the network, the real ~/.taslation or a real update."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

from taslation import netguard
from taslation.config import ConfigError, Settings
from taslation.i18n import _, set_language
from taslation.ui import updates
from taslation.ui.dialogs import updates as dialog_mod
from taslation.ui.dialogs.updates import UpdateDialog, reason_text

from test_check_update import CHANGELOG, CHANGELOG_PATH, Server, body, scratch  # (the loopback server)

ROOT = Path(__file__).resolve().parents[1]
NOW = 1_800_000_000.0  # a made-up clock


@pytest.fixture
def program(tmp_path, monkeypatch):
    """A scratch program folder (no .git: as an installation) that the window's code takes for its own."""
    folder = tmp_path / "program"
    folder.mkdir()
    monkeypatch.setattr(updates, "REPO_DIR", folder)
    return folder


@pytest.fixture
def state(tmp_path):
    return tmp_path / "state"


def newer_answer(**changes):
    answer = {"result": "newer", "installed": "0.8.1", "installed_date": "2026-11-20", "newest": "0.9.0",
              "date": "2026-11-25", "newer": True, "changes": "0.9.0 - 2026-11-25\n* Help > Check for updates...",
              "reason": ""}
    answer.update(changes)
    return answer


# ---------------------------------------------------------------- the state file and the once-a-day rule
def test_the_state_file_keeps_the_time_and_the_newest_version_only(state):
    assert updates.load_state(state) == {"checked": 0.0, "newest": "", "date": ""}
    updates.save_state(state, NOW, "0.9.0", "2026-11-25")
    data = json.loads((state / "update-check.json").read_text("utf-8"))
    assert data == {"checked": NOW, "newest": "0.9.0", "date": "2026-11-25"}
    updates.save_state(state, NOW + 5)  # a look that got no answer: its time, the newest seen before stays
    assert updates.load_state(state) == {"checked": NOW + 5, "newest": "0.9.0", "date": "2026-11-25"}
    for bad in ("not json", "[1]", '{"checked": "yesterday", "newest": "v1", "date": 3}', '{"checked": NaN}'):
        (state / "update-check.json").write_text(bad, "utf-8")
        assert updates.load_state(state) == {"checked": 0.0, "newest": "", "date": ""}, bad


def test_a_newer_version_is_known_only_when_it_is_newer_than_this_one():
    assert updates.newer_known({"newest": "0.9.0", "date": "2026-11-25"}, "0.8.1") == ("0.9.0", "2026-11-25")
    assert updates.newer_known({"newest": "0.10.0", "date": ""}, "0.9.9") == ("0.10.0", "")
    for newest in ("0.8.1", "0.8.0", "", "x"):
        assert updates.newer_known({"newest": newest}, "0.8.1") is None


def test_the_look_at_the_start_comes_at_most_once_a_day_and_only_for_who_turned_it_on(program):
    daily, off = SimpleNamespace(update_check="daily"), SimpleNamespace(update_check="off")
    assert updates.start_check_due(daily, {"checked": 0.0}, NOW)  # never looked
    assert not updates.start_check_due(off, {"checked": 0.0}, NOW)  # the default: never at the start
    assert not updates.start_check_due(daily, {"checked": NOW - 3600}, NOW)  # an hour ago
    assert not updates.start_check_due(daily, {"checked": NOW - updates.DAY_S + 1}, NOW)
    assert updates.start_check_due(daily, {"checked": NOW - updates.DAY_S}, NOW)  # a day ago
    assert updates.start_check_due(daily, {"checked": NOW + 7200}, NOW)  # the clock was put back: as never
    (program / ".git").mkdir()  # a git clone: git updates it
    assert not updates.start_check_due(daily, {"checked": 0.0}, NOW)


def test_the_setting_is_off_unless_turned_on():
    assert Settings().update_check == "off"
    with pytest.raises(ConfigError):
        Settings(update_check="hourly").validate()


# ---------------------------------------------------------------- the asking program's answer
def test_the_answer_is_read_and_checked():
    line = json.dumps(newer_answer())
    assert updates.parse_answer("noise\n" + line + "\n") == newer_answer()
    up = updates.parse_answer(json.dumps(newer_answer(result="up to date", newest="0.8.1", newer=False)))
    assert up["result"] == "up to date" and up["changes"] == ""
    failed = updates.parse_answer(json.dumps({"result": "could not ask", "reason": "GitHub could not be reached."}))
    assert failed["result"] == "could not ask" and failed["reason"] == "GitHub could not be reached."
    for bad in ("", "{", "[]", json.dumps(newer_answer(newest="0.9")), json.dumps(newer_answer(installed="0.9.0")),
                json.dumps(newer_answer(result="maybe")), json.dumps(newer_answer(newest="0.8.0"))):
        assert updates.parse_answer(bad)["result"] == "could not ask", bad
    odd = updates.parse_answer(json.dumps(newer_answer(changes="a\u202eb\x07c\n" + "x" * 9000, date="soon")))
    assert odd["changes"].startswith("abc\n") and len(odd["changes"]) == updates.CHANGES_CAP and odd["date"] == ""


def test_the_window_s_process_asks_nothing_itself_the_program_beside_it_does(tmp_path, monkeypatch):
    """The real check_update.py run as the window runs it, against a loopback server, while the offline guard is in
    this process recording every call it allows: the answer comes, and the guard saw no call at all."""
    folder = scratch(tmp_path, "0.8.1")
    server = Server({CHANGELOG_PATH: body(CHANGELOG.encode())})
    before = dict(os.environ)
    guard = netguard.install(audit_hook=False)
    netguard.record_allowed(True)
    blocked_before = len(guard.blocked)  # (what other tests in this process had blocked)
    try:
        monkeypatch.setattr(updates, "TEST_BASE", server.base)
        check = updates.Check(folder)
        deadline = time.monotonic() + 60
        while check.answer is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert guard.blocked[blocked_before:] == [] and guard.allowed == []
    finally:
        netguard.record_allowed(False)
        netguard.uninstall()
        os.environ.clear()
        os.environ.update(before)
        server.close()
    assert check.answer is not None and check.answer["result"] == "newer", check.answer
    assert (check.answer["installed"], check.answer["newest"], check.answer["date"]) == ("0.8.1", "0.9.0", "2026-11-25")
    assert [r["path"] for r in server.seen] == [CHANGELOG_PATH]


def test_the_program_runs_isolated_without_a_console_and_below_normal_priority(program, monkeypatch):
    (program / "check_update.py").write_text("", "utf-8")
    started = []

    class Proc:
        def __init__(self, command, **kwargs):
            started.append((command, kwargs))

        def communicate(self, timeout=None):
            return json.dumps(newer_answer()).encode(), b""

        def poll(self):
            return 0

    monkeypatch.setattr(updates.subprocess, "Popen", Proc)
    check = updates.Check()
    check._thread.join(10)
    command, kwargs = started[0]
    assert command[1:] == ["-I", str(program / "check_update.py"), "check"]
    assert Path(command[0]).name.lower() in ("python.exe", "python")  # never pythonw.exe: its output is read
    assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["cwd"] == str(program) and "env" not in kwargs
    if sys.platform == "win32":
        assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    assert check.answer == newer_answer()


def test_a_program_that_does_not_answer_is_ended(program):
    (program / "check_update.py").write_text("import time\ntime.sleep(60)\n", "utf-8")
    started = time.monotonic()
    check = updates.Check(wait_s=1.0)
    check._thread.join(30)
    assert time.monotonic() - started < 20
    assert check.answer["result"] == "could not ask" and check.answer["reason"] == "GitHub did not answer in time."
    assert check._proc.poll() is not None  # ended


def test_no_program_no_request(program):
    check = updates.Check()
    check._thread.join(10)
    assert check.answer["result"] == "could not ask" and "check_update.py" in check.answer["reason"]


REASONS = [  # every sentence check_update.py gives for a check that could not ask (its failure_sentence, AskError)
    "GitHub did not answer in time.", "The secure connection to GitHub could not be made.",
    "GitHub could not be reached: is this computer online?", "GitHub could not be reached.",
    "The connection to GitHub broke off.", "GitHub answered with HTTP 503.",
    "The newest version could not be read from GitHub's answer.",
    "GitHub sent the request on to another address (evil.example), which is not asked.",
    "GitHub answered with a redirect that names no address.", "GitHub sent the request on too many times.",
    "GitHub's answer is larger than expected (more than 1 MB).",
    "The installed version could not be read: pyproject.toml is not in the TASlation folder.",
    "The installed version could not be read from pyproject.toml.",
    "check_update.py is not in the TASlation folder.", "check_update.py could not be started (Access is denied).",
]


@pytest.mark.parametrize("code", ["en", "ja", "de"])
def test_every_reason_is_one_sentence_in_the_window_s_language(code):
    set_language(code)
    try:
        fallback = _("GitHub could not be asked just now.")
        mapped = {reason: reason_text(reason) for reason in REASONS}
        known = [r for r in REASONS if "redirect" not in r and "too many" not in r]
        assert all(mapped[r] != fallback for r in known), [r for r in known if mapped[r] == fallback]
        assert "503" in mapped["GitHub answered with HTTP 503."]
        assert all("evil.example" not in text for text in mapped.values())  # (a host GitHub named is not repeated)
        if code != "en":
            assert all(text != reason for reason, text in mapped.items())
        assert reason_text("something new") == fallback
    finally:
        set_language("en")


def test_the_reasons_in_check_update_py_are_those_the_window_knows():
    source = (ROOT / "check_update.py").read_text("utf-8")
    for reason in ("GitHub did not answer in time.", "The secure connection to GitHub could not be made.",
                   "GitHub could not be reached: is this computer online?", "The connection to GitHub broke off.",
                   "The newest version could not be read from GitHub's answer.", "GitHub answered with HTTP {",
                   "GitHub sent the request on to another address (", "GitHub's answer is larger than expected",
                   "The installed version could not be read"):
        assert reason in source, reason


# ---------------------------------------------------------------- the look at the start
class Window:
    """What the start's look needs of the window: its settings, whether it is ready or busy, its job queue, the status
    line, the Help menu's item, and Tk's ``after`` (kept, run by the test)."""

    def __init__(self, root, state_dir, update_check="daily"):
        self.root = root
        self.settings = Settings(state_dir=state_dir, update_check=update_check)
        self.ready, self.busy, self.reading, self.batch = True, False, False, None
        self._jobs: queue.Queue = queue.Queue()
        self._queued = None
        self.status_var = tk.StringVar(root, value="Ready.")
        self._status_render = self._status_key = self._status_page = None
        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="?")
        self._update_entry = (self.menu, 0)
        self.later: list = []

    def after(self, ms, func=None, *args):
        self.later.append((ms, func))
        return "after#test"

    def winfo_exists(self):
        return True

    def run_later(self):
        ms, func = self.later.pop(0)
        func()
        return ms

    def label(self):
        return str(self.menu.entrycget(0, "label"))


class FakeCheck:
    """`updates.Check` that answers what the test gives it, at once."""
    answers: list = []
    made = 0

    def __init__(self, root=None, wait_s=None):
        FakeCheck.made += 1
        self.answer = FakeCheck.answers.pop(0)
        self._cancelled = SimpleNamespace(is_set=lambda: False)

    def cancel(self):
        pass


@pytest.fixture
def fake_check(monkeypatch, program):
    FakeCheck.answers, FakeCheck.made = [], 0
    monkeypatch.setattr(updates, "Check", FakeCheck)
    monkeypatch.setattr(updates, "installed_version", lambda: "0.8.1")
    monkeypatch.setattr(updates.time, "time", lambda: NOW)
    return FakeCheck


def test_a_newer_version_found_at_the_start_shows_in_the_help_menu_and_one_quiet_line(hidden_root, state, fake_check):
    before = set(hidden_root.winfo_children())  # (what other tests left on the shared root)
    w = Window(hidden_root, state)
    updates.setup(w)
    updates.relabel(w)
    assert w.label() == "Check for updates..."
    updates.on_ready(w)
    updates.on_ready(w)  # the window ready again (a model loaded): planned once
    assert [ms for ms, _f in w.later] == [updates.START_DELAY_MS]  # never sooner than 30 s after the start
    fake_check.answers.append(newer_answer())
    w.run_later()  # the look
    assert fake_check.made == 1
    w.run_later()  # its answer, as `watch` polls for it
    assert w.label() == "Check for updates... (0.9.0 is available)"
    assert w.status_var.get() == "TASlation 0.9.0 is available: Help > Check for updates..."
    assert not [c for c in hidden_root.winfo_children()
                if isinstance(c, tk.Toplevel) and c not in before]  # no dialog, no popup
    assert updates.load_state(state) == {"checked": NOW, "newest": "0.9.0", "date": "2026-11-25"}
    assert not w.later  # once
    other = Window(hidden_root, state)  # the next start within the day: nothing asked, the menu says it
    updates.setup(other)
    updates.relabel(other)
    updates.on_ready(other)
    assert other.label() == "Check for updates... (0.9.0 is available)" and not other.later


def test_the_look_waits_while_a_page_is_read_and_the_quiet_line_while_the_status_line_is_the_work_s(
        hidden_root, state, fake_check):
    w = Window(hidden_root, state)
    updates.setup(w)
    updates.on_ready(w)
    w.busy = True  # a page is translated
    w.run_later()
    assert fake_check.made == 0 and [ms for ms, _f in w.later] == [updates.BUSY_RETRY_MS]
    w.busy, w._queued = False, object()  # a page waits
    w.run_later()
    assert fake_check.made == 0
    w._queued = None
    w._jobs.put("job")  # a job waits for the worker
    w.run_later()
    assert fake_check.made == 0
    w._jobs.get()
    fake_check.answers.append(newer_answer())
    w.run_later()
    assert fake_check.made == 1
    w.busy = True  # the reader turned a page meanwhile
    w.status_var.set("Translating...")
    w.run_later()  # the answer: noted, the menu says it, the line waits
    assert w.label().endswith("(0.9.0 is available)") and w.status_var.get() == "Translating..."
    assert [ms for ms, _f in w.later] == [updates.QUIET_RETRY_MS]
    w.busy = False
    w.run_later()
    assert w.status_var.get().startswith("TASlation 0.9.0 is available")


def test_a_look_that_fails_says_nothing(hidden_root, state, fake_check):
    w = Window(hidden_root, state)
    updates.setup(w)
    updates.on_ready(w)
    fake_check.answers.append(updates.failed("GitHub could not be reached."))
    w.run_later()
    w.run_later()
    assert w.status_var.get() == "Ready." and w.label() == "?"  # (not relabelled)
    assert updates.load_state(state)["checked"] == NOW and not w.later  # not asked again before tomorrow
    tomorrow = Window(hidden_root, state)
    updates.setup(tomorrow)
    updates.on_ready(tomorrow, now=NOW + 3600)
    assert not tomorrow.later
    later = Window(hidden_root, state)
    updates.setup(later)
    updates.on_ready(later, now=NOW + updates.DAY_S + 1)
    assert later.later


def test_up_to_date_says_nothing_either(hidden_root, state, fake_check):
    w = Window(hidden_root, state)
    updates.setup(w)
    updates.on_ready(w)
    fake_check.answers.append(newer_answer(result="up to date", newest="0.8.1", newer=False, changes=""))
    w.run_later()
    w.run_later()
    assert w.status_var.get() == "Ready." and updates.load_state(state)["newest"] == "0.8.1"


@pytest.mark.parametrize("why", ["off", "clone", "today"])
def test_nothing_is_asked_at_the_start_otherwise(hidden_root, state, fake_check, program, why):
    w = Window(hidden_root, state, update_check="off" if why == "off" else "daily")
    if why == "clone":
        (program / ".git").write_text("gitdir: elsewhere\n", "utf-8")  # (a worktree's .git is a file)
    if why == "today":
        updates.save_state(state, NOW - 60)
    updates.setup(w)
    updates.on_ready(w)
    assert not w.later and fake_check.made == 0


def test_a_look_under_way_ends_with_the_window(state):
    ended = []
    w = SimpleNamespace(_update_check=SimpleNamespace(cancel=lambda: ended.append(True)))
    updates.stop(w)
    assert ended == [True] and w._update_check is None
    updates.stop(SimpleNamespace())  # (a window that never looked)


# ---------------------------------------------------------------- the Help menu
def test_check_for_updates_is_in_the_help_menu_before_about(tmp_path, hidden_root, state, monkeypatch):
    from taslation.ui import app as app_mod

    called = []

    class Menus(tk.Toplevel):
        _build_menus = app_mod.App._build_menus

        def __getattr__(self, name):
            if name.startswith(("open_", "toggle_", "show_", "_on_", "retranslate", "translate", "set_", "undo", "redo",
                                "_redisplay", "_apply", "review_")):
                return lambda *a: called.append(name)
            raise AttributeError(name)

    m = Menus(hidden_root)
    m.withdraw()
    m.settings = Settings(state_dir=state)
    for name in ("auto_var", "original_var", "top_var", "over_var", "order_numbers_var"):
        setattr(m, name, tk.BooleanVar(m))
    m.role_var, m.ui_lang_var = tk.StringVar(m), tk.StringVar(m)
    m._update_known = ("0.9.0", "2026-11-25")
    m._build_menus()
    menus = {str(m.menubar.entrycget(i, "label")): m.menubar.nametowidget(m.menubar.entrycget(i, "menu"))
             for i in range(int(m.menubar.index("end")) + 1) if m.menubar.type(i) == "cascade"}
    menu = menus["Help"]
    labels = [str(menu.entrycget(i, "label")) if menu.type(i) != "separator" else "-"
              for i in range(int(menu.index("end")) + 1)]
    assert labels == ["How to use...", "Keys...", "Legal notice...", "-", "Check for updates... (0.9.0 is available)",
                      "About TASlation"]
    assert m._update_entry == (menu, 4)
    menu.invoke(4)
    assert called == ["open_updates"]
    m._update_known = None
    updates.relabel(m)
    assert str(menu.entrycget(4, "label")) == "Check for updates..."
    m.destroy()


# ---------------------------------------------------------------- the dialog
class DialogWindow:
    def __init__(self, root, state_dir, config_path):
        self.root = root
        self.settings = Settings(state_dir=state_dir)
        self.settings.config_path = config_path
        self._update_entry = None

    def after(self, ms, func=None, *args):
        return self.root.after(ms, func, *args)


def _open(hidden_root, tmp_path, answer, program, on_update=None):
    w = DialogWindow(hidden_root, tmp_path / "state", tmp_path / "taslation.toml")
    FakeCheck.answers, FakeCheck.made = [answer], 0
    d = UpdateDialog(hidden_root, w, on_update=on_update, root=program)
    deadline = time.monotonic() + 5
    while d.shown == "asking" and time.monotonic() < deadline:
        hidden_root.update()
        time.sleep(0.02)
    return w, d


@pytest.fixture
def dialog_checks(monkeypatch, program):
    monkeypatch.setattr(updates, "Check", FakeCheck)
    monkeypatch.setattr(updates, "installed_version", lambda: "0.8.1")
    return program


def _texts(widget) -> list[str]:
    out = []
    for child in widget.winfo_children():
        try:
            out.append(str(child.cget("text")))
        except tk.TclError:
            pass
        out += _texts(child)
    return out


def test_the_dialog_shows_a_newer_version_with_its_changes_and_update_now(tmp_path, hidden_root, dialog_checks):
    chosen = []
    w, d = _open(hidden_root, tmp_path, newer_answer(), dialog_checks, on_update=chosen.append)
    assert d.shown == "newer" and d.title() == "Check for updates"
    texts = _texts(d)
    assert "A newer version of TASlation is available." in d.lines
    assert "This one: 0.8.1, of 2026-11-20" in d.lines and "The new one: 0.9.0, of 2026-11-25" in d.lines
    assert d.changes.get("1.0", "end-1c") == newer_answer()["changes"] and str(d.changes.cget("state")) == "disabled"
    assert "Update now" in texts and "Later" in texts
    assert "Look for a new version once a day when TASlation starts" in texts
    assert updates.load_state(tmp_path / "state")["newest"] == "0.9.0"  # noted
    d.update_btn.invoke()
    assert chosen == ["0.9.0"] and not d.winfo_exists()


def test_the_dialog_says_this_is_the_newest_version(tmp_path, hidden_root, dialog_checks):
    _w, d = _open(hidden_root, tmp_path, newer_answer(result="up to date", newest="0.8.1", newer=False, changes=""),
                  dialog_checks)
    assert d.shown == "up to date" and d.lines == ["This TASlation is the newest version.", "This one: 0.8.1, of 2026-11-20"]
    assert d.update_btn is None and "Update now" not in _texts(d)
    d.close_btn.invoke()


def test_the_dialog_says_why_github_could_not_be_asked_in_the_window_s_language(tmp_path, hidden_root, dialog_checks):
    set_language("ja")
    try:
        _w, d = _open(hidden_root, tmp_path, updates.failed("GitHub could not be reached: is this computer online?"),
                      dialog_checks)
        assert d.shown == "could not ask" and d.lines == [_("GitHub could not be reached: is this computer online?")]
        assert d.lines[0] != "GitHub could not be reached: is this computer online?" and d.update_btn is None
        d.close()
    finally:
        set_language("en")


def test_in_a_git_clone_the_dialog_asks_nothing(tmp_path, hidden_root, dialog_checks):
    (dialog_checks / ".git").mkdir()
    _w, d = _open(hidden_root, tmp_path, newer_answer(), dialog_checks)
    assert d.shown == "clone" and FakeCheck.made == 0 and d.choice_box is None
    assert "git pull" in d.lines[0]
    d.close()


def test_the_box_keeps_the_setting_in_taslation_toml(tmp_path, hidden_root, dialog_checks):
    w, d = _open(hidden_root, tmp_path, newer_answer(), dialog_checks)
    assert not d.choice_var.get()
    d.choice_box.invoke()
    assert w.settings.update_check == "daily"
    text = (tmp_path / "taslation.toml").read_text("utf-8")
    assert [line for line in text.splitlines() if line.startswith("update_check")][0].startswith('update_check = "daily"')
    d.choice_box.invoke()
    assert w.settings.update_check == "off"
    d.close()


def test_a_box_that_cannot_be_kept_goes_back_and_says_why(tmp_path, hidden_root, dialog_checks):
    w, d = _open(hidden_root, tmp_path, newer_answer(), dialog_checks)
    w.settings.config_path = tmp_path / "a folder"
    (tmp_path / "a folder").mkdir()
    d.choice_box.invoke()
    assert not d.choice_var.get() and w.settings.update_check == "off"
    assert str(d.choice_note.cget("text")).replace("\n", " ").startswith("Not kept:")
    d.close()


def test_closing_the_dialog_while_it_asks_ends_the_program(tmp_path, hidden_root, monkeypatch, program):
    cancelled = []

    class Slow(FakeCheck):
        def __init__(self, root=None, wait_s=None):
            self.answer = None
            self._cancelled = SimpleNamespace(is_set=lambda: bool(cancelled))

        def cancel(self):
            cancelled.append(True)

    monkeypatch.setattr(updates, "Check", Slow)
    w = DialogWindow(hidden_root, tmp_path / "state", tmp_path / "taslation.toml")
    d = UpdateDialog(hidden_root, w, root=program)
    assert d.shown == "asking" and d.lines == ["Asking GitHub for the newest version ..."]
    d.close()
    assert cancelled == [True] and not d.winfo_exists()
    hidden_root.update()
    assert not (tmp_path / "state" / "update-check.json").exists()  # nothing noted


# ---------------------------------------------------------------- Update now
def test_update_cmd_s_command_line(program):
    line = updates.update_command("0.9.0", 4242)
    shell = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "cmd.exe"
    assert line == f'"{shell}" /d /s /c ""{program / "update.cmd"}" -Download -Version 0.9.0 -WaitFor 4242 -Confirmed -Restart"'
    for bad in ("0.9", "0.9.0 & calc", "../0.9.0", ""):
        with pytest.raises(ValueError):
            updates.update_command(bad, 1)


def _program_files(folder: Path) -> None:
    for name in ("update.cmd", "update.ps1", "check_update.py"):
        (folder / name).write_text("", "utf-8")


def test_update_cmd_starts_in_a_console_of_its_own_outside_the_window_s_job(program, monkeypatch):
    _program_files(program)
    monkeypatch.setattr(updates, "update_env", lambda: {"PATH": "x"})
    calls = []

    def popen(line, **kwargs):
        calls.append((line, kwargs))
        if len(calls) == 1 and kwargs["creationflags"] & getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0):
            raise PermissionError(5, "Access is denied")  # a job that lets no process go
        return SimpleNamespace()

    assert updates.launch_update("0.9.0", pid=77, popen=popen) is None
    line, kwargs = calls[-1]
    assert line == updates.update_command("0.9.0", 77) and kwargs["cwd"] == str(program)
    assert kwargs["env"] == {"PATH": "x"}
    if sys.platform == "win32":
        assert len(calls) == 2
        assert calls[0][1]["creationflags"] == subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_BREAKAWAY_FROM_JOB
        assert kwargs["creationflags"] == subprocess.CREATE_NEW_CONSOLE


def test_update_cmd_that_cannot_start_is_said(program, monkeypatch):
    _program_files(program)
    monkeypatch.setattr(updates, "update_env", lambda: {})

    def popen(line, **kwargs):
        raise FileNotFoundError(2, "The system cannot find the file specified")

    assert updates.launch_update("0.9.0", popen=popen) == \
        "update.cmd could not be started (The system cannot find the file specified)."
    (program / "update.ps1").unlink()
    assert updates.launch_update("0.9.0", popen=popen) == "update.ps1 is not in the TASlation folder."
    (program / ".git").mkdir()
    assert updates.launch_update("0.9.0", popen=popen) == "This TASlation is a git clone: update it with git."


def test_update_cmd_gets_the_environment_windows_keeps_not_the_guard_s():
    base = {"PATH": r"C:\bin", "HF_HUB_OFFLINE": "1", "NO_PROXY": "*", "no_proxy": "*", "TASLATION_STATE_DIR": "s"}
    kept = {"NO_PROXY": "intranet.example", "HTTPS_PROXY": "http://proxy.example:8080"}
    env = updates.update_env(base, kept.get)
    assert env == {"PATH": r"C:\bin", "TASLATION_STATE_DIR": "s", "NO_PROXY": "intranet.example",
                   "HTTPS_PROXY": "http://proxy.example:8080"}
    assert set(updates.GUARD_VARIABLES) >= set(netguard.OFFLINE_ENV) | set(netguard.PROXY_ENV)


class Closing:
    def __init__(self):
        self.closed = []
        self._update_check = None

    def _on_close(self, asked=False):
        self.closed.append(asked)


def test_update_now_closes_the_window_once_update_cmd_started(monkeypatch):
    from taslation.ui import strip

    released = []
    monkeypatch.setattr(strip, "close_warning", lambda window: None)
    monkeypatch.setattr(strip, "release_run_images", lambda window: released.append(window))
    w = Closing()
    asked = []
    assert updates.update_now(w, "0.9.0", launch=lambda version: asked.append(version))
    assert asked == ["0.9.0"] and released == [w] and w.closed == [True]


def test_update_now_that_cannot_start_keeps_the_window_open(monkeypatch):
    from taslation.ui import strip
    from taslation.ui.dialogs import caches

    told, released = [], []
    monkeypatch.setattr(strip, "close_warning", lambda window: None)
    monkeypatch.setattr(strip, "release_run_images", lambda window: released.append(window))
    monkeypatch.setattr(caches, "tell", lambda parent, text, **kw: told.append(text))
    w = Closing()
    assert not updates.update_now(w, "0.9.0", launch=lambda version: "update.ps1 is not in the TASlation folder.")
    assert told == ["The update did not start: update.ps1 is not in the TASlation folder. TASlation stays open."]
    assert w.closed == [] and released == []  # the run's pictures stay


def test_update_now_asks_first_what_closing_would_lose(monkeypatch):
    from taslation.ui import strip
    from taslation.ui.dialogs import caches

    boxes = []

    class Box:
        def __init__(self, master, title, text, **kw):
            boxes.append((text, kw))
            self.answer = False

        def winfo_exists(self):
            return False

    monkeypatch.setattr(strip, "close_warning", lambda window: "The whole-book run has read 3 page(s)...")
    monkeypatch.setattr(caches, "WarningBox", Box)
    w, started = Closing(), []
    assert not updates.update_now(w, "0.9.0", launch=lambda version: started.append(version))
    assert started == [] and w.closed == []
    assert boxes[0][1]["go"] == "Close anyway" and boxes[0][1]["stay"] == "Keep TASlation open"


def test_the_close_asked_already_is_not_asked_again():
    from taslation.ui import app as app_mod

    import inspect

    source = inspect.getsource(app_mod.App._on_close)
    assert "if not asked and not self._close_allowed()" in source and "updates.stop(self)" in source
