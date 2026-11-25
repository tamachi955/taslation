"""See-through mode on the Tk side - the program's one mode since TASlation's own window went (the viewer's window or
its full screen): TASlation's lettering lies over the viewer's own window (`capture.seethrough`), and the viewer takes
every click and key itself - but, with the left pane's Edit on (`see_edit`: the Translator role), the clicks on the
page's regions.

* `start` makes the see-through window at the window's start (Windows; and asks the capture for frames up to every
  `wgc.FAST_UPDATE_MS`); where it cannot be made the program says so and ends (`could_not_start`); `close` ends it. `tick` (every TICK_MS) tells it which viewer to lie over and
  hands it the page's patches when they changed (`present`; `_redisplay` asks for that too). The mode's one key is
  Insert, held only while the viewer is in front and only while ``Settings.add_area_key`` is on (`tick`:
  `SeeThrough.set_add_key`; Add area, `see_edit`): every other key goes to the viewer, and the lettering is hidden
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
  outer edges (`note_frame` keeps the page box at rest, the area's columns, the steady band and the ground's colour),
  LEFT the controls - Translate (Stop while a page can be stopped) with, at the row's right end, a square button drawn
  as a circular arrow that has the page on show translated again (`_again`: the window's Translate again, its lines
  asked of the translator anew; dim until a page was lettered and while the window's Translate is), Auto, the target
  language (an arrow each side; taken once no
  arrow was clicked for LANGUAGE_SETTLE_MS), the lettering's switch, the indicators' switch (kept in the settings
  file: ``see_through_indicators``), Edit (with TASlation's window hidden: the page's regions edited on the overlay,
  `see_edit`), Add area (a text area drawn on the page, Edit on or off: `see_edit.toggle_adding`; pressed while one
  is to be added; "(Insert)" while that key adds one), Set area..., Settings..., Menu (`see_menu`: what the hidden
  root's controls
  offer that still means something here), Quit -, RIGHT the indicators: what the status slot says, how far the page
  filling in is (lines lettered of the lines read), the status line, the backlog and the pages that went by too fast
  (the indicator's own lines), where the translator runs - the window's words as they are: they name the panes'
  controls and the Menu's entries, no key -, under the bubble last under
  the pointer (`bubble_rows`: Copy the Japanese, Copy the translation and Ask again, then its Japanese and its
  translation; kept once the pointer has left it, so that the pointer can go to the pane, until another bubble is
  under it or the viewer shows another page: `bubble_tick`; Ask again asks the translator for that line alone, with
  no question first: `ask_bubble`). The right pane takes a click on those plates alone; with the indicators switched
  off the block goes with them. `panes_tick` (every TICK_MS) acts on the clicks on the panes and draws a pane again
  only when what it says changed. A pane that would come near the page hides (`panes.place`); the right one leaves
  the bubble's block out where it does not fit with it.
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
  menu or the button: `asked`) takes the keys as it shows (`_mapped`), the others keep their own way (the start's
  ones leave the foreground where it is: `layout.dialog_keys`). With no viewer chosen the viewer chooser comes by
  itself (`see_menu.chooser_due`), and the setup banner's lines come as a small dialog of their own
  (`see_menu.show_banner`).

Nothing here presses a key or posts a message to the viewer, and nothing but the reader's own choice in a pane, the
menu, the taskbar button or a region in Edit, or a dialog of TASlation's own, moves the foreground."""

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
CUT_PX = 3  # a bubble read this close to rows painted over was cut by them (`read_under_bars`)
# (CUT_PX and the patches' and the look's pixel sizes are at 96 DPI: `px` takes them to the viewer's, `tick`)


QUIET_MS = 500  # (see-through mode) the decoy of `quiet_start` goes so long after the window's start is made
LANGUAGE_SETTLE_MS = 1200  # the language chosen with the left pane's arrows is taken once none was clicked so long
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
    """Where a dialog of the hidden window is centred (`layout.dialog_area`): the middle of the viewer's window, or,
    with none, the middle of the primary monitor's work area; None while the window is on the screen (its dialogs go
    over it, as ever)."""
    if not hidden(app):
        return None
    win = getattr(app, "selected", None)
    if win is not None:
        try:
            from ..capture import window_exists, window_rect

            if window_exists(win.hwnd):
                left, top, right, bottom = window_rect(win.hwnd)
                return (left + right) // 2, (top + bottom) // 2
        except Exception:  # noqa: BLE001 - (the viewer gone meanwhile: the primary monitor)
            pass
    from .layout import work_area

    left, top, right, bottom = work_area(app)
    return (left + right) // 2, (top + bottom) // 2


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
    dialogs = own_dialogs(app)
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
    if not hidden(app) or not isinstance(widget, tk.Toplevel) or not _recently_asked(app, ASKED_S):
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


COULD_NOT_START = "TASlation could not lay its lettering over the viewer's window on this computer, and ends."


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
    app._see_job = None
    app._see_carries = []  # (when, pages carried over, bubbles left out), see after_bars
    app._see_dpi = st.BASE_DPI  # the viewer's monitor's DPI (`tick`)
    app._see_ground = None  # (frame size, page box, steady band's rows, ground's colour, the capture area's columns)
    # at the last rest (`note_frame`)
    app._see_unrested = None  # (when, page box, ground) of a frame not at rest yet (`note_frame`, `rest_tick`)
    app._see_box_seen = None  # ((viewer, frame size), page box) of the frame noted last
    app._see_held_at = 0.0  # when the button was last seen held in the viewer
    app._see_pane_memo = {}  # side -> (what its picture was made of, the picture, its box) as handed over last
    app._see_language = None  # (language, after job) while the left pane's arrows are being clicked
    app._see_clicked = []  # (when, control) of each click acted on, for the tools
    app._see_ticks = 0
    app._see_asked = -1e9  # when the reader last asked for something (`asked`)
    app._see_menu_up = False  # a menu of TASlation's is up (`see_menu.popup`)
    app._see_root_hwnd = 0  # the hidden window's handle, for the tools (`keep_hidden`)
    app._see_hidden_fixes = {}  # what `keep_hidden` put back, counted
    app._see_handed_back = 0  # how often `hand_back` gave the foreground back to the viewer
    app._see_front = {}  # what `front_tick` did instead, counted
    app._see_closed_at = -1e9  # when a dialog of the window's went or a menu ended last (`_closed`)
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


def close(app: Any) -> None:
    patcher, app._see_patcher = getattr(app, "_see_patcher", None), None
    if patcher is not None:
        patcher.close()
    over = getattr(app, "_see_through", None)
    if over is not None:
        app._see_through = None
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
    app._see_dpi = window.viewer_dpi(hwnd)
    over.set_hover_delay(hover_delay(app))
    set_add_key = getattr(over, "set_add_key", None)
    if set_add_key is not None:  # (the Insert key: Add area while the viewer is in front, `see_edit`)
        set_add_key(hidden(app) and bool(getattr(getattr(app, "settings", None), "add_area_key", True)))
    present(app)
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


def _languages(app: Any) -> list[str]:
    """The target languages the left pane's arrows go through: the "To:" box's list (English names), the language in
    force first when it is not one of them."""
    from .constants import LANGUAGES

    names = list(LANGUAGES)
    current = str(_get(getattr(app, "lang_var", None), "") or "")
    if current and current not in names:
        names.insert(0, current)
    return names


def _language_shown(app: Any) -> str:
    """The target language as the left pane shows it: the one being chosen with its arrows, else the one in force."""
    picking = getattr(app, "_see_language", None)
    language = picking[0] if picking is not None else str(_get(getattr(app, "lang_var", None), "") or "")
    from .constants import LANGUAGES

    return _(language) if language in LANGUAGES else language


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

    edit = [pn.Row("edit", _(see_edit.EDIT), "toggle", on=see_edit.on(app)),
            pn.Row("add_area", _(see_edit.ADD_AREA), on=see_edit.adding(app))] if hidden(app) else []
    return [first,
            pn.Row("auto", _("Auto"), "toggle", on=bool(_get(getattr(app, "auto_var", None), False))),
            pn.Row("language", _language_shown(app), "choice"),
            pn.Row("lettering", _("Lettering"), "toggle", on=bool(over is None or over.on)),
            pn.Row("indicators", _("Indicators"), "toggle", on=indicators_on(app)),
            *edit,
            pn.Row("area", _("Set area...")),
            pn.Row("settings", _("Settings...")),
            pn.Row("menu", _("Menu")),
            pn.Row("quit", _("Quit"))]


def right_rows(app: Any) -> list[pn.Row]:
    """The right pane, words only, each row only when it has something to say: the setup banner's lines (the setup's
    problems and notices, what keeps TASlation from reading the viewer: `StatusMixin._show_banner`; what their buttons
    do is in the Menu, `see_menu.build`) and the offline guard's warning, which TASlation's window would show; for a
    few seconds after a choice in the viewer chooser, "Viewer: <title>" (``_see_viewer_note``, `viewers.VIEWER_NOTE_S`);
    the status slot (`status_slot`: what the page cannot show itself), how far the page filling in is, the status
    line, the indicator's lines on the pages behind (the backlog, those that went by too fast: `side_model`), where the
    translator runs, in the window's words as they are (they name the panes' controls and the Menu's entries, no
    key). The reader's notes on a
    page (`_show_notes`, the window's strip under the page) are left out."""
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
    status = str(_get(getattr(app, "status_var", None), "") or "").strip()
    note = getattr(app, "_see_viewer_note", None)  # (the viewer chosen in the chooser: `ViewerMixin._on_window_selected`)
    if note is not None and time.monotonic() < note[1]:
        said = _("Viewer: {title}").format(title=note[0])
        if not status.startswith(said):  # (the status line saying it already, perhaps with more: once)
            rows.append(pn.Row("", said, "text"))
    side = getattr(app, "_side", None)
    shown = getattr(getattr(side, "slot", None), "shown", None)
    want = shown[0] if shown else None
    slot = status_slot.slot_text(want[0]).strip() if want else ""
    if slot:
        rows.append(pn.Row("", slot, "text", warn=bool(want and want[1])))
    fill = getattr(app, "_fill", None)
    if fill is not None and fill.final is None:
        total = sum(1 for s in fill.states if s != "skipped")
        if total:
            rows.append(pn.Row("", _("This page: {done} of {total} lines").format(done=fill.filled, total=total),
                               "text"))
    if status and any(status == row.text for row in rows):
        status = ""  # (the status line saying a banner's line again: once)
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
    where = getattr(app, "_compute_where", "")
    if where in ("gpu", "cpu"):
        rows.append(pn.Row("", _("Translator: on the GPU") if where == "gpu" else _("Translator: on the processor"),
                           "text"))
    return rows


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


def panes_tick(app: Any) -> None:
    """The clicks on the side panes acted on, the bubble the right one shows followed (`bubble_tick`), then both panes
    handed to the see-through window as they are to be: on the ground at the capture area's outer edges, beside the
    page at the last rest, or hidden (no page on a flat ground yet, no room, the right one switched off). The right
    one holds the bubble's block above the indicators when they fit with it, else the indicators alone; its plates'
    boxes go with it (the window lets it take a click there alone)."""
    over = getattr(app, "_see_through", None)
    if over is None:
        return
    for side, x, y, _t in over.take_clicks():
        if pane_click(app, side, x, y) == "quit":
            return  # (the window has gone)
    bubble_tick(app, over)
    rest_tick(app)
    ground = getattr(app, "_see_ground", None)
    if ground is None:
        for side, memo in list(app._see_pane_memo.items()):
            app._see_pane_memo[side] = (memo[0], memo[1], None)  # (a click comes to nothing)
        over.set_panes(None, None)
        return
    size, page, band, colour, columns = ground
    dpi = getattr(app, "_see_dpi", st.BASE_DPI)
    language = ui_language()
    scheme = pn.colours(colour)
    room_left, room_right = pn.rooms(size, page, dpi, columns)
    left = _picture(app, "left", left_rows(app), room_left, language, dpi, scheme)
    left_size = left.size if left else None
    words = right_rows(app) if indicators_on(app) else []
    block = bubble_rows(app) if indicators_on(app) else []
    used = "bubble"
    right = _picture(app, used, block + words, room_right, language, dpi, scheme) if block else None
    box_left, box_right = pn.place(size, page, band, left_size, right.size if right else None, dpi, columns)
    if right is None or box_right is None:  # (no bubble, or no room for its block: the indicators alone)
        used = "right"
        right = _picture(app, used, words, room_right, language, dpi, scheme)
        box_left, box_right = pn.place(size, page, band, left_size, right.size if right else None, dpi, columns)
    app._see_right_used = used
    for side, picture, box in (("left", left, box_left), ("right", right if used == "right" else None, box_right),
                               ("bubble", right if used == "bubble" else None, box_right)):
        memo = app._see_pane_memo.get(side)
        if memo is not None:
            app._see_pane_memo[side] = (memo[0], memo[1], box if picture is not None else None)
    over.set_panes((left.bgra, box_left) if left is not None and box_left is not None else None,
                   (right.bgra, box_right, tuple(b for _name, b in right.hits))
                   if right is not None and box_right is not None else None)


def pane_click(app: Any, side: str, x: int, y: int) -> str:
    """A click on the pane *side* at (*x*, *y*) of its picture as last handed over: the control there acted on; its
    name ("" for none)."""
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


def _pick_language(app: Any, step: int) -> None:
    """An arrow of the language row: the next or the one before in the list, shown at once, taken once no arrow was
    clicked for LANGUAGE_SETTLE_MS (the translator may follow it with another model)."""
    names = _languages(app)
    picking = getattr(app, "_see_language", None)
    current = picking[0] if picking is not None else str(_get(getattr(app, "lang_var", None), "") or "")
    index = names.index(current) if current in names else 0
    chosen = names[(index + step) % len(names)]
    if picking is not None:
        try:
            app.after_cancel(picking[1])
        except (tk.TclError, ValueError):
            pass
    try:
        job = app.after(LANGUAGE_SETTLE_MS, lambda: _language_settled(app))
    except Exception:  # noqa: BLE001 - no Tk loop (a test): taken at once
        app._see_language = (chosen, None)
        _language_settled(app)
        return
    app._see_language = (chosen, job)


def _language_settled(app: Any) -> None:
    """The language chosen with the arrows taken, as the "To:" box takes one chosen there (`_target_picked`); a
    language whose model is not there is offered in a dialog of the window's, which takes the keys as it shows: the
    reader asked for it (`asked`)."""
    picking, app._see_language = getattr(app, "_see_language", None), None
    if picking is None:
        return
    language = picking[0]
    if language == str(_get(getattr(app, "lang_var", None), "") or ""):
        return
    plan = getattr(app, "_plan", None)
    try:
        offered = plan is not None and plan(language) is not None
    except Exception:  # noqa: BLE001 - not known: taken as an offer
        offered = True
    if offered:
        asked(app)
    from .constants import LANGUAGES

    shown = getattr(app, "lang_shown", None)
    if shown is not None:
        shown.set(_(language) if language in LANGUAGES else language)  # (the "To:" box: lang_var follows)
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
    """The left pane's Add area: a text area to add begun, or given up (`see_edit.toggle_adding`), Edit on or off."""
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
    if edited is not None and result is not None and result.original is not None:  # (Edit: the region in the editor,
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
    "language_prev": lambda app: _pick_language(app, -1),
    "language_next": lambda app: _pick_language(app, 1),
    "lettering": toggle,
    "indicators": _flip_indicators,
    "area": _dialog("set_area"),
    "settings": _dialog("open_settings"),
    "menu": _menu,
    "edit": lambda app: _edit(app),  # (Edit: the Translator role on the overlay, `see_edit`)
    "add_area": _add_area,  # (Add area: a text area drawn on the page, Edit on or off)
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
        patches = st.make_patches(self._frame_pixels(original), _rgb(lettered), margin=margin, gap=gap)
        self.over.present(key, original.size, patches, final)
        self.made += 1


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
            over.present(id(original), original.size, st.make_patches(_rgb(original), _rgb(lettered), margin=margin,
                                                                      gap=gap), final)
        memo[:] = [(original, state), *[(img, s) for img, s in memo if img is not original]][:MEMO_KEPT]


# ------------------------------------------------------------------ which frames start a job
def area_rgb(app: Any, image: Image.Image, facts: Any) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """The capture area of *image* (the reader's own when set, else the whole frame) and its box."""
    hand = app._hand_set() if getattr(app, "_manual_area", False) else (0, 0, 0, 0)
    from . import area

    box = area.margins_to_box(hand, image.size)
    if box[2] <= box[0] or box[3] <= box[1]:
        box = (0, 0, image.width, image.height)
    rgb = facts.rgb()
    return rgb[box[1]:box[3], box[0]:box[2]], box


def frame_look(app: Any, image: Image.Image, facts: Any) -> st.Look:
    """`seethrough.look` of *image*'s capture area (kept with the frame's facts), its boxes in the frame's pixels; for
    a frame `reading_frame` made, the look it was given (`LOOK_INFO`)."""
    given = getattr(image, "info", {}).get(LOOK_INFO)
    if given is not None:
        return given

    def make() -> st.Look:
        rgb, box = area_rgb(app, image, facts)
        before = app._see_rest_box
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
    (within LOOK_STEP; the first frame of a viewer or of a size counts), and no button held in the viewer (`held`).
    Another is kept aside (`_see_unrested`) and becomes it once REST_S has passed with no frame after it and no press
    (`rest_tick`). Before, every frame was: a page that a viewer drags along with the pointer, out of its place and
    over the panes' places, hid the panes while it was held there, and the frame of a page taken while it moved, or
    found on no flat ground, set the panes by it until the next frame at rest. A frame with bars over the page leaves
    the ground as it is - but while none of a frame of its size is had: then it gives it (`_ground_under_bars`)."""
    found = frame_look(app, image, facts)
    if found.kind is not None:
        return
    if not found.bands:
        if app._see_bars_since is not None:  # the bars have gone: a page read under them is read once more
            try:
                app.after(GONE_LOOK_MS, lambda: _bars_due(app, gone=True))
            except Exception:  # noqa: BLE001 - no Tk loop (a test)
                pass
        app._see_bars_since = None
        ground = _ground_of(app, image, facts, found)
        if _at_rest(app, image, found.box):
            _rest(app, found.box, ground)
        else:
            app._see_unrested = (time.monotonic(), found.box, ground)
        return
    if app._see_bars_since is None:
        app._see_bars_since = time.monotonic()
        try:
            app.after(int(BAR_WAIT_S * 1000) + 30, lambda: _bars_due(app))
        except Exception:  # noqa: BLE001 - no Tk loop (a test)
            pass
    _ground_under_bars(app, image, facts, found)


def _ground_of(app: Any, image: Image.Image, facts: Any, found: st.Look) -> Any:
    """The side panes' ground in the frame *image* whose look is *found*: (its size, the page box, the steady band's
    rows, the ground's colour, the capture area's columns); None when no page on a flat ground was found."""
    if found.box is None:
        return None
    _rgb, area = area_rgb(app, image, facts)
    steady = st.steady_box(image.size, area)
    return image.size, found.box, (steady[1], steady[3]), found.ground, (area[0], area[2])


def _ground_under_bars(app: Any, image: Image.Image, facts: Any, found: st.Look) -> None:
    """A frame with bars over the page (`note_frame`) while no ground of a frame of its size is had: the side panes'
    ground taken from it, at rest as any frame is (`_at_rest`, `rest_tick`). What the panes are placed by is there
    with the bars as without them - the page's columns (`seethrough.ground_box` leaves the bars' rows out) and the
    steady band, where bars never come -, and a viewer that came into sight with its bars up and keeps them (the
    pointer resting on them, a click that holds them: a viewer brought to the front from behind other windows) gave
    no frame without them before: the panes would stay hidden until the bars went, page turn after page turn. With a
    ground of the frame's size had, the frames with bars leave it as it is (as ever)."""
    ground = getattr(app, "_see_ground", None)
    if found.box is None or (ground is not None and ground[0] == image.size):
        return
    under = _ground_of(app, image, facts, found)
    if _at_rest(app, image, found.box):
        _rest(app, found.box, under)
    else:
        app._see_unrested = (time.monotonic(), found.box, under)


def _at_rest(app: Any, image: Image.Image, box: Any) -> bool:
    """Whether the frame *image*, its page box *box* (None: none found), shows the page at rest in its place (see
    `note_frame`); the box is kept for the next frame's look."""
    win = getattr(app, "selected", None)
    key = (int(win.hwnd) if win is not None else 0, image.size)
    seen, app._see_box_seen = getattr(app, "_see_box_seen", None), (key, box)
    if held(app):
        app._see_held_at = time.monotonic()
        return False
    return seen is None or seen[0] != key or _same_box(seen[1], box, px(app, st.LOOK_STEP))


def _rest(app: Any, box: Any, ground: Any) -> None:
    """The page at rest: its box (which tells half a spread) and the side panes' ground (None: no page on a flat
    ground, the panes hide)."""
    app._see_unrested = None
    if box is not None:
        app._see_rest_box = box
    app._see_ground = ground


def rest_tick(app: Any) -> None:
    """(each tick) The frame kept aside by `note_frame` becomes the page at rest once REST_S has passed with no frame
    after it and no button held in the viewer since (the viewer's own frames stopped coming: a page at rest is drawn
    once)."""
    pending = getattr(app, "_see_unrested", None)
    if pending is None:
        return
    now = time.monotonic()
    if held(app):
        app._see_held_at = now
        return
    if now - max(pending[0], getattr(app, "_see_held_at", 0.0)) >= REST_S:
        _rest(app, pending[1], pending[2])


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
