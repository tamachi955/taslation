"""The person's keys stay with the book (see-through mode): the log of the foreground (`ui.seethrough.foreground_tick`:
every change that involves TASlation's windows, and the viewer losing it while a job is at work, one line and a count,
no title); a dialog that comes by itself during a session shown without taking the foreground while the person is in
the book (`seethrough.comes_quietly`, `layout.show_by_itself` / `show_quietly`: ``wm state normal``, never ``wm
deiconify``; topmost by SWP_NOACTIVATE; `front_tick` brings none such to the front), a box of TASlation's too
(`caches._box`); the region editor's closing handing the foreground back in the same call (`seethrough.closing`,
`EditBubbleDialog._save` / ``destroy``); the lettering and the panes never activated by a press (MA_NOACTIVATE on every
path); the server's runner put at the server's priority class, never above normal (`ollama_start.level_runners`); the
stand-in browser started minimised and not activated, the foreground locked while it opens
(`tools.standin_viewer.quiet_start`, `lock_foreground`). Fakes and a withdrawn Tk root only: nothing is shown, no key,
no click, no process's class changed, no lock set."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import taslation.capture as capture
from taslation import ollama_start as os_
from taslation.capture import Fronted
from taslation.capture import seethrough as cs
from taslation.pipeline import manual_region
from taslation.ui import layout
from taslation.ui import seethrough as ui
from taslation.ui.dialogs import caches, review

ROOT = Path(__file__).resolve().parent.parent
ME = os.getpid()
VIEWER, ROOT_HWND, LETTERING, PANE, DIALOG = 5, 77, 40, 41, 300


class Notes:
    def __init__(self, notes):
        self.notes = list(notes)

    def take(self):
        notes, self.notes = self.notes, []
        return notes


def _app(**more):
    app = SimpleNamespace(_see_hidden=True, _own_hwnd=lambda: ROOT_HWND, selected=SimpleNamespace(hwnd=VIEWER),
                          _see_through=SimpleNamespace(hwnd=LETTERING, panes={"left": PANE},
                                                       own_windows=lambda: frozenset({LETTERING, PANE})),
                          busy=False, _busy_since=None, _see_kinds={})
    for key, value in more.items():
        setattr(app, key, value)
    return app


def _note(hwnd, pid=ME, root=None, owner=None, cls="", at=None):
    return Fronted(time.monotonic() if at is None else at, hwnd, pid, hwnd if root is None else root,
                   hwnd if owner is None else owner, cls)


# ------------------------------------------------------------------ the log of the foreground
def test_each_change_that_involves_the_programs_windows_is_one_line_and_counted_by_kind_with_no_title(caplog):
    t0 = 1000.0
    app = _app(_busy_since=t0, busy=True, role_var=SimpleNamespace(get=lambda: "translator"))
    app._see_kinds[DIALOG] = "EditBubbleDialog"
    app._see_front_kind = "the viewer"
    app._see_fronts = Notes([
        _note(DIALOG, at=t0 + 0.120),                      # the viewer -> the region editor
        _note(VIEWER, pid=999, at=t0 + 0.400),             # back to the viewer
        _note(ROOT_HWND, at=t0 + 0.410),                   # the hidden window (a dialog of its own went)
        _note(VIEWER, pid=999, at=t0 + 0.450),
        _note(LETTERING, at=t0 + 0.500),                   # the lettering (never to be)
        _note(PANE, at=t0 + 0.600),
        _note(900, pid=999, at=t0 + 0.700),                # to another program
        _note(901, pid=999, at=t0 + 0.800),                # another to another: not ours, not the viewer: no line
        _note(VIEWER, pid=999, at=t0 + 0.900),
        _note(VIEWER, pid=999, at=t0 + 0.950),             # the same again: no change
        _note(902, pid=999, at=t0 - 0.030),                # the viewer loses it while a job runs (before its start)
        _note(903, pid=ME, cls="#32770", at=t0 + 1.0),    # a message box of TASlation's
        _note(904, pid=ME, cls="#32768", at=t0 + 1.1),    # a menu
        _note(0, pid=0, at=t0 + 1.2),                      # nothing in front
    ])
    with caplog.at_level("INFO", logger=ui.log.name):
        lines = ui.foreground_tick(app)
    assert lines[0] == ("foreground: the viewer -> a dialog (EditBubbleDialog); 120 ms after the last job's start, "
                        "a job at work; editing on; just before: nothing of TASlation's")
    assert lines[1].startswith("foreground: a dialog (EditBubbleDialog) -> the viewer; 400 ms")
    assert any(line.startswith("foreground: the viewer -> another program; -30 ms") for line in lines)
    counts = app._see_foreground
    # (back to the viewer from another program too)
    assert counts["a dialog (EditBubbleDialog)"] == 1 and counts["back to the viewer"] == 3
    assert counts["the hidden window"] == 1 and counts["the lettering"] == 1 and counts["a side pane"] == 1
    assert counts["to another program"] == 2 and counts["a message box"] == 1 and counts["a menu"] == 1
    assert counts["the viewer lost it in a job"] == 4  # (to the editor, the hidden window, the lettering, another)
    assert counts["to nothing"] == 1
    assert len(lines) == sum(v for k, v in counts.items() if k != "the viewer lost it in a job")
    assert all(r.getMessage() in lines for r in caplog.records)
    assert app._see_front_kind == "nothing" and app._see_fronts.notes == []


def test_the_log_says_when_no_job_ran_yet_and_edit_off_and_another_programs_window_is_only_another_program():
    app = _app(_see_front_kind="another program")
    app._see_fronts = Notes([_note(DIALOG), _note(VIEWER, pid=999, root=1234, owner=VIEWER)])  # (a popup of the viewer)
    lines = ui.foreground_tick(app)
    assert lines == ["foreground: another program -> a window of TASlation's; no job yet; editing off; just before: "
                     "nothing of TASlation's",
                     "foreground: a window of TASlation's -> the viewer; no job yet; editing off"]
    kinds = [ui.front_kind(app, _note(888, pid=999)), ui.front_kind(app, _note(0, pid=0))]
    assert kinds == ["another program", "nothing"]
    assert ui.foreground_tick(SimpleNamespace()) == []  # (no hook: silent)


class Looked(Notes):
    """Notes with the window in front at each tick as well (`capture.ForegroundNotes.now`)."""

    def __init__(self, notes, front):
        super().__init__(notes)
        self.front = front

    def now(self):
        return self.front


def test_a_change_the_hook_did_not_bring_is_seen_at_the_tick_and_logged_once():
    app = _app(_see_front_kind="the viewer", _see_front_hwnd=VIEWER)
    app._see_kinds[DIALOG] = "WarningBox"
    app._see_fronts = Looked([], _note(DIALOG))  # (the hook brought nothing: the dialog is in front now)
    assert ui.foreground_tick(app) == ["foreground: the viewer -> a dialog (WarningBox); no job yet; editing off; "
                                       "just before: nothing of TASlation's"]
    assert ui.foreground_tick(app) == [] and app._see_front_polled == 1  # (still in front: no second line)
    app._see_fronts = Looked([_note(VIEWER, pid=999)], _note(VIEWER, pid=999))  # (the hook's note: none added)
    assert ui.foreground_tick(app) == ["foreground: a dialog (WarningBox) -> the viewer; no job yet; editing off"]
    assert app._see_front_polled == 1 and app._see_front_notes == 1


def test_a_dialog_shown_is_remembered_by_its_frame_for_the_log(hidden_root, monkeypatch):
    import tkinter as tk

    class SomeDialog(tk.Toplevel):
        pass

    app = _app()
    dialog = SomeDialog(hidden_root)
    dialog.withdraw()
    ui._remember_kind(app, dialog)
    assert app._see_kinds[int(dialog.wm_frame(), 16)] == "SomeDialog"
    for i in range(ui.KINDS_KEPT + 5):
        app._see_kinds[10_000 + i] = "x"
        ui._remember_kind(app, dialog)
    assert len(app._see_kinds) <= ui.KINDS_KEPT + 1
    dialog.destroy()


def test_the_foreground_notes_take_nothing_of_another_programs_window():
    other = capture.fronted(0)
    assert other.hwnd == 0 and other.own_class == ""
    if sys.platform == "win32":
        import ctypes

        desk = int(ctypes.windll.user32.GetDesktopWindow())
        assert capture.fronted(desk, own_pid=-1).own_class == ""  # (another process: no class name either)


def test_a_line_to_a_window_of_taslations_says_what_taslation_did_just_before():
    t0 = time.monotonic()
    app = _app(_see_front_kind="the viewer")
    app._see_kinds[DIALOG] = "ViewerDialog"
    ui.did(app, "a request of the person's")
    ui.did(app, "ViewerDialog shown")
    app._see_acts[-1] = (t0, "ViewerDialog shown")
    app._see_fronts = Notes([_note(DIALOG, at=t0 + 0.004), _note(VIEWER, pid=999, at=t0 + 0.2),
                             _note(LETTERING, at=t0 + ui.JUST_BEFORE_S + 1)])
    lines = ui.foreground_tick(app)
    assert lines[0].endswith("; just before: ViewerDialog shown, 4 ms before")
    assert "just before" not in lines[1]  # (to the viewer: none)
    assert lines[2].endswith("; just before: nothing of TASlation's")  # (too long before)
    for i in range(ui.ACTS_KEPT + 3):
        ui.did(app, f"act {i}")
    assert len(app._see_acts) == ui.ACTS_KEPT and ui.just_before(app).startswith(f"act {ui.ACTS_KEPT + 2}, ")
    assert ui.just_before(SimpleNamespace()) == "nothing of TASlation's"


def test_the_viewer_losing_or_getting_the_foreground_is_logged_outside_a_job_and_its_programs_other_window_named():
    app = _app(_see_front_kind="the viewer")
    app.selected.pid = 999
    app._see_fronts = Notes([_note(950, pid=999),            # the viewer's program's other window (a browser's)
                             _note(960, pid=555),            # from it to another program: no line
                             _note(0, pid=0),                # nothing: no line
                             _note(VIEWER, pid=999),         # back to the viewer
                             _note(961, pid=555)])           # to another program, no job at work
    lines = ui.foreground_tick(app)
    assert lines == ["foreground: the viewer -> another window of the viewer's program; no job yet; editing off",
                     "foreground: nothing -> the viewer; no job yet; editing off",
                     "foreground: the viewer -> another program; no job yet; editing off"]
    assert app._see_foreground == {"to another window of the viewer's program": 1, "back to the viewer": 1,
                                   "to another program": 1}


def test_a_window_of_taslations_not_seen_shown_yet_is_named_by_its_live_window(hidden_root):
    import tkinter as tk

    class SomeDialog(tk.Toplevel):
        pass

    app = hidden_root
    dialog, entry, tip = SomeDialog(app), tk.Toplevel(app), tk.Toplevel(app)
    try:
        for w in (dialog, entry, tip):
            w.withdraw()
        entry._see_name = ui.PLACE_ENTRY
        entry.wm_overrideredirect(True)
        tip.wm_overrideredirect(True)
        kinds = [ui.front_kind(app, _note(int(w.wm_frame(), 16), cls="TkTopLevel")) for w in (dialog, entry, tip)]
        assert kinds == ["a dialog (SomeDialog)", "the place entry", "a window of TASlation's (TkTopLevel)"]
        assert app._see_kinds[int(dialog.wm_frame(), 16)] == "SomeDialog"  # (remembered: it may go before the log)
    finally:
        for w in (dialog, entry, tip):
            w.destroy()
        app.__dict__.pop("_see_kinds", None)


# ------------------------------------------------------------------ the guard of the keys
@pytest.fixture
def front_now(monkeypatch):
    """The window in front, a fake's: (hwnd, pid, class) set by the test; what was given the foreground."""
    state = {"front": (LETTERING, ME, "TASlationSeeThrough"), "given": []}

    def fronted(hwnd, own_pid=None):
        front, pid, cls = state["front"]
        return _note(front, pid=pid, cls=cls)

    def give(hwnd):
        state["given"].append(hwnd)
        state["front"] = (hwnd, 999, "")
        return True

    monkeypatch.setattr(capture, "foreground_window", lambda: state["front"][0])
    monkeypatch.setattr(capture, "fronted", fronted)
    monkeypatch.setattr(capture, "give_foreground", give)
    monkeypatch.setattr(capture, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(ui, "own_dialogs", lambda app: state.get("dialogs", []))
    return state


@pytest.mark.parametrize("front, given", [
    ((LETTERING, ME, "TASlationSeeThrough"), "the lettering"), ((PANE, ME, "TASlationPane"), "a side pane"),
    ((555, ME, "TkTopLevel"), "a window of TASlation's (TkTopLevel)"), ((ROOT_HWND, ME, "TkTopLevel"), ""),
    ((DIALOG, ME, "TkTopLevel"), ""), ((903, ME, "#32770"), ""), ((904, ME, "#32768"), ""), ((VIEWER, 999, ""), ""),
    ((900, 999, ""), "")],
    ids=["the lettering", "a side pane", "an unknown window", "the hidden window (front_tick's)", "a dialog",
         "a message box", "a menu", "the viewer", "another program"])
def test_the_guard_gives_the_viewer_the_foreground_back_from_a_window_of_taslations_that_takes_no_keys(
        front_now, caplog, front, given):
    app = _app()
    app._see_kinds[DIALOG] = "EditBubbleDialog"
    front_now["front"] = front
    ui.did(app, "a press on the page: click")
    with caplog.at_level("INFO", logger=ui.log.name):
        assert ui.guard(app) == given
    if given:
        assert front_now["given"] == [VIEWER] and app._see_guarded == {given: 1}
        line = app._see_foreground_lines[-1]
        assert line.startswith(f"foreground guard: {given} was in front with no dialog of TASlation's open; given back "
                               "to the viewer; just before: a press on the page: click, ")
        assert any(r.getMessage() == line for r in caplog.records)
    else:
        assert front_now["given"] == [] and not getattr(app, "_see_guarded", None)


def test_the_guard_waits_while_a_dialog_the_editor_the_place_entry_or_a_menu_holds_the_person(front_now):
    holding = Shown()
    for setup in (lambda a: front_now.__setitem__("dialogs", [holding]),
                  lambda a: setattr(a, "_see_place_entry", object()),
                  lambda a: setattr(a, "_editor", SimpleNamespace(winfo_exists=lambda: True)),
                  lambda a: setattr(a, "_see_menu_up", True), ui.asked,
                  lambda a: setattr(a, "selected", None), lambda a: setattr(a, "_see_hidden", False)):
        app = _app()
        front_now["dialogs"], front_now["front"] = [], (LETTERING, ME, "")
        setup(app)
        assert ui.guard(app) == "" and front_now["given"] == []
    holding._see_quiet = True  # (a dialog that came by itself and waits, never clicked, holds no one)
    app = _app()
    front_now["dialogs"] = [holding]
    assert ui.guard(app) == "the lettering" and front_now["given"] == [VIEWER]


def test_the_guard_logs_the_same_window_once_in_a_while_and_counts_every_time(front_now):
    app = _app()
    for _again in range(3):
        front_now["front"] = (PANE, ME, "")
        assert ui.guard(app) == "a side pane"
    assert app._see_guarded == {"a side pane": 3} and len(app._see_foreground_lines) == 1
    app._see_guard_last = (PANE, time.monotonic() - ui.GUARD_QUIET_S - 1)
    front_now["front"] = (PANE, ME, "")
    ui.guard(app)
    assert len(app._see_foreground_lines) == 2


def test_nothing_of_taslations_moves_the_foreground_when_the_viewer_gets_it_from_another_program(front_now,
                                                                                                  monkeypatch):
    """(Alt+Tab, a click on the viewer, its taskbar button: Windows gives the viewer the foreground; the guard, the
    hand-back and the tick's look at the hidden window take nothing then)"""
    monkeypatch.setattr(ui.window, "cursor_pos", lambda: (10, 10))
    monkeypatch.setattr(ui.window, "shell_at", lambda point: True)
    app = _app(_see_front_kind="another program")
    front_now["front"] = (VIEWER, 999, "")
    app._see_fronts = Notes([_note(VIEWER, pid=999)])
    assert ui.foreground_tick(app) == ["foreground: another program -> the viewer; no job yet; editing off"]
    assert ui.guard(app) == "" and ui.front_tick(app) == "" and ui.hand_back(app) is False
    assert front_now["given"] == []


# ------------------------------------------------------------------ a press on the page with another program in front
@pytest.mark.parametrize("front, pid, tops, woken", [
    (VIEWER, 999, (VIEWER, VIEWER, VIEWER), False), (1234, 999, (1234, 1234, VIEWER), False),
    (900, 999, (900, 900, 900), True), (0, 0, (), True), (ROOT_HWND, ME, (ROOT_HWND,) * 3, True),
    (LETTERING, ME, (LETTERING,) * 3, True), (PANE, ME, (PANE,) * 3, True), (DIALOG, ME, (DIALOG,) * 3, False)],
    ids=["the viewer", "a popup of the viewer's", "another program", "nothing", "the hidden window", "the lettering",
         "a side pane", "a dialog, the editor, the place entry, a box or a menu of TASlation's"])
def test_a_press_on_the_page_makes_the_viewer_the_foreground_window_unless_it_or_a_dialog_of_taslations_is(
        front, pid, tops, woken):
    own = frozenset({ROOT_HWND, LETTERING, PANE})
    assert cs.wakes_viewer(front, pid, tops, VIEWER, ME, own) is woken
    assert cs.wakes_viewer(front, pid, tops, 0, ME, own) is False  # (no viewer followed)


class User32:
    """The calls `SeeThrough._wake_viewer` makes, a fake's: the window in front and the processes of the windows."""

    def __init__(self, front, pids):
        self.front, self.pids = front, pids

    def GetForegroundWindow(self):
        return self.front

    def GetWindowThreadProcessId(self, hwnd, ref):
        ref._obj.value = self.pids.get(hwnd, 0)
        return 1

    def GetAncestor(self, hwnd, how):
        return hwnd

    def SetCapture(self, hwnd):  # (the press's capture: nothing of the system's)
        return 0

    def ReleaseCapture(self):
        return 1

    def GetCapture(self):
        return 0


def _layer(monkeypatch, front, gives=True):
    """A see-through window's state as editing has it (no thread, no window), the window in front *front*, the
    foreground given (or refused) by a fake."""
    from taslation.capture import windows

    over = cs.SeeThrough()
    over.hwnd, over.panes, over._viewer, over._root = LETTERING, {"left": PANE}, VIEWER, ROOT_HWND
    over._edit_takes, over._last_look = True, (None,) * 6 + ((400, 300),)
    over._marks_live = SimpleNamespace(adding=False, locked=False, key=1, boxes=((10, 10, 60, 60),), serial=1)
    over._edit_redraw = lambda: None
    fake = User32(front, {VIEWER: 999, 900: 555, LETTERING: ME, PANE: ME, ROOT_HWND: ME, DIALOG: ME})
    given = []

    def give(hwnd):
        given.append(hwnd)
        fake.front = hwnd if gives else fake.front
        return gives

    monkeypatch.setattr(cs, "_user32", fake)
    monkeypatch.setattr(windows, "give_foreground", give)
    monkeypatch.setattr(cs.st, "edit_grip",
                        lambda marks, point, reach, left_out: (0, "move") if point[0] < 60 else None)
    monkeypatch.setattr(cs, "IS_WINDOWS", True)
    return over, fake, given


def _lp(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


@pytest.mark.parametrize("message, wparam", [
    (cs.WM_LBUTTONDOWN, 1), (cs.WM_RBUTTONDOWN, 2), (cs.WM_MBUTTONDOWN, 16), (cs.WM_XBUTTONDOWN, 1 << 16),
    (cs.WM_MOUSEWHEEL, 120 << 16), (cs.WM_MOUSEHWHEEL, 120 << 16)],
    ids=["left button", "right button", "middle button", "side button", "wheel", "tilt wheel"])
def test_each_press_on_the_lettering_while_editing_with_another_program_in_front_gives_the_viewer_the_foreground(
        monkeypatch, message, wparam):
    over, fake, given = _layer(monkeypatch, 900)
    over._edit_message(message, wparam, _lp(30, 30))
    assert given == [VIEWER] and fake.front == VIEWER and over.counts["woke"] == 1
    assert [n for n in over.notes if n["ev"] == "woke"][-1]["ok"] == 1
    assert over._edit_message(cs.WM_MOUSEACTIVATE, 0, 0) == cs.MA_NOACTIVATE  # (and the layer is never activated)
    over._edit_message(message, wparam, _lp(30, 30))  # (the viewer in front now: nothing more)
    assert given == [VIEWER]


def test_after_the_viewer_is_given_the_foreground_a_press_on_a_box_does_what_it_does_one_on_the_ground_nothing(
        monkeypatch):
    over, fake, given = _layer(monkeypatch, 900)
    over._edit_message(cs.WM_LBUTTONDOWN, 1, _lp(30, 30))  # (on the box)
    assert given == [VIEWER] and over._press is not None and over._press["index"] == 0
    over._edit_message(cs.WM_LBUTTONUP, 0, _lp(30, 30))
    assert [e["kind"] for e in over.take_edits()] == ["click"]
    fake.front = 900
    over._edit_message(cs.WM_LBUTTONDOWN, 1, _lp(200, 200))  # (on the empty ground: the way back to the book)
    assert given == [VIEWER, VIEWER] and over._press is None
    over._edit_message(cs.WM_MOUSEMOVE, 1, _lp(260, 260))
    over._edit_message(cs.WM_LBUTTONUP, 0, _lp(260, 260))
    assert over.take_edits() == [] and any(n["ev"] == "woke_only" for n in over.notes)
    over._edit_message(cs.WM_LBUTTONDOWN, 1, _lp(200, 200))  # (the viewer in front: a drag on the ground draws)
    assert over._press is not None and over._press.get("draw")


@pytest.mark.parametrize("front", [VIEWER, DIALOG], ids=["the viewer", "a dialog of TASlation's"])
def test_a_press_leaves_the_foreground_where_it_is_with_the_viewer_or_a_dialog_of_taslations_in_front(monkeypatch,
                                                                                                    front):
    over, fake, given = _layer(monkeypatch, front)
    over._edit_message(cs.WM_LBUTTONDOWN, 1, _lp(200, 200))
    assert given == [] and fake.front == front and over._press is not None and over.counts["woke"] == 0


@pytest.mark.parametrize("front", [ROOT_HWND, LETTERING, 0], ids=["the hidden window", "the lettering", "nothing"])
def test_a_press_with_taslations_hidden_window_or_nothing_in_front_gives_the_viewer_the_foreground(monkeypatch, front):
    over, fake, given = _layer(monkeypatch, front)
    over._edit_message(cs.WM_LBUTTONDOWN, 1, _lp(30, 30))
    assert given == [VIEWER]


def test_a_refused_hand_over_is_counted_and_the_press_goes_on(monkeypatch):
    over, fake, given = _layer(monkeypatch, 900, gives=False)
    over._edit_message(cs.WM_LBUTTONDOWN, 1, _lp(30, 30))
    assert given == [VIEWER] and over.counts["woke_failed"] == 1 and over.counts["woke"] == 0
    assert over._press is not None  # (on a box: held all the same)


def test_a_press_or_the_wheel_on_a_side_pane_gives_the_viewer_the_foreground_first(monkeypatch):
    woken = []
    monkeypatch.setitem(cs._pane_wakes, 4242, lambda why: woken.append(why))
    monkeypatch.setitem(cs._pane_clicks, 4242, lambda x, y: woken.append(("click", x, y)))
    assert cs._pane_proc(4242, cs.WM_MOUSEACTIVATE, 0, 0) == cs.MA_NOACTIVATE and woken == []
    cs._pane_proc(4242, cs.WM_LBUTTONDOWN, 1, _lp(5, 6))
    cs._pane_proc(4242, cs.WM_LBUTTONUP, 0, _lp(5, 6))
    assert woken == ["pane", ("click", 5, 6)]  # (then the click acted on as ever)
    assert cs._pane_proc(4242, cs.WM_MOUSEWHEEL, 120 << 16, 0) == 0 and woken[-1] == "pane"


def test_in_reader_mode_the_lettering_is_click_through_and_a_click_reaches_the_viewer_itself():
    assert cs.EX_STYLE & cs.WS_EX_TRANSPARENT and cs.EX_STYLE & cs.WS_EX_NOACTIVATE
    assert cs._proc(0, cs.WM_NCHITTEST, 0, 0) == cs.HTTRANSPARENT  # (no Edit: no hit, the viewer below takes it)
    reader = SimpleNamespace(_edit_takes=False)
    assert cs.SeeThrough._edit_message(reader, cs.WM_LBUTTONDOWN, 1, 0) is None  # (nothing taken, nothing woken)


# ------------------------------------------------------------------ who gets the keys
def _front(monkeypatch, hwnd, owner):
    monkeypatch.setattr(capture, "foreground_window", lambda: hwnd)
    monkeypatch.setattr(capture, "foreground_owner", lambda h, viewer, own_pid=None: owner)


@pytest.mark.parametrize("front, owner, quiet", [
    (VIEWER, "viewer", True), (900, "other", True), (ROOT_HWND, "own", True), (LETTERING, "own", True),
    (PANE, "own", True), (DIALOG, "own", False)],
    ids=["the viewer", "another program", "the hidden window", "the lettering", "a pane", "a dialog of its own"])
def test_a_dialog_that_comes_by_itself_comes_quietly_unless_the_person_is_in_a_dialog_of_its_own(
        monkeypatch, front, owner, quiet):
    _front(monkeypatch, front, owner)
    app = _app()
    assert ui.comes_quietly(app) is quiet
    ui.asked(app)  # (asked for just now: it takes the keys)
    assert ui.comes_quietly(app) is False
    app._see_asked -= ui.ASKED_S + 0.1
    assert ui.comes_quietly(app) is quiet
    app._see_hidden = False  # (TASlation's window on the screen: as ever)
    assert ui.comes_quietly(app) is False


class Shown:
    """A dialog's Tk calls, noted (a stand-in for a Toplevel)."""

    def __init__(self):
        self.calls, self.bound, self._see_quiet = [], {}, False

    def bind(self, sequence, func, add=None):
        self.bound.setdefault(sequence, []).append(func)

    def wm_state(self, state=None):
        self.calls.append(("state", state))

    def update_idletasks(self):
        pass

    def deiconify(self):
        self.calls.append(("deiconify",))

    def geometry(self, spec=None):
        self.calls.append(("geometry", spec))

    def winfo_ismapped(self):
        return True

    def attributes(self, *a):
        self.calls.append(("attributes",) + a)

    def lift(self):
        self.calls.append(("lift",))

    def focus_force(self):
        self.calls.append(("focus_force",))

    def focus_get(self):
        return None

    def focus_set(self):
        self.calls.append(("focus_set",))


def test_a_quiet_dialog_is_shown_without_deiconify_topmost_and_takes_the_keys_once_clicked(monkeypatch):
    win, focus = Shown(), Shown()
    layout.show_quietly(win, focus)
    assert ("state", "normal") in win.calls and ("deiconify",) not in win.calls
    assert ("focus_force",) not in win.calls and ("lift",) not in win.calls
    assert ("attributes", "-topmost", True) in win.calls  # (no frame: Tk's own flag; a frame: SWP_NOACTIVATE)
    assert win._see_quiet is True and focus.calls == []
    for taken in win.bound["<FocusIn>"]:  # (clicked: Windows activates it)
        taken(None)
    assert win._see_quiet is False and focus.calls == [("focus_set",)]


def test_a_quiet_dialog_shown_for_the_first_time_comes_where_it_was_placed():
    """(Tk's ``wm state normal`` maps a window never shown at the primary monitor's top left whatever place it was
    given while withdrawn - the GPU's box over a viewer on the second monitor came there: it is mapped unseen and
    moved to `place_window`'s place before it is seen)"""
    win = Shown()
    win._placed_at = (2650, 408)
    layout.show_quietly(win)
    calls = win.calls
    hidden, state, moved, seen = (calls.index(("attributes", "-alpha", 0.0)), calls.index(("state", "normal")),
                                  calls.index(("geometry", "+2650+408")), calls.index(("attributes", "-alpha", 1.0)))
    assert hidden < state < moved < seen and ("deiconify",) not in calls
    plain = Shown()  # (not placed by `place_window`: as before)
    layout.show_quietly(plain)
    assert not any(c[0] in ("geometry",) or c[1:2] == ("-alpha",) for c in plain.calls)


def test_show_by_itself_shows_quietly_or_as_ever(monkeypatch):
    parent = SimpleNamespace(_root=lambda: app)
    app = _app()
    monkeypatch.setattr(ui, "comes_quietly", lambda a: True)
    win = Shown()
    assert layout.show_by_itself(win, parent) is True
    assert ("deiconify",) not in win.calls and win._see_quiet and "<Destroy>" in win.bound  # (the viewer back after)
    monkeypatch.setattr(ui, "comes_quietly", lambda a: False)
    keys = []
    monkeypatch.setattr(layout, "dialog_keys", lambda w, p, f=None: keys.append(w))
    win = Shown()
    assert layout.show_by_itself(win, parent) is False and ("deiconify",) in win.calls and keys == [win]
    win = Shown()
    assert layout.show_by_itself(win, parent, quiet=True) is True  # (the caller decided)


def test_front_tick_brings_no_quiet_dialog_to_the_front_and_hands_the_foreground_to_the_viewer(monkeypatch):
    given = []
    monkeypatch.setattr(capture, "foreground_window", lambda: ROOT_HWND)
    monkeypatch.setattr(capture, "give_foreground", lambda hwnd: given.append(hwnd) or True)
    monkeypatch.setattr(capture, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(ui.window, "cursor_pos", lambda: (10, 10))
    monkeypatch.setattr(ui.window, "shell_at", lambda point: False)
    quiet = Shown()
    quiet._see_quiet = True
    monkeypatch.setattr(ui, "own_dialogs", lambda app: [quiet])
    app = _app()
    assert ui.front_tick(app) == "viewer" and given == [VIEWER] and quiet.calls == []
    quiet._see_quiet = False  # (clicked once: it is the person's)
    assert ui.front_tick(app) == "dialog" and ("focus_force",) in quiet.calls


def test_a_box_that_comes_by_itself_while_the_person_reads_is_shown_quietly(hidden_root, monkeypatch):
    shown, given = [], []
    monkeypatch.setattr(ui, "comes_quietly", lambda app: True)
    monkeypatch.setattr(layout, "show_quietly", lambda win, focus=None: shown.append((win, focus)))
    monkeypatch.setattr(caches, "give_foreground", lambda hwnd: given.append(hwnd) or True)
    monkeypatch.setattr(caches, "foreground_window", lambda: VIEWER)
    monkeypatch.setattr(hidden_root, "winfo_viewable", lambda: True)
    hidden_root.selected = SimpleNamespace(hwnd=VIEWER)
    try:
        box = caches._box(hidden_root, "A warning that came by itself.", False, alone=True)
        assert shown and shown[0][0] is box and shown[0][1] is box.continue_btn
        assert given == []  # (the box is not given the foreground: the viewer keeps it)
        box.destroy()
    finally:
        del hidden_root.selected


# ------------------------------------------------------------------ a dialog's closing
class Dialog:
    def __init__(self, frame):
        self.frame = frame

    def wm_frame(self):
        return hex(self.frame)


def test_the_closing_dialog_gives_the_foreground_to_the_viewer_in_the_same_call(monkeypatch):
    front, given = [DIALOG], []
    monkeypatch.setattr(capture, "foreground_window", lambda: front[0])
    monkeypatch.setattr(capture, "give_foreground", lambda hwnd: given.append(hwnd) or True)
    monkeypatch.setattr(capture, "window_exists", lambda hwnd: True)
    editor = Dialog(DIALOG)
    monkeypatch.setattr(ui, "own_dialogs", lambda app: [editor])
    app = _app()
    ui.asked(app)
    assert ui.closing(app, editor) is True and given == [VIEWER] and app._see_closing == 1
    assert app._see_asked < 0  # (the request ended with it: what comes by itself next comes quietly)
    front[0] = ROOT_HWND  # (Windows gave the hidden window the foreground already)
    assert ui.closing(app, editor) is True and given == [VIEWER, VIEWER]
    front[0] = VIEWER  # (the person went to the book meanwhile: nothing to give)
    assert ui.closing(app, editor) is False
    front[0] = DIALOG
    other = Dialog(DIALOG + 1)
    monkeypatch.setattr(ui, "own_dialogs", lambda app: [editor, other])  # (another dialog holds the person)
    assert ui.closing(app, editor) is False
    other._see_quiet = True  # (one that came by itself and was never clicked does not)
    assert ui.closing(app, editor) is True
    app._see_menu_up = True
    assert ui.closing(app, editor) is False
    app._see_menu_up, app.selected = False, None
    assert ui.closing(app, editor) is False and len(given) == 3


def _region():
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text = "translated", "Nice weather today, huh?", "今日はいい天気だね"
    return r


def test_the_editor_hands_the_foreground_back_before_its_save_is_stored_and_on_every_close_but_a_step(
        hidden_root, monkeypatch):
    order = []
    monkeypatch.setattr(ui, "closing", lambda app, dialog: order.append(("closing", type(dialog).__name__)))
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: order.append(("saved",)),
                                on_drop=lambda: None)
    d._save()
    assert order == [("closing", "EditBubbleDialog"), ("saved",)]  # (one call: back first, the change after)
    order.clear()
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None)
    d.destroy()  # (Cancel, Escape, the close button)
    assert order == [("closing", "EditBubbleDialog")]
    order.clear()
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None)
    d._handed = True  # (Previous, Next: the next editor takes the keys)
    d.destroy()
    assert order == []


def test_a_press_on_the_lettering_or_a_pane_never_activates_it_on_any_path():
    assert cs._proc(0, cs.WM_MOUSEACTIVATE, 0, 0) == cs.MA_NOACTIVATE  # (no Edit)
    cs._edit_hooks[123] = lambda message, wparam, lparam: None  # (Edit's hook with nothing to say of it)
    try:
        assert cs._proc(123, cs.WM_MOUSEACTIVATE, 0, 0) == cs.MA_NOACTIVATE
    finally:
        del cs._edit_hooks[123]
    assert cs.SeeThrough._edit_message(SimpleNamespace(_edit_takes=True), cs.WM_MOUSEACTIVATE, 0, 0) == \
        cs.MA_NOACTIVATE  # (Edit taking the mouse)
    assert cs._pane_proc(0, cs.WM_MOUSEACTIVATE, 0, 0) == cs.MA_NOACTIVATE


# ------------------------------------------------------------------ the runner's priority class
def test_a_class_above_normal_is_capped_at_normal():
    assert os_.capped(os_.ABOVE_NORMAL_PRIORITY_CLASS) == os_.NORMAL_PRIORITY_CLASS
    assert os_.capped(os_.HIGH_PRIORITY_CLASS) == os_.NORMAL_PRIORITY_CLASS
    for value in (os_.NORMAL_PRIORITY_CLASS, os_.BELOW_NORMAL_PRIORITY_CLASS, os_.IDLE_PRIORITY_CLASS):
        assert os_.capped(value) == value


@pytest.fixture
def processes(monkeypatch):
    """A server TASlation started (1, 10) and its runner (2, 20), their classes kept here, none changed for real."""
    classes = {(1, 10): os_.NORMAL_PRIORITY_CLASS, (2, 20): os_.ABOVE_NORMAL_PRIORITY_CLASS}
    monkeypatch.setattr(os_.sys, "platform", "win32")
    monkeypatch.setattr(os_, "own_server", lambda url: (1, 10) if url == "ours" else None)
    monkeypatch.setattr(os_, "descendants", lambda pid, started: [(2, 20)] if (pid, started) == (1, 10) else [])
    monkeypatch.setattr(os_, "priority_class", lambda pid, started: classes.get((pid, started)))

    def set_class(pid, started, value):
        classes[(pid, started)] = value
        return True

    monkeypatch.setattr(os_, "set_priority_class", set_class)
    monkeypatch.setattr(os_, "_yielded", {})
    return classes


def test_the_runner_goes_to_the_servers_class_never_above_normal(processes):
    assert os_.level_runners("ours") == 1 and processes[(2, 20)] == os_.NORMAL_PRIORITY_CLASS
    assert os_.level_runners("ours") == 0  # (at its class already)
    processes[(1, 10)], processes[(2, 20)] = os_.BELOW_NORMAL_PRIORITY_CLASS, os_.ABOVE_NORMAL_PRIORITY_CLASS
    assert os_.level_runners("ours") == 1 and processes[(2, 20)] == os_.BELOW_NORMAL_PRIORITY_CLASS  # (a runner's
    # class below normal: GitHub's runners run everything there)
    processes[(1, 10)], processes[(2, 20)] = os_.HIGH_PRIORITY_CLASS, os_.ABOVE_NORMAL_PRIORITY_CLASS
    assert os_.level_runners("ours") == 1 and processes[(2, 20)] == os_.NORMAL_PRIORITY_CLASS  # (never above normal)
    processes[(2, 20)] = os_.ABOVE_NORMAL_PRIORITY_CLASS
    assert os_.level_runners("the person's own") == 0 and processes[(2, 20)] == os_.ABOVE_NORMAL_PRIORITY_CLASS


def test_a_runner_loaded_while_the_server_yields_gets_its_lowered_class_and_unyield_caps_it(processes):
    os_._yielded[(1, 10)] = os_.NORMAL_PRIORITY_CLASS
    assert os_.level_runners("ours") == 1 and processes[(2, 20)] == os_.BELOW_NORMAL_PRIORITY_CLASS
    os_._yielded[(1, 10)] = os_.ABOVE_NORMAL_PRIORITY_CLASS  # (a server someone set above normal)
    os_.unyield_server()
    assert processes[(1, 10)] == os_.ABOVE_NORMAL_PRIORITY_CLASS and processes[(2, 20)] == os_.NORMAL_PRIORITY_CLASS


def test_the_runner_is_looked_at_as_a_computing_answer_begins_at_most_once_in_the_gap(monkeypatch):
    looked = []
    monkeypatch.setattr(os_.sys, "platform", "win32")
    monkeypatch.setattr(os_, "_level_soon", lambda url: looked.append(url))
    monkeypatch.setattr(os_, "_levelled_at", -1e9)
    os_.after_answer("ours", "/api/tags")  # (no computing: nothing loads)
    os_.after_answer("ours", "/api/chat")
    os_.after_answer("ours", "/api/generate")  # (within the gap)
    assert looked == ["ours"]
    os_._levelled_at -= os_.LEVEL_GAP_S + 0.1
    os_.after_answer("ours", "/api/generate")
    assert looked == ["ours", "ours"]


# ------------------------------------------------------------------ the stand-in browser
def test_the_stand_in_browser_is_started_minimised_and_not_activated():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import standin_viewer as sv
    finally:
        sys.path.remove(str(ROOT / "tools"))
    info = sv.quiet_start()
    if sys.platform != "win32":
        assert info is None
        return
    assert info.dwFlags & sv.STARTF_USESHOWWINDOW and info.wShowWindow == sv.SW_SHOWMINNOACTIVE == 7
    assert sv.SW_SHOWNOACTIVATE == 4  # (then shown without activation, `StandinBrowser.wait_window`)


def test_the_foreground_is_locked_while_the_stand_in_opens_and_lifted_on_every_way_out(monkeypatch):
    """(no real lock is set: the call is a fake's) Locked before the browser starts, lifted once its window is shown,
    when the wait ends without one, and at the close."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import standin_viewer as sv
    finally:
        sys.path.remove(str(ROOT / "tools"))
    calls: list[int] = []
    monkeypatch.setattr(sv.sys, "platform", "win32")
    monkeypatch.setattr(sv, "_user32", SimpleNamespace(LockSetForegroundWindow=lambda how: calls.append(how) or 1),
                        raising=False)
    assert sv.lock_foreground(True) and sv.lock_foreground(False)
    assert calls == [sv.LSFW_LOCK, sv.LSFW_UNLOCK] == [1, 2]

    browser = object.__new__(sv.StandinBrowser)
    browser._locked = True
    browser.proc = SimpleNamespace(poll=lambda: 1)  # (the browser ended at once: the wait raises)
    calls.clear()
    with pytest.raises(RuntimeError):
        browser.wait_window(1.0)
    assert calls == [sv.LSFW_UNLOCK] and not browser._locked
    browser._unlock()  # (lifted once only)
    assert calls == [sv.LSFW_UNLOCK]
