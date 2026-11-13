"""Over the book: TASlation's window over a full-screen viewer never takes the foreground (WS_EX_NOACTIVATE, topmost
with SWP_NOACTIVATE), holds its own keys as hot keys only while that is on, and is a normal window while a dialog or a
box of it takes typing. The Windows calls are stand-ins here (the real ones are measured with a throwaway browser:
docs/research/2026-11-model-knockout.md); `HotKeys` itself is tried for real with a key nobody has."""

from __future__ import annotations

import inspect
import tkinter as tk
from types import SimpleNamespace

import pytest

from taslation.capture import overlay
from taslation.ui import layout, overbook
from taslation.ui.overbook import OverBookMixin, over_due, wanted_hotkeys

from conftest import windows_only


# ------------------------------------------------------------------ the style bits and the order of the windows
def test_the_style_gets_no_activate_and_keeps_the_rest():
    layered_app = 0x00080100  # WS_EX_LAYERED (Tk's alpha) | WS_EX_WINDOWEDGE
    on = overlay.over_style(layered_app, True)
    assert on == layered_app | overlay.WS_EX_NOACTIVATE == layered_app | 0x08000000
    assert overlay.over_style(on, True) == on  # twice is once
    assert overlay.over_style(on, False) == layered_app
    assert overlay.over_style(layered_app | overlay.WS_EX_TOPMOST, False) & overlay.WS_EX_TOPMOST  # SetWindowPos's


def test_the_order_changes_without_activation_move_or_size():
    flags = overlay.OVER_FLAGS
    assert flags & overlay.SWP_NOACTIVATE and flags & overlay.SWP_NOMOVE and flags & overlay.SWP_NOSIZE
    assert flags == 0x0013  # nothing else: no SWP_SHOWWINDOW, no SWP_FRAMECHANGED
    assert overlay.over_order(True, False) == overlay.HWND_TOPMOST
    assert overlay.over_order(False, True) == overlay.HWND_TOPMOST  # Always on top, or reading mode
    assert overlay.over_order(False, False) == overlay.HWND_NOTOPMOST


class FakeUser32:
    def __init__(self, style=0x00080100):
        self.style = style
        self.calls = []

    def IsWindow(self, hwnd):
        return True

    def GetWindowLongW(self, hwnd, index):
        assert index == overlay.GWL_EXSTYLE
        return self.style

    def SetWindowLongW(self, hwnd, index, value):
        self.calls.append(("style", hwnd, value))
        before, self.style = self.style, value
        return before

    def SetWindowPos(self, hwnd, after, x, y, cx, cy, flags):
        self.calls.append(("pos", hwnd, after, flags))
        return True


@pytest.fixture
def fake_user32(monkeypatch):
    fake = FakeUser32()
    monkeypatch.setattr(overlay, "IS_WINDOWS", True)
    monkeypatch.setattr(overlay, "user32", fake, raising=False)
    return fake


def test_set_over_puts_the_style_on_and_the_window_topmost_with_no_activate(fake_user32):
    assert overlay.set_over(7, True)
    assert fake_user32.calls == [("style", 7, 0x00080100 | 0x08000000),
                                 ("pos", 7, overlay.HWND_TOPMOST, overlay.OVER_FLAGS)]
    assert overlay.has_over(7)
    fake_user32.calls.clear()
    assert overlay.set_over(7, True)  # the style is there: only the order again
    assert fake_user32.calls == [("pos", 7, overlay.HWND_TOPMOST, overlay.OVER_FLAGS)]


def test_set_over_off_takes_the_style_away_and_keeps_always_on_top(fake_user32):
    overlay.set_over(7, True)
    fake_user32.calls.clear()
    assert overlay.set_over(7, False)
    assert fake_user32.calls == [("style", 7, 0x00080100), ("pos", 7, overlay.HWND_NOTOPMOST, overlay.OVER_FLAGS)]
    fake_user32.calls.clear()
    overlay.set_over(7, False, topmost=True)
    assert fake_user32.calls == [("pos", 7, overlay.HWND_TOPMOST, overlay.OVER_FLAGS)]
    assert all(call[-1] & overlay.SWP_NOACTIVATE for call in fake_user32.calls if call[0] == "pos")


# ------------------------------------------------------------------ when it is on, and which keys it holds
def test_over_due():
    base = dict(enabled=True, viewer_fills=True, same_monitor=True, held=False)
    assert over_due(**base)
    assert not over_due(**{**base, "enabled": False})  # View > Over the full-screen viewer off
    assert not over_due(**{**base, "viewer_fills": False})  # a viewer in a window of its size: nothing over it
    assert not over_due(**{**base, "same_monitor": False})  # the book on another monitor
    assert not over_due(**{**base, "held": True})  # a dialog, a box typed in, the Translator's page


def test_the_hot_keys_wanted():
    assert wanted_hotkeys(False, False, "viewer") == frozenset()
    assert wanted_hotkeys(True, False, "viewer") == {"F5"}  # F11 and Esc stay the viewer's (its full screen)
    assert wanted_hotkeys(True, True, "viewer") == {"F5", "F11", "Escape"}
    assert wanted_hotkeys(True, False, "own") == {"F5"}
    assert wanted_hotkeys(True, True, "other") == frozenset()  # a third program in front keeps its keys
    # no page of a whole-book run is shown from the strip (reading is on the viewer): Esc has nothing to go back from
    assert list(inspect.signature(wanted_hotkeys).parameters) == ["on", "reading", "owner"]
    page_keys = {"Left", "Right", "Up", "Down", "Prior", "Next", "Home", "End", "space"}
    assert not page_keys & set(overbook.OVER_HOTKEYS)  # the page keys are never registered


# ------------------------------------------------------------------ the window's side, with stand-ins
class FakeHotKeys:
    started = 0

    def __init__(self):
        FakeHotKeys.started += 1
        self.keys: set[str] = set()
        self.pressed: list[str] = []
        self.log: list[tuple[str, str]] = []
        self.closed = False

    @classmethod
    def start(cls):
        cls.last = cls()
        return cls.last

    @property
    def registered(self):
        return frozenset(self.keys)

    def register(self, name, vk):
        assert vk == overbook.OVER_HOTKEYS[name]
        self.keys.add(name)
        self.log.append(("+", name))
        return True

    def unregister(self, name):
        self.keys.discard(name)
        self.log.append(("-", name))

    def clear(self):
        for name in list(self.keys):
            self.unregister(name)

    def take(self):
        pressed, self.pressed = self.pressed, []
        return [name for name in pressed if name in self.keys]

    def close(self):
        self.clear()
        self.closed = True


class Box:
    """A box of the main window to type in, as a click and the focus see it."""

    def __init__(self, window, cls="TEntry", state="normal"):
        self.window, self.cls, self.state = window, cls, state
        self.focused = False

    def winfo_toplevel(self):
        return self.window

    def winfo_class(self):
        return self.cls

    def cget(self, option):
        assert option == "state"
        return self.state

    def focus_set(self):
        self.focused = True
        self.window.focus = self


class Dialog:
    """A dialog of the window on the screen: what is done to it."""

    def __init__(self, hwnd):
        self.hwnd, self.topmost = hwnd, False

    def attributes(self, name, value):
        assert name == "-topmost"
        self.topmost = value

    def wm_frame(self):
        return hex(self.hwnd)


class Button:
    """The status bar's button that moves TASlation to the book's monitor: whether it is on show."""

    def __init__(self):
        self.packed = False

    def pack(self, **_kw):
        self.packed = True

    def pack_forget(self):
        self.packed = False

    def winfo_manager(self):
        return "pack" if self.packed else ""


class Window(OverBookMixin):
    """The parts of the App the mode uses."""

    def __init__(self, root, tmp_path):
        self._root_tk = root
        self.canvas = Box(self, "Canvas")
        self.tk = root.tk
        self.settings = SimpleNamespace(state_dir=tmp_path, over_book=True)
        self.selected = SimpleNamespace(hwnd=500)
        self.reading = False
        self.role_var = tk.StringVar(root, value="reader")
        self.top_var = tk.BooleanVar(root, value=False)
        self.own = 100
        self.dialogs = False
        self.dialog_windows: list = []  # the dialogs on the screen, as `_over_dialog_windows` gives them
        self.move_btn, self.status_label = Button(), object()
        self.zoomed, self.geometries, self.idle = False, [], []
        self.focus = None
        self.done: list[str] = []
        self.said: list[str] = []
        self._init_over()

    def _root(self):
        return self._root_tk

    def _own_hwnd(self):
        return self.own

    def _over_dialogs(self):
        return self.dialogs

    def _over_dialog_windows(self):
        return list(self.dialog_windows)

    def focus_get(self):
        return self.focus

    def say(self, key, **_values):
        self.said.append(key)

    def translate_now(self):
        self.done.append("translate")

    def state(self, value=None):
        if value is None:
            return "zoomed" if self.zoomed else "normal"
        self.zoomed = value == "zoomed"

    def update_idletasks(self):
        pass

    def winfo_width(self):
        return 960

    def winfo_height(self):
        return 900

    def geometry(self, text):
        self.geometries.append((text, self.zoomed))

    def after_idle(self, func):
        self.idle.append(func)

    def toggle_reading(self):
        self.done.append("reading")
        self.reading = not self.reading

    def _on_escape(self):
        self.done.append("escape")


@pytest.fixture
def screen(monkeypatch):
    """What Windows says, as the test sets it: the viewer fills its monitor, the window is on it, who is in front,
    and what was done to the windows."""
    state = SimpleNamespace(fills=True, own_monitor=(0, 0, 1920, 1080), viewer_monitor=(0, 0, 1920, 1080),
                            front="viewer", styled=set(), calls=[], given=[])

    def set_over(hwnd, on, topmost=False):
        state.calls.append((hwnd, on, topmost))
        (state.styled.add if on else state.styled.discard)(hwnd)
        return True

    def give(hwnd):
        state.given.append(hwnd)
        state.front = "viewer" if hwnd == 500 else "own"
        return True

    monkeypatch.setattr(overbook, "IS_WINDOWS", False)  # (no bindings and no timer on the stand-in)
    monkeypatch.setattr(overbook, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(overbook, "is_fullscreen", lambda hwnd: state.fills)
    monkeypatch.setattr(overbook, "monitor_rect", lambda hwnd: state.own_monitor if hwnd < 500 else state.viewer_monitor)
    monkeypatch.setattr(overbook, "foreground_window", lambda: 1)
    monkeypatch.setattr(overbook, "foreground_owner", lambda front, viewer: state.front)
    monkeypatch.setattr(overbook, "set_over", set_over)
    monkeypatch.setattr(overbook, "has_over", lambda hwnd: hwnd in state.styled)
    monkeypatch.setattr(overbook, "give_foreground", give)
    monkeypatch.setattr(overbook, "HotKeys", FakeHotKeys)
    return state


@pytest.fixture
def window(hidden_root, tmp_path, screen, monkeypatch):
    w = Window(hidden_root, tmp_path)
    monkeypatch.setattr(overbook, "IS_WINDOWS", True)
    return w


def test_over_a_full_screen_viewer_the_window_is_styled_and_holds_f5_only(window, screen):
    window._over_sync()
    assert window._over_on and screen.calls == [(100, True, False)]
    assert FakeHotKeys.last.registered == {"F5"}
    assert screen.given == []  # the viewer had the foreground already: nothing moves
    assert window.said  # said once what the mode does
    window._over_sync()
    assert len(screen.calls) == 1 and len(window.said) == 1  # nothing again while nothing changed


def test_entering_while_taslation_has_the_foreground_gives_it_to_the_viewer_once(window, screen):
    screen.front = "own"
    window._over_sync()
    assert screen.given == [500]
    window._over_sync()
    assert screen.given == [500]


def test_no_mode_for_a_viewer_in_a_window_or_on_another_monitor_or_when_turned_off(window, screen):
    screen.fills = False
    window._over_sync()
    assert not window._over_on and screen.calls == []
    screen.fills = True
    screen.viewer_monitor = (1920, 0, 3840, 1080)  # the book on the second monitor: nothing over it
    window._over_sync()
    assert not window._over_on
    screen.viewer_monitor = screen.own_monitor
    window.over_var.set(False)
    window.toggle_over()
    assert not window._over_on
    from taslation.i18n import load_ui_flag

    assert load_ui_flag(window.settings.state_dir, overbook.OVER_OFF_FLAG)  # kept for the next start
    window.over_var.set(True)
    window.toggle_over()
    assert window._over_on and not load_ui_flag(window.settings.state_dir, overbook.OVER_OFF_FLAG)


def test_the_hot_keys_follow_the_mode_reading_mode_and_who_is_in_front(window, screen):
    window._over_sync()
    keys = FakeHotKeys.last
    window.reading = True
    window._over_sync()
    assert keys.registered == {"F5", "F11", "Escape"}
    screen.front = "other"  # another program in front: its keys are its own
    window._over_sync()
    assert keys.registered == frozenset() and window._over_on
    screen.front = "viewer"
    window.reading = False
    window._over_sync()
    assert keys.registered == {"F5"}
    screen.fills = False  # the viewer left its full screen: the mode ends, the keys go back
    window._over_sync()
    assert not window._over_on and keys.registered == frozenset()
    assert screen.calls[-1] == (100, False, False)
    window._over_close()
    assert keys.closed and window._over_hotkeys is None


def test_a_hot_key_does_what_the_key_does_in_the_window(window, screen):
    window._over_sync()
    FakeHotKeys.last.pressed = ["F5"]
    window._over_sync()
    assert window.done == ["translate"]
    window.reading = True
    window._over_sync()
    FakeHotKeys.last.pressed = ["Escape", "F11"]
    window._over_sync()
    assert window.done == ["translate", "escape", "reading"]


def test_a_dialog_leaves_the_mode_and_its_closing_brings_it_back(window, screen):
    window._over_sync()
    window.dialogs = True  # book settings, the series sheet, the editor ...: they take typing
    dialog = Dialog(200)
    window.dialog_windows = [dialog]
    window._over_sync()
    assert not window._over_on and FakeHotKeys.last.registered == frozenset()
    assert screen.calls[-1] == (100, False, True)  # a normal window, but still above the full-screen viewer ...
    assert dialog.topmost and screen.given == [200]  # ... and the dialog above it, in front: it takes typing
    window._over_sync()
    assert screen.given == [200]  # once
    window.dialogs, window.dialog_windows = False, []
    screen.front = "own"  # Windows gave the foreground back to the window the dialog was over
    window._over_sync()
    assert window._over_on and screen.given == [200, 500]  # the reader's next key goes to the book


def test_after_a_dialog_the_viewer_gets_the_foreground_when_nobody_has_it_but_never_from_another_program(
        window, screen, monkeypatch):
    window._over_sync()
    window.dialogs, window.dialog_windows = True, [Dialog(200)]  # the question at closing, say: kept open
    window._over_sync()
    window.dialogs, window.dialog_windows = False, []
    monkeypatch.setattr(overbook, "foreground_window", lambda: 0)  # for a moment nobody is in front
    screen.front = "other"
    window._over_sync()
    assert window._over_on and screen.given == [200, 500]
    window.dialogs, window.dialog_windows = True, [Dialog(201)]
    window._over_sync()
    window.dialogs, window.dialog_windows = False, []
    monkeypatch.setattr(overbook, "foreground_window", lambda: 1)
    screen.front = "other"  # the reader went to another program meanwhile
    window._over_sync()
    assert window._over_on and screen.given == [200, 500, 201]


def test_dialogs_over_the_viewer_come_in_front_one_after_another_and_the_modal_one_last(window, screen):
    window._over_sync()
    first, second = Dialog(201), Dialog(202)
    window.dialogs, window.dialog_windows = True, [first]
    window._over_sync()
    window.dialog_windows = [first, second]  # (`_over_dialog_windows` puts the one holding the input last)
    window._over_sync()
    assert first.topmost and second.topmost and screen.given == [201, 202]


def test_a_dialog_with_the_viewer_in_a_window_or_on_another_monitor_is_left_as_ever(window, screen):
    screen.viewer_monitor = (1920, 0, 3840, 1080)
    window.dialogs, window.dialog_windows = True, [Dialog(200)]
    window._over_sync()
    assert not window.dialog_windows[0].topmost and screen.given == [] and screen.calls == []
    screen.viewer_monitor, screen.fills = screen.own_monitor, False
    window._over_sync()
    assert not window.dialog_windows[0].topmost and screen.given == []


def test_reading_mode_keeps_the_window_topmost_when_a_dialog_holds_the_mode(window, screen):
    window.reading = True
    window._over_sync()
    window.dialogs = True
    window._over_sync()
    assert screen.calls[-1] == (100, False, True)


def test_a_box_clicked_to_type_in_takes_the_keys_until_the_reader_goes_back(window, screen):
    window._over_sync()
    box = Box(window)
    window._over_type_click(SimpleNamespace(widget=box))
    assert not window._over_on and window._over_typing and box.focused
    assert screen.given == [100] and screen.front == "own"  # TASlation has the keys for the box
    window._over_sync()
    assert not window._over_on  # still typing
    screen.front = "viewer"  # the reader clicked the book
    window._over_sync()
    assert window._over_on and not window._over_typing


def test_a_list_to_pick_from_or_a_box_of_a_dialog_does_not_hold_the_mode(window, screen):
    window._over_sync()
    window._over_type_click(SimpleNamespace(widget=Box(window, "TCombobox", "readonly")))  # the Viewer list
    assert window._over_on
    window._over_type_click(SimpleNamespace(widget=Box(object(), "TEntry")))  # a dialog's box (its own window)
    assert window._over_on


def test_tk_making_its_window_anew_gets_the_style_and_gives_the_foreground_back(window, screen):
    window._over_sync()
    window.own = 101  # Tk's full screen made a new top-level window, without the style, and activated it
    screen.front = "own"
    window._over_sync()
    assert screen.calls[-1] == (101, True, False) and screen.given == [500]


def test_the_translators_page_takes_the_keys_when_pressed_the_readers_does_not(window, screen):
    window._over_sync()
    window._over_page_press()  # Reader: the press goes on to the viewer, the keys stay there
    assert window._over_on and screen.given == []
    window.role_var.set("translator")
    window._over_sync()
    assert window._over_on  # over the book in this role too, until the page is pressed
    window._over_page_press()
    assert not window._over_on and window.canvas.focused and screen.given == [100]
    window._over_sync()
    assert not window._over_on  # Enter, Delete, Ctrl+Z go to the page's boxes
    screen.front = "viewer"
    window._over_sync()
    assert window._over_on


# ------------------------------------------------------------------ the book full screen on another monitor
def test_a_book_full_screen_on_another_monitor_is_offered_a_move_and_no_key_is_taken(window, screen):
    screen.viewer_monitor = (1920, 0, 3840, 1080)
    window._over_sync()
    assert not window._over_on and window._over_hotkeys is None  # F5 and F11 stay the viewer's
    assert window.move_btn.packed and window.said == [overbook.MOVE_OFFER]  # said once for this viewer ...
    window.reading = True
    window._over_sync()
    assert not window.move_btn.packed  # (reading mode: no offer, and no key either)
    window.reading = False
    window._over_sync()
    assert window.move_btn.packed and window.said == [overbook.MOVE_OFFER]  # ... not again
    assert window._over_hotkeys is None
    window.over_var.set(False)  # View > Over the full-screen viewer off: no offer either
    window._over_sync()
    assert not window.move_btn.packed
    window.over_var.set(True)
    screen.fills = False  # the viewer in a window: nothing to be over
    window._over_sync()
    assert not window.move_btn.packed
    screen.fills = True
    window.selected = SimpleNamespace(hwnd=501)  # another viewer: said for it too
    window._over_sync()
    assert window.said == [overbook.MOVE_OFFER, overbook.MOVE_OFFER] and window._over_hotkeys is None


def test_the_hot_keys_go_when_the_window_leaves_the_books_monitor(window, screen):
    window._over_sync()
    keys = FakeHotKeys.last
    assert keys.registered == {"F5"}
    screen.own_monitor = (1920, 0, 3840, 1080)  # the reader dragged TASlation to the other monitor
    window._over_sync()
    assert not window._over_on and keys.registered == frozenset() and window.move_btn.packed


def test_the_move_puts_the_window_in_the_middle_of_the_books_monitor_and_the_mode_comes(window, screen, monkeypatch):
    screen.viewer_monitor = (1920, 0, 3840, 1080)
    asked = []
    monkeypatch.setattr(overbook, "initial_geometry",
                        lambda widget, size, at=None: asked.append((size, at)) or "960x900+2400+60")
    window.zoomed = True
    window.move_to_book()
    assert asked == [((960, 900), (2880, 540))]  # its size kept, on the monitor the book fills
    assert window.geometries == [("960x900+2400+60", False)] and window.zoomed  # maximised there again
    screen.own_monitor = screen.viewer_monitor  # Windows moved it
    for func in window.idle:
        func()
    assert window._over_on and FakeHotKeys.last.registered == {"F5"} and not window.move_btn.packed


# ------------------------------------------------------------------ where the reader put the window
MONITORS = [(0, 0, 1920, 1080), (1920, 0, 3840, 1080)]


@pytest.fixture
def monitors(monkeypatch):
    """The monitors Windows has, as the test sets them (`layout.monitor_at`)."""
    shown = list(MONITORS)

    def at(x, y):
        return next((m for m in shown if m[0] <= x < m[2] and m[1] <= y < m[3]), None)

    monkeypatch.setattr(layout, "monitor_at", at)
    return shown


class Placed(Window):
    """The window with its size and place, as `ReadingMixin` gives them."""

    def __init__(self, root, tmp_path):
        super().__init__(root, tmp_path)
        self.normal, self.maximised = "1180x920+362+26", False
        self._reading_saved = (("", False), True, 1.0)

    def _current_geometry(self):
        return self.normal, self.maximised


def test_a_place_is_used_again_only_on_the_monitor_it_was_kept_with(monitors):
    assert layout.kept_place("1180x920+2282+26", MONITORS[1])
    assert layout.kept_place("1180x920+-1900+26", (-1920, 0, 0, 1080)) is False  # no such monitor now
    monitors.append((-1920, 0, 0, 1080))
    assert layout.kept_place("1180x920+-1900+26", (-1920, 0, 0, 1080))
    assert not layout.kept_place("1180x920+2282+26", (1920, 0, 4480, 1440))  # that monitor changed since
    assert not layout.kept_place("1180x920+100+26", MONITORS[1])  # the title bar is not on it
    assert not layout.kept_place("", MONITORS[1]) and not layout.kept_place("1180x920+2282+26", "nonsense")


def test_once_over_the_book_its_place_is_kept_and_the_next_start_opens_there(hidden_root, tmp_path, screen, monitors,
                                                                             monkeypatch):
    def start():
        monkeypatch.setattr(overbook, "IS_WINDOWS", False)  # (no bindings and no timer on the stand-in)
        window = Placed(hidden_root, tmp_path)
        monkeypatch.setattr(overbook, "IS_WINDOWS", True)
        return window

    w = start()
    screen.viewer_monitor = MONITORS[1]
    w._over_sync()  # the book full screen on the other monitor: offered, nothing kept
    assert w.move_btn.packed and overbook.opening_place(tmp_path) is None
    w._over_close()  # (closed before it ever was over the book: still nothing)
    assert overbook.opening_place(tmp_path) is None

    w = start()
    w.normal = "1180x920+2282+26"  # moved there (the button, or by hand)
    screen.own_monitor = MONITORS[1]
    w._over_sync()
    assert w._over_on and overbook.opening_place(tmp_path) == ("1180x920+2282+26", False)
    w.normal, w.maximised = "1000x800+2300+60", True  # moved and maximised over the book later
    w._over_close()
    assert overbook.opening_place(tmp_path) == ("1000x800+2300+60", True)

    w = start()  # the next start: no move needed, so no offer; F5 is TASlation's at once
    w._over_sync()
    assert w._over_on and not w.move_btn.packed and FakeHotKeys.last.registered == {"F5"}
    w.normal, w.maximised = "1180x920+362+26", False  # the reader took it back to the first monitor on purpose
    screen.own_monitor = MONITORS[0]
    w._over_sync()
    w._over_close()
    assert overbook.opening_place(tmp_path) == ("1180x920+362+26", False)  # kept where they left it

    monitors.remove(MONITORS[0])  # that monitor unplugged: a first start's place again
    assert overbook.opening_place(tmp_path) is None


# ------------------------------------------------------------------ the hot keys for real (no key is pressed)
@windows_only
def test_hot_keys_register_take_and_go_back(hidden_root):
    vk_f24 = 0x87  # a key no keyboard has: nobody's key is taken for the test
    keys = overlay.HotKeys.start()
    assert keys is not None
    try:
        assert keys.register("F24", vk_f24) and keys.registered == {"F24"}
        assert keys.register("F24", vk_f24)  # registered already
        hot = keys._ids["F24"]
        overlay.user32.PostMessageW.argtypes = None
        overlay.user32.PostMessageW(keys.hwnd, overlay.WM_HOTKEY, hot, 0)  # as Windows sends it
        for _ in range(20):
            hidden_root.update()  # Tk's event loop hands it to the message-only window
            if overlay._notes[keys.hwnd]:
                break
        assert keys.take() == ["F24"] and keys.take() == []
        keys.unregister("F24")
        assert keys.registered == frozenset()
        assert overlay.user32.RegisterHotKey(keys.hwnd, 99, overlay.MOD_NOREPEAT, vk_f24)  # free again
        overlay.user32.UnregisterHotKey(keys.hwnd, 99)
    finally:
        keys.close()
    assert keys.hwnd == 0
