"""TASlation's own window never on the screen (`ui.seethrough.hidden`): its size and place always off every monitor,
never minimised nor maximised, alpha 0 and an application's window with its taskbar button titled TASlation, each put
back when changed; the foreground handed back to the viewer when Windows gave it to the window, and a click on its
taskbar button giving a dialog on show, the chooser, the Menu with the left pane's controls or the viewer; its Close
quitting as Quit does; its dialogs over the viewer and on the viewer's monitor, the ones the reader asked for taking
the keys; the Menu (`ui.see_menu`) with the window's entries that still mean something, the viewer chooser and Series
and Volume as small dialogs, the chooser coming by itself with no viewer, the setup banner's lines in the right pane
with their buttons in the Menu (a dialog with that pane off); a start whose see-through window could not be made said
in a box and ended; the Translator role as the left pane's Edit, the viewer's window looked at as it is (never
enlarged), no line that TASlation covers the viewer, the panes' words naming no menu and no key, and the Settings
dialog with the mode's rows only; and without the hidden flag (`quiet_start` off Windows), nothing of it. Fake windows
and a withdrawn Tk root only: nothing is shown, no key, no click, the foreground only read."""

import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from taslation.config import Settings
from taslation.ui import layout
from taslation.ui import see_menu as sm
from taslation.ui import seethrough as ui

SCREEN = (0, 0, 1920, 1080)


# ------------------------------------------------------------------ the place off every monitor
@pytest.mark.parametrize("screen", [SCREEN, (-1920, -200, 3840, 1280), (0, 0, 7680, 2160)],
                         ids=["one monitor", "a monitor left of the primary", "a wide desk"])
def test_the_window_goes_up_and_left_of_every_monitor_by_its_size(screen):
    x, y = ui.off_screen(screen)
    for size in ((1180, 920), (screen[2], screen[3])):  # (any window no larger than every monitor together)
        assert x + size[0] + 40 < screen[0] and y + size[1] + 40 < screen[1]  # (its frame too: some 40 px)
    assert ui.root_geometry("1180x920+100+50", screen) == f"1180x920+{x}+{y}"
    assert ui.root_geometry("+5+5", screen) == f"+{x}+{y}" and ui.root_geometry("800x600", screen) == f"800x600+{x}+{y}"
    assert ui.root_geometry("1180x920-10-10", screen) == f"1180x920+{x}+{y}"
    assert ui.root_geometry("", screen) == "" and ui.root_geometry("zoomed", screen) == "zoomed"


class Wm:
    """Tk's own window calls, noted."""

    def __init__(self):
        self.calls = []

    def wm_geometry(self, geometry=None):
        self.calls.append(("geometry", geometry))
        return geometry or "1180x920+-2320+-1480"

    def wm_state(self, state=None):
        self.calls.append(("state", state))
        return "normal"

    def wm_iconify(self):
        self.calls.append(("iconify",))
        return ""

    def wm_title(self, string=None):
        self.calls.append(("title", string))
        return string or "TASlation"


class Root(ui.HiddenWindowMixin, Wm):
    pass


def test_every_size_and_place_given_the_hidden_window_goes_off_the_screen_and_it_is_never_minimised_nor_maximised(
        monkeypatch):
    monkeypatch.setattr(ui.window, "virtual_screen", lambda: SCREEN)
    root = Root()
    root._see_hidden = True
    root.geometry("1180x920+300+40")
    root.state("zoomed")
    root.wm_state("iconic")
    root.iconify()
    root.state("normal")
    assert root.state() == "normal"
    assert root.calls == [("geometry", "1180x920+-2320+-1480"), ("state", "normal"), ("state", None)]
    from taslation.ui import app as app_mod

    for name in ("geometry", "wm_geometry", "state", "wm_state", "iconify", "wm_iconify", "dialog_centre"):
        assert getattr(app_mod.App, name) is getattr(ui.HiddenWindowMixin, name), name


def test_without_the_hidden_flag_the_window_is_tks_own(monkeypatch):
    root = Root()  # (no _see_hidden: as a window `quiet_start` did not hide)
    root.geometry("1180x920+300+40")
    root.state("zoomed")
    root.iconify()
    assert root.calls == [("geometry", "1180x920+300+40"), ("state", "zoomed"), ("iconify",)]
    assert root.dialog_centre() is None
    monkeypatch.setattr(ui.window, "IS_WINDOWS", False)  # (off Windows: nothing hides it)
    later, attributes = [], []
    app = SimpleNamespace(after=lambda ms, f: later.append(ms), wm_attributes=lambda *a: attributes.append(a))
    ui.quiet_start(app)
    assert not ui.hidden(app) and attributes == [] and app._quiet_decoy is None and not ui.quiet(app)
    assert ui.keep_hidden(app) is None and ui.hand_back(app) is False


def test_the_hidden_window_is_never_seen(monkeypatch):
    monkeypatch.setattr(ui.window, "IS_WINDOWS", True)
    set_ = []
    window = SimpleNamespace(attributes=lambda *a: set_.append(a), _see_hidden=True)
    ui.HiddenWindowMixin._apply_alpha(window)
    assert set_ == [("-alpha", 0.0)]
    window._see_hidden = False
    ui.HiddenWindowMixin._apply_alpha(window)
    assert set_ == [("-alpha", 0.0)]  # (not hidden: left as Tk has it)
    from taslation.ui import app as app_mod

    assert app_mod.App._apply_alpha is ui.HiddenWindowMixin._apply_alpha


def test_a_start_whose_see_through_window_could_not_be_made_says_so_and_ends(monkeypatch):
    from taslation.ui.dialogs import caches

    monkeypatch.setattr(ui.window.SeeThrough, "start", classmethod(lambda cls: None))
    told = []
    monkeypatch.setattr(caches, "tell", lambda parent, text, **k: told.append((parent, text)))
    app = SimpleNamespace(settings=Settings(), _see_hidden=True, quit_before_start=False)
    assert ui.start(app) is False
    assert app.quit_before_start is True and not ui.on(app)
    assert told == [(app, ui.COULD_NOT_START)]  # (in the window's language: English here)


# ------------------------------------------------------------------ kept as it is to be
class Calls:
    """Tk's ``wm`` calls of a fake window: what each reads, and what was set."""

    def __init__(self, state="normal", alpha=0.0, tool=0):
        self.values = {"state": state, "-alpha": alpha, "-toolwindow": tool}
        self.set = []

    def call(self, *args):
        if args[:2] == ("wm", "state"):
            if len(args) > 3:
                self.set.append(("state", args[3]))
                return ""
            return self.values["state"]
        if args[:2] == ("wm", "attributes"):
            if len(args) > 4:
                self.set.append((args[3], args[4]))
                return ""
            return self.values[args[3]]
        raise AssertionError(args)


def test_keep_hidden_puts_back_what_changed_and_counts_it(monkeypatch):
    facts = {"on_monitor": True}
    monkeypatch.setattr(ui.window, "window_facts", lambda hwnd: dict(facts) if hwnd == 77 else None)
    monkeypatch.setattr(ui.window, "virtual_screen", lambda: SCREEN)
    peeks = []
    monkeypatch.setattr(ui.window, "no_peek", lambda hwnd: peeks.append(hwnd) or True)
    calls, placed = Calls(state="iconic", alpha="0.5", tool=1), []  # (a tool window has no taskbar button)
    app = SimpleNamespace(_see_hidden=True, tk=calls, _w=".", _own_hwnd=lambda: 77, wm_geometry=placed.append)
    ui.keep_hidden(app)
    assert calls.set == [("state", "normal"), ("-alpha", 0.0), ("-toolwindow", 0)]
    assert placed == [ui.root_geometry("+0+0", SCREEN)] and app._see_root_hwnd == 77
    assert app._see_hidden_fixes == {"state": 1, "alpha": 1, "tool": 1, "place": 1}
    app.tk, facts["on_monitor"], placed[:] = Calls(), False, []
    ui.keep_hidden(app)
    assert app.tk.set == [] and placed == [] and sum(app._see_hidden_fixes.values()) == 4  # (as it is to be)
    assert peeks == [77]  # (left out of the taskbar's peek once for its handle)


def handing(monkeypatch, front):
    import taslation.capture as capture

    given = []
    monkeypatch.setattr(capture, "foreground_window", lambda: front[0])
    monkeypatch.setattr(capture, "give_foreground", lambda hwnd: given.append(hwnd) or True)
    monkeypatch.setattr(capture, "window_exists", lambda hwnd: True)
    return given


def test_the_foreground_windows_give_the_hidden_window_goes_back_to_the_viewer(monkeypatch):
    front = [77]
    given = handing(monkeypatch, front)
    app = SimpleNamespace(_see_hidden=True, _own_hwnd=lambda: 77, selected=SimpleNamespace(hwnd=5))
    assert ui.hand_back(app) is True and given == [5] and app._see_handed_back == 1
    app._see_menu_up = True  # (a menu of TASlation's is up: it needs the window in front)
    assert ui.hand_back(app) is False
    app._see_menu_up = False
    ui.asked(app)  # (the reader just asked for a dialog: it is on its way)
    assert ui.hand_back(app) is False
    app._see_asked -= ui.HAND_BACK_WAIT_S + 0.1
    assert ui.hand_back(app) is True
    front[0] = 99  # (another window in front: the viewer, the reader's own, a dialog of TASlation's)
    assert ui.hand_back(app) is False
    front[0], app.selected = 77, None  # (no viewer to give it to)
    assert ui.hand_back(app) is False and given == [5, 5]


# ------------------------------------------------------------------ the dialogs: where, and who gets the keys
def test_the_hidden_windows_dialogs_are_centred_over_the_viewer_and_a_dialogs_own_over_it(hidden_root, monkeypatch):
    class Top(ui.HiddenWindowMixin, tk.Toplevel):
        pass

    top = Top(hidden_root)
    top.withdraw()
    top._see_hidden = True
    monkeypatch.setattr(ui, "dialog_centre", lambda app: (700, 450) if ui.hidden(app) else None)
    monkeypatch.setattr(layout, "work_area", lambda widget, x=None, y=None: (0, 0, 1920, 1040))
    dialog = tk.Toplevel(top)
    frame = ttk.Frame(top)
    assert layout.dialog_area(dialog, top)[1] == (700, 450)
    assert layout.dialog_area(dialog, frame)[1] == (700, 450)  # (a widget of the window: its window says)
    other = tk.Toplevel(hidden_root)  # (a dialog over a dialog: over that dialog, as ever)
    assert layout.dialog_area(dialog, other)[1] != (700, 450)
    assert layout.dialog_area(dialog, top, at=(10, 20))[1] == (10, 20)
    top._see_hidden = False
    assert layout.dialog_area(dialog, top)[1] != (700, 450)


def test_dialog_centre_is_the_viewers_middle_or_the_primary_monitors(monkeypatch):
    import taslation.capture as capture

    monkeypatch.setattr(capture, "window_exists", lambda hwnd: hwnd == 5)
    monkeypatch.setattr(capture, "window_rect", lambda hwnd: (100, 200, 1100, 900))
    monkeypatch.setattr(layout, "work_area", lambda widget, x=None, y=None: (0, 0, 1920, 1040))
    app = SimpleNamespace(_see_hidden=True, selected=SimpleNamespace(hwnd=5))
    assert ui.dialog_centre(app) == (600, 550)
    app.selected = SimpleNamespace(hwnd=6)  # (closed meanwhile)
    assert ui.dialog_centre(app) == (960, 520)
    app.selected = None
    assert ui.dialog_centre(app) == (960, 520)
    app._see_hidden = False
    assert ui.dialog_centre(app) is None


def test_the_start_dialogs_go_to_the_viewers_monitor_whatever_monitor_the_hidden_window_is_nearest(monkeypatch):
    monkeypatch.setattr(layout, "IS_WINDOWS", True)
    monkeypatch.setattr(layout, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(layout, "monitor_rect", lambda hwnd: (0, 0, 1920, 1080))
    app = SimpleNamespace(selected=SimpleNamespace(hwnd=5), _own_hwnd=lambda: 77, _see_hidden=True)
    parent = SimpleNamespace(_root=lambda: app)
    assert layout.book_monitor(parent) == (0, 0, 1920, 1080)  # (the same monitor, but the window is not there)
    app._see_hidden = False
    assert layout.book_monitor(parent) is None  # (as ever: they share it)


def test_a_dialog_the_reader_asked_for_takes_the_keys_as_it_shows_and_the_others_do_not(hidden_root):
    done = []

    class Dialog(tk.Toplevel):
        def lift(self, *a):
            done.append("lift")

        def focus_force(self):
            done.append("focus")

    dialog = Dialog(hidden_root)
    dialog.withdraw()
    app = SimpleNamespace(_see_hidden=True, _quiet_decoy=None)
    ui._mapped(app, SimpleNamespace(widget=dialog))
    assert done == []  # (it came by itself: as its own code has it)
    ui.asked(app)
    ui._mapped(app, SimpleNamespace(widget=dialog))
    assert done == ["lift", "focus"]
    tip = Dialog(hidden_root)
    tip.withdraw()
    tip.overrideredirect(True)
    ui._mapped(app, SimpleNamespace(widget=tip))
    ui._mapped(app, SimpleNamespace(widget=ttk.Frame(hidden_root)))  # (no top-level)
    app._see_asked -= ui.ASKED_S + 0.1
    ui._mapped(app, SimpleNamespace(widget=dialog))
    assert done == ["lift", "focus"]


# ------------------------------------------------------------------ the Menu
def menu_app(root, **more):
    done = []
    app = SimpleNamespace(ui_lang_var=tk.StringVar(root, value="en"), done=done, _see_hidden=True,
                          auto_var=tk.BooleanVar(root, value=True), _see_through=None)
    for name in ("open_caches", "review_names", "open_help", "open_notice", "open_updates", "open_about",
                 "open_settings", "_on_ui_language", "_on_close", "translate_now", "set_area"):
        setattr(app, name, lambda _n=name: done.append((_n, getattr(app, "_see_asked", None))))
    for key, value in more.items():
        setattr(app, key, value)
    return app


def entries(menu):
    out = []
    for i in range(int(menu.index("end")) + 1):
        kind = menu.type(i)
        out.append("-" if kind == "separator" else menu.entrycget(i, "label"))
    return out


def test_the_menu_has_the_windows_entries_that_still_mean_something_and_each_is_asked_for(hidden_root, monkeypatch):
    from taslation.ui import gpu_release

    app = menu_app(hidden_root)
    opened = []
    monkeypatch.setattr(sm, "open_viewer", lambda a, by_itself=False: opened.append(("viewer", a._see_asked)))
    monkeypatch.setattr(sm, "open_book", lambda a: opened.append(("book", a._see_asked)))
    monkeypatch.setattr(gpu_release, "release_now", lambda a: opened.append(("release", a._see_asked)))
    menu, language, help_menu = (tk.Menu(hidden_root, tearoff=0) for _ in range(3))
    sm.build(app, menu, language, help_menu)
    assert entries(menu) == ["Viewer...", "Series and Volume...", "-", "Saved translations...",
                             "Names rendered in more than one way...", gpu_release.RELEASE_ENTRY, "-", "Language",
                             "Help"]
    assert entries(help_menu) == ["How to use...", "Legal notice...", "-", "Check for updates...", "About TASlation"]
    assert len(entries(language)) == len(sm.UI_LANGUAGES)
    for i in (0, 1, 3, 4, 5):
        menu.invoke(i)
    for i in (0, 1, 3, 4):
        help_menu.invoke(i)
    language.invoke(1)
    assert [n for n, _t in opened] == ["viewer", "book", "release"]
    assert [n for n, _t in app.done] == ["open_caches", "review_names", "open_help", "open_notice", "open_updates",
                                         "open_about", "_on_ui_language"]
    assert all(t is not None for _n, t in opened + app.done)  # (each the reader's asking: its dialog takes the keys)
    assert app.ui_lang_var.get() == list(sm.UI_LANGUAGES)[1]
    # what only the window's own page and canvas had is not there
    for gone in ("Show original", "Always on top", "Over the full-screen viewer", "Reading-order numbers", "Keys...",
                 "Page keys...", "Set area...", "Settings...", "Quit", "Full screen (F11)"):
        assert gone not in entries(menu) + entries(help_menu)
    # built again, the same entries (each opening fills the menu anew)
    sm.build(app, menu, language, help_menu)
    assert entries(menu)[-1] == "Help" and len(entries(language)) == len(sm.UI_LANGUAGES)


def test_the_buttons_menu_adds_the_left_panes_controls_settings_and_quit_and_quit_is_no_asking(hidden_root,
                                                                                                 monkeypatch):
    # (the taskbar button opens it while the left pane has no room beside the page: it has what the left pane has)
    toggled = []
    monkeypatch.setattr(ui, "toggle", lambda a: toggled.append(a))
    app = menu_app(hidden_root)
    menu, language, help_menu = (tk.Menu(hidden_root, tearoff=0) for _ in range(3))
    sm.build(app, menu, language, help_menu, full=True)
    assert entries(menu)[:5] == ["Translate", "Auto", "Lettering", "Set area...", "-"]
    assert entries(menu)[-4:] == ["Help", "-", "Settings...", "Quit"]
    menu.invoke(len(entries(menu)) - 1)
    assert app.done == [("_on_close", None)]
    menu.invoke(len(entries(menu)) - 2)
    assert app.done[-1][0] == "open_settings" and app.done[-1][1] is not None
    menu.invoke(0)
    menu.invoke(3)
    assert [n for n, _t in app.done[-2:]] == ["translate_now", "set_area"]
    menu.invoke(1)
    assert app.auto_var.get() is False
    menu.invoke(2)
    assert toggled == [app]
    pane_menu = tk.Menu(hidden_root, tearoff=0)
    sm.build(app, pane_menu, tk.Menu(pane_menu, tearoff=0), tk.Menu(pane_menu, tearoff=0))
    assert "Translate" not in entries(pane_menu)  # (the pane's own Menu: the controls are beside it)


class FakeMenu:
    def __init__(self, app, popped):
        self.app, self.popped = app, popped

    def tk_popup(self, x, y):
        self.popped.append((x, y, self.app._see_menu_up))

    def grab_release(self):
        pass


def test_a_menu_opens_with_the_hidden_window_in_front_and_is_taken_to_be_up_until_it_ended(monkeypatch):
    popped, fronts, later = [], [], []
    app = SimpleNamespace(_see_hidden=True, _own_hwnd=lambda: 77, after=lambda ms, f: later.append((ms, f)))
    monkeypatch.setattr(sm, "menu_for", lambda a, kind: (FakeMenu(a, popped), None, None))
    monkeypatch.setattr(sm, "build", lambda *a, **k: None)
    monkeypatch.setattr(sm, "_front", lambda hwnd: fronts.append(hwnd) or True)
    shown = [True]
    monkeypatch.setattr(sm, "_menus_shown", lambda: shown[0])
    sm.popup(app, 300, 400, "pane")
    assert popped == [(300, 400, True)] and fronts == [77] and ui.menu_up(app)
    (ms, down), = later
    assert ms == sm.MENU_GRACE_MS
    down()  # (a menu of this process still on the screen: looked at again)
    assert ui.menu_up(app) and len(later) == 2
    shown[0] = False
    later[-1][1]()
    assert not ui.menu_up(app) and [k for _t, k in app._see_menu_opened] == ["pane"]
    assert ui.recently_closed(app)  # (the window in front now is Windows' doing: no click on its button)


def test_the_menu_row_opens_the_menu_at_the_panes_right_edge_level_with_the_row(monkeypatch):
    popped = []
    monkeypatch.setattr(sm, "popup", lambda app, x, y, kind: popped.append((x, y, kind)))
    picture = SimpleNamespace(hits=(("area", (0, 200, 120, 230)), ("menu", (0, 280, 120, 310))))
    app = SimpleNamespace(_see_through=SimpleNamespace(pane_shown=lambda side: (8, 100, 128, 500)),
                          _see_pane_memo={"left": (None, picture, (8, 100, 128, 500))})
    assert sm.popup_at_pane(app) is True and popped == [(128, 380, "pane")]
    ui.PANE_ACTIONS["menu"](app)
    assert popped[-1] == (128, 380, "pane")
    app._see_through = SimpleNamespace(pane_shown=lambda side: None)  # (the pane hidden meanwhile)
    assert sm.popup_at_pane(app) is False and len(popped) == 2


# ------------------------------------------------------------------ the taskbar button
def front_app(monkeypatch, front, shell, dialogs=()):
    """A hidden window (handle 77) with the viewer 5, the left pane with room; what `front_tick` opens, noted."""
    given = handing(monkeypatch, front)
    opened = []
    monkeypatch.setattr(ui.window, "cursor_pos", lambda: (500, 1060))
    monkeypatch.setattr(ui.window, "shell_at", lambda point: shell[0] and point == (500, 1060))
    monkeypatch.setattr(ui, "own_dialogs", lambda app: list(dialogs))
    monkeypatch.setattr(sm, "open_viewer", lambda app: opened.append("chooser"))
    monkeypatch.setattr(sm, "popup", lambda app, x, y, kind: opened.append((x, y, kind)))
    app = SimpleNamespace(_see_hidden=True, _own_hwnd=lambda: 77, selected=SimpleNamespace(hwnd=5),
                          _see_pane_memo={"left": (None, None, (8, 100, 128, 500))})
    return app, given, opened


def test_a_click_on_the_taskbar_button_brings_the_viewer_or_opens_what_the_reader_needs(monkeypatch):
    front, shell = [77], [True]
    app, given, opened = front_app(monkeypatch, front, shell)
    assert ui.front_tick(app) == "viewer" and given == [5] and opened == []  # (the panes beside the page)
    app._see_pane_memo["left"] = (None, None, None)  # (the left pane with no room: its controls at the pointer)
    assert ui.front_tick(app) == "menu" and opened == [(500, 1060, "button")] and given == [5]
    app.selected = None  # (no viewer chosen: the chooser, taking the keys)
    assert ui.front_tick(app) == "chooser" and opened[-1] == "chooser" and ui._recently_asked(app, ui.ASKED_S)
    assert app._see_front == {"menu": 1, "chooser": 1}


def test_the_window_in_front_by_windows_doing_hands_the_foreground_back_as_before(monkeypatch):
    front, shell = [77], [False]
    app, given, opened = front_app(monkeypatch, front, shell)
    app._see_pane_memo["left"] = (None, None, None)
    assert ui.front_tick(app) == "viewer" and given == [5] and opened == []  # (the pointer on no taskbar)
    shell[0] = True
    app._see_closed_at = time.monotonic()  # (a dialog of its own just went: Windows activated its owner)
    assert ui.front_tick(app) == "viewer" and given == [5, 5] and opened == []
    app._see_closed_at -= ui.CLOSED_S + 0.1
    app._see_menu_up = True  # (a menu of TASlation's is up: it needs the window in front)
    assert ui.front_tick(app) == "" and len(given) == 2
    app._see_menu_up = False
    front[0] = 99  # (another window in front)
    assert ui.front_tick(app) == "" and len(given) == 2 and opened == []
    app.selected = None
    front[0], shell[0] = 77, False  # (no viewer, no click: left as it is, as before)
    assert ui.front_tick(app) == "" and opened == []


def test_a_dialog_of_its_own_on_show_comes_to_the_front_instead(monkeypatch):
    done = []
    dialog = SimpleNamespace(lift=lambda: done.append("lift"), focus_force=lambda: done.append("focus"))
    app, given, opened = front_app(monkeypatch, [77], [True], dialogs=[object(), dialog])
    assert ui.front_tick(app) == "dialog" and done == ["lift", "focus"] and given == [] and opened == []


def test_a_click_that_minimised_the_window_puts_it_back_unactivated_and_brings_the_viewer(monkeypatch):
    front, shell = [99], [True]  # (Windows gave the foreground away as it minimised the window)
    app, given, opened = front_app(monkeypatch, front, shell)
    assert ui.front_tick(app, clicked=True) == "viewer" and given == [5]
    app._see_pane_memo["left"] = (None, None, None)
    assert ui.front_tick(app, clicked=True) == "menu" and given == [5, 77] and opened == [(500, 1060, "button")]
    later, done = [], []
    monkeypatch.setattr(ui, "keep_hidden", lambda a: done.append("normal"))
    monkeypatch.setattr(ui, "front_tick", lambda a, clicked=False: done.append(("front", clicked)))
    viewer_iconic = [False]
    monkeypatch.setattr(ui.window, "window_facts", lambda hwnd: {"iconic": viewer_iconic[0]} if hwnd == 5 else None)
    app.tk = SimpleNamespace(call=lambda *a: "iconic")
    app._w, app.after_idle = ".", later.append
    ui._unmapped(app, SimpleNamespace(widget=app))
    later.pop()()
    assert done == ["normal", ("front", True)]
    viewer_iconic[0] = True  # (the viewer minimised with it: Show desktop, Win+M - only put back)
    ui._unmapped(app, SimpleNamespace(widget=app))
    later.pop()()
    assert done == ["normal", ("front", True), "normal"]
    viewer_iconic[0], shell[0] = False, False  # (the pointer on no taskbar: no click on the button)
    ui._unmapped(app, SimpleNamespace(widget=app))
    later.pop()()
    assert done == ["normal", ("front", True), "normal", "normal"]
    ui._unmapped(app, SimpleNamespace(widget=object()))  # (another widget unmapped: nothing)
    app.tk = SimpleNamespace(call=lambda *a: "normal")
    ui._unmapped(app, SimpleNamespace(widget=app))  # (not minimised)
    assert later == []


def test_a_dialog_gone_is_noted_and_the_dialogs_on_show_are_the_ones_with_a_frame(hidden_root):
    dialog, tip = tk.Toplevel(hidden_root), tk.Toplevel(hidden_root)
    for each in (dialog, tip):
        each.withdraw()
    tip.overrideredirect(True)
    try:
        app = SimpleNamespace(_see_closed_at=-1e9)
        ui._closed(app, SimpleNamespace(widget=tip))
        ui._closed(app, SimpleNamespace(widget=ttk.Frame(dialog)))
        assert not ui.recently_closed(app)
        ui._closed(app, SimpleNamespace(widget=dialog))
        assert ui.recently_closed(app) and not ui.recently_closed(app, 0.0)
        names = (str(hidden_root), str(tip), str(dialog))
        fake = SimpleNamespace(tk=SimpleNamespace(call=lambda *a: names, splitlist=tuple), _w=".",
                               nametowidget=hidden_root.nametowidget, _quiet_decoy=None)
        assert ui.own_dialogs(fake) == [dialog]  # (not the window, not the tip)
    finally:
        dialog.destroy()
        tip.destroy()


def test_the_hidden_window_is_titled_for_its_taskbar_button_and_its_close_quits_as_quit_does():
    import inspect

    root = Root()
    root._see_hidden = True
    root.title("TASlation - translating...")
    assert root.calls[-1] == ("title", ui.BUTTON_TITLE)
    root.title()
    assert root.calls[-1] == ("title", None)
    del root._see_hidden
    root.wm_title("Any")
    assert root.calls[-1] == ("title", "Any")
    from taslation.ui import app as app_mod

    for name in ("title", "wm_title"):
        assert getattr(app_mod.App, name) is getattr(ui.HiddenWindowMixin, name), name
    # the button's Close, its thumbnail's X and Alt+F4 send WM_CLOSE, which Tk turns into WM_DELETE_WINDOW: the
    # window's close, as the left pane's Quit and the Menu's Quit
    source = inspect.getsource(app_mod.App)
    assert 'self.protocol("WM_DELETE_WINDOW", self._on_close)' in source
    calls = []
    ui.PANE_ACTIONS["quit"](SimpleNamespace(_on_close=lambda: calls.append("close")))
    assert calls == ["close"]


# ------------------------------------------------------------------ the viewer chooser, Series and Volume, the banner
class FakeApp(tk.Toplevel):
    """The window as the dialogs see it: withdrawn, so that nothing of theirs shows."""

    def __init__(self, master):
        super().__init__(master)
        self.withdraw()
        self.windows = [SimpleNamespace(hwnd=11, label=lambda: "Sample viewer one"),
                        SimpleNamespace(hwnd=12, label=lambda: "Sample viewer two")]
        self.selected = None
        self.window_box = ttk.Combobox(self, values=[w.label() for w in self.windows])
        self.picked, self.rescans = [], 0
        self.book_var = tk.StringVar(self, value="")
        self._see_hidden, self._see_through = True, None
        sm.init(self)

    def _rescan_windows(self):
        self.rescans += 1

    def refresh_windows(self, select=None):
        pass

    def _on_window_selected(self, picked=False, named=False):
        self.picked.append((self.window_box.current(), picked))
        self.selected = self.windows[self.window_box.current()]


@pytest.fixture
def keys(monkeypatch):
    given = []
    monkeypatch.setattr(layout, "dialog_keys", lambda win, parent, focus=None: given.append(win))
    return given


def test_the_viewer_chooser_chooses_as_the_toolbars_list_does(hidden_root, keys):
    app = FakeApp(hidden_root)
    dialog = sm.open_viewer(app)
    assert app._see_chooser is dialog and not dialog.by_itself and keys == []  # (asked for: `_mapped` gives keys)
    assert list(dialog.box.cget("values")) == ["Sample viewer one", "Sample viewer two"] and app.rescans == 1
    assert sm.open_viewer(app) is dialog  # (the one open brought up)
    dialog.box.current(1)
    dialog.ok()
    assert app.picked == [(1, True)] and app.selected.hwnd == 12 and app._see_chooser is None
    assert not dialog.winfo_exists()


def test_with_no_viewer_the_chooser_comes_by_itself_and_goes_once_one_is_chosen(hidden_root, keys):
    app = FakeApp(hidden_root)
    start = app._see_started
    sm.chooser_tick(app, now=start + 1.0)
    assert app._see_chooser is None  # (not at once: a viewer may be found first)
    sm.chooser_tick(app, now=start + sm.CHOOSER_DUE_S + 0.1)
    dialog = app._see_chooser
    assert dialog is not None and dialog.by_itself and keys == [dialog]  # (no key while another program is in front)
    assert dialog.attributes("-topmost")
    app.selected = app.windows[0]  # (TASlation found the viewer meanwhile)
    sm.chooser_tick(app, now=start + 10)
    assert app._see_chooser is None and not dialog.winfo_exists()


def test_a_chooser_closed_with_no_choice_comes_again_only_once_a_viewer_was_chosen_and_lost(hidden_root, keys):
    app = FakeApp(hidden_root)
    late = app._see_started + 10
    sm.chooser_tick(app, now=late)
    app._see_chooser.close()
    assert app._see_chooser is None and app._see_chooser_declined
    sm.chooser_tick(app, now=late + 1)
    assert app._see_chooser is None
    app.selected = app.windows[0]
    sm.chooser_tick(app, now=late + 2)
    app.selected = None  # (lost)
    sm.chooser_tick(app, now=late + 3)
    assert app._see_chooser is not None and app._see_chooser.by_itself


def test_no_chooser_comes_while_a_dialog_holds_the_window(hidden_root, keys, monkeypatch):
    from taslation.ui.dialogs import help as help_dialogs

    monkeypatch.setattr(help_dialogs, "modal_up", lambda window: True)
    app = FakeApp(hidden_root)
    sm.chooser_tick(app, now=app._see_started + 10)
    assert app._see_chooser is None


def test_the_trouble_lines_choose_viewer_opens_the_chooser_while_the_window_is_hidden(monkeypatch):
    from taslation.ui import trouble

    opened = []
    monkeypatch.setattr(sm, "open_viewer", lambda app, by_itself=False: opened.append(app._see_asked))
    window = SimpleNamespace(_see_hidden=True)
    trouble.choose_viewer(window)
    assert len(opened) == 1 and opened[0] > 0


def test_series_and_volume_set_the_books_name_as_the_toolbars_fields_do(hidden_root, monkeypatch):
    from taslation.ui import book_fields

    committed = []
    monkeypatch.setattr(book_fields, "kept_name", lambda window, name: name)
    monkeypatch.setattr(book_fields, "fields_committed", lambda window: committed.append(window.book_var.get()))
    app = FakeApp(hidden_root)
    app.book_var.set("Sample Series 2")
    dialog = sm.open_book(app)
    assert (dialog.fields.series_var.get(), dialog.fields.volume_var.get()) == ("Sample Series", "2")
    dialog.fields.volume_var.set("3")
    dialog.ok()
    assert app.book_var.get() == "Sample Series 3" and app._book_edited and committed == ["Sample Series 3"]
    assert not dialog.winfo_exists() and app._see_book_dialog is None
    dialog = sm.open_book(app)
    dialog.fields.volume_var.set("完全版")  # (an edition, no volume: refused, the dialog stays)
    dialog.ok()
    assert dialog.winfo_exists() and dialog.refused_label.winfo_manager() and app.book_var.get() == "Sample Series 3"
    dialog.destroy()  # (Close: the name as it was)
    assert app.book_var.get() == "Sample Series 3" and committed == ["Sample Series 3"]


def test_the_setup_banners_lines_come_as_a_dialog_that_follows_them_and_stays_closed_once_closed(hidden_root, keys):
    from taslation.ui.banner import NOTICE_COLOURS, PROBLEM_COLOURS

    app = FakeApp(hidden_root)
    pressed = []
    rows = [("The translator is not running.", PROBLEM_COLOURS,
             ("Start translator again", lambda: pressed.append(app._see_asked))),
            ("Translating on the processor.", NOTICE_COLOURS, None)]
    sm.show_banner(app, rows)
    dialog = app._see_banner
    assert dialog is not None and dialog.by_itself and dialog.texts == tuple(r[0] for r in rows) and keys == [dialog]
    buttons = [w for w in dialog.body.winfo_children()[0].winfo_children() if isinstance(w, ttk.Button)]
    assert [b.cget("text") for b in buttons] == ["Start translator again"]
    buttons[0].invoke()
    assert pressed and pressed[0] > 0  # (a click on it is the reader's asking)
    sm.show_banner(app, rows)
    assert app._see_banner is dialog  # (the same lines: the same dialog)
    sm.show_banner(app, rows[1:])
    assert app._see_banner is dialog and dialog.texts == (rows[1][0],)  # (followed in place)
    dialog.close()
    assert app._see_banner is None
    sm.show_banner(app, rows[1:])
    assert app._see_banner is None  # (closed on these lines)
    sm.show_banner(app, rows)
    assert app._see_banner is not None  # (another line: said)
    sm.show_banner(app, [])
    assert app._see_banner is None and app._see_banner_closed == ()


def banner_window(**more):
    shown = []
    window = SimpleNamespace(_health=[], _trouble=None, _on_cpu=None, lang_var=None, _unshaped_closed=True,
                             setup_banner=SimpleNamespace(show_rows=lambda rows: shown.append(list(rows))),
                             _place_strip=lambda strip, on: None, _see_through=object(), _see_hidden=True,
                             settings=Settings(see_through_indicators=False))  # (no right pane: the dialog)
    for key, value in more.items():
        setattr(window, key, value)
    return window, shown


@pytest.mark.parametrize("kind, kept", [("closed", False), ("tied", False), ("minimised", True), ("black", True)])
def test_the_banners_dialog_leaves_choosing_a_viewer_to_the_chooser(monkeypatch, kind, kept):
    from taslation.ui import status

    said = []
    monkeypatch.setattr(sm, "show_banner", lambda window, rows: said.append([r[0] for r in rows]))
    window, shown = banner_window(_trouble=kind)
    status.StatusMixin._show_banner(window)
    assert len(said) == 1 and len(said[-1]) == len(shown[-1]) == (1 if kept else 0)
    window._see_hidden = False  # (the mode off: the banner as ever, no dialog)
    status.StatusMixin._show_banner(window)
    assert len(shown[-1]) == 1 and len(said) == 1


# ------------------------------------------------------------------ start, tick, close
class FakeOver:
    def __init__(self):
        self.on = True

    def follow(self, hwnd):
        pass

    def set_hover_delay(self, ms):
        pass

    def take_clicks(self):
        return []

    def take_edits(self):
        return []

    def set_edit(self, marks):
        self.marks = marks

    def set_panes(self, left, right):
        pass

    def close(self):
        pass


def test_the_start_listens_for_dialogs_and_the_window_minimised_and_makes_no_icon(monkeypatch):
    from taslation.capture import wgc

    over, binds = FakeOver(), []
    monkeypatch.setattr(ui.window.SeeThrough, "start", classmethod(lambda cls: over))
    monkeypatch.setattr(wgc, "set_update_ms", lambda ms: None)
    app = SimpleNamespace(settings=Settings(), _see_hidden=True, after=lambda ms, f: "job",
                          bind_class=lambda *a, **k: binds.append(a[:2]))
    assert ui.start(app) is True
    assert binds == [("Toplevel", "<Map>"), ("Toplevel", "<Unmap>"), ("Toplevel", "<Destroy>"), ("Tk", "<Unmap>")]
    assert app._see_chooser is None and not hasattr(app, "_see_tray") and app._see_front == {}
    ui.close(app)
    assert app._see_through is None


def test_a_tick_of_the_hidden_window_keeps_it_hidden_offers_the_chooser_and_looks_at_who_is_in_front(monkeypatch):
    done = []
    monkeypatch.setattr(ui.window, "viewer_dpi", lambda hwnd: 96)
    monkeypatch.setattr(ui, "present", lambda app: None)
    monkeypatch.setattr(ui, "panes_tick", lambda app: None)
    monkeypatch.setattr(ui, "keep_hidden", lambda app: done.append("keep"))
    monkeypatch.setattr(ui, "front_tick", lambda app, clicked=False: done.append("front"))
    monkeypatch.setattr(sm, "chooser_tick", lambda app: done.append("chooser"))
    app = SimpleNamespace(_see_through=FakeOver(), selected=None, _see_hidden=True, _see_ticks=0)
    for _ in range(ui.HIDE_EVERY + 1):
        ui.tick(app)
    assert done.count("front") == ui.HIDE_EVERY + 1
    assert done.count("keep") == done.count("chooser") == 2  # (the first tick and every HIDE_EVERY-th)
    app._see_hidden, done[:] = False, []
    ui.tick(app)
    assert done == []  # (the mode with the window on the screen: none of it)


def test_no_icon_in_the_notification_area_and_the_menu_presses_nothing_and_moves_no_pointer():
    import importlib.util
    import inspect

    assert importlib.util.find_spec("taslation.capture.tray") is None
    for module in (sm, ui):
        source = inspect.getsource(module)
        for call in ("SendInput", "keybd_event", "mouse_event", "SetCursorPos", "SetWindowsHookEx",
                     "Shell_NotifyIcon"):
            assert call not in source, (module.__name__, call)


# ------------------------------------------------------------------ what needs TASlation's own window is not used
def test_edit_follows_only_the_role_kept_for_the_book_while_the_window_is_hidden():
    from taslation.ui import translator

    changed = []
    window = SimpleNamespace(_see_hidden=True)

    class Var:
        value = "reader"

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    window.role_var = Var()
    window._on_role_changed = lambda chosen=True: changed.append(window.role_var.get())
    window.say = lambda *a, **k: changed.append("said")
    translator.TranslatorMixin._apply_role(window, "translator", chosen=False)  # (a book with no translations)
    assert window.role_var.get() == "reader" and changed == []  # Edit stays off: never switched on by itself
    translator.TranslatorMixin._apply_role(window, "translator", chosen=True)  # (the role kept for a book)
    assert window.role_var.get() == "translator" and changed == ["translator"]  # Edit on, nothing said of why
    window.role_var.set("translator")
    translator.TranslatorMixin._apply_role(window, "reader", chosen=False)  # (a book with translations)
    assert window.role_var.get() == "translator" and changed == ["translator"]
    window._see_hidden = False  # (the window on the screen: as ever)
    window.role_var.set("reader")
    translator.TranslatorMixin._apply_role(window, "translator", chosen=False)
    assert window.role_var.get() == "translator" and changed[1:] == ["translator", "said"]


def test_the_role_is_the_edit_switch_s_state():
    from taslation.ui import see_edit

    app = SimpleNamespace(_see_hidden=True, _see_through=object(), role_var=SimpleNamespace(get=lambda: "translator"))
    assert see_edit.on(app) is True
    app.role_var = SimpleNamespace(get=lambda: "reader")
    assert see_edit.on(app) is False
    assert see_edit.on(SimpleNamespace(_see_hidden=True, _see_through=object())) is False  # (no role yet: off)
    app.role_var, app._see_hidden = SimpleNamespace(get=lambda: "translator"), False
    assert see_edit.on(app) is False  # (the window on the screen: its own Translator role, no Edit)


def test_the_viewers_window_is_never_enlarged_only_looked_at(monkeypatch):
    import inspect

    from taslation.ui import viewers

    assert not hasattr(viewers, "enlarge_window")  # (nothing that moves or resizes it is at hand)
    assert "SetWindowPos" not in inspect.getsource(viewers) and "MoveWindow" not in inspect.getsource(viewers)
    shown = [False]
    monkeypatch.setattr(viewers, "window_shown", lambda hwnd: shown[0])
    window = SimpleNamespace(_see_hidden=True, selected=SimpleNamespace(hwnd=5), _enlarge_asked=None)
    assert viewers.ViewerMixin._enlarge_first(window) is True and window._enlarge_asked is None  # (minimised: later)
    shown[0] = True
    assert viewers.ViewerMixin._enlarge_first(window) is True
    # looked at once (read as it is): what early start waits for before it starts a page at once
    assert window._enlarge_asked == 5 and viewers.ViewerMixin._enlarge_first(window) is True
    window.selected = None
    assert viewers.ViewerMixin._enlarge_first(window) is True and window._enlarge_asked == 5


def test_early_start_goes_on_once_the_viewer_was_looked_at(monkeypatch):
    from taslation.ui import live, viewers

    monkeypatch.setattr(viewers, "window_shown", lambda hwnd: True)
    window = SimpleNamespace(_see_hidden=True, selected=SimpleNamespace(hwnd=5), _enlarge_asked=None,
                             _early=None, ready=True, busy=False, _early_on=lambda: True, _black_open=lambda: False,
                             auto_var=SimpleNamespace(get=lambda: True), _auto_last=None, _start_pending=None,
                             _starts_book=lambda image: False, _all_cached=lambda image: False)
    op = SimpleNamespace(operation=None)
    assert not live.LiveViewMixin._early_allowed(window, op, None, None)  # (the viewer's first page: not looked at)
    viewers.ViewerMixin._enlarge_first(window)
    assert live.LiveViewMixin._early_allowed(window, op, None, None)
    window.auto_var = SimpleNamespace(get=lambda: False)  # (Auto off: nothing starts by itself)
    assert not live.LiveViewMixin._early_allowed(window, op, None, None)


# ------------------------------------------------------------------ the banner's lines in the right pane
def test_the_banners_lines_and_the_guards_warning_are_in_the_right_pane_and_their_buttons_in_the_menu(hidden_root,
                                                                                                      monkeypatch):
    from taslation.ui import status
    from taslation.ui.banner import NOTICE_COLOURS, PROBLEM_COLOURS

    dialogs = []
    monkeypatch.setattr(sm, "show_banner", lambda window, rows: dialogs.append(list(rows)))
    pressed = []
    message = SimpleNamespace(code="health.ollama_down", params={})
    monkeypatch.setattr(status.trouble, "setup_line", lambda m: "The translator is not running.")
    monkeypatch.setattr(status.trouble, "setup_button",
                        lambda window, m: ("Start translator again", lambda: pressed.append(window._see_asked)))
    window, _shown = banner_window(_health=[message], _on_cpu=30, _close_cpu_line=lambda: pressed.append("closed"),
                                   settings=Settings(see_through_indicators=True))
    status.StatusMixin._show_banner(window)
    assert dialogs == [[]]  # (with the right pane on: no dialog)
    assert [r[0] for r in window._see_banner_rows][0] == "The translator is not running."
    window.guard_var = SimpleNamespace(get=lambda: "Blocked a connection to the internet.")
    window.status_var = SimpleNamespace(get=lambda: "The translator is not running.")  # (said once only)
    rows = ui.right_rows(window)
    texts = [r.text for r in rows]
    assert texts[0] == "The translator is not running." and rows[0].warn
    assert texts.count("The translator is not running.") == 1
    assert "Blocked a connection to the internet." in texts and not rows[1].warn  # (the processor's notice)
    assert next(r for r in rows if r.text.startswith("Blocked")).warn
    menu = tk.Menu(hidden_root, tearoff=0)
    window.ui_lang_var = tk.StringVar(hidden_root, value="en")
    for name in ("open_caches", "review_names", "open_help", "open_notice", "open_updates", "open_about",
                 "_on_ui_language"):
        setattr(window, name, lambda: None)
    sm.build(window, menu, tk.Menu(menu, tearoff=0), tk.Menu(menu, tearoff=0))
    labels = entries(menu)
    assert labels[0] == "Start translator again" and labels[1].startswith("Close: ") and labels[2] == "-"
    menu.invoke(0)
    menu.invoke(1)
    assert pressed[0] > 0 and pressed[1] == "closed"
    window.settings.see_through_indicators = False  # (the right pane off: the lines in their dialog)
    status.StatusMixin._show_banner(window)
    assert [r[0] for r in dialogs[-1]] == [r[0] for r in window._see_banner_rows]


@pytest.mark.parametrize("text, left", [
    ("No area is set for this viewer: Set area... (Page menu) lets you drag a rectangle around the page.",
     "No area is set for this viewer: Set area... lets you drag a rectangle around the page."),
    ("このビューアには範囲が設定されていません。「範囲設定...」（ページメニュー）でページの周りに矩形をドラッグして指定できます。",
     "このビューアには範囲が設定されていません。「範囲設定...」でページの周りに矩形をドラッグして指定できます。"),
    ("Ready (12 pages kept).", "Ready (12 pages kept)."),
    ("The translation took too long. Press F5 to try again.", "The translation took too long."),
])
def test_the_panes_words_name_no_menu_of_the_window_and_no_key(text, left):
    from taslation import panes as pn

    assert pn.pane_words(text) == left


def test_every_language_s_page_menu_aside_is_left_out_of_the_panes_words():
    from taslation import panes as pn
    from taslation.locales.features import window_tidy

    english = "No area is set for this viewer: Set area... (Page menu) lets you drag a rectangle around the page."
    for code, text in window_tidy.TEXTS[english].items():
        left = pn.pane_words(text)
        assert left != text and len(left) < len(text), code
        assert not any(mark in left for mark in "()（）"), code


# ------------------------------------------------------------------ the Settings dialog
def test_the_settings_dialog_has_the_modes_own_rows_and_none_of_the_old_windows(hidden_root, tmp_path, monkeypatch):
    from taslation.ui.dialogs import settings as dlg

    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    settings = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                        config_path=tmp_path / "taslation.toml")
    gone = {"see_through", "hover_shows", "hover_reveal", "bubble_zoom", "side_indicator", "panel_font_size",
            "always_on_top", "over_book", "next_page_key", "prev_page_key"}
    owner = tk.Toplevel(hidden_root)
    owner.withdraw()
    owner._see_hidden = True
    got = []
    see = dlg.SettingsDialog(owner, settings, on_saved=got.append)
    assert [see.pages.tab(t, "text") for t in see.pages.tabs()] == ["General", "System"]
    assert not gone & (set(see.extra) | set(see.numbers) | set(see.values()))
    assert "see_through_indicators" in see.extra
    assert set(see.numbers) == {"hover_delay_ms"}  # (the mode's own row of the delay: the patch under the pointer)
    assert see.changed() == {}
    see.extra["see_through_indicators"].set(False)
    see.numbers["hover_delay_ms"].set(str(settings.hover_delay_ms + 50))
    assert see.save() is True
    assert got == [{"see_through_indicators": False, "hover_delay_ms": settings.hover_delay_ms + 50}]
    again = Settings.from_toml(tmp_path / "taslation.toml")
    assert again.see_through_indicators is False and again.hover_delay_ms == settings.hover_delay_ms + 50
    see.destroy()
    owner.destroy()
