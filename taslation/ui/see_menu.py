"""What TASlation offers beyond the side panes, with no window of its own (the hidden Tk root, `seethrough.hidden`,
hosts the dialogs), in places of their own.

* The menu (`build`, `popup`): the left pane's Menu row opens it at the pane's right edge, level with the row
  (`popup_at_pane`), and a click on TASlation's taskbar button while the left pane has no room beside the page opens
  it at the pointer (`seethrough.front_tick`, "button"), with the left pane's controls (Translate, Auto, Translate
  into - the target languages as a cascade -, Lettering, Add area, Set area...) and Settings... and Quit added. While
  the setup banner has buttons
  (Start translator again, Download model, Show viewer, Close), they come first (`banner_actions`: their lines are
  in the right pane). Its entries: the viewer chooser and the book's Series and Volume (`ViewerDialog`,
  `BookDialog`, small dialogs), Saved translations..., Names rendered in more than one way..., Release the model now,
  TASlation's language, and Help (How to use..., Legal notice..., Check for updates..., About TASlation). While the
  left pane's Edit is on, the editing comes first (`see_edit.build_menu`: Undo, Redo, the cascade Page with the
  page's tools and what acts on the regions chosen, then Review..., My corrections..., Lines to review..., Find
  and replace..., Series sheet..., Book settings...). Every entry but Quit counts as the reader asking
  (`seethrough.asked`): a dialog it opens takes the keys.
* The target languages (`languages_at_pane`, `build_targets`): the left pane's language row lists every one at the
  pane's right edge, level with the row, in a menu of the same kind - Windows' popup menu of this process's, so the
  lettering and the panes stay under it (`capture.seethrough.own_menu`), a click on one takes it at once
  (`seethrough.take_language`: the page on show asked for again in it) and ends the list, and a click anywhere else
  (the row again too) or Esc ends it with no change -, each named as the row names it, the one in force ticked: all
  of them in one column while the viewer is tall enough for it (`TARGET_ENTRY_PX` each), else in two, never a list
  to scroll; near the foot of the work area the list goes up from the row's foot instead (`list_top`). The taskbar
  button's menu has them as its cascade Translate into.
* A menu needs its window in front for a click outside it to close it (Windows' rule for a menu of a window that is
  not in front): the hidden window is made the foreground first - the click that opened the menu was the reader's,
  on a pane or the taskbar button of TASlation's -, and `seethrough.front_tick` gives the foreground back to the
  viewer once the menu has ended (``_see_menu_up`` until then).
* No viewer followed: the viewer chooser (`ViewerDialog`) is on the screen (`chooser_tick`) - at every start, once
  the legal notice and the GPU's dialog are over, alone; again when the viewer's window was closed (saying so); never
  while a dialog holds the window, nor for a viewer named with --window (`ViewerMixin._watch_windows` looks for that
  one). TASlation chooses no viewer by itself: the windows that look like it come first and one is preselected,
  Enter or OK chooses it, Quit ends TASlation. Centred over the window preselected, else on the primary monitor,
  topmost; at the start it takes the keys as it shows, after a viewer was closed only while TASlation's window has
  them (`layout.dialog_keys`: a click gives it the keys).
* The setup banner's lines (`StatusMixin._show_banner`): in the right side pane, their buttons in the Menu; with that
  pane switched off, as a small dialog of their own while there is something to say (`show_banner`, `BannerDialog`),
  with the buttons the banner has (Start translator again, Download model, Show viewer, Close). The lines that ask to
  choose a viewer are left to the chooser. Closed by the reader, the dialog stays closed until its lines change."""

from __future__ import annotations

import ctypes
import os
import sys
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Callable, Sequence

from ..i18n import UI_LANGUAGES, _
from . import seethrough
from .banner import break_lines
from .constants import VIEWER_CLOSED, WINDOW_WATCH_MS

MENU_GRACE_MS = 300  # a menu is taken to be up so long after it ended (`_menu_down`)
VIEWER_LIST_CHARS = 48  # the chooser's list, in "0" widths: its entries are shortened in the middle to it
WRAP_PX = 460  # the dialogs' lines are broken this wide (px at the window's scale)
BOOK_CHARS = 30  # the book dialog's Series field
BANNER_LATER_MS = 500  # the banner's lines before Tk has shown the window: their dialog comes so much later
CLOSE_CHARS = 32  # a banner line's Close in the Menu names so many of its first characters
TRANSLATE_INTO = "Translate into"  # the taskbar button's menu: the target languages' cascade
TARGET_ENTRY_PX = 20  # (px at 96 DPI) a target language's entry in the list, a little over what Windows draws (19 px
# at 100 %, measured): one column while the viewer is as tall as all of them, else two
MENU_EDGE_PX = 4  # (px at 96 DPI) a menu's frame above and below its entries (3 px measured)

IS_WINDOWS = sys.platform == "win32"


def init(app: Any) -> None:
    """The state of this module's parts, at see-through mode's start."""
    app._see_menus = {}  # kind ("pane", "button") -> (its menu, the Language menu, the Help menu), kept and refilled
    app._see_targets_menu = None  # the left pane's list of the target languages, kept and refilled
    app._see_menu_opened = []  # (when, kind) of each menu opened, for the tools
    app._see_chooser = None  # the viewer chooser while it is open
    app._see_book_dialog = None
    app._see_banner = None  # the banner's dialog while it is open
    app._see_banner_closed = ()  # the lines it had when the reader closed it


# ------------------------------------------------------------------ the menu
def _asking(app: Any, command: Callable[[], Any]) -> Callable[[], None]:
    def run() -> None:
        seethrough.asked(app)
        command()
    return run


def banner_actions(app: Any) -> list[tuple[str, Callable[[], None]]]:
    """What the setup banner's buttons do (Start translator again, Download model, Show viewer, Close), as the Menu's
    first entries while their lines are in the right pane (``_see_banner_rows``, `StatusMixin._show_banner`): a
    Close names its line's first words."""
    out: list[tuple[str, Callable[[], None]]] = []
    for line, _colours, button in getattr(app, "_see_banner_rows", ()) or ():
        if button is None:
            continue
        text, command = button
        if text == _("Close"):
            words = " ".join(str(line).split())
            text = f"{text}: {words[:CLOSE_CHARS].rstrip()}{'...' if len(words) > CLOSE_CHARS else ''}"
        out.append((text, command))
    return out


def build(app: Any, menu: tk.Menu, language: tk.Menu, help_menu: tk.Menu, full: bool = False) -> None:
    """*menu* filled anew with the entries (see the module's notes), its cascades *language* and *help_menu* too;
    *full*: the taskbar button's menu, with the left pane's controls first (Translate, Auto, Translate into - the
    target languages, `build_targets` -, Lettering, Add area, Set area...: the left pane is not on the screen) and
    Settings... and Quit at its end. The setup banner's buttons come first while it has some (`banner_actions`)."""
    from . import updates
    from .gpu_release import RELEASE_ENTRY, release_now

    for each in (menu, language, help_menu):
        each.delete(0, "end")
    actions = banner_actions(app)
    for text, command in actions:
        menu.add_command(label=text, command=_asking(app, command))
    if actions:
        menu.add_separator()
    from . import see_edit

    if see_edit.on(app):  # (Edit: Undo, Redo, the page's tools, the editing lists; a cascade kept with the menu)
        page = getattr(menu, "_see_page", None)
        if page is None:
            page = menu._see_page = tk.Menu(menu, tearoff=0)
        see_edit.build_menu(app, menu, page)
    if full:
        over = getattr(app, "_see_through", None)
        menu.add_command(label=_("Translate"), command=_asking(app, app.translate_now))
        menu.add_checkbutton(label=_("Auto"), variable=app.auto_var)
        targets = getattr(menu, "_see_targets", None)  # (a cascade kept with the menu, filled anew)
        if targets is None:
            targets = menu._see_targets = tk.Menu(menu, tearoff=0)
        build_targets(app, targets)
        menu.add_cascade(label=_(TRANSLATE_INTO), menu=targets)
        menu._see_lettering = tk.BooleanVar(menu, value=bool(over is None or over.on))  # (kept: Tk's variable)
        menu.add_checkbutton(label=_("Lettering"), command=lambda: seethrough.toggle(app),
                             variable=menu._see_lettering)
        # (Add area as the left pane has it - the Insert key can be switched off -, ticked while a text area is to be
        # added; no dialog, so not the reader asking: the foreground goes back to the viewer as the menu ends)
        menu._see_adding = tk.BooleanVar(menu, value=see_edit.adding(app))
        menu.add_checkbutton(label=_(see_edit.ADD_AREA), command=lambda: see_edit.toggle_adding(app),
                             variable=menu._see_adding)
        menu.add_command(label=_("Set area..."), command=_asking(app, app.set_area))
        menu.add_separator()
    menu.add_command(label=_("Viewer..."), command=_asking(app, lambda: open_viewer(app)))
    menu.add_command(label=_("Series and Volume..."), command=_asking(app, lambda: open_book(app)))
    menu.add_separator()
    menu.add_command(label=_("Saved translations..."), command=_asking(app, app.open_caches))
    menu.add_command(label=_("Names rendered in more than one way..."), command=_asking(app, app.review_names))
    menu.add_command(label=_(RELEASE_ENTRY), command=_asking(app, lambda: release_now(app)))
    menu.add_separator()
    for code, name in UI_LANGUAGES.items():
        language.add_radiobutton(label=name, value=code, variable=app.ui_lang_var,
                                 command=_asking(app, app._on_ui_language))
    menu.add_cascade(label=_("Language"), menu=language)
    help_menu.add_command(label=_("How to use..."), command=_asking(app, app.open_help))
    help_menu.add_command(label=_("Legal notice..."), command=_asking(app, app.open_notice))
    help_menu.add_separator()
    help_menu.add_command(label=updates.menu_label(app), command=_asking(app, app.open_updates))
    help_menu.add_command(label=_("About TASlation"), command=_asking(app, app.open_about))
    menu.add_cascade(label=_("Help"), menu=help_menu)
    if full:
        menu.add_separator()
        menu.add_command(label=_("Settings..."), command=_asking(app, app.open_settings))
        menu.add_command(label=_("Quit"), command=app._on_close)


def menu_for(app: Any, kind: str) -> tuple[tk.Menu, tk.Menu, tk.Menu]:
    """The menu of *kind* ("pane" or "button") with its two cascades, made once and filled anew before each opening
    (`build`): a menu is never destroyed while one of its commands may still be on its way."""
    menus = app.__dict__.setdefault("_see_menus", {})
    made = menus.get(kind)
    try:
        if made is not None and all(m.winfo_exists() for m in made):
            return made
    except tk.TclError:
        pass
    menu = tk.Menu(app, tearoff=0)
    made = (menu, tk.Menu(menu, tearoff=0), tk.Menu(menu, tearoff=0))
    menus[kind] = made
    return made


def popup(app: Any, x: int, y: int, kind: str) -> None:
    """The menu of *kind* at the screen point (*x*, *y*), the hidden window in front while it is up (see the module's
    notes). On Windows Tk's menu runs until it ends (Tk's timers go on meanwhile)."""
    menu, language, help_menu = menu_for(app, kind)
    build(app, menu, language, help_menu, full=kind == "button")
    _track(app, menu, x, y, kind)


def _track(app: Any, menu: Any, x: int, y: int, kind: str) -> None:
    """*menu*, filled, at the screen point (*x*, *y*) until it ends (`popup`; the list of the target languages,
    `languages_at_pane`), the hidden window in front meanwhile."""
    app._see_menu_up = True
    app.__dict__.setdefault("_see_menu_opened", []).append((time.monotonic(), kind))
    _front(seethrough.root_hwnd(app))
    try:
        menu.tk_popup(int(x), int(y))
    except tk.TclError:
        pass
    finally:
        try:
            menu.grab_release()
        except tk.TclError:
            pass
        try:
            app.after(MENU_GRACE_MS, lambda: _menu_down(app))
        except (tk.TclError, RuntimeError):  # (Quit chosen: the window has gone)
            app._see_menu_up = False


def _menu_down(app: Any) -> None:
    """The menu taken to have ended - unless a menu of this process is still on the screen (looked at again); when, for
    `seethrough.front_tick` (the window is in front then, by no click of the reader's)."""
    if _menus_shown():
        try:
            app.after(MENU_GRACE_MS, lambda: _menu_down(app))
            return
        except (tk.TclError, RuntimeError):
            pass
    app._see_menu_up = False
    app._see_closed_at = time.monotonic()


def popup_at_pane(app: Any) -> bool:
    """The left pane's Menu: the menu at the pane's right edge, its top level with the Menu row's. Whether it
    opened."""
    over = getattr(app, "_see_through", None)
    memo = getattr(app, "_see_pane_memo", {}).get("left")
    box = over.pane_shown("left") if over is not None else None
    if box is None or memo is None:
        return False
    top = next((hit[1] for name, hit in memo[1].hits if name == "menu"), 0)
    popup(app, box[2], box[1] + top, "pane")
    return True


# ------------------------------------------------------------------ the target languages
def build_targets(app: Any, menu: tk.Menu, columns: int = 1) -> None:
    """*menu* filled anew with every target language (`seethrough.languages`), each named as the left pane's row names
    it (`seethrough.language_label`), the one in force ticked; a click on one takes it at once
    (`seethrough.take_language`) - no dialog of its own, so not the reader asking: the foreground goes back to the
    viewer as the menu ends. *columns*: 1, or 2 (the second begins halfway down the list)."""
    menu.delete(0, "end")
    names = seethrough.languages(app)
    menu._see_target = tk.StringVar(menu, value=seethrough.target(app))  # (kept: Tk's variable)
    half = -(-len(names) // 2) if columns > 1 else 0
    for i, name in enumerate(names):
        menu.add_radiobutton(label=seethrough.language_label(name), value=name, variable=menu._see_target,
                             command=lambda n=name: seethrough.take_language(app, n),
                             columnbreak=1 if half and i == half else 0)


def target_columns(count: int, height: int, dpi: int) -> int:
    """The columns of the list of *count* target languages beside a viewer *height* px tall (at *dpi*): one while all
    of them fit that height (`TARGET_ENTRY_PX` each, the menu's frame besides), else two - never a list to scroll."""
    from .. import seethrough as st

    need = count * st.scaled(TARGET_ENTRY_PX, dpi) + 2 * st.scaled(MENU_EDGE_PX, dpi)
    return 1 if need <= height else 2


def list_top(top: int, bottom: int, height: int, area: tuple[int, int, int, int]) -> int:
    """Where the top of a list *height* px tall goes beside a row whose top and foot are *top* and *bottom* (screen
    px): level with the row's top, or - with no room for it below that in the work area *area* - going up from the
    row's foot (flipped upwards), never above the work area's top."""
    if top + height <= area[3]:
        return top
    return max(area[1], bottom - height)


def targets_menu(app: Any) -> tk.Menu:
    """The left pane's list of the target languages, made once and filled anew before each opening (a menu is never
    destroyed while one of its commands may still be on its way)."""
    menu = getattr(app, "_see_targets_menu", None)
    try:
        if menu is not None and menu.winfo_exists():
            return menu
    except tk.TclError:
        pass
    menu = app._see_targets_menu = tk.Menu(app, tearoff=0)
    return menu


def languages_at_pane(app: Any) -> bool:
    """The left pane's language row: every target language listed at the pane's right edge, level with the row (see
    the module's notes), in one column or two (`target_columns`, by the viewer's height), going up from the row's foot
    near the foot of the work area (`list_top`). Whether it opened."""
    from .. import seethrough as st
    from .layout import work_area

    over = getattr(app, "_see_through", None)
    memo = getattr(app, "_see_pane_memo", {}).get("left")
    box = over.pane_shown("left") if over is not None else None
    row = next((hit for name, hit in memo[1].hits if name == "language"), None) if memo is not None else None
    if box is None or row is None:
        return False
    dpi = int(getattr(app, "_see_dpi", st.BASE_DPI))
    ground = getattr(app, "_see_ground", None)
    height = int(ground[0][1]) if ground else 0  # (the viewer's frame: its client area's height)
    count = len(seethrough.languages(app))
    columns = target_columns(count, height, dpi)
    menu = targets_menu(app)
    build_targets(app, menu, columns)
    rows = -(-count // columns)
    tall = rows * st.scaled(TARGET_ENTRY_PX, dpi) + 2 * st.scaled(MENU_EDGE_PX, dpi)
    try:  # (Tk's own figure for it, when taller: a larger menu font set on the machine)
        tall = max(tall, int(menu.winfo_reqheight()) + 2 * st.scaled(MENU_EDGE_PX, dpi))
    except (tk.TclError, AttributeError, TypeError, ValueError):
        pass
    x, top, bottom = box[2], box[1] + row[1], box[1] + row[3]
    _track(app, menu, x, list_top(top, bottom, tall, work_area(app, x, top)), "targets")
    return True


# ------------------------------------------------------------------ the foreground for a menu
if IS_WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    _user32.FindWindowExW.restype = wintypes.HWND
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD


def _front(hwnd: int) -> bool:
    """``SetForegroundWindow`` of the hidden window: granted only to the program the reader's click went to, as it
    goes to this one here (nothing forces it). Whether it was granted."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        return bool(_user32.SetForegroundWindow(hwnd))
    except OSError:
        return False


def _menus_shown() -> bool:
    """Whether a menu window of this process is on the screen (Windows' menu class, "#32768")."""
    if not IS_WINDOWS:
        return False
    hwnd, me = None, os.getpid()
    for _ in range(64):
        hwnd = _user32.FindWindowExW(None, hwnd, "#32768", None)
        if not hwnd:
            return False
        pid = wintypes.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == me and _user32.IsWindowVisible(hwnd):
            return True
    return False


# ------------------------------------------------------------------ the dialogs
class _Dialog(tk.Toplevel):
    """A small dialog of the hidden window's: transient of it (no taskbar button of its own), placed by
    `layout.dialog_area` (over the viewer), shown at once. *by_itself*: one that came without being asked for - on
    the viewer's monitor and topmost, taking no key while another program is in front (`layout.place_by_book`,
    `layout.dialog_keys`)."""

    def __init__(self, app: Any, by_itself: bool = False):
        super().__init__(app)
        self.withdraw()
        self.app, self.by_itself = app, by_itself
        self.title("TASlation")
        self.transient(app)
        self.resizable(False, False)
        self.frame = ttk.Frame(self, padding=14)
        self.frame.pack(fill="both", expand=True)

    def show(self, focus: tk.Misc | None = None, at: tuple[int, int] | None = None, keys: bool = False) -> None:
        """Shown, placed over the viewer (*at*: centred on that screen point instead); one that came by itself
        topmost, shown without taking the foreground while the person is in the book or in another program
        (`layout.show_by_itself`: a click gives it the keys) - unless *keys*: it takes them as it shows (the start's
        viewer chooser, the one thing on the screen)."""
        from .layout import dialog_keys, place_by_book, place_window, show_by_itself, stay_on_top

        if self.by_itself:
            if at is not None:
                place_window(self, self.app, at=at)
            else:
                place_by_book(self, self.app)
            stay_on_top(self)
        else:
            place_window(self, self.app, at=at)
        viewable = self.app.winfo_viewable()  # (a window not on the screen, as the tests' root: it stays out of sight)
        if self.by_itself and not keys:
            if viewable:
                show_by_itself(self, self.app, focus)
            else:
                dialog_keys(self, self.app, focus)
            return
        if viewable:
            self.deiconify()
        if keys and self.winfo_viewable():
            try:
                self.lift()
                self.focus_force()
                (focus or self).focus_set()
            except tk.TclError:
                pass
        elif focus is not None:
            focus.focus_set()

    def wrapped(self, parent: tk.Misc, text: str, **options: Any) -> ttk.Label:
        label = ttk.Label(parent, justify="left", **options)
        label.configure(text=break_lines(text, WRAP_PX, label))
        return label


class ViewerDialog(_Dialog):
    """The viewer chooser: a drop-down list of the windows on the screen, each named as its taskbar button is (a
    browser window by its tab and the browser's name: `viewers.entry_titles`, shortened in the middle to the list's
    width), the ones that look like the viewer first and one of them preselected (`viewers.offered`: the viewer
    followed, else the one remembered from an earlier choice, else one with a viewer's part or a reading word in its
    title; none ranking: none, and OK greyed until the person picks one). List again lists the windows again (as the
    list does as it opens, and every WINDOW_WATCH_MS by itself: a viewer opened meanwhile comes into the list,
    preselected while the person has picked nothing). OK (Enter) chooses the window as a pick in the toolbar does
    (`ViewerMixin._on_window_selected`, *picked*: remembered in viewers.json, followed from then on). The last button
    is Quit while no viewer is followed - TASlation then has nothing to do: it ends, as the left pane's Quit does -,
    else Close (the viewer stays as it is); Escape and the dialog's own close do what it does. Nothing is followed,
    shown or read of any window before OK."""

    def __init__(self, app: Any, by_itself: bool = False):
        super().__init__(app, by_itself)
        self.windows: list[Any] = []
        self.pick: int | None = None  # the window the person picked in the list (kept when it is listed again)
        self._seen: tuple[Any, ...] = ()  # the windows as last listed
        self._watch_id: str | None = None
        start = getattr(app, "selected", None) is None and getattr(app, "_viewer_closed", None) is None
        if getattr(app, "selected", None) is None and not start:
            self.wrapped(self.frame, _(VIEWER_CLOSED)).pack(anchor="w", pady=(0, 8))
        self.wrapped(self.frame, _("The window that shows your book. TASlation reads the page from it.")).pack(
            anchor="w")
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text=_("Viewer:")).pack(side="left")
        self.box = ttk.Combobox(row, state="readonly", width=VIEWER_LIST_CHARS, postcommand=self.relist)
        self.box.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.box.bind("<<ComboboxSelected>>", self._picked, add="+")
        buttons = ttk.Frame(self.frame)
        buttons.pack(fill="x", pady=(14, 0))
        self.last_button = ttk.Button(buttons, command=self.close)
        self.last_button.pack(side="right")
        self.ok_button = ttk.Button(buttons, text=_("OK"), command=self.ok)
        self.ok_button.pack(side="right", padx=(0, 6))
        self.again_button = ttk.Button(buttons, text=_("List again"), command=self.relist)
        self.again_button.pack(side="left")
        for key in ("<Return>", "<KP_Enter>"):
            self.bind(key, lambda _e: self.ok())
        self.bind("<Escape>", lambda _e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Destroy>", self._gone, add="+")
        self.relist()
        self.show(self.box, at=self._over_preselected(), keys=by_itself and start)
        self._watch_id = self.after(WINDOW_WATCH_MS, self._watch)

    # ---- the list
    def _width_px(self) -> tuple[Callable[[str], int], int]:
        try:
            font = tkfont.nametofont(str(self.box.cget("font")) or "TkTextFont")
        except tk.TclError:
            font = tkfont.nametofont("TkTextFont")
        return font.measure, VIEWER_LIST_CHARS * max(1, font.measure("0"))

    def relist(self) -> None:
        """The list as the windows are now (the window's own list rescanned): ordered and preselected by
        `viewers.offered`, the person's own pick kept while it is listed."""
        from .viewers import entry_titles, middle_cut, offered

        try:
            self.app._rescan_windows()
        except Exception:  # noqa: BLE001 - the list stays as it was
            pass
        windows = list(getattr(self.app, "windows", []) or [])
        self.windows, first = offered(windows, getattr(self.app, "selected", None))
        self._seen = tuple((w.hwnd, w.title) for w in self.windows)
        measure, room = self._width_px()
        self.box.configure(values=[middle_cut(t, lambda s: measure(s) <= room) for t in entry_titles(self.windows)])
        keep = self.pick if any(w.hwnd == self.pick for w in self.windows) else None
        if keep is None:
            self.pick = None
            keep = first.hwnd if first is not None else None
        index = next((i for i, w in enumerate(self.windows) if w.hwnd == keep), -1)
        if index >= 0:
            self.box.current(index)
        else:
            self.box.set("")
        self._sync()

    def _picked(self, _event: Any = None) -> None:
        index = self.box.current()
        self.pick = self.windows[index].hwnd if 0 <= index < len(self.windows) else None
        self._sync()

    def _sync(self) -> None:
        """OK greyed while nothing is chosen in the list; the last button Quit while no viewer is followed, else
        Close."""
        chosen = 0 <= self.box.current() < len(self.windows)
        self.ok_button.state(["!disabled"] if chosen else ["disabled"])
        quits = getattr(self.app, "selected", None) is None
        self.last_button.configure(text=_("Quit") if quits else _("Close"))

    def _over_preselected(self) -> tuple[int, int] | None:
        """Where the dialog is centred: over the window preselected when it lies on a monitor (none: the primary
        monitor's middle, `layout.dialog_area`)."""
        from .layout import monitor_at

        index = self.box.current()
        if not 0 <= index < len(self.windows):
            return None
        left, top, right, bottom = self.windows[index].rect
        centre = ((left + right) // 2, (top + bottom) // 2)
        return centre if monitor_at(*centre) is not None else None

    def _listed_open(self) -> bool:
        try:
            down = self.box.tk.call("ttk::combobox::PopdownWindow", self.box)
            return bool(int(self.box.tk.call("winfo", "ismapped", down)))
        except (tk.TclError, ValueError):
            return False

    def _watch(self) -> None:
        """(every WINDOW_WATCH_MS while it is open) The list again when the windows changed - not while it is open."""
        self._watch_id = None
        try:
            if not self._listed_open():
                try:
                    self.app._rescan_windows()
                except Exception:  # noqa: BLE001 - looked at again next time
                    pass
                windows = list(getattr(self.app, "windows", []) or [])
                if {(w.hwnd, w.title) for w in windows} != set(self._seen):
                    self.relist()
            self._sync()
            self._watch_id = self.after(WINDOW_WATCH_MS, self._watch)
        except tk.TclError:  # (gone meanwhile)
            pass

    # ---- the buttons
    def ok(self) -> None:
        """The window chosen in the list becomes the viewer, as the toolbar's list chooses one."""
        index = self.box.current()
        if not 0 <= index < len(self.windows):
            self.bell()
            return
        hwnd = self.windows[index].hwnd
        found = next((i for i, w in enumerate(self.app.windows) if w.hwnd == hwnd), None)
        if found is None:
            self.app.refresh_windows()
            found = next((i for i, w in enumerate(self.app.windows) if w.hwnd == hwnd), None)
        if found is None:  # (the window has gone meanwhile)
            self.relist()
            self.bell()
            return
        self.app.window_box.current(found)
        self.app._on_window_selected(picked=True)
        self.destroy()

    def close(self) -> None:
        """Quit while no viewer is followed (TASlation ends, as the left pane's Quit ends it), else Close."""
        quits = getattr(self.app, "selected", None) is None
        self.destroy()
        if quits:
            self.app._on_close()

    def _gone(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        if self._watch_id is not None:
            try:
                self.after_cancel(self._watch_id)
            except tk.TclError:
                pass
            self._watch_id = None
        if getattr(self.app, "_see_chooser", None) is self:
            self.app._see_chooser = None


def open_viewer(app: Any, by_itself: bool = False) -> ViewerDialog:
    """The viewer chooser (the one open brought up)."""
    dialog = getattr(app, "_see_chooser", None)
    try:
        if dialog is not None and dialog.winfo_exists():
            if not by_itself:
                dialog.by_itself = False  # (asked for now)
                dialog._see_quiet = False
                dialog.lift()
                dialog.focus_force()
            return dialog
    except tk.TclError:
        pass
    dialog = ViewerDialog(app, by_itself=by_itself)
    app._see_chooser = dialog
    return dialog


def chooser_tick(app: Any) -> None:
    """(every half second) While no viewer is followed, the viewer chooser is on the screen: from the start's end on
    - the legal notice, then the GPU's memory judged and its dialog answered (``_start_judged``) -, never while a
    dialog holds the window, and again once a viewer chosen was closed; it goes as a viewer is chosen in it. Not for
    a viewer named with --window: the window looks for that one itself (`ViewerMixin._watch_windows`)."""
    from .dialogs.help import modal_up

    if getattr(app, "selected", None) is not None or getattr(app, "_see_chooser", None) is not None:
        return
    if getattr(app, "window_query", "") or not getattr(app, "_start_judged", True) or modal_up(app):
        return
    open_viewer(app, by_itself=True)


class BookDialog(_Dialog):
    """The toolbar's Series and Volume as a dialog (`book_fields.BookFields`, the toolbar's own rules: the name kept
    in its one spelling, `kept_name`; a volume refused said in the dialog): OK sets the book's name as the toolbar's
    fields do once they are left (`fields_committed`); Close leaves it as it was."""

    def __init__(self, app: Any):
        from .book_fields import BookFields, kept_name

        super().__init__(app)
        self.name_var = tk.StringVar(self, value=app.book_var.get())
        self.fields = BookFields(self.frame, self.name_var, series_chars=BOOK_CHARS,
                                 resolve=lambda name: kept_name(app, name), on_refused=self._refused)
        self.fields.pack(fill="x")
        self.refused_label = ttk.Label(self.frame, justify="left")
        buttons = ttk.Frame(self.frame)
        buttons.pack(fill="x", pady=(14, 0))
        self.buttons = buttons
        ttk.Button(buttons, text=_("Close"), command=self.destroy).pack(side="right")
        ttk.Button(buttons, text=_("OK"), command=self.ok).pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Destroy>", self._gone, add="+")
        self.show(self.fields.series)

    def _refused(self, text: str) -> None:
        from .book_fields import refused_line
        from . import theme

        self.refused_label.configure(text=break_lines(refused_line(text), WRAP_PX, self.refused_label),
                                     foreground=theme.colour("error"))
        if not self.refused_label.winfo_manager():
            self.refused_label.pack(anchor="w", pady=(6, 0), before=self.buttons)

    def ok(self) -> None:
        """The fields as the reader leaves them (`BookFields.commit`); a volume refused keeps the dialog open."""
        from .book_fields import fields_committed

        if not self.fields.commit():
            return
        name = self.name_var.get()
        if name != self.app.book_var.get():
            self.app._book_edited = True  # (as a name typed in the toolbar's fields: the reader's)
            self.app.book_var.set(name)
        fields_committed(self.app)
        self.destroy()

    def _gone(self, event: tk.Event) -> None:
        if event.widget is self and getattr(self.app, "_see_book_dialog", None) is self:
            self.app._see_book_dialog = None


def open_book(app: Any) -> BookDialog:
    """Series and Volume... (the one open brought up)."""
    dialog = getattr(app, "_see_book_dialog", None)
    try:
        if dialog is not None and dialog.winfo_exists():
            dialog.lift()
            dialog.focus_force()
            return dialog
    except tk.TclError:
        pass
    dialog = BookDialog(app)
    app._see_book_dialog = dialog
    return dialog


Row = tuple[str, tuple[str, str], "tuple[str, Callable[[], None]] | None"]


class BannerDialog(_Dialog):
    """The setup banner's lines in a dialog of their own that came by itself (see the module's notes): each line in
    the banner's colours with its button, and Close."""

    def __init__(self, app: Any, rows: Sequence[Row]):
        super().__init__(app, by_itself=True)
        self.texts: tuple[str, ...] = ()
        self.body = ttk.Frame(self.frame)
        self.body.pack(fill="both", expand=True)
        close = ttk.Frame(self.frame)
        close.pack(fill="x", pady=(12, 0))
        ttk.Button(close, text=_("Close"), command=self.close).pack(side="right")
        self.bind("<Escape>", lambda _e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Destroy>", self._gone, add="+")
        self.set_rows(rows)
        self.show()

    def set_rows(self, rows: Sequence[Row]) -> None:
        from . import theme

        for child in self.body.winfo_children():
            child.destroy()
        self.texts = tuple(str(line) for line, _colours, _button in rows)
        for line, colours, button in rows:
            bg, fg = theme.strip_colours(colours)
            row = tk.Frame(self.body, bg=bg, bd=0, highlightthickness=0)
            row.pack(fill="x", pady=(0, 4))
            label = tk.Label(row, anchor="w", justify="left", bg=bg, fg=fg, padx=10, pady=4)
            label.configure(text=break_lines(str(line), WRAP_PX, label))
            label.pack(side="left", fill="x", expand=True)
            if button is not None:
                text, command = button
                ttk.Button(row, text=text, command=_asking(self.app, command)).pack(side="right", padx=6, pady=4)

    def close(self) -> None:
        """Closed by the reader: not again for these lines."""
        self.app._see_banner_closed = self.texts
        self.destroy()

    def _gone(self, event: tk.Event) -> None:
        if event.widget is self and getattr(self.app, "_see_banner", None) is self:
            self.app._see_banner = None


def show_banner(app: Any, rows: Sequence[Row]) -> None:
    """The banner's lines *rows* ((line, colours, button or None)) shown in their dialog, which follows their changes;
    none: it goes. Lines the reader closed it on stay unsaid until they change."""
    dialog = getattr(app, "_see_banner", None)
    texts = tuple(str(line) for line, _colours, _button in rows)
    if not rows:
        app._see_banner_closed = ()
        if dialog is not None:
            try:
                dialog.destroy()
            except tk.TclError:
                pass
        return
    if texts == tuple(getattr(app, "_see_banner_closed", ()) or ()):
        return
    try:
        if dialog is None and not app.winfo_viewable() and getattr(app, "_see_through", None) is not None:
            # (the window's start, before Tk has shown it: its dialogs would stay hidden - looked at again soon)
            if not getattr(app, "_see_banner_later", False):
                app._see_banner_later = True
                app.after(BANNER_LATER_MS, lambda: _banner_again(app))
            return
        if dialog is not None and dialog.winfo_exists():
            if dialog.texts != texts:
                from .layout import place_again

                dialog.set_rows(rows)
                place_again(dialog, app)
            return
    except tk.TclError:
        pass
    app._see_banner = BannerDialog(app, rows)


def _banner_again(app: Any) -> None:
    app._see_banner_later = False
    show = getattr(app, "_show_banner", None)
    if show is not None and seethrough.on(app):
        try:
            show()
        except tk.TclError:
            pass
