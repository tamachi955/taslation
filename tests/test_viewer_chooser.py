"""The viewer chooser (`ui.see_menu.ViewerDialog`): at every start, once the legal notice is over, at once (the
models load behind it), TASlation asks which window is the viewer and chooses none by itself. A drop-down of the
windows named as their taskbar buttons, the remembered viewer first and preselected (Enter or OK), nothing
preselected and OK greyed when none looks like a viewer, List again, Quit (Close while a viewer is followed); again
after the viewer was closed, saying so, the new window only preselected; none for a viewer named with --window; the
right pane's foot names the viewer followed ("Viewer: <title>", a long title shortened in the middle). Fake windows
(invented titles) and a withdrawn Tk root only: nothing is shown, no window of the computer's is touched."""

import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from taslation import capture, viewerparts
from taslation.capture import WindowInfo
from taslation.ui import constants, layout
from taslation.ui import see_menu as sm
from taslation.ui import seethrough as ui

CHROME = "Chrome_WidgetWin_1"
NOTEPAD = WindowInfo(hwnd=11, title="notes.txt - Notepad", class_name="Notepad", pid=11, rect=(0, 0, 900, 700))
CHAT = WindowInfo(hwnd=12, title="Yomizuq画面翻訳アプリ - Chat - Google Chrome", class_name=CHROME, pid=12,
                  rect=(0, 0, 1600, 1000))
READER = WindowInfo(hwnd=13, title="見本の物語 1 - Yomizuq - 個人 - Microsoft Edge", class_name=CHROME, pid=13,
                    rect=(100, 50, 1300, 950))


class FakeApp(tk.Toplevel):
    """The window as the chooser sees it: withdrawn, so that nothing of it shows; its list of windows is *screen*."""

    def __init__(self, master, screen):
        super().__init__(master)
        self.withdraw()
        self.screen = screen
        self.windows = list(screen)
        self.selected = None
        self.window_query = ""
        self._viewer_closed = None
        self.window_box = ttk.Combobox(self, values=[w.label() for w in self.windows])
        self.picked, self.closed = [], 0
        self._see_hidden, self._see_through = True, None
        sm.init(self)

    def _rescan_windows(self):
        if [w.hwnd for w in self.screen] != [w.hwnd for w in self.windows]:
            self.windows = list(self.screen)
            self.window_box.configure(values=[w.label() for w in self.windows])

    def refresh_windows(self, select=None):
        self._rescan_windows()

    def _on_window_selected(self, picked=False, named=False):
        self.picked.append((self.windows[self.window_box.current()], picked))
        self.selected = self.windows[self.window_box.current()]

    def _on_close(self):
        self.closed += 1


@pytest.fixture
def keys(monkeypatch):
    given = []
    monkeypatch.setattr(layout, "dialog_keys", lambda win, parent, focus=None: given.append(win))
    return given


def _remember(win):
    viewerparts.chosen(win)  # (as an earlier start's choice: viewers.json in the test's scratch state)


def _texts(dialog):
    """The dialog's lines, each as one line (they are broken to the dialog's width)."""
    return [" ".join(str(w.cget("text")).split()) for w in dialog.frame.winfo_children() if isinstance(w, ttk.Label)]


def test_the_remembered_viewer_comes_first_preselected_named_as_its_taskbar_button(hidden_root, keys):
    _remember(READER)
    app = FakeApp(hidden_root, [CHAT, NOTEPAD, READER])
    dialog = sm.open_viewer(app)
    assert list(dialog.box.cget("values")) == ["見本の物語 1 - Yomizuq - Microsoft Edge", CHAT.title, NOTEPAD.title]
    assert dialog.box.current() == 0 and dialog.ok_button.instate(["!disabled"])
    assert dialog.last_button.cget("text") == "Quit" and dialog.again_button.cget("text") == "List again"
    assert not app.picked and app.selected is None  # (nothing chosen before OK)
    dialog.ok()
    assert app.picked == [(READER, True)] and app._see_chooser is None and not dialog.winfo_exists()


def test_with_nothing_that_looks_like_a_viewer_nothing_is_preselected_and_ok_waits(hidden_root, keys):
    app = FakeApp(hidden_root, [CHAT, NOTEPAD])
    dialog = sm.open_viewer(app)
    assert dialog.box.current() == -1 and dialog.box.get() == "" and dialog.ok_button.instate(["disabled"])
    dialog.box.current(1)
    dialog._picked()  # (the person's pick in the list: <<ComboboxSelected>>)
    assert dialog.ok_button.instate(["!disabled"]) and dialog.pick == NOTEPAD.hwnd
    dialog.ok()
    assert app.picked == [(NOTEPAD, True)]


def test_list_again_lists_the_windows_anew_and_keeps_the_persons_pick(hidden_root, keys):
    _remember(READER)
    screen = [CHAT, NOTEPAD]
    app = FakeApp(hidden_root, screen)
    dialog = sm.open_viewer(app)
    screen.append(READER)  # the viewer opened while the dialog is up
    dialog._watch()  # (every WINDOW_WATCH_MS by itself)
    assert dialog.windows[0] == READER and dialog.box.current() == 0  # nothing picked: preselected
    dialog.box.current(2)
    dialog._picked()
    screen.remove(CHAT)
    dialog.again_button.invoke()  # List again
    assert dialog.windows == [READER, NOTEPAD] and dialog.box.current() == 1  # the pick kept
    screen.remove(NOTEPAD)
    dialog.relist()
    assert dialog.box.current() == 0 and dialog.pick is None  # (the pick gone: the preselection again)
    dialog.destroy()


def test_quit_ends_taslation_while_no_viewer_is_followed_and_close_leaves_the_viewer(hidden_root, keys):
    app = FakeApp(hidden_root, [CHAT, NOTEPAD])
    dialog = sm.open_viewer(app)
    dialog.close()  # Quit (Escape and the dialog's own close do the same)
    assert app.closed == 1 and not dialog.winfo_exists() and app._see_chooser is None
    app.selected = NOTEPAD  # (Menu > Viewer... while a viewer is followed)
    dialog = sm.open_viewer(app)
    assert dialog.last_button.cget("text") == "Close" and dialog.box.current() == 1  # the viewer followed
    dialog.close()
    assert app.closed == 1 and app.selected is NOTEPAD and not app.picked


def test_the_chooser_comes_at_once_alone_and_stays_until_a_choice(hidden_root, keys, monkeypatch):
    """At the window's first tick, the models loading behind it (nothing waits for the start's judgement of the GPU,
    whose dialog waits for it instead: `chooser_due`); never while a dialog holds the window."""
    from taslation.ui.dialogs import help as help_dialogs

    app = FakeApp(hidden_root, [CHAT, NOTEPAD])
    monkeypatch.setattr(help_dialogs, "modal_up", lambda window: True)  # a dialog holds the window
    sm.chooser_tick(app)
    assert app._see_chooser is None
    monkeypatch.setattr(help_dialogs, "modal_up", lambda window: False)
    sm.chooser_tick(app)
    dialog = app._see_chooser
    assert dialog is not None and dialog.by_itself and dialog.attributes("-topmost")
    assert keys == []  # (at the start it takes the keys as it shows, as the legal notice does)
    assert constants.VIEWER_CLOSED not in _texts(dialog)
    sm.chooser_tick(app)
    assert app._see_chooser is dialog  # (one; it stays: nothing chooses a viewer but the person)
    dialog.destroy()
    assert not sm.chooser_due(app)  # (no see-through mode in this stand-in: no chooser)
    monkeypatch.setattr(ui, "on", lambda window: True)  # (see-through mode, TASlation's own window hidden)
    assert sm.chooser_due(app)  # (no viewer followed: the GPU's dialog of the start waits for it)
    app.selected = NOTEPAD  # (chosen in it)
    assert not sm.chooser_due(app)  # (the viewer chosen: the GPU's dialog may come)
    app.selected, app.window_query = None, "Yomizuq"
    assert not sm.chooser_due(app)  # (a viewer named with --window: no chooser to wait for)
    app.window_query, app._see_hidden = "", False
    assert not sm.chooser_due(app)  # (no hidden window: no chooser)


def test_the_viewer_closed_brings_the_chooser_again_saying_so_the_new_window_only_preselected(hidden_root, keys):
    _remember(READER)
    reopened = WindowInfo(hwnd=21, title=READER.title, class_name=CHROME, pid=21, rect=READER.rect)
    app = FakeApp(hidden_root, [NOTEPAD, reopened])
    app._viewer_closed = READER  # (`ViewerMixin._viewer_gone`)
    sm.chooser_tick(app)
    dialog = app._see_chooser
    assert dialog.by_itself and keys == [dialog]  # (the keys only while TASlation's window has them)
    assert constants.VIEWER_CLOSED in _texts(dialog)
    assert dialog.windows[dialog.box.current()] == reopened and app.selected is None and not app.picked
    dialog.destroy()


def test_no_chooser_for_a_viewer_named_with_window(hidden_root, keys):
    app = FakeApp(hidden_root, [CHAT])
    app.window_query = "Yomizuq"  # (gui --window; the tools' window_query=browser.token)
    sm.chooser_tick(app)
    assert app._see_chooser is None


def test_the_chooser_goes_over_the_window_preselected_or_the_primary_monitor(hidden_root, keys, monkeypatch):
    _remember(READER)
    monkeypatch.setattr(layout, "monitor_at", lambda x, y: (0, 0, 1920, 1080) if 0 <= x < 1920 else None)
    monkeypatch.setattr(capture, "window_exists", lambda hwnd: False)  # (made-up handles: no window's place read)
    app = FakeApp(hidden_root, [NOTEPAD, READER])
    dialog = sm.open_viewer(app)
    assert dialog._over_preselected() == (700, 500)
    dialog.box.set("")
    assert dialog._over_preselected() is None  # (nothing preselected: the primary monitor's middle)
    dialog.destroy()
    gone = WindowInfo(hwnd=22, title=READER.title, class_name=CHROME, pid=22, rect=(-32000, -32000, -31840, -31972))
    app = FakeApp(hidden_root, [gone])  # (minimised: on no monitor)
    dialog = sm.open_viewer(app)
    assert dialog.box.current() == 0 and dialog._over_preselected() is None
    dialog.destroy()


def test_the_chooser_goes_where_the_window_is_now_not_where_it_was_listed(hidden_root, keys, monkeypatch):
    """(the list keeps a window's place from when it was first listed while its windows and titles stay the same:
    a viewer moved to another monitor since has the chooser over it there)"""
    _remember(READER)
    monitors = {0: (0, 0, 1920, 1080), 1: (1920, 0, 3840, 1080)}
    monkeypatch.setattr(layout, "monitor_at", lambda x, y: monitors.get(x // 1920) if 0 <= x < 3840 else None)
    place = {"rect": (2020, 50, 3220, 950), "monitor": monitors[1]}  # (moved to the second)
    monkeypatch.setattr(capture, "window_exists", lambda hwnd: hwnd == READER.hwnd)
    monkeypatch.setattr(capture, "window_rect", lambda hwnd: place["rect"])
    monkeypatch.setattr(layout, "monitor_rect", lambda hwnd: place["monitor"])
    app = FakeApp(hidden_root, [NOTEPAD, READER])
    dialog = sm.open_viewer(app)
    assert dialog._over_preselected() == (2620, 500)
    place.update(rect=(1020, 50, 2820, 950), monitor=monitors[0])  # (straddling, as much on each: Windows' choice)
    assert dialog._over_preselected() == (1470, 500)  # (on that monitor, as the other dialogs: not on the edge)
    dialog.destroy()


def test_a_long_title_is_shortened_in_the_middle_to_the_lists_width(hidden_root, keys):
    long = WindowInfo(hwnd=23, title="見本の物語 " + "とても長い副題 " * 12 + "- Yomizuq - Google Chrome",
                      class_name=CHROME, pid=23, rect=(0, 0, 800, 600))
    app = FakeApp(hidden_root, [long])
    dialog = sm.open_viewer(app)
    shown = dialog.box.cget("values")[0]
    measure, room = dialog._width_px()
    assert "…" in shown and shown.startswith("見本の物語") and shown.endswith("Google Chrome") and measure(shown) <= room
    dialog.destroy()


def test_the_right_pane_s_foot_names_the_viewer_followed_a_long_title_shortened_in_the_middle():
    from taslation import panes as pn
    from taslation.capture import taskbar_title

    short = WindowInfo(hwnd=24, title="見本 - Google Chrome", class_name=CHROME, pid=24, rect=(0, 0, 800, 600))
    app = SimpleNamespace(status_var=SimpleNamespace(get=lambda: ""), selected=short)
    changing, foot = ui.right_rows(app)
    named = f"Viewer: {taskbar_title(short)}"
    assert changing == [] and named in [row.text for row in foot] and "…" not in named
    app.status_var = SimpleNamespace(get=lambda: named)  # (the status line says it: once)
    assert ui.right_rows(app)[0] == []
    app.selected = WindowInfo(hwnd=23, title="見本の物語 " + "とても長い副題 " * 12 + "- Yomizuq - Google Chrome",
                              class_name=CHROME, pid=23, rect=(0, 0, 800, 600))
    (row,) = [r for r in ui.right_rows(app)[1] if r.text.startswith("Viewer: ")]
    assert "…" in row.text and row.text.startswith("Viewer: 見本の物語") and row.text.endswith("Chrome")
    assert row.lines == 1 and pn.fits_line("en", 96)(row.text)
    app.selected = None
    assert ui.NO_VIEWER in [r.text for r in ui.right_rows(app)[1]]
