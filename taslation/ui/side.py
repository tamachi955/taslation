"""The indicator beside the page in the window (a part of `app.App`): the screens turned past in normal reading and how
far the work on each is, from the engine's events (`backlog`, each with ``reading`` True, by one way only:
`backlog.reading_event` from `JobsMixin._handle_event` to the ``_on_reading_<kind>`` handlers here); it is there
whenever its setting has it (``side_indicator``):

* ``page_stage`` {seq, fingerprint, stage "read" or "translate", state[, thumb][, into]} - a screen and one of its
  stages (`side_model.SideModel.update`; the thumbnail, at most 96 px tall, with its first event - none for a page
  that only went by -, kept in memory only; read "merged" {into}: a page that went by was the screen *into*);
* ``page_on_show`` {seq} - the screen the viewer shows (None: one not told yet, or none of the book's): outlined,
  kept in view;
* ``backlog`` {pages, lines, paused, dropped} - the work still to do on the screens behind; *dropped* the screens
  that went by too fast, not caught or done since, or True: the backlog was dropped (another book, another viewer
  window) - everything goes, and the screens are numbered from 1 again.

`SideView` draws it in the exit-side margin of the page area (`side_model.side_layout`), the picture kept clear of
that side where the margin is too narrow even for the rail (`side_model.room_kept`, through
`ImageCanvas.side_room_of`). A click on a thumbnail says in the status line how to read that screen - turn to it in
the viewer - and does nothing else (`_pick_screen`): reading is on the viewer; no page from memory is ever shown, and
nothing goes to the viewer.

It also keeps what the person saw lettered on each screen (`seen.Seen`, memory only) for the updated mark: the
diamond on a screen whose words changed since, and, when it comes on show again, corner brackets on its changed
bubbles for their read time (`on_picture`, from `LiveViewMixin._redisplay`); and the Reader's status slot
(`status_slot`). The window's other parts reach all this through the few functions here (`before`, `after`,
`on_picture`, `clear`), which do nothing on a window without the indicator (`_build_side` makes it)."""

from __future__ import annotations

import logging
import time
import tkinter as tk
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from . import status_slot
from .seen import Seen, words
from .side_model import SETTINGS, SideLayout, SideModel, room_kept, screen_tip, side_layout
from .side_view import SideView

LOG = logging.getLogger(__name__)
HOVER_MS = 450  # the pointer resting this long on a bracketed bubble counts as reading it
# on the right of the page the indicator starts this far down: the busy badge's place, the full screen's close button's
TOP_CLEAR = 48
# the window's events after which the book's cache may hold other words (a translation stage of normal reading moving
# looks too: `on_stage`)
CACHE_EVENTS = ("names_applied", "find", "result", "translate_done", "renamed")


@dataclass
class SideState:
    """The window's indicator, memory only: the screens, what was seen of them, the status slot, the widgets."""

    model: SideModel = field(default_factory=SideModel)
    seen: Seen = field(default_factory=Seen)
    slot: status_slot.SlotState = field(default_factory=status_slot.SlotState)
    cached: dict[int, Counter] = field(default_factory=dict)  # a screen's cached words when last on show
    view: SideView | None = None
    slot_label: Any = None
    hover_job: str | None = None
    hover_box: tuple[int, int, int, int] | None = None
    read_job: str | None = None
    marks_job: str | None = None
    shown_frame: Any = None  # the viewer's frame when the screen on show was told (`on_show`)
    now: Any = time.monotonic


def state(window: Any) -> SideState | None:
    return getattr(window, "_side", None)


def setting(window: Any) -> str:
    value = str(getattr(getattr(window, "settings", None), "side_indicator", "column") or "column")
    return value if value in SETTINGS else "column"


def rtl(window: Any) -> bool:
    try:
        return bool(getattr(getattr(window, "pipeline", None), "rtl", True))
    except Exception:  # noqa: BLE001 - the book's direction not known: right to left, as most manga
        return True


def side_room(window: Any, part: tuple[int, int], size: tuple[int, int]) -> tuple[int, int]:
    """The canvas pixels kept clear left and right of the picture (`ImageCanvas.side_room_of`)."""
    canvas = window.canvas
    return room_kept(setting(window), part, size, canvas.inset, canvas.enlarge, rtl(window))


def top_clear(window: Any, side: str) -> int:
    if side != "right":
        return 0
    if getattr(window, "reading", False) or status_slot.badge_allowed(window):
        return TOP_CLEAR
    return 0


def place(window: Any) -> None:
    """The indicator where it goes beside the picture drawn now (after every drawing of the page area)."""
    st = state(window)
    if st is None or st.view is None:
        return
    canvas = window.canvas
    try:
        w, h = canvas.winfo_width(), canvas.winfo_height()
        shown = canvas._shown if getattr(canvas, "_image", None) is not None and not canvas.message else None
        side = "left" if rtl(window) else "right"
        layout = side_layout(setting(window), (w, h), shown, rtl(window),
                             bool(getattr(window, "reading", False)), top_clear(window, side)) \
            if w >= 2 and h >= 2 else SideLayout()
        canvas.slot_side = side
        st.view.place_at(layout, str(canvas.cget("bg")))
    except tk.TclError:
        pass


def clear(window: Any) -> None:
    """Everything of the indicator forgotten: another book, another viewer window."""
    st = state(window)
    if st is None:
        return
    st.model.clear()
    st.seen.clear()
    st.cached.clear()
    st.shown_frame = None
    if st.view is not None:
        try:
            st.view.redraw()
        except tk.TclError:
            pass
    canvas = getattr(window, "canvas", None)
    if canvas is not None and getattr(canvas, "brackets", None):
        canvas.set_brackets([])


# ------------------------------------------------------------------ the engine's events
def on_stage(window: Any, data: dict[str, Any]) -> None:
    """``page_stage`` of normal reading: the screen's cell (a new one at its place), the cache's words looked at again
    once a translation stage moved."""
    st = state(window)
    if st is None:
        return
    model = st.model
    within = _within(window)
    if model.renumbered(data.get("seq"), data.get("fingerprint", ""), within):
        clear(window)  # (the engine numbers another book's screens from 1 again)
    new = model.update(data.get("seq"), data.get("fingerprint", ""), data.get("thumb"), data.get("stage"),
                       data.get("state"))
    try:
        seq = int(data.get("seq"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return
    if seq not in model.screens:
        st.seen.forget(seq)
    if st.view is not None:
        try:
            st.view.screen_changed(seq, new)
        except tk.TclError:
            pass
    if data.get("stage") == "translate":
        marks_later(window)


def on_show(window: Any, data: dict[str, Any]) -> None:
    """``page_on_show``: the screen on show outlined and kept in view (None: a screen not told yet, or none of the
    book's). The engine tells it once the frame is confirmed, after the page area showed that frame - and a page from
    the cache, lettered then - so the viewer's frame now is the screen's (`shown_frame`: until the viewer shows
    another, what the page area shows is that screen's), and what it shows lettered is looked at now."""
    st = state(window)
    if st is None or not st.model.show(data.get("seq")):
        return
    st.shown_frame = getattr(window, "_live", None) if st.model.on_show is not None else None
    if st.view is not None:
        try:
            st.view.show(st.model.on_show)
        except tk.TclError:
            pass
    look_now(window)


def look_now(window: Any) -> None:
    """What the page area shows of the screen on show looked at without drawing the page again (`on_picture`), its
    brackets drawn or taken away."""
    canvas = getattr(window, "canvas", None)
    if canvas is None:
        return
    boxes = on_picture(window, getattr(canvas, "_image", None))
    if boxes != list(getattr(canvas, "brackets", None) or []):
        try:
            canvas.set_brackets(boxes)
        except tk.TclError:
            pass


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
    """An event the window has handled, as the slot and the updated mark take it: a page job's error, a result, an
    event after which the cache's words may have changed. (Normal reading's own events come by one way only, the
    ``_on_reading_<kind>`` handlers.)"""
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
        if kind in CACHE_EVENTS:
            marks_later(window)
    except Exception:  # noqa: BLE001 - the indicator never stops the event pump
        pass


def _within(window: Any) -> int:
    try:
        return int(getattr(getattr(window, "settings", None), "fingerprint_max_distance", 0) or 0)
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------ the updated mark
Bubbles = list[tuple[tuple[int, int, int, int], str]]


def shown_words(window: Any) -> tuple[Bubbles, tuple[int, int], tuple[str, ...]] | None:
    """The bubbles lettered on the page on show and their words ("" for one showing its Japanese), the picture's size
    and its fingerprints; None while no lettering of TASlation's is on show (the original, the translation under
    the pointer only, the viewer's frame as it is, a page translated again over its old lettering)."""
    from . import hover

    if window.original_var.get() or hover.reverse_on(window):
        return None
    fill = getattr(window, "_fill", None)
    if fill is not None and window._fill_on_show():
        if fill.base is not fill.frame or not fill.texts:
            return None
        bubbles = []
        for i, box in enumerate(fill.boxes):
            if i in fill.texts:
                bubbles.append((tuple(box), fill.texts[i]))
            elif fill.states[i] in ("found", "read"):
                bubbles.append((tuple(box), ""))
        return bubbles, fill.frame.size, ()
    result = getattr(window, "last_result", None)
    if result is not None and window._result_on_show():
        bubbles = [((r.x0, r.y0, r.x1, r.y1), r.translated_text if r.status == "translated" else "")
                   for r in result.regions if r.status in ("translated", "untranslated")]
        return bubbles, result.original.size, tuple(result.fingerprints)
    return None


def _same_screen(window: Any, seq: int, fingerprints: tuple[str, ...]) -> bool:
    """Whether a page with *fingerprints* is the screen *seq* (no fingerprint to tell: taken as it)."""
    screen = state(window).model.screens.get(seq)
    if screen is None or not screen.fingerprint or not fingerprints:
        return True
    from .. import fingerprint as fp

    try:
        return min(fp.hamming(screen.fingerprint, f) for f in fingerprints) <= _within(window)
    except (TypeError, ValueError):
        return screen.fingerprint in fingerprints


def turned_away(window: Any, st: SideState) -> bool:
    """Whether the viewer's frame now is of another page than the frame on show when the screen on show was told
    (`shown_frame`; `LiveViewMixin._shows_page`: a soft picture and its sharp one are the same page). A screen is told
    on show only once its frame is confirmed: until then, what the page area shows is not the screen told last."""
    frame, live = st.shown_frame, getattr(window, "_live", None)
    if frame is None or live is None or live is frame:
        return False
    try:
        return not window._shows_page(live, frame)
    except Exception:  # noqa: BLE001 - not known: taken as the same page
        return False


def on_picture(window: Any, image: Any) -> list[tuple[int, int, int, int]]:
    """The page area is drawn again (`LiveViewMixin._redisplay`): what the person sees lettered on the screen on show
    taken in (`Seen.look`), its diamond set or gone, and the brackets to draw on its changed bubbles (image pixels;
    none on a window without the indicator)."""
    st = state(window)
    if st is None:
        return []
    try:
        seq = st.model.on_show
        if seq is not None and turned_away(window, st):
            seq = None  # (the viewer shows another frame: the next screen is not told yet - a watch of this one ends)
        got = shown_words(window) if seq is not None and image is not None else None
        if got is not None and not _same_screen(window, seq, got[2]):
            got = None
        bubbles, size, fps = got if got is not None else (None, (1, 1), ())
        before = st.seen.watch.seq if st.seen.watch is not None else None
        updated, _changed = st.seen.look(seq, bubbles, size, st.now(), fps)
        screen = st.model.screens.get(seq) if seq is not None else None
        if updated is not None and screen is not None:
            if before != seq:
                st.cached[seq] = cached_words(window, seq)
            if screen.updated != updated:
                screen.updated = updated
                _marks_again(st)
            watch = st.seen.watch
            if watch is not None and watch.due is not None and st.read_job is None:
                _read_later(window, watch.due - st.now())
        if image is None or st.seen.watch is None or not st.seen.watch.brackets:
            return []
        return st.seen.brackets(image.size)
    except Exception:  # noqa: BLE001 - the page is drawn whatever happens here
        return []


def _marks_again(st: SideState) -> None:
    if st.view is not None:
        try:
            st.view.redraw_marks()
        except tk.TclError:
            pass


def _read_later(window: Any, seconds: float) -> None:
    st = state(window)

    def due() -> None:
        st.read_job = None
        watch = st.seen.watch
        if watch is None or watch.due is None:
            return
        if not st.seen.due(st.now()):
            _read_later(window, watch.due - st.now())
            return
        read(window)

    try:
        st.read_job = window.after(max(1, int(seconds * 1000)), due)
    except (tk.TclError, AttributeError):
        st.read_job = None


def read(window: Any) -> None:
    """The screen on show read: its brackets and its diamond go."""
    st = state(window)
    seq = st.seen.acknowledge()
    if seq is None:
        return
    screen = st.model.screens.get(seq)
    if screen is not None and screen.updated:
        screen.updated = False
        _marks_again(st)
    window.canvas.set_brackets([])


def hover_moved(window: Any, event: tk.Event) -> None:
    """The pointer over the page: resting on a bracketed bubble for `HOVER_MS` counts as reading it."""
    st = state(window)
    if st is None or st.seen.watch is None or not st.seen.watch.brackets:
        return
    canvas = window.canvas
    image = getattr(canvas, "_image", None)
    if image is None:
        return
    x, y = canvas.to_image_coords(event.x, event.y)
    box = next((b for b in st.seen.brackets(image.size) if b[0] <= x <= b[2] and b[1] <= y <= b[3]), None)
    if box == st.hover_box:
        return
    hover_left(window)
    if box is None:
        return
    st.hover_box = box

    def rested() -> None:
        st.hover_job = None
        if st.hover_box != box or st.seen.watch is None:
            return
        size = canvas._image.size if canvas._image is not None else image.size
        if st.seen.hovered(box, size):
            screen = st.model.screens.get(st.seen.watch.seq)
            if screen is not None and screen.updated:
                screen.updated = False
                _marks_again(st)
        canvas.set_brackets(st.seen.brackets(size))

    try:
        st.hover_job = window.after(HOVER_MS, rested)
    except tk.TclError:
        st.hover_job = None


def hover_left(window: Any) -> None:
    st = state(window)
    if st is None:
        return
    if st.hover_job is not None:
        try:
            window.after_cancel(st.hover_job)
        except tk.TclError:
            pass
    st.hover_job = st.hover_box = None


def cached_words(window: Any, seq: int) -> Counter:
    """The words the cache holds for the screen *seq* (its fingerprints as seen, else as the engine told them)."""
    st = state(window)
    cache = getattr(getattr(window, "pipeline", None), "cache", None)
    screen = st.model.screens.get(seq)
    shown = st.seen.shown.get(seq)
    fps = (shown.fingerprints if shown is not None else ()) or ((screen.fingerprint,) if screen is not None and
                                                                 screen.fingerprint else ())
    if cache is None or not fps:
        return Counter()
    within = _within(window)
    texts: Counter = Counter()
    by_fp = {page.fingerprint: page for page in list(cache.pages)}
    for f in fps:
        page = by_fp.get(f)
        if page is None and within:
            hit = cache.lookup(f, 0.0, within)
            page = hit[0] if hit is not None else None
        if page is not None:
            texts.update(w for w in (words(b.text) for b in page.bubbles) if w)
    return texts


def marks_later(window: Any) -> None:
    """The screens' words in the cache looked at again, once for the events that came together."""
    st = state(window)
    if st is None or st.marks_job is not None:
        return

    def due() -> None:
        st.marks_job = None
        mark_from_cache(window)

    try:
        st.marks_job = window.after_idle(due)
    except (tk.TclError, AttributeError):
        st.marks_job = None


def mark_from_cache(window: Any) -> None:
    """Each screen seen lettered, not on show, whose words in the cache changed since it was on show with some the
    person has not seen: its diamond. (A mark goes only once the screen is read: `read`, `hover_moved`.)"""
    st = state(window)
    if st is None or getattr(getattr(window, "pipeline", None), "cache", None) is None:
        return
    watched = st.seen.watch.seq if st.seen.watch is not None else None
    changed = False
    for seq in list(st.seen.shown):
        screen = st.model.screens.get(seq)
        if screen is None:
            continue
        now = cached_words(window, seq)
        if seq == watched:  # on show: seen as it changes
            st.cached[seq] = now
            continue
        if screen.updated:
            continue
        then = st.cached.get(seq, Counter())
        if st.seen.changed_in_cache(seq, (now - then).elements()):
            screen.updated = True
            changed = True
    if changed:
        _marks_again(st)


# ------------------------------------------------------------------ the window's part
def _quietly(handler: Any, window: Any, data: Any) -> None:
    try:
        handler(window, data if isinstance(data, dict) else {})
    except Exception as e:  # noqa: BLE001 - the indicator never stops the event pump
        LOG.debug("side: an event of normal reading not taken (%s)", type(e).__name__)  # (its kind only)


class SideMixin:
    """The indicator in the window. A part of `app.App` (no `__init__`): `_build_side` makes its widgets, again after
    a language switch, keeping what it knows."""

    def _build_side(self) -> None:
        if getattr(self, "_side", None) is None:
            self._side = SideState()
        st = self._side
        st.view = SideView(self.canvas, st.model, self._pick_screen, str(self.canvas.cget("bg")),
                           now=lambda: st.now())
        st.read_job = st.hover_job = st.marks_job = None  # (the widgets they ran on are gone)
        st.hover_box = None
        st.slot.shown = None
        self.canvas.side_room_of = lambda part, size: side_room(self, part, size)
        self.canvas.on_drawn = lambda: place(self)
        self.canvas.badge_allowed = lambda: status_slot.badge_allowed(self)
        self.canvas.bind("<Motion>", lambda e: hover_moved(self, e), add="+")
        self.canvas.bind("<Leave>", lambda _e: hover_left(self), add="+")
        st.slot_label = status_slot.SlotLabel(self.status_bar)

    # the engine's events of normal reading (``reading`` True), the one way they come: `backlog.reading_event`, from
    # `JobsMixin._handle_event`; never raising into the event pump
    def _on_reading_page_stage(self, data: dict[str, Any]) -> None:
        _quietly(on_stage, self, data)

    def _on_reading_page_on_show(self, data: dict[str, Any]) -> None:
        _quietly(on_show, self, data)

    def _on_reading_backlog(self, data: dict[str, Any]) -> None:
        _quietly(on_backlog, self, data)

    def _pick_screen(self, seq: int) -> None:
        """A click on a screen of the indicator: the status line says how to read it - in the viewer, where
        TASlation shows the translation over it (one that went by: turn back to it there). Nothing else happens: the
        page area keeps the viewer's page, and nothing goes to the viewer."""
        model = self._side.model
        self.status(lambda: screen_tip(model, seq))

    def _side_setting_changed(self) -> None:
        """The setting changed: the page drawn again with the room it keeps, the indicator in its new form."""
        self._redisplay()
        place(self)
