"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: short videos of the live page-by-page flow, one feature a video, for
posts - the real TASlation window, in English, over public sample pages on the browser-type stand-in viewer, recorded
as the stand-in turns its pages, and made into a video at real speed with a stopwatch per page. Never part of a
release; the videos show CC BY-NC pages and are never committed or shipped.

    python tools/promo_video.py record --out REC.zip [--label L] [--ollama URL] [--package CHECKOUT] [--turns 6]
                                       [--pace 2] [--series 1] [--first 2] [--layout single|spread] [--fps 15]
                                       [--start-ollama PORT] [--ollama-window-cache auto|off|on]
                                       [--ocr-runs-on auto|cpu|gpu] [--from-start | --turn-at-ready]
    python tools/promo_video.py render REC.zip [REC_B.zip] --out promo/NAME.mp4 [--title TEXT] [--end LINE]...
                                       [--labels A B] [--pages FROM-TO] [--max-pause 2.5] [--format auto|mp4|gif]
                                       [--start-speed 4] [--start-head 1] [--real-before 1.5]
    python tools/promo_video.py info REC.zip [REC_B.zip]
    python tools/promo_video.py sample --out FOLDER [--format auto|mp4|gif]

**record** runs the window once and keeps what it showed in a recording file (*--out*, a ZIP outside any repository
and outside ``~/.taslation``: the scratch folder), so that a video can be made again without a run:

* the stand-in: `standin_viewer`'s page in a throwaway Chrome or Edge window of its own (``--app``, a scratch profile,
  deleted at the end), as `tools/standin_e2e.py` starts it: a band at the top, a dark ground, every turn drawn soft
  first and sharp a while later (*--soft*, seeded by *--seed*). Its pages are OpenMantra's ("Towards Fully Automated
  Manga Translation", Ryota Hinami, Shonosuke Ishiwatari, Kazuhiko Yasuda, Yusuke Matsui, AAAI 2021; published by
  Mantra Inc., CC BY-NC 4.0), read in place from ``~/.taslation/datasets/openmantra`` by file URL: the *--series*-th
  series of the sorted list (never named here), the page before *--first* to start on, then one page (*--layout
  single*) or one spread a turn. The page turns BY ITSELF from the script in its URL, each turn released by this tool
  through the control file in the scratch folder: no key, no click, nothing is sent to any window;
* TASlation's window in this process (`ui.app.App` as ``taslation gui --book NAME`` opens it: page by page, Auto on,
  the Reader role), in English, on a scratch state folder (TASLATION_STATE_DIR: the legal notice dismissed, the
  first start's popup seen, the reader's capture area 0,85,0,0 as on a browser reader), the offline guard on (only
  the translator's port on this computer can be reached), the real OCR models (TASLATION_MODELS_DIR) and the default
  translator through the Ollama at *--ollama* (requests only: never started, stopped or set up here; what the window
  loaded it lets go of at its close, and what is still loaded of it at the end that was not before is unloaded).
  *--package* runs another checkout's ``taslation`` package (the one under that folder) in the same way, so that two
  versions can be recorded alike; *--label* names the recording (default: TASlation and the package's version).
  With *--start-ollama PORT* the window's own starter starts Ollama instead, as `tools/standin_e2e.py --start-ollama`
  has it: on that loopback port, where nothing may answer (never the default port, whose server is the person's), with
  the environment the starter chooses for the window's settings (*--ollama-window-cache*, *--ocr-runs-on*: the
  window's settings ``ollama_window_cache`` and ``ocr_runs_on``, the app's defaults where not given); the port is set
  in this process alone, the server told it by OLLAMA_HOST in this process's environment (with OLLAMA_NOPRUNE: the
  model store stays as it is); what the starter chose goes into the recording (``server``), and the server is stopped
  as TASlation's own end stops it. Where the OCR readers read while the pictures were taken goes in as well
  (``readers``, looked at every half second);
* the guard of `tools/demo_video.py`, as `tools/standin_e2e.py` has it: the window list the app sees holds the
  stand-in alone (found by the process tree this tool started AND the token in its title; no other window's title
  is read), every function that captures, moves, raises or enlarges a window acts on the stand-in or this process's
  own windows, keys and clicks are refused outright, the global hot keys are never registered with Windows, the
  window chosen is checked at every step and anything but the stand-in ends the run at once; the window is told the
  viewer is in front (the reader's case), and the foreground is never changed by this tool;
* the run: the stand-in starts on the page before *--first*; once the window has loaded the translation model and
  translated that page (the start-up: left out, unless *--from-start* or *--turn-at-ready* below) and rests for a
  moment, the pictures begin, and then
  *--turns* turns, each released *--pace* seconds after the window finished the page before (its result on the
  page), each timed: the stand-in's own draw of the new page (the turn), the first lettered bubble, the last, the
  finished page and the bubbles lettered (the window's own page events: what its page showed, when);
* pictures of TASlation's OWN window only (PrintWindow of its handle, the client area; never a copy of the screen,
  never the stand-in's window), about *--fps* a second, each with its time, into the recording file (JPEG, a picture
  the same as the one before kept once); *--grab tk* takes them from the Tk loop as `tools/demo_video.py` does,
  *--grab thread* (the default) from a thread of their own;
* *--from-start*: the start-up IS recorded. The pictures begin as the window is made (the first picture is asked for
  right after `App` is made, before its loop runs) and the window's start is timed: ``launch_t`` just before `App` is
  made, ``appeared_t`` the first picture of the window that is not of one colour (the window drawn: THE WINDOW'S
  APPEARANCE, where the clocks of a start begin), ``ready_t`` as the window takes its "ready" event (the status line
  says Ready). The window opens at its size and place from its first picture on (kept for it in the scratch state as
  its place at the last close; a package that keeps none opens as at a first start and is moved). The page the
  stand-in shows at the launch (the one before *--first*) is the recording's first page, timed from the appearance
  to its first bubble and its last; *--turns* (0 allowed) turns follow it as usual;
* *--turn-at-ready* (a recording from the start as well): the stand-in shows the page before *--first* at the
  launch, and its first turn is released at the moment the window says it is ready (from the window's own handler
  of the "ready" event, right after it ran: the turn a person makes as the window becomes ready); that turn is
  timed as any turn, from the stand-in's draw of the new page, and its sharp frame is noted too.

Nothing of the pages' text is printed or logged: the tool prints numbers. At the end: the window closed through its
own close, the browser's process tree (and nothing else) ended, its profile and the scratch state deleted.

**render** makes the video of one recording, or of two side by side (for two server set-ups, *--ollama*, or two
versions, *--package*; each side with its label):

* real speed, no speed-up: a page is shown for as long as it took, from the turn to its last bubble lettered and on;
  a pause between two pages longer than *--max-pause* is shortened (never the time a page takes), and the caption
  says so while it is on show; two sides start each page at the same moment (the caption says so too), so the faster
  side waits on its finished page;
* per page and side a stopwatch that starts at the turn and stops when the page's last bubble is lettered, and the
  count of bubbles lettered; *--pages FROM-TO* takes a stretch of the recorded turns (pages next to each other only,
  so that nothing in between is left out);
* a recording from the start (two side by side: both of the same kind): with *--from-start*, the first page's
  stopwatch starts at each window's appearance (``appeared_t``; both sides at the same moment of the video) and stops
  at its page's last bubble; with *--turn-at-ready*, the video shows each window from its appearance to the turn
  (both turns at the same moment of the video, the side that appeared later empty before it appeared) and the
  stopwatch starts at the turn. Under it: the first bubble's time on the same clock, and the start's own clock
  (from the appearance; stopped at the window's "ready"). The start's quiet stretch is shown *--start-speed* times
  faster (1: in full): from *--start-head* s after the appearance to *--real-before* s before the first of the
  sides' first bubbles (from the start) or before the turn (at ready); while it is, every picture carries an "x4"
  badge and the caption says so, and the clocks go on showing real seconds (they run faster with the pictures);
* a title card (*--title*, ``\\n`` for a new line) and an end card of up to four lines (*--end*, once a line: what
  was done, the percentage, the computer it was measured on, the project's address); text on the cards comes from
  the command line, the tool's own words state facts only;
* on every frame, small but readable, the credit the dataset's licence asks for (`CREDIT`);
* MP4 with H.264 (the Windows Media Foundation encoder through OpenCV, no hardware encoder asked for; the written
  file read back: its sample entry must be ``avc1``, its frames all there, and its ``moov`` put first for streaming),
  at most *--width* (1280) pixels wide, *--fps* (30) frames a second; where that cannot be made, an animated GIF of at
  most *--gif-limit-mb* (15) MB (Pillow, one palette, made smaller until it fits). The report says which was made.
  The video may be written into a repository only where git ignores the path (``promo/`` of the main checkout, in
  ``.git/info/exclude``).

**info** prints a recording's facts (numbers only). **sample** proves the rendering without a window, a model or a
manga page: made-up recordings of drawn rectangles and text, rendered alone and side by side, and as a GIF."""

from __future__ import annotations

import argparse
import bisect
import contextlib
import faulthandler
import hashlib
import io
import json
import logging
import math
import os
import queue
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

REAL_STATE = Path.home() / ".taslation"
CREDIT = "Sample pages: OpenMantra dataset (Mantra Inc., CC BY-NC 4.0), modified"
PROJECT = "github.com/tamachi955/taslation"
FORMAT = 1  # the recording file's
BOOK = "OpenMantra sample"
PLAMO = "taslation-plamo3-translate-2b"
DEFAULT_PORT = 11434
DEFAULT_OLLAMA = f"http://127.0.0.1:{DEFAULT_PORT}"
LETTERED_KINDS = ("filling", "final", "translated")  # what the window's page shows when it shows lettering
MAX_END_LINES = 4
CUT_TOLERANCE_MS = 60.0  # a pause shown this much shorter than it was is one cut
NOTE_REAL = "Real time"
NOTE_SIDES = "Real time. Both sides start each page at the same moment"
NOTE_START = "Real time. The clock starts as the window appears"
NOTE_START_SIDES = "Real time. Both clocks start as each window appears"
MODES = ("turns", "start", "turn_at_ready")  # a recording of turns after the start-up; from the start; a turn at ready
MIN_SPED_MS = 1000.0  # a stretch of the start shorter than this is shown as it was

# the record's pace
TICK_MS = 40
REST_S = 1.5  # the window at rest so long after the first page before the pictures begin
PREROLL_S = 1.0  # the pictures this long before the first turn
END_HOLD_S = 2.5  # ... and this long after the last page finished
PLACEMENT_EVERY_S = 0.5  # where the OCR readers read, looked at so often
TURN_WAIT_S = 10.0  # the stand-in's draw of a turn released, at most this long after
END_DUMP_S = 90.0  # the end of a run taking longer than this: where its threads are, said
GRAB_TK_MIN_MS = 10

# colours of the video
BG = (16, 16, 18)
HEADER_BG = (30, 31, 34)
CAPTION_BG = (22, 22, 24)
TEXT = (242, 242, 242)
DIM = (150, 152, 158)
GREEN = (86, 211, 120)
AMBER = (240, 180, 60)


def now_ms() -> float:
    return time.time() * 1000.0


def speed_text(factor: float) -> str:
    return f"x{factor:g}"


def sped_note(factor: float) -> str:
    """The caption while a stretch is shown *factor* times faster."""
    return f"Shown {factor:g} times faster ({speed_text(factor)}). The clocks show real seconds"


# ---------------------------------------------------------------------------------------------------- the files
def git_ignored(path: Path) -> bool | None:
    """Whether *path* lies in a git work tree: None when it does not; else whether git ignores it there."""
    path = Path(path).resolve()
    folder = path.parent
    while not folder.exists():
        folder = folder.parent
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=folder, capture_output=True, text=True,
                             timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None if not path.is_relative_to(ROOT) else False
    if top.returncode != 0:
        return None
    check = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=folder, capture_output=True, timeout=20)
    return check.returncode == 0


def check_video_path(path: Path) -> Path:
    """A video goes outside every repository, or where git ignores it (``promo/``): never where it could be
    committed."""
    path = Path(path).resolve()
    if path.is_relative_to(REAL_STATE.resolve()):
        raise SystemExit("a video never goes into ~/.taslation")
    if git_ignored(path) is False:
        raise SystemExit(f"{path} could be committed: write videos where git ignores them (promo/, excluded in "
                         ".git/info/exclude) or outside the repository")
    return path


def check_scratch_path(path: Path) -> Path:
    """A recording, and the scratch of a run, go outside every repository and outside ``~/.taslation``."""
    path = Path(path).resolve()
    if path.is_relative_to(REAL_STATE.resolve()) or path.is_relative_to(ROOT) or git_ignored(path) is not None:
        raise SystemExit(f"{path}: recordings go into a scratch folder, not into a repository nor ~/.taslation")
    return path


# ---------------------------------------------------------------------------------------------------- the recording
class RecordingWriter:
    """A recording file being written: the pictures as they come (JPEG; one the same as the picture before it is
    kept once, its time noted all the same), then its facts (`finish`, ``meta.json``)."""

    def __init__(self, path: Path, quality: int = 92):
        self.path = Path(path)
        self.quality = quality
        self.zip = zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_STORED)
        self.frames: list[tuple[float, str]] = []
        self.stored = 0
        self.size: tuple[int, int] | None = None  # the first picture's
        self.last_size: tuple[int, int] | None = None  # ... and the last one's
        self._digest = b""
        self.lock = threading.Lock()

    def add(self, t: float, image: Image.Image) -> bool:
        """The picture *image* taken at *t* (ms since the epoch); False when it is the one before again."""
        rgb = image if image.mode == "RGB" else image.convert("RGB")
        digest = hashlib.blake2b(rgb.tobytes() + repr(rgb.size).encode(), digest_size=16).digest()
        with self.lock:
            if self.frames and digest == self._digest:
                self.frames.append((t, self.frames[-1][1]))
                return False
            name = f"frames/{self.stored:06d}.jpg"
            buffer = io.BytesIO()
            rgb.save(buffer, format="JPEG", quality=self.quality, subsampling=0)
            self.zip.writestr(name, buffer.getvalue())
            self.stored += 1
            self.size = self.size or rgb.size
            self.last_size = rgb.size
            self._digest = digest
            self.frames.append((t, name))
            return True

    def finish(self, meta: dict[str, Any]) -> Path:
        with self.lock:
            data = dict(meta)
            data["format"] = FORMAT
            data.setdefault("picture", list(self.size) if self.size else None)
            data["frames"] = [[round(t, 1), name] for t, name in self.frames]
            self.zip.writestr("meta.json", json.dumps(data, indent=0, default=str))
            self.zip.close()
        return self.path

    def abandon(self) -> None:
        with contextlib.suppress(Exception):
            self.zip.close()
        with contextlib.suppress(OSError):
            self.path.unlink()


class Recording:
    """A recording file read back: its facts (`meta`), its pictures by time (`at`, `picture`) and its pages' times
    (`pages`)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path, "r")
        self.meta: dict[str, Any] = json.loads(self.zip.read("meta.json").decode("utf-8"))
        if self.meta.get("format") != FORMAT:
            raise SystemExit(f"{self.path}: not a recording of this tool's (format {self.meta.get('format')})")
        self.frames = [(float(t), str(name)) for t, name in self.meta.get("frames", [])]
        if not self.frames:
            raise SystemExit(f"{self.path}: the recording holds no picture")
        self.times = [t for t, _name in self.frames]
        self.mode = str(self.meta.get("mode") or "turns")
        if self.mode not in MODES:
            raise SystemExit(f"{self.path}: a recording of an unknown kind ({self.mode})")
        turns = list(self.meta.get("turns", []))
        if self.mode == "start":  # the page on show at the launch, timed from the window's appearance
            turns = [start_turn(self.meta, self.appeared)] + turns
        self.pages = page_times(turns, self.meta.get("displays", []), self.meta.get("results", []), self.end)
        self._lettered = [lettered_line(turn, self.meta.get("displays", [])) for turn in self.pages]

    @property
    def label(self) -> str:
        return str(self.meta.get("label") or "")

    @property
    def first(self) -> float:
        return self.times[0]

    @property
    def from_start(self) -> bool:
        return self.mode != "turns"

    @property
    def appeared(self) -> float:
        """The window's appearance (``appeared_t``: its first picture not of one colour); the first picture where the
        recording does not say."""
        value = self.meta.get("appeared_t")
        return float(value) if value is not None else self.times[0]

    @property
    def ready_t(self) -> float | None:
        value = self.meta.get("ready_t")
        return float(value) if value is not None else None

    @property
    def end(self) -> float:
        return float(self.meta.get("end_t") or self.times[-1])

    @property
    def size(self) -> tuple[int, int]:
        size = self.meta.get("picture") or Image.open(io.BytesIO(self.zip.read(self.frames[0][1]))).size
        w, h = size
        return int(w), int(h)

    def at(self, t: float) -> str:
        """The picture on show at *t*: the last one taken at *t* or before (the first one before it)."""
        i = bisect.bisect_right(self.times, t) - 1
        return self.frames[max(0, i)][1]

    def picture(self, name: str) -> Image.Image:
        return Image.open(io.BytesIO(self.zip.read(name))).convert("RGB")

    def lettered(self, index: int, t: float) -> int:
        """How many bubbles page *index* (of `pages`) showed lettered at *t*, by the window's own page events."""
        times, counts = self._lettered[index]
        i = bisect.bisect_right(times, t) - 1
        return counts[i] if i >= 0 else 0

    def close(self) -> None:
        self.zip.close()


def start_turn(meta: dict[str, Any], appeared: float) -> dict[str, Any]:
    """A recording from the start: its first page is the one the stand-in showed at the launch, its "turn" the
    window's appearance (no turn was made: the clock of the start begins there)."""
    return {"k": 0, "t": float(appeared), "screen": meta.get("start_screen") or [0, 0], "start": True,
            "sharp_t": None, "released_t": None}


def start_facts(rec: Recording) -> dict[str, Any] | None:
    """The start of a recording from the start, in seconds: the appearance after the launch, ready after the
    appearance (and after the launch); from the start: the first page's first bubble and last from the appearance;
    at ready: the turn after ready, its first bubble and last from the turn, and from its sharp frame."""
    if not rec.from_start:
        return None

    def s(ms: float | None) -> float | None:
        return None if ms is None else round(ms / 1000, 2)

    meta, appeared, ready = rec.meta, rec.appeared, rec.ready_t
    launch = meta.get("launch_t")
    out: dict[str, Any] = {"mode": rec.mode,
                           "appeared_after_launch_s": s(appeared - float(launch)) if launch is not None else None,
                           "ready_after_appeared_s": s(ready - appeared) if ready is not None else None,
                           "ready_after_launch_s": s(ready - float(launch)) if ready is not None and launch else None}
    if not rec.pages:
        return out
    page = rec.pages[0]
    if rec.mode == "start":
        out.update(first_bubble_after_appeared_s=s(page.get("first_ms")),
                   last_bubble_after_appeared_s=s(page.get("page_ms")),
                   finished_after_appeared_s=s(page.get("result_ms")), bubbles=page.get("bubbles"))
    else:
        sharp = page.get("sharp_t")
        out.update(turn_after_ready_s=s(page["t"] - ready) if ready is not None else None,
                   turn_after_appeared_s=s(page["t"] - appeared),
                   first_bubble_after_turn_s=s(page.get("first_ms")),
                   last_bubble_after_turn_s=s(page.get("page_ms")),
                   finished_after_turn_s=s(page.get("result_ms")),
                   first_bubble_after_sharp_s=s(page["first_t"] - float(sharp))
                   if sharp is not None and page.get("first_t") is not None else None,
                   last_bubble_after_sharp_s=s(page["stop_t"] - float(sharp))
                   if sharp is not None and page.get("stop_t") is not None else None,
                   bubbles=page.get("bubbles"))
    return out


def _screen(value: Any) -> tuple[int, bool] | None:
    if value is None:
        return None
    try:
        page, spread = value
        return int(page), bool(int(spread))
    except (TypeError, ValueError):
        return None


def _mine(turn: dict[str, Any], displays: Sequence[dict[str, Any]], end: float) -> list[dict[str, Any]]:
    """The window's page events of the page *turn* turned to (from its turn to the next, ``turn["until"]``): those
    whose picture is of that screen; where the window's pictures carry no readable code at all (another stand-in),
    those after the first picture of the viewer's own (``live``) after the turn."""
    a, c, screen = turn["t"], turn.get("until", end), _screen(turn.get("screen"))
    spell = [d for d in displays if a <= float(d["t"]) < c]
    if any(d.get("screen") is not None for d in displays):
        return [d for d in spell if _screen(d.get("screen")) == screen]
    live = next((i for i, d in enumerate(spell) if d.get("kind") == "live"), None)
    return spell[live + 1:] if live is not None else []


def page_times(turns: Sequence[dict[str, Any]], displays: Sequence[dict[str, Any]],
               results: Sequence[dict[str, Any]], end: float) -> list[dict[str, Any]]:
    """Each turn's times (ms since the epoch; ``*_ms`` from the turn): ``t`` the stand-in's draw of the new page, the
    first bubble lettered on it, the last (``stop_t``: the first page event that shows as many lettered as the
    finished page holds; the finished page's own time when none did, or when it holds none), the finished page
    (``result_t``, the window's result on the page) and its bubbles; ``finished`` False when no result came before the
    next turn."""
    displays = sorted(displays, key=lambda d: float(d["t"]))
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(turns):
        if raw.get("t") is None:
            continue
        turn = dict(raw)
        turn["t"] = float(turn["t"])
        nxt = next((float(u["t"]) for u in turns[i + 1:] if u.get("t") is not None), float(end))
        turn["until"] = nxt
        screen = _screen(turn.get("screen"))
        mine = [d for d in _mine(turn, displays, end) if d.get("kind") in LETTERED_KINDS]
        result = next((r for r in sorted(results, key=lambda r: float(r["t"]))
                       if turn["t"] <= float(r["t"]) < nxt
                       and (_screen(r.get("screen")) in (screen, None))), None)
        first = next((float(d["t"]) for d in mine if int(d.get("lettered") or 0) >= 1), None)
        stop = bubbles = None
        if result is not None:
            bubbles = int(result.get("bubbles") or 0)
            reached = next((float(d["t"]) for d in mine if bubbles and int(d.get("lettered") or 0) >= bubbles), None)
            stop = min(reached, float(result["t"])) if reached is not None else float(result["t"])
            if bubbles and first is None:
                first = stop
        turn.update(first_t=first, stop_t=stop, result_t=float(result["t"]) if result else None, bubbles=bubbles,
                    finished=result is not None)
        a = turn["t"]
        turn.update(first_ms=None if first is None else round(first - a, 1),
                    page_ms=None if stop is None else round(stop - a, 1),
                    result_ms=None if result is None else round(float(result["t"]) - a, 1))
        out.append(turn)
    return out


def lettered_line(turn: dict[str, Any], displays: Sequence[dict[str, Any]]) -> tuple[list[float], list[int]]:
    """The bubbles page *turn* showed lettered, as its page events came: (times, counts); the finished page's count
    from its stop on."""
    mine = _mine(turn, sorted(displays, key=lambda d: float(d["t"])), turn.get("until", math.inf))
    times, counts = [turn["t"]], [0]
    for d in mine:
        n = int(d.get("lettered") or 0) if d.get("kind") in LETTERED_KINDS else 0
        if turn.get("stop_t") is not None and float(d["t"]) >= turn["stop_t"]:
            n = max(n, int(turn.get("bubbles") or 0))
        times.append(float(d["t"]))
        counts.append(n)
    if turn.get("stop_t") is not None:
        times.append(turn["stop_t"])
        counts.append(int(turn.get("bubbles") or 0))
        order = sorted(range(len(times)), key=lambda k: (times[k], k))
        times, counts = [times[k] for k in order], [counts[k] for k in order]
        # from the stop on the page holds its bubbles (a later event of the page may count them otherwise)
        counts = [max(c, int(turn.get("bubbles") or 0)) if t >= turn["stop_t"] else c for t, c in zip(times, counts)]
    return times, counts


# ---------------------------------------------------------------------------------------------------- the plan
@dataclass
class Options:
    """How the video is cut (ms): *lead* the time before a turn shown at a page's start (*first_lead* for the first
    page: the page before it is the one the start-up translated), *max_pause* the longest pause between two pages
    shown as it was, *end_hold* after the last page, the cards."""

    lead_ms: float = 500.0
    first_lead_ms: float = 0.0
    max_pause_ms: float = 2500.0
    end_hold_ms: float = 2000.0
    title_ms: float = 2500.0
    end_ms: float = 4500.0
    pages: tuple[int, int] | None = None  # FROM-TO, 1-based, of the recorded turns
    # a recording from the start: its quiet stretch shown *start_speed* times faster (1: in full), from *start_head*
    # after the appearance to *real_before* before the first of the first bubbles (from the start) or the turn (at
    # ready)
    start_speed: float = 4.0
    start_head_ms: float = 1000.0
    real_before_ms: float = 1500.0


@dataclass
class Segment:
    """A stretch of the video: a card, or a page (*index* into each recording's pages, *number* its place in the
    video), shown from *lead* ms before its turn to *body* + *tail* ms after it (*body*: the slowest side's page);
    *cut_before* / *cut_after*: the pause before / after it was shortened (real and shown ms of the side whose page
    took longest); *speeds*: stretches of it shown faster, each (from, to, how many times faster), in ms from the
    turn (*ms* is what the video shows: those stretches take their real time divided by their factor)."""

    kind: str
    ms: float
    number: int = 0
    index: int = 0
    lead: float = 0.0
    body: float = 0.0
    tail: float = 0.0
    cut_before: tuple[float, float] | None = None
    cut_after: tuple[float, float] | None = None
    speeds: tuple[tuple[float, float, float], ...] = ()

    def u_at(self, local: float) -> float:
        """The real time (ms from the turn) shown *local* ms into the segment."""
        u, left = -self.lead, local
        for a, b, factor in self.speeds:
            if left <= a - u:
                return u + left
            left -= a - u
            if left <= (b - a) / factor:
                return a + left * factor
            left -= (b - a) / factor
            u = b
        return u + left

    def factor_at(self, local: float) -> float:
        """How many times faster than real time the video runs *local* ms into the segment (1.0: real time)."""
        u = self.u_at(local)
        return next((factor for a, b, factor in self.speeds if a <= u < b), 1.0)


def shown_ms(real: float, speeds: Sequence[tuple[float, float, float]]) -> float:
    """What *real* ms with *speeds* in them take in the video."""
    return real - sum((b - a) * (1.0 - 1.0 / factor) for a, b, factor in speeds)


def sped(a: float, b: float, factor: float) -> tuple[tuple[float, float, float], ...]:
    """The stretch from *a* to *b* (ms from the turn) shown *factor* times faster: none where the factor is 1 or less,
    or the stretch shorter than MIN_SPED_MS."""
    return ((a, b, float(factor)),) if factor > 1.0 and b - a >= MIN_SPED_MS else ()


def kind_of(recs: Sequence[Recording]) -> str:
    """The kind of the recordings of one video (`MODES`): two side by side are of one kind."""
    modes = {r.mode for r in recs}
    if len(modes) != 1:
        raise SystemExit("two recordings side by side are of one kind (both from the start, both a turn at ready, "
                         "or both of turns)")
    return modes.pop()


def page_span(rec: Recording, index: int) -> float:
    """How long page *index* of *rec* is timed: from its turn to its last bubble lettered; to the next turn when it
    never finished."""
    page = rec.pages[index]
    return float(page["page_ms"]) if page.get("page_ms") is not None else float(page["until"] - page["t"])


def plan(recs: Sequence[Recording], opts: Options) -> list[Segment]:
    """The video's segments: the title card, the pages, the end card (see `Segment`). A recording from the start
    whose first page is shown: from the start, that page from the appearance on (no lead: nothing was there before
    it); at ready, the turn's lead the longest stretch from a side's appearance to its turn; the stretch of it the
    options say shown faster (`Options.start_speed`)."""
    mode = kind_of(recs)
    count = min(len(r.pages) for r in recs)
    if count == 0:
        raise SystemExit("the recording holds no timed page")
    lo, hi = opts.pages or (1, count)
    if not 1 <= lo <= hi <= count:
        raise SystemExit(f"--pages is a stretch within 1-{count}")
    indexes = list(range(lo - 1, hi))
    spans = [[page_span(r, i) for r in recs] for i in indexes]
    bodies = [max(s) for s in spans]
    slowest = [max(range(len(recs)), key=lambda s, row=row: row[s]) for row in spans]
    pauses: list[tuple[float, float]] = []  # (real, shown) after each page but the last, of its slowest side
    for j, i in enumerate(indexes[:-1]):
        rec = recs[slowest[j]]
        real = rec.pages[i + 1]["t"] - (rec.pages[i]["t"] + spans[j][slowest[j]])
        pauses.append((max(0.0, real), max(0.0, min(opts.max_pause_ms, real))))
    first = indexes[0]

    def room_before(r: Recording) -> float:  # from the page before's last bubble (or the first picture) to the turn
        before = r.pages[first - 1].get("stop_t") if first > 0 else None
        return r.pages[first]["t"] - (before if before is not None else r.first)

    # (the first page of the recording: the page before it is the start-up's, shown for *first_lead* at most)
    lead0 = min([opts.first_lead_ms if first == 0 else opts.lead_ms] + [room_before(r) for r in recs])
    leads = [max(0.0, lead0)] + [min(opts.lead_ms, shown * 0.4) for _real, shown in pauses]
    speeds0: tuple[tuple[float, float, float], ...] = ()
    if mode == "start" and first == 0:  # the clock at the appearance: the stretch before the first bubbles
        leads[0] = 0.0
        firsts = [float(r.pages[0]["first_ms"]) if r.pages[0].get("first_ms") is not None else page_span(r, 0)
                  for r in recs]
        speeds0 = sped(opts.start_head_ms, min(firsts) - opts.real_before_ms, opts.start_speed)
    elif mode == "turn_at_ready" and first == 0:  # each window from its appearance to the turn
        leads[0] = max(0.0, max(r.pages[0]["t"] - r.appeared for r in recs))
        speeds0 = sped(-leads[0] + opts.start_head_ms, -opts.real_before_ms, opts.start_speed)
    last = indexes[-1]
    end_room = min(r.end - (r.pages[last]["t"] + page_span(r, last)) for r in recs)
    tails = [shown - leads[j + 1] for j, (_real, shown) in enumerate(pauses)]
    tails.append(max(0.0, min(opts.end_hold_ms, end_room)))
    cuts: list[tuple[float, float] | None] = []
    for j, (real, shown) in enumerate(pauses):
        # the real time a side's pictures skip between this page's end and the next page's start: its own pause
        # less what is shown of it (its wait for the slowest side, then the pause shown)
        i = indexes[j]
        skipped = [(r.pages[i + 1]["t"] - (r.pages[i]["t"] + spans[j][s])) - (bodies[j] - spans[j][s] + shown)
                   for s, r in enumerate(recs)]
        cuts.append((real, shown) if max(skipped) > CUT_TOLERANCE_MS else None)
    segments: list[Segment] = []
    if opts.title_ms > 0:
        segments.append(Segment("title", opts.title_ms))
    for j, i in enumerate(indexes):
        speeds = speeds0 if j == 0 else ()
        segments.append(Segment("page", shown_ms(leads[j] + bodies[j] + tails[j], speeds), number=j + 1, index=i,
                                lead=leads[j], body=bodies[j], tail=tails[j],
                                cut_before=cuts[j - 1] if j > 0 else None,
                                cut_after=cuts[j] if j < len(cuts) else None, speeds=speeds))
    if opts.end_ms > 0:
        segments.append(Segment("end", opts.end_ms))
    return segments


@dataclass
class SideState:
    """One side of a page's frame: the picture on show (*name*, taken at *source_t*), the stopwatch (*watch_ms*,
    *watch*: "ready" before the turn, "running", "stopped" at the last bubble, "unfinished") and the bubbles
    lettered. A recording from the start also has: *present* (False before the window appeared: nothing to show),
    *first_ms* (the page's first bubble on the stopwatch's clock, from the moment it was lettered on), *start_ms* (the
    start's own clock: from the appearance, stopped at the window's ready) and *ready* (the window said it is ready)."""

    name: str
    source_t: float
    watch_ms: float
    watch: str
    lettered: int
    present: bool = True
    first_ms: float | None = None
    start_ms: float | None = None
    ready: bool = False


def side_state(rec: Recording, index: int, u: float) -> SideState:
    """Side *rec* at *u* ms from page *index*'s turn (negative: before it): its own time, never before the page before
    was finished nor at its next turn or after (a side that waits holds its last picture before it); a recording from
    the start never before the window appeared."""
    page = rec.pages[index]
    a = page["t"]
    src = a + u
    if u < 0 and index > 0 and rec.pages[index - 1].get("stop_t") is not None:
        src = max(src, rec.pages[index - 1]["stop_t"])
    floor = rec.appeared if rec.from_start else rec.first
    present = src >= floor
    src = max(floor, min(src, page["until"] - 1.0))
    span = page_span(rec, index)
    if u < 0:
        watch, ms = "ready", 0.0
    elif page.get("page_ms") is not None and u >= span:
        watch, ms = "stopped", span
    elif page.get("page_ms") is None and u >= span:
        watch, ms = "unfinished", span
    else:
        watch, ms = "running", u
    state = SideState(rec.at(src), src, ms, watch, rec.lettered(index, src) if u >= 0 else 0)
    if rec.from_start:
        first, ready = page.get("first_t"), rec.ready_t
        state.present = present
        state.first_ms = float(first) - a if present and first is not None and u >= 0 and src >= first else None
        state.start_ms = (min(src, ready) if ready is not None else src) - rec.appeared if present else None
        state.ready = present and ready is not None and src >= ready
    return state


@dataclass
class FrameFacts:
    """What one frame of the video shows (for the drawing and the tests)."""

    index: int
    ms: float
    kind: str
    number: int = 0
    of: int = 0
    sides: list[SideState] = field(default_factory=list)
    note: str = ""
    speed: float = 1.0  # how many times faster than real time this frame's stretch is shown


class Video:
    """The video of *recs* (one or two recordings) at *fps*, at most *max_width* pixels wide: its segments (`plan`),
    its layout and its frames (`facts`, `image`)."""

    def __init__(self, recs: Sequence[Recording], opts: Options, title: str = "", end_lines: Sequence[str] = (),
                 labels: Sequence[str] | None = None, fps: float = 30.0, max_width: int = 1280):
        if not 1 <= len(recs) <= 2:
            raise SystemExit("one recording, or two side by side")
        if len(end_lines) > MAX_END_LINES:
            raise SystemExit(f"the end card holds {MAX_END_LINES} lines at most")
        self.recs, self.opts, self.fps = list(recs), opts, float(fps)
        self.title = title.replace("\\n", "\n")
        self.end_lines = [line.replace("\\n", " ") for line in end_lines]
        self.labels = list(labels) if labels else [r.label for r in recs]
        if len(self.labels) != len(recs):
            raise SystemExit("one label for each recording")
        self.mode = kind_of(self.recs)
        self.segments = plan(self.recs, opts)
        self.starts = [0.0]
        for seg in self.segments:
            self.starts.append(self.starts[-1] + seg.ms)
        self.ms = self.starts[-1]
        self.count = max(1, int(math.floor(self.ms * self.fps / 1000.0 + 1e-6)))
        self.pages = sum(1 for s in self.segments if s.kind == "page")
        # (a recording from the start whose first page, the start's, is in the video)
        self.shows_start = self.mode != "turns" and next(s.index for s in self.segments if s.kind == "page") == 0
        self.layout = Layout(self, max_width)
        self._scaled: dict[tuple[int, str], Image.Image] = {}

    def __len__(self) -> int:
        return self.count

    def segment_at(self, ms: float) -> tuple[Segment, float]:
        k = max(0, min(len(self.segments) - 1, bisect.bisect_right(self.starts, ms) - 1))
        return self.segments[k], ms - self.starts[k]

    def note(self, seg: Segment, u: float, speed: float = 1.0) -> str:
        if speed > 1.0:
            return sped_note(speed)
        two = len(self.recs) == 2
        if self.mode == "start" and seg.index == 0:
            base = NOTE_START_SIDES if two else NOTE_START
        else:
            base = NOTE_SIDES if two else NOTE_REAL
        cut = seg.cut_before if u < 0 else seg.cut_after if u >= seg.body else None
        if cut is None:
            return base
        real, shown = cut
        if len(self.recs) == 2:
            return f"{base}. Pause between pages shortened"
        return f"{base}. Pause between pages shortened from {real / 1000:.1f} s to {shown / 1000:.1f} s"

    def facts(self, i: int) -> FrameFacts:
        ms = i * 1000.0 / self.fps
        seg, local = self.segment_at(ms)
        if seg.kind != "page":
            return FrameFacts(i, ms, seg.kind)
        u, speed = seg.u_at(local), seg.factor_at(local)
        sides = [side_state(r, seg.index, u) for r in self.recs]
        return FrameFacts(i, ms, "page", seg.number, self.pages, sides, self.note(seg, u, speed), speed)

    def notes(self) -> set[str]:
        """Every caption the video's page frames can say (to lay the caption strip out once)."""
        out = {NOTE_SIDES if len(self.recs) == 2 else NOTE_REAL}
        for seg in self.segments:
            if seg.kind == "page":
                for u in (-1.0, 1.0, seg.body + 1.0):
                    out.add(self.note(seg, u))
                out.update(sped_note(factor) for _a, _b, factor in seg.speeds)
        return out

    def scaled(self, side: int, name: str) -> Image.Image:
        key = (side, name)
        picture = self._scaled.get(key)
        if picture is None:
            if len(self._scaled) > 64:
                self._scaled.clear()
            rec = self.recs[side]
            raw = rec.picture(name)
            w, h = self.layout.pictures[side]
            if rec.from_start and raw.size != rec.size:  # (the window still being laid out: at the same scale)
                k = w / rec.size[0]
                shrunk = raw.resize((max(1, round(raw.width * k)), max(1, round(raw.height * k))), Image.LANCZOS)
                picture = Image.new("RGB", (w, h), BG)
                picture.paste(shrunk.crop((0, 0, min(w, shrunk.width), min(h, shrunk.height))), (0, 0))
            else:
                picture = raw if raw.size == (w, h) else raw.resize((w, h), Image.LANCZOS)
            self._scaled[key] = picture
        return picture

    def image(self, facts: FrameFacts) -> Image.Image:
        return self.layout.draw(facts)

    def frames(self) -> Iterator[Image.Image]:
        for i in range(self.count):
            yield self.image(self.facts(i))

    def summary(self) -> dict[str, Any]:
        cuts = [s.number for s in self.segments if s.kind == "page" and s.cut_after is not None]
        out = {"seconds": round(self.ms / 1000, 2), "frames": self.count, "fps": self.fps, "pages": self.pages,
               "size": list(self.layout.size), "pauses_shortened_after_pages": cuts,
               "page_seconds": [[round(page_span(r, s.index) / 1000, 2) for r in self.recs]
                                for s in self.segments if s.kind == "page"],
               "labels": self.labels}
        if self.mode != "turns":
            out["kind"] = self.mode
            out["start"] = [start_facts(r) for r in self.recs]
            out["sped"] = [{"page": s.number, "from_s": round(a / 1000, 2), "to_s": round(b / 1000, 2), "factor": f,
                            "real_s": round((b - a) / 1000, 2), "shown_s": round((b - a) / f / 1000, 2)}
                           for s in self.segments for a, b, f in s.speeds]
        return out


# ---------------------------------------------------------------------------------------------------- the drawing
@lru_cache(maxsize=64)
def font(size: int, bold: bool = False, mono: bool = False) -> Any:
    names = (("consolab.ttf", "courbd.ttf", "DejaVuSansMono-Bold.ttf") if mono else
             ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else
             ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"))
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # (an older Pillow)
        return ImageFont.load_default()


def text_width(text: str, face: Any) -> float:
    return ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(text, font=face)


def fitting_size(texts: Sequence[str], largest: int, smallest: int, width: float) -> int:
    """The largest size from *largest* down to *smallest* at which every one of *texts* is at most *width* wide
    (*smallest* where none is: those are wrapped)."""
    size = largest
    while size > smallest and max((text_width(t, font(size)) for t in texts), default=0) > width:
        size -= 1
    return size


def wrap(text: str, face: Any, width: float) -> list[str]:
    """*text* in lines no wider than *width* (its own line breaks kept; a word longer than that alone on a line)."""
    out: list[str] = []
    for part in text.split("\n"):
        line = ""
        for word in part.split():
            trial = f"{line} {word}".strip()
            if line and text_width(trial, face) > width:
                out.append(line)
                line = word
            else:
                line = trial
        out.append(line)
    return out


def even(n: float) -> int:
    return max(2, int(round(n)) // 2 * 2)


class Layout:
    """Where everything goes: one column per recording (the window's picture, scaled to the column, under a header
    with its label, the page, the stopwatch and the bubbles), a caption strip across the bottom (the note on the
    left, the dataset's credit on the right, or each on a line of its own where they do not fit side by side)."""

    def __init__(self, video: Video, max_width: int):
        self.video = video
        n = len(video.recs)
        self.gap = 12 if n == 2 else 0
        sizes = [r.size for r in video.recs]
        column = min(min(w for w, _h in sizes), (max_width - self.gap * (n - 1)) // n)
        self.column = even(column)
        self.pictures = [(self.column, even(h * self.column / w)) for w, h in sizes]
        self.picture_h = max(h for _w, h in self.pictures)
        width = self.column * n + self.gap * (n - 1)
        self.k = max(0.75, min(1.5, self.column / 640))
        k = self.k
        self.pad = round(12 * k)
        self.label_font, self.page_font = font(round(20 * k), bold=True), font(round(17 * k))
        self.watch_font, self.bubble_font = font(round(40 * k), mono=True), font(round(19 * k))
        self.tag_font = font(round(15 * k), bold=True)
        # a recording from the start: a third row (the first bubble, the start's own clock) and the speed's badge
        self.extra = video.mode != "turns"
        self.extra_font, self.badge_font = font(round(19 * k)), font(round(38 * k), bold=True)
        self.header_h = even(self.pad * 2 + round(24 * k) + round(6 * k) + round(44 * k)
                             + (round(30 * k) if self.extra else 0))
        s = max(1.0, width / 1280)
        size = max(14, round(16 * s))  # (small, but never too small to read)
        self.credit_font = self.note_font = font(size)
        self.margin = round(12 * s)
        widest = max(text_width(note, self.note_font) for note in video.notes())
        self.credit_lines = wrap(CREDIT, self.credit_font, width - 2 * self.margin)
        self.one_line = (len(self.credit_lines) == 1
                         and widest + text_width(CREDIT, self.credit_font) + 3 * self.margin <= width)
        self.row = round(size * 1.55)
        self.caption_pad = round(size * 0.3)
        rows = 1 if self.one_line else 1 + len(self.credit_lines)
        self.caption_h = even(size * 2.1) if self.one_line else even(2 * self.caption_pad + rows * self.row)
        self.size = (even(width), even(self.header_h + self.picture_h + self.caption_h))
        self._captions: dict[str, Image.Image] = {}

    def caption(self, note: str) -> Image.Image:
        """The strip under the pictures: the note, and the dataset's credit (beside it, or under it on lines of its
        own, wrapped where the video is too narrow for it on one line)."""
        strip = self._captions.get(note)
        if strip is None:
            w, h = self.size[0], self.caption_h
            strip = Image.new("RGB", (w, h), CAPTION_BG)
            draw = ImageDraw.Draw(strip)
            if self.one_line:
                draw.text((self.margin, h / 2), note, fill=TEXT, font=self.note_font, anchor="lm")
                draw.text((w - self.margin, h / 2), CREDIT, fill=DIM, font=self.credit_font, anchor="rm")
            else:
                y = self.caption_pad + self.row / 2
                draw.text((self.margin, y), note, fill=TEXT, font=self.note_font, anchor="lm")
                for line in self.credit_lines:
                    y += self.row
                    draw.text((self.margin, y), line, fill=DIM, font=self.credit_font, anchor="lm")
            self._captions[note] = strip
        return strip

    def credit_box(self) -> tuple[int, int, int, int]:
        """Where the credit is on every frame (and nothing else is)."""
        w, h = self.size
        top = h - self.caption_h
        if self.one_line:
            return (int(w - self.margin - text_width(CREDIT, self.credit_font) - 4), top, w, h)
        return (0, top + self.caption_pad + self.row, w, h)

    def card(self, kind: str) -> Image.Image:
        w, h = self.size
        frame = Image.new("RGB", (w, h), BG)
        draw = ImageDraw.Draw(frame)
        room = h - self.caption_h
        s = max(0.7, w / 1280)
        if kind == "title":
            parts = self.video.title.split("\n", 1) if self.video.title else [""]
            big, small = font(round(52 * s), bold=True), font(round(30 * s))
            lines = [(line, big, TEXT) for line in wrap(parts[0], big, w * 0.86)]
            if len(parts) > 1:
                lines += [(line, small, DIM) for line in wrap(parts[1], small, w * 0.86)]
        else:  # (each line on one line where a smaller face, down to 24 points at this scale, holds it)
            face = font(fitting_size(self.video.end_lines, round(34 * s), max(14, round(24 * s)), w * 0.86))
            lines = [(line, face, TEXT if PROJECT not in line else GREEN) for text in self.video.end_lines
                     for line in wrap(text, face, w * 0.86)]
        heights = [round(face.size * 1.5) for _line, face, _c in lines]
        y = (room - sum(heights)) / 2
        for (line, face, colour), lh in zip(lines, heights):
            draw.text((w / 2, y + lh / 2), line, fill=colour, font=face, anchor="mm")
            y += lh
        frame.paste(self.caption(""), (0, h - self.caption_h))
        return frame

    def page_text(self, facts: FrameFacts) -> str:
        if self.extra and facts.number == 1 and self.video.shows_start:
            return {"start": "The page on show at the start",
                    "turn_at_ready": "Turned to as the window became ready"}[self.video.mode]
        return f"Page {facts.number} of {facts.of}"

    def header(self, draw: ImageDraw.ImageDraw, x: int, label: str, facts: FrameFacts, side: SideState) -> None:
        k, pad, w = self.k, self.pad, self.column
        draw.rectangle((x, 0, x + w - 1, self.header_h - 1), fill=HEADER_BG)
        top = pad + round(12 * k)
        page = self.page_text(facts)
        if label:
            draw.text((x + pad, top), label, fill=TEXT, font=self.label_font, anchor="lm")
            draw.text((x + w - pad, top), page, fill=DIM, font=self.page_font, anchor="rm")
        else:
            draw.text((x + pad, top), page, fill=DIM, font=self.page_font, anchor="lm")
        row = top + round(12 * k) + round(6 * k) + round(22 * k)
        colour = {"ready": DIM, "running": TEXT, "stopped": GREEN, "unfinished": AMBER}[side.watch]
        watch = f"{side.watch_ms / 1000:.2f} s"
        draw.text((x + pad, row), watch, fill=colour, font=self.watch_font, anchor="lm")
        tag = {"stopped": "last bubble lettered", "unfinished": "not finished"}.get(side.watch, "")
        if tag:
            tx = x + pad + text_width(watch, self.watch_font) + round(12 * k)
            draw.text((tx, row), tag, fill=colour, font=self.tag_font, anchor="lm")
        bubbles = f"Bubbles lettered: {side.lettered}"
        draw.text((x + w - pad, row), bubbles, fill=TEXT if side.watch != "ready" else DIM, font=self.bubble_font,
                  anchor="rm")
        if self.extra:  # the first bubble on the stopwatch's clock, and the start's own clock
            third = row + round(22 * k) + round(14 * k)
            first = "First bubble: -" if side.first_ms is None else f"First bubble: {side.first_ms / 1000:.2f} s"
            draw.text((x + pad, third), first, fill=GREEN if side.first_ms is not None else DIM, font=self.extra_font,
                      anchor="lm")
            if not side.present:
                start, colour = "Not started yet", DIM
            elif side.ready:
                start, colour = f"Ready after {side.start_ms / 1000:.2f} s", TEXT
            else:
                start, colour = f"Starting: {(side.start_ms or 0.0) / 1000:.2f} s", DIM
            draw.text((x + w - pad, third), start, fill=colour, font=self.extra_font, anchor="rm")

    def badge(self, draw: ImageDraw.ImageDraw, x: int, speed: float) -> None:
        """The speed on the picture while its stretch is shown faster: "x4" in a box at the picture's top left."""
        k, text = self.k, speed_text(speed)
        pad = round(10 * k)
        tw = text_width(text, self.badge_font)
        left, top = x + round(14 * k), self.header_h + round(14 * k)
        box = (left, top, left + tw + 2 * pad, top + self.badge_font.size + 2 * pad)
        draw.rounded_rectangle(box, radius=round(8 * k), fill=(20, 20, 22), outline=AMBER, width=max(2, round(3 * k)))
        draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), text, fill=AMBER, font=self.badge_font, anchor="mm")

    def draw(self, facts: FrameFacts) -> Image.Image:
        if facts.kind != "page":
            return self.card(facts.kind)
        w, h = self.size
        frame = Image.new("RGB", (w, h), BG)
        draw = ImageDraw.Draw(frame)
        for s, side in enumerate(facts.sides):
            x = s * (self.column + self.gap)
            self.header(draw, x, self.video.labels[s], facts, side)
            if side.present:  # (a window not there yet: the ground alone)
                frame.paste(self.video.scaled(s, side.name), (x, self.header_h))
            if facts.speed > 1.0:
                self.badge(draw, x, facts.speed)
        frame.paste(self.caption(facts.note), (0, h - self.caption_h))
        return frame


# ---------------------------------------------------------------------------------------------------- MP4
class VideoError(RuntimeError):
    """An MP4 that could not be made or did not read back as H.264."""


def boxes(data: bytes | bytearray, start: int, end: int) -> Iterator[tuple[str, int, int, int]]:
    """The MP4 boxes in *data* from *start* to *end*: (kind, start, payload start, end)."""
    i = start
    while i + 8 <= end:
        size, kind = struct.unpack(">I4s", bytes(data[i:i + 8]))
        head = 8
        if size == 1:
            size = struct.unpack(">Q", bytes(data[i + 8:i + 16]))[0]
            head = 16
        elif size == 0:
            size = end - i
        if size < head or i + size > end:
            raise VideoError("a broken MP4 box")
        yield kind.decode("latin-1"), i, i + head, i + size
        i += size


CONTAINERS = {"moov", "trak", "mdia", "minf", "stbl", "edts", "dinf"}


def find_box(data: bytes | bytearray, path: Sequence[str], start: int = 0, end: int | None = None
             ) -> tuple[int, int, int] | None:
    """The first box at *path* (kinds from the top): (start, payload start, end)."""
    end = len(data) if end is None else end
    for kind, at, payload, stop in boxes(data, start, end):
        if kind != path[0]:
            continue
        if len(path) == 1:
            return at, payload, stop
        found = find_box(data, path[1:], payload, stop)
        if found:
            return found
    return None


def video_trak(data: bytes) -> tuple[int, int] | None:
    """The payload of the first video track (its handler ``vide``)."""
    moov = find_box(data, ["moov"])
    if moov is None:
        return None
    for kind, _at, payload, stop in boxes(data, moov[1], moov[2]):
        if kind == "trak":
            hdlr = find_box(data, ["mdia", "hdlr"], payload, stop)
            if hdlr is not None and bytes(data[hdlr[1] + 8:hdlr[1] + 12]) == b"vide":
                return payload, stop
    return None


def mp4_facts(path: Path) -> dict[str, Any]:
    """What an MP4 file holds, read from its boxes: the video track's sample entry (``avc1`` for H.264), its profile
    and level, its size, its frames (samples) and seconds, and whether ``moov`` comes before ``mdat``."""
    data = Path(path).read_bytes()
    top = [kind for kind, *_rest in boxes(data, 0, len(data))]
    out: dict[str, Any] = {"bytes": len(data), "boxes": top,
                           "moov_first": "moov" in top and "mdat" in top and top.index("moov") < top.index("mdat")}
    trak = video_trak(data)
    if trak is None:
        out["entry"] = None
        return out
    stsd = find_box(data, ["mdia", "minf", "stbl", "stsd"], *trak)
    if stsd is not None:
        entry_at = stsd[1] + 8
        size, kind = struct.unpack(">I4s", data[entry_at:entry_at + 8])
        out["entry"] = kind.decode("latin-1")
        out["width"], out["height"] = struct.unpack(">HH", data[entry_at + 32:entry_at + 36])
        avcc = find_box(data, ["avcC"], entry_at + 8 + 78, entry_at + size)
        if avcc is not None:
            profile, _compat, level = data[avcc[1] + 1:avcc[1] + 4]
            out["profile"] = {66: "Baseline", 77: "Main", 88: "Extended", 100: "High"}.get(profile, str(profile))
            out["level"] = level / 10
    stsz = find_box(data, ["mdia", "minf", "stbl", "stsz"], *trak)
    if stsz is not None:
        out["frames"] = struct.unpack(">I", data[stsz[1] + 8:stsz[1] + 12])[0]
    mdhd = find_box(data, ["mdia", "mdhd"], *trak)
    if mdhd is not None:
        version = data[mdhd[1]]
        if version == 1:
            scale, duration = struct.unpack(">IQ", data[mdhd[1] + 20:mdhd[1] + 32])
        else:
            scale, duration = struct.unpack(">II", data[mdhd[1] + 12:mdhd[1] + 20])
        out["seconds"] = round(duration / scale, 3) if scale else None
    return out


def _shift_chunks(moov: bytearray, start: int, end: int, shift: int) -> int:
    """Every chunk offset (``stco``, ``co64``) in the boxes of *moov* from *start* to *end* moved by *shift*."""
    n = 0
    for kind, _at, payload, stop in boxes(moov, start, end):
        if kind in CONTAINERS:
            n += _shift_chunks(moov, payload, stop, shift)
        elif kind in ("stco", "co64"):
            count = struct.unpack(">I", moov[payload + 4:payload + 8])[0]
            width, code = (4, ">I") if kind == "stco" else (8, ">Q")
            for k in range(count):
                at = payload + 8 + k * width
                value = struct.unpack(code, moov[at:at + width])[0] + shift
                if kind == "stco" and value >= 1 << 32:
                    raise VideoError("a chunk offset beyond 4 GB")
                moov[at:at + width] = struct.pack(code, value)
                n += 1
    return n


def faststart(path: Path) -> bool:
    """``moov`` put before ``mdat`` (the chunk offsets moved with it), so that a player can start before the whole
    file is there; False when it was there already."""
    path = Path(path)
    data = path.read_bytes()
    top = list(boxes(data, 0, len(data)))
    kinds = [kind for kind, *_rest in top]
    if "moov" not in kinds or "mdat" not in kinds or kinds.index("moov") < kinds.index("mdat"):
        return False
    _k, moov_at, _p, moov_end = top[kinds.index("moov")]
    _k, mdat_at, _p, _e = top[kinds.index("mdat")]
    moov = bytearray(data[moov_at:moov_end])
    _shift_chunks(moov, 8, len(moov), len(moov))
    moved = data[:mdat_at] + bytes(moov) + data[mdat_at:moov_at] + data[moov_end:]
    temporary = path.with_name(path.name + ".fast")
    temporary.write_bytes(moved)
    os.replace(temporary, path)
    return True


def write_mp4(frames: Iterator[Image.Image], path: Path, size: tuple[int, int], fps: float, count: int
              ) -> dict[str, Any]:
    """The frames as an H.264 MP4 through OpenCV's Windows Media Foundation writer (software: no hardware encoder is
    asked for), then checked: the sample entry ``avc1``, *count* frames, read back by another decoder (OpenCV's
    FFmpeg) frame by frame; ``moov`` moved first. Raises `VideoError` when any of it fails (nothing is left)."""
    try:
        import cv2
    except ImportError as e:
        raise VideoError("OpenCV is not installed") from e
    path = Path(path)
    temporary = path.with_name(path.stem + ".part.mp4")
    params = [cv2.VIDEOWRITER_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_NONE]
    writer = cv2.VideoWriter(str(temporary), cv2.CAP_MSMF, cv2.VideoWriter_fourcc(*"H264"), float(fps), size, params)
    try:
        if not writer.isOpened():
            raise VideoError("Media Foundation's H.264 writer did not open")
        hardware = writer.get(cv2.VIDEOWRITER_PROP_HW_ACCELERATION)
        written = 0
        for frame in frames:
            if frame.size != size:
                raise VideoError("a frame of another size")
            writer.write(cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2BGR))
            written += 1
        writer.release()
        facts = mp4_facts(temporary)
        if facts.get("entry") not in ("avc1", "avc3"):
            raise VideoError(f"the file holds {facts.get('entry')!r}, not H.264")
        if facts.get("frames") != written or written != count:
            raise VideoError(f"{facts.get('frames')} frames in the file, {written} written, {count} meant")
        facts["moved_moov_first"] = faststart(temporary)
        facts.update(mp4_facts(temporary))
        capture = cv2.VideoCapture(str(temporary), cv2.CAP_FFMPEG)
        read = 0
        try:
            while True:
                ok, picture = capture.read()
                if not ok:
                    break
                if read == 0 and picture.shape[:2] != (size[1], size[0]):
                    raise VideoError("it reads back at another size")
                read += 1
        finally:
            capture.release()
        if read != written:
            raise VideoError(f"{read} frames read back of {written}")
        facts.update(format="mp4", codec="H.264", read_back_frames=read, hardware_acceleration=hardware,
                     writer="OpenCV Media Foundation (MSMF)")
        os.replace(temporary, path)
        return facts
    except BaseException:
        with contextlib.suppress(Exception):
            writer.release()
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise


# ---------------------------------------------------------------------------------------------------- GIF
GIF_STEPS = ((1.0, 10.0), (0.8, 10.0), (0.65, 10.0), (0.5, 10.0), (0.4, 8.0))  # (width, frames a second)


def gif_durations(count: int, fps: float) -> list[int]:
    """Each frame's time in a GIF (ms, in tens: a GIF keeps hundredths of a second) so that they add up as the
    frames' times do."""
    marks = [10 * round(i * 1000.0 / fps / 10) for i in range(count + 1)]
    return [max(10, b - a) for a, b in zip(marks, marks[1:])]


def write_gif(make: Callable[[float, float], Video], path: Path, limit: int, width: int,
              steps: Sequence[tuple[float, float]] = GIF_STEPS) -> dict[str, Any]:
    """An animated GIF of at most *limit* bytes: the video made by *make(width, fps)* at the first of *steps* whose
    GIF fits (one adaptive palette from a sample of the frames, no dither, a frame the same as the one before shown
    longer instead, optimised)."""
    path = Path(path)
    tried: list[dict[str, Any]] = []
    for scale, fps in steps:
        video = make(max(160, int(width * scale)), fps)
        sample_at = sorted({int(i) for i in np.linspace(0, len(video) - 1, min(len(video), 24))})
        sample = [video.image(video.facts(i)) for i in sample_at]
        w, h = sample[0].size
        montage = Image.new("RGB", (w // 2 * min(4, len(sample)), h // 2 * ((len(sample) + 3) // 4)))
        for k, frame in enumerate(sample):
            montage.paste(frame.resize((w // 2, h // 2), Image.BOX), ((k % 4) * (w // 2), (k // 4) * (h // 2)))
        palette = montage.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        frames: list[Image.Image] = []
        durations: list[int] = []
        last = b""
        for frame, ms in zip(video.frames(), gif_durations(len(video), fps)):
            paletted = frame.quantize(palette=palette, dither=Image.Dither.NONE)
            raw = paletted.tobytes()
            if frames and raw == last:
                durations[-1] += ms
                continue
            frames.append(paletted)
            durations.append(ms)
            last = raw
        temporary = path.with_name(path.stem + ".part.gif")
        frames[0].save(temporary, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True,
                       disposal=1)
        size = temporary.stat().st_size
        tried.append({"width": w, "fps": fps, "bytes": size})
        if size <= limit:
            os.replace(temporary, path)
            return {"format": "gif", "bytes": size, "width": w, "height": h, "fps": fps, "frames": len(video),
                    "distinct_frames": len(frames), "seconds": round(sum(durations) / 1000, 2), "limit_bytes": limit,
                    "tried": tried}
        temporary.unlink()
    raise VideoError(f"no GIF of {limit} bytes or less: {tried}")


# ---------------------------------------------------------------------------------------------------- render
def render(recs: Sequence[Recording], out: Path, opts: Options, title: str = "", end_lines: Sequence[str] = (),
           labels: Sequence[str] | None = None, fps: float = 30.0, width: int = 1280, fmt: str = "auto",
           gif_limit: int = 15 * 1024 * 1024) -> dict[str, Any]:
    """The video of *recs* into *out* (see the module's docstring); what was made."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    def make(w: float, f: float) -> Video:
        return Video(recs, opts, title, end_lines, labels, f, int(w))

    video = make(width, fps)
    report: dict[str, Any] = {"video": video.summary()}
    seconds = video.ms / 1000
    if not 20 <= seconds <= 40:
        report["length_note"] = f"{seconds:.1f} s: aimed at 20 to 40 s (--pages, --max-pause, the cards' times)"
    if fmt in ("auto", "mp4"):
        target = out.with_suffix(".mp4")
        try:
            report["result"] = write_mp4(video.frames(), target, video.layout.size, fps, len(video))
            report["result"]["path"] = str(target)
            return report
        except VideoError as e:
            report["mp4_failed"] = str(e)
            if fmt == "mp4":
                raise SystemExit(f"no MP4: {e}") from e
    target = out.with_suffix(".gif")
    report["result"] = write_gif(make, target, gif_limit, width)
    report["result"]["path"] = str(target)
    return report


# ---------------------------------------------------------------------------------------------------- made-up frames
def made_up_window(size: tuple[int, int], page: int, total: int, lettered: int, soft: bool, status: str,
                   seed: int = 1) -> Image.Image:
    """A drawn stand-in for TASlation's window (no manga page, no real window): a toolbar, a page of panels and
    bubbles (marks for text not translated, lines for text lettered), the page's number, a status line."""
    w, h = size
    s = w / 720  # (drawn for a window 720 wide, and in proportion at any other width)
    image = Image.new("RGB", size, (240, 240, 242))
    draw = ImageDraw.Draw(image)
    bar, foot = max(12, round(44 * s)), max(10, round(30 * s))
    draw.rectangle((0, 0, w, bar), fill=(226, 227, 230))
    for k in range(5):
        draw.rounded_rectangle((10 * s + 78 * s * k, bar * 0.2, 78 * s * (k + 1), bar * 0.8), radius=max(1, 5 * s),
                               fill=(206, 208, 212))
    draw.text((w - 12 * s, bar / 2), "MADE-UP FRAMES", fill=(90, 90, 96), font=font(max(8, round(15 * s)), bold=True),
              anchor="rm")
    draw.rectangle((0, bar, w, h - foot), fill=(43, 43, 43))
    room_w, room_h = w - 40 * s, h - foot - bar - 40 * s
    pw = max(20, int(min(room_w, room_h * 830 / 1170)))
    ph = max(28, int(pw * 1170 / 830))
    x0, y0 = int((w - pw) // 2), int(bar + 20 * s + (room_h - ph) // 2)
    sheet = Image.new("RGB", (pw, ph), (255, 255, 255))
    sd = ImageDraw.Draw(sheet)
    rng = np.random.default_rng(seed * 1009 + page)
    line = max(1, round(3 * s))
    cut = int(ph * rng.uniform(0.38, 0.55))
    m = max(2, round(12 * s))
    panels = ((m, m, pw - m, cut - m // 2), (m, cut + m // 2, pw // 2 - m // 2, ph - m),
              (pw // 2 + m // 2, cut + m // 2, pw - m, ph - m))
    for x1, y1, x2, y2 in panels:
        sd.rectangle((x1, y1, x2, y2), outline=(20, 20, 20), width=line)
        for _ in range(3):  # shapes of a drawing, in grey
            fx, fy = rng.uniform(0.1, 0.6), rng.uniform(0.1, 0.6)
            gw, gh = rng.uniform(0.1, 0.3), rng.uniform(0.08, 0.25)
            bx, by = x1 + fx * (x2 - x1), y1 + fy * (y2 - y1)
            sd.rectangle((bx, by, bx + gw * (x2 - x1), by + gh * (y2 - y1)), fill=(196, 196, 196))
    sd.text((pw - 18 * s, ph - 22 * s), f"p. {page}", fill=(170, 170, 170), font=font(max(8, round(26 * s)), bold=True),
            anchor="rm")
    bw, bh = pw * 0.22, ph * 0.12
    for b in range(total):
        cx = pw * 0.05 + bw / 2 + (b % 3) * (pw * 0.9 - bw) / 2 + rng.uniform(-0.02, 0.02) * pw
        cy = ph * 0.04 + bh / 2 + (b // 3) * (bh * 1.35) + rng.uniform(-0.01, 0.01) * ph
        sd.ellipse((cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), fill=(255, 255, 255), outline=(10, 10, 10),
                   width=line)
        if b < lettered:  # lines across: text lettered
            for r in range(3):
                y = cy - bh * 0.2 + r * bh * 0.2
                sd.line((cx - bw * 0.28, y, cx + bw * 0.28, y), fill=(60, 60, 60), width=max(1, round(4 * s)))
        else:  # strokes down: text not translated yet
            for c in range(3):
                x = cx - bw * 0.15 + c * bw * 0.15
                sd.line((x, cy - bh * 0.28, x, cy + bh * 0.28), fill=(10, 10, 10), width=max(1, round(5 * s)))
    if soft:
        sheet = sheet.filter(ImageFilter.GaussianBlur(max(1, 3 * s)))
    image.paste(sheet, (x0, y0))
    draw.rectangle((0, h - foot, w, h), fill=(226, 227, 230))
    draw.text((10 * s, h - foot / 2), status, fill=(40, 40, 44), font=font(max(8, round(15 * s))), anchor="lm")
    return image


def made_up(path: Path, label: str, pages: Sequence[tuple[float, int]], pauses: Sequence[float] | float = 2000.0,
            size: tuple[int, int] = (720, 900), fps: float = 15.0, seed: int = 1, start: float = 1.8e12,
            soft_ms: float = 260.0, seen_ms: float = 90.0) -> Path:
    """A recording of made-up frames (`made_up_window`), as a record would leave it: *pages* (ms from the turn to
    the last bubble, bubbles) turned one after another, each *pauses* ms after the page before finished; the window
    sees a turn *seen_ms* after it, soft until *soft_ms*, then letters the bubbles one by one from 45 % of the page's
    time to its end."""
    writer = RecordingWriter(path)
    states: list[tuple[float, dict[str, Any]]] = []
    turns, displays, results = [], [], []
    t = start
    states.append((t, {"page": 0, "total": 4, "lettered": 4, "soft": False, "status": "Translated: 4 lines"}))
    t += 1000.0
    for k, (page_ms, n) in enumerate(pages, 1):
        a = t
        turns.append({"k": k, "t": a, "screen": [k, 0], "sharp_t": a + soft_ms, "released_t": a - 60})
        states.append((a + seen_ms, {"page": k, "total": n, "lettered": 0, "soft": True,
                                     "status": "Looking at the page..."}))
        displays.append({"t": a + seen_ms, "screen": [k, 0], "kind": "live", "lettered": 0})
        states.append((a + soft_ms + seen_ms, {"page": k, "total": n, "lettered": 0, "soft": False,
                                               "status": "Translating..."}))
        displays.append({"t": a + soft_ms + seen_ms, "screen": [k, 0], "kind": "live", "lettered": 0})
        for j in range(n):
            tj = a + page_ms * (0.45 + 0.55 * (j / (n - 1) if n > 1 else 1.0))
            states.append((tj, {"page": k, "total": n, "lettered": j + 1, "soft": False,
                                "status": f"Translating... {j + 1} of {n} line(s) done"}))
            displays.append({"t": tj, "screen": [k, 0], "kind": "filling", "lettered": j + 1})
        done = a + page_ms + 35.0
        states.append((done, {"page": k, "total": n, "lettered": n, "soft": False, "status": f"Translated: {n} lines"}))
        displays.append({"t": done, "screen": [k, 0], "kind": "translated", "lettered": n})
        results.append({"t": done + 1.0, "screen": [k, 0], "bubbles": n})
        pause = pauses[k - 1] if isinstance(pauses, (list, tuple)) else float(pauses)
        t = done + 1.0 + pause
    end = results[-1]["t"] + END_HOLD_S * 1000
    times = [s[0] for s in states]
    step = 1000.0 / fps
    shot = start
    drawn: dict[tuple[Any, ...], Image.Image] = {}
    while shot <= end:
        state = states[max(0, bisect.bisect_right(times, shot) - 1)][1]
        key = (state["page"], state["total"], state["lettered"], state["soft"], state["status"])
        if key not in drawn:
            drawn.clear()
            drawn[key] = made_up_window(size, *key, seed=seed)
        writer.add(shot, drawn[key])
        shot += step
    writer.finish({"label": label, "made_up": True, "version": "made-up", "fps": fps, "picture": list(size),
                   "start_t": start, "end_t": end, "turns": turns, "displays": displays, "results": results})
    return Path(path)


def made_up_start(path: Path, label: str, mode: str, appear_ms: float = 900.0, ready_ms: float = 4800.0,
                  first_ms: float = 6000.0, page_ms: float = 9000.0, bubbles: int = 6, turn_ms: float = 120.0,
                  soft_ms: float = 260.0, size: tuple[int, int] = (720, 900), fps: float = 15.0, seed: int = 1,
                  start: float = 1.8e12) -> Path:
    """A recording from the start of made-up frames (`made_up_window`), as a record with *--from-start* (*mode*
    "start") or *--turn-at-ready* ("turn_at_ready") would leave it: the window made at *start*, pictures of one colour
    until it appears *appear_ms* later, ready *ready_ms* after its appearance; from the start, the page on show
    letters its bubbles one by one from *first_ms* to *page_ms* after the appearance; at ready, the stand-in turns
    *turn_ms* after the ready (soft for *soft_ms*) and the turned-to page letters from *first_ms* to *page_ms* after
    the turn."""
    if mode not in ("start", "turn_at_ready") or not 0 < first_ms <= page_ms:
        raise ValueError("a made-up recording from the start: from the start or at ready, the first bubble first")
    writer = RecordingWriter(path)
    step = 1000.0 / fps
    first_shot = start + 20.0
    # (the appearance is a picture's time: the first one taken from *appear_ms* on)
    appeared = first_shot + math.ceil(max(0.0, start + appear_ms - first_shot) / step - 1e-9) * step
    ready = appeared + ready_ms
    states: list[tuple[float, dict[str, Any] | None]] = [(start, None)]  # (None: the window not drawn yet)
    turns, displays, results = [], [], []
    states.append((appeared, {"page": 0, "total": 0, "lettered": 0, "soft": False, "status": "Starting..."}))
    states.append((ready, {"page": 0, "total": bubbles, "lettered": 0, "soft": False, "status": "Ready."}))
    displays.append({"t": ready, "screen": [0, 0], "kind": "live", "lettered": 0})
    if mode == "start":
        a, screen, page = appeared, [0, 0], 0
    else:
        a, screen, page = ready + turn_ms, [1, 0], 1
        turns.append({"k": 1, "t": a, "screen": screen, "sharp_t": a + soft_ms, "released_t": ready + 5.0})
        states.append((a + 60.0, {"page": 1, "total": bubbles, "lettered": 0, "soft": True, "status": "Reading..."}))
        displays.append({"t": a + 60.0, "screen": screen, "kind": "live", "lettered": 0})
        states.append((a + soft_ms + 60.0, {"page": 1, "total": bubbles, "lettered": 0, "soft": False,
                                            "status": "Translating..."}))
    for j in range(bubbles):
        tj = a + first_ms + (page_ms - first_ms) * (j / (bubbles - 1) if bubbles > 1 else 1.0)
        states.append((tj, {"page": page, "total": bubbles, "lettered": j + 1, "soft": False,
                            "status": f"Translating... {j + 1} of {bubbles} line(s) done"}))
        displays.append({"t": tj, "screen": screen, "kind": "filling", "lettered": j + 1})
    done = a + page_ms + 35.0
    states.append((done, {"page": page, "total": bubbles, "lettered": bubbles, "soft": False,
                          "status": f"Translated: {bubbles} lines"}))
    displays.append({"t": done, "screen": screen, "kind": "translated", "lettered": bubbles})
    results.append({"t": done + 1.0, "screen": screen, "bubbles": bubbles})
    end = done + END_HOLD_S * 1000
    times = [s[0] for s in states]
    blank = Image.new("RGB", size, (0, 0, 0))
    drawn: dict[tuple[Any, ...], Image.Image] = {}
    for k in range(int((end - first_shot) // step) + 1):
        shot = first_shot + k * step
        state = states[max(0, bisect.bisect_right(times, shot + 1e-6) - 1)][1]
        if state is None:
            writer.add(shot, blank)
        else:
            key = (state["page"], state["total"], state["lettered"], state["soft"], state["status"])
            if key not in drawn:
                drawn.clear()
                drawn[key] = made_up_window(size, *key, seed=seed)
            writer.add(shot, drawn[key])
    writer.finish({"label": label, "made_up": True, "version": "made-up", "fps": fps, "picture": list(size),
                   "start_t": first_shot, "end_t": end, "turns": turns, "displays": displays, "results": results,
                   "mode": mode, "launch_t": start, "constructed_t": start + 10.0, "appeared_t": appeared,
                   "ready_t": ready, "start_screen": [0, 0]})
    return Path(path)


def sample(out: Path, fmt: str = "auto") -> dict[str, Any]:
    """Made-up recordings rendered alone and side by side (and as a GIF), into *out*."""
    out = check_scratch_path(out)
    out.mkdir(parents=True, exist_ok=True)
    a = made_up(out / "made_up_a.zip", "Set-up A", [(3400, 6), (2900, 5), (4100, 8), (3000, 4), (3600, 7)],
                pauses=[2000, 2000, 4600, 2000, 2000])
    b = made_up(out / "made_up_b.zip", "Set-up B", [(2300, 6), (2000, 5), (2700, 8), (2100, 4), (2400, 7)],
                pauses=2000, seed=1)
    title = "Made-up frames\\nThe stopwatch starts at the turn and stops at the last bubble"
    end = ["Made-up frames, to check the video's layout", "Measured on: no computer (drawn)",
           "Every frame says where the pages come from", PROJECT]
    report: dict[str, Any] = {}
    recs = [Recording(a), Recording(b)]
    try:
        report["side_by_side"] = render(recs, out / "sample_side_by_side.mp4", Options(), title, end, fmt=fmt)
        report["single"] = render(recs[:1], out / "sample_single.mp4", Options(), title, end, fmt=fmt)
        report["gif"] = render(recs, out / "sample_side_by_side_gif.gif", Options(), title, end, fmt="gif")
    finally:
        for rec in recs:
            rec.close()
    for mode in ("start", "turn_at_ready"):  # recordings from the start: the stretch before the bubbles sped up
        slow = made_up_start(out / f"made_up_{mode}_a.zip", "Set-up A", mode, ready_ms=4900.0,
                             first_ms=8000.0 if mode == "start" else 7000.0, page_ms=11000.0)
        fast = made_up_start(out / f"made_up_{mode}_b.zip", "Set-up B", mode, appear_ms=1000.0, ready_ms=4700.0,
                             first_ms=6000.0 if mode == "start" else 2600.0, page_ms=8000.0 if mode == "start" else
                             6600.0)
        recs = [Recording(slow), Recording(fast)]
        try:
            report[mode] = render(recs, out / f"sample_{mode}.mp4", Options(), title, end, fmt=fmt)
        finally:
            for rec in recs:
                rec.close()
    return report


# ---------------------------------------------------------------------------------------------------- the record
def script_of(turns: int) -> str:
    """The stand-in's script: each turn waits for its release (``gK``, the control file's go), then the next screen."""
    return ",".join([f"g{k},n" for k in range(1, turns + 1)] + ["e"])


def record_mode(args: argparse.Namespace) -> str:
    """The kind of recording the command line asks for (`MODES`)."""
    if getattr(args, "turn_at_ready", False):
        return "turn_at_ready"
    return "start" if getattr(args, "from_start", False) else "turns"


def check_turns(mode: str, turns: int) -> None:
    """--turns: 1 to 40; 0 too from the start (the page on show at the start alone); at ready 1 at least (the turn)."""
    low = 0 if mode == "start" else 1
    if not low <= turns <= 40:
        raise SystemExit(f"--turns is {low} to 40" + (" with --from-start" if mode == "start" else ""))


def pages_needed(turns: int, layout: str) -> int:
    """The pages the stand-in is given: the page (or spread) the start-up translates, then one a turn."""
    return (turns + 1) * (2 if layout == "spread" else 1)


def places(areas: Sequence[tuple[tuple[int, int, int, int], bool]], viewer: tuple[int, int], app: tuple[int, int]
           ) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """(the stand-in's rect, TASlation's) as x, y, width, height: the stand-in on the primary monitor's left,
    TASlation on another monitor when there is one, else on the primary's right, side by side, neither over the
    other (a browser window wholly covered stops drawing)."""
    (left, top, right, bottom), _primary = areas[0] if areas else ((0, 0, 1920, 1040), True)
    width, height = right - left, bottom - top
    if len(areas) > 1:
        vw = min(viewer[0], width)
        (l2, t2, r2, b2), _p = areas[1]
        own = (l2 + 40, t2 + 20, min(app[0], r2 - l2 - 80), min(app[1], b2 - t2 - 90))
    else:
        vw = min(viewer[0], width // 2)
        aw = min(app[0], width - vw - 30)
        own = (right - aw - 10, top + 10, aw, min(app[1], height - 90))
    return (left, top, vw, min(viewer[1], height)), own


def loopback(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or not parsed.port:
        raise SystemExit(f"--ollama is an http address on this computer with its port (got {url!r})")
    return url.rstrip("/")


def started_url(port: int) -> str:
    """The address of the server TASlation's starter starts for *--start-ollama PORT*: a spare loopback port, never
    Ollama's default one (the server there is the person's own, never started, stopped or set up here)."""
    if not 1024 < port < 65536 or port == DEFAULT_PORT:
        raise SystemExit(f"--start-ollama is a spare port above 1024, not {DEFAULT_PORT} (got {port})")
    return f"http://127.0.0.1:{port}"


def settings_for(settings_cls: Any, asked: Sequence[str] = (), **values: Any) -> Any:
    """Settings with those of *values* the package's `Settings` has (another checkout may lack some); a setting named
    in *asked* (given on the command line) that it lacks ends the run instead."""
    import dataclasses

    names = {f.name for f in dataclasses.fields(settings_cls)}
    lacking = sorted(k for k in asked if k not in names)
    if lacking:
        raise SystemExit(f"this package's settings have no {', '.join(lacking)}")
    return settings_cls(**{k: v for k, v in values.items() if k in names})


def readers_during(records: Sequence[dict[str, Any]], start: float | None, end: float | None) -> dict[str, Any]:
    """Where the OCR readers read while the pictures were taken, from the placements noted as they changed
    (`standin_e2e.Notes.placement`: each with its time, the rule's device and why, and each reader's device): the one
    in force at *start* and those after it until *end*; *all_gpu* when each of them had every reader on the GPU."""
    if start is None:
        return {"placements": [], "all_gpu": False}
    before = [r for r in records if float(r["t"]) <= start]
    inside = [r for r in records if start < float(r["t"]) <= (end if end is not None else float("inf"))]
    held = ([before[-1]] if before else []) + inside
    seen = [{"device": r.get("device"), "why": r.get("why"), "engines": list(r.get("engines") or [])} for r in held]
    unique = [s for k, s in enumerate(seen) if s not in seen[:k]]
    ok = bool(held) and all(r.get("engines") and all(e == "cuda" for e in r["engines"]) for r in held)
    return {"placements": unique, "all_gpu": ok}


def server_summary(started: dict[str, Any] | None) -> dict[str, Any] | None:
    """What TASlation's starter chose for the server it started (`standin_e2e.stop_started`'s record), and whether it
    was stopped: the KV cache, the full-size window cache, the RAM cache and why."""
    if not started:
        return None
    setup = started.get("setup") or {}
    return {"full_window": setup.get("full_window"), "cache_ram_mib": setup.get("cache_ram"),
            "kv_cache": setup.get("kv_cache"), "why": setup.get("why"), "readers_room_mib": setup.get("rooms"),
            "stopped": started.get("stopped"), "loaded_at_close": started.get("loaded_at_close")}


class Probe:
    """What the window's page showed, as it drew it (`standin_e2e.Notes.display`: the screen by the stand-in's code,
    what it showed, the bubbles lettered), and each finished page as the window took it (its result put on the
    page: when, which screen, how many bubbles)."""

    def __init__(self, notes: Any):
        self.notes = notes
        self.results: list[dict[str, Any]] = []
        self.errors: dict[str, int] = {}
        self.chosen: set[int] = set()  # every window the app chose
        self.lock = threading.Lock()
        self.ready_t: float | None = None  # the window took its "ready" event (its handler began)
        self.on_ready: Callable[[Any], None] | None = None  # called once, right after the window's handler of it ran

    def ready(self, app: Any, before: bool) -> None:
        """The window's "ready" event: its time as the handler begins (*before*), and `on_ready` once it has run."""
        try:
            if before:
                self.ready_t = self.ready_t or now_ms()
            elif self.on_ready is not None:
                call, self.on_ready = self.on_ready, None
                call(app)
        except Exception as e:  # noqa: BLE001 - noted, never in the app's way
            self.error("ready", e)

    def error(self, where: str, e: BaseException) -> None:
        key = f"{where}: {type(e).__name__}"
        self.errors[key] = self.errors.get(key, 0) + 1

    def displayed(self, app: Any) -> None:
        try:
            self.notes.display(app)
        except Exception as e:  # noqa: BLE001 - noted, never in the app's way
            self.error("display", e)

    def result(self, app: Any, data: dict[str, Any]) -> None:
        try:
            result = data.get("result")
            if result is None or getattr(app, "last_result", None) is not result:
                return  # (held until its frame is confirmed: it comes again)
            shown = self.notes.shown(getattr(result, "original", None))
            with self.lock:
                self.results.append({"t": now_ms(), "screen": [shown.page, int(shown.spread)] if shown.screen else None,
                                     "bubbles": len(getattr(result, "translated", None) or [])})
        except Exception as e:  # noqa: BLE001
            self.error("result", e)

    def displays(self) -> list[dict[str, Any]]:
        out = []
        for d in list(self.notes.displays):
            known = d.get("state") in ("soft", "sharp", "spinner")
            out.append({"t": round(float(d["t"]), 1), "screen": [d["page"], int(bool(d["spread"]))] if known else None,
                        "state": d.get("state"), "kind": d.get("kind"), "lettered": int(d.get("lettered") or 0)})
        return out


# functions an older package's `capture.windows` has that the guard's table no longer names (0.7.0 and before: a real
# click at a screen position, and a raise with an ALT tap of its own, both input through the system): refused
# outright where they are there (the program never called them)
OLDER_GUARDED = {"click_screen": "never", "bring_to_front": "never"}


def older_guarded(windows: Any, table: dict[str, Any], target: Callable[..., Any]) -> dict[str, tuple[str, Any]]:
    """The functions of `OLDER_GUARDED` that *windows* (a package's `capture.windows`) has and *table* does not
    name, each with whom it may act on and where its window is (*target*)."""
    return {name: (allow, target) for name, allow in OLDER_GUARDED.items()
            if name not in table and callable(getattr(windows, name, None))}


def install(guard: Any, viewer_info: Callable[[], Any], hotkeys: Any, probe: Probe) -> dict[str, Any]:
    """The guard of `tools/demo_video.py` as `tools/standin_e2e.py` has it (keys and clicks refused outright; the
    global hot keys this tool's, never Windows'), the window told the viewer is in front, and the probe on the
    window's page (`App._redisplay`) and on its results (`App._handle_event`); what was replaced."""
    import demo_video

    import taslation.capture.overlay as overlay
    import taslation.capture.wgc as wgc
    import taslation.capture.windows as windows
    from taslation.ui import app as app_mod
    from taslation.ui import live, overbook

    table = {name: (("never" if allow == "viewer" else allow), target)
             for name, (allow, target) in demo_video.GUARDED.items()}  # (TASlation sends no key, no click here)
    table.update(older_guarded(windows, table, demo_video.first_arg))
    done = {"list_windows": demo_video.replace_everywhere(windows.list_windows,
                                                          lambda include_own=False: [w for w in [viewer_info()] if w])}
    for name, (allow, target) in table.items():
        original = getattr(windows, name)
        done[name] = demo_video.replace_everywhere(original, guard.wrap(name, original, allow, target))
    latest = wgc.latest

    def compositor(hwnd: int, *a: Any, **k: Any) -> Any:
        if guard.is_viewer(hwnd):
            return latest(hwnd, *a, **k)
        if guard.is_own(hwnd):
            return None  # PrintWindow: the viewer's capture session is never taken for a picture of the window
        guard.refuse("a capture session")

    wgc.latest = compositor
    overlay.HotKeys.start = classmethod(lambda cls, *a, **k: hotkeys)  # type: ignore[assignment]
    App = app_mod.App
    redisplay, handle_event, chosen = App._redisplay, App._handle_event, App._on_window_selected

    def drawn(self: Any) -> Any:
        out = redisplay(self)
        probe.displayed(self)
        return out

    def handled(self: Any, kind: str, data: dict[str, Any]) -> Any:
        if kind == "ready":
            probe.ready(self, before=True)
        out = handle_event(self, kind, data)
        if kind == "result":
            probe.result(self, data)
        elif kind == "ready":
            probe.ready(self, before=False)
        return out

    def selected(self: Any, *a: Any, **k: Any) -> Any:
        out = chosen(self, *a, **k)
        if getattr(self, "selected", None) is not None:
            probe.chosen.add(int(self.selected.hwnd))
        return out

    App._redisplay, App._handle_event, App._on_window_selected = drawn, handled, selected
    real_owner = live.foreground_owner
    live.foreground_owner = lambda hwnd, viewer, *a, **k: (real_owner(hwnd, viewer, *a, **k), "viewer")[1]
    over_owner = overbook.foreground_owner

    def over(hwnd: int, viewer: int, *a: Any, **k: Any) -> str:
        got = over_owner(hwnd, viewer, *a, **k)
        return "viewer" if got != "own" else got

    overbook.foreground_owner = over
    return done


def one_colour(image: Image.Image) -> bool:
    """Whether every pixel of *image* is of one colour (a window not drawn yet)."""
    extrema = image.getextrema()
    if extrema and isinstance(extrema[0], tuple):
        return all(lo == hi for lo, hi in extrema)
    return extrema[0] == extrema[1]


class Recorder:
    """Pictures of TASlation's own window (*hwnd*, checked to be this process's and not the stand-in's): about *fps*
    a second, from a thread of their own (*on_tk* False) or from the Tk loop, each with its time, handed to a saver
    thread that writes them into the recording (*writer*). *failed* is set once a picture is refused."""

    def __init__(self, app: Any, hwnd: int, guard: Any, writer: RecordingWriter, fps: float, on_tk: bool):
        if not guard.is_own(hwnd) or guard.is_viewer(hwnd):
            raise SystemExit("the window to picture is not TASlation's own")
        self.app, self.hwnd, self.writer, self.period, self.on_tk = app, hwnd, writer, 1.0 / fps, on_tk
        self.saving: queue.Queue[Any] = queue.Queue(maxsize=240)
        self.on = False
        self.failed = ""
        self.taken = self.missed = self.dropped = 0
        self.capture_ms: list[float] = []
        self.began = self.ended = 0.0
        self.appeared: float | None = None  # the time of the first picture not of one colour (the window drawn)
        self.saver = threading.Thread(target=self._save, name="promo-save", daemon=True)
        self.grabber: threading.Thread | None = None

    def start(self) -> None:
        self.on, self.began = True, now_ms()
        self.saver.start()
        if self.on_tk:
            self.app.after(0, self._tick)
        else:
            self.grabber = threading.Thread(target=self._loop, name="promo-grab", daemon=True)
            self.grabber.start()

    def halt(self) -> None:
        """No picture after this one (the Tk loop goes on, so that a picture under way, which may need the window's
        own thread to draw it, can end)."""
        if self.on:
            self.on = False
            self.ended = now_ms()

    def grabbing(self) -> bool:
        return self.grabber is not None and self.grabber.is_alive()

    def stop(self) -> None:
        """The pictures over and all of them saved."""
        self.halt()
        if self.grabber is not None:
            self.grabber.join(10)
        if self.saver.is_alive():
            self.saving.put(None)
            self.saver.join(120)

    def _grab(self) -> None:
        from taslation.capture import windows

        t = now_ms()
        began = time.perf_counter()
        try:
            image = windows.capture_window(self.hwnd, client_only=True, allow_screen_fallback=False)
        except Exception as e:  # noqa: BLE001 - a refused call ends the run; another picture missed is noted
            if type(e).__name__ == "Refused":
                self.failed = "a picture was refused"
                self.on = False
            self.missed += 1
            return
        self.capture_ms.append((time.perf_counter() - began) * 1000)
        self.taken += 1
        if self.appeared is None and not one_colour(image):
            self.appeared = t
        try:
            self.saving.put_nowait((t, image))
        except queue.Full:
            self.dropped += 1

    def _loop(self) -> None:
        due = time.perf_counter()
        while self.on:
            self._grab()
            due += self.period
            wait = due - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            else:
                due = time.perf_counter()

    def _tick(self) -> None:
        if not self.on:
            return
        began = time.perf_counter()
        self._grab()
        spent = time.perf_counter() - began
        self.app.after(max(GRAB_TK_MIN_MS, int((self.period - spent) * 1000)), self._tick)

    def _save(self) -> None:
        while True:
            item = self.saving.get()
            if item is None:
                return
            t, image = item
            try:
                self.writer.add(t, image)
            except Exception:  # noqa: BLE001 - said once, the run goes on
                self.failed = self.failed or "a picture could not be saved"

    def facts(self) -> dict[str, Any]:
        ms = sorted(self.capture_ms)
        seconds = max(0.001, (self.ended or now_ms()) - self.began) / 1000

        def q(p: float) -> float | None:
            return round(ms[min(len(ms) - 1, int(p * len(ms)))], 1) if ms else None

        return {"where": "tk" if self.on_tk else "thread", "taken": self.taken, "missed": self.missed,
                "dropped": self.dropped, "kept": self.writer.stored, "per_second": round(self.taken / seconds, 2),
                "capture_ms_median": q(0.5), "capture_ms_p95": q(0.95), "capture_ms_max": q(1.0),
                "failed": self.failed}


class Director:
    """The run on the Tk loop: the guard looked at every TICK_MS; the start-up's page translated and the window at
    rest, then the pictures; each turn released *--pace* s after the page before was finished; the turns' times from
    what the stand-in said."""

    def __init__(self, app: Any, browser: Any, guard: Any, selection: Any, probe: Probe, writer: RecordingWriter,
                 args: argparse.Namespace, standin_dir: Path, warm_screen: tuple[int, bool], mode: str = "turns"):
        self.app, self.browser, self.guard, self.selection = app, browser, guard, selection
        self.probe, self.writer, self.args, self.standin_dir = probe, writer, args, standin_dir
        self.warm_screen = warm_screen
        self.mode = mode  # `MODES`: from the start, the pictures from the window's first on, and no rest
        self.phase, self.phase_at = ("warm" if mode == "turns" else "start"), time.monotonic()
        self.began = time.monotonic()
        self.turns: list[dict[str, Any]] = []
        self.k = 0
        self.seen = 0
        self.lags: list[float] = []
        self.idle_since: float | None = None
        self.recorder: Recorder | None = None
        self.over = False
        self.failed = ""
        self.facts: dict[str, Any] = {}
        self.mono0, self.epoch0 = time.monotonic(), now_ms()
        self.placed_at = 0.0

    def start(self) -> None:
        if self.mode != "turns":  # the pictures from the first the window gives (its loop runs after this)
            if self.mode == "turn_at_ready":
                self.probe.on_ready = self.turn_at_ready
            self.pictures()
        self.app.after(TICK_MS, self.tick)

    def pictures(self) -> bool:
        """The pictures of TASlation's own window begin."""
        hwnd = self.app._own_hwnd() if hasattr(self.app, "_own_hwnd") else None
        if not hwnd:
            self.stop("TASlation's own window has no handle")
            return False
        self.recorder = Recorder(self.app, int(hwnd), self.guard, self.writer, self.args.fps, self.args.grab == "tk")
        self.recorder.start()
        self.say("pictures begin")
        return True

    def turn_at_ready(self, _app: Any) -> None:
        """--turn-at-ready: the first turn released as the window has taken its "ready" event."""
        if self.over or self.phase != "start" or self.k:
            return
        self.say("the window is ready: the turn is released")
        self.release()

    def tick(self) -> None:
        if self.over:
            return
        try:
            self.check()
            if not self.over:
                self.pull()
                self.step()
        except Exception as e:  # noqa: BLE001 - said by its type, and the run ends
            traceback.print_exc()
            self.stop(f"{type(e).__name__} in the driver")
        if not self.over:
            self.app.after(TICK_MS, self.tick)

    def check(self) -> None:
        why = self.selection.check(getattr(self.app, "selected", None))
        if why:
            self.stop(why)
        elif self.guard.refused:
            self.stop("a call was refused: " + ", ".join(sorted(set(self.guard.refused))))
        elif not self.browser.alive():
            self.stop("the stand-in browser ended")
        elif self.recorder is not None and self.recorder.failed:
            self.stop(self.recorder.failed)
        if time.monotonic() - self.placed_at >= PLACEMENT_EVERY_S:  # where the OCR readers read, as it changes
            self.placed_at = time.monotonic()
            self.probe.notes.placement(self.app)

    def stop(self, why: str) -> None:
        if self.over:
            return
        self.over = True
        # (the end takes seconds: where every thread is, said on standard error each END_DUMP_S it takes longer;
        # code places only, no text of a page)
        faulthandler.dump_traceback_later(END_DUMP_S, repeat=True, file=sys.stderr)
        if why != "done":
            self.failed = why
            print(f"run stopped: {why}", file=sys.stderr, flush=True)
        if self.recorder is not None:
            self.recorder.halt()
        self._quit_once_still(time.monotonic() + 10)

    def _quit_once_still(self, deadline: float) -> None:
        """The window's loop ends once no picture is under way (the Tk loop runs meanwhile: never a wait on it)."""
        if self.recorder is not None and self.recorder.grabbing() and time.monotonic() < deadline:
            self.app.after(20, lambda: self._quit_once_still(deadline))
            return
        self.app.after_idle(self.app.quit)

    def say(self, what: str) -> None:
        print(f"{time.monotonic() - self.began:7.1f} s  {what}", file=sys.stderr, flush=True)

    def go(self, phase: str, at: float | None = None) -> None:
        self.phase, self.phase_at = phase, time.monotonic() if at is None else at

    def epoch(self, mono: float) -> float:
        return self.epoch0 + (mono - self.mono0) * 1000.0

    def pull(self) -> None:
        """What the stand-in said since the last tick: the draw of each turn (its own time) and of its sharp frame."""
        for mono, said in self.browser.said(self.seen):
            self.seen += 1
            with contextlib.suppress(KeyError, ValueError):
                t = float(said["t"])
                self.lags.append(self.epoch(mono) - t)
                turn = self.turns[-1] if self.turns else None
                if said.get("ev") != "draw" or turn is None:
                    continue
                if said.get("why") == "next" and turn["t"] is None:
                    turn["t"] = t
                    turn["screen"] = [int(said.get("page", -1)), int(said.get("spread", "0") or 0)]
                elif said.get("why") == "sharp" and turn["t"] is not None and turn["sharp_t"] is None:
                    turn["sharp_t"] = t

    def idle(self) -> bool:
        app = self.app
        return bool(getattr(app, "ready", False) and not getattr(app, "busy", False)
                    and getattr(app, "_queued", None) is None)

    def result_for(self, screen: Any, after: float) -> dict[str, Any] | None:
        want = _screen(screen)
        with self.probe.lock:
            return next((r for r in self.probe.results if float(r["t"]) >= after
                         and _screen(r.get("screen")) in (want, None)), None)

    def step(self) -> None:
        now = time.monotonic()
        waited = now - self.phase_at
        args = self.args
        if self.phase == "start":  # a recording from the start: the window's start under way, the pictures taken
            warm = self.result_for(list(self.warm_screen), 0.0) if self.mode == "start" else None
            if warm is not None and getattr(self.app, "ready", False):
                self.facts["start_up_s"] = round(now - self.began, 1)
                self.facts["start_up_page_bubbles"] = warm["bubbles"]
                self.say(f"the page on show at the start translated ({warm['bubbles']} bubbles)")
                self.go("pace", now - max(0.0, now_ms() - float(warm["t"])) / 1000)
            elif waited > args.start_timeout:
                self.stop("the window did not translate the page on show at the start within --start-timeout"
                          if self.mode == "start" else "the window was not ready within --start-timeout")
        elif self.phase == "warm":
            warm = self.result_for(list(self.warm_screen), 0.0)
            if getattr(self.app, "ready", False) and warm is not None:
                self.facts["start_up_s"] = round(now - self.began, 1)
                self.facts["start_up_page_bubbles"] = warm["bubbles"]
                self.say(f"the start-up's page translated ({warm['bubbles']} bubbles)")
                self.go("rest")
            elif waited > args.start_timeout:
                self.stop("the window did not translate the start-up's page within --start-timeout")
        elif self.phase == "rest":
            self.idle_since = (self.idle_since or now) if self.idle() else None
            if self.idle_since is not None and now - self.idle_since >= REST_S:
                if self.pictures():
                    self.go("roll")
            elif waited > 60:
                self.stop("the window did not come to rest after the start-up")
        elif self.phase == "roll":
            if waited >= PREROLL_S:
                self.release()
        elif self.phase == "turning":
            turn = self.turns[-1]
            if turn["t"] is not None:
                self.go("page")
            elif waited > TURN_WAIT_S:
                self.stop("the stand-in did not turn its page")
        elif self.phase == "page":
            turn = self.turns[-1]
            result = self.result_for(turn["screen"], turn["t"])
            if result is not None:
                turn["result_seen_t"] = result["t"]
                self.say(f"page {turn['k']} finished: {result['bubbles']} bubbles, "
                         f"{(result['t'] - turn['t']) / 1000:.2f} s after the turn")
                self.go("pace", now - max(0.0, now_ms() - float(result["t"])) / 1000)
            elif waited > args.page_timeout:
                turn["timed_out"] = True
                self.say(f"page {turn['k']} not finished within --page-timeout")
                self.go("pace")
        elif self.phase == "pace":
            if waited >= args.pace:
                if self.k < args.turns:
                    self.release()
                else:
                    self.go("hold")
        elif self.phase == "hold":
            if waited >= END_HOLD_S:
                self.stop("done")

    def release(self) -> None:
        import standin_viewer as sv

        self.k += 1
        self.turns.append({"k": self.k, "t": None, "screen": None, "sharp_t": None, "released_t": round(now_ms(), 1)})
        sv.write_control(self.standin_dir, self.k)
        self.go("turning")


def record(args: argparse.Namespace) -> int:
    """The run (see the module's docstring): the recording into *args.out*, its facts printed (numbers only)."""
    out = check_scratch_path(args.out)
    if out.exists():
        raise SystemExit(f"{out} is there already: give another --out")
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.first < (3 if args.layout == "spread" else 2):
        raise SystemExit("--first is a page after the one the start-up translates (2 or more; 3 with spreads)")
    url = started_url(args.start_ollama) if args.start_ollama else loopback(args.ollama)
    package = Path(args.package).resolve() if args.package else ROOT
    if not (package / "taslation" / "__init__.py").is_file():
        raise SystemExit(f"{package} holds no taslation package")
    models = args.models or os.environ.get("TASLATION_MODELS_DIR") or ""
    if not models:
        guess = [ROOT / "models", ROOT.parent / "models", Path("C:/Temp/CleranTrans/models")]
        models = str(next((g for g in guess if g.is_dir()), ""))
    if not models or not Path(models).is_dir():
        raise SystemExit("set TASLATION_MODELS_DIR (or --models) to the folder of the installed models")

    import standin_e2e as e2e
    import standin_viewer as sv

    count = pages_needed(args.turns, args.layout)
    start_page = args.first - (2 if args.layout == "spread" else 1)
    pictures = e2e.dataset_pages(args.series, start_page, count)
    if not pictures or len(pictures) < count:
        raise SystemExit("the dataset's pages are needed (tools/fetch_openmantra.py), enough of them from --first")
    if args.start_ollama:  # the server TASlation's starter starts (as `tools/standin_e2e.py --start-ollama` does)
        if e2e.ollama_get(url, "/api/version") is not None:
            raise SystemExit(f"something answers at {url} already: --start-ollama needs a port where nothing does")
        ps_before: list[str] | None = []
    else:
        tags = e2e.ollama_get(url, "/api/tags")
        there = [str(m.get("name", "")) for m in (tags or {}).get("models", [])] if isinstance(tags, dict) else []
        if not any(name.split(":")[0] == PLAMO for name in there):
            raise SystemExit(f"the Ollama at {url} does not answer, or has no {PLAMO}: start the server set-up first")
        ps_before = e2e.loaded_models(url)
    found = sv.find_browser(args.browser)
    if found is None:
        raise SystemExit("neither Chrome nor Edge is installed here")

    scratch = Path(tempfile.mkdtemp(prefix="promo-run-", dir=out.parent))
    state, standin_dir = scratch / "state", scratch / "standin"
    state.mkdir()
    standin_dir.mkdir()
    os.environ["TASLATION_STATE_DIR"] = str(state)  # (before TASlation is imported: nothing finds ~/.taslation)
    os.environ.pop("SELFTRANS_STATE_DIR", None)
    os.environ["TASLATION_MODELS_DIR"] = models
    if args.start_ollama:  # (this process alone: the server is told its port, and leaves the model store as it is)
        os.environ["OLLAMA_HOST"] = f"127.0.0.1:{args.start_ollama}"
        os.environ["OLLAMA_NOPRUNE"] = "1"
    sys.path.insert(0, str(package))
    import taslation
    from taslation.capture import enable_dpi_awareness

    if not Path(taslation.__file__).resolve().is_relative_to(package):
        raise SystemExit(f"taslation comes from {taslation.__file__}, not from {package}")
    if args.start_ollama:
        try:
            from taslation import ollama_start
        except ImportError:
            raise SystemExit("this package has no starter of its own for Ollama: --start-ollama needs one") from None
        ollama_start.DEFAULT_PORT = args.start_ollama  # (this process alone: the port its starter starts Ollama on)
    version = str(getattr(taslation, "__version__", "?"))
    label = args.label or f"TASlation {version}"
    sv.write_page_list(standin_dir, pictures)
    sv.write_control(standin_dir, 0)
    enable_dpi_awareness()
    standin_rect, app_rect = places(e2e.Monitors().areas, args.viewer_size, args.size)
    token = "t" + secrets.token_hex(5)
    soft = args.soft
    page = sv.page_url(token, sv.parse_script(script_of(args.turns)), standin_dir, seed=args.seed, soft=soft,
                       layout=args.layout)
    writer = RecordingWriter(out)
    report: dict[str, Any] = {"label": label, "version": version, "turns": args.turns, "layout": args.layout}
    browser = sv.StandinBrowser(found[1], page, standin_dir / "profile", standin_rect, token)
    closed: dict[str, Any] = {}
    meta: dict[str, Any] | None = None
    try:
        hwnd = browser.wait_window()
        ready = browser.wait_event("ready", 30)
        since = len(browser.said())
        e2e.place_own(hwnd, standin_rect, top=True)
        ready = e2e.placed_view(browser, ready, since)
        meta = run_window(args, browser, hwnd, ready, standin_dir, url, app_rect, writer)
    except BaseException as e:  # noqa: BLE001 - said, then everything is closed
        if not isinstance(e, SystemExit):
            traceback.print_exc()
        report["failed"] = str(e) if isinstance(e, SystemExit) else f"{type(e).__name__} in the driver"
    finally:
        closed = browser.close()
        if args.start_ollama:  # what the starter chose, and the server stopped as TASlation's own end stops it
            try:
                report["server_started"] = e2e.stop_started(url, state)
            except Exception as e:  # noqa: BLE001 - said; the cleanup below still runs
                report["server_started"] = {"error": type(e).__name__}
        report["cleanup"] = cleanup(state, scratch, url, ps_before)
        report["cleanup"]["browser"] = closed
    server = server_summary(report.get("server_started"))
    report["server"] = server
    if meta is not None:
        meta["server"] = server
        meta["settings_asked"] = {"ollama_window_cache": args.ollama_window_cache, "ocr_runs_on": args.ocr_runs_on}
        report["readers"] = meta.get("readers")
    if meta is None or meta.get("failed"):
        writer.abandon()
        report["failed"] = report.get("failed") or (meta or {}).get("failed")
        print(json.dumps(report, indent=1, default=str))
        return 1
    meta.update(label=label, version=version, package=str(package), ollama=url,
                ollama_started_by_taslation=bool(args.start_ollama), fps=args.fps, pace_s=args.pace,
                layout=args.layout, soft_ms=list(soft), seed=args.seed, series=args.series, first=args.first,
                made_up=False)
    writer.finish(meta)
    rec = Recording(out)
    try:
        report["pages"] = [{k: p.get(k) for k in ("k", "first_ms", "page_ms", "result_ms", "bubbles", "finished")}
                           for p in rec.pages]
        spans = [p["page_ms"] for p in rec.pages if p.get("page_ms") is not None]
        report["page_ms_median"] = round(float(np.median(spans)), 1) if spans else None
        report["pictures"] = meta.get("pictures")
        if rec.from_start:
            report["start"] = start_facts(rec)
            report["start"]["appeared_on_first_picture"] = meta.get("appeared_on_first_picture")
            report["start"]["first_picture_after_construction_ms"] = meta.get("first_picture_after_construction_ms")
        report["recording"] = str(out)
    finally:
        rec.close()
    print(json.dumps(report, indent=1, default=str))
    return 0


def run_window(args: argparse.Namespace, browser: Any, hwnd: int, ready: dict[str, str], standin_dir: Path,
               url: str, app_rect: tuple[int, int, int, int], writer: RecordingWriter) -> dict[str, Any]:
    """TASlation's window on the stand-in (*hwnd*), driven by the `Director` until its turns are done; the
    recording's facts (the pictures went into *writer* meanwhile)."""
    import demo_video
    import standin_e2e as e2e
    import standin_viewer as sv

    from taslation import errorlog, netguard
    from taslation.capture import WindowInfo, client_rect_on_screen, program_name, window_class, window_rect
    from taslation.config import Settings
    from taslation.pagekeys import Profiles
    from taslation.ui import app as app_mod
    from taslation.ui.translator import remember_role

    # every module in place before the guard replaces what they import
    from taslation import batch, pipeline, translation_view  # noqa: F401
    from taslation.ui import jobs, live, overbook, reading, strip, trouble, viewers  # noqa: F401
    from taslation.ui.dialogs import batch as batch_dialog, caches, start, stop  # noqa: F401

    guard = demo_video.Guard(hwnd)
    if guard.is_own(hwnd) or sv.find_window(browser.tree, browser.token) != hwnd:
        raise SystemExit("the stand-in's window is not what it should be")
    _x, _y, _w, client_h = client_rect_on_screen(hwnd)
    dpr = float(ready.get("dpr", 1) or 1)
    top = client_h - round(float(ready["vh"]) * dpr)
    area = e2e.AREA
    sv.write_control(standin_dir, 0, band=round((area[1] - top) / dpr))
    selection = sv.SelectionGuard(hwnd)
    pid = next(p for w, p in sv.top_windows() if w == hwnd)

    def viewer_info() -> Any:
        if not guard.is_viewer(hwnd) or pid not in browser.tree:
            return None
        return WindowInfo(hwnd, sv.window_text(hwnd), window_class(hwnd), pid, window_rect(hwnd), program_name(pid))

    notes = e2e.Notes(top, dpr)
    hotkeys = e2e.HotKeys(notes)
    probe = Probe(notes)
    patched = install(guard, viewer_info, hotkeys, probe)
    state = demo_video.scratch_state()
    info = viewer_info()
    remember_role(state, BOOK, "reader")
    profiles = Profiles(state / "profiles.json")
    profiles.set_margins(info, area)
    profiles.set_margins(info, area, large=True)
    chosen = {k: v for k, v in (("ollama_window_cache", args.ollama_window_cache), ("ocr_runs_on", args.ocr_runs_on))
              if v is not None}
    settings = settings_for(Settings, asked=list(chosen), state_dir=state, ui_language="en", target_language="English",
                            over_book=False, flash_when_done=False, sound_when_done=False, always_on_top=False,
                            models_dir=Path(os.environ["TASLATION_MODELS_DIR"]), ollama_url=url, **chosen)
    settings.validate()
    errorlog.setup(settings)
    tap = e2e.LogTap(notes)  # (where the OCR readers went, by the log's templates: codes and numbers only)
    logging.getLogger().addHandler(tap)
    netguard.install(settings.ollama_port)  # nothing but the translator's port on this computer
    mode = record_mode(args)
    if mode != "turns":  # (pictured from its first: the window opens at its size and place, not moved there after)
        open_at(state, app_rect)
    launch_t = now_ms()  # (from the start: the launch, just before the window is made; its start begins in it)
    app = app_mod.App(settings, window_query=browser.token, book=BOOK, auto=True)
    constructed_t = now_ms()
    x, y, w, h = app_rect
    app.geometry(f"{w}x{h}+{x}+{y}")
    app.after(600, lambda: app.geometry(f"{w}x{h}+{x}+{y}"))
    warm = (0, args.layout == "spread")  # (the stand-in's screens count its own list: the start-up's page is 0)
    director = Director(app, browser, guard, selection, probe, writer, args, standin_dir, warm, mode)
    director.start()
    try:
        app.mainloop()
    finally:
        if director.recorder is not None:
            director.recorder.stop()
        if director.failed and selection.stopped:
            with contextlib.suppress(Exception):
                app.destroy()  # (another window was chosen: nothing more is done with it)
        else:
            demo_video.finish_app(app)
        logging.getLogger().removeHandler(tap)
    lags = sorted(director.lags)
    offset = lags[0] if lags else 0.0
    turns = [dict(t) for t in director.turns]
    if offset < 0:  # the browser's clock ahead of this one: its times moved back by as much (never shortening a page)
        for turn in turns:
            for key in ("t", "sharp_t"):
                if turn.get(key) is not None:
                    turn[key] = turn[key] + offset
    recorder = director.recorder.facts() if director.recorder is not None else {}
    failed = director.failed or ("" if writer.stored else "no picture was taken")
    start_t = director.recorder.began if director.recorder else None
    end_t = director.recorder.ended if director.recorder else None
    appeared_t = director.recorder.appeared if director.recorder else None
    if mode != "turns" and not failed and (appeared_t is None or probe.ready_t is None):
        failed = "the window's appearance or its ready was not seen"
    with notes.lock:
        placements = [dict(r) for r in notes.ocr]
        ocr_log = [dict(r) for r in notes.ocr_log]
    # (from the start: where the readers read once they were loaded, from the window's ready on)
    read_from = probe.ready_t if mode != "turns" and probe.ready_t is not None else start_t
    readers = {**readers_during(placements, read_from, end_t), "all_placements": [
        {**r, "t": round(float(r["t"]) - (start_t or 0.0), 1)} for r in placements],
        "log": [{**r, "t": round(float(r["t"]) - (start_t or 0.0), 1)} for r in ocr_log]}
    start: dict[str, Any] = {}
    if mode != "turns":
        start = {"mode": mode, "launch_t": round(launch_t, 1), "constructed_t": round(constructed_t, 1),
                 "appeared_t": round(appeared_t, 1) if appeared_t is not None else None,
                 "ready_t": round(probe.ready_t, 1) if probe.ready_t is not None else None,
                 "start_screen": list(warm[:1]) + [int(warm[1])],
                 # (the window drawn on its first picture already: it may have appeared a moment before it)
                 "appeared_on_first_picture": bool(writer.frames) and appeared_t == writer.frames[0][0],
                 "first_picture_after_construction_ms": round(writer.frames[0][0] - constructed_t, 1)
                 if writer.frames else None}
    return {**start, "failed": failed, "turns": turns, "displays": probe.displays(), "results": probe.results,
            "start_t": start_t, "end_t": end_t, "readers": readers,
            # (from the start: the window's size once it is laid out, its last picture's; the first may be 1 by 1)
            "picture": list((writer.last_size if mode != "turns" else writer.size) or ()) or None,
            "pictures": recorder, "start_up": director.facts,
            "clock": {"standin_lag_ms_min": round(offset, 1), "standin_lag_ms_median":
                      round(lags[len(lags) // 2], 1) if lags else None},
            "probe_errors": probe.errors,
            "guard": {"patched": patched, "refused": guard.refused, "reached_the_stand_in": guard.used,
                      "chosen": sorted(probe.chosen), "stand_in": hwnd,
                      "only_the_stand_in_chosen": probe.chosen <= {hwnd},
                      "hot_keys_held_at_the_end": sorted(hotkeys.registered)}}


def open_at(state: Path, rect: tuple[int, int, int, int]) -> bool:
    """The window opens at *rect* (x, y, width, height) from its first picture on: the size and place the window keeps
    in the scratch state for its next start (``window_place`` in ui.json, with the rectangle of its monitor), as the
    package has it; False where it has no such place (the window opens as at a first start, then is moved)."""
    try:
        from taslation.ui.layout import monitor_at
        from taslation.ui.overbook import keep_place
    except ImportError:
        return False
    x, y, w, h = rect
    monitor = monitor_at(x + 40, y + 10)
    if monitor is None:
        return False
    keep_place(state, f"{w}x{h}+{x}+{y}", False, monitor)
    return True


def cleanup(state: Path, scratch: Path, url: str, ps_before: list[str] | None) -> dict[str, Any]:
    """What the window loaded at the Ollama and left loaded let go of, the app's log in the scratch state let go of,
    the scratch folder (the state, the stand-in's files and profile) deleted."""
    import logging

    import standin_e2e as e2e

    out: dict[str, Any] = {}
    after = e2e.loaded_models(url)
    mine = [m for m in (after or []) if m.split(":")[0] == PLAMO and m not in (ps_before or [])]
    out["ollama_loaded_before"], out["ollama_loaded_after_close"] = ps_before, after
    if mine:
        out["unloaded"] = [e2e.ollama_unload(url, m) for m in mine]
        out["ollama_loaded_at_end"] = e2e.loaded_models(url)
    root = logging.getLogger()
    for handler in list(root.handlers):
        name = getattr(handler, "baseFilename", "")
        if name and Path(name).resolve().is_relative_to(state.resolve()):
            root.removeHandler(handler)
            handler.close()
    for _attempt in range(20):
        shutil.rmtree(scratch, ignore_errors=True)
        if not scratch.exists():
            break
        time.sleep(0.5)
    out["scratch_deleted"] = not scratch.exists()
    return out


# ---------------------------------------------------------------------------------------------------- the command line
def size_arg(text: str) -> tuple[int, int]:
    w, h = (int(v) for v in text.lower().split("x"))
    return w, h


def range_arg(text: str) -> tuple[int, int]:
    lo, _sep, hi = text.partition("-")
    return int(lo), int(hi or lo)


def info(paths: Sequence[Path]) -> dict[str, Any]:
    out = {}
    for path in paths:
        rec = Recording(path)
        try:
            out[str(path)] = {"label": rec.label, "version": rec.meta.get("version"),
                              "made_up": rec.meta.get("made_up"), "pictures": len(rec.frames),
                              "seconds": round((rec.end - rec.first) / 1000, 1),
                              "size": list(rec.size),
                              "pages": [{k: p.get(k) for k in ("k", "first_ms", "page_ms", "result_ms", "bubbles",
                                                               "finished")} for p in rec.pages],
                              "recorder": rec.meta.get("pictures"), "start_up": rec.meta.get("start_up"),
                              "settings_asked": rec.meta.get("settings_asked"), "server": rec.meta.get("server"),
                              "readers": {k: v for k, v in (rec.meta.get("readers") or {}).items()
                                          if k in ("placements", "all_gpu")},
                              "kind": rec.mode, "start": start_facts(rec)}
        finally:
            rec.close()
    return out


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="run the window once and keep what it showed")
    rec.add_argument("--out", type=Path, required=True, help="the recording file (a ZIP in a scratch folder)")
    rec.add_argument("--label", default="", help="the recording's name in a video (default: TASlation VERSION)")
    rec.add_argument("--ollama", default=DEFAULT_OLLAMA, help="the translator's server on this computer")
    rec.add_argument("--start-ollama", type=int, default=None, metavar="PORT",
                     help="TASlation's own starter starts Ollama on this loopback port, where nothing may answer (not "
                          "the default port; instead of --ollama), with the environment it chooses; stopped at the end")
    rec.add_argument("--ollama-window-cache", default=None, choices=("auto", "off", "on"),
                     help="the window's setting ollama_window_cache (default: the app's)")
    rec.add_argument("--ocr-runs-on", default=None, choices=("auto", "cpu", "gpu"),
                     help="the window's setting ocr_runs_on (default: the app's)")
    rec.add_argument("--package", type=Path, default=None, help="another checkout whose taslation package runs")
    rec.add_argument("--turns", type=int, default=6)
    rec.add_argument("--pace", type=float, default=2.0, help="seconds from a finished page to the next turn")
    rec.add_argument("--series", type=int, default=1, help="the dataset's series, by its place in the sorted list")
    rec.add_argument("--first", type=int, default=2, help="the first page shown (from 1; the page before it is the "
                                                          "start-up's)")
    rec.add_argument("--layout", default="single", choices=("single", "spread"))
    rec.add_argument("--soft", type=range_arg, default=(150, 400), help="the stand-in's soft time per turn, ms (A-B)")
    rec.add_argument("--seed", type=int, default=1, help="the stand-in's draws")
    rec.add_argument("--fps", type=float, default=15.0, help="pictures of the window a second")
    rec.add_argument("--grab", default="thread", choices=("thread", "tk"), help="where the pictures are taken")
    rec.add_argument("--size", type=size_arg, default=(860, 1000), help="TASlation's window, WIDTHxHEIGHT")
    rec.add_argument("--viewer-size", type=size_arg, default=(760, 1000), help="the stand-in's window")
    rec.add_argument("--browser", default="auto", choices=("auto", "chrome", "edge"))
    rec.add_argument("--models", default="", help="the models folder (default: TASLATION_MODELS_DIR)")
    rec.add_argument("--start-timeout", type=float, default=600.0, help="seconds for the start-up's page")
    rec.add_argument("--page-timeout", type=float, default=120.0, help="seconds a page may take")
    start = rec.add_mutually_exclusive_group()
    start.add_argument("--from-start", action="store_true",
                       help="record the start too: from the window's first picture, the page on show at the launch "
                            "timed from the window's appearance (--turns may be 0)")
    start.add_argument("--turn-at-ready", action="store_true",
                       help="record the start too, and release the first turn as the window says it is ready")
    ren = sub.add_parser("render", help="make the video of one recording or two side by side")
    ren.add_argument("recordings", type=Path, nargs="+")
    ren.add_argument("--out", type=Path, required=True, help="the video (.mp4; .gif where no MP4 can be made)")
    ren.add_argument("--labels", nargs="+", default=None)
    ren.add_argument("--title", default="", help="the title card's text (\\n: a new line; empty: no title card)")
    ren.add_argument("--end", action="append", default=[], help="a line of the end card (up to four)")
    ren.add_argument("--pages", type=range_arg, default=None, help="FROM-TO of the recorded turns")
    ren.add_argument("--lead", type=float, default=0.5, help="seconds before a turn shown at a page's start")
    ren.add_argument("--first-lead", type=float, default=0.0, help="... before the first page's turn")
    ren.add_argument("--max-pause", type=float, default=2.5, help="seconds a pause between pages is shown at most")
    ren.add_argument("--end-hold", type=float, default=2.0, help="seconds after the last page")
    ren.add_argument("--title-s", type=float, default=2.5)
    ren.add_argument("--end-s", type=float, default=4.5)
    ren.add_argument("--width", type=int, default=1280, help="the video's width at most")
    ren.add_argument("--fps", type=float, default=30.0)
    ren.add_argument("--format", default="auto", choices=("auto", "mp4", "gif"))
    ren.add_argument("--gif-limit-mb", type=float, default=15.0)
    ren.add_argument("--start-speed", type=float, default=4.0,
                     help="a recording from the start: its quiet stretch shown this many times faster (1: in full)")
    ren.add_argument("--start-head", type=float, default=1.0, help="... from this many seconds after the appearance")
    ren.add_argument("--real-before", type=float, default=1.5,
                     help="... to this many seconds before the first of the first bubbles (from the start) or before "
                          "the turn (at ready)")
    inf = sub.add_parser("info", help="a recording's facts, numbers only")
    inf.add_argument("recordings", type=Path, nargs="+")
    sam = sub.add_parser("sample", help="made-up recordings rendered: no window, no model, no manga")
    sam.add_argument("--out", type=Path, required=True, help="a scratch folder")
    sam.add_argument("--format", default="auto", choices=("auto", "mp4", "gif"))
    return ap.parse_args(argv)


def options_of(args: argparse.Namespace) -> Options:
    """The render's command line as `Options`."""
    if args.start_speed < 1:
        raise SystemExit("--start-speed is 1 (in full) or more")
    return Options(lead_ms=args.lead * 1000, first_lead_ms=args.first_lead * 1000, max_pause_ms=args.max_pause * 1000,
                   end_hold_ms=args.end_hold * 1000, title_ms=args.title_s * 1000 if args.title else 0.0,
                   end_ms=args.end_s * 1000 if args.end else 0.0, pages=args.pages, start_speed=args.start_speed,
                   start_head_ms=args.start_head * 1000, real_before_ms=args.real_before * 1000)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse(argv)
    if args.command == "record":
        if sys.platform != "win32":
            raise SystemExit("the record needs Windows (window capture)")
        check_turns(record_mode(args), args.turns)
        try:
            return record(args)
        finally:
            faulthandler.cancel_dump_traceback_later()
    if args.command == "info":
        print(json.dumps(info(args.recordings), indent=1, default=str))
        return 0
    if args.command == "sample":
        print(json.dumps(sample(args.out, args.format), indent=1, default=str))
        return 0
    out = check_video_path(args.out)
    for suffix in (".mp4", ".gif"):  # (either may be written)
        check_video_path(out.with_suffix(suffix))
    opts = options_of(args)
    recs = [Recording(p) for p in args.recordings]
    try:
        report = render(recs, out, opts, args.title, args.end, args.labels, args.fps, args.width, args.format,
                        int(args.gif_limit_mb * 1024 * 1024))
    finally:
        for rec in recs:
            rec.close()
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
