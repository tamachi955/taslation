"""See-through mode on the Tk side - the program's one mode since TASlation's own window went (the viewer's window or
its full screen): TASlation's lettering lies over the viewer's own window (`capture.seethrough`), and the viewer takes
every click and key itself in Reader mode (the left pane's switch); while editing (`see_edit`: the Translator role,
the default) the page takes the mouse - every press, move and release over the viewer's client area is TASlation's,
where no window lies over it - and the viewer the keys alone.

* `start` makes the see-through window at the window's start (Windows; and asks the capture for frames up to every
  `wgc.FAST_UPDATE_MS`); where it cannot be made the program says so and ends (`could_not_start`); `close` ends it. `tick` (every TICK_MS) tells it which viewer to lie over and
  hands it the page's patches when they changed (`present`; `_redisplay` asks for that too). The mode's keys are
  Insert, held only while the viewer is in front and only while ``Settings.add_area_key`` is on (`tick`:
  `SeeThrough.set_add_key`; Add area, `see_edit`), and Delete, held only while a region is selected in editing
  (`see_edit.tick`: `SeeThrough.set_delete_key`): every other key goes to the viewer, and the lettering is hidden
  and shown again with the left pane's switch.
* The patches are where the lettered page differs from the frame it was read from - the page filling in (drafts,
  then the final page) and the last translated page -, made by a thread of their own once per change of the page
  (`Patcher`; the Tk thread only notes the change, `present`) and handed over as immutable arrays. Whether a patch
  shows is the see-through window's own decision, at every frame of the viewer's (`taslation.seethrough`: a patch
  belongs to the pixels it was made from), and the patch under the pointer gives way to the original once the pointer
  has rested on it ``hover_delay_ms`` (`hover_delay`). TASlation's own page is not drawn (`LiveViewMixin._redisplay`:
  the window is never on the screen here).
* Which frames start a page job (`frame_look`, `waits`, `reading_frame`): another page only when the steady part of
  the page area changed (`seethrough.steady_thumb` of `steady_area`: bars at its top and bottom come and go without a
  job), never on a frame to wait out (a black with a spinner, half a spread, a washed-out preview), nor on one with
  bars over it until they have stayed BAR_WAIT_S - then it is read with the bars' rows painted over (their words are
  not the book's). Once they have gone (`after_bars`), the page's cached translations are carried over to the frame
  without them, the bubbles that reach those rows (cut by a bar) left out, and the page is read once more for those
  alone (`Pipeline.carry_over`: the lines kept are not asked again). The page on a flat ground of any colour is the
  capture area (`seethrough.ground_box`: a white ground too).
* The side panes (`taslation.panes`, shown by `capture.seethrough`): on the viewer's ground at the capture area's two
  outer edges, or nearer the page where an edge is far from it (`pn.MAX_FROM_PAGE`, from the widest the page has
  been in frames of that size: `pn.reaches`), each where it was while that still does (`_see_pane_places`), so that
  they stand still from spreads to a single page, and a wider page than any before moves them once, only as far as
  it must (`note_frame` keeps the page box at rest, the area's columns, the steady band and the ground's colour),
  LEFT the controls - Translate (Stop while a page can be stopped) with, at the row's right end, a square button drawn
  as a circular arrow that has the page on show translated again (`_again`: the window's Translate again, its lines
  asked of the translator anew; dim until a page was lettered and while the window's Translate is), Auto, the target
  language (a click lists every target language at the pane's right side, `see_menu.languages_at_pane`; one clicked
  there is taken at once, `take_language`), the lettering's switch, the indicators' switch (kept in the settings
  file: ``see_through_indicators``), Reader mode (with TASlation's window hidden; unchecked, the page's regions are
  edited on the overlay, `see_edit`), Add area (a text area drawn on the page, editing or in Reader mode:
  `see_edit.toggle_adding`; pressed while one is to be added; "(Insert)" while that key adds one), Set area...,
  Settings..., Menu (`see_menu`: what the hidden root's controls offer that still means something here), Quit -,
  RIGHT the indicators, a column as high as the steady band (`panes.render_column`) by one rule: what changes
  above, what lasts below (`right_rows`). From the top: the bubble last under the pointer (`bubble_rows`: Copy the
  Japanese, Copy the translation and Ask again, then its Japanese and its translation; kept once the pointer has
  left it, so that the pointer can go to the pane, until another bubble is under it or the viewer shows another
  page: `bubble_tick`; Ask again asks the translator for that line alone, with no question first: `ask_bubble`),
  then the changing lines - the setup banner's, the offline guard's, what the status slot says, the status line,
  the backlog and the pages that went by too fast (the indicator's own lines) -, cut before the foot where the band
  is short: the oldest and least urgent first, the warnings last (`_drop_order`). At the bottom the foot, whose rows
  keep their places whatever the rest says (each of one height: `panes.Row.alike`): how far the page filling in is
  (lines lettered of the lines read; its room kept while none fills in), the mode (editing or Reader mode), where
  the translator runs (the readers too where they run elsewhere), the viewer followed (its title shortened in the
  middle), and the target language with the book where the band has room (`foot_rows`) - the window's words as they
  are: they name the panes' controls and the Menu's entries, no key. The right pane takes a click on the block's
  plates alone; with the indicators switched off the block goes with them. `panes_tick` (every TICK_MS) acts on the
  clicks on the panes and draws a pane again only when what it says changed. A pane that would come near the page
  hides (`panes.place`); the right one leaves the bubble's block out where it does not fit with the foot.
* TASlation's own window is never on the screen in this mode (`hidden`): the Tk root stays the host of the widgets
  and the dialogs, mapped in its normal state - so that its widgets are laid out at their sizes, and its dialogs (Tk
  transients of it) show: Tk keeps a transient of a withdrawn or minimised window hidden - but off every monitor
  (`root_geometry`: up and left of the virtual screen by its own size; every size and place given to it goes there,
  `App.wm_geometry`), at alpha 0, and an application's window: its taskbar button (the title "TASlation" whatever is
  given it, `HiddenWindowMixin.wm_title`, the program's icon; in Alt+Tab as an application is; left out of the
  taskbar's peek, `capture.seethrough.no_peek`) is the way to the program while the panes are hidden, and its Close
  (the button's menu, its thumbnail's X, Alt+F4) quits as the left pane's Quit does (``WM_DELETE_WINDOW``,
  `App._on_close`). Never minimised, maximised or full screen. Its first showing is a quiet one (`quiet_start`'s decoy)
  and takes no foreground. `keep_hidden` puts each of those back should anything have changed it (counted; a
  minimised one at once, `_unmapped`, without activating it). Whenever the window is in front (`front_tick`): a
  dialog of its own on show comes to the front instead; else, the reader having clicked the button (the pointer on
  a taskbar or a button's thumbnails, `capture.seethrough.shell_at`, and no dialog nor menu of TASlation's gone just
  before, CLOSED_S), the viewer chooser while no viewer is chosen, the Menu with the left pane's controls, Settings...
  and Quit at the pointer while the left pane has no room beside the page (`see_menu.popup`, "button"); and
  otherwise the foreground goes back to the viewer (`hand_back`: a dialog of its own closed, a menu ended, the button
  clicked with the panes on the screen). Its dialogs come up alone, over the viewer (`dialog_centre`,
  `layout.dialog_area`), on the viewer's monitor (`layout.book_monitor`); one the reader asked for (from a pane, the
  menu or the button: `asked`) takes the keys as it shows (`_mapped`), and so do the start's own (the legal notice,
  the GPU's box at the start, the viewer chooser at the start, the first book's name). One that comes by itself
  during a session - the setup banner's, a warning box, a question a change of the sheet brought, the GPU's box later
  than the start, the name of a new book - while the person is in the book or in another program comes quietly
  (`comes_quietly`, `layout.show_by_itself`): shown without being activated (``wm state normal``, never ``wm
  deiconify``, which forces the focus), topmost by SWP_NOACTIVATE, on the viewer's monitor; it takes the keys once
  clicked, and `front_tick` brings none such to the front (`_shown_dialogs`). A dialog the person closes gives the
  foreground back to the viewer at once: the region editor in the same call that closes it (`closing`), any other
  at the next idle moment (`_closed`), not at the next tick. With no viewer chosen the viewer chooser comes by itself
  (`see_menu.chooser_due`), and the setup banner's lines come as a small dialog of their own
  (`see_menu.show_banner`).
* The log of the foreground (`foreground_tick`, from `capture.ForegroundNotes`: its hook's notes and the window in
  front at each tick, since the hook does not bring every change): every change of the window in front
  that involves TASlation's windows - to the hidden window, a dialog by its kind, a message box, a menu, the
  lettering, a side pane; from one of them back to the viewer or to another program - and every time the viewer
  loses the foreground while a job is at work is one line in the log (what to what, ms after the last job's start,
  whether a job is at work, whether the page is being edited; no title, no text) and counted (``_see_foreground``): what explains a
  key of the person's that did not reach the book.

Nothing here presses a key or posts a message to the viewer, and nothing but the reader's own choice in a pane, the
menu, the taskbar button or a region being edited, or a dialog of TASlation's own, moves the foreground."""

from __future__ import annotations

import logging
import re
import threading
import time
import tkinter as tk
from typing import Any

import numpy as np
from PIL import Image

from .. import config
from .. import panes as pn
from .. import seethrough as st
from ..capture import seethrough as window
from ..capture import wgc
from ..i18n import _
from ..i18n import current as ui_language
from ..render.lettering import strip_marks
from .constants import PICK_AGAIN, PICK_NO_PAGE, TAB_AWAY, TAB_WAITING

log = logging.getLogger(__name__)
# what the bubble's block says (the window's own words: its popup's buttons and lines, the region editor's)
COPY_JAPANESE, COPY_TRANSLATION = "Copy the Japanese", "Copy the translation"
JAPANESE_COPIED = "The bubble's Japanese is on the clipboard."
TRANSLATION_COPIED = "The bubble's translation is on the clipboard."
READING = "Reading the Japanese..."
NOT_KEPT = "This choice holds until TASlation closes: it could not be kept in the settings file ({error})."
NOT_READ = {"none": "No Japanese was read in this region.",
            "no-ocr": "The reading model is not loaded yet. Try again in a moment."}

TICK_MS = 50
BAR_WAIT_S = 3.5  # a frame with bars over the page is read only once they have stayed so long (a viewer's own bars go
# by themselves in 1-3 s once the pointer rests; bars held longer are painted over in the frame read)
MEMO_KEPT = 4
LOOK_INFO = "taslation.see_look"  # (the picture's info) the look a frame read with its bars painted over was given
PAINTED_INFO = "taslation.see_painted"  # (the picture's info) the rows painted over in it
GONE_LOOK_MS = 150  # once the bars have gone, the viewer is looked at so soon (a page read under them: read_under_bars)
REST_S = 0.3  # a frame not at rest (`note_frame`) is the page at rest once it has stayed so long, no press held
RELEASE_S = 1.0  # ... and one the button was held over, once so long has passed since its release with no other picture
# (`rest_tick`: the viewer had not answered it yet; the live view's RELEASE_ANSWER_MS)
CUT_PX = 3  # a bubble read this close to rows painted over was cut by them (`read_under_bars`)
COMPARE_INFO = "taslation.see_compare"  # (the picture's info) what the patches of a page read from it are compared
# by beyond their own place (`compare_within`); kept when the bars' mark (PAINTED_INFO) goes
EDGE_PX = 2  # a patch's margin keeps so far inside the page box and the capture area (`compare_within`)
# (CUT_PX, EDGE_PX and the patches' and the look's pixel sizes are at 96 DPI: `px` takes them to the viewer's, `tick`)
UNSHOWN_EVERY_S = 1.0  # the page on show's translated regions whose lettering shows not looked at more often
UNSHOWN_SETTLE_S = 0.5  # ... and only once the viewer's frame looked at has been its newest so long
UNSHOWN_LOGGED = 3  # lines a page gives the log of them at the most (`unshown_tick`)


QUIET_MS = 500  # (see-through mode) the decoy of `quiet_start` goes so long after the window's start is made
OFF_GAP = 400  # px between the hidden window's bottom right and the virtual screen's top left (its frame: some 40)
HIDE_EVERY = 10  # ticks (0.5 s) between the looks of `keep_hidden`
ASKED_S = 1.5  # a dialog that shows so soon after the reader asked for something (`asked`) takes the keys
HAND_BACK_WAIT_S = 0.4  # ... and `hand_back` leaves the foreground where it is so long after such a request (the
# dialog it opens is on its way)
CLOSED_S = 0.6  # the window in front so soon after a dialog of its own went or a menu ended is Windows' doing (it
# activates the owner), not a click on its taskbar button (`front_tick`)
BUTTON_TITLE = "TASlation"  # the hidden window's title: its taskbar button's, Alt+Tab's


def px(app: Any, size: int) -> int:
    """*size* px at 96 DPI as many pixels of the viewer's frames (its monitor's DPI, `tick`): a viewer at 125 % or
    150 % draws everything that much larger (`seethrough.scaled`)."""
    return st.scaled(size, getattr(app, "_see_dpi", st.BASE_DPI))


def on(app: Any) -> bool:
    """Whether see-through mode runs in the window *app*."""
    return getattr(app, "_see_through", None) is not None


def quiet_start(app: Any) -> None:
    """At the very start of the window, before Tk first shows it, in see-through mode (Windows): the window made one
    that is never on the screen (`hidden`: titled BUTTON_TITLE here for its taskbar button, alpha 0 and off every
    monitor with `App._apply_alpha` and `App.wm_geometry`, before it is first shown), and Tk kept from taking the
    foreground from the viewer as it shows it: Tk activates the first top-level window it makes (SetActiveWindow when it is first shown - Tk 8.6.15,
    whatever its state: hidden or minimised alike), so the first one it makes is a decoy put inside a frame of the
    window's own (``-use``), a child window, which nothing activates. The window itself is then shown as Tk shows
    every later one, not activated (SW_SHOWNOACTIVATE): the viewer stays in front and takes the reader's keys with no
    click first. Nothing moves the foreground. The decoy goes once the window is shown (`quiet_started`)."""
    app._quiet_decoy = None
    app._quiet_ended = False
    app._see_hidden = False
    if not window.IS_WINDOWS:
        return
    app._see_hidden = True
    try:
        box = tk.Frame(app, container=True)  # (never shown)
        decoy = tk.Toplevel(app, use=str(box.winfo_id()))
        app._quiet_decoy = (decoy, box)
    except tk.TclError:  # (no decoy: the window takes the foreground at its start as ever)
        pass
    try:
        app.wm_title(BUTTON_TITLE)
    except (tk.TclError, AttributeError):
        pass


def quiet(app: Any) -> bool:
    """Whether the window starts quietly (`quiet_start`): not maximised then, for Windows activates a window it
    maximises."""
    return getattr(app, "_quiet_decoy", None) is not None and not getattr(app, "_quiet_ended", False)


def quiet_started(app: Any) -> None:
    """The window's start made (Tk shows it at its first idle, the decoy first): the decoy goes QUIET_MS later."""
    if getattr(app, "_quiet_decoy", None) is None:
        return

    def drop() -> None:
        decoy, app._quiet_decoy = app._quiet_decoy, None
        for widget in decoy or ():
            try:
                widget.destroy()
            except tk.TclError:
                pass

    app.after(QUIET_MS, drop)


def quiet_end(app: Any) -> None:
    """No quiet start after all (the legal notice, which is the reader's to answer: it takes the foreground as
    ever). In see-through mode the window stays off the screen all the same (`hidden`)."""
    app._quiet_ended = True


# ------------------------------------------------------------------ TASlation's own window, never on the screen
def hidden(app: Any) -> bool:
    """Whether TASlation's own window is kept off the screen (see-through mode: see the module's notes)."""
    return bool(getattr(app, "_see_hidden", False))


def off_screen(screen: tuple[int, int, int, int] | None = None) -> tuple[int, int]:
    """Where the hidden window's top left goes: up and left of the virtual screen *screen* ((left, top, width,
    height), every monitor together; `capture.seethrough.virtual_screen` when not given) by its size and OFF_GAP, so
    that a window no larger than every monitor together meets none."""
    left, top, width, height = screen if screen is not None else window.virtual_screen()
    return left - max(width, 1) - OFF_GAP, top - max(height, 1) - OFF_GAP


GEOMETRY_PARTS = re.compile(r"^\s*(?:(\d+)x(\d+))?\s*(?:[+-]-?\d+[+-]-?\d+)?\s*$")


def root_geometry(geometry: str, screen: tuple[int, int, int, int] | None = None) -> str:
    """The size and place *geometry* (Tk's "WxH+X+Y", "WxH" or "+X+Y") as the hidden window takes it: its size kept,
    its place replaced by `off_screen`'s. "" (the size the widgets ask for) and what is no geometry stay as they
    are."""
    text = str(geometry or "")
    m = GEOMETRY_PARTS.match(text)
    if not text.strip() or m is None:
        return text
    x, y = off_screen(screen)
    size = f"{m.group(1)}x{m.group(2)}" if m.group(1) else ""
    return f"{size}+{x}+{y}"


def dialog_centre(app: Any) -> tuple[int, int] | None:
    """Where a dialog of the hidden window is centred (`layout.dialog_area`): the middle of the viewer's window - of
    the part of it on its monitor (the one that holds most of it, `layout.monitor_rect`: a viewer over two monitors,
    or partly off the screen, has its dialogs where it shows) -, or, with none, the middle of the primary monitor's
    work area; None while the window is on the screen (its dialogs go over it, as ever). Never the hidden window's own
    place, off every monitor."""
    if not hidden(app):
        return None
    from . import layout

    win = getattr(app, "selected", None)
    if win is not None:
        try:
            from ..capture import window_exists, window_rect

            if window_exists(win.hwnd):
                return layout.centre_on(window_rect(win.hwnd), layout.monitor_rect(win.hwnd))
        except Exception:  # noqa: BLE001 - (the viewer gone meanwhile: the primary monitor)
            pass
    left, top, right, bottom = layout.work_area(app)
    return (left + right) // 2, (top + bottom) // 2


def dialog_dpi(app: Any) -> int | None:
    """The DPI TASlation's dialogs are drawn for while its own window is hidden (Tk's scaling, `scaling.DpiWatch`'s
    *source*): that of the viewer's monitor once a viewer is followed (``_see_dpi``, `tick`: where they go,
    `dialog_centre`), else of the primary monitor (where the start's go) - never that of the monitor nearest the
    hidden window's place off every monitor; None while the window is on the screen (its own monitor's, as ever)."""
    if not hidden(app):
        return None
    if getattr(app, "selected", None) is not None and getattr(app, "_see_through", None) is not None:
        return int(getattr(app, "_see_dpi", 0) or 0) or None
    from .layout import dpi_at

    return dpi_at()


def root_hwnd(app: Any) -> int:
    """The hidden window's own top-level handle (0 where there is none yet)."""
    try:
        return int(app._own_hwnd() or 0)
    except (tk.TclError, AttributeError, OSError):
        return 0


def keep_hidden(app: Any) -> None:
    """The hidden window as it is to be, every HIDE_EVERY ticks and at once when it was minimised (`_unmapped`): in
    its normal state (never minimised nor maximised: Tk keeps a transient of a minimised window hidden; Tk's ``wm
    state normal`` neither raises nor activates it), alpha 0, an application's window (no tool window: its taskbar
    button), on no monitor - each put back where anything changed it, and counted (``_see_hidden_fixes``) -, and left
    out of the taskbar's peek once its handle is known (`capture.seethrough.no_peek`). Its handle is kept for the
    tools (``_see_root_hwnd``)."""
    if not hidden(app):
        return
    fixes = app.__dict__.setdefault("_see_hidden_fixes", {})
    hwnd = root_hwnd(app)
    app._see_root_hwnd = hwnd
    try:
        state = str(app.tk.call("wm", "state", app._w))
        if state in ("iconic", "zoomed"):
            app.tk.call("wm", "state", app._w, "normal")
            fixes["state"] = fixes.get("state", 0) + 1
        if float(app.tk.call("wm", "attributes", app._w, "-alpha")) != 0.0:
            app.tk.call("wm", "attributes", app._w, "-alpha", 0.0)
            fixes["alpha"] = fixes.get("alpha", 0) + 1
        if int(app.tk.call("wm", "attributes", app._w, "-toolwindow")):
            app.tk.call("wm", "attributes", app._w, "-toolwindow", 0)
            fixes["tool"] = fixes.get("tool", 0) + 1
    except (tk.TclError, ValueError):
        return
    if hwnd and getattr(app, "_see_no_peek", 0) != hwnd and window.no_peek(hwnd):
        app._see_no_peek = hwnd
    facts = window.window_facts(hwnd) if hwnd else None
    if facts is not None and facts["on_monitor"]:
        try:
            app.wm_geometry(root_geometry("+0+0"))
            fixes["place"] = fixes.get("place", 0) + 1
        except tk.TclError:
            pass


def _unmapped(app: Any, event: Any) -> None:
    """(the hidden window unmapped: minimised) Put back in its normal state at once (`keep_hidden`), not activated;
    and when that was a click on its taskbar button while it was in front - the pointer on a taskbar or a button's
    thumbnails, the viewer not minimised with it (Show desktop, Win+M) - what the click asked for done
    (`front_tick`, *clicked*: Windows has given the foreground to another window meanwhile)."""
    if getattr(event, "widget", None) is not app or not hidden(app):
        return
    try:
        if str(app.tk.call("wm", "state", app._w)) != "iconic":
            return
    except tk.TclError:
        return
    clicked = window.shell_at(window.cursor_pos()) and not _viewer_minimised(app)

    def back() -> None:
        keep_hidden(app)
        if clicked:
            front_tick(app, clicked=True)

    try:
        app.after_idle(back)
    except (tk.TclError, RuntimeError):
        pass


def _viewer_minimised(app: Any) -> bool:
    win = getattr(app, "selected", None)
    if win is None:
        return False
    facts = window.window_facts(int(win.hwnd))
    return facts is None or bool(facts["iconic"])


def _closed(app: Any, event: Any) -> None:
    """(a top-level of the window's unmapped or destroyed) When, for `front_tick`: Windows then activates its owner,
    the hidden window, which is no click of the reader's. Tips and popups without a frame are not counted."""
    widget = getattr(event, "widget", None)
    if not isinstance(widget, tk.Toplevel):
        return
    try:
        if widget.wm_overrideredirect():
            return
    except tk.TclError:
        pass
    app._see_closed_at = time.monotonic()
    try:  # (what the tick would do, at once: the viewer back in front once Windows has given the window the foreground)
        app.after_idle(lambda: hidden(app) and front_tick(app))
    except (tk.TclError, RuntimeError, AttributeError):
        pass


def recently_closed(app: Any, within: float = CLOSED_S) -> bool:
    """Whether a dialog of the window's went, or a menu of TASlation's ended, within *within* seconds."""
    return time.monotonic() - float(getattr(app, "_see_closed_at", -1e9)) < within


def own_dialogs(app: Any) -> list[Any]:
    """The dialogs of the hidden window's on the screen (Tk's ``wm stackorder``: mapped, lowest first), each a frame
    of its own - no tip, no popup without a frame, not the start's decoy, not the window itself."""
    try:
        names = app.tk.splitlist(app.tk.call("wm", "stackorder", app._w))
    except (tk.TclError, AttributeError):
        return []
    decoy = getattr(app, "_quiet_decoy", None) or ()
    out = []
    for name in names:
        try:
            widget = app.nametowidget(str(name))
        except (KeyError, tk.TclError):
            continue
        try:
            if widget is app or widget in decoy or not isinstance(widget, tk.Toplevel) or widget.wm_overrideredirect():
                continue
        except tk.TclError:
            continue
        out.append(widget)
    return out


def left_room(app: Any) -> bool:
    """Whether the left pane had room beside the page at the last look (`panes_tick`: its place, None where the
    ground leaves it none or no page on a flat ground was found yet)."""
    memo = (getattr(app, "_see_pane_memo", None) or {}).get("left")
    return memo is not None and memo[2] is not None


def front_tick(app: Any, clicked: bool = False) -> str:
    """The hidden window in front (every tick), or minimised by a click on its taskbar button (*clicked*): what the
    reader is to get instead (see the module's notes) - a dialog of the window's on show comes to the front
    ("dialog"); after a click on the button (the pointer on a taskbar or a button's thumbnails, and no dialog nor menu
    of TASlation's gone just before: CLOSED_S) the viewer chooser while no viewer is chosen ("chooser"), the Menu at
    the pointer while the left pane has no room beside the page ("menu"); else the foreground back to the viewer
    (`hand_back`, "viewer"). Not while a menu of TASlation's is up, nor just after the reader asked for a dialog. ""
    when nothing was done."""
    if not hidden(app) or menu_up(app) or _recently_asked(app, HAND_BACK_WAIT_S):
        return ""
    from ..capture import foreground_window, give_foreground, window_exists

    try:
        hwnd = root_hwnd(app)
        if not hwnd or (not clicked and foreground_window() != hwnd):
            return ""
    except (OSError, RuntimeError):
        return ""
    dialogs = _shown_dialogs(app)  # (one that came by itself and was never clicked waits: the keys go to the book)
    if dialogs:
        try:
            if clicked:
                give_foreground(hwnd)  # (Windows gave the foreground away as it minimised the window)
            dialogs[-1].lift()
            dialogs[-1].focus_force()
        except (tk.TclError, OSError, RuntimeError):
            return ""
        _count(app, "dialog")
        return "dialog"
    point = window.cursor_pos()
    if not (clicked or (not recently_closed(app) and window.shell_at(point))):
        return "viewer" if hand_back(app) else ""
    from . import see_menu

    win = getattr(app, "selected", None)
    try:
        gone = win is None or not window_exists(win.hwnd)
    except (OSError, RuntimeError):
        gone = True
    try:
        if gone:
            if clicked:
                give_foreground(hwnd)
            asked(app)
            see_menu.open_viewer(app)
            _count(app, "chooser")
            return "chooser"
        if not left_room(app) and point is not None:
            if clicked:
                give_foreground(hwnd)  # (a menu needs its window in front)
            _count(app, "menu")
            see_menu.popup(app, point[0], point[1], "button")
            return "menu"
        if clicked:
            give_foreground(win.hwnd)
            _count(app, "viewer")
            return "viewer"
    except (OSError, RuntimeError):
        return ""
    return "viewer" if hand_back(app) else ""


def _count(app: Any, what: str) -> None:
    """What `front_tick` did, counted for the tools (``_see_front``)."""
    counts = app.__dict__.setdefault("_see_front", {})
    counts[what] = counts.get(what, 0) + 1


def asked(app: Any) -> None:
    """The reader asked for something from a pane, the menu or the taskbar button: a dialog that shows within ASKED_S
    takes the keys (`_mapped`), and `hand_back` waits HAND_BACK_WAIT_S."""
    app._see_asked = time.monotonic()


def _recently_asked(app: Any, within: float) -> bool:
    return time.monotonic() - float(getattr(app, "_see_asked", -1e9)) < within


def _mapped(app: Any, event: Any) -> None:
    """(a top-level of the window's is shown) One the reader asked for (`asked`) is lifted and given the keys: it is
    what they wait for. The others are left as their own code has them; tips (no frame) and the start's decoy too."""
    widget = getattr(event, "widget", None)
    if not hidden(app) or not isinstance(widget, tk.Toplevel):
        return
    _remember_kind(app, widget)
    if not _recently_asked(app, ASKED_S) or getattr(widget, "_see_quiet", False):
        return
    try:
        if widget.wm_overrideredirect() or widget in (getattr(app, "_quiet_decoy", None) or ()):
            return
        widget.lift()
        widget.focus_force()
    except tk.TclError:
        pass


def menu_up(app: Any) -> bool:
    """Whether a menu of TASlation's is up (`see_menu.popup`): the window holds the foreground for it meanwhile."""
    return bool(getattr(app, "_see_menu_up", False))


def hand_back(app: Any) -> bool:
    """The hidden window in front (Windows gives it the foreground when a dialog of its own closes, or a menu ended):
    the foreground given back to the viewer, so that the reader's next key goes to the book - not while a menu of
    TASlation's is up, nor just after the reader asked for a dialog (it is on its way: HAND_BACK_WAIT_S). Whether it
    was given back."""
    if not hidden(app) or menu_up(app) or _recently_asked(app, HAND_BACK_WAIT_S):
        return False
    win = getattr(app, "selected", None)
    if win is None:
        return False
    from ..capture import foreground_window, give_foreground, window_exists

    try:
        hwnd = root_hwnd(app)
        if not hwnd or foreground_window() != hwnd or not window_exists(win.hwnd):
            return False
        give_foreground(win.hwnd)
    except (OSError, RuntimeError):
        return False
    app._see_handed_back = int(getattr(app, "_see_handed_back", 0)) + 1
    return True


def _shown_dialogs(app: Any) -> list[Any]:
    """The dialogs of the window's on show that hold the person's attention: `own_dialogs` but those that came by
    themselves and were never clicked (`layout.show_quietly`: they wait in sight, the keys stay where they go)."""
    return [d for d in own_dialogs(app) if not getattr(d, "_see_quiet", False)]


def _typed_in(app: Any) -> bool:
    """Whether the window in front is one the person types in that is TASlation's: a dialog of its own, a message
    box, a menu - not the hidden window (Windows gives it the foreground when a dialog of its own closes, `hand_back`),
    the lettering or a side pane (they never take it: the viewer keeps the keys)."""
    from ..capture import foreground_owner, foreground_window

    win = getattr(app, "selected", None)
    try:
        front = foreground_window()
        if foreground_owner(front, int(win.hwnd) if win is not None else 0) != "own":
            return False
        over = getattr(app, "_see_through", None)
        mine = set(over.own_windows()) if over is not None and hasattr(over, "own_windows") else set()
        return front not in mine | {root_hwnd(app)}
    except (OSError, RuntimeError, AttributeError):
        return False


def comes_quietly(app: Any) -> bool:
    """Whether a dialog of TASlation's that came by itself during a session (the setup banner's, a warning box, a
    question the person's change of the sheet brought, the book's name for a new book...) is shown without taking the
    foreground (`layout.show_by_itself`): TASlation's own window hidden, the person not having asked for anything just
    now (`asked`, ASKED_S) and not in a dialog of TASlation's (`_typed_in`) - the viewer or another program in front:
    the person's keys stay where they go, the dialog waits in sight above the viewer and takes them once it is
    clicked. The start's own dialogs and the ones asked for take the keys as they show."""
    if not hidden(app) or _recently_asked(app, ASKED_S):
        return False
    return not _typed_in(app)


def closing(app: Any, dialog: Any) -> bool:
    """A dialog of the hidden window's that has the keys closing at the person's own act (the region editor's Save,
    Cancel, Close, Escape): the foreground given back to the viewer now, in the same call, before the dialog goes -
    not ~50-400 ms later as `hand_back` would (Windows gives it to the hidden window as the dialog's owner meanwhile,
    and a key pressed then would go to TASlation, not to the book). Only while the dialog (or the hidden window) has
    the foreground, no menu of TASlation's is up and no other dialog of its own holds the person (`_shown_dialogs`).
    A request made before (`asked`) ends with it: a dialog that comes by itself next comes quietly. Whether it was
    given back."""
    if not hidden(app) or menu_up(app):
        return False
    win = getattr(app, "selected", None)
    if win is None:
        return False
    from ..capture import foreground_window, give_foreground, window_exists

    try:
        frame = int(dialog.wm_frame(), 16)
    except (tk.TclError, ValueError, AttributeError, TypeError):
        frame = 0
    if any(d is not dialog for d in _shown_dialogs(app)):
        return False
    try:
        front = foreground_window()
        if not front or front not in (frame, root_hwnd(app)) or not window_exists(win.hwnd):
            return False
        give_foreground(win.hwnd)
    except (OSError, RuntimeError):
        return False
    app._see_asked = -1e9
    app._see_closing = int(getattr(app, "_see_closing", 0)) + 1
    return True


# ------------------------------------------------------------------ the log of the foreground
KINDS_KEPT = 64  # the dialogs' kinds kept by their windows' handles (`_mapped`), the newest
NOT_OURS = ("the viewer", "another program", "nothing")


def _remember_kind(app: Any, widget: Any) -> None:
    """(a top-level of the window's shown) Its kind - its class's name, no title - kept by its window's handle for the
    log of the foreground (`front_kind`): it may be gone by the time the log names it."""
    try:
        frame = int(widget.wm_frame(), 16)
    except (tk.TclError, ValueError, AttributeError, TypeError):
        return
    kinds = app.__dict__.setdefault("_see_kinds", {})
    kinds.pop(frame, None)
    kinds[frame] = type(widget).__name__
    while len(kinds) > KINDS_KEPT:
        kinds.pop(next(iter(kinds)))


def front_kind(app: Any, note: Any) -> str:
    """What came to the front (`capture.Fronted`) as the log of the foreground names it: a window of TASlation's by
    its kind - "the hidden window", "a dialog (its class)", "a message box", "a menu", "the lettering", "a side pane",
    "a window of TASlation's" -, "the viewer" (its window or a popup of it), "another program" or "nothing"."""
    import os

    if not note.hwnd:
        return "nothing"
    if note.pid == os.getpid():
        top = note.root or note.hwnd
        if top == root_hwnd(app):
            return "the hidden window"
        over = getattr(app, "_see_through", None)
        if over is not None and top == getattr(over, "hwnd", 0):
            return "the lettering"
        if over is not None and top in (getattr(over, "panes", {}) or {}).values():
            return "a side pane"
        kind = (getattr(app, "_see_kinds", {}) or {}).get(top)
        if kind:
            return f"a dialog ({kind})"
        if note.own_class == "#32770":
            return "a message box"
        if note.own_class == "#32768":
            return "a menu"
        return "a window of TASlation's"
    win = getattr(app, "selected", None)
    viewer = int(win.hwnd) if win is not None else 0
    if viewer and viewer in (note.hwnd, note.root, note.owner):
        return "the viewer"
    return "another program"


def foreground_tick(app: Any) -> list[str]:
    """(every tick, the window hidden) Each change of the window in front since the last tick (`capture.
    ForegroundNotes`: the hook's notes, and the window in front now when it is not the last one noted - the hook does
    not bring every change) that involves TASlation's windows - to one of them (`front_kind`), or from one of them back to
    the viewer or to another program -, and each time the viewer loses the foreground to anything while a job is at
    work: one line in the log, counted (``_see_foreground``: by where it went; "the viewer lost it in a job" too). Each
    line says from where to where, how many ms after the last job's start it came (`StatusMixin._go_busy`; negative:
    before it), whether a job is at work and whether the page is being edited - no title, no text. This is what explains a key
    of the person's that went elsewhere than the book. The lines, for the tests."""
    notes = getattr(app, "_see_fronts", None)
    if notes is None:
        return []
    from . import see_edit

    lines: list[str] = []
    taken = notes.take()
    app._see_front_notes = int(getattr(app, "_see_front_notes", 0) or 0) + len(taken)  # (the hook's, for a tool)
    look = getattr(notes, "now", None)
    if look is not None:  # (and the window in front now: a change the hook did not bring is not lost)
        front = look()
        last = taken[-1].hwnd if taken else getattr(app, "_see_front_hwnd", None)
        if front.hwnd != last:
            taken.append(front)
            app._see_front_polled = int(getattr(app, "_see_front_polled", 0) or 0) + 1
    if taken:
        app._see_front_hwnd = taken[-1].hwnd
    for note in taken:
        to = front_kind(app, note)
        was = getattr(app, "_see_front_kind", None) or "nothing"
        if to == was:
            continue
        app._see_front_kind = to
        job = bool(getattr(app, "busy", False))
        lost = was == "the viewer" and job
        if to in NOT_OURS and was in NOT_OURS and not lost:
            continue
        counts = app.__dict__.setdefault("_see_foreground", {})
        key = to if to not in NOT_OURS else "back to the viewer" if to == "the viewer" else f"to {to}"
        counts[key] = counts.get(key, 0) + 1
        if lost:
            counts["the viewer lost it in a job"] = counts.get("the viewer lost it in a job", 0) + 1
        since = getattr(app, "_busy_since", None)
        ms = "no job yet" if since is None else f"{round((note.at - float(since)) * 1000)} ms after the last job's start"
        line = (f"foreground: {was} -> {to}; {ms}{', a job at work' if job else ''}; "
                f"editing {'on' if see_edit.on(app) else 'off'}")
        log.info("%s", line)
        lines.append(line)
        kept = app.__dict__.setdefault("_see_foreground_lines", [])  # (the newest, for a tool's report)
        kept.append(line)
        del kept[:-LINES_KEPT]
    return lines


LINES_KEPT = 32  # the newest lines of the log of the foreground kept on the window (`foreground_tick`)


COULD_NOT_START ="TASlation could not lay its lettering over the viewer's window on this computer, and ends."


def could_not_start(app: Any) -> None:
    """The see-through window could not be made (no Windows, or Windows refused it): the reader is told, in a box of
    TASlation's own, and the program ends once it is answered (`App.quit_before_start`, `run_app`)."""
    log.error("see-through mode: the see-through window could not be made; TASlation ends")
    app.quit_before_start = True
    try:
        from .dialogs import caches as boxes

        boxes.tell(app, _(COULD_NOT_START))
    except Exception:  # noqa: BLE001 - (no box either: the log has it)
        pass


class HiddenWindowMixin:
    """TASlation's own window (`app.App`, before ``tk.Tk``) as see-through mode keeps it off the screen (`hidden`):
    every size and place given it keeps its size and goes off every monitor (`root_geometry`), it is never minimised
    nor maximised (Tk keeps a transient of a minimised window hidden; Windows brings a maximised one onto a monitor),
    its title is BUTTON_TITLE whatever is given it (its taskbar button's: no busy title), and its dialogs say where
    they go instead of over it (`dialog_centre`, read by `layout.dialog_area`). Without the mode each of these is Tk's
    own."""

    def wm_title(self, string: str | None = None) -> Any:
        if string is not None and hidden(self):
            string = BUTTON_TITLE
        return super().wm_title(string)  # type: ignore[misc]

    title = wm_title

    def wm_geometry(self, newGeometry: str | None = None) -> Any:  # noqa: N803 - (Tk's own name)
        if newGeometry and hidden(self):
            newGeometry = root_geometry(newGeometry)
        return super().wm_geometry(newGeometry)  # type: ignore[misc]

    geometry = wm_geometry

    def wm_state(self, newstate: str | None = None) -> Any:
        if newstate in ("iconic", "zoomed") and hidden(self):
            return ""
        return super().wm_state(newstate)  # type: ignore[misc]

    state = wm_state

    def wm_iconify(self) -> Any:
        if hidden(self):
            return ""
        return super().wm_iconify()  # type: ignore[misc]

    iconify = wm_iconify

    def dialog_centre(self) -> tuple[int, int] | None:
        """Where a dialog over this window is centred instead (`layout.dialog_area`): while it is off the screen,
        over the viewer; None otherwise."""
        return dialog_centre(self)

    def _apply_alpha(self) -> None:
        """The window unseen (alpha 0) while it is off the screen, before it is first shown (an alpha set later makes
        a browser behind it flicker)."""
        if window.IS_WINDOWS and hidden(self):
            try:
                self.attributes("-alpha", 0.0)  # type: ignore[attr-defined]
            except tk.TclError:
                pass

    def _own_hwnd(self) -> int | None:
        """The window's own top-level handle (None off Windows)."""
        if not window.IS_WINDOWS:
            return None
        import ctypes

        return int(ctypes.windll.user32.GetAncestor(self.winfo_id(), 2))  # type: ignore[attr-defined] - GA_ROOT


def start(app: Any) -> bool:
    """The see-through window made (Windows only); whether it runs - where it does not, the program ends
    (`could_not_start`)."""
    app._see_through = None
    app._see_memo = []
    app._see_bars_since = None
    app._see_rest_box = None
    app._see_rest_size = None  # the size of the frame the rest box was found in (`frame_look`)
    app._see_job = None
    app._see_carries = []  # (when, pages carried over, bubbles left out), see after_bars
    app._see_dpi = st.BASE_DPI  # the viewer's monitor's DPI (`tick`)
    app._see_ground = None  # (frame size, page box, steady band's rows, ground's colour, the capture area's columns)
    # at the last rest (`note_frame`)
    app._see_unrested = None  # (when, page box, ground, frame size, its facts' memo) of a frame not at rest yet (`_aside`)
    app._see_box_seen = None  # ((viewer, frame size), page box) of the frame noted last
    app._see_newest = None  # the facts' memo of the newest frame noted, whatever it was (`note_frame`, `rest_tick`)
    app._see_frame_seen = None  # (its size, its capture area's box) (`note_frame`, `_pick_ground`)
    app._see_box_now = None  # (frame size, page box, since when it stands, the frame's facts) of the newest frame
    # noted (`_note_box`: what the panes are checked against, `_settled`)
    app._see_pane_over = {}  # side -> why it is hidden though placed ("": it is not) (`_clear_of_page`)
    app._see_held_at = 0.0  # when the button was last seen held in the viewer
    app._see_held_memo = None  # the facts' memo of the newest frame noted while it was (`_at_rest`)
    app._see_pane_memo = {}  # side -> (what its picture was made of, the picture, its box) as handed over last
    # ((frame size, columns, dpi), the page's edges seen the panes go by, the panes' edges toward it) (`panes_tick`)
    app._see_pane_places = None
    app._see_clicked = []  # (when, control) of each click acted on, for the tools
    app._see_ticks = 0
    app._see_asked = -1e9  # when the reader last asked for something (`asked`)
    app._see_menu_up = False  # a menu of TASlation's is up (`see_menu.popup`)
    app._see_root_hwnd = 0  # the hidden window's handle, for the tools (`keep_hidden`)
    app._see_hidden_fixes = {}  # what `keep_hidden` put back, counted
    app._see_handed_back = 0  # how often `hand_back` gave the foreground back to the viewer
    app._see_front = {}  # what `front_tick` did instead, counted
    app._see_closed_at = -1e9  # when a dialog of the window's went or a menu ended last (`_closed`)
    app._see_closing = 0  # how often a dialog's closing gave the foreground back at once (`closing`)
    app._see_fronts = None  # the notes of the window in front (`capture.ForegroundNotes`, `foreground_tick`)
    app._see_front_kind = None  # what was in front at the last note (`front_kind`)
    app._see_foreground = {}  # the changes of the foreground that involve TASlation's windows, counted
    app._see_kinds = {}  # a dialog's window -> its kind (`_remember_kind`)
    app._see_no_peek = 0  # the handle left out of the taskbar's peek (`keep_hidden`)
    app._see_patcher = None  # the patch thread (`Patcher`)
    app._see_bubble = None  # (its page's key, its patch's box, chosen when, last on show when): the bubble the right
    # pane shows (`bubble_tick`)
    app._see_reads = {}  # id of a region from the cache -> (its Japanese's reading: "asked", "" done, or why not, when)
    app._see_right_used = "right"  # the right pane's picture handed over: "bubble" (with the bubble's block) or not
    over = window.SeeThrough.start()
    if over is None:
        could_not_start(app)
        return False
    app._see_through = over
    app._see_patcher = Patcher(over)
    wgc.set_update_ms(wgc.FAST_UPDATE_MS)
    if hidden(app):
        from . import see_menu

        see_menu.init(app)
        start_foreground_log(app)
        try:
            app.bind_class("Toplevel", "<Map>", lambda e: _mapped(app, e), add="+")
            for sequence in ("<Unmap>", "<Destroy>"):
                app.bind_class("Toplevel", sequence, lambda e: _closed(app, e), add="+")
            app.bind_class("Tk", "<Unmap>", lambda e: _unmapped(app, e), add="+")
        except tk.TclError:
            pass
    try:
        app._see_job = app.after(TICK_MS, lambda: _tick(app))
    except Exception:  # noqa: BLE001 - no Tk loop (a test): the window runs all the same
        pass
    return True


def start_foreground_log(app: Any) -> None:
    """The notes of the window in front set up on this (Tk's) thread (`foreground_tick`), what is in front now the
    first; where the hook cannot be set, the window in front at each tick is all the log has (none outside
    Windows)."""
    from ..capture import ForegroundNotes

    try:
        notes = ForegroundNotes.start()
    except (OSError, AttributeError):
        notes = None
    app._see_fronts = notes
    if notes is not None:
        first = notes.now()
        app._see_front_kind, app._see_front_hwnd = front_kind(app, first), first.hwnd


def close(app: Any) -> None:
    notes, app._see_fronts = getattr(app, "_see_fronts", None), None
    if notes is not None:
        notes.close()
    patcher, app._see_patcher = getattr(app, "_see_patcher", None), None
    if patcher is not None:
        patcher.close()
    over = getattr(app, "_see_through", None)
    if over is not None:
        app._see_through = None
        events = getattr(getattr(app, "_following", None), "events", None)
        if events is not None and getattr(events, "on_moved", None) == getattr(over, "poke", None):
            events.on_moved = None
        over.close()
        wgc.set_update_ms(wgc.MIN_UPDATE_MS)


def _tick(app: Any) -> None:
    app._see_job = None
    if not on(app):
        return
    try:
        tick(app)
    finally:
        try:
            app._see_job = app.after(TICK_MS, lambda: _tick(app))
        except Exception:  # noqa: BLE001 - the window is going
            pass


def tick(app: Any) -> None:
    """The viewer followed, the patches handed over when they changed, the side panes' clicks acted on and the panes
    drawn again when they changed; with TASlation's own window hidden, the window kept as it is to be (`keep_hidden`),
    the viewer chooser offered while no viewer is chosen, and what the reader gets when the window is in front
    (`front_tick`: a click on its taskbar button, a dialog of its own gone)."""
    over = app._see_through
    win = getattr(app, "selected", None)
    hwnd = int(win.hwnd) if win is not None else 0
    over.follow(hwnd)
    tab_now, set_away = getattr(app, "_tab_now", None), getattr(over, "set_away", None)
    if set_away is not None:  # (a browser window that shows another tab: nothing lettered over it, `_tab_seen`)
        set_away(bool(hwnd) and tab_now is not None and tab_now() != "book")
    events = getattr(getattr(app, "_following", None), "events", None)
    poke = getattr(over, "poke", None)
    if events is not None and poke is not None and getattr(events, "on_moved", None) != poke:
        events.on_moved = poke  # (the viewer moved or resized: the see-through window looks at once, not LOOK_S on)
    before, app._see_dpi = getattr(app, "_see_dpi", None), window.viewer_dpi(hwnd)
    watch = getattr(app, "_dpi_watch", None)
    if app._see_dpi != before and watch is not None and hidden(app):  # (the dialogs drawn for the viewer's monitor)
        watch.check()
    over.set_hover_delay(hover_delay(app))
    set_add_key = getattr(over, "set_add_key", None)
    if set_add_key is not None:  # (the Insert key: Add area while the viewer is in front, `see_edit`)
        set_add_key(hidden(app) and bool(getattr(getattr(app, "settings", None), "add_area_key", True)))
    present(app)
    unshown_tick(app)
    if hidden(app):
        from . import see_edit

        see_edit.tick(app, over)
    panes_tick(app)
    if not on(app) or not hidden(app):  # (Quit on the left pane: the window has gone)
        return
    from . import see_menu

    app._see_ticks = int(getattr(app, "_see_ticks", 0)) + 1
    if app._see_ticks % HIDE_EVERY == 1:
        keep_hidden(app)
        see_menu.chooser_tick(app)
    foreground_tick(app)
    front_tick(app)


def hover_delay(app: Any) -> int:
    """How long (ms) the pointer rests on a patch before it is left out, the original showing there
    (``Settings.hover_delay_ms``, its bounds; 0: at once)."""
    low, high = config.HOVER_DELAY_RANGE
    try:
        value = int(getattr(getattr(app, "settings", None), "hover_delay_ms", 0))
    except (TypeError, ValueError):
        return 0
    return max(low, min(high, value))


def toggle(app: Any) -> None:
    """The left pane's Lettering: the lettering over the viewer hidden, or shown again."""
    over = getattr(app, "_see_through", None)
    if over is not None:
        over.set_on(not over.on)


# ------------------------------------------------------------------ the side panes
def indicators_on(app: Any) -> bool:
    """Whether the right pane, the indicators, is to show (``see_through_indicators``)."""
    return bool(getattr(app.settings, "see_through_indicators", True))


def _get(var: Any, default: Any = None) -> Any:
    try:
        return var.get() if var is not None else default
    except tk.TclError:
        return default


def _stoppable(app: Any) -> bool:
    """Whether a page job can be stopped now (the window's Stop is not greyed)."""
    button = getattr(app, "stop_btn", None)
    try:
        return button is not None and str(button.cget("state")) != "disabled"
    except tk.TclError:
        return False


def languages(app: Any) -> list[str]:
    """The target languages the left pane's list offers (`see_menu.build_targets`): the "To:" box's list (English
    names), the language in force first when it is not one of them."""
    from .constants import LANGUAGES

    names = list(LANGUAGES)
    current = target(app)
    if current and current not in names:
        names.insert(0, current)
    return names


def target(app: Any) -> str:
    """The target language in force (its English name; "" for none)."""
    return str(_get(getattr(app, "lang_var", None), "") or "")


def language_label(language: str) -> str:
    """A target language as the left pane's row and its list name it: in the window's language."""
    from .constants import LANGUAGES

    return _(language) if language in LANGUAGES else language


def _language_shown(app: Any) -> str:
    """The target language as the left pane shows it: the one in force."""
    return language_label(target(app))


def again_enabled(app: Any) -> bool:
    """Whether the left pane's circular arrow (the page on show translated again: `_again`) is live: once a page was
    lettered, and not while the window's Translate is greyed (a job at work for a while)."""
    if getattr(app, "last_result", None) is None:
        return False
    button = getattr(app, "translate_btn", None)
    try:
        return button is None or str(button.cget("state")) != "disabled"
    except tk.TclError:
        return False


def left_rows(app: Any) -> list[pn.Row]:
    """The left pane: what the window offers a reader in the Reader role, the controls a click acts on."""
    over = getattr(app, "_see_through", None)
    again = {"square": "again", "square_enabled": again_enabled(app)}
    first = pn.Row("stop", _("Stop"), **again) if _stoppable(app) else pn.Row("translate", _("Translate"), **again)
    from . import see_edit

    edit = [pn.Row("edit", _(see_edit.READER_MODE), "toggle", on=see_edit.reader_mode(app)),
            pn.Row("add_area", _(see_edit.ADD_AREA), on=see_edit.adding(app))] if hidden(app) else []
    return [first,
            pn.Row("auto", _("Auto"), "toggle", on=bool(_get(getattr(app, "auto_var", None), False))),
            pn.Row("language", _language_shown(app), "list"),
            pn.Row("lettering", _("Lettering"), "toggle", on=bool(over is None or over.on)),
            pn.Row("indicators", _("Indicators"), "toggle", on=indicators_on(app)),
            *edit,
            pn.Row("area", _("Set area...")),
            pn.Row("settings", _("Settings...")),
            pn.Row("menu", _("Menu")),
            pn.Row("quit", _("Quit"))]


MODE_EDITING = "Editing: turn pages with the keys"  # (the right pane's foot; Reader mode: `see_edit.READER_MODE`)
TRANSLATOR_AT = {"gpu": "Translator: on the GPU", "cpu": "Translator: on the processor"}
TRANSLATOR_NOT_YET = "Translator: not loaded yet"
TRANSLATOR_READERS_AT = {("gpu", "cpu"): "Translator: on the GPU; OCR: on the processor",
                         ("cpu", "gpu"): "Translator: on the processor; OCR: on the GPU"}  # (the readers elsewhere)
NO_VIEWER = "Viewer: none chosen"
PROGRESS = "This page: {done} of {total} lines"
FOOT_LINES = 2  # a row of the right pane's foot is wrapped into at most so many lines
READERS_NOT_PLACED = "not_asked"  # (`ocr.place.NOT_ASKED`: the readers' place not judged yet)


def right_rows(app: Any) -> tuple[list[pn.Row], list[pn.Row]]:
    """The right pane's words: (the changing rows, the foot's rows). The changing ones, each only when it has
    something to say, grow down from the pane's top (under the bubble's block): the setup banner's lines (the setup's
    problems and notices, what keeps TASlation from reading the viewer: `StatusMixin._show_banner`; what their
    buttons do is in the Menu, `see_menu.build`) and the offline guard's warning, which TASlation's window would
    show; while the viewer's window shows another tab, a line that says so (`viewers.ViewerMixin._tab_seen`; the
    status line's waiting line left out then; a browser window picked whose tab gave no page yet: how to have the tab
    in front read, `PICK_AGAIN`), and while a browser window picked shows no page with text under its tab, one that
    says so and how to choose the window again (`viewers.ViewerMixin._pick_wait`); the status slot (`status_slot`: what the page cannot show itself), the
    status line, the indicator's lines on the pages behind (the backlog, those that went by too fast: `side_model`);
    those that do not fit above the
    foot are left out, the oldest and least urgent first, the warnings last (`_drop_order`). The foot's rows
    (`foot_rows`) stay at the pane's bottom, where they are whatever the rest says: the line of the page filling in
    (its room kept while none is), the mode, where the translator runs (and the readers where they run elsewhere),
    the viewer followed, the target language and the book where there is room. In the window's words as they are
    (they name the panes' controls and the Menu's entries, no key). The reader's notes on a page (`_show_notes`, the
    window's strip under the page) are left out."""
    from . import status_slot
    from .banner import PROBLEM_COLOURS

    rows: list[pn.Row] = []
    for line, colours, _button in getattr(app, "_see_banner_rows", ()) or ():
        text = str(line).strip()
        if text:
            rows.append(pn.Row("", text, "text", warn=colours == PROBLEM_COLOURS))
    guard = str(_get(getattr(app, "guard_var", None), "") or "").strip()
    if guard:
        rows.append(pn.Row("", guard, "text", warn=True))
    away = bool(getattr(app, "_tab_away", False))
    if away:  # (the viewer's window shows another tab: said in one line, `viewers.ViewerMixin._tab_seen`)
        rows.append(pn.Row("", _(TAB_AWAY), "text"))
        if getattr(app, "_pick_trial", None) is not None:  # (a pick on trial: the tab in front read once chosen)
            rows.append(pn.Row("", _(PICK_AGAIN), "text"))
    elif getattr(app, "_pick_nothing", False):  # (a window picked shows no page with text: `_pick_wait`)
        rows.append(pn.Row("", _(PICK_NO_PAGE), "text"))
    status = str(_get(getattr(app, "status_var", None), "") or "").strip()
    if away and getattr(app, "_status_key", None) == TAB_WAITING:
        status = ""  # (the status line's waiting line says it again, at more length: once)
    side = getattr(app, "_side", None)
    shown = getattr(getattr(side, "slot", None), "shown", None)
    want = shown[0] if shown else None
    slot = status_slot.slot_text(want[0]).strip() if want else ""
    if slot:
        rows.append(pn.Row("", slot, "text", warn=bool(want and want[1])))
    foot = foot_rows(app)
    if status and any(status == row.text for row in (*rows, *foot)):
        status = ""  # (the status line saying a banner's line or a foot's again: once)
    if status:
        rows.append(pn.Row("", status, "text"))
    model = getattr(side, "model", None)
    if model is not None:
        try:
            counts = model.counts()
            backlog = model.backlog
            if backlog.pages > 0:
                rows.append(pn.Row("", _("Working on the others: {pages} page(s), {lines} line(s) to go.").format(
                    pages=backlog.pages, lines=backlog.lines), "text"))
            missed = max(counts["missed"], backlog.dropped)
            if missed:
                rows.append(pn.Row("", _("{n} turned too fast to catch: turn back to them in the viewer to have them read.").format(n=missed), "text"))
        except Exception:  # noqa: BLE001 - the indicator's lines left out
            pass
    return rows, foot


def _readers_at(app: Any) -> str:
    """Where the readers run ("gpu", "cpu"; "" while not judged yet: `ocr.Readers.placement`)."""
    placement = getattr(getattr(getattr(app, "pipeline", None), "ocr", None), "placement", None)
    device = str(getattr(placement, "device", "") or "")
    if placement is None or getattr(placement, "why", "") == READERS_NOT_PLACED or device not in ("gpu", "cpu"):
        return ""
    return device


def _viewer_title(win: Any) -> str:
    try:
        from ..capture import taskbar_title

        return taskbar_title(win)
    except Exception:  # noqa: BLE001 - (a window as the tests make it)
        return str(getattr(win, "title", "") or "")


def foot_rows(app: Any) -> list[pn.Row]:
    """The right pane's foot (`right_rows`), from its top down, each row of one height whatever it says
    (`pn.Row.alike`): the line of the page filling in ("This page: 3 of 8 lines"; its room kept, empty, while no page
    fills in), the mode (TASlation's own window hidden: editing or Reader mode), where the translator runs - and the
    readers, where they run elsewhere - ("not loaded yet" until Ollama's log said), the viewer followed (its title
    shortened in the middle to one line) or none, then - a spare row, left out where the band is short - the target
    language and the book's name (shortened in the middle)."""
    from . import see_edit

    dpi = int(getattr(app, "_see_dpi", st.BASE_DPI))
    fits = pn.fits_line(ui_language(), dpi)
    fill = getattr(app, "_fill", None)
    progress = ""
    if fill is not None and fill.final is None:
        total = sum(1 for s in fill.states if s != "skipped")
        if total:
            progress = _(PROGRESS).format(done=fill.filled, total=total)
    rows = [pn.Row("", progress, "text", lines=FOOT_LINES, alike=(_(PROGRESS).format(done=888, total=888),))]
    if hidden(app):
        editing, reading = _(MODE_EDITING), _(see_edit.READER_MODE)
        rows.append(pn.Row("", reading if see_edit.reader_mode(app) else editing, "text", lines=FOOT_LINES,
                           alike=(editing, reading)))
    where, readers = getattr(app, "_compute_where", ""), _readers_at(app)
    if where in TRANSLATOR_AT:
        text = _(TRANSLATOR_READERS_AT.get((where, readers)) or TRANSLATOR_AT[where])
    else:
        text = _(TRANSLATOR_NOT_YET)
    rows.append(pn.Row("", text, "text", lines=FOOT_LINES, alike=tuple(
        _(t) for t in (TRANSLATOR_NOT_YET, *TRANSLATOR_AT.values(), *TRANSLATOR_READERS_AT.values()))))
    win = getattr(app, "selected", None)
    if win is not None:
        head, _mark, tail = _("Viewer: {title}").partition("{title}")
        title = pn.middle_cut(_viewer_title(win), lambda t: fits(head + t + tail))
        rows.append(pn.Row("", head + title + tail, "text", lines=1))
    else:
        rows.append(pn.Row("", _(NO_VIEWER), "text", lines=1))
    language = _language_shown(app)
    book = str(_get(getattr(app, "book_var", None), "") or "").strip()
    if book:
        lead = f"{language} · "
        text = lead + pn.middle_cut(book, lambda b: fits(lead + b))
    else:
        text = language
    rows.append(pn.Row("", text, "text", lines=1, spare=True))
    return rows


def _drop_order(app: Any, rows: list[pn.Row]) -> tuple[int, ...]:
    """The order the changing rows of the right pane are left out in where they do not fit above its foot: the
    oldest first (since when each text has been shown: ``_see_row_seen``, by its words), the warnings last."""
    now = time.monotonic()
    seen: dict[str, float] = app.__dict__.setdefault("_see_row_seen", {})
    texts = {row.text for row in rows}
    for text in [t for t in seen if t not in texts]:
        del seen[text]
    for text in texts:
        seen.setdefault(text, now)
    return tuple(sorted(range(len(rows)), key=lambda i: (rows[i].warn, seen[rows[i].text], -i)))


def _picture(app: Any, side: str, rows: list[pn.Row], room: int, language: str, dpi: int,
             scheme: pn.Colours) -> pn.Picture | None:
    """The picture of the pane *side* of *rows* in the *room* its ground leaves (None: it does not fit), made again
    only when what it is made of changed. The right one is as wide as the room lets it (MAX_W at the most), whatever
    it says: only its height changes with its words."""
    if not rows:
        return None
    width = pn.width_for(rows, language, dpi, room, fill=side in ("right", "bubble"))
    if width is None:
        return None
    key = (tuple(rows), width, language, dpi, scheme)
    memo = app._see_pane_memo.get(side)
    if memo is not None and memo[0] == key:
        return memo[1]
    picture = pn.render(rows, width, language, dpi, scheme)
    app._see_pane_memo[side] = (key, picture, None)
    return picture


def _column(app: Any, side: str, block: list[pn.Row], changing: list[pn.Row], foot: list[pn.Row],
            drop: tuple[int, ...], room: int, height: int, language: str, dpi: int,
            scheme: pn.Colours) -> pn.Picture | None:
    """The right pane's picture (`pn.render_column`: the bubble's *block* and the *changing* rows from the top, the
    *foot* at the bottom of the column *height* px high) in the *room* its ground leaves (None: it does not fit, or
    has nothing to say), made again only when what it is made of changed."""
    rows = [*block, *changing, *foot]
    if not rows:
        return None
    width = pn.width_for(rows, language, dpi, room, fill=True)
    if width is None:
        return None
    key = (tuple(block), tuple(changing), tuple(foot), drop, width, height, language, dpi, scheme)
    memo = app._see_pane_memo.get(side)
    if memo is not None and memo[0] == key:
        return memo[1]
    picture = pn.render_column(block, changing, foot, width, height, language, dpi, scheme, drop)
    if picture is None:
        return None
    app._see_pane_memo[side] = (key, picture, None)
    return picture


def pane_on_screen(box: tuple[int, int, int, int] | None, origin: tuple[int, int] | None
                   ) -> tuple[int, int, int, int] | None:
    """A side pane's *box* (frame pixels) while the whole of it lies on the monitors - its four corners each on one,
    the viewer's client area at *origin* on the screen -; None where part of it is off them (a viewer dragged partly
    off the screen, past an outer edge or into a gap between monitors): it hides, as one with no room beside the page
    does, and the Menu comes from the taskbar button (`left_room`). As it is where the viewer's place is not known,
    and outside Windows."""
    if box is None or origin is None or not window.IS_WINDOWS:
        return box
    from .layout import monitor_at

    x, y = int(origin[0]), int(origin[1])
    corners = ((box[0], box[1]), (box[2] - 1, box[1]), (box[0], box[3] - 1), (box[2] - 1, box[3] - 1))
    return box if all(monitor_at(cx + x, cy + y) is not None for cx, cy in corners) else None


def panes_tick(app: Any) -> None:
    """The clicks on the side panes acted on, the bubble the right one shows followed (`bubble_tick`), then both panes
    handed to the see-through window as they are to be: on the ground at the capture area's outer edges or nearer the
    page, beside the page at the last rest - placed by the widest the page has been in frames of this size
    (`pn.reaches`) and where they were (`pn.place`'s *before*, both in `_see_pane_places`), so that they stand still
    from spreads to a single page -, or hidden (no page on a flat ground yet, no room, the right one switched off).
    The page they go by reaches at the least to the page box of the frame on show once it has stood (`_settled`) and,
    with a capture area set by hand that leaves them room beyond it, to the area's edges: they stand outside it then
    (`_book_columns`); after the placement no pane shown lies over the frame on show's page or in that area
    (`_clear_of_page`). While a browser window picked shows no page of a book in its tab and no page on a flat
    ground (a page of text, a blank tab: `viewers.ViewerMixin._pick_nothing`) they stand in the viewer's window all
    the same (`_pick_ground`), the right one saying so - nothing else would. The right one is a column as high as
    the band (`pn.column_height`): the bubble's block and the changing rows from its top down, its foot at the
    bottom, the foot's rows where they stay (`right_rows`); the bubble's block only where it fits with the foot, else
    the indicators alone; its plates' boxes go with it (the window lets it take a click there alone)."""
    over = getattr(app, "_see_through", None)
    if over is None:
        return
    for side, x, y, _t in over.take_clicks():
        if pane_click(app, side, x, y) == "quit":
            return  # (the window has gone)
    bubble_tick(app, over)
    rest_tick(app)
    ground = getattr(app, "_see_ground", None)
    made_up = ground is None and bool(getattr(app, "_pick_nothing", False))
    if made_up:
        ground = _pick_ground(app)
    if ground is None:
        for side, memo in list(app._see_pane_memo.items()):
            app._see_pane_memo[side] = (memo[0], memo[1], None)  # (a click comes to nothing)
        over.set_panes(None, None)
        return
    size, page, band, colour, columns = ground
    dpi = getattr(app, "_see_dpi", st.BASE_DPI)
    book, columns = _book_columns(app, size, dpi, columns)  # (outside an area set by hand, where it leaves room)
    settled = _settled(app, size)
    if settled is not None and settled[0] is not None:  # (the page of the frame on show, whatever the ground's was)
        now = settled[0]
        page = (min(page[0], now[0]), page[1], max(page[2], now[2]), page[3])
    if book is not None:  # (the capture area set by hand: the least the page reaches to)
        page = (page[0] if book[0] is None else min(page[0], book[0]), page[1],
                page[2] if book[1] is None else max(page[2], book[1]), page[3])
    language = ui_language()
    scheme = pn.colours(colour)
    rows = left_rows(app)
    changing, foot = right_rows(app) if indicators_on(app) else ([], [])
    # the page box the panes go by: the widest the page has been in frames alike (`pn.reaches`), so that they stand
    # still from spreads to a single page; their places there kept too (`pn.place`'s *before*)
    key = (tuple(size), tuple(columns) if columns else None, dpi)
    kept = getattr(app, "_see_pane_places", None)
    seen, before = (kept[1], kept[2]) if kept is not None and kept[0] == key else ((None, None), None)
    if made_up:
        seen, before = (None, None), None  # (no page: the made-up one neither goes by nor leaves a page seen)
    indicators = [*changing, *foot]
    fits = (lambda room: pn.width_for(rows, language, dpi, room) is not None,
            lambda room: bool(indicators) and pn.width_for(indicators, language, dpi, room, fill=True) is not None)
    reach = pn.reaches(size, page, seen, fits, dpi, columns)
    wide = (page[0] if reach[0] is None else reach[0], page[1], page[2] if reach[1] is None else reach[1], page[3])
    room_left, room_right = pn.rooms(size, wide, dpi, columns)
    left = _picture(app, "left", rows, room_left, language, dpi, scheme)
    left_size = left.size if left else None
    drop = _drop_order(app, changing)
    block = bubble_rows(app) if indicators_on(app) else []
    height = pn.column_height(size, band, dpi)
    used = "bubble"
    right = _column(app, used, block, changing, foot, drop, room_right, height, language, dpi, scheme) if block else None
    box_left, box_right = pn.place(size, wide, band, left_size, right.size if right else None, dpi, columns,
                                   before=before)
    if right is None or box_right is None:  # (no bubble, or no room for its block: the indicators alone)
        used = "right"
        right = _column(app, used, [], changing, foot, drop, room_right, height, language, dpi, scheme)
        box_left, box_right = pn.place(size, wide, band, left_size, right.size if right else None, dpi, columns,
                                       before=before)
    if not made_up:
        app._see_pane_places = (key, pn.seen_after(reach, seen), pn.edges((box_left, box_right), before))
    box_left, box_right = _clear_of_page(app, settled, (box_left, box_right), book, made_up)
    app._see_right_used = used
    origin = over.client_origin() if callable(getattr(over, "client_origin", None)) else None
    box_left, box_right = pane_on_screen(box_left, origin), pane_on_screen(box_right, origin)
    for side, picture, box in (("left", left, box_left), ("right", right if used == "right" else None, box_right),
                               ("bubble", right if used == "bubble" else None, box_right)):
        memo = app._see_pane_memo.get(side)
        if memo is not None:
            app._see_pane_memo[side] = (memo[0], memo[1], box if picture is not None else None)
    over.set_panes((left.bgra, box_left) if left is not None and box_left is not None else None,
                   (right.bgra, box_right, tuple(b for _name, b in right.hits))
                   if right is not None and box_right is not None else None)


def _pick_ground(app: Any) -> Any:
    """The side panes' ground while a browser window picked shows no page of a book in its tab and no page on a flat
    ground (`panes_tick`): the newest frame's size and capture area (`note_frame`), the area's middle third taken for
    the page, no ground's colour (the dark plates). None before any frame."""
    seen = getattr(app, "_see_frame_seen", None)
    if seen is None:
        return None
    size, (left, top, right, bottom) = seen
    third = (right - left) // 3
    if third <= 0 or bottom <= top:
        return None
    steady = st.steady_box(size, (left, top, right, bottom))
    return size, (left + third, top, right - third, bottom), (steady[1], steady[3]), None, (left, right)


def pane_click(app: Any, side: str, x: int, y: int) -> str:
    """A click on the pane *side* at (*x*, *y*) of its picture as last handed over: the control there acted on; its
    name ("" for none). A place entry open on a region's plate goes first (`see_edit.drop_place_entry`)."""
    from . import see_edit

    see_edit.drop_place_entry(app)
    memo = app._see_pane_memo.get(side if side == "left" else getattr(app, "_see_right_used", "right"))
    if memo is None or memo[2] is None:
        return ""
    name = memo[1].hit(x, y)
    action = PANE_ACTIONS.get(name)
    if action is None:
        return ""
    app._see_clicked.append((time.monotonic(), name))
    action(app)
    return name


def _language_list(app: Any) -> None:
    """The left pane's language row: every target language listed at the pane's right side (`see_menu`)."""
    from . import see_menu

    see_menu.languages_at_pane(app)


def take_language(app: Any, language: str) -> None:
    """*language*, clicked in the list of target languages (the left pane's, the taskbar button's Menu), taken at
    once as the "To:" box takes one chosen there (`_target_picked`: the page on show asked for again in it); a
    language whose model is not there is offered in a dialog of the window's, which takes the keys as it shows: the
    reader asked for it (`asked`). The language in force: nothing happens."""
    if not language or language == target(app):
        return
    plan = getattr(app, "_plan", None)
    try:
        offered = plan is not None and plan(language) is not None
    except Exception:  # noqa: BLE001 - not known: taken as an offer
        offered = True
    if offered:
        asked(app)
    shown = getattr(app, "lang_shown", None)
    if shown is not None:
        shown.set(language_label(language))  # (the "To:" box: lang_var follows)
    picked = getattr(app, "_target_picked", None)
    if picked is not None:
        picked()


def _flip_indicators(app: Any) -> None:
    """The indicators' switch: the right pane shown or not, the choice kept in the settings file for the next starts
    (as the window's other choices are: `config.write_settings`)."""
    value = not indicators_on(app)
    app.settings.see_through_indicators = value
    banner = getattr(app, "_show_banner", None)
    if banner is not None:  # (the setup banner's lines: in the right pane, or with it off in a dialog of their own)
        try:
            banner()
        except tk.TclError:
            pass
    try:
        config.write_settings(config.settings_file(app.settings), {"see_through_indicators": value})
    except (config.ConfigError, OSError) as e:
        say = getattr(app, "say", None)
        if say is not None:
            say(NOT_KEPT, error=getattr(e, "strerror", None) or str(e))


def _dialog(step: str) -> Any:
    """An action that opens a dialog of the window's: it comes up alone and takes the keys (`asked`)."""
    def act(app: Any) -> None:
        asked(app)
        getattr(app, step)()
    return act


def _menu(app: Any) -> None:
    """The left pane's Menu: the menu at the pane's right edge, level with the row (`see_menu.popup`)."""
    from . import see_menu

    see_menu.popup_at_pane(app)


def _flip_auto(app: Any) -> None:
    var = getattr(app, "auto_var", None)
    if var is not None:
        var.set(not bool(_get(var, False)))


def _edit(app: Any) -> None:
    from . import see_edit

    see_edit.toggle(app)


def _add_area(app: Any) -> None:
    """The left pane's Add area: a text area to add begun, or given up (`see_edit.toggle_adding`), editing or in Reader mode."""
    from . import see_edit

    see_edit.toggle_adding(app)


def _again(app: Any) -> None:
    """The circular arrow: the page on show translated again as the window's Translate again does it
    (`TranslatorMixin.retranslate_page`, in the Reader role too: its lines asked of the translator anew, and what that
    translates replaces the cache's; the lines the reader corrected are kept unless its question's box says
    otherwise). Its question is the reader's to answer: it takes the keys (`asked`)."""
    asked(app)
    app.retranslate_page()


# ------------------------------------------------------------------ the bubble last under the pointer (the right pane)
BUBBLE_GONE_S = 0.6  # the bubble's block goes once the viewer has shown another page (or none of its patches) so long
READ_AFTER_S = 0.3  # a bubble from the cache shown so long has its Japanese read (once; in memory only)
NOT_READ_AGAIN_S = 5.0  # ... and once more so long after the reading model was not there yet
BUBBLE_LINES = 5  # the bubble's Japanese and its translation are wrapped into at most so many lines each
BUBBLE_STATES = ("translated", "untranslated")  # the regions a bubble's block may show (one with a translation, one
# read and left without one)
# the target languages (`constants.LANGUAGES`) whose script the panes' fonts set (`panes.FONTS`; others: Segoe UI) ...
TARGET_FONTS = {"Chinese (Simplified)": "zh", "Chinese (Traditional)": "zh-tw", "Korean": "ko", "Thai": "th"}
# ... and those the panes cannot set as they are written (right to left, or shaped): their translation is not shown in
# the block (it is on the page; Copy the translation copies it all the same)
NOT_PLAIN = frozenset({"Arabic", "Hebrew", "Hindi", "Bengali"})


def bubble_tick(app: Any, over: Any) -> None:
    """The bubble the right pane shows (``_see_bubble``): the patch left out under the pointer
    (`SeeThrough.hovered`) once one is, kept after the pointer has left it - so that the pointer can go to the pane -
    until another one is, or until the viewer has shown another page (or none of the page's patches: a turn, a jump)
    for BUBBLE_GONE_S (`SeeThrough.look_key`); none while the lettering is switched off."""
    if not over.on:
        app._see_bubble = None
        return
    now = time.monotonic()
    held = getattr(app, "_see_bubble", None)
    from . import see_edit

    edited = see_edit._editor_region(app) if see_edit.on(app) else None
    result = getattr(app, "last_result", None)
    if edited is not None and result is not None and result.original is not None:  # (editing: the region in the editor,
        box = tuple(int(v) for v in edited.bbox)  # whatever the pointer is over meanwhile)
        since = held[2] if held is not None and (held[0], held[1]) == (id(result.original), box) else now
        app._see_bubble = (id(result.original), box, since, now)
        return
    hovered = over.hovered()
    if hovered is not None and (held is None or (held[0], held[1]) != tuple(hovered)):
        app._see_bubble = (hovered[0], tuple(hovered[1]), now, now)
        return
    if held is None:
        return
    if hovered is not None or over.look_key() == held[0]:
        app._see_bubble = (held[0], held[1], held[2], now)
    elif now - held[3] > BUBBLE_GONE_S:
        app._see_bubble = None


def _meets(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def bubble_target(app: Any) -> tuple[Any, Any] | None:
    """What the bubble the right pane shows (``_see_bubble``) is: (the last translated page, its region the patch's
    box meets most) while that page's frame is the patch's; (None, the index of the box of the page filling in) while
    the page filling in is; None otherwise."""
    held = getattr(app, "_see_bubble", None)
    if held is None:
        return None
    key, box = held[0], held[1]
    result = getattr(app, "last_result", None)
    if result is not None and result.original is not None and id(result.original) == key:
        regions = [r for r in getattr(result, "regions", None) or () if getattr(r, "status", "") in BUBBLE_STATES]
        best = max(regions, key=lambda r: _meets(tuple(r.bbox), box), default=None)
        return (result, best) if best is not None and _meets(tuple(best.bbox), box) > 0 else None
    fill = getattr(app, "_fill", None)
    if fill is not None and id(fill.frame) == key:
        lettered = [i for i, s in enumerate(fill.states) if s == "lettered" and i < len(fill.boxes)]
        best = max(lettered, key=lambda i: _meets(tuple(fill.boxes[i]), box), default=None)
        return (None, best) if best is not None and _meets(tuple(fill.boxes[best]), box) > 0 else None
    return None


def bubble_japanese(app: Any, found: tuple[Any, Any]) -> tuple[str, str]:
    """(the Japanese of the bubble *found* (`bubble_target`), what its row says while there is none). A region of a
    page from the cache has none (the cache keeps no Japanese): it is read from its crop of the capture in memory
    (`BubbleTextMixin._japanese_of`, as Copy the Japanese of the window does) once the bubble has been shown
    READ_AFTER_S, and kept with the region in memory only. A box of the page filling in has none yet."""
    result, region = found
    if result is None:
        return "", ""
    text = str(getattr(region, "source_text", "") or "").strip()
    if text:
        return text, ""
    reads: dict[int, tuple[str, float]] = app.__dict__.setdefault("_see_reads", {})
    state = reads.get(id(region))
    now = time.monotonic()
    if state is not None and state[0] == "no-ocr" and now - state[1] > NOT_READ_AGAIN_S:
        state = None
    held = getattr(app, "_see_bubble", None)
    read = getattr(app, "_japanese_of", None)
    if state is None:
        if read is None or held is None or now - held[2] < READ_AFTER_S:
            return "", ""
        if len(reads) > 256:
            reads.clear()
        key = id(region)
        reads[key] = ("asked", now)

        def done(got: str, error: str) -> None:
            reads[key] = ("" if got else (error or "none"), time.monotonic())

        read(result, region, done)
        state = reads[key]
        text = str(getattr(region, "source_text", "") or "").strip()
        if text:
            return text, ""
    if state[0] == "asked":
        return "", _(READING)
    return "", _(NOT_READ.get(state[0], NOT_READ["none"])) if state[0] else ""


def bubble_translation(app: Any, found: tuple[Any, Any]) -> str:
    """The translation of the bubble *found* (`bubble_target`), without the lettering's marks."""
    result, target = found
    if result is None:
        fill = getattr(app, "_fill", None)
        text = str(fill.texts.get(target, "")) if fill is not None else ""
    else:
        text = str(getattr(target, "translated_text", "") or "")
    return strip_marks(text).strip()


def bubble_again_enabled(app: Any, found: tuple[Any, Any]) -> bool:
    """Whether the bubble's Ask again is live: a region of the last translated page, nothing at work (the circular
    arrow's rule, `again_enabled`, and no job of the worker's)."""
    result = found[0]
    return (result is not None and result is getattr(app, "last_result", None) and not getattr(app, "busy", False)
            and getattr(app, "pipeline", None) is not None and again_enabled(app))


def bubble_rows(app: Any) -> list[pn.Row]:
    """The bubble's block at the top of the right pane, while there is a bubble to show (`bubble_target`): Copy the
    Japanese, Copy the translation and Ask again - the plates first, where they stay whatever the bubble says -, then
    its Japanese and its translation, each wrapped into BUBBLE_LINES lines at the most (the last cut with an
    ellipsis) and set in its own script's font. Its words are in memory only, and the clipboard takes them only on
    a click."""
    found = bubble_target(app)
    if found is None:
        return []
    source, note = bubble_japanese(app, found)
    translation = bubble_translation(app, found)
    target = str(_get(getattr(app, "lang_var", None), "") or "")
    rows = [pn.Row("bubble_source", _(COPY_JAPANESE), enabled=bool(source)),
            pn.Row("bubble_translation", _(COPY_TRANSLATION), enabled=bool(translation)),
            pn.Row("bubble_again", _("Ask again"), enabled=bubble_again_enabled(app, found))]
    if source or note:
        rows.append(pn.Row("", source or note, "text", lang="ja" if source else "", lines=BUBBLE_LINES))
    if translation and target not in NOT_PLAIN:
        rows.append(pn.Row("", translation, "text", lang=TARGET_FONTS.get(target, "en"), lines=BUBBLE_LINES))
    return rows


def _copy_source(app: Any) -> None:
    found = bubble_target(app)
    text = bubble_japanese(app, found)[0] if found is not None else ""
    if text:
        app._to_clipboard(text, JAPANESE_COPIED)


def _copy_translation(app: Any) -> None:
    found = bubble_target(app)
    text = bubble_translation(app, found) if found is not None else ""
    if text:
        app._to_clipboard(text, TRANSLATION_COPIED)


def _ask_bubble(app: Any) -> None:
    """The bubble's Ask again: its line asked of the translator anew (`ask_bubble`), with no question first."""
    found = bubble_target(app)
    if found is not None and bubble_again_enabled(app, found):
        ask_bubble(app, found[0], found[1])


def ask_bubble(app: Any, result: Any, region: Any) -> bool:
    """One bubble of the page on show translated again: its line asked of the translator anew (`Pipeline.ask_again`,
    the Japanese read first where the page came from the cache: `Pipeline.read_source`), the answer replacing the
    cache's as the model's own (`Pipeline.set_translation`, not marked as the reader's: the page translated again
    replaces it as ever), the page lettered again and its patches made anew. The status line says "Asking the
    model..." meanwhile, and what came: nothing, or the model's error. False when it cannot be asked now."""
    pipeline = getattr(app, "pipeline", None)
    if pipeline is None or result is None or getattr(app, "busy", False):
        return False
    from ..messages import message_of
    from ..translate import TranslationError
    from .progress import rendered

    app._go_busy()
    app.say("Asking the model...")

    def job() -> None:
        try:
            if not str(getattr(region, "source_text", "") or "").strip():
                pipeline.read_source(result, region)
            text = pipeline.ask_again(result, region)
            if not text:
                app._post("status", key="The model gave no other translation.")
            elif pipeline.set_translation(result, region, text, edited=False):
                app._post("result", result=result, edited=True, quiet=True)
            else:
                app._post("status", key="Could not keep the translation: give the book a name first (Menu > Series and Volume...).")
        except TranslationError as e:
            app._post("status", key="No answer from the model: {error}", values={"error": rendered(message_of(e))})
        except Exception:  # noqa: BLE001 - the page stays as it was
            log.debug("see-through mode: a bubble could not be asked again", exc_info=True)
        finally:
            app._post("translate_done")

    app._jobs.put(job)
    return True


PANE_ACTIONS: dict[str, Any] = {
    "translate": lambda app: app.translate_now(),
    "again": _again,  # (the circular arrow: the page on show translated again, the cache's lines replaced)
    "stop": lambda app: app.stop_page(),
    "auto": _flip_auto,
    "language": _language_list,  # (every target language listed beside the pane: `see_menu.languages_at_pane`)
    "lettering": toggle,
    "indicators": _flip_indicators,
    "area": _dialog("set_area"),
    "settings": _dialog("open_settings"),
    "menu": _menu,
    "edit": lambda app: _edit(app),  # (Reader mode: the Reader role, or editing on the overlay, `see_edit`)
    "add_area": _add_area,  # (Add area: a text area drawn on the page, editing or in Reader mode)
    "quit": lambda app: app._on_close(),
    "bubble_source": _copy_source,  # (the right pane: the bubble last under the pointer)
    "bubble_translation": _copy_translation,
    "bubble_again": _ask_bubble,
}


# ------------------------------------------------------------------ the patches
def _rgb(image: Image.Image) -> np.ndarray:
    return np.asarray(image if image.mode == "RGB" else image.convert("RGB"))


class Patcher:
    """The patches made off the Tk thread (`present` hands each changed page here; `seethrough.make_patches`, some
    15 ms a full-HD page, would hold the Tk thread up a dozen times a page as its lines are lettered): a thread of its
    own makes them and hands them to the see-through window (`SeeThrough.present`, which takes them under its lock).
    Each page waits once: a newer state of a page not made yet replaces the one waiting and goes last, as a set handed
    over later is the newer. The frames' pixels are kept for the last MEMO_KEPT frames (a frame never changes); the
    lettered page comes as the picture it is (a finished page or a page's result is never changed) or as a copy (the
    page filling in, which the Tk thread letters in place). Nothing is written anywhere."""

    def __init__(self, over: Any, run: bool = True) -> None:
        self.over = over
        self._lock = threading.Lock()
        self._waiting: dict[int, tuple[Any, ...]] = {}  # frame key -> (frame, lettered, final, margin, gap), in order
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._pixels: list[tuple[Image.Image, np.ndarray]] = []  # (frame, its RGB pixels), the patch thread's own
        self.made = 0
        self._thread: threading.Thread | None = None
        if run:
            self._thread = threading.Thread(target=self._run, name="taslation-patches", daemon=True)
            self._thread.start()

    def put(self, original: Image.Image, lettered: Image.Image, final: bool, margin: int, gap: int) -> None:
        with self._lock:
            key = id(original)
            self._waiting.pop(key, None)
            self._waiting[key] = (original, lettered, final, margin, gap)
        self._wake.set()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(1.0)
            self._wake.clear()
            self.drain()

    def drain(self) -> None:
        """Every page waiting made, the oldest first (the patch thread; a test calls it itself)."""
        while not self._stop.is_set():
            with self._lock:
                if not self._waiting:
                    return
                key = next(iter(self._waiting))
                job = self._waiting.pop(key)
            try:
                self._make(key, *job)
            except Exception:  # noqa: BLE001 - that state of the page shows no patches; the next one is made
                log.debug("see-through mode: the patches of a page could not be made", exc_info=True)

    def _frame_pixels(self, original: Image.Image) -> np.ndarray:
        for image, pixels in self._pixels:
            if image is original:
                return pixels
        pixels = _rgb(original)
        self._pixels = [(original, pixels), *self._pixels[:MEMO_KEPT - 1]]
        return pixels

    def _make(self, key: int, original: Image.Image, lettered: Image.Image, final: bool, margin: int,
              gap: int) -> None:
        within, off_rows = compared_by(original)
        patches = st.make_patches(self._frame_pixels(original), _rgb(lettered), margin=margin, gap=gap,
                                  within=within, off_rows=off_rows)
        self.over.present(key, original.size, patches, final)
        self.made += 1


def _meets_box(a: Any, b: Any) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _differs_where(where: dict[str, Any], limit: float) -> str:
    """The part of a patch's compared pixels that keeps it hidden (`seethrough.where_differs`): "box" when its own
    place is another, else the margin's side with the largest share of other pixels ("top", ...); "size" for a frame
    that does not hold the place."""
    if "size" in where:
        return "size"
    if where.get("box", (0.0, 0))[0] > limit:
        return "box"
    sides = [(v[0], k) for k, v in where.items() if k != "box"]
    return max(sides)[1] if sides else "box"


def unshown(app: Any, settled: bool = True) -> dict[str, Any] | None:
    """The page on show's regions lettered or erased (`pipeline.erases`) whose patch does not show now, and why, from
    the see-through window's last look (`SeeThrough.why_not_shown`): numbers and kinds only, no text. None while the
    page on show is not the last translated page (one filling in, another page in the viewer) or nothing is known;
    with *settled*, also while the viewer's frame has been its newest for less than UNSHOWN_SETTLE_S (a report, asked
    for, takes the look as it is).

    Each region not shown: (its index among the page's regions, the kind, facts): "no patch" (its lettering changed
    no pixel there), "covered" (a window over the viewer), "hover" (the pointer rests on it), "original" (the editor
    shows its original), "left out" (editing: its box takes nothing), "hidden:WHY" (the lettering hidden: off, away,
    no viewer...), "no match" (no patch of the page matches the frame), or "differs:PART" - its pixels compared are
    other than when it was read (`_differs_where`: "box", "top", "bottom", "left", "right", "size"), with the share
    and the limit."""
    over = getattr(app, "_see_through", None)
    result = getattr(app, "last_result", None)
    original = getattr(result, "original", None)
    why_of = getattr(over, "why_not_shown", None)
    if original is None or not callable(why_of):
        return None
    try:
        on_show = bool(app._result_on_show())
    except Exception:  # noqa: BLE001 - (a page going)
        on_show = False
    why = why_of() or {}
    key = id(original)
    if not on_show or (why.get("key") not in (None, key)):
        return None
    if settled and not why.get("hidden") and time.monotonic() - float(why.get("frame_at", 0.0)) < UNSHOWN_SETTLE_S:
        return None  # (a frame the viewer may be drawing over: a turn's first frames)
    from ..pipeline import erases

    regions = [(i, r) for i, r in enumerate(result.regions) if erases(r)]
    out: list[tuple[int, str, dict[str, Any]]] = []
    hidden = why.get("hidden")
    if hidden:
        out = [(i, f"hidden:{hidden}", {}) for i, _r in regions]
    elif why.get("key") is None:
        known = key in why.get("sets", ())
        out = [(i, "no match", {"set_known": int(known)}) for i, _r in regions]
    else:
        boxes, drawn = why.get("boxes", ()), set(why.get("drawn", ()))
        covered, held, bare = set(why.get("covered", ())), set(why.get("held", ())), set(why.get("bare", ()))
        valid, where, shares = set(why.get("valid", ())), why.get("where", {}), why.get("shares", ())
        limit = float(why.get("share_limit", st.CHANGED_SHARE))
        left_out_boxes = {tuple(b) for k, b in enumerate(why.get("region_boxes", ())) if k in set(why.get(
            "left_out", ()))}
        for i, r in regions:
            bbox = tuple(int(v) for v in r.bbox)
            own = [k for k, b in enumerate(boxes) if _meets_box(b, bbox)]
            if any(k in drawn for k in own):
                continue
            if not own:
                out.append((i, "no patch", {}))
                continue
            facts: dict[str, Any] = {"patches": len(own)}
            if any(k in covered for k in own):
                kind = "covered"
            elif why.get("hover") in own:
                kind = "hover"
            elif any(k in bare for k in own):
                kind = "original"
            elif all(k in valid for k in own) and bbox in left_out_boxes:
                kind = "left out"
            else:
                bad = [k for k in own if k not in valid]
                worst = max(bad or own, key=lambda k: shares[k] if k < len(shares) else 0.0)
                part = _differs_where(where.get(worst, {}), limit)
                kind = f"differs:{part}"
                facts.update(share=shares[worst] if worst < len(shares) else None, limit=limit,
                             where={k: v[0] for k, v in where.get(worst, {}).items()},
                             box=tuple(boxes[worst]), near=tuple(why.get("near", ())[worst]) if worst < len(
                                 why.get("near", ())) else None, held=int(worst in held))
            out.append((i, kind, facts))
    from collections import Counter

    within, off_rows = (getattr(original, "info", {}).get(COMPARE_INFO) or (None, ()))
    return {"key": key, "regions": len(regions), "not_shown": out, "kinds": dict(Counter(k for _i, k, _f in out)),
            "editing": bool(why.get("editing")), "final": bool(why.get("final", True)),
            "boxes": [(i, tuple(int(v) for v in r.bbox)) for i, r in regions], "within": within,
            "off_rows": tuple(off_rows), "size": tuple(original.size)}


def unshown_tick(app: Any, now: float | None = None) -> None:
    """(`tick`, every UNSHOWN_EVERY_S) The page on show's lettered regions not shown (`unshown`), kept for the tools
    and the report (``_see_unshown``: the page's frame key -> {"last": the last look's, "looks": how many looks,
    "kinds_seen": the kinds summed over them, "regions": each lettered region's index -> {"shown_at", "unshown_at"
    (monotonic s of the last look that found its lettering on show, and not), "kind" (why, at the last look it was
    not)}}) and one line in the log per page - and again when its count changes, UNSHOWN_LOGGED lines a page at the
    most: how many regions, how many not shown, the kinds (numbers and kinds only)."""
    now = time.monotonic() if now is None else now
    if now - float(getattr(app, "_see_unshown_at", 0.0)) < UNSHOWN_EVERY_S:
        return
    app._see_unshown_at = now
    try:
        found = unshown(app)
    except Exception:  # noqa: BLE001 - a look less
        log.debug("see-through mode: the regions not shown could not be counted", exc_info=True)
        return
    if found is None:
        return
    kept: dict[int, Any] = app.__dict__.setdefault("_see_unshown", {})
    logged: dict[int, Any] = app.__dict__.setdefault("_see_unshown_logged", {})
    key = found["key"]
    entry = kept.pop(key, None) or {"looks": 0, "kinds_seen": {}}
    entry["last"], entry["looks"] = found, entry["looks"] + 1
    for kind, n in found["kinds"].items():
        entry["kinds_seen"][kind] = entry["kinds_seen"].get(kind, 0) + n
    seen = entry.setdefault("regions", {})
    hidden_now = {i: kind for i, kind, _facts in found["not_shown"]}
    for i, _box in found["boxes"]:
        each = seen.setdefault(i, {"shown_at": None, "unshown_at": None, "kind": ""})
        if i in hidden_now:
            each["unshown_at"], each["kind"] = now, hidden_now[i]
        else:
            each["shown_at"] = now
    kept[key] = entry
    if len(kept) > 64:
        for old in list(kept)[:-64]:
            kept.pop(old, None)
    said = (len(found["not_shown"]), tuple(sorted(found["kinds"].items())))
    lines, last = logged.get(key, (0, None))
    if said != last and lines < UNSHOWN_LOGGED:
        logged[key] = (lines + 1, said)
        kinds = ", ".join(f"{k} {n}" for k, n in sorted(found["kinds"].items())) or "none"
        log.info("see-through: page %s: %d of %d lettered regions not shown (%s)%s", f"{key & 0xFFFF:04x}",
                 said[0], found["regions"], kinds, " editing" if found["editing"] else "")
    if len(logged) > 256:
        for old in list(logged)[:-256]:
            logged.pop(old, None)


def compared_by(original: Any) -> tuple[Any, tuple[tuple[int, int], ...]]:
    """(within, off_rows) of `seethrough.compare_box` for the patches of a page read from the frame *original*: what
    `compare_within` stamped on it at its capture; (None, ()) for a frame that has none (a test's, an older one)."""
    given = getattr(original, "info", {}).get(COMPARE_INFO)
    if not given:
        return None, ()
    within, off_rows = given
    return within, tuple(off_rows)


def compare_within(app: Any, image: Image.Image, facts: Any) -> None:
    """(each frame captured in see-through mode, `LiveViewMixin._capture_frame`) What the patches of a page read from
    *image* (the frame as it is read: `reading_frame`'s) are compared by beyond their own place, stamped on it
    (COMPARE_INFO, which its copies carry): the capture area and the page box found in it (`frame_look`; none found:
    the area alone), each EDGE_PX inside its edges, and the rows painted over in it (PAINTED_INFO) with CUT_PX about
    them. A margin outside those took in pixels that change while the page does not - the viewer's ground and the
    browser's band beside a page's edge, the page's border row, the painted rows once the bars had gone (the page is
    there then) -, and the lettering of a bubble touching the page's edge stayed hidden."""
    try:
        _rgb_area, area = area_rgb(app, image, facts)
        found = frame_look(app, image, facts)
        edge = px(app, EDGE_PX)
        box = area
        if found.box is not None:
            page = found.box
            box = (max(area[0], page[0]), max(area[1], page[1]), min(area[2], page[2]), min(area[3], page[3]))
            if box[2] <= box[0] or box[3] <= box[1]:
                box = area
        within = (box[0] + edge, box[1] + edge, box[2] - edge, box[3] - edge)
        if within[2] <= within[0] or within[3] <= within[1]:
            within = box
        cut = px(app, CUT_PX)
        rows = tuple((max(0, int(a) - cut), int(b) + cut) for a, b in getattr(image, "info", {}).get(PAINTED_INFO, ()))
        image.info[COMPARE_INFO] = (tuple(int(v) for v in within), rows)
    except Exception:  # noqa: BLE001 - (no stamp: the patches are compared as before, the box grown alone)
        log.debug("see-through mode: what the patches are compared by could not be stamped", exc_info=True)


def pairs(app: Any) -> list[tuple[Image.Image, Image.Image, bool, tuple[Any, ...]]]:
    """(frame read, lettered page, final, what it is now) of the page filling in and of the last translated page, the
    older first."""
    out = []
    fill = getattr(app, "_fill", None)
    result = getattr(app, "last_result", None)
    if result is not None and result.image is not None and result.original is not None and (
            fill is None or result.original is not fill.frame):
        out.append((result.original, result.image, True, ("result", id(result.image))))
    if fill is not None:
        lettered = fill.final if fill.final is not None else fill.page
        if lettered is not None:
            out.append((fill.frame, lettered, fill.final is not None,
                        ("fill", id(lettered), tuple(fill.states), fill.final is not None)))
    return out


def present(app: Any) -> None:
    """The patches of the page filling in and of the last translated page handed to the see-through window, each when
    it changed (what it is, `pairs`): made by the patch thread (`Patcher`), the page filling in copied first, since
    the Tk thread letters it in place; without that thread, here."""
    over = getattr(app, "_see_through", None)
    if over is None:
        return
    memo: list[tuple[Image.Image, tuple[Any, ...]]] = app._see_memo
    fill = getattr(app, "_fill", None)
    patcher = getattr(app, "_see_patcher", None)
    for original, lettered, final, state in pairs(app):
        known = next((s for img, s in memo if img is original), None)
        if known == state:
            continue
        if original.size != lettered.size:
            continue
        margin, gap = px(app, st.MARGIN), px(app, st.GROUP_PX)
        if patcher is not None:
            patcher.put(original, lettered.copy() if fill is not None and lettered is fill.page else lettered, final,
                        margin, gap)
        else:
            within, off_rows = compared_by(original)
            over.present(id(original), original.size, st.make_patches(_rgb(original), _rgb(lettered), margin=margin,
                                                                      gap=gap, within=within, off_rows=off_rows),
                         final)
        memo[:] = [(original, state), *[(img, s) for img, s in memo if img is not original]][:MEMO_KEPT]


# ------------------------------------------------------------------ which frames start a job
def area_rgb(app: Any, image: Image.Image, facts: Any) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """The capture area of *image* (the reader's own when set, else the whole frame) and its box."""
    box = _area_of(app, image)
    rgb = facts.rgb()
    return rgb[box[1]:box[3], box[0]:box[2]], box


def _area_of(app: Any, image: Image.Image) -> tuple[int, int, int, int]:
    """The box of *image*'s capture area (`area_rgb`)."""
    hand = app._hand_set() if getattr(app, "_manual_area", False) else (0, 0, 0, 0)
    from . import area

    box = area.margins_to_box(hand, image.size)
    if box[2] <= box[0] or box[3] <= box[1]:
        box = (0, 0, image.width, image.height)
    return box


def frame_look(app: Any, image: Image.Image, facts: Any) -> st.Look:
    """`seethrough.look` of *image*'s capture area (kept with the frame's facts), its boxes in the frame's pixels; for
    a frame `reading_frame` made, the look it was given (`LOOK_INFO`). The page box at the last rest tells half a spread
    (`seethrough.half_of`) only in a frame of the size it was found in (`_see_rest_size`): in the viewer's window given
    another size, a single page about half as wide as the spread before and near one of its sides was taken for half a
    spread drawn, a frame to wait out - and so was every frame after it, since no frame waited out is at rest: the
    page there was never read nor followed (the narrow window's turns, a window dragged narrower, until another size)."""
    given = getattr(image, "info", {}).get(LOOK_INFO)
    if given is not None:
        return given

    def make() -> st.Look:
        rgb, box = area_rgb(app, image, facts)
        before = app._see_rest_box
        if getattr(app, "_see_rest_size", None) not in (None, image.size):
            before = None  # (another size than the rest's: no half of its spread here)
        if before is not None:
            before = (before[0] - box[0], before[1] - box[1], before[2] - box[0], before[3] - box[1])
        found = st.look(rgb, before, step=px(app, st.LOOK_STEP))
        page = None if found.box is None else (found.box[0] + box[0], found.box[1] + box[1],
                                                 found.box[2] + box[0], found.box[3] + box[1])
        rows = tuple((a + box[1], b + box[1]) for a, b in found.bands)
        return st.Look(page, rows, found.kind, found.ground)

    return facts.get(("see_look",), make)


def held(app: Any) -> bool:
    """Whether the button is held down in the viewer (`LiveViewMixin._held_in_viewer`): a page some viewers drag
    along with the pointer is out of its place meanwhile."""
    ask = getattr(app, "_held_in_viewer", None)
    try:
        return bool(ask()) if callable(ask) else False
    except Exception:  # noqa: BLE001 - not known: as with no press
        return False


def _same_box(a: Any, b: Any, near: int) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return all(abs(int(x) - int(y)) <= near for x, y in zip(a, b))


def note_frame(app: Any, image: Image.Image, facts: Any) -> None:
    """A frame just captured of the viewer (`LiveViewMixin._capture_frame`): since when bars lie over the page (and a
    look once they have stayed BAR_WAIT_S: a viewer draws no new frame while they stand still), and the page box of
    the last frame at rest (which tells half a spread) with what the side panes are placed by: the frame's size, the
    steady band's rows (`seethrough.steady_box` of the capture area: where bars never come), the ground's colour
    (none at rest on no flat ground: the panes hide) and the capture area's columns (the panes at its edges).

    Only a frame of the page at rest in its place is that (`_at_rest`): its page box the one the frame before had
    (within LOOK_STEP; the first frame of a viewer or of a size counts), and no button held in the viewer (`held`);
    a frame with no page box while a ground of frames of its size is had never is (`_keeps_ground`: a slide's frames),
    nor the very picture noted while the button was held, captured again once it is up (the viewer has not answered
    the release yet). Another is kept aside (`_aside`) and becomes it once REST_S has passed with no other picture after
    it and no press - one the button was held over, RELEASE_S after the release - (`rest_tick`). Before, every frame
    was: a page that a viewer drags along with the pointer, out of its place and
    over the panes' places, hid the panes while it was held there, and the frame of a page taken while it moved, or
    found on no flat ground, set the panes by it until the next frame at rest. A frame with bars over the page leaves
    the ground as it is - but while none of a frame of its size is had: then it gives it (`_ground_under_bars`) -, and
    once the bars have stayed BAR_WAIT_S it is a frame as any other (`_bars_last`). Before, bars that never went kept
    the ground of the first frame for good: on a viewer whose area set by hand began 3 px above the browser's own bar's
    foot, every frame had a band across the area's top (the browser's bar, 4 px on every fourth row), and the book's
    cover, a single page in the middle, placed the panes for 688 s and the spreads after it, 300 px from the cover's
    box, on both pages. The page box is the look's, or where it finds none, the capture area set by hand when the
    ground beyond it is flat (`_box_of`)."""
    app._see_newest = getattr(facts, "memo", None)  # (the newest picture noted, whatever it is: `rest_tick`)
    app._see_frame_seen = (image.size, _area_of(app, image))  # (the newest frame's size and area: `_pick_ground`)
    found = frame_look(app, image, facts)
    if found.kind is not None:
        note_state(app, found.kind)
        return
    box, colour = _box_of(app, image, facts, found)
    _note_box(app, image, box, facts)
    if found.bands:
        note_state(app, "bars")
        if app._see_bars_since is None:
            app._see_bars_since = time.monotonic()
            try:
                app.after(int(BAR_WAIT_S * 1000) + 30, lambda: _bars_due(app))
            except Exception:  # noqa: BLE001 - no Tk loop (a test)
                pass
        if not _bars_last(app):
            _ground_under_bars(app, image, facts, box, colour)
            return
    else:
        if app._see_bars_since is not None:  # the bars have gone: a page read under them is read once more
            try:
                app.after(GONE_LOOK_MS, lambda: _bars_due(app, gone=True))
            except Exception:  # noqa: BLE001 - no Tk loop (a test)
                pass
        app._see_bars_since = None
    ground = _ground_of(app, image, facts, box, colour)
    if _at_rest(app, image, box, facts) and not _keeps_ground(app, image, box):
        if not found.bands:
            note_state(app, "rest")
        _rest(app, box, ground, image.size)
    else:
        if not found.bands:
            note_state(app, "held" if held(app) else "moving")
        _aside(app, box, ground, image.size, facts)


FRAME_STATES_KEPT = 64  # (`note_state`) the newest frames' states kept, for a report


def note_state(app: Any, state: str) -> None:
    """What a frame of the viewer captured was (a report's "frame states lately": `report`): "rest" (the page at rest
    in its place), "moving", "held" (the button held in the viewer), "bars" (bars over the page), "black", "half",
    "washed" (frames to wait out, `seethrough.loading_kind`; "black" too where the live view finds the frame black)
    or "tab" (another tab on show); the newest FRAME_STATES_KEPT, with when."""
    kept = app.__dict__.get("_see_frame_states")
    if kept is None:
        from collections import deque

        kept = app.__dict__["_see_frame_states"] = deque(maxlen=FRAME_STATES_KEPT)
    kept.append((time.monotonic(), str(state)))


def _ground_of(app: Any, image: Image.Image, facts: Any, box: Any, colour: Any) -> Any:
    """The side panes' ground in the frame *image* whose page box is *box* (`_box_of`) on a ground of *colour*: (its
    size, the page box, the steady band's rows, the ground's colour, the capture area's columns); None when no page on
    a flat ground was found."""
    if box is None:
        return None
    _rgb, area = area_rgb(app, image, facts)
    steady = st.steady_box(image.size, area)
    return image.size, box, (steady[1], steady[3]), colour, (area[0], area[2])


def _bars_last(app: Any) -> bool:
    """Whether the bars over the page have stayed BAR_WAIT_S (`note_frame`): no viewer's bars sliding in and out but
    a state - a viewer that keeps them while it is not in front, a browser's bar under an area set by hand -, whose
    frames are the page at rest or not as any other frame is (`_at_rest`)."""
    since = getattr(app, "_see_bars_since", None)
    return since is not None and time.monotonic() - float(since) >= BAR_WAIT_S


def _ground_under_bars(app: Any, image: Image.Image, facts: Any, box: Any, colour: Any) -> None:
    """A frame with bars over the page that have not stayed BAR_WAIT_S yet (`note_frame`) while no ground of a frame
    of its size is had: the side panes' ground taken from it, at rest as any frame is (`_at_rest`, `rest_tick`). What
    the panes are placed by is there with the bars as without them - the page's columns (`seethrough.ground_box`
    leaves the bars' rows out) and the steady band, where bars never come -, and a viewer that came into sight with its
    bars up and keeps them (the pointer resting on them, a click that holds them: a viewer brought to the front from
    behind other windows) gave no frame without them before: the panes would stay hidden until the bars went, page turn
    after page turn. With a ground of the frame's size had, the frames with new bars leave it as it is."""
    ground = getattr(app, "_see_ground", None)
    if box is None or (ground is not None and ground[0] == image.size):
        return
    under = _ground_of(app, image, facts, box, colour)
    if _at_rest(app, image, box, facts):
        _rest(app, box, under, image.size)
    else:
        _aside(app, box, under, image.size, facts)


BEYOND_PX = 24  # (`_beyond`) px of the frame beyond each side of a capture area set by hand looked at (at 96 DPI)


def _box_of(app: Any, image: Image.Image, facts: Any, found: st.Look) -> tuple[Any, Any]:
    """The page box the frame *image* gives the side panes (frame pixels) and the ground's colour: the look's
    (*found*); where it finds none, the capture area the reader set by hand when the ground beyond it is flat
    (`_beyond`) - a page that fills the area set about it leaves no ground inside it, and neither do a spread of colour
    pictures, a dark page beside a black one, a page running off the window's foot: the area stands in for the page
    box (the panes go outside it, `_book_columns`), where it leaves a pane room beyond it: one that does not would hide
    the panes it holds (a slide's frames, the page half out, would be a page at rest). (None, the look's colour) where
    there is neither."""
    if found.box is not None or not getattr(app, "_manual_area", False):
        return found.box, found.ground
    if _book_columns(app, image.size, getattr(app, "_see_dpi", st.BASE_DPI), None)[0] is None:
        return None, found.ground

    def make() -> Any:
        _rgb, area = area_rgb(app, image, facts)
        colour = _beyond(facts.rgb(), area, px(app, BEYOND_PX), px(app, st.LOOK_STEP))
        return None if colour is None else (tuple(int(v) for v in area), colour)

    try:
        got = facts.get(("see_stand_in",), make)
    except Exception:  # noqa: BLE001 - not known: no page box
        got = None
    return (None, found.ground) if got is None else got


def _beyond(rgb: np.ndarray, area: Any, width: int, step: int) -> tuple[int, int, int] | None:
    """The ground's colour beyond the capture area *area* in the frame *rgb*: the frame's *width* px beyond each of its
    sides that has any (the area's steady rows, every *step*-th pixel), when each is one colour (GROUND_SHARE within
    GROUND_TOL of its median) and the two are alike; None where they are not, or the area has no side with frame
    beyond it."""
    height, full = rgb.shape[:2]
    left, top, right, bottom = (int(v) for v in area)
    _l, t, _r, b = st.steady_box((full, height), (left, top, right, bottom))
    step = max(1, int(step))
    strips = []
    if left >= step:
        strips.append(rgb[t:b:step, max(0, left - width):left:step])
    if full - right >= step:
        strips.append(rgb[t:b:step, right:min(full, right + width):step])
    colours = []
    for strip in strips:
        pixels = strip.reshape(-1, strip.shape[-1])[:, :3].astype(np.int16)
        if not pixels.size:
            continue
        colour = np.median(pixels, axis=0)
        if float(np.all(np.abs(pixels - colour) <= st.GROUND_TOL, axis=1).mean()) < st.GROUND_SHARE:
            return None
        colours.append(colour)
    if not colours or (len(colours) == 2 and bool(np.any(np.abs(colours[0] - colours[1]) > st.GROUND_TOL))):
        return None
    return tuple(int(round(float(v))) for v in colours[0])  # type: ignore[return-value]


def _note_box(app: Any, image: Image.Image, box: Any, facts: Any) -> None:
    """(each frame noted that is not one to wait out, bars or none) The newest frame's page box (`_box_of`; None:
    none found) and since when it has stood - the box the frame before had, within LOOK_STEP, in frames of this size -,
    with the frame's facts: what the side panes are checked against, whatever became of the ground (`_settled`). A
    frame the button was held over (or the very picture noted then, captured again once it is up) stands from no
    time."""
    now = time.monotonic()
    memo = getattr(facts, "memo", None)
    was = getattr(app, "_see_box_now", None)
    same = was is not None and was[0] == image.size and _same_box(was[1], box, px(app, st.LOOK_STEP))
    pressed = held(app) or (memo is not None and memo is getattr(app, "_see_held_memo", None))
    app._see_box_now = (image.size, box, was[2] if same and not pressed else now, facts)


def _settled(app: Any, size: Any) -> tuple[Any, Any] | None:
    """The newest frame noted (`_note_box`), of *size*, once its page box - or that it has none - has stood REST_S, no
    button held in the viewer and RELEASE_S past the last release (a slide's frames and the page let go: set aside, as
    `note_frame` sets them aside): (its page box or None, its facts); else None (nothing to check the panes by)."""
    now_box = getattr(app, "_see_box_now", None)
    if now_box is None or tuple(now_box[0]) != tuple(size) or held(app):
        return None
    now = time.monotonic()
    if now - now_box[2] < REST_S or now - float(getattr(app, "_see_held_at", 0.0) or 0.0) < RELEASE_S:
        return None
    return now_box[1], now_box[3]


def _book_columns(app: Any, size: Any, dpi: Any, columns: Any) -> tuple[Any, Any]:
    """With a capture area the reader set by hand (they said where the book is), the side panes never lie inside its
    columns where it leaves a pane room beyond it: per such side the area's edge is the least the page reaches to (the
    page the panes go by is widened to it, MAX_FROM_PAGE measured from the farther out of the two: `panes_tick`) and
    the frame's edge bounds the pane. A side where the area leaves no room beyond it (an area that trims only a
    browser's bars) bounds the pane as before - between the area's edge and the page. (per side the area's edge or
    None, the columns the panes are placed within); (None, *columns*) with no area set by hand."""
    if not getattr(app, "_manual_area", False) or not callable(getattr(app, "_hand_set", None)):
        return None, columns
    from . import area

    try:
        hand = area.margins_to_box(app._hand_set(), tuple(size))
    except Exception:  # noqa: BLE001 - not known: as with none
        return None, columns
    width = int(size[0])
    if hand[2] <= hand[0]:
        return None, columns
    least = st.scaled(pn.MIN_W + 2 * pn.GAP, dpi)
    room_left, room_right = hand[0] >= least, width - hand[2] >= least
    if not (room_left or room_right):
        return None, columns
    first, last = columns if columns is not None else (0, width)
    return ((hand[0] if room_left else None, hand[2] if room_right else None),
            (0 if room_left else first, width if room_right else last))


OVER_PAGE = "its place lay over the page box of the frame on show"  # (`_clear_of_page`: why a pane is hidden)
IN_AREA = "its place lay inside the capture area set by hand"
NO_BOX = "the frame on show has no page box, and its place came from an older page's"


def _clear_of_page(app: Any, settled: tuple[Any, Any] | None, boxes: tuple[Any, Any], book: Any = None,
                   made_up: bool = False) -> tuple[Any, Any]:
    """The rule `panes_tick` keeps after every placement: a pane shown never lies inside the columns of a capture area
    set by hand that it is kept out of (*book*, `_book_columns`), nor - once the frame on show has stood (`_settled`;
    while none has, a slide's frames among them, as placed) - over that frame's page box (`_box_of`), nor anywhere
    when that frame has none (its place came from an older page's; but the made-up ground of a tab with no page,
    *made_up*, where none is the rule: `_pick_ground`). A pane that would is hidden, and the log says so once (until
    it is clear again). Before, a page box kept from the book's cover, a single page in the middle, placed the panes
    on the spreads after it for 688 s (`note_frame`)."""
    out: list[Any] = []
    said = getattr(app, "_see_pane_over", None)
    if said is None:
        said = app._see_pane_over = {}
    for k, (side, box) in enumerate(zip(("left", "right"), boxes)):
        why = ""
        edge = book[k] if book is not None else None
        page = settled[0] if settled is not None else None
        if box is None:
            pass
        elif edge is not None and (box[2] > edge if k == 0 else box[0] < edge):
            why = IN_AREA
        elif page is not None and pn.overlap(box, page) > 0:
            why = OVER_PAGE
        elif settled is not None and page is None and not made_up:
            why = NO_BOX
        if why and said.get(side) != why:
            log.info("see-through: the %s pane at %s hidden: %s (%s)", side, tuple(int(v) for v in box), why,
                     "no page box" if page is None else f"page box {tuple(int(v) for v in page)}")
        said[side] = why
        out.append(None if why else box)
    return out[0], out[1]


def _keeps_ground(app: Any, image: Image.Image, box: Any) -> bool:
    """Whether the frame *image*, in which no page box was found (*box* None), leaves the side panes' ground as it is
    although the frame before had none either: a ground of frames of its size is had. Such a frame is no page in its
    place - a slide's frames are such, the page half out of the frame - and it becomes the page at rest only once the
    very picture has stayed REST_S, no other one noted after it (`rest_tick`). Before, a slide let go at the screen's
    edge hid both panes for a fifth of a second (the stand-in's scenario "s" on GitHub's runners, 2 runs of 3): the
    frame held last, the page half out, became the page at rest REST_S after the release, the next screen's soft
    frame drawn meanwhile being one to wait out (`frame_look`'s kind), until the sharp one had stayed too; and two
    frames with no box were taken for a page at rest by being alike."""
    return box is None and _ground_had(app, image.size)


def _ground_had(app: Any, size: Any) -> bool:
    """Whether the side panes have a ground of frames of *size*."""
    ground = getattr(app, "_see_ground", None)
    return ground is not None and ground[0] == size


def _aside(app: Any, box: Any, ground: Any, size: Any, facts: Any = None) -> None:
    """A frame not at rest kept aside (`note_frame`): it becomes the page at rest once REST_S has passed with no other
    picture after it - one the button was held over, RELEASE_S after the release - (`rest_tick`). The very picture
    captured again (its facts shared, `live._captured_facts`) is no other picture: its wait goes on from its first
    capture."""
    now = time.monotonic()
    memo = getattr(facts, "memo", None)
    pending = getattr(app, "_see_unrested", None)
    if pending is not None and len(pending) > 4 and memo is not None and pending[4] is memo:
        now = pending[0]
    app._see_unrested = (now, box, ground, size, memo)


def _at_rest(app: Any, image: Image.Image, box: Any, facts: Any = None) -> bool:
    """Whether the frame *image*, its page box *box* (None: none found), shows the page at rest in its place (see
    `note_frame`); the box is kept for the next frame's look. The very picture noted while the button was held (its
    facts shared, `live._captured_facts`), captured again once it is up, is not: it is the page left as it was held,
    the viewer has not answered the release yet - the page snapped back, or the next one drawn -, and being as the
    frame before (itself) it was taken for the page at rest at once. Before, a slide let go at the screen's edge hid
    the right pane for a quarter of a second (the stand-in's scenario "s" on GitHub's runners, once after six runs
    that passed): the one picture of the slide that reached the capture there showed the page some 200 px to the
    right, the next screen came 0.7 s after the release, and the ground taken from that picture meanwhile put the
    page's right edge over the right pane's place (`pn.reaches`: no room, no pane)."""
    win = getattr(app, "selected", None)
    key = (int(win.hwnd) if win is not None else 0, image.size)
    memo = getattr(facts, "memo", None)
    seen, app._see_box_seen = getattr(app, "_see_box_seen", None), (key, box)
    if held(app):
        app._see_held_at = time.monotonic()
        app._see_held_memo = memo
        return False
    if memo is not None and memo is getattr(app, "_see_held_memo", None):
        return False  # (kept aside, its wait from its first capture: `_aside`, `rest_tick`)
    return seen is None or seen[0] != key or _same_box(seen[1], box, px(app, st.LOOK_STEP))


def _rest(app: Any, box: Any, ground: Any, size: Any = None) -> None:
    """The page at rest: its box (which tells half a spread, in frames of *size*, the frame's: `frame_look`) and the
    side panes' ground (None: no page on a flat ground, the panes hide)."""
    app._see_unrested = None
    if box is not None:
        app._see_rest_box = box
        app._see_rest_size = size
    app._see_ground = ground


def rest_tick(app: Any) -> None:
    """(each tick) The frame kept aside by `note_frame` becomes the page at rest once REST_S has passed with no other
    picture after it (`_aside`) and no button held in the viewer since (the viewer's own frames stopped coming: a page
    at rest is drawn once). One the button was held over (noted before its release) does so only RELEASE_S after
    the release, as the live view waits for the viewer's answer (`_release_unanswered`): a viewer answers a frame or
    two after it, a busy computer's capture far later - the stand-in's next screen 0.7 s after it on GitHub's runners,
    the page left where it was slid meanwhile (`_at_rest`). One noted while the button was held, and one with no
    page box, while the panes have a ground of frames of its size, do so only while still the newest picture noted
    (`_keeps_ground`); else it is dropped, the ground left as it is."""
    pending = getattr(app, "_see_unrested", None)
    if pending is None:
        return
    now = time.monotonic()
    if held(app):
        app._see_held_at = now
        return
    held_at = getattr(app, "_see_held_at", 0.0)
    memo = pending[4] if len(pending) > 4 else None
    noted_held = memo is not None and memo is getattr(app, "_see_held_memo", None)
    if now - max(pending[0], held_at) >= (RELEASE_S if noted_held or held_at >= pending[0] else REST_S):
        size = pending[3] if len(pending) > 3 else None
        if ((pending[1] is None or noted_held) and len(pending) > 4 and getattr(app, "_see_newest", None) is not memo
                and _ground_had(app, size)):
            app._see_unrested = None  # (another picture came after it: a frame to wait out, or one with bars)
            return
        _rest(app, pending[1], pending[2], size)


def _bars_due(app: Any, gone: bool = False) -> None:
    """The bars have stayed BAR_WAIT_S, or (*gone*) have gone: the viewer looked at again, as a look of the follow's
    does (while a job runs, the look comes once it is done: `_look`)."""
    if on(app) and (gone or (app._see_bars_since is not None and not getattr(app, "busy", False))):
        try:
            app._tick()
        except Exception:  # noqa: BLE001 - a look that fails is looked at again by the follow
            pass


def waits(app: Any, image: Image.Image, facts: Any) -> bool:
    """Whether the frame *image* is one to wait out (it counts as one with nothing drawn: neither shown nor followed):
    a loading one (`seethrough.loading_kind`), or one with bars over the page that have not stayed BAR_WAIT_S yet
    (`note_frame`)."""
    found = frame_look(app, image, facts)
    if found.kind is not None:
        return True
    if not found.bands:
        return False
    since = app._see_bars_since
    return since is None or time.monotonic() - since < BAR_WAIT_S


def reading_frame(app: Any, image: Image.Image, facts: Any) -> Image.Image:
    """The frame as it is read: with the rows of bars painted in the ground's colour (`waits` lets such a frame
    through only once they have stayed BAR_WAIT_S), carrying *image*'s look with no bars (`painted_look`: a look at
    its own pixels would take the painted rows for ground and find another page box, and its steady part another
    picture of the page, long after - once the window has let go of the frame's facts); else *image* itself."""
    found = frame_look(app, image, facts)
    if not found.bands or found.kind is not None or waits(app, image, facts):
        return image
    read = Image.fromarray(st.masked(facts.rgb(), found.bands, found.ground))
    read.info[LOOK_INFO] = painted_look(app, image, facts)
    read.info[PAINTED_INFO] = found.bands
    return read


def read_under_bars(app: Any, image: Image.Image) -> bool:
    """Whether the page on show in *image* (a frame with no bars painted over: they have gone) was last read from a
    frame with bars painted over (`reading_frame`) and a bubble read reaches the rows painted over (CUT_PX: cut at a
    bar's edge, and its lettering's patch, whose margin takes in those rows, never shown)."""
    if PAINTED_INFO in getattr(image, "info", {}):
        return False
    result = getattr(app, "last_result", None)
    original = getattr(result, "original", None)
    if original is None or PAINTED_INFO not in getattr(original, "info", {}) or original.size != image.size:
        return False
    rows = original.info[PAINTED_INFO]
    boxes = [tuple(getattr(r, "bbox", ())) for r in getattr(result, "regions", None) or ()]
    near = px(app, CUT_PX)
    cut = any(len(b) == 4 and b[1] < end + near and b[3] > start - near for b in boxes for start, end in rows)
    return cut and bool(app._shows_page(image, original))


def after_bars(app: Any, image: Image.Image) -> bool:
    """The bars have gone from the page last read with them painted over (`read_under_bars` aside, any such page on
    show again in *image*, nothing running): its cached pages carried over to the units of *image*
    (`Pipeline.carry_over`: the painted frame's units have fingerprints of their own - and on a dark ground boxes of
    their own -, so that the page would not be found again), the bubbles that reach the painted rows left out and the
    page marked as lacking them. Whether it is to be read once more now: some were left out (that reading reads and
    asks for those alone, and for a bubble the bars hid whole), or none could be carried over and a bubble was cut
    (then the page is read anew). Done once: the read frame's mark goes."""
    if PAINTED_INFO in getattr(image, "info", {}) or getattr(app, "busy", False):
        return False
    result = getattr(app, "last_result", None)
    original = getattr(result, "original", None)
    if original is None or PAINTED_INFO not in getattr(original, "info", {}) or original.size != image.size:
        return False
    if not app._shows_page(image, original):
        return False
    cut = read_under_bars(app, image)
    rows = original.info.pop(PAINTED_INFO)
    carried = dropped = 0
    pipeline = getattr(app, "pipeline", None)
    if pipeline is not None:
        try:
            carried, dropped = pipeline.carry_over(result, image, rows, px(app, CUT_PX))
        except Exception:  # noqa: BLE001 - the cache stays as it was; the page is read anew if a bubble was cut
            carried = dropped = 0
    notes = getattr(app, "_see_carries", None)
    if notes is not None:
        notes.append((time.monotonic(), carried, dropped))
    return dropped > 0 or (carried == 0 and cut)


def steady_area(app: Any, image: Image.Image, facts: Any) -> tuple[int, int, int, int]:
    """What the steady part of *image*'s page area is cut from (`seethrough.steady_box`; frame pixels): the page box's
    columns - the ground beside the page left out, where a viewer draws its arrows - and the capture area's rows, not
    the page box's: under bars at its top or bottom the box reaches the frame's edge (whether the page goes on under a
    bar is not seen), and without them its top and bottom are where the page's own picture leaves the ground's colour,
    which a dark page on a dark ground does well below its edge. The rows the bars cover are left out all the same."""
    found = frame_look(app, image, facts)
    _rgb, area = area_rgb(app, image, facts)
    if found.box is None:
        return area
    return found.box[0], area[1], found.box[2], area[3]


def detail_box(app: Any, image: Image.Image, facts: Any, box: Any) -> Any:
    """The part of *box* (frame pixels; None: the whole frame) that bars over the page's top and bottom never touch -
    the page's steady part (`seethrough.steady_box` of `steady_area`) within it -, by which the window tells a sharper
    or softer picture of the page: so a frame read with its bars painted over is never taken for a softer one. *box*
    itself where no page is found."""
    if frame_look(app, image, facts).box is None:
        return box
    steady = st.steady_box(image.size, steady_area(app, image, facts))
    if box is None:
        return steady
    inner = (max(box[0], steady[0]), max(box[1], steady[1]), min(box[2], steady[2]), min(box[3], steady[3]))
    return inner if inner[0] < inner[2] and inner[1] < inner[3] else box


def painted_look(app: Any, image: Image.Image, facts: Any) -> st.Look:
    """The look of the frame `reading_frame` made of *image* (its bars painted over): *image*'s, with no bars - so
    that the frame read is never one to wait out, and its steady part is *image*'s (`thumb`)."""
    found = frame_look(app, image, facts)
    return st.Look(found.box, (), found.kind, found.ground)


def thumb(app: Any, image: Image.Image, facts: Any) -> np.ndarray:
    """The thumbnail the window compares frames by in see-through mode: the steady part of the page area
    (`seethrough.steady_thumb`), or a flat one (nothing drawn) for a frame to wait out (`waits`)."""
    if waits(app, image, facts):
        return np.zeros((st.THUMB, st.THUMB), np.float32)

    def make() -> np.ndarray:
        return st.steady_thumb(facts.rgb(), steady_area(app, image, facts))

    return facts.get(("see_thumb",), make)


def page_box(app: Any, image: Image.Image, facts: Any) -> tuple[int, int, int, int] | None:
    """The page on its ground in *image* (frame pixels), for the capture area (`LiveViewMixin._find_page`); None on a
    frame to wait out, or where none is found."""
    found = frame_look(app, image, facts)
    if found.kind is not None:
        return None
    return found.box
