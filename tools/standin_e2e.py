"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the real TASlation window checked end to end on the browser-type
stand-in viewer (`tools/standin_viewer`), with no real book and no real viewer - a developer's debugging aid, never
part of a release.

    python tools/standin_e2e.py --out SCRATCH [--scenario all | a,b,c,d,e,f,f2] [--canned] [--browser auto|chrome|edge]
                                [--seed 1] [--series 1] [--first 1] [--synthetic] [--front viewer|as-is]

What runs, all on this computer:

* the stand-in: `standin_viewer`'s page in a throwaway Chrome or Edge window of its own (``--app``, a scratch profile
  under *--out*, deleted at the end), drawing sample pages as a browser-based reader does - a band at the top, a dark
  ground, spreads right to left, every turn soft first and sharp a while later, black for a while now and then, a
  spinner. Its pages are the OpenMantra dataset's (``~/.taslation/datasets/openmantra``, read in place by file URL:
  the series chosen by its place in the sorted list, *--series*, never by name; no picture is copied), or with
  *--synthetic* (or no dataset) the repository's two test pages, turned and flipped. The page TURNS BY ITSELF from a
  script in its URL, released part by part through a control file in the scratch folder: no key, no click, nothing
  is sent to any window by this tool, and TASlation sends none either (its key and click functions refuse here);
* TASlation's window in this process (`ui.app.App`, as ``taslation gui --book NAME`` opens it: page by page, Auto
  on, the Reader role, early start and the load of the model at the start as the defaults have them), on a scratch
  state folder (TASLATION_STATE_DIR under *--out*: the legal notice dismissed as the tests do, the window in
  English; the reader's capture area 0,85,0,0 as on the owner's browser reader), with the real OCR models
  (TASLATION_MODELS_DIR) and the default translator through the Ollama on this computer (requests only: it is
  never started, stopped or set up here; what the window loaded it lets go of at its close, and the end checks
  /api/ps). *--canned* (or an Ollama that does not answer or lacks the model) answers from a small server of this
  tool instead ("Line N.", after a load and an answer time like the real model's), which the report says;
* the window sees one window, the stand-in's - found by the process tree this tool started AND the token in its
  title, never by another window's title, which is never read - and the guard (`demo_video.Guard`, keys and
  clicks refused outright): every function that captures, moves, raises or enlarges a window acts on the
  stand-in or this process's own windows, else the run stops; the window chosen is checked at every step
  (`standin_viewer.SelectionGuard`) and anything but the stand-in stops the run at once, nothing pressed.
  The foreground is never changed: the window follows a viewer in front, which is the reader's case, and with
  *--front viewer* (the default) it is told the viewer is in front whoever is (the report counts who really was).

The scenarios, in this order (each released once the window has come to rest after the one before):
  c  turns while the model still loads at the start         a  slow reading: 9 turns 6-8 s apart
  b  fast flipping: 10 turns 0.3-0.5 s apart, then a rest   d  black flashes and spinners between turns
  e  turning back to pages translated (cache hits)          f  the dark theme, then a narrow window (single pages)

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
it); the jobs kept from a frame that was not the sharp one (must be none); the jobs cancelled, per scenario (d, the
flashes and spinners: none); overlays left on a page the stand-in had left; that no profile in the scratch state keeps
turn times; where the OCR read (the readers' placement, through every load of the model, and the System page's
facts); errors (type names and counts, also from the log); the pages in the cache at the end against those the
stand-in rested on. Into *--out*: report.json, and shots/ - pictures of
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
import http.client
import json
import logging
import os
import queue
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
    "f": ("dark theme", ["n", "w6000", "n", "w6000"]),
    "f2": ("narrow window", ["n", "w6000", "n", "w6000"]),
}
ORDER = ["c", "a", "b", "d", "e", "f", "f2"]
# the turns whose soft frame and sharp frame drawn quickly are pictured (turns that come to a window at rest), and
# those pictured at rest
SOFT_SHOTS = {"a": (1,), "e": (3,), "f2": (1,)}
REST_SHOTS = {"a": (1, 5)}


@dataclass
class Segment:
    name: str
    go: int
    steps: list[str]
    screens: list[tuple[int, bool]] = field(default_factory=list)  # the screen after each turn, as foreseen


def wanted(text: str) -> list[str]:
    """The scenarios asked for, in `ORDER` ("f" brings the narrow window with it; "f2" alone is the narrow window
    without the dark theme)."""
    if text.strip().lower() in ("", "all"):
        return list(ORDER)
    asked = {p.strip().lower() for p in text.split(",") if p.strip()}
    unknown = asked - set(SCENARIOS)
    if unknown:
        raise SystemExit(f"unknown scenario(s): {', '.join(sorted(unknown))}")
    return [n for n in ORDER if n in asked or (n == "f2" and "f" in asked)]


def build_plan(names: list[str], count: int) -> tuple[list[Segment], list[sv.Step]]:
    """The segments of the stand-in's script (each held at ``gN`` until the driver releases it, ``mN`` to mark it)
    and the script; the screen each turn will show, foreseen as the page turns (spreads until the narrow window)."""
    segments: list[Segment] = []
    index, spread = 0, True
    text: list[str] = []
    for go, name in enumerate(names, 1):
        steps = SCENARIOS[name][1]
        segment = Segment(name, go, steps)
        if name == "f2":
            spread = False
        for step in steps:
            if step in ("n", "p"):
                width = 2 if spread else 1
                index = max(0, min(count - 1, index + (width if step == "n" else -width)))
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
        self.on_display: Callable[[dict[str, Any]], None] | None = None

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
        job = {"id": len(self.jobs) + 1, "t": now_ms(), **self.code(self.shown(image)), "started": False,
               "gate": False, "requests": 0, "translated": 0, "first_translated_t": None,
               "result_t": None, "result_translated": None, "result_from": None, "cancelled_t": None,
               "discarded": None, "done_t": None, "gate_end": None}
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
        with self.lock:
            if job is not None:
                gate = job.pop("_gate", None)
                job["gate_end"] = getattr(gate, "state", None)
            self.current = None

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
                job["cache_hits"] = getattr(result, "cache_hits", None)
                job["cache_misses"] = getattr(result, "cache_misses", None)
                job["stored"] = len(data.get("stored") or ())
            elif kind == "page_cancelled":
                job["cancelled_t"] = t
                job["discarded"] = bool(data.get("discarded"))
                job["stored_at_cancel"] = len(data.get("stored") or ())
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


def install(notes: Notes, args: argparse.Namespace, guard: Any, viewer_info: Callable[[], Any]) -> dict[str, Any]:
    """The guard (`demo_video`'s, keys and clicks refused), and the hooks that take the notes; what was replaced."""
    import demo_video

    import taslation.capture.overlay as overlay
    import taslation.capture.wgc as wgc
    import taslation.capture.windows as windows
    from taslation.ocr import place
    from taslation.translate import ollama as ollama_mod
    from taslation.translate import plamo as plamo_mod
    from taslation.ui import app as app_mod
    from taslation.ui import live

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
    refuse_keys = classmethod(lambda cls, *a, **k: guard.refuse("global hot keys"))
    overlay.HotKeys.start = refuse_keys  # type: ignore[assignment]

    App = app_mod.App
    start_translate, job_translate = App._start_translate, App._job_translate
    handle_event, redisplay, capture, chosen = App._handle_event, App._redisplay, App._capture, App._on_window_selected

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
        notes.timed("_capture", (time.perf_counter() - began) * 1000, bool(getattr(self, "busy", False)))
        notes.captured(image)
        return image

    def selected(self: Any, *a: Any, **k: Any) -> Any:
        out = chosen(self, *a, **k)
        if self.selected is not None:
            notes.selected.append(int(self.selected.hwnd))
        return out

    App._start_translate, App._job_translate, App._handle_event = started, worked, handled
    App._redisplay, App._capture, App._on_window_selected = drawn, captured, selected
    for name in TIMED:  # the Tk thread's time in the live view's calls, a job running or not
        if hasattr(App, name):
            setattr(App, name, timed_call(notes, name, getattr(App, name)))

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
                 narrow_rect: tuple[int, int, int, int]):
        self.app, self.browser, self.guard, self.selection = app, browser, guard, selection
        self.notes, self.segments, self.args, self.out, self.standin_dir = notes, segments, args, out, standin_dir
        self.narrow_rect = narrow_rect
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
            elif ev == "black" and e.get("on") == "1" and self.current == "d":
                self.due.append((time.monotonic() + 0.3, f"d_flash{self.turns_in['d']}"))
            elif ev == "spinner" and e.get("on") == "1" and self.current == "d":
                self.due.append((time.monotonic() + 0.8, f"d_spinner{self.turns_in['d']}"))
            self.events.append(e)

    def turned(self, e: dict[str, Any]) -> None:
        """A turn began on the stand-in: the pictures due for it."""
        seg, k, at = self.current, self.turns_in[self.current], time.monotonic()
        if k in REST_SHOTS.get(seg, ()):
            self.due.append((at + 5.2, f"{seg}_turn{k}_rest"))
        elif seg == "c" and k == 2:
            self.due.append((at + 1.0, "c_loading"))
        elif seg == "b" and k == 10:
            self.due.append((at + 6.0, "b_after_flipping"))
        elif seg == "d" and k == 3:
            self.due.append((at + 5.0, "d_rest"))
        elif seg == "e" and k == 1:
            self.due.append((at + 1.5, "e_back_cached"))
        elif seg in ("f", "f2") and k == 2:
            self.due.append((at + 5.0, "f_dark_rest" if seg == "f" else "f_narrow_rest"))

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
        if self.index >= len(self.segments):
            if self.phase != "end":
                self.phase, self.phase_at = "end", now
                return
            if (self.ended and rested) or waited > self.args.timeout:
                if waited > self.args.timeout:
                    self.released["end"] = {"timed_out": True}
                self.finish()
            return
        seg = self.segments[self.index]
        if self.phase == "prepare":
            self.before(seg)
            self.phase, self.phase_at = "settle", now
            return
        if self.phase == "settle":
            ready_go = self.waiting_go >= seg.go
            if seg.name == "c":
                go = ready_go and getattr(self.app, "selected", None) is not None
            elif seg.name == "f2":
                go = ready_go and rested and self.resized()
            else:
                go = ready_go and rested and (self.index > 0 or self.first_page_done())
            timed_out = ready_go and waited > self.args.timeout
            if timed_out and not self.app.ready:
                self.stop("the window was not ready within --timeout")
                return
            if go or timed_out:
                self.released[seg.name] = {"waited_s": round(waited, 1), "timed_out": bool(timed_out and not go),
                                           "t": now_ms()}
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

    def shot(self, label: str) -> None:
        """A picture of TASlation's own window (its handle, the client area; never the screen) into shots/."""
        from taslation.capture import windows

        if label in self.taken or self.over:
            return
        self.taken.add(label)
        try:
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
    page view draws (its crop, None outside reading mode) and the picture's size, the viewer's window size."""
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
            "over_500": sum(1 for v in values if v > 500), "over_1000": sum(1 for v in values if v > 1000)}


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
            "old_page_ms": old_page_ms, "old_lettering_ms": old_lettering_ms,
            "lettered_unsettled_ms": lettered_unsettled_ms(notes.displays, scr, sharp, hi),
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
    import re

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
    report: dict[str, Any] = {"scenarios": names, "seed": args.seed, "front": args.front}
    pictures: list[Any] | None = None if args.synthetic else dataset_pages(args.series, args.first, count)
    report["pages"] = "dataset" if pictures else "synthetic"
    if not pictures:
        pictures = synthetic_pages(count)
    count = len(pictures)
    segments, steps = build_plan(names, count)
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
    browser = sv.StandinBrowser(found[1], page, standin_dir / "profile", standin_rect, token)
    closed: dict[str, Any] = {}
    try:
        hwnd = browser.wait_window()
        ready = browser.wait_event("ready", 30)
        place_own(hwnd, standin_rect, top=True)
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
    sv.write_control(standin_dir, 0, band=round((AREA[1] - top) / dpr))
    selection = sv.SelectionGuard(hwnd)
    pid = next(p for w, p in sv.top_windows() if w == hwnd)

    def viewer_info() -> Any:
        if not guard.is_viewer(hwnd) or pid not in browser.tree:
            return None
        return WindowInfo(hwnd, sv.window_text(hwnd), window_class(hwnd), pid, window_rect(hwnd), program_name(pid))

    notes = Notes(top, dpr)
    patched = install(notes, args, guard, viewer_info)
    state = demo_video.scratch_state()
    info = viewer_info()
    remember_role(state, BOOK, "reader")
    profiles = Profiles(state / "profiles.json")
    profiles.set_margins(info, AREA)
    profiles.set_margins(info, AREA, large=True)
    settings = Settings(state_dir=state, ui_language="en", target_language="English", over_book=False,
                        flash_when_done=False, sound_when_done=False, always_on_top=False,
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
    callback = app.report_callback_exception

    def tk_error(kind: Any, value: Any, tb: Any) -> None:
        notes.error("tk callback", getattr(kind, "__name__", "?"))
        callback(kind, value, tb)

    app.report_callback_exception = tk_error  # type: ignore[method-assign]
    x, y, w, h = app_rect
    app.geometry(f"{w}x{h}+{x}+{y}")
    app.after(600, lambda: app.geometry(f"{w}x{h}+{x}+{y}"))
    director = Director(app, browser, guard, selection, notes, segments, args, out, standin_dir, narrow_rect)
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
    return summarise(director, notes, tap, browser, patched, guard, began, ended, top, dpr, mode)


def summarise(director: Director, notes: Notes, tap: LogTap, browser: sv.StandinBrowser, patched: dict[str, Any],
              guard: Any, began: float, ended: float, top: int, dpr: float, mode: str) -> dict[str, Any]:
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
                 "gate": j["gate"], "gate_end": j["gate_end"], "requests": j["requests"],
                 "lettered_events": j["translated"],
                 "first_lettered_s": rel(j["first_translated_t"]), "result_s": rel(j["result_t"]),
                 "result_translated": j["result_translated"], "result_from": j["result_from"],
                 "cache_hits": j.get("cache_hits"), "cache_misses": j.get("cache_misses"),
                 "stored": j.get("stored"), "stored_at_cancel": j.get("stored_at_cancel"),
                 "cancelled_s": rel(j["cancelled_t"]), "discarded": j["discarded"], "done_s": rel(j["done_t"])}
                for j in started]
    kept_soft = [j for j in job_list if j["frame"] != "sharp" and j["discarded"] is not True
                 and (j["gate_end"] == "confirmed" or not j["gate"]) and (j["stored"] or j["stored_at_cancel"])]
    cancels = []
    for j in started:  # each page job cancelled: was its page still the stand-in's then (a black frame aside)?
        if j["cancelled_t"] is None:
            continue
        screen = screen_at(line, j["cancelled_t"])
        cancels.append({"id": j["id"], "t_s": rel(j["cancelled_t"]), "segment": segment_at_t(j["cancelled_t"]),
                        "frame": j["state"], "gate_end": j["gate_end"],
                        "page_on_show": screen == (j["page"], j["spread"]),
                        "flash_or_spinner_within_1s": flash_near(line, j["cancelled_t"])})
    false_cancels = [c for c in cancels if c["page_on_show"] and c["frame"] == "sharp"
                     and c["gate_end"] in ("confirmed", None)]
    old_lettering = {
        "during_job": spread_of([r["old_lettering_ms"] for r in rows if r["job_at_turn"] and r["old_lettering_ms"]]),
        "no_job": spread_of([r["old_lettering_ms"] for r in rows if not r["job_at_turn"] and r["old_lettering_ms"]]),
        "by_segment": {s: spread_of([r["old_lettering_ms"] for r in rows if r["segment"] == s
                                     and r["old_lettering_ms"]]) for s in dict.fromkeys(r["segment"] for r in rows)}}
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
    request_list = {"columns": ["t_s", "job", "frame", "gate", "outcome", "ran_ms", "server_ms", "server_wait_ms",
                                "wasted"],
                    "rows": [[rel(r["t"]), r["job"], r["frame"], r["gate"], r["outcome"], ms(r["end_t"], r["t"]),
                              r["server_ms"], server_wait(r), wasted_why(by_id.get(r["job"]))
                              if r["job"] is not None else None] for r in requests]}
    return {
        "latency_rested": latency,
        "wasted_requests": wasted_summary,
        "jobs_cancelled_after_kept": {"count": len(cancelled_after_kept),
                                      "requests": sum(j["requests"] for j in cancelled_after_kept)},
        "request_list": request_list,
        "old_lettering_after_a_turn": old_lettering,
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
        "failed": director.failed, "seconds": round((ended - began) / 1000, 1),
        "clock": {"standin_to_window_ms": round(offset, 1),
                  "log_latency_ms_median": round(statistics.median(lat) - offset, 1) if lat else None},
        "band_top_px": top, "dpr": dpr,
        "released": director.released, "theme": director.theme,
        "segments": table, "turns": rows, "incidents": spells,
        "jobs": {"started": len(started), "on": dict(Counter(j["state"] for j in started)),
                 "not_started": len(jobs) - len(started),
                 "with_gate": sum(1 for j in started if j["gate"]),
                 "gate_end": dict(Counter(str(j["gate_end"]) for j in started)),
                 "discarded": sum(1 for j in started if j.get("discarded")),
                 "results_from": dict(Counter(str(j["result_from"]) for j in started if j["result_t"])),
                 "confirmed_on_soft": sum(1 for j in started if j["state"] == "soft" and j["gate_end"] == "confirmed"),
                 "kept_from_unsettled_frames": [j["id"] for j in kept_soft],
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
          f"{len(cancels['page_still_on_show'])}; confirmed on a soft frame {run_['jobs']['confirmed_on_soft']}; kept "
          f"from frames not the sharp one {run_['jobs']['kept_from_unsettled_frames']}")


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / f"taslation-standin-{os.getpid()}",
                    help="the scratch folder (the state, the stand-in's files, report.json, shots/)")
    ap.add_argument("--scenario", default="all", help="all, or some of a,b,c,d,e,f,f2 (f brings f2 with it)")
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
    return run(parse(argv))


if __name__ == "__main__":
    raise SystemExit(main())
