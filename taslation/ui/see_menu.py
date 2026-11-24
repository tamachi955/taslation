"""See-through mode without TASlation's own window (`seethrough.hidden`): what that window offered and the side panes
do not, in places of their own.

* The menu (`build`, `popup`): the left pane's Menu row opens it at the pane's right edge, level with the row
  (`popup_at_pane`), and a click on TASlation's taskbar button while the left pane has no room beside the page opens
  it at the pointer (`seethrough.front_tick`, "button"), with the left pane's controls (Translate, Auto, Lettering,
  Set area...) and Settings... and Quit added. While the setup banner has buttons
  (Start translator again, Download model, Show viewer, Close), they come first (`banner_actions`: their lines are
  in the right pane). Its entries are the window's own commands and dialogs that still mean something here -
  the viewer chooser and the book's Series and Volume (`ViewerDialog`, `BookDialog`: the toolbar's two controls as
  small dialogs), Saved translations..., Names rendered in more than one way..., Release the model now, the window's
  language, and Help (How to use..., Legal notice..., Check for updates..., About TASlation). While the left pane's
  Edit is on, the editing comes first (`see_edit.build_menu`: Undo, Redo, the cascade Page with the page's tools and
  what the window's Page menu does to the regions chosen, then Review..., My corrections..., Lines to review..., Find
  and replace..., Series sheet..., Book settings...). Left out: what only concerns the window's own page and canvas
  (Show original, what the page and a bubble under the pointer show, Always on top, Over the full-screen viewer,
  Reading-order numbers - Edit numbers the regions itself -, Full screen, Page keys..., Help > Keys...). Every entry
  but Quit counts as the reader asking (`seethrough.asked`): a dialog it opens takes the keys.
* A menu needs its window in front for a click outside it to close it (Windows' rule for a menu of a window that is
  not in front): the hidden window is made the foreground first - the click that opened the menu was the reader's,
  on a pane or the taskbar button of TASlation's -, and `seethrough.front_tick` gives the foreground back to the
  viewer once the menu has ended (``_see_menu_up`` until then).
* No viewer chosen: the viewer chooser comes by itself (`chooser_tick`, CHOOSER_DUE_S after the start, never while a
  dialog holds the window), on the viewer's monitor or the primary one, topmost, taking no key while another program
  is in front (`layout.dialog_keys`: a click gives it the keys), and closes itself once a viewer is chosen - by the
  reader there or by TASlation, which goes on looking for one (`ViewerMixin._watch_windows`). Closed without a
  choice, it comes again only once a viewer has been chosen and lost.
* The setup banner's lines (`StatusMixin._show_banner`): in the right side pane, their buttons in the Menu; with that
  pane switched off, as a small dialog of their own while there is something to say (`show_banner`, `BannerDialog`),
  with the buttons the banner has (Start translator again, Download model, Show viewer, Close). The lines that ask to
  choose a viewer are left to the chooser, and the one that asks to move TASlation aside has no window to move.
  Closed by the reader, the dialog stays closed until its lines change."""

from __future__ import annotations

import ctypes
import os
import sys
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

from ..i18n import UI_LANGUAGES, _
from . import seethrough
from .banner import break_lines

CHOOSER_DUE_S = 2.5  # with no viewer chosen so long after the start, the chooser comes by itself
MENU_GRACE_MS = 300  # a menu is taken to be up so long after it ended (`_menu_down`)
VIEWER_LIST_CHARS = 40  # the chooser's list, in "0" widths (the toolbar's list as it opens)
WRAP_PX = 460  # the dialogs' lines are broken this wide (px at the window's scale)
BOOK_CHARS = 30  # the book dialog's Series field
BANNER_LATER_MS = 500  # the banner's lines before Tk has shown the window: their dialog comes so much later
CLOSE_CHARS = 32  # a banner line's Close in the Menu names so many of its first characters

IS_WINDOWS = sys.platform == "win32"


def init(app: Any) -> None:
    """The state of this module's parts, at see-through mode's start."""
    app._see_menus = {}  # kind ("pane", "button") -> (its menu, the Language menu, the Help menu), kept and refilled
    app._see_menu_opened = []  # (when, kind) of each menu opened, for the tools
    app._see_chooser = None  # the viewer chooser while it is open
    app._see_chooser_declined = False  # one that came by itself was closed with no choice
    app._see_book_dialog = None
    app._see_banner = None  # the banner's dialog while it is open
    app._see_banner_closed = ()  # the lines it had when the reader closed it
    app._see_started = time.monotonic()


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
    *full*: the taskbar button's menu, with the left pane's controls first (Translate, Auto, Lettering, Set area...:
    the left pane is not on the screen) and Settings... and Quit at its end. The setup banner's buttons come first
    while it has some (`banner_actions`)."""
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
        menu._see_lettering = tk.BooleanVar(menu, value=bool(over is None or over.on))  # (kept: Tk's variable)
        menu.add_checkbutton(label=_("Lettering"), command=lambda: seethrough.toggle(app),
                             variable=menu._see_lettering)
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

    def show(self, focus: tk.Misc | None = None) -> None:
        from .layout import dialog_keys, place_by_book, place_window

        if self.by_itself:
            place_by_book(self, self.app)
            try:
                self.attributes("-topmost", True)
            except tk.TclError:
                pass
        else:
            place_window(self, self.app)
        if self.app.winfo_viewable():  # (a window not on the screen, as the tests' root: it stays out of sight)
            self.deiconify()
        if self.by_itself:
            dialog_keys(self, self.app, focus)
        elif focus is not None:
            focus.focus_set()

    def wrapped(self, parent: tk.Misc, text: str, **options: Any) -> ttk.Label:
        label = ttk.Label(parent, justify="left", **options)
        label.configure(text=break_lines(text, WRAP_PX, label))
        return label


class ViewerDialog(_Dialog):
    """The toolbar's Viewer list as a dialog: the windows that may show the book, rescanned as the list opens (as
    the toolbar's is: `ViewerMixin._rescan_windows`), the one chosen in the window first; OK chooses it as a pick in
    the toolbar does (`ViewerMixin._on_window_selected`, *picked*)."""

    def __init__(self, app: Any, by_itself: bool = False):
        super().__init__(app, by_itself)
        self.windows: list[Any] = []
        self.wrapped(self.frame, _("The window that shows your book. TASlation reads the page from it.")).pack(
            anchor="w")
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text=_("Viewer:")).pack(side="left")
        self.box = ttk.Combobox(row, state="readonly", width=VIEWER_LIST_CHARS, postcommand=self.rescan)
        self.box.pack(side="left", fill="x", expand=True, padx=(4, 0))
        buttons = ttk.Frame(self.frame)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text=_("Close"), command=self.close).pack(side="right")
        ttk.Button(buttons, text=_("OK"), command=self.ok).pack(side="right", padx=(0, 6))
        for key in ("<Return>", "<KP_Enter>"):
            self.bind(key, lambda _e: self.ok())
        self.bind("<Escape>", lambda _e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Destroy>", self._gone, add="+")
        self.rescan()
        self.show(self.box)

    def rescan(self) -> None:
        """The list as the windows are now (the window's own list rescanned), the one chosen in the window first."""
        try:
            self.app._rescan_windows()
        except Exception:  # noqa: BLE001 - the list stays as it was
            pass
        self.windows = list(getattr(self.app, "windows", []) or [])
        self.box.configure(values=[w.label() for w in self.windows])
        chosen = getattr(self.app, "selected", None)
        index = next((i for i, w in enumerate(self.windows) if chosen is not None and w.hwnd == chosen.hwnd), None)
        if index is not None:
            self.box.current(index)
        elif self.windows and self.box.current() < 0:
            self.box.current(0)

    def ok(self) -> None:
        """The window in the list chosen as the viewer, as the toolbar's list chooses one."""
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
            self.rescan()
            self.bell()
            return
        self.app.window_box.current(found)
        self.app._on_window_selected(picked=True)
        self.destroy()

    def close(self) -> None:
        """Closed with no choice: one that came by itself comes again only once a viewer has been chosen and lost."""
        if self.by_itself and getattr(self.app, "selected", None) is None:
            self.app._see_chooser_declined = True
        self.destroy()

    def _gone(self, event: tk.Event) -> None:
        if event.widget is self and getattr(self.app, "_see_chooser", None) is self:
            self.app._see_chooser = None


def open_viewer(app: Any, by_itself: bool = False) -> ViewerDialog:
    """The viewer chooser (the one open brought up)."""
    dialog = getattr(app, "_see_chooser", None)
    try:
        if dialog is not None and dialog.winfo_exists():
            if not by_itself:
                dialog.by_itself = False  # (asked for now: it stays once a viewer is chosen)
                dialog.lift()
                dialog.focus_force()
            return dialog
    except tk.TclError:
        pass
    dialog = ViewerDialog(app, by_itself=by_itself)
    app._see_chooser = dialog
    return dialog


def chooser_tick(app: Any, now: float | None = None) -> None:
    """(every half second) With no viewer chosen CHOOSER_DUE_S after the start, the chooser comes by itself (not
    while a dialog holds the window, nor again after the reader closed it - until a viewer is chosen and lost); once
    a viewer is chosen, the one that came by itself goes."""
    from .dialogs.help import modal_up

    now = time.monotonic() if now is None else now
    dialog = getattr(app, "_see_chooser", None)
    if getattr(app, "selected", None) is not None:
        app._see_chooser_declined = False
        if dialog is not None and dialog.by_itself:
            try:
                dialog.destroy()
            except tk.TclError:
                pass
            app._see_chooser = None
        return
    if dialog is not None or getattr(app, "_see_chooser_declined", False):
        return
    if now - float(getattr(app, "_see_started", now)) < CHOOSER_DUE_S or modal_up(app):
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
