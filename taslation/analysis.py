"""The session's analysis log: what each page cost and what each helper changed, NUMBERS ONLY.

One JSON line per page read or shown from the cache (`begin` / `end` round `Pipeline.process`), appended to
``<state dir>/analysis.jsonl`` (`FILE_NAME`; at `MAX_BYTES` the file starts again, the one before kept as
``analysis.1.jsonl``), and lines of what the person saw (``"type": "ui"``, written by the window as the next page comes:
`ui.measure`) and of each change they made (``"type": "edit"``). A page's line holds:

* ``n`` (the page's number in the session), ``t`` / ``end`` (wall-clock ms at its start and end), ``ms`` (its wall
  time), ``outcome`` ("done", or the exception's class that stopped it), ``ahead`` (a page lettered ahead of its next
  showing, `Pipeline.keep_shown`), the frame's ``size``, its ``units`` (1 or 2), ``hits`` / ``misses`` of the cache and
  ``cached`` (the page drawn from the cache or from this session's lettered pages, nothing read), the capture area's
  ``margins``;
* ``facts``: the page's coarse look on a 64 x 64 grid of the capture area's pixels (`THUMB`): the share of colour
  (``colour``: a channel `COLOUR_SPREAD` from the others), of ink (``ink``: grey under `INK_LEVEL`), of dark ground
  (``dark``: under `DARK_LEVEL`) and of what is drawn (``drawn``: anything but paper, under `PAPER_LEVEL`);
* ``stages``: the ms of the pipeline's stages (fingerprint, detect, ocr, translate, render, ...);
* ``helpers``: {name: [ms, calls]} of each helper worth naming (`timed`, `timing`), and ``counts``: what they counted
  (LaMa's windows, its hole and window px and those on the GPU, the fit's probes, glyph px added, line px kept ...);
* ``effect``: per helper, how many regions it CHANGED the outcome for on this page (`acted`; ``.boxes`` names count
  the distinct lettering boxes, where a helper sees a box and no region: `acted_box`) - not how often it ran;
* ``regions``: how many, by status, kind, tier, fit taken (``fitted``, ``won``), sound word, review flag and lettering
  flag, those found by the layout model, those read with low confidence and left as drawn (``low_as_drawn``);
* ``first_letter_ms`` (ms from the start to its first lettering told to the window), ``gpu_free_mb`` (before, after:
  only where torch has CUDA up already, never started for it) and ``self_ms``, what the log itself cost;
* ``cases``: each defect of level S1 or S2 found on the page itself (`page_defects`), one by one with its numbers - the
  region's index, box, kind, tier, confidence, the helpers that acted on it -, and ``minor``: the S3 and S4 ones
  counted by code.

Every defect the log counts carries its level (`LEVELS`, the owner's scale: how bad it is for the reader; how often it
happens is what the log measures): S1 reading fails (a bubble's lettering not translated, its original shown where a
translation exists, a translation on the wrong page, the keys or the panes keeping the person from reading, a page too
slow to use: over `PAGE_BUDGET_S` with a GPU, `PAGE_BUDGET_CPU_S` without), S2 content lost or damaged (a translation
cut, covered or out of sight, the drawing destroyed by an erase, a false region lettered over the art), S3 readable
but hard (under the readable size, hyphenated, specks or ghosts left, an outline or a line cut, lettering over an
outline), S4 cosmetic (a slant, a size a little off, a pane a little far). What the page cannot tell by itself comes
from the window (``ui`` lines: a patch not shown for no meant reason, a press that could not give the viewer the keys)
and from the person's own changes (``edit`` lines: a region added by hand is something missed, S1; one retyped or asked
again S2 - S1 where it had no translation -; one deleted S2 where it had been lettered over the art, else S3; moved or
resized S3). The summary's first table is by level (`summary_lines`).

Nothing else is written: no page text, no reading, no translation, no title, no file or window name, no pixel (the rule
of "Copy a report"). Every key and every string value written is one of the program's own names - lowercase ASCII,
short (`NAME`) -, anything else becomes "other" (`clean`); the helpers hand over numbers and their own enums, never a
region's text. With developer measuring on (`taslation.devmeasure`, a source checkout only) the same lines also go to
the session's folder, and the region's readings and the model's requests are kept there beside them - never here.

On by default when running from a source checkout (a ``.git`` beside the package: `source_checkout`), off in an
installed copy; the settings file's ``analysis_log`` ("auto", "on", "off"; in no dialog) forces either (`wanted`).
The timing is perf_counter pairs round calls that run anyway (`timed`: about a microsecond a call while a page is
timed, a thread-local look while none is), a 64 x 64 grid of the frame's pixels a page (no copy of the frame), and the
line written on the worker once the page is done. What the log costs is measured and written with each page
(``self_ms``: its own work, plus each timed call at the cost `_call_cost` measured at the start, and the writing
of the line before)."""

from __future__ import annotations

import functools
import json
import os
import re
import sys
import threading
import time
from collections import Counter, deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

FILE_NAME = "analysis.jsonl"
OLD_NAME = "analysis.1.jsonl"
SETTING = "analysis_log"
CHOICES = ("auto", "on", "off")
VERSION = 1  # of a line's fields
MAX_BYTES = 4 * 2 ** 20  # the file this large starts again (the one before kept, one)
KEPT = 600  # lines kept in memory for the report's [analysis] section (`records`)
NAME = re.compile(r"[a-z][a-z0-9_.:+-]{0,47}")  # a key or a string value written: the program's own names and enums
OTHER = "other"
THUMB = 64  # the side of the grid of pixels the page's facts are judged on
COLOUR_SPREAD = 24  # a pixel whose channels are so far apart, or more, is colour
INK_LEVEL = 80  # grey under it: ink
DARK_LEVEL = 32  # grey under it: dark ground
PAPER_LEVEL = 230  # grey under it: drawn (not paper)

PAGE_BUDGET_S = 15.0  # s: a page slower than this where torch has CUDA up is too slow to use (S1) ...
PAGE_BUDGET_CPU_S = 45.0  # ... and without a GPU
S1, S2, S3, S4 = "s1", "s2", "s3", "s4"
LEVEL_WORDS = {S1: "S1 reading fails", S2: "S2 content lost or damaged", S3: "S3 readable but hard",
               S4: "S4 cosmetic"}
# every defect the log counts and its level (see the module's notes)
LEVELS = {
    # S1: reading fails
    "not_translated": S1,  # read as Japanese to translate, and no translation came
    "bubble_left_as_drawn": S1,  # in a bubble or a box, read as Japanese with confidence, left as drawn
    "patch_not_shown": S1,  # (window) a lettered region's patch not on show for no meant reason ("not drawn")
    "page_slow": S1,  # the page took longer than its budget
    "keys_not_back": S1,  # (window) a press on TASlation's lettering or panes did not give the viewer the keys
    "edit_add": S1,  # (person) a region added by hand: something missed
    "edit_retyped_untranslated": S1,  # (person) a region with no translation given one
    "edit_asked_untranslated": S1,  # (person) a bubble with no translation asked again (the right pane's Ask again)
    # S2: content lost or damaged
    "lettering_cut": S2,  # the text did not fit at its size: cut at its room's edge (``no-fit``)
    "unsure_lettered_on_art": S2,  # read with low confidence, lettered, erased on the drawing: a false region?
    "edit_retyped": S2,  # (person) a translation retyped
    "edit_asked": S2,  # (person) a bubble's translation asked again (the right pane's Ask again)
    "edit_again": S2,  # (person) the page translated again
    "edit_drop_on_art": S2,  # (person) a region deleted that had been lettered over the art
    # S3: readable but hard
    "small": S3,  # set under the readable size (review flag)
    "hyphenated": S3,  # a word hyphenated to fit
    "overrun": S3,  # lettering run over the bubble's outline
    "unsure_left_as_drawn": S3,  # read with low confidence, left as drawn (in a bubble: S1 only with confidence)
    "review_ocr": S3, "review_long": S3, "review_short": S3, "review_rendering": S3,
    "edit_move": S3, "edit_resize": S3, "edit_drop": S3, "edit_order": S3, "edit_size": S3,
    # S4: cosmetic
    "turned": S4,  # the line turned a quarter to fit a tall bubble
    "letter_check": S4,  # what the automatic lettering's checks found (tight, off centre, a lone word...)
    "review_spelling": S4,
    "edit_kind": S4, "edit_rotate": S4, "edit_direction": S4, "edit_paste": S4, "edit_skip": S4,
}
BUBBLE_KINDS = frozenset({"bubble", "dark-bubble", "text-on-page", "text-on-dark", "manual", "manual-dark"})
ART_HELPERS = frozenset({"lama", "tone_fill", "ground_fill", "see_through"})  # an erase on the drawing
LEFT_AS_DRAWN = frozenset({"ocr-noise", "not-japanese", "detected"})  # read, and left as it is drawn
MEANT_UNSHOWN = frozenset({"covered", "bars", "hover", "original", "left_out", "no_match", "no_patch"})

_TL = threading.local()  # .page: the page timed on this thread (`begin`, `adopt`)
_LOCK = threading.Lock()


def source_checkout(root: Path | str | None = None) -> bool:
    """Whether the program runs from a source checkout: a ``.git`` (folder, or a worktree's file) beside the package
    (the release's ZIP has none)."""
    if root is None:
        from .config import REPO_DIR

        root = REPO_DIR
    return (Path(root) / ".git").exists()


def wanted(setting: Any, root: Path | str | None = None) -> bool:
    """Whether the log is written with ``analysis_log`` *setting*: "on" always, "off" never, "auto" (or anything
    else) in a source checkout only."""
    value = str(setting or "auto").strip().lower()
    if value == "on":
        return True
    if value == "off":
        return False
    return source_checkout(root)


# ------------------------------------------------------------------ cleaning: numbers and the program's own names
def _name(value: Any) -> str:
    text = str(value)
    return text if NAME.fullmatch(text) else OTHER


def clean(value: Any, depth: int = 0) -> Any:
    """*value* as it may be written: numbers, booleans and None as they are (floats rounded to 3 places), every
    string and every key one of the program's own names (`NAME`) or "other", lists and dicts likewise (6 deep at the
    most); anything else (a picture, an object) None."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return round(value, 3) if value == value and abs(value) != float("inf") else None
    if isinstance(value, str):
        return _name(value)
    if depth >= 6:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = _name(k)
            out[key] = _merge(out[key], clean(v, depth + 1)) if key in out else clean(v, depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=repr) if isinstance(value, (set, frozenset)) else value
        return [clean(v, depth + 1) for v in items]
    try:  # (numpy numbers)
        import numpy as np

        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return clean(float(value))
        if isinstance(value, np.bool_):
            return bool(value)
    except Exception:  # noqa: BLE001 - not numpy's
        pass
    return None


def _merge(a: Any, b: Any) -> Any:
    """Two values whose keys became the same name ("other"): numbers added, else the first."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return a + b
    return a


# ------------------------------------------------------------------ the log
class Log:
    """The session's log: the file (None: the lines kept in memory and given to the sinks alone), the sinks (more
    files the lines go to as well: a developer measuring session's), the lines kept for the report, the page count."""

    def __init__(self, path: Path | None):
        self.path = path
        self.sinks: list[Path] = []
        self.listeners: list[Callable[["Page", Any], None]] = []  # (developer measuring: `Page`, the page's result)
        self.records: deque[dict[str, Any]] = deque(maxlen=KEPT)
        self.lock = threading.Lock()
        self.pages = 0
        self.t0 = time.time()
        self.call_cost = _call_cost()
        self.loose: dict[str, list[float]] = {}  # times taken on no page (the window's own: a page's sign, ...)
        self.loose_counts: Counter[str] = Counter()
        self.failed = False
        self.wrote = 0.0  # s the last line's writing took (counted in the next page's ``self_ms``)

    def next_page(self) -> int:
        with self.lock:
            self.pages += 1
            return self.pages

    def write(self, line: dict[str, Any]) -> dict[str, Any]:
        """*line* cleaned (`clean`), kept and appended to the file and the sinks; what was written. A file that cannot
        be written is said once in the log and left."""
        t = time.perf_counter()
        line = clean(line)
        text = json.dumps(line, separators=(",", ":"), sort_keys=True) + "\n"
        with self.lock:
            self.records.append(line)
            for path in ([self.path] if self.path is not None else []) + list(self.sinks):
                try:
                    if path == self.path and path.exists() and path.stat().st_size > MAX_BYTES:
                        os.replace(path, path.with_name(OLD_NAME))
                    with open(path, "a", encoding="utf-8", newline="\n") as f:
                        f.write(text)
                except OSError as e:
                    if not self.failed:
                        self.failed = True
                        import logging

                        logging.getLogger(__name__).info("the analysis log could not be written (%s)",
                                                         type(e).__name__)
            self.wrote = time.perf_counter() - t
        return line

    def take_loose(self) -> tuple[dict[str, list[float]], dict[str, int]]:
        with self.lock:
            times, counts = self.loose, dict(self.loose_counts)
            self.loose, self.loose_counts = {}, Counter()
        return times, counts


_LOG: Log | None = None


def start(state_dir: Path | str | None, setting: Any = "auto", root: Path | str | None = None) -> Log | None:
    """The session's log started (`wanted` with ``analysis_log`` *setting*), written into *state_dir* (None: kept in
    memory alone); None when it is off. Started once: a second start keeps the first."""
    global _LOG
    if not wanted(setting, root):
        return _LOG
    with _LOCK:
        if _LOG is None:
            path = Path(state_dir) / FILE_NAME if state_dir is not None else None
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
            _LOG = Log(path)
        return _LOG


def ensure(state_dir: Path | str | None = None) -> Log:
    """The log, started now whatever the setting (developer measuring: its lines go to the session's folder; with no
    log on, none to the state folder's file)."""
    global _LOG
    with _LOCK:
        if _LOG is None:
            _LOG = Log(None)
        return _LOG


def stop() -> None:
    """The log ended (the tests; a window that closes keeps it to the end)."""
    global _LOG
    with _LOCK:
        _LOG = None


def log() -> Log | None:
    return _LOG


def on() -> bool:
    return _LOG is not None


def records() -> list[dict[str, Any]]:
    """The lines kept in memory (the newest `KEPT`), oldest first."""
    current = _LOG
    if current is None:
        return []
    with current.lock:
        return list(current.records)


def write(line: dict[str, Any]) -> dict[str, Any] | None:
    """A line of the window's (``"type": "ui"``, ``"edit"``) written, with the time; None while the log is off."""
    current = _LOG
    if current is None:
        return None
    return current.write({"v": VERSION, "t": int(time.time() * 1000), **line})


# ------------------------------------------------------------------ a page
class Page:
    """What one page cost and what changed it, filled in by the threads that work on it (`adopt`)."""

    def __init__(self, n: int, cost: float):
        self.n = n
        self.t0 = time.perf_counter()
        self.wall = time.time()
        self.cost = cost
        self.calls = 0
        self.own = 0.0  # s the log itself took (`begin`, `end`)
        self.times: dict[str, list[float]] = {}  # name -> [s, calls]
        self.counts: Counter[str] = Counter()
        self.boxes: dict[str, set[tuple[int, ...]]] = {}
        self.first_letter: float | None = None
        self.lock = threading.Lock()
        # developer measuring: what it keeps of the page (`taslation.devmeasure`)
        self.keep: dict[str, Any] | None = None
        self.facts: dict[str, Any] = {}
        self.line: dict[str, Any] | None = None
        self.previous: Page | None = None  # the page timed on its thread before it (put back at its end)

    def add(self, name: str, seconds: float, calls: int = 1) -> None:
        with self.lock:
            got = self.times.get(name)
            if got is None:
                self.times[name] = [seconds, calls]
            else:
                got[0] += seconds
                got[1] += calls
            self.calls += calls

    def count(self, name: str, n: float = 1) -> None:
        with self.lock:
            self.counts[name] += n


def current() -> Page | None:
    """The page timed on this thread, if any."""
    return getattr(_TL, "page", None)


@contextmanager
def adopt(page: Page | None) -> Iterator[None]:
    """On this thread, *page* is the one timed while the block runs (a thread that works on a page for its own:
    the spread's next unit read beside, a draft lettered on the drafts' thread)."""
    before = getattr(_TL, "page", None)
    _TL.page = page
    try:
        yield
    finally:
        _TL.page = before


def timed(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """A decorator: each call of the function timed as *name* on the page timed on its thread (`Page.add`), or as
    the session's own while none is (``loose``, written with the next ``ui`` line); nothing while the log is off."""
    def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def run(*args: Any, **kwargs: Any) -> Any:
            page = getattr(_TL, "page", None)
            if page is None and _LOG is None:
                return fn(*args, **kwargs)
            t = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                _took(page, name, time.perf_counter() - t)
        return run
    return wrap


@contextmanager
def timing(name: str) -> Iterator[None]:
    """The block timed as *name*, as `timed` times a call."""
    page = getattr(_TL, "page", None)
    if page is None and _LOG is None:
        yield
        return
    t = time.perf_counter()
    try:
        yield
    finally:
        _took(page, name, time.perf_counter() - t)


def _took(page: Page | None, name: str, seconds: float) -> None:
    if page is not None:
        page.add(name, seconds)
        return
    current_log = _LOG
    if current_log is not None:
        with current_log.lock:
            got = current_log.loose.setdefault(name, [0.0, 0])
            got[0] += seconds
            got[1] += 1


def count(name: str, n: float = 1) -> None:
    """*n* added to the count *name* of the page timed on this thread (or the session's own while none is)."""
    page = getattr(_TL, "page", None)
    if page is not None:
        page.count(name, n)
        return
    current_log = _LOG
    if current_log is not None:
        with current_log.lock:
            current_log.loose_counts[name] += n


def traced(regions: Iterable[Any]) -> None:
    """Each of *regions* given its trace (`TextRegion.trace`) while a page is timed, so that the copies made of it
    from now on share it (`acted` on a copy counts for the region)."""
    if getattr(_TL, "page", None) is None:
        return
    for r in regions:
        if getattr(r, "trace", None) is None:
            try:
                r.trace = {}
            except AttributeError:
                pass


def acted(region: Any, name: str, n: float = 1) -> None:
    """The helper *name* changed what came of *region* (it took the region, or gave it something): kept on its trace
    (``acted``, a set: a region counts once a helper) and counted (``effect.`` *name*, every time)."""
    page = getattr(_TL, "page", None)
    if page is None:
        return
    trace = getattr(region, "trace", None)
    if trace is None:
        try:
            trace = region.trace = {}
        except AttributeError:
            trace = None
    if trace is not None:
        trace.setdefault("acted", set()).add(name)
    page.count("effect." + name, n)


def acted_box(name: str, box: Sequence[int]) -> None:
    """The helper *name* changed the outcome for the lettering box *box* (a helper that sees no region): the page's
    distinct boxes counted (``effect`` *name* ``.boxes``)."""
    page = getattr(_TL, "page", None)
    if page is None:
        return
    with page.lock:
        page.boxes.setdefault(name, set()).add(tuple(int(v) for v in box))


def note(region: Any, key: str, value: Any) -> None:
    """*value* kept on *region*'s trace under *key* for developer measuring alone (`taslation.devmeasure`: the
    readers' readings); nothing while no measuring session keeps the page. Never written to the analysis log."""
    page = getattr(_TL, "page", None)
    if page is None or page.keep is None:
        return
    trace = getattr(region, "trace", None)
    if trace is None:
        try:
            trace = region.trace = {}
        except AttributeError:
            return
    trace[key] = value


def wants_pictures() -> bool:
    """Whether the page timed on this thread keeps its pictures (developer measuring)."""
    page = getattr(_TL, "page", None)
    return page is not None and page.keep is not None


def erased(out: Any) -> None:
    """The page erased and not lettered yet (`Pipeline._render`), kept where developer measuring keeps the page."""
    page = getattr(_TL, "page", None)
    if page is not None and page.keep is not None:
        page.keep["erased"] = out.copy()


def lettered(page: Page | None) -> None:
    """*page*'s first lettering was told to the window (`PageFill`): when, from its start."""
    if page is not None and page.first_letter is None:
        page.first_letter = time.perf_counter() - page.t0


def measuring() -> bool:
    """Whether a developer measuring session keeps what the translator is asked (`request`)."""
    current_log = _LOG
    return current_log is not None and any(getattr(x, "request", None) is not None for x in current_log.listeners)


def request(data: Callable[[], dict[str, Any]]) -> None:
    """A request the translator made and its raw answer (*data*() gives them: the prompt's parts, the prompt, the
    answer, the server's statistics), handed to developer measuring alone - never written to the analysis log, and
    *data* not even called while no measuring session listens."""
    current_log = _LOG
    if current_log is None:
        return
    takers = [getattr(x, "request") for x in current_log.listeners if getattr(x, "request", None) is not None]
    if not takers:
        return
    try:
        given = data()
    except Exception:  # noqa: BLE001 - measuring never stops a request
        return
    for take in takers:
        try:
            take(getattr(_TL, "page", None), given)
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ begin / end round a page
def begin(rgb: Any = None, margins: Sequence[int] | None = None, ahead: bool = False) -> Page | None:
    """A page's record begun on this thread (None while the log is off); *rgb* the frame (its facts judged now: else
    by `frame`, once the page has it as an array)."""
    current_log = _LOG
    if current_log is None:
        return None
    t = time.perf_counter()
    page = Page(current_log.next_page(), current_log.call_cost)
    facts: dict[str, Any] = {"ahead": bool(ahead)}
    if rgb is not None:
        try:
            facts["size"] = [int(rgb.shape[1]), int(rgb.shape[0])]
            facts["facts"] = page_facts(rgb, margins)
        except Exception:  # noqa: BLE001 - the facts left out
            pass
    if margins is not None:
        facts["margins"] = [int(v) for v in margins]
    facts["gpu_free_mb"] = [_gpu_free_mb()]
    page.facts = facts
    for listener in list(current_log.listeners):
        try:
            hold = getattr(listener, "begin", None)
            if hold is not None:
                hold(page)
        except Exception:  # noqa: BLE001 - measuring never stops a page
            pass
    page.previous = getattr(_TL, "page", None)
    _TL.page = page
    page.own += time.perf_counter() - t
    return page


def frame(rgb: Any, margins: Sequence[int] | None = None) -> None:
    """The page timed on this thread is the frame *rgb* (an array the page made anyway): its facts judged now."""
    page = getattr(_TL, "page", None)
    if page is None or "facts" in page.facts:
        return
    t = time.perf_counter()
    try:
        page.facts["size"] = [int(rgb.shape[1]), int(rgb.shape[0])]
        page.facts["facts"] = page_facts(rgb, margins)
    except Exception:  # noqa: BLE001 - the facts left out
        pass
    page.own += time.perf_counter() - t


def end(page: Page | None, result: Any = None, outcome: str = "done", timings: dict[str, float] | None = None
        ) -> dict[str, Any] | None:
    """*page*'s line written (`page_line`) and its listeners told (developer measuring keeps the page); the thread's
    page ended. What was written (None for no page)."""
    if page is None:
        return None
    if getattr(_TL, "page", None) is page:
        _TL.page = page.previous
    current_log = _LOG
    t = time.perf_counter()
    line = page_line(page, result, outcome, timings)
    page.own += time.perf_counter() - t
    wrote = current_log.wrote if current_log is not None else 0.0  # (the line before's writing)
    line["self_ms"] = round(1000 * (page.own + page.calls * page.cost + wrote), 3)
    if current_log is None:
        return line
    page.line = written = current_log.write(line)
    for listener in list(current_log.listeners):
        try:
            listener(page, result)
        except Exception:  # noqa: BLE001 - measuring never stops a page
            import logging

            logging.getLogger(__name__).debug("a listener of the analysis log failed", exc_info=True)
    return written


def page_line(page: Page, result: Any, outcome: str, timings: dict[str, float] | None) -> dict[str, Any]:
    """The line of *page* (see the module's notes), from what it gathered and its *result* (`PageResult`)."""
    now = time.perf_counter()
    line: dict[str, Any] = {"type": "page", "v": VERSION, "n": page.n, "t": int(page.wall * 1000),
                            "end": int(time.time() * 1000), "ms": round(1000 * (now - page.t0), 1),
                            "outcome": outcome, **page.facts}
    line["gpu_free_mb"] = list(page.facts.get("gpu_free_mb") or []) + [_gpu_free_mb()]
    stages = timings if timings is not None else (getattr(result, "timings", None) or {})
    line["stages"] = {k.replace(" ", "_"): round(1000 * float(v), 1) for k, v in dict(stages).items()}
    with page.lock:
        line["helpers"] = {k: [round(1000 * v[0], 2), int(v[1])] for k, v in sorted(page.times.items())}
        line["counts"] = {k: (int(v) if float(v).is_integer() else round(float(v), 3))
                          for k, v in sorted(page.counts.items())}
        boxes = {k + ".boxes": len(v) for k, v in page.boxes.items()}
    if page.first_letter is not None:
        line["first_letter_ms"] = round(1000 * page.first_letter, 1)
    if result is not None:
        units = list(getattr(result, "units", None) or [])
        line["units"] = len(units)
        hits, misses = int(getattr(result, "cache_hits", 0) or 0), int(getattr(result, "cache_misses", 0) or 0)
        line["hits"], line["misses"] = hits, misses
        line["cached"] = bool(units) and misses == 0
        line["error"] = bool(getattr(result, "error", None))
        regions = list(getattr(result, "regions", None) or [])
        line["regions"] = region_facts(regions)
        cases, minor = page_defects(regions)
        if outcome == "done" and not page.facts.get("ahead"):
            budget = PAGE_BUDGET_S if (page.facts.get("gpu_free_mb") or [None])[0] is not None else PAGE_BUDGET_CPU_S
            if line["ms"] > 1000 * budget:
                stage = max(line["stages"].items(), key=lambda kv: kv[1])[0] if line["stages"] else "none"
                helper = max(line["helpers"].items(), key=lambda kv: kv[1][0])[0] if line["helpers"] else "none"
                cases.append({"code": "page_slow", "level": S1, "ms": line["ms"], "budget_s": budget,
                              "stage": stage, "helper": helper})
        line["cases"], line["minor"] = cases, minor
        effect: Counter[str] = Counter()
        for r in regions:
            trace = getattr(r, "trace", None)
            if isinstance(trace, dict):
                effect.update(trace.get("acted", ()))
        line["effect"] = {**dict(sorted(effect.items())), **boxes}
    else:
        line["effect"] = boxes
    return line


def region_facts(regions: Sequence[Any]) -> dict[str, Any]:
    """*regions* counted by status, kind, tier, fit taken, sound word and flags (numbers and enums only)."""
    from .review import OCR_UNSURE

    def tally(values: Iterable[Any]) -> dict[str, int]:
        return dict(sorted(Counter(_name(v) for v in values if v not in (None, "")).items()))

    drawn = ("translated", "erase")
    low = sum(1 for r in regions if getattr(r, "status", "") not in drawn
              and float(getattr(r, "ocr_confidence", 1.0) or 0.0) < OCR_UNSURE and getattr(r, "source_text", ""))
    won = []
    for r in regions:
        fitted = getattr(r, "fitted", "") or ""
        won.append(fitted)
    return {"n": len(regions), "status": tally(getattr(r, "status", "") for r in regions),
            "kind": tally(getattr(r, "kind", "") for r in regions),
            "tier": tally(f"t{int(getattr(r, 'tier', 0) or 0)}" for r in regions if getattr(r, "from_model", False)),
            "model": sum(1 for r in regions if getattr(r, "from_model", False)),
            "from_cache": sum(1 for r in regions if getattr(r, "from_cache", False)),
            "fitted": tally(won),
            "sound": tally(getattr(r, "sound", "") for r in regions),
            "flags": tally(f for r in regions for f in (getattr(r, "flags", None) or ())),
            "letter_flags": tally(f for r in regions for f in (getattr(r, "letter_flags", None) or ())),
            "low_as_drawn": low}


def _case(code: str, index: int, r: Any) -> dict[str, Any]:
    trace = getattr(r, "trace", None)
    return {"code": code, "level": LEVELS[code], "i": index, "box": [int(v) for v in getattr(r, "bbox", (0, 0, 0, 0))],
            "kind": _name(getattr(r, "kind", "")), "tier": int(getattr(r, "tier", 0) or 0),
            "model": bool(getattr(r, "from_model", False)),
            "conf": round(float(getattr(r, "ocr_confidence", 1.0) or 0), 3),
            "status": _name(getattr(r, "status", "")),
            "acted": sorted(trace.get("acted", ())) if isinstance(trace, dict) else []}


def page_defects(regions: Sequence[Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The defects the page shows by itself (`LEVELS`): the S1 and S2 ones each as a case with its numbers
    (`_case`), the S3 and S4 ones counted by code."""
    from .review import OCR_UNSURE

    cases: list[dict[str, Any]] = []
    minor: Counter[str] = Counter()

    def found(code: str, i: int, r: Any) -> None:
        if LEVELS[code] in (S1, S2):
            cases.append(_case(code, i, r))
        else:
            minor[code] += 1

    for i, r in enumerate(regions):
        status, kind = getattr(r, "status", ""), getattr(r, "kind", "")
        sure = float(getattr(r, "ocr_confidence", 1.0) or 0.0) >= OCR_UNSURE
        read = bool(getattr(r, "source_text", ""))
        trace = getattr(r, "trace", None)
        acted_on = set(trace.get("acted", ())) if isinstance(trace, dict) else set()
        if status == "untranslated":
            found("not_translated", i, r)
        elif status in LEFT_AS_DRAWN and read:
            if sure and kind in BUBBLE_KINDS and status != "not-japanese":
                found("bubble_left_as_drawn", i, r)
            elif not sure:
                found("unsure_left_as_drawn", i, r)
        elif status == "translated" and not sure and acted_on & ART_HELPERS:
            found("unsure_lettered_on_art", i, r)
        letter_flags = tuple(getattr(r, "letter_flags", None) or ())
        if "no-fit" in letter_flags:
            found("lettering_cut", i, r)
        if any(f not in ("no-fit", "font-missing", "font-glyphs") for f in letter_flags):
            found("letter_check", i, r)
        for flag in getattr(r, "flags", None) or ():
            code = "small" if flag == "small" else f"review_{flag}"
            if code in LEVELS:
                found(code, i, r)
        if "fit_hyphenated" in acted_on:
            found("hyphenated", i, r)
        if "fit_overrun" in acted_on:
            found("overrun", i, r)
        if "fit_turned" in acted_on:
            found("turned", i, r)
    return cases, dict(sorted(minor.items()))


def edit_code(kind: str, before: Any) -> str:
    """The defect a change of the person's (`ui.history.Step`'s kind) tells of, for the region *before* it (a copy as
    it was): a region added is something missed; retyped, one that was wrong (or had no translation); deleted, a
    false region (lettered over the art: S2)."""
    if kind in ("edit", "ask"):
        code = "edit_retyped" if kind == "edit" else "edit_asked"
        return code if getattr(before, "status", "") == "translated" else code + "_untranslated"
    if kind in ("drop", "drops"):
        trace = getattr(before, "trace", None)
        acted_on = set(trace.get("acted", ())) if isinstance(trace, dict) else set()
        return "edit_drop_on_art" if acted_on & ART_HELPERS else "edit_drop"
    code = f"edit_{kind}"
    return code if code in LEVELS else "edit_other"


def edited(kind: str, result: Any, touched: Sequence[tuple[Any, Any]]) -> dict[str, Any] | None:
    """A change of the person's made on the page *result* (`ui.history.Step`, once done): its line (``"type":
    "edit"``: the kind, the page's number in the session, each region it touched - *touched*: (before, after) copies,
    either None - as `region_entry` keeps it, and the defect it tells of, `edit_code`); developer measuring keeps the
    page's new state. None while the log is off."""
    current = _LOG
    if current is None:
        return None
    n = int(getattr(result, "analysis_n", 0) or 0)
    entries: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    minor: Counter[str] = Counter()
    for before, after in touched:
        region = before if before is not None else after
        if region is None:
            continue
        code = "edit_add" if kind == "add" else edit_code(kind, region)
        entry = {**region_entry(region), "code": code}
        entries.append(entry)
        if LEVELS.get(code) in (S1, S2):
            cases.append({"code": code, "level": LEVELS[code], "kind": entry["kind"], "tier": entry["tier"],
                          "w": entry["w"], "h": entry["h"], "acted": entry["acted"],
                          "box": [int(v) for v in getattr(region, "bbox", (0, 0, 0, 0))]})
        elif code in LEVELS:
            minor[code] += 1
    if not entries and kind in ("again", "skip", "order"):
        code = f"edit_{kind}"
        if LEVELS.get(code) in (S1, S2):
            cases.append({"code": code, "level": LEVELS[code]})
        else:
            minor[code] += 1
    line = current.write({"type": "edit", "v": VERSION, "t": int(time.time() * 1000), "page": n, "kind": kind,
                          "regions": entries, "cases": cases, "minor": dict(minor)})
    for listener in list(current.listeners):
        hook = getattr(listener, "edited", None)
        if hook is not None:
            try:
                hook(kind, result)
            except Exception:  # noqa: BLE001 - measuring never stops a change
                pass
    return line


def region_entry(region: Any) -> dict[str, Any]:
    """An edited region as the log keeps it: its kind, tier, size, the helpers that had acted on it, its flags."""
    trace = getattr(region, "trace", None)
    acted_on = sorted(trace.get("acted", ())) if isinstance(trace, dict) else []
    return {"kind": _name(getattr(region, "kind", "")), "tier": int(getattr(region, "tier", 0) or 0),
            "model": bool(getattr(region, "from_model", False)),
            "w": int(getattr(region, "x1", 0) - getattr(region, "x0", 0)),
            "h": int(getattr(region, "y1", 0) - getattr(region, "y0", 0)),
            "acted": acted_on, "flags": [_name(f) for f in (getattr(region, "flags", None) or ())],
            "status": _name(getattr(region, "status", "")), "sound": _name(getattr(region, "sound", "") or "none")}


def page_facts(rgb: Any, margins: Sequence[int] | None = None) -> dict[str, float]:
    """The page's coarse look (see the module's notes), judged on a `THUMB` x `THUMB` grid of the pixels of the capture
    area (*margins*: left, top, right, bottom px left out)."""
    import numpy as np

    h, w = rgb.shape[:2]
    left, top, right, bottom = (list(margins) + [0, 0, 0, 0])[:4] if margins is not None else (0, 0, 0, 0)
    y0, y1 = max(0, min(h - 1, top)), max(1, h - max(0, bottom))
    x0, x1 = max(0, min(w - 1, left)), max(1, w - max(0, right))
    if y1 <= y0 or x1 <= x0:
        y0, y1, x0, x1 = 0, h, 0, w
    ys = np.linspace(y0, y1 - 1, THUMB).astype(np.intp)  # (a grid of pixels: no copy of the frame, no filtering)
    xs = np.linspace(x0, x1 - 1, THUMB).astype(np.intp)
    small = rgb[np.ix_(ys, xs)][..., :3].astype(np.int16)
    grey = small.mean(axis=2)
    spread = small.max(axis=2) - small.min(axis=2)
    n = float(THUMB * THUMB)
    return {"colour": round(float((spread >= COLOUR_SPREAD).sum()) / n, 3),
            "ink": round(float((grey < INK_LEVEL).sum()) / n, 3),
            "dark": round(float((grey < DARK_LEVEL).sum()) / n, 3),
            "drawn": round(float((grey < PAPER_LEVEL).sum()) / n, 3)}


def _gpu_free_mb() -> int | None:
    """The GPU's free memory in MB, where torch has CUDA up already (never started for it); None elsewhere."""
    torch = sys.modules.get("torch")
    try:
        if torch is None or not torch.cuda.is_initialized():
            return None
        return int(torch.cuda.mem_get_info()[0] // 2 ** 20)
    except Exception:  # noqa: BLE001 - none to say
        return None


def _call_cost() -> float:
    """The seconds a timed call costs beyond the call itself, measured once (`timed` round a function that does
    nothing, on a page)."""
    page = Page(0, 0.0)

    def nothing() -> None:
        return None

    wrapped = timed("cost")(nothing)
    rounds = 2000
    before = getattr(_TL, "page", None)
    _TL.page = page
    try:
        t = time.perf_counter()
        for _ in range(rounds):
            nothing()
        bare = time.perf_counter() - t
        t = time.perf_counter()
        for _ in range(rounds):
            wrapped()
        taken = time.perf_counter() - t
    finally:
        _TL.page = before
    return max(0.0, (taken - bare) / rounds)


# ------------------------------------------------------------------ the tables
def _median(values: Sequence[float]) -> float:
    s = sorted(values)
    if not s:
        return 0.0
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def _quantile(values: Sequence[float], q: float) -> float:
    s = sorted(values)
    if not s:
        return 0.0
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def level_lines(lines: Sequence[dict[str, Any]]) -> list[str]:
    """The first table: the defects by level (`LEVELS`), S1 and S2 case by case with the page's number in the
    session and their numbers, S3 and S4 counted with their rate (per page read, per 100 regions)."""
    pages = [ln for ln in lines if ln.get("type") == "page"]
    regions = sum(int((p.get("regions") or {}).get("n") or 0) for p in pages)
    cases: list[tuple[int, dict[str, Any]]] = []
    minor: Counter[str] = Counter()
    for ln in lines:
        for c in ln.get("cases") or []:
            if isinstance(c, dict):
                cases.append((int(ln.get("page", ln.get("n", 0)) or 0), c))
        minor.update({k: int(v) for k, v in (ln.get("minor") or {}).items() if isinstance(v, (int, float))})
    out = [f"defects by level ({len(pages)} pages, {regions} regions)"]
    for level in (S1, S2):
        mine = [(n, c) for n, c in cases if c.get("level") == level]
        out.append(f"{LEVEL_WORDS[level]}: {len(mine)}")
        for n, c in sorted(mine, key=lambda nc: (nc[0], str(nc[1].get("code")))):
            facts = ", ".join(f"{k} {_num(v) if not isinstance(v, list) else '/'.join(str(x) for x in v)}"
                              for k, v in c.items() if k not in ("code", "level"))
            out.append(f"  page {n}: {c.get('code')}" + (f" ({facts})" if facts else ""))
    for level in (S3, S4):
        mine = {k: v for k, v in minor.items() if LEVELS.get(k) == level}
        out.append(f"{LEVEL_WORDS[level]}: {sum(mine.values())}")
        for k, v in sorted(mine.items(), key=lambda kv: -kv[1]):
            out.append(f"  {k} {v} ({v / max(1, len(pages)):.2f} a page, "
                       f"{100 * v / max(1, regions):.1f} per 100 regions)")
    return out


def summary_lines(lines: Sequence[dict[str, Any]], slowest: int = 10) -> list[str]:
    """The session's tables from its *lines* (numbers only): first the defects by level (`level_lines`); then per
    stage and helper the total seconds, the share of the session, the median and the 95th percentile per page; the
    slowest pages with their facts; per helper the regions it changed; fits, sound words, patches withheld, panes
    hidden, edits by kind and by what had acted on the region; what the log cost."""
    pages = [ln for ln in lines if ln.get("type") == "page"]
    out: list[str] = level_lines(lines) + [""]
    total_ms = sum(float(p.get("ms") or 0.0) for p in pages)
    read = [p for p in pages if not p.get("cached")]
    ends = Counter(str(p.get("outcome") or "done") for p in pages)
    how = ", ".join(f"{k} {n}" for k, n in sorted(ends.items(), key=lambda kv: (kv[0] != "done", kv[0])))
    out.append(f"pages {len(pages)} ({how or 'none'}; read {len(read)}, from the cache {len(pages) - len(read)}); "
               f"{total_ms / 1000:.1f} s in pages")
    if pages:
        out += _time_lines(pages, slowest, total_ms)
    out += _count_lines(lines, pages, total_ms)
    return out


def _time_lines(pages: Sequence[dict[str, Any]], slowest: int, total_ms: float) -> list[str]:
    """The stages' and helpers' times and the slowest pages (`summary_lines`)."""
    out: list[str] = []
    per: dict[str, list[float]] = {}
    calls: Counter[str] = Counter()
    for p in pages:
        for k, v in (p.get("stages") or {}).items():
            per.setdefault("stage " + k, []).append(float(v))
        for k, (ms, n) in ((k, v) for k, v in (p.get("helpers") or {}).items() if isinstance(v, list) and len(v) == 2):
            per.setdefault(k, []).append(float(ms))
            calls[k] += int(n)
    out.append("")
    out.append(f"{'stage / helper':32} {'total s':>8} {'share':>6} {'med ms':>8} {'p95 ms':>8} "
               f"{'pages':>5} {'calls':>6}")
    for k, values in sorted(per.items(), key=lambda kv: -sum(kv[1])):
        total = sum(values)
        out.append(f"{k[:32]:32} {total / 1000:8.2f} {100 * total / total_ms if total_ms else 0:5.1f}% "
                   f"{_median(values):8.1f} {_quantile(values, 0.95):8.1f} {len(values):5d} "
                   f"{calls.get(k, '') if not k.startswith('stage ') else '':>6}")
    out.append("")
    out.append(f"slowest pages: {'n':>4} {'ms':>8} {'units':>5} {'cache':>5} {'colour':>6} {'ink':>5} {'dark':>5} "
               f"{'drawn':>5} {'regions':>7}  top stage")
    for p in sorted(pages, key=lambda q: -float(q.get("ms") or 0.0))[:slowest]:
        f = p.get("facts") or {}
        stages = p.get("stages") or {}
        top = max(stages.items(), key=lambda kv: kv[1])[0] if stages else "-"
        if (p.get("outcome") or "done") != "done":
            top = f"{top} ({p.get('outcome')})"
        out.append(f"{'':14} {p.get('n', 0):4d} {float(p.get('ms') or 0):8.0f} {p.get('units', 0):5d} "
                   f"{'yes' if p.get('cached') else 'no':>5} {f.get('colour', 0):6.2f} {f.get('ink', 0):5.2f} "
                   f"{f.get('dark', 0):5.2f} {f.get('drawn', 0):5.2f} {(p.get('regions') or {}).get('n', 0):7d}  {top}")
    return out


def _count_lines(lines: Sequence[dict[str, Any]], pages: Sequence[dict[str, Any]], total_ms: float) -> list[str]:
    """What the helpers changed and counted, the regions, the window's lines, the edits, the log's cost
    (`summary_lines`)."""
    out: list[str] = []
    effect: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    fitted: Counter[str] = Counter()
    sound: Counter[str] = Counter()
    status: Counter[str] = Counter()
    flags: Counter[str] = Counter()
    low = 0
    for p in pages:
        effect.update({k: int(v) for k, v in (p.get("effect") or {}).items() if isinstance(v, (int, float))})
        counts.update({k: v for k, v in (p.get("counts") or {}).items() if isinstance(v, (int, float))})
        regions = p.get("regions") or {}
        fitted.update(regions.get("fitted") or {})
        sound.update(regions.get("sound") or {})
        status.update(regions.get("status") or {})
        flags.update(regions.get("flags") or {})
        low += int(regions.get("low_as_drawn") or 0)
    out.append("")
    out.append("regions changed, per helper: " + (", ".join(f"{k} {v}" for k, v in sorted(effect.items())) or "none"))
    out.append("counts: " + (", ".join(f"{k} {_num(v)}" for k, v in sorted(counts.items())) or "none"))
    out.append("regions by status: " + (", ".join(f"{k} {v}" for k, v in sorted(status.items())) or "none")
               + f"; read with low confidence, left as drawn {low}")
    out.append("fits taken: " + (", ".join(f"{k} {v}" for k, v in sorted(fitted.items())) or "none"))
    out.append("sound words: " + (", ".join(f"{k} {v}" for k, v in sorted(sound.items())) or "none"))
    out.append("review flags: " + (", ".join(f"{k} {v}" for k, v in sorted(flags.items())) or "none"))
    uis = [ln for ln in lines if ln.get("type") == "ui"]
    withheld: Counter[str] = Counter()
    panes: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    loose: dict[str, list[float]] = {}
    for u in uis:
        withheld.update(u.get("withheld") or {})
        panes.update(u.get("panes") or {})
        seen.update({k: v for k, v in (u.get("counts") or {}).items() if isinstance(v, (int, float))})
        for k, v in (u.get("loose") or {}).items():
            if isinstance(v, list) and len(v) == 2:
                got = loose.setdefault(k, [0.0, 0])
                got[0], got[1] = got[0] + float(v[0]), got[1] + int(v[1])
    out.append("patches withheld (looks): " + (", ".join(f"{k} {v}" for k, v in sorted(withheld.items())) or "none"))
    out.append("panes hidden: " + (", ".join(f"{k} {v}" for k, v in sorted(panes.items())) or "none"))
    out.append("window: " + (", ".join(f"{k} {_num(v)}" for k, v in sorted(seen.items())) or "none"))
    out.append("timed outside the pages: " + (", ".join(f"{k} {v[0]:.0f} ms / {v[1]}" for k, v in sorted(
        loose.items(), key=lambda kv: -kv[1][0])) or "none"))
    edits = [ln for ln in lines if ln.get("type") == "edit"]
    kinds = Counter(str(e.get("kind")) for e in edits)
    by: Counter[str] = Counter()
    for e in edits:
        for r in e.get("regions") or []:
            for name in r.get("acted") or ["none"]:
                by[f"{e.get('kind')}:{name}"] += 1
    out.append("edits: " + (", ".join(f"{k} {v}" for k, v in sorted(kinds.items())) or "none"))
    out.append("edited regions by what had acted on them: " + (", ".join(f"{k} {v}" for k, v in sorted(by.items()))
                                                              or "none"))
    own = sum(float(p.get("self_ms") or 0.0) for p in pages)
    share = 100 * own / total_ms if total_ms else 0
    out.append(f"the log's own cost: {own:.1f} ms in all, {share:.2f} % of the pages' time")
    return out


def _num(value: Any) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def read_lines(path: Path | str) -> list[dict[str, Any]]:
    """The lines of an analysis file (a line that is no JSON object left out)."""
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for text in f:
                try:
                    line = json.loads(text)
                except ValueError:
                    continue
                if isinstance(line, dict):
                    out.append(line)
    except OSError:
        pass
    return out
