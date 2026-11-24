"""What the right side pane says of the screens turned past in normal reading (a part of `app.App`): how far the work on
each is, from the engine's events (`backlog`, each with ``reading`` True, by one way only: `backlog.reading_event`
from `JobsMixin._handle_event` to the ``_on_reading_<kind>`` handlers here):

* ``page_stage`` {seq, fingerprint, stage "read" or "translate", state[, thumb][, into]} - a screen and one of its
  stages (`side_model.SideModel.update`; read "merged" {into}: a page that went by was the screen *into*);
* ``page_on_show`` {seq} - the screen the viewer shows (None: one not told yet, or none of the book's);
* ``backlog`` {pages, lines, paused, dropped} - the work still to do on the screens behind; *dropped* the screens
  that went by too fast, not caught or done since, or True: the backlog was dropped (another book, another viewer
  window) - everything goes, and the screens are numbered from 1 again.

The right pane's lines (`seethrough.right_rows`) read the model's counts and its backlog, and the Reader's status
slot (`status_slot`). The window's other parts reach all this through the few functions here (`before`, `after`,
`clear`), which do nothing before `_build_side` made it. Memory only; no page is ever shown from memory, and nothing
goes to the viewer."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from . import status_slot
from .side_model import SideModel

LOG = logging.getLogger(__name__)


@dataclass
class SideState:
    """The screens and the status slot, memory only."""

    model: SideModel = field(default_factory=SideModel)
    slot: status_slot.SlotState = field(default_factory=status_slot.SlotState)
    now: Any = time.monotonic


def state(window: Any) -> SideState | None:
    return getattr(window, "_side", None)


def clear(window: Any) -> None:
    """Everything of the screens forgotten: another book, another viewer window."""
    st = state(window)
    if st is not None:
        st.model.clear()


# ------------------------------------------------------------------ the engine's events
def on_stage(window: Any, data: dict[str, Any]) -> None:
    """``page_stage`` of normal reading: the screen's cell (a new one at its place)."""
    st = state(window)
    if st is None:
        return
    model = st.model
    if model.renumbered(data.get("seq"), data.get("fingerprint", ""), _within(window)):
        clear(window)  # (the engine numbers another book's screens from 1 again)
    model.update(data.get("seq"), data.get("fingerprint", ""), data.get("stage"), data.get("state"))


def on_show(window: Any, data: dict[str, Any]) -> None:
    """``page_on_show``: the screen on show (None: a screen not told yet, or none of the book's)."""
    st = state(window)
    if st is not None:
        st.model.show(data.get("seq"))


def on_backlog(window: Any, data: dict[str, Any]) -> None:
    """``backlog``: its totals (*dropped*: the screens that went by too fast, not caught or done since); *dropped*
    True - the backlog was dropped (another book, another viewer window): everything goes, and the screens are
    numbered from 1 again."""
    st = state(window)
    if st is None:
        return
    if data.get("dropped") is True:
        clear(window)
    st.model.set_backlog(data.get("pages"), data.get("lines"), data.get("paused"), data.get("dropped"), st.now())


def before(window: Any, kind: str, data: dict[str, Any]) -> Any:
    """What an event needs noted before the window handles it: the frame of the page job an error ends."""
    try:
        if state(window) is not None and kind == "error":
            return getattr(window, "_job_frame", None)
    except Exception:  # noqa: BLE001 - never in the way of the event
        pass
    return None


def after(window: Any, kind: str, data: dict[str, Any], noted: Any) -> None:
    """An event the window has handled, as the slot takes it: a page job's error, a result. (Normal reading's own
    events come by one way only, the ``_on_reading_<kind>`` handlers.)"""
    st = state(window)
    if st is None:
        return
    try:
        if kind == "error" and noted is not None:
            st.slot.error_frame, st.slot.error_at = noted, time.monotonic()
        elif kind == "result":
            result = data.get("result")
            if result is not None and result is getattr(window, "last_result", None):
                st.slot.error_frame = None
                if status_slot.nothing_to_read(result):
                    st.slot.nothing, st.slot.nothing_until = result, time.monotonic() + status_slot.NOTHING_S
    except Exception:  # noqa: BLE001 - the slot never stops the event pump
        pass


def _within(window: Any) -> int:
    try:
        return int(getattr(getattr(window, "settings", None), "fingerprint_max_distance", 0) or 0)
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------ the window's part
def _quietly(handler: Any, window: Any, data: Any) -> None:
    try:
        handler(window, data if isinstance(data, dict) else {})
    except Exception as e:  # noqa: BLE001 - the indicator never stops the event pump
        LOG.debug("side: an event of normal reading not taken (%s)", type(e).__name__)  # (its kind only)


class SideMixin:
    """The screens and the slot. A part of `app.App` (no `__init__`): `_build_side` makes its state once, kept across a
    language switch."""

    def _build_side(self) -> None:
        if getattr(self, "_side", None) is None:
            self._side = SideState()
        self._side.slot.shown = None

    # the engine's events of normal reading (``reading`` True), the one way they come: `backlog.reading_event`, from
    # `JobsMixin._handle_event`; never raising into the event pump
    def _on_reading_page_stage(self, data: dict[str, Any]) -> None:
        _quietly(on_stage, self, data)

    def _on_reading_page_on_show(self, data: dict[str, Any]) -> None:
        _quietly(on_show, self, data)

    def _on_reading_backlog(self, data: dict[str, Any]) -> None:
        _quietly(on_backlog, self, data)
