"""See-through mode on the Tk side (a prototype behind ``Settings.see_through``, off by default; the Reader role, the
viewer's window or its full screen): TASlation's lettering lies over the viewer's own window (`capture.seethrough`),
and the viewer takes every click and key itself.

* `start` makes the see-through window at the window's start when the setting is on (and asks the capture for frames
  up to every `wgc.FAST_UPDATE_MS`); `close` ends it. `tick` (every TICK_MS) tells it which viewer to lie over and
  hands it the page's patches when they changed (`present`; `_redisplay` asks for that too). The mode holds no hot
  key: every key goes to the viewer, and the lettering is hidden and shown again with the left pane's switch.
* The patches are where the lettered page differs from the frame it was read from - the page filling in (drafts,
  then the final page) and the last translated page -, made on the Tk thread and handed over as immutable arrays.
  Whether a patch shows is the see-through window's own decision, at every frame of the viewer's
  (`taslation.seethrough`: a patch belongs to the pixels it was made from).
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
  as a circular arrow that asks for the page on show again (`translate_now`, what F5 does in the window; dim until a
  page was lettered and while the window's Translate is), Auto, the target language (an arrow each side; taken once no
  arrow was clicked for LANGUAGE_SETTLE_MS), the lettering's switch, the indicators' switch (kept in the settings
  file: ``see_through_indicators``), Set area..., Settings..., the way back to TASlation's window, Quit -, RIGHT the
  indicators: what the status slot says, how far the page filling in is (lines lettered of the lines read), the status
  line, the backlog, the pages that went by too fast and those updated since they were seen (the indicator's own
  lines), where the translator runs - the window's words with what they say of keys left out (`panes.without_keys`:
  the keys are the viewer's here). `panes_tick` (every TICK_MS) acts on the clicks on the left pane and draws a pane
  again only when what it says changed. A pane that would come near the page hides (`panes.place`).
* TASlation's own window is put aside: shown at a quiet start (never activated, so that its widgets are laid out)
  and minimised QUIET_MS later (`quiet_started`; minimising a window that is not active moves no foreground), reached
  again from the left pane (TASlation window) or the taskbar. A dialog of its own that comes up meanwhile - the
  book's name asked for, a model offered - would wait unseen behind the minimised window (Tk keeps a transient of a
  minimised window hidden), so the window is shown again for it (`_dialog_waits`). A control that opens a dialog
  (Set area..., Settings..., a language whose model is not there) shows the window first, and that is the one time a
  click on a pane brings TASlation in front: the reader asked for its dialog.

Nothing here presses a key or posts a message to the viewer, and nothing but the reader's own choice in a pane, or a
dialog of TASlation's own, moves the foreground."""

from __future__ import annotations

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

TICK_MS = 50
BAR_WAIT_S = 3.5  # a frame with bars over the page is read only once they have stayed so long (a viewer's own bars go
# by themselves in 1-3 s once the pointer rests; bars held longer are painted over in the frame read)
MEMO_KEPT = 4
LOOK_INFO = "taslation.see_look"  # (the picture's info) the look a frame read with its bars painted over was given
PAINTED_INFO = "taslation.see_painted"  # (the picture's info) the rows painted over in it
GONE_LOOK_MS = 150  # once the bars have gone, the viewer is looked at so soon (a page read under them: read_under_bars)
CUT_PX = 3  # a bubble read this close to rows painted over was cut by them (`read_under_bars`)
# (CUT_PX and the patches' and the look's pixel sizes are at 96 DPI: `px` takes them to the viewer's, `tick`)


QUIET_MS = 500  # (see-through mode) the decoy of `quiet_start` goes so long after the window's start is made, and the
# window is minimised then (once it has been shown: its widgets laid out at their sizes)
ASIDE_TRIES = 10  # ... looked at again every QUIET_MS so many times while it is not shown yet
LANGUAGE_SETTLE_MS = 1200  # the language chosen with the left pane's arrows is taken once none was clicked so long


def px(app: Any, size: int) -> int:
    """*size* px at 96 DPI as many pixels of the viewer's frames (its monitor's DPI, `tick`): a viewer at 125 % or
    150 % draws everything that much larger (`seethrough.scaled`)."""
    return st.scaled(size, getattr(app, "_see_dpi", st.BASE_DPI))


def on(app: Any) -> bool:
    """Whether see-through mode runs in the window *app*."""
    return getattr(app, "_see_through", None) is not None


def quiet_start(app: Any, settings: Any) -> None:
    """At the very start of the window, before Tk first shows it, in see-through mode (Windows): Tk activates the
    first top-level window it makes (SetActiveWindow when it is first shown - Tk 8.6.15, whatever its state: hidden
    or minimised alike), which takes the foreground from the viewer; so the first one it makes is a decoy put inside
    a frame of the window's own (``-use``), a child window, which nothing activates. The window itself is then shown
    as Tk shows every later one, not activated (SW_SHOWNOACTIVATE): the viewer stays in front and takes the reader's
    keys with no click first. Nothing moves the foreground. The decoy goes once the window is shown
    (`quiet_started`)."""
    app._quiet_decoy = None
    app._quiet_ended = False
    if not (bool(getattr(settings, "see_through", False)) and window.IS_WINDOWS):
        return
    try:
        box = tk.Frame(app, container=True)  # (never shown)
        decoy = tk.Toplevel(app, use=str(box.winfo_id()))
        app._quiet_decoy = (decoy, box)
    except tk.TclError:  # (no decoy: the window takes the foreground at its start as ever)
        pass


def quiet(app: Any) -> bool:
    """Whether the window starts quietly (`quiet_start`): not maximised then, for Windows activates a window it
    maximises."""
    return getattr(app, "_quiet_decoy", None) is not None and not getattr(app, "_quiet_ended", False)


def quiet_started(app: Any) -> None:
    """The window's start made (Tk shows it at its first idle, the decoy first): the decoy goes QUIET_MS later, and
    in see-through mode the window is put aside then (`aside`) - unless the start was not quiet after all (the legal
    notice)."""
    if getattr(app, "_quiet_decoy", None) is None:
        return
    put_aside = quiet(app) and on(app)

    def drop() -> None:
        decoy, app._quiet_decoy = app._quiet_decoy, None
        for widget in decoy or ():
            try:
                widget.destroy()
            except tk.TclError:
                pass
        if put_aside and not getattr(app, "_quiet_ended", False):
            aside(app)

    app.after(QUIET_MS, drop)


def aside(app: Any, tries: int = ASIDE_TRIES) -> None:
    """TASlation's own window minimised, once it has been shown (never activated: minimising it moves no foreground),
    so that the viewer stands alone with the panes; it is reached again from the left pane (`window_up`) or the
    taskbar."""
    try:
        if not app.winfo_ismapped():
            if tries > 0:
                app.after(QUIET_MS, lambda: aside(app, tries - 1))
            return
        if app.state() == "normal":
            app.iconify()
            app._see_aside = True
    except tk.TclError:
        pass


def window_up(app: Any) -> None:
    """TASlation's own window shown again and brought in front (the reader asked for it, or for one of its dialogs):
    maximised again when it opened so."""
    app._see_aside = False
    try:
        if app.state() in ("iconic", "withdrawn"):
            app.deiconify()
            if getattr(app, "_opening_zoomed", False):
                app.state("zoomed")
        app.lift()
        app.focus_force()
    except tk.TclError:
        pass


def _dialog_waits(app: Any) -> None:
    """While the window is put aside (`aside`), a dialog of its own that is to show (a transient top-level, neither
    shown nor a tip): Tk keeps it hidden behind the minimised window, so the window is shown again for it."""
    if not getattr(app, "_see_aside", False):
        return
    try:
        if app.state() != "iconic":
            app._see_aside = False  # (the reader showed it again: theirs from now on)
            return
        decoy = getattr(app, "_quiet_decoy", None) or ()
        for child in app.winfo_children():
            if not isinstance(child, tk.Toplevel) or child in decoy:
                continue
            if child.wm_transient() and not child.wm_overrideredirect() and not child.winfo_viewable():
                window_up(app)
                return
    except tk.TclError:
        pass


def quiet_end(app: Any) -> None:
    """No quiet start after all (the legal notice, which is the reader's to answer: it and the window after it take
    the foreground as ever)."""
    app._quiet_ended = True


def start(app: Any) -> bool:
    """The see-through window made when the setting asks for it (Windows only); whether it runs."""
    app._see_through = None
    app._see_memo = []
    app._see_bars_since = None
    app._see_rest_box = None
    app._see_job = None
    app._see_carries = []  # (when, pages carried over, bubbles left out), see after_bars
    app._see_dpi = st.BASE_DPI  # the viewer's monitor's DPI (`tick`)
    app._see_ground = None  # (frame size, page box, steady band's rows, ground's colour, the capture area's columns)
    # at the last rest (`note_frame`)
    app._see_pane_memo = {}  # side -> (what its picture was made of, the picture, its box) as handed over last
    app._see_language = None  # (language, after job) while the left pane's arrows are being clicked
    app._see_clicked = []  # (when, control) of each click acted on, for the tools
    app._see_aside = False  # the window was put aside (`aside`)
    if not bool(getattr(app.settings, "see_through", False)):
        return False
    over = window.SeeThrough.start()
    if over is None:
        return False
    app._see_through = over
    wgc.set_update_ms(wgc.FAST_UPDATE_MS)
    try:
        app._see_job = app.after(TICK_MS, lambda: _tick(app))
    except Exception:  # noqa: BLE001 - no Tk loop (a test): the window runs all the same
        pass
    return True


def close(app: Any) -> None:
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
    drawn again when they changed."""
    over = app._see_through
    win = getattr(app, "selected", None)
    hwnd = int(win.hwnd) if win is not None else 0
    over.follow(hwnd)
    app._see_dpi = window.viewer_dpi(hwnd)
    present(app)
    panes_tick(app)
    if on(app):  # (not after Quit on the left pane: the window has gone)
        _dialog_waits(app)


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
    """Whether the left pane's circular arrow (ask for the page on show again: `translate_now`, F5 in the window) is
    live: once a page was lettered, and not while the window's Translate is greyed (a job at work for a while)."""
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
    return [first,
            pn.Row("auto", _("Auto"), "toggle", on=bool(_get(getattr(app, "auto_var", None), False))),
            pn.Row("language", _language_shown(app), "choice"),
            pn.Row("lettering", _("Lettering"), "toggle", on=bool(over is None or over.on)),
            pn.Row("indicators", _("Indicators"), "toggle", on=indicators_on(app)),
            pn.Row("area", _("Set area...")),
            pn.Row("settings", _("Settings...")),
            pn.Row("window", _("TASlation window")),
            pn.Row("quit", _("Quit"))]


def right_rows(app: Any) -> list[pn.Row]:
    """The right pane, words only, each row only when it has something to say: the status slot (`status_slot`: what
    the page cannot show itself), how far the page filling in is, the status line, the indicator's lines on the pages
    behind (the backlog, those that went by too fast, those updated since they were seen: `side_model`), where the
    translator runs. The window's words name no key here (`panes.without_keys`: every key is the viewer's)."""
    from . import status_slot

    rows: list[pn.Row] = []
    side = getattr(app, "_side", None)
    shown = getattr(getattr(side, "slot", None), "shown", None)
    want = shown[0] if shown else None
    slot = pn.without_keys(status_slot.slot_text(want[0])) if want else ""
    if slot:
        rows.append(pn.Row("", slot, "text", warn=bool(want and want[1])))
    fill = getattr(app, "_fill", None)
    if fill is not None and fill.final is None:
        total = sum(1 for s in fill.states if s != "skipped")
        if total:
            rows.append(pn.Row("", _("This page: {done} of {total} lines").format(done=fill.filled, total=total),
                               "text"))
    status = pn.without_keys(str(_get(getattr(app, "status_var", None), "") or "").strip())
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
            if counts["updated"]:
                rows.append(pn.Row("", _("{n} updated since you saw them.").format(n=counts["updated"]), "text"))
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
    width = pn.width_for(rows, language, dpi, room, fill=side == "right")
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
    """The clicks on the left pane acted on, then both panes handed to the see-through window as they are to be: on
    the ground at the capture area's outer edges, beside the page at the last rest, or hidden (no page on a flat
    ground yet, no room, the right one switched off)."""
    over = getattr(app, "_see_through", None)
    if over is None:
        return
    for side, x, y, _t in over.take_clicks():
        if pane_click(app, side, x, y) == "quit":
            return  # (the window has gone)
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
    right = _picture(app, "right", right_rows(app), room_right, language, dpi, scheme) if indicators_on(app) else None
    box_left, box_right = pn.place(size, page, band, left.size if left else None, right.size if right else None, dpi,
                                   columns)
    for side, picture, box in (("left", left, box_left), ("right", right, box_right)):
        memo = app._see_pane_memo.get(side)
        if memo is not None:
            app._see_pane_memo[side] = (memo[0], memo[1], box if picture is not None else None)
    over.set_panes((left.bgra, box_left) if left is not None and box_left is not None else None,
                   (right.bgra, box_right) if right is not None and box_right is not None else None)


def pane_click(app: Any, side: str, x: int, y: int) -> str:
    """A click on the pane *side* at (*x*, *y*) of its picture as last handed over: the control there acted on; its
    name ("" for none)."""
    memo = app._see_pane_memo.get(side) if side == "left" else None
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
    language whose model is not there is offered in a dialog of the window's, which is shown first."""
    picking, app._see_language = getattr(app, "_see_language", None), None
    if picking is None:
        return
    language = picking[0]
    if language == str(_get(getattr(app, "lang_var", None), "") or ""):
        return
    plan = getattr(app, "_plan", None)
    try:
        offered = plan is not None and plan(language) is not None
    except Exception:  # noqa: BLE001 - not known: the window shown, as for an offer
        offered = True
    if offered:
        window_up(app)
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
    try:
        config.write_settings(config.settings_file(app.settings), {"see_through_indicators": value})
    except (config.ConfigError, OSError) as e:
        from .hover import NOT_KEPT

        say = getattr(app, "say", None)
        if say is not None:
            say(NOT_KEPT, error=getattr(e, "strerror", None) or str(e))


def _with_window(step: str) -> Any:
    """An action that opens a dialog of the window's: the window shown first (put aside, its dialogs would not
    show)."""
    def act(app: Any) -> None:
        window_up(app)
        getattr(app, step)()
    return act


def _flip_auto(app: Any) -> None:
    var = getattr(app, "auto_var", None)
    if var is not None:
        var.set(not bool(_get(var, False)))


PANE_ACTIONS: dict[str, Any] = {
    "translate": lambda app: app.translate_now(),
    "again": lambda app: app.translate_now(),  # (the circular arrow: what F5 does in the window, for the page on show)
    "stop": lambda app: app.stop_page(),
    "auto": _flip_auto,
    "language_prev": lambda app: _pick_language(app, -1),
    "language_next": lambda app: _pick_language(app, 1),
    "lettering": toggle,
    "indicators": _flip_indicators,
    "area": _with_window("set_area"),
    "settings": _with_window("open_settings"),
    "window": window_up,
    "quit": lambda app: app._on_close(),
}


# ------------------------------------------------------------------ the patches
def _rgb(image: Image.Image) -> np.ndarray:
    return np.asarray(image if image.mode == "RGB" else image.convert("RGB"))


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
    it changed (made here, on the Tk thread: some 5-10 ms for a full-HD page)."""
    over = getattr(app, "_see_through", None)
    if over is None:
        return
    memo: list[tuple[Image.Image, tuple[Any, ...]]] = app._see_memo
    for original, lettered, final, state in pairs(app):
        known = next((s for img, s in memo if img is original), None)
        if known == state:
            continue
        if original.size != lettered.size:
            continue
        patches = st.make_patches(_rgb(original), _rgb(lettered), margin=px(app, st.MARGIN),
                                  gap=px(app, st.GROUP_PX))
        over.present(id(original), original.size, patches, final)
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


def note_frame(app: Any, image: Image.Image, facts: Any) -> None:
    """A frame just captured of the viewer (`LiveViewMixin._capture_frame`): since when bars lie over the page (and a
    look once they have stayed BAR_WAIT_S: a viewer draws no new frame while they stand still), and the page box of
    the last frame at rest (which tells half a spread) with what the side panes are placed by: the frame's size, the
    steady band's rows (`seethrough.steady_box` of the capture area: where bars never come), the ground's colour
    (none at rest on no flat ground: the panes hide) and the capture area's columns (the panes at its edges)."""
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
        if found.box is not None:
            app._see_rest_box = found.box
            _rgb, area = area_rgb(app, image, facts)
            steady = st.steady_box(image.size, area)
            app._see_ground = (image.size, found.box, (steady[1], steady[3]), found.ground, (area[0], area[2]))
        else:
            app._see_ground = None
        return
    if app._see_bars_since is None:
        app._see_bars_since = time.monotonic()
        try:
            app.after(int(BAR_WAIT_S * 1000) + 30, lambda: _bars_due(app))
        except Exception:  # noqa: BLE001 - no Tk loop (a test)
            pass


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
