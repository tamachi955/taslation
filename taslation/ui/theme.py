"""The window's colours (`Settings.theme`): "light", Windows' own look exactly as it always was; "dark"; or "system",
which follows the app mode Windows has for programs (the registry value ``AppsUseLightTheme``, only read). Windows'
high contrast comes before all three: while it is on, the window keeps Windows' own look, which follows the contrast
theme, and the few colours the window sets itself are taken from Windows' system colours (`CONTRAST`). Both are
looked at as the window starts and whenever it comes to the front (`App._colours_again`).

What is chrome follows the theme here; what belongs to the page does not (the page area's dark ground, the frames
drawn on a page, the lettering, the page list's state colours): those keep their colours in every theme, and are dark
already.

* Light changes nothing: no ttk style, no option of the option database, no title bar is touched (`apply` does
  nothing while the window is light). The colours the window sets itself are `LIGHT`'s, the ones it always had.
* Dark is a ttk theme of its own (`DARK_THEME`) made on Tk's "clam", whose elements take the colours given to them
  (Windows' native themes, "vista" and "winnative", draw most parts with Windows' own colours and leave the
  colour options alone); the option database gives Tk's classic widgets made from then on (text boxes, lists, the
  menus, the lists of the comboboxes) `DARK`'s colours, and Windows 10 and 11 draw the title bars dark
  (`title_bar`: DwmSetWindowAttribute with DWMWA_USE_IMMERSIVE_DARK_MODE, for the main window and every dialog as it
  comes on the screen).
* A change applies at once (`apply` again, from the Settings dialog): ttk's widgets follow their theme by themselves;
  the classic widgets already made, and the colours the window set on its labels, are found by their colours and
  given the new theme's (`_recolour`); the window's own named styles are set again in the new theme (`style`).

Every text and ground pair of `LIGHT` and `DARK` meets WCAG AA (`READ_PAIRS`, 4.5:1; `GLYPH_PAIRS`, the borders and
marks of controls, 3:1); tests/test_theme.py works the ratios out."""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
import weakref
from tkinter import ttk
from typing import Any, Callable

IS_WINDOWS = sys.platform == "win32"
THEMES = ("system", "light", "dark")  # the setting's values
LIGHT_MODE, DARK_MODE, CONTRAST_MODE = "light", "dark", "contrast"  # what the window shows (`mode`)
DARK_THEME = "taslation-dark"  # the ttk theme of the dark mode ...
BASE_THEME = "clam"  # ... made on this one: its elements and layouts, none of its colours
PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"  # (HKEY_CURRENT_USER)
APPS_VALUE = "AppsUseLightTheme"  # 0: Windows' app mode is dark
OPTION_PRIORITY = 60  # the option database entries of the dark mode ("userDefault": above Tk's own widgetDefault)

# ------------------------------------------------------------------ the palettes
# The roles, and what each colours:
#   ground          windows and dialogs                 raised    buttons, headings, tabs not chosen
#   hover/pressed   a control under the pointer / held  field     entries, lists, text boxes, trees
#   text            text on any of these grounds        disabled  the text of a control that is greyed out
#   accent          progress bars, a default button     selection what is selected, and its selection_text
#   border          the edges of controls                focus     the ring of the control with the keys
#   thumb           a scrollbar's thumb                 menu      the menus' ground
#   hint, note, tool_hint   the dimmed lines of the dialogs and of translator mode's strip (three greys, as they were)
#   error, warning  a line that says what went wrong / what could not be done
#   problem_ground, notice_ground, banner_text   the setup banner over the page; band_*: the scan band
#   flash           the region editor's translation box, a moment after the model's answer came into it
#   tip_ground, tip_text, tip_border   the tooltips
LIGHT: dict[str, str] = {
    # Windows' own colours (what Tk's classic widgets and the native ttk themes draw with) by Tk's names; their
    # usual values, for the contrast tests, are in `LIGHT_VALUES`
    "ground": "SystemButtonFace", "raised": "SystemButtonFace", "hover": "SystemButtonFace",
    "pressed": "SystemButtonFace", "field": "SystemWindow", "text": "SystemWindowText", "disabled": "SystemDisabledText",
    "accent": "SystemHighlight", "selection": "SystemHighlight", "selection_text": "SystemHighlightText",
    "border": "SystemWindowFrame", "focus": "SystemWindowFrame", "thumb": "SystemButtonFace", "menu": "SystemMenu",
    # the colours the window has always set itself
    "hint": "#5a5a5a", "note": "#6b6b6b", "tool_hint": "#4a4a4a", "error": "#b3261e", "warning": "#c03030",
    "problem_ground": "#fff4ce", "notice_ground": "#e5f1fb", "banner_text": "#1f1f1f",
    "band_ground": "#1f3b63", "band_text": "#ffffff", "flash": "#fff4bf",
    "tip_ground": "SystemInfoBackground", "tip_text": "SystemInfoText", "tip_border": "SystemInfoText",
}
# what Windows' colours of `LIGHT` are by default (Windows 10 and 11, light): for the contrast tests only
LIGHT_VALUES: dict[str, str] = {
    "SystemButtonFace": "#f0f0f0", "SystemWindow": "#ffffff", "SystemWindowText": "#000000",
    "SystemButtonText": "#000000", "SystemDisabledText": "#6d6d6d", "SystemHighlight": "#0078d7",
    "SystemHighlightText": "#ffffff", "SystemWindowFrame": "#646464", "SystemMenu": "#f0f0f0",
    "SystemMenuText": "#000000", "SystemInfoBackground": "#ffffe1", "SystemInfoText": "#000000",
}
DARK: dict[str, str] = {
    "ground": "#1e1e1e", "raised": "#2d2d2d", "hover": "#3a3a3a", "pressed": "#474747", "field": "#262626",
    "text": "#e8e8e8", "disabled": "#9a9a9a", "accent": "#4ea1ff", "selection": "#2e5c99", "selection_text": "#ffffff",
    "border": "#7a7a7a", "focus": "#9ec5ff", "thumb": "#7d7d7d", "menu": "#2b2b2b",
    "hint": "#b0b0b0", "note": "#a6a6a6", "tool_hint": "#bdbdbd", "error": "#ff8a80", "warning": "#ffab91",
    "problem_ground": "#3d3314", "notice_ground": "#16304a", "banner_text": "#f2f2f2",
    "band_ground": "#1f3b63", "band_text": "#ffffff", "flash": "#4a4220",
    "tip_ground": "#333333", "tip_text": "#f0f0f0", "tip_border": "#7a7a7a",
}
# Windows' high contrast: Windows' look, and for what the window colours itself Windows' system colours; "" is the
# control's own text colour (a ttk label's: the contrast theme's)
CONTRAST: dict[str, str] = {
    **{role: value for role, value in LIGHT.items() if value.startswith("System")},
    "hint": "SystemGrayText", "note": "SystemGrayText", "tool_hint": "SystemGrayText", "error": "", "warning": "",
    "problem_ground": "SystemInfoBackground", "notice_ground": "SystemInfoBackground", "banner_text": "SystemInfoText",
    "band_ground": "SystemHighlight", "band_text": "SystemHighlightText", "flash": "SystemInfoBackground",
}
PALETTES = {LIGHT_MODE: LIGHT, DARK_MODE: DARK, CONTRAST_MODE: CONTRAST}

# the pairs that are read (text on its ground: 4.5:1) and the edges and marks of controls (3:1), in both palettes
READ_PAIRS: tuple[tuple[str, str], ...] = (
    ("text", "ground"), ("text", "raised"), ("text", "hover"), ("text", "pressed"), ("text", "field"),
    ("text", "menu"), ("disabled", "ground"), ("disabled", "raised"), ("disabled", "field"), ("disabled", "menu"),
    ("selection_text", "selection"), ("hint", "ground"), ("hint", "field"), ("note", "ground"), ("note", "field"),
    ("tool_hint", "ground"), ("error", "ground"), ("warning", "ground"), ("banner_text", "problem_ground"),
    ("banner_text", "notice_ground"), ("band_text", "band_ground"), ("text", "flash"), ("tip_text", "tip_ground"))
GLYPH_PAIRS: tuple[tuple[str, str], ...] = (
    ("border", "ground"), ("border", "field"), ("border", "raised"), ("accent", "ground"), ("accent", "field"),
    ("focus", "ground"), ("focus", "field"), ("thumb", "ground"), ("thumb", "field"), ("text", "field"),
    ("tip_border", "ground"))
# the roles whose colours a change of theme looks for on the widgets already made (`_recolour`): their colours are
# told apart within each palette
FOUND_ROLES = ("ground", "field", "text", "disabled", "selection", "selection_text", "focus", "menu", "hint", "note",
               "tool_hint", "error", "warning")
# ... and in the light mode Tk's other names for some of them (a label's text is SystemButtonText, a menu's
# SystemMenuText); a role whose light colour is Tk's default comes back as the widget's own default
LIGHT_ALIASES = {"systembuttontext": "text", "systemmenutext": "text"}
DEFAULTED_ROLES = frozenset({"field", "text", "disabled", "selection", "selection_text", "focus", "menu"})
# the selection's colours are looked for only on the options that hold a selection (or a menu's active entry): white
# text elsewhere (the scan band, a popup over the page, an ink swatch) is not a selection's text
SELECTION_OPTIONS = {"selection": frozenset({"selectbackground", "inactiveselectbackground", "activebackground"}),
                     "selection_text": frozenset({"selectforeground", "activeforeground"})}
COLOUR_OPTIONS = ("background", "foreground", "activebackground", "activeforeground", "disabledforeground",
                  "disabledbackground", "readonlybackground", "selectbackground", "selectforeground",
                  "inactiveselectbackground", "insertbackground", "highlightbackground", "highlightcolor",
                  "selectcolor", "troughcolor")
# Tk's classic widgets the window or Tk makes (the lists of the comboboxes: ComboboxPopdown, Listbox): their
# colours in the option database while the window is dark
CLASSIC = {"Toplevel": "toplevel", "Frame": "frame", "Label": "label", "Text": "text", "Listbox": "listbox",
           "Menu": "menu", "Canvas": "canvas", "Entry": "entry"}

_mode = LIGHT_MODE  # what the window shows now
_native: dict[str, str] = {}  # the interpreter's ttk theme before the dark one (Tk's own: "vista" on Windows)
_styles: dict[str, tuple[Callable[[], Any], dict[str, Any]]] = {}  # the window's own named styles (`style`)
_bound: set[str] = set()  # the interpreters whose windows' title bars follow the theme (`_watch_title_bars`)
_titles: dict[str, tuple[int, bool]] = {}  # a window's path -> its frame's handle and whether it was drawn dark


# ------------------------------------------------------------------ which mode
def _read_apps_light() -> int:
    """Windows' app mode as the registry has it (1: light, 0: dark), only read. OSError when it cannot be read."""
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE, 0, winreg.KEY_READ) as key:
        value, _kind = winreg.QueryValueEx(key, APPS_VALUE)
    return int(value)


def system_dark(read: Callable[[], int] | None = None) -> bool:
    """Whether Windows has its programs dark (Settings > Personalisation > Colours: the app mode). Light where it
    cannot be read, and outside Windows."""
    if read is None:
        if not IS_WINDOWS:
            return False
        read = _read_apps_light
    try:
        return int(read()) == 0
    except (OSError, ImportError, TypeError, ValueError):
        return False


def _query_contrast() -> bool:
    """Whether Windows' high contrast is on (SystemParametersInfo SPI_GETHIGHCONTRAST, HCF_HIGHCONTRASTON)."""
    import ctypes
    from ctypes import wintypes

    class HighContrast(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD), ("lpszDefaultScheme", wintypes.LPWSTR)]

    user32 = ctypes.WinDLL("user32")  # a loader of its own: the argument types set here stay here
    user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    user32.SystemParametersInfoW.restype = wintypes.BOOL
    info = HighContrast()
    info.cbSize = ctypes.sizeof(HighContrast)
    if not user32.SystemParametersInfoW(0x0042, info.cbSize, ctypes.byref(info), 0):
        return False
    return bool(info.dwFlags & 0x1)


def high_contrast(query: Callable[[], bool] | None = None) -> bool:
    """Whether Windows' high contrast is on; no where it cannot be asked, and outside Windows."""
    if query is None:
        if not IS_WINDOWS:
            return False
        query = _query_contrast
    try:
        return bool(query())
    except (OSError, AttributeError, ValueError):
        return False


def effective(setting: str, contrast: bool | None = None, dark_system: bool | None = None) -> str:
    """What the window shows for *setting* (`THEMES`; anything else counts as "system"): `CONTRAST_MODE` while
    Windows' high contrast is on (*contrast*, else asked), else dark or light (for "system": Windows' app mode,
    *dark_system*, else read)."""
    if high_contrast() if contrast is None else contrast:
        return CONTRAST_MODE
    if setting == "light":
        return LIGHT_MODE
    if setting == "dark":
        return DARK_MODE
    return DARK_MODE if (system_dark() if dark_system is None else dark_system) else LIGHT_MODE


def mode() -> str:
    """What the window shows now: `LIGHT_MODE`, `DARK_MODE` or `CONTRAST_MODE`."""
    return _mode


def is_dark() -> bool:
    return _mode == DARK_MODE


def colour(role: str) -> str:
    """The colour of *role* (`LIGHT`'s roles) in the mode the window shows."""
    return PALETTES[_mode][role]


def pair(ground_role: str, text_role: str) -> tuple[str, str]:
    """(ground, text) of two roles in the mode the window shows."""
    return colour(ground_role), colour(text_role)


# ------------------------------------------------------------------ the dark ttk theme
def dark_settings(p: dict[str, str] = DARK) -> dict[str, dict[str, Any]]:
    """The dark ttk theme's styles: every widget class the window uses, in *p*'s colours, the sizes as Tk's clam has
    them (its elements are what draws them)."""
    flat = {"lightcolor": p["raised"], "darkcolor": p["raised"]}
    button_states = [("disabled", p["ground"]), ("pressed", p["pressed"]), ("active", p["hover"])]
    return {
        ".": {"configure": {"background": p["ground"], "foreground": p["text"], "bordercolor": p["border"],
                            "lightcolor": p["ground"], "darkcolor": p["ground"], "troughcolor": p["ground"],
                            "fieldbackground": p["field"], "selectbackground": p["selection"],
                            "selectforeground": p["selection_text"], "selectborderwidth": 0,
                            "insertcolor": p["text"], "focuscolor": p["focus"], "arrowcolor": p["text"],
                            "indicatorbackground": p["field"], "indicatorforeground": p["text"],
                            "upperbordercolor": p["border"], "lowerbordercolor": p["border"],
                            "font": "TkDefaultFont"},
              "map": {"foreground": [("disabled", p["disabled"])],
                      "selectbackground": [("!focus", p["hover"])], "selectforeground": [("!focus", p["text"])]}},
        "TFrame": {"configure": {"background": p["ground"]}},
        "TLabel": {"configure": {"background": p["ground"], "foreground": p["text"]}},
        # (paddings that make the controls as large as Windows' own: the toolbar's rows stay as they were)
        "TButton": {"configure": {"background": p["raised"], "anchor": "center", "width": -11, "padding": (2, 2),
                                  "relief": "raised", **flat},
                    "map": {"background": button_states,
                            "lightcolor": button_states, "darkcolor": button_states,
                            "bordercolor": [("alternate", p["accent"]), ("focus", p["focus"])],
                            "foreground": [("disabled", p["disabled"])]}},
        "Toolbutton": {"configure": {"background": p["ground"], "anchor": "center", "padding": (2, 2),
                                     "relief": "flat", "lightcolor": p["ground"], "darkcolor": p["ground"]},
                       "map": {"relief": [("disabled", "flat"), ("selected", "sunken"), ("pressed", "sunken"),
                                          ("active", "raised")],
                               "background": [("disabled", p["ground"]), ("selected", p["selection"]),
                                              ("pressed", p["pressed"]), ("active", p["hover"])],
                               "lightcolor": [("selected", p["selection"]), ("active", p["hover"])],
                               "darkcolor": [("selected", p["selection"]), ("active", p["hover"])],
                               "foreground": [("disabled", p["disabled"]), ("selected", p["selection_text"])]}},
        "TCheckbutton": {"configure": {"background": p["ground"], "foreground": p["text"], "padding": 2,
                                       "indicatormargin": (1, 1, 4, 1)},
                         "map": {"indicatorbackground": [("disabled", p["ground"]), ("pressed", p["hover"])],
                                 "indicatorforeground": [("disabled", p["disabled"])]}},
        "TRadiobutton": {"configure": {"background": p["ground"], "foreground": p["text"], "padding": 2,
                                       "indicatormargin": (1, 1, 4, 1)},
                         "map": {"indicatorbackground": [("disabled", p["ground"]), ("pressed", p["hover"])],
                                 "indicatorforeground": [("disabled", p["disabled"])]}},
        "TEntry": {"configure": {"fieldbackground": p["field"], "foreground": p["text"], "insertcolor": p["text"],
                                 "bordercolor": p["border"], "lightcolor": p["field"], "padding": 1,
                                 "insertwidth": 1},
                   "map": {"fieldbackground": [("readonly", p["ground"]), ("disabled", p["ground"])],
                           "lightcolor": [("focus", p["accent"])], "bordercolor": [("focus", p["accent"])]}},
        "TSpinbox": {"configure": {"fieldbackground": p["field"], "foreground": p["text"], "insertcolor": p["text"],
                                   "background": p["raised"], "bordercolor": p["border"], "lightcolor": p["field"],
                                   "darkcolor": p["raised"], "arrowcolor": p["text"], "arrowsize": 9,
                                   "padding": (2, 0, 2, 0)},
                     "map": {"fieldbackground": [("readonly", p["ground"]), ("disabled", p["ground"])],
                             "background": [("pressed", p["pressed"]), ("active", p["hover"])],
                             "arrowcolor": [("disabled", p["disabled"])],
                             "lightcolor": [("focus", p["accent"])], "bordercolor": [("focus", p["accent"])]}},
        "TCombobox": {"configure": {"fieldbackground": p["field"], "foreground": p["text"], "insertcolor": p["text"],
                                    "background": p["raised"], "bordercolor": p["border"], "lightcolor": p["field"],
                                    "darkcolor": p["raised"], "arrowcolor": p["text"], "padding": 1,
                                    "insertwidth": 1},
                      "map": {"fieldbackground": [("readonly", "focus", p["selection"]), ("readonly", p["raised"]),
                                                  ("disabled", p["ground"])],
                              "foreground": [("disabled", p["disabled"]), ("readonly", "focus", p["selection_text"])],
                              "selectbackground": [("readonly", p["selection"]), ("!focus", p["hover"])],
                              "selectforeground": [("readonly", p["selection_text"]), ("!focus", p["text"])],
                              "background": [("pressed", p["pressed"]), ("active", p["hover"])],
                              "arrowcolor": [("disabled", p["disabled"])],
                              "lightcolor": [("focus", p["accent"])], "bordercolor": [("focus", p["accent"])]}},
        "ComboboxPopdownFrame": {"configure": {"background": p["field"], "bordercolor": p["border"],
                                               "relief": "solid", "borderwidth": 1}},
        "TNotebook": {"configure": {"background": p["ground"], "bordercolor": p["border"], "lightcolor": p["ground"],
                                    "darkcolor": p["ground"], "tabmargins": (2, 2, 2, 0)}},
        "TNotebook.Tab": {"configure": {"background": p["raised"], "foreground": p["text"], "bordercolor": p["border"],
                                        "padding": (2, 1, 2, 1), **flat},
                          "map": {"background": [("selected", p["ground"]), ("active", p["hover"])],
                                  "lightcolor": [("selected", p["ground"]), ("active", p["hover"])],
                                  "darkcolor": [("selected", p["ground"]), ("active", p["hover"])],
                                  "padding": [("selected", (2, 2, 2, 1))]}},
        "Treeview": {"configure": {"background": p["field"], "fieldbackground": p["field"], "foreground": p["text"],
                                   "bordercolor": p["border"], "lightcolor": p["field"]},
                     "map": {"background": [("disabled", p["ground"]), ("selected", p["selection"])],
                             "foreground": [("disabled", p["disabled"]), ("selected", p["selection_text"])]}},
        "Heading": {"configure": {"font": "TkHeadingFont", "relief": "raised", "padding": 3, "background": p["raised"],
                                  "foreground": p["text"], "bordercolor": p["border"], **flat},
                    "map": {"background": [("pressed", p["pressed"]), ("active", p["hover"])],
                            "lightcolor": [("pressed", p["pressed"]), ("active", p["hover"])],
                            "darkcolor": [("pressed", p["pressed"]), ("active", p["hover"])]}},
        "TScrollbar": {"configure": {"background": p["thumb"], "troughcolor": p["ground"], "bordercolor": p["ground"],
                                     "lightcolor": p["thumb"], "darkcolor": p["thumb"], "arrowcolor": p["ground"],
                                     "gripcount": 0},
                       "map": {"background": [("disabled", p["raised"]), ("pressed", p["text"]),
                                              ("active", p["disabled"])],
                               "lightcolor": [("disabled", p["raised"]), ("pressed", p["text"]),
                                              ("active", p["disabled"])],
                               "darkcolor": [("disabled", p["raised"]), ("pressed", p["text"]),
                                             ("active", p["disabled"])],
                               "arrowcolor": [("disabled", p["thumb"])]}},
        "TProgressbar": {"configure": {"background": p["accent"], "troughcolor": p["field"], "bordercolor": p["border"],
                                       "lightcolor": p["accent"], "darkcolor": p["accent"]}},
        "TSeparator": {"configure": {"background": p["border"]}},
        "TLabelframe": {"configure": {"background": p["ground"], "bordercolor": p["border"], "lightcolor": p["ground"],
                                      "darkcolor": p["ground"], "relief": "groove", "borderwidth": 1}},
        "TLabelframe.Label": {"configure": {"background": p["ground"], "foreground": p["text"]}},
        "TPanedwindow": {"configure": {"background": p["ground"]}},
        "Sash": {"configure": {"background": p["raised"], "sashthickness": 6, "gripcount": 0}},
        "TSizegrip": {"configure": {"background": p["ground"]}},
        "TScale": {"configure": {"background": p["raised"], "troughcolor": p["field"], "bordercolor": p["border"],
                                 **flat}},
    }


def _ensure_dark_theme(style: ttk.Style) -> None:
    if DARK_THEME not in style.theme_names():
        style.theme_create(DARK_THEME, parent=BASE_THEME)
    style.theme_settings(DARK_THEME, dark_settings())


def style(widget: tk.Misc, name: str, **options: Any) -> None:
    """The window's own named style *name* (``"Viewer.TCombobox"``) configured with *options* in the theme in use,
    and set again in the new theme whenever the theme changes, as long as *widget* is there."""
    ttk.Style(widget).configure(name, **options)
    kept = _styles.get(name)
    same = kept is not None and kept[0]() is widget
    # (kept by name: a font object's name; the widget weakly, which the style is forgotten with)
    _styles[name] = (weakref.ref(widget), {**(kept[1] if same else {}), **{k: str(v) if isinstance(v, tkfont.Font)
                                                                           else v for k, v in options.items()}})


def _restyle(style_: ttk.Style) -> None:
    for name, (owner_ref, options) in list(_styles.items()):
        owner = owner_ref()
        try:
            alive = owner is not None and bool(owner.winfo_exists())
        except tk.TclError:
            alive = False
        if not alive:
            del _styles[name]
            continue
        try:
            style_.configure(name, **options)
        except tk.TclError:
            del _styles[name]


# ------------------------------------------------------------------ changing the mode
def apply(root: tk.Misc, setting: str, contrast: bool | None = None, dark_system: bool | None = None) -> str:
    """Show the window of *root* in the mode *setting* stands for (`effective`): at the start, before the widgets are
    made, and whenever the setting changes (the widgets already made follow). Nothing happens while the mode stays
    what it is - the light mode at the start among them: Windows' own look is left exactly as it is. The mode."""
    global _mode
    new = effective(setting, contrast, dark_system)
    old = _mode
    if new == old:
        return new
    style_ = ttk.Style(root)
    interp = str(root.tk.interpaddr())
    if new == DARK_MODE:
        _native.setdefault(interp, style_.theme_use())
        _ensure_dark_theme(style_)
        style_.theme_use(DARK_THEME)
    elif old == DARK_MODE:
        style_.theme_use(_native.get(interp, style_.theme_use()))
    if new == DARK_MODE or old == DARK_MODE:
        _restyle(style_)
        _option_database(root, new)
    _mode = new
    _recolour(root, PALETTES[old], PALETTES[new], light=new != DARK_MODE)
    if new == DARK_MODE:
        _watch_title_bars(root)
    if new == DARK_MODE or old == DARK_MODE:
        for window in _toplevels(root):
            _title_bar_for(window, again=True)
    return new


def _class_defaults(root: tk.Misc, command: str) -> list[tuple[str, str, str]]:
    """(option, its name in the option database, its default) of the colour options of Tk's classic widget made by
    *command*, from a widget made for the purpose and gone at once (never on the screen)."""
    path = f"._taslation_theme_{command}"
    root.tk.call(command, path)
    try:
        if command == "toplevel":
            root.tk.call("wm", "withdraw", path)
        found = []
        for spec in root.tk.splitlist(root.tk.call(path, "configure")):
            parts = root.tk.splitlist(spec)
            if len(parts) == 5 and str(parts[0]).lstrip("-") in COLOUR_OPTIONS:
                found.append((str(parts[0]).lstrip("-"), str(parts[1]), str(parts[3])))
        return found
    finally:
        root.tk.call("destroy", path)


def _option_database(root: tk.Misc, new: str) -> None:
    """The option database gives the classic widgets made from now on the colours of *new*: `DARK`'s, or (back to
    light) Tk's own defaults again."""
    reverse = _reverse(LIGHT, light=True)
    for cls, command in {**CLASSIC, "ComboboxPopdown": "toplevel"}.items():
        for _option, name, default in _class_defaults(root, command):
            role = reverse.get(default.lower())
            if role is None:
                continue
            value = DARK[role] if new == DARK_MODE else default
            root.option_add(f"*{cls}.{name}", value, OPTION_PRIORITY)


def _reverse(palette: dict[str, str], light: bool) -> dict[str, str]:
    """A colour of *palette* (lower case) -> its role, for `FOUND_ROLES` (and in the light mode Tk's other names)."""
    found: dict[str, str] = {}
    for role in FOUND_ROLES:
        value = palette[role]
        if value:
            found.setdefault(value.lower(), role)
    if light:
        for name, role in LIGHT_ALIASES.items():
            found.setdefault(name, role)
    return found


def _walk(root: tk.Misc) -> list[str]:
    """Every window under *root*, by its Tcl path (the lists of the comboboxes too, which Tkinter does not know)."""
    paths, queue = [], [str(root)]
    while queue:
        path = queue.pop()
        paths.append(path)
        try:
            queue.extend(str(child) for child in root.tk.splitlist(root.tk.call("winfo", "children", path)))
        except tk.TclError:
            pass
    return paths


def _recolour(root: tk.Misc, old: dict[str, str], new: dict[str, str], light: bool) -> int:
    """The widgets already made, given *new*'s colours where they have *old*'s: a classic widget's grounds and texts,
    a label's colour the window set (a hint, an error), the colours of a tree's tags. A role of `DEFAULTED_ROLES`
    goes back to the widget's own default in the light modes. How many options changed."""
    reverse = _reverse(old, light=old is not DARK)
    call, changed = root.tk.call, 0

    def value_for(role: str, default: str, classic: bool) -> str:
        if light and role in DEFAULTED_ROLES:
            return default
        value = new[role]
        return default if classic and not value else value

    for path in _walk(root):
        try:
            cls = str(call("winfo", "class", path))
            specs = [root.tk.splitlist(spec) for spec in root.tk.splitlist(call(path, "configure"))]
        except tk.TclError:
            continue
        classic = not cls.startswith("T") or cls in ("Tk", "Text", "Toplevel")
        for spec in specs:
            option = str(spec[0]).lstrip("-")
            if len(spec) != 5 or option not in COLOUR_OPTIONS:
                continue
            current = str(spec[4])
            role = reverse.get(current.lower()) if current else None
            if role is None or option not in SELECTION_OPTIONS.get(role, (option,)):
                continue
            value = value_for(role, str(spec[3]), classic)
            if value != current:
                try:
                    call(path, "configure", spec[0], value)
                    changed += 1
                except tk.TclError:
                    pass
        if cls == "Treeview":
            changed += _recolour_tags(root, path, reverse, new, light)
    return changed


def _recolour_tags(root: tk.Misc, path: str, reverse: dict[str, str], new: dict[str, str], light: bool) -> int:
    call, changed = root.tk.call, 0
    try:
        tags = root.tk.splitlist(call(path, "tag", "names"))
    except tk.TclError:
        return 0
    for tag in tags:
        for option in ("-foreground", "-background"):
            try:
                current = str(call(path, "tag", "configure", tag, option))
            except tk.TclError:
                continue
            role = reverse.get(current.lower()) if current else None
            if role is None or role in SELECTION_OPTIONS:
                continue
            value = "" if light and role in DEFAULTED_ROLES else new[role]
            if value != current:
                call(path, "tag", "configure", tag, option, value)
                changed += 1
    return changed


# ------------------------------------------------------------------ the title bars
def _toplevels(root: tk.Misc) -> list[tk.Misc]:
    """The main window and its dialogs that Tkinter knows (the tooltips among them: `_title_bar_for` leaves out what
    has no frame)."""
    found, queue = [], [root]
    while queue:
        widget = queue.pop()
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            found.append(widget)
        try:
            queue.extend(widget.winfo_children())
        except tk.TclError:
            pass
    return found


_dlls: dict[str, Any] = {}  # the system libraries the title bars are drawn with, loaded once with their own types


def _dll(name: str) -> Any:
    """user32 or dwmapi, a loader of this module's own (the argument types set here stay here)."""
    if name not in _dlls:
        import ctypes
        from ctypes import wintypes

        dll = ctypes.WinDLL(name)
        if name == "user32":
            dll.GetAncestor.argtypes, dll.GetAncestor.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
            dll.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
        else:
            dll.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            dll.DwmSetWindowAttribute.restype = ctypes.c_long
        _dlls[name] = dll
    return _dlls[name]


def frame_handle(win: tk.Misc) -> int:
    """The handle of *win*'s frame on the screen, the window its title bar belongs to (0 when there is none)."""
    return int(_dll("user32").GetAncestor(win.winfo_id(), 2) or 0)  # GA_ROOT


def title_bar(hwnd: int, dark: bool, redraw: bool = False) -> bool:
    """Windows 10 (1809 on) and 11 draw the title bar of the window *hwnd* dark or light: DwmSetWindowAttribute with
    DWMWA_USE_IMMERSIVE_DARK_MODE (20; 19 before Windows 10 20H1). *redraw*: the frame is drawn again at once (a
    change while it is on the screen). Whether Windows took it; elsewhere nothing happens."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        import ctypes

        value = ctypes.c_int(1 if dark else 0)
        dwm = _dll("dwmapi")
        done = any(dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0
                   for attribute in (20, 19))
        if done and redraw:
            _dll("user32").RedrawWindow(hwnd, None, None, 0x0401)  # RDW_INVALIDATE | RDW_FRAME
        return done
    except (AttributeError, OSError, ValueError):
        return False


def _title_bar_for(win: Any, again: bool = False) -> None:
    """*win*'s title bar in the mode the window shows, once Windows has its frame: set when it is drawn otherwise,
    left alone in the light modes for a window never drawn dark. *again*: the mode changed while it may be on the
    screen."""
    if not IS_WINDOWS:
        return
    dark = _mode == DARK_MODE
    try:
        path = str(win)
        if not dark and path not in _titles:  # light, and never drawn dark: as Windows draws it
            return
        if not win.winfo_exists() or not win.winfo_ismapped() or win.wm_overrideredirect():
            return
        hwnd = frame_handle(win)
    except (tk.TclError, AttributeError, OSError):
        return
    if not hwnd or _titles.get(path) == (hwnd, dark):
        return
    title_bar(hwnd, dark, redraw=again)
    _titles[path] = (hwnd, dark)


def _watch_title_bars(root: tk.Misc) -> None:
    """Every window of *root*'s interpreter gets its title bar drawn as the mode wants as it comes on the screen,
    and again when Tk has made its frame anew (once per interpreter; light windows never drawn dark are left
    alone)."""
    interp = str(root.tk.interpaddr())
    if interp in _bound:
        return
    _bound.add(interp)
    for cls in ("Tk", "Toplevel"):
        for sequence in ("<Map>", "<Configure>"):
            root.bind_class(cls, sequence, lambda e: _title_bar_for(e.widget), add="+")


# ------------------------------------------------------------------ what other parts draw with
def tooltip_colours() -> tuple[str, str] | None:
    """The tooltips' ground and text while the window is dark; None otherwise (the system's tooltip colours)."""
    return (DARK["tip_ground"], DARK["tip_text"]) if _mode == DARK_MODE else None


def strip_colours(colours: tuple[str, str]) -> tuple[str, str]:
    """A strip's colours over the page (`banner`: a setup problem, a notice, the scan band), given as the light mode
    has them, in the mode the window shows."""
    for ground, text in (("problem_ground", "banner_text"), ("notice_ground", "banner_text"),
                         ("band_ground", "band_text")):
        if tuple(colours) == (LIGHT[ground], LIGHT[text]):
            return colour(ground), colour(text)
    return colours[0], colours[1]


def reset_for_tests(root: tk.Misc | None = None) -> None:
    """Back to the light mode (tests: the shared Tk root is left as it was found)."""
    global _mode
    if root is not None and _mode != LIGHT_MODE:
        apply(root, "light", contrast=False)
    _mode = LIGHT_MODE
    _titles.clear()
