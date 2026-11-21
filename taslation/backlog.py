"""Work behind the reader: the pages of normal reading the reader turned past go on being read and translated, from
the capture taken while the viewer showed them, while the reader reads on (no UI here; the window draws what the
events below tell it).

What enters the backlog, and only that way: a page job on show in the window (`ui.jobs._job_translate`) that the
reader turned away from (`pipeline.turn_away`) while it was still at work, whose frame the window had confirmed - it
stayed as it is for KEEP_SETTLES times settle_ms counted from the look (`ui.live._early_confirm`), the job's
`pipeline.PageGate` confirmed - and whose confirmation lasts for good (`PageGate.sealed`: the time a viewer that draws a
page soft first may still take it back is over). On such a viewer a frame that looked soft (`PageGate.soft`) is never
caught; nor is a frame confirmed while the frames still changed (``PageGate.settled`` False: the window confirms the
frame there is once the frames have kept changing for its SETTLE_TRIES looks, pages flipped through without a stop)
unless a look of the window's KEEP_SETTLES times settle_ms after then still saw it (``PageGate.settled_by``: the recheck
RECHECK_MS after the confirmation), nor a page whose job had no gate, nor one over the caps. A
page that is not caught is as it was before there was a backlog: the lines answered by then stay stored, and the page
is read and asked for the rest when the viewer shows it again (`Pipeline._complete_page`); the window is told so
("missed", the page counted among those that went by - ``backlog``'s dropped -; a page whose job had no gate "waiting",
not counted so: `Tracking.tell_not_caught`). A page job never leaves a stage told at work with nothing at work on it
(`Tracking._left`): stopped, its confirmation taken back, it waits; failed, it failed. (A page turned by TASlation's own
page key while a job ran was taken as settled, its job without a gate: `ui.live._await_change` now starts it early, a
gate of its own, as a page the viewer turned while the job ran.)

A page job of normal reading with Auto on still has no gate (`ui.jobs._start_translate` takes one only from the early
start, `ui.live._early_start`) when it is: F5 (`translate_now`); the sharper frame of a page read again
(`ui.live._take_retake`: a viewer that drew the page soft first, when the soft frame was taken - before the viewer is
known to draw so, or a soft frame not seen as soft); a frame taken as settled when the early start is not allowed
(`_early_allowed`: the first key of a viewer that ignores posted keys, pressed for real after a wait - ``turned_at`` -,
the first page of a book that waits for its start - `_translate_pending` -, a page the cache holds whole, also a soft
frame of one, and with early_start off); a frame two looks found alike with no follow under way (`ui.live._look`);
and in Translator mode the completion of a page taken from the cache (`_complete_taken`) and the completions after an
edit (follow = "poll" has no gate at all). Such a page was never confirmed - F5 captures at once, the settle path takes a
frame still changing after SETTLE_TRIES looks, a sharper frame is taken as it comes, no take-back time has passed on a
viewer that draws soft first - and so it is never caught (nothing from an unconfirmed frame is read or kept behind the
reader: the second of the design's guarantees); turned past, it is no page that went by too fast either, and waits for its next showing.

What is kept of a page caught, in memory only and never written anywhere: when the job had read every page unit it
reads (`PageWork.read_all`), its regions as read (copies taken before the translation changed them) and from them
the text and geometry of what is still to translate (`Pipeline.scanned_of`, a `ScannedUnit` per unit); else the frame
itself, packed without loss (`pageimages.pack`, on a thread of its own) until the backlog's read has read it
(`Pipeline.scan`), then dropped - the regions that read gave kept in its place. Caps: FRAME_CAP_MB of frames (counted
as they are until packed) and of the regions' masks together, and UNIT_CAP page units; a page that would pass either
is not caught (regions that would pass it are not kept: the page is then read again when shown). A thumbnail at most
`batch.THUMB_HEIGHT` px high of every screen told to the window (in memory, too small to read; never shown as a page).
The backlog is dropped (`drop`) when the window closes, for another book, another viewer window, and when a
whole-book run starts; pages already stored stay stored, and nothing more is told of a screen dropped. Auto off, Stop
and Tools > Release the model now pause it (`paused`); the next page job, or Auto on, goes on with it. A translator
that does not answer pauses it too ("no_answer", `follow_silence`: a request of any job's ended without an answer by
the rule of `translate.ollama`, asked again and, for the server TASlation started, the server started again): it goes
on by itself at the next answer of any request, and with F5 or Auto on (`go_on_after_silence`: asked once more, paused
again at the next such end); a request of its own that ends so is said (``model_status``, the sentence that the
translator does not answer), and never waits for a page job as a failure every request repeats does (`fatal`). The
backlog's requests come under that rule as any request does: the seconds one waited without a byte count with the
page on show's (`translate.ollama._Waits`; a turn that stops one keeps them), and its restart takes the step's
`Preempt` as a request's cancel. What one of them tells - a load, the rule's sentences - is the backlog's, not the
page on show's (`in_step`: ``behind`` in the ``model_status`` event): the window says it in its status line only,
never as the page's stage, its badge or its slot (`ui.jobs._model_status`).

A page shown again whose entry holds its regions as read is not read again (`Backlog.lend`, at the job's start: the
frame of the same page units as the capture they came from - `same_units` -, of its pixel size, nothing a reading
depends on changed since - `Pipeline.read_signature`): its page job takes copies of them (`PageWork.reuse`), finds
and reads nothing on the frame on show, letters the lines stored at once and asks for the rest only - over the
viewer's current frame, which the window takes as it takes a page the cache does not hold whole (on a viewer that
draws a page soft first: not a frame that looks soft, `ui.live`). A read of the backlog's stopped (by a turn, any
job) leaves its detection and the units read by then (``found``, counted against FRAME_CAP_MB with the frame, let go
with the entry): a page job of that very page takes them and reads the rest, and so does the backlog's own next read
of the frame (`Backlog._resume_of`, under the conditions `lend` has), rather than read it from the start. A page done
- by the backlog, or on show - keeps its regions as read (`Backlog.keep_done`, DONE_CAP_MB, the oldest go first): shown
again, it is lettered from the cache over them, nothing found or read, its bar done throughout (`Tracking._progress`:
a stage told done is never told at work again while the page is on show).

The order of work on the window's single worker (`Backlog.tick`, `Backlog.step`): the page on show first, always - a
step of the backlog is queued only while no page job runs or waits, nothing of a page job is held for its frame
(`Pipeline.behind_allowed`) and the window is idle (not busy, no whole-book run, nothing queued); in the hold of a page
job kept for now (the 2 s in which the window may still take its confirmation back on a viewer that draws a page soft
first: `Pipeline.behind_reads_allowed`) a read only, of the nearest page that needs one - it asks the translator
nothing and changes nothing a take-back puts back -, the decision held off while it runs (`Pipeline.holding_decision`;
the worker does not decide that job before such a step, `ui.jobs.next_job`) and stopped as the hold's time is up, the
translations waiting for the decision; then the page
nearest the reader ahead of it, one page at a time (`_next`, chosen anew at each step: the entry with the smallest
`Screen.sight` past the screen on show, or the one last on show, else the smallest of all - the page the reader is
likeliest to turn to next), all it needs in order - its read, then its translation - before the next page; then the
warming of the next page's first request (`Pipeline.warm_soon`). A step is small and stops as soon as a page
or any job comes (`Preempt`: `Pipeline.stop_warm` sets it, and the job queue not being empty does): a read stops between
two regions (between the detectors too), a translation between two line requests - the request in flight is given up,
its connection closed -, and the lines answered by then are stored as a page turned away from stores them (the
sequence's host `keeps_answered`: `translate.sequence`). A turn waits for no more than the step under way.

History: every request of the backlog's, as every request of the page on show, gets the pairs in the order the
requests were made (the translator's `GrowingContext`), so that each extends the one before. (A history in story order,
each request given the pairs of the pages before it in the story, was measured in the stand-in's scenario k and on
OpenMantra and taken out: no better translation, more of the server's time - docs/OFFLINE_VERIFICATION.md.)

Events to the window (through *post*, the window's ``_post``), outside a whole-book run, each with ``reading=True``:

* ``page_stage`` {seq, fingerprint, stage, state[, thumb], reading}: a screen of normal reading, at every change, in
  the shape a whole-book run's has (`batch`): *seq* the screen's place in the order of first sight in this book and
  session (1, 2, ...), *fingerprint* that of its first page unit, *stage* "read" or "translate", *state* "waiting",
  "working", "done", "failed", "skipped" or "missed" (a page that went by before it could be caught: on show
  SHOWN_AT_LEAST_MS or more, not soft, its frame changed before it was confirmed - or confirmed and not caught), and
  read "merged" {into} for a page that went by and was then seen to be the screen *into*. The first event of a screen
  has *thumb* (not a page that went by: it has none). Nothing is told of a frame before it is confirmed, but that it
  went by.
* ``page_on_show`` {seq, reading}: the screen on show changed (None: none of the book's).
* ``backlog`` {pages, lines, paused, dropped, reading}: the backlog's totals changed - the pages caught and not done
  yet, the lines still to translate of those read, whether it is paused, and the screens that went by too fast to be
  caught (`missed`, not caught or done since); *dropped* True (pages and lines 0) when the backlog was dropped, told
  before anything else of it, the screens then numbered from 1 again. Empty totals are not told before anything was.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Sequence

from .messages import Cancelled, message_of
from .pageimages import MB, Packed, pack, unpack

LOG = logging.getLogger(__name__)

FRAME_CAP_MB = 256  # the frames the backlog holds, packed (counted as they are until packed)
UNIT_CAP = 1000  # the page units it holds read (text and geometry)
SHOWN_AT_LEAST_MS = 150  # a frame dropped before its confirmation that was on show this long went by as a page
# (`ui.live.LEFT_PAGE_MS`: the time after which the window takes another frame for another page)
MERGE_WITHIN = 2  # a page that went by is the next screen confirmed when their fingerprints are this many times
# ``fingerprint_max_distance`` apart at most (a soft picture of the page, drawn first, and its sharp one)
HOLD_S = 0.0  # a step of the backlog that asks the model waits until the reader has stayed this long on a finished page
WAIT_STEP_S = 0.05  # how often a `Preempt` waited on looks whether a job waits for the worker
DONE_CAP_MB = 64  # the regions as read kept of the pages done (`Backlog.keep_done`: a page shown again is read nowhere)


def reading_event(window: Any, kind: str, data: dict[str, Any]) -> None:
    """(the window's event pump: `ui.jobs._handle_event`) An event of normal reading's - ``page_stage`` with
    ``reading``, ``page_on_show``, ``backlog`` - to the window's handler of it (``_on_reading_<kind>``), when it has
    one; else nothing: a whole-book run's page strip never takes them."""
    handler = getattr(window, f"_on_reading_{kind}", None)
    if handler is not None:
        handler(data)


_STEP = threading.local()  # (``on``: the thread is running a step of the backlog's: `in_step`)


def in_step() -> bool:
    """Whether the calling thread runs a step of the backlog's now (`Backlog.step`): what a request of the translator
    tells (its ``on_status``: a load, a request without an answer) is the backlog's then, which the window says in its
    status line only, never as the page on show's (`ui.jobs._model_status`)."""
    return bool(getattr(_STEP, "on", False))


def _allowed(pipeline: Any) -> tuple[bool, bool]:
    """Whether the backlog may work now at all, and whether a translation too: everything while nothing of a page
    job is held (`Pipeline.behind_allowed`), a read only in the hold of a page job kept for now
    (`Pipeline.behind_reads_allowed`)."""
    full = bool(pipeline.behind_allowed())
    reads = getattr(pipeline, "behind_reads_allowed", None)
    return full or (bool(reads()) if callable(reads) else False), full


class Preempt:
    """The cancel of a step of the backlog: set by `Pipeline.stop_warm` (a page to read, any job: `ui.jobs.next_job`)
    and by Stop; and set by itself while *waiting*() says a job waits for the worker. Taken where a
    `threading.Event` is (`is_set`, `wait`): the translator's requests and its restart (`ollama_start._wait_answer`)."""

    def __init__(self, waiting: Callable[[], bool] | None = None) -> None:
        self._event = threading.Event()
        self._waiting = waiting
        self.set_at: float | None = None  # (when it was first seen set: what a turn waited for is measured from it)

    def set(self) -> None:
        if self.set_at is None:
            self.set_at = time.monotonic()
        self._event.set()

    def is_set(self) -> bool:
        if self._event.is_set():
            return True
        waiting = self._waiting
        if waiting is not None and waiting():
            self.set()
            return True
        return False

    def wait(self, timeout: float | None = None) -> bool:
        """As `threading.Event.wait`: True once it is set - a job that comes to wait for the worker is looked for
        every WAIT_STEP_S -, False when *timeout* seconds went by first."""
        end = None if timeout is None else time.monotonic() + max(0.0, float(timeout))
        while not self.is_set():
            left = WAIT_STEP_S if end is None else min(WAIT_STEP_S, end - time.monotonic())
            if left <= 0:
                return False
            self._event.wait(left)
        return True


@dataclass(eq=False)
class Screen:
    """A screen of normal reading (one page or a two-page spread: what is captured and cached as one), as the
    window is told of it. *sight*: its place in the order of first sight (what the order of work goes by); *seq*:
    its number as told (0 until it is told, then 1, 2, ... in the order they are told)."""

    sight: int
    fingerprint: str
    aspect: float
    fingerprints: tuple[str, ...] = ()
    seq: int = 0
    stages: dict[str, str] = field(default_factory=dict)
    thumbed: bool = False
    missed: bool = False  # (told as gone by, not caught or done since)


@dataclass(eq=False)
class Entry:
    """A page turned past and caught: its screen, the viewer window it was captured from, and what is kept of it -
    its frame until read (``raw`` until packed, then ``frame``), or what is still to translate of its page units
    (``units``; ``regions``: as `process` left them, until made units) - and, once read, its regions as read
    (``read``, by unit index: what a page job takes in place of a reading, `Backlog.lend`), with the capture's page
    units, pixel size and `Pipeline.read_signature` (``page_units``, ``size``, ``sig``); ``found``: the detection of a
    read of the backlog's stopped half-way (``read`` then holds the units read by then, and ``aliases`` what
    `Pipeline.scan` noted of their regions: what the backlog's own next read of the frame takes up, `_resume_of`)."""

    screen: Screen
    hwnd: Any
    raw: Any = None  # (PIL image: until packed)
    frame: Packed | None = None
    held_bytes: int = 0  # (what the frame counts against FRAME_CAP_MB)
    regions: list[tuple[Any, list[Any]]] | None = None
    units: list[Any] | None = None
    caught_at: float = field(default_factory=time.monotonic)
    order: int = 0  # (the order it was caught in)
    read: dict[int, tuple[Any, list[Any]]] | None = None
    found: list[Any] | None = None
    page_units: list[Any] = field(default_factory=list)
    size: tuple[int, int] | None = None
    sig: bytes = b""
    kept_bytes: int = 0  # (what the regions kept count against FRAME_CAP_MB: their masks)
    aliases: dict[int, list[Any]] | None = None

    def let_go(self) -> None:
        """Everything it holds of the page goes (its screen stays)."""
        self.raw = self.frame = None
        self.held_bytes = 0
        self.read = self.found = self.aliases = None
        self.kept_bytes = 0

    @property
    def unit_count(self) -> int:
        if self.units is not None:
            return len(self.units)
        if self.regions is not None:
            return len(self.regions)
        return 0

    @property
    def lines(self) -> int:
        return sum(len(u.japanese()) for u in self.units) if self.units is not None else 0


def _frame_bytes(image: Any) -> int:
    try:
        w, h = image.size
        return int(w) * int(h) * len(image.getbands())
    except Exception:  # noqa: BLE001
        return 0


def _region_bytes(regions: Any) -> int:
    """What *regions* (TextRegions, or a dict of (unit, regions) by index) hold in arrays: their masks, and those of
    the classical regions that gave them their shapes."""
    if isinstance(regions, dict):
        return sum(_region_bytes(rs) for _u, rs in regions.values())
    total = 0
    for r in regions or ():
        for part in (r, getattr(r, "adopted", None), getattr(r, "after", None)):
            mask = getattr(part, "mask", None)
            total += int(getattr(mask, "nbytes", 0) or 0)
    return total


def same_units(kept: Sequence[Any], units: Sequence[Any], within: int) -> bool:
    """Whether the page units *units* of a capture are those *kept* (one by one: the same index and box, the aspect
    alike, the fingerprint within *within* bits, as `Backlog.screen_for` matches a screen)."""
    from .fingerprint import hamming

    if not kept or len(kept) != len(units):
        return False
    for a, b in zip(kept, units):
        if (int(a.index) != int(b.index) or tuple(a.box) != tuple(b.box)
                or abs(float(a.aspect) - float(b.aspect)) > 0.02 or hamming(a.fingerprint, b.fingerprint) > within):
            return False
    return True


def _not_the_same(pipeline: Any, kept: Sequence[Any], at: Any, sig: bytes, units: Sequence[Any], size: Any,
                  within: int) -> str:
    """Why what a read of a capture gave - its page units *kept*, its pixel size *at*, its `Pipeline.read_signature`
    *sig* - is not taken for a reading of a frame of page units *units* and pixel size *size*: "size", "units" (not
    `same_units`), "settings" (something a reading depends on changed since); "" when it is (`Backlog.lend`,
    `Backlog._resume_of`)."""
    if at is None or tuple(at) != tuple(size):
        return "size"
    if not same_units(kept, list(units), within):
        return "units"
    try:
        same = bool(sig) and sig == pipeline.read_signature(list(units))
    except Exception:  # noqa: BLE001 - not known: read as ever
        same = False
    return "" if same else "settings"


class _Recording(deque):  # type: ignore[type-arg]
    """The pairs a request of a translator that does not grow them starts from (a deque, as a whole-book run's), with
    those added to it since (``added``)."""

    def __init__(self, pairs: Any = (), maxlen: int | None = None) -> None:
        super().__init__(pairs, maxlen=maxlen)
        self.added: list[tuple[str, str]] = []

    def extend(self, pairs: Any) -> None:  # type: ignore[override]
        pairs = list(pairs)
        self.added.extend(pairs)
        super().extend(pairs)

    def append(self, pair: Any) -> None:  # type: ignore[override]
        self.added.append(pair)
        super().append(pair)


class _Host:
    """The host of `translate.sequence.translate_units` for a page of the backlog: its requests stopped by *stop*
    (`Preempt`), what was answered by then kept (``keeps_answered``), each unit stored as it completes
    (`Pipeline.commit_unit`)."""

    keeps_answered = True

    def __init__(self, pipeline: Any, stop: Any, lock: Any) -> None:
        self.pipeline = pipeline
        self.progress = SimpleNamespace(answering=0)
        self.retranslate = False
        self._view = None
        self._stop = stop
        self._fatal: Any = None
        self._storing = lock
        self.failed: list[Any] = []
        self.left: list[Any] = []
        self.complete: set[int] = set()
        self.final: set[int] = set()
        self.stored = 0  # lines stored

    def _translate_units(self, units: list[Any], recent: Any, notes_text: str, upcoming: list[str], language: str,
                         depth: int = 0) -> None:
        from .translate.sequence import translate_units

        translate_units(self, units, recent, notes_text, upcoming, language, depth)

    def _note(self, note: Any) -> None:
        LOG.debug("backlog: %s", getattr(note, "code", "note"))

    def _failed(self, error: Any) -> None:
        self.failed.append(error)

    def _reask_failed(self, e: Exception) -> bool:
        from .translate.base import worth_asking_again
        from .translate.sequence import fatal

        error = message_of(e)
        self._failed(error)
        if fatal(error):
            self._fatal = error
            return False
        return not self._stop.is_set() and worth_asking_again(error)

    def _leave_for_reading(self, units: Sequence[Any]) -> None:
        self.left.extend(units)

    def _on_slow(self, seconds: float) -> None:
        return None

    def _answered(self, answered: set[int], k: int, count: int) -> None:
        if 0 <= k < count:
            answered.add(k)

    def _model_loaded(self) -> None:
        return None

    def _store_unit(self, unit: Any, texts: dict[int, str], flags: dict[int, list[str]], fresh: int,
                    large: dict[int, tuple[int, int, float]] | None = None) -> bool:
        with self._storing:
            complete = (self.pipeline.commit_unit(unit, dict(texts), {i: list(f) for i, f in flags.items()},
                                                  dict(large)) if large
                        else self.pipeline.commit_unit(unit, dict(texts), {i: list(f) for i, f in flags.items()}))
        self.stored += fresh
        if complete:
            self.complete.add(id(unit))
        return bool(complete)

    def _units_final(self, units: Sequence[Any]) -> None:
        self.final.update(id(u) for u in units)


class Backlog:
    """The pages turned past of one window (see the module's docstring). *post*(kind, **data): the window's event
    queue. Its state is changed under its lock, from the window's thread (`tick`, the pauses, a confirmation) and its
    worker (a page job's `Tracking`, `step`)."""

    def __init__(self, post: Callable[..., None]) -> None:
        self._post = post
        self._lock = threading.RLock()
        self.screens: list[Screen] = []
        self.entries: list[Entry] = []
        self._held: dict[int, Entry] = {}  # (by sight: an entry whose page is on show again, its job at work)
        # (by sight, the oldest first: what a page done or failed kept of its read, for its next showing - `keep_done`)
        self._done: dict[int, Entry] = {}
        self._sight = 0
        self._seq = 0
        self._order = 0
        self.paused: set[str] = set()  # "auto", "stop", "release", "no_answer"
        # (the translator and its count of requests ended without an answer when the reader last went on: F5, Auto on)
        self._silence_seen: tuple[int, int] = (0, 0)
        self.hwnd: Any = None  # (the viewer window its pages come from)
        self.book = ""
        self._told: tuple[Any, ...] | None = None  # (None: nothing told yet)
        self._on_show: Any = ()  # (the seq last told on show; () before any)
        self._here = 0  # (the sight of the screen on show, or of the one last on show: where the work begins, `_next`)
        self.step_queued = False
        self.peak_bytes = 0  # (the most the frames have held at once: the scenario's measurement)
        self.caught = 0
        self.not_caught = 0
        self.last_wait: float | None = None  # (what the last pre-empted step held the worker after it was stopped)
        self.waits: list[float] = []
        self.last_frame_wait: float | None = None  # (s from the catch of the frame read last to the end of its read)
        self.frame_waits: list[float] = []
        self.lends: dict[str, int] = {}  # (what `lend` said, how many times: the scenario's measurement)
        self.resumes: dict[str, int] = {}  # (what came of the reads stopped before, `_resume_of`: the same)
        self.in_hold: dict[str, int] = {}  # (the steps run in a page job's hold, by what they did; "time up": stopped)
        self.finished_at = float("-inf")  # (when the page on show was last done: `HOLD_S`)
        self.fatal: Any = None  # (a failure every later request repeats: the backlog waits for a page job)
        # (page jobs turned past whose confirmation is kept for now, `Pipeline.decide_kept`: caught once sealed)
        self.pending: list[tuple["Tracking", Any]] = []
        self._packer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="taslation-backlog")

    # ------------------------------------------------------------------ the screens
    def screen_for(self, units: Sequence[Any], within: int) -> Screen:
        """The screen of a capture whose page units are *units*: the one of these first seen with the same first
        page unit (its fingerprint within *within* bits, `fingerprint.hamming`, and its aspect alike), else a new one,
        next in the order of first sight."""
        from .fingerprint import hamming

        first = units[0]
        with self._lock:
            best: tuple[int, Screen] | None = None
            for screen in self.screens:
                if abs(screen.aspect - float(first.aspect)) > 0.02:
                    continue
                d = hamming(screen.fingerprint, first.fingerprint)
                if d <= within and (best is None or d < best[0]):
                    best = (d, screen)
            if best is not None:
                return best[1]
            self._sight += 1
            screen = Screen(self._sight, first.fingerprint, float(first.aspect),
                            tuple(u.fingerprint for u in units))
            self.screens.append(screen)
            return screen

    def tell(self, screen: Screen, stage: str, state: str, image: Any = None, **extra: Any) -> None:
        """``page_stage`` for *screen* (numbered now when it was never told), when its *stage* changes to *state*;
        the screen's first event gets its thumbnail, made from *image* (none: a page that went by)."""
        from .batch import thumb_of

        with self._lock:
            if not any(s is screen for s in self.screens):
                return  # (a screen dropped - or merged into another - is never told of again: its seq is another's)
            if screen.stages.get(stage) == state and not extra:
                return
            screen.stages[stage] = state
            if not screen.seq:
                self._seq += 1
                screen.seq = self._seq
            data: dict[str, Any] = {"seq": screen.seq, "fingerprint": screen.fingerprint, "stage": stage,
                                    "state": state, "reading": True, **extra}
            if not screen.thumbed and image is not None:
                try:
                    data["thumb"] = thumb_of(image)
                    screen.thumbed = True
                except Exception:  # noqa: BLE001 - told without it
                    pass
            self._post("page_stage", **data)

    def show(self, screen: Screen | None) -> None:
        """``page_on_show`` when the screen on show is another than the one told last; nothing for a screen the
        backlog no longer has (dropped since)."""
        with self._lock:
            if screen is not None and not any(s is screen for s in self.screens):
                return
            if screen is not None:
                self._here = screen.sight
            seq = screen.seq if screen is not None and screen.seq else None
            if seq == self._on_show:
                return
            self._on_show = seq
            self._post("page_on_show", seq=seq, reading=True)

    def totals(self) -> None:
        """``backlog`` when its totals changed - never while they were never other than empty (no page, no line, no
        screen gone by: a window that was told nothing of the backlog is told nothing of its pauses either)."""
        with self._lock:
            entries = [*self.entries, *self._held.values()]
            told = (len(entries), sum(e.lines for e in entries), bool(self.paused),
                    sum(1 for s in self.screens if s.missed))
            if told == self._told or (self._told is None and not (told[0] or told[1] or told[3])):
                return
            self._told = told
            self._post("backlog", pages=told[0], lines=told[1], paused=told[2], dropped=told[3], reading=True)

    # ------------------------------------------------------------------ memory
    @property
    def frame_bytes(self) -> int:
        """What the backlog's frames hold (as they are until packed)."""
        with self._lock:
            return sum(e.held_bytes for e in [*self.entries, *self._held.values()])

    @property
    def region_bytes(self) -> int:
        """What the regions it keeps as read hold (their masks: `Entry.kept_bytes`)."""
        with self._lock:
            return sum(e.kept_bytes for e in [*self.entries, *self._held.values()])

    @property
    def bytes_held(self) -> int:
        """Frames and regions together: what FRAME_CAP_MB caps, and ``peak_bytes`` the most of."""
        with self._lock:
            return sum(e.held_bytes + e.kept_bytes for e in [*self.entries, *self._held.values()])

    @property
    def unit_total(self) -> int:
        with self._lock:
            return sum(e.unit_count for e in [*self.entries, *self._held.values()])

    @property
    def done_bytes(self) -> int:
        """What the reads kept of the pages done hold (`keep_done`: DONE_CAP_MB at most, apart from FRAME_CAP_MB)."""
        with self._lock:
            return sum(e.kept_bytes for e in self._done.values())

    def keep_done(self, entry: Entry) -> None:
        """(under the lock, or not) What *entry* - its page done or failed, by the backlog or on show - read of its
        page kept for the page's next showing (`lend`): its regions as read with the capture's page units, pixel size
        and read signature, nothing else (no frame). Then a page turned back to is lettered from the cache over those
        regions, nothing found or read on its frame - before, its read was let go with the page done and the page job
        found and read the page again (3.4 s on the processor), its bar "reading" over a page shown translated. The
        oldest go first past DONE_CAP_MB; dropped with the backlog."""
        if not entry.read or not entry.page_units or entry.size is None or not entry.sig:
            return
        kept = Entry(entry.screen, entry.hwnd, read=dict(entry.read), page_units=list(entry.page_units),
                     size=tuple(entry.size), sig=entry.sig, kept_bytes=entry.kept_bytes or _region_bytes(entry.read))
        if kept.kept_bytes > DONE_CAP_MB * MB:
            return
        with self._lock:
            if not any(s is entry.screen for s in self.screens):
                return  # (a screen of before a drop)
            self._done.pop(entry.screen.sight, None)
            self._done[entry.screen.sight] = kept
            while sum(e.kept_bytes for e in self._done.values()) > DONE_CAP_MB * MB:
                self._done.pop(next(iter(self._done)))

    def _pack_later(self, entry: Entry) -> None:
        """*entry*'s frame packed on the backlog's thread (`pageimages.pack`); what it counts goes down to the packed
        size."""
        def run() -> None:
            raw = entry.raw
            if raw is None:
                return
            try:
                packed = pack(raw)
            except Exception:  # noqa: BLE001 - kept as it is
                return
            with self._lock:
                if entry.raw is raw:
                    entry.frame, entry.raw = packed, None
                    entry.held_bytes = len(packed.data)

        try:
            self._packer.submit(run)
        except RuntimeError:  # (shut down: the window closes)
            pass

    # ------------------------------------------------------------------ catching
    def catch(self, screen: Screen, image: Any, work: Any, pipeline: Any, hwnd: Any) -> bool:
        """(the worker, a page job turned away from, its gate sealed) The page caught when the caps allow: what its
        job read (`PageWork.read_all`) or its frame. Whether it was caught."""
        read = dict(work.read) if work is not None and work.read_all and work.read else None
        sig = b""
        if read is not None:
            try:
                sig = pipeline.read_signature(list(work.units))
            except Exception:  # noqa: BLE001 - kept to translate, never taken as read by a page job
                sig = b""
        with self._lock:
            if not any(s is screen for s in self.screens):
                return False  # (a screen of before a drop)
            if read is not None:
                regions = [read[i] for i in sorted(read)]
                kept = _region_bytes(read)
                entry = Entry(screen, hwnd, regions=regions, read=read, page_units=list(work.units),
                              size=tuple(work.size) if getattr(work, "size", None) else None, sig=sig,
                              kept_bytes=kept)
                if self.unit_total + len(regions) > UNIT_CAP or self.bytes_held + kept > FRAME_CAP_MB * MB:
                    return False
            else:
                size = _frame_bytes(image)
                if image is None or self.bytes_held + size > FRAME_CAP_MB * MB or self.unit_total + 2 > UNIT_CAP:
                    return False
                entry = Entry(screen, hwnd, raw=image, held_bytes=size)
            self._order += 1
            entry.order = self._order
            self.entries = [e for e in self.entries if e.screen is not screen] + [entry]
            self._held.pop(screen.sight, None)
            self.peak_bytes = max(self.peak_bytes, self.bytes_held)
            self.caught += 1
            self.hwnd = hwnd
            screen.missed = False
        if entry.raw is not None:
            self._pack_later(entry)
        return True

    def hold(self, screen: Screen) -> None:
        """The page of *screen* is on show again, its job at work: its entry, if it has one, waits beside the backlog
        (`release`) - the page on show does what it would, taking what the entry read (`lend`)."""
        with self._lock:
            for e in self.entries:
                if e.screen is screen:
                    self.entries.remove(e)
                    self._held[screen.sight] = e
                    break

    def release(self, screen: Screen, done: bool) -> None:
        """The job of the page of *screen* on show is over: its entry held (`hold`) goes when the page is *done*, else
        back to the backlog (a page turned past not caught anew: what it kept is still to do)."""
        with self._lock:
            e = self._held.pop(screen.sight, None)
            if e is not None and e.screen is not screen:  # (another screen's of the same sight: one before a drop)
                self._held[screen.sight] = e
                return
            if e is not None and not done and all(x.screen is not screen for x in self.entries):
                self.entries.append(e)
                self.entries.sort(key=lambda x: x.screen.sight)
            elif e is not None and done:
                self._frame_gone(e)
                self.keep_done(e)  # (its read, for the page's next showing)
                e.let_go()

    def lend(self, screen: Screen, work: Any, pipeline: Any, within: int) -> str:
        """(the worker, a page job on show, its units known: `Tracking.on_units`) What the entry of *screen* held
        (`hold`) read of the page, given to the job (*work*, `PageWork`) in place of a reading of its frame: copies of
        its regions as read (``reuse``; ``lent``: the very ones kept, never changed, for what the job keeps of them;
        ``found``: the detection of a read stopped half-way, the units not read by then read from it). Only when the
        frame is of the same page units as the capture they came from (`same_units`), of its pixel size, and nothing
        a reading depends on changed since (`Pipeline.read_signature`). A page done has no entry: what its read kept
        is lent the same way (`keep_done`). What it said: "reused", "partial", or why the page is read as ever -
        "none" (no entry, or one with nothing read), "frame" (its frame not read yet), "size", "units", "settings"."""
        import copy

        with self._lock:
            e = self._held.get(screen.sight)
            if e is None or e.screen is not screen:
                e = self._done.get(screen.sight)
            if e is None or e.screen is not screen:
                why = "none"
            elif not e.read and e.found is None:
                why = "frame" if e.raw is not None or e.frame is not None else "none"
            else:
                why = ""
                read, found, kept, size, sig = e.read or {}, e.found, list(e.page_units), e.size, e.sig
        if not why:
            why = _not_the_same(pipeline, kept, size, sig, list(getattr(work, "units", ()) or ()),
                                tuple(getattr(work, "size", ()) or ()), within)
        if not why:
            copies = copy.deepcopy(read)  # (one copy of them all: what one region points at stays with the copy)
            work.reuse = {i: regions for i, (_unit, regions) in copies.items()}
            work.lent = {i: regions for i, (_unit, regions) in read.items()}
            if found is not None:
                work.found = copy.deepcopy(found)
            why = "partial" if found is not None else "reused"
        with self._lock:
            self.lends[why] = self.lends.get(why, 0) + 1
        return why

    def held_entry(self, screen: Screen) -> Entry | None:
        with self._lock:
            return self._held.get(screen.sight)

    # ------------------------------------------------------------------ dropping and pausing
    def drop(self, why: str = "") -> None:
        """Everything the backlog holds goes (another book, another viewer window, a whole-book run, the close): its
        frames and units, its screens; pages stored stay stored. The window is told at once, when anything was there:
        ``backlog`` with *dropped* True (pages and lines 0: the screens told so far are gone, the numbering starts at 1
        again), then the totals as ever."""
        with self._lock:
            had = bool(self.entries or self._held or self.screens or self.pending)
            self.entries, self._held, self.screens, self.pending = [], {}, [], []
            self._done = {}
            self._sight = self._seq = 0
            self._here = 0
            self.paused.discard("stop")
            self.paused.discard("release")
            self.fatal = None
            self.book = ""
            if had:
                self._post("backlog", pages=0, lines=0, paused=bool(self.paused), dropped=True, reading=True)
                self._told = ()  # (the totals told after it, empty as they are)
        if had:
            LOG.info("backlog dropped (%s)", why or "-")
            self.show(None)
            self.totals()

    def pause(self, why: str) -> None:
        with self._lock:
            self.paused.add(why)
        self.totals()

    def resume(self, why: str) -> None:
        with self._lock:
            self.paused.discard(why)
        self.totals()

    # ------------------------------------------------------------------ a translator that does not answer
    @staticmethod
    def _silence_of(pipeline: Any) -> tuple[int, tuple[int, int]]:
        """The translator's incident a request was ended in without an answer (0: none, or an answer since: its
        ``silent``) and the mark of where it stands (the translator, its ``endings``)."""
        translator = getattr(pipeline, "translator", None)
        silent = int(getattr(translator, "silent", 0) or 0)
        return silent, (id(translator), int(getattr(translator, "endings", 0) or 0))

    def follow_silence(self, pipeline: Any) -> None:
        """(`tick`) Paused ("no_answer") while the translator does not answer - a request of any job ended so (the
        rule of `translate.ollama`) and no answer came since - unless the reader went on since its last such end
        (`go_on_after_silence`); going on by itself once an answer comes."""
        silent, mark = self._silence_of(pipeline)
        if silent and mark != self._silence_seen:
            if "no_answer" not in self.paused:
                LOG.info("backlog paused: the translation program does not answer (incident %d)", silent)
                self.pause("no_answer")
        elif "no_answer" in self.paused:
            LOG.info("backlog goes on: %s", "an answer came" if not silent else "the reader went on")
            self.resume("no_answer")

    def go_on_after_silence(self, pipeline: Any) -> None:
        """(F5, Auto on) The pause for a translator that does not answer lifted: the backlog asks once more, and pauses
        again at the next request ended without an answer."""
        _silent, self._silence_seen = self._silence_of(pipeline)
        if "no_answer" in self.paused:
            self.resume("no_answer")

    def close(self) -> None:
        """(the window closes) Dropped, and its thread let go."""
        self.drop("close")
        self._packer.shutdown(wait=False)

    # ------------------------------------------------------------------ the work
    def _next(self, reads_only: bool = False) -> tuple[str, Entry] | None:
        """The next step, chosen anew at each: the page nearest the reader ahead of it - the entry with the smallest
        sight past the screen on show (or the one last on show, `_here`), else the smallest of all - and what it still
        needs, in order: its read (or its regions made units), then its translation. The next entry comes once it is
        done or failed (or the reader is elsewhere). With *reads_only* (a page job's hold: `step`) the nearest entry
        that still needs a read (or its regions made units), the translations left for after the hold, in the same
        order."""
        with self._lock:
            ahead = sorted((e for e in self.entries if e.screen.sight > self._here), key=lambda e: e.screen.sight)
            rest = sorted((e for e in self.entries if e.screen.sight <= self._here), key=lambda e: e.screen.sight)
            for e in [*ahead, *rest]:
                if e.frame is not None or e.raw is not None:
                    return "read", e
                if e.regions is not None:
                    return "make", e
                if e.units is not None and not reads_only:
                    return "translate", e
        return None

    def _frame_gone(self, entry: Entry) -> None:
        """(under the lock) *entry*'s frame let go: how long it was held, from its catch (the scenario's
        measurement)."""
        if entry.raw is not None or entry.frame is not None:
            self.last_frame_wait = time.monotonic() - entry.caught_at
            self.frame_waits.append(self.last_frame_wait)

    def has_work(self) -> bool:
        with self._lock:
            return bool(self.entries)

    def settle_pending(self) -> None:
        """The pages turned past whose confirmation was kept for now (`Pipeline.decide_kept`, before the worker's next
        job): caught once their gate is sealed; told as not caught when it was taken back (`Tracking.tell_not_caught`: its
        stages not done "missed" - nothing holds the page any more, and a sharper picture of it on show again has a job
        of its own that tells it anew). Before, such a page was only let go of, its stages left as they were (translate
        "waiting", read perhaps "working") with nothing at work on it."""
        with self._lock:
            pending, self.pending = self.pending, []
        left: list[tuple[Tracking, Any]] = []
        for tracking, work in pending:
            gate = tracking.gate
            if gate is not None and _sealed(gate):
                tracking.catch(work)
            elif gate is not None and gate.state == "confirmed":
                left.append((tracking, work))
            else:
                tracking.tell_not_caught()
        if left:
            with self._lock:
                self.pending = left + self.pending

    def tick(self, window: Any) -> None:
        """(the window's thread, at each look at its events) A step of the backlog queued for the worker when the
        window is idle (see the module's docstring) and nothing is paused; the backlog dropped when the viewer chosen
        is another window than its pages came from; paused while Auto is off."""
        auto = getattr(window, "auto_var", None)
        try:
            on = bool(auto.get()) if auto is not None else True
        except Exception:  # noqa: BLE001
            on = True
        if on and "auto" in self.paused:
            self.resume("auto")
            self.go_on_after_silence(getattr(window, "pipeline", None))
        elif not on and "auto" not in self.paused:
            self.pause("auto")
        self.follow_silence(getattr(window, "pipeline", None))
        if self.pending:
            self.settle_pending()
        if not self.has_work() or self.step_queued:
            return
        win = getattr(window, "selected", None)
        if self.hwnd is not None and (win is None or getattr(win, "hwnd", None) != self.hwnd):
            self.drop("another viewer window")
            return
        pipeline = getattr(window, "pipeline", None)
        if (self.paused or self.fatal is not None or pipeline is None or not getattr(window, "ready", False)
                or getattr(window, "busy", False) or getattr(window, "batch", None) is not None
                or getattr(window, "_batching", False) or getattr(window, "_queued", None) is not None
                or not window._jobs.empty()):
            return
        allowed, full = _allowed(pipeline)
        if not allowed or getattr(pipeline, "translator", None) is None:
            return
        nxt = self._next(reads_only=not full)
        if nxt is None:
            return
        if nxt[0] == "translate" and time.monotonic() - self.finished_at < HOLD_S:
            return
        self.step_queued = True

        def job() -> None:
            self._run(window)

        job.in_hold = not full  # type: ignore[attr-defined] # (a read in a hold: `ui.jobs.next_job` leaves it undecided)
        window._jobs.put(job)

    def _run(self, window: Any) -> None:
        """(the worker) One step, then the window's idle look queues the next."""
        try:
            self.step(window.pipeline, lambda: not window._jobs.empty(), getattr(window, "settings", None))
        finally:
            self.step_queued = False

    def step(self, pipeline: Any, waiting: Callable[[], bool] | None = None, settings: Any = None) -> str:
        """(the worker) One step of the backlog's work, stopped by a page or any job (`Preempt`); what it did: "read",
        "translate", "made", "stopped", "failed" or "" (nothing to do, or not now). In the hold of a page job kept for
        now (`Pipeline.behind_reads_allowed` without `behind_allowed`) only a read (or regions made units): the
        nearest one (`_next` with *reads_only*), with the decision of that job held off meanwhile
        (`Pipeline.holding_decision`: the window's close decides it on its own thread) and stopped as the hold's time
        is up (`Pipeline.kept_open_left`), what it read by then kept for its next read (`_resume_of`)."""
        allowed, full = _allowed(pipeline)
        if not allowed or self.paused:
            return ""
        if not full:
            with pipeline.holding_decision():
                allowed, full = _allowed(pipeline)  # (as it stands now: the close may have decided it meanwhile)
                if allowed and not full:
                    did = self._step(pipeline, waiting, settings, hold=True)
                    if did:
                        with self._lock:
                            self.in_hold[did] = self.in_hold.get(did, 0) + 1
                    return did
            if not allowed:
                return ""
        return self._step(pipeline, waiting, settings, hold=False)

    def _step(self, pipeline: Any, waiting: Callable[[], bool] | None, settings: Any, hold: bool) -> str:
        """`step`'s work: *hold* - a read only, stopped as the hold's time is up (not a turn: no wait counted)."""
        nxt = self._next(reads_only=hold)
        if nxt is None:
            return ""
        what, entry = nxt
        time_up = [False]

        def stopping() -> bool:
            if waiting is not None and waiting():
                return True
            if hold:
                left = pipeline.kept_open_left()
                if left is None or left <= 0.0:
                    time_up[0] = True
                    return True
            return False

        stop = Preempt(stopping if waiting is not None or hold else None)
        pipeline.behind_stop = stop
        last_seq = getattr(pipeline, "last_seq", None)
        _STEP.on = True  # (what the translator tells meanwhile is the backlog's: `in_step`)
        try:
            if what == "read":
                return self._read(pipeline, entry, stop)
            if what == "make":
                return self._make(pipeline, entry)
            return self._translate(pipeline, entry, stop, settings)
        except Cancelled:  # (a page, a job, Stop: the step ends, what it answered stored; it comes again)
            if time_up[0]:  # (the hold's time up: no turn waited for it)
                self.last_wait = None
                with self._lock:
                    self.in_hold["time up"] = self.in_hold.get("time up", 0) + 1
            elif stop.set_at is not None:
                waited = time.monotonic() - stop.set_at
                self.last_wait = waited
                self.waits.append(waited)
            with self._lock:
                if entry in self.entries:
                    self.tell(entry.screen, "translate" if what == "translate" else "read", "waiting")
            return "stopped"
        except Exception:  # noqa: BLE001 - never a box over the book: the page is read when shown again
            LOG.exception("backlog: a step failed")
            self._finish(entry, "translate" if what == "translate" else "read", "failed")
            return "failed"
        finally:
            _STEP.on = False
            pipeline.behind_stop = None
            if last_seq is not None:
                pipeline.last_seq = last_seq  # (where the book was read last is the reader's, not the backlog's)
            self.totals()

    def _read(self, pipeline: Any, entry: Entry, stop: Preempt) -> str:
        """The frame of *entry* read (`Pipeline.scan`, the cache's entries held to it), the units with something to
        translate kept, the frame dropped. A read of it stopped before is taken up where it stopped (`_resume_of`)."""
        with self._lock:
            raw, packed = entry.raw, entry.frame
        image = raw if raw is not None else unpack(packed) if packed is not None else None
        if image is None:
            return ""
        self.tell(entry.screen, "read", "working")
        size = tuple(image.size)
        # (the reading as it goes: `Pipeline.scan`'s *keep*; *resume*: what a read of this frame stopped before had)
        keep = SimpleNamespace(units=None, found=None, read={}, aliases={},
                               resume=self._resume_of(pipeline, entry, size))
        try:
            scan = pipeline.scan(image, skip_cached=True, cancel=stop, behind=True, keep=keep)
        except Cancelled:
            # (stopped half-way: its detection and the units read by then kept - for the page job of this very page
            # should the reader turn to it now, `lend`, and for the backlog's own next read of it, `_resume_of`)
            if keep.found is not None:
                self._keep_read(pipeline, entry, keep, size, partial=True)
            raise
        except Exception:  # noqa: BLE001 - the page is read when shown again
            LOG.exception("backlog: a page could not be read")
            self._finish(entry, "read", "failed")
            return "failed"
        del image
        self._keep_read(pipeline, entry, keep, size)
        with self._lock:
            self._frame_gone(entry)
            entry.raw = entry.frame = None
            entry.held_bytes = 0
            entry.units = [u for u in scan.units if u.japanese()]
            self.peak_bytes = max(self.peak_bytes, self.bytes_held)
        self.tell(entry.screen, "read", "done")
        if not entry.units:
            # (all of it in the cache by now: done; no line on it to translate: nothing needed)
            self._finish(entry, "translate", "done" if any(getattr(u, "kept", None) for u in scan.units) else "skipped")
        else:
            self.tell(entry.screen, "translate", "waiting")
        return "read"

    def _keep_read(self, pipeline: Any, entry: Entry, keep: Any, size: tuple[int, int], partial: bool = False) -> None:
        """What the read of *entry*'s frame gave (*keep*, `Pipeline.scan`'s), kept as read for a page job of the page
        (`lend`): the regions of each unit read, the capture's units, size and read signature; *partial*: the
        detection too, the read stopped half-way. Nothing is kept when that would pass the caps."""
        try:
            sig = pipeline.read_signature(list(keep.units or ()))
        except Exception:  # noqa: BLE001 - never taken as read
            return
        read = dict(keep.read)
        found = keep.found if partial else None
        aliases = dict(getattr(keep, "aliases", None) or {}) if partial else None
        kept = _region_bytes(read) + (_region_bytes(found) if found is not None else 0)
        with self._lock:
            # (the frame stays while a read stopped half-way; else it goes right after)
            others = self.bytes_held - entry.kept_bytes - (0 if partial else entry.held_bytes)
            if others + kept > FRAME_CAP_MB * MB:
                entry.read, entry.found, entry.aliases, entry.kept_bytes = None, None, None, 0
                return
            entry.read, entry.found, entry.aliases, entry.kept_bytes = read, found, aliases, kept
            entry.page_units, entry.size, entry.sig = list(keep.units or ()), size, sig
            if partial:
                self.peak_bytes = max(self.peak_bytes, self.bytes_held)

    def _resume_of(self, pipeline: Any, entry: Entry, size: tuple[int, int]) -> Callable[[Sequence[Any]], Any] | None:
        """(`_read`) What a read of *entry*'s frame stopped half-way kept (`_keep_read` *partial*: its detection, the
        units read by then, the regions those were read in place of), for its next read to take up rather than read
        the frame from the start: `Pipeline.scan`'s ``keep.resume``, called with the frame's page units, which gives
        copies of them (found, read, aliases) under the conditions `lend` gives them to a page job - the same page
        units as the read stopped had (`same_units`), the frame's pixel size *size*, nothing a reading depends on
        changed since (`Pipeline.read_signature`) -, else None and the frame is read from the start. None when
        nothing was kept. What came of it is counted in ``resumes`` ("resumed", or why not)."""
        import copy

        with self._lock:
            found, read, aliases = entry.found, entry.read, entry.aliases
            kept, at, sig = list(entry.page_units), entry.size, entry.sig
        if found is None:
            return None
        within = int(getattr(getattr(pipeline, "settings", None), "fingerprint_max_distance", 36) or 36)

        def resume(units: Sequence[Any]) -> Any:
            why = _not_the_same(pipeline, kept, at, sig, units, size, within)
            with self._lock:
                self.resumes[why or "resumed"] = self.resumes.get(why or "resumed", 0) + 1
            if why:
                return None
            return copy.deepcopy((found, dict(read or {}), dict(aliases or {})))  # (the entry's own never change)

        return resume

    def _make(self, pipeline: Any, entry: Entry) -> str:
        """The regions `process` read of *entry*'s page units made units to translate (`Pipeline.scanned_of`)."""
        with self._lock:
            regions, entry.regions = entry.regions or [], None
        units = [pipeline.scanned_of(unit, rs) for unit, rs in regions]
        with self._lock:
            entry.units = [u for u in units if u.japanese()]
        if not entry.units:
            self._finish(entry, "translate", "done")
        return "made"

    def _translate(self, pipeline: Any, entry: Entry, stop: Preempt, settings: Any) -> str:
        """What is still to translate of *entry*'s units (held to the cache first: `Pipeline.resync`) asked for, as a
        whole-book run asks for a run of units (`translate.sequence.translate_units`), stopped between line requests,
        what was answered by then stored. Its requests get the pairs in the order of work, as the page on show's do: a
        translator that grows them (`GrowingContext`) has them grown as it answers; for one that does not, the pairs
        answered (`_Recording`) join the pages' pairs (`Pipeline._context`) as the step ends, stopped or not."""
        from .translate.base import GrowingContext, grows_context

        units = [pipeline.resync(u) for u in entry.units or []]
        todo = [u for u in units if u.japanese()]
        if not todo:
            self._finish(entry, "translate", "done")
            return "translate"
        translator = pipeline.translator
        s = pipeline.settings
        language = getattr(s, "target_language", "English")
        notes = pipeline.premises()
        context = getattr(pipeline, "_context", None)
        on = bool(getattr(context, "maxlen", 0))
        grown_pairs = getattr(pipeline, "_grown", None)
        grown = on and grows_context(translator) and isinstance(grown_pairs, GrowingContext)
        self.tell(entry.screen, "translate", "working")
        host = _Host(pipeline, stop, threading.Lock())
        if grown:
            recent: Any = grown_pairs
        else:
            recent = _Recording(pipeline.context_pairs() if on else (),
                                maxlen=max(0, int(getattr(s, "context_pairs", 40))))
        try:
            host._translate_units(todo, recent, notes, [], language)
        finally:  # (stopped too - `Cancelled`, the lines answered by then stored -: what was answered goes on as context)
            if isinstance(recent, _Recording) and on and context is not None and recent.added:
                context.append(list(recent.added))  # (the pages' pairs of a translator that does not grow them)
        if host._fatal is not None:
            if getattr(host._fatal, "code", "") == "ollama.not_answering":
                # (the translator does not answer, asked again and, when TASlation started it, started again: the
                # backlog pauses until the next answer, F5 or Auto on - `follow_silence` - and says so, in the status
                # line only: it is no page on show's)
                self.pause("no_answer")
                self._post("model_status", message=host._fatal, behind=True)
            else:
                with self._lock:
                    self.fatal = host._fatal
            self.tell(entry.screen, "translate", "waiting")
            return "failed"
        if all(id(u) in host.complete for u in todo):
            self._finish(entry, "translate", "done")
        else:  # (a failed request, a line the model would not give: the page asks for it when shown again)
            self._finish(entry, "translate", "failed")
        return "translate"

    def _finish(self, entry: Entry, stage: str, state: str) -> None:
        with self._lock:
            if entry in self.entries:
                self.entries.remove(entry)
            self._frame_gone(entry)
            if stage == "translate":
                self.keep_done(entry)  # (its read, for the page's next showing)
            entry.let_go()
        self.tell(entry.screen, stage, state)

    # ------------------------------------------------------------------ what a turn waited for
    def wait_stats(self) -> dict[str, float]:
        w = sorted(self.waits)
        if not w:
            return {"n": 0}
        return {"n": len(w), "median": w[len(w) // 2], "max": w[-1]}


class Tracking:
    """A page job of normal reading on show in the window (`ui.jobs._job_translate`), told to the window as it goes
    and, turned past, caught by the backlog or not (see the module's docstring). Made on the worker for the job; its
    gate's confirmation calls it on the window's thread (`PageGate.on_kept`)."""

    def __init__(self, backlog: Backlog, pipeline: Any, image: Any, gate: Any, hwnd: Any) -> None:
        self.backlog = backlog
        self.pipeline = pipeline
        self.image = image
        self.gate = gate
        self.hwnd = hwnd
        self.screen: Screen | None = None
        self.read_done = False
        self.reported = False
        self.reuse = ""  # (what `Backlog.lend` said of the page: "" before its units were known)
        self.ended = False  # (`finished` or `cancelled` came: else the job failed, `over`)
        self.work: Any = None  # (the job's `PageWork`, once its units are known)
        self._lock = backlog._lock
        backlog.resume("stop")  # (the reader reads on: Stop and a release paused the backlog until now)
        backlog.resume("release")
        with backlog._lock:
            backlog.fatal = None

    def _within(self) -> int:
        return int(getattr(self.pipeline.settings, "fingerprint_max_distance", 36) or 36)

    def attach(self, work: Any) -> None:
        """*work* (`PageWork`) tells this as the job goes. A job without one (no gate: a page taken as settled, one
        from the cache) has its screen found and told when it ends (`finished`)."""
        if work is not None:
            work.on_units = self.on_units
            work.on_read = self.on_read

    def on_units(self, work: Any) -> None:
        """(the worker, in `process`) The capture's page units are known: its screen found, its entry held while it is
        on show - what the backlog read of the page given to the job in place of a reading (`Backlog.lend`) -; told to
        the window once the gate is confirmed (at once when it is)."""
        units = list(work.units or [])
        self.work = work
        if not units:
            self.backlog.show(None)
            return
        screen = self.backlog.screen_for(units, self._within())
        self.screen = screen
        self.backlog.hold(screen)
        self.reuse = self.backlog.lend(screen, work, self.pipeline, self._within())
        on_kept = getattr(self.gate, "on_kept", None)
        if self.gate is None:
            self._report()
        elif on_kept is not None:
            on_kept(self._report)

    def on_read(self, work: Any) -> None:
        """(the worker) Every unit the job reads is read (none to read: a page the cache holds, `Pipeline.process`)."""
        with self._lock:  # (the backlog's: told in order with the confirmation's, `_report`)
            self.read_done = True
            if self.reported and self.screen is not None:
                self._progress("read", "done")
                self._progress("translate", "working")

    def _progress(self, stage: str, state: str) -> None:
        """(under the lock) The job's progress told: a stage the screen was told done or skipped - the page done by
        the backlog or a job before, shown translated from the cache - is never told at work again while it is on
        show (its job's end says what came of it, `finished`)."""
        screen = self.screen
        if screen is None:
            return
        if state == "working" and screen.stages.get(stage) in ("done", "skipped"):
            return
        self.backlog.tell(screen, stage, state, self.image)

    def _report(self) -> None:
        """(the frame confirmed) The screen on show, and how far its job is: its read done once every unit is read,
        or when the backlog's read of it is lent whole (`Backlog.lend`: nothing read on show)."""
        screen = self.screen
        if screen is None:
            return
        b = self.backlog
        with self._lock:
            self.reported = True
            screen.missed = False  # (a page told as gone by is on show now)
            read = self.read_done or self.reuse == "reused"
            self._progress("read", "done" if read else "working")
            if read:
                self._progress("translate", "working")
            merge_missed(b, screen, self._within())
            b.show(screen)
        b.totals()

    def _left(self, state: str) -> None:
        """The job ends with its page neither done nor caught: a stage it told the window as at work is told *state*
        ("waiting": still to do - read, or asked for the rest, when shown again -; "failed": the job failed), never
        left at work with nothing at work on it. Nothing when it told the window nothing."""
        screen = self.screen
        if screen is None or not self.reported:
            return
        for stage in ("read", "translate"):
            if screen.stages.get(stage) == "working":
                self.backlog.tell(screen, stage, state, self.image)
        self.backlog.totals()

    def finished(self, result: Any) -> None:
        """(the worker) The job is done, the page shown: its stages ended as they came out."""
        self.ended = True
        b = self.backlog
        b.finished_at = time.monotonic()
        screen = self.screen
        if screen is None:
            units = list(getattr(result, "units", None) or [])
            if not units:
                b.show(None)
                return
            screen = self.screen = b.screen_for(units, self._within())
        if self.gate is not None and not self.gate.confirmed:  # (its confirmation taken back: a sharper picture
            b.release(screen, done=False)  # of the page came, whose own job tells it)
            self._left("waiting")
            return
        regions = list(getattr(result, "regions", None) or [])
        untranslated = any(getattr(r, "status", "") == "untranslated" for r in regions)
        translated = any(getattr(r, "translated_text", "") for r in regions)
        error = getattr(result, "error", "")
        b.tell(screen, "read", "done", self.image)
        if error or untranslated:
            b.tell(screen, "translate", "failed", self.image)
        else:
            b.tell(screen, "translate", "done" if translated else "skipped", self.image)
        screen.missed = False
        b.release(screen, done=not (error or untranslated))
        self._keep_read(screen)
        b.show(screen)
        b.totals()

    def _keep_read(self, screen: Screen) -> None:
        """(the page done on show) What the job read of every unit it read, kept for the page's next showing
        (`Backlog.keep_done`): that showing finds and reads nothing, as for a page the backlog did, where what was
        lettered ahead of it (`Pipeline.keep_shown`) does not serve it (another frame of the page, of the same size)."""
        work = self.work
        if work is None or not getattr(work, "read", None) or not getattr(work, "read_all", False):
            return
        try:
            sig = self.pipeline.read_signature(list(work.units))
        except Exception:  # noqa: BLE001 - not kept: the next showing reads the page as ever
            return
        size = tuple(work.size) if getattr(work, "size", None) else None
        self.backlog.keep_done(Entry(screen, self.hwnd, read=dict(work.read), page_units=list(work.units),
                                     size=size, sig=sig))

    def cancelled(self, turned: bool, work: Any) -> None:
        """(the worker, the job raised `Cancelled`) *turned*: the reader turned away from the page (`turn_away`); a
        page whose gate was sealed is caught (when the caps allow), one whose frame went by is told as such, one with
        no gate (F5, a page taken as settled, a sharper frame read again: the module's docstring) is told as waiting
        for its next showing, not caught."""
        self.ended = True
        b = self.backlog
        gate = self.gate
        screen = self.screen
        gone_at, since = getattr(gate, "gone_at", None), getattr(gate, "shown_since", None)
        if gate is not None and gate.state == "dropped" and screen is not None and not _soft(gate) and \
                gone_at is not None and since is not None and (gone_at - since) * 1000 >= SHOWN_AT_LEAST_MS and \
                getattr(gate, "gone_by", "") == "window":
            # (its frame changed before it was confirmed: a page that went by - unless the screen is known already)
            b.release(screen, done=False)
            if not screen.stages and not screen.seq:
                screen.missed = True
                b.tell(screen, "read", "missed")
            b.totals()
            return
        if screen is None:
            return
        if gate is not None and not gate.confirmed:  # (its confirmation taken back, or never given: what it told
            b.release(screen, done=False)  # the window waits for the page's next job)
            self._left("waiting")
            return
        if not turned:  # (Stop, the close: the page stays as it is - still to do, read or asked when shown again)
            for stage in ("read", "translate"):
                if screen.stages.get(stage) not in ("done", "failed", "skipped"):
                    b.tell(screen, stage, "waiting")
            b.release(screen, done=False)
            b.totals()
            return
        if gate is not None and not _sealed(gate) and not _soft(gate) and _settled(gate):  # (kept for now: caught
            # once sealed, `Backlog.settle_pending`)
            with b._lock:
                b.pending.append((self, work))
            b.tell(screen, "translate", "waiting", self.image)
            return
        self.catch(work)

    def catch(self, work: Any) -> None:
        """(the page turned past, its gate sealed or soft, or none) Caught when it may be (see the module's
        docstring), else told as not caught (`tell_not_caught`): a page whose job had a gate as one that went by, one
        whose job had none as one waiting for its next showing - it is no page that went by too fast."""
        b = self.backlog
        gate = self.gate
        screen = self.screen
        if screen is None:
            return
        caught = gate is not None and _sealed(gate) and not _soft(gate) and _settled(gate) and \
            b.catch(screen, self.image, work, self.pipeline, self.hwnd)
        if not caught:
            self.tell_not_caught(went_by=gate is not None)
            return
        b.tell(screen, "read", "done" if work is not None and work.read_all and work.read else "waiting", self.image)
        b.tell(screen, "translate", "waiting", self.image)
        b.totals()

    def tell_not_caught(self, went_by: bool = True) -> None:
        """(the page turned past, not caught: `catch`, and `Backlog.settle_pending` for a page kept for now whose
        confirmation was taken back) What its entry held goes back to the backlog (`Backlog.release`), and every stage
        not done is told "missed", the screen counted among the pages gone by (``backlog``'s dropped) when its
        translation was missed - as "waiting" when the backlog goes on with an entry of the page that was held while it
        was on show, and when the page did not go by (*went_by* False: a page job with no gate, which is never caught -
        see the module's docstring -: read, or asked for the rest, when the viewer shows it again, as after Stop). Every
        such page is counted in ``not_caught``."""
        b = self.backlog
        screen = self.screen
        if screen is None:
            return
        b.not_caught += 1
        b.release(screen, done=False)
        with b._lock:
            queued = any(e.screen is screen for e in b.entries)
        state = "missed" if went_by and not queued else "waiting"
        for stage in ("read", "translate"):
            if screen.stages.get(stage) not in ("done", "failed", "skipped"):
                b.tell(screen, stage, state, self.image)
        screen.missed = state == "missed" and screen.stages.get("translate") == "missed"
        b.totals()

    def over(self) -> None:
        """(the worker, the job's end, however it ended) What the backlog held for the page while it was on show
        (`Backlog.hold`) and was not let go of goes back to it; a job that ended neither done nor cancelled (it
        failed) leaves no stage told at work."""
        screen = self.screen
        if screen is not None and self.backlog.held_entry(screen) is not None:
            self.backlog.release(screen, done=False)
        if not self.ended:
            self._left("failed")

    def kept_later(self, work: Any) -> bool:
        """A page turned past whose confirmation was kept for now (`Pipeline.decide_kept`): caught once it is sealed."""
        return self.gate is not None and self.gate.confirmed and not _sealed(self.gate)


def _soft(gate: Any) -> bool:
    """Whether *gate*'s frame looked soft (`ui.live`: a viewer seen to draw a page soft first)."""
    return bool(getattr(gate, "soft", False))


def _settled(gate: Any) -> bool:
    """Whether *gate*'s frame had stayed as it is when it was confirmed (``settled``, set by `ui.live`; a gate it was
    not set on: confirmed is settled)."""
    return bool(getattr(gate, "settled", True))


def _sealed(gate: Any) -> bool:
    """Whether *gate*'s confirmation lasts for good (`PageGate.sealed`; a gate that cannot be taken back: confirmed)."""
    sealed = getattr(gate, "sealed", None)
    return bool(gate.confirmed if sealed is None else sealed)


def merge_missed(backlog: Backlog, screen: Screen, within: int) -> None:
    """A screen confirmed: a page told as gone by just before it whose fingerprint is near enough
    (MERGE_WITHIN times *within*) was this screen (a soft picture of it, drawn first): told as merged into it."""
    from .fingerprint import hamming

    with backlog._lock:
        gone = [s for s in backlog.screens if s.missed and s is not screen and s.seq
                and hamming(s.fingerprint, screen.fingerprint) <= MERGE_WITHIN * within]
        for s in gone:
            backlog.screens.remove(s)
    for s in gone:
        backlog._post("page_stage", seq=s.seq, fingerprint=s.fingerprint, stage="read", state="merged",
                      into=screen.seq or None, reading=True)


# ---------------------------------------------------------------------- the window's side (`ui.jobs`)
def backlog_of(window: Any, make: bool = True) -> Backlog | None:
    """*window*'s backlog (made on first use with *make*: its events go to the window's ``_post``)."""
    backlog = getattr(window, "_backlog", None)
    if backlog is None and make and hasattr(window, "_post"):
        backlog = Backlog(window._post)
        window._backlog = backlog
    return backlog


def tracking_for(window: Any, image: Any, gate: Any, again: Any = None, replace_edited: bool = False) -> Tracking | None:
    """(the worker, a page job of *window* starting) Its `Tracking`: None for "Translate again", and while a
    whole-book run is on (its own events tell its pages)."""
    if again is not None or replace_edited or getattr(window, "batch", None) is not None or \
            getattr(window, "_batching", False):
        return None
    pipeline = getattr(window, "pipeline", None)
    backlog = backlog_of(window)
    if pipeline is None or backlog is None:
        return None
    backlog.settle_pending()  # (the job before it, kept for now, was decided before this one: `next_job`)
    if getattr(pipeline, "behind_paused", False):
        pipeline.behind_paused = False  # (a page read again: the model is wanted again, `release`)
    win = getattr(window, "selected", None)
    return Tracking(backlog, pipeline, image, gate, getattr(win, "hwnd", None))


def drop_backlog(window: Any, why: str) -> None:
    """*window*'s backlog dropped (another book, a whole-book run starting)."""
    backlog = backlog_of(window, make=False)
    if backlog is not None:
        backlog.drop(why)


def pause_backlog(window: Any, why: str) -> None:
    """*window*'s backlog paused (Stop): its step under way stopped (`Pipeline.stop_warm`)."""
    backlog = backlog_of(window, make=False)
    if backlog is None:
        return
    backlog.pause(why)
    stop = getattr(getattr(window, "pipeline", None), "behind_stop", None)
    if stop is not None:
        stop.set()


def go_on_after_silence(window: Any) -> None:
    """(F5) *window*'s backlog paused for a translator that does not answer goes on (`Backlog.go_on_after_silence`)."""
    backlog = backlog_of(window, make=False)
    if backlog is not None:
        backlog.go_on_after_silence(getattr(window, "pipeline", None))


def tick(window: Any) -> None:
    """(the window's event pump) `Backlog.tick`; Tools > Release the model now (`Pipeline.stop_warm` with *wait*)
    pauses it until the next page job."""
    backlog = backlog_of(window, make=False)
    if backlog is None:
        return
    if getattr(getattr(window, "pipeline", None), "behind_paused", False) and "release" not in backlog.paused:
        backlog.pause("release")
    backlog.tick(window)


def holds_warming(window: Any) -> bool:
    """Whether the warming of the next page's first request waits (`ui.jobs._warm_when_idle`): the backlog has work
    it may do now (the warming comes once it is done, and after each page of it)."""
    backlog = backlog_of(window, make=False)
    return backlog is not None and backlog.has_work() and not backlog.paused and backlog.fatal is None
