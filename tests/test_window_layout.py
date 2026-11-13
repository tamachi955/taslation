"""The window's layout and its place on the screen: the toolbar that flows into rows in every language, one place for
every command, comboboxes as wide as their entries, the target languages in the window's language, the status line said again after a language switch, reading mode giving the window back
its size and place, the page panel found in the viewer's frames, the hint on an empty canvas, readable labels and
handles, the Caches, notice, passphrase and region dialogs, the icon. Parts of the App are borrowed onto stand-ins
on the shared hidden root (never mapped)."""
from __future__ import annotations

import importlib.util
import json
import random
import re
import tkinter as tk
import tkinter.font as tkfont
import tomllib
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from test_notice import shown_text

from taslation import backup, i18n, jurisdictions, notice
from taslation.capture import WindowInfo
from taslation.config import Settings
from taslation.detect import page_area
from taslation.i18n import UI_LANGUAGES, _, set_language
from taslation.ui import app as app_mod
from taslation.ui import area, layout, live, viewers, wrap
from taslation.ui.preview import ImageCanvas
from taslation.ui.live import BlackViewerMixin

ROOT = Path(__file__).resolve().parents[1]
VIEWER = WindowInfo(hwnd=7, title="Yomizuq - Google Chrome", class_name="Chrome_WidgetWin_1", pid=7, rect=(0, 0, 960, 540))


def _sized(canvas, width=400, height=300):
    canvas.winfo_width, canvas.winfo_height = (lambda: width), (lambda: height)
    return canvas


# ------------------------------------------------------------------ the toolbar and the menus
class Bars(tk.Toplevel):
    """The App's toolbar and menus, built on a withdrawn window of the hidden root."""

    _build_toolbar = app_mod.App._build_toolbar
    _build_translator_tools = app_mod.App._build_translator_tools
    _build_menus = app_mod.App._build_menus
    _sync_tools = app_mod.App._sync_tools
    _target_typed = app_mod.App._target_typed
    _target_set = app_mod.App._target_set

    def __init__(self, root):
        super().__init__(root)
        self.withdraw()
        self.settings = SimpleNamespace(target_language="English", ollama_model="qwen3.5:4b", role="reader")
        for name in ("window_var", "book_var", "model_var", "lang_var", "role_var", "ui_lang_var"):
            setattr(self, name, tk.StringVar(self))
        for name in ("auto_var", "original_var", "top_var", "over_var", "order_numbers_var"):
            setattr(self, name, tk.BooleanVar(self))
        self.model_var.set("qwen3.5:4b")
        self.role_var.set("reader")

    def _noop(self, *_args, **_kwargs):
        pass

    open_page_keys = _noop
    set_area = clear_area = translate_now = enter_reading = _on_role_changed = toggle_order = toggle_skip = _noop
    retranslate_page = open_book_settings = open_review = open_find_replace = undo_edit = redo_edit = _turn_direction = open_batch_dialog = stop_batch = _noop
    _redisplay = _apply_on_top = open_glossary = open_caches = review_names = _rescan_windows = _noop
    _on_window_selected = open_notice = _on_ui_language = toggle_over = _noop
    open_about = open_help = open_keys = _noop
    open_settings = _noop

    def build(self, code: str) -> app_mod.FlowBar:
        set_language(code)
        for child in self.winfo_children():
            child.destroy()
        self._build_menus()
        self._build_toolbar()
        self.update_idletasks()
        return self.toolbar


def _texts(widget) -> list[tuple[str, str]]:
    found, stack = [], [widget]
    while stack:
        w = stack.pop()
        if w.winfo_class() in ("TButton", "TCheckbutton", "TRadiobutton"):
            found.append((w.winfo_class(), str(w.cget("text"))))
        stack.extend(w.winfo_children())
    return found


def _menu_labels(menu: tk.Menu) -> list[str]:
    """Every entry's label, the menus' own names among them."""
    labels = []
    for i in range(int(menu.index("end")) + 1):
        kind = menu.type(i)
        if kind == "cascade":
            labels.append(str(menu.entrycget(i, "label")))
            labels += _menu_labels(menu.nametowidget(menu.entrycget(i, "menu")))
        elif kind in ("command", "checkbutton", "radiobutton"):
            labels.append(str(menu.entrycget(i, "label")))
    return labels


def test_the_toolbar_flows_into_rows_and_shows_every_control_whole_in_every_language(hidden_root):
    w = Bars(hidden_root)
    rows = {}
    for code in UI_LANGUAGES:
        bar = w.build(code)
        for width in (820, 1180, 1366):
            for flowing in (bar, w.tools_bar):  # the toolbar, and translator mode's strip under it
                places = flowing.relayout(width)
                room = width - 2 * flowing._pad[0]
                for group, (x, _y) in zip(flowing.groups, places):
                    assert x + group.winfo_reqwidth() <= room, (code, width, [t for _k, t in _texts(group)])
                assert int(flowing.cget("height")) >= 24 * flowing.rows  # the bar is as tall as its rows
            rows[(code, width)] = bar.rows
        # one place each: no control of the toolbar or of the strip is in a menu too, and none shows twice
        labels = _menu_labels(w.menubar)
        shown = [text for _kind, text in _texts(bar) + _texts(w.tools_bar)]
        assert len(shown) == len(set(shown)) and len(labels) == len(set(labels)), code
        assert not {text.replace(" (F5)", "").replace(" (F11)", "") for text in shown} & set(labels), code
        assert not set(shown) & set(labels), code
    assert all(rows[(c, 1366)] <= rows[(c, 1180)] <= rows[(c, 820)] <= 3 for c in UI_LANGUAGES)
    assert sum(rows[(c, 1180)] == 1 for c in UI_LANGUAGES) > len(UI_LANGUAGES) / 2  # one row for most languages
    set_language("en")


def test_the_comboboxes_are_as_wide_as_their_longest_entry(hidden_root):
    w = Bars(hidden_root)
    for code in UI_LANGUAGES:
        w.build(code)
        font = tkfont.nametofont(str(w.lang_box.cget("font")) or "TkTextFont")
        widest = min(max(font.measure(v) for v in w.lang_box.cget("values")), 30 * font.measure("0"))
        assert int(w.lang_box.cget("width")) * font.measure("0") >= widest, code
    box = ttk.Combobox(hidden_root)
    app_mod.fit_combobox(box, ["qwen3.5:4b", "a-much-longer-model-name:latest"], min_chars=14)
    font = tkfont.nametofont(str(box.cget("font")) or "TkTextFont")
    assert int(box.cget("width")) * font.measure("0") >= font.measure("a-much-longer-model-name:latest") + 6
    app_mod.fit_combobox(box, ["x"], min_chars=14)
    assert int(box.cget("width")) == 14
    set_language("en")


def test_the_window_has_no_mode_box_and_each_choice_one_place(hidden_root):
    w = Bars(hidden_root)
    w.build("en")
    assert not hasattr(w, "mode_box") and not hasattr(w, "mode_var") and not hasattr(w, "_stop_entry")
    assert not hasattr(w, "model_box") and not hasattr(w, "_tool_entries") and w.model_var.get() == "qwen3.5:4b"
    assert all("Mode" not in text for _kind, text in _texts(w.toolbar))
    menus = {str(w.menubar.entrycget(i, "label")): w.menubar.nametowidget(w.menubar.entrycget(i, "menu"))
             for i in range(int(w.menubar.index("end")) + 1) if w.menubar.type(i) == "cascade"}
    assert list(menus) == ["Page", "Tools", "View", "Language", "Help"]
    assert _menu_labels(menus["Page"]) == ["Set area...", "Page keys...", "Ignore this area on all pages of this book",
                                         "Copy format", "Paste format", "Paste format on every region of this kind...",
                                         "Copy region", "Paste region", "Set kind...", "Set text size...",
                                         "Place in reading order..."]
    assert _menu_labels(menus["Tools"]) == ["Saved translations...", "Names rendered in more than one way...",
                                              "Settings..."]
    assert _menu_labels(menus["View"]) == ["Show original", "Always on top", "Over the full-screen viewer",
                                         "Reading-order numbers"]
    assert _menu_labels(menus["Help"]) == ["How to use...", "Keys...", "Legal notice...", "About TASlation"]
    shown = [text for _kind, text in _texts(w.toolbar)]
    assert sorted(shown) == sorted(["Translate (F5)", "Auto", "Reading mode (F11)", "Reader", "Translator",
                                    "Read whole book...", "Stop (Esc)"])
    set_language("en")


def test_translator_tools_follow_the_role_on_the_strip(hidden_root):
    w = Bars(hidden_root)
    w.build("en")
    assert not w._tool_strip.winfo_manager()  # the reader role: translator mode's strip is not there
    assert [str(b.cget("text")) for b in w.tool_btns] == [
        "Reading order", "Skip page", "Translate again", "Book settings...", "Series sheet...", "Review...",
        "Find and replace...", "Text direction (T)", "Undo (Ctrl+Z)", "Redo (Ctrl+Y)"]
    assert all(str(b.cget("state")) == "disabled" for b in w.tool_btns)
    w.role_var.set("translator")
    w._sync_tools()
    assert all(str(b.cget("state")) == "normal" for b in w.tool_btns)
    assert w._tool_strip.winfo_manager() == "pack" and w.hint_label.winfo_manager() == "pack"
    assert str(w.hint_label.cget("text")).startswith("Click: select · drag: move")
    w.role_var.set("reader")
    w._sync_tools()
    assert not w._tool_strip.winfo_manager()  # gone again with its hint
    assert w.translate_btn.cget("text") == "Translate (F5)"
    set_language("ja")
    assert _("Translate (F5)") == "翻訳 (F5)" and _("Translate again") == "訳し直す"
    w.role_var.set("translator")
    w.build("ja")  # built anew (a language switch) in the translator role: the strip is there at once
    assert w._tool_strip.winfo_manager() == "pack"
    assert str(w.hint_label.cget("text")) == ("クリックで選択・ドラッグで移動・ハンドルで大きさ変更・丸いハンドルで回転（Shift で 15° ずつ）・"
                                              "ダブルクリックか Enter で編集・Esc で選択解除・"
                                              "空いた所をドラッグで追加・Delete で削除・T で文字列の方向・Ctrl+Z で元に戻す・"
                                              "Ctrl+Y でやり直す・Tab で次の領域・Alt+矢印キーで 1px ずつ移動")
    w.role_var.set("reader")
    set_language("en")


def test_the_viewer_box_is_narrow_and_its_list_wide_enough_for_whole_titles(hidden_root):
    w = Bars(hidden_root)
    w.build("en")
    assert int(w.window_box.cget("width")) == app_mod.VIEWER_CHARS
    offset = ttk.Style(w).lookup(str(w.window_box.cget("style")), "postoffset")
    zero = tkfont.nametofont("TkTextFont").measure("0")
    assert int(str(offset).split()[2]) == (app_mod.VIEWER_LIST_CHARS - app_mod.VIEWER_CHARS) * zero


def test_the_target_languages_show_in_the_windows_language_and_stay_english(hidden_root):
    w = Bars(hidden_root)
    w.lang_var.set("German")
    w.build("ja")
    values = list(w.lang_box.cget("values"))
    assert len(values) == len(app_mod.LANGUAGES) == len(set(values)) and "英語" in values and "English" not in values
    assert w.lang_box.get() == "ドイツ語" and w.lang_var.get() == "German"
    w.lang_box.set("フランス語")  # chosen from the list
    assert w.lang_var.get() == "French"
    w.lang_shown.set("Klingon")  # typed: as it is
    assert w.lang_var.get() == "Klingon"
    w.lang_shown.set("Italian")  # an English name typed is the same language
    assert w.lang_var.get() == "Italian" and w.lang_box.get() == "Italian"
    w.lang_var.set("Korean")  # set by the window: the box follows
    assert w.lang_box.get() == "韓国語"
    assert app_mod.stored_target("ポルトガル語（ブラジル）") == "Portuguese (Brazil)"
    assert app_mod.shown_target("Klingon") == "Klingon"
    for code in UI_LANGUAGES:
        set_language(code)
        names = [app_mod.shown_target(language) for language in app_mod.LANGUAGES]
        assert len(set(names)) == 20, code
        assert [app_mod.stored_target(name) for name in names] == app_mod.LANGUAGES, code
    set_language("en")


# ------------------------------------------------------------------ the status line
class Line:
    status = app_mod.App.status
    say = app_mod.App.say

    def __init__(self, root):
        self.status_var = tk.StringVar(master=root)
        self.reading = False


def test_a_status_line_is_said_again_in_the_new_language(hidden_root):
    w = Line(hidden_root)
    w.say("Viewer: {title}", title="Yomizuq - Google Chrome")
    assert w.status_var.get() == "Viewer: Yomizuq - Google Chrome" and w._status_key == "Viewer: {title}"
    set_language("ja")
    assert w._status_render() == "ビューア: Yomizuq - Google Chrome"  # what _rebuild_ui puts back after a switch
    w.status("plain text from elsewhere")
    assert w._status_render is None and w._status_key is None
    set_language("en")


# ------------------------------------------------------------------ the window's size and place
class FakeTk:
    """What the geometry helpers ask of Tk, with idle callbacks run on demand."""

    _restore_geometry = app_mod.App._restore_geometry
    _current_geometry = app_mod.App._current_geometry
    _track_geometry = app_mod.App._track_geometry

    def __init__(self, geometry: str, state: str = "normal"):
        self._geometry, self._state = geometry, state
        self.reading, self._restoring, self._normal_geometry = False, False, geometry
        self.idle: list = []
        self.calls: list[tuple[str, str]] = []

    def geometry(self, new=None):
        if new is None:
            return self._geometry
        self.calls.append(("geometry", new))
        self._geometry = new

    def state(self, new=None):
        if new is None:
            return self._state
        self.calls.append(("state", new))
        self._state = new

    def after_idle(self, func):
        self.idle.append(func)

    def run_idle(self):
        while self.idle:
            self.idle.pop(0)()


def test_reading_mode_gives_the_window_back_its_size_and_place_after_tks_own_resizing():
    w = FakeTk("1180x920+1940+20")
    for _cycle in range(3):
        saved = w._current_geometry()
        assert saved == ("1180x920+1940+20", False)
        w._geometry = "1180x900+1940+20"  # the menu bar put back takes its 20 px from the inside, as Tk does
        w._restore_geometry(saved)
        assert w._restoring and w.geometry() == "1180x900+1940+20"  # not before Tk is done
        w.run_idle()
        assert w.geometry() == "1180x920+1940+20" and not w._restoring
    # maximised on the second monitor: full screen leaves it maximised on the first one; its place comes back
    # first, then it is maximised again there (on Windows that order puts it on the monitor of its place)
    w = FakeTk("1180x920+1940+20")
    w._track_geometry(SimpleNamespace(widget=w))
    w._state, w._geometry = "zoomed", "1920x989+1940+20"
    saved = w._current_geometry()
    assert saved == ("1180x920+1940+20", True)
    w._state, w._geometry = "zoomed", "1920x1009+0+0"
    w.calls.clear()
    w._restore_geometry(saved)
    w.run_idle()
    assert w.calls == [("state", "normal"), ("geometry", "1180x920+1940+20"), ("state", "zoomed")]
    assert not w._restoring
    w._track_geometry(SimpleNamespace(widget=w))  # maximised: its size and place before it are kept
    assert w._normal_geometry == "1180x920+1940+20"
    w.calls.clear()  # a language switch while maximised and nothing else: left as it is
    w._restore_geometry(saved, rezoom=False)
    w.run_idle()
    assert w.calls == []


class Reading(tk.Toplevel):
    """Reading mode in and out on a withdrawn window of the hidden root (full screen is only recorded)."""

    _enlarge_first = lambda self, then=None: True  # (the window enlarged: tests/test_enlarge.py)
    enter_reading = app_mod.App.enter_reading
    leave_reading = app_mod.App.leave_reading
    status = app_mod.App.status
    say = app_mod.App.say
    _normal_status = app_mod.App._normal_status
    _restore_geometry = app_mod.App._restore_geometry
    _current_geometry = app_mod.App._current_geometry
    _window_monitor = app_mod.App._window_monitor
    _onto_monitor = app_mod.App._onto_monitor
    _area_offer_due = app_mod.App._area_offer_due
    _set_covered = app_mod.App._set_covered
    _watch_top_edge = app_mod.App._watch_top_edge
    _top_edge_moved = app_mod.App._top_edge_moved
    _top_edge_left = app_mod.App._top_edge_left
    _show_close = app_mod.App._show_close
    _hide_close = app_mod.App._hide_close
    _close_clicked = app_mod.App._close_clicked
    _ask_name_after_reading = app_mod.App._ask_name_after_reading

    def __init__(self, root):
        super().__init__(root)
        self.withdraw()
        self.attrs = {"-alpha": 0.99, "-fullscreen": 0}
        self.menubar = tk.Menu(self)
        self.config(menu=self.menubar)
        self.bar = ttk.Frame(self)
        self.bar.pack(fill="x")
        self._bars = (self.bar,)
        self.canvas = ImageCanvas(self)
        self.canvas.pack(fill="both", expand=True)
        self.status_bar = ttk.Frame(self)
        self.status_bar.pack(fill="x")
        self.notes_label = ttk.Label(self)
        self.status_var = tk.StringVar(self)
        self.original_var, self.auto_var, self.top_var = tk.BooleanVar(self), tk.BooleanVar(self), tk.BooleanVar(self)
        self.selected, self.last_result = VIEWER, None
        self.reading = self._batching = self._viewer_hidden = self._scan_waits_told = self._restoring = False
        self._ordering = self._chosen_region = self._status_render = self._status_key = None
        self._normal_geometry = ""
        self._manual_area = True  # an area of the reader's: Set area... is not offered first
        self._covered = False
        self.alphas: list[float] = []  # every alpha the window was given, in turn

    def attributes(self, *args):
        if len(args) == 1:
            return self.attrs.get(args[0], 0)
        self.attrs[args[0]] = args[1]
        if args[0] == "-alpha":
            self.alphas.append(args[1])

    def _own_hwnd(self):  # not on a screen: no monitor to go to
        return None

    def _apply_on_top(self):
        pass

    def _redisplay(self):
        pass

    def _show_notes(self):
        pass

    def _result_on_show(self):
        return False

    def _on_escape(self):
        pass


def test_leaving_reading_mode_puts_back_the_place_and_the_normal_status(hidden_root):
    w = Reading(hidden_root)
    w.geometry("640x480+2000+40")
    w.update_idletasks()
    w.say("Viewer: {title}", title=VIEWER.title)
    w.auto_var.set(True)  # (Auto on already: the plain first line, tests/test_reading_flow.py has the other)
    for _cycle in range(3):
        w.enter_reading()
        assert w.reading and w.attrs["-fullscreen"] is True and str(w.cget("menu")) == ""
        assert w.status_var.get() == "Reading mode: page keys turn the viewer's pages; F11 or Esc leaves it."
        w.leave_reading()
        assert not w.reading and w.attrs["-fullscreen"] is False and str(w.cget("menu")) == str(w.menubar)
        assert w.status_var.get() == "Viewer: " + VIEWER.title  # not the reading window's line any more
        w.geometry("640x460+0+0")  # what Tk might leave meanwhile
        w.update_idletasks()  # the idle callbacks: the size and place come back after Tk's own resizing
        assert w.geometry() == "640x480+2000+40" and not w._restoring


def test_reading_mode_rests_show_original_and_gives_it_back(hidden_root):
    """Show original is in a menu, and the reading window has none: left on, it would show originals with no way back."""
    w = Reading(hidden_root)
    w.original_var.set(True)
    w.enter_reading()
    assert w.reading and not w.original_var.get()  # the translation, as in reading mode
    w.leave_reading()
    assert not w.reading and w.original_var.get()  # as the reader had it
    w.original_var.set(False)
    w.enter_reading()
    w.leave_reading()
    assert not w.original_var.get()


def test_the_first_size_fits_the_work_area_and_sits_in_its_middle(monkeypatch):
    for screen, work, expected in (((1366, 768), (0, 0, 1366, 728), "1180x669+85+0"),
                                   ((1920, 1080), (0, 0, 1920, 1032), "1180x920+362+26"),
                                   ((1024, 600), (0, 0, 1024, 560), "984x501+12+0")):
        monkeypatch.setattr(layout, "work_area", lambda _w, x=None, y=None, work=work: work)
        monkeypatch.setattr(layout, "frame_extents", lambda: (8, 31))
        widget = SimpleNamespace(winfo_screenwidth=lambda s=screen: s[0], winfo_screenheight=lambda s=screen: s[1])
        geometry = app_mod.initial_geometry(widget)
        assert geometry == expected, (screen, geometry)
        width, height = (int(v) for v in geometry.split("+")[0].split("x"))
        assert width <= screen[0] - 40 and height <= screen[1] - 90


class Dialog:
    """What place_window asks of a dialog and of its parent."""

    def __init__(self, size=(400, 300), viewable=True, root=(0, 0, 0, 0)):
        self.size, self.viewable, self.root = size, viewable, root
        self.placed, self.shown = None, True

    def state(self):
        return "normal" if self.shown else "withdrawn"

    def withdraw(self):
        self.shown = False

    def deiconify(self):
        self.shown = True

    def update_idletasks(self):
        pass

    def wm_geometry(self):
        return f"{self.size[0]}x{self.size[1]}+0+0"

    def geometry(self, value):
        self.placed = value

    def winfo_viewable(self):
        return self.viewable

    def winfo_rootx(self):
        return self.root[0]

    def winfo_rooty(self):
        return self.root[1]

    def winfo_width(self):
        return self.root[2]

    def winfo_height(self):
        return self.root[3]


def test_dialogs_open_over_their_parent_and_stay_on_its_monitor(monkeypatch):
    monkeypatch.setattr(layout, "work_area", lambda _w, x=None, y=None: (1920, 0, 3840, 1032) if x is None or x >= 1920
                        else (0, 0, 1920, 1032))
    monkeypatch.setattr(layout, "frame_extents", lambda: (8, 31))
    parent = Dialog(root=(2000, 100, 1180, 900))
    d = Dialog()
    app_mod.place_window(d, parent)
    assert d.placed == f"+{2000 + 590 - 208}+{100 + 450 - 169}" and d.shown  # centred over the window
    parent = Dialog(root=(3500, 900, 300, 100))  # near the corner of the second monitor: moved onto it
    app_mod.place_window(d, parent)
    assert d.placed == f"+{3840 - 416}+{1032 - 339}"
    hidden = Dialog(viewable=False)
    d.placed = None
    app_mod.place_window(d, hidden)  # a parent not on the screen (the tests' root): left as Tk puts it
    assert d.placed is None
    d = Dialog()
    app_mod.place_window(d)  # no parent: the middle of the primary monitor's work area
    assert d.placed == f"+{2880 - 208}+{516 - 169}"


class Placed(Dialog):
    """A dialog whose topmost flag is seen, of a window that has a viewer chosen."""

    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app, self.topmost = app, False

    def _root(self):
        return self.app

    def attributes(self, name, value):
        assert name == "-topmost"
        self.topmost = value


@pytest.fixture
def two_monitors(monkeypatch):
    """The window (hwnd 100) on the first monitor, the viewer (hwnd 500) full screen on the second."""
    state = SimpleNamespace(viewer=(1920, 0, 3840, 1080), own=(0, 0, 1920, 1080), front="viewer", given=[])
    monkeypatch.setattr(layout, "IS_WINDOWS", True)
    monkeypatch.setattr(layout, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(layout, "monitor_rect", lambda hwnd: state.viewer if hwnd == 500 else state.own)
    monkeypatch.setattr(layout, "work_area", lambda _w, x=None, y=None: (1920, 0, 3840, 1032) if x is not None and x >= 1920
                        else (0, 0, 1920, 1032))
    monkeypatch.setattr(layout, "frame_extents", lambda: (8, 31))
    monkeypatch.setattr(layout, "foreground_window", lambda: 1)
    monkeypatch.setattr(layout, "foreground_owner", lambda front, viewer: state.front)
    monkeypatch.setattr(layout, "give_foreground", lambda hwnd: state.given.append(hwnd) or True)
    return state


def test_a_dialog_comes_where_the_reader_reads_on_the_books_monitor_and_above_it(two_monitors):
    app = SimpleNamespace(selected=SimpleNamespace(hwnd=500), _own_hwnd=lambda: 100)
    parent = Placed(app, root=(362, 26, 1180, 920))
    d = Placed(app)
    assert layout.place_by_book(d, parent)
    assert d.placed == f"+{2880 - 208}+{540 - 169}" and d.topmost  # the middle of the book's monitor, topmost
    two_monitors.own = two_monitors.viewer  # the window over the book: over the window, as ever
    d = Placed(app)
    assert not layout.place_by_book(d, parent) and not d.topmost
    assert d.placed == f"+{362 + 590 - 208}+{26 + 460 - 169}"
    app.selected = None  # no viewer chosen yet
    assert not layout.place_by_book(Placed(app), parent)


def test_a_dialog_nobody_asked_for_takes_no_key_from_the_book_and_gives_it_back_after(hidden_root, two_monitors,
                                                                                     monkeypatch):
    monkeypatch.setattr(hidden_root, "selected", SimpleNamespace(hwnd=500), raising=False)
    forced = []
    for front, wanted in (("viewer", []), ("other", []), ("own", ["force"])):
        two_monitors.front = front
        dialog = tk.Toplevel(hidden_root)
        dialog.withdraw()
        dialog.focus_force = lambda: forced.append("force")
        layout.dialog_keys(dialog, hidden_root)
        assert forced == wanted, front  # the keys only when TASlation had them
        forced.clear()
        two_monitors.front = "own"  # the reader clicked the dialog (or was in TASlation)
        dialog.destroy()
        assert two_monitors.given == ([500] if front == "viewer" else []), front  # back to the book, if from there
        two_monitors.given.clear()


# ------------------------------------------------------------------ the page panel in the viewer's frames
def _framed(size=(960, 540), box=(150, 44, 810, 520), level=32, seed=1):
    """A capture of a reader in a browser: a dark frame around a white page with panels and lettering."""
    img = Image.new("RGB", size, (level, level, level))
    d = ImageDraw.Draw(img)
    d.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=(250, 250, 250))
    rnd = random.Random(seed)
    for _i in range(60):
        x, y = rnd.randint(box[0] + 20, box[2] - 80), rnd.randint(box[1] + 20, box[3] - 40)
        d.rectangle((x, y, x + rnd.randint(8, 60), y + rnd.randint(3, 20)), fill=(20, 20, 20))
    d.rectangle((box[0] + 10, box[1] + 10, box[2] - 11, box[3] - 11), outline=(0, 0, 0), width=3)
    return img


def _browser(size=(960, 600), page=(200, 130, 760, 560), bars=85):
    """A capture of a browser-based viewer in a browser: the tab strip and the address bar (light) above the reader
    (dark), whose own header line, its "ライブラリ" and "さらに読む" links and its page slider with "1/200ページ・0%"
    lie around the page."""
    img = _framed(size, page)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, size[0] - 1, 39), fill=(222, 222, 222))  # the tab strip
    d.rectangle((0, 40, size[0] - 1, bars - 1), fill=(250, 250, 250))  # the address bar ...
    for x in range(120, 520, 14):
        d.rectangle((x, 56, x + 8, 66), fill=(60, 60, 60))  # ... and the address
    for x in (*range(20, 80, 12), *range(380, 560, 12), *range(840, 920, 12)):  # the links, the title line
        d.rectangle((x, 98, x + 7, 110), fill=(200, 200, 200))
    d.rectangle((40, 584, 920, 586), fill=(150, 150, 150))  # the page slider ...
    for x in range(800, 900, 10):
        d.rectangle((x, 570, x + 6, 579), fill=(200, 200, 200))  # ... and its page count
    return img


class Viewer(BlackViewerMixin):
    _enlarge_first = lambda self, then=None: True  # (the window enlarged: tests/test_enlarge.py)
    _capture = app_mod.App._capture
    _resizing = app_mod.App._resizing
    _find_page = app_mod.App._find_page
    _found_margins = app_mod.App._found_margins
    _apply_found_margins = app_mod.App._apply_found_margins
    _hand_set = app_mod.App._hand_set
    _inner_margins = app_mod.App._inner_margins
    _area_hint_due = app_mod.App._area_hint_due
    set_area = app_mod.App.set_area
    clear_area = app_mod.App.clear_area
    _area_chosen = app_mod.App._area_chosen
    _look_soon = app_mod.App._look_soon
    _follows_events = app_mod.App._follows_events
    say = app_mod.App.say

    def __init__(self, manual=None):
        self.settings = Settings()
        self.settings.margins = manual or (0, 0, 0, 0)
        self.selected, self.reading, self.busy, self.ready = VIEWER, False, False, False
        self._manual_area, self._page_areas, self._area_hinted = manual is not None, {}, False
        self._hand_area, self._inner_areas = manual, {}
        self.profiles = SimpleNamespace(set_margins=lambda title, margins, large=False: None)
        self.statuses: list[str] = []
        self.frame = _framed()

    def _covers_viewer(self, hwnd):
        return False

    def _set_covered(self, covered):
        pass

    def _current_window(self):
        return self.selected

    def status(self, text):
        self.statuses.append(text() if callable(text) else text)


@pytest.fixture
def viewer(monkeypatch):
    w = Viewer()
    monkeypatch.setattr(live, "capture_window", lambda hwnd, client_only=True, allow_screen_fallback=True: w.frame)
    return w


def test_the_page_panel_found_in_a_capture_becomes_the_capture_area(viewer):
    image = viewer._capture(VIEWER.hwnd)
    assert image is viewer.frame
    assert tuple(viewer.settings.margins) == (150, 44, 150, 20)  # the whole window less the frame
    assert viewer.settings.with_overrides(next_page_key="Left").margins == (150, 44, 150, 20)  # the batch's too
    assert not viewer._area_hint_due()  # found: no hint


def test_a_hand_set_area_is_the_outer_bound_and_the_page_panel_inside_it_is_read(monkeypatch):
    """An area set months ago trims only the browser's bars: the reader's own header, links and page slider are inside
    it. The page panel found inside it is read (what the two have in common), the area itself stays the reader's;
    a frame where nothing is found changes nothing; Clear area goes back to the panel found on the whole capture."""
    w = Viewer(manual=(0, 85, 0, 0))
    w.frame = _browser()
    monkeypatch.setattr(live, "capture_window", lambda hwnd, **_k: w.frame)
    w._capture(VIEWER.hwnd)
    assert tuple(w.settings.margins) == (200, 130, 200, 40) and w._hand_area == (0, 85, 0, 0)
    assert tuple(w.settings.with_overrides(next_page_key="Left").margins) == (200, 130, 200, 40)  # the batch's too
    assert not w._page_areas and not w._area_hint_due()  # nothing looked for on the whole capture meanwhile
    w.frame = Image.new("RGB", (960, 600), "white")  # nothing found on this one (a panel over the page)
    w._capture(VIEWER.hwnd)
    assert tuple(w.settings.margins) == (200, 130, 200, 40)
    w.clear_area()  # no area of the reader's: the panel found on the whole capture alone, as before
    assert tuple(w.settings.margins) == (0, 0, 0, 0) and w._hand_area is None
    w.frame = _framed()
    w._capture(VIEWER.hwnd)
    assert tuple(w.settings.margins) == (150, 44, 150, 20)


def test_a_tight_hand_set_area_stays_and_one_with_nothing_inside_is_read_whole(monkeypatch):
    for tight in ((200, 130, 200, 40), (197, 127, 197, 37), (202, 132, 202, 42)):  # drawn around the page
        w = Viewer(manual=tight)
        w.frame = _browser()
        monkeypatch.setattr(live, "capture_window", lambda hwnd, w=w, **_k: w.frame)
        w._capture(VIEWER.hwnd)
        assert tuple(w.settings.margins) == tight, tight  # the panel found is the area within a few px: as it is
    w = Viewer(manual=(0, 85, 0, 0))
    w.frame = Image.new("RGB", (960, 600), "white")  # no page panel in it at all
    monkeypatch.setattr(live, "capture_window", lambda hwnd, **_k: w.frame)
    w._capture(VIEWER.hwnd)
    assert tuple(w.settings.margins) == (0, 85, 0, 0)
    assert live.panel_inside(_browser(), (188, 118, 772, 572)) == (200, 130, 760, 560)  # 12 px of the frame: read


def test_the_panels_found_inside_the_area_join_and_a_new_area_or_size_starts_over(monkeypatch):
    w = Viewer(manual=(0, 85, 0, 0))
    w.frame = _browser()
    monkeypatch.setattr(live, "capture_window", lambda hwnd, **_k: w.frame)
    found = [(300, 45, 660, 475)]  # in the area's pixels: a cover alone, then a spread
    monkeypatch.setattr(page_area, "find_page_area", lambda image: found[0])  # (what `panel_inside` looks with)
    w._capture(VIEWER.hwnd)
    assert tuple(w.settings.margins) == (300, 130, 300, 40)
    found[0] = (200, 50, 760, 475)
    w._capture(VIEWER.hwnd)
    assert tuple(w.settings.margins) == (200, 130, 200, 40)  # the union: nothing one capture showed is cut
    w.busy = True  # a panel found in the middle of a job waits for its end
    found[0] = (100, 40, 860, 480)
    w._capture(VIEWER.hwnd)
    assert tuple(w.settings.margins) == (200, 130, 200, 40)
    w.busy = False
    w._apply_found_margins()
    assert tuple(w.settings.margins) == (100, 125, 100, 35)
    w._area_chosen((0, 100, 960, 600), (960, 600))  # another area of the reader's: from scratch
    assert tuple(w.settings.margins) == (0, 100, 0, 0) and w._hand_area == (0, 100, 0, 0)
    found[0] = (200, 30, 760, 460)
    w._capture(VIEWER.hwnd)
    assert tuple(w.settings.margins) == (200, 130, 200, 40)
    w.frame = _browser(size=(1000, 600))  # the window was resized: from scratch too
    found[0] = None
    w._capture(VIEWER.hwnd)
    assert tuple(w.settings.margins) == (0, 100, 0, 0)


def test_the_found_boxes_join_and_a_new_size_starts_over(viewer, monkeypatch):
    found = [(300, 44, 660, 520)]  # a cover alone, then the spreads after it
    monkeypatch.setattr(live, "find_page_area", lambda image: found[0])
    viewer._capture(VIEWER.hwnd)
    assert tuple(viewer.settings.margins) == (300, 44, 300, 20)
    found[0] = (150, 50, 810, 520)
    viewer._capture(VIEWER.hwnd)
    assert tuple(viewer.settings.margins) == (150, 44, 150, 20)  # the union: nothing one capture showed is cut
    found[0] = None  # nothing found on this one (an end-of-book panel): the area stays
    viewer._capture(VIEWER.hwnd)
    assert tuple(viewer.settings.margins) == (150, 44, 150, 20)
    viewer.busy = True  # a page found in the middle of a job waits for its end
    found[0] = (100, 40, 860, 530)
    viewer._capture(VIEWER.hwnd)
    assert tuple(viewer.settings.margins) == (150, 44, 150, 20)
    viewer.busy = False
    viewer._apply_found_margins()
    assert tuple(viewer.settings.margins) == (100, 40, 100, 10)
    viewer.frame = _framed(size=(1000, 600))  # the window was resized: from scratch
    found[0] = None
    viewer._capture(VIEWER.hwnd)
    assert tuple(viewer.settings.margins) == (0, 0, 0, 0) and viewer._area_hint_due()  # nothing yet: the hint
    found[0] = (100, 50, 900, 580)
    viewer._capture(VIEWER.hwnd)
    assert tuple(viewer.settings.margins) == (100, 50, 100, 20)


def test_set_area_starts_from_the_page_found(viewer, monkeypatch):
    opened = []
    monkeypatch.setattr(viewers, "AreaDialog",
                        lambda master, image, callback, margins, inner=None, clear=None: opened.append(margins))
    viewer.set_area()
    assert opened == [(150, 44, 150, 20)]
    w = Viewer(manual=(0, 85, 0, 0))  # an area of the reader's: the dialog starts from it, not from what is read of it
    w.frame = _browser()
    monkeypatch.setattr(live, "capture_window", lambda hwnd, **_k: w.frame)
    dialogs = []
    monkeypatch.setattr(viewers, "AreaDialog", lambda master, image, callback, margins, inner=None, clear=None: dialogs.append(
        (margins, inner)))
    w.set_area()
    ((margins, inner),) = dialogs
    assert margins == (0, 85, 0, 0) and tuple(w.settings.margins) == (200, 130, 200, 40)
    assert inner((0, 85, 960, 600)) == (200, 130, 760, 560) and inner((200, 130, 760, 560)) is None  # what is read
    assert "address bar" in _("Drag the handles to resize the area, drag inside it to move it, or drag elsewhere to draw a new one. Keep only the page inside it: the browser's tabs and address bar would otherwise be read as part of the page. Enter = use it, Esc = cancel.")


def test_clear_area_is_a_button_of_the_set_area_dialog(hidden_root, viewer, monkeypatch):
    opened = []
    monkeypatch.setattr(viewers, "AreaDialog", lambda master, image, callback, margins, inner=None, clear=None:
                        opened.append(clear))
    viewer._manual_area, viewer._hand_area = True, (10, 10, 10, 10)
    viewer.set_area()
    opened[0]()  # what the button does: no area of the reader's, the page found again
    assert not viewer._manual_area and viewer._hand_area is None
    left = []
    viewer.after = lambda ms, then: left.append(then)
    viewer.set_area(then=lambda: left.append("reading"))
    opened[1]()  # reading mode offered the area first: it opens after this too
    assert len(left) == 1 and left[0]() is None and left[-1] == "reading"

    cleared = []
    d = app_mod.AreaDialog(hidden_root, _browser(), lambda box, size: pytest.fail("not chosen"), clear=lambda: cleared.append(1))
    d.withdraw()
    buttons = [w for w in d.winfo_children()[1].winfo_children() if w.winfo_class() == "TButton"]
    next(b for b in buttons if str(b.cget("text")) == "Clear area").invoke()
    assert cleared == [1] and not d.winfo_exists()
    d = app_mod.AreaDialog(hidden_root, _browser(), lambda box, size: None)  # no *clear*: no button
    d.withdraw()
    assert "Clear area" not in [str(b.cget("text")) for b in d.winfo_children()[1].winfo_children() if b.winfo_class() == "TButton"]
    d.destroy()


def test_the_area_dialog_shows_the_page_panel_found_inside_the_area_dashed(hidden_root):
    image = _browser()
    d = app_mod.AreaDialog(hidden_root, image, lambda box, size: None, (0, 85, 0, 0),
                           inner=lambda box: live.panel_inside(image, box))
    try:
        d.withdraw()
        _sized(d.canvas, 960 + 2 * area.HANDLE, 600 + 2 * area.HANDLE).set_image(image)  # one canvas px per image px
        assert d.inner_box == (200, 130, 760, 560) and len(d.canvas.find_withtag("area-inner")) == 1
        (item,) = d.canvas.find_withtag("area-inner")
        assert d.canvas.itemcget(item, "dash") != "" and d.canvas.coords(item) == [
            200 + area.HANDLE, 130 + area.HANDLE, 760 + area.HANDLE, 560 + area.HANDLE]
        d._press(SimpleNamespace(x=area.HANDLE + 960, y=area.HANDLE + 600))  # the bottom-right handle, dragged ...
        d._drag(SimpleNamespace(x=area.HANDLE + 900, y=area.HANDLE + 590))
        assert not d.canvas.find_withtag("area-inner")  # (not shown while it moves)
        d._release(SimpleNamespace(x=area.HANDLE + 900, y=area.HANDLE + 590))
        assert d.box == (0, 85, 900, 590) and d.inner_box == (200, 130, 760, 560)  # ... found again inside it
        assert len(d.canvas.find_withtag("area-inner")) == 1
        d.box = (199, 129, 761, 561)  # drawn tightly around the page: the area itself is read, nothing dashed
        d._find_inner()
        d._draw()
        assert d.inner_box is None and not d.canvas.find_withtag("area-inner")
        d.box = (0, 0, 960, 600)  # the whole window: the page panel in it
        d._find_inner()
        d._draw()
        assert d.inner_box == (200, 130, 760, 560) and len(d.canvas.find_withtag("area-inner")) == 1
    finally:
        d.destroy()


# ------------------------------------------------------------------ the canvas
class Empty:
    _redisplay = app_mod.App._redisplay

    def __init__(self, root):
        self.canvas = _sized(ImageCanvas(root))
        self.reading = self._viewer_hidden = False
        self.selected = None
        self.settings = SimpleNamespace(margins=(0, 0, 0, 0))

    def _picture(self):
        return None, [], []


def test_with_no_viewer_the_canvas_says_what_to_do(hidden_root):
    w = Empty(hidden_root)
    set_language("ja")
    try:
        w._redisplay()
        items = w.canvas.find_withtag("hint")
        shown = w.canvas.itemcget(items[0], "text")
        assert items and re.sub(r"\s", "", shown) == re.sub(r"\s", "", i18n.JA[app_mod.NO_VIEWER])
        font = tkfont.Font(font=w.canvas.itemcget(items[0], "font"))
        assert w.canvas.itemcget(items[0], "fill") == "#ffffff" and shown.count("\n") >= 1  # broken into lines ...
        assert all(font.measure(line) <= 400 - 80 for line in shown.split("\n"))  # ... that fit the canvas
        assert "TASlation" in shown  # never broken inside
    finally:
        set_language("en")
    w.selected = VIEWER  # a viewer is chosen: its picture comes instead
    w._redisplay()
    assert not w.canvas.find_withtag("hint") and w.canvas.hint == ""


def test_translator_labels_and_handles_read_on_white_and_on_black(hidden_root):
    c = _sized(ImageCanvas(hidden_root))
    c.overlay = [((20, 20, 120, 90), "#3ddc84", "1"), ((150, 30, 260, 120), "#ff5e5e", "?")]
    c.set_image(Image.new("RGB", (400, 300), "white"))
    texts = c.find_withtag("overlay-label")
    boxes = c.find_withtag("overlay-label-box")
    assert len(texts) == len(boxes) == 2
    for t, b in zip(texts, boxes):
        assert c.itemcget(t, "fill") == "#ffffff" and c.itemcget(b, "fill") == "#202020"
        size = tkfont.Font(font=c.itemcget(t, "font")).actual("size")
        assert abs(size) >= 11
        assert c.find_all().index(t) > c.find_all().index(b)  # the text over its box
    c.draw_frame((50, 50, 150, 120), "chosen", colour="#ffd400")
    items = c.find_withtag("chosen")
    # two-tone: a dark stroke 4 px wide under the yellow one, 2 px
    assert len(items) == 2 + 8 and float(c.itemcget(items[1], "width")) == 2
    assert c.itemcget(items[0], "outline") == "#202020" and float(c.itemcget(items[0], "width")) == 4
    for handle in items[2:]:
        x0, y0, x1, y1 = c.coords(handle)
        assert (x1 - x0, y1 - y0) == (area.HANDLE, area.HANDLE)
        assert c.itemcget(handle, "fill") == "#ffd400" and c.itemcget(handle, "outline") == "#202020"


# ------------------------------------------------------------------ the notice wrapped by hand
def _measure(text: str) -> int:  # a fixed-width stand-in for a font: 7 px a character, 14 for a wide one
    return sum(14 if app_mod.is_cjk(ch) else 7 for ch in text)


def test_lines_break_between_words_and_cjk_characters_never_inside_a_latin_run():
    text = "TASlation は、お使いのビューアで開いている本のページを、日本語の文字を機械翻訳に置き換えて表示します。§ 184b StGB と Art. 47-4 も同じです。"
    for width in range(70, 420, 7):  # from the widest run that must not break, "Art. 47-4"
        lines = app_mod.wrap_line(text, width, _measure)
        assert "".join(lines) == text  # nothing lost, nothing added
        assert all(_measure(line.rstrip(" ")) <= width for line in lines), width
        joined = "\n".join(lines)
        for run in ("TASlation", "§ 184b", "Art. 47-4", "StGB"):
            assert joined.count(run) == text.count(run), (width, run)
        assert not any(line.startswith(("、", "。")) for line in lines)  # no comma or full stop starts a line
    words = "Ollama runs on this computer; nothing leaves it unless you share it yourself."
    lines = app_mod.wrap_line(words, 140, _measure)
    assert "".join(lines) == words and all(line.endswith(" ") or line == lines[-1] for line in lines)
    assert app_mod.wrap_line("", 100, _measure) == [""]
    assert app_mod.wrap_line("x" * 30, 70, _measure) == ["x" * 10] * 3  # a run longer than a line: by characters
    assert [len(p) for p in app_mod.wrap_text("one\n\ntwo", 100, _measure)] == [1, 1, 1]


def test_thai_breaks_at_its_spaces_and_never_inside_a_letter_with_its_marks():
    """Thai has no spaces between words: a line breaks at the spaces between its clauses, and a clause too long for a
    line is cut at a syllable where the spelling shows one, a mark never starting a line."""
    clauses = "ไม่พบเนื้อหาหน้า กรุณาตรวจสอบหน้าต่างโปรแกรมอ่าน แล้วกดปุ่มอีกครั้ง"
    assert app_mod.wrap_line(clauses, 300, _measure) == ["ไม่พบเนื้อหาหน้า ", "กรุณาตรวจสอบหน้าต่างโปรแกรมอ่าน ", "แล้วกดปุ่มอีกครั้ง"]
    one_run = "ผู้ปั้นกี่ที่นี้" * 6 + "ไม่ฟุ้งซ่านเกิดแล้วปู่" * 4
    for width in (50, 77, 120, 200):
        lines = app_mod.wrap_line(one_run, width, _measure)
        assert "".join(lines) == one_run and len(lines) > 1
        for line in lines:
            assert not wrap._joined(line[0]) and line[-1] not in wrap.THAI_LEADING_VOWELS, (width, line)
    assert app_mod.wrap_line("ก่อนหน้า" * 6 + "เกิด", 350, _measure) == ["ก่อนหน้า" * 6, "เกิด"]  # a syllable starts at เ
    assert app_mod.wrap_line("หลาย ๆ อย่าง", 49, _measure) == ["หลาย ๆ ", "อย่าง"]  # mai yamok stays with its word
    assert wrap._cut("ก" * 5, 3) == 3


def test_the_notice_fits_its_box_keeps_its_runs_and_sets_the_heading_in_bold(tmp_path, monkeypatch, hidden_root):
    monkeypatch.setattr(notice, "default_country", lambda: None)
    d = app_mod.NoticeDialog(hidden_root, tmp_path, "ja")
    d.withdraw()
    width = int(d.text.cget("width")) * d._font.measure("0")
    for lang, country in (("ja", "JP"), ("zh", "OTHER"), ("ko", "KR"), ("de", "DE"), ("en", "GB"), ("ru", "US")):
        d.language, d.country = lang, country if country in d._countries else jurisdictions.OTHER
        d._render()
        full = notice.full_text(lang, d.country)
        assert shown_text(d) == full and str(d.text.cget("wrap")) == "none"
        shown = d.text.get("1.0", "end-1c")
        for run in ("TASlation", "Ollama", "§ 184b"):
            assert shown.count(run) == full.count(run), (lang, run)  # never broken in two
        for number, line in enumerate(shown.split("\n"), start=1):
            font = d._bold if "heading" in d.text.tag_names(f"{number}.0") else d._font
            assert font.measure(line.rstrip(" ")) <= width, (lang, number)
        heading = notice.country_heading(d.country, lang) if hasattr(notice, "country_heading") else None
        if heading:
            first = d.text.tag_ranges("heading")
            assert first and d.text.get(first[0], first[1]).replace("\n", "") == heading
            assert d._bold.actual("weight") == "bold"
    for button in (d.ok_btn, d.leave_btn):  # room around the text, the button as wide as it needs
        padding = button.cget("padding")
        assert tuple(int(str(v)) for v in (padding.split() if isinstance(padding, str) else padding)) == (12, 1)
    assert d.resizable() == (False, False)


# ------------------------------------------------------------------ the Caches, passphrase and region dialogs
def _store_with_a_cache(tmp_path):
    from taslation.cache import CacheStore

    store = CacheStore(tmp_path / "cache")
    cache = store.open("A rather long book title, volume 12", "qwen3.5:4b", "German")
    cache.save()
    return store


@pytest.mark.parametrize("code", ["de", "ru"])
def test_the_caches_dialog_takes_the_size_of_its_content(tmp_path, hidden_root, code):
    store = _store_with_a_cache(tmp_path)
    set_language(code)
    try:
        d = app_mod.CachesDialog(hidden_root, store)
        d.withdraw()
        d.update_idletasks()
        assert not d.wm_geometry().startswith("760x520")  # no fixed size
        head = tkfont.nametofont("TkHeadingFont")
        for column in ("#0", "pages", "bubbles", "language", "updated"):
            heading = str(d.tree.heading(column, "text"))
            assert int(d.tree.column(column, "width")) >= head.measure(heading) + 20, (code, heading)
        item = d.tree.get_children()[0]
        assert d.tree.set(item, "language") == "German" and tuple(d.tree.cget("columns")) == ("pages", "bubbles", "language", "updated")
        assert tuple(d.notes_tree.cget("columns") if hasattr(d, "notes_tree") else ()) in ((), ("language", "volumes", "updated"))
        assert not hasattr(d, "path_var") and not hasattr(d, "notes_path_var")  # Open folder shows where the files are
        assert not [c for c in d._frame.winfo_children() if c.winfo_class() == "TScrollbar"]
        d.tree.selection_set(item)
        d._sync_buttons()
        tree_width = sum(int(d.tree.column(c, "width")) for c in ("#0", "pages", "bubbles", "language", "updated"))
        for label in d._explanations:
            assert 0 < int(str(label.cget("wraplength"))) <= tree_width
        d.destroy()
    finally:
        set_language("en")


def test_each_import_failure_says_what_went_wrong(monkeypatch):
    for name in ("WrongPassphrase", "BrokenPassphrase", "UnreadableExport", "TooLarge"):
        monkeypatch.setattr(backup, name, type(name, (backup.BackupError,), {}), raising=False)
    monkeypatch.setattr(backup, "NameClash", type("NameClash", (FileExistsError,), {}), raising=False)
    said = {name: app_mod.import_error_text(getattr(backup, name)("x"))
            for name in ("WrongPassphrase", "BrokenPassphrase", "UnreadableExport", "TooLarge", "NameClash")}
    assert said["WrongPassphrase"] == "Wrong passphrase or damaged file."
    assert said["BrokenPassphrase"].startswith("The passphrase holds a broken or control character")
    assert said["UnreadableExport"].startswith("This file was written by a newer version of TASlation")
    assert said["TooLarge"].startswith("The file is larger than TASlation reads")
    assert said["NameClash"].startswith("Not imported: the file for this book already holds another book's")
    assert len(set(said.values())) == 5
    assert app_mod.import_error_text(backup.BackupError("damaged file")).startswith("Could not import: the file is damaged")
    monkeypatch.delattr(backup, "WrongPassphrase")  # an older backup module names no causes: the likeliest one
    assert app_mod.import_error_text(backup.BackupError("x")) == "Wrong passphrase or damaged file."


def test_the_passphrase_dialog_asks_backup_and_names_a_broken_character(hidden_root, monkeypatch):
    broken = type("BrokenPassphrase", (backup.BackupError,), {})
    monkeypatch.setattr(backup, "BrokenPassphrase", broken, raising=False)
    asked = []

    def check(passphrase):
        asked.append(passphrase)
        if "\x07" in passphrase:
            raise broken("a control character")
        if len(passphrase) < backup.MIN_PASSPHRASE:
            raise backup.BackupError("too short")

    monkeypatch.setattr(backup, "check_passphrase", check)
    d = app_mod.PassphraseDialog(hidden_root, confirm=True)
    d.vars[0].set("a long passphrase\x07")
    d.vars[1].set("a long passphrase\x07")
    assert asked and str(d.ok_btn.cget("state")) == "disabled"
    assert d.hint_var.get() == "The passphrase holds a broken or control character; type it again."
    d.vars[0].set("a long passphrase")
    d.vars[1].set("a long passphrase")
    assert str(d.ok_btn.cget("state")) == "normal" and d.hint_var.get() == ""  # all is well: the line says nothing
    d.destroy()


def test_the_region_editors_formatting_folds_away_unless_the_region_has_one(hidden_root):
    import numpy as np

    from taslation.annotations import RegionStyle
    from taslation.pipeline import manual_region

    region = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    region.status, region.translated_text = "translated", "Nice weather today, huh?"
    d = app_mod.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None, place=(1, 1))
    assert not d.bar.winfo_manager() and str(d.format_btn.cget("text")) == "▸ Formatting"
    assert d.style() == RegionStyle()  # folded away, it still says what it holds
    d.format_btn.invoke()  # one click
    assert d.bar.winfo_manager() == "pack" and str(d.format_btn.cget("text")) == "▾ Formatting"
    d.format_btn.invoke()
    assert not d.bar.winfo_manager()
    d.destroy()
    region.style = RegionStyle.make(align="left")
    d = app_mod.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None, place=(1, 1))
    assert d.bar.winfo_manager() == "pack" and d.style().align == "left"  # a style of its own: open from the start
    d.destroy()


def test_the_region_editor_names_its_state_in_words_and_uses_the_windows_font(hidden_root):
    import numpy as np

    from taslation.pipeline import manual_region

    region = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    region.status, region.translated_text = "translated", "Nice weather today, huh?"
    set_language("ja")
    try:
        d = app_mod.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None,
                                     place=(4, 6))
        header = d.winfo_children()[0].winfo_children()[0].cget("text")
        assert header == "吹き出し 6 個中 4 番目・訳文あり" and "manual" not in header
        assert str(d.text.cget("font")) == "TkDefaultFont"
        d.destroy()
    finally:
        set_language("en")
    assert app_mod.status_word("ocr-noise") == "not lettering" and app_mod.status_word("new-state") == "new-state"
    assert app_mod.status_word("low-confidence") == "unsure reading" and app_mod.status_word("sfx") == "sound effect"
    assert app_mod.status_word("print") == "printed text, not dialogue"


# ------------------------------------------------------------------ the icon, the package, the language file
def test_the_icon_is_drawn_and_ships_with_the_package():
    assets = ROOT / "taslation" / "ui" / "assets"
    ico = Image.open(assets / "taslation.ico")
    assert sorted(ico.info["sizes"]) == [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    png = Image.open(assets / "taslation.png")
    assert png.size == (256, 256) and png.mode == "RGBA" and png.getpixel((0, 0))[3] == 0  # a transparent ground
    spec = importlib.util.spec_from_file_location("make_icon", ROOT / "tools" / "make_icon.py")
    make_icon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make_icon)
    for size in (16, 32, 256):
        img = make_icon.draw_icon(size)
        assert img.size == (size, size) and img.getpixel((size - 1, 0))[3] == 0
    small = make_icon.draw_icon(16)
    assert small.getpixel((8, 10))[:3] == make_icon.GREEN[:3]  # the front bubble is green ...
    assert small.getpixel((8, 7))[:3] == (255, 255, 255)  # ... with white lines in it
    assert small.getpixel((7, 3))[:3] == make_icon.INK[:3] and small.getpixel((2, 3))[:3] == (255, 255, 255)
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    shipped = data["tool"]["setuptools"]["package-data"]["taslation.ui"]
    assert "assets/*.ico" in shipped and "assets/*.png" in shipped
    assert app_mod.ICON_ICO.is_file() and app_mod.ICON_PNG.is_file()


def test_the_window_language_is_written_all_or_nothing(tmp_path, monkeypatch):
    written = []
    real = i18n.write_atomic
    monkeypatch.setattr(i18n, "write_atomic", lambda path, data: (written.append(path), real(path, data)))
    i18n.save_ui_language(tmp_path, "pt")
    path = tmp_path / "ui.json"
    assert written == [path] and path.read_text(encoding="utf-8") == json.dumps({"language": "pt"}, indent=1)
    assert i18n.load_ui_language(tmp_path) == "pt" and sorted(p.name for p in tmp_path.iterdir()) == ["ui.json"]
