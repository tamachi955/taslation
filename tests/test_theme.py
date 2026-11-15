"""The window's colours (`ui.theme`): the setting and its default; Windows' app mode as the registry has it (faked
both ways, and failing) and its high contrast (faked); every text and ground pair of both palettes at WCAG AA; the
light mode touching nothing; the dark mode on the toolbar, the strips over the page and several dialogs, built dark
and switched while open, with no classic widget left on a light ground and the ttk styles on the dark one; back to
light as it was; the title bars; the Settings dialog's row and its saving. Everything is built on the shared hidden
root (never mapped), and no title bar of a real window is drawn: the frames' handles and the drawing are faked."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

import numpy as np
import pytest
from test_window_layout import Bars

from taslation.cache import CacheStore
from taslation.config import ConfigError, Settings
from taslation.i18n import CATALOGS, set_language
from taslation.locales.features import window_theme
from taslation.pipeline import manual_region
from taslation.ui import app as app_mod
from taslation.ui import banner, bubble_text, theme, translator, zoom
from taslation.ui.dialogs import book_settings, caches, review, shortcuts_page, system_page
from taslation.ui.dialogs import settings as dlg
from taslation.ui.dialogs.book_settings import BookSettingsDialog
from taslation.ui.dialogs.corrections import CorrectionsDialog
from taslation.ui.dialogs.find_replace import FindReplaceDialog
from taslation.ui.dialogs.help import HelpWindow
from taslation.ui.dialogs.review_list import LinesToReviewDialog
from taslation.ui.preview import ImageCanvas


@pytest.fixture
def titles(hidden_root, monkeypatch):
    """The title bars drawn, faked (no frame of a real window is asked for, none is drawn); Windows' high contrast
    off whatever this machine has; the light mode again after the test."""
    drawn = []
    monkeypatch.setattr(theme, "frame_handle", lambda win: 0)
    monkeypatch.setattr(theme, "title_bar", lambda hwnd, dark, redraw=False: drawn.append((hwnd, dark, redraw)) or True)
    monkeypatch.setattr(theme, "high_contrast", lambda query=None: False)
    yield drawn
    theme.reset_for_tests(hidden_root)


# ------------------------------------------------------------------ the setting, and which mode
def test_the_setting_is_as_windows_is_set_by_default_and_takes_three_values(tmp_path):
    assert Settings().theme == "system" and theme.THEMES == ("system", "light", "dark")
    for value in theme.THEMES:
        Settings(theme=value).validate()
    with pytest.raises(ConfigError, match="theme"):
        Settings(theme="blue").validate()
    path = tmp_path / "taslation.toml"
    path.write_text('theme = "dark"\n', encoding="utf-8")
    assert Settings.from_toml(path).theme == "dark"
    example = (Path(__file__).resolve().parents[1] / "taslation.toml.example").read_text(encoding="utf-8")
    assert 'theme = "system"' in example


def test_windows_app_mode_is_read_from_the_registry_only_read(monkeypatch):
    opened, asked = [], []

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake = SimpleNamespace(HKEY_CURRENT_USER="HKCU", KEY_READ=0x20019,
                           OpenKey=lambda *args: (opened.append(args), Key())[1],
                           QueryValueEx=lambda key, name: (asked.append(name), (0, 4))[1])
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert theme._read_apps_light() == 0
    assert opened == [("HKCU", theme.PERSONALIZE, 0, 0x20019)] and asked == ["AppsUseLightTheme"]


def test_system_follows_windows_app_mode_both_ways_and_is_light_where_it_cannot_be_read(monkeypatch):
    def unreadable():
        raise OSError("the value is not there")

    assert theme.system_dark(lambda: 0) is True  # Windows' apps dark
    assert theme.system_dark(lambda: 1) is False  # ... light
    assert theme.system_dark(unreadable) is False
    assert theme.system_dark(lambda: "not a number") is False
    monkeypatch.setattr(theme, "IS_WINDOWS", True)
    monkeypatch.setattr(theme, "_read_apps_light", lambda: 0)
    assert theme.system_dark() is True
    monkeypatch.setattr(theme, "_read_apps_light", unreadable)
    assert theme.system_dark() is False
    monkeypatch.setattr(theme, "IS_WINDOWS", False)  # outside Windows: light, nothing read
    monkeypatch.setattr(theme, "_read_apps_light", lambda: pytest.fail("read outside Windows"))
    assert theme.system_dark() is False and theme.high_contrast() is False
    # what the window shows for each setting
    assert theme.effective("system", contrast=False, dark_system=True) == theme.DARK_MODE
    assert theme.effective("system", contrast=False, dark_system=False) == theme.LIGHT_MODE
    assert theme.effective("light", contrast=False, dark_system=True) == theme.LIGHT_MODE
    assert theme.effective("dark", contrast=False, dark_system=False) == theme.DARK_MODE
    assert theme.effective("odd", contrast=False, dark_system=True) == theme.DARK_MODE  # counts as system
    for setting in theme.THEMES:  # high contrast first, whatever the setting says
        assert theme.effective(setting, contrast=True, dark_system=True) == theme.CONTRAST_MODE


def test_high_contrast_is_asked_and_a_failing_question_is_no():
    def broken():
        raise OSError("no answer")

    assert theme.high_contrast(lambda: True) is True
    assert theme.high_contrast(lambda: 0) is False
    assert theme.high_contrast(broken) is False


# ------------------------------------------------------------------ the palettes
def _hex(value: str) -> tuple[int, int, int]:
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def _luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG's relative luminance of *rgb* (0 to 1 each)."""
    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fore: str, ground: str) -> float:
    """WCAG's contrast ratio of two "#rrggbb" colours."""
    high, low = sorted((_luminance(tuple(c / 255 for c in _hex(fore))),
                        _luminance(tuple(c / 255 for c in _hex(ground)))), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _value(palette: dict[str, str], role: str) -> str:
    value = palette[role]
    return theme.LIGHT_VALUES.get(value, value)


def test_the_ratio_is_wcags():
    assert ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert ratio("#767676", "#ffffff") == pytest.approx(4.54, abs=0.01)  # the lightest grey at AA on white
    assert ratio("#ffffff", "#ffffff") == pytest.approx(1.0)


@pytest.mark.parametrize("name", ["light", "dark"])
def test_every_text_and_ground_pair_meets_wcag_aa(name):
    palette = theme.LIGHT if name == "light" else theme.DARK
    low = []
    for pairs, least in ((theme.READ_PAIRS, 4.5), (theme.GLYPH_PAIRS, 3.0)):
        for fore, ground in pairs:
            if name == "light" and ("thumb" in (fore, ground) or (fore, ground) == ("selection_text", "selection")):
                # (light is Windows' own look, left exactly as it is: Windows draws the scrollbars itself, and its
                # default selection, white on #0078d7, is 4.48:1)
                continue
            found = ratio(_value(palette, fore), _value(palette, ground))
            if found < least:
                low.append((fore, ground, round(found, 2)))
    assert low == []


def test_the_page_side_colours_stay_readable():
    for text in ("text", "hint"):  # the popup over the page, in every mode but high contrast
        assert ratio(zoom.ZOOM_COLOURS[text], zoom.ZOOM_COLOURS["ground"]) >= 4.5
    assert ratio(bubble_text.SELECTED[1], bubble_text.SELECTED[0]) >= 4.5


def test_the_colours_looked_for_on_a_change_are_told_apart_and_none_is_the_pages():
    for palette in (theme.LIGHT, theme.DARK):
        found = [palette[role].lower() for role in theme.FOUND_ROLES]
        assert len(found) == len(set(found))
    page = {"#202020", "#000000", *zoom.ZOOM_COLOURS.values(), *banner.PROBLEM_COLOURS, *banner.NOTICE_COLOURS,
            *banner.BAND_COLOURS, theme.DARK["problem_ground"], theme.DARK["notice_ground"], theme.DARK["banner_text"]}
    for palette in (theme.LIGHT, theme.DARK):
        looked_for = {colour for colour, role in theme._reverse(palette, light=palette is theme.LIGHT).items()
                      if role not in theme.SELECTION_OPTIONS}  # (a selection's: only on a selection's options)
        assert not {c.lower() for c in page} & looked_for
    assert set(theme.LIGHT) == set(theme.DARK) == set(theme.CONTRAST)


def test_the_light_colours_are_the_ones_the_window_always_had():
    assert caches.ERROR_COLOUR == "#b3261e" and review.FLASH == "#fff4bf" and review.FIT_COLOUR == "#c03030"
    assert shortcuts_page.FIXED_COLOUR == system_page.NOTE_COLOUR == "#6b6b6b" and translator.HINT_COLOUR == "#4a4a4a"
    assert book_settings.HINT_COLOUR == "#5a5a5a"
    assert banner.PROBLEM_COLOURS == ("#fff4ce", "#1f1f1f") and banner.NOTICE_COLOURS == ("#e5f1fb", "#1f1f1f")
    assert banner.BAND_COLOURS == ("#1f3b63", "#ffffff")
    assert theme.mode() == theme.LIGHT_MODE and theme.colour("hint") == "#5a5a5a"
    assert theme.strip_colours(banner.PROBLEM_COLOURS) == banner.PROBLEM_COLOURS


# ------------------------------------------------------------------ light: nothing touched
STYLES = (".", "TButton", "Toolbutton", "TLabel", "TFrame", "TEntry", "TCombobox", "TSpinbox", "TCheckbutton",
          "TRadiobutton", "TNotebook", "TNotebook.Tab", "Treeview", "Heading", "TScrollbar", "TProgressbar",
          "TLabelframe", "Viewer.TCombobox")


def _look(root) -> tuple:
    style = ttk.Style(root)
    return style.theme_use(), {name: (style.configure(name), style.map(name)) for name in STYLES}


def test_the_light_mode_touches_no_style_option_or_title_bar(hidden_root, titles, monkeypatch):
    before = _look(hidden_root)
    label = ttk.Label(hidden_root, text="A hint", foreground=theme.colour("hint"))

    def refused(*_args, **_kwargs):
        pytest.fail("the light mode touched the look")

    monkeypatch.setattr(theme, "ttk", SimpleNamespace(Style=refused))
    for name in ("_ensure_dark_theme", "_restyle", "_option_database", "_recolour", "_watch_title_bars",
                 "_title_bar_for"):
        monkeypatch.setattr(theme, name, refused)
    for setting in ("light", "system"):  # (the window's start on a light Windows)
        assert theme.apply(hidden_root, setting, contrast=False, dark_system=False) == theme.LIGHT_MODE
    assert _look(hidden_root) == before and titles == []
    assert str(label.cget("foreground")) == "#5a5a5a"
    assert str(tk.Text(hidden_root).cget("background")) == "SystemWindow"


# ------------------------------------------------------------------ dark: the main window and the dialogs
def _region():
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text = "translated", "Nice weather today, huh?", "今日はいい天気だね"
    return r


ROWS = [("Ollama is not running.", banner.PROBLEM_COLOURS, ("Start", lambda: None)),
        ("Qwen translates for now.", banner.NOTICE_COLOURS, None)]


def _main_window(root):
    """The toolbar, translator mode's strip, the menus, the strips over the page, the page and the status line."""
    w = Bars(root)
    w.build("en")
    strips = ttk.Frame(w)
    strips.pack(fill="x")
    w.banner = banner.SetupBanner(strips)
    w.banner.show_rows(ROWS)
    w.banner.pack(fill="x")
    w.band = banner.Strip(strips, banner.BAND_COLOURS, pad=(12, 6))
    w.band.set(["Reading the book: page 3"])
    w.band.pack(fill="x")
    ImageCanvas(w, bg="#202020").pack(fill="both", expand=True)
    bar = ttk.Frame(w, padding=(8, 3))
    bar.pack(fill="x")
    w.guard = ttk.Label(bar, text="Blocked a connection.", foreground=theme.colour("error"))
    w.guard.pack(side="right")
    ttk.Progressbar(bar, mode="indeterminate", length=90).pack(side="right")
    ttk.Label(bar, text="Ready.").pack(side="left")
    return w


def _dialogs(root, tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    settings = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                        config_path=tmp_path / "taslation.toml")
    book = SimpleNamespace(annotations=SimpleNamespace(settings={}, areas=[]), _base_settings=settings,
                           set_book_settings=lambda values: None)
    made = [dlg.SettingsDialog(root, settings), HelpWindow(root), caches.CachesDialog(root, CacheStore(tmp_path / "c")),
            review.ReviewDialog(root, [], on_edit=lambda region: None),
            BookSettingsDialog(root, book, on_change=lambda: None),
            FindReplaceDialog(root, lambda query: ([], ""), lambda query, text, picked: False, lambda: None,
                              lambda: None, on_replace_series=lambda query, text: False),
            LinesToReviewDialog(root, lambda: None), CorrectionsDialog(root, lambda: None),
            review.EditBubbleDialog(root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                    note="A note for the reader.", place=(1, 2))]
    for d in made:
        d.withdraw()
    boxes = [w for w in _ttk_widgets(made[0]) if w.winfo_class() == "TCombobox"]
    root.tk.call("ttk::combobox::PopdownWindow", str(boxes[0]))  # a combobox's list, made as it opens
    return made


def _ttk_widgets(widget):
    found, stack = [], [widget]
    while stack:
        w = stack.pop()
        found.append(w)
        stack.extend(w.winfo_children())
    return found


def _lum(root, value: str) -> float:
    return _luminance(tuple(c / 65535 for c in root.winfo_rgb(value)))


GROUNDS = ("background", "highlightbackground", "troughcolor", "disabledbackground", "readonlybackground")
TEXTS = ("foreground", "insertbackground")


def _light_left(root, top) -> list[tuple[str, str, str, str]]:
    """What is still light under *top* (by Tcl path: the comboboxes' lists too): a classic widget's ground or a
    dark text, a ttk widget whose style draws on a light ground or with dark text."""
    style, call, left = ttk.Style(root), root.tk.call, []
    for path in theme._walk(top):
        cls = str(call("winfo", "class", path))
        specs = {str(s[0]).lstrip("-"): str(s[4]) for s in map(root.tk.splitlist, root.tk.splitlist(call(path, "configure")))
                 if len(s) == 5}
        if not cls.startswith("T") or cls in ("Tk", "Text", "Toplevel"):
            for option in GROUNDS:
                if specs.get(option) and _lum(root, specs[option]) > 0.15:
                    left.append((path, cls, option, specs[option]))
            if cls in ("Text", "Listbox", "Entry", "Label", "Menu"):
                for option in TEXTS:
                    if specs.get(option) and _lum(root, specs[option]) < 0.35:
                        left.append((path, cls, option, specs[option]))
            continue
        name = specs.get("style") or cls
        grounds = {"TProgressbar": ("troughcolor",), "TScrollbar": ("troughcolor",), "TScale": ("troughcolor",),
                   "TSeparator": ()}.get(cls, ("background",))
        if cls in ("TEntry", "TCombobox", "TSpinbox", "Treeview"):
            grounds += ("fieldbackground",)
        for option in grounds:
            value = style.lookup(name, option)
            if not value or _lum(root, value) > 0.15:
                left.append((path, name, option, value))
        if cls in ("TLabel", "TButton", "TCheckbutton", "TRadiobutton", "TEntry", "TCombobox", "Treeview"):
            value = specs.get("foreground") or style.lookup(name, "foreground")
            if not value or _lum(root, value) < 0.35:
                left.append((path, name, "foreground", value))
        if specs.get("background") and _lum(root, specs["background"]) > 0.15:  # a ground set on the widget itself
            left.append((path, name, "background", specs["background"]))
    return left


def test_built_dark_nothing_keeps_a_light_ground(hidden_root, titles, tmp_path, monkeypatch):
    assert theme.apply(hidden_root, "dark", contrast=False) == theme.DARK_MODE
    assert ttk.Style(hidden_root).theme_use() == theme.DARK_THEME
    w = _main_window(hidden_root)
    dialogs = _dialogs(hidden_root, tmp_path, monkeypatch)
    for top in (w, *dialogs):
        assert _light_left(hidden_root, top) == [], top
    assert str(w.guard.cget("foreground")) == theme.DARK["error"]
    assert str(w.banner.labels[0].cget("background")) == theme.DARK["problem_ground"]
    assert str(w.band.labels[0].cget("background")) == theme.DARK["band_ground"]  # the band stays as it is
    editor, book = dialogs[-1], dialogs[4]
    assert str(book.areas_list.cget("background")) == theme.DARK["field"]  # a classic list
    assert str(book.no_areas.cget("foreground")) == theme.DARK["hint"]
    assert str(editor.note_label.cget("foreground")) == theme.DARK["hint"]
    assert str(editor.text.cget("background")) == theme.DARK["field"]
    look = ttk.Style(hidden_root)
    assert look.lookup("TCombobox", "fieldbackground", ("readonly",)) == theme.DARK["raised"]
    assert look.lookup("TButton", "foreground", ("disabled",)) == theme.DARK["disabled"]
    assert look.lookup("Treeview", "background", ("selected",)) == theme.DARK["selection"]
    assert look.lookup("Heading", "background") == theme.DARK["raised"]


def test_switched_while_open_the_window_and_its_dialogs_follow_and_come_back(hidden_root, titles, tmp_path,
                                                                            monkeypatch):
    native = ttk.Style(hidden_root).theme_use()
    w = _main_window(hidden_root)
    dialogs = _dialogs(hidden_root, tmp_path, monkeypatch)
    before = _look(hidden_root)
    editor = dialogs[-1]
    popdown = next(p for p in theme._walk(dialogs[0]) if str(hidden_root.tk.call("winfo", "class", p)) == "Listbox")
    assert theme.apply(hidden_root, "dark", contrast=False) == theme.DARK_MODE
    w.banner.show_rows(ROWS)  # as the window draws its strips again (`App._colours_again`)
    w.band.set(w.band.texts())
    for top in (w, *dialogs):
        assert _light_left(hidden_root, top) == [], top
    assert str(hidden_root.cget("background")) == theme.DARK["ground"]
    # and back: Windows' own look as it was, the window's own colours as they were
    assert theme.apply(hidden_root, "light", contrast=False) == theme.LIGHT_MODE
    assert str(w.band.labels[0].cget("foreground")) == "#ffffff"  # white text that is no selection's stays
    w.banner.show_rows(ROWS)
    w.band.set(w.band.texts())
    assert ttk.Style(hidden_root).theme_use() == native and _look(hidden_root) == before
    assert str(hidden_root.cget("background")) == "SystemButtonFace"
    assert str(editor.text.cget("background")) == "SystemWindow"
    assert str(editor.text.cget("foreground")) == "SystemWindowText"
    assert str(hidden_root.tk.call(popdown, "cget", "-background")) == "SystemWindow"
    assert str(editor.note_label.cget("foreground")) == "#5a5a5a" and str(w.guard.cget("foreground")) == "#b3261e"
    assert str(dialogs[4].areas_list.cget("background")) == "SystemWindow"
    assert str(dialogs[4].no_areas.cget("foreground")) == "#5a5a5a"
    assert str(w.banner.labels[0].cget("background")) == "#fff4ce"
    assert str(tk.Text(hidden_root).cget("background")) == "SystemWindow"  # the option database as Tk has it
    assert str(tk.Listbox(hidden_root).cget("foreground")) == "SystemButtonText"
    assert str(tk.Menu(hidden_root).cget("background")) == "SystemMenu"


def test_the_window_named_styles_come_again_in_each_theme(hidden_root, titles):
    owner = tk.Frame(hidden_root)
    theme.style(owner, "Probe.TButton", padding=7)
    assert theme.apply(hidden_root, "dark", contrast=False) == theme.DARK_MODE
    assert str(ttk.Style(hidden_root).lookup("Probe.TButton", "padding")) == "7"
    owner.destroy()
    theme.apply(hidden_root, "light", contrast=False)
    assert "Probe.TButton" not in theme._styles  # forgotten with its widget


def test_the_editor_box_lights_up_and_comes_back_to_the_colours_in_force(hidden_root, titles, monkeypatch):
    theme.apply(hidden_root, "dark", contrast=False)
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                place=(1, 1))
    d.withdraw()
    later = []
    monkeypatch.setattr(d, "after", lambda ms, job: later.append(job) or "job")
    d._flash()
    assert str(d.text.cget("background")) == theme.DARK["flash"]
    later[-1]()
    assert str(d.text.cget("background")) == theme.DARK["field"]
    d.destroy()


# ------------------------------------------------------------------ high contrast
def test_high_contrast_keeps_windows_look_and_takes_its_colours(hidden_root, titles):
    style = ttk.Style(hidden_root)
    before = _look(hidden_root)
    hint = ttk.Label(hidden_root, text="A hint", foreground=theme.colour("hint"))
    error = ttk.Label(hidden_root, text="It went wrong.", foreground=theme.colour("error"))
    text = tk.Text(hidden_root)
    assert theme.apply(hidden_root, "dark", contrast=True) == theme.CONTRAST_MODE  # dark asked, contrast on
    assert _look(hidden_root) == before and style.theme_use() != theme.DARK_THEME and titles == []
    assert str(text.cget("background")) == "SystemWindow" and str(tk.Text(hidden_root).cget("background")) == "SystemWindow"
    assert str(hint.cget("foreground")) == "SystemGrayText" and str(error.cget("foreground")) == ""
    assert theme.strip_colours(banner.PROBLEM_COLOURS) == ("SystemInfoBackground", "SystemInfoText")
    assert theme.strip_colours(banner.BAND_COLOURS) == ("SystemHighlight", "SystemHighlightText")
    assert theme.tooltip_colours() is None and zoom.zoom_colours() == zoom.CONTRAST_ZOOM
    if sys.platform == "win32":  # every colour of the contrast mode is one of Windows' that Tk knows
        for value in {*theme.CONTRAST.values(), *zoom.CONTRAST_ZOOM.values(), *bubble_text.CONTRAST_SELECTED} - {""}:
            hidden_root.winfo_rgb(value)
    # high contrast off again: the setting's own
    assert theme.apply(hidden_root, "dark", contrast=False) == theme.DARK_MODE
    assert str(hint.cget("foreground")) == theme.DARK["hint"]
    assert str(text.cget("background")) == theme.DARK["field"]


# ------------------------------------------------------------------ the title bars
class Frame:
    """A window as `_title_bar_for` asks it: on the screen or not, a tooltip (no frame) or not, its frame's handle."""

    def __init__(self, path, hwnd, mapped=True, bare=False):
        self.path, self.hwnd, self.mapped, self.bare = path, hwnd, mapped, bare

    def winfo_exists(self):
        return True

    def winfo_ismapped(self):
        return self.mapped

    def wm_overrideredirect(self):
        return self.bare

    def __str__(self):
        return self.path


def test_the_title_bars_follow_the_mode_once_each(monkeypatch):
    drawn = []
    monkeypatch.setattr(theme, "IS_WINDOWS", True)
    monkeypatch.setattr(theme, "_titles", {})
    monkeypatch.setattr(theme, "frame_handle", lambda win: win.hwnd)
    monkeypatch.setattr(theme, "title_bar", lambda hwnd, dark, redraw=False: drawn.append((hwnd, dark, redraw)) or True)
    main, tip, hidden = Frame(".", 11), Frame(".tip", 12, bare=True), Frame(".dialog", 13, mapped=False)
    theme._title_bar_for(main)
    assert drawn == []  # light, never drawn dark: as Windows draws it
    monkeypatch.setattr(theme, "_mode", theme.DARK_MODE)
    for window in (main, tip, hidden, main):
        theme._title_bar_for(window)
    assert drawn == [(11, True, False)]  # once; no tooltip, nothing off the screen
    main.hwnd = 21  # Tk made the frame anew (full screen): drawn again
    theme._title_bar_for(main)
    assert drawn[-1] == (21, True, False)
    monkeypatch.setattr(theme, "_mode", theme.LIGHT_MODE)
    theme._title_bar_for(main, again=True)  # back to light while on the screen
    assert drawn[-1] == (21, False, True)
    theme._title_bar_for(Frame(".other", 31))
    assert len(drawn) == 3


def test_a_title_bar_is_drawn_only_on_windows_and_for_a_frame(monkeypatch):
    monkeypatch.setattr(theme, "_dll", lambda name: pytest.fail("a system library was asked"))
    monkeypatch.setattr(theme, "IS_WINDOWS", False)
    assert theme.title_bar(5, True) is False
    monkeypatch.setattr(theme, "IS_WINDOWS", True)
    assert theme.title_bar(0, True) is False


def test_dark_watches_the_windows_as_they_come_on_the_screen(hidden_root, titles):
    theme.apply(hidden_root, "dark", contrast=False)
    assert str(hidden_root.tk.interpaddr()) in theme._bound
    for cls in ("Tk", "Toplevel"):
        assert "<Map>" in hidden_root.bind_class(cls) and "<Configure>" in hidden_root.bind_class(cls)


# ------------------------------------------------------------------ the Settings dialog and the window
@pytest.fixture
def in_force(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", config_path=tmp_path / "taslation.toml")


def _colours_box(d):
    return next(w for w in _ttk_widgets(d) if w.winfo_class() == "TCombobox"
                and str(w.cget("textvariable")) == str(d.colours_var))


def _label_texts(d):
    return [str(w.cget("text")).replace("\n", " ") for w in _ttk_widgets(d) if w.winfo_class() == "TLabel"]


def test_the_settings_dialog_offers_the_three_and_saves_the_choice(hidden_root, in_force, titles):
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert list(_colours_box(d).cget("values")) == ["As Windows is set", "Light", "Dark"]
    assert d.colours_var.get() == "As Windows is set" and d.values()["theme"] == "system"
    assert dlg.CONTRAST_TEXT not in _label_texts(d)
    d.colours_var.set("Dark")
    assert d.save() is True and got == [{"theme": "dark"}]
    assert d.message_var.get() == "Saved. The changes apply now."
    assert Settings.from_toml(in_force.config_path).theme == "dark"
    d.destroy()
    set_language("ja")
    in_force.theme = "light"
    d = dlg.SettingsDialog(hidden_root, in_force)
    assert list(_colours_box(d).cget("values")) == [window_theme.TEXTS[label]["ja"]
                                                    for _value, label in dlg.THEME_CHOICES]
    assert d.values()["theme"] == "light"
    d.destroy()


def test_the_settings_dialog_says_while_high_contrast_is_on(hidden_root, in_force, titles, monkeypatch):
    monkeypatch.setattr(theme, "high_contrast", lambda query=None: True)
    d = dlg.SettingsDialog(hidden_root, in_force)
    assert dlg.CONTRAST_TEXT in _label_texts(d)
    d.destroy()


def test_the_strings_are_in_every_language():
    for english in (*(label for _value, label in dlg.THEME_CHOICES), "Colours:", dlg.THEME_TIP, dlg.CONTRAST_TEXT):
        assert english in window_theme.TEXTS
        assert all(english in CATALOGS[code] for code in CATALOGS if code != "en"), english


class Window(tk.Toplevel):
    """The window's colours as `App` changes them, on a withdrawn window of the hidden root."""

    _settings_saved = app_mod.App._settings_saved
    _colours_again = app_mod.App._colours_again

    def __init__(self, root):
        super().__init__(root)
        self.withdraw()
        self.settings = SimpleNamespace(theme="system")
        self.drawn: list[str] = []

    def _show_banner(self):
        self.drawn.append("banner")

    def _show_band(self):
        self.drawn.append("band")


def test_a_saved_choice_applies_at_once_and_the_strips_are_drawn_anew(hidden_root, titles, monkeypatch):
    monkeypatch.setattr(theme, "system_dark", lambda read=None: False)
    w = Window(hidden_root)
    w._settings_saved({"theme": "dark"})
    assert w.settings.theme == "dark" and theme.mode() == theme.DARK_MODE and w.drawn == ["banner", "band"]
    assert str(w.cget("background")) == theme.DARK["ground"]
    w._colours_again(SimpleNamespace(widget=w))  # it comes to the front: nothing changed, nothing drawn
    assert w.drawn == ["banner", "band"]
    monkeypatch.setattr(theme, "system_dark", lambda read=None: True)
    w.settings.theme = "system"
    w._colours_again(SimpleNamespace(widget=tk.Frame(w)))  # (a widget of the window, not the window)
    assert theme.mode() == theme.DARK_MODE and len(w.drawn) == 2
    monkeypatch.setattr(theme, "system_dark", lambda read=None: False)  # Windows' apps light meanwhile
    w._colours_again(SimpleNamespace(widget=w))
    assert theme.mode() == theme.LIGHT_MODE and len(w.drawn) == 4
    assert str(w.cget("background")) == "SystemButtonFace"
