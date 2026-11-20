"""Work behind the reader: the pages of normal reading the reader turned past go on being read and translated, from
the capture taken while the viewer showed them, while the reader reads on (no UI here; the window draws what the
events below tell it).

What enters the backlog, and only that way: a page job on show in the window (`ui.jobs._job_translate`) that the
reader turned away from (`pipeline.turn_away`) while it was still at work, whose frame the window had confirmed - it
stayed as it is for KEEP_SETTLES times settle_ms counted from the look (`ui.live._early_confirm`), the job's
`pipeline.PageGate` confirmed - and whose confirmation lasts for good (`PageGate.sealed`: the time a viewer that draws a
page soft first may still take it back is over). On such a viewer a frame that looked soft (`PageGate.soft`) is never
caught; nor is a frame confirmed while the frames still changed (``PageGate.settled`` False: the window confirms the
frame there is once the frames have kept changing for its SETTLE_TRIES looks, pages flipped through without a stop),
nor a page whose job had no gate (a page the window took as settled), nor one over the caps. A page that is
not caught is as it was before there was a backlog: the lines answered by then stay stored, and the page is read and
asked for the rest when the viewer shows it again (`Pipeline._complete_page`).

What is kept of a page caught, in memory only and never written anywhere: when the job had read every page unit it
reads (`PageWork.read_all`), the text and geometry of what is still to translate (`Pipeline.scanned_of`, a
`ScannedUnit` per unit); else the frame itself, packed without loss (`pageimages.pack`, on a thread of its own) until
the backlog's read has read it (`Pipeline.scan`), then dropped. Caps: FRAME_CAP_MB of frames (counted as they are until
packed) and UNIT_CAP page units; a page that would pass either is not caught. A thumbnail at most `batch.THUMB_HEIGHT`
px high of every screen told to the window (in memory, too small to read; never shown as a page). The backlog is
dropped (`drop`) when the window closes, for another book, another viewer window, and when a whole-book run starts;
pages already stored stay stored. Auto off, Stop and Tools > Release the model now pause it (`paused`); the next page
job, or Auto on, goes on with it.

The order of work on the window's single worker (`Backlog.tick`, `Backlog.step`): the page on show first, always - a
step of the backlog is queued only while no page job runs or waits, nothing of a page job is held for its frame
(`Pipeline.behind_allowed`) and the window is idle (not busy, no whole-book run, nothing queued); then the backlog's
reads in the order the pages were first seen; then its translations in story order (the same order: `Screen.sight`);
then the warming of the next page's first request (`Pipeline.warm_soon`). A step is small and stops as soon as a page
or any job comes (`Preempt`: `Pipeline.stop_warm` sets it, and the job queue not being empty does): a read stops between
two regions (between the detectors too), a translation between two line requests - the server finishes the prompt it
was sent -, and the lines answered by then are stored as a page turned away from stores them (the sequence's host
`keeps_answered`: `translate.sequence`). A turn waits for no more than the step under way.

History: a request behind the reader gets the pairs of the nearest translated pages before it in the story
(`translate.base.StoryContext`, keyed by `Screen.sight`) when ``HISTORY`` is "story"; with "work" (the fallback, the
rule before there was a backlog) the pairs in the order the requests were made.

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
  caught (`missed`, not caught or done since).
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
HISTORY = "story"  # "story": a request behind the reader gets the pairs of the pages before it in the story; "work":
# in the order the requests were made (the rule before there was a backlog)
HOLD_S = 0.0  # a step of the backlog that asks the model waits until the reader has stayed this long on a finished page
SWITCH_HOLD_S = 2.0  # (story history) a request whose pairs part from the server's waits this long on a finished page
SWITCH_PAIRS = 8  # ... and gets this many of the pairs that part at most: some 0.5 s of the server's time


def reading_event(window: Any, kind: str, data: dict[str, Any]) -> None:
    """(the window's event pump: `ui.jobs._handle_event`) An event of normal reading's - ``page_stage`` with
    ``reading``, ``page_on_show``, ``backlog`` - to the window's handler of it (``_on_reading_<kind>``), when it has
    one; else nothing: a whole-book run's page strip never takes them."""
    handler = getattr(window, f"_on_reading_{kind}", None)
    if handler is not None:
        handler(data)


class Preempt:
    """The cancel of a step of the backlog: set by `Pipeline.stop_warm` (a page to read, any job: `ui.jobs.next_job`)
    and by Stop; and set by itself while *waiting*() says a job waits for the worker."""

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


@dataclass(eq=False)
class Screen:
    """A screen of normal reading (one page or a two-page spread: what is captured and cached as one), as the
    window is told of it. *sight*: its place in the order of first sight (the story order: the history's key); *seq*:
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
    (``units``; ``regions``: as `process` left them, until made units)."""

    screen: Screen
    hwnd: Any
    raw: Any = None  # (PIL image: until packed)
    frame: Packed | None = None
    held_bytes: int = 0  # (what the frame counts against FRAME_CAP_MB)
    regions: list[tuple[Any, list[Any]]] | None = None
    units: list[Any] | None = None
    caught_at: float = field(default_factory=time.monotonic)
    order: int = 0  # (the order it was caught in)

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
        self._sight = 0
        self._seq = 0
        self._order = 0
        self.paused: set[str] = set()  # "auto", "stop", "release"
        self.hwnd: Any = None  # (the viewer window its pages come from)
        self.book = ""
        self._told: tuple[int, int, bool, int] | None = None
        self._on_show: Any = ()  # (the seq last told on show; () before any)
        self.step_queued = False
        self.peak_bytes = 0  # (the most the frames have held at once: the scenario's measurement)
        self.caught = 0
        self.not_caught = 0
        self.last_wait: float | None = None  # (what the last pre-empted step held the worker after it was stopped)
        self.waits: list[float] = []
        self.finished_at = float("-inf")  # (when the page on show was last done: `HOLD_S`)
        self.hold_until = float("-inf")  # (a request that would part from the server's pairs waits until then)
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
        """``page_on_show`` when the screen on show is another than the one told last."""
        with self._lock:
            seq = screen.seq if screen is not None and screen.seq else None
            if seq == self._on_show:
                return
            self._on_show = seq
            self._post("page_on_show", seq=seq, reading=True)

    def totals(self) -> None:
        """``backlog`` when its totals changed."""
        with self._lock:
            entries = [*self.entries, *self._held.values()]
            told = (len(entries), sum(e.lines for e in entries), bool(self.paused),
                    sum(1 for s in self.screens if s.missed))
            if told == self._told:
                return
            self._told = told
            self._post("backlog", pages=told[0], lines=told[1], paused=told[2], dropped=told[3], reading=True)

    # ------------------------------------------------------------------ memory
    @property
    def frame_bytes(self) -> int:
        with self._lock:
            return sum(e.held_bytes for e in [*self.entries, *self._held.values()])

    @property
    def unit_total(self) -> int:
        with self._lock:
            return sum(e.unit_count for e in [*self.entries, *self._held.values()])

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
        with self._lock:
            if work is not None and work.read_all and work.read:
                regions = [work.read[i] for i in sorted(work.read)]
                entry = Entry(screen, hwnd, regions=regions)
                if self.unit_total + len(regions) > UNIT_CAP:
                    return False
            else:
                size = _frame_bytes(image)
                if image is None or self.frame_bytes + size > FRAME_CAP_MB * MB or self.unit_total + 2 > UNIT_CAP:
                    return False
                entry = Entry(screen, hwnd, raw=image, held_bytes=size)
            self._order += 1
            entry.order = self._order
            self.entries = [e for e in self.entries if e.screen is not screen] + [entry]
            self._held.pop(screen.sight, None)
            self.peak_bytes = max(self.peak_bytes, self.frame_bytes)
            self.caught += 1
            self.hwnd = hwnd
            screen.missed = False
        if entry.raw is not None:
            self._pack_later(entry)
        return True

    def hold(self, screen: Screen) -> None:
        """The page of *screen* is on show again, its job at work: its entry, if it has one, waits beside the backlog
        (`release`) - the page on show does what it would."""
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
            if e is not None and not done and all(x.screen is not screen for x in self.entries):
                self.entries.append(e)
                self.entries.sort(key=lambda x: x.screen.sight)

    def held_entry(self, screen: Screen) -> Entry | None:
        with self._lock:
            return self._held.get(screen.sight)

    # ------------------------------------------------------------------ dropping and pausing
    def drop(self, why: str = "") -> None:
        """Everything the backlog holds goes (another book, another viewer window, a whole-book run, the close): its
        frames and units, its screens; pages stored stay stored."""
        with self._lock:
            had = bool(self.entries or self._held or self.screens)
            self.entries, self._held, self.screens = [], {}, []
            self._sight = self._seq = 0
            self.paused.discard("stop")
            self.paused.discard("release")
            self.fatal = None
            self.book = ""
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

    def close(self) -> None:
        """(the window closes) Dropped, and its thread let go."""
        self.drop("close")
        self._packer.shutdown(wait=False)

    # ------------------------------------------------------------------ the work
    def _next(self) -> tuple[str, Entry] | None:
        """The next step: the first read in the order of first sight, else the first translation in story order."""
        with self._lock:
            reads = [e for e in self.entries if e.frame is not None or e.raw is not None]
            if reads:
                return "read", min(reads, key=lambda e: e.screen.sight)
            made = [e for e in self.entries if e.regions is not None]
            if made:
                return "make", min(made, key=lambda e: e.screen.sight)
            asks = [e for e in self.entries if e.units is not None]
            if asks:
                return "translate", min(asks, key=lambda e: e.screen.sight)
        return None

    def has_work(self) -> bool:
        with self._lock:
            return bool(self.entries)

    def settle_pending(self) -> None:
        """The pages turned past whose confirmation was kept for now (`Pipeline.decide_kept`, before the worker's next
        job): caught once their gate is sealed; dropped, without a word, when it was taken back (a sharper picture of
        the page came: its own job is the page's)."""
        with self._lock:
            pending, self.pending = self.pending, []
        left: list[tuple[Tracking, Any]] = []
        for tracking, work in pending:
            gate = tracking.gate
            if gate is not None and _sealed(gate):
                tracking.catch(work)
            elif gate is not None and gate.state == "confirmed":
                left.append((tracking, work))
            elif tracking.screen is not None:
                self.release(tracking.screen, done=False)
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
        elif not on and "auto" not in self.paused:
            self.pause("auto")
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
                or not window._jobs.empty() or not pipeline.behind_allowed()):
            return
        if getattr(pipeline, "translator", None) is None:
            return
        nxt = self._next()
        if nxt is None:
            return
        now = time.monotonic()
        if nxt[0] == "translate" and (now - self.finished_at < HOLD_S or now < self.hold_until):
            return
        self.step_queued = True
        window._jobs.put(lambda: self._run(window))

    def _run(self, window: Any) -> None:
        """(the worker) One step, then the window's idle look queues the next."""
        try:
            self.step(window.pipeline, lambda: not window._jobs.empty(), getattr(window, "settings", None))
        finally:
            self.step_queued = False

    def step(self, pipeline: Any, waiting: Callable[[], bool] | None = None, settings: Any = None) -> str:
        """(the worker) One step of the backlog's work, stopped by a page or any job (`Preempt`); what it did: "read",
        "translate", "made", "stopped", "failed" or "" (nothing to do, or not now)."""
        if not pipeline.behind_allowed() or self.paused:
            return ""
        nxt = self._next()
        if nxt is None:
            return ""
        what, entry = nxt
        stop = Preempt(waiting)
        pipeline.behind_stop = stop
        last_seq = getattr(pipeline, "last_seq", None)
        try:
            if what == "read":
                return self._read(pipeline, entry, stop)
            if what == "make":
                return self._make(pipeline, entry)
            return self._translate(pipeline, entry, stop, settings)
        except Cancelled:  # (a page, a job, Stop: the step ends, what it answered stored; it comes again)
            if stop.set_at is not None:
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
            pipeline.behind_stop = None
            if last_seq is not None:
                pipeline.last_seq = last_seq  # (where the book was read last is the reader's, not the backlog's)
            self.totals()

    def _read(self, pipeline: Any, entry: Entry, stop: Preempt) -> str:
        """The frame of *entry* read (`Pipeline.scan`, the cache's entries held to it), the units with something to
        translate kept, the frame dropped."""
        with self._lock:
            raw, packed = entry.raw, entry.frame
        image = raw if raw is not None else unpack(packed) if packed is not None else None
        if image is None:
            return ""
        self.tell(entry.screen, "read", "working")
        try:
            scan = pipeline.scan(image, skip_cached=True, cancel=stop, behind=True)
        except Cancelled:
            raise
        except Exception:  # noqa: BLE001 - the page is read when shown again
            LOG.exception("backlog: a page could not be read")
            self._finish(entry, "read", "failed")
            return "failed"
        del image
        with self._lock:
            entry.raw = entry.frame = None
            entry.held_bytes = 0
            entry.units = [u for u in scan.units if u.japanese()]
        self.tell(entry.screen, "read", "done")
        if not entry.units:
            self._finish(entry, "translate", "done" if scan.units else "skipped")
        else:
            self.tell(entry.screen, "translate", "waiting")
        return "read"

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
        what was answered by then stored. Its requests get the pairs of the pages before it in the story
        (`StoryContext.place`, ``HISTORY`` "story"); one whose pairs part from the last request's waits until the
        reader has stayed SWITCH_HOLD_S on a page done (`hold_until`: the warming of the reader's next page comes
        meanwhile), and gets at most SWITCH_PAIRS of what parts (`StoryContext.switch_to`)."""
        from .translate.base import GrowingContext, context_fits, grows_context

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
        story = getattr(pipeline, "_grown", None)
        storied = HISTORY == "story" and hasattr(story, "place")
        grown = on and grows_context(translator) and isinstance(story, GrowingContext)
        before = getattr(story, "at", None)
        if storied:
            story.place(entry.screen.sight)
        try:
            if storied and grown and story.switches(context_fits(translator, notes)):
                wait = self.finished_at + SWITCH_HOLD_S - time.monotonic()
                if wait > 0:
                    self.hold_until = time.monotonic() + wait
                    return "held"
            self.tell(entry.screen, "translate", "working")
            host = _Host(pipeline, stop, threading.Lock())
            if grown:
                recent: Any = story
            else:
                recent = _Recording(pipeline.context_pairs() if on else (),
                                    maxlen=max(0, int(getattr(s, "context_pairs", 40))))
            if storied and grown:
                story.switch_to = SWITCH_PAIRS
            host._translate_units(todo, recent, notes, [], language)
            if isinstance(recent, _Recording) and on and context is not None and recent.added:
                context.append(list(recent.added))  # (the pages' pairs of a translator that does not grow them)
        finally:
            if storied:
                story.switch_to = None
                story.place(before)  # (the reader's page again)
        if host._fatal is not None:
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
            entry.raw = entry.frame = None
            entry.held_bytes = 0
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
        self._lock = backlog._lock
        backlog.resume("stop")  # (the reader reads on: Stop and a release paused the backlog until now)
        backlog.resume("release")
        with backlog._lock:
            backlog.fatal = None

    def _within(self) -> int:
        return int(getattr(self.pipeline.settings, "fingerprint_max_distance", 36) or 36)

    def attach(self, work: Any) -> None:
        """*work* (`PageWork`) tells this as the job goes. A job without one (no gate: a page taken as settled, one
        from the cache) has its screen found here, before it is read (the history placed at it)."""
        if work is not None:
            work.on_units = self.on_units
            work.on_read = self.on_read
            return
        place = getattr(getattr(self.pipeline, "_grown", None), "place", None)
        if place is None or HISTORY != "story" or self.image is None:
            return
        try:
            import numpy as np

            units = self.pipeline.units_of(np.asarray(self.image.convert("RGB")))
        except Exception:  # noqa: BLE001 - placed at the end
            return
        if units:
            self.screen = self.backlog.screen_for(units, self._within())
            place(self.screen.sight)

    def on_units(self, work: Any) -> None:
        """(the worker, in `process`) The capture's page units are known: its screen found (the history placed at it),
        its entry held while it is on show; told to the window once the gate is confirmed (at once when it is)."""
        units = list(work.units or [])
        if not units:
            self.backlog.show(None)
            return
        screen = self.backlog.screen_for(units, self._within())
        self.screen = screen
        place = getattr(getattr(self.pipeline, "_grown", None), "place", None)
        if place is not None:
            place(screen.sight if HISTORY == "story" else None)
        self.backlog.hold(screen)
        on_kept = getattr(self.gate, "on_kept", None)
        if self.gate is None:
            self._report()
        elif on_kept is not None:
            on_kept(self._report)

    def on_read(self, work: Any) -> None:
        """(the worker) Every unit the job reads is read."""
        with self._lock:  # (the backlog's: told in order with the confirmation's, `_report`)
            self.read_done = True
            if self.reported and self.screen is not None:
                self.backlog.tell(self.screen, "read", "done", self.image)
                self.backlog.tell(self.screen, "translate", "working", self.image)

    def _report(self) -> None:
        """(the frame confirmed) The screen on show, and how far its job is."""
        screen = self.screen
        if screen is None:
            return
        b = self.backlog
        with self._lock:
            self.reported = True
            screen.missed = False  # (a page told as gone by is on show now)
            b.tell(screen, "read", "done" if self.read_done else "working", self.image)
            if self.read_done:
                b.tell(screen, "translate", "working", self.image)
            merge_missed(b, screen, self._within())
            b.show(screen)
        b.totals()

    def finished(self, result: Any) -> None:
        """(the worker) The job is done, the page shown: its stages ended as they came out."""
        b = self.backlog
        b.finished_at = time.monotonic()
        screen = self.screen
        if screen is None:
            units = list(getattr(result, "units", None) or [])
            if not units:
                b.show(None)
                return
            screen = self.screen = b.screen_for(units, self._within())
        if self.gate is not None and not self.gate.confirmed:
            b.release(screen, done=False)
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
        b.show(screen)
        b.totals()

    def cancelled(self, turned: bool, work: Any) -> None:
        """(the worker, the job raised `Cancelled`) *turned*: the reader turned away from the page (`turn_away`); a
        page whose gate was sealed is caught (when the caps allow), one whose frame went by is told as such."""
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
        if not (gate is not None and gate.confirmed):
            b.release(screen, done=False)
            return
        if not turned:  # (Stop, the close: the page stays as it is)
            for stage in ("read", "translate"):
                if screen.stages.get(stage) not in ("done", "failed", "skipped"):
                    b.tell(screen, stage, "skipped")
            b.release(screen, done=False)
            b.totals()
            return
        if not _sealed(gate) and not _soft(gate) and _settled(gate):  # (kept for now: caught once sealed,
            # `Backlog.settle_pending`)
            with b._lock:
                b.pending.append((self, work))
            b.tell(screen, "translate", "waiting", self.image)
            return
        self.catch(work)

    def catch(self, work: Any) -> None:
        """(the page turned past, its gate sealed or soft) Caught when it may be (see the module's docstring), else
        told as not caught."""
        b = self.backlog
        gate = self.gate
        screen = self.screen
        if screen is None or gate is None:
            return
        caught = _sealed(gate) and not _soft(gate) and _settled(gate) and \
            b.catch(screen, self.image, work, self.pipeline, self.hwnd)
        if caught:
            b.tell(screen, "read", "done" if work is not None and work.read_all and work.read else "waiting",
                   self.image)
            b.tell(screen, "translate", "waiting", self.image)
        else:
            b.not_caught += 1
            b.release(screen, done=False)
            for stage in ("read", "translate"):
                if screen.stages.get(stage) not in ("done", "failed", "skipped"):
                    b.tell(screen, stage, "missed", self.image)
            screen.missed = screen.stages.get("translate") == "missed"
        b.totals()

    def over(self) -> None:
        """(the worker, the job's end, however it ended) What the backlog held for the page while it was on show
        (`Backlog.hold`) and was not let go of goes back to it."""
        screen = self.screen
        if screen is not None and self.backlog.held_entry(screen) is not None:
            self.backlog.release(screen, done=False)

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
    return (backlog is not None and backlog.has_work() and not backlog.paused and backlog.fatal is None
            and time.monotonic() >= backlog.hold_until)
