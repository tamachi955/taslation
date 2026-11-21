"""The viewer the person chose kept directly under TASlation's window in the order of the windows while TASlation is
the window in front, and a status line when the viewer is hidden wholly and its frames stand still.

Why: a browser that windows hiding what lies under them cover wholly stops drawing (the occlusion tracking of
Chromium and Firefox), and TASlation then gets no new frame of it: no page turned is seen. TASlation's own window
hides nothing so (`constants.WINDOW_ALPHA`), but another program's window that lay over the viewer stays between the
two when the person brings TASlation to the front.

What is done, and only that (`keep_under`, each heartbeat of the window: `live.LiveViewMixin._beat`): the viewer's
window put directly under TASlation's (`capture.keep_viewer_under`: SetWindowPos with SWP_NOACTIVATE - no
activation, no change of the foreground, no key, no click, nothing that turns a page; only the viewer's place in the
order, and then its location change announced as a window event, which a browser's occlusion tracking looks again
at), when a window that could hide some of it lies between the two. A window that lay between is not moved: it
lies under the viewer from then on - one the person laid over a part of the viewer on purpose (a note, a dictionary)
too, unless PARTLY_COVERED_TOO is False: then only when the windows of other programs hide all of it. Topmost windows stay above the viewer, which is never made topmost (under a
topmost TASlation - Always on top, the full screen - it goes to the top of the windows that are not topmost). The
viewer's own dialogs and popups move with it and stay above it; TASlation's own (its dialogs, the panel beside a
bubble, an input method's window) are TASlation's and never counted.

When: only while a window of TASlation's is the window in front (`capture.foreground_owner` "own") - at once when it
came to the front, then every ORDER_EVERY_S while it stays there, should the order change -, at most ORDER_MOST
times in one such spell (another program that puts its window back over the viewer at once is not fought: the line
below says what is left). How the two are told apart: the person bringing another program to the front makes that
program's window the one in front, and from then on nothing is done until TASlation is in front again (that is the
person's choice of order, and so is the viewer in front); a window that came between with no change of the window in
front - shown without activation, put there by its program - is what the spell's later looks catch. Nothing either
while TASlation is minimised, for a viewer minimised (handled as ever: `viewers`), hidden or topmost, while it is
raised for a look (`live.LiveViewMixin._raise_viewer`), nor while its window is given a new size.

The second measure (`covered_line`): when the viewer is hidden wholly - a browser by windows that hide what lies under
them (`capture.fully_covered` with *opaque*), another viewer, seen to draw nothing while covered, by any window - and
its frames stand still (the capture's frame count unchanged) for COVERED_STILL_S, the status line says so, once in such
a spell; the line goes when its spell ends (a frame comes, or the viewer is in sight again) and it is still shown.
Never while TASlation's own window is what the viewer draws nothing behind (`live.LiveViewMixin._set_covered`: its
band and line say what to do then). Nothing is asked of a window but its place, its size and what covers it."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from ..capture import (BROWSER_CLASSES, IS_WINDOWS, foreground_owner, foreground_window, fully_covered,
                       keep_viewer_under, window_class)

LOG = logging.getLogger(__name__)

# Which windows between TASlation's and the viewer's have the viewer put up under TASlation's - one switch, no
# setting, so that both ways can be shown: True, any window that hides some of the viewer (a window the person laid
# over a part of it on purpose - a note, a dictionary - goes under it at each click on TASlation); False, only once
# the windows of other programs that hide what lies under them hide all of it (`capture.fully_covered` with *opaque*:
# what stops a browser drawing), so that one over a part of it stays where the person put it.
PARTLY_COVERED_TOO = True
ORDER_EVERY_S = 0.5  # while TASlation is in front, the order looked at this often (and at once when it came to it)
ORDER_MOST = 5  # the viewer put under TASlation's window at most this many times in one spell of TASlation in front
COVER_EVERY_S = 1.0  # how often the second measure looks whether the viewer is hidden wholly
COVERED_STILL_S = 3.0  # hidden wholly, its frames standing still this long: the status line says so
COVERED_KEY = "The viewer is hidden behind other windows and has stopped drawing: move them off it, or bring the viewer to the front."


@dataclass
class OrderState:
    """What the window keeps between two heartbeats: whether TASlation was in front at the last one, when the order
    was looked at and how often the viewer was put under it in this spell (and in all), and of the second measure when
    the viewer was found hidden wholly with its frames standing still since, the frame count then, and whether the
    line was said in this spell."""

    front: bool = False
    looked: float = float("-inf")
    placed: int = 0
    total: int = 0
    spells: int = 0
    last: str = ""  # what `capture.keep_viewer_under` said last
    cover_looked: float = float("-inf")
    cover_since: float | None = None
    cover_seq: int | None = None
    said: bool = False


def state_of(window: Any) -> OrderState:
    state = getattr(window, "_order_state", None)
    if state is None:
        state = OrderState()
        try:
            window._order_state = state
        except AttributeError:
            pass
    return state


def _viewer(window: Any) -> int:
    return int(getattr(getattr(window, "selected", None), "hwnd", 0) or 0)


def _own(window: Any) -> int:
    own = getattr(window, "_own_hwnd", None)
    try:
        return int(own() or 0) if callable(own) else 0
    except Exception:  # noqa: BLE001 - no handle: nothing is done
        return 0


def _busy_with_the_viewer(window: Any) -> bool:
    """The viewer raised for a look, or its window being given a new size: its place is the window's own business."""
    if getattr(window, "_raised", None) is not None:
        return True
    resizing = getattr(window, "_resizing", None)
    try:
        return bool(resizing()) if callable(resizing) else False
    except Exception:  # noqa: BLE001
        return False


def keep_under(window: Any, now: float | None = None) -> str:
    """(each heartbeat) The viewer put directly under TASlation's window when it should be (see the module's
    docstring). What `capture.keep_viewer_under` said ("placed", "", or why nothing was done), or "" when it was not
    asked."""
    state = state_of(window)
    viewer, own = _viewer(window), _own(window)
    if not IS_WINDOWS or not viewer or not own:
        state.front = False
        return ""
    now = time.monotonic() if now is None else now
    if foreground_owner(foreground_window(), viewer) != "own":
        state.front = False  # (the person went to another program, or to the viewer: the order is theirs)
        return ""
    if not state.front:  # (TASlation came to the front: a spell of its own, looked at at once)
        state.front, state.placed, state.looked = True, 0, float("-inf")
        state.spells += 1
    if now - state.looked < ORDER_EVERY_S - 1e-6 or state.placed >= ORDER_MOST or _busy_with_the_viewer(window):
        return ""
    state.looked = now
    between: list[int] = []
    try:
        if not PARTLY_COVERED_TOO and not fully_covered(viewer, opaque=True):
            what = "partly"  # (some of it in sight: a window over a part of it stays where the person put it)
        else:
            what = keep_viewer_under(viewer, own, between=between)
    except Exception:  # noqa: BLE001 - the heartbeat goes on
        LOG.exception("the viewer could not be put under TASlation's window")
        return ""
    if what == "placed":
        state.placed += 1
        state.total += 1
        LOG.info("window order: the viewer put directly under TASlation's window (%d in this spell, %d in all; the "
                 "window(s) between, now under it: %s)", state.placed, state.total, _kinds(between))
        if state.placed >= ORDER_MOST:
            LOG.info("window order: a window comes back between them at once; left as it is until TASlation comes to "
                     "the front again")
    elif what in ("refused",) and state.last != what:
        LOG.warning("window order: Windows did not put the viewer under TASlation's window (%s)", what)
    state.last = what
    return what


def _kinds(hwnds: list[int]) -> str:
    """The window classes of *hwnds* for the log (a class names a kind of window, never what it shows: no title)."""
    try:
        return ", ".join(window_class(h)[:40] or "?" for h in hwnds[:8]) + (" ..." if len(hwnds) > 8 else "")
    except Exception:  # noqa: BLE001 - only the log's
        return f"{len(hwnds)}"


def hidden_wholly(window: Any, viewer: int) -> bool:
    """Whether the viewer *viewer* is hidden wholly so that it draws nothing: a browser by windows that hide what lies
    under them (its published rule), another viewer by any window when it was seen to draw nothing while covered
    (`live.LiveViewMixin._draws_covered`); a viewer that draws so, or one not known yet, never."""
    if window_class(viewer) in BROWSER_CLASSES:
        return fully_covered(viewer, opaque=True)
    draws = getattr(window, "_draws_covered", None)
    try:
        if not callable(draws) or draws(viewer) is not False:
            return False
    except Exception:  # noqa: BLE001
        return False
    return fully_covered(viewer)


def covered_line(window: Any, now: float | None = None) -> bool:
    """(each heartbeat) The second measure (see the module's docstring): the status line once the viewer has been
    hidden wholly with its frames standing still for COVERED_STILL_S, once a spell; taken back as the spell ends while
    it is still shown. Whether it was said now."""
    state = state_of(window)
    viewer = _viewer(window)
    now = time.monotonic() if now is None else now
    if not IS_WINDOWS or not viewer or getattr(window, "_covered", False):  # (TASlation's own covering: its band says it)
        _end_cover(window, state)
        return False
    if now - state.cover_looked < COVER_EVERY_S - 1e-6:
        return False
    state.cover_looked = now
    try:
        hidden = hidden_wholly(window, viewer)
        count = window._frame_count() if hidden else None
    except Exception:  # noqa: BLE001 - not known: nothing said
        hidden, count = False, None
    if not hidden or count is None:  # (in sight, or no frame count to tell frames that stand still by)
        _end_cover(window, state)
        return False
    if state.cover_since is None or count != state.cover_seq:  # (hidden from now on, or a frame came: counted anew)
        if state.cover_since is not None:
            _end_cover(window, state)
        state.cover_since, state.cover_seq = now, count
        return False
    if state.said or now - state.cover_since < COVERED_STILL_S - 1e-6:
        return False
    state.said = True
    LOG.info("the viewer is hidden wholly and its frames stand still (%.1f s): the reader is told", now - state.cover_since)
    window.say("The viewer is hidden behind other windows and has stopped drawing: move them off it, or bring the viewer to the front.")  # (COVERED_KEY)
    return True


def _end_cover(window: Any, state: OrderState) -> None:
    """A spell of the viewer hidden wholly is over: its line taken back while it is still the one shown."""
    if state.said and getattr(window, "_status_key", None) == COVERED_KEY:
        try:
            window.status("")
        except Exception:  # noqa: BLE001
            pass
    state.cover_since, state.cover_seq, state.said = None, None, False


def beat(window: Any, now: float | None = None) -> None:
    """(`live.LiveViewMixin._beat`) Both, never in the heartbeat's way."""
    now = time.monotonic() if now is None else now
    try:
        keep_under(window, now)
        covered_line(window, now)
    except Exception:  # noqa: BLE001 - the heartbeat goes on
        LOG.exception("window order: a look failed")
