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
* a page whose every unit is in the cache is taken on its first changed frame, without the wait for it to settle
  (`_take_at_once`: drawn from the cache, nothing read from the frame), and looked at every FOLLOW_STEP_MS for
  RECHECK_MS after: a viewer that draws a soft picture first has it replaced by the sharp one as soon as that comes
  (`_retake`), and the job on the soft frame, cancelled or done, adds nothing to the cache; in translator mode the
  page is completed from what it reads once its frame has settled (`_completion`);
* once when TASlation or the viewer comes back to the front, once the viewer's window or TASlation's own stops moving
  (maximised over the viewer, TASlation may make it stop drawing), when the viewer's title changes - a browser's is
  its active tab's -, and, while TASlation is in front, once input over the viewer's window stops (Windows scrolls a
  window under the pointer that is not in front: `_note_input`) (`_look`); a look while a page is translated that
  finds a new page there, alike on a second look settle_ms later, cancels the job (`_look_over_job`);
* never while neither is in front - except for a viewer just chosen (at the start, from the list, by the watch): it
  is looked at at once whoever is in front, and every auto_interval_ms until a frame of it is on the page
  (`Following.unseen`, `_follow_viewer`), and for a viewer whose window TASlation just gave a new size: the fresh frame
  goes on the page, the capture area is the new size's own, and Auto goes on from there (`_resize_begins`,
  `_look_afresh`).

Windows tells who is in front and what happens to the viewer's window (`capture.WindowEvents`, whose notes the
heartbeat takes in: `_beat`), and `follow_decision` decides what each heartbeat does."""

from __future__ import annotations

import time
import tkinter as tk
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

from .. import fingerprint as fp
from .. import recovery
from ..batch import detail, frames_differ, sharper, thumbnail
from ..capture.windows import BROWSER_CLASSES, covered_by_opaque, window_class
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
from ..regions import PageResult
from . import area
from .constants import (
    BLANK_SPREAD,
    BROWSER_MINIMISED,
    FOLLOW_STEP_MS,
    FOLLOW_WAITS,
    FRAME_GAP_MS,
    FRAME_STEP_MS,
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
from .strip import run_page_on_show

COVERED_PROBE_MS = 500  # a viewer asked to paint itself anew (`_learn_covered`): a frame within this says it drew


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
    detail, when; for a sharper frame waiting to be read again, the softer frame read before."""

    frame: Image.Image
    thumb: np.ndarray
    detail: np.ndarray
    at: float
    soft: Image.Image | None = None
    complete: bool = False  # translator mode: shown from the cache at once, completed once the frame has settled


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
    last_detail: np.ndarray | None = None  # ... and its fine detail
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


@dataclass
class Following:
    """How the window follows the viewer (made at the first heartbeat: `LiveViewMixin._follower`)."""

    mode: str = "poll"  # "events" while Windows' window events are hooked
    events: Any = None  # the hooks (capture.WindowEvents)
    owner: str = "own"  # who is in front: "own" (a window of TASlation's), "viewer", "other"
    look_at: float | None = None  # a look at the viewer is due from then on
    last_poll: float = 0.0
    polled: int | None = None  # the viewer's frame count at the last poll (`capture.frame_count`)
    last_input: int = 0  # when the session's last input came (Windows' ticks), as seen at the last heartbeat
    seen: np.ndarray | None = None  # the thumbnail of the last frame captured
    op: Operation | None = None  # the operation being followed
    taken: Taken | None = None  # the page taken last, while a sharper frame of it may come
    retake: Taken | None = None  # such a sharper frame, read once the job on the softer one is done
    unseen: bool = True  # the viewer chosen has no picture on the page yet: it is looked at whoever is in front


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
        black = is_black(image, self.settings.margins)
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
    def _found_margins(self) -> tuple[int, int, int, int]:
        """The margins of the page panel found so far in the chosen viewer's frames ((0, 0, 0, 0): none yet)."""
        known = self._page_areas.get(viewer_key(self.selected)) if self.selected is not None else None
        return area_margins(known[1], known[0]) if known is not None else (0, 0, 0, 0)

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

    def _inner_margins(self) -> tuple[int, int, int, int]:
        """The capture area within the reader's own: the page panel found inside it so far, as far as it lies within
        the area (`_find_page`); the area itself while none is found for this viewer, capture size and area."""
        hand = self._hand_set()
        known = getattr(self, "_inner_areas", {}).get(viewer_key(self.selected)) \
            if self.selected is not None else None
        if known is None or known[1] != hand or known[2] is None:
            return hand
        size, _hand, box = known
        return area_margins(box, size, hand)

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
        self.canvas.enlarge = reading
        self.canvas.message = _("This viewer cannot be read behind the reading window; press Esc") if (
            reading and self._viewer_hidden) else ""
        # no viewer chosen yet: what to do, in the window's language (the live picture takes its place once one is)
        self.canvas.hint = _(NO_VIEWER) if self.selected is None else ""
        image, overlay, outlines = self._picture()
        self.canvas.overlay, self.canvas.outlines = overlay, outlines
        if image is None:
            self.canvas.crop = None
            self.canvas.set_image(None)
            return
        self.canvas.crop = area.margins_to_box(self.settings.margins, image.size) if reading else None  # the page alone
        self.canvas.set_image(image)

    def _picture(self) -> tuple[Image.Image | None, list[Any], list[Any]]:
        """What the page shows, with translator mode's region overlay and the outlines of a page filling in:

        * a page the whole-book run is translating (`strip.run_page_on_show`): the lines answered so far lettered,
          the others outlined;
        * a page being translated: the frame it is read from with the regions lettered so far, the others outlined;
        * else the last translated page while the viewer still shows that page - its lettering laid over the
          viewer's latest frame, so a toolbar or the pointer shows as it is now;
        * else the viewer's latest frame as it is (a page not translated yet, a page turned, the viewer's panels).
        Show original leaves the lettering out. Reading is on the viewer only: the first is the one page of a
        whole-book run's memory ever shown, as the run's progress while it translates; outside that, every picture is
        the viewer's page (`strip`'s docstring), so that TASlation never lets a book be read without the viewer."""
        original = self.original_var.get()
        run = run_page_on_show(self)
        if run is not None:
            return (run.frame if original else run.image), [], run.outlines()
        fill = self._fill
        if fill is not None:
            image = fill.final if fill.final is not None else fill.page if fill.page is not None else fill.base
            return (fill.frame if original else image), [], ([] if fill.final is not None else fill.outlines())
        result, live = self.last_result, self._live
        if result is not None and (live is None or self._same_page(result, live)):
            if original:
                return (live if live is not None else result.original), self._overlay_items(), []
            return self._lettered(result, live), self._overlay_items(), []
        return live, [], []

    def _result_on_show(self) -> bool:
        """Whether the page shows the last result (not a page filling in, nor the viewer showing another page)."""
        result = self.last_result
        return (self._fill is None and result is not None and run_page_on_show(self) is None
                and (self._live is None or self._same_page(result, self._live)))

    def _same_page(self, result: PageResult, live: Image.Image) -> bool:
        """Whether the viewer's frame *live* still shows *result*'s page: the same size, and the capture area about
        the same as when the page was read (the viewer's toolbar or the pointer beside the page do not count)."""
        if live is result.original:
            return True
        if live.size != result.original.size:
            return False
        return not frames_differ(self._area_thumb(result.original), self._area_thumb(live))

    def _area_thumb(self, image: Image.Image) -> np.ndarray:
        """The thumbnail of *image*'s capture area (remembered for the last few frames)."""
        margins = tuple(self.settings.margins)
        for key, img, thumb in self._thumbs:
            if img is image and key == margins:
                return thumb
        box = area.margins_to_box(margins, image.size)
        whole = box == (0, 0, image.width, image.height) or box[2] <= box[0] or box[3] <= box[1]
        thumb = thumbnail(image if whole else image.crop(box))
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
        thumb = self._job_thumb if self._job_thumb is not None else thumbnail(result.original)
        if self._live_thumb is None or not frames_differ(self._live_thumb, thumb, LIVE_CHANGE):
            self._live, self._live_thumb = result.original, thumb

    def _show_live(self, image: Image.Image, thumb: np.ndarray | None = None) -> None:
        """The live view: a frame of the viewer goes on the page when it differs from the one on show, or is of another
        size (a page filling in keeps its frame until its job is done). From the first one on, the viewer chosen is
        followed by the usual rules (`Following.unseen`)."""
        f = getattr(self, "_following", None)
        if f is not None:
            f.unseen = False
        thumb = thumbnail(image) if thumb is None else thumb
        if (self._live is not None and self._live_thumb is not None and self._live.size == image.size
                and not frames_differ(self._live_thumb, thumb, LIVE_CHANGE)):
            return
        self._live, self._live_thumb = image, thumb
        if self._fill is None:
            self._redisplay()

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
        if not noted or self.reading:  # the reading window shows the page alone
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
        """Translator mode: outline every region (green = translated, orange = not, blue = reader-made), with the
        speaker, a dagger where a note for the reader is, and the reading-order number while an order is being set;
        not the pieces of the drawing the OCR read unsure (`_page_regions`)."""
        if self.role_var.get() != "translator" or self.last_result is None or self.reading:
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
            if self.reading:  # no dialog over the reading window, and the scan would turn the pages under the reader
                self._start_translate(image, thumb=thumb, complete=complete)
                if self._name_needed():  # kept nowhere: its name is asked for on leaving (`_ask_name_after_reading`)
                    self._unkept_reading = getattr(self, "_unkept_reading", 0) + 1
                if whole and not self._scan_waits_told:
                    self._scan_waits_told = True
                    self.say("Reading mode translates page by page; the whole-book scan waits until you leave it (Esc).")
                return
            if self.selected is None:
                return
            self._begin_book(image, thumb, whole)
            return
        self._start_translate(image, thumb=thumb, complete=complete)

    def _page_uncached(self, image: Image.Image) -> bool:
        """Is any page unit of this capture missing from the book's cache? (A quick check on the Tk thread.) Under a
        name that names no book (a viewer, a browser, nothing: `_name_needed`) every page is: nothing is kept under
        it, so the start asks for the name even when an old cache under the viewer's name holds the page."""
        book, model, language = self.book_var.get().strip(), self.model_var.get().strip(), self.lang_var.get().strip()
        if not self.settings.cache_enabled:
            return False
        if self._name_needed():
            return True
        try:
            cache = self.store.open(book, model, language or "English")
            units = fp.analyze(np.asarray(image.convert("RGB")), self.settings.margins)
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
            return book_read(len(self.store.open(book, model, language or "English")))
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
            cache = self.store.open(book, model, language or "English")
            units = fp.analyze(np.asarray(image.convert("RGB")), s.margins)
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
        it settles first, as ever)."""
        if not self._all_cached(image):
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
        """One heartbeat: Windows' notes taken in (`_take_notes`) and what `follow_decision` says done. Returns the ms
        to the next heartbeat."""
        f = self._follower()
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
        """The viewer's frame count (`capture.frame_count`: the capture's frame events), None without them."""
        win = self.selected
        if win is None:
            return None
        try:
            return frame_count(win.hwnd)
        except Exception:  # noqa: BLE001 - no count: polled as without frame events
            return None

    def _tick(self) -> None:
        """Follow = "poll": the capture of every auto_interval_ms (`_poll`). Follow = "events": the viewer looked at
        once, now (`_look`) - also what a request that waited for the models or for a job does (`_run_queued`)."""
        if self._follows_events():
            self._look()
        else:
            self._poll()

    def _poll(self) -> None:
        """Every auto_interval_ms (follow = "poll"; with "events" while the viewer itself is in front, and at each new
        frame it draws): the viewer's frame, captured once, goes on the page when it changed (the live view, while no
        job runs), and Auto translates it once it is a new page that has settled (alike on two ticks); a page that
        settles while the models load waits for them. A blank frame changes nothing - it is neither shown nor
        remembered - so the page is looked at again as soon as the viewer draws it. With "events" a page taken lately
        that comes again sharper is read again (`_check_sharper`), and a new page is followed at once until it settles
        (`_begin_follow`), or taken at once when the cache holds all of it (`_take_at_once`)."""
        win = self.selected
        try:
            if win is None or self.busy or self.batch is not None or self._black_open():
                return
            if not window_exists(win.hwnd):
                self._viewer_gone()
                return
            if not self._viewer_shows_book(win):
                return
            auto = bool(self.auto_var.get())
            events = self._follows_events()
            if events:
                self._following.polled = self._frame_count()  # (before the capture: a frame that comes during it is new)
            image = self._capture(win.hwnd)
            thumb = thumbnail(image)
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
                    frame_detail = detail(image, self._area_box(image))
                    if not self._take_at_once(win.hwnd, image, thumb, frame_detail):
                        self._begin_follow(win.hwnd, None, phase="settle", last=thumb, last_detail=frame_detail)
                return
            if self._auto_last is None or frames_differ(self._auto_last, thumb):
                if self._auto_candidate is not None and not frames_differ(self._auto_candidate, thumb, 0.5):
                    if not self.ready:
                        self._queue("auto")  # taken as soon as the models are loaded
                        return
                    self._auto_last = thumb
                    self._auto_candidate = None
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
        """The viewer's frame. Behind the reading window the screen shows this window, so there only a frame the
        viewer draws itself is taken; a blank one, or none, puts a message on the page instead (CaptureError). In
        the normal window a viewer that draws nothing is copied from the screen instead, unless the screen there
        shows part of TASlation - a picture of itself: then ViewerCovered, and the last good frame stays. A blank
        frame behind other windows is looked at raised, once (`_blank_behind`): a viewer whose frames are coming
        shows a blank page then, and that is no failure. A blank frame while TASlation is giving the window a new size
        is that change on its way (`_resizing`): it says nothing of the viewer, and nothing of the page. The frame
        taken is remembered with the viewer's frame count before it (`_last_frame`)."""
        self._captured = None
        try:
            seq = frame_count(hwnd)
        except Exception:  # noqa: BLE001 - not counted
            seq = None
        if self.reading:
            try:
                image = capture_window(hwnd, allow_screen_fallback=False)
                if is_blank(image) and self._blank_behind(hwnd):
                    raise CaptureError("the viewer gives no picture behind the reading window")
            except CaptureError:
                self._set_viewer_hidden(True)
                raise
            self._set_viewer_hidden(False)
        else:
            covered = self._covers_viewer(hwnd)
            image = capture_window(hwnd, allow_screen_fallback=not covered)
            if covered and is_blank(image) and self._blank_behind(hwnd):
                raise ViewerCovered("the viewer draws nothing behind TASlation")
            self._set_covered(False)
        black = self._see_black(hwnd, image)
        if is_blank(image):
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
        elif not self.reading:  # the reading window says so on the page
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
        thumb = thumbnail(image)
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
            thumb = thumbnail(self._capture(hwnd))
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
        thumb = thumbnail(image)
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
        switch: is the book in front? looked at once), moved or resized (looked at once it stops), closed."""
        now = time.monotonic()
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
                f.look_at = now + self.settings.settle_ms / 1000
            elif kind == "closed":
                f.look_at = None
                self._viewer_gone()
                if self.selected is not None:  # still there for a moment, or a run is on: looked at again
                    f.look_at = now + self.settings.settle_ms / 1000
        if getattr(self, "_over_on", False):
            self._front_as_it_is(f, now)

    def _front_as_it_is(self, f: Following, now: float) -> None:
        """Over the book (`overbook`, reading mode too): who is in front as Windows has it now, whatever the notes
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
        """The capture area of *image* (the margins every part of TASlation reads)."""
        return area.margins_to_box(self.settings.margins, image.size)

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
        if self.batch is not None or self._batching:
            f.look_at = time.monotonic() + again  # once the batch is done
            return
        if not window_exists(win.hwnd):
            self._viewer_gone()
            return
        if not self._viewer_shows_book(win):
            return
        if self.busy:
            self._queue("auto")  # looked at again once the job is done ...
            self._look_over_job(win)  # ... which gives way to a new page in the viewer
            return
        try:
            image = self._capture(win.hwnd)
        except CaptureError as e:
            self._capture_failed(e)
            f.look_at = time.monotonic() + again  # again while it lasts (covered, hidden, minimised)
            return
        thumb = thumbnail(image)
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
        if not self.auto_var.get() or (self._auto_last is not None and not frames_differ(self._auto_last, thumb)):
            return
        if seen is not None and not frames_differ(seen, thumb, 0.5):
            self._take(image, thumb)
        else:
            self._begin_follow(win.hwnd, None, phase="settle", last=thumb,
                               last_detail=detail(image, self._area_box(image)))

    def _look_over_job(self, win: Any) -> None:
        """A look while a page is translated with Auto on (`_look`): the viewer's frame compared with the page being
        translated, as `_watch_page` judges it (`_turned_from_job`). A new page there, alike on two looks, cancels the
        job (`_cancel_page`), so that a page turned by the wheel over the viewer while TASlation is in front does not
        wait for it; Auto takes the page once the job is gone (`_queue`: the look then finds it settled). A new page
        on one look may still be turning: the viewer is looked at again settle_ms later. Nothing is captured while
        no page job runs that the window can cancel."""
        cancel = getattr(self, "_page_cancel", None)
        if cancel is None or cancel.is_set() or not self.auto_var.get():
            return
        try:
            image = self._capture(win.hwnd)
        except CaptureError:
            return  # looked at again once the job is done
        thumb = thumbnail(image)
        if self._drew_nothing(thumb):  # the viewer drew nothing
            return
        f = self._following
        f.seen = thumb
        if self._turned_from_job(image, thumb):
            self._cancel_page()
        elif self._watch_candidate is not None:  # a new page on this look: has it settled?
            f.look_at = time.monotonic() + self.settings.settle_ms / 1000

    def _take(self, image: Image.Image, thumb: np.ndarray, frame_detail: np.ndarray | None = None,
              operation: bool = False, complete: bool | None = None) -> str:
        """A settled frame of the viewer taken as the page (follow = "events"). With Auto on a new page is started at
        once (`_on_new_page`), or - while the models load, a job or the batch runs - as soon as it can be (`_queue`:
        the viewer is looked at again then). With Auto off a page turned by TASlation's own *operation* is translated,
        as before. *complete*: the page job's (`_on_new_page`). Returns "started", "queued" or "same" (nothing to
        take)."""
        f = self._following
        if self.auto_var.get():
            if self._auto_last is not None and not frames_differ(self._auto_last, thumb):
                return "same"
            if not self.ready or self.busy or self.batch is not None or self._batching:
                f.taken = None
                self._cancel_page()  # the page being read is not on show any more
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
        """The page just taken, for the looks after it (a sharper frame of it may come)."""
        f = self._following
        f.retake = None
        if frame_detail is None:
            frame_detail = detail(image, self._area_box(image))
        f.taken = Taken(image, thumb, frame_detail, time.monotonic())

    def _check_sharper(self, image: Image.Image, thumb: np.ndarray) -> bool:
        """Whether *image* is the page taken lately (within RETAKE_WITHIN_MS) come again sharper; then it is read
        again from it (`_retake`)."""
        f = self._following
        taken = f.taken
        if taken is None or time.monotonic() - taken.at > RETAKE_WITHIN_MS / 1000 or frames_differ(taken.thumb, thumb):
            return False
        frame_detail = detail(image, self._area_box(image))
        if not sharper(taken.detail, frame_detail):
            return False
        self._retake(image, thumb, frame_detail)
        return True

    def _retake(self, image: Image.Image, thumb: np.ndarray, frame_detail: np.ndarray) -> None:
        """The page taken has come sharper (a viewer that draws a soft picture first): it is read from this frame - at
        once when the job on the softer frame is done; else, as no running job can be stopped, once it is (`_queue`;
        `_look` takes it then)."""
        f = self._following
        soft = f.taken.frame if f.taken is not None else None
        f.taken = None
        f.retake = Taken(image, thumb, frame_detail, time.monotonic(), soft)
        self._take_retake(image, thumb)

    def _take_retake(self, image: Image.Image, thumb: np.ndarray) -> None:
        """The sharper frame read as the page (`_retake`), once nothing runs: the job on the softer frame is cancelled
        where the window can cancel it (`_cancel_page`: nothing of it reaches the cache), else waited for (`_queue`).
        When that job read the whole page anew - none of it came from the cache - what it stored is dropped first, so
        that the bubbles are read again from the sharp picture (nothing older goes: a page that was in the cache,
        even in part, keeps its translations and is only drawn again on the sharp picture)."""
        f = self._following
        if not self.ready or self.busy or self.batch is not None or self._batching:
            self._cancel_page()
            self._queue("auto")  # `_look` takes it once the job is gone
            return
        retake, f.retake = f.retake, None
        result = self.last_result
        soft = retake.soft if retake is not None else None
        if (soft is not None and result is not None and result.cache_misses and not result.cache_hits
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

    def _cancel_page(self) -> bool:
        """The page translation that runs, cancelled where the window can cancel it (a page job with its own cancel
        event, `_page_cancel`, as Stop cancels it: nothing of it reaches the cache, and no line says it was
        stopped); False when it cannot be (then it is done first, and the page waits for it)."""
        cancel = getattr(self, "_page_cancel", None)
        if cancel is None or cancel.is_set() or self.batch is not None:
            return False
        self._cancel_why = "page"
        cancel.set()
        sync = getattr(self, "_sync_stop", None)
        if sync is not None:
            sync()
        return True

    # ------------------------------------------------------------------ an operation followed (events)
    def _begin_follow(self, hwnd: int, reference: Any, key: str = "", retried: bool = False, *,
                      phase: str = "change", last: np.ndarray | None = None,
                      last_detail: np.ndarray | None = None, operation: bool = False, fast: bool = False,
                      seq: int | None = None) -> None:
        """Follow the viewer's frame (follow = "events"), in place of a follow before: from *phase* "change" (an
        operation of TASlation's: awaited to change from *reference*, at FOLLOW_STEP_MS; with *seq*, the viewer's
        frame count when *reference* was captured, at each new frame as it comes, `_counted_change`), "settle" (it has
        changed: *last* is the frame seen; *operation*: after TASlation's own operation) or, *fast*, "recheck" (a page
        just taken at once: `_take_at_once`)."""
        f = self._follower()
        self._end_follow()
        if phase == "change":
            f.retake = None  # an operation: the page a sharper frame waited for is not the one to come
        op = Operation(hwnd, reference, key, retried or not key, time.monotonic(), phase, last, last_detail,
                       operation=phase == "change" or operation)
        f.op = op
        if phase == "settle":
            self._settle_on(op, last, last_detail, op.started)
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

    def _settle_on(self, op: Operation, thumb: np.ndarray | None, frame_detail: np.ndarray | None, now: float) -> None:
        """*op* followed from the frame *thumb* (seen at *now*) until it settles: two frames settle_ms apart alike -
        with the viewer's frames counted (`capture.frame_count`), no new frame for settle_ms, looked at every
        FRAME_STEP_MS, so that a frame that changes is seen as it comes (a page the cache holds is taken then:
        `_take_at_once`); else a look every settle_ms. After a key pressed for real, every settle_ms (the two turns
        are watched for)."""
        op.phase, op.last, op.last_detail, op.settles = "settle", thumb, frame_detail, 0
        op.last_at = op.settle_from = now
        op.fast_until = None
        op.seq = self._frame_count() if op.turned_at is None else None
        self._next_step(op, FRAME_STEP_MS if op.seq is not None else self.settings.settle_ms)

    def _end_follow(self) -> None:
        """The operation followed, if any, followed no further."""
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

    def _follow_step(self) -> None:
        """One step of the operation followed (`_step`); it ends unless the step asked for the next one."""
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

    def _next_step(self, op: Operation, ms: int) -> None:
        op.job = self.after(ms, self._follow_step)

    def _step(self, op: Operation) -> None:
        """The viewer's frame once, for the operation followed: "change" - every FOLLOW_STEP_MS until it differs from
        the frame before the operation (`_await_change`: a key the viewer ignored is pressed for real; with its frames
        counted, at each new frame as well, `_counted_change`); "settle" -
        every settle_ms until two frames are alike and the later is not sharper (frames counted: at every new frame,
        until none came for settle_ms; `_settle_on`), then the page is taken (`_take`; a page the cache holds is taken
        on the first frame of it, `_take_at_once`;
        after a key pressed for real, not before TWO_TURNS_S has passed since the page turned: a page that turns once
        more by then turned twice, `_say_two_turns`); "recheck" - RECHECK_MS after the page was taken: a frame of
        another page is followed until it settles, a sharper frame of the same page is read again, and a page taken at
        once in translator mode is completed from its frame once that has settled (`_completion`, `_complete_taken`).
        While a run reads the pages the reader turns only "change" is followed (the key got to the viewer); the run
        takes the page."""
        f = self._following
        if viewer_rests(self) or self._black_open() or (in_a_run(self) and op.phase != "change"):
            return  # (a viewer that stays black: the look when it is back takes it from there)
        now = time.monotonic()
        settle_s = self.settings.settle_ms / 1000
        if op.seq is not None and op.phase == "change" and not self._counted_change(op, now):
            return
        if op.seq is not None and op.phase in ("recheck", "settle"):  # the viewer's frames counted
            count = self._frame_count()
            if count is not None and count == op.seq:  # no new frame since the last look: nothing to capture ...
                if op.phase == "recheck":
                    if self._completion(op, now):
                        return
                    if op.fast_until is not None and now < op.fast_until:
                        self._next_step(op, FRAME_STEP_MS)
                    return
                if now - op.last_at < settle_s:  # ... yet; once settle_ms passed so, it has settled
                    self._next_step(op, FRAME_STEP_MS)
                    return
            op.seq = count
        try:
            image = self._capture(op.hwnd)
        except CaptureError as e:
            self._capture_failed(e)
            f.look_at = now + self.settings.auto_interval_ms / 1000  # looked at again while it lasts
            return
        thumb = thumbnail(image)
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
        frame_detail = detail(image, self._area_box(image))
        self._show_live(image, thumb)
        f.seen = thumb
        if op.phase == "settle":
            moving = frames_differ(op.last, thumb, 0.5) or sharper(op.last_detail, frame_detail)
            if op.turned_at is not None and not op.twice:  # after a key pressed for real: does it turn once more?
                if op.calm is not None and frames_differ(op.calm, thumb):
                    op.twice = True  # it had settled, and turned again: the posted key had arrived after all
                elif op.calm is None and not moving:
                    op.calm = thumb
            waiting = op.turned_at is not None and not op.twice and now - op.turned_at < TWO_TURNS_S
            if moving and op.turned_at is None and self._take_at_once(op.hwnd, image, thumb, frame_detail,
                                                                      op.operation):
                return  # (a page the cache holds: taken now, then rechecked)
            if op.seq is not None and op.turned_at is None:  # frames counted: settled after settle_ms without change
                if moving and now - op.settle_from < SETTLE_TRIES * settle_s:
                    op.last, op.last_detail, op.last_at = thumb, frame_detail, now
                    self._next_step(op, FRAME_STEP_MS)
                    return
                if not moving and now - op.last_at < settle_s:
                    self._next_step(op, FRAME_STEP_MS)
                    return
            elif (moving or waiting) and op.settles < SETTLE_TRIES:
                op.last, op.last_detail, op.settles = thumb, frame_detail, op.settles + 1
                self._next_step(op, self.settings.settle_ms)
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
        if frames_differ(taken.thumb, thumb):  # another page meanwhile: followed until it settles
            if self._take_at_once(op.hwnd, image, thumb, frame_detail, op.operation):
                return  # (a page the cache holds: taken now)
            self._settle_on(op, thumb, frame_detail, now)
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
        thumb = thumbnail(image)
        if frames_differ(taken.thumb, thumb):  # another page after all: followed until it settles
            self._settle_on(op, thumb, detail(image, self._area_box(image)), now)
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
            if in_a_run(self):
                return
            self._auto_candidate = None
            f.seen = thumb
            frame_detail = detail(image, self._area_box(image))
            if op.pressed:
                op.turned_at = now  # (does it turn once more, soon? "settle" watches)
            elif self._take_at_once(op.hwnd, image, thumb, frame_detail, operation=True, shown=False):
                return  # a page the cache holds: taken on its first frame, then rechecked
            self._show_live(image, thumb)  # the turned page shows at once
            self._settle_on(op, thumb, frame_detail, now)
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
            # real, once (`press_briefly`: the foreground handed over and back, no ALT tap).
            press_briefly(op.hwnd, op.key)
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
        if not self.reading:  # (the reading window shows the status line on the page by itself)
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
