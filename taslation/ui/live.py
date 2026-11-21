"""The viewer live on the page: each frame captured (`_capture`, where the page panel is found), the picture shown
(the latest frame, the translated page laid over it while the viewer shows that page, a page filling in), the
viewer hidden behind TASlation, and Auto following the page turns.

How the viewer is followed is `Settings.follow`. With "poll" its frame is captured every auto_interval_ms (`_tick`).
With "events" (Windows; "poll" whenever the hooks cannot be had) it is captured only when there is a reason to:

* after TASlation's own operations on it - a key passed on (`reading.forward_key`), a click passed on - the frame is
  followed at FOLLOW_STEP_MS until it changes, then until it settles (two frames settle_ms apart alike, and none
  sharper), the page is shown and with Auto on started at once, and RECHECK_MS later it is looked at once more: a
  viewer such as a browser-based one may draw a soft picture first, and a sharper frame of the page is read
  again (`_retake`; `_follow_change`, `_step`). A key is pressed for real (the posted one may have been ignored)
  only once page_turn_wait_ms passed without the frame changing at all - a loading indicator or a partial repaint
  says the viewer took it, and a slow viewer is waited for -; when the page then turns twice within TWO_TURNS_S,
  the reader is told how to go back one (`_say_two_turns`). With the viewer's frames counted (`capture.frame_count`)
  the change is captured at each new frame as it comes (`_counted_change`). A viewer that draws nothing while other
  windows hide it is raised for a moment before each key (`_raise_for_key`); whether it does is found out with no
  key as it is chosen (`_learn_covered`), and kept in its profile with how it took the keys (`_note_covered`,
  `_learned`), so that a later session neither raises it nor waits for a posted key for nothing;
* while the viewer itself is in front, so that pages turned there are followed (`_poll`): at each new frame it draws
  (the capture's frame events: `capture.frame_count`, looked at every FRAME_STEP_MS), and every auto_interval_ms; a
  frame that changed is followed at once as an operation's is, until it settles;
* with ``early_start`` (the default) a page the cache does not hold is started on its first changed frame too
  (`_early_start`), with a gate (`pipeline.PageGate`, `Pipeline.page_on_show`). The job reads the page at once, and no
  wait comes before its requests: just before the first one (and before the translator's model is loaded for it) it
  asks whether the frame it read is on show still, and the window answers at its next look at the viewer that finds
  it so - the viewer's frame count unchanged since that frame was captured, or a capture of the same picture: no
  later frame further than SAME_PICTURE from it on the thumbnail, none sharper (`batch.sharper`) - every FRAME_STEP_MS
  with the viewer's frames counted, every FOLLOW_STEP_MS without (`_frame_seen`). The window watches the frame through
  the whole job: one that differs drops it - the request in flight cancelled, everything the job did put back - and
  the page is started again on the new frame, so that nothing lasts from a frame that changed. What the job stores
  lasts once the frame has stayed as it is for KEEP_SETTLES times settle_ms, counted from the look that saw it
  (`Look.at`: before the capture, not after what the window worked out of it): the gate is confirmed then
  (`_early_confirm`), and a page done before that - every line reused, a short page - is shown then and not before
  (`_show_held`); this delays no request. A request may so go out for a frame that changes after it (a soft picture
  read before the sharp one came), and is cancelled with its job. After the confirmation it is as for a page that
  settled: a frame of the page sharper within RECHECK_MS is read again (`_retake`), and another page cancels the job
  as while a job runs (below) - what the job stored lasts, and its lines are reused. A sharper frame takes the
  confirmation back (a sharp picture that reached the window late): nothing of the job on the softer frame lasts -
  put back while the job runs, and once it is done within TAKE_BACK_MS of the confirmation for a viewer seen to draw
  soft first -, put back before the job on the sharp frame begins. Off: the fixed wait;
* a page whose every unit is in the cache is taken on its first changed frame, without the wait for it to settle
  (`_take_at_once`: drawn from the cache, nothing read from the frame), and looked at every FOLLOW_STEP_MS for
  RECHECK_MS after: a viewer that draws a soft picture first has it replaced by the sharp one as soon as that comes
  (`_retake`), and the job on the soft frame, cancelled or done, adds nothing to the cache. Once the viewer has drawn
  a page soft first (`_drew_soft`), a frame that looks soft by its own soft and sharp pictures (`_looks_soft`) is not
  taken so: the sharp frame is, as it comes, so that the lettering goes on the page once, where the sharp picture has
  its bubbles. In translator mode the page is completed from what it reads once its frame has settled
  (`_completion`);
* once when TASlation or the viewer comes back to the front, once the viewer's window or TASlation's own stops moving
  (maximised over the viewer, TASlation may make it stop drawing), at once as well when the viewer's window is given
  another size (`_take_notes`: the capture's first frame of the new size may be all that comes, `wgc.restart`), when
  the viewer's title changes - a browser's is its active tab's -, and, while TASlation is in front, once input over
  the viewer's window stops (Windows scrolls a window under the pointer that is not in front: `_note_input`)
  (`_look`);
* while a page job runs, as while none runs (at each new frame of the viewer in front, at a look): a frame of another
  page goes on the page at once as the viewer draws it - the page being translated, lettered so far, is on show only
  while the viewer shows that page (`_fill_on_show`) -, and is followed until it settles; once it has stayed as it is
  for LEFT_PAGE_MS (the viewer has left the job's page; whether the new picture is final is its own job's gate's
  matter) it cancels the job, is followed on, and is started early on the frame there is - a gate of its own - as soon
  as the worker is free of the job (`_waits_for_worker`); a frame back on the job's page before that letters it again,
  the job never cancelled; a black flash or a spinner over the page changes nothing (`_look_over_job`). A frame of
  another size (the viewer's window resized) is another page so, read by its own size's capture area from the first
  (`_margins_of`): the job's area stays in force for the job alone until it is gone;
* never while neither is in front - except for a viewer just chosen (at the start, from the list, by the watch): it
  is looked at at once whoever is in front, and every auto_interval_ms until a frame of it is on the page
  (`Following.unseen`, `_follow_viewer`), and for a viewer whose window TASlation just gave a new size: the fresh frame
  goes on the page, the capture area is the new size's own, and Auto goes on from there (`_resize_begins`,
  `_look_afresh`).

While a whole-book run reads the pages the reader turns, the run captures the viewer and the window none of it: in the
whole book each frame the run captures goes on the page as it comes (`_run_frame`), so that a page turned shows as
without a run, and the page being read shows its rectangles only while the viewer shows it. Once the run translates, it needs the viewer no more (`BatchReader.viewer_free`): the window follows the viewer again as above,
the reader's keys and clicks going on to it (`constants.viewer_rests`), and a page taken goes not to a page job - the
worker runs the run, and no request may compete with it - but to the run (`BatchReader.viewer_page`, on a thread of the
window's own, `_ask_beside`): a page the cache holds is shown lettered from it with no model at all, laid over the
viewer's frame while it shows that page, and any other says it is not translated yet (`beside_line`). The run's page
being translated keeps the page area until the reader turns to another page (`Beside.reading`) - from the viewer's
first frame of it on, not once it is taken (`_run_page_kept`) -; then the viewer's page has it - the run's progress,
and its busy badge, only while the viewer shows the very page being translated (`_badge_due`) - until the run ends.

Windows tells who is in front and what happens to the viewer's window (`capture.WindowEvents`, whose notes the
heartbeat takes in: `_beat`), and `follow_decision` decides what each heartbeat does."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .. import fingerprint as fp
from .. import recovery
from ..batch import (CRISP_KEPT, SharpSeen, crispness, detail, frames_differ, looks_sharp, lower_priority, sharper,
                     thumbnail)
from ..capture.windows import BROWSER_CLASSES, covered_by_opaque, window_class
from ..config import Settings
from ..capture import (
    IS_WINDOWS,
    CaptureError,
    ViewerCovered,
    WindowEvents,
    ask_repaint,
    capture_window,
    behind_others,
    client_rect_on_screen,
    foreground_owner,
    foreground_window,
    frame_count,
    frames_come,
    fresh_frame,
    fully_covered,
    is_black,
    is_blank,
    is_browser_class,
    last_input,
    lower_window,
    press_briefly,
    raise_window,
    screen_shows_own,
    window_at_pointer,
    window_exists,
    window_minimised,
    window_rect,
)
from ..detect.page_area import (  # noqa: F401 - panel_inside, TIGHT_PX: as the area dialog and the tests know them
    TIGHT_PX,
    JoinedArea,
    area_margins,
    find_page_area,
    joined,
    page_panel,
    panel_inside,
)
from ..i18n import _
from ..messages import Message
from ..pagekeys import key_ways, opposite_key, pressed_for, same_key, viewer_key
from ..pipeline import PageGate, turn_away
from ..regions import PageResult
from . import area, hover, in_place, order, side
from .constants import (
    BLANK_SPREAD,
    BROWSER_MINIMISED,
    FOLLOW_STEP_MS,
    FOLLOW_WAITS,
    FRAME_GAP_MS,
    FRAME_STEP_MS,
    FULL_SCREEN_SCAN_WAITS,
    LIVE_CHANGE,
    NO_VIEWER,
    READING_NOTE_MS,
    RECHECK_MS,
    RETAKE_WITHIN_MS,
    RUN_AUTO_OFF,
    SETTLE_TRIES,
    TWO_TURNS_S,
    VIEWER_BLACK,
    VIEWER_LOADING,
    book_read,
    in_a_run,
    viewer_rests,
)
from .progress import status_word, unsure_art, usual_char
from .strip import end_follow, run_page_on_show

COVERED_PROBE_MS = 500  # a viewer asked to paint itself anew (`_learn_covered`): a frame within this says it drew
FACTS_KEPT = 4  # the frames whose `FrameFacts` the window keeps, the latest first ...
PIXELS_KEPT = 2  # ... with the pixels of so many of them (and of the frame captured last)
# What a page started on its first frame (`_early_start`) stores lasts once its frame has stayed as it is for so many
# times settle_ms (the fixed wait, 400 ms: 800 ms), counted from the look that saw it (`_early_confirm`); its requests
# do not wait for it. The browser-type stand-in viewer draws its soft picture for 150-400 ms by its script and 400-420
# ms on the screen at times (its timer, then the next frame): settle_ms itself confirmed some of those soft frames;
# twice settle_ms confirmed none there. A viewer slower at times than that has its page read again once it sharpens
# (`_retake`), as with the fixed wait.
KEEP_SETTLES = 2
# A sharper picture of a page started early that comes after its frame was confirmed takes the confirmation back
# (`_retake`, `PageGate.take_back`): nothing its job stored lasts - put back while the job runs, whenever it comes; once
# the job is done, within so long after the confirmation, for a viewer seen to draw a page soft first (`PageGate`'s
# *open_for*; a viewer that never did pays nothing: its page jobs are kept for good as they end). The stay counts the
# frames as they reach the capture: a sharp picture drawn late, or one that reaches the window a few hundred ms after
# the viewer drew it (a busy computer), comes after a soft picture already confirmed. Twice the recheck that follows a
# confirmation (RECHECK_MS); meanwhile one page's snapshot of the stores is held and the cache's save waits.
TAKE_BACK_MS = 2000
# While a page job runs, a frame of another page cancels it once it has stayed as it is for this long (`_settle_s`):
# long enough to say that the viewer left the job's page - under 150 ms (three frame gaps, FRAME_GAP_MS) a frame of a
# viewer's slide could pass for one -, not that the new picture is final, for the new page is then started early with
# a gate of its own.
LEFT_PAGE_MS = 150
SAME_PICTURE = 0.5  # the thumbnails' mean difference under which two frames show the same picture (`_step`'s settle)


@dataclass
class Look:
    """A capture of the viewer's window *hwnd* (`_capture`): when it began (*at*), the viewer's frame count before it
    (*seq*: None, not counted), the picture, and the last moment the window knew the viewer still showed that picture
    (*until*: the capture, or the moment before a look at the frame count since that found no new frame,
    `_frame_count`): what a page job started early is told of its frame (`_frame_seen`)."""

    hwnd: int
    at: float
    seq: int | None
    image: Image.Image
    until: float


def _same_picture(a: Image.Image | None, b: Image.Image | None) -> bool:
    """Whether *a* and *b* are the same capture, or hold the very same pixels."""
    if a is None or b is None:
        return False
    if a is b:
        return True
    return a.size == b.size and np.array_equal(np.asarray(a.convert("RGB")), np.asarray(b.convert("RGB")))


class FrameFacts:
    """What the live view works out of one frame (a capture of the viewer, a page read), each once: numpy's copy of
    its pixels, whether it is blank or black, its thumbnail, its fine detail and its page units - the very values
    `capture.is_blank`, `capture.is_black`, `batch.thumbnail`, `batch.detail` and `fingerprint.analyze` give for it,
    so that a frame leads to the decisions it led to when every check worked them out anew (and took the pixels out
    of the picture anew: 12 ms a time for a full-screen frame, measured). A frame captured again with the very same
    bytes shares the facts of the capture before it (`_captured_facts`)."""

    __slots__ = ("image", "_pixels", "memo", "hwnd", "seq")

    def __init__(self, image: Image.Image) -> None:
        self.image = image
        self._pixels: np.ndarray | None = None
        self.memo: dict[Any, Any] = {}
        self.hwnd: int | None = None  # a capture: the window ...
        self.seq: int | None = None  # ... and its frame count before the capture

    @property
    def pixels(self) -> np.ndarray:
        """``np.asarray(image)`` (read-only)."""
        if self._pixels is None:
            self._pixels = np.asarray(self.image)
        return self._pixels

    def rgb(self) -> np.ndarray:
        """``np.asarray(image.convert("RGB"))``: the pixels themselves for an RGB picture (a capture's)."""
        return self.pixels if self.image.mode == "RGB" else np.asarray(self.image.convert("RGB"))

    def get(self, key: Any, make: Any) -> Any:
        """The fact *key*, made by *make* the first time (what *make* raises is raised, and nothing is kept)."""
        memo = self.memo
        if key not in memo:
            memo[key] = make()
        return memo[key]


def _facts(window: Any, image: Image.Image) -> FrameFacts:
    """The facts of *image* the window keeps (`FrameFacts`, by the picture's identity), made when it has none."""
    kept = getattr(window, "_frame_facts", None)
    if kept is None:
        kept = window._frame_facts = []
    for facts in kept:
        if facts.image is image:
            return facts
    facts = FrameFacts(image)
    kept.insert(0, facts)
    del kept[FACTS_KEPT:]
    last = getattr(window, "_capture_facts", None)
    for older in kept[PIXELS_KEPT:]:
        if older is not last:
            older._pixels = None  # (17 MB a full-screen frame; made again when asked for)
    return facts


def _captured_facts(window: Any, hwnd: int, seq: int | None, image: Image.Image) -> FrameFacts:
    """A frame `_capture` just took of the window *hwnd* (*seq*: its frame count before): when the capture before was
    of that window, the count has not moved since (or is not known) and the bytes are the very same - a frame
    captured again while the viewer drew none -, what was worked out of them holds for this one too, and nothing is
    worked out again."""
    facts = _facts(window, image)
    last = getattr(window, "_capture_facts", None)
    if (last is not None and last is not facts and last.memo is not facts.memo and last.hwnd == hwnd
            and (seq is None or last.seq == seq) and last.image.size == image.size
            and last.image.mode == image.mode and fp.same_pixels(last.pixels, facts.pixels)):
        facts.memo = last.memo
    facts.hwnd, facts.seq = hwnd, seq
    window._capture_facts = facts
    return facts


def known_pixels(window: Any, image: Image.Image) -> np.ndarray | None:
    """``np.asarray(image)`` when the window holds it already (the frame's `FrameFacts`), else None: the canvas takes
    its page's place out of them (`ImageCanvas.pixels_of`)."""
    for facts in getattr(window, "_frame_facts", None) or ():
        if facts.image is image:
            return facts._pixels
    return None


def _blank(window: Any, image: Image.Image) -> bool:
    """`capture.is_blank` of *image*."""
    facts = _facts(window, image)
    return facts.get("blank", lambda: is_blank(facts.pixels))  # (is_blank takes numpy's copy of the pixels)


def _black(window: Any, image: Image.Image, margins: Any) -> bool:
    """`capture.is_black` of *image* in the capture area *margins*."""
    facts = _facts(window, image)
    margins = tuple(margins)
    return facts.get(("black", margins), lambda: is_black(facts.pixels, margins))


def thumbnail_of(image: Image.Image, pixels: np.ndarray | None = None, size: int = 64) -> np.ndarray:
    """`batch.thumbnail` of *image*: from its *pixels* (``np.asarray(image)``) when it is an RGB picture - the very
    values, with the picture's pixels taken out of it once (tests/test_follow.py holds the two alike) -, else
    `batch.thumbnail` itself."""
    if (pixels is None or image.mode != "RGB" or pixels.dtype != np.uint8 or pixels.ndim != 3
            or pixels.shape[2] != 3):
        return thumbnail(image, size)
    gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
    return cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)


def _thumb(window: Any, image: Image.Image) -> np.ndarray:
    """`batch.thumbnail` of *image*."""
    facts = _facts(window, image)
    return facts.get("thumb", lambda: thumbnail_of(image, facts.pixels if image.mode == "RGB" else None))


def _detail(window: Any, image: Image.Image, box: Any) -> np.ndarray:
    """`batch.detail` of *image* in *box*."""
    facts = _facts(window, image)
    box = tuple(box) if box is not None else None
    return facts.get(("detail", box), lambda: detail(image, box))


def _crisp(window: Any, image: Image.Image, box: Any) -> float:
    """`batch.crispness` of *image* in *box*."""
    facts = _facts(window, image)
    box = tuple(box) if box is not None else None
    return facts.get(("crisp", box), lambda: crispness(image, box))


def _units(window: Any, image: Image.Image, margins: Any) -> list[Any]:
    """`fingerprint.analyze` of *image* in the capture area *margins* (shared: never change what it gives). The
    analysis is kept by `fingerprint.analyze` as well, so that the page job that reads this frame takes its units
    from there (`Pipeline.units_of`)."""
    facts = _facts(window, image)
    return facts.get(("units", tuple(margins)), lambda: fp.analyze(facts.rgb(), margins))


def follow_decision(mode: str, owner: str, *, following: bool, look_due: bool, poll_due: bool,
                    unseen: bool = False, frame_new: bool = False) -> str:
    """What the live view does at a heartbeat: "poll" (capture now, Auto comparing it with the ticks before),
    "look" (capture once now), "follow" (nothing here: an operation of TASlation's on the viewer is being followed
    and its captures come by themselves) or "idle" (no capture).

    With *mode* "poll" (follow = "poll", or no window events to be had) the viewer is polled whenever *poll_due*
    (every auto_interval_ms), as before. With "events": an operation is followed to its end whoever is in front;
    a look that is due while the viewer just chosen has no picture on the page yet (*unseen*) is taken whoever is
    in front; else while neither TASlation nor the viewer is in front (*owner* "other") nothing is captured; a look
    that is due (*look_due*: a window came back to the front, the viewer's window stopped moving or was renamed, the
    last look failed) is taken; while the viewer itself is in front it is polled when *poll_due* or when it drew a
    new frame (*frame_new*), so that pages turned there are followed; while TASlation is in front, nothing."""
    if mode != "events":
        return "poll" if poll_due else "idle"
    if following:
        return "follow"
    if look_due and unseen:
        return "look"
    if owner == "other":
        return "idle"
    if look_due:
        return "look"
    if owner == "viewer" and (poll_due or frame_new):
        return "poll"
    return "idle"


@dataclass
class Taken:
    """A frame taken as the page (follow = "events"), for the looks after it: the frame, its thumbnail and its fine
    detail, when; for a sharper frame waiting to be read again, the softer frame read before - None when nothing of
    the job on it lasts (its confirmation taken back: nothing of it to drop from the cache)."""

    frame: Image.Image
    thumb: np.ndarray
    detail: np.ndarray
    at: float
    soft: Image.Image | None = None
    complete: bool = False  # translator mode: shown from the cache at once, completed once the frame has settled
    gate: PageGate | None = None  # the gate of the page job started early on the frame (`_early_start`)


@dataclass
class Operation:
    """An operation of TASlation's on the viewer being followed: its frame awaited to change from *reference* (None:
    it has changed already), then to settle, and looked at once more after the page is taken."""

    hwnd: int
    reference: np.ndarray | None
    key: str = ""  # the key passed on ("" for a click)
    retried: bool = False  # the key was pressed for real already (a click has none to press)
    started: float = 0.0
    phase: str = "change"  # "change", "settle", "recheck"
    last: np.ndarray | None = None  # "settle": the frame before ...
    last_detail: np.ndarray | None = None  # ... its fine detail ...
    last_image: Image.Image | None = None  # ... and its capture
    settles: int = 0
    job: str | None = None  # the after() of its next step
    operation: bool = True  # after TASlation's own operation (False: a look found the page changing)
    prev: np.ndarray | None = None  # "change": the frame of the step before
    stirred_at: float | None = None  # "change": when the frame last changed at all (the viewer took the key)
    pressed: bool = False  # the key was pressed for real after the posted one changed nothing
    turned_at: float | None = None  # after that press: when the page turned ...
    calm: np.ndarray | None = None  # ... the frame it settled on ...
    twice: bool = False  # ... and whether it turned once more soon after (the posted key had arrived after all)
    raised: bool = False  # "change": the viewer was raised for a look (`_raise_viewer`) since the frame last changed
    fast_until: float | None = None  # "recheck" after a page taken at once (`_take_at_once`): looked at until then
    seq: int | None = None  # the frame count at the last capture (`capture.frame_count`; None: frames not counted)
    last_at: float = 0.0  # "settle" and "recheck" with frames counted: when the frame last changed ...
    settle_from: float = 0.0  # ... and since when it is followed to settle
    looked_at: float = 0.0  # "change" with frames counted: when the frame was last captured
    redo: bool = False  # "settle": the page started early was dropped; started again once the worker is free
    over_job: bool = False  # "settle": begun while a page job runs, on a frame of another page (`_look_over_job`)
    held_soft: bool = False  # "settle": its frame looks soft (a viewer that draws soft first): not started early on it
    keys: tuple[str, ...] = ()  # "change": the posted keys awaited, the first one's own wait for all (`_held_keys`)


@dataclass
class Early:
    """A page job started on the first frame of a new page, before the frame settled (`_early_start`): the operation
    followed, the job's gate (`pipeline.PageGate`), the frame it reads, what the window held before it - what is
    put back when the job is dropped (`_early_drop`) -, and the last capture found to show that frame (`_frame_seen`)."""

    op: Operation
    gate: PageGate
    image: Image.Image
    thumb: np.ndarray
    auto_last: np.ndarray | None
    candidate: np.ndarray | None
    taken: Taken | None
    retake: Taken | None
    look: Look | None = None


@dataclass
class Following:
    """How the window follows the viewer (made at the first heartbeat: `LiveViewMixin._follower`)."""

    mode: str = "poll"  # "events" while Windows' window events are hooked
    events: Any = None  # the hooks (capture.WindowEvents)
    owner: str = "own"  # who is in front: "own" (a window of TASlation's), "viewer", "other"
    look_at: float | None = None  # a look at the viewer is due from then on
    moved: float | None = None  # the viewer's window noted moving last then, and not looked at once it stopped yet
    size: tuple[int, int] | None = None  # the size of the viewer's window at the last note that it moved (or watched)
    last_poll: float = 0.0
    polled: int | None = None  # the viewer's frame count at the last poll (`capture.frame_count`)
    last_input: int = 0  # when the session's last input came (Windows' ticks), as seen at the last heartbeat
    seen: np.ndarray | None = None  # the thumbnail of the last frame captured
    op: Operation | None = None  # the operation being followed
    taken: Taken | None = None  # the page taken last, while a sharper frame of it may come
    retake: Taken | None = None  # such a sharper frame, read once the job on the softer one is done
    unseen: bool = True  # the viewer chosen has no picture on the page yet: it is looked at whoever is in front
    # a viewer that has drawn a page soft first (`_drew_soft`): its window, and the `batch.crispness` of the soft
    # pictures it drew and of their sharp ones, what its frames are judged by (`_looks_soft`), and those sharp
    # pictures' by their pages, by which a frame of such a page may be found soft as well
    soft_of: int | None = None
    soft: deque[float] = field(default_factory=lambda: deque(maxlen=CRISP_KEPT))
    sharp: deque[float] = field(default_factory=lambda: deque(maxlen=CRISP_KEPT))
    sharp_pages: SharpSeen = field(default_factory=SharpSeen)


@dataclass
class Beside:
    """Reading on the viewer beside a whole-book run that translates (`reads_beside`): the viewer's page
    as the translation began (*base*, a thumbnail), whether the reader has turned to another since (*reading*: the page
    area shows the viewer's page from then on, not the run's), and the page asked of the run (`BatchReader.viewer_page`,
    on a thread of the window's own: *token* the latest, *pending* the frame waiting to be asked, the latest only). *seq*
    and *state* say what the run answered for the page on show; *note* the line on the page that says it."""

    base: np.ndarray | None = None
    reading: bool = False
    token: int = 0
    pending: tuple[int, Image.Image] | None = None
    thread: threading.Thread | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    seq: int | None = None
    state: str = ""
    note: str = ""


def reads_beside(window: Any) -> bool:
    """Whether *window* follows the viewer beside a whole-book run: the run translates and needs the viewer no more
    (`BatchReader.viewer_free`; never while it reads the pages, which it captures itself)."""
    batch = getattr(window, "batch", None)
    return batch is not None and bool(getattr(batch, "viewer_free", False))


def beside_line(state: str) -> str:
    """What the page says, in the window's language, while the viewer shows a page beside the run whose answer was
    *state* (`batch.ViewerPage`); "" for a page shown translated, or no page."""
    if state == "waiting":
        return _("Not translated yet: the whole-book run has not come to this page. It shows translated once it has.")
    if state == "untranslated":
        return _("Not translated yet: this page was not read in the whole-book run. It is translated once the run is done.")
    if state == "later":
        return _("This page is translated: it shows once the whole-book run is done.")
    return ""


class BlackViewerMixin:
    """A viewer that stays black, followed in the window (`taslation.recovery`). A part of `App` through
    `LiveViewMixin`."""

    def _black_open(self) -> bool:
        """Whether the viewer has stayed black so far (`recovery.BlackWatch`): nothing but the heartbeat looks at it
        then (`_black_beat`), so no capture is made for the other looks and no page is taken."""
        return getattr(self, "_black_watch", None) is not None

    def _drew_nothing(self, thumb: np.ndarray) -> bool:
        """Whether the viewer's frame, whose thumbnail is *thumb*, has nothing on it: one flat colour, or black."""
        return float(thumb.max()) - float(thumb.min()) < BLANK_SPREAD or self._black_open()

    def _see_black(self, hwnd: int, image: Image.Image) -> bool:
        """A frame of the viewer judged (`capture.is_black`), and whether it is black: the first one opens a spell
        (`recovery.BlackWatch`), a later one takes the spell a step on. Never while TASlation enlarges the window
        (`_resizing`): the frames then are of that change. A run has its own wait for a black viewer. No key goes for
        it."""
        black = _black(self, image, self._margins_of(image))
        if in_a_run(self):
            return black
        watch = getattr(self, "_black_watch", None)
        waiting = getattr(self, "_enlarging", None)
        if waiting is not None and waiting.get("enlarged") is not None:
            self._black_watch = None
            return black
        if watch is None:
            if not black:
                return False
            watch = self._black_watch = recovery.BlackWatch(hwnd, self.settings, size=self._window_size(hwnd))
        self._black_step(watch, black)
        return black

    def _black_step(self, watch: recovery.BlackWatch, black: bool) -> None:
        """The spell one step on, and what the reader is told: still loading, then how to reload the book in its own
        window (`VIEWER_BLACK`)."""
        happened = watch.step(black, self._window_size(watch.hwnd), time.monotonic())
        if happened == recovery.LOADING:
            self.say(VIEWER_LOADING)
        elif happened == recovery.GAVE_UP:
            self.say(VIEWER_BLACK)
        elif happened == recovery.RECOVERED:
            self._black_over(watch)

    def _black_over(self, watch: recovery.BlackWatch) -> None:
        """A frame shows something: silently after a mere wait; after the notice (the person reloaded the book, say) the
        page is taken afresh, as the viewer shows it now."""
        self._black_watch = None
        if getattr(self, "_status_key", None) in (VIEWER_LOADING, VIEWER_BLACK):
            self._normal_status()
        if watch.told:
            self._sync_area()
            self._apply_found_margins()
            self._look_afresh()
        else:
            self._look_soon()

    def _black_beat(self) -> bool:
        """The heartbeat while the viewer has stayed black: about once a second, in memory, whether a frame came
        (`BlackWatch.new_frame`), and only such a frame is taken and judged (`_capture`, `_see_black`). A spell ends
        without a word when the viewer is gone, the window shows something else than the book or a batch takes over.
        Returns whether a spell is open: the heartbeat does nothing else then."""
        watch = getattr(self, "_black_watch", None)
        if watch is None:
            return False
        win = self.selected
        over = win is None or win.hwnd != watch.hwnd or not window_exists(watch.hwnd)
        if not over:
            over = self.batch is not None or self._batching or not self._book_in_front()
        if over:
            self._black_watch = None
            return False
        now = time.monotonic()
        if now < watch.next_at:
            return True
        watch.next_at = now + watch.step_s
        if not watch.new_frame(now):
            self._black_step(watch, True)
            return self._black_open()
        try:
            self._capture(watch.hwnd)
        except CaptureError as e:  # covered, hidden: that says nothing of the viewer
            self._black_watch = None
            self._capture_failed(e)
        return self._black_open()


class LiveViewMixin(BlackViewerMixin):
    """The capture, the live picture and Auto. A part of `app.App` (no `__init__`: the state it uses is made by
    `App.__init__`; the other parts are reached through ``self``)."""

    # ------------------------------------------------------------------ the page in the viewer's window
    def _found_margins(self, size: tuple[int, int] | None = None) -> tuple[int, int, int, int]:
        """The margins of the page panel found so far in the chosen viewer's frames ((0, 0, 0, 0): none yet), in
        frames of *size* only when given."""
        known = self._page_areas.get(viewer_key(self.selected)) if self.selected is not None else None
        if known is None or (size is not None and known[0] != size):
            return (0, 0, 0, 0)
        return area_margins(known[1], known[0])

    def _find_page(self, image: Image.Image) -> None:
        """The page panel in the chosen viewer's frame (`find_page_area`). While the reader has set no area for the
        viewer it is looked for on the whole capture: the boxes found are joined per viewer and capture size - a
        cover alone gives a narrower box than the spreads after it, a frame where none is found changes nothing, a
        new size starts over - and the joined box is the capture area, applied as a hand-set area is (the margins
        every part of TASlation reads), though not in the middle of a job (`_apply_found_margins` follows when it is
        done). An area the reader set is the outer bound, not the end of the story: the panel is looked for inside it
        as well (`page_area.page_panel`, `panel_inside`: an area that trims only a browser's bars leaves the reader's
        own header, links and page slider in it), joined the same way per viewer, capture size and area
        (`_inner_areas`), and the capture area is what the two have in common - the area alone while nothing is found
        (`_inner_margins`); a page that fills the area within TIGHT_PX joins the area itself (a cover narrower than the
        spreads the area was drawn around narrows it only until a spread is shown). A whole-book run that follows the
        reader widens its own area with the pages it takes and tells the window the panels it found (`_run_found`),
        joined into the same records."""
        win = self.selected
        if win is None:
            return
        if getattr(self, "_enlarged", None) is not None or getattr(self, "_area_large", False):
            self._sync_area()  # enlarged, or made smaller again by the reader: the area of this frame
        key, size = viewer_key(win), image.size
        if self._manual_area:
            hand = self._hand_set()
            inner = getattr(self, "_inner_areas", None)
            if inner is None:
                inner = self._inner_areas = {}
            known = inner.get(key)
            box = known[2] if known is not None and known[:2] == (size, hand) else None
            inner[key] = (size, hand, joined(box, page_panel(image, hand)))
            self._apply_found_margins()
            return
        known = self._page_areas.get(key)
        box = known[1] if known is not None and known[0] == size else None
        try:
            found = find_page_area(image)
        except Exception:  # noqa: BLE001 - a frame the finder cannot take changes nothing
            found = None
        self._page_areas[key] = (size, joined(box, found))  # type: ignore[assignment]
        self._apply_found_margins()
        if self.ready and not self.busy and self._area_hint_due():
            self._area_hinted = True
            title = win.title
            self.status(lambda: _("Viewer: {title}").format(title=title) + "  " + _(
                "No area is set for this viewer: Set area... (Page menu) lets you drag a rectangle around the page."))

    def _hand_set(self) -> tuple[int, int, int, int]:
        """The chosen viewer's capture area as the reader set it (``_hand_area``; a window without that record - a
        test's stand-in - has the area in its margins)."""
        hand = getattr(self, "_hand_area", None)
        margins = hand if hand is not None else self.settings.margins
        return tuple(int(m) for m in margins)  # type: ignore[return-value]

    def _inner_margins(self, size: tuple[int, int] | None = None) -> tuple[int, int, int, int]:
        """The capture area within the reader's own: the page panel found inside it so far, as far as it lies within
        the area (`_find_page`); the area itself while none is found for this viewer, capture size (*size*, when
        given) and area."""
        hand = self._hand_set()
        known = getattr(self, "_inner_areas", {}).get(viewer_key(self.selected)) \
            if self.selected is not None else None
        if known is None or known[1] != hand or known[2] is None or (size is not None and known[0] != size):
            return hand
        found_size, _hand, box = known
        return area_margins(box, found_size, hand)

    def _apply_found_margins(self, starting: bool = False) -> None:
        """The page found so far becomes the capture area - within the reader's own area when there is one
        (`_inner_margins`) - while no job is running (*starting*: the batch has not begun reading yet, and its window
        has just been enlarged). A run that follows the reader widens its area with the pages it meets
        (`page_area.JoinedArea`, started from `_run_area`; the pipeline takes it in between two pages); other jobs keep
        one area. What the run found joins the window's record as it goes (`_run_found`), so that the area applied here
        once the run is done holds everything the run read."""
        if self.selected is None or (self.busy and not starting):
            return
        margins = self._inner_margins() if self._manual_area else self._found_margins()
        if tuple(self.settings.margins) != margins:
            self.settings.margins = margins

    def _run_area(self) -> JoinedArea | None:
        """The capture area a whole-book run starts from and widens with the pages it takes (`page_area.JoinedArea`):
        the margins in force now, the reader's own area as the outer bound when there is one (`_hand_set`), and the
        page panels found so far in the chosen viewer's frames for it (`_page_areas`, `_inner_areas`). None while no
        viewer is chosen. On the Tk thread, as the run starts."""
        win = self.selected
        if win is None:
            return None
        key = viewer_key(win)
        if self._manual_area:
            hand: tuple[int, int, int, int] | None = self._hand_set()
            known = getattr(self, "_inner_areas", {}).get(key)
            size, found = (known[0], known[2]) if known is not None and known[1] == hand else (None, None)
        else:
            hand = None
            size, found = self._page_areas.get(key) or (None, None)
        return JoinedArea(tuple(self.settings.margins), hand, size, found if size is not None else None)

    def _run_found(self, data: dict[str, Any]) -> None:
        """A whole-book run that follows the reader found page panels in the pages it took (``page_area`` {hwnd, size,
        found, hand, margins}: their union in the capture's pixels, inside the reader's area *hand* when there is one,
        and the run's area now): joined into the window's record for the viewer, as the panels of its own frames are
        (`_find_page`), so that the capture area the window applies once the run is done (`_apply_found_margins`)
        holds every page the run read. The run's area is joined in as well: it is what the panels give, unless the run
        read pages without a panel in a wider area before (it started with no panel known), and then the window keeps
        that wider area too - never narrower than the run's, whose pages it shows. A record of another viewer, or of
        another area of the reader's than the window's now, is left alone."""
        win = self.selected
        found = data.get("found")
        if win is None or found is None or win.hwnd != data.get("hwnd", win.hwnd):
            return
        key, size = viewer_key(win), tuple(data["size"])
        read = data.get("margins")
        if read is not None:  # (the box the run's area leaves: the panels found, or more)
            found = joined(tuple(int(v) for v in found), area.margins_to_box(tuple(read), size))
        hand = data.get("hand")
        if hand is not None:
            hand = tuple(int(m) for m in hand)
            if not self._manual_area or hand != self._hand_set():
                return
            inner = getattr(self, "_inner_areas", None)
            if inner is None:
                inner = self._inner_areas = {}
            known = inner.get(key)
            box = known[2] if known is not None and known[:2] == (size, hand) else None
            inner[key] = (size, hand, joined(box, found))
        else:
            if self._manual_area:
                return
            known = self._page_areas.get(key)
            box = known[1] if known is not None and known[0] == size else None
            self._page_areas[key] = (size, joined(box, found))  # type: ignore[assignment]
        self._apply_found_margins()

    def _area_hint_due(self) -> bool:
        """Once a session: the chosen viewer has no area of the reader's, and its frames were looked at without a
        page panel found - Set area... is the way then."""
        if self._area_hinted or self.selected is None or self._manual_area:
            return False
        known = self._page_areas.get(viewer_key(self.selected))
        return known is not None and known[1] is None

    # ------------------------------------------------------------------ the picture on the page
    def _redisplay(self) -> None:
        reading = self.reading
        self._status_follows_page()  # (a line about the page before goes with it)
        self.canvas.enlarge = reading
        self.canvas.message = _("This viewer cannot be read behind the full screen; press F11") if (
            reading and self._viewer_hidden) else ""
        # no viewer chosen yet: what to do, in the window's language (the live picture takes its place once one is)
        self.canvas.hint = _(NO_VIEWER) if self.selected is None else ""
        in_place.refresh(self)  # (a bubble showing its other side in its place: drawn with the page, or gone)
        image, overlay, outlines = self._picture()
        self.canvas.overlay, self.canvas.outlines = overlay, outlines
        self.canvas.brackets = side.on_picture(self, image)  # (the updated mark: the bubbles changed since last seen)
        # what the canvas may draw cheaply, leaving the very picture of a full draw (`ImageCanvas.set_image`): a new
        # frame of the viewer's, and the page filling in, lettered in place in the boxes noted since it was drawn
        moved, self._live_moved = getattr(self, "_live_moved", False), False
        lettered, self._fill_changed = getattr(self, "_fill_changed", None), None
        fill = getattr(self, "_fill", None)
        self.canvas.moving = bool(moved and image is not None and run_page_on_show(self) is None)
        self.canvas.pixels_of = lambda picture: known_pixels(self, picture)
        self.canvas.changed = (lettered[1] if lettered is not None and image is not None and lettered[0] is image
                               and fill is not None and fill.page is image else None)
        if image is None:
            self.canvas.crop = None
            self.canvas.set_image(None)
            return
        self.canvas.crop = area.margins_to_box(self._margins_of(image), image.size) if reading else None  # the page alone
        self.canvas.set_image(image)

    def _picture(self) -> tuple[Image.Image | None, list[Any], list[Any]]:
        """What the page shows, with translator mode's region overlay and the outlines of a page filling in:

        * a page the whole-book run is translating (`strip.run_page_on_show`): the lines answered so far lettered,
          the others outlined;
        * a page being translated, while the viewer still shows it (`_fill_on_show`): the frame it is read from with
          the regions lettered so far, the others outlined;
        * else the last translated page while the viewer still shows that page - its lettering laid over the
          viewer's latest frame, so a toolbar or the pointer shows as it is now;
        * else the viewer's latest frame as it is (a page not translated yet, a page turned, the viewer's panels).
        Show original leaves the lettering out. With the original on the page and the translation under the
        pointer (`hover.reverse_on`: `Settings.hover_shows` "translation", in the Reader role), the
        page being translated and the last translated page show as the viewer does too, without the outlines - but
        for the box under the pointer whose translation has not come, where its bubble shows in its place
        (`in_place.hovered_outline`; the panel beside it says so itself: `zoom`); a whole-book run's page stays as it
        is. A bubble that shows its other side in its place is laid over this picture (`in_place.refresh`).
        Reading is on the viewer only: the first is the one page of a whole-book run's memory ever shown, as the
        run's progress while it translates; outside that, every picture is the viewer's page (`strip`'s docstring),
        so that TASlation never lets a book be read without the viewer."""
        original = self.original_var.get()
        run = run_page_on_show(self)
        if run is not None:
            return (run.frame if original else run.image), [], run.outlines()
        reverse = hover.reverse_on(self)
        fill = self._fill
        if fill is not None and self._fill_on_show():
            if reverse:
                return fill.frame, [], in_place.hovered_outline(self, fill)
            image = fill.final if fill.final is not None else fill.page if fill.page is not None else fill.base
            return (fill.frame if original else image), [], ([] if fill.final is not None else fill.outlines())
        result, live = self.last_result, self._live
        if result is not None and (live is None or self._same_page(result, live)):
            if original or reverse:
                return (live if live is not None else result.original), self._overlay_items(), []
            return self._lettered(result, live), self._overlay_items(), []
        return live, [], []

    def _status_follows_page(self) -> None:
        """The status line speaks of the page on show: a line about one page (`_page_status`, a page job's line,
        `_job_line`) goes as soon as the viewer's latest frame (`_live`) is of another page (`_shows_page`: a soft
        picture and its sharp one, the pointer over it, are the same page) - a turn, the viewer's window given another
        size -, and the line of what is on show takes its place (`_normal_status`), with no note of its own on the
        full screen's page, where the old line's note goes too. Asked whenever the page is drawn (`_redisplay`)."""
        page = getattr(self, "_status_page", None)
        if page is None or self._live is None or self._shows_page(self._live, page):
            return
        old, self._status_page = self.status_var.get(), None
        self._normal_status()
        if self.reading and self.canvas.note in (old, self.status_var.get()):
            self.canvas.set_note("")

    def _result_on_show(self) -> bool:
        """Whether the page shows the last result (not a page filling in, nor the viewer showing another page)."""
        result = self.last_result
        return ((self._fill is None or not self._fill_on_show()) and result is not None
                and run_page_on_show(self) is None and (self._live is None or self._same_page(result, self._live)))

    def _fill_on_show(self) -> bool:
        """Whether the page filling in (`_fill`, the page a job reads) is the viewer's page still, as its latest frame
        (`_live`) tells: the job's frame itself, or a frame of that size whose capture area is about the same
        (`_same_page`'s test: a spinner, the pointer, a soft picture and its sharp one alike). While the viewer shows
        another page - turned while the job runs, before the new frame has stayed for LEFT_PAGE_MS and the job is
        cancelled (`_look_over_job`) - the page shows the viewer's frame as it is, the job's lettering nowhere; back on
        the job's page, the page filling in shows again. Frames of nothing (a black flash) never become the live
        frame, so the page filling in stays through them. Nor is it on show once the viewer has drawn its page sharper than
        the frame it is read from (`_sharper_than`: a soft picture replaced, its job dropped or read again): its
        lettering is laid on that frame, which the viewer shows no more, so the page shows the viewer's frame as it is
        until the page is lettered on the sharp one (a page partly in the cache, started on its soft frame, lettered
        on the blurry picture what the cache held, and that stayed on show until its job was gone)."""
        fill = self._fill
        if fill is None:
            return False
        live = self._live
        return live is None or (self._shows_page(live, fill.frame) and not self._sharper_than(fill.frame, live))

    def _sharper_than(self, frame: Image.Image, image: Image.Image) -> bool:
        """Whether the frame *image* is a sharper picture than *frame* (`batch.sharper` on their fine detail in the
        capture area); kept for the last two frames asked about."""
        if image is frame:
            return False
        memo = getattr(self, "_sharper_memo", None)
        if memo is not None and memo[0] is frame and memo[1] is image:
            return memo[2]
        found = sharper(_detail(self, frame, self._area_box(frame)), _detail(self, image, self._area_box(image)))
        self._sharper_memo = (frame, image, found)
        return found

    def _same_page(self, result: PageResult, live: Image.Image) -> bool:
        """Whether the viewer's frame *live* still shows *result*'s page: the same size, and the capture area about
        the same as when the page was read (the viewer's toolbar or the pointer beside the page do not count)."""
        if live is result.original:
            return True
        if live.size != result.original.size:
            return False
        return not frames_differ(self._area_thumb(result.original), self._area_thumb(live))

    def _area_thumb(self, image: Image.Image) -> np.ndarray:
        """The thumbnail of *image*'s capture area (`_margins_of`; remembered for the last few frames)."""
        margins = self._margins_of(image)
        for key, img, thumb in self._thumbs:
            if img is image and key == margins:
                return thumb
        box = area.margins_to_box(margins, image.size)
        whole = box == (0, 0, image.width, image.height) or box[2] <= box[0] or box[3] <= box[1]
        thumb = _thumb(self, image) if whole else thumbnail(image.crop(box))
        self._thumbs = [(margins, image, thumb), *self._thumbs[:3]]
        return thumb

    def _lettered(self, result: PageResult, live: Image.Image | None) -> Image.Image:
        """*result*'s translated page; when the viewer's latest frame *live* is another capture of that page, the
        lettering laid over it (where the translated page differs from the capture it was read from)."""
        if live is None or live is result.original:
            return result.image
        memo = self._lettered_memo
        if memo is not None and memo[0] is result.image and memo[1] is live:
            return memo[2]
        mask, pixels = self._lettering(result)
        out = np.array(live if live.mode == "RGB" else live.convert("RGB"))
        out[mask] = pixels
        image = Image.fromarray(out)
        self._lettered_memo = (result.image, live, image)
        return image

    def _lettering(self, result: PageResult) -> tuple[np.ndarray, np.ndarray]:
        """Where *result*'s translated page differs from its capture (the erased text and the lettering), and its
        pixels there."""
        memo = self._mask_memo
        if memo is not None and memo[0] is result.image:
            return memo[1], memo[2]
        page = np.asarray(result.image)
        mask = np.any(page != np.asarray(result.original), axis=2)
        self._mask_memo = (result.image, mask, page[mask])
        return mask, page[mask]

    def _settle_live(self, result: PageResult) -> None:
        """A job's page has come: when the viewer still shows the frame it was read from, that capture is the live
        frame (the page then shows as it is, nothing laid over it)."""
        thumb = self._job_thumb if self._job_thumb is not None else _thumb(self, result.original)
        if self._live_thumb is None or not frames_differ(self._live_thumb, thumb, LIVE_CHANGE):
            self._live, self._live_thumb = result.original, thumb

    def _show_live(self, image: Image.Image, thumb: np.ndarray | None = None) -> None:
        """The live view: a frame of the viewer goes on the page when it differs from the one on show, or is of another
        size. A page filling in keeps its frame while the viewer shows that page (`_fill_on_show`); a frame of another
        page takes its place at once, and the page filling in is back as soon as the viewer shows its page again. From
        the first one on, the viewer chosen is followed by the usual rules (`Following.unseen`)."""
        f = getattr(self, "_following", None)
        if f is not None:
            f.unseen = False
        thumb = _thumb(self, image) if thumb is None else thumb
        if (self._live is not None and self._live_thumb is not None and self._live.size == image.size
                and not frames_differ(self._live_thumb, thumb, LIVE_CHANGE)):
            return
        fill = self._fill
        filling = fill is not None and self._fill_on_show()
        self._live, self._live_thumb = image, thumb
        if fill is None or not self._fill_on_show():
            self._live_moved = True  # (a frame of the viewer's: drawn quickly while they keep coming, `_redisplay`)
            self._redisplay()
        elif not filling:
            self._redisplay()  # the viewer back on the page being translated: it shows filling in again
        if reads_beside(self):
            self._show_badge()  # (beside a run, its badge goes and comes with its page: `_run_page_kept`)

    def _run_frame(self, image: Image.Image) -> None:
        """A frame of the viewer as a whole-book run reading the pages saw it come (``viewer_frame``: the run captures
        the viewer then, the live view does not): on the page as the live view puts a frame there (`_show_live`), so
        that a page turned shows as soon as the viewer draws it, as without a run, not once the run takes it
        (``batch_page``); a frame of nothing is left out, as ever. The badge of the page being read is on the page only
        while that page is (`_badge_due`). Once the run needs the viewer no more the window looks itself."""
        if self.batch is None or reads_beside(self):
            return
        thumb = _thumb(self, image)
        if self._drew_nothing(thumb):
            return
        self._show_live(image, thumb)
        self._show_badge()

    def _quiet_live(self, image: Image.Image, thumb: np.ndarray) -> None:
        """*image* the live frame (`_show_live`), not drawn yet: what is drawn next shows it."""
        f = getattr(self, "_following", None)
        if f is not None:
            f.unseen = False
        self._live, self._live_thumb = image, thumb

    def _noted_regions(self) -> list[Any]:
        """The page's regions that carry a note for the reader, in reading order (numbered as the daggers)."""
        if self.last_result is None:
            return []
        return [r for r in self.last_result.regions if getattr(r, "reader_note", "") and r.status != "dropped"]

    def _show_notes(self) -> None:
        """Under the page: the notes for the reader on it, or nothing."""
        noted = self._noted_regions()
        if not noted or self.reading:  # the full screen shows the page alone
            self.notes_label.pack_forget()
            return
        self.notes_var.set(_("Notes for the reader: ") + "   ".join(f"\u2020{i + 1} {r.reader_note}" for i, r in enumerate(noted)))
        self.notes_label.pack(fill="x", before=self.status_bar)

    def _page_regions(self) -> list[Any]:
        """The regions of the page on show that translator mode outlines and a click selects: all but the dropped
        ones and the unsure readings that are pieces of the drawing (`unsure_art`, held to the page's usual
        character size or the book's so far: `usual_char`)."""
        result = self.last_result
        if result is None:
            return []
        try:
            book = [float(s) for s in getattr(getattr(self, "pipeline", None), "_book_sizes", ()) or ()]
        except (TypeError, ValueError):
            book = []
        usual = usual_char(result.regions, book)
        return [r for r in result.regions if r.status != "dropped" and not unsure_art(r, usual)]

    def _overlay_items(self) -> list[tuple[tuple[int, int, int, int], str, str]]:
        """Translator mode, in the window and on the full screen: outline every region (green = translated, orange =
        not, blue = reader-made), with the speaker, a dagger where a note for the reader is, and the reading-order
        number while an order is being set; not the pieces of the drawing the OCR read unsure (`_page_regions`)."""
        if self.role_var.get() != "translator" or self.last_result is None:
            return []
        items = []
        noted = self._noted_regions()
        for r in self._page_regions():
            colour = {"translated": "#3ddc84"}.get(r.status, "#ffb347")
            if r.kind.startswith("manual"):
                colour = "#4da3ff"
            label = "" if r.status == "translated" else status_word(r.status)
            if getattr(r, "flags", None):
                colour, label = "#ff5e5e", "?"  # flagged for a look: see `taslation review`
            if r.speaker:
                label = (label + " " if label else "") + r.speaker
            if r.continues:
                label += " ..."
            number = next((i for i, n in enumerate(noted, 1) if n is r), 0)  # (by identity: `==` reaches the masks)
            if number:
                label = (label + " " if label else "") + f"\u2020{number}"
            if self._ordering is not None:
                place = next((i for i, o in enumerate(self._ordering, 1) if o is r), 0)
                label = (str(place) if place else "?") + (f" {label}" if label else "")
            items.append((r.bbox, colour, label))
        return items

    # ------------------------------------------------------------------ Auto
    def _on_new_page(self, image: Image.Image, thumb: np.ndarray | None = None, complete: bool | None = None) -> None:
        """Auto mode found a new page: translate it. The first page of a book not in its cache, and not read yet
        (`_book_read`: a page of a book read already is translated as a page, with no dialog), starts the book first
        (`_begin_book`): in whole-book mode the setup is checked and the reader asked - the book's name when the
        window's title gives none, and whether to read the whole book first, so that every later page is instant;
        in page-by-page mode only the name is asked for when the title gives none. While that is under way the
        latest page waits for it. A viewer not read yet has its window enlarged first (`_enlarge_first`), and this
        frame goes: Auto takes the next. *complete*: the page job's own (None: as the role has it; False: a page the
        cache holds whole, drawn from it alone, `_take_at_once`)."""
        if self._start_pending is not None:
            self._start_pending = (image, thumb)
            return
        if not self._enlarge_first():
            return
        if self._book_scanned and self._scanned_book != self.book_var.get().strip():
            self._book_scanned = False  # another book since: it starts as a book of its own
        whole = self.scan_mode() == "book"
        if not self._book_scanned and (whole or self._name_needed()) and self._page_uncached(image):
            if whole and not self._name_needed() and self._book_read():
                self._start_translate(image, thumb=thumb)  # a page of a book read already: no whole-book start
                return
            if self.reading:  # no dialog over the full screen, and the scan would turn the pages under the reader
                self._start_translate(image, thumb=thumb, complete=complete)
                if self._name_needed():  # kept nowhere: its name is asked for on leaving (`_ask_name_after_reading`)
                    self._unkept_reading = getattr(self, "_unkept_reading", 0) + 1
                if whole and not self._scan_waits_told:
                    self._scan_waits_told = True
                    self.say(FULL_SCREEN_SCAN_WAITS)
                return
            if self.selected is None:
                return
            self._begin_book(image, thumb, whole)
            return
        self._start_translate(image, thumb=thumb, complete=complete)

    def _page_uncached(self, image: Image.Image) -> bool:
        """Is any page unit of this capture missing from the book's cache? (A quick check on the Tk thread: the cache
        as its file holds it, read again only once a save changed the file, `CacheStore.peek`.) Under a
        name that names no book (a viewer, a browser, nothing: `_name_needed`) every page is: nothing is kept under
        it, so the start asks for the name even when an old cache under the viewer's name holds the page."""
        book, model, language = self.book_var.get().strip(), self.model_var.get().strip(), self.lang_var.get().strip()
        if not self.settings.cache_enabled:
            return False
        if self._name_needed():
            return True
        try:
            cache = self.store.peek(book, model, language or "English")
            units = _units(self, image, self._margins_of(image))
        except Exception:
            return False
        return bool(units) and any(
            cache.lookup(u.fingerprint, u.aspect, self.settings.fingerprint_max_distance) is None for u in units)

    def _book_read(self) -> bool:
        """Whether the book in the Book box has been read (`book_read`: its cache holds `BOOK_READ_PAGES` translated
        pages or more), a quick check on the Tk thread. Its whole-book start is not offered again then: a page of it
        that is not translated yet is translated as a page. A name that names no book, the cache off: not read."""
        if not self.settings.cache_enabled or self._name_needed():
            return False
        book, model, language = self.book_var.get().strip(), self.model_var.get().strip(), self.lang_var.get().strip()
        try:
            return book_read(len(self.store.peek(book, model, language or "English")))
        except Exception:  # noqa: BLE001 - cannot be told: the start is offered as ever
            return False

    def _all_cached(self, image: Image.Image) -> bool:
        """Whether a page job on *image* can draw all of it from the book's cache (a quick check on the Tk thread, as
        `_page_uncached`): every page unit found in the cache and none marked incomplete (that one is completed in any
        mode, from a settled frame), the cache on and the book named, the models ready and no whole-book run on. Such
        a page may be taken from a frame that has not settled (`_take_at_once`): what is drawn comes from the cache
        alone; in translator mode, which completes a cached page from what it reads (`_completes`), the completion
        follows once the frame has settled (`_completion`)."""
        s = self.settings
        if not getattr(s, "cache_enabled", False) or not self.ready or self.batch is not None or self._batching:
            return False
        try:
            if self._name_needed():
                return False
            book, model, language = self.book_var.get().strip(), self.model_var.get().strip(), self.lang_var.get().strip()
            cache = self.store.peek(book, model, language or "English")
            units = _units(self, image, self._margins_of(image))
            if not units:
                return False
            for u in units:
                hit = cache.lookup(u.fingerprint, u.aspect, s.fingerprint_max_distance)
                if hit is None or hit[0].incomplete:
                    return False
        except Exception:  # noqa: BLE001 - not known: the page settles first, as ever
            return False
        return True

    def _completes(self) -> bool:
        """Whether a page job completes a page the cache holds from what it reads (regions the cache has no bubble for
        read and translated): in translator mode, but not for a book a whole-book run finished reading in this session
        (`_run_read`: the run read every region of its pages)."""
        if self.role_var.get() != "translator":
            return False
        book, model, language = self.book_var.get().strip(), self.model_var.get().strip(), self.lang_var.get().strip()
        run = getattr(self, "_run_read", ("", "", ""))
        return (run[0], run[1], run[2] or "English") != (book, model, language or "English")

    def _take_at_once(self, hwnd: int, image: Image.Image, thumb: np.ndarray, frame_detail: np.ndarray,
                      operation: bool = False, shown: bool = True) -> bool:
        """A changed frame whose page the cache holds whole (`_all_cached`) taken at once, without the wait for it to
        settle (follow = "events"), drawn from the cache alone, then looked at every FOLLOW_STEP_MS until RECHECK_MS
        after ("recheck" with `Operation.fast_until`): a sharper frame of it - a viewer that draws a soft picture first
        - is read again (`_retake`) and takes the soft one's place on the page, another page is followed in turn. In
        translator mode (`_completes`) the page is completed from a frame of it once that has settled (`_completion`):
        a frame still on its way is read for nothing. A frame not *shown* yet becomes the live frame without being
        drawn: the page goes from the old page's translation to the new one's, not by way of the untranslated page
        (drawing a full-screen frame took some 40 ms, measured). False when the page is not wholly in the cache (then
        it settles first, as ever), and for a soft picture of a viewer that draws a page soft first (`_looks_soft`):
        the page is taken at once on its sharp frame as that comes, or as it settles. What the cache held was lettered
        where the soft picture let its bubbles be found: on the browser-type stand-in viewer a quarter of them (11 of
        44 over 4 pages), 2-25 px (median 10) from where the sharp picture has them, and that left the page as the
        sharp picture came, for 0.2-1.6 s until it was read; the soft picture stays 0.15-0.45 s there."""
        if not self._all_cached(image) or self._looks_soft(image):
            return False
        if not shown:
            self._quiet_live(image, thumb)
        complete = self._completes()
        took = self._take(image, thumb, frame_detail, operation=operation, complete=False if complete else None)
        if took != "started" and not shown:
            self._redisplay()  # nothing started: the turned page shows as it is
        if took == "started":
            f = self._following
            if complete and f.taken is not None:
                f.taken.complete = True
            self._begin_follow(hwnd, None, phase="recheck", operation=operation, fast=True)
        return True

    def _auto_tick(self) -> None:
        """The live view's heartbeat, started once by the window and then by itself: every auto_interval_ms with
        follow = "poll", every FOLLOW_STEP_MS with "events" (`_beat`)."""
        delay = self.settings.auto_interval_ms
        try:
            delay = self._beat()
        finally:
            self.after(delay, self._auto_tick)

    def _beat(self) -> int:
        """One heartbeat: Windows' notes taken in (`_take_notes`) and what `follow_decision` says done; while TASlation
        is in front the viewer kept directly under its window, and a viewer hidden wholly that drew no frame of a page
        key handed on to it said in the status line (`order.beat`). Returns the ms to the next heartbeat."""
        f = self._follower()
        self._watch_beside()
        order.beat(self)
        if f.mode != "events":
            if not self._black_beat():
                self._tick()
            return self.settings.auto_interval_ms
        self._take_notes(f)
        if self._black_beat():
            return FOLLOW_STEP_MS
        now = time.monotonic()
        self._note_input(f, now)
        interval = self.settings.auto_interval_ms / 1000
        count = self._frame_count() if f.owner == "viewer" and f.op is None else None
        frame_new = count is not None and count != f.polled and now - f.last_poll >= FRAME_GAP_MS / 1000 - 0.002
        action = follow_decision(f.mode, f.owner, following=f.op is not None,
                                 look_due=f.look_at is not None and now >= f.look_at,
                                 poll_due=now - f.last_poll >= interval - 0.002, unseen=f.unseen, frame_new=frame_new)
        if action == "look":
            f.look_at = None
            self._look()
            f.last_poll = time.monotonic()
        elif action == "poll":
            self._poll()
            f.last_poll = time.monotonic()  # as before: the next one auto_interval_ms after this one is done
        if f.owner == "viewer" and f.op is None and count is not None:
            return FRAME_STEP_MS  # its frames counted: a new one is captured at once
        due = f.last_poll + interval - time.monotonic()  # the viewer in front: the next poll on time, as before
        if f.owner == "viewer" and f.op is None and 0 < due < FOLLOW_STEP_MS / 1000:
            return max(1, round(due * 1000))
        return FOLLOW_STEP_MS

    def _frame_count(self) -> int | None:
        """The viewer's frame count (`capture.frame_count`: the capture's frame events), None without them. A count
        that has not moved since the last capture says the viewer still showed that picture as it was read
        (`Look.until`: the moment before)."""
        win = self.selected
        if win is None:
            return None
        before = time.monotonic()
        try:
            count = frame_count(win.hwnd)
        except Exception:  # noqa: BLE001 - no count: polled as without frame events
            return None
        look = getattr(self, "_look_now", None)
        if look is not None and count is not None and look.seq is not None and count == look.seq:
            look.until = max(look.until, before)
        return count

    def _tick(self) -> None:
        """Follow = "poll": the capture of every auto_interval_ms (`_poll`). Follow = "events": the viewer looked at
        once, now (`_look`) - also what a request that waited for the models or for a job does (`_run_queued`)."""
        if self._follows_events():
            self._look()
        else:
            self._poll()

    def _poll(self) -> None:
        """Every auto_interval_ms (follow = "poll"; with "events" while the viewer itself is in front, and at each new
        frame it draws): the viewer's frame, captured once, goes on the page when it changed (the live view; with
        "events" while a page job runs, `_look_over_job`'s, and with "poll" `_watch_page`'s, every auto_interval_ms),
        and Auto translates it once it is a new page that has settled (alike on two ticks); a page that
        settles while the models load waits for them. A blank frame changes nothing - it is neither shown nor
        remembered - so the page is looked at again as soon as the viewer draws it. With "events" a page taken lately
        that comes again sharper is read again (`_check_sharper`), and a new page is followed at once until it settles
        (`_begin_follow`), or taken at once when the cache holds all of it (`_take_at_once`)."""
        win = self.selected
        beside = reads_beside(self)  # (a run that translates: the window follows the viewer as without one)
        try:
            if win is None or self._black_open():
                return
            if (self.busy or self.batch is not None) and not beside:
                if (self.batch is None and not self._batching and self._follows_events()
                        and window_exists(win.hwnd) and self._viewer_shows_book(win)):
                    self._following.polled = self._frame_count()  # (before the capture, as below)
                    self._look_over_job(win)  # a page job runs: its page watched at each new frame
                return
            if not window_exists(win.hwnd):
                self._viewer_gone()
                return
            if not self._viewer_shows_book(win):
                return
            auto = bool(self.auto_var.get()) or beside
            events = self._follows_events()
            if events:
                self._following.polled = self._frame_count()  # (before the capture: a frame that comes during it is new)
            image = self._capture(win.hwnd)
            thumb = _thumb(self, image)
            if self._drew_nothing(thumb):  # one flat colour, or black: the viewer drew nothing
                return
            self._show_live(image, thumb)
            if events:
                self._following.seen = thumb
                if self._check_sharper(image, thumb):
                    return
            if not auto:
                return
            if events:
                if self._auto_last is None or frames_differ(self._auto_last, thumb):  # a new page: followed at once
                    frame_detail = _detail(self, image, self._area_box(image))
                    if not self._take_at_once(win.hwnd, image, thumb, frame_detail):
                        self._begin_follow(win.hwnd, None, phase="settle", last=thumb, last_detail=frame_detail,
                                           image=image)
                return
            if self._auto_last is None or frames_differ(self._auto_last, thumb):
                if self._auto_candidate is not None and not frames_differ(self._auto_candidate, thumb, 0.5):
                    if not self.ready:
                        self._queue("auto")  # taken as soon as the models are loaded
                        return
                    self._auto_last = thumb
                    self._auto_candidate = None
                    if beside:
                        self._beside_page(image, thumb)
                    else:
                        self._on_new_page(image, thumb)
                else:
                    self._auto_candidate = thumb
            else:
                self._auto_candidate = None
        except CaptureError as e:
            self._capture_failed(e)

    def _auto_switched(self) -> None:
        """The Auto box's value was set (a trace on it, `App._build_ui`). A whole-book run turns Auto off as it starts
        and on again as it ends when it was on (`jobs._start_batch`, `_batch_done`: the run reads each page the reader
        turns): the first time a session, the run's first line says so (`RUN_AUTO_OFF`, once the run has said its
        own). The reader's own clicks on the box, and Auto put back, say nothing."""
        if getattr(self, "_run_auto_told", False) or not getattr(self, "_batching", False):
            return
        if self.auto_var.get() or not getattr(self, "_auto_before_batch", None):
            return
        self._run_auto_told = True
        self.after_idle(lambda: self._batching and self.say(RUN_AUTO_OFF))

    def _viewer_shows_book(self, win: Any) -> bool:
        """Whether the viewer's window shows the book (a browser window shows its active tab; a minimised window,
        browser or not, shows nothing: it is not restored again by itself, only when the viewer is chosen). While it
        does not: the waiting line, once, with Auto on; once it does again, the viewer's line."""
        if window_minimised(win.hwnd) or not self._book_in_front():
            if self.auto_var.get() and not self._waiting:
                self._waiting = True
                self._say_waiting()
            return False
        if self._waiting:
            self._waiting = False
            self.say("Viewer: {title}", title=win.title)
        return True

    def _say_waiting(self) -> None:
        """The line while the viewer's window is minimised (a browser's too: its frames are blank then), or shows
        another tab of the browser; for a viewer that is no browser (its title changing with every page never makes
        it wait: `capture.still_the_book`), while its window is hidden or minimised."""
        win = self.selected
        if win is not None and is_browser_class(win.class_name) and window_minimised(win.hwnd):
            self.say(BROWSER_MINIMISED)
            return
        if win is not None and not is_browser_class(win.class_name):
            self.say("Waiting: the viewer's window is hidden or minimised; bring it back.")
            return
        self.say("Waiting: the browser shows another tab. Bring the book's tab back, or drag that tab out into a window of its own.")

    # ------------------------------------------------------------------ the capture
    def _capture(self, hwnd: int) -> Image.Image:
        """The viewer's frame. Behind the full screen the screen shows this window, so there only a frame the
        viewer draws itself is taken; a blank one, or none, puts a message on the page instead (CaptureError). In
        the normal window a viewer that draws nothing is copied from the screen instead, unless the screen there
        shows part of TASlation - a picture of itself: then ViewerCovered, and the last good frame stays. A blank
        frame behind other windows is looked at raised, once (`_blank_behind`): a viewer whose frames are coming
        shows a blank page then, and that is no failure. A blank frame while TASlation is giving the window a new size
        is that change on its way (`_resizing`): it says nothing of the viewer, and nothing of the page. The frame
        taken is remembered with the viewer's frame count before it (`_last_frame`), and the look with when it began
        (`Look`: the wait for a page started early is counted from it, and its job told of its frame, `_frame_seen`)."""
        self._captured = None
        looked = time.monotonic()
        try:
            seq = frame_count(hwnd)
        except Exception:  # noqa: BLE001 - not counted
            seq = None
        image = self._capture_frame(hwnd, seq)
        self._look_now = Look(hwnd, looked, seq, image, looked)
        return image

    def _capture_frame(self, hwnd: int, seq: int | None) -> Image.Image:
        """`_capture`'s capture itself (*seq*: the viewer's frame count before it)."""
        if self.reading:
            try:
                image = capture_window(hwnd, allow_screen_fallback=False)
                _captured_facts(self, hwnd, seq, image)  # (the very bytes of the capture before: worked out once)
                if _blank(self, image) and self._blank_behind(hwnd):
                    raise CaptureError("the viewer gives no picture behind the full screen")
            except CaptureError:
                self._set_viewer_hidden(True)
                raise
            self._set_viewer_hidden(False)
        else:
            covered = self._covers_viewer(hwnd)
            image = capture_window(hwnd, allow_screen_fallback=not covered)
            _captured_facts(self, hwnd, seq, image)
            if covered and _blank(self, image) and self._blank_behind(hwnd):
                raise ViewerCovered("the viewer draws nothing behind TASlation")
            self._set_covered(False)
        black = self._see_black(hwnd, image)
        if _blank(self, image):
            if self._resizing():
                return image
        else:
            if getattr(self, "_blank_looked", False) and getattr(self, "_raised", None) is not None:
                self._raise_helped(hwnd)
            self._blank_looked = False
            self._blank_since = None
        if black:
            return image  # no page in it
        # Every frame of the window passes here, before the capture area (margins) and the pipeline see it: with no
        # area of the reader's, the page panel found in it becomes the capture area.
        self._find_page(image)
        if seq is not None:
            self._captured = (hwnd, seq, image)
        return image

    def _last_frame(self, hwnd: int, seq: int | None) -> Image.Image | None:
        """The frame `_capture` took last of the window *hwnd*, when the viewer has drawn none since (*seq*: its frame
        count now, the same as before that capture): capturing it again would give the same picture. None else."""
        captured = getattr(self, "_captured", None)
        if captured is None or seq is None or captured[0] != hwnd or captured[1] != seq:
            return None
        return captured[2]

    def _blank_behind(self, hwnd: int) -> bool:
        """A blank frame of the viewer: whether it stands for a viewer that draws nothing. Never while its window is
        being given a new size (`_resizing`). The viewer is raised for a look once a spell of blank frames that has
        lasted (`_blank_lasted`), and the frames that come then tell; before and after that a viewer whose frames are
        coming is taken at its word (a blank page)."""
        if self._resizing():
            return False
        if not getattr(self, "_blank_looked", False) and self._blank_lasted(hwnd) and self._raise_viewer(hwnd):
            self._blank_looked = True
            return True
        return not frames_come(hwnd)

    def _blank_lasted(self, hwnd: int) -> bool:
        """Whether the viewer's frame has stayed blank for page_turn_wait_ms with its window's size stable: a window
        that was resized gives a black frame for a moment, and a change of its size starts the wait over."""
        now, size = time.monotonic(), self._window_size(hwnd)
        since = getattr(self, "_blank_since", None)
        if since is None or since[1] != size:
            self._blank_since = (now, size)
            return False
        return now - since[0] >= self.settings.page_turn_wait_ms / 1000

    def _window_size(self, hwnd: int) -> tuple[int, int] | None:
        """The size of the viewer's window (None: it cannot be told)."""
        try:
            left, top, right, bottom = window_rect(hwnd)
        except CaptureError:
            return None
        return right - left, bottom - top

    def _resizing(self) -> bool:
        """Whether TASlation is waiting for the viewer's window to take a new size and settle (`_enlarge_first`): its
        frames meanwhile are of the change, and nothing is concluded from them."""
        waiting = getattr(self, "_enlarging", None)
        return waiting is not None and waiting.get("enlarged") is not None

    def _resize_begins(self) -> None:
        """TASlation is about to wait for the viewer's window to take a new size: what was seen of the frames before it
        says nothing of those to come (the page taken, a sharper frame of it awaited, a spell of blank frames)."""
        self._blank_since, self._blank_looked = None, False
        f = getattr(self, "_following", None)
        if f is not None:
            f.taken = f.retake = None

    def _look_afresh(self, frame: Image.Image | None = None, thumb: np.ndarray | None = None) -> None:
        """The viewer's window has taken its new size: *frame*, the first settled one of that size (None: none could be
        had), goes on the page, and the viewer is looked at at once and until a frame of it is on the page, whoever is
        in front, as a viewer just chosen is (`Following.unseen`): nothing else would notice while neither window is in
        front, and Auto's first page goes on from that look. With follow = "poll" the ticks go on by themselves."""
        self._blank_since = None
        if frame is not None:
            self._show_live(frame, thumb)
        if self._follows_events():
            f = self._following
            f.seen = thumb
            f.look_at, f.unseen = 0.0, True

    def _forget_page_area(self) -> None:
        """No frame of the viewer's new size has come: the page panels found in the frames of the old size go, and
        with them the area they gave (the capture area is the new size's own: `_apply_found_margins`)."""
        if self.selected is not None:
            key = viewer_key(self.selected)
            self._page_areas.pop(key, None)
            getattr(self, "_inner_areas", {}).pop(key, None)

    def _raise_viewer(self, hwnd: int) -> bool:
        """The viewer, behind other windows, raised for a look (`capture.raise_window`: no key, no change of the
        foreground) for page_turn_wait_ms and settle_ms; the frames meanwhile go on as ever, this does not wait.
        Whether it was raised. Never while its window is being given a new size (`_resizing`)."""
        if getattr(self, "_raised", None) is not None or self._resizing() or not behind_others(hwnd):
            return False
        self._raised = raise_window(hwnd)
        if self._raised is None:
            return False
        self._raised_size = self._window_size(hwnd)
        self._raised_job = self.after(self.settings.page_turn_wait_ms + self.settings.settle_ms, self._lower_viewer)
        return True

    def _lower_viewer(self) -> None:
        """The viewer raised for a look back in its place."""
        raised, self._raised = getattr(self, "_raised", None), None
        if raised is None:
            return
        try:
            self.after_cancel(self._raised_job)
        except tk.TclError:
            pass
        lower_window(raised)

    def _raise_helped(self, hwnd: int) -> None:
        """Raised, the viewer showed what it did not draw behind the others: it draws nothing while covered
        (`_note_covered`). A new size of its window since it was raised explains the new frame as well, and nothing is
        concluded."""
        size = getattr(self, "_raised_size", None)
        if self._resizing() or (size is not None and size != self._window_size(hwnd)):
            return
        self._note_covered(hwnd, False)

    def _draws_covered(self, hwnd: int) -> bool | None:
        """Whether the viewer *hwnd* goes on drawing while other windows hide it. A browser follows the published rule
        of Chromium and Firefox, asked as the windows lie now: it stops only under windows that hide what lies under
        them (`capture.covered_by_opaque`; TASlation's own window at WINDOW_ALPHA hides nothing so). Any other viewer:
        as this session saw it (`_note_covered`), else as a session before saw it (its profile's "while_covered":
        `pagekeys.Profiles.covered_for`). None: not known yet."""
        if window_class(hwnd) in BROWSER_CLASSES:
            return not covered_by_opaque(hwnd)
        seen = getattr(self, "_covered_seen", {})
        if hwnd in seen:
            return seen[hwnd]
        win, profiles = getattr(self, "selected", None), getattr(self, "profiles", None)
        if win is None or getattr(win, "hwnd", None) != hwnd or profiles is None:
            return None
        try:
            return profiles.covered_for(win)
        except Exception:  # noqa: BLE001 - a profile that cannot be read says nothing
            return None

    def _note_covered(self, hwnd: int, draws: bool) -> None:
        """What was seen of the viewer *hwnd* while other windows hid it: frames came (*draws*), or came only once it
        was raised (`_raise_helped`). Kept for the session and in the viewer's profile ("while_covered"), so that a
        later session does not find it out again at its first key; a viewer that draws nothing so is raised before
        each key from then on (`_raise_for_key`), and the reader is told, once. A browser follows the published rule
        instead (`_draws_covered`), and nothing is kept for it."""
        if window_class(hwnd) in BROWSER_CLASSES:
            return
        seen = self.__dict__.setdefault("_covered_seen", {})
        known = seen.get(hwnd)
        seen[hwnd] = draws
        win, profiles = getattr(self, "selected", None), getattr(self, "profiles", None)
        if win is not None and getattr(win, "hwnd", None) == hwnd and profiles is not None:
            try:
                profiles.set_covered(win, draws)
            except Exception:  # noqa: BLE001 - kept for the session alone
                pass
        if not draws and known is not False:
            self.say("This viewer draws nothing while it is covered: from now on it comes to the front for a moment at each page.")

    def _learned(self, hwnd: int, real: bool, posted: bool) -> None:
        """A key turned the page of the viewer *hwnd* (`pagekeys.KeyWays.learned`: *real*, pressed for real after a
        posted one did nothing, else *posted*). Kept in the viewer's profile too ("key_way"), so that a later session
        presses its first key the way that works at once: a viewer that ignores posted keys made the first key wait
        page_turn_wait_ms. A browser always gets real presses, and nothing is kept for it."""
        key_ways(self).learned(hwnd, real, posted)
        if not (real or posted) or window_class(hwnd) in BROWSER_CLASSES:
            return
        win, profiles = getattr(self, "selected", None), getattr(self, "profiles", None)
        if win is not None and getattr(win, "hwnd", None) == hwnd and profiles is not None:
            try:
                profiles.set_key_way(win, "real" if real else "posted")
            except Exception:  # noqa: BLE001 - kept for the session alone
                pass

    def _raise_for_key(self, hwnd: int) -> None:
        """Before a key passed on: a viewer that draws nothing while covered is raised first (`_draws_covered`: one
        seen so, in this session or a session before, or a browser that windows hiding what lies under them cover).
        A viewer that draws on, or one not known yet, is not raised: a browser under TASlation's own window at
        WINDOW_ALPHA goes on drawing, and raised for page_turn_wait_ms + settle_ms at every key it came over
        TASlation's page each time for nothing; one not known is raised for a look only when its frame does not
        change (`_await_change`)."""
        if self._draws_covered(hwnd) is False:
            self._raise_viewer(hwnd)

    def _look_raised(self, hwnd: int) -> bool:
        """Whether a frame that did not change after a key is worth a look with the viewer raised before anything is
        concluded from it: when other windows hide the viewer wholly (`capture.fully_covered`; one partly in sight
        draws as one in front does) and it is not known to draw so (`_draws_covered`)."""
        return self._draws_covered(hwnd) is not True and fully_covered(hwnd)

    def _seen_turn(self, hwnd: int, raised: bool, pressed: bool) -> None:
        """The page of the viewer *hwnd* turned after a key: what that shows of how it draws while covered. Raised for
        a look (*raised*) with the posted key, it showed what it had not drawn behind the others (`_raise_helped`);
        raised and then *pressed* for real, the press is what turned it, and nothing is concluded. Not raised at all
        while other windows hid it wholly, it draws so (`_note_covered`), when that was not known yet."""
        if raised:
            if not pressed:
                self._raise_helped(hwnd)
            return
        if (getattr(self, "_raised", None) is None and self._draws_covered(hwnd) is None
                and fully_covered(hwnd)):
            self._note_covered(hwnd, True)

    def _learn_covered(self, hwnd: int, done: Any = None) -> None:
        """Whether a viewer just chosen draws while other windows hide it wholly, found out with no key: it is asked to
        paint itself anew (`capture.ask_repaint`: what Windows asks of a window that another one moved off), and a
        frame of it within COVERED_PROBE_MS says it draws so. When none comes it is raised for a look
        (`_raise_viewer`) and asked again; a frame then says it draws only so. Either is kept (`_note_covered`); no
        frame either way says nothing. Nothing is asked of a viewer not hidden wholly (it draws for the eye then),
        of a browser (the published rule), of one known already, or during a run or a resize. *done* is called
        after, either way."""
        def finish() -> None:
            if done is not None:
                done()

        selected = getattr(self, "selected", None)
        if (not IS_WINDOWS or selected is None or getattr(selected, "hwnd", None) != hwnd
                or self._draws_covered(hwnd) is not None or in_a_run(self) or self._resizing()
                or getattr(self, "_raised", None) is not None or not fully_covered(hwnd)):
            finish()
            return
        seq = self._frame_count()
        if seq is None:  # no capture session with a frame yet: one is had first
            try:
                self._capture(hwnd)
            except CaptureError:
                pass
            seq = self._frame_count()
            if seq is None:
                finish()
                return
        ask_repaint(hwnd)
        self.after(FRAME_STEP_MS, lambda: self._probe_covered(hwnd, seq, time.monotonic(), False, finish))

    def _probe_covered(self, hwnd: int, seq: int, started: float, raised: bool, finish: Any) -> None:
        """One step of `_learn_covered`: every FRAME_STEP_MS until COVERED_PROBE_MS passed, a fresh frame of the viewer
        awaited (`capture.fresh_frame`: newer than frame *seq*, and of the window's present size). *raised*: since
        it was raised for a look."""
        selected = getattr(self, "selected", None)
        gone = selected is None or getattr(selected, "hwnd", None) != hwnd or not window_exists(hwnd)
        if gone or in_a_run(self) or self._resizing():
            if raised:
                self._lower_viewer()
            finish()
            return
        if fresh_frame(hwnd, seq):
            if raised:
                self._lower_viewer()
            self._note_covered(hwnd, not raised)
            finish()
            return
        if time.monotonic() - started < COVERED_PROBE_MS / 1000:
            self.after(FRAME_STEP_MS, lambda: self._probe_covered(hwnd, seq, started, raised, finish))
            return
        if not raised and self._raise_viewer(hwnd):
            seq = self._frame_count() or seq
            ask_repaint(hwnd)
            self.after(FRAME_STEP_MS, lambda: self._probe_covered(hwnd, seq, time.monotonic(), True, finish))
            return
        if raised:
            self._lower_viewer()
        finish()  # no frame either way (a window that draws only when its picture changes): nothing is kept

    def _covers_viewer(self, hwnd: int) -> bool:
        """Whether one of this program's windows lies over the viewer's place on the screen, where a copy of the
        screen would show TASlation instead of the viewer."""
        own = self._own_rects()
        if not own:
            return False
        try:
            x, y, w, h = client_rect_on_screen(hwnd)
        except CaptureError:
            return False
        return screen_shows_own((x, y, x + w, y + h), own)

    def _own_rects(self) -> list[tuple[int, int, int, int]]:
        """Where this program's windows are on the screen: the main window and the dialogs that are open."""
        if not IS_WINDOWS:
            return []
        rects = []
        for widget in (self, *self.winfo_children()):
            if not isinstance(widget, (tk.Tk, tk.Toplevel)):
                continue
            try:
                if widget.winfo_viewable():
                    rects.append(window_rect(widget.winfo_id()))
            except (tk.TclError, CaptureError):
                pass
        return rects

    def _set_covered(self, covered: bool) -> None:
        """The viewer draws nothing behind TASlation (or draws again): the page keeps the last good frame, and a band
        over it in the busy badge's style and the status bar say what to do; when the viewer draws again both go (the
        status line gives way to the normal window's own, unless something else was said meanwhile). Meanwhile the
        viewer is looked at every auto_interval_ms (with follow = "events" too: nothing else would notice)."""
        if covered == self._covered:
            return
        self._covered = covered
        if covered:
            self.say("The viewer stopped drawing because TASlation covers it completely. Un-maximise TASlation, or move it so that a strip of the viewer stays visible.")
            self._covered_key = self._status_key
            self.canvas.set_banner(_(self._covered_key))
            if self._follows_events():
                self._following.look_at = time.monotonic() + self.settings.auto_interval_ms / 1000
            return
        self.canvas.set_banner("")
        if self._status_key is not None and self._status_key == getattr(self, "_covered_key", None):
            self._normal_status()

    def _set_viewer_hidden(self, hidden: bool) -> None:
        if hidden != self._viewer_hidden:
            self._viewer_hidden = hidden
            self._redisplay()

    def _capture_failed(self, error: CaptureError) -> None:
        if isinstance(error, ViewerCovered):
            self._set_covered(True)
        elif not self.reading:  # the full screen says so on the page
            self.say(error.message if error.message.code != "viewer.error" else Message("viewer.gone"))

    # ------------------------------------------------------------------ after a page turn
    def _follow_change(self, hwnd: int, reference: Any, key: str, started: float, retried: bool = False,
                       stirred: bool = False, prev: Any = None, pressed: bool = False, raised: bool = False,
                       seq: int | None = None) -> None:
        """After TASlation passed a key (*key*; "" for a click) on to the viewer: its frame is followed until it
        changes from *reference*. Follow = "events": at FOLLOW_STEP_MS, then until it settles, the page taken at once
        and looked at again RECHECK_MS later (`_begin_follow`). Follow = "poll": every 120 ms until it changes, shown
        at once; with Auto off the page is translated once it settled (with Auto on the ticks take it). As with
        "events" (`_await_change`): a key that changed nothing at all for page_turn_wait_ms is pressed for real, once
        - any change of the frame (*stirred*; *prev*: the frame before) says the viewer took it, and the page is
        waited for up to FOLLOW_WAITS times as long -, and a page that turns twice soon after that press is said
        (`_second_turn`). Before that, a viewer behind other windows is raised for a look, as long again (*raised*:
        `_raise_viewer`), when other windows hide it wholly and it is not known to draw so (`_look_raised`): it may
        have turned without drawing. *retried*: a key pressed for real from the start (`pagekeys.KeyWays`): none follows it. Which way the
        page turned is noted for the next keys, and whether the viewer drew while covered (`_seen_turn`). *seq*: the
        viewer's frame count before the operation (follow = "events": `_begin_follow`). During a run only the change
        is followed, as with "events": the run takes the page by itself."""
        if self._follows_events() or in_a_run(self):
            self._begin_follow(hwnd, reference, key, retried, seq=seq)
            return
        try:
            image = self._capture(hwnd)
        except CaptureError:
            return
        thumb = _thumb(self, image)
        now = time.monotonic()
        if frames_differ(reference, thumb):
            self._seen_turn(hwnd, raised, pressed)
            self._learned(hwnd, pressed, bool(key) and not retried)
            self._auto_candidate = None
            self._show_live(image, thumb)  # the turned page shows at once
            if not self.auto_var.get():
                self._auto_last = thumb
                self.after(self.settings.settle_ms, lambda: self._translate_after_turn(hwnd))
            if pressed:  # pressed for real: does the page turn once more, soon?
                self.after(120, lambda: self._second_turn(hwnd, key, now + TWO_TURNS_S, thumb))
            return
        stirred = stirred or frames_differ(prev if prev is not None else reference, thumb, LIVE_CHANGE)
        wait = self.settings.page_turn_wait_ms / 1000
        if (not raised and not stirred and now - started >= wait and self._look_raised(hwnd)
                and self._raise_viewer(hwnd)):
            self.after(120, lambda: self._follow_change(hwnd, reference, key, now, retried, stirred, thumb, pressed,
                                                        True))
            return
        if not retried and not stirred and now - started >= wait:
            # The posted key changed nothing at all (a window that ignores posted keys): the person's key pressed for
            # real, once (`press_briefly`: the foreground handed over and back, no ALT tap).
            press_briefly(hwnd, key)
            self._follow_change(hwnd, reference, key, time.monotonic(), retried=True, prev=thumb, pressed=True)
            return
        if now - started > (FOLLOW_WAITS * wait if stirred else wait):
            if not stirred:
                self.say("The viewer did not change (end of book, or the key means nothing there).")
            return
        self.after(120, lambda: self._follow_change(hwnd, reference, key, started, retried, stirred, thumb, pressed,
                                                    raised))

    def _second_turn(self, hwnd: int, key: str, until: float, last: Any, calm: Any = None) -> None:
        """Follow = "poll", after a key pressed for real turned the page: until *until* (TWO_TURNS_S later) its frame,
        once it has settled (*calm*: two frames 120 ms apart alike), is watched for turning once more - the posted
        key had arrived after all, and the viewer turned two pages (`_say_two_turns`)."""
        try:
            thumb = _thumb(self, self._capture(hwnd))
        except CaptureError:
            return
        if calm is not None and frames_differ(calm, thumb):
            self._say_two_turns(key)
            return
        if calm is None and not frames_differ(last, thumb, 0.5):
            calm = thumb  # the first turn has settled
        if time.monotonic() < until:
            self.after(120, lambda: self._second_turn(hwnd, key, until, thumb, calm))

    def _translate_after_turn(self, hwnd: int) -> None:
        if self.busy or not self.ready or not self._enlarge_first(self.translate_now):
            return
        try:
            image = self._capture(hwnd)
        except CaptureError as e:
            self._capture_failed(e)
            return
        thumb = _thumb(self, image)
        self._auto_last = thumb
        self._show_live(image, thumb)
        self._start_translate(image, thumb=thumb)

    # ------------------------------------------------------------------ following the viewer by events
    def _follower(self) -> Following:
        """How the window follows the viewer, made at the first heartbeat. With follow = "events" Windows' window
        events are hooked (`capture.WindowEvents`: the window in front; the viewer's window renamed, moved or
        closed) and the window's own moves watched (`_watch_own_window`); a click passed on to the viewer is
        followed as a key is (translator mode's `_forward_click`). Without the hooks (not Windows, a hook that cannot
        be set) and with follow = "poll", the viewer is polled as before."""
        f = getattr(self, "_following", None)
        if f is not None:
            return f
        f = self._following = Following()
        if getattr(self.settings, "follow", "poll") != "events":
            return f
        events = WindowEvents.start()
        if events is None:
            return f
        if not events.watch(self.selected.hwnd if self.selected is not None else None):
            events.close()
            return f
        f.mode, f.events = "events", events
        f.owner = foreground_owner(events.front, events.viewer)
        f.look_at = 0.0  # the viewer as it is now, whoever is in front (`Following.unseen`)
        f.size = self._window_size(events.viewer) if events.viewer else None  # (its notes that it moved tell from it)
        self._watch_own_window()
        return f

    def _follows_events(self) -> bool:
        """Whether the viewer is followed by events (follow = "events", the hooks set)."""
        f = getattr(self, "_following", None)
        return f is not None and f.mode == "events"

    def _stop_events(self, f: Following) -> None:
        """Back to polling, the hooks removed."""
        self._end_follow()
        if f.events is not None:
            f.events.close()
        f.events, f.mode = None, "poll"

    def _follow_viewer(self) -> None:
        """A viewer chosen (follow = "events"): its window is watched in place of the one before and looked at at
        once, whoever is in front - and again every auto_interval_ms while no frame of it could be shown yet (a look
        that fails says so as always: covered, blank) -, then followed by the usual rules (`follow_decision`); when
        its hooks cannot be set, the viewer is polled as before."""
        f = getattr(self, "_following", None)
        if f is None or f.mode != "events":
            return
        self._end_follow()
        f.seen = f.taken = f.retake = None
        if not f.events.watch(self.selected.hwnd if self.selected is not None else None):
            self._stop_events(f)
            return
        f.owner = foreground_owner(foreground_window(), f.events.viewer)
        f.look_at, f.unseen = 0.0, True
        f.moved, f.size = None, self._window_size(f.events.viewer) if f.events.viewer else None

    def _look_soon(self) -> None:
        """Follow = "events": the viewer looked at at the next heartbeat (the capture area changed: Auto reads the
        page again, as the next ticks do with "poll")."""
        if self._follows_events():
            self._following.look_at = 0.0

    def destroy(self) -> None:
        """The window goes: Windows' window events are unhooked first, so that no note comes in after it."""
        f = getattr(self, "_following", None)
        if f is not None and f.events is not None:
            self._stop_events(f)
        super().destroy()

    def _take_notes(self, f: Following) -> None:
        """Windows' notes since the last heartbeat: who is in front now - a window of TASlation's or the viewer coming
        back to the front is looked at once (and the viewer in front polled) -, the viewer's window renamed (a tab
        switch: is the book in front? looked at once), moved or resized (looked at once it stops: settle_ms after the
        last note, `Following.moved`; and at once as well at the first note of a spell that gives it another size,
        since the capture's first frame of the new size may be all that comes - `wgc.restart` - and a page job on a
        frame of the old size gives way to it as to a turned page, `_look_over_job`: a drag that goes on is not looked
        at), closed."""
        now = time.monotonic()
        settle = self.settings.settle_ms / 1000
        for kind, hwnd in f.events.take():
            if kind == "front":
                owner = foreground_owner(hwnd, f.events.viewer)
                if owner != f.owner:
                    f.owner = owner
                    if owner != "other":
                        f.look_at = now
            elif kind == "renamed":
                f.look_at = now
            elif kind == "moved":
                size = self._window_size(hwnd)
                if f.moved is None and size != f.size:
                    f.look_at = now
                f.moved, f.size = now, size
            elif kind == "closed":
                f.look_at, f.moved = None, None
                self._viewer_gone()
                if self.selected is not None:  # still there for a moment, or a run is on: looked at again
                    f.look_at = now + settle
        if f.moved is not None and now >= f.moved + settle:
            f.moved = None
            f.look_at = now if f.look_at is None else min(f.look_at, now)
        if getattr(self, "_over_on", False):
            self._front_as_it_is(f, now)

    def _front_as_it_is(self, f: Following, now: float) -> None:
        """Over the book (`overbook`, the full screen too): who is in front as Windows has it now, whatever the notes
        said. A click on the window there (WS_EX_NOACTIVATE: the Finished reading button, the page strip) gives a
        note that TASlation came to the front while the viewer keeps the foreground, and no note follows, for nothing
        changed: from the notes alone TASlation would stay "in front" and no page turned in the viewer would be
        followed. As with a note, a window back in front is looked at once."""
        owner = foreground_owner(foreground_window(), f.events.viewer)
        if owner != f.owner:
            f.owner = owner
            if owner != "other":
                f.look_at = now

    def _note_input(self, f: Following, now: float) -> None:
        """TASlation in front: input that came while the pointer is over the viewer's window - Windows scrolls a
        window under the pointer that is not in front, and a viewer may turn its page on the wheel - asks for one look
        at the viewer once it stops (none while it goes on)."""
        if f.owner != "own" or f.events is None or not f.events.viewer:
            return
        tick = last_input()
        if tick == f.last_input:
            return
        f.last_input = tick
        if window_at_pointer() == f.events.viewer:
            f.look_at = now + self.settings.settle_ms / 1000

    def _area_box(self, image: Image.Image) -> tuple[int, int, int, int]:
        """The capture area of *image* (the margins every part of TASlation reads: `_margins_of`)."""
        return area.margins_to_box(self._margins_of(image), image.size)

    def _margins_of(self, image: Image.Image) -> tuple[int, int, int, int]:
        """The capture area (margins) the window reads the viewer's frame *image* by: the margins in force, but for a
        frame of another size than the one a page job reads while that job runs - the viewer's window was given
        another size: the margins in force stay the job's until it is done (`_apply_found_margins`; it is cancelled
        once the frame of the new size has stayed, as for a turned page), and the new size's frames are read by that
        size's own area at once (`_inner_margins`, `_found_margins`: `_find_page` looks at every frame captured), not
        by an area of the old size's. A whole-book run keeps its own area (`page_area.JoinedArea`)."""
        job = getattr(self, "_job_frame", None)
        if job is None or job.size == image.size or not self.busy or in_a_run(self):
            return tuple(self.settings.margins)  # type: ignore[return-value]
        return self._inner_margins(image.size) if self._manual_area else self._found_margins(image.size)

    def _look(self) -> None:
        """Follow = "events": the viewer looked at once - it came back to the front, stopped moving or was renamed,
        the last look failed, the capture area changed, or a request waited for the models or for a job (`_tick`).
        Its frame goes on the page. With Auto on a new page is taken at once when the frame is the one seen last (it
        has settled), else followed until it settles; a sharper frame of a page read from a softer one is read again
        (`_retake`). While the look cannot be had, the viewer is looked at again every auto_interval_ms; while a job
        or the batch runs, once it is done - unless a page job runs and the viewer has turned to a new page meanwhile
        (the wheel over it while TASlation is in front): then the job gives way to it (`_look_over_job`)."""
        f = self._follower()
        win = self.selected
        again = self.settings.auto_interval_ms / 1000
        if win is None or self._black_open():
            return
        beside = reads_beside(self)  # (a run that translates: looked at as without one)
        if (self.batch is not None or self._batching) and not beside:
            f.look_at = time.monotonic() + again  # once the batch is done
            return
        if not window_exists(win.hwnd):
            self._viewer_gone()
            return
        if not self._viewer_shows_book(win):
            return
        if self.busy and not beside:
            self._queue("auto")  # looked at again once the job is done ...
            self._look_over_job(win)  # ... which gives way to a new page in the viewer
            return
        if f.op is not None and f.op.over_job:
            return  # (a page seen while a job ran, followed until it settles: its follow takes it, not two looks)
        if f.op is not None and f.op.phase == "settle" and f.op.turned_at is None and self._early_on() and not beside:
            self._settle_now(f.op)  # (its frame is its follow's to take: started early on it now, a gate of its own)
            return
        try:
            image = self._capture(win.hwnd)
        except CaptureError as e:
            self._capture_failed(e)
            f.look_at = time.monotonic() + again  # again while it lasts (covered, hidden, minimised)
            return
        thumb = _thumb(self, image)
        if self._drew_nothing(thumb):  # the viewer drew nothing: again soon
            f.look_at = time.monotonic() + again
            return
        self._show_live(image, thumb)
        seen, f.seen = f.seen, thumb
        if f.retake is not None:
            if not frames_differ(f.retake.thumb, thumb):
                self._take_retake(image, thumb)
                return
            f.retake = None  # the viewer has moved on
        if not (self.auto_var.get() or beside) or (
                self._auto_last is not None and not frames_differ(self._auto_last, thumb)):
            return
        if seen is not None and not frames_differ(seen, thumb, 0.5):
            self._take(image, thumb)
        else:
            self._begin_follow(win.hwnd, None, phase="settle", last=thumb,
                               last_detail=_detail(self, image, self._area_box(image)), image=image)

    def _settle_now(self, op: Operation) -> None:
        """A look (the models ready, a job gone: `_run_queued`) while *op* follows a frame until it settles: the frame
        is left to *op*, stepped at once, and - no page started early on it yet - started early on the frame there is
        (`Operation.redo`: a gate of its own, kept once the frame has stayed KEEP_SETTLES times settle_ms from the look
        that saw it first). Before, the look took the frame as settled whenever it matched the follow's last capture -
        tens of ms old when the models became ready just after a turn - and the page job on a soft frame then started
        with no gate."""
        if self._early_of(op) is None:
            op.redo = True
        if op.job is not None:
            try:
                self.after_cancel(op.job)
            except tk.TclError:
                pass
        self._next_step(op, 0)

    def _look_over_job(self, win: Any) -> None:
        """A look while a page job runs with Auto on (follow = "events"): at each new frame of the viewer in front
        (`_poll`), and at a look (`_look`: the wheel over the viewer while TASlation is in front). The frame goes on
        the page (`_show_live`): the page filling in while the viewer shows its page, else - one look at another page
        is enough - the viewer's frame as it is, while the job goes on. A frame of another page is followed until it
        settles, as a page turned while no job runs (`_begin_follow`, `Operation.over_job`): once it has stayed as it
        is for LEFT_PAGE_MS (`_settle_s`) it cancels the job, and is started early - a gate of its own - as soon as
        the worker is free of it (`_waits_for_worker`); back on the job's page before that, the follow ends and the
        job goes on as if nothing had happened. A black or blank frame changes nothing (a flash on the focus: the page
        on show stays, and so does the job). A sharper frame of the page the job reads is read again
        (`_check_sharper`). While a job cancelled for a page is on its way out, the frames still go on the page; the
        page is started once the job is gone (by its follow; else `_run_queued`). Nothing is captured while no page job
        runs that the window can cancel or did, nor while a follow looks.

        Before, a look every auto_interval_ms cancelled the job once two looks in a row had found another page
        (`_watch_page`), and the old page's lettering stayed on show until then and the job had gone: 1.1-1.8 s after
        a turn on the browser-type stand-in viewer."""
        runs = self._page_job_runs()
        if not (runs or self._page_job_ends()) or not self.auto_var.get():
            return
        f = self._following
        if f.op is not None:
            return
        try:
            image = self._capture(win.hwnd)
        except CaptureError:
            return  # looked at again at its next frame, or once the job is done
        thumb = _thumb(self, image)
        if self._drew_nothing(thumb):  # the viewer drew nothing
            return
        self._show_live(image, thumb)
        f.seen = thumb
        if not runs:
            return
        if self._on_job_page(image):
            self._check_sharper(image, thumb)
            return
        self._begin_follow(win.hwnd, None, phase="settle", last=thumb,
                           last_detail=_detail(self, image, self._area_box(image)), image=image, over_job=True)

    def _page_job_runs(self) -> bool:
        """Whether a page job runs that the window can cancel (`_cancel_page`)."""
        cancel = getattr(self, "_page_cancel", None)
        return bool(self.busy) and cancel is not None and not cancel.is_set() and self.batch is None

    def _page_job_ends(self) -> bool:
        """Whether a page job the window cancelled (a page turned, Stop) is still on its way out."""
        cancel = getattr(self, "_page_cancel", None)
        return bool(self.busy) and cancel is not None and cancel.is_set() and self.batch is None

    def _on_job_page(self, image: Image.Image) -> bool:
        """Whether the viewer's frame *image* shows the page the running job reads (`_job_frame`; `_shows_page`)."""
        frame = getattr(self, "_job_frame", None)
        return frame is not None and self._shows_page(image, frame)

    def _shows_page(self, image: Image.Image, frame: Image.Image) -> bool:
        """Whether the frame *image* shows the page of the frame *frame*: the very capture, or one of its size whose
        capture area is about the same (`_same_page`'s test)."""
        if image is frame:
            return True
        return image.size == frame.size and not frames_differ(self._area_thumb(frame), self._area_thumb(image))

    def _take(self, image: Image.Image, thumb: np.ndarray, frame_detail: np.ndarray | None = None,
              operation: bool = False, complete: bool | None = None) -> str:
        """A settled frame of the viewer taken as the page (follow = "events"). With Auto on a new page is started at
        once (`_on_new_page`), or - while the models load, a job or the batch runs - as soon as it can be (`_queue`:
        the viewer is looked at again then). With Auto off a page turned by TASlation's own *operation* is translated,
        as before. *complete*: the page job's (`_on_new_page`). Beside a run that translates, a new page is asked of
        the run, whatever Auto says (`_beside_take`). Returns "started", "queued" or "same" (nothing to take)."""
        f = self._following
        if reads_beside(self):
            return self._beside_take(image, thumb, frame_detail)
        if self.auto_var.get():
            if self._auto_last is not None and not frames_differ(self._auto_last, thumb):
                return "same"
            if not self.ready or self.busy or self.batch is not None or self._batching:
                f.taken = None
                self._cancel_page(turned=True)  # the page being read is not on show any more
                self._queue("auto")
                return "queued"
            self._auto_last, self._auto_candidate = thumb, None
            self._mark_taken(image, thumb, frame_detail)
            self._on_new_page(image, thumb, complete=complete)
            return "started"
        if not operation or not self.ready or self.busy or self.batch is not None:
            return "same"
        if not self._enlarge_first(self.translate_now):
            return "same"
        self._auto_last = thumb
        self._mark_taken(image, thumb, frame_detail)
        self._start_translate(image, thumb=thumb, complete=complete)
        return "started"

    def _mark_taken(self, image: Image.Image, thumb: np.ndarray, frame_detail: np.ndarray | None = None) -> None:
        """The page just taken, for the looks after it (a sharper frame of it may come), with the gate its job is
        started with when it is started early (`_early_start`)."""
        f = self._following
        f.retake = None
        if frame_detail is None:
            frame_detail = _detail(self, image, self._area_box(image))
        f.taken = Taken(image, thumb, frame_detail, time.monotonic(), gate=getattr(self, "_early_gate", None))

    def _check_sharper(self, image: Image.Image, thumb: np.ndarray) -> bool:
        """Whether *image* is the page taken lately (within RETAKE_WITHIN_MS) come again sharper; then it is read
        again from it (`_retake`)."""
        f = self._following
        taken = f.taken
        if taken is None or time.monotonic() - taken.at > RETAKE_WITHIN_MS / 1000 or frames_differ(taken.thumb, thumb):
            return False
        frame_detail = _detail(self, image, self._area_box(image))
        if not sharper(taken.detail, frame_detail):
            return False
        self._retake(image, thumb, frame_detail)
        return True

    def _retake(self, image: Image.Image, thumb: np.ndarray, frame_detail: np.ndarray) -> None:
        """The page taken has come sharper (a viewer that draws a soft picture first): it is read from this frame - at
        once when the job on the softer frame is done; else, as no running job can be stopped, once it is (`_queue`;
        `_look` takes it then). A page started early on the softer frame has its confirmation taken back
        (`PageGate.take_back`) where it still can be - its job running, or done within TAKE_BACK_MS of the
        confirmation for a viewer seen to draw soft first -: nothing of that job lasts, put back before the job on
        this frame begins (`Pipeline.decide_kept`), so that this one stores the page."""
        f = self._following
        taken, f.taken = f.taken, None
        soft = taken.frame if taken is not None else None
        if soft is not None:
            self._drew_soft(soft, image)
        if taken is not None and taken.gate is not None and taken.gate.take_back():
            soft = None  # (nothing of the soft frame's job to drop from the cache: `_take_retake`)
        f.retake = Taken(image, thumb, frame_detail, time.monotonic(), soft)
        self._take_retake(image, thumb)

    def _drew_soft(self, soft: Image.Image, sharp: Image.Image) -> None:
        """The viewer chosen has drawn a page soft first: *soft*, then its sharp picture *sharp* (`batch.sharper`). The
        `crispness` of both is kept with the viewer's window, CRISP_KEPT of each at most - what its frames are judged
        by (`_looks_soft`), and the sharp one's with its page (`batch.SharpSeen`); a window chosen anew starts afresh,
        as a whole-book run does (`batch.PageWatch`)."""
        win = self.selected
        if win is None:
            return
        f = self._following
        if f.soft_of != win.hwnd:
            f.soft_of = win.hwnd
            f.soft.clear()
            f.sharp.clear()
            f.sharp_pages.clear()
        f.soft.append(_crisp(self, soft, self._area_box(soft)))
        crisp = _crisp(self, sharp, self._area_box(sharp))
        f.sharp.append(crisp)
        units = _units(self, sharp, self._margins_of(sharp))
        if units:
            f.sharp_pages.note(units[0].fingerprint, sharp.size, crisp)

    def _looks_soft(self, image: Image.Image) -> bool:
        """Whether *image*, a frame of the viewer chosen, is a soft picture of its page by what that viewer has drawn:
        it has drawn a page soft first (`_drew_soft`), and the frame is less crisp than PAGE_SHARP_SHARE of the sharp
        picture it drew of that very page (`batch.SharpSeen`), or its `crispness` is not nearer that of its sharp
        pictures than that of its soft ones (`batch.looks_sharp`, as a whole-book run judges its frames). The page's
        own picture only adds soft frames to those the viewer's pictures find: a soft picture as crisp as
        PAGE_SHARP_SHARE of its page's sharp one stays soft when they call it so. Never so for a viewer not seen to
        draw a page soft first: it pays nothing."""
        if not self._draws_soft_first():
            return False
        f = self._following
        crisp = _crisp(self, image, self._area_box(image))
        units = _units(self, image, self._margins_of(image))
        if units:
            distance = getattr(self.settings, "fingerprint_max_distance", Settings.fingerprint_max_distance)
            if f.sharp_pages.judge(units[0].fingerprint, image.size, crisp, distance) is False:
                return True
        return not looks_sharp(crisp, f.soft, f.sharp)

    def _draws_soft_first(self) -> bool:
        """Whether the viewer chosen has drawn a page soft first (`_drew_soft`)."""
        f = self._following
        win = self.selected
        return win is not None and f.soft_of == win.hwnd and bool(f.soft)

    def _take_retake(self, image: Image.Image, thumb: np.ndarray) -> None:
        """The sharper frame read as the page (`_retake`), once nothing runs: the job on the softer frame is cancelled
        where the window can cancel it (`_cancel_page`: nothing of it reaches the cache), else waited for (`_queue`).
        The page units that job stored anew (as it said, done or stopped after its storing: `_page_stored`) are
        dropped first, so that their bubbles are read again from the sharp picture (nothing older goes: a page unit
        that was in the cache keeps its translations and is only drawn again on the sharp picture; one the job added
        to, a page that lacked some, is put back as it was). A job that said
        nothing of it (none but a stand-in's) is judged by its page: dropped when none of it came from the cache. A
        job started early whose confirmation `_retake` took back leaves nothing at all (no page unit, no line kept for
        reuse, no line drawn by its requests: `pipeline.Provisional`), so nothing is dropped here."""
        f = self._following
        if reads_beside(self):  # beside a run that translates: the sharper frame is asked of the run
            retake, f.retake = f.retake, None
            self._auto_last, self._auto_candidate = thumb, None
            self._mark_taken(image, thumb, retake.detail if retake is not None else None)
            self._beside_page(image, thumb)
            return
        if not self.ready or self.busy or self.batch is not None or self._batching:
            self._cancel_page()
            self._queue("auto")  # `_look` takes it once the job is gone
            return
        retake, f.retake = f.retake, None
        result = self.last_result
        soft = retake.soft if retake is not None else None
        stored = getattr(self, "_stored_by", None)  # (the page units the last page job stored anew, and its frame)
        if soft is not None and stored is not None and _same_picture(stored[0], soft):
            # the job on the soft frame said what it stored anew - done or cancelled after its storing, a spread in
            # part from the cache: those units are dropped (the others were in the cache before it, and stay)
            self._stored_by = None
            if stored[1] and self.pipeline is not None:
                units = [SimpleNamespace(fingerprint=fingerprint, aspect=aspect) for fingerprint, aspect in stored[1]]
                try:
                    self.pipeline.forget_page(SimpleNamespace(units=units))
                    if len(stored) > 2 and stored[2]:  # (an entry the job added to: as it was before the job)
                        self.pipeline.restore_pages(stored[2])
                except Exception:  # noqa: BLE001 - the cache stays as it was; the page is drawn again from it
                    pass
        elif (soft is not None and result is not None and result.cache_misses and not result.cache_hits
                and self.pipeline is not None and result.original.size == soft.size
                and np.array_equal(np.asarray(result.original), np.asarray(soft.convert("RGB")))):
            try:
                self.pipeline.forget_page(result)
            except Exception:  # noqa: BLE001 - the cache stays as it was; the page is drawn again from it
                pass
        self._auto_last, self._auto_candidate = thumb, None
        self._mark_taken(image, thumb, retake.detail if retake is not None else None)
        if self.auto_var.get():
            self._on_new_page(image, thumb)
        else:
            self._start_translate(image, thumb=thumb)

    def _cancel_page(self, turned: bool = False) -> bool:
        """The page translation that runs, cancelled where the window can cancel it (a page job with its own cancel
        event, `_page_cancel`, as Stop cancels it: nothing of it reaches the cache, and no line says it was
        stopped); False when it cannot be (then it is done first, and the page waits for it). *turned*: the viewer
        shows another page - the lines answered by then are kept, the page marked as lacking the rest
        (`pipeline.turn_away`), so that coming back to it asks only for the rest."""
        cancel = getattr(self, "_page_cancel", None)
        if cancel is None or cancel.is_set() or self.batch is not None:
            return False
        self._cancel_why = "page"
        if turned:
            turn_away(cancel)
        cancel.set()
        sync = getattr(self, "_sync_stop", None)
        if sync is not None:
            sync()
        return True

    # ------------------------------------------------------------------ a page started on its first frame (events)
    def _early_on(self) -> bool:
        """Whether a page the cache does not hold is started on its first changed frame (``early_start``, with
        follow = "events"); off, it is started once it has settled, after settle_ms, as before."""
        return bool(getattr(self.settings, "early_start", False)) and self._follows_events()

    def _settle_s(self, op: Operation) -> float:
        """How long *op*'s frame must stay as it is (seconds): for a page started early on it (`_early_start`),
        KEEP_SETTLES times settle_ms - then what its job stores lasts (`_early_confirm`) -, and for a frame of another
        page while a job runs (`Operation.over_job`), before which the job is not cancelled, LEFT_PAGE_MS; else -
        early_start off, a key pressed for real (its two turns are watched for), a page the cache holds, a page that
        could not be started early - settle_ms, as ever."""
        settle_ms = self.settings.settle_ms
        if not self._early_on() or op.turned_at is not None:
            return settle_ms / 1000
        if self._early_of(op) is not None:
            return KEEP_SETTLES * settle_ms / 1000
        return (LEFT_PAGE_MS if op.over_job else settle_ms) / 1000

    def _watched(self, op: Operation) -> bool:
        """Whether *op*, its frames not counted, is looked at every FOLLOW_STEP_MS rather than every settle_ms: a page
        started early on its frame (or to be started again once the worker is free, `Operation.redo`), whose job waits
        before its first request for a look that finds its frame on show (`_frame_seen`), and is dropped by the first
        that finds another."""
        return self._early_on() and op.turned_at is None and (op.redo or op.held_soft or self._early_of(op) is not None)

    def _waits_for_worker(self, op: Operation, now: float) -> bool:
        """Whether *op*'s frame, to be started early once the worker is free (`Operation.redo`; a frame of another
        page than the running job's, `Operation.over_job`, once it has stayed LEFT_PAGE_MS: the job is cancelled
        first), is followed on while a page job holds the worker, rather than taken as settled (`_take`: queued, and
        taken by the look once the job is gone, with no gate): so a frame that has not stayed as it is for KEEP_SETTLES
        times settle_ms is never kept from a job without a gate. Not with early_start off, after a key pressed for
        real, with a whole-book run, nor once the frame has stayed RETAKE_WITHIN_MS (a job that does not end)."""
        if not self._early_on() or op.turned_at is not None or not self.busy:
            return False
        if self.batch is not None or self._batching or reads_beside(self):
            return False
        return now - op.last_at < RETAKE_WITHIN_MS / 1000

    def _frame_seen(self, op: Operation, fresh: bool = False) -> None:
        """The page started early on *op*'s frame, not confirmed yet, told that its frame is on show still
        (`PageGate.seen`, with the last moment the window knew it: `Look.until`), so that its job, waiting before its
        first request for a look after it asked (`PageGate.on_show`), goes on. *fresh*: the capture just taken shows
        the job's frame (no further than SAME_PICTURE from it, none sharper: `_step`); else the capture that did
        (`Early.look`) holds while the viewer has drawn no frame since - its frame count unchanged (`_frame_count`) -,
        and so does another capture taken with that same count."""
        early = self._early_of(op)
        look = getattr(self, "_look_now", None)
        if early is None or look is None or look.hwnd != op.hwnd:
            return
        if fresh:
            early.look = look
        elif early.look is not look:
            if early.look is None or look.seq is None or look.seq != early.look.seq:
                return
            early.look = look  # (captured again, the viewer having drawn no frame since)
        early.gate.seen(look.until)

    def _mark_stayed(self, now: float, thumb: np.ndarray | None = None) -> None:
        """(the recheck) A page confirmed while the frames still changed (``PageGate.settled`` False, `_step`) that a
        look KEEP_SETTLES times settle_ms after its confirmation still finds on show - no new frame since, or the same
        picture (*thumb*) - stayed after all: its page is caught behind the reader once turned past (`backlog`)."""
        taken = self._following.taken
        gate = taken.gate if taken is not None else None
        by = getattr(gate, "settled_by", None)
        if gate is None or getattr(gate, "settled", True) or by is None or now < by:
            return
        if thumb is None or not frames_differ(taken.thumb, thumb):
            gate.settled = True

    def _recheck_after(self, op: Operation, now: float) -> None:
        """A page started early, confirmed as *op* settled (`_early_confirm`): looked at once more RECHECK_MS later -
        with the viewer's frames counted, at each new frame until then, so that a sharper frame or another page that
        comes after the confirmation is seen as it comes."""
        op.phase = "recheck"
        if op.seq is not None:
            op.fast_until = now + RECHECK_MS / 1000
            self._next_step(op, FRAME_STEP_MS)
        else:
            self._next_step(op, RECHECK_MS)

    def _starts_book(self, image: Image.Image) -> bool:
        """Whether Auto's `_on_new_page` would do more with *image* than translate it: start the book (the start
        dialog, the name asked for: `_begin_book`), or on the full screen count it among the pages kept nowhere - asked
        without changing anything."""
        scanned = getattr(self, "_book_scanned", False) and getattr(self, "_scanned_book", "") == \
            self.book_var.get().strip()
        whole = self.scan_mode() == "book"
        if scanned or not (whole or self._name_needed()) or not self._page_uncached(image):
            return False
        return not (whole and not self._name_needed() and self._book_read())

    def _early_allowed(self, op: Operation, image: Image.Image, thumb: np.ndarray) -> bool:
        """Whether *op*'s frame *image* may be started at once, before it settles (`_early_start`): early_start on,
        no key pressed for real (its two turns are watched for), none started early yet, the models ready, the worker
        free, no whole-book run; Auto on and the frame a new page whose start asks nothing (no book start, no window
        being enlarged), or Auto off and a page turned by TASlation's own operation; the viewer enlarged already; and
        a page the cache does not hold whole (one it does is taken as ever: at once, `_take_at_once`, or settled)."""
        if not self._early_on() or op.turned_at is not None or getattr(self, "_early", None) is not None:
            return False
        if reads_beside(self) or not self.ready or self.busy or self.batch is not None or self._batching:
            return False
        if self._black_open() or getattr(self, "_enlarging", None) is not None:
            return False
        win = self.selected
        if win is None or getattr(self, "_enlarge_asked", None) != win.hwnd:
            return False  # (the first page of a viewer: its window may be enlarged first, `_enlarge_first`)
        if self.auto_var.get():
            if self._auto_last is not None and not frames_differ(self._auto_last, thumb):
                return False
            if getattr(self, "_start_pending", None) is not None or self._starts_book(image):
                return False
        elif not op.operation:
            return False
        return not self._all_cached(image)

    def _early_start(self, op: Operation, image: Image.Image, thumb: np.ndarray, frame_detail: np.ndarray,
                     soft: bool = False) -> bool:
        """early_start: *op*'s frame started as the page at once (`_take`), before it settles, with a gate
        (`pipeline.PageGate`): the job reads the page and may show it; it asks the model once a look after it asked
        has found its frame on show still (`_frame_seen`), and keeps nothing until the frame is confirmed
        (`_early_confirm`); a frame that changes before that drops it (`_early_drop`). Whether it was started so.

        On a viewer seen to draw a page soft first, a frame that looks soft (`_looks_soft`) is not started (unless
        *soft*): its job would be dropped as the sharp picture comes 0.15-0.45 s later, and the sharp frame's job
        waited for it to end - on the stand-in viewer it began 290-300 ms (median) after the sharp frame was drawn,
        120-160 ms with the soft frame not started (its own detection and OCR as long either way). The page starts on
        the sharp frame as it comes, or - a page that is low in detail, the frame staying as it is - once the frame has
        stayed settle_ms (`_step`: the settle path's time, with a gate; a page turned to while a job ran too)."""
        op.held_soft = False  # (of the frame looked at last)
        if not self._early_allowed(op, image, thumb):
            return False
        if not soft and self._looks_soft(image):
            op.held_soft = True
            return False
        f = self._following
        gate = PageGate(TAKE_BACK_MS / 1000 if self._draws_soft_first() else 0.0)
        gate.soft = soft  # (a frame that looked soft: never caught behind the reader, `backlog`)
        look = getattr(self, "_look_now", None)
        early = Early(op, gate, image, thumb, self._auto_last, self._auto_candidate, f.taken, f.retake,
                      look if look is not None and look.image is image else None)
        self._early_gate = gate
        try:
            took = self._take(image, thumb, frame_detail, operation=op.operation)
        finally:
            self._early_gate = None
        if took != "started" or getattr(self, "_page_gate", None) is not gate:
            gate.drop()
            if took == "started":  # (no job came of it - a black frame: taken as it settles, as ever)
                self._early_revert(early)
            return False
        self._early = early
        return True

    def _early_of(self, op: Operation) -> Early | None:
        """The page started early on *op*'s frame and not confirmed yet, if any."""
        early = getattr(self, "_early", None)
        return early if early is not None and early.op is op else None

    def _early_revert(self, early: Early) -> None:
        """What the window held before *early* was started, back (the page it took is not taken)."""
        if self._auto_last is early.thumb:
            self._auto_last, self._auto_candidate = early.auto_last, early.candidate
        f = self._following
        if f.taken is not None and f.taken.frame is early.image:
            f.taken, f.retake = early.taken, early.retake

    def _early_drop(self) -> None:
        """The page started early, not confirmed, dropped: its gate (nothing of the job lasts:
        `Pipeline.page_on_show`), its job cancelled as a new page cancels one, and the window as before it."""
        early, self._early = getattr(self, "_early", None), None
        if early is None:
            return
        early.gate.drop()
        if getattr(self, "_page_gate", None) is early.gate:
            cancel = getattr(self, "_page_cancel", None)
            if cancel is not None and not cancel.is_set():
                self._cancel_why = "page"
                cancel.set()
                sync = getattr(self, "_sync_stop", None)
                if sync is not None:
                    sync()
        self._early_revert(early)

    def _early_end(self, op: Operation) -> None:
        """*op* is followed no further: a page started early on its frame and not confirmed is dropped."""
        if self._early_of(op) is not None:
            self._early_drop()

    def _early_confirm(self, op: Operation, now: float) -> bool:
        """*op*'s frame has stayed as it is for KEEP_SETTLES times settle_ms: the page started early on it is confirmed
        - what its job stores lasts, and the page it finished before the confirmation is shown now (`_show_held`) - and
        looked at once more (`_recheck_after`). False when the job gave the page up first (Stop, a failure, a new page
        another look saw: `_early_gone`): the page is then taken as ever."""
        early, self._early = getattr(self, "_early", None), None
        if early is None:
            return False
        if early.gate.confirm():
            self._recheck_after(op, now)
            held = getattr(self, "_show_held", None)
            if held is not None:
                held(early.gate)
            return True
        self._early_gave_up(early)
        return False

    def _early_gave_up(self, early: Early) -> None:
        """The job of *early* gave its page up before the frame was confirmed: after Stop the page stays taken (as Stop
        leaves a page: F5 translates it); else the window goes back to before it, and the page is started again on
        the frame there is (`Operation.redo`)."""
        if getattr(self, "_cancel_why", "") == "stop":
            return
        self._early_revert(early)
        f = getattr(self, "_following", None)
        if f is not None and f.op is early.op and early.op.phase == "settle":
            early.op.redo = True

    def _early_gone(self, data: dict[str, Any]) -> None:
        """(the worker's "page_cancelled", *discarded*) A page job whose frame was never confirmed is over and kept
        nothing: when the window had not dropped it itself, as `_early_gave_up`; a page it showed goes from the page."""
        early = getattr(self, "_early", None)
        if early is not None and early.gate is data.get("gate"):
            self._early = None
            self._early_gave_up(early)
        result = data.get("result")
        if result is not None and result is self.last_result:
            self.last_result = None  # (the viewer shows another picture by now: its frame goes on the page)
            self._redisplay()

    def _page_stored(self, data: dict[str, Any]) -> None:
        """(the worker's "result" or "page_cancelled" of a page job) The page units the job stored anew, with the frame
        it read: what a sharper picture of that frame drops (`_take_retake`)."""
        if "stored" not in data:
            return
        frame = getattr(self, "_job_frame", None)
        stored = [] if data.get("discarded") else list(data.get("stored") or ())
        replaced = [] if data.get("discarded") else list(data.get("replaced") or ())
        self._stored_by = (frame, stored, replaced) if frame is not None else None

    # ------------------------------------------------------------------ beside a whole-book run that translates
    def _watch_beside(self) -> None:
        """At each heartbeat: a run that has come to its translation starts the reading beside it (`_begin_beside`);
        one that is over ends it (`_end_beside`)."""
        if reads_beside(self):
            if getattr(self, "_beside", None) is None:
                self._begin_beside()
        elif getattr(self, "_beside", None) is not None and not in_a_run(self):
            self._end_beside()

    def _begin_beside(self) -> Beside:
        """The run has come to its translation: the viewer's page as it is now is the page the reader has not turned
        from yet (`Beside.base`), taken without a word, so that only a page turned since takes the page area from the
        run's page being translated. One capture, whoever is in front (the run captures nothing any more)."""
        b = self._beside = Beside()
        win = self.selected
        if win is None or not window_exists(win.hwnd) or not self._book_in_front():
            return b
        try:
            image = self._capture(win.hwnd)
        except CaptureError:
            return b
        thumb = thumbnail(image)
        if self._drew_nothing(thumb):
            return b
        b.base = thumb
        self._auto_last, self._auto_candidate = thumb, None
        self._quiet_live(image, thumb)
        f = getattr(self, "_following", None)
        if f is not None:
            f.seen = thumb
        return b

    def _end_beside(self) -> None:
        """The run is over (`jobs._batch_done`): the reading beside it ends, and its line on the page with it."""
        b, self._beside = getattr(self, "_beside", None), None
        if b is not None:
            self._beside_unsay(b)

    def _beside_take(self, image: Image.Image, thumb: np.ndarray, frame_detail: np.ndarray | None) -> str:
        """`_take` beside a run that translates: a new settled page asked of the run (`_beside_page`), "started" so
        that it is looked at again as a page taken is (a sharper frame of it: `_retake`)."""
        if self._auto_last is not None and not frames_differ(self._auto_last, thumb):
            return "same"
        self._auto_last, self._auto_candidate = thumb, None
        self._mark_taken(image, thumb, frame_detail)
        return "started" if self._beside_page(image, thumb) else "same"

    def _beside_page(self, image: Image.Image, thumb: np.ndarray) -> bool:
        """A page of the viewer taken beside a run that translates. The page on show as the translation began
        (`Beside.base`) leaves the run's page being translated on the page area; any other page the reader turns to
        takes it from there on (the run's page goes, `strip.end_follow`), and is asked of the run (`_ask_beside`): no
        model request, no page job. Whether it was asked."""
        b = getattr(self, "_beside", None)
        if b is None:  # (taken before the heartbeat began the reading beside the run: this is the page on show)
            b = self._beside = Beside()
        if not b.reading:
            if b.base is None:
                b.base = thumb
                return False
            if not frames_differ(b.base, thumb):
                return False
            b.reading = True
        b.seq, b.state = None, ""
        self._beside_unsay(b)
        end_follow(self, redisplay=False)  # (the run's page being translated, when it was on show ...)
        self._show_badge()  # (... and the badge of its progress: `_badge_due`)
        self._redisplay()
        self._ask_beside(image)
        return True

    def _beside_unsay(self, b: Beside) -> None:
        """The line on the page about the page before goes (unless another line took its place meanwhile)."""
        if b.note and getattr(self.canvas, "note", "") == b.note:
            self.canvas.set_note("")
        b.note = ""

    def _ask_beside(self, image: Image.Image) -> None:
        """The viewer's frame *image* asked of the run (`BatchReader.viewer_page`) on a thread of the window's own, at a
        lower priority, one at a time: a frame asked for while one is answered waits, and only the latest does. The
        answer comes as ``beside_page`` (`_beside_shown`). Nothing of it is written anywhere."""
        b, batch = getattr(self, "_beside", None), getattr(self, "batch", None)
        if b is None or batch is None:
            return
        with b.lock:
            b.token += 1
            b.pending = (b.token, image)
            if b.thread is not None:
                return  # (the thread asks it next)
            b.thread = threading.Thread(target=self._beside_loop, args=(b, batch), name="beside-run-page",
                                        daemon=True)
            b.thread.start()

    def _beside_loop(self, b: Beside, batch: Any) -> None:
        lower_priority()
        while True:
            with b.lock:
                job, b.pending = b.pending, None
                if job is None:
                    b.thread = None
                    return
            token, image = job
            try:
                page = batch.viewer_page(image)
            except Exception:  # noqa: BLE001 - nothing to show of it: the page stays as the viewer shows it
                page = None
            self._post("beside_page", token=token, page=page)

    def _beside_shown(self, data: dict[str, Any]) -> None:
        """The run's answer for the page asked last (``beside_page``; an older one is dropped): a page translated is
        the page on show - its lettering laid over the viewer's frame while that shows the page (`_picture`,
        `_same_page`) -, any other shows the viewer's frame as it is, with a line on the page that says why
        (`beside_line`)."""
        b = getattr(self, "_beside", None)
        page = data.get("page")
        if b is None or not b.reading or data.get("token") != b.token or page is None:
            return
        b.seq, b.state = int(getattr(page, "seq", 0) or 0), str(getattr(page, "state", ""))
        if b.state == "translated" and page.image is not None and page.frame is not None:
            self.last_result = PageResult(image=page.image, original=page.frame, regions=[])
        else:
            self.last_result = None
        self._redisplay()
        state = b.state
        line = beside_line(state)
        self._beside_unsay(b)
        b.note = line
        if line:
            self.canvas.set_note(line)
            self._page_status(lambda: beside_line(state), self._live)
        elif state == "translated":
            self.say("This page is translated; the whole-book run goes on with the rest of the book.")
            self._status_page = self._live  # (about the page on show: `_page_status`)

    def _beside_stage(self, data: dict[str, Any]) -> None:
        """A page of the run has its translation (``page_stage`` translate done or failed): when the viewer shows that
        page beside the run, waiting for it, it is asked of the run again, and shows translated."""
        b = getattr(self, "_beside", None)
        if b is None or not b.reading or data.get("stage") != "translate" or data.get("state") not in ("done", "failed"):
            return
        try:
            seq = int(data.get("seq"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        if seq == b.seq and b.state == "waiting" and self._live is not None:
            self._ask_beside(self._live)

    def _beside_translation_page(self, data: dict[str, Any]) -> bool:
        """Whether the run's picture of the page it translates (``translation_page``) is kept from the page area: once
        the reader reads beside the run, but for the page the viewer shows (its seq as the run answered it, while it
        waits for its translation), whose progress is shown then; the run's page on show goes when the run moves on to
        another."""
        b = getattr(self, "_beside", None)
        if b is None or not b.reading:
            return False
        if b.seq and b.state == "waiting" and data.get("seq") == b.seq:
            return False
        if getattr(self, "_run_view", None) is not None:
            end_follow(self)
        return True

    def _run_page_kept(self, view: Any) -> bool:
        """Beside a run that translates (`Beside`): whether its page being translated (*view*, `strip.RunPage`) keeps
        the page area, as the viewer's latest frame (`_live`) tells - before the reader has turned, while the viewer
        shows the page it showed as the translation began (`Beside.base`); once the reader reads beside the run, while
        it shows that very page (`_shows_page`, against the frame the run read). A page turned to shows as the viewer
        draws it, not once it is taken (`_beside_page`, settle_ms after it stopped changing: on the browser-type
        stand-in viewer the run's page stayed 0.5-0.9 s after such a turn), and the badge goes with the run's page
        (`_show_live`, `_badge_due`)."""
        b = getattr(self, "_beside", None)
        live = self._live
        if b is None or live is None:
            return True
        if not b.reading:
            return b.base is None or not frames_differ(b.base, _thumb(self, live))
        return self._shows_page(live, view.frame)

    # ------------------------------------------------------------------ an operation followed (events)
    def _begin_follow(self, hwnd: int, reference: Any, key: str = "", retried: bool = False, *,
                      phase: str = "change", last: np.ndarray | None = None,
                      last_detail: np.ndarray | None = None, operation: bool = False, fast: bool = False,
                      seq: int | None = None, image: Image.Image | None = None, over_job: bool = False) -> None:
        """Follow the viewer's frame (follow = "events"), in place of a follow before: from *phase* "change" (an
        operation of TASlation's: awaited to change from *reference*, at FOLLOW_STEP_MS; with *seq*, the viewer's
        frame count when *reference* was captured, at each new frame as it comes, `_counted_change`), "settle" (it has
        changed: *last* is the frame seen, *image* its capture; *operation*: after TASlation's own operation;
        *over_job*: a frame of another page than the running job's, `_look_over_job`) or, *fast*, "recheck" (a page
        just taken at once: `_take_at_once`). A posted key that comes while the one before is still awaited with
        nothing changed goes with it (`_held_keys`)."""
        f = self._follower()
        held = self._held_keys(f.op, hwnd) if phase == "change" and key and not retried else None
        self._end_follow()
        if phase == "change":
            f.retake = None  # an operation: the page a sharper frame waited for is not the one to come
        op = Operation(hwnd, reference, key, retried or not key, time.monotonic(), phase, last, last_detail,
                       operation=phase == "change" or operation, over_job=over_job)
        if key and phase == "change":
            op.keys = (key,)
        if held is not None:  # (its wait goes on from the first key, the frames before it the same)
            op.keys, op.started, op.reference, op.prev = (*held.keys, key), held.started, held.reference, held.prev
            if held.pressed:  # the keys before it pressed for real already, and the page not turned yet: it too
                press_briefly(hwnd, key)
                op.retried = op.pressed = True
        f.op = op
        if phase == "settle":
            self._settle_on(op, last, last_detail, op.started, image)
            return
        if fast:
            op.fast_until = op.started + RECHECK_MS / 1000
            op.seq = self._frame_count()
            op.last_at = op.started
        elif phase == "change" and seq is not None:
            op.seq = seq  # (looked_at 0: the first step captures whatever the count says)
            op.job = self.after(FRAME_STEP_MS, self._follow_step)
            return
        op.job = self.after(FOLLOW_STEP_MS if phase == "change" or fast else self.settings.settle_ms, self._follow_step)

    @staticmethod
    def _held_keys(op: Operation | None, hwnd: int) -> Operation | None:
        """The operation *op* followed when a new posted key comes for the viewer *hwnd*, if its own posted keys are
        still awaited with nothing changed at all (no frame moved, not raised for a look): the new key goes with them.
        Once the first one's page_turn_wait_ms has passed with nothing changed all of them are pressed for real, in
        order (`_await_change`); when they were pressed for real already, the new one is pressed for real at once
        (`_begin_follow`). Else the new key would have ended that wait, and the keys before it, never pressed for
        real, would have turned nothing - two keys within the wait turned one page -, or, coming after they were, it
        would have taken their page turn for its own, and the viewer for one that takes posted keys. None when there
        is no such operation (and for keys pressed for real from the start, which nothing follows up)."""
        if (op is None or op.phase != "change" or op.hwnd != hwnd or not op.keys or (op.retried and not op.pressed)
                or op.raised or op.stirred_at is not None):
            return None
        return op

    def _settle_on(self, op: Operation, thumb: np.ndarray | None, frame_detail: np.ndarray | None, now: float,
                   image: Image.Image | None = None) -> None:
        """*op* followed from the frame *thumb* (seen at *now*; *image*: its capture) until it settles: two frames
        settle_ms apart alike - with the viewer's frames counted (`capture.frame_count`), no new frame for settle_ms,
        looked at every FRAME_STEP_MS, so that a frame that changes is seen as it comes (a page the cache holds is
        taken then: `_take_at_once`); else a look every settle_ms. After a key pressed for real, every settle_ms (the
        two turns are watched for). With early_start the page is started on this very frame (`_early_start`), and
        what its job stores lasts once the frame has stayed as it is for KEEP_SETTLES times settle_ms (`_settle_s`),
        counted from the look that saw the frame (`Look.at`); its frames not counted, it is looked at every
        FOLLOW_STEP_MS meanwhile (`_watched`). The count is the one before that look's capture, so that a frame that
        came during it is captured at the next step."""
        op.phase, op.last, op.last_detail, op.last_image, op.settles = "settle", thumb, frame_detail, image, 0
        look = getattr(self, "_look_now", None)
        seen = look is not None and image is not None and look.image is image
        op.last_at = op.settle_from = look.at if seen else now
        op.fast_until = None
        op.redo = False
        op.seq = None
        if op.turned_at is None:
            count = self._frame_count()
            op.seq = look.seq if seen and count is not None and look.seq is not None else count
        if image is not None and thumb is not None and frame_detail is not None:
            self._early_start(op, image, thumb, frame_detail)
        if op.seq is not None:
            self._next_step(op, FRAME_STEP_MS)
        else:
            self._next_step(op, FOLLOW_STEP_MS if self._watched(op) else round(self._settle_s(op) * 1000))

    def _end_follow(self) -> None:
        """The operation followed, if any, followed no further (a page started early on its frame is dropped)."""
        f = getattr(self, "_following", None)
        op = f.op if f is not None else None
        if op is None:
            return
        f.op = None
        if op.job is not None:
            try:
                self.after_cancel(op.job)
            except tk.TclError:
                pass
        self._early_end(op)

    def _follow_step(self) -> None:
        """One step of the operation followed (`_step`); it ends unless the step asked for the next one (and a page
        started early on its frame, still not confirmed, is dropped with it)."""
        f = self._following
        op = f.op
        if op is None:
            return
        op.job = None
        try:
            self._step(op)
        finally:
            if f.op is op and op.job is None:
                f.op = None
                self._early_end(op)

    def _next_step(self, op: Operation, ms: int) -> None:
        op.job = self.after(ms, self._follow_step)

    def _step(self, op: Operation) -> None:
        """The viewer's frame once, for the operation followed: "change" - every FOLLOW_STEP_MS until it differs from
        the frame before the operation (`_await_change`: a key the viewer ignored is pressed for real; with its frames
        counted, at each new frame as well, `_counted_change`); "settle" -
        every settle_ms until two frames are alike and the later is not sharper (frames counted: at every new frame,
        until none came for settle_ms; `_settle_on`), then the page is taken (`_take`; a page the cache holds is taken
        on the first frame of it, `_take_at_once`; a page started early on its first frame is confirmed once the frame
        has stayed as it is for KEEP_SETTLES times settle_ms, looked at every FOLLOW_STEP_MS meanwhile when its frames
        are not counted, and its job told at each look that finds its frame on show still, `_frame_seen`;
        after a key pressed for real, not before TWO_TURNS_S has passed since the page turned: a page that turns once
        more by then turned twice, `_say_two_turns`); "recheck" - RECHECK_MS after the page was taken: a frame of
        another page is followed until it settles, a sharper frame of the same page is read again, and a page taken at
        once in translator mode is completed from its frame once that has settled (`_completion`, `_complete_taken`).
        While a run reads the pages the reader turns only "change" is followed (the key got to the viewer); the run
        takes the page. Once the run translates, all of it is followed, as without a run (`reads_beside`)."""
        f = self._following
        if viewer_rests(self) or self._black_open() or (
                in_a_run(self) and op.phase != "change" and not reads_beside(self)):
            return  # (a viewer that stays black: the look when it is back takes it from there)
        now = time.monotonic()
        settle_s = self.settings.settle_ms / 1000
        if op.seq is not None and op.phase == "change" and not self._counted_change(op, now):
            return
        if op.seq is not None and op.phase in ("recheck", "settle"):  # the viewer's frames counted
            count = self._frame_count()
            if count is not None and count == op.seq:  # no new frame since the last look: nothing to capture ...
                if op.phase == "recheck":
                    self._mark_stayed(now)
                    if self._completion(op, now):
                        return
                    if op.fast_until is not None and now < op.fast_until:
                        self._next_step(op, FRAME_STEP_MS)
                    return
                self._frame_seen(op)  # (the frame of a page started early on it is on show still)
                if op.redo and not self.busy:
                    pass  # (the page dropped is gone from the worker: started again on the frame there is, below)
                elif now - op.last_at < self._settle_s(op) or (op.redo and self._waits_for_worker(op, now)):
                    self._next_step(op, FRAME_STEP_MS)  # ... yet; once its time has passed, it settled
                    return
            op.seq = count
        try:
            image = self._capture(op.hwnd)
        except CaptureError as e:
            self._capture_failed(e)
            f.look_at = now + self.settings.auto_interval_ms / 1000  # looked at again while it lasts
            return
        thumb = _thumb(self, image)
        blank = self._drew_nothing(thumb)  # nothing drawn (yet)
        if op.phase == "change":
            self._await_change(op, image, thumb, now, blank)
            return
        if blank:
            if now - op.started < self.settings.page_turn_wait_ms / 1000 or (
                    op.fast_until is not None and now < op.fast_until):
                self._next_step(op, FOLLOW_STEP_MS)
            else:
                f.look_at = now + self.settings.auto_interval_ms / 1000
            return
        frame_detail = _detail(self, image, self._area_box(image))
        self._show_live(image, thumb)
        f.seen = thumb
        if op.phase == "settle":
            sharpened = sharper(op.last_detail, frame_detail)
            moving = sharpened or frames_differ(op.last, thumb, SAME_PICTURE)
            if sharpened and op.last_image is not None and not frames_differ(op.last, thumb):
                self._drew_soft(op.last_image, image)  # (the page come sharper as it settles: drawn soft first)
            if not moving:
                self._frame_seen(op, fresh=True)
            if op.turned_at is not None and not op.twice:  # after a key pressed for real: does it turn once more?
                if op.calm is not None and frames_differ(op.calm, thumb):
                    op.twice = True  # it had settled, and turned again: the posted key had arrived after all
                elif op.calm is None and not moving:
                    op.calm = thumb
            waiting = op.turned_at is not None and not op.twice and now - op.turned_at < TWO_TURNS_S
            if moving and self._early_of(op) is not None:
                self._early_drop()  # the frame changed under the page started on it: nothing of that job lasts ...
                op.redo = True  # ... and the page starts again on this frame once the worker is free of it
            if (moving or op.redo or (op.over_job and not self.busy)) and op.turned_at is None and not (
                    op.redo and self.busy):
                op.redo = False
                # (a page the cache holds: taken now, then rechecked - unless a job runs that this frame, not
                # confirmed yet, would cancel: `_look_over_job`)
                if not (op.over_job and self.busy) and self._take_at_once(op.hwnd, image, thumb, frame_detail,
                                                                          op.operation):
                    return
                if self._early_start(op, image, thumb, frame_detail):  # (early_start: started on this frame)
                    op.over_job = False  # (the job it was seen over is gone)
            counted = op.seq is not None and op.turned_at is None
            if counted or self._watched(op):  # settled once unchanged for `_settle_s` (frames counted: at each new
                step = FRAME_STEP_MS if counted else FOLLOW_STEP_MS  # frame; else looked at every FOLLOW_STEP_MS)
                if moving and now - op.settle_from < SETTLE_TRIES * settle_s:
                    op.last, op.last_detail, op.last_image, op.last_at = thumb, frame_detail, image, now
                    self._next_step(op, step)
                    return
                if not moving and now - op.last_at < self._settle_s(op):
                    self._next_step(op, step)
                    return
            elif (moving or waiting) and op.settles < SETTLE_TRIES:
                op.last, op.last_detail, op.last_image, op.settles = thumb, frame_detail, image, op.settles + 1
                if moving:
                    op.last_at = now
                self._next_step(op, round(self._settle_s(op) * 1000))
                return
            early = self._early_of(op)
            if early is not None:
                # (frames that kept changing for SETTLE_TRIES looks confirm the frame there is: it has not stayed, and
                # its page is caught once turned past only if a look the fixed time from now still sees it - the
                # recheck, below -, `backlog`)
                early.gate.settled = not moving
                if moving:
                    early.gate.settled_by = now + KEEP_SETTLES * settle_s
                if self._early_confirm(op, now):
                    return  # (the page started on its first frame goes on: kept, and asks the model now)
            if op.over_job and not op.redo and self.busy and self._on_job_page(image):
                return  # (back on the page the running job reads: it goes on, nothing is taken)
            if (op.over_job or op.redo) and self._waits_for_worker(op, now):
                if op.over_job and not op.redo:  # the viewer has left the page the running job reads: it goes ...
                    f.taken = None
                    self._cancel_page(turned=True)
                op.redo = True  # ... and this frame is started early, a gate of its own, once the worker is free
                self._next_step(op, FRAME_STEP_MS if op.seq is not None else FOLLOW_STEP_MS)
                return
            if op.held_soft and now - op.last_at < self.settings.settle_ms / 1000:
                # (a soft frame of a page turned to while a job ran - that job cancelled once the frame had stayed
                # LEFT_PAGE_MS -: it waits for the sharp frame as long as the settle path would, no longer)
                self._next_step(op, FRAME_STEP_MS if op.seq is not None else FOLLOW_STEP_MS)
                return
            if op.held_soft and self._early_start(op, image, thumb, frame_detail, soft=True):
                # (a frame that looked soft and stayed settle_ms - a page low in detail -: started now, the settle
                # path's time, with a gate, kept once it has stayed KEEP_SETTLES times settle_ms)
                self._next_step(op, FRAME_STEP_MS if op.seq is not None else FOLLOW_STEP_MS)
                return
            took = self._take(image, thumb, frame_detail, operation=op.operation)
            if op.twice:
                self._say_two_turns(op.key)
            op.turned_at, op.twice = None, False  # (said once)
            if took == "started":
                op.phase = "recheck"
                self._next_step(op, RECHECK_MS)
            return
        taken = f.taken  # "recheck"
        if taken is None:
            return
        self._mark_stayed(now, thumb)
        if frames_differ(taken.thumb, thumb):  # another page meanwhile: followed until it settles
            # (while the page taken is being translated, its job goes on until this frame has stayed as it is for
            # LEFT_PAGE_MS, as for a turn `_look_over_job` sees: it cancels it then - before, it did at once, and a
            # frame that was not the page's for long, a picture redrawn, a page turned and back, cancelled a page still
            # on show)
            over = self._page_job_runs()
            if not over and self._take_at_once(op.hwnd, image, thumb, frame_detail, op.operation):
                return  # (a page the cache holds: taken now)
            op.over_job = over
            self._settle_on(op, thumb, frame_detail, now, image)
            return
        if sharper(taken.detail, frame_detail):
            self._retake(image, thumb, frame_detail)
            return
        if taken.complete:  # the same page again: completed once the frame has settled
            if op.seq is not None:
                op.last_at = now  # (a new frame: settled once none came for settle_ms, `_completion`)
                self._next_step(op, FRAME_STEP_MS)
                return
            if (op.last is None or frames_differ(op.last, thumb, 0.5)) and now - op.started < SETTLE_TRIES * settle_s:
                op.last = thumb
                self._next_step(op, self.settings.settle_ms)
                return
            self._complete_taken(op, image, thumb, now)
            return
        if op.fast_until is not None and now < op.fast_until:  # taken at once: a sharper frame may come yet
            self._next_step(op, FRAME_STEP_MS if op.seq is not None else FOLLOW_STEP_MS)

    def _counted_change(self, op: Operation, now: float) -> bool:
        """"change" with the viewer's frames counted (`capture.frame_count`; *op*.seq the count at the last capture):
        whether to capture the frame now - at the first new frame, no sooner than FRAME_GAP_MS after the capture
        before, and at least every FOLLOW_STEP_MS whatever the count says (the waits of `_await_change` go on at their
        pace). Else the next step comes in FRAME_STEP_MS: a page the viewer has drawn by the time the key's handover
        is over is captured within that, not FOLLOW_STEP_MS later."""
        count = self._frame_count()
        since = now - op.looked_at
        if since < FOLLOW_STEP_MS / 1000 - 0.002 and (
                count is None or count == op.seq or since < FRAME_GAP_MS / 1000 - 0.002):
            self._next_step(op, FRAME_STEP_MS)
            return False
        op.seq = count if count is not None else op.seq
        op.looked_at = now
        return True

    def _completion(self, op: Operation, now: float) -> bool:
        """"recheck" with the viewer's frames counted, no new frame since the last look, after a page taken at once
        from the cache in translator mode (`Taken.complete`): the frame has settled once no new frame came for
        settle_ms (at most SETTLE_TRIES times settle_ms after the page was taken), and the page is completed from it
        (`_complete_taken`); until then the next step comes in FRAME_STEP_MS. Whether there was a page to complete."""
        taken = self._following.taken
        if taken is None or not taken.complete:
            return False
        settle_s = self.settings.settle_ms / 1000
        if now - op.last_at < settle_s and now - op.started < SETTLE_TRIES * settle_s:
            self._next_step(op, FRAME_STEP_MS)
            return True
        try:
            image = self._capture(op.hwnd)
        except CaptureError:
            taken.complete = False
            return True
        thumb = _thumb(self, image)
        if frames_differ(taken.thumb, thumb):  # another page after all: followed until it settles
            self._settle_on(op, thumb, _detail(self, image, self._area_box(image)), now, image)
            return True
        self._complete_taken(op, image, thumb, now)
        return True

    def _complete_taken(self, op: Operation, image: Image.Image, thumb: np.ndarray, now: float) -> None:
        """Translator mode: the page taken at once from the cache, settled now, read again from this frame to complete
        it (`pipeline.process`'s *complete*: the regions the cache has no bubble for read and translated). While the
        job drawing it from the cache still runs it waits for it, every FOLLOW_STEP_MS until RETAKE_WITHIN_MS after the
        page was taken; with a whole-book run, or the models not ready, the page stays as the cache drew it."""
        f = self._following
        taken = f.taken
        if taken is None:
            return
        if self.busy and self.batch is None and not self._batching and now - taken.at < RETAKE_WITHIN_MS / 1000:
            self._next_step(op, FOLLOW_STEP_MS)
            return
        taken.complete = False
        if not self.ready or self.busy or self.batch is not None or self._batching:
            return
        self._auto_last, self._auto_candidate = thumb, None
        self._mark_taken(image, thumb, taken.detail)
        self._start_translate(image, thumb=thumb, complete=True)
        if op.fast_until is not None and now < op.fast_until:  # a sharper frame may come yet
            self._next_step(op, FRAME_STEP_MS if op.seq is not None else FOLLOW_STEP_MS)

    def _await_change(self, op: Operation, image: Image.Image, thumb: np.ndarray, now: float, blank: bool) -> None:
        """"change": the frame after TASlation's operation, every FOLLOW_STEP_MS until it differs from the one before
        it (the page turned: followed until it settles). Any change of the frame at all meanwhile - full thumbnails
        compared: a loading indicator, a partial repaint, a blank frame - says that the viewer took the key: it is
        never pressed again, and the page is waited for up to FOLLOW_WAITS times page_turn_wait_ms (a slow viewer
        shows it seconds later). A posted key that changed nothing at all for page_turn_wait_ms is pressed for real,
        once (a window that ignores posted keys); when that changes nothing at all either for as long, the follow
        ends and the status line says so. Before anything is concluded from a frame that did not change, a viewer
        hidden wholly by other windows is raised for a look, as long again (`_raise_viewer`) - unless it is known to
        draw so (`_look_raised`): then, as for a viewer partly in sight, the key is pressed for real after the first
        wait. What the turn showed of the viewer is kept (`_seen_turn`, `_learned`)."""
        f = self._following
        wait = self.settings.page_turn_wait_ms / 1000
        if not blank and (op.reference is None or frames_differ(op.reference, thumb)):  # the page turned
            self._seen_turn(op.hwnd, op.raised, op.pressed)
            if getattr(self, "_raised", None) is not None:
                self.after(self.settings.settle_ms, self._lower_viewer)  # drawn: back in its place at once
            self._learned(op.hwnd, op.pressed, bool(op.key) and not op.retried)
            if in_a_run(self) and not reads_beside(self):
                return  # (the run reading the pages takes the page)
            self._auto_candidate = None
            f.seen = thumb
            frame_detail = _detail(self, image, self._area_box(image))
            if op.pressed:
                if len(op.keys) <= 1:
                    op.turned_at = now  # (does it turn once more, soon? "settle" watches; several keys turn several)
            elif self._take_at_once(op.hwnd, image, thumb, frame_detail, operation=True, shown=False):
                return  # a page the cache holds: taken on its first frame, then rechecked
            # (a page job at work meanwhile - the page before still read or asked for -: the page goes as one the
            # viewer turned while the job ran, `_look_over_job` - the job cancelled once the frame has stayed
            # LEFT_PAGE_MS, the page started early, a gate of its own, once the worker is free - not taken as settled
            # and queued, then started with no gate: never caught once turned past, `backlog`)
            op.over_job = bool(self.auto_var.get()) and (self._page_job_runs() or self._page_job_ends())
            self._show_live(image, thumb)  # the turned page shows at once
            self._settle_on(op, thumb, frame_detail, now, image)
            return
        if blank or frames_differ(op.prev if op.prev is not None else op.reference, thumb, LIVE_CHANGE):
            op.stirred_at = now  # the viewer is at it: it took the key
        op.prev = thumb
        if (not op.raised and op.stirred_at is None and now - op.started >= wait and self._look_raised(op.hwnd)
                and self._raise_viewer(op.hwnd)):
            op.raised, op.started = True, now
            self._next_step(op, FRAME_STEP_MS if op.seq is not None else FOLLOW_STEP_MS)
            return
        if not op.retried and op.stirred_at is None and now - op.started >= wait:
            # The posted key changed nothing at all (a window that ignores posted keys): the person's key pressed for
            # real, once (`press_briefly`: the foreground handed over and back, no ALT tap) - with the keys pressed
            # since, in order (`_held_keys`), each of them once.
            press_briefly(op.hwnd, list(op.keys) if len(op.keys) > 1 else op.key)
            op.retried, op.pressed, op.started = True, True, time.monotonic()
            self._next_step(op, FRAME_STEP_MS if op.seq is not None else FOLLOW_STEP_MS)
            return
        if now - op.started > (wait if op.stirred_at is None else FOLLOW_WAITS * wait):
            if op.stirred_at is None and op.key:
                self.say("The viewer did not change (end of book, or the key means nothing there).")
            if blank:  # nothing drawn: looked at again while it lasts
                f.look_at = now + self.settings.auto_interval_ms / 1000
            return
        self._next_step(op, FRAME_STEP_MS if op.seq is not None else FOLLOW_STEP_MS)

    def _say_two_turns(self, key: str) -> None:
        """A key pressed for real (the posted one had changed nothing) turned the page twice within TWO_TURNS_S: the
        posted key had arrived after all. The reader is told, with the key to press in this window that turns back one
        page (`key_label`: for the viewer's next key its previous one, else *key*'s opposite, as pressed here:
        `pagekeys.pressed_for`), in the status line and - as the line moves on while the page is read - on the page
        for a while."""
        from .constants import FORWARDED_KEYS
        from .reading import key_label  # (imported here: `reading` imports `viewers`, which imports this module)

        pair = self._page_key_pair()
        back = opposite_key(key)
        if pair is not None:
            viewer, window = pair
            if same_key(key, viewer.next):
                back = viewer.prev
            elif same_key(key, viewer.prev):
                back = viewer.next
            back = pressed_for(back, viewer, window, FORWARDED_KEYS.values())
        if back:
            def line() -> str:
                return _("The viewer turned two pages; press {key} once to go back.").format(key=key_label(back))
        else:
            def line() -> str:
                return _("The viewer turned two pages.")
        self.status(line)
        if not self.reading:  # (the full screen shows the status line on the page by itself)
            self.canvas.set_note(line(), READING_NOTE_MS)

    # ------------------------------------------------------------------ the window's own moves, watched (events)
    def _watch_own_window(self) -> None:
        """Follow = "events": TASlation's own window moved or resized is watched too (Tk's <Configure>): maximised over
        the viewer it may make the viewer stop drawing, moved aside let it draw again; one look once it stops tells."""
        try:
            self.bind("<Configure>", self._own_moved, add="+")
        except tk.TclError:
            pass

    def _own_moved(self, event: tk.Event) -> None:
        if event.widget is self and self._follows_events():
            self._following.look_at = time.monotonic() + self.settings.settle_ms / 1000
