"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the real TASlation window checked end to end on the browser-type
stand-in viewer (`tools/standin_viewer`), with no real book and no real viewer - a developer's debugging aid, never
part of a release.

    python tools/standin_e2e.py --out SCRATCH [--scenario all | c,a,b,d,e,r,t,o,z,w,x,f,f2] [--canned] [--scale 1.0]
                                [--browser auto|chrome|edge] [--seed 1] [--series 1] [--first 1] [--synthetic]
                                [--front viewer|as-is] [--cancel-soft-ms 700]

What runs, all on this computer:

* the stand-in: `standin_viewer`'s page in a throwaway Chrome or Edge window of its own (``--app``, a scratch profile
  under *--out*, deleted at the end), drawing sample pages as a browser-based reader does - a band at the top, a dark
  ground, spreads right to left, every turn soft first and sharp a while later, black for a while now and then, a
  spinner. Its pages are the OpenMantra dataset's (``~/.taslation/datasets/openmantra``, read in place by file URL:
  the series chosen by its place in the sorted list, *--series*, never by name; no picture is copied), or with
  *--synthetic* (or no dataset) the repository's two test pages, turned and flipped. The page TURNS BY ITSELF from a
  script in its URL, released part by part through a control file in the scratch folder: no key, no click, nothing
  is sent to any window by this tool, and TASlation sends none either (its key and click functions refuse here; in
  scenario t the key the window hands to the viewer for a page key pressed on its page is noted, never sent, and
  releases the stand-in's turn);
* TASlation's window in this process (`ui.app.App`, as ``taslation gui --book NAME`` opens it: page by page, Auto
  on, the Reader role, early start and the load of the model at the start as the defaults have them), on a scratch
  state folder (TASLATION_STATE_DIR under *--out*: the legal notice dismissed as the tests do, the window in
  English; the reader's capture area 0,85,0,0 as on the owner's browser reader, its top scaled with *--scale*),
  with the real OCR models
  (TASLATION_MODELS_DIR) and the default translator through the Ollama on this computer (requests only: it is
  never started, stopped or set up here; what the window loaded it lets go of at its close, and the end checks
  /api/ps). *--canned* (or an Ollama that does not answer or lacks the model) answers from a small server of this
  tool instead ("Line N.", after a load and an answer time like the real model's), which the report says;
* the window sees one window, the stand-in's - found by the process tree this tool started AND the token in its
  title, never by another window's title, which is never read - and the guard (`demo_video.Guard`, keys and
  clicks refused outright): every function that captures, moves, raises or enlarges a window acts on the
  stand-in or this process's own windows, else the run stops; the window chosen is checked at every step
  (`standin_viewer.SelectionGuard`) and anything but the stand-in stops the run at once, nothing pressed.
  This tool never changes the foreground: the window follows a viewer in front, which is the reader's case, and with
  *--front viewer* (the default) it is told the viewer is in front whoever is (the report counts who really was) -
  over the book (scenario o) it is told so whenever its own window is not in front, and it gives the stand-in the
  foreground from its own window as that mode does. Its global hot keys are never registered with Windows: the
  window holds them in this tool's `HotKeys`, which notes their names, and a hot key "pressed" is this tool's call
  handed to the window as Windows hands one over (only for a key the window holds); no key reaches the system;
* *--scale* other than 1: the stand-in's browser draws as on a display of that scale (``--force-device-scale-factor``,
  its own window and the page's devicePixelRatio), TASlation's text size (`Settings.ui_scale`) is set to it and the
  reader's capture area scaled with it; no setting of the system's is changed.

The scenarios, in this order (each released once the window has come to rest after the one before):
  c  turns while the model still loads at the start         a  slow reading: 9 turns 6-8 s apart
  b  fast flipping: 10 turns 0.3-0.5 s apart, then a rest   d  black flashes and spinners between turns
  e  turning back to pages translated (cache hits)
  r  the full screen in the Reader role, entered and left by F11's own handler (`toggle_reading`): slow turns, a
     quick one, back
  t  the full screen in the Translator role: the toolbar's Translator, F11's own handler; at rest a region selected
     by a click on the page and the region editor opened by a double click (Tk's own pointer events on the page,
     no input of the system's) and closed by its Esc, the selection let go by Esc; then the window's next page key
     (Tk's key event on the page) turns the page - the key the window hands to the viewer releases the stand-in's
     turn (`page_key`) -, and t2 its previous page key back; the full screen left by Esc, the Reader role again
     (t brings t2, t2 brings t)
  o  over the book: the stand-in made to fill its monitor, View > Over the full-screen viewer on, the status bar's
     Move TASlation there, the Full screen button; turns as in r; the full screen left by the F11 hot key, the mode
     turned off, both windows put back
  z  TASlation's text size at 150 % of the run's (Settings), turns, back
  w  a whole-book run (as the dialog's Start starts it) on a short stretch: the run reads the screens the stand-in
     turns to, then Finished reading (the band's); w2 then turns back to pages of the run and on past them, the
     window beside the run (w brings w2, w2 brings w)
  x  a request cancelled in flight at the translator: screens of little text (the dataset's pages with one or two
     lines, by its annotation's counts) drawn soft for --cancel-soft-ms at half resolution, so that the window reads
     the soft frame and asks on it before the sharp one comes; then back (needs the dataset)
  f  the dark theme, then a narrow window (single pages)

What is recorded, numbers only (no line of the pages, read or translated, is printed, logged or written): every
frame the stand-in draws carries a code in its band (the screen, soft or sharp, spinner); the frames the window
captured, the frame each page job reads and the picture its page area is given are decoded from it, so that what
the window shows is matched to what the stand-in showed exactly, not by likeness. Per turn: from the stand-in's draw
of the sharp frame to the first request of the page job that finished the page, to the first lettered bubble and to
the finished page (spreads of the turns that came to rest, per scenario), whether the page at rest is the stand-in's
and translated, from which frame; the page jobs and the translator's requests per page, and the gate each request
went out under (a page started early asks before its frame is confirmed); the requests sent for nothing (a job on a
frame that was not the sharp one, or one dropped as its frame changed: how long each ran, how long after its job's
cancel, and when the next request went out and how long that waited at the server, against Ollama's own time for
it); the jobs on a soft frame whose frame was confirmed, those of them whose confirmation was taken back (while they
ran, after them), and the jobs on a frame that was not the sharp one with a page unit or a kept line of theirs in the
cache the window left (must be none where the sharp frame of their page came: each told with its page, how late the
window captured that sharp frame and why); the jobs cancelled, per scenario (d, the
flashes and spinners: none); overlays left on a page the stand-in had left; that no profile in the scratch state keeps
turn times; where the OCR read (the readers' placement, through every load of the model, and the System page's
facts); errors (type names and counts, also from the log); the pages in the cache at the end against those the
stand-in rested on; the window's modes as they changed (reading, over the book, a run, beside it, the text size) and
the hot keys it held; the whole-book run's decisions on the frames and the frames it read (each must be a sharp one),
how it ended and its requests; the requests of scenario x sent for nothing and what their cancel cost. Into *--out*:
report.json, and shots/ - pictures of
TASlation's OWN window only (PrintWindow of its handle, the client area; never a copy of the screen) at chosen
moments: they show the sample pages (CC BY-NC) and the model's lettering, for the developer's eyes; delete them after.
With each picture: the capture area, the part of the frame the page view draws against the page the stand-in drew
there (`page_facts`: rows of the browser's title bar and of the band drawn, the ground drawn round the page) and what
the reading makes of the frame (`reading_facts`: the page units in the area and on the whole frame, their fingerprints'
distance), numbers only.

At the end: the window closed through its own close, the canned server stopped, the browser's process tree (and
nothing else) ended, its profile and the scratch state deleted, what the window loaded in Ollama checked gone."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import http.client
import json
import logging
import math
import os
import queue
import re
import secrets
import shutil
import statistics
import sys
import tempfile
import threading
import time
import traceback
from collections import Counter
from ctypes import wintypes
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import standin_viewer as sv  # noqa: E402

REAL_STATE = Path.home() / ".taslation"
DATASET = REAL_STATE / "datasets" / "openmantra"  # read only: its pages, by file URL
FIXTURES = ROOT / "tests" / "fixtures"
BOOK = "Stand-in sample"
PLAMO = "taslation-plamo3-translate-2b"
AREA = (0, 85, 0, 0)  # the owner's capture area on the browser reader: the browser's title bar and the band
TICK_MS = 40  # the director looks this often (the Tk loop)
OCR_EVERY_S = 0.1
IDLE_S = 2.0  # the window at rest so long before the next scenario is released
REST_MS = 2000  # a screen on show sharp so long is one the reader rested on
STALE_MS = 1000  # a page lettered on show this long after the stand-in left it is an overlay left behind
LAG_MS = 1000  # ... any page of the window's this long: the window did not follow
LONG_CAPTURE_MS = 100  # a capture that took longer is noted with when it was
MODE_WAIT_S = 20.0  # a mode of a scenario not on so long after it was entered: the scenario is released all the same
STANDIN_SIZE = (1300, 900)
NARROW_SIZE = (860, 1000)
APP_SIZE = (1180, 940)
KINDS = ("translated", "result", "page_cancelled", "translate_done", "ready", "model_status", "error", "slow")


def now_ms() -> float:
    return time.time() * 1000.0


# ---------------------------------------------------------------------------------------------------- the plan
SCENARIOS: dict[str, tuple[str, list[str]]] = {
    "c": ("turns while the model loads", ["w1200", "n", "w2500-3500", "n", "w2500-3500", "n", "w8000"]),
    "a": ("slow reading", ["n", "w6000-8000"] * 9),
    "b": ("fast flipping", ["n", "w300-500"] * 10 + ["w8000"]),
    "d": ("black flashes, spinners", ["n", "w6000", "f800", "w5000", "s1500", "w5000", "n", "w300", "f700",
                                      "w6000", "s2500", "n", "w6000"]),
    "e": ("turning back", ["p", "w3000", "p", "w3000", "p", "w3000", "n", "w3000", "n", "w4000"]),
    "r": ("full screen, Reader role", ["n", "w6000", "n", "w6000", "n", "w300-500", "n", "w6000", "p", "w3000"]),
    "t": ("full screen, Translator role", ["n", "w6000"]),  # (each turn released by a page key: `Director.page_key`)
    "t2": ("its page key back", ["p", "w4000"]),
    "o": ("over the book", ["n", "w6000", "n", "w6000", "n", "w300-500", "n", "w6000"]),
    "z": ("text size", ["n", "w6000", "p", "w3000", "n", "w4000"]),
    "w": ("whole-book run", ["w1500", "n", "w2500-3000", "n", "w2500-3000", "n", "w2500-3000", "n", "w3000"]),
    "w2": ("beside the run", ["p", "w3000", "p", "w3000", "n", "w3000", "n", "w3000", "n", "w3000", "n", "w4000"]),
    "x": ("cancelled in flight", []),  # (its steps: `cancel_steps`, on the screens of little text added for it)
    "f": ("dark theme", ["n", "w6000", "n", "w6000"]),
    "f2": ("narrow window", ["n", "w6000", "n", "w6000"]),
}
ORDER = ["c", "a", "b", "d", "e", "r", "t", "t2", "o", "z", "w", "w2", "x", "f", "f2"]
PAIRS = (("f", "f2"), ("w", "w2"), ("w2", "w"), ("t", "t2"), ("t2", "t"))  # a scenario that brings another with it
KEYED = {"t": "next", "t2": "prev"}  # the scenarios whose turn a page key pressed on the window's page releases
ACTS_WAIT_S = 90.0  # scenario t: the Translator's acts begin at rest on a translated page, or after this long at most
FULL_SCREEN_SETTLE_S = 2.0  # ... and once the full screen has had this long to lay the page out at its size
# the turns whose soft frame and sharp frame drawn quickly are pictured (turns that come to a window at rest), and
# (scenario, turn) -> (seconds after the turn began, name): the other pictures of a turn
SOFT_SHOTS = {"a": (1,), "e": (3,), "r": (1,), "t": (1,), "o": (1,), "x": (1,), "f2": (1,)}
SHOTS = {("c", 2): (1.0, "c_loading"), ("a", 1): (5.2, "a_turn1_rest"), ("a", 5): (5.2, "a_turn5_rest"),
         ("b", 10): (6.0, "b_after_flipping"), ("d", 3): (5.0, "d_rest"), ("e", 1): (1.5, "e_back_cached"),
         ("r", 1): (5.2, "r_rest"), ("r", 4): (5.0, "r_after_flipping"), ("r", 5): (1.5, "r_back_cached"),
         ("t", 1): (5.2, "t_rest_after_the_key"), ("t2", 1): (1.5, "t2_back_cached"),
         ("o", 1): (5.2, "o_rest"), ("o", 4): (5.0, "o_after_flipping"), ("z", 1): (5.2, "z_rest"),
         ("w", 2): (2.0, "w_reading"), ("w2", 1): (2.0, "w2_page_of_the_run"), ("w2", 5): (2.0, "w2_page_not_read"),
         ("x", 1): (4.0, "x_rest"), ("f", 2): (5.0, "f_dark_rest"), ("f2", 1): (1.5, "f_narrow_turn1"),
         ("f2", 2): (5.0, "f_narrow_rest")}
RESIZE_SHOT_S = 3.0  # the picture of the window this long after the stand-in drew its page at a new size
TEXT_SIZE = 1.5  # scenario z: TASlation's text size, times the run's
CANCEL_SCREENS = 3  # scenario x: the screens of little text (spreads of pages with 1 to CANCEL_LINES lines of text)
CANCEL_LINES = 2
CANCEL_FACTOR = 2  # ... drawn soft this many times smaller (a soft frame the window can read)


@dataclass
class Segment:
    name: str
    go: int
    steps: list[str]
    screens: list[tuple[int, bool]] = field(default_factory=list)  # the screen after each turn, as foreseen


def wanted(text: str) -> list[str]:
    """The scenarios asked for, in `ORDER` ("f" brings the narrow window with it, "f2" alone is the narrow window
    without the dark theme; "w" and "w2" come together: `PAIRS`)."""
    if text.strip().lower() in ("", "all"):
        return list(ORDER)
    asked = {p.strip().lower() for p in text.split(",") if p.strip()}
    unknown = asked - set(SCENARIOS)
    if unknown:
        raise SystemExit(f"unknown scenario(s): {', '.join(sorted(unknown))}")
    asked |= {other for one, other in PAIRS if one in asked}
    return [n for n in ORDER if n in asked]


def cancel_steps(first: int, back: int, soft_ms: int) -> list[str]:
    """Scenario x's steps: the turns drawn soft for *soft_ms* at 1/CANCEL_FACTOR of the resolution, to the screens of
    little text from page *first* on (CANCEL_SCREENS spreads), then the stand-in's own soft time and blur again and
    back to page *back*, the screen before."""
    steps = [f"t{soft_ms}", f"b{CANCEL_FACTOR}"]
    for k in range(CANCEL_SCREENS):
        steps += [f"j{first + 2 * k}", "w5000"]
    return [*steps, "t", "b", f"j{back}", "w4000"]


def build_plan(names: list[str], count: int, cancel_first: int | None = None,
               soft_ms: int = 700) -> tuple[list[Segment], list[sv.Step]]:
    """The segments of the stand-in's script (each held at ``gN`` until the driver releases it, ``mN`` to mark it)
    and the script; the screen each turn will show, foreseen as the page turns (spreads until the narrow window).
    Scenario x turns to the screens of little text from page *cancel_first* on (`cancel_steps`)."""
    segments: list[Segment] = []
    index, spread = 0, True
    text: list[str] = []
    for go, name in enumerate(names, 1):
        steps = cancel_steps(cancel_first or 0, index, soft_ms) if name == "x" else SCENARIOS[name][1]
        segment = Segment(name, go, steps)
        if name == "f2":
            spread = False
        for step in steps:
            if step in ("n", "p") or step.startswith("j"):
                width = 2 if spread else 1
                index = int(step[1:]) if step.startswith("j") else index + (width if step == "n" else -width)
                index = max(0, min(count - 1, index))
                index = index - index % 2 if spread else index
                segment.screens.append((index, spread))
        segments.append(segment)
        text += [f"g{go}", f"m{go}", *steps]
    text.append("e")
    return segments, sv.parse_script(",".join(text))


def pages_needed(names: list[str]) -> int:
    turns = sum(SCENARIOS[n][1].count("n") * (1 if n == "f2" else 2) for n in names)
    return turns + 8


def dataset_pages(series: int, first: int, count: int) -> list[Path] | None:
    """*count* pages of the dataset in reading order: the *series*-th series of the sorted list from its page *first*
    on, then the next series. None without the dataset. (No series' name is printed or written.)"""
    images = DATASET / "images"
    if not images.is_dir():
        return None
    folders = sorted(p / "ja" for p in images.iterdir() if (p / "ja").is_dir())
    if not 1 <= series <= len(folders):
        raise SystemExit(f"--series is 1 to {len(folders)}")
    out: list[Path] = []
    for k, folder in enumerate(folders[series - 1:]):
        files = sorted(folder.glob("*.jpg"))
        out += files[(first - 1 if k == 0 else 0):]
        if len(out) >= count:
            return out[:count]
    return out or None


def text_counts(dataset: Path = DATASET) -> dict[Path, int]:
    """How many lines of text each page of the dataset holds, by its annotation (a count: no line is read out, no
    title kept); empty without it."""
    try:
        books = json.loads((dataset / "annotation.json").read_text(encoding="utf-8"))
        return {(dataset / page["image_paths"]["ja"]).resolve(): len(page.get("text") or [])
                for book in books for page in book.get("pages", [])}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def little_text_pages(taken: list[Path], count: int, dataset: Path = DATASET) -> list[Path]:
    """*count* pages of the dataset with 1 to CANCEL_LINES lines of text and none of *taken*, from its last series
    back (in reading order within a series); fewer when there are not so many."""
    counts = text_counts(dataset)
    images = dataset / "images"
    if not counts or not images.is_dir():
        return []
    used = {Path(p).resolve() for p in taken}
    out: list[Path] = []
    for folder in sorted((p / "ja" for p in images.iterdir() if (p / "ja").is_dir()), reverse=True):
        for path in sorted(folder.glob("*.jpg")):
            if path.resolve() not in used and 1 <= counts.get(path.resolve(), 0) <= CANCEL_LINES:
                out.append(path)
                if len(out) == count:
                    return out
    return out


def synthetic_pages(count: int) -> list[tuple[Path, str]]:
    """The repository's two test pages, as they are and flipped, again and again (a page seen before is the same
    page to the cache)."""
    base = [FIXTURES / "sample_page.png", FIXTURES / "sample_page2.png"]
    cycle = [(p, flip) for flip in ("", "h", "v", "hv") for p in base]
    return [cycle[k % len(cycle)] for k in range(count)]


# ---------------------------------------------------------------------------------------------------- the canned model
class Canned(ThreadingHTTPServer):
    """Ollama as the window talks to it, with one model, PLaMo's name: /api/version, /api/tags, /api/ps and
    /api/generate (a warm-up loads it after *load_s*, keep_alive 0 lets it go, a prompt is answered "Line N." after
    *answer_ms*, streamed as Ollama streams). The prompt is never kept."""

    daemon_threads = True

    def __init__(self, load_s: float, answer_ms: int) -> None:
        super().__init__(("127.0.0.1", 0), _CannedHandler)
        self.load_s, self.answer_ms = load_s, answer_ms
        self.loaded = False
        self.lines = 0
        self.counts: Counter[str] = Counter()
        self.lock = threading.Lock()
        self.port = self.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=lambda: self.serve_forever(poll_interval=0.05), daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.shutdown()
        self.server_close()


class _CannedHandler(BaseHTTPRequestHandler):
    server: Canned

    def log_message(self, *args: Any) -> None:
        pass

    def _json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        s = self.server
        s.counts[self.path] += 1
        if self.path == "/api/version":
            self._json({"version": "0.0-canned"})
        elif self.path == "/api/tags":
            self._json({"models": [{"name": PLAMO + ":latest", "model": PLAMO + ":latest", "size": 1_900_000_000}]})
        elif self.path == "/api/ps":
            size = 1_900_000_000
            self._json({"models": [{"name": PLAMO + ":latest", "model": PLAMO + ":latest", "size": size,
                                    "size_vram": size}] if s.loaded else []})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        s = self.server
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        s.counts[self.path] += 1
        prompt = bool(payload.get("prompt") or payload.get("messages"))
        payload.pop("prompt", None)
        payload.pop("messages", None)
        if not prompt and payload.get("keep_alive") == 0:
            s.loaded = False
            self._json({"model": payload.get("model"), "response": "", "done": True, "done_reason": "unload"})
            return
        if not s.loaded:
            time.sleep(s.load_s)
            s.loaded = True
        if not prompt:
            self._json({"model": payload.get("model"), "response": "", "done": True, "done_reason": "load"})
            return
        time.sleep(s.answer_ms / 1000.0)
        with s.lock:
            s.lines += 1
            text = f"Line {s.lines}."
        if self.path == "/api/chat":
            self._json({"message": {"role": "assistant", "content": text}, "done": True, "done_reason": "stop"})
            return
        if not payload.get("stream"):
            self._json({"response": text, "done": True, "done_reason": "stop", "eval_count": 4})
            return
        self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def line(obj: Any) -> None:
            data = (json.dumps(obj) + "\n").encode("utf-8")
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
            self.wfile.flush()

        try:
            for k in range(0, len(text), 4):
                line({"response": text[k:k + 4], "done": False})
            line({"response": "", "done": True, "done_reason": "stop", "eval_count": 4})
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except OSError:
            pass
        self.close_connection = True


def ollama_get(url: str, path: str, timeout: float = 3.0) -> Any:
    """GET *path* of the Ollama at *url* (a loopback address): its JSON, None when it does not answer."""
    host, _, port = url.split("//", 1)[1].partition(":")
    conn = http.client.HTTPConnection(host, int(port or 80), timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return json.loads(resp.read().decode("utf-8")) if resp.status == 200 else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def ollama_unload(url: str, model: str) -> bool:
    host, _, port = url.split("//", 1)[1].partition(":")
    conn = http.client.HTTPConnection(host, int(port or 80), timeout=15)
    try:
        conn.request("POST", "/api/generate", body=json.dumps({"model": model, "keep_alive": 0, "stream": False}),
                     headers={"Content-Type": "application/json"})
        return conn.getresponse().status == 200
    except (OSError, http.client.HTTPException):
        return False
    finally:
        conn.close()


def loaded_models(url: str) -> list[str] | None:
    data = ollama_get(url, "/api/ps")
    if not isinstance(data, dict):
        return None
    return sorted(str(m.get("name") or m.get("model") or "") for m in data.get("models") or [])


# ---------------------------------------------------------------------------------------------------- the screens
class Monitors:
    """The monitors' work areas, the primary first (no window is looked at)."""

    def __init__(self) -> None:
        self.areas: list[tuple[tuple[int, int, int, int], bool]] = []
        user32 = ctypes.windll.user32

        class Info(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                            wintypes.LPARAM)
        def each(handle, _dc, _rect, _lparam):  # type: ignore[no-untyped-def]
            info = Info()
            info.cbSize = ctypes.sizeof(Info)
            if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
                w = info.rcWork
                self.areas.append(((w.left, w.top, w.right, w.bottom), bool(info.dwFlags & 1)))
            return True

        user32.EnumDisplayMonitors(0, 0, each, 0)
        self.areas.sort(key=lambda a: not a[1])

    def places(self) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
        """(the stand-in's rect, TASlation's) as x, y, width, height: the stand-in on the primary monitor, TASlation
        on another one when there is one, else on the primary's right."""
        (left, top, right, bottom), _primary = self.areas[0] if self.areas else ((0, 0, 1920, 1040), True)
        standin = (left, top, min(STANDIN_SIZE[0], right - left), min(STANDIN_SIZE[1], bottom - top))
        if len(self.areas) > 1:
            (l2, t2, r2, b2), _p = self.areas[1]
            app = (l2 + 60, t2 + 40, min(APP_SIZE[0], r2 - l2 - 80), min(APP_SIZE[1], b2 - t2 - 80))
        else:
            width = min(APP_SIZE[0], (right - left) // 2)
            app = (right - width - 10, top + 10, width, min(APP_SIZE[1], bottom - top - 60))
        return standin, app


def place_own(hwnd: int, rect: tuple[int, int, int, int], top: bool = False) -> None:
    """The stand-in's window (this tool's own) to *rect*; *top*: above the others without taking the foreground."""
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT]
    flags = 0x0010 | (0 if top else 0x0004)  # SWP_NOACTIVATE, SWP_NOZORDER
    x, y, w, h = rect
    if top:
        user32.SetWindowPos(hwnd, wintypes.HWND(-1), x, y, w, h, flags)  # HWND_TOPMOST ...
        user32.SetWindowPos(hwnd, wintypes.HWND(-2), x, y, w, h, flags)  # ... then HWND_NOTOPMOST: on top, as any
    else:
        user32.SetWindowPos(hwnd, 0, x, y, w, h, flags)


def placed_view(browser: Any, ready: dict[str, str], since: int, seconds: float = 3.0, quiet: float = 0.5
                ) -> dict[str, str]:
    """The stand-in's view once its window is in place: *ready* with the size it said last after *since* (a browser
    drawing at another scale takes the size it starts at in its own scaled pixels, so its window starts at another
    size than the place it is given), once no other size has come for *quiet* seconds (*seconds* at most)."""
    view, seen, calm = dict(ready), since, time.monotonic()
    end = calm + seconds
    while time.monotonic() < end and time.monotonic() - calm < quiet:
        said = browser.said(seen)
        seen += len(said)
        for _t, event in said:
            if event.get("ev") == "size":
                view.update({k: v for k, v in event.items() if k != "ev"})
                calm = time.monotonic()
        time.sleep(0.05)
    return view


# ---------------------------------------------------------------------------------------------------- the notes
class Notes:
    """What the hooks see, as numbers and codes (`standin_viewer.Shown` of every picture): the page jobs, the
    translator's requests, the pictures the page area was given, the frames captured, the loads of the model, the OCR
    readers' place, who was in front, the errors. Written from the Tk thread, the worker and the pipeline's threads."""

    def __init__(self, top: int, dpr: float):
        self.top, self.dpr = top, dpr
        self.lock = threading.RLock()
        self.jobs: list[dict[str, Any]] = []
        self.by_image: dict[int, dict[str, Any]] = {}
        self.current: dict[str, Any] | None = None
        self.tags: dict[int, tuple[dict[str, Any] | None, float]] = {}
        self.requests: list[dict[str, Any]] = []
        self.warmups: list[dict[str, Any]] = []
        self.app_events: list[dict[str, Any]] = []
        self.displays: list[dict[str, Any]] = []
        self.captures: list[dict[str, Any]] = []
        self.capture_counts: Counter[str] = Counter()
        self.loads: list[list[float]] = []
        self.load_depth = 0
        self.ocr: list[dict[str, Any]] = []
        self.ocr_log: list[dict[str, Any]] = []
        self.owners: Counter[str] = Counter()
        self.errors: Counter[str] = Counter()
        self.selected: list[int] = []
        self.cancels: list[float] = []  # when a running page job's cancel was set by the live view (a turn, a drop)
        self.local = threading.local()  # (the request a translator thread is in: `request`, `http_begin`, `http_end`)
        self.timings: dict[str, list[tuple[float, bool]]] = {}  # the Tk thread's time in the live view's calls
        self.tk_cpu: list[tuple[float, float, bool]] = []  # (monotonic, the Tk thread's CPU time, a job running)
        self.status_lines: list[dict[str, Any]] = []  # the status line's kind and the page it speaks of, from when
        self.long_captures: list[tuple[float, float]] = []  # (when, ms): the captures that took over LONG_CAPTURE_MS
        self.margins: list[dict[str, Any]] = []  # the capture area in force and the frame's own, as they changed
        self.modes: list[dict[str, Any]] = []  # reading, over the book, a run, beside it, text size, as changed
        self.hotkeys: list[dict[str, Any]] = []  # the hot keys the window held, as they changed, and the presses
        self.run_frames: list[dict[str, Any]] = []  # a whole-book run's decisions on the viewer's frames, and ...
        self.run_reads: list[dict[str, Any]] = []  # ... the frames it got from its store to read
        self.run_ends: list[dict[str, Any]] = []
        self.lookups: list[dict[str, Any]] = []  # each page unit a page job looked for in the cache, and what it found
        self.resolves: list[dict[str, Any]] = []  # ... and each look for the page as read at other sizes
        self.decides: list[dict[str, Any]] = []  # each page job kept for now, decided (`Pipeline.decide_kept`): how
        self.on_display: Callable[[dict[str, Any]], None] | None = None
        self.leaves: list[dict[str, Any]] = []  # each leave of the full screen: when, and the calls that led to it

    def timed(self, name: str, ms: float, busy: bool) -> None:
        with self.lock:
            self.timings.setdefault(name, []).append((ms, busy))

    def shown(self, image: Any) -> sv.Shown:
        try:
            return sv.decode(image, self.top, self.dpr) if image is not None else sv.Shown()
        except Exception:  # noqa: BLE001 - a picture of another shape: not known
            return sv.Shown()

    @staticmethod
    def code(shown: sv.Shown) -> dict[str, Any]:
        return {"page": shown.page, "spread": shown.spread, "state": shown.state()}

    def error(self, where: str, kind: str) -> None:
        with self.lock:
            self.errors[f"{where}: {kind}"] += 1

    # the page jobs
    def new_job(self, image: Any) -> dict[str, Any]:
        job = {"id": len(self.jobs) + 1, "t": now_ms(), **self.code(self.shown(image)),
               "size": list(image.size) if image is not None else None, "started": False,
               "gate": False, "requests": 0, "translated": 0, "first_translated_t": None,
               "result_t": None, "result_translated": None, "result_from": None, "cancelled_t": None,
               "discarded": None, "done_t": None, "gate_end": None, "over_t": None, "open_for": None,
               "open_until_t": None, "units": [], "line_ids": []}
        with self.lock:
            self.jobs.append(job)
            self.by_image[id(image)] = job
        return job

    def job_started(self, job: dict[str, Any], image: Any, started: bool, gate: Any) -> None:
        with self.lock:
            job["started"], job["gate"] = started, gate is not None
            if not started:
                self.by_image.pop(id(image), None)

    def take_job(self, image: Any, gate: Any) -> dict[str, Any] | None:
        with self.lock:
            job = self.by_image.pop(id(image), None)
            if job is not None:
                job["_gate"] = gate
                job["work_t"] = now_ms()
            self.current = job
            return job

    def job_over(self, job: dict[str, Any] | None) -> None:
        """The job's end: its gate's state then (``gate_end``), and the gate kept for the end of the run, when the
        window may have taken its confirmation back since (`gates_at_end`), with the end of its open time
        (`PageGate.open_until`) on this tool's clock."""
        with self.lock:
            if job is not None:
                gate = job.pop("_gate", None)
                job["gate_end"] = getattr(gate, "state", None)
                job["over_t"] = now_ms()
                if gate is not None:
                    job["gate_obj"] = gate
                    job["open_for"] = getattr(gate, "open_for", None)
                    until = getattr(gate, "open_until", None)
                    if until is not None and math.isfinite(until):
                        job["open_until_t"] = job["over_t"] + (until - time.monotonic()) * 1000
            self.current = None

    def gates_at_end(self) -> None:
        """(the window closed) Each job's gate as the run left it: its state (``gate_final``: "dropped" after a
        confirmation is one taken back, `PageGate.take_back`) and whether it was ever confirmed (``confirmed_ever``:
        its open time set, `PageGate.confirm`)."""
        with self.lock:
            for job in self.jobs:
                gate = job.pop("gate_obj", None) or job.pop("_gate", None)
                if gate is None:
                    continue
                until = getattr(gate, "open_until", None)
                job["gate_final"] = getattr(gate, "state", None)
                job["confirmed_ever"] = (math.isfinite(until) if until is not None
                                         else job["gate_end"] == "confirmed")

    def line_put(self, line: str) -> None:
        """A kept line the job running put first (`linememo.LineMemo.put`), by `line_id`."""
        with self.lock:
            if self.current is not None:
                self.current["line_ids"].append(line)

    def decided(self, gate: Any, kept: bool | None) -> None:
        """The page job kept for now whose gate is *gate* decided (`Pipeline.decide_kept`): *kept* for good (True) or
        put back (False), and by the job that runs then (None: between jobs, or the window's close)."""
        with self.lock:
            job = next((j for j in reversed(self.jobs) if gate is not None
                        and (j.get("gate_obj") is gate or j.get("_gate") is gate)), None)
            self.decides.append({"t": now_ms(), "job": job["id"] if job else None, "kept": kept,
                                 "by": self.current["id"] if self.current else None})

    def tag(self, item: Any) -> None:
        if isinstance(item, tuple) and len(item) == 2 and item[0] in KINDS and isinstance(item[1], dict):
            with self.lock:
                self.tags[id(item[1])] = (self.current, now_ms())

    def app_event(self, app: Any, kind: str, data: dict[str, Any]) -> None:
        t = now_ms()
        with self.lock:
            job, posted = self.tags.pop(id(data), (None, t))
            self.app_events.append({"kind": kind, "t": t, "posted": posted, "job": job["id"] if job else None})
            if job is None:
                return
            if kind == "translated":
                job["translated"] += 1
                job["first_translated_t"] = job["first_translated_t"] or t
            elif kind == "result":
                result = data.get("result")
                job["result_t"] = t
                job["result_translated"] = len(getattr(result, "translated", []) or [])
                job["result_from"] = self.code(self.shown(getattr(result, "original", None)))["state"]
                job["result_boxes"] = [[int(v) for v in r.bbox] for r in getattr(result, "translated", []) or []]
                job["cache_hits"] = getattr(result, "cache_hits", None)
                job["cache_misses"] = getattr(result, "cache_misses", None)
                job["stored"] = len(data.get("stored") or ())
            elif kind == "page_cancelled":
                job["cancelled_t"] = t
                job["discarded"] = bool(data.get("discarded"))
                job["stored_at_cancel"] = len(data.get("stored") or ())
            if kind in ("result", "page_cancelled"):  # the page units it said it stored anew, for the end's look
                job["units"] += [fp for fp, _aspect in data.get("stored") or () if fp not in job["units"]]
            elif kind == "translate_done":
                job["done_t"] = t

    # the translator
    def request(self, kind: str) -> dict[str, Any]:
        """A request to the translator begins (a line, or lines joined): noted with its job and its gate's state;
        `request_over` notes its end."""
        t = now_ms()
        with self.lock:
            job = self.current
            gate = job.get("_gate") if job else None
            state = getattr(gate, "state", "none") if gate is not None else "none"
            rec = {"t": t, "kind": kind, "job": job["id"] if job else None, "gate": state,
                   "frame": job["state"] if job else None, "end_t": None,
                   "outcome": None, "http_t": None, "http_end_t": None, "server_ms": None, "load_ms": None}
            self.requests.append(rec)
            if job is not None:
                job["requests"] += 1
        return rec

    def request_over(self, rec: dict[str, Any], outcome: str) -> None:
        with self.lock:
            rec["end_t"], rec["outcome"] = now_ms(), outcome

    def cancelled(self, t: float) -> None:
        with self.lock:
            self.cancels.append(t)

    def warmup(self, kind: str) -> None:
        with self.lock:
            job = self.current
            gate = job.get("_gate") if job else None
            self.warmups.append({"t": now_ms(), "kind": kind, "job": job["id"] if job else None,
                                 "gate": getattr(gate, "state", "none") if gate is not None else "none"})

    def load_begin(self) -> None:
        with self.lock:
            self.load_depth += 1
            if self.load_depth == 1:
                self.loads.append([now_ms(), 0.0])

    def load_end(self) -> None:
        with self.lock:
            self.load_depth = max(0, self.load_depth - 1)
            if self.load_depth == 0 and self.loads:
                self.loads[-1][1] = now_ms()

    # what the window shows and captures
    def display(self, app: Any) -> None:
        canvas = getattr(app, "canvas", None)
        image = getattr(canvas, "_image", None)
        if image is None:
            return
        fill, result, live = getattr(app, "_fill", None), getattr(app, "last_result", None), getattr(app, "_live", None)
        if fill is not None and (image is fill.page or image is fill.final):
            kind, lettered, source = ("final" if image is fill.final else "filling"), fill.filled, fill.frame
        elif fill is not None and (image is fill.frame or image is getattr(fill, "base", None)):
            kind, lettered, source = "reading", 0, fill.frame
        elif result is not None and image is not live:
            kind, lettered, source = "translated", len(result.translated), result.original
        else:
            kind, lettered, source = "live", 0, live
        shown = self.shown(image)
        rec = {"t": now_ms(), **self.code(shown), "kind": kind, "lettered": lettered,
               "from": self.code(self.shown(source))["state"] if source is not None else None,
               "quick": getattr(canvas, "_fit_key", 0) is None}
        with self.lock:
            last = self.displays[-1] if self.displays else None
            same = last is not None and all(last[k] == rec[k] for k in ("page", "spread", "state", "kind", "lettered",
                                                                         "from", "quick"))
            if not same:
                self.displays.append(rec)
        if not same and self.on_display is not None:
            self.on_display(rec)

    def status_line(self, app: Any, t: float) -> None:
        """The status line set at *t*, as `status_kind` tells it (its kind, never its text), with the page it speaks of
        as the stand-in's code (None: a line of no page, or a picture without the code)."""
        kind, about, result = status_kind(getattr(app, "_status_render", None), getattr(app, "_status_key", None))
        picture = {"result": getattr(result, "original", None), "job": getattr(app, "_job_frame", None),
                   "viewer": getattr(app, "_live", None)}.get(about or "")
        shown = self.shown(picture) if picture is not None else sv.Shown()
        rec = {"t": t, "kind": kind, "about": about, "page": list(shown.screen) if shown.screen else None}
        with self.lock:
            last = self.status_lines[-1] if self.status_lines else None
            if last is None or any(last[k] != rec[k] for k in ("kind", "about", "page")):
                self.status_lines.append(rec)

    def area(self, app: Any) -> None:
        """The capture area in force, the one the window reads the frame on show by (`_margins_of` where the window has
        it, else the area in force) and the frame's own (what the window applies once no job runs), with the frame's
        size: noted as they change."""
        live = getattr(app, "_live", None)
        try:
            margins = [int(m) for m in app.settings.margins]
            own = [int(m) for m in (app._inner_margins() if app._manual_area else app._found_margins())]
            read = ([int(m) for m in app._margins_of(live)] if live is not None and hasattr(app, "_margins_of")
                    else margins)
        except Exception as e:  # noqa: BLE001 - said by its type
            self.error("area sample", type(e).__name__)
            return
        rec = {"t": now_ms(), "size": list(live.size) if live is not None else None, "margins": margins, "own": own,
               "read": read, "busy": bool(getattr(app, "busy", False))}
        with self.lock:
            last = self.margins[-1] if self.margins else None
            if last is None or any(last[k] != rec[k] for k in ("size", "margins", "own", "read", "busy")):
                self.margins.append(rec)

    def mode(self, app: Any) -> None:
        """The window's modes, noted as they change: the full screen, over the book, a whole-book run on, the window
        beside it (`live.reads_beside`), TASlation's text size, the role."""
        from taslation.ui.constants import in_a_run
        from taslation.ui.live import reads_beside

        rec = {"t": now_ms(), "reading": bool(getattr(app, "reading", False)),
               "over": bool(getattr(app, "_over_on", False)), "run": in_a_run(app), "beside": reads_beside(app),
               "text_size": float(app.settings.ui_scale), "role": str(app.role_var.get())}
        with self.lock:
            last = self.modes[-1] if self.modes else None
            if last is None or any(last[k] != rec[k] for k in rec if k != "t"):
                self.modes.append(rec)

    def held(self, names: frozenset[str]) -> None:
        with self.lock:
            self.hotkeys.append({"t": now_ms(), "held": sorted(names)})

    def pressed(self, name: str, taken: bool) -> None:
        with self.lock:
            self.hotkeys.append({"t": now_ms(), "pressed": name, "taken": taken})

    def lookup(self, pipeline: Any, unit: Any, hit: Any, read: tuple[Any, Any] | None) -> None:
        """A page unit a page job looked for in the cache (`Pipeline._lookup`), in numbers: the frame's size and the
        capture area it was fingerprinted by (`Pipeline.units_of`), the unit's box and aspect, the distance of the page
        found (None: a miss), and the nearest page the cache holds whatever its aspect, with its aspect."""
        from taslation.fingerprint import hamming

        size, margins = read if read is not None else (None, None)
        nearest, aspect = None, None
        for page in list(getattr(pipeline.cache, "pages", None) or ()):
            d = hamming(unit.fingerprint, page.fingerprint)
            if nearest is None or d < nearest:
                nearest, aspect = d, round(float(page.aspect or 0), 3)
        rec = {"t": now_ms(), "size": list(size) if size else None, "margins": list(margins) if margins else None,
               "box": [int(v) for v in unit.box], "aspect": round(float(unit.aspect), 3),
               "hit": hit[1] if hit is not None else None, "nearest": nearest, "nearest_aspect": aspect}
        with self.lock:
            rec["job"] = self.current["id"] if self.current else None
            self.lookups.append(rec)

    def resolved(self, ms: float, readings: int | None, replaced: int) -> None:
        """A page job's look for the page units the cache did not hold as found (`Pipeline._resolve`): its time, the
        readings it went through (None: it needed none) and the units one of them found."""
        with self.lock:
            self.resolves.append({"t": now_ms(), "job": self.current["id"] if self.current else None,
                                  "ms": round(ms, 1), "readings": readings, "replaced": replaced})

    def run_frame(self, kind: Any, image: Any) -> None:
        with self.lock:
            self.run_frames.append({"t": now_ms(), "kind": str(kind), **self.code(self.shown(image))})

    def run_read(self, key: Any, image: Any) -> None:
        with self.lock:
            self.run_reads.append({"t": now_ms(), "key": key, **self.code(self.shown(image))})

    def run_end(self, progress: Any) -> None:
        ended = getattr(progress, "summary", None) or getattr(progress, "reason", None)
        with self.lock:
            self.run_ends.append({"t": now_ms(), "code": str(getattr(ended, "code", type(ended).__name__)),
                                  "pages": getattr(progress, "pages", None)})

    def captured(self, image: Any) -> None:
        shown = self.shown(image)
        rec = {"t": now_ms(), **self.code(shown), "size": list(getattr(image, "size", (0, 0)))}
        with self.lock:
            self.capture_counts[rec["state"]] += 1
            last = self.captures[-1] if self.captures else None
            if last is None or any(last[k] != rec[k] for k in ("page", "spread", "state", "size")):
                self.captures.append(rec)

    def placement(self, app: Any) -> None:
        ocr = getattr(getattr(app, "pipeline", None), "ocr", None)
        if ocr is None:
            return
        placement = getattr(ocr, "placement", None)
        try:
            engines = tuple(str(getattr(e, "device", "?")) for e in ocr._movable())
        except Exception:  # noqa: BLE001 - a reader of another kind
            engines = ()
        rec = {"t": now_ms(), "device": getattr(placement, "device", None), "why": getattr(placement, "why", None),
               "engines": list(engines), "loading": self.load_depth > 0}
        with self.lock:
            last = self.ocr[-1] if self.ocr else None
            if last is None or any(last[k] != rec[k] for k in ("device", "why", "engines", "loading")):
                self.ocr.append(rec)


class HotKeys:
    """TASlation's global hot keys as this tool lets the window have them (in `capture.overlay.HotKeys`' place): none
    is registered with Windows - the keys stay the system's and their owner's -, the names the window holds are noted
    as they change, and a press is this tool's (`press`), handed to the window by `take` as Windows hands over a
    WM_HOTKEY: only for a key the window holds then (another is the viewer's, and noted as not taken)."""

    def __init__(self, notes: Notes):
        self.notes = notes
        self.names: set[str] = set()
        self.presses: list[str] = []

    @property
    def registered(self) -> frozenset[str]:
        return frozenset(self.names)

    def register(self, name: str, vk: int, mods: int = 0) -> bool:
        if name not in self.names:
            self.names.add(name)
            self.notes.held(self.registered)
        return True

    def unregister(self, name: str) -> None:
        if name in self.names:
            self.names.discard(name)
            self.notes.held(self.registered)

    def clear(self) -> None:
        for name in list(self.names):
            self.unregister(name)

    def close(self) -> None:
        self.clear()

    def press(self, name: str) -> None:
        self.presses.append(name)

    def take(self) -> list[str]:
        taken = [name for name in self.presses if name in self.names]
        for name in self.presses:
            self.notes.pressed(name, name in self.names)
        self.presses.clear()
        return taken


# status lines said with `say` that speak of a page: of the page the job read, of the viewer's page on show
JOB_KEYS = ("Stopped: this page was not translated",)
VIEWER_KEYS = ("This page is translated; the whole-book run",)


def status_kind(render: Any, key: str | None) -> tuple[str, str | None, Any]:
    """What a status line is, from the window's record of it (*render*, the callable that says it again in the
    window's language, and *key*, its template when it was said with `say`): its kind - "page_summary" (a page's
    summary), "progress" (a page job at work), "beside" (beside a whole-book run), "say:" and the template's first
    words, "message:" and a Message's code, "other" -, never its text; which page it speaks of ("result": the page in
    its words, "job": the page the running job reads, "viewer": the viewer's frame on show, None: no page); and the
    page's result for "result"."""
    cells = []
    for cell in getattr(render, "__closure__", None) or ():
        with contextlib.suppress(ValueError):
            cells.append(cell.cell_contents)
    names = getattr(getattr(render, "__code__", None), "co_names", ())
    result = next((c for c in cells if type(c).__name__ == "PageResult"), None)
    if result is not None:
        return "page_summary", "result", result
    if "progress_line" in names:
        return "progress", "job", None
    if "beside_line" in names:
        return "beside", "viewer", None
    if key:
        about = "job" if key.startswith(JOB_KEYS) else "viewer" if key.startswith(VIEWER_KEYS) else None
        return "say:" + "_".join(re.findall(r"[A-Za-z]+", key)[:4]), about, None
    message = next((c for c in cells if type(c).__name__ == "Message"), None)
    if message is not None:
        return "message:" + str(getattr(message, "code", "?")), None, None
    return "other", None, None


def tk_error() -> type[Exception]:
    """Tk's error class (imported where it is used: the tool's top imports no Tk)."""
    import tkinter as tk

    return tk.TclError


def page_point(app: Any, region: Any) -> tuple[int, int]:
    """The middle of *region* (image pixels) on the window's page canvas, in the canvas's pixels."""
    from taslation.ui import area

    x0, y0, x1, y1 = region.bbox
    x, y = area.to_canvas((x0 + x1) / 2, (y0 + y1) / 2, app.canvas.scale, app.canvas.offset)
    return int(round(x)), int(round(y))


def _user32() -> Any:
    """user32 of this tool's own (its functions' argument types set here touch no other module's)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32")
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    return user32


def root_of(widget: Any) -> int:
    """The top-level window (Windows' handle) of the Tk widget *widget*."""
    return int(_user32().GetAncestor(widget.winfo_id(), 2) or 0)  # GA_ROOT


def over_facts(window: Any, app: Any) -> dict[str, Any]:
    """Where TASlation's own window *window* (a dialog) lies against the window *app* on the full screen, as Windows
    has them, by asking it only (nothing moves): whether the window at the dialog's middle is the dialog (it is above
    the full screen there), whether the dialog lies within the full screen's rectangle, whether the window owns it,
    and both sizes."""
    from ctypes import wintypes

    from taslation.capture import window_rect

    user32 = _user32()
    out: dict[str, Any] = {}
    try:
        own, full = root_of(window), root_of(app)
        left, top, right, bottom = window_rect(own)
        f_left, f_top, f_right, f_bottom = window_rect(full)
        at = int(user32.WindowFromPoint(wintypes.POINT((left + right) // 2, (top + bottom) // 2)) or 0)
        at_root = int(user32.GetAncestor(at, 2) or 0) if at else 0
        owner = int(user32.GetWindow(own, 4) or 0)  # GW_OWNER
        out.update(dialog_on_top_at_its_middle=at_root == own, within_the_full_screen=(
            left >= f_left and top >= f_top and right <= f_right and bottom <= f_bottom),
                   owned_by_the_window=owner == full, dialog_size=[right - left, bottom - top],
                   full_screen_size=[f_right - f_left, f_bottom - f_top])
    except Exception as e:  # noqa: BLE001 - said by its type
        out["error"] = type(e).__name__
    return out


class LogTap(logging.Handler):
    """The app's log records: where the OCR readers went (the template's codes, never a text of a page), and the
    warnings and errors by logger, level and type name."""

    TEMPLATES = (("the OCR readers run on the %s (%s)", "run_on"),
                 ("the OCR readers stay on the GPU through", "stay_through_load"),
                 ("the OCR readers go to the CPU for the translation model's load", "cpu_for_load"),
                 ("where the OCR runs could not be decided", "undecided"))

    def __init__(self, notes: Notes):
        super().__init__(logging.INFO)
        self.notes = notes
        self.levels: Counter[str] = Counter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.msg if isinstance(record.msg, str) else ""
            for template, code in self.TEMPLATES:
                if msg.startswith(template):
                    args = record.args if isinstance(record.args, tuple) else ()
                    words = ([] if code == "stay_through_load" else
                             [str(a) for a in args if isinstance(a, (str, int, float))][:2])
                    with self.notes.lock:
                        self.notes.ocr_log.append({"t": now_ms(), "note": code, "args": words})
            if record.levelno >= logging.WARNING:
                kind = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else ""
                self.levels[f"{record.levelname} {record.name}{(' ' + kind) if kind else ''}"] += 1
        except Exception:  # noqa: BLE001 - never in the app's way
            pass


# ---------------------------------------------------------------------------------------------------- the hooks
# the live view's calls on the Tk thread whose time is noted (those the window has: older code lacks some)
TIMED = ("_beat", "_poll", "_look", "_look_over_job", "_watch_page", "_follow_step", "_poll_events")


def timed_call(notes: Notes, name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    def call(self: Any, *a: Any, **k: Any) -> Any:
        busy = bool(getattr(self, "busy", False))
        began = time.perf_counter()
        try:
            return original(self, *a, **k)
        finally:
            notes.timed(name, (time.perf_counter() - began) * 1000, busy)

    call.__name__ = name
    return call


def install(notes: Notes, args: argparse.Namespace, guard: Any, viewer_info: Callable[[], Any],
            hotkeys: HotKeys) -> dict[str, Any]:
    """The guard (`demo_video`'s, keys and clicks refused; the global hot keys this tool's *hotkeys*), and the hooks
    that take the notes; what was replaced."""
    import demo_video

    import taslation.capture.overlay as overlay
    import taslation.capture.wgc as wgc
    import taslation.capture.windows as windows
    from taslation import batch as batch_mod
    from taslation import fingerprint
    from taslation import linememo
    from taslation import pageimages
    from taslation import pipeline as pipeline_mod
    from taslation.ocr import place
    from taslation.translate import ollama as ollama_mod
    from taslation.translate import plamo as plamo_mod
    from taslation.ui import app as app_mod
    from taslation.ui import live, overbook

    table = {name: (("never" if allow == "viewer" else allow), target)
             for name, (allow, target) in demo_video.GUARDED.items()}  # (TASlation sends no key, no click here)
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
    start_translate, job_translate = App._start_translate, App._job_translate
    handle_event, redisplay, capture, chosen = App._handle_event, App._redisplay, App._capture, App._on_window_selected
    batch_done = App._batch_done

    def started(self: Any, image: Any, *a: Any, **k: Any) -> Any:
        job = notes.new_job(image)
        try:
            return start_translate(self, image, *a, **k)
        finally:
            notes.job_started(job, image, getattr(self, "_job_frame", None) is image, getattr(self, "_page_gate", None))

    def worked(self: Any, image: Any, *a: Any, **k: Any) -> Any:
        job = notes.take_job(image, k.get("gate"))
        try:
            return job_translate(self, image, *a, **k)
        finally:
            notes.job_over(job)

    def handled(self: Any, kind: str, data: dict[str, Any]) -> Any:
        if kind in KINDS:
            notes.app_event(self, kind, data)
        return handle_event(self, kind, data)

    def drawn(self: Any) -> Any:
        out = redisplay(self)
        try:
            notes.display(self)
        except Exception as e:  # noqa: BLE001 - noted, never in the app's way
            notes.error("display hook", type(e).__name__)
        return out

    def captured(self: Any, hwnd: int) -> Any:
        began = time.perf_counter()
        image = capture(self, hwnd)
        took = (time.perf_counter() - began) * 1000
        notes.timed("_capture", took, bool(getattr(self, "busy", False)))
        if took > LONG_CAPTURE_MS:
            with notes.lock:
                notes.long_captures.append((now_ms(), took))
        notes.captured(image)
        return image

    def selected(self: Any, *a: Any, **k: Any) -> Any:
        out = chosen(self, *a, **k)
        if self.selected is not None:
            notes.selected.append(int(self.selected.hwnd))
        return out

    def run_done(self: Any, progress: Any) -> Any:
        notes.run_end(progress)
        return batch_done(self, progress)

    App._start_translate, App._job_translate, App._handle_event = started, worked, handled
    App._redisplay, App._capture, App._on_window_selected = drawn, captured, selected
    App._batch_done = run_done
    decided, stored = batch_mod.BatchReader._decided, pageimages.PageImages.frame

    def run_decided(self: Any, decisions: Any) -> Any:  # a whole-book run's decisions on the viewer's frames
        for kind, image in decisions:
            notes.run_frame(kind, image)
        return decided(self, decisions)

    def run_stored(self: Any, key: Any) -> Any:  # ... and each frame it gets from its store, to read or letter
        image = stored(self, key)
        notes.run_read(key, image)
        return image

    batch_mod.BatchReader._decided, pageimages.PageImages.frame = run_decided, run_stored
    units_of, lookup = pipeline_mod.Pipeline.units_of, pipeline_mod.Pipeline._lookup

    def fingerprinted(self: Any, rgb: Any) -> Any:  # the page units, by the capture area in force as they are found
        units = units_of(self, rgb)
        notes.local.read = ((int(rgb.shape[1]), int(rgb.shape[0])), tuple(int(m) for m in self.settings.margins))
        return units

    def looked_up(self: Any, unit: Any, *a: Any, **k: Any) -> Any:  # ... and what the cache gave each of them
        hit = lookup(self, unit, *a, **k)
        try:
            notes.lookup(self, unit, hit, getattr(notes.local, "read", None))
        except Exception as e:  # noqa: BLE001 - noted, never in the app's way
            notes.error("lookup hook", type(e).__name__)
        return hit

    pipeline_mod.Pipeline.units_of, pipeline_mod.Pipeline._lookup = fingerprinted, looked_up
    resolve, readings = pipeline_mod.Pipeline._resolve, fingerprint.readings

    def counted_readings(*a: Any, **k: Any) -> Any:  # the readings a look for the page went through
        for units in readings(*a, **k):
            notes.local.readings += 1
            yield units

    def resolved(self: Any, rgb: Any, units: Any) -> Any:  # ... and how long it took, what it found
        notes.local.readings = 0
        t = time.perf_counter()
        out = resolve(self, rgb, units)
        ms = (time.perf_counter() - t) * 1000
        ran = notes.local.readings
        notes.resolved(ms, ran if ran else None, sum(1 for a, b in zip(units, out) if a is not b))
        return out

    pipeline_mod.Pipeline._resolve, fingerprint.readings = resolved, counted_readings
    put_line, decide_kept = linememo.LineMemo.put, pipeline_mod.Pipeline.decide_kept

    def line_kept(self: Any, scope: str, key: str, *a: Any, **k: Any) -> Any:  # a kept line put first, by its job
        scope = scope[:linememo.MAX_SCOPE]
        first = self.find(scope, key) is None
        changed = put_line(self, scope, key, *a, **k)
        if changed and first and self.rings:
            notes.line_put(line_id(self.rings[0].secret, scope, self.rings[0].digest(key)))
        return changed

    def kept_decided(self: Any) -> Any:  # a page job kept for now, decided: when, how, by which job
        held = getattr(self, "_kept_open", None)
        kept = decide_kept(self)
        if held is not None:
            notes.decided(getattr(held, "gate", None), kept)
        return kept

    linememo.LineMemo.put, pipeline_mod.Pipeline.decide_kept = line_kept, kept_decided
    for name in TIMED:  # the Tk thread's time in the live view's calls, a job running or not
        if hasattr(App, name):
            setattr(App, name, timed_call(notes, name, getattr(App, name)))
    leave_reading = App.leave_reading

    def left(self: Any, *a: Any, **k: Any) -> Any:
        if getattr(self, "reading", False):  # who left the full screen: the functions' names on the way, no more
            calls = [f.name for f in traceback.extract_stack(limit=8)[:-1]]
            with notes.lock:
                notes.leaves.append({"t": now_ms(), "role": str(self.role_var.get()), "calls": calls[-6:]})
        return leave_reading(self, *a, **k)

    App.leave_reading = left

    def counted(cls: Any, name: str, note: Callable[[str], None]) -> None:
        original = cls.__dict__[name]

        def call(self: Any, *a: Any, **k: Any) -> Any:
            note(f"{cls.__name__}.{name}")
            return original(self, *a, **k)

        setattr(cls, name, call)

    def requested(cls: Any, name: str) -> None:  # a request to the translator: its begin, its end and how it ended
        original = cls.__dict__[name]

        def call(self: Any, *a: Any, **k: Any) -> Any:
            rec = notes.request(f"{cls.__name__}.{name}")
            held, notes.local.request = getattr(notes.local, "request", None), rec
            outcome = "ok"
            try:
                return original(self, *a, **k)
            except BaseException as e:
                outcome = type(e).__name__
                raise
            finally:
                notes.local.request = held
                notes.request_over(rec, outcome)

        setattr(cls, name, call)

    requested(plamo_mod.PlamoTranslator, "_generate")
    requested(ollama_mod.OllamaTranslator, "_chat")
    stream_once = ollama_mod.OllamaTranslator._stream_once

    def streamed(self: Any, path: str, payload: dict[str, Any], *a: Any, **k: Any) -> Any:
        # the HTTP exchange of a request noted (`requested`): when it went out, when it ended, the server's time for
        # it (Ollama's total_duration, the model's load in it) and the model's own work in it (the load, the prompt,
        # the answer), so that a wait at the server shows: Ollama counts a request queued behind another in its
        # total_duration (a short request sent beside a long one: total 3164 ms, work 57 ms)
        rec = getattr(notes.local, "request", None)
        if rec is None or not (payload.get("prompt") or payload.get("messages")):
            return stream_once(self, path, payload, *a, **k)
        rec["http_t"] = now_ms()
        try:
            data = stream_once(self, path, payload, *a, **k)
        finally:
            rec["http_end_t"] = now_ms()
        with contextlib.suppress(TypeError, ValueError):
            rec["server_ms"] = round(float(data.get("total_duration") or 0) / 1e6, 1)
            rec["load_ms"] = round(float(data.get("load_duration") or 0) / 1e6, 1)
            rec["work_ms"] = round(sum(float(data.get(key) or 0) for key in
                                       ("load_duration", "prompt_eval_duration", "eval_duration")) / 1e6, 1)
        return data

    ollama_mod.OllamaTranslator._stream_once = streamed
    for name in ("_cancel_page", "_early_drop"):  # a running page job cancelled by the live view: when
        if not hasattr(App, name):
            continue

        def cancelling(self: Any, *a: Any, _original: Callable[..., Any] = getattr(App, name), **k: Any) -> Any:
            cancel = getattr(self, "_page_cancel", None)
            was = cancel is None or cancel.is_set()
            try:
                return _original(self, *a, **k)
            finally:
                if not was and cancel.is_set() and bool(getattr(self, "busy", False)):
                    notes.cancelled(now_ms())

        setattr(App, name, cancelling)
    counted(plamo_mod.PlamoTranslator, "warm_up", notes.warmup)
    counted(ollama_mod.OllamaTranslator, "warm_up", notes.warmup)
    loading = place.loading

    @contextlib.contextmanager
    def load() -> Any:
        notes.load_begin()
        try:
            with loading():
                yield
        finally:
            notes.load_end()

    place.loading = load
    real_owner = live.foreground_owner

    def owner(hwnd: int, viewer: int, *a: Any, **k: Any) -> str:
        got = real_owner(hwnd, viewer, *a, **k)
        with notes.lock:
            notes.owners[got] += 1
        return "viewer" if args.front == "viewer" else got

    live.foreground_owner = owner

    def over_owner(hwnd: int, viewer: int, *a: Any, **k: Any) -> str:  # over the book: its own window as it is
        got = real_owner(hwnd, viewer, *a, **k)
        return "viewer" if args.front == "viewer" and got != "own" else got

    overbook.foreground_owner = over_owner
    hook = threading.excepthook

    def thread_error(info: Any) -> None:
        notes.error(f"thread {getattr(info.thread, 'name', '?')}", getattr(info.exc_type, "__name__", "?"))
        hook(info)

    threading.excepthook = thread_error
    return done


# ---------------------------------------------------------------------------------------------------- the director
class Director:
    """The run on the Tk loop: the guard looked at every TICK_MS, what the stand-in said taken in, the OCR readers'
    place sampled, each scenario released once the window is at rest, the pictures taken; numbers only."""

    def __init__(self, app: Any, browser: sv.StandinBrowser, guard: Any, selection: sv.SelectionGuard,
                 notes: Notes, segments: list[Segment], args: argparse.Namespace, out: Path, standin_dir: Path,
                 narrow_rect: tuple[int, int, int, int], app_rect: tuple[int, int, int, int], hotkeys: HotKeys):
        self.app, self.browser, self.guard, self.selection = app, browser, guard, selection
        self.notes, self.segments, self.args, self.out, self.standin_dir = notes, segments, args, out, standin_dir
        self.narrow_rect, self.app_rect, self.hotkeys = narrow_rect, app_rect, hotkeys
        self.entered: dict[str, dict[str, Any]] = {}  # per scenario of a mode: what was done to enter it, and when
        self.standin_before: tuple[int, int, int, int] | None = None  # the stand-in's rect before scenario o
        self.run_ends_seen = 0
        self.resized_at, self.resizes_seen = float("-inf"), 0  # the stand-in's last draw at a new size, pictured after
        self.mono0, self.epoch0 = time.monotonic(), now_ms()
        self.events: list[dict[str, Any]] = []
        self.seen = 0
        self.waiting_go = 0
        self.ended = False
        self.index = 0
        self.phase = "prepare"
        self.phase_at = time.monotonic()
        self.idle_since: float | None = None
        self.over = False
        self.failed = ""
        self.released: dict[str, dict[str, Any]] = {}
        self.facts: dict[str, Any] = {}
        self.theme: dict[str, str] = {}
        self.shots: list[dict[str, Any]] = []
        self.taken: set[str] = set()
        self.due: list[tuple[float, str]] = []
        self.watch: dict[tuple[str, int, bool], list[str]] = {}
        self.turns_in: Counter[str] = Counter()
        self.segment_of_go = {s.go: s.name for s in segments}
        self.current = ""
        self.keyed: dict[str, dict[str, Any]] = {}  # scenario t's and t2's page key: how it was pressed, what it handed
        self.key_for: Segment | None = None  # the scenario whose turn the next key handed to the stand-in releases
        self._hook_page_keys()
        self.page_rect: tuple[int, int, int, int] | None = None  # the page the stand-in drew last (its canvas's pixels)
        self.band_px = 0  # the height of its band then
        self.last_ocr = 0.0
        self.saver: queue.Queue[Any] = queue.Queue()
        self.saver_thread = threading.Thread(target=self._save, name="standin-shots", daemon=True)
        self.saver_thread.start()
        (out / "shots").mkdir(parents=True, exist_ok=True)
        for s in segments:
            for k in SOFT_SHOTS.get(s.name, ()):
                if k <= len(s.screens):
                    self.watch[(s.name, *s.screens[k - 1])] = [f"{s.name}_turn{k}_soft",
                                                               f"{s.name}_turn{k}_sharp_quick"]
        notes.on_display = self.on_display

    # the loop
    def start(self) -> None:
        self.app.after(TICK_MS, self.tick)

    def tick(self) -> None:
        if self.over:
            return
        try:
            with self.notes.lock:  # (this runs on the Tk thread: its CPU time so far, a page job running or not)
                self.notes.tk_cpu.append((time.monotonic(), time.thread_time(), bool(getattr(self.app, "busy", False))))
            self.check()
            if not self.over:
                self.pull()
                if time.monotonic() - self.last_ocr >= OCR_EVERY_S:
                    self.last_ocr = time.monotonic()
                    self.notes.placement(self.app)
                self.notes.area(self.app)
                self.notes.mode(self.app)
                self.step()
                self.due_shots()
        except Exception as e:  # noqa: BLE001 - said by its type, and the run ends
            self.stop(f"{type(e).__name__} in the driver")
        if not self.over:
            self.app.after(TICK_MS, self.tick)

    def check(self) -> None:
        """The guard first: anything chosen but the stand-in, a call refused, the stand-in gone - the run stops."""
        why = self.selection.check(getattr(self.app, "selected", None))
        if why:
            self.stop(why)
        elif self.guard.refused:
            self.stop("a call was refused: " + ", ".join(sorted(set(self.guard.refused))))
        elif not self.browser.alive():
            self.stop("the stand-in browser ended")

    def stop(self, why: str) -> None:
        if self.over:
            return
        self.over = True
        if why != "done":
            self.failed = why
            print(f"run stopped: {why}", file=sys.stderr, flush=True)
        self.app.after_idle(self.app.quit)

    def epoch(self, mono: float) -> float:
        return self.epoch0 + (mono - self.mono0) * 1000.0

    def pull(self) -> None:
        """What the stand-in said since the last tick."""
        for mono, said in self.browser.said(self.seen):
            self.seen += 1
            e: dict[str, Any] = dict(said)
            e["t"], e["recv"] = float(said["t"]), self.epoch(mono)
            e["segment"] = self.current
            ev = e["ev"]
            if ev == "draw":  # (where it drew the page: `page_facts`)
                with contextlib.suppress(KeyError, ValueError):
                    x0, y0, x1, y1 = (int(round(float(v))) for v in e["box"].split(","))
                    self.page_rect, self.band_px = (x0, y0, x1, y1), int(e["band"])
            if ev == "wait":
                self.waiting_go = int(e.get("go", 0))
            elif ev == "mark":
                self.current = self.segment_of_go.get(int(e.get("id", 0)), "")
                e["segment"] = self.current
            elif ev == "end":
                self.ended = True
            elif ev == "draw" and e.get("why") in ("next", "previous", "jump"):
                self.turns_in[self.current] += 1
                self.turned(e)
            elif ev == "draw" and e.get("why") == "resize" and time.monotonic() - self.resized_at > RESIZE_SHOT_S:
                # the page at its new size, as the window draws it once it has read it (from the cache, if it holds it)
                self.resized_at, self.resizes_seen = time.monotonic(), self.resizes_seen + 1
                self.due.append((self.resized_at + RESIZE_SHOT_S,
                                 f"{self.current or 'start'}_resized{self.resizes_seen}"))
            elif ev == "black" and e.get("on") == "1" and self.current == "d":
                self.due.append((time.monotonic() + 0.3, f"d_flash{self.turns_in['d']}"))
            elif ev == "spinner" and e.get("on") == "1" and self.current == "d":
                self.due.append((time.monotonic() + 0.8, f"d_spinner{self.turns_in['d']}"))
            self.events.append(e)

    def turned(self, e: dict[str, Any]) -> None:
        """A turn began on the stand-in: the pictures due for it (`SHOTS`)."""
        seg, k = self.current, self.turns_in[self.current]
        if (seg, k) in SHOTS:
            delay, label = SHOTS[(seg, k)]
            self.due.append((time.monotonic() + delay, label))

    # the scenarios
    def idle(self) -> bool:
        app = self.app
        f = getattr(app, "_following", None)
        return bool(app.ready and not app.busy and app._queued is None and app.batch is None
                    and (f is None or f.op is None) and getattr(app, "_early", None) is None
                    and getattr(app, "_enlarging", None) is None)

    def step(self) -> None:
        now = time.monotonic()
        self.idle_since = (self.idle_since or now) if self.idle() else None
        rested = self.idle_since is not None and now - self.idle_since >= IDLE_S
        waited = now - self.phase_at
        if len(self.notes.run_ends) > self.run_ends_seen:  # a whole-book run ended: the window a while after
            self.run_ends_seen = len(self.notes.run_ends)
            self.due.append((time.monotonic() + 4.0, f"run{self.run_ends_seen}_ended"))
        if self.index >= len(self.segments):
            if self.phase != "end":
                if self.index:
                    self.after(self.segments[-1])
                self.phase, self.phase_at = "end", now
                return
            if (self.ended and rested) or waited > self.args.timeout:
                if waited > self.args.timeout:
                    self.released["end"] = {"timed_out": True}
                self.finish()
            return
        seg = self.segments[self.index]
        if self.phase == "prepare":
            if self.index:
                self.after(self.segments[self.index - 1])
            self.before(seg)
            self.phase, self.phase_at = "settle", now
            return
        if self.phase == "settle":
            ready_go = self.waiting_go >= seg.go
            if seg.name in ("r", "t", "o", "z", "w") and seg.name not in self.entered and ready_go and rested:
                self.enter(seg.name)  # (a mode entered at rest, as a reader does; released once it is on)
                return
            app = self.app
            mode = self.entered.get(seg.name)
            if seg.name == "c":
                go = ready_go and getattr(app, "selected", None) is not None
            elif seg.name == "f2":
                go = ready_go and rested and self.resized()
            elif seg.name in ("r", "o", "z"):
                go = ready_go and rested and mode is not None and now - mode["at"] >= 1.0 and (
                    seg.name == "z" or bool(app.reading) and (seg.name == "r" or bool(app._over_on)))
            elif seg.name == "w":  # the run reads the pages the stand-in turns to
                batch = getattr(app, "batch", None)
                go = (ready_go and mode is not None and batch is not None and bool(getattr(batch, "following", False))
                      and now - mode["at"] >= 1.0)
            elif seg.name == "w2":  # Finished reading: the run translates, and the window follows the viewer beside it
                from taslation.ui.live import reads_beside

                go = ready_go and reads_beside(app)
            elif seg.name in KEYED:  # the turn released by the page key the window hands on (`page_key`)
                go = self.keyed_turn(seg, ready_go, rested, now)
            else:
                go = ready_go and rested and (self.index > 0 or self.first_page_done())
            timed_out = ready_go and (waited > self.args.timeout or (
                seg.name in ("r", "o", "z") and mode is not None and now - mode["at"] > MODE_WAIT_S))
            if timed_out and not app.ready:
                self.stop("the window was not ready within --timeout")
                return
            if go or timed_out:
                self.released[seg.name] = {"waited_s": round(waited, 1), "timed_out": bool(timed_out and not go),
                                           "t": now_ms()}
                self.key_for = None
                sv.write_control(self.standin_dir, seg.go)
                self.phase, self.phase_at = "running", now
            return
        if self.phase == "running" and (self.waiting_go > seg.go or self.ended):
            self.index += 1
            self.phase, self.phase_at = "prepare", now

    def first_page_done(self) -> bool:
        return any(d["kind"] == "translated" for d in self.notes.displays) or (
            self.app.ready and time.monotonic() - self.phase_at > 30)

    def before(self, seg: Segment) -> None:
        from taslation.ui import theme

        if seg.name == "f":
            self.theme["before"] = theme.mode()
            self.app._settings_saved({"theme": "dark"})
            self.theme["after"] = theme.mode()
        elif seg.name == "f2":
            self.resize_from = len(self.events)
            hwnd = self.browser.hwnd
            if hwnd and self.guard.is_viewer(hwnd):
                place_own(hwnd, self.narrow_rect)
        elif seg.name == "w2":
            self.app.finish_reading()  # the band's Finished reading: the stand-in has come to the stretch's end
            self.entered["w2"] = {"at": time.monotonic(), "finished_reading": True}

    def enter(self, name: str) -> None:
        """The mode of scenario *name* entered, as a reader does: r - F11 (`toggle_reading`, the key's own handler);
        t - the toolbar's Translator, then F11's handler; o - over the book (`over_begin`); z - TASlation's text size
        TEXT_SIZE times the run's (Settings); w - a whole-book run started as the dialog's Start starts it."""
        app = self.app
        self.entered[name] = {"at": time.monotonic()}
        if name == "r":
            self.shot("r_toolbar_reader_role")  # (the window as it was: the toolbar's Full screen and the role)
            app.toggle_reading()
            self.entered["r"].update(full_screen=bool(app.reading), auto_on_it=bool(app.auto_var.get()),
                                     first_line=self.status_facts())
            app.after(1500, lambda: self.shot("r_full_screen_reader_role"))
        elif name == "t":
            facts = self.entered["t"]
            facts.update(auto_before=bool(app.auto_var.get()), role_before=str(app.role_var.get()))
            facts["role_by_its_button"] = self.choose_role("translator")

            def full() -> None:
                self.shot("t_toolbar_translator_role")
                app.toggle_reading()  # F11's own handler
                facts["full_at"] = time.monotonic()  # (the acts wait for the page laid out on it: `keyed_turn`)
                facts.update(full_screen=bool(app.reading), role_on_it=str(app.role_var.get()),
                             auto_on_it=bool(app.auto_var.get()), first_line=self.status_facts())
                app.after(1500, lambda: self.shot("t_full_screen_translator_role"))

            app.after(900, full)
        elif name == "o":
            self.over_begin()
        elif name == "z":
            app._settings_saved({"ui_scale": round(self.args.scale * TEXT_SIZE, 2)})
        elif name == "w":
            app._start_batch(app.selected, app.settings.batch_max_pages, app.settings.context_mode)

    def after(self, seg: Segment) -> None:
        """The stand-in has gone through scenario *seg*: its mode left (r: F11's handler; o: `over_end`; z: the run's
        text size again)."""
        app = self.app
        if seg.name == "r" and app.reading:
            app.toggle_reading()
            if "r" in self.entered:
                self.entered["r"].update(left=not app.reading, auto_after=bool(app.auto_var.get()),
                                         status_after=self.status_facts())
        elif seg.name == "t2":
            self.leave_translator()
        elif seg.name == "o":
            self.over_end()
        elif seg.name == "z":
            app._settings_saved({"ui_scale": self.args.scale})

    # scenario t: the full screen in the Translator role
    def _hook_page_keys(self) -> None:
        """The page keys of scenarios t and t2: the key the window hands to the stand-in for a page key pressed on
        its page (`reading.ReadingMixin._pass_on`; a browser's keys go pressed for real, `press_briefly`) is noted
        and never sent - it releases the stand-in's turn of the scenario it was pressed for (`key_for`), as a viewer
        turns its page on the key. Any other key goes to the guard, which refuses it and stops the run."""
        from taslation.ui import reading as reading_mod

        guarded = reading_mod.press_briefly

        def page_key(hwnd: int, key: Any, *a: Any, **k: Any) -> Any:
            seg = self.key_for
            if seg is None or not self.guard.is_viewer(hwnd):
                return guarded(hwnd, key, *a, **k)
            self.key_for = None
            facts = self.keyed.setdefault(seg.name, {})
            facts["handed_on"] = key if isinstance(key, str) else list(key)
            facts["handed_on_after_ms"] = round((time.monotonic() - facts.get("at", time.monotonic())) * 1000)
            sv.write_control(self.standin_dir, seg.go)
            return True

        reading_mod.press_briefly = page_key

    def keyed_turn(self, seg: Segment, ready_go: bool, rested: bool, now: float) -> bool:
        """Scenarios t and t2: whether the page key has released the stand-in's turn (`page_key`); before that, at rest
        on the full screen in the Translator role, t's acts there (`translator_acts`, which end with its key), and
        t2's key at rest."""
        facts = self.keyed.get(seg.name)
        if facts is not None:
            return "handed_on" in facts  # (the key pressed: released once the window hands it on)
        if not ready_go:
            return False
        app = self.app
        if seg.name == "t2":
            if rested:
                self.press_page_key(seg)
            return False
        mode = self.entered.get("t")
        if mode is None or "acts" in mode:
            return False
        on = (bool(app.reading) and app.role_var.get() == "translator" and rested and app._editing()
              and now - mode.get("full_at", now) >= FULL_SCREEN_SETTLE_S)
        if on or now - mode["at"] > ACTS_WAIT_S:
            mode["acts"] = {"waited_s": round(now - mode["at"], 1)}
            self.translator_acts(seg)
        return False

    def translator_acts(self, seg: Segment) -> None:
        """Scenario t at rest on the full screen in the Translator role, as a person works there: the largest region
        lettered selected by a click on it (Tk's own press and release on the page canvas) and pictured; the region
        editor opened by a double click on it, its place over the full screen noted (`over_facts`) and its own window
        pictured, then closed by its Esc (`close_asked`); the selection let go by Esc (the window's handler); then
        the next page key (`press_page_key`). Each step notes what came of it, as numbers and names."""
        app, acts = self.app, self.entered["t"]["acts"]
        region = self.largest_region()
        acts["region_found"] = region is not None
        if region is None or not app._editing():
            acts["skipped"] = "no region" if region is None else "the translated page not on show"
            self.press_page_key(seg)
            return
        clock = [int(time.monotonic() * 1000) & 0x3FFFFFFF]  # the events' times: clicks far apart, a double close

        def click(gap: int) -> None:  # (at the region's middle where the page is drawn now)
            x, y = page_point(app, region)
            clock[0] += gap
            app.canvas.event_generate("<ButtonPress-1>", x=x, y=y, time=clock[0])
            app.canvas.event_generate("<ButtonRelease-1>", x=x, y=y, time=clock[0] + 60)

        def select() -> None:
            click(0)
            acts["selected_by_a_click"] = app._chosen_region is region
            acts["clicks_handed_to_the_stand_in"] = self.guard.used.get("post_click", 0)
            acts["status_after_the_click"] = self.status_facts()
            app.after(700, pictured)

        def pictured() -> None:
            self.shot("t_region_selected")
            app.after(300, edit)

        def edit(tries: int = 0) -> None:
            if self.over or not app._editing():
                acts["editor"] = "the translated page not on show"
                app.after(300, key)
                return
            if app.busy and tries < 40:  # a job at work (the editor opens at rest, as a person's double click does)
                app.after(500, lambda: edit(tries + 1))
                return
            acts["busy_at_the_double_click"] = bool(app.busy)
            x, y = page_point(app, region)
            acts["region_under_the_double_click"] = app._region_at(*app.canvas.to_image_coords(x, y)) is region
            click(5000)  # (a click of its own, long after the one that selected) ...
            click(250)  # ... and the second of a double click
            editor = getattr(app, "_editor", None)
            acts["editor_by"] = "a double click" if editor is not None and editor.winfo_exists() else None
            if acts["editor_by"] is None and acts["region_under_the_double_click"]:
                app._on_double(SimpleNamespace(x=x, y=y))  # (Tk took the two clicks for two: the double's handler)
                acts["editor_by"] = "the double click's handler"
            app.after(1200, opened)

        def opened() -> None:
            editor = getattr(app, "_editor", None)
            acts["editor_open"] = bool(editor is not None and editor.winfo_exists())
            if acts["editor_open"]:
                acts["editor_window"] = over_facts(editor, app)
                self.shot("t_region_editor", window=editor)
                editor.close_asked()  # its Esc: nothing changed, it closes
            app.after(700, closed)

        def closed() -> None:
            editor = getattr(app, "_editor", None)
            acts["editor_closed"] = editor is None or not editor.winfo_exists()
            acts["full_screen_after_the_editor"] = bool(app.reading)
            acts["selected_after_the_editor"] = app._chosen_region is region
            with contextlib.suppress(KeyError, tk_error()):
                acts["keys_back_on_the_page"] = app.focus_get() is app.canvas
            app._on_escape()  # Esc's own handler, a region selected: it lets go of it, the full screen stays
            acts["esc_let_go"] = app._chosen_region is None
            acts["full_screen_after_esc"] = bool(app.reading)
            app.after(700, key)

        def key() -> None:
            if not self.over:
                self.press_page_key(seg)

        select()

    def largest_region(self) -> Any:
        """The largest region on the page on show whose middle lies on the page the full screen draws, a lettered one
        first; None without one."""
        app = self.app
        try:
            regions = list(app._page_regions())
        except Exception:  # noqa: BLE001 - no regions to be had
            return None
        regions = [r for r in regions if app.canvas.inside(*page_point(app, r))]
        lettered = [r for r in regions if getattr(r, "status", "") == "translated"] or regions
        return max(lettered, key=lambda r: (r.bbox[2] - r.bbox[0]) * (r.bbox[3] - r.bbox[1]), default=None)

    def press_page_key(self, seg: Segment) -> None:
        """The window's next or previous page key (`KEYED`, as Page > Page keys... has them) pressed on its page: Tk's
        key event on the page canvas, whose binding hands it to `forward_key`; where Tk does not deliver it (it
        delivers keys to the window with the system's keyboard focus, which this tool never moves) the binding's own
        call. The key the window then hands to the stand-in releases its turn (`page_key`)."""
        from taslation.ui.constants import FORWARDED_KEYS

        app = self.app
        pair = app._page_key_pair()
        meaning = KEYED[seg.name]
        key = getattr(pair[1], meaning, "") if pair is not None else ""
        key = key or ("Left" if meaning == "next" else "Right")
        keysym = next((k for k, v in FORWARDED_KEYS.items() if v == key), key)
        facts = self.keyed.setdefault(seg.name, {})
        facts.update(at=time.monotonic(), pressed=key, on_the_full_screen=bool(app.reading),
                     role=str(app.role_var.get()), auto=bool(app.auto_var.get()))
        calls: list[str] = []

        def counted(k: str) -> None:
            calls.append(k)
            type(app).forward_key(app, k)

        self.key_for = seg
        app.forward_key = counted  # (only counted: the window's own `forward_key` does the rest)
        try:
            app.canvas.event_generate(f"<KeyPress-{keysym}>")
        finally:
            del app.forward_key
        facts["by"] = "a key event on the page" if calls else "the binding's call"
        if not calls:
            app.forward_key(key)
        facts["status_after_the_key"] = self.status_facts()

    def leave_translator(self) -> None:
        """Scenario t over (after t2): the full screen left by Esc's own handler (pressed again while it only let go
        of a region), F11's handler where it did not; then the toolbar's Reader again, for the scenarios after it."""
        app, facts = self.app, self.entered.get("t")
        if facts is None:
            return
        presses = 0
        while app.reading and presses < 2:
            app._on_escape()
            presses += 1
        facts["esc_presses_to_leave"] = presses if not app.reading else None
        if app.reading:
            app.toggle_reading()
        facts.update(auto_after=bool(app.auto_var.get()), status_after=self.status_facts())
        facts["reader_by_its_button"] = self.choose_role("reader")
        facts["role_after"] = str(app.role_var.get())

    def choose_role(self, value: str) -> bool:
        """The toolbar's role button for *value* invoked, as a click on it does (its command: `_on_role_changed`);
        False where none was found and the role was set as that command sets it."""
        app = self.app
        stack: list[Any] = [app]
        while stack:
            widget = stack.pop()
            with contextlib.suppress(Exception):
                if (widget.winfo_class() == "TRadiobutton" and str(widget.cget("value")) == value
                        and str(widget.cget("variable")) == str(app.role_var)):
                    widget.invoke()
                    return True
            stack.extend(widget.winfo_children())
        app.role_var.set(value)
        app._on_role_changed()
        return False

    def status_facts(self) -> dict[str, Any]:
        """The status line as its kind (`status_kind`, never its text) and its note on the full screen's page: shown
        or not, for how long (`StatusMixin._note_ms`)."""
        app = self.app
        kind = status_kind(getattr(app, "_status_render", None), getattr(app, "_status_key", None))[0]
        note = str(getattr(app.canvas, "note", "") or "")
        return {"kind": kind, "note_on_the_page": bool(note), "note_ms": app._note_ms(note) if note else None}

    def over_begin(self) -> None:
        """Scenario o: the stand-in's window made to fill its monitor (a viewer's full screen, as `is_fullscreen` tells
        it), View > Over the full-screen viewer turned on; then, as a reader would, the status bar's Move TASlation
        there (offered while TASlation is on another monitor) and the Full screen button (F11 over the book is the
        viewer's own key). What was offered and done is noted."""
        from taslation.capture import monitor_rect, window_rect

        app, hwnd, facts = self.app, self.browser.hwnd, self.entered["o"]
        if not hwnd or not self.guard.is_viewer(hwnd):
            return
        self.standin_before = window_rect(hwnd)
        monitor = monitor_rect(hwnd)
        if monitor is None:
            facts["failed"] = "no monitor"
            return
        left, top, right, bottom = monitor
        place_own(hwnd, (left, top, right - left, bottom - top))
        app.over_var.set(True)
        app.toggle_over()

        def move() -> None:
            button = getattr(app, "move_btn", None)
            facts["move_offered"] = bool(button is not None and button.winfo_manager())
            app.move_to_book()  # the status bar's button
            app.after(1000, read)

        def read() -> None:
            facts["over_before_reading"] = bool(app._over_on)
            app.enter_reading()  # the Full screen button

        app.after(800, move)

    def over_end(self) -> None:
        """Scenario o over: the full screen left by the F11 hot key (this tool's press, `HotKeys`), then the mode turned
        off, TASlation's window back in its place and the stand-in's back to its size (F11's handler where the press
        was not taken: noted)."""
        app, facts = self.app, self.entered.get("o")
        if facts is None:
            return
        self.hotkeys.press("F11")

        def off() -> None:
            facts["left_by_hot_key"] = not app.reading
            if app.reading:
                app.toggle_reading()
            app.over_var.set(False)
            app.toggle_over()
            x, y, w, h = self.app_rect
            app.geometry(f"{w}x{h}+{x}+{y}")
            hwnd = self.browser.hwnd
            if self.standin_before is not None and hwnd and self.guard.is_viewer(hwnd):
                left, top, right, bottom = self.standin_before
                place_own(hwnd, (left, top, right - left, bottom - top))

        app.after(800, off)

    def resized(self) -> bool:
        return any(e["ev"] == "size" for e in self.events[getattr(self, "resize_from", len(self.events)):])

    def finish(self) -> None:
        """The last scenario over and the window at rest: the last picture, the System page's facts; the loop
        ends."""
        from taslation import devices

        self.shot("end")
        try:
            ocr = getattr(getattr(self.app, "pipeline", None), "ocr", None)
            stages = devices.stage_devices(self.app.settings, self.app.translator, ocr=ocr)
            self.facts["stages"] = {s.stage: s.device for s in stages}
        except Exception as e:  # noqa: BLE001 - said by its type
            self.facts["stages_error"] = type(e).__name__
        self.stop("done")

    # the pictures
    def on_display(self, rec: dict[str, Any]) -> None:
        labels = self.watch.get((self.current, rec["page"], rec["spread"]))
        if not labels:
            return
        soft, quick = labels
        if rec["state"] == "soft" and soft not in self.taken:
            self.app.after_idle(lambda: self.shot(soft))
        elif rec["state"] == "sharp" and rec["quick"] and quick not in self.taken:
            self.app.after_idle(lambda: self.shot(quick))

    def due_shots(self) -> None:
        now = time.monotonic()
        for at, label in [d for d in self.due if d[0] <= now]:
            self.due.remove((at, label))
            self.shot(label)

    def shot(self, label: str, window: Any = None) -> None:
        """A picture of TASlation's own window (its handle, the client area; never the screen) into shots/; with
        *window*, of that dialog of TASlation's instead (the whole of it, its title bar too)."""
        from taslation.capture import windows

        if label in self.taken or self.over:
            return
        self.taken.add(label)
        try:
            if window is not None:
                image = windows.capture_window(root_of(window), client_only=False, allow_screen_fallback=False)
            else:
                image = windows.capture_window(self.app._own_hwnd(), client_only=True, allow_screen_fallback=False)
        except Exception as e:  # noqa: BLE001 - said by its type
            self.shots.append({"label": label, "error": type(e).__name__})
            return
        path = self.out / "shots" / f"{len(self.shots) + 1:02d}_{label}.png"
        last = self.notes.displays[-1] if self.notes.displays else {}
        facts = area_facts(self.app)
        self.shots.append({"label": label, "path": str(path), "t": now_ms(), "size": list(image.size),
                           "window_shows": {k: last.get(k) for k in ("page", "spread", "state", "kind", "lettered",
                                                                    "from")},
                           "drawn_quickly": getattr(self.app.canvas, "_fit_key", 0) is None,
                           "area": facts,
                           "page": page_facts(facts.get("drawn_box"), self.page_rect, self.band_px, self.notes.top),
                           "reading": reading_facts(self.app)})
        self.saver.put((image, path))

    def _save(self) -> None:
        while True:
            item = self.saver.get()
            if item is None:
                return
            image, path = item
            try:
                image.save(path, format="PNG", compress_level=3)
            except OSError:
                pass

    def close_saver(self) -> None:
        self.saver.put(None)
        self.saver_thread.join(30)


def area_facts(app: Any) -> dict[str, Any]:
    """The capture area the window reads by, as numbers: the margins in use, the reader's area for the frame there
    is now (and whether it is the enlarged window's), the page panel found within it, the part of the picture the
    page view draws (its crop, None off the full screen) and the picture's size, the viewer's window size."""
    from taslation.capture import window_rect

    out: dict[str, Any] = {}
    for name, get in (("margins", lambda: app.settings.margins), ("hand", lambda: app._hand_area),
                      ("inner", lambda: app._inner_margins()), ("large", lambda: app._area_large),
                      ("manual", lambda: app._manual_area), ("enlarged", lambda: app._window_enlarged()),
                      ("drawn_box", lambda: app.canvas.shown_box()), ("crop", lambda: app.canvas.crop),
                      ("picture_size", lambda: app.canvas._image.size)):
        try:
            value = get()
            out[name] = list(value) if isinstance(value, (tuple, list)) else value
        except Exception as e:  # noqa: BLE001 - said by its type
            out[name] = type(e).__name__
    try:
        left, top, right, bottom = window_rect(app.selected.hwnd)
        out["viewer_size"] = [right - left, bottom - top]
    except Exception as e:  # noqa: BLE001 - said by its type
        out["viewer_size"] = type(e).__name__
    return out


def page_facts(drawn: Any, rect: tuple[int, int, int, int] | None, band: int, top: int) -> dict[str, Any]:
    """The stand-in's page as it drew it last (*rect*: the pages of the screen in its canvas's pixels; *band*: its
    band's height), in the capture's pixels - its canvas begins *top* rows down the client area, under the browser's
    own title bar -, and the part the page view draws (*drawn*, `area_facts`) against it: the rows of the title bar
    and of the band in it (0: none), the columns of the ground beside the page or the rows over and under it in it on
    each side (left, top, right, bottom; negative: that much of the page left out), whether the page is whole in it."""
    if rect is None:
        return {"page": None}
    page = [rect[0], top + rect[1], rect[2], top + rect[3]]
    out: dict[str, Any] = {"page": page, "content_top": top + band}
    if not (isinstance(drawn, list) and len(drawn) == 4):
        return out
    x0, y0, x1, y1 = (int(v) for v in drawn)
    out["title_bar_rows_drawn"] = max(0, min(top, y1) - y0)
    out["band_rows_drawn"] = max(0, min(top + band, y1) - max(top, y0))
    out["ground_drawn"] = [page[0] - x0, page[1] - y0, x1 - page[2], y1 - page[3]]
    out["page_whole"] = x0 <= page[0] and y0 <= page[1] and x1 >= page[2] and y1 >= page[3]
    return out


def reading_facts(app: Any) -> dict[str, Any]:
    """What the reading makes of the viewer's latest frame, as numbers (no picture, no text): the page units' boxes
    in the capture area in force (the pipeline's `units_of`), in the reader's own area alone (``hand``), in the page
    panel the window finds on the whole frame with no area of the reader's (`find_page_area`, its box ``panel``) and
    on the whole frame (no area), with each unit's fingerprint distance to the one of the same place in the area in
    force (bits; 0: the same page identity); the paper `fingerprint.page_box` finds on the whole frame and the page
    `ui.area.page_bounds` finds on it. Computed without the fingerprints' shared memo (`fingerprint._analyze`), so the
    window's own is left as it is."""
    import cv2
    import numpy as np

    from taslation import fingerprint as fp
    from taslation.detect.page_area import find_page_area, page_area_margins
    from taslation.ui import area

    live = getattr(app, "_live", None)
    if live is None:
        return {"frame": None}
    out: dict[str, Any] = {"frame": list(live.size)}
    try:
        rgb = np.asarray(live.convert("RGB"))
        margins = tuple(int(m) for m in app.settings.margins)
        units = fp._analyze(rgb, margins, True, None, True)
        out["margins"] = list(margins)
        out["units"] = [list(u.box) for u in units]
        panel = find_page_area(live)
        out["panel"] = list(panel) if panel is not None else None
        others = {"hand": tuple(int(m) for m in app._hand_set()), "whole_frame": (0, 0, 0, 0)}
        if panel is not None:
            others["panel"] = tuple(int(m) for m in page_area_margins(panel, live.size))
        for name, other in others.items():
            found = fp._analyze(rgb, other, True, None, True)
            out[f"units_{name}"] = [list(u.box) for u in found]
            out[f"{name}_bits_off"] = [fp.hamming(a.fingerprint, b.fingerprint) for a, b in zip(units, found)]
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        box = fp.page_box(gray)
        out["page_box_whole_frame"] = list(box) if box is not None else None
        bounds = area.page_bounds(live)
        out["page_bounds_whole_frame"] = list(bounds) if bounds is not None else None
    except Exception as e:  # noqa: BLE001 - said by its type
        out["error"] = type(e).__name__
    return out


# ---------------------------------------------------------------------------------------------------- the report
def timeline(events: list[dict[str, Any]], offset: float) -> list[tuple[float, tuple[int, bool] | None, str]]:
    """What the stand-in showed from when: (t, screen or None for black, state), in the window's clock."""
    out: list[tuple[float, tuple[int, bool] | None, str]] = []
    screen: tuple[int, bool] | None = None
    for e in events:
        t = e["t"] + offset
        if e["ev"] == "draw":
            screen = (int(e["page"]), e["spread"] == "1")
            out.append((t, screen, e.get("state", "sharp")))
        elif e["ev"] == "black":
            out.append((t, None, "black") if e.get("on") == "1" else (t, screen, "after-black"))
        elif e["ev"] == "spinner" and e.get("on") == "1":
            out.append((t, (int(e["page"]), e["spread"] == "1"), "spinner"))
    return out


def at(line: list[tuple[float, Any, str]], t: float) -> tuple[Any, str]:
    found: tuple[Any, str] = (None, "none")
    for when, screen, state in line:
        if when > t:
            break
        found = (screen, state)
    return found


def screen_at(line: list[tuple[float, Any, str]], t: float) -> Any:
    """The stand-in's screen at *t*; in a black frame, the screen under it."""
    found = None
    for when, screen, _state in line:
        if when > t:
            break
        if screen is not None:
            found = screen
    return found


def flash_near(line: list[tuple[float, Any, str]], t: float, within_ms: float = 1000) -> bool:
    """Whether the stand-in showed black or a spinner at *t* or within *within_ms* before it."""
    return at(line, t)[1] in ("black", "spinner") or any(
        t - within_ms <= when <= t and state in ("black", "spinner") for when, _s, state in line)


def spread_of(values: list[int]) -> dict[str, Any]:
    return {"n": len(values), "median": median(values), "max": max(values, default=None),
            "over_250": sum(1 for v in values if v > 250), "over_500": sum(1 for v in values if v > 500),
            "over_1000": sum(1 for v in values if v > 1000)}


RUN_STATES = ("no run", "run reading", "run translating")


def run_state(modes: list[dict[str, Any]], t: float) -> str:
    """What a whole-book run did at *t*, as the window's modes tell (`Notes.mode`): "run reading" (it reads the pages
    the reader turns, and captures the viewer itself), "run translating" (the window follows the viewer beside it,
    `live.reads_beside`), "no run"."""
    found = None
    for m in modes:
        if m["t"] > t:
            break
        found = m
    if found is None or not found["run"]:
        return "no run"
    return "run translating" if found["beside"] else "run reading"


def turns_of(events: list[dict[str, Any]], offset: float, end: float) -> list[dict[str, Any]]:
    """The stand-in's turns: the screen, its soft and its sharp draw, the rest after it; the start's screen and a
    change of layout (the narrow window) as turns too."""
    turns: list[dict[str, Any]] = []
    for e in events:
        if e["ev"] != "draw":
            continue
        t, screen, why = e["t"] + offset, (int(e["page"]), e["spread"] == "1"), e.get("why")
        last = turns[-1] if turns else None
        if why in ("next", "previous", "jump") or (why in ("start", "resize") and (last is None or
                                                                                  last["screen"] != screen)):
            turns.append({"segment": e.get("segment") or "start", "screen": screen, "why": why, "soft_t": t,
                          "sharp_t": t if e.get("state") == "sharp" else None})
        elif last is not None and last["screen"] == screen and last["sharp_t"] is None and e.get("state") == "sharp":
            last["sharp_t"] = t
    for k, turn in enumerate(turns):
        turn["next_t"] = turns[k + 1]["soft_t"] if k + 1 < len(turns) else end
    return turns


def lettered_shown(d: dict[str, Any]) -> bool:
    """Whether the window showed lettering then: the finished picture (its lettering is in the picture, whatever the
    fill counted), or overlays on the page."""
    return d["kind"] == "final" or (d["kind"] in ("filling", "translated") and d["lettered"] > 0)


def ms(a: float | None, b: float | None) -> int | None:
    return None if a is None or b is None else round(a - b)


def old_page_times(displays: list[dict[str, Any]], scr: tuple[int, bool], lo: float, end: float
                   ) -> tuple[int | None, int | None]:
    """When the stand-in began a turn at *lo* to *scr* and the window showed another page: how long the window
    showed that page still, and how long with its lettering (None: the window showed no other page then; 0 for the
    lettering: none was on it)."""
    before = [d for d in displays if d["t"] <= lo]
    first = before[-1] if before else None
    if first is None or (first["page"], first["spread"]) == scr:
        return None, None
    old = (first["page"], first["spread"])
    after = [d for d in displays if d["t"] > lo]
    page_end = next((d["t"] for d in after if (d["page"], d["spread"]) != old), end)
    if not lettered_shown(first):
        return round(page_end - lo), 0
    lettering_end = next((d["t"] for d in after if (d["page"], d["spread"]) != old or not lettered_shown(d)), end)
    return round(page_end - lo), round(lettering_end - lo)


def lettered_unsettled_ms(displays: list[dict[str, Any]], scr: tuple[int, bool], sharp: float | None,
                          hi: float) -> int:
    """How long, after the stand-in drew *scr* sharp and before it turned on, the window showed lettering read from
    a frame of it that was not the sharp one (a page started on its soft frame, lettered on the blurry picture)."""
    if sharp is None:
        return 0
    total = 0.0
    for k, d in enumerate(displays):
        until = displays[k + 1]["t"] if k + 1 < len(displays) else hi
        a, b = max(d["t"], sharp), min(until, hi)
        if b > a and (d["page"], d["spread"]) == scr and lettered_shown(d) and d["from"] not in ("sharp", None):
            total += b - a
    return round(total)


def lettered_soft_ms(displays: list[dict[str, Any]], scr: tuple[int, bool], lo: float, hi: float) -> int:
    """How long, from the stand-in's first draw of *scr* at *lo* to its next turn at *hi*, the window showed lettering
    on a soft picture of *scr* (a page the cache holds, lettered before the viewer had drawn it sharp)."""
    total = 0.0
    for k, d in enumerate(displays):
        until = displays[k + 1]["t"] if k + 1 < len(displays) else hi
        a, b = max(d["t"], lo), min(until, hi)
        if b > a and (d["page"], d["spread"]) == scr and lettered_shown(d) and d["state"] == "soft":
            total += b - a
    return round(total)


def lettering_gone_ms(displays: list[dict[str, Any]], scr: tuple[int, bool], lo: float, hi: float) -> int:
    """How long, from the stand-in's first draw of *scr* at *lo* to its next turn at *hi*, the window showed *scr*
    without lettering between two pictures of it with lettering: lettering that left the page and came back (a page
    lettered on its soft picture, then shown as the sharp one came until that was read)."""
    total = pending = 0.0
    seen = False
    for k, d in enumerate(displays):
        if not lo <= d["t"] < hi:
            continue
        until = min(displays[k + 1]["t"] if k + 1 < len(displays) else hi, hi)
        if (d["page"], d["spread"]) != scr:
            pending = 0.0
        elif lettered_shown(d):
            total, pending, seen = total + pending, 0.0, True
        elif seen:
            pending += until - d["t"]
    return round(total)


def soft_lettering(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """The page jobs whose page was read from a soft frame and lettered, each against the next job on its screen at
    its frame's size whose page was read from the sharp frame: how many boxes each lettered, and how far the soft
    frame's boxes lie from where the sharp frame puts them, in pixels - the largest shift of an edge of a box from the
    sharp frame's box it overlaps most (a box that overlaps none is not counted; None: no such job came)."""
    from taslation.regions import box_iou

    done = sorted((j for j in jobs if j["result_t"] is not None and j.get("result_boxes")), key=lambda j: j["result_t"])
    rows = []
    for k, j in enumerate(done):
        if j["result_from"] != "soft":
            continue
        key = (j["page"], j["spread"], j["size"])
        sharp = next((o for o in done[k + 1:] if (o["page"], o["spread"], o["size"]) == key
                      and o["result_from"] == "sharp"), None)
        shifts = []
        for box in j["result_boxes"] if sharp is not None else ():
            other = max(sharp["result_boxes"], key=lambda o: box_iou(box, o))
            if box_iou(box, other) > 0:
                shifts.append(max(abs(a - b) for a, b in zip(box, other)))
        rows.append({"job": j["id"], "page": j["page"], "spread": j["spread"], "size": j["size"],
                     "boxes": len(j["result_boxes"]), "sharp_job": sharp["id"] if sharp is not None else None,
                     "sharp_boxes": len(sharp["result_boxes"]) if sharp is not None else None,
                     "shift_px": max(shifts) if shifts else None, "shifts_px": shifts})
    return {"jobs": len(rows), "shift_px": dist([r["shift_px"] for r in rows]),
            "box_shift_px": dist([s for r in rows for s in r["shifts_px"]]),
            "boxes": sum(r["boxes"] for r in rows), "sharp_boxes": sum(r["sharp_boxes"] or 0 for r in rows),
            "unmatched": sum(1 for r in rows if r["shift_px"] is None), "list": rows}


def status_of_another_page(lines: list[dict[str, Any]], scr: tuple[int, bool], lo: float, hi: float
                           ) -> tuple[int, str | None, int]:
    """How the status line spoke of another page than *scr* in a turn from *lo* to *hi* (the stand-in's first draw of
    *scr* to its next turn; *lines*: `Notes.status_lines`): how long the line on at *lo*, of a page before, stayed (0:
    it spoke of no page, or of *scr*; a line of no page or of *scr* ends it) and its kind, and how long lines of
    another page were on in all."""
    def other(s: dict[str, Any]) -> bool:
        return s["page"] is not None and tuple(s["page"]) != tuple(scr)

    before = [s for s in lines if s["t"] <= lo]
    first = before[-1] if before else None
    stayed, kind = 0, None
    if first is not None and other(first):
        kind = first["kind"]
        stayed = round(min(next((s["t"] for s in lines if s["t"] > lo and not other(s)), hi), hi) - lo)
    total = 0.0
    for k, s in enumerate(lines):
        a, b = max(s["t"], lo), min(lines[k + 1]["t"] if k + 1 < len(lines) else hi, hi)
        if b > a and other(s):
            total += b - a
    return stayed, kind, round(total)


def resize_rows(events: list[dict[str, Any]], offset: float, notes: Notes, turns: list[dict[str, Any]],
                rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per change of the stand-in's window size after the window's first capture (its "size" line), from its draw of
    the new layout, numbers: to the window's first capture of another size, to the first moment the window read that
    frame by its own capture area, and by its own area in force too (`Notes.area`); the captures that took over
    LONG_CAPTURE_MS within 3 s; whether a page job ran, and how long the old layout's lettering stayed (the turn's
    `old_lettering_ms`)."""
    out = []
    for k, e in enumerate(events):
        if e["ev"] != "size":
            continue
        t = e["t"] + offset
        draw = next((d["t"] + offset for d in events[k:] if d["ev"] == "draw" and d.get("why") == "resize"), t)
        before = [c for c in notes.captures if c["t"] <= t]
        if not before:
            continue  # (the stand-in's own size at the start: nothing of another size was captured yet)
        old = before[-1]["size"]
        new = next((c for c in notes.captures if c["t"] > t and c["size"] != old), None)
        size = new["size"] if new is not None else None
        read = next((m["t"] for m in notes.margins if m["t"] > t and m["size"] == size and m["read"] == m["own"]), None)
        own = next((m["t"] for m in notes.margins if m["t"] > t and m["size"] == size and m["margins"] == m["own"]),
                   None)
        turn = next((r for r, w in zip(rows, turns) if w["why"] == "resize" and abs(w["soft_t"] - draw) < 50), None)
        out.append({"from_t": round(draw), "size_before": old, "size_after": size,
                    "first_capture_ms": ms(new["t"], draw) if new is not None else None,
                    "read_by_own_area_ms": ms(read, draw), "own_area_in_force_ms": ms(own, draw),
                    "long_captures_ms": [round(m) for when, m in notes.long_captures if t <= when <= t + 3000],
                    "job_running": turn["job_at_turn"] if turn else None,
                    "old_lettering_ms": turn["old_lettering_ms"] if turn else None})
    return out


def across_sizes(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """The page jobs on a sharp frame of a page the cache held as it was stored at another frame size only (by page
    jobs done before this one began that stored all of their screen, at sizes other than this frame's; a page the
    cache gave a job stays stored where it was), each page of the screen so: right after a change of the window's size
    (the screen on show as the size changed, no other shown at the new size before it) or on a turn back to the page
    later, as often as it comes. Per job, the units the cache gave and did not and
    the requests sent - for nothing: the page was held. A single page held as a page of a spread (the narrow window),
    or the other way round, is told apart ("layout")."""
    held: list[tuple[float, int, bool, tuple[int, int]]] = []  # (done, page, in a spread, frame size)
    rows: list[dict[str, Any]] = []
    size_before, since = None, []  # the size of the sharp frames before, and the screens shown at it since it came
    for j in sorted(jobs, key=lambda j: j["t_s"]):
        size = tuple(j["size"]) if j.get("size") else None
        pages = [j["page"], j["page"] + 1] if j["spread"] else [j["page"]]
        if j["frame"] == "sharp" and size is not None and j["page"] is not None:
            screen = (j["page"], bool(j["spread"]))
            if size != size_before:
                since = []
            earlier = [[(spread, s) for done, p, spread, s in held if p == page and done <= j["t_s"]] for page in pages]
            if all(earlier) and all(s != size for found in earlier for _spread, s in found):
                layouts = {spread for found in earlier for spread, _s in found}
                rows.append({"id": j["id"], "t_s": j["t_s"], "page": j["page"], "spread": j["spread"],
                             "size": list(size),
                             "held_at": [list(s) for s in sorted({s for found in earlier for _x, s in found})],
                             "layout": "same" if layouts == {bool(j["spread"])} else "spread/single",
                             "why": "size change" if all(s == screen for s in since) else "turn back",
                             "unit_hits": j.get("cache_hits"), "unit_misses": j.get("cache_misses"),
                             "requests": j["requests"]})
            since.append(screen)
            size_before = size
        units = 2 if j["spread"] else 1
        if size is not None and j["page"] is not None and j.get("done_s") is not None and \
                (j.get("stored") or j.get("stored_at_cancel") or 0) >= units:
            held.extend((j["done_s"], page, bool(j["spread"]), size) for page in pages)

    def total(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {"jobs": len(items), "unit_hits": sum(r["unit_hits"] or 0 for r in items),
                "unit_misses": sum(r["unit_misses"] or 0 for r in items), "requests": sum(r["requests"] for r in items)}

    return {**total(rows),
            "by_layout": {k: total([r for r in rows if r["layout"] == k]) for k in ("same", "spread/single")},
            "by_why": {k: total([r for r in rows if r["why"] == k]) for k in ("size change", "turn back")},
            "list": rows}


def wasted_why(job: dict[str, Any] | None) -> str | None:
    """Why the requests of the page job *job* were sent for nothing (None: they were not): its frame was not the sharp
    one ("soft": soft, a spinner, black or a frame without the stand-in's code), or what it did was dropped
    ("dropped": its frame changed before it was kept, and everything it did went back)."""
    if job is None:
        return None
    if job["state"] != "sharp":
        return "soft"
    if job.get("discarded"):
        return "dropped"
    return None


def finishing_job(jobs: list[dict[str, Any]], scr: tuple[int, bool], lo: float, hi: float) -> dict[str, Any] | None:
    """The page job that finished the turn's page: of the jobs started on its screen while the stand-in showed it,
    the last whose result came and was not dropped."""
    mine = [j for j in jobs if j["started"] and lo <= j["t"] < hi and (j["page"], j["spread"]) == scr
            and j["result_t"] is not None and j.get("discarded") is not True]
    return mine[-1] if mine else None


def wasted_requests(requests: list[dict[str, Any]], jobs: list[dict[str, Any]], cancels: list[float],
                    end: float) -> list[dict[str, Any]]:
    """Each request sent for nothing (`wasted_why`), as numbers: how long it ran and how it ended, when the live view
    cancelled its job (the first cancel within it) and how long the request ran on after that, and the next request
    that was not sent for nothing - how long after this one's end it went out and how long it waited at the server
    (`server_wait`: a server still busy with this one would make it wait)."""
    by_id = {j["id"]: j for j in jobs}
    real = [r for r in requests if r["job"] is not None and wasted_why(by_id.get(r["job"])) is None]
    out = []
    for r in requests:
        job = by_id.get(r["job"]) if r["job"] is not None else None
        why = wasted_why(job)
        if why is None:
            continue
        stop = r["end_t"] if r["end_t"] is not None else end
        cancel = next((c for c in sorted(cancels) if r["t"] <= c <= stop), None)
        nxt = next((q for q in real if q["t"] >= r["t"]), None)
        out.append({"t": r["t"], "job": r["job"], "why": why, "frame": r["frame"], "gate": r["gate"],
                    "outcome": r["outcome"], "ran_ms": ms(stop, r["t"]),
                    "ran_on_after_cancel_ms": ms(stop, cancel),
                    "next_real_after_ms": ms(nxt["t"], stop) if nxt is not None else None,
                    "next_real_server_wait_ms": server_wait(nxt) if nxt is not None else None})
    return out


def readings_on_a_miss(resolves: list[dict[str, Any]], rel: Callable[[Any], Any]) -> dict[str, Any]:
    """The page jobs' looks for page units the cache did not hold as found (`Notes.resolved`): how many there were,
    how many went through readings and found a unit so, the time those took and the readings they went through
    (all of them for a page the cache holds at no size), each with its time in the run (*rel*)."""
    ran = [r for r in resolves if r["readings"] is not None]
    return {"looks": len(resolves), "with_readings": len(ran), "found": sum(1 for r in ran if r["replaced"]),
            "ms": dist([r["ms"] for r in ran]), "readings": dist([r["readings"] for r in ran]),
            "ms_when_found": dist([r["ms"] for r in ran if r["replaced"]]),
            "list": [{**{k: v for k, v in r.items() if k != "t"}, "t_s": rel(r["t"])} for r in ran]}


def line_id(secret: bytes, scope: str, digest: str) -> str:
    """A kept line as this tool's notes name it: its ring's secret, its scope and its digest (`linememo.Ring`) hashed
    together, so that neither the line nor the book's secret is held in the notes or written anywhere."""
    return hashlib.sha256(b"\0".join((secret, scope.encode("utf-8", "surrogatepass"), digest.encode("ascii")))
                          ).hexdigest()[:32]


def cache_at_end(settings: Any) -> dict[str, Any]:
    """The book's cache as the window left it on disk, read once the window has closed: its page units' fingerprints
    and its kept lines (`line_id`) - or the type of what went wrong."""
    try:
        from taslation.cache import CacheStore

        book = CacheStore(settings.cache_dir).open(BOOK, PLAMO, "English")
        return {"units": {page.fingerprint for page in book.pages},
                "lines": {line_id(ring.secret, name, digest) for ring in book.lines.rings
                          for name, entries in ring.scopes.items() for digest in entries}}
    except Exception as e:  # noqa: BLE001 - said by its type
        return {"error": type(e).__name__}


DECIDE_SLACK_MS = 20  # a page kept for now decided this close to the end of its open time: its time was up (the clocks)


def left_why(job: dict[str, Any], sharp_seen: float | None, decide: dict[str, Any] | None) -> str:
    """Why something *job* stored (on a frame that was not the sharp one) is in the cache at the end: no sharp frame
    of its page was captured after it; it had no gate (not started early); its gate was dropped, and yet (what putting
    a job back must never leave); its confirmation was not taken back though the sharp frame came while it ran or
    within its open time; it was kept for good as it ended (no open time: a viewer not yet seen drawing soft first);
    kept for now, it was decided for good before its open time was up and before the sharp frame came (*decide*:
    `Notes.decided`, by the job that came next); the sharp frame came after its open time."""
    if sharp_seen is None:
        return "no sharp frame"
    if not job.get("gate"):
        return "no gate"
    if job.get("gate_final") != "confirmed":
        return "put back, yet left"
    over = job.get("over_t")
    if over is None or sharp_seen <= over:
        return "sharp frame not taken back"
    if not job.get("open_for"):
        return "viewer not yet seen drawing soft first"
    until = job.get("open_until_t")
    if (decide is not None and decide["kept"] and until is not None
            and decide["t"] < min(until - DECIDE_SLACK_MS, sharp_seen)):
        return "decided by another job"
    if until is not None and sharp_seen >= until:
        return "later than the open time"
    return "sharp frame not taken back"


def soft_frames_at_end(jobs: list[dict[str, Any]], turns: list[dict[str, Any]], captures: list[dict[str, Any]],
                       decides: list[dict[str, Any]], cache_end: dict[str, Any] | None,
                       rel: Callable[[Any], Any]) -> dict[str, Any]:
    """The page jobs on a frame that was not the sharp one, by what is true at the end of the run: those on a soft
    frame whose frame was confirmed (at any time: ``confirmed_ever``, `Notes.gates_at_end`); of them, those whose
    confirmation the window took back (`PageGate.take_back`) while they ran (their gate dropped as they ended) or
    after them (kept for now: confirmed as they ended); and every job with something of its own in the cache the
    window left on disk (*cache_end*: `cache_at_end`) - a page unit it said it stored anew, a kept line it put first,
    neither stored anew by a later job (which it would not have been, had it still been there). Each of those is told
    with its page, how late the window captured the sharp frame of its page after the stand-in drew it, and why
    (`left_why`); none must be left where that sharp frame came."""
    started = [j for j in jobs if j["started"]]
    confirmed = [j for j in started if j["state"] == "soft" and j.get("confirmed_ever")]
    taken_back = [j for j in confirmed if j.get("gate_final") == "dropped"]
    out: dict[str, Any] = {
        "confirmed": len(confirmed),
        "taken_back": {"while_running": sum(1 for j in taken_back if j["gate_end"] == "dropped"),
                       "after_the_job": sum(1 for j in taken_back if j["gate_end"] == "confirmed")},
        "left_in_the_cache": None, "left_though_the_sharp_frame_came": None, "left": [],
        "cache": "not read" if cache_end is None else cache_end.get("error", "read")}
    if cache_end is None or "error" in cache_end:
        return out
    for job in started:
        if job["state"] == "sharp":
            continue
        later = [j for j in started if j["id"] > job["id"]]
        units = [u for u in job.get("units") or () if u in cache_end["units"]
                 and not any(u in (j.get("units") or ()) for j in later)]
        lines = [line for line in job.get("line_ids") or () if line in cache_end["lines"]
                 and not any(line in (j.get("line_ids") or ()) for j in later)]
        if not units and not lines:
            continue
        screen = (job["page"], bool(job["spread"]))
        turn = next((t for t in turns if t["soft_t"] <= job["t"] < t["next_t"] and t["screen"] == screen), None)
        end = turn["next_t"] if turn is not None else math.inf
        sharp_seen = next((c["t"] for c in captures if job["t"] <= c["t"] < end and c["state"] == "sharp"
                           and (c["page"], bool(c["spread"])) == screen), None)
        decide = next((d for d in reversed(decides) if d["job"] == job["id"]), None)
        out["left"].append({
            "id": job["id"], "t_s": rel(job["t"]), "page": job["page"], "spread": job["spread"],
            "frame": job["state"], "units_left": len(units), "lines_left": len(lines),
            "sharp_captured_late_ms": ms(sharp_seen, turn["sharp_t"]) if turn is not None else None,
            "why": left_why(job, sharp_seen, decide), "decided_by": decide["by"] if decide is not None else None})
    out["left_in_the_cache"] = len(out["left"])
    out["left_though_the_sharp_frame_came"] = sum(1 for r in out["left"] if r["why"] != "no sharp frame")
    return out


def server_wait(r: dict[str, Any]) -> int | None:
    """How long a request waited beyond the model's work for it (its HTTP exchange less Ollama's load, prompt and
    answer durations; not less its total_duration, which takes in a wait behind another request): the wait for the
    server, the server's own handling, and the way to it and back."""
    if r.get("http_t") is None or r.get("http_end_t") is None or not r.get("work_ms"):
        return None
    return round(r["http_end_t"] - r["http_t"] - r["work_ms"])


def dist(values: list[Any]) -> dict[str, Any]:
    """A spread of values (None left out): how many, the smallest, the quartiles, the median, the largest."""
    kept = sorted(v for v in values if v is not None)
    if not kept:
        return {"n": 0}

    def q(p: float) -> int:
        return round(kept[min(len(kept) - 1, int(p * (len(kept) - 1) + 0.5))])

    return {"n": len(kept), "min": round(kept[0]), "p25": q(0.25), "median": round(statistics.median(kept)),
            "p75": q(0.75), "max": round(kept[-1])}


def turn_rows(turns: list[dict[str, Any]], notes: Notes, end: float) -> list[dict[str, Any]]:
    """Per turn of the stand-in, numbers: the times are from the stand-in's draw of the turn's sharp frame (its own
    clock, put on the window's by the least latency of its console lines: `summarise`) to the window's first
    request for the job that finished the page (`finishing_job`), its first picture of the page with lettering on
    it, and its finished page."""
    rows = []
    started = [j for j in notes.jobs if j["started"]]
    for k, turn in enumerate(turns):
        scr, lo, hi = turn["screen"], turn["soft_t"], turn["next_t"]
        sharp = turn["sharp_t"]
        old_page_ms, old_lettering_ms = old_page_times(notes.displays, scr, lo, end)
        mine = [d for d in notes.displays if lo <= d["t"] < hi and (d["page"], d["spread"]) == scr]
        lettered = next((d["t"] for d in mine if lettered_shown(d)), None)
        lettered_sharp = next((d["t"] for d in mine if lettered_shown(d) and d["from"] == "sharp"), None)
        finished = next((d["t"] for d in mine if d["kind"] == "final" or (d["kind"] == "translated" and d["lettered"])),
                        None)
        empty = next((d["t"] for d in mine if d["kind"] == "translated" and not d["lettered"]), None)
        shown = next((d["t"] for d in mine), None)
        before = [d for d in notes.displays if d["t"] < hi - 1]
        rest = before[-1] if before else None
        if rest is None:
            at_rest = "nothing"
        elif (rest["page"], rest["spread"]) != scr:
            at_rest = "another page"
        else:
            at_rest = {"translated": "translated", "final": "translated", "filling": "filling",
                       "reading": "being read", "live": "untranslated"}[rest["kind"]]
        jobs = [j for j in notes.jobs if j["started"] and lo <= j["t"] < hi and (j["page"], j["spread"]) == scr]
        seen_sharp = next((c["t"] for c in notes.captures if c["t"] >= lo and (c["page"], c["spread"]) == scr
                           and c["state"] == "sharp"), None)
        last = finishing_job(notes.jobs, scr, lo, hi)
        first_request = min((r["t"] for r in notes.requests if last is not None and r["job"] == last["id"]),
                            default=None)
        mine_requests = [r for r in notes.requests if any(r["job"] == j["id"] for j in jobs)]
        status_stayed, status_kind_, status_other = status_of_another_page(notes.status_lines, scr, lo, hi)
        rows.append({
            "n": k, "segment": turn["segment"], "page": scr[0], "spread": scr[1], "why": turn["why"],
            "soft_to_sharp_ms": ms(sharp, lo), "rest_ms": ms(hi, sharp), "captured_sharp_ms": ms(seen_sharp, sharp),
            "shown_ms": ms(shown, sharp), "first_request_ms": ms(first_request, sharp),
            "first_lettered_ms": ms(lettered, sharp), "finished_ms": ms(finished, sharp),
            "finishing_job": last["id"] if last is not None else None,
            "finishing_job_on": last["state"] if last is not None else None,
            "wasted_requests": sum(1 for r in mine_requests
                                   if wasted_why(next(j for j in jobs if j["id"] == r["job"])) is not None),
            "empty_result_shown_ms": ms(empty, sharp),
            "at_rest": at_rest, "at_rest_from": rest.get("from") if rest else None,
            "at_rest_lettered": rest.get("lettered") if rest else None,
            "jobs": len(jobs), "jobs_on": dict(Counter(j["state"] for j in jobs)),
            "requests": sum(j["requests"] for j in jobs),
            "jobs_discarded": sum(1 for j in jobs if j.get("discarded")),
            "job_at_turn": any(j["t"] <= lo < (j["done_t"] or end) for j in started),
            "run": run_state(notes.modes, lo),
            "old_page_ms": old_page_ms, "old_lettering_ms": old_lettering_ms,
            "lettered_unsettled_ms": lettered_unsettled_ms(notes.displays, scr, sharp, hi),
            "lettered_soft_ms": lettered_soft_ms(notes.displays, scr, lo, hi),
            # a page the cache held whole (its jobs drew it all from the cache, none read a page unit anew): its
            # lettering from the turn, the first read from the sharp frame, and lettering that left and came back
            "cached": any(j.get("cache_hits") for j in jobs) and not any(j.get("cache_misses") for j in jobs),
            "lettered_from_turn_ms": ms(lettered, lo), "lettered_sharp_from_turn_ms": ms(lettered_sharp, lo),
            "lettering_gone_ms": lettering_gone_ms(notes.displays, scr, lo, hi),
            "status_old_page_ms": status_stayed, "status_old_page_kind": status_kind_,
            "status_other_page_ms": status_other,
        })
    return rows


def incidents(notes: Notes, line: list[tuple[float, Any, str]], end: float) -> dict[str, list[dict[str, Any]]]:
    """Stretches where the window's page area showed another screen than the stand-in (black aside): with lettering
    on it longer than STALE_MS (an overlay left behind), any longer than LAG_MS (the window did not follow)."""
    stale: list[dict[str, Any]] = []
    lag: list[dict[str, Any]] = []
    points = sorted({t for t, _s, _st in line} | {d["t"] for d in notes.displays} | {end})
    shows = notes.displays
    spell: dict[str, Any] | None = None

    def close(spell: dict[str, Any] | None) -> None:
        if spell is None:
            return
        length = spell["to"] - spell["from"]
        item = {"from_t": round(spell["from"]), "ms": round(length), "window": list(spell["key"][:2]),
                "standin": list(spell["key"][2]), "lettered": spell["key"][3]}
        if spell["key"][3] and length > STALE_MS:
            stale.append(item)
        elif length > LAG_MS:
            lag.append(item)

    j = 0
    for a, b in zip(points, points[1:]):
        while j + 1 < len(shows) and shows[j + 1]["t"] <= a:
            j += 1
        if not shows or shows[j]["t"] > a:
            continue
        d = shows[j]
        screen, state = at(line, a)
        differs = screen is not None and state != "black" and (d["page"], d["spread"]) != screen
        lettered = lettered_shown(d)
        key =(d["page"], d["spread"], screen, lettered) if differs else None
        if spell is not None and spell["key"] == key:
            spell["to"] = b
            continue
        close(spell)
        spell = {"key": key, "from": a, "to": b} if key is not None else None
    close(spell)
    return {"stale_overlays": stale, "not_following": lag}


def median(values: list[int | None]) -> int | None:
    kept = [v for v in values if v is not None]
    return round(statistics.median(kept)) if kept else None


def segment_table(rows: list[dict[str, Any]], spells: dict[str, list[dict[str, Any]]],
                  segment_at: Callable[[float], str]) -> list[dict[str, Any]]:
    out = []
    names = list(dict.fromkeys(r["segment"] for r in rows))
    for name in names:
        mine = [r for r in rows if r["segment"] == name]
        rested = [r for r in mine if (r["rest_ms"] or 0) >= REST_MS]
        out.append({
            "segment": name, "turns": len(mine), "rested": len(rested),
            "first_request_ms_median": median([r["first_request_ms"] for r in rested]),
            "first_request_ms_max": max([r["first_request_ms"] for r in rested if r["first_request_ms"] is not None],
                                        default=None),
            "first_lettered_ms_median": median([r["first_lettered_ms"] for r in rested]),
            "first_lettered_ms_max": max([r["first_lettered_ms"] for r in rested if r["first_lettered_ms"] is not None],
                                         default=None),
            "finished_ms_median": median([r["finished_ms"] for r in rested]),
            "finished_ms_max": max([r["finished_ms"] for r in rested if r["finished_ms"] is not None], default=None),
            "translated_at_rest": sum(1 for r in rested if r["at_rest"] == "translated"),
            "at_rest_from_soft": sum(1 for r in rested
                                     if r["at_rest"] == "translated" and r["at_rest_from"] != "sharp"),
            "jobs": sum(r["jobs"] for r in mine),
            "requests": sum(r["requests"] for r in mine),
            "wasted_requests": sum(r["wasted_requests"] for r in mine),
            "stale": len([s for s in spells["stale_overlays"] if segment_at(s["from_t"]) == name]),
            "not_following": len([s for s in spells["not_following"] if segment_at(s["from_t"]) == name]),
        })
    return out


def log_facts(state: Path) -> dict[str, Any]:
    """The app's log in the scratch state: how many tracebacks, warnings and errors, and the exception type names
    in it (nothing else of a line)."""
    counts: Counter[str] = Counter()
    types: Counter[str] = Counter()
    for path in sorted(state.glob("log.txt*")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith("Traceback"):
                counts["tracebacks"] += 1
            for level in (" WARNING ", " ERROR ", " CRITICAL "):
                if level in line[:40]:
                    counts[level.strip().lower()] += 1
            match = re.match(r"^\s*((?:[A-Za-z_][\w]*\.)*[A-Z][\w]*(?:Error|Exception|Interrupt|Exit))\b", line)
            if match:
                types[match.group(1).rsplit(".", 1)[-1]] += 1
    return {"lines": dict(counts), "exception_types": dict(types)}


# ---------------------------------------------------------------------------------------------------- the run
def run(args: argparse.Namespace) -> int:
    out = args.out.resolve()
    if out.is_relative_to(ROOT) or out.is_relative_to(REAL_STATE):
        raise SystemExit("--out is a scratch folder: not in the repository, not in ~/.taslation")
    out.mkdir(parents=True, exist_ok=True)
    state = out / "state"
    standin_dir = out / "standin"
    for folder in (state, standin_dir):
        if folder.exists():
            raise SystemExit(f"{folder} is there from a run before: delete it, or give another --out")
    state.mkdir()
    standin_dir.mkdir()
    os.environ["TASLATION_STATE_DIR"] = str(state)  # (before TASlation is imported: nothing finds ~/.taslation)
    os.environ.pop("SELFTRANS_STATE_DIR", None)
    models = args.models or os.environ.get("TASLATION_MODELS_DIR") or ""
    if not models:
        guess = [ROOT / "models", ROOT.parent / "models", Path("C:/Temp/CleranTrans/models")]
        models = str(next((g for g in guess if g.is_dir()), ""))
    if not models or not Path(models).is_dir():
        raise SystemExit("set TASLATION_MODELS_DIR (or --models) to the folder of the installed models")
    os.environ["TASLATION_MODELS_DIR"] = models

    names = wanted(args.scenario)
    count = pages_needed(names)
    report: dict[str, Any] = {"scenarios": names, "seed": args.seed, "front": args.front, "scale": args.scale}
    pictures: list[Any] | None = None if args.synthetic else dataset_pages(args.series, args.first, count)
    report["pages"] = "dataset" if pictures else "synthetic"
    if not pictures:
        pictures = synthetic_pages(count)
    cancel_first = None
    if "x" in names:  # the screens of little text, after the others (a spread's first page at an even place)
        extra = little_text_pages(pictures, 2 * CANCEL_SCREENS) if report["pages"] == "dataset" else []
        if len(extra) == 2 * CANCEL_SCREENS:
            pictures = pictures[:len(pictures) - len(pictures) % 2]
            cancel_first = len(pictures)
            pictures = [*pictures, *extra]
        else:
            names.remove("x")
            report["x_left_out"] = "needs the dataset's pages of little text"
    count = len(pictures)
    segments, steps = build_plan(names, count, cancel_first, args.cancel_soft_ms)
    sv.write_page_list(standin_dir, pictures)
    sv.write_control(standin_dir, 0)
    report["page_count"] = count

    found = sv.find_browser(args.browser)
    if found is None:
        raise SystemExit("neither Chrome nor Edge is installed here")
    report["browser"] = found[0]

    url = "http://127.0.0.1:11434"
    canned: Canned | None = None
    ps_before: list[str] | None = None
    mode = "canned" if args.canned else "real"
    if not args.canned:
        tags = ollama_get(url, "/api/tags")
        names_there = [str(m.get("name", "")) for m in (tags or {}).get("models", [])] if isinstance(tags, dict) else []
        if not any(n.split(":")[0] == PLAMO for n in names_there):
            mode = "canned (Ollama did not answer, or has no PLaMo)"
        else:
            ps_before = loaded_models(url)
    if mode != "real":
        canned = Canned(args.canned_load_s, args.canned_ms)
        url = canned.url
    report["translator"] = mode
    report["ollama_loaded_before"] = ps_before

    sys.path.insert(0, str(ROOT))
    import taslation
    from taslation.capture import enable_dpi_awareness

    if not Path(taslation.__file__).resolve().is_relative_to(ROOT):
        raise SystemExit(f"taslation comes from {taslation.__file__}, not from {ROOT}: set PYTHONPATH")
    enable_dpi_awareness()
    standin_rect, app_rect = Monitors().places()
    narrow_rect = (standin_rect[0], standin_rect[1], NARROW_SIZE[0], NARROW_SIZE[1])
    token = "t" + secrets.token_hex(5)
    page = sv.page_url(token, steps, standin_dir, seed=args.seed)
    browser = sv.StandinBrowser(found[1], page, standin_dir / "profile", standin_rect, token, args.scale)
    closed: dict[str, Any] = {}
    try:
        hwnd = browser.wait_window()
        ready = browser.wait_event("ready", 30)
        since = len(browser.said())
        place_own(hwnd, standin_rect, top=True)
        ready = placed_view(browser, ready, since)
        report["run"] = run_app(args, report, browser, hwnd, ready, segments, out, standin_dir, url, app_rect,
                                narrow_rect, mode)
    except Exception as e:  # noqa: BLE001 - said (its type and where, no value), then everything is closed
        traceback.print_exc()
        report["run"] = {"failed": f"{type(e).__name__} in the driver"}
    finally:
        if canned is not None:
            canned.stop()
            report["canned_requests"] = dict(canned.counts)
        closed = browser.close()
    report["cleanup"] = cleanup(report, closed, state, standin_dir, mode, url if mode == "real" else "", ps_before)
    path = out / "report.json"
    path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print_table(report, path)
    return 0 if not report["run"].get("failed") else 1


def run_app(args: argparse.Namespace, report: dict[str, Any], browser: sv.StandinBrowser, hwnd: int,
            ready: dict[str, str], segments: list[Segment], out: Path, standin_dir: Path, url: str,
            app_rect: tuple[int, int, int, int], narrow_rect: tuple[int, int, int, int], mode: str) -> dict[str, Any]:
    import demo_video

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
    area = (AREA[0], round(AREA[1] * args.scale), AREA[2], AREA[3])  # (the reader's area, set at their scale)
    report["area"] = list(area)
    sv.write_control(standin_dir, 0, band=round((area[1] - top) / dpr))
    selection = sv.SelectionGuard(hwnd)
    pid = next(p for w, p in sv.top_windows() if w == hwnd)

    def viewer_info() -> Any:
        if not guard.is_viewer(hwnd) or pid not in browser.tree:
            return None
        return WindowInfo(hwnd, sv.window_text(hwnd), window_class(hwnd), pid, window_rect(hwnd), program_name(pid))

    notes = Notes(top, dpr)
    hotkeys = HotKeys(notes)
    patched = install(notes, args, guard, viewer_info, hotkeys)
    state = demo_video.scratch_state()
    info = viewer_info()
    remember_role(state, BOOK, "reader")
    profiles = Profiles(state / "profiles.json")
    profiles.set_margins(info, area)
    profiles.set_margins(info, area, large=True)
    settings = Settings(state_dir=state, ui_language="en", target_language="English", over_book=False,
                        flash_when_done=False, sound_when_done=False, always_on_top=False, ui_scale=args.scale,
                        models_dir=Path(os.environ["TASLATION_MODELS_DIR"]), ollama_url=url)
    settings.validate()
    errorlog.setup(settings)
    tap = LogTap(notes)
    logging.getLogger().addHandler(tap)
    netguard.install(settings.ollama_port)  # nothing but the translator's port on this computer, as the window has it
    app = app_mod.App(settings, window_query=browser.token, book=BOOK, auto=True)
    queue_put = app._events.put

    def tagged(item: Any, *a: Any, **k: Any) -> Any:
        notes.tag(item)
        return queue_put(item, *a, **k)

    app._events.put = tagged  # type: ignore[method-assign]
    status_set = app.status_var.set

    def status_said(value: Any) -> Any:  # the status line set: told once the window's record of it is complete
        out = status_set(value)
        t = now_ms()
        app.after_idle(lambda: notes.status_line(app, t))
        return out

    app.status_var.set = status_said  # type: ignore[method-assign]
    callback = app.report_callback_exception

    def tk_error(kind: Any, value: Any, tb: Any) -> None:
        notes.error("tk callback", getattr(kind, "__name__", "?"))
        callback(kind, value, tb)

    app.report_callback_exception = tk_error  # type: ignore[method-assign]
    x, y, w, h = app_rect
    app.geometry(f"{w}x{h}+{x}+{y}")
    app.after(600, lambda: app.geometry(f"{w}x{h}+{x}+{y}"))
    director = Director(app, browser, guard, selection, notes, segments, args, out, standin_dir, narrow_rect,
                        app_rect, hotkeys)
    director.start()
    began = now_ms()
    try:
        app.mainloop()
    finally:
        ended = now_ms()
        if director.failed and director.selection.stopped:
            try:
                app.destroy()  # (another window was chosen: nothing more is done with it)
            except Exception:  # noqa: BLE001
                pass
        else:
            demo_video.finish_app(app)
        director.close_saver()
        logging.getLogger().removeHandler(tap)
    return summarise(director, notes, tap, browser, patched, guard, began, ended, top, dpr, mode,
                     cache_at_end(settings))


def summarise(director: Director, notes: Notes, tap: LogTap, browser: sv.StandinBrowser, patched: dict[str, Any],
              guard: Any, began: float, ended: float, top: int, dpr: float, mode: str,
              cache_end: dict[str, Any]) -> dict[str, Any]:
    """The report's run, from the notes once the window has closed; *cache_end*: the cache it left (`cache_at_end`)."""
    notes.gates_at_end()
    events = director.events
    lat = [e["recv"] - e["t"] for e in events]
    offset = min(lat) if lat else 0.0
    line = timeline(events, offset)
    turns = turns_of(events, offset, ended)
    rows = turn_rows(turns, notes, ended)
    spells = incidents(notes, line, ended)

    def segment_at_t(t: float) -> str:
        seg = "start"
        for turn in turns:
            if turn["soft_t"] <= t:
                seg = turn["segment"]
        return seg

    table = segment_table(rows, spells, segment_at_t)
    loads = []
    for a, b in notes.loads:
        inside = [o for o in notes.ocr if a <= o["t"] <= (b or ended)]
        before = [o for o in notes.ocr if o["t"] < a]
        devices_in = sorted({tuple(o["engines"]) for o in inside}
                            | ({tuple(before[-1]["engines"])} if before else set()))
        loads.append({"from_t": round(a), "ms": round((b or ended) - a), "segment": segment_at_t(a),
                      "readers_on": [list(d) for d in devices_in]})
    jobs = notes.jobs
    started = [j for j in jobs if j["started"]]
    requests = notes.requests

    def rel(t: float | None) -> float | None:
        return None if t is None else round((t - began) / 1000, 2)

    for row, turn in zip(rows, turns):
        row["t_s"] = rel(turn["soft_t"])
    for items in spells.values():
        for item in items:
            item["from_s"] = rel(item["from_t"])
    for load in loads:
        load["from_s"] = rel(load.pop("from_t"))
    job_list = [{"id": j["id"], "t_s": rel(j["t"]), "page": j["page"], "spread": j["spread"], "frame": j["state"],
                 "size": j["size"], "gate": j["gate"], "gate_end": j["gate_end"], "requests": j["requests"],
                 "lettered_events": j["translated"],
                 "first_lettered_s": rel(j["first_translated_t"]), "result_s": rel(j["result_t"]),
                 "result_translated": j["result_translated"], "result_from": j["result_from"],
                 "result_boxes": j.get("result_boxes"),
                 "cache_hits": j.get("cache_hits"), "cache_misses": j.get("cache_misses"),
                 "stored": j.get("stored"), "stored_at_cancel": j.get("stored_at_cancel"),
                 "cancelled_s": rel(j["cancelled_t"]), "discarded": j["discarded"], "done_s": rel(j["done_t"])}
                for j in started]
    kept_soft = [j for j in job_list if j["frame"] != "sharp" and j["discarded"] is not True
                 and (j["gate_end"] == "confirmed" or not j["gate"]) and (j["stored"] or j["stored_at_cancel"])]
    cancels = []
    sizes = [e["t"] + offset for e in events if e["ev"] == "size"]
    for j in started:  # each page job cancelled: was its page still the stand-in's then (a black frame aside)?
        if j["cancelled_t"] is None:
            continue
        screen = screen_at(line, j["cancelled_t"])
        cancels.append({"id": j["id"], "t_s": rel(j["cancelled_t"]), "segment": segment_at_t(j["cancelled_t"]),
                        "frame": j["state"], "gate_end": j["gate_end"],
                        "page_on_show": screen == (j["page"], j["spread"]),
                        "flash_or_spinner_within_1s": flash_near(line, j["cancelled_t"]),
                        "resize_within_1s": any(j["cancelled_t"] - 1000 <= s <= j["cancelled_t"] for s in sizes)})
    # (a job on a frame of the size before gives way to the new size's frame of the same page: no false cancel)
    false_cancels = [c for c in cancels if c["page_on_show"] and c["frame"] == "sharp"
                     and c["gate_end"] in ("confirmed", None) and not c["resize_within_1s"]]
    old_lettering = {
        "during_job": spread_of([r["old_lettering_ms"] for r in rows if r["job_at_turn"] and r["old_lettering_ms"]]),
        "no_job": spread_of([r["old_lettering_ms"] for r in rows if not r["job_at_turn"] and r["old_lettering_ms"]]),
        "by_segment": {s: spread_of([r["old_lettering_ms"] for r in rows if r["segment"] == s
                                     and r["old_lettering_ms"]]) for s in dict.fromkeys(r["segment"] for r in rows)},
        "by_run": {s: spread_of([r["old_lettering_ms"] for r in rows if r["run"] == s and r["old_lettering_ms"]])
                   for s in RUN_STATES}}
    old_page = {  # (the page before on the page area, lettered or not: a whole-book run's reading shows no lettering)
        "by_run": {s: spread_of([r["old_page_ms"] for r in rows if r["run"] == s and r["old_page_ms"] is not None])
                   for s in RUN_STATES},
        "by_segment": {s: spread_of([r["old_page_ms"] for r in rows
                                     if r["segment"] == s and r["old_page_ms"] is not None])
                       for s in dict.fromkeys(r["segment"] for r in rows)}}
    soft_rows = [r for r in rows if r["lettered_soft_ms"]]
    lettered_soft = {"turns": len(soft_rows), "ms": dist([r["lettered_soft_ms"] for r in soft_rows]),
                     "by_segment": {s: dist([r["lettered_soft_ms"] for r in soft_rows if r["segment"] == s])
                                    for s in dict.fromkeys(r["segment"] for r in soft_rows)},
                     "read_from_soft": soft_lettering(started), "cached_pages": {}}
    for kind, soft in (("soft_first", True), ("sharp_at_once", False)):  # (by the stand-in's draw of the turn)
        mine = [r for r in rows if r["cached"] and ((r["soft_to_sharp_ms"] or 0) > 0) == soft]
        gone = [r["lettering_gone_ms"] for r in mine if r["lettering_gone_ms"]]
        lettered_soft["cached_pages"][kind] = {
            "turns": len(mine), "lettered_ms": dist([r["lettered_from_turn_ms"] for r in mine]),
            "lettered_sharp_ms": dist([r["lettered_sharp_from_turn_ms"] for r in mine]),
            "lettered_on_soft": sum(1 for r in mine if r["lettered_soft_ms"]),
            "lettering_gone": len(gone), "lettering_gone_ms": dist(gone)}
    ready_at = next((e["t"] for e in notes.app_events if e["kind"] == "ready"), None)
    displays = [[rel(d["t"]), d["page"], int(bool(d["spread"])), d["state"], d["kind"], d["lettered"], d["from"],
                 int(bool(d["quick"]))] for d in notes.displays]
    rested_rows = [r for r in rows if (r["rest_ms"] or 0) >= REST_MS]
    latency = {"all": {key: dist([r[key] for r in rested_rows])
                       for key in ("first_request_ms", "first_lettered_ms", "finished_ms")}}
    for seg in dict.fromkeys(r["segment"] for r in rested_rows):
        latency[seg] = {key: dist([r[key] for r in rested_rows if r["segment"] == seg])
                        for key in ("first_request_ms", "first_lettered_ms", "finished_ms")}
    wasted = wasted_requests(requests, jobs, notes.cancels, ended)
    by_id = {j["id"]: j for j in jobs}
    real = [r for r in requests if r["job"] is not None and wasted_why(by_id.get(r["job"])) is None]
    wasted_summary = {
        "count": len(wasted), "by_why": dict(Counter(w["why"] for w in wasted)),
        "by_outcome": dict(Counter(str(w["outcome"]) for w in wasted)),
        "by_segment": dict(Counter(segment_at_t(w["t"]) for w in wasted)),
        "ran_ms": dist([w["ran_ms"] for w in wasted]),
        "ran_on_after_cancel_ms": dist([w["ran_on_after_cancel_ms"] for w in wasted]),
        "next_real_after_ms": dist([w["next_real_after_ms"] for w in wasted]),
        "next_real_server_wait_ms": dist([w["next_real_server_wait_ms"] for w in wasted]),
        # beside it: the server wait of every request that was not sent for nothing
        "real_server_wait_ms": dist([server_wait(r) for r in real]),
        "real_ran_ms": dist([ms(r["end_t"], r["t"]) for r in real]),
        "list": [{**{k: v for k, v in w.items() if k != "t"}, "t_s": rel(w["t"]), "segment": segment_at_t(w["t"])}
                 for w in wasted]}
    cancelled_after_kept = [j for j in started if j["cancelled_t"] is not None and j.get("discarded") is False
                            and j["state"] == "sharp"]
    stale_status = [r for r in rows if r["status_old_page_ms"]]
    status_summary = {
        "turns": len(rows), "turns_with_a_line_of_the_page_before": len(stale_status),
        "stayed_ms": dist([r["status_old_page_ms"] for r in stale_status]),
        "by_kind": {kind: dist([r["status_old_page_ms"] for r in stale_status if r["status_old_page_kind"] == kind])
                    for kind in sorted({str(r["status_old_page_kind"]) for r in stale_status})},
        "by_segment": {s: dist([r["status_old_page_ms"] for r in stale_status if r["segment"] == s])
                       for s in dict.fromkeys(r["segment"] for r in stale_status)},
        "lines_of_another_page_ms": dist([r["status_other_page_ms"] for r in rows if r["status_other_page_ms"]]),
        "kinds_seen": dict(Counter(s["kind"] for s in notes.status_lines))}
    resizes = resize_rows(events, offset, notes, turns, rows)
    for item in resizes:
        item["from_s"] = rel(item.pop("from_t"))
    leaves = [{**{k: v for k, v in item.items() if k != "t"}, "t_s": rel(item["t"])} for item in notes.leaves]
    modes = {"leaves_of_the_full_screen": leaves,
             "columns": ["t_s", "reading", "over", "run", "beside", "text_size", "role"],
             "rows": [[rel(m["t"]), int(m["reading"]), int(m["over"]), int(m["run"]), int(m["beside"]),
                       m["text_size"], m["role"]] for m in notes.modes],
             "entered": {name: {k: v for k, v in facts.items() if k != "at"}
                         for name, facts in director.entered.items()},
             "hot_keys": [{**{k: v for k, v in h.items() if k != "t"}, "t_s": rel(h["t"])} for h in notes.hotkeys]}
    run_requests = [r for r in requests if r["job"] is None]
    whole_book = {
        "decisions": dict(Counter(f"{f['kind']}:{f['state']}" for f in notes.run_frames)),
        "frames_got": dict(Counter(f["state"] for f in notes.run_reads)),
        "frames_got_not_sharp": sorted({str(f["key"]) for f in notes.run_reads if f["state"] != "sharp"}),
        "pages_got": len({f["key"] for f in notes.run_reads}),
        "ends": [{"code": e["code"], "pages": e["pages"], "t_s": rel(e["t"])} for e in notes.run_ends],
        "requests": len(run_requests), "requests_by_outcome": dict(Counter(str(r["outcome"]) for r in run_requests)),
        "status_kinds_beside": dict(Counter(s["kind"] for s in notes.status_lines
                                            if segment_at_t(s["t"]) == "w2"))}
    cancel_rows = [r for r in rows if r["segment"] == "x"]
    in_flight = [w for w in wasted if segment_at_t(w["t"]) == "x"]
    cancel = {"soft_ms": director.args.cancel_soft_ms, "factor": CANCEL_FACTOR,
              "jobs_on_soft": sum(1 for j in started if segment_at_t(j["t"]) == "x" and j["state"] == "soft"),
              "requests_on_soft": sum(1 for r in requests if segment_at_t(r["t"]) == "x" and r["frame"] == "soft"),
              "cancelled_in_flight": len([w for w in in_flight if w["ran_on_after_cancel_ms"] is not None]),
              "ran_ms": dist([w["ran_ms"] for w in in_flight]),
              "ran_on_after_cancel_ms": dist([w["ran_on_after_cancel_ms"] for w in in_flight]),
              "next_real_after_ms": dist([w["next_real_after_ms"] for w in in_flight]),
              "next_real_server_wait_ms": dist([w["next_real_server_wait_ms"] for w in in_flight]),
              "turns": [{k: r[k] for k in ("page", "soft_to_sharp_ms", "first_request_ms", "finished_ms", "jobs",
                                           "jobs_on", "requests", "wasted_requests", "at_rest", "at_rest_from")}
                        for r in cancel_rows]}
    request_list = {"columns": ["t_s", "job", "frame", "gate", "outcome", "ran_ms", "server_ms", "server_wait_ms",
                                "wasted"],
                    "rows": [[rel(r["t"]), r["job"], r["frame"], r["gate"], r["outcome"], ms(r["end_t"], r["t"]),
                              r["server_ms"], server_wait(r), wasted_why(by_id.get(r["job"]))
                              if r["job"] is not None else None] for r in requests]}
    return {
        "latency_rested": latency,
        "status_line_of_the_page_before": status_summary,
        "resizes": resizes,
        "cache_across_sizes": across_sizes(job_list),
        "readings_on_a_miss": readings_on_a_miss(notes.resolves, rel),
        "modes": modes,
        "whole_book_run": whole_book,
        "cancel_in_flight": cancel,
        "wasted_requests": wasted_summary,
        "jobs_cancelled_after_kept": {"count": len(cancelled_after_kept),
                                      "requests": sum(j["requests"] for j in cancelled_after_kept)},
        "request_list": request_list,
        "old_lettering_after_a_turn": old_lettering,
        "old_page_after_a_turn": old_page,
        "lettering_on_a_soft_frame": lettered_soft,
        "cancels": {"all": len(cancels), "by_segment": dict(Counter(str(c["segment"]) for c in cancels)),
                    "page_still_on_show": false_cancels, "list": cancels},
        "lettered_unsettled_ms": {"total": sum(r["lettered_unsettled_ms"] for r in rows),
                                  "turns": sum(1 for r in rows if r["lettered_unsettled_ms"])},
        "empty_unsettled_results_shown": sum(1 for d in notes.displays if d["kind"] == "translated"
                                             and not d["lettered"] and d["from"] not in ("sharp", None)),
        "tk_thread": tk_share(notes.tk_cpu),
        "timings": timing_table(notes.timings, notes.tk_cpu),
        "displays": {"columns": ["t_s", "page", "spread", "state", "kind", "lettered", "from", "quick"],
                     "rows": displays},
        "ready_s": rel(ready_at), "app_events": dict(Counter(e["kind"] for e in notes.app_events)),
        "job_list": job_list,
        "lookup_list": {"columns": ["t_s", "job", "size", "margins", "box", "aspect", "hit", "nearest",
                                    "nearest_aspect"],
                        "rows": [[rel(r["t"]), r["job"], r["size"], r["margins"], r["box"], r["aspect"], r["hit"],
                                  r["nearest"], r["nearest_aspect"]] for r in notes.lookups]},
        "area_list": [{**{k: v for k, v in m.items() if k != "t"}, "t_s": rel(m["t"])} for m in notes.margins],
        "failed": director.failed, "seconds": round((ended - began) / 1000, 1),
        "clock": {"standin_to_window_ms": round(offset, 1),
                  "log_latency_ms_median": round(statistics.median(lat) - offset, 1) if lat else None},
        "band_top_px": top, "dpr": dpr,
        "released": director.released, "theme": director.theme,
        "page_keys": {name: {k: v for k, v in facts.items() if k != "at"} for name, facts in director.keyed.items()},
        "segments": table, "turns": rows, "incidents": spells,
        "jobs": {"started": len(started), "on": dict(Counter(j["state"] for j in started)),
                 "not_started": len(jobs) - len(started),
                 "with_gate": sum(1 for j in started if j["gate"]),
                 "gate_end": dict(Counter(str(j["gate_end"]) for j in started)),
                 "discarded": sum(1 for j in started if j.get("discarded")),
                 "results_from": dict(Counter(str(j["result_from"]) for j in started if j["result_t"])),
                 # (by the gate as each job ended - a confirmation taken back after that still counts -, as before)
                 "confirmed_on_soft": sum(1 for j in started if j["state"] == "soft" and j["gate_end"] == "confirmed"),
                 "kept_from_unsettled_frames": [j["id"] for j in kept_soft],
                 # (by what is true at the end: the gates as the run left them, and the cache on disk)
                 "soft_frames_at_end": soft_frames_at_end(jobs, turns, notes.captures, notes.decides, cache_end, rel),
                 "on_black_spinner_unknown_shown": sum(1 for j in started if j["state"] in ("black", "spinner",
                                                                                            "unknown")
                                                      and j["result_t"] and j["result_translated"])},
        "requests": {"total": len(requests), "by_kind": dict(Counter(r["kind"] for r in requests)),
                     "outside_page_jobs": sum(1 for r in requests if r["job"] is None),
                     "gate_pending": sum(1 for r in requests if r["gate"] == "pending"),
                     "by_gate": dict(Counter(r["gate"] for r in requests)),
                     "by_frame": dict(Counter(str(r["frame"]) for r in requests)),
                     "warm_ups": len(notes.warmups),
                     "warm_ups_for_unconfirmed": sum(1 for w in notes.warmups if w["gate"] == "pending")},
        "captures": dict(notes.capture_counts),
        "capture_sizes": [[rel(c["t"]), *c["size"]] for k, c in enumerate(notes.captures)
                          if k == 0 or c["size"] != notes.captures[k - 1]["size"]],
        "ocr": {"placements": [{**o, "t": rel(o["t"])} for o in notes.ocr],
                "log": [{**o, "t": rel(o["t"])} for o in notes.ocr_log], "loads": loads,
                "system_page": director.facts},
        "front_owner_counts": dict(notes.owners),
        "errors": {"hooks": dict(notes.errors), "log_records": dict(tap.levels)},
        "guard": {"patched": patched, "refused": guard.refused, "chosen": sorted(set(notes.selected)),
                  "stand_in": browser.hwnd, "reached_the_stand_in": guard.used,
                  "only_the_stand_in_chosen": set(notes.selected) <= {browser.hwnd}},
        "shots": director.shots,
        "stand_in_events": dict(Counter(e["ev"] for e in events)),
        "rested_pages": rested_pages(rows),
    }


def tk_share(samples: list[tuple[float, float, bool]]) -> dict[str, Any]:
    """The Tk thread's CPU time against the wall clock, between the director's looks, a page job running or not."""
    out: dict[str, Any] = {}
    for key, busy in (("job_running", True), ("no_job", False)):
        wall = cpu = 0.0
        for (t0, c0, b0), (t1, c1, _b1) in zip(samples, samples[1:]):
            if b0 == busy:
                wall, cpu = wall + (t1 - t0), cpu + (c1 - c0)
        out[key] = {"wall_s": round(wall, 1), "cpu_s": round(cpu, 2), "share": round(cpu / wall, 3) if wall else None}
    return out


def timing_table(timings: dict[str, list[tuple[float, bool]]], samples: list[tuple[float, float, bool]]
                 ) -> dict[str, Any]:
    """Per call timed (`TIMED`, and the capture): how often, and how long, a page job running or not."""
    walls = {busy: sum(t1 - t0 for (t0, _c0, b0), (t1, _c1, _b1) in zip(samples, samples[1:]) if b0 == busy)
             for busy in (True, False)}
    out: dict[str, Any] = {}
    for name, items in sorted(timings.items()):
        row: dict[str, Any] = {}
        for key, busy in (("job_running", True), ("no_job", False)):
            values = sorted(ms_ for ms_, b in items if b == busy)
            if not values:
                continue
            row[key] = {"n": len(values), "per_s": round(len(values) / walls[busy], 1) if walls[busy] else None,
                        "median_ms": round(statistics.median(values), 2),
                        "p90_ms": round(values[int(0.9 * (len(values) - 1))], 2),
                        "max_ms": round(values[-1], 1), "total_s": round(sum(values) / 1000, 2),
                        "share": round(sum(values) / 1000 / walls[busy], 3) if walls[busy] else None}
        out[name] = row
    return out


def rested_pages(rows: list[dict[str, Any]]) -> int:
    pages: set[int] = set()
    for r in rows:
        if (r["rest_ms"] or 0) >= REST_MS:
            pages.add(r["page"])
            if r["spread"]:
                pages.add(r["page"] + 1)
    return len(pages)


def cleanup(report: dict[str, Any], closed: dict[str, Any], state: Path, standin_dir: Path, mode: str, url: str,
            ps_before: list[str] | None) -> dict[str, Any]:
    """What the state holds at the end (any turn times a profile keeps - none -, the pages in the cache, the log's
    errors), read before it goes; the scratch folders deleted; what the window loaded in Ollama checked gone (and let
    go of if not)."""
    out: dict[str, Any] = {"browser": closed}
    try:
        from taslation.cache import CacheStore
        from taslation.config import Settings
        from taslation.pagekeys import Profiles

        settings = Settings(state_dir=state)
        store = CacheStore(settings.cache_dir)
        out["cache_pages"] = store.page_count(BOOK, "English")
        book = store.open(BOOK, PLAMO, "English")
        out["cache_lines_per_page"] = [len(p.bubbles) for p in sorted(book.pages, key=lambda p: p.seq)]
        out["cache_pages_without_lines"] = sum(1 for p in book.pages if not p.bubbles)
        out["cache_pages_incomplete"] = sum(1 for p in book.pages if p.incomplete)
        data = Profiles(state / "profiles.json").data
        out["settle_seen_kept"] = [v.get("settle_seen") for v in data.values() if isinstance(v, dict)
                                   and v.get("settle_seen")]
    except Exception as e:  # noqa: BLE001 - said by its type
        out["state_error"] = type(e).__name__
    out["log"] = log_facts(state)
    if url:
        after = loaded_models(url)
        out["ollama_loaded_after_close"] = after
        mine = [m for m in (after or []) if m.split(":")[0] == PLAMO and m not in (ps_before or [])]
        if mine:
            out["unloaded_by_driver"] = [ollama_unload(url, m) for m in mine]
            out["ollama_loaded_at_end"] = loaded_models(url)
    root = logging.getLogger()
    for handler in list(root.handlers):  # the app's log file in the scratch state, let go so that it can go
        name = getattr(handler, "baseFilename", "")
        if name and Path(name).resolve().is_relative_to(state.resolve()):
            root.removeHandler(handler)
            handler.close()
    for folder, key in ((state, "state_deleted"), (standin_dir, "standin_folder_deleted")):
        for _attempt in range(20):
            shutil.rmtree(folder, ignore_errors=True)
            if not folder.exists():
                break
            time.sleep(0.5)
        out[key] = not folder.exists()
    return out


def print_table(report: dict[str, Any], path: Path) -> None:
    run_ = report["run"]
    print(f"translator: {report['translator']}; browser: {report['browser']}; pages: {report['pages']}; "
          f"{run_.get('seconds')} s" + (f"; STOPPED: {run_['failed']}" if run_.get("failed") else ""))
    if "segments" not in run_:
        print(f"report {path}")
        return
    head = ("segment", "turns", "rested", "request med/max ms", "lettered med/max ms", "finished med/max ms",
            "translated at rest", "from soft", "jobs", "requests", "wasted", "stale", "lag")
    print(" | ".join(head))
    for s in run_["segments"]:
        print(" | ".join(str(v) for v in (
            s["segment"], s["turns"], s["rested"], f"{s['first_request_ms_median']}/{s['first_request_ms_max']}",
            f"{s['first_lettered_ms_median']}/{s['first_lettered_ms_max']}",
            f"{s['finished_ms_median']}/{s['finished_ms_max']}", f"{s['translated_at_rest']}/{s['rested']}",
            s["at_rest_from_soft"], s["jobs"], s["requests"], s["wasted_requests"],
            s["stale"], s["not_following"])))
    for key, value in run_["latency_rested"]["all"].items():
        print(f"rested turns, {key}: {value}")
    wasted = run_["wasted_requests"]
    print(f"wasted requests {wasted['count']} {wasted['by_why']} {wasted['by_outcome']}; ran {wasted['ran_ms']}; "
          f"ran on after the cancel {wasted['ran_on_after_cancel_ms']}; next real request's server wait "
          f"{wasted['next_real_server_wait_ms']} (all real: {wasted['real_server_wait_ms']})")
    req = run_["requests"]
    clean = report["cleanup"]
    print(f"requests {req['total']} (on a gate pending {req['gate_pending']}, outside jobs "
          f"{req['outside_page_jobs']}); turn times kept in a profile {len(clean.get('settle_seen_kept') or [])}; "
          f"cache pages {clean.get('cache_pages')} vs rested {run_['rested_pages']}; shots {len(run_['shots'])}; "
          f"report {path}")
    old, cancels = run_["old_lettering_after_a_turn"], run_["cancels"]
    print(f"old lettering after a turn, job running: {old['during_job']}; no job: {old['no_job']}; jobs cancelled "
          f"{cancels['all']} {cancels['by_segment']}, of them with their page still on show "
          f"{len(cancels['page_still_on_show'])}")
    at_end = run_["jobs"]["soft_frames_at_end"]
    left = [(r["id"], r["page"], r["sharp_captured_late_ms"], r["why"]) for r in at_end["left"]]
    print(f"soft frames at the end: confirmed {at_end['confirmed']}; taken back "
          f"{at_end['taken_back']['while_running']} while running, {at_end['taken_back']['after_the_job']} after the "
          f"job; left in the cache {at_end['left_in_the_cache']} ({at_end['left_though_the_sharp_frame_came']} though "
          f"the sharp frame came; cache {at_end['cache']}) {left}; by the gate as the job ended: confirmed on a soft "
          f"frame {run_['jobs']['confirmed_on_soft']}, kept from frames not the sharp one "
          f"{run_['jobs']['kept_from_unsettled_frames']}")
    print(f"the page before after a turn, by the run: {run_['old_page_after_a_turn']['by_run']}; its lettering "
          f"{old['by_run']}")
    soft = run_["lettering_on_a_soft_frame"]
    read = soft["read_from_soft"]
    print(f"lettering on a soft frame: {soft['turns']} turns, {soft['ms']} ms, by segment {soft['by_segment']}; read "
          f"from a soft frame {read['jobs']} jobs, {read['boxes']} boxes lettered (the sharp frame "
          f"{read['sharp_boxes']}), off the sharp frame's by {read['box_shift_px']} px, per job {read['shift_px']}, "
          f"unmatched {read['unmatched']}")
    for kind, c in soft["cached_pages"].items():
        print(f"pages the cache held, drawn {kind.replace('_', ' ')}: {c['turns']} turns, lettered {c['lettered_ms']} "
              f"ms from the turn, read from the sharp frame {c['lettered_sharp_ms']} ms, lettered on the soft picture "
              f"{c['lettered_on_soft']}, lettering gone and back {c['lettering_gone']} times, "
              f"{c['lettering_gone_ms']} ms")
    status = run_["status_line_of_the_page_before"]
    print(f"status line of the page before after a turn: {status['turns_with_a_line_of_the_page_before']} of "
          f"{status['turns']} turns, stayed {status['stayed_ms']}, by kind {status['by_kind']}")
    for item in run_["resizes"]:
        print(f"resize at {item['from_s']} s {item['size_before']} -> {item['size_after']}: first capture "
              f"{item['first_capture_ms']} ms, read by its own area {item['read_by_own_area_ms']} ms, its own area in "
              f"force {item['own_area_in_force_ms']} ms, long captures {item['long_captures_ms']}, job running "
              f"{item['job_running']}, old lettering {item['old_lettering_ms']} ms")
    across = run_["cache_across_sizes"]
    print(f"pages held at another size only: {across['jobs']} jobs, units from the cache {across['unit_hits']}, not "
          f"{across['unit_misses']}, requests {across['requests']}; by why {across['by_why']}; by layout "
          f"{across['by_layout']}")
    looks = run_["readings_on_a_miss"]
    print(f"readings of a page the cache did not hold as found: {looks['with_readings']} of {looks['looks']} looks, "
          f"found {looks['found']}; ms {looks['ms']} (when found {looks['ms_when_found']}); readings "
          f"{looks['readings']}")
    modes = run_["modes"]
    print(f"modes entered {modes['entered']}; hot keys pressed "
          f"{[(h['pressed'], h['taken']) for h in modes['hot_keys'] if 'pressed' in h]}")
    if run_.get("page_keys"):
        print(f"page keys pressed on the window's page: {run_['page_keys']}")
    print(f"the full screen left: {modes.get('leaves_of_the_full_screen')}")
    whole = run_["whole_book_run"]
    if whole["decisions"] or whole["ends"]:
        print(f"whole-book run: decisions {whole['decisions']}; frames got {whole['frames_got']}, not sharp "
              f"{whole['frames_got_not_sharp']}; ended {whole['ends']}; requests {whole['requests']}")
    cancel = run_["cancel_in_flight"]
    if cancel["turns"]:
        print(f"cancelled in flight (soft {cancel['soft_ms']} ms): jobs on soft {cancel['jobs_on_soft']}, requests "
              f"on soft {cancel['requests_on_soft']}, cancelled while running {cancel['cancelled_in_flight']}; ran on "
              f"after the cancel {cancel['ran_on_after_cancel_ms']}; next real request after "
              f"{cancel['next_real_after_ms']}, its server wait {cancel['next_real_server_wait_ms']}")


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / f"taslation-standin-{os.getpid()}",
                    help="the scratch folder (the state, the stand-in's files, report.json, shots/)")
    ap.add_argument("--scenario", default="all",
                    help="all, or some of c,a,b,d,e,r,o,z,w,x,f,f2 (f brings f2 with it, w brings w2)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="the display scale the stand-in's browser draws at, and TASlation's text size (1 to 3)")
    ap.add_argument("--cancel-soft-ms", type=int, default=700,
                    help="scenario x: how long the screens of little text stay soft")
    ap.add_argument("--canned", action="store_true", help="the canned translator, not the Ollama on this computer")
    ap.add_argument("--canned-ms", type=int, default=350, help="the canned translator's answer time per line")
    ap.add_argument("--canned-load-s", type=float, default=5.0, help="the canned translator's load time")
    ap.add_argument("--browser", default="auto", choices=("auto", "chrome", "edge"))
    ap.add_argument("--seed", type=int, default=1, help="the stand-in's draws (soft times, waits)")
    ap.add_argument("--series", type=int, default=1, help="the dataset's series, by its place in the sorted list")
    ap.add_argument("--first", type=int, default=1, help="its first page (from 1)")
    ap.add_argument("--synthetic", action="store_true", help="the repository's test pages, not the dataset")
    ap.add_argument("--front", default="viewer", choices=("viewer", "as-is"),
                    help="viewer: the window is told the viewer is in front (the reader's case); as-is: as it is")
    ap.add_argument("--models", default="", help="the models folder (default: TASLATION_MODELS_DIR)")
    ap.add_argument("--timeout", type=float, default=180.0, help="seconds a scenario may wait for the window's rest")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        raise SystemExit("the stand-in needs Windows (window capture)")
    args = parse(argv)
    if not 1.0 <= args.scale <= 3.0:
        raise SystemExit("--scale is 1 to 3")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
