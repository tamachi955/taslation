"""The viewer the person chose kept directly under TASlation's windows in the order of the windows while a window of
TASlation's (a dialog, the Menu) is the window in front.

Why: a browser that windows hiding what lies under them cover wholly stops drawing (the occlusion tracking of
Chromium and Firefox), and TASlation then gets no new frame of it: no page turned is seen. TASlation's see-through
windows hide nothing so, but another program's window that lay over the viewer stays between the
two when the person brings TASlation to the front.

What is done, and only that (`keep_under`, each heartbeat of the window: `live.LiveViewMixin._beat`): the viewer's
window put directly under TASlation's (`capture.keep_viewer_under`: SetWindowPos with SWP_NOACTIVATE - no
activation, no change of the foreground, no key, no click, nothing that turns a page; only the viewer's place in the
order, and then its location change announced as a window event, which a browser's occlusion tracking looks again
at), when a window that could hide some of it lies between the two. A window that lay between is not moved: it
lies under the viewer from then on - one the person laid over a part of the viewer on purpose (a note, a dictionary)
too, unless PARTLY_COVERED_TOO is False: then only when the windows of other programs hide all of it. Topmost windows
stay above the viewer, which is never made topmost. The viewer's own dialogs and popups move with it and stay above
it; TASlation's own (its dialogs, the see-through window and the panes, an input method's window) are TASlation's and
never counted.

When: only while a window of TASlation's is the window in front (`capture.foreground_owner` "own") - at once when it
came to the front, then every ORDER_EVERY_S while it stays there, should the order change -, at most ORDER_MOST
times in one such spell (another program that puts its window back over the viewer at once is not fought: the line
below says what is left). How the two are told apart: the person bringing another program to the front makes that
program's window the one in front, and from then on nothing is done until TASlation is in front again (that is the
person's choice of order, and so is the viewer in front); a window that came between with no change of the window in
front - shown without activation, put there by its program - is what the spell's later looks catch. Nothing either
while TASlation is minimised, for a viewer minimised (handled as ever: `viewers`), hidden or topmost, nor while it is
raised for a look (`live.LiveViewMixin._raise_viewer`). Nothing is asked of a window but its place and what covers
it."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from ..capture import IS_WINDOWS, foreground_owner, foreground_window, fully_covered, keep_viewer_under, window_class, window_pid

LOG = logging.getLogger(__name__)

# Which windows between TASlation's and the viewer's have the viewer put up under TASlation's - one switch, no
# setting, so that both ways can be shown: True, any window that hides some of the viewer (a window the person laid
# over a part of it on purpose - a note, a dictionary - goes under it at each click on TASlation); False, only once
# the windows of other programs that hide what lies under them hide all of it (`capture.fully_covered` with *opaque*:
# what stops a browser drawing), so that one over a part of it stays where the person put it.
PARTLY_COVERED_TOO = True
ORDER_EVERY_S = 0.5  # while TASlation is in front, the order looked at this often (and at once when it came to it)
ORDER_MOST = 5  # the viewer put under TASlation's window at most this many times in one spell of TASlation in front


@dataclass
class OrderState:
    """What the window keeps between two heartbeats: whether TASlation was in front at the last one, when the order
    was looked at and how often the viewer was put under it in this spell (and in all)."""

    front: bool = False
    looked: float = float("-inf")
    placed: int = 0
    total: int = 0
    spells: int = 0
    last: str = ""  # what `capture.keep_viewer_under` said last


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
    """The viewer raised for a look: its place is the window's own business (TASlation never gives the viewer's window
    a new size)."""
    return getattr(window, "_raised", None) is not None


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
                 "window(s) between, now under it: %s)", state.placed, state.total, _kinds(between, viewer))
        if state.placed >= ORDER_MOST:
            LOG.info("window order: a window comes back between them at once; left as it is until TASlation comes to "
                     "the front again")
    elif what in ("refused",) and state.last != what:
        LOG.warning("window order: Windows did not put the viewer under TASlation's window (%s)", what)
    state.last = what
    return what


def _kinds(hwnds: list[int], viewer: int = 0) -> str:
    """The window classes of *hwnds* for the log (a class names a kind of window, never what it shows: no title), each
    of the viewer's own program said so (another window of it, not one the viewer owns)."""
    try:
        program = window_pid(viewer) if viewer else 0
        return ", ".join((window_class(h)[:40] or "?") + (" (the viewer's program)" if program and window_pid(h) == program
                                                          else "") for h in hwnds[:8]) + (" ..." if len(hwnds) > 8 else "")
    except Exception:  # noqa: BLE001 - only the log's
        return f"{len(hwnds)}"


def beat(window: Any, now: float | None = None) -> None:
    """(`live.LiveViewMixin._beat`) `keep_under`, never in the heartbeat's way."""
    now = time.monotonic() if now is None else now
    try:
        keep_under(window, now)
    except Exception:  # noqa: BLE001 - the heartbeat goes on
        LOG.exception("window order: a look failed")
