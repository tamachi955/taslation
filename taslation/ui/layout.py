"""The windows' looks and places: the application's icon and taskbar name, the hidden root's first size (it is
never on the screen: `seethrough.hidden`), dialogs placed over the viewer and kept on its monitor, comboboxes and tree
columns as wide as what they show, labels that wrap at a width, and the hidden root's toolbar whose groups of controls
flow into rows (`FlowBar`)."""

from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, Iterable, Sequence

from ..capture import IS_WINDOWS, foreground_owner, foreground_window, give_foreground, monitor_rect, window_exists
from . import area

DEFAULT_SIZE = (1180, 920)  # the window's first size, when the screen's work area has room for it
MIN_SIZE = (820, 600)
ASSETS = Path(__file__).resolve().with_name("assets")
ICON_ICO, ICON_PNG = ASSETS / "taslation.ico", ASSETS / "taslation.png"  # made by tools/make_icon.py
APP_ID = "TASlation.TASlation"  # Windows groups the taskbar button under this, with the window's own icon


# ------------------------------------------------------------------ the window on the screen
def set_app_id() -> None:
    """Windows: the taskbar shows this program as TASlation, with the window's icon rather than Python's. Must come
    before the first window is made."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass


def apply_icon(root: tk.Tk) -> None:
    """The application icon on *root* and on every dialog made after it (Windows: the .ico with all its sizes for
    the title bars and the taskbar; elsewhere the 256 px picture)."""
    try:
        if IS_WINDOWS and ICON_ICO.is_file():
            root.iconbitmap(default=str(ICON_ICO))
        elif ICON_PNG.is_file():
            photo = tk.PhotoImage(master=root, file=str(ICON_PNG))
            root.iconphoto(True, photo)
            root._taslation_icon = photo  # type: ignore[attr-defined]  # Tk shows it only while it is kept
    except tk.TclError:
        pass


def give_icons(win: tk.Misc) -> None:
    """Windows: once *win* is on the screen, its own small and big icons at the sizes the title bar and the taskbar
    draw, which Windows picks from the .ico (Tk gives a window the .ico's first picture, the 16 px one, for both)."""
    if not IS_WINDOWS or not ICON_ICO.is_file():
        return
    done: list[bool] = []

    def on_map(event: tk.Event) -> None:
        if event.widget is not win or done:
            return
        done.append(True)
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32")  # a loader of its own: the argument types set here stay here
            user32.GetAncestor.argtypes, user32.GetAncestor.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                                          ctypes.c_int, wintypes.UINT]
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            hwnd = user32.GetAncestor(win.winfo_id(), 2)  # GA_ROOT: the window the title bar belongs to
            for which, metric in ((1, 11), (0, 49)):  # ICON_BIG at SM_CXICON, ICON_SMALL at SM_CXSMICON
                size = user32.GetSystemMetrics(metric)
                icon = user32.LoadImageW(None, str(ICON_ICO), 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
                if icon and hwnd:
                    user32.SendMessageW(hwnd, 0x0080, which, icon)  # WM_SETICON
        except (AttributeError, OSError, tk.TclError):
            pass

    win.bind("<Map>", on_map, add="+")


def frame_extents() -> tuple[int, int]:
    """A window's side border and its title bar with the top border, in pixels (what a window's place on the screen
    adds to its inside)."""
    if IS_WINDOWS:
        try:
            import ctypes

            metric = ctypes.windll.user32.GetSystemMetrics
            border = metric(32) + metric(92)  # SM_CXFRAME + SM_CXPADDEDBORDER
            return border, metric(4) + metric(33) + metric(92)  # SM_CYCAPTION + SM_CYFRAME + SM_CXPADDEDBORDER
        except (AttributeError, OSError):
            pass
    return 8, 31


def work_area(widget: tk.Misc, x: int | None = None, y: int | None = None) -> tuple[int, int, int, int]:
    """The work area (the screen without the taskbar: left, top, right, bottom) of the monitor at the screen point
    (x, y), or of the primary monitor; outside Windows the whole screen."""
    if IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes

            class MonitorInfo(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                            ("dwFlags", wintypes.DWORD)]

            user32 = ctypes.windll.user32
            user32.MonitorFromPoint.restype = wintypes.HMONITOR
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            point = wintypes.POINT(int(x) if x is not None else 0, int(y) if y is not None else 0)
            monitor = user32.MonitorFromPoint(point, 2 if x is not None else 1)  # nearest; primary
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(MonitorInfo)
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.rcWork
                return r.left, r.top, r.right, r.bottom
        except (AttributeError, OSError, ValueError):
            pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


def monitor_at(x: int, y: int) -> tuple[int, int, int, int] | None:
    """The whole rectangle (left, top, right, bottom) of the monitor that holds the screen point (x, y); None when no
    monitor does (one unplugged since) or outside Windows."""
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        monitor = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 0)  # MONITOR_DEFAULTTONULL
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            r = info.rcMonitor
            return r.left, r.top, r.right, r.bottom
    except (AttributeError, OSError, ValueError):
        pass
    return None


GEOMETRY = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")  # Tk's "WxH+X+Y" (a place left of the primary: "+-1900")


def kept_place(geometry: str, monitor: Any) -> bool:
    """Whether the size and place *geometry* (Tk's "WxH+X+Y"), kept with the rectangle of the monitor it was on, can be
    used again: that monitor is still there, as it was (`monitor_at` its middle gives the same rectangle), and the
    window's title bar lies on it."""
    m = GEOMETRY.match(str(geometry or ""))
    try:
        left, top, right, bottom = (int(v) for v in monitor)
    except (TypeError, ValueError):
        return False
    if m is None or right <= left or bottom <= top:
        return False
    x, y = int(m.group(3)), int(m.group(4))
    if monitor_at((left + right) // 2, (top + bottom) // 2) != (left, top, right, bottom):
        return False
    return left <= x + 40 < right and top <= y + 10 < bottom


def initial_geometry(widget: tk.Misc, size: tuple[int, int] = DEFAULT_SIZE,
                     at: tuple[int, int] | None = None) -> str:
    """The hidden root's first size and place: *size*, or as much of the primary monitor's work area as there is
    (at most the screen less 40 by 90 pixels), in the middle of that work area - or of the work area of the monitor
    at the screen point *at*; its widgets are laid out at that size (the place itself is off every monitor:
    `seethrough.HiddenWindowMixin`). The size is the inside of the window, as Tk's geometry counts it."""
    left, top, right, bottom = work_area(widget) if at is None else work_area(widget, *at)
    border, caption = frame_extents()
    menu = 20
    width = max(200, min(size[0], widget.winfo_screenwidth() - 40, right - left - 2 * border))
    height = max(200, min(size[1], widget.winfo_screenheight() - 90, bottom - top - caption - menu - border))
    x = left + max(0, (right - left - width - 2 * border) // 2)
    y = top + max(0, (bottom - top - height - caption - menu - border) // 2)
    return f"{width}x{height}+{x}+{y}"


def dialog_area(win: tk.Misc, parent: tk.Misc | None = None,
                at: tuple[int, int] | None = None) -> tuple[tuple[int, int, int, int], tuple[int, int]]:
    """The work area (left, top, right, bottom) a dialog is kept on and the screen point it is centred on, as
    `place_window` takes them: the middle of *parent* and the work area of the monitor there (with *at*: that point;
    with neither: the primary monitor's work area and its middle). A parent that says where its dialogs go instead
    (``dialog_centre``: the main window while see-through mode keeps it off the screen) is not looked at."""
    if at is None and parent is not None:
        centre = _centre_instead(parent)
        if centre is not None:
            at = centre
    if at is not None:
        cx, cy = int(at[0]), int(at[1])
        return work_area(win, cx, cy), (cx, cy)
    if parent is not None:
        cx = parent.winfo_rootx() + parent.winfo_width() // 2
        cy = parent.winfo_rooty() + parent.winfo_height() // 2
        return work_area(win, cx, cy), (cx, cy)
    left, top, right, bottom = work_area(win)
    return (left, top, right, bottom), ((left + right) // 2, (top + bottom) // 2)


def _centre_instead(parent: tk.Misc) -> tuple[int, int] | None:
    """Where *parent*'s window says its dialogs go (its ``dialog_centre``), None when it says nothing."""
    try:
        say = getattr(parent.winfo_toplevel(), "dialog_centre", None)
        return say() if callable(say) else None
    except (tk.TclError, AttributeError, TypeError):
        return None


def dialog_spot(size: tuple[int, int], centre: tuple[int, int], area: tuple[int, int, int, int]) -> tuple[int, int]:
    """Where a dialog whose inside is *size* goes (Tk's "+X+Y" of its frame): its frame centred on *centre*, moved
    as needed so that the whole of it, title bar first, lies on *area*."""
    border, caption = frame_extents()
    outer_w, outer_h = int(size[0]) + 2 * border, int(size[1]) + caption + border
    left, top, right, bottom = area
    x = max(left, min(centre[0] - outer_w // 2, right - outer_w))
    y = max(top, min(centre[1] - outer_h // 2, bottom - outer_h))
    return x, y


def place_window(win: tk.Toplevel, parent: tk.Misc | None = None, at: tuple[int, int] | None = None,
                 fit: Callable[[], None] | None = None) -> None:
    """Centre the dialog *win* over *parent* (with no parent: over the primary monitor's work area; with *at*, over
    that screen point instead) and move it as needed so that the whole of it, title bar included, stays on the
    monitor it lands on. It is placed while still withdrawn, so it never shows first somewhere else; *fit*, when
    given, runs then too (a dialog that makes itself lower for the work area). A dialog whose parent is not on the
    screen is left alone. (A dialog on the screen whose content changed: `place_again`.)"""
    try:
        if parent is not None and not parent.winfo_viewable():
            return
        hidden = win.state() == "withdrawn"
        win.withdraw()
        win.update_idletasks()
        if fit is not None:
            fit()
            win.update_idletasks()
        size = re.match(r"(\d+)x(\d+)", win.wm_geometry())
        width, height = (int(size.group(1)), int(size.group(2))) if size else (win.winfo_reqwidth(), win.winfo_reqheight())
        area, centre = dialog_area(win, parent, at)
        x, y = dialog_spot((width, height), centre, area)
        win.geometry(f"+{x}+{y}")
        if not hidden:
            win.deiconify()
    except tk.TclError:
        pass


def asked_size(win: tk.Misc) -> tuple[int, int]:
    """The inside size *win* asks for with what it shows now (a dialog that is not resized by hand has that size)."""
    win.update_idletasks()
    return win.winfo_reqwidth(), win.winfo_reqheight()


def hold_size(win: tk.Toplevel) -> tuple[int, int]:
    """*win* kept at the size it has (`asked_size`) while its content changes, until `place_again` gives it its new
    size and place in one move: it is never seen grown or shrunk where it stood. That size."""
    size = asked_size(win)
    try:
        win.geometry(f"{size[0]}x{size[1]}")
    except tk.TclError:
        pass
    return size


def place_again(win: tk.Toplevel, parent: tk.Misc | None = None, before: tuple[int, int] | None = None) -> bool:
    """The dialog *win*, whose content changed, placed where `place_window` would place a dialog of its new size over
    *parent* (`dialog_area`, `dialog_spot`): centred on it and kept on the work area of the monitor there, its new
    size and place given in one move. It is moved where it stands - never withdrawn, shown again, raised or given the
    focus, so a dialog on the screen takes nothing from the window in front and a hidden one stays hidden. Left where
    it is when its size is still *before* (`hold_size` before the change: the reader may have moved it) or its parent
    is not on the screen. Either way it then takes the size its content asks for (`hold_size` ends). Whether it was
    moved."""
    moved = False
    try:
        size = asked_size(win)
        if (parent is None or parent.winfo_viewable()) and (before is None or tuple(before) != size):
            area, centre = dialog_area(win, parent)
            x, y = dialog_spot(size, centre, area)
            win.geometry(f"{size[0]}x{size[1]}+{x}+{y}")
            win.update_idletasks()  # (moved now, not at the next idle moment)
            moved = True
    except tk.TclError:
        pass
    try:
        win.geometry("")  # (the size its content asks for again: the same now)
        win.update_idletasks()
    except tk.TclError:
        pass
    return moved


def book_monitor(parent: tk.Misc) -> tuple[int, int, int, int] | None:
    """The monitor of the viewer chosen in the window *parent* belongs to, when the window is on another one: where
    the reader looks (a book full screen there, say). None when they share a monitor, with no viewer, outside
    Windows. (See-through mode, the window never on the screen: always the viewer's monitor.)"""
    app = parent._root()
    viewer = getattr(getattr(app, "selected", None), "hwnd", 0) or 0
    own_hwnd = getattr(app, "_own_hwnd", None)
    if not IS_WINDOWS or not viewer or own_hwnd is None:
        return None
    try:
        theirs = monitor_rect(viewer) if window_exists(viewer) else None
        if getattr(app, "_see_hidden", False):
            return theirs
        own = own_hwnd()
        mine = monitor_rect(own) if own else None
    except (OSError, tk.TclError, ValueError):
        return None
    return theirs if theirs is not None and mine is not None and theirs != mine else None


def place_by_book(win: tk.Toplevel, parent: tk.Misc) -> bool:
    """`place_window` over *parent* - but while the viewer chosen in the window is on another monitor
    (`book_monitor`), in the middle of the viewer's monitor and topmost, above a full-screen book there: the reader
    sees it where they read. Whether it went there."""
    monitor = book_monitor(parent)
    if monitor is None:
        place_window(win, parent)
        return False
    place_window(win, parent, at=((monitor[0] + monitor[2]) // 2, (monitor[1] + monitor[3]) // 2))
    stay_on_top(win)
    return True


def stay_on_top(win: tk.Toplevel) -> None:
    """*win* topmost, above a full-screen viewer too, and never activated for it: Windows is asked directly
    (`capture.stay_on_top`, SWP_NOACTIVATE) once the dialog has its frame, so that a dialog shown without the
    foreground (`show_quietly`) stays without it; before that, and outside Windows, Tk's own ``-topmost``."""
    from ..capture import stay_on_top as on_top

    try:
        frame = int(win.wm_frame(), 16)
        framed = IS_WINDOWS and frame != int(win.winfo_id())
    except (tk.TclError, ValueError, AttributeError, TypeError):
        framed, frame = False, 0
    if framed and on_top(frame):
        win._on_top = True  # type: ignore[attr-defined] - (for the tests: Tk's own flag is not set this way)
        return
    try:
        win.attributes("-topmost", True)
    except tk.TclError:
        pass


def show_quietly(win: tk.Toplevel, focus: tk.Misc | None = None) -> None:
    """*win*, a dialog placed and still withdrawn, shown without taking the foreground: Tk's ``wm state normal``
    (SW_SHOWNOACTIVATE; ``wm deiconify`` would raise it and force the focus into it, SetForegroundWindow, which
    Windows lets through while the pointer's last input went to TASlation - a box in Edit), then topmost
    (`stay_on_top`, SWP_NOACTIVATE). It waits in sight until the person clicks it (Windows activates it then: it takes
    the keys, *focus* the first) and is marked meanwhile (``_see_quiet``: `seethrough.front_tick` brings no such
    dialog to the front, a region editor's closing gives the foreground back past it)."""
    win._see_quiet = True  # type: ignore[attr-defined]

    def taken(_event: Any = None) -> None:
        if not getattr(win, "_see_quiet", False):
            return
        win._see_quiet = False  # type: ignore[attr-defined]
        if focus is not None:
            try:
                if win.focus_get() in (None, win):
                    focus.focus_set()
            except (tk.TclError, KeyError):
                pass

    try:
        win.bind("<FocusIn>", taken, add="+")
        win.wm_state("normal")
        win.update_idletasks()
    except tk.TclError:
        return
    stay_on_top(win)


def show_by_itself(win: tk.Toplevel, parent: tk.Misc, focus: tk.Misc | None = None,
                   quiet: bool | None = None) -> bool:
    """*win*, a dialog that came by itself, placed and still withdrawn, shown: quietly while the person is in the
    book or in another program (`show_quietly`; *quiet* None: `seethrough.comes_quietly` decides, True or False:
    decided by the caller), else as ever - shown and given the keys while TASlation's own window has them
    (`dialog_keys`). Either way the viewer gets the foreground back once it closes after the person went to it from the
    book. Whether it came quietly."""
    from . import seethrough

    app = parent._root()
    if quiet is None:
        quiet = seethrough.comes_quietly(app)
    if not quiet:  # (the keys as the dialog is on the screen: at once, or once Tk has mapped it)
        def keys() -> None:
            if not getattr(win, "_by_itself_keys", False):
                win._by_itself_keys = True  # type: ignore[attr-defined]
                dialog_keys(win, parent, focus)

        try:
            win.bind("<Map>", lambda event: keys() if event.widget is win else None, add="+")
            win.deiconify()
            if win.winfo_ismapped():
                keys()
        except tk.TclError:
            pass
        return False
    show_quietly(win, focus)
    _viewer_back(win, app)
    return True


def _viewer_back(win: tk.Toplevel, app: Any) -> None:
    """When *win* goes with TASlation's window in front (the person went to it from the book), the viewer gets the
    foreground back."""
    viewer = getattr(getattr(app, "selected", None), "hwnd", 0) or 0
    if not viewer:
        return

    def back(event: tk.Event) -> None:
        if event.widget is not win:
            return
        try:
            if foreground_owner(foreground_window(), viewer) == "own" and window_exists(viewer):
                give_foreground(viewer)
        except (OSError, RuntimeError):  # the viewer gone meanwhile
            pass

    win.bind("<Destroy>", back, add="+")


def dialog_keys(win: tk.Toplevel, parent: tk.Misc, focus: tk.Misc | None = None) -> None:
    """A dialog on the screen takes the keys only when TASlation's own window has them (the reader is in TASlation:
    *focus*, or the dialog, gets them). One that came by itself while the reader is in the book or in another
    program leaves the foreground where it is - in sight above the book (`place_by_book`), a click gives it the keys
    - and when it closes after the reader went to it from the book, the book gets the foreground back. (A dialog
    that is still to be shown: `show_by_itself`, which shows it without taking the foreground there.)"""
    app = parent._root()
    viewer = getattr(getattr(app, "selected", None), "hwnd", 0) or 0
    try:
        owner = foreground_owner(foreground_window(), viewer) if IS_WINDOWS else "own"
    except OSError:
        owner = "other"
    if owner == "own":
        try:
            win.lift()
            win.focus_force()
            (focus or win).focus_set()
        except tk.TclError:
            pass
        return
    if owner != "viewer" or not viewer:
        return
    _viewer_back(win, app)


def fit_combobox(box: ttk.Combobox, values: Iterable[Any], min_chars: int = 4, max_chars: int = 60) -> None:
    """Make *box* wide enough for its longest entry in its own font (the arrow is drawn beside the text area that
    ``width`` counts in the font's "0" widths)."""
    try:
        font = tkfont.nametofont(str(box.cget("font")) or "TkTextFont")
    except tk.TclError:
        font = tkfont.nametofont("TkTextFont")
    zero = max(1, font.measure("0"))
    widest = max((font.measure(str(v)) for v in values), default=0)
    box.configure(width=max(min_chars, min(max_chars, -(-(widest + 10) // zero))))


def fit_columns(tree: ttk.Treeview, columns: Sequence[tuple[str, str, Sequence[str], int]],
                rows: Sequence[Sequence[Any]]) -> int:
    """Every column of *tree* (id, heading, typical cells, at most so many pixels) as wide as its heading and its
    cells in *rows* (one value per column, the tree's own text first) in the tree's fonts; the first column
    stretches when the tree grows. Returns the tree's width."""
    style = ttk.Style(tree)
    body = tkfont.nametofont(style.lookup("Treeview", "font") or "TkDefaultFont")
    head = tkfont.nametofont(style.lookup("Treeview.Heading", "font") or "TkHeadingFont")
    total = 0
    for i, (column, heading, typical, limit) in enumerate(columns):
        cells = [str(row[i]) for row in rows if i < len(row)] + [str(t) for t in typical]
        width = max([head.measure(heading) + 24] + [body.measure(c) + 18 for c in cells])
        if column == "#0":
            width += 20  # the tree's indent before its text
        width = min(limit, width)
        tree.heading(column, text=heading)
        tree.column(column, width=width, minwidth=min(width, 60), stretch=column == "#0",
                    anchor="w" if column in ("#0", "volumes") else "center")
        total += width
    return total


def wrap_label(label: ttk.Label, width: int) -> None:
    """*label* wraps at *width* pixels (set only when it changes: a new wrap changes the label's height, which
    configures it again)."""
    try:
        width = max(100, int(width))
        if str(label.cget("wraplength")) != str(width):
            label.configure(wraplength=width)
    except tk.TclError:
        pass


# ------------------------------------------------------------------ the toolbar
class FlowBar(ttk.Frame):
    """Groups of controls side by side, a new row whenever the next group would not fit the bar's width: at any
    width every control shows whole. Each group is a frame of its own; the bar lays them out again when its width or a
    group's size changes."""

    def __init__(self, master: tk.Misc, padding: tuple[int, int] = (8, 4), gap: tuple[int, int] = (14, 4)):
        super().__init__(master, height=30)
        self.groups: list[ttk.Frame] = []
        self._pad, self._gap = padding, gap
        self._job: str | None = None
        self.rows = 1
        self.bind("<Configure>", lambda _e: self._schedule())

    def group(self) -> ttk.Frame:
        frame = ttk.Frame(self)
        self.groups.append(frame)
        frame.bind("<Configure>", lambda _e: self._schedule())
        self._schedule()
        return frame

    def _schedule(self) -> None:
        if self._job is None:
            self._job = self.after_idle(self.relayout)

    def relayout(self, width: int | None = None) -> list[tuple[int, int]]:
        """Place the groups for the bar's width (or *width*); the bar takes the height of the rows. Returns where
        each group went."""
        self._job = None
        try:
            if width is None:
                width = self.winfo_width()
                if width < 2:  # not on screen yet: as wide as the window asks to be
                    width = max(self.winfo_reqwidth(), self.winfo_toplevel().winfo_width(), MIN_SIZE[0])
            sizes = [(g.winfo_reqwidth(), g.winfo_reqheight()) for g in self.groups]
            places, height, self.rows = area.flow(sizes, width - 2 * self._pad[0], self._gap[0], self._gap[1])
            for g, (x, y) in zip(self.groups, places):
                g.place(x=self._pad[0] + x, y=self._pad[1] + y)
            height += 2 * self._pad[1]
            if int(self.cget("height")) != height:
                self.configure(height=height)
            return places
        except tk.TclError:  # the window is going
            return []

    def destroy(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        super().destroy()
