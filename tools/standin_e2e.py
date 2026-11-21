"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the real TASlation window checked end to end on the browser-type
stand-in viewer (`tools/standin_viewer`), with no real book and no real viewer - a developer's debugging aid, never
part of a release.

    python tools/standin_e2e.py --out SCRATCH [--scenario all | c,a,b,d,e,r,t,o,z,w,x,f,f2] [--canned] [--scale 1.0]
                                [--browser auto|chrome|edge] [--seed 1] [--series 1] [--first 1] [--synthetic]
                                [--front viewer|as-is] [--cancel-soft-ms 700] [--ollama-url http://127.0.0.1:11434]
                                [--ocr-runs-on auto|cpu|gpu] [--start-ollama PORT] [--ollama-window-cache auto|off|on]
                                [--wait-done CAP_S]

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
  tool instead ("Line N.", after a load and an answer time like the real model's), which the report says. With
  *--start-ollama PORT* the window's own starter starts Ollama instead, on that loopback port where nothing may
  answer, with the environment it chooses for the window's settings (*--ollama-window-cache*): the port it starts on
  is set to PORT in this process alone, the server is told it by OLLAMA_HOST in this process's environment (with
  OLLAMA_NOPRUNE: a second server leaves the model store as it is); at the end what the starter chose goes into the
  report (``server_started``) and the server is stopped as TASlation's own end stops it;
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

The rests are written for a computer of the owner's speed. *--wait-done CAP_S* is for a slower one (GitHub's runners:
the OCR on four logical processors, the model on them too): each rest of a, d, e, r, o, z, x, f and f2, the one at
its end too (the driver changes the window for the next scenario as soon as the stand-in waits for it), is held until
the page on show is finished - the window shows it translated -, or the window has been at rest without it, or CAP_S
has gone by (``hN`` in the stand-in's script, let go through its control file); x's screens of little text are kept
soft until the window asked on the soft frame (``kN``, KEEP_SOFT_S at most) instead of --cancel-soft-ms. Each hold and
kept frame, why it ended and how long it held, is in the report (``run.waits``). Without it the script and the
control file are what they always were.

What is recorded, numbers only (no line of the pages, read or translated, is printed, logged or written): every
frame the stand-in draws carries a code in its band (the screen, soft or sharp, spinner); the frames the window
captured, the frame each page job reads and the picture its page area is given are decoded from it, so that what
the window shows is matched to what the stand-in showed exactly, not by likeness. Per turn: from the stand-in's draw
of the sharp frame to the first request of the page job that finished the page, to the first lettered bubble and to
the finished page (spreads of the turns that came to rest, per scenario), whether the page at rest is the stand-in's
and translated, from which frame (a rest ends at the next turn, or where the driver changed the window for the next
scenario before it); the page jobs and the translator's requests per page, and the gate each request went out under
(a page started early asks before its frame is confirmed); the requests sent for nothing (a job on a
frame that was not the sharp one, or one dropped as its frame changed: how long each ran, how long after its job's
cancel, and when the next request went out and how long that waited at the server, against Ollama's own time for
it); the jobs on a soft frame whose frame was confirmed, those of them whose confirmation was taken back (while they
ran, after them), and the jobs on a frame that was not the sharp one with a page unit or a kept line of theirs in the
cache the window left (must be none where the sharp frame of their page came: each told with its page, how late the
window captured that sharp frame and why); which capture gave the stand-in's frames (Windows.Graphics.Capture, or
PrintWindow where it gave none: ``capture_route``); each frame the window judged soft or sharp (`_looks_soft`: the
page's own sharp picture's verdict and the viewer's pictures') against what the stand-in drew; the jobs cancelled,
per scenario (d, the flashes and spinners: none; a job whose page went on at a new size of the stand-in is not one
cancelled with its page on show, ``resized_away``); overlays left on a page the stand-in had left; that no profile in
the scratch state keeps
turn times; where the OCR read (the readers' placement, through every load of the model, and the System page's
facts); errors (type names and counts, also from the log); the pages in the cache at the end against those the
stand-in rested on; the window's modes as they changed (reading, over the book, a run, beside it, the text size) and
the hot keys it held; the whole-book run's decisions on the frames and the frames it read or erased (each must be a
sharp one; one that was not, with who got it and when the run took a sharper one after it: ``run_gets``; a frame whose
reading was thrown away because a sharper one took its place meanwhile is left out of them and counted,
``readings_thrown_away``), how it ended and its requests; the requests of scenario x sent for nothing and what their
cancel cost. Into *--out*: report.json (with the lines of the rule for a request without an answer and of the
backlog's pause for it, ``no_answer``, each silence with what the server answered just then: `LogTap`); stacks.txt
when a request to the translator stays under way too long (`watch_stuck`: the threads' stacks, files, lines and
functions only); with --start-ollama the server's own log, ollama_server.log (no prompt or answer in it); and shots/ -
pictures of
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
import subprocess
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
    # (scenario k: its steps from `k_steps`, on pages no scenario before it turned to)
    "k5": ("flipped past at 0.5 s a page, read back", []),
    "k1": ("flipped past at 1 s a page, read back", []),
    "k2": ("flipped past at 2 s a page, read back", []),
    "k3": ("flipped past at 3 s a page, read back (by its name only)", []),
}
ORDER = ["c", "a", "b", "d", "e", "r", "t", "t2", "o", "z", "w", "w2", "x", "f", "f2"]
K_PACES = {"k5": 500, "k1": 1000, "k2": 2000, "k3": 3000}  # scenario k: ms a page (never in "all")
K_ASKED = ("k5", "k1", "k2")  # what "k" asks for (k3 only by its name)
K_READ_MS = 8000  # ... the pages read back at this pace
K_KEY_GIVE_UP_S = 3.0  # --k-keys: a key the window has not handed on so long after it was pressed releases its turn
K_STAYED_MS = 800  # ... a flipped page whose sharp frame stayed this long is caught (the gate's confirmation)
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
# --wait-done (a slower computer than the one the rests were written for): the rests of these scenarios held until
# their page is finished (`held`, `hold_over`), and scenario x's soft frames kept until the window asked on them,
# KEEP_SOFT_S at most. Not c (turns while the model loads), b (quick turns), t and t2 (a turn each, released by the
# window's page key), w and w2 (the run reads the pages the stand-in turns to; beside it they wait for the run).
HOLD_SCENARIOS = ("a", "d", "e", "r", "o", "z", "x", "f", "f2")
KEEP_SOFT_S = 15.0


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
    if "k" in asked:
        asked = (asked - {"k"}) | set(K_ASKED)
    unknown = asked - set(SCENARIOS)
    if unknown:
        raise SystemExit(f"unknown scenario(s): {', '.join(sorted(unknown))}")
    asked |= {other for one, other in PAIRS if one in asked}
    return [n for n in [*ORDER, *K_PACES] if n in asked]


def k_steps(name: str, fresh: int, width: int, turns: int, read: int, soft: bool,
            read_ms: int = K_READ_MS, keyed: bool = False, stay_ms: int = 0) -> list[str]:
    """Scenario k's steps at the pace of *name* (`K_PACES`): to page *fresh* (one no scenario before turned to) and a
    rest there, *turns* pages flipped past, the last of them kept *stay_ms* (0: the pace), back to the first of them,
    and *read* of them read at *read_ms* a page (K_READ_MS); without *soft*, every page drawn sharp at once (the
    stand-in's soft time and blur off, and back after). *keyed* (--k-keys): no wait of the stand-in's own - each turn
    waits for its release (``u``), at the times of `k_key_times`."""
    pace = K_PACES[name]
    pre, post = ([], []) if soft else (["t0", "b1"], ["t", "b"])
    if keyed:
        steps = [*pre, f"j{fresh}", *(["u", "n"] * turns), "u", f"j{fresh + width}", *(["u", "n"] * max(0, read - 1))]
        return [*steps, "u", *post]
    flips = ["n", f"w{pace}"] * turns
    if stay_ms and flips:
        flips[-1] = f"w{stay_ms}"
    steps = [*pre, f"j{fresh}", f"w{read_ms}", *flips, f"j{fresh + width}", f"w{read_ms}"]
    steps += ["n", f"w{read_ms}"] * max(0, read - 1)
    return [*steps, *post]


def k_key_times(pace_ms: int, turns: int, read: int, read_ms: int = K_READ_MS,
                stay_ms: int = 0) -> list[tuple[float, str]]:
    """--k-keys: when each turn of scenario k (`k_steps`, *keyed*) is released, in seconds after the pace began, and
    how: "key" by the window's page key handed on, "driver" by the driver alone (the turn back to the first page
    flipped past, and the end of the last page read back) - the times of the waits of the steps without keys."""
    out: list[tuple[float, str]] = []
    t = read_ms / 1000
    for i in range(turns):
        out.append((round(t, 3), "key"))
        t += (stay_ms if stay_ms and i == turns - 1 else pace_ms) / 1000
    out.append((round(t, 3), "driver"))
    for _ in range(max(0, read - 1)):
        t += read_ms / 1000
        out.append((round(t, 3), "key"))
    out.append((round(t + read_ms / 1000, 3), "driver"))
    return out


def cancel_steps(first: int, back: int, soft_ms: int, keep_ms: int | None = None) -> list[str]:
    """Scenario x's steps: the turns drawn soft for *soft_ms* at 1/CANCEL_FACTOR of the resolution, to the screens of
    little text from page *first* on (CANCEL_SCREENS spreads), then the stand-in's own soft time and blur again and
    back to page *back*, the screen before. With *keep_ms* (--wait-done) the turns are kept soft until the driver's
    word instead (``kN``: once the window asked on the soft frame, *keep_ms* at most)."""
    steps = [f"t{soft_ms}" if keep_ms is None else f"k{keep_ms}", f"b{CANCEL_FACTOR}"]
    for k in range(CANCEL_SCREENS):
        steps += [f"j{first + 2 * k}", "w5000"]
    return [*steps, "t" if keep_ms is None else "k", "b", f"j{back}", "w4000"]


def held(steps: list[str], first: int) -> list[str]:
    """--wait-done: *steps* with a hold (``hN``, numbered on from *first*) after each rest a reader takes - a wait of
    REST_MS or more -, the rest at their end too; the driver lets it go once the page on show is finished
    (`hold_over`). (The rest at the end is held as well because the driver changes the window as soon as the stand-in
    waits for the next scenario - a mode left, the theme, the text size or the stand-in's size changed, Finished
    reading -, before the window is at rest: a page still being translated then was cut short, as scenario f's last on
    a runner, by f2's narrow window.)"""
    out, n = [], first
    for step in steps:
        out.append(step)
        if step.startswith("w") and int(step[1:].split("-")[0]) >= REST_MS:
            out.append(f"h{n}")
            n += 1
    return out


def build_plan(names: list[str], count: int, cancel_first: int | None = None, soft_ms: int = 700,
               wait_done: float | None = None, k: dict[str, Any] | None = None
               ) -> tuple[list[Segment], list[sv.Step]]:
    """The segments of the stand-in's script (each held at ``gN`` until the driver releases it, ``mN`` to mark it)
    and the script; the screen each turn will show, foreseen as the page turns (spreads until the narrow window).
    Scenario x turns to the screens of little text from page *cancel_first* on (`cancel_steps`); scenario k's
    segments (`k_steps`, *k*: turns, read, soft, narrow) to pages after the farthest one turned to before. With
    *wait_done* (--wait-done's cap, seconds) the rests of HOLD_SCENARIOS are held (`held`) and x's soft frames kept
    until the window asked (KEEP_SOFT_S at most, and the cap); without it the script is the same as ever."""
    segments: list[Segment] = []
    index, spread, farthest = 0, True, 0
    text: list[str] = []
    holds = 0
    k = k or {}
    for go, name in enumerate(names, 1):
        if name in K_PACES and k.get("narrow"):
            spread = False
        if name == "x":
            keep = None if wait_done is None else round(min(wait_done, KEEP_SOFT_S) * 1000)
            steps = cancel_steps(cancel_first or 0, index, soft_ms, keep)
        elif name in K_PACES:
            width = 2 if spread else 1
            fresh = farthest + width
            fresh = fresh - fresh % 2 if spread else fresh
            steps = k_steps(name, fresh, width, int(k.get("turns", 20)), int(k.get("read", 20)),
                            bool(k.get("soft", True)), int(k.get("read_ms") or K_READ_MS), bool(k.get("keys")),
                            int(k.get("stay_ms") or 0))
        else:
            steps = SCENARIOS[name][1]
        if wait_done is not None and name in HOLD_SCENARIOS:
            steps = held(steps, holds + 1)
            holds += sum(1 for s in steps if s.startswith("h"))
        segment = Segment(name, go, steps)
        if name == "f2":
            spread = False
        for step in steps:
            if step in ("n", "p") or (step.startswith("j") and step[1:].isdigit()):
                width = 2 if spread else 1
                index = int(step[1:]) if step.startswith("j") else index + (width if step == "n" else -width)
                index = max(0, min(count - 1, index))
                index = index - index % 2 if spread else index
                farthest = max(farthest, index + width - 1)
                segment.screens.append((index, spread))
        segments.append(segment)
        text += [f"g{go}", f"m{go}", *steps]
    text.append("e")
    return segments, sv.parse_script(",".join(text))


def pages_needed(names: list[str], k_turns: int = 20) -> int:
    turns = sum(SCENARIOS[n][1].count("n") * (1 if n == "f2" else 2) for n in names)
    turns += sum(2 * (k_turns + 2) for n in names if n in K_PACES)
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
        # the stand-in's looks at Windows.Graphics.Capture: "frames" when it gave one, "none" when the capture went on
        # with PrintWindow (`capture_route`)
        self.compositor: Counter[str] = Counter()
        self.capture_n = 0  # every capture the window made, and when the last one was (`watch_frames`)
        self.last_capture_t = 0.0
        self.drawn_last: dict[str, Any] | None = None  # the screen the stand-in drew last (its page, state, when)
        self.frame_stalls: list[dict[str, Any]] = []  # (`watch_frames`)
        self.inputs: list[list[float]] = []  # spells of input to the computer from anyone (`watch_input`)
        self.tool_cover: dict[str, Any] | None = None  # the tool's own window over the stand-in (`--cover`)
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
        self.soft_looks: list[dict[str, Any]] = []  # each frame the window judged soft or sharp (`soft_look`)
        self.margins: list[dict[str, Any]] = []  # the capture area in force and the frame's own, as they changed
        self.modes: list[dict[str, Any]] = []  # reading, over the book, a run, beside it, text size, as changed
        self.hotkeys: list[dict[str, Any]] = []  # the hot keys the window held, as they changed, and the presses
        self.run_frames: list[dict[str, Any]] = []  # a whole-book run's decisions on the viewer's frames, and ...
        self.run_reads: list[dict[str, Any]] = []  # ... the frames it got from its store to read or erase
        self.run_ends: list[dict[str, Any]] = []
        # what the driver changed in the window between scenarios (a mode entered or left, the theme, the text size,
        # the stand-in's size, Finished reading), and when: a rest on the page before ends there (`turn_rows`)
        self.acts: list[dict[str, Any]] = []
        self.lookups: list[dict[str, Any]] = []  # each page unit a page job looked for in the cache, and what it found
        self.resolves: list[dict[str, Any]] = []  # ... and each look for the page as read at other sizes
        self.decides: list[dict[str, Any]] = []  # each page job kept for now, decided (`Pipeline.decide_kept`): how
        self.on_display: Callable[[dict[str, Any]], None] | None = None
        self.leaves: list[dict[str, Any]] = []  # each leave of the full screen: when, and the calls that led to it
        # where a page job's time went (`span`: its stages, by thread), the cuts of the pairs that only grow
        # (`GrowingContext.take`), and the loads and unloads of the model that leave the server holding nothing
        self.spans_off: list[tuple[str, float, float, str, Any]] = []  # (spans while no page job ran)
        self.cuts: list[dict[str, Any]] = []
        self.server_resets: list[dict[str, Any]] = []
        self.warms: list[dict[str, Any]] = []  # each step of the warming while the reader reads (no job's request)
        self.readings: list[dict[str, Any]] = []  # normal reading's events (`backlog`: no thumbnail, no text)
        self.backlog: list[dict[str, Any]] = []  # the backlog's catches and steps, with what it held after each
        self.warm_calls: list[dict[str, Any]] = []  # each warming begun (`PlamoTranslator.warm_prefix`): what it did
        # (memory only, never written or printed: a request's line as a number, to find a line asked for again)
        self.sources: dict[int, int] = {}
        self.side: SideCheck | None = None  # the indicator looked at from the window (`--side-indicator` not off)

    def span(self, label: str, t0: float, t1: float, extra: Any = None) -> None:
        """A stage of the page job running (*label*, from *t0* to *t1*, on this thread; *extra*: a code or a number),
        noted with that job (`spans_off` between jobs)."""
        rec = (label, t0, t1, threading.current_thread().name, extra)
        with self.lock:
            job = self.current
            if job is not None:
                job.setdefault("spans", []).append(rec)
            else:
                self.spans_off.append(rec)

    def cut(self, before: int, after: int) -> None:
        with self.lock:
            self.cuts.append({"t": now_ms(), "job": self.current["id"] if self.current else None,
                              "before": before, "after": after, "thread": threading.current_thread().name})

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
                        job["confirmed_t"] = job["open_until_t"] - (job["open_for"] or 0) * 1000
                    # (confirmed while the frames still changed: ``settled_by`` set; stayed after all: ``settled``;
                    # a frame the window took for a soft one: ``soft``)
                    job["settled"] = getattr(gate, "settled", None)
                    job["soft_gate"] = getattr(gate, "soft", None)
                    by = getattr(gate, "settled_by", None)
                    job["settled_by_t"] = job["over_t"] + (by - time.monotonic()) * 1000 if by is not None else None
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

    def reading(self, kind: str, data: dict[str, Any]) -> None:
        """A normal reading event (`backlog`), numbers only: the thumbnail's size, never the thumbnail."""
        thumb = data.get("thumb")
        rec = {"t": now_ms(), "kind": kind, **{k: data.get(k) for k in ("seq", "stage", "state", "into", "pages",
                                                                       "lines", "paused", "dropped")},
               "thumb": list(getattr(thumb, "size", ())) if thumb is not None else None}
        with self.lock:
            self.readings.append(rec)

    def backlog_note(self, what: str, backlog: Any, **facts: Any) -> None:
        """A catch or a step of the backlog, with what it held after it (the frames' bytes, the most at once, the
        units, the entries still holding a frame they were read from)."""
        try:
            with backlog._lock:
                entries = [*backlog.entries, *backlog._held.values()]
                held = {"bytes": backlog.bytes_held, "frames": backlog.frame_bytes, "regions": backlog.region_bytes,
                        "peak": backlog.peak_bytes, "units": backlog.unit_total, "entries": len(entries),
                        "framed_after_read": sum(1 for e in entries if e.units is not None
                                                 and (e.raw is not None or e.frame is not None))}
        except Exception as e:  # noqa: BLE001 - noted, never in the app's way
            held = {"error": type(e).__name__}
        with self.lock:
            self.backlog.append({"t": now_ms(), "what": what, **facts, **held})

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
                   "outcome": None, "http_t": None, "http_end_t": None, "server_ms": None, "load_ms": None,
                   "side": getattr(self.local, "side", None), "n": len(self.requests)}
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
        """A frame a whole-book run got from its store (`PageImages.frame`), and who got it: its reading loop ("read")
        or its erase ahead ("erase", the thread `batch.BatchReader._start_erasing` names), the only two callers."""
        by = "erase" if threading.current_thread().name == "batch-erase-ahead" else "read"
        with self.lock:
            self.run_reads.append({"t": now_ms(), "key": key, "by": by, **self.code(self.shown(image))})

    def run_read_again(self, key: Any) -> None:
        """The reading of the frame of *key* the run's reading loop got last was thrown away: a sharper picture of the
        page took its place meanwhile, and the page is read again from it (`batch.BatchReader._scan_sharp`)."""
        with self.lock:
            got = next((f for f in reversed(self.run_reads) if f["key"] == key and f["by"] == "read"), None)
            if got is not None:
                got["thrown_away"] = True

    def act(self, segment: str, what: str) -> None:
        with self.lock:
            self.acts.append({"t": now_ms(), "segment": segment, "act": what})

    def run_end(self, progress: Any) -> None:
        ended = getattr(progress, "summary", None) or getattr(progress, "reason", None)
        with self.lock:
            self.run_ends.append({"t": now_ms(), "code": str(getattr(ended, "code", type(ended).__name__)),
                                  "pages": getattr(progress, "pages", None)})

    def soft_look(self, image: Any, own: Any, viewer: Any, soft: bool) -> None:
        """The window judged *image* soft or not (`_looks_soft`): its page's own sharp picture's verdict (*own*: True
        sharp, False soft, None no picture of it kept, "-" not asked), the viewer's pictures of all pages' (*viewer*,
        `looks_sharp`: True sharp, "-" not asked), the window's (*soft*), and what the stand-in drew there."""
        rec = {"t": now_ms(), **self.code(self.shown(image)), "own": own, "viewer": viewer, "soft": soft}
        with self.lock:
            self.soft_looks.append(rec)

    def captured(self, image: Any) -> None:
        shown = self.shown(image)
        rec = {"t": now_ms(), **self.code(shown), "size": list(getattr(image, "size", (0, 0)))}
        with self.lock:
            self.capture_counts[rec["state"]] += 1
            self.capture_n += 1
            self.last_capture_t = rec["t"]
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

    # the lines of the rule for a request without an answer (`translate.ollama`, `ollama_start.OllamaStarter.restart`,
    # `pipeline.LoadAhead`) and of the backlog's pause for it: fixed words, numbers and a thread's name, never a line
    NO_ANSWER_PREFIXES = ("no answer:", "backlog paused: the translation program", "backlog goes on:")
    # the window's lines of the viewer kept under it and of the viewer hidden wholly (`ui.order`): fixed words and
    # numbers only
    WINDOW_ORDER_PREFIXES = ("window order:", "the viewer is hidden wholly")

    def __init__(self, notes: Notes, url: str | None = None):
        super().__init__(logging.INFO)
        self.notes = notes
        self.url = url
        self.levels: Counter[str] = Counter()
        self.no_answer: list[dict[str, Any]] = []
        self.window_order: list[dict[str, Any]] = []

    def _no_answer(self, record: logging.LogRecord) -> None:
        """A line of the rule kept with its time and thread; for the first line of each silence (it names the
        incident) what the server answers just then (`server_says`, on a thread of the tool's own)."""
        line = {"t": now_ms(), "line": record.getMessage()[:300], "thread": record.threadName}
        with self.notes.lock:
            self.no_answer.append(line)
        if self.url and "(incident" in line["line"] and ", silence " in line["line"]:
            threading.Thread(target=lambda: line.__setitem__("server_says", server_says(self.url)),
                             name="standin-no-answer-probe", daemon=True).start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.msg if isinstance(record.msg, str) else ""
            if msg.startswith(self.NO_ANSWER_PREFIXES):
                self._no_answer(record)
            if msg.startswith(self.WINDOW_ORDER_PREFIXES):
                with self.notes.lock:
                    self.window_order.append({"t": now_ms(), "line": record.getMessage()[:200]})
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


# ---------------------------------------------------------------------------------------------------- the indicator
SIDE_CHECK_MS = 200  # the indicator beside the page looked at this long after an event of normal reading (at most)


class SideCheck:
    """The indicator beside the page (`ui.side`) looked at from the window itself (scenario k with it on): what normal
    reading told it (``page_stage`` with ``reading``, ``page_on_show``, ``backlog``), kept here as the indicator's
    rules take it (a stage the latest told, "merged" takes a screen away, a drop or another book's screen 1 clears),
    against what its model holds and what its canvas has drawn - each screen's cell or rail mark in the state last
    told, the screen on show outlined, a screen that went by drawn as missed, nothing left after a drop. Numbers and
    screen numbers only. Runs on the Tk thread (the event handler, and a check `SIDE_CHECK_MS` after an event, never
    inside the event pump)."""

    def __init__(self, notes: Notes):
        self.notes = notes
        self.told: dict[int, dict[str, str]] = {}
        self.prints: dict[int, str] = {}
        self.on_show: int | None = None
        self.totals: tuple[int, int, bool, int] | None = None
        self.pending: str | None = None
        self.checks = 0
        self.check_ms: list[float] = []
        self.wrong: Counter[str] = Counter()
        self.examples: dict[str, list[Any]] = {}
        self.kinds: Counter[str] = Counter()
        self.layouts: Counter[str] = Counter()
        self.ever: set[tuple[int, str]] = set()  # (seq, fingerprint) of every screen told
        self.missed_told: set[tuple[int, str]] = set()
        self.missed_drawn: set[tuple[int, str]] = set()
        self.on_show_drawn = 0
        self.on_show_checked = 0
        self.drops: list[dict[str, Any]] = []

    # what was told
    def told_event(self, app: Any, kind: str, data: dict[str, Any]) -> None:
        from taslation import fingerprint as fp
        from taslation.ui.constants import in_a_run
        from taslation.ui.side_model import MERGED, SIDE_STAGES, STATES

        self.kinds[kind] += 1
        if kind == "backlog":
            if data.get("dropped") is True:
                self.told.clear()
                self.prints.clear()
                self.on_show = None
            self.totals = (_count_of(data.get("pages")), _count_of(data.get("lines")), bool(data.get("paused")),
                           0 if data.get("dropped") is True else _count_of(data.get("dropped")))
            return
        if kind == "page_on_show":
            try:
                self.on_show = None if data.get("seq") is None else int(data["seq"])
            except (TypeError, ValueError):
                self.on_show = None
            return
        if in_a_run(app):
            return
        try:
            seq = int(data.get("seq"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        print_ = str(data.get("fingerprint") or "")
        old = self.prints.get(seq)
        within = int(getattr(app.settings, "fingerprint_max_distance", 0) or 0)
        if old and print_:
            try:
                other = fp.hamming(old, print_) > within
            except (TypeError, ValueError):
                other = old != print_
            if other:  # (the engine numbers another book's screens from 1 again)
                self.told.clear()
                self.prints.clear()
                self.on_show = None
        stage, state = data.get("stage"), data.get("state")
        if stage == "read" and state == MERGED:
            if self.told.pop(seq, None) is not None:
                self.prints.pop(seq, None)
                if self.on_show == seq:
                    self.on_show = None
            return
        stages = self.told.setdefault(seq, {s: "waiting" for s in SIDE_STAGES})
        if print_ and not self.prints.get(seq):
            self.prints[seq] = print_
        if stage in SIDE_STAGES and state in STATES:
            stages[stage] = state
        key = (seq, self.prints.get(seq, ""))
        self.ever.add(key)
        if stages["read"] == "missed" or stages["translate"] == "missed":
            self.missed_told.add(key)

    def handled(self, app: Any, kind: str, data: dict[str, Any]) -> None:
        """(the event handled) A drop looked at at once; the rest a little later."""
        if kind == "backlog" and data.get("dropped") is True:
            self.drop_looked(app)
        if self.pending is None:
            try:
                self.pending = app.after(SIDE_CHECK_MS, lambda: self.check(app))
            except Exception:  # noqa: BLE001 - the window closing
                self.pending = None

    def _wrong(self, what: str, example: Any) -> None:
        self.wrong[what] += 1
        items = self.examples.setdefault(what, [])
        if len(items) < 5:
            items.append(example)

    # what the window holds
    def drop_looked(self, app: Any) -> None:
        st = getattr(app, "_side", None)
        if st is None:
            return
        model, view = st.model, st.view
        left = sorted(model.screens)
        drawn = self._drawn_screens(view) if view is not None else []
        rec = {"t": now_ms(), "screens_left": len(left), "on_show": model.on_show, "drawn_left": len(drawn)}
        self.drops.append(rec)
        if left or model.on_show is not None or drawn:
            self._wrong("drop_not_cleared", rec)

    @staticmethod
    def _drawn_screens(view: Any) -> list[str]:
        """The canvas items of a screen's cell (``s<seq>``) or a rail mark (``mark-<mark>``)."""
        out = []
        try:
            for item in view.find_all():
                tags = view.gettags(item)
                if any((t.startswith("s") and t[1:].isdigit()) or t.startswith("mark-") for t in tags):
                    out.append(item)
        except Exception:  # noqa: BLE001 - the widget gone
            return []
        return out

    def check(self, app: Any) -> None:
        self.pending = None
        began = time.perf_counter()
        try:
            self._check(app)
        except Exception as e:  # noqa: BLE001 - noted, never in the app's way
            self.notes.error("side check", type(e).__name__)
        self.check_ms.append((time.perf_counter() - began) * 1000)

    def _check(self, app: Any) -> None:
        from taslation.ui.side_model import Screen

        st = getattr(app, "_side", None)
        if st is None:
            self._wrong("no_indicator", None)
            return
        self.checks += 1
        model, view = st.model, st.view
        if set(model.screens) != set(self.told):
            self._wrong("screens", {"told": sorted(self.told), "model": sorted(model.screens)})
        for seq, stages in self.told.items():
            screen = model.screens.get(seq)
            if screen is not None and dict(screen.stages) != stages:
                self._wrong("stages", {"seq": seq, "told": dict(stages), "model": dict(screen.stages)})
        if model.on_show != self.on_show:
            self._wrong("on_show", {"told": self.on_show, "model": model.on_show})
        if self.totals is not None:
            b = model.backlog
            if (b.pages, b.lines, b.paused, b.dropped) != self.totals:
                self._wrong("totals", {"told": list(self.totals), "model": [b.pages, b.lines, b.paused, b.dropped]})
        kind = view.layout.kind if view is not None and view.shown else ""
        self.layouts[kind or "none"] += 1
        if not kind:
            return
        if kind == "column":
            self._check_column(view, model)
        else:
            self._check_rail(view, model)
        for seq, stages in self.told.items():  # (the screens that went by, drawn as such)
            told = Screen(seq, stages=dict(stages))
            if told.mark == "missed" and self._drawn_missed(view, model, seq, kind):
                self.missed_drawn.add((seq, self.prints.get(seq, "")))

    def _bar_state(self, view: Any, box: tuple[int, int, int, int], seq: int) -> str:
        from taslation.ui.side_view import MISSED
        from taslation.ui.strip import DONE, EDGE, FAILED, SKIPPED

        x0, y0, x1, y1 = box
        items = [i for i in view.find_overlapping(x0 - 1, y0 - 1, x1 + 1, y1 + 1)
                 if f"s{seq}" in view.gettags(i) and "marks" not in view.gettags(i)
                 and view.type(i) in ("rectangle", "line")]
        if any("stripe" in view.gettags(i) for i in items):
            return "working"
        rects = [i for i in items if view.type(i) == "rectangle"]
        fills = {str(view.itemcget(i, "fill")).lower() for i in rects}
        if DONE.lower() in fills:
            return "done"
        if FAILED.lower() in fills:
            return "failed"
        if any(str(view.itemcget(i, "dash")) and str(view.itemcget(i, "outline")).lower() == MISSED.lower()
               for i in rects):
            return "missed"
        outlines = {str(view.itemcget(i, "outline")).lower() for i in rects}
        if SKIPPED.lower() in outlines:
            return "skipped"
        if EDGE.lower() in outlines:
            return "waiting"
        return "?"

    def _check_column(self, view: Any, model: Any) -> None:
        from taslation.ui.side_model import SIDE_STAGES
        from taslation.ui.strip import CHOSEN

        for index, seq in enumerate(model.order):
            screen = model.screens[seq]
            parts = view._cell_parts(index)
            for stage in SIDE_STAGES:
                drawn = self._bar_state(view, parts[stage], seq)
                if drawn != screen.state(stage):
                    self._wrong("bar", {"seq": seq, "stage": stage, "state": screen.state(stage), "drawn": drawn})
            outlined = any(view.type(i) == "rectangle" and str(view.itemcget(i, "outline")).lower() == CHOSEN.lower()
                           for i in view.find_withtag(f"s{seq}") if "marks" in view.gettags(i))
            if seq == model.on_show:
                self.on_show_checked += 1
                self.on_show_drawn += outlined
                if not outlined:
                    self._wrong("on_show_not_outlined", {"seq": seq})
            elif outlined:
                self._wrong("outlined_not_on_show", {"seq": seq, "on_show": model.on_show})

    def _check_rail(self, view: Any, model: Any) -> None:
        marks = list(getattr(view, "_marks", []) or [])
        seen = [s for m in marks for s in m.seqs]
        if sorted(seen) != list(model.order):
            self._wrong("rail_screens", {"marks": len(seen), "model": len(model.order)})
        rx, rw = view.layout.rail_x, view.layout.rail_w
        for m in marks:
            want = {model.screens[s].mark for s in m.seqs if s in model.screens}
            if len(m.seqs) == 1 and want and m.mark not in want:
                self._wrong("rail_mark", {"seqs": list(m.seqs), "mark": m.mark, "model": sorted(want)})
            drawn = {t for i in view.find_overlapping(rx, m.y0, rx + rw - 1, max(m.y0 + 1, m.y1) - 1)
                     for t in view.gettags(i) if t.startswith("mark-")}
            if f"mark-{m.mark}" not in drawn:
                self._wrong("rail_mark_not_drawn", {"seqs": [m.seqs[0], m.seqs[-1]], "mark": m.mark})
        on = [m for m in marks if m.on_show]
        outlined = bool(view.find_withtag("on-show"))
        if model.on_show is not None and model.on_show in model.screens:
            self.on_show_checked += 1
            ok = len(on) == 1 and model.on_show in on[0].seqs and outlined
            self.on_show_drawn += ok
            if not ok:
                self._wrong("on_show_not_outlined", {"seq": model.on_show, "marks_on_show": len(on)})
        elif on or outlined:
            self._wrong("outlined_not_on_show", {"on_show": model.on_show})

    def _drawn_missed(self, view: Any, model: Any, seq: int, kind: str) -> bool:
        if seq not in model.screens:
            return False
        if kind == "column":
            index = model.order.index(seq)
            parts = view._cell_parts(index)
            return "missed" in (self._bar_state(view, parts["read"], seq), self._bar_state(view, parts["translate"], seq))
        return any(seq in m.seqs and m.mark == "missed" for m in getattr(view, "_marks", []) or [])

    def report(self) -> dict[str, Any]:
        ms = sorted(self.check_ms)
        return {"checks": self.checks, "events": dict(self.kinds), "layouts": dict(self.layouts),
                "wrong": dict(self.wrong), "examples": self.examples,
                "screens_told": len(self.ever), "missed_told": len(self.missed_told),
                "missed_drawn_as_missed": len(self.missed_drawn & self.missed_told),
                "on_show_outlined": [self.on_show_drawn, self.on_show_checked],
                "drops": self.drops,
                "check_ms": {"median": round(statistics.median(ms), 2), "max": round(ms[-1], 1)} if ms else None}


def _count_of(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


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


FULL_MS_PER_TOKEN = 1.0  # a request whose prompt took the server this long per prompt token was computed from its start
FULL_MS_LEAST = 250  # ... and at least this long (an extending request: about 75 to 125 ms with its tail)


class ServerState:
    """What the translator's server holds after each request, in memory only (the last prompt and its answer, never
    written or printed), so that each request can be told against it: the part of the prompt it shares with what the
    server holds, and where it parts and why (`prompt_replay.why`: "extends", "history cut", "context block", ...);
    "first after load" after a load or an unload of the model. A main request after a request beside the page's own
    (asked again, romanised, aside) that would have extended the main one before it is "after <kind>"."""

    def __init__(self, notes: Notes):
        import prompt_replay

        self.pr = prompt_replay
        self.notes = notes
        self.lock = threading.Lock()
        self.last: Any = None
        self.main: Any = None

    def reset(self, why: str) -> None:
        with self.lock:
            self.last = self.main = None
        with self.notes.lock:
            self.notes.server_resets.append({"t": now_ms(), "why": why,
                                             "job": self.notes.current["id"] if self.notes.current else None})

    def asked(self, rec: dict[str, Any], prompt: str, answer: str) -> None:
        pr = self.pr
        from taslation.translate import plamo as pl

        try:
            side = rec.get("side")
            cur = pr.Asked(side or "line", pr.shape_of(prompt), answer, None, {})
            with self.lock:
                prev, main = self.last, self.main
                if prev is None:
                    reason, kept = "first after load", 0
                else:
                    kept = pr.common(prompt, prev.state)
                    reason = pr.why(cur, prev)[0]
                    if reason != "extends" and side is None and prev.kind in pr.SIDE_KINDS and main is not None \
                            and pr.why(cur, main)[0] == "extends":
                        reason = f"after {prev.kind}"
                self.last = cur
                if side is None:
                    self.main = cur
            rec["why"] = reason
            rec["prompt_tokens_est"] = pl.tokens_about(prompt)
            rec["kept_tokens_est"] = pl.tokens_about(prompt[:kept]) if kept else 0
            rec["joined"] = "\n" in cur.shape.source
            rec["pairs"] = len(cur.shape.pairs)
            with self.notes.lock:
                self.notes.sources[rec["n"]] = hash(cur.shape.source)
        except Exception as e:  # noqa: BLE001 - noted, never in the app's way
            self.notes.error("server state", type(e).__name__)


def full_computed(rec: dict[str, Any]) -> bool | None:
    """Whether the server computed the request's prompt from its start (by its own prompt time: `FULL_MS_PER_TOKEN`
    per prompt token and `FULL_MS_LEAST`); None without the server's counters."""
    n, took = rec.get("prompt_n"), rec.get("prompt_ms")
    if not n or took is None:
        return None
    return took >= max(FULL_MS_LEAST, FULL_MS_PER_TOKEN * n)


# the page job's stages noted (`Notes.span`): (the class's module, class, method, label)
STAGES = (("pipeline", "Pipeline", "process", "process"), ("pipeline", "Pipeline", "units_of", "units"),
          ("pipeline", "Pipeline", "_resolve", "resolve"), ("pipeline", "Pipeline", "_detect", "detect"),
          ("pipeline", "Pipeline", "_annotate", "annotate"), ("pipeline", "Pipeline", "_ocr_regions", "ocr"),
          ("pipeline", "Pipeline", "_take_corrections", "order"), ("pipeline", "Pipeline", "_order_read", "order"),
          ("pipeline", "Pipeline", "share_rooms", "order"), ("pipeline", "Pipeline", "_translate_regions", "translate"),
          ("pipeline", "Pipeline", "_complete_page", "complete"), ("pipeline", "Pipeline", "tighten", "tighten"),
          ("pipeline", "Pipeline", "review", "review"), ("pipeline", "Pipeline", "_locate_large", "large"),
          ("pipeline", "Pipeline", "_store_regions", "store"), ("pipeline", "Pipeline", "_render", "render"),
          ("pipeline", "Pipeline", "letter_region", "letter"), ("pipeline", "Pipeline", "flush_saves", "save"),
          ("pipeline", "Pipeline", "keep_shown", "keep_shown"), ("pipeline", "Pipeline", "_early_look", "early_look"),
          ("pipeline", "PageGate", "on_show", "gate_wait"), ("pipeline", "PageWork", "settle", "settle"),
          ("pipeline", "PageFill", "wait", "drafts_wait"), ("pipeline", "LoadAhead", "_run", "load_ahead"),
          ("translate.ollama", "OllamaTranslator", "ensure_loaded", "ensure_loaded"),
          ("translate.plamo", "PlamoTranslator", "warm_up", "warm_up"),
          ("translate.ollama", "OllamaTranslator", "warm_up", "warm_up"))
SIDES = (("pipeline", "ask_for_missing", "re-ask"), ("pipeline", "ask_again_romanised", "romanised"))


def stages(notes: Notes, server: ServerState) -> None:
    """The hooks of where a page job's time goes (`STAGES`, each a `Notes.span`; inside `keep_shown` a stage's label
    begins with "ks."), the OCR readers' reads with the device each ran on (`DeviceModels.run`: "ocr_read"), the
    requests beside a page's own marked with their kind (`SIDES`, `translate_aside`), the cuts of the pairs that only
    grow, and the server's state reset by a load or an unload of the model (`ServerState`)."""
    import importlib

    from taslation.ocr import place
    from taslation.translate import base
    from taslation.translate import plamo as plamo_mod

    def spanned(cls: Any, name: str, label: str) -> None:
        original = cls.__dict__.get(name)
        if original is None or getattr(original, "_staged", False):
            return

        def call(self: Any, *a: Any, **k: Any) -> Any:
            inside = getattr(notes.local, "ks", 0)
            if label == "keep_shown":
                notes.local.ks = inside + 1
            t0 = now_ms()
            try:
                return original(self, *a, **k)
            finally:
                if label == "keep_shown":
                    notes.local.ks = inside
                notes.span(("ks." + label) if inside else label, t0, now_ms())

        call.__name__ = name
        call._staged = True  # type: ignore[attr-defined]
        setattr(cls, name, call)

    for module, cls_name, name, label in STAGES:
        cls = getattr(importlib.import_module("taslation." + module), cls_name, None)
        if cls is not None:
            spanned(cls, name, label)
    for module, name, kind in SIDES:
        mod = importlib.import_module("taslation." + module)
        fn = getattr(mod, name, None)
        if fn is None:
            continue

        def marked(*a: Any, _fn: Callable[..., Any] = fn, _kind: str = kind, **k: Any) -> Any:
            held = getattr(notes.local, "side", None)
            notes.local.side = _kind
            try:
                return _fn(*a, **k)
            finally:
                notes.local.side = held

        setattr(mod, name, marked)
    aside = plamo_mod.PlamoTranslator.translate_aside

    def asked_aside(self: Any, *a: Any, **k: Any) -> Any:
        held = getattr(notes.local, "side", None)
        notes.local.side = "aside"
        try:
            return aside(self, *a, **k)
        finally:
            notes.local.side = held

    plamo_mod.PlamoTranslator.translate_aside = asked_aside
    run = place.DeviceModels.run

    def read_on(self: Any, read: Callable[..., Any]) -> Any:
        def timed_read(device: str, models: Any) -> Any:
            t0 = now_ms()
            try:
                return read(device, models)
            finally:
                notes.span("ocr_read", t0, now_ms(), str(device))

        return run(self, timed_read)

    place.DeviceModels.run = read_on
    take = base.GrowingContext.take

    def took(self: Any, *a: Any, **k: Any) -> Any:
        before, cuts = len(self), self.cuts
        out = take(self, *a, **k)
        if self.cuts != cuts:
            notes.cut(before, len(out))
        return out

    base.GrowingContext.take = took
    warm, unload = plamo_mod.PlamoTranslator.warm_up, plamo_mod.PlamoTranslator._unload

    def warmed(self: Any, *a: Any, **k: Any) -> Any:
        try:
            return warm(self, *a, **k)
        finally:
            server.reset("load")

    def unloaded(self: Any, *a: Any, **k: Any) -> Any:
        try:
            return unload(self, *a, **k)
        finally:
            server.reset("unload")

    warmed._staged = True  # type: ignore[attr-defined]
    plamo_mod.PlamoTranslator.warm_up, plamo_mod.PlamoTranslator._unload = warmed, unloaded


STUCK_NO_HTTP_S = 20.0  # a request this long under way that has not gone out over HTTP: the threads' stacks written
STUCK_S = 60.0  # ... and one this long under way at all
STUCK_DUMPS = 6
STUCK_TK_S = 20.0  # the Tk thread this long without a tick of the driver: the stacks written as well
PROBE_S = 5.0  # each question the watch asks the server on a dump, on a connection of its own


def server_says(url: str | None) -> str:
    """What the server at *url* answers just then, on connections of the watch's own: whether /api/version answers and
    how fast, and what /api/ps lists (each model's name, its memory on the GPU and when it expires) - to tell a server
    that answers nothing, one whose model went away and one that answers this but not the window's request."""
    if not url:
        return "server: not asked"
    t0 = time.monotonic()
    try:
        version = ollama_get(url, "/api/version", timeout=PROBE_S)
        t1 = time.monotonic()
        ps = ollama_get(url, "/api/ps", timeout=PROBE_S)
    except Exception as e:  # (the window's network guard, say: the watch goes on)
        return f"server: not asked ({type(e).__name__})"
    t2 = time.monotonic()
    said = (f"server: version {version.get('version') if isinstance(version, dict) else 'no answer'} "
            f"in {round((t1 - t0) * 1000)} ms; ps ")
    if not isinstance(ps, dict):
        return said + f"no answer in {round((t2 - t1) * 1000)} ms"
    models = [f"{m.get('name') or m.get('model')} ({round(int(m.get('size_vram') or 0) / 2 ** 20)} MiB on the GPU, "
              f"expires {m.get('expires_at')})" for m in ps.get("models") or []]
    return said + f"{models or 'nothing loaded'} in {round((t2 - t1) * 1000)} ms"


def watch_stuck(notes: Notes, path: Path, url: str | None = None) -> None:
    """A thread of the tool's own that writes every thread's stack to *path* (each frame's file, line and function:
    no source line, no value) when a request to the translator has been under way STUCK_NO_HTTP_S without going out
    over HTTP, or STUCK_S at all, or the Tk thread has not ticked for STUCK_TK_S - what a translation that stops
    without an error is found by. STUCK_DUMPS at most, one per such request or silence, each with the requests then
    under way (their kind, job, age and whether they went out) and what the server at *url* answers then
    (`server_says`)."""
    dumped: set[int] = set()
    silences: set[float] = set()

    def look() -> None:
        while len(dumped) + len(silences) < STUCK_DUMPS:
            time.sleep(2.0)
            now = now_ms()
            with notes.lock:
                open_ = [dict(r) for r in notes.requests if r["end_t"] is None]
                last_tick = notes.tk_cpu[-1][0] if notes.tk_cpu else None
            stuck = [r for r in open_ if r["n"] not in dumped and (
                now - r["t"] > STUCK_S * 1000 or (r["http_t"] is None and now - r["t"] > STUCK_NO_HTTP_S * 1000))]
            silent = (last_tick is not None and last_tick not in silences
                      and time.monotonic() - last_tick > STUCK_TK_S)
            if not stuck and not silent:
                continue
            dumped.update(r["n"] for r in stuck)
            if silent:
                silences.add(last_tick)
            names = {t.ident: t.name for t in threading.enumerate()}
            lines = [f"== {time.strftime('%H:%M:%S')}: requests under way "
                     + ", ".join(f"#{r['n']} {r['kind']} job {r['job']} {round((now - r['t']) / 1000)} s"
                                 f"{'' if r['http_t'] else ' (not sent)'}" for r in open_)
                     + (f"; the Tk thread silent {round(time.monotonic() - last_tick)} s" if silent else ""),
                     server_says(url)]
            for ident, frame in sys._current_frames().items():
                lines.append(f"-- thread {names.get(ident, ident)}")
                lines += [f"   {fs.filename}:{fs.lineno} {fs.name}" for fs in traceback.extract_stack(frame)]
            with contextlib.suppress(OSError):
                with open(path, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")

    threading.Thread(target=look, name="tool-watch-stuck", daemon=True).start()


FRAME_STALL_S = 6.0  # a sharp screen the stand-in drew and kept this long that no frame the window took showed ...
FRAME_STALL_CAPTURES = 3  # ... while the window took this many frames: its frames are standing still
FRAME_PROBE_AT_S = (0.0, 30.0, 120.0, 300.0)  # when a stall is looked at, from its finding
FRESH_FRAME_S = 2.0  # how long the probe's own capture session waits for its first frame
COVER_GRID = 8  # the points of the stand-in's client area (COVER_GRID squared) the probe asks which window is on top


def last_input_tick() -> int | None:
    """The system's tick count (ms) at anyone's last input to the computer (keys, mouse, touch: `GetLastInputInfo`, a
    time and nothing else); None when it cannot be had."""
    class Last(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    last = Last()
    last.cbSize = ctypes.sizeof(Last)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last)):
        return None
    return int(last.dwTime)


def idle_seconds() -> float:
    """How long ago anyone gave the computer input (`last_input_tick`); -1 when it cannot be told."""
    tick = last_input_tick()
    if tick is None:
        return -1.0
    return ((ctypes.windll.kernel32.GetTickCount() - tick) & 0xFFFFFFFF) / 1000.0


def watch_input(notes: Notes, stop: threading.Event | None = None, every: float = 1.0) -> threading.Thread:
    """A thread that notes when the computer got input from anyone in the run (this tool sends none, nor the window
    under its guard): spells of seconds with input, merged within 3 s - a run with a person at the machine is told
    from one without. *stop* ends it, *every* its pace (tests); its thread."""
    def look() -> None:
        seen = last_input_tick()
        while not (stop.wait(every) if stop is not None else time.sleep(every)):
            tick = last_input_tick()
            if tick is None or tick == seen:  # (the tick itself compared: a time worked out from it jitters)
                continue
            seen = tick
            at = now_ms() - ((ctypes.windll.kernel32.GetTickCount() - tick) & 0xFFFFFFFF)
            with notes.lock:
                if notes.inputs and at - notes.inputs[-1][1] < 3000:
                    notes.inputs[-1][1] = at
                else:
                    notes.inputs.append([at, at])

    thread = threading.Thread(target=look, name="tool-watch-input", daemon=True)
    thread.start()
    return thread


def window_cover(hwnd: int, own_pid: int, standin_pids: Callable[[], set[int]] = set) -> dict[str, Any]:
    """Which window is on top at COVER_GRID x COVER_GRID points of the stand-in's client area (the stand-in, another
    window of the stand-in's browser - its processes *standin_pids* -, a TASlation window, the tool's cover, or
    another program by its file name; no window's title), which one is in front, and whether the stand-in is
    minimised, hidden or cloaked: a browser window wholly covered by opaque ones stops drawing."""
    from taslation.capture import client_rect_on_screen, program_name
    from taslation.capture import windows as win

    user32 = ctypes.WinDLL("user32")
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

    def who(h: Any) -> str:
        h = int(h or 0)
        if not h:
            return "none"
        if h == hwnd:
            return "stand-in"
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == own_pid:
            return "tool cover" if win.window_class(h) == COVER_CLASS else "TASlation"
        if pid.value in browser:
            return "stand-in browser"
        return program_name(pid.value) or "?"

    browser = set(standin_pids())
    x, y, w, h = client_rect_on_screen(hwnd)
    points: Counter[str] = Counter()
    for i in range(COVER_GRID):
        for j in range(COVER_GRID):
            p = wintypes.POINT(x + w * (2 * i + 1) // (2 * COVER_GRID), y + h * (2 * j + 1) // (2 * COVER_GRID))
            points[who(user32.GetAncestor(user32.WindowFromPoint(p), 2))] += 1  # (GA_ROOT)
    return {"points": dict(points), "front": who(user32.GetForegroundWindow()),
            "iconic": bool(ctypes.windll.user32.IsIconic(hwnd)),
            "visible": bool(ctypes.windll.user32.IsWindowVisible(hwnd)), "cloaked": win._is_cloaked(hwnd),
            "client": [x, y, w, h]}


def fresh_frame(notes: Notes, hwnd: int) -> dict[str, Any]:
    """The stand-in as a capture session of the probe's own sees it (its first frame is the window as the compositor
    holds it now), decoded and let go (nothing kept): the same page as the window's frames - the browser drew nothing
    new -, or the page the stand-in drew - the window's session stands still."""
    from taslation.capture import wgc
    from taslation.capture import windows as win

    import numpy as np

    try:
        from windows_capture import WindowsCapture
    except Exception as e:  # noqa: BLE001 - said by its type
        return {"none": type(e).__name__}
    got: dict[str, Any] = {}
    done = threading.Event()
    t0 = time.monotonic()
    capture = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd)

    def on_frame_arrived(frame: Any, control: Any) -> None:
        if "bgra" not in got:
            got["bgra"], got["ms"] = np.array(frame.frame_buffer, copy=True), round((time.monotonic() - t0) * 1000)
            done.set()
        control.stop()

    def on_closed() -> None:
        done.set()

    capture.event(on_frame_arrived)
    capture.event(on_closed)
    try:
        control = capture.start_free_threaded()
    except Exception as e:  # noqa: BLE001
        return {"none": type(e).__name__}
    done.wait(FRESH_FRAME_S)
    with contextlib.suppress(Exception):
        control.stop()
    if "bgra" not in got:
        return {"none": f"no frame in {FRESH_FRAME_S:g} s"}
    bgra = got.pop("bgra")
    box = wgc.crop_box((bgra.shape[1], bgra.shape[0]), win._frame_bounds(hwnd), win._client_box(hwnd))
    image = wgc.Frame(bgra, 0).image(box) if box is not None else None
    return {"ms": got["ms"], "shows": Notes.code(notes.shown(image)) if image is not None else "another size"}


def watch_frames(notes: Notes, hwnd: int, own_pid: int, path: Path, stop: threading.Event | None = None,
                 every: float = 0.5, standin_pids: Callable[[], set[int]] = set) -> threading.Thread:
    """A thread that finds the window's frames of the stand-in standing still: a sharp screen the stand-in drew and
    kept FRAME_STALL_S that no frame the window took showed, while it took FRAME_STALL_CAPTURES or more. Each stall
    noted from then until the window's frames move again (one of another screen, or more of its capture session),
    and looked at FRAME_PROBE_AT_S after its finding: the window's capture session (its frame count, ended, its
    thread), the probe's own session's first frame (`fresh_frame`), what covers the stand-in (`window_cover`), the
    seconds since anyone's input; the threads' stacks written to *path* once a stall (the first three). *stop* ends
    it, *every* its pace (tests); its thread."""
    from taslation.capture import wgc

    def probe(stall: dict[str, Any]) -> None:
        s = wgc._session
        look: dict[str, Any] = {"t": now_ms(), "idle_s": round(idle_seconds(), 1)}
        look["window_session"] = None if s is None else {
            "this_window": s.hwnd == hwnd, "frames": s.seq, "ended": s.ended, "error": (s.error or "")[:120],
            "age_s": round(time.monotonic() - s.started, 1), "thread_alive": s._thread.is_alive()}
        try:
            look["cover"] = window_cover(hwnd, own_pid, standin_pids)
        except Exception as e:  # noqa: BLE001
            look["cover"] = type(e).__name__
        try:
            look["fresh"] = fresh_frame(notes, hwnd)
        except Exception as e:  # noqa: BLE001
            look["fresh"] = type(e).__name__
        with notes.lock:
            look["drawn"] = dict(notes.drawn_last) if notes.drawn_last else None
            stall["probes"].append(look)

    def stacks(header: str) -> None:
        names = {t.ident: t.name for t in threading.enumerate()}
        lines = [header]
        for ident, frame in sys._current_frames().items():
            lines.append(f"-- thread {names.get(ident, ident)}")
            lines += [f"   {fs.filename}:{fs.lineno} {fs.name}" for fs in traceback.extract_stack(frame)]
        with contextlib.suppress(OSError):
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

    def window_frames() -> int | None:
        """How many frames the window's capture session of the stand-in has had (None: no session of it)."""
        s = wgc._session
        return s.seq if s is not None and s.hwnd == hwnd and not s.ended else None

    def go_on() -> bool:
        if stop is None:
            time.sleep(every)
            return True
        return not stop.wait(every)

    def look() -> None:
        stall: dict[str, Any] | None = None
        while go_on():
            with notes.lock:
                drawn = dict(notes.drawn_last) if notes.drawn_last else None
                last = notes.captures[-1] if notes.captures else None
                shows = (last["page"], last["spread"], last["state"]) if last else None
                n, last_t = notes.capture_n, notes.last_capture_t
            now = now_ms()
            frames = window_frames()
            if stall is not None:  # (it ends as the window's frames move again: a frame of another screen, or more
                # frames of its session - not a turn of the stand-in to the screen the frames stood still on)
                moved = frames is not None and stall["frames_at_find"] is not None and frames > stall["frames_at_find"]
                if shows != stall["frozen"] or moved:
                    with notes.lock:
                        stall.update(until_t=now, lasted_s=round((now - stall["from_t"]) / 1000, 1), shows_then=shows)
                    stall = None
                elif len(stall["probes"]) < len(FRAME_PROBE_AT_S) and \
                        now - stall["found_t"] >= FRAME_PROBE_AT_S[len(stall["probes"])] * 1000:
                    probe(stall)
                continue
            if (drawn is None or drawn["state"] != "sharp" or now - drawn["t"] < FRAME_STALL_S * 1000
                    or n - drawn["capture_n"] < FRAME_STALL_CAPTURES or last_t <= drawn["t"]
                    or shows == (drawn["page"], drawn["spread"], drawn["state"])):
                continue
            with notes.lock:
                seen_since = any(c["t"] >= drawn["t"] and (c["page"], c["spread"]) == (drawn["page"], drawn["spread"])
                                 for c in notes.captures)
            if seen_since:
                continue
            stall = {"from_t": drawn["t"], "found_t": now, "drawn": drawn, "frozen": shows, "frames_at_find": frames,
                     "frozen_since_t": last["t"] if last else None, "until_t": None, "lasted_s": None, "probes": []}
            with notes.lock:
                notes.frame_stalls.append(stall)
            if len(notes.frame_stalls) <= 3:
                stacks(f"== {time.strftime('%H:%M:%S')}: the window's frames stand still on {shows} while the "
                       f"stand-in shows {(drawn['page'], drawn['spread'], drawn['state'])}")
            probe(stall)

    thread = threading.Thread(target=look, name="tool-watch-frames", daemon=True)
    thread.start()
    return thread


COVER_CLASS = "StandinToolCover"
COVER_MARGIN = 24  # the cover's reach beyond the stand-in's window on every side


class CoverWindow:
    """A plain opaque window of this tool's own process laid over the stand-in's window and directly above it in the
    order of windows (`--cover`): what a reader's other program over the viewer is, made on purpose. Shown with no
    activation and no key; any window that lay above the stand-in stays above the cover. *part* below 1 (`--cover-part`):
    only the left part of the stand-in so wide is covered (a note or a dictionary laid over a part of the viewer), the
    rest stays in sight. Its own thread and message loop; `close` ends it."""

    def __init__(self, standin: int, part: float = 1.0):
        self.standin, self.hwnd, self.part = standin, 0, part
        self.shown_t: float | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="tool-cover", daemon=True)
        self._thread.start()
        self._ready.wait(3.0)

    def _run(self) -> None:
        user32, kernel32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32"), ctypes.WinDLL("gdi32")
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM)
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t

        def proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == 0x0002:  # WM_DESTROY
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._proc = proc_type(proc)  # (kept: the class holds a pointer to it)

        class WndClass(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", proc_type), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        gdi32.GetStockObject.restype = wintypes.HGDIOBJ
        instance = kernel32.GetModuleHandleW(None)
        wc = WndClass(0, self._proc, 0, 0, instance, None, None, gdi32.GetStockObject(2), None, COVER_CLASS)  # GRAY
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WndClass)]
        user32.RegisterClassW(ctypes.byref(wc))
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                           wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        r = wintypes.RECT()
        user32.GetWindowRect(self.standin, ctypes.byref(r))
        x, y = r.left - COVER_MARGIN, r.top - COVER_MARGIN
        w, h = r.right - r.left + 2 * COVER_MARGIN, r.bottom - r.top + 2 * COVER_MARGIN
        if self.part < 1.0:  # (the left part alone: its right edge inside the stand-in)
            w = COVER_MARGIN + max(1, int((r.right - r.left) * self.part))
        style = 0x00C00000 | 0x00080000  # WS_CAPTION | WS_SYSMENU: a window as any program's (not shown yet)
        self.hwnd = int(user32.CreateWindowExW(0x08000000, COVER_CLASS, "stand-in cover", style, x, y, w, h,
                                               None, None, instance, None) or 0)  # WS_EX_NOACTIVATE
        if self.hwnd:
            user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetWindow.restype = wintypes.HWND
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, wintypes.UINT]
            above = user32.GetWindow(self.standin, 3)  # GW_HWNDPREV: the window just above the stand-in, if any
            after = above if above and int(above) != self.hwnd else wintypes.HWND(0)  # (else HWND_TOP)
            user32.SetWindowPos(self.hwnd, after, x, y, w, h, 0x0010 | 0x0040)  # SWP_NOACTIVATE | SWP_SHOWWINDOW
            self.shown_t = now_ms()
        self._ready.set()
        msg = wintypes.MSG()
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user32.UnregisterClassW(COVER_CLASS, instance)

    def close(self) -> float:
        """The cover gone; when."""
        if self.hwnd:
            user32 = ctypes.WinDLL("user32")
            user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.PostMessageW(self.hwnd, 0x0010, 0, 0)  # WM_CLOSE
            self._thread.join(3.0)
        return now_ms()


def cover_over(cover: int, standin: int) -> bool:
    """Whether the tool's cover lies above the stand-in's window in the order of the windows (the walk down from
    the cover reaches the stand-in)."""
    user32 = ctypes.WinDLL("user32")
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    h = user32.GetWindow(cover, 2)  # GW_HWNDNEXT
    for _ in range(4096):
        if not h:
            return False
        if int(h) == int(standin):
            return True
        h = user32.GetWindow(h, 2)
    return False


def cover_part(text: str) -> float:
    """`--cover-part`'s F."""
    try:
        part = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("a number, as 0.4") from None
    if not 0 < part <= 1:
        raise argparse.ArgumentTypeError("more than 0, at most 1")
    return part


def cover_plan(text: str) -> tuple[str, float, float]:
    """`--cover`'s SEGMENT:AT:FOR."""
    try:
        segment, at, lasts = text.split(":")
        plan = (segment, float(at), float(lasts))
    except ValueError:
        raise argparse.ArgumentTypeError("SEGMENT:AT:FOR, as k2:12:30") from None
    if plan[1] < 0 or plan[2] <= 0:
        raise argparse.ArgumentTypeError("AT 0 or more, FOR more than 0")
    return plan


def stalls_report(notes: Notes, rel: Callable[[float | None], float | None]) -> list[dict[str, Any]]:
    """The report's stalls of the window's frames (`watch_frames`), its times from the run's start."""
    def screen(code: Any) -> list[Any] | None:
        if isinstance(code, dict):
            return [code.get("page"), code.get("spread"), code.get("state")]
        return list(code) if code else None

    with notes.lock:
        stalls = [dict(s, probes=[dict(p) for p in s["probes"]]) for s in notes.frame_stalls]
    return [{"from": rel(s["from_t"]), "found": rel(s["found_t"]), "until": rel(s["until_t"]),
             "lasted_s": s["lasted_s"], "drawn": screen(s["drawn"]), "frozen": screen(s["frozen"]),
             "frozen_since": rel(s["frozen_since_t"]), "shows_then": screen(s.get("shows_then")),
             "probes": [{**{k: v for k, v in p.items() if k not in ("t", "drawn")}, "t": rel(p["t"]),
                         "drawn": screen(p.get("drawn"))} for p in s["probes"]]} for s in stalls]


def keep_server_log(ollama_start: Any, path: Path) -> None:
    """The Ollama server the window starts (--start-ollama) writes its own log to *path*: what it loads, its slots and
    its HTTP lines, at Ollama's default level (no prompt and no answer in it: ``OLLAMA_DEBUG_LOG_REQUESTS`` is off),
    to tell a server that stops answering from a window that stops asking. The rest of the launch as the starter has
    it (`ollama_start.launch`)."""
    launch = ollama_start.launch

    def logged(command: list[str], env: dict[str, str] | None = None) -> Any:
        options: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        if env is not None:
            options["env"] = env
        try:
            log = open(path, "ab")
        except OSError:
            return launch(command, env)
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, shell=False,
                                cwd=str(Path(command[0]).parent), **options)
        log.close()  # (the server holds its own handle)
        ollama_start._launched.append(proc)
        return proc

    ollama_start.launch = logged


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
            frame = latest(hwnd, *a, **k)
            with notes.lock:
                notes.compositor["frames" if frame is not None else "none"] += 1
            return frame
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
        side = None
        if kind in KINDS:
            notes.app_event(self, kind, data)
        elif kind in ("page_on_show", "backlog") or (kind == "page_stage" and data.get("reading")):
            notes.reading(kind, data)
            side = notes.side
            if side is not None:
                try:
                    side.told_event(self, kind, data)
                except Exception as e:  # noqa: BLE001 - noted, never in the app's way
                    notes.error("side told", type(e).__name__)
        out = handle_event(self, kind, data)
        if side is not None:
            try:
                side.handled(self, kind, data)
            except Exception as e:  # noqa: BLE001 - noted, never in the app's way
                notes.error("side handled", type(e).__name__)
        return out

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
    looks_soft, judge, viewer_sharp = App._looks_soft, batch_mod.SharpSeen.judge, live.looks_sharp
    asked: dict[str, Any] = {}

    def judged(self: Any, *a: Any, **k: Any) -> Any:  # the page's own sharp picture's verdict, as `_looks_soft` asks it
        out = judge(self, *a, **k)
        asked["own"] = out
        return out

    def by_viewer(*a: Any, **k: Any) -> Any:  # ... and the viewer's pictures of all pages'
        out = viewer_sharp(*a, **k)
        asked["viewer"] = out
        return out

    def soft_look(self: Any, image: Any) -> Any:  # each judgement of a frame: both verdicts, the window's, the truth
        asked.clear()
        out = looks_soft(self, image)
        if asked:
            notes.soft_look(image, asked.get("own", "-"), asked.get("viewer", "-"), bool(out))
        return out

    App._looks_soft, batch_mod.SharpSeen.judge, live.looks_sharp = soft_look, judged, by_viewer
    decided, stored = batch_mod.BatchReader._decided, pageimages.PageImages.frame
    marked = pageimages.PageImages.read

    def run_decided(self: Any, decisions: Any) -> Any:  # a whole-book run's decisions on the viewer's frames
        for kind, image in decisions:
            notes.run_frame(kind, image)
        return decided(self, decisions)

    def run_stored(self: Any, key: Any) -> Any:  # ... and each frame it gets from its store, to read or letter
        image = stored(self, key)
        notes.run_read(key, image)
        return image

    def run_marked(self: Any, key: Any, *a: Any, **k: Any) -> Any:  # ... and a reading of one thrown away
        done = marked(self, key, *a, **k)
        if done is False:
            notes.run_read_again(key)
        return done

    batch_mod.BatchReader._decided, pageimages.PageImages.frame = run_decided, run_stored
    pageimages.PageImages.read = run_marked
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
    from taslation import backlog as backlog_mod

    catch_page, backlog_step = backlog_mod.Backlog.catch, backlog_mod.Backlog.step

    def caught(self: Any, screen: Any, image: Any, work: Any, *a: Any, **k: Any) -> Any:  # a page turned past
        # (--k-backlog off: nothing is caught - the same turns timed as before there was a backlog)
        got = catch_page(self, screen, image, work, *a, **k) if args.k_backlog == "on" else False
        notes.backlog_note("catch", self, seq=getattr(screen, "seq", None), sight=getattr(screen, "sight", None),
                           caught=bool(got), read=bool(work is not None and work.read_all and work.read))
        return got

    def stepped(self: Any, pipeline: Any, *a: Any, **k: Any) -> Any:  # ... and each step of its work
        held, notes.local.side = getattr(notes.local, "side", None), "backlog"
        began, what = now_ms(), ""
        try:
            # (the page it works on: chosen so again inside, nothing changed between; in a page job's hold a read only,
            # `Pipeline.behind_reads_allowed`)
            hold = not pipeline.behind_allowed()
            nxt = self._next(reads_only=hold)
        except Exception:  # noqa: BLE001 - not known
            hold, nxt = None, None
        resumes = dict(getattr(self, "resumes", {}) or {})
        try:
            what = backlog_step(self, pipeline, *a, **k)
            return what
        finally:
            notes.local.side = held
            if what:
                # (a read that took up one stopped before - "resumed" - or began again from the start, and why: what
                # `Backlog._resume_of` counted in this step; None for a read with nothing kept of one before)
                now = dict(getattr(self, "resumes", {}) or {})
                took = next((key for key, n in now.items() if n != resumes.get(key, 0)), None)
                notes.backlog_note("step", self, began=began, did=what, resumed=took, in_hold=hold,
                                   on=nxt[0] if nxt else None, sight=nxt[1].screen.sight if nxt else None,
                                   here=getattr(self, "_here", None),
                                   waited_ms=round(self.last_wait * 1000) if what == "stopped"
                                   and self.last_wait is not None else None,
                                   frame_wait_ms=round(self.last_frame_wait * 1000) if what == "read"
                                   and self.last_frame_wait is not None else None)

    on_units = backlog_mod.Tracking.on_units

    def units_known(self: Any, work: Any) -> Any:  # a page job's units known: what the backlog lent it, its screen
        try:
            return on_units(self, work)
        finally:
            with notes.lock:
                job = notes.current
                if job is not None:
                    job["reuse"] = getattr(self, "reuse", "") or None
                    job["sight"] = getattr(getattr(self, "screen", None), "sight", None)

    backlog_mod.Backlog.catch, backlog_mod.Backlog.step = caught, stepped
    backlog_mod.Tracking.on_units = units_known
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
    server = ServerState(notes)
    stream_once = ollama_mod.OllamaTranslator._stream_once

    def streamed(self: Any, path: str, payload: dict[str, Any], *a: Any, **k: Any) -> Any:
        # the HTTP exchange of a request noted (`requested`): when it went out, when it ended, the server's time for
        # it (Ollama's total_duration, the model's load in it) and the model's own work in it (the load, the prompt,
        # the answer), so that a wait at the server shows: Ollama counts a request queued behind another in its
        # total_duration (a short request sent beside a long one: total 3164 ms, work 57 ms)
        rec = getattr(notes.local, "request", None)
        if rec is None or not (payload.get("prompt") or payload.get("messages")):
            return stream_once(self, path, payload, *a, **k)
        pieces: list[str] = []
        if a and callable(a[0]):  # (the answer as it came, for what the server holds after a request cancelled)
            on_text = a[0]

            def kept(piece: str, _on_text: Callable[[str], None] = on_text) -> None:
                pieces.append(piece)
                _on_text(piece)

            a = (kept, *a[1:])
        rec["http_t"] = now_ms()
        data: Any = None
        try:
            data = stream_once(self, path, payload, *a, **k)
        finally:
            rec["http_end_t"] = now_ms()
            if payload.get("prompt"):
                answer = (str((data.get("message") or {}).get("content") or "") if isinstance(data, dict)
                          else "".join(pieces))
                server.asked(rec, str(payload["prompt"]), answer)
        with contextlib.suppress(TypeError, ValueError):
            rec["server_ms"] = round(float(data.get("total_duration") or 0) / 1e6, 1)
            rec["load_ms"] = round(float(data.get("load_duration") or 0) / 1e6, 1)
            rec["work_ms"] = round(sum(float(data.get(key) or 0) for key in
                                       ("load_duration", "prompt_eval_duration", "eval_duration")) / 1e6, 1)
            rec["prompt_n"] = int(data.get("prompt_eval_count") or 0)
            rec["prompt_ms"] = round(float(data.get("prompt_eval_duration") or 0) / 1e6, 1)
            rec["answer_n"] = int(data.get("eval_count") or 0)
            rec["answer_ms"] = round(float(data.get("eval_duration") or 0) / 1e6, 1)
        return data

    ollama_mod.OllamaTranslator._stream_once = streamed
    request_plain = ollama_mod.OllamaTranslator._request

    def plain(self: Any, path: str, payload: Any = None, *a: Any, **k: Any) -> Any:  # (a request not streamed)
        rec = getattr(notes.local, "request", None)
        if rec is None or not isinstance(payload, dict) or not payload.get("prompt"):
            return request_plain(self, path, payload, *a, **k)
        rec["http_t"] = now_ms()
        data: Any = None
        try:
            data = request_plain(self, path, payload, *a, **k)
        finally:
            rec["http_end_t"] = now_ms()
            server.asked(rec, str(payload["prompt"]), str((data or {}).get("response") or "")
                         if isinstance(data, dict) else "")
        with contextlib.suppress(TypeError, ValueError, AttributeError):
            rec["server_ms"] = round(float(data.get("total_duration") or 0) / 1e6, 1)
            rec["prompt_n"] = int(data.get("prompt_eval_count") or 0)
            rec["prompt_ms"] = round(float(data.get("prompt_eval_duration") or 0) / 1e6, 1)
            rec["answer_n"] = int(data.get("eval_count") or 0)
            rec["answer_ms"] = round(float(data.get("eval_duration") or 0) / 1e6, 1)
        return data

    ollama_mod.OllamaTranslator._request = plain
    warm_step = getattr(plamo_mod.PlamoTranslator, "_warm_step", None)
    if warm_step is not None:
        def warmed(self: Any, prompt: str, _step: Callable[..., Any] = warm_step) -> Any:
            # a step of the warming while the reader reads (`PlamoTranslator.warm_prefix`): its own record, no job's,
            # told against what the server holds as any request is, and what it holds after it
            rec: dict[str, Any] = {"t": now_ms(), "kind": "warm", "side": "warm", "job": None,
                                   "n": -1 - len(notes.warms), "end_t": None, "outcome": None}
            got: Any = None
            try:
                got = _step(self, prompt)
                return got
            finally:
                rec["end_t"], rec["outcome"] = now_ms(), "ok" if got is not None else "failed"
                server.asked(rec, prompt, "")
                if isinstance(got, dict):
                    rec["prompt_n"], rec["prompt_ms"] = got.get("prompt_n"), round(float(got.get("prompt_ms") or 0), 1)
                with notes.lock:
                    notes.warms.append(rec)

        plamo_mod.PlamoTranslator._warm_step = warmed
        prefix = plamo_mod.PlamoTranslator.warm_prefix

        def warming(self: Any, *a: Any, _prefix: Callable[..., Any] = prefix, **k: Any) -> Any:
            t = now_ms()
            facts = _prefix(self, *a, **k)  # (what a warming did: its steps, or why it did nothing)
            with notes.lock:
                notes.warm_calls.append({"t": t, "end_t": now_ms(), "why": str(facts.get("why")),
                                         "steps": facts.get("steps"), "left": facts.get("left")})
            return facts

        plamo_mod.PlamoTranslator.warm_prefix = warming
    stages(notes, server)
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
    from taslation.ui import order as order_mod

    if getattr(args, "order_partly", "as-built") != "as-built":  # (`ui.order`'s switch, for this run alone)
        order_mod.PARTLY_COVERED_TOO = args.order_partly == "on"
    if getattr(args, "front_for_order", "as-is") == "own":  # (the viewer kept under the window as with it in front)

        def order_owner(hwnd: Any, viewer: int, *a: Any, **k: Any) -> str:
            real_owner(hwnd, viewer, *a, **k)
            return "own"

        order_mod.foreground_owner = order_owner
    hook = threading.excepthook

    def thread_error(info: Any) -> None:
        notes.error(f"thread {getattr(info.thread, 'name', '?')}", getattr(info.exc_type, "__name__", "?"))
        hook(info)

    threading.excepthook = thread_error
    return done


# ---------------------------------------------------------------------------------------------------- the director
def hold_over(screen: tuple[int, bool] | None, state: str, shown: dict[str, Any] | None, rested_s: float,
              held_s: float, cap_s: float) -> str | None:
    """--wait-done: why a hold of the stand-in's script is over, or None while it holds. "finished": the stand-in shows
    *screen* sharp (*state*) and the window's picture (*shown*, the last of `Notes.displays`) is that screen
    translated - its finished picture, or its result; "idle": the window has been at rest IDLE_S (*rested_s*, counted
    from LAG_MS after the stand-in last changed what it shows) with the screen sharp and not so; "cap": it has held
    *cap_s* (*held_s*)."""
    sharp = state == "sharp" and screen is not None
    if (sharp and shown is not None and (shown.get("page"), bool(shown.get("spread"))) == tuple(screen)
            and shown.get("kind") in ("translated", "final")):
        return "finished"
    if sharp and rested_s >= IDLE_S:
        return "idle"
    if held_s >= cap_s:
        return "cap"
    return None


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
        self.cover: CoverWindow | None = None  # (`cover_step`)
        self.cover_from: float | None = None
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
        self.turns_released = 0  # --k-keys: the turns the control file has released (the stand-in's ``u`` steps)
        self.k_keys: dict[str, dict[str, Any]] = {}  # --k-keys: per pace, the keys pressed and what became of them
        self._hook_page_keys()
        self.page_rect: tuple[int, int, int, int] | None = None  # the page the stand-in drew last (its canvas's pixels)
        self.band_px = 0  # the height of its band then
        # --wait-done (its cap, seconds; None: the script has no holds and keeps no soft frame): the control file's
        # values, the script's holds and kept soft frames as the stand-in said them, what it shows (`waits`)
        self.wait_done: float | None = getattr(args, "wait_done", None)
        self.control = {"go": 0, "hold": 0, "sharp": 0, "turns": 0}
        self.holds: list[dict[str, Any]] = []
        self.keeps: list[dict[str, Any]] = []
        self.screen_now: tuple[int, bool] | None = None
        self.screen_state, self.screen_since = "none", time.monotonic()
        self.last_ocr = 0.0
        self.side_drop_at: float | None = None  # (`side_drop_due`)
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
                self.cover_step()
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

    def cover_step(self) -> None:
        """`--cover SEGMENT:AT:FOR`: AT seconds after SEGMENT began, the tool's own window laid over the stand-in
        (`CoverWindow`) for FOR seconds, once; when, in the notes."""
        plan = getattr(self.args, "cover", None)
        if not plan or (self.notes.tool_cover or {}).get("gone_t"):
            return
        segment, at, lasts = plan
        if self.cover_from is None:
            if self.current != segment:
                return
            self.cover_from = time.monotonic()
        since = time.monotonic() - self.cover_from
        if self.cover is None and since >= at:
            self.cover = CoverWindow(self.browser.hwnd, getattr(self.args, "cover_part", 1.0))
            with self.notes.lock:
                self.notes.tool_cover = {"segment": segment, "shown_t": self.cover.shown_t, "gone_t": None,
                                         "made": bool(self.cover.hwnd), "part": self.cover.part}
        elif self.cover is not None and since >= at + lasts:
            gone = self.cover.close()
            with self.notes.lock:
                self.notes.tool_cover["gone_t"] = gone
        elif self.cover is not None and self.cover.hwnd:
            over = cover_over(self.cover.hwnd, self.browser.hwnd)
            with self.notes.lock:
                c = self.notes.tool_cover
                c["looks"] = c.get("looks", 0) + 1
                c["over_looks"] = c.get("over_looks", 0) + (1 if over else 0)
                if not over and c.get("under_t") is None:
                    c["under_t"] = now_ms()  # (the stand-in first found over the cover: put under the window)

    def stop(self, why: str) -> None:
        if self.over:
            return
        self.over = True
        if self.cover is not None and not (self.notes.tool_cover or {}).get("gone_t"):
            gone = self.cover.close()
            with self.notes.lock:
                self.notes.tool_cover["gone_t"] = gone
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
                with contextlib.suppress(KeyError, ValueError), self.notes.lock:  # (`watch_frames`)
                    self.notes.drawn_last = {"t": e["recv"], "page": int(e["page"]), "spread": e["spread"] == "1",
                                             "state": e["state"], "capture_n": self.notes.capture_n}
            elif ev == "black" and e.get("on") == "1":
                with self.notes.lock:
                    self.notes.drawn_last = None
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
            if self.wait_done is not None:
                self.waited(e, mono)

    def waited(self, e: dict[str, Any], mono: float) -> None:
        """--wait-done: what the stand-in shows (its screen, sharp, soft, black or under a spinner, and since when), and
        its holds and kept soft frames as it says them (`waits` lets them go)."""
        ev = e["ev"]
        with contextlib.suppress(KeyError, ValueError):
            if ev == "draw":
                self.screen_now = (int(e["page"]), e.get("spread") == "1")
                self.screen_state, self.screen_since = e.get("state", "sharp"), mono
            elif ev in ("black", "spinner") and e.get("on") == "1":
                self.screen_state, self.screen_since = ev, mono
            elif ev == "hold":
                self.holds.append({"id": int(e["id"]), "segment": self.current, "page": int(e["page"]),
                                   "spread": e.get("spread") == "1", "at": mono, "why": None, "waited_ms": None})
            elif ev == "keep":
                with self.notes.lock:
                    since = len(self.notes.requests)
                self.keeps.append({"n": int(e["n"]), "segment": self.current, "page": int(e["page"]),
                                   "spread": e.get("spread") == "1", "at": mono, "requests_from": since,
                                   "asked_ms": None, "why": None, "waited_ms": None})
            elif ev == "kept":
                keep = next((k for k in self.keeps if k["n"] == int(e["n"]) and k["why"] is None), None)
                if keep is not None:
                    keep["why"] = {"word": "asked"}.get(e.get("why", ""), e.get("why"))
                    keep["waited_ms"] = round((mono - keep["at"]) * 1000)

    def turned(self, e: dict[str, Any]) -> None:
        """A turn began on the stand-in: the pictures due for it (`SHOTS`)."""
        seg, k = self.current, self.turns_in[self.current]
        if (seg, k) in SHOTS:
            delay, label = SHOTS[(seg, k)]
            self.due.append((time.monotonic() + delay, label))
        if seg in K_PACES and self.notes.side is not None:  # the indicator after the flips, and after the reads back
            turns = self.args.k_turns
            read = self.args.k_read or turns
            if k == turns + 2:  # (the turn back to the first page flipped past)
                self.due.append((time.monotonic() + 0.4, f"{seg}_side_after_the_flips"))
            elif k == turns + 1 + read:  # (the last page read back, near the end of its stay)
                self.due.append((time.monotonic() + max(0.5, self.args.k_read_ms / 1000 - 1.0),
                                 f"{seg}_side_read_back"))

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
        if self.wait_done is not None:
            self.waits(now)
        if len(self.notes.run_ends) > self.run_ends_seen:  # a whole-book run ended: the window a while after
            self.run_ends_seen = len(self.notes.run_ends)
            self.due.append((time.monotonic() + 4.0, f"run{self.run_ends_seen}_ended"))
        if self.index >= len(self.segments):
            if self.phase != "end":
                if self.index:
                    self.after(self.segments[-1])
                self.phase, self.phase_at = "end", now
                return
            if (self.ended and rested and self.backlog_done()) or waited > self.args.timeout:
                if self.side_drop_due():
                    return
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
            if (seg.name in ("r", "t", "o", "z", "w") and seg.name not in self.entered and ready_go and rested
                    and not (seg.name == "w" and self.args.k_narrow and not self.resized())):
                self.enter(seg.name)  # (a mode entered at rest, as a reader does; released once it is on)
                return
            app = self.app
            mode = self.entered.get(seg.name)
            if seg.name == "c":
                go = ready_go and getattr(app, "selected", None) is not None
            elif seg.name == "f2":
                go = ready_go and rested and self.resized()
            elif seg.name in K_PACES:  # (each pace on its own: the backlog of the one before done)
                first = seg is next(x for x in self.segments if x.name in K_PACES)
                go = (ready_go and rested and self.backlog_done() and (self.index > 0 or self.first_page_done())
                      and not (first and self.args.k_narrow and not self.resized()))
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
                self.release(go=seg.go)
                self.phase, self.phase_at = "running", now
            return
        if self.phase == "running" and seg.name in K_PACES and self.args.k_keys:
            self.k_keys_step(seg, now)
        if self.phase == "running" and (self.waiting_go > seg.go or self.ended):
            self.index += 1
            self.phase, self.phase_at = "prepare", now

    def release(self, go: int | None = None, hold: int | None = None, sharp: int | None = None,
                turns: int | None = None) -> None:
        """The control file written: the stand-in's script released to *go* (``gN``); with --wait-done, its holds to
        *hold* (``hN``) and its turns kept soft to *sharp* (``kN``) as well; with --k-keys, once a turn was released,
        the turns released (*turns*, ``u``); a value not given as it was. Without the options the file is what it
        always was (the go alone)."""
        for key, value in (("go", go), ("hold", hold), ("sharp", sharp), ("turns", turns)):
            if value is not None:
                self.control[key] = int(value)
        turned = {"turns": self.control["turns"]} if self.control.get("turns") else {}
        if self.wait_done is None:
            sv.write_control(self.standin_dir, self.control["go"], **turned)
        else:
            sv.write_control(self.standin_dir, self.control["go"], hold=self.control["hold"],
                             sharp=self.control["sharp"], **turned)

    def waits(self, now: float) -> None:
        """--wait-done, at every look: the hold the stand-in is at let go once `hold_over` says why (its page finished,
        the window at rest without it, or the cap); the soft frame it keeps let go once the window asked on it - a
        request of a page job on a soft frame of that screen, sent since the stand-in drew it."""
        hold = self.holds[-1] if self.holds else None
        if hold is not None and hold["why"] is None:
            with self.notes.lock:
                shown = dict(self.notes.displays[-1]) if self.notes.displays else None
            rested_from = max(self.idle_since if self.idle_since is not None else now,
                              self.screen_since + LAG_MS / 1000)
            why = hold_over(self.screen_now, self.screen_state, shown, now - rested_from, now - hold["at"],
                            float(self.wait_done or 0))
            if why:
                hold["why"], hold["waited_ms"] = why, round((now - hold["at"]) * 1000)
                self.release(hold=hold["id"])
        keep = self.keeps[-1] if self.keeps else None
        if keep is not None and keep["why"] is None and keep["asked_ms"] is None:
            with self.notes.lock:
                asked = [r["job"] for r in self.notes.requests[keep["requests_from"]:]
                         if r["frame"] == "soft" and r["job"] is not None]
                jobs = {j["id"]: j for j in self.notes.jobs if j["id"] in asked}
            if any((j["page"], bool(j["spread"])) == (keep["page"], keep["spread"]) for j in jobs.values()):
                keep["asked_ms"] = round((now - keep["at"]) * 1000)
                self.release(sharp=keep["n"])

    def waits_report(self) -> dict[str, Any]:
        """--wait-done's holds and kept soft frames, numbers only."""
        holds = [{k: h[k] for k in ("id", "segment", "page", "spread", "why", "waited_ms")} for h in self.holds]
        keeps = [{k: h[k] for k in ("n", "segment", "page", "spread", "asked_ms", "why", "waited_ms")}
                 for h in self.keeps]
        return {"cap_s": self.wait_done, "keep_soft_s": min(float(self.wait_done or 0), KEEP_SOFT_S),
                "holds": holds, "holds_by_why": dict(Counter(str(h["why"]) for h in holds)),
                "held_ms": dist([h["waited_ms"] for h in holds]),
                "keeps": keeps, "keeps_by_why": dict(Counter(str(k["why"]) for k in keeps)),
                "kept_ms": dist([k["waited_ms"] for k in keeps])}

    def first_page_done(self) -> bool:
        return any(d["kind"] == "translated" for d in self.notes.displays) or (
            self.app.ready and time.monotonic() - self.phase_at > 30)

    def side_drop_due(self) -> bool:
        """(scenario k with the indicator on, at the end) The backlog dropped once as another book drops it
        (`backlog.drop_backlog`), pictured before and after: the indicator is looked at as the drop is handled
        (`SideCheck.drop_looked`); True while the window is given its 2 s for it."""
        if self.notes.side is None or not any(s.name in K_PACES for s in self.segments):
            return False
        from taslation import backlog as backlog_mod

        now = time.monotonic()
        if self.side_drop_at is None:
            self.shot("k_side_before_the_drop")
            held = backlog_mod.backlog_of(self.app, make=False)
            if held is not None:  # (what it held at the end, before the drop: `bytes_at_end`)
                self.notes.backlog_note("before the drop", held)
            backlog_mod.drop_backlog(self.app, "the tool's look at the indicator")
            self.side_drop_at = now
            self.due.append((now + 1.0, "k_side_after_the_drop"))
            return True
        return now - self.side_drop_at < 2.0

    def before(self, seg: Segment) -> None:
        from taslation.ui import theme

        if seg.name == "f":
            self.notes.act(seg.name, "dark theme")
            self.theme["before"] = theme.mode()
            self.app._settings_saved({"theme": "dark"})
            self.theme["after"] = theme.mode()
        elif seg.name == "f2":
            self.resize_from = len(self.events)
            hwnd = self.browser.hwnd
            if hwnd and self.guard.is_viewer(hwnd):
                self.notes.act(seg.name, "narrow window")
                place_own(hwnd, self.narrow_rect)
        elif (seg.name in K_PACES and self.args.k_narrow and seg is next(x for x in self.segments
                                                                             if x.name in K_PACES)
              or seg.name == "w" and self.args.k_narrow):  # (the whole-book run in the narrow window: single pages)
            self.resize_from = len(self.events)
            hwnd = self.browser.hwnd
            if hwnd and self.guard.is_viewer(hwnd):
                place_own(hwnd, self.narrow_rect)
        elif seg.name == "w2":
            self.notes.act(seg.name, "finished reading")
            self.app.finish_reading()  # the band's Finished reading: the stand-in has come to the stretch's end
            self.entered["w2"] = {"at": time.monotonic(), "finished_reading": True}

    def enter(self, name: str) -> None:
        """The mode of scenario *name* entered, as a reader does: r - F11 (`toggle_reading`, the key's own handler);
        t - the toolbar's Translator, then F11's handler; o - over the book (`over_begin`); z - TASlation's text size
        TEXT_SIZE times the run's (Settings); w - a whole-book run started as the dialog's Start starts it."""
        app = self.app
        self.entered[name] = {"at": time.monotonic()}
        self.notes.act(name, "entered")
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
            self.notes.act(seg.name, "left")
            app.toggle_reading()
            if "r" in self.entered:
                self.entered["r"].update(left=not app.reading, auto_after=bool(app.auto_var.get()),
                                         status_after=self.status_facts())
        elif seg.name == "t2":
            self.notes.act(seg.name, "left")
            self.leave_translator()
        elif seg.name == "o":
            self.notes.act(seg.name, "left")
            self.over_end()
        elif seg.name == "z":
            self.notes.act(seg.name, "left")
            app._settings_saved({"ui_scale": self.args.scale})
        elif seg.name in K_PACES and seg.name in self.k_keys:
            self.key_for = None
            app.__dict__.pop("_raise_for_key", None)

    # scenario k by the window's page key (--k-keys)
    def k_keys_step(self, seg: Segment, now: float) -> None:
        """--k-keys: scenario k's turns, each released by the window's next page key (pressed on the window's page:
        its binding's own call, `forward_key`) once the window hands it on (`_hook_page_keys`), at the times of
        `k_key_times` from the pace's release; the turn back and the end of the last page read back released by the
        driver alone. A key not handed on within K_KEY_GIVE_UP_S releases its turn all the same, noted so. The
        window's raise of the viewer before a key is left out (the stand-in drawing while covered,
        --standin-draws-covered: the windows of a person at the machine stay as they lie)."""
        plan = self.k_keys.get(seg.name)
        if plan is None:
            a = self.args
            plan = self.k_keys[seg.name] = {
                "due": k_key_times(K_PACES[seg.name], a.k_turns, a.k_read or a.k_turns, a.k_read_ms, a.k_stay_ms),
                "next": 0, "keys": [], "extra": 0, "began": self.phase_at}
            self.app._raise_for_key = lambda _hwnd: None
        t = now - plan["began"]
        while plan["next"] < len(plan["due"]) and t >= plan["due"][plan["next"]][0]:
            at, how = plan["due"][plan["next"]]
            plan["next"] += 1
            if how == "key":
                self.k_press(seg, plan, at)
            else:
                self.k_release(seg)
        for row in plan["keys"]:
            if row.get("handed_after_ms") is None and not row.get("gave_up") and now - row["mono"] > K_KEY_GIVE_UP_S:
                row["gave_up"] = True
                self.k_release(seg)

    def k_press(self, seg: Segment, plan: dict[str, Any], at: float) -> None:
        """The window's next page key, as Page > Page keys... has it, pressed on its page (the binding's own call:
        Tk delivers keys to the window with the system's keyboard focus, which this tool never moves)."""
        app = self.app
        pair = app._page_key_pair()
        key = (getattr(pair[1], "next", "") if pair is not None else "") or "Left"
        now = time.monotonic()
        plan["keys"].append({"due_s": at, "late_ms": round((now - plan["began"] - at) * 1000), "mono": now,
                             "t": now_ms(), "busy": bool(getattr(app, "busy", False))})
        self.key_for = seg
        app.forward_key(key)

    def k_release(self, seg: Segment) -> None:
        self.turns_released += 1
        self.release(turns=self.turns_released)

    def k_handed(self, seg: Segment, key: Any) -> None:
        """--k-keys: the keys the window handed on (one or several in one handover), each releasing the turn of the
        oldest key pressed that was not handed on yet; one with no such key is counted (`extra`) and releases
        nothing."""
        plan = self.k_keys.get(seg.name)
        keys = [key] if isinstance(key, str) else list(key)
        for _ in keys:
            row = next((r for r in (plan or {}).get("keys", [])
                        if r.get("handed_after_ms") is None and not r.get("gave_up")), None)
            if row is None:
                if plan is not None:
                    plan["extra"] += 1
                continue
            row["handed_after_ms"] = round((time.monotonic() - row["mono"]) * 1000)
            row["handed_t"] = now_ms()
            row["together"] = len(keys)
            self.k_release(seg)

    def k_keys_facts(self, rel: Callable[[float | None], float | None]) -> dict[str, Any]:
        """--k-keys, per pace: the keys pressed, handed on, given up on; each with its time on the run's clock (*rel*:
        ``t_s`` pressed, ``handed_s`` handed on)."""
        out: dict[str, Any] = {}
        for name, plan in self.k_keys.items():
            rows = [{**{k: v for k, v in r.items() if k not in ("mono", "t", "handed_t")}, "t_s": rel(r.get("t")),
                     "handed_s": rel(r.get("handed_t"))} for r in plan["keys"]]
            out[name] = {"pressed": len(rows), "handed_on": sum(1 for r in rows if r.get("handed_after_ms") is not None),
                         "gave_up": sum(1 for r in rows if r.get("gave_up")), "extra": plan["extra"],
                         "handed_after_ms": tail([r.get("handed_after_ms") for r in rows]),
                         "pressed_busy": sum(1 for r in rows if r["busy"]), "keys": rows}
        return out

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
            if seg.name in K_PACES:  # (--k-keys: every key handed on releases a turn, `k_handed`)
                self.k_handed(seg, key)
                return True
            self.key_for = None
            facts = self.keyed.setdefault(seg.name, {})
            facts["handed_on"] = key if isinstance(key, str) else list(key)
            facts["handed_on_after_ms"] = round((time.monotonic() - facts.get("at", time.monotonic())) * 1000)
            self.release(go=seg.go)
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

    def backlog_done(self) -> bool:
        """Whether the window's backlog has nothing left to do (or waits, paused: the end of a scenario all the
        same)."""
        b = getattr(self.app, "_backlog", None)
        return b is None or not b.has_work() or bool(b.paused) or b.fatal is not None

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


def soft_looks_summary(looks: list[dict[str, Any]], rel: Callable[[float], float]) -> dict[str, Any]:
    """The window's judgements of frames as soft or sharp (`Notes.soft_look`), against what the stand-in drew: how
    many, by the two verdicts it is made of (the page's own sharp picture's, the viewer's pictures of all pages'),
    and each one that missed - a soft frame taken for sharp, a sharp one for soft."""
    def name(v: Any) -> str:
        return {True: "sharp", False: "soft", None: "none"}.get(v, str(v))

    by = Counter(f"{r['state']}: own {name(r['own'])}, viewer {name(r['viewer'])} -> {'soft' if r['soft'] else 'sharp'}"
                 for r in looks)
    missed = [{"t_s": rel(r["t"]), "page": r["page"], "spread": r["spread"], "drawn": r["state"],
               "own": name(r["own"]), "viewer": name(r["viewer"]), "taken_for": "soft" if r["soft"] else "sharp"}
              for r in looks if r["state"] in ("soft", "sharp") and (r["state"] == "soft") != r["soft"]]
    return {"judged": len(looks), "by": dict(sorted(by.items())), "missed": len(missed), "missed_list": missed[:40]}


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


def resized_away(job: dict[str, Any], sizes: list[float], captures: list[dict[str, Any]]) -> bool:
    """Whether the page job *job*, cancelled with its page on show, gave that page over to its frame at a new size:
    the stand-in's size changed while the job ran (a "size" line, at *sizes*, between its start and its cancel) and
    the window's last capture by the cancel was of another size than the job's frame - the window's design, which goes
    on with a job on the new frame (the cache keeps what the job stored). On a slower computer that comes seconds after
    the change (a runner: the first capture of the new size 934 ms after it, the window's own area in force after
    2.4 s, the cancel after 2.3 s), not within the 1 s of `resize_within_1s`."""
    t0, t1, size = job["t"], job["cancelled_t"], job.get("size")
    if t1 is None or size is None or not any(t0 <= s <= t1 for s in sizes):
        return False
    last = None
    for c in captures:
        if c["t"] > t1:
            break
        last = c
    return last is not None and list(last["size"]) != list(size)


def run_gets(reads: list[dict[str, Any]], frames: list[dict[str, Any]], rel: Callable[[Any], Any]) -> dict[str, Any]:
    """A whole-book run's frames got from its store, by who got them (`Notes.run_read`: "read", its reading loop, or
    "erase", its erase ahead), and each one that was not the sharp frame: when, its screen, who got it, and how long
    after it the run took a sharper frame of that screen in its place (its decision "sharper"; None: none after it).
    A frame its reading loop got so is the page it read - but for one whose reading was thrown away (``thrown_away``:
    a sharper picture took its place while it was read, and the page was read again from that one), left out here."""
    by: dict[str, Counter[str]] = {}
    for f in reads:
        by.setdefault(str(f.get("by", "read")), Counter())[f["state"]] += 1
    listed = []
    for f in reads:
        if f["state"] == "sharp" or f.get("thrown_away"):
            continue
        screen = (f.get("page"), f.get("spread"))
        sharper = next((d["t"] for d in frames if d["t"] >= f["t"] and d["kind"] == "sharper"
                        and (d.get("page"), d.get("spread")) == screen), None)
        listed.append({"key": str(f["key"]), "by": str(f.get("by", "read")), "t_s": rel(f["t"]), "page": f.get("page"),
                       "spread": f.get("spread"), "state": f["state"], "sharper_taken_after_ms": ms(sharper, f["t"])})
    return {"frames_got_by": {k: dict(v) for k, v in by.items()}, "frames_got_not_sharp_list": listed}


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
    it, and its finished page. Its rest ends at the next turn or where the driver changed the window before it (a mode
    left or entered, the theme, the text size, the stand-in's size, Finished reading: `Notes.acts`), whichever comes
    first: what the window showed then is the page at rest (`at_rest`), not what the next scenario made of it."""
    rows = []
    started = [j for j in notes.jobs if j["started"]]
    acts = sorted(getattr(notes, "acts", ()), key=lambda a: a["t"])
    for k, turn in enumerate(turns):
        scr, lo, hi = turn["screen"], turn["soft_t"], turn["next_t"]
        sharp = turn["sharp_t"]
        cut = next((a for a in acts if (sharp if sharp is not None else lo) < a["t"] < hi), None)
        rest_end = cut["t"] if cut is not None else hi
        old_page_ms, old_lettering_ms = old_page_times(notes.displays, scr, lo, end)
        mine = [d for d in notes.displays if lo <= d["t"] < hi and (d["page"], d["spread"]) == scr]
        lettered = next((d["t"] for d in mine if lettered_shown(d)), None)
        lettered_sharp = next((d["t"] for d in mine if lettered_shown(d) and d["from"] == "sharp"), None)
        finished = next((d["t"] for d in mine if d["kind"] == "final" or (d["kind"] == "translated" and d["lettered"])),
                        None)
        empty = next((d["t"] for d in mine if d["kind"] == "translated" and not d["lettered"]), None)
        shown = next((d["t"] for d in mine), None)
        before = [d for d in notes.displays if d["t"] < rest_end - 1]
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
            "soft_to_sharp_ms": ms(sharp, lo), "rest_ms": ms(rest_end, sharp),
            "rest_ended_by": f"{cut['segment']} {cut['act']}" if cut is not None else None,
            "captured_sharp_ms": ms(seen_sharp, sharp),
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
            "cached": (any(j.get("cache_hits") for j in jobs) and not any(j.get("cache_misses") for j in jobs)
                       and not any(j.get("reuse") in ("reused", "partial") for j in jobs)),
            # what the backlog lent its jobs (`backlog.Backlog.lend`: "reused", "partial", or why it was read as ever),
            # and the screen they were (`Screen.sight`)
            "reuse": [j.get("reuse") for j in jobs], "sights": [j.get("sight") for j in jobs],
            "job_ids": [j["id"] for j in jobs],
            "lettered_from_turn_ms": ms(lettered, lo), "lettered_sharp_from_turn_ms": ms(lettered_sharp, lo),
            "lettering_gone_ms": lettering_gone_ms(notes.displays, scr, lo, hi),
            "status_old_page_ms": status_stayed, "status_old_page_kind": status_kind_,
            "status_other_page_ms": status_other,
        })
    return rows


def tail(values: list[Any]) -> dict[str, Any]:
    """How many, the median, the 90th percentile (nearest rank) and the largest of *values* (None left out)."""
    kept = sorted(v for v in values if v is not None)
    if not kept:
        return {"n": 0}
    return {"n": len(kept), "median": round(statistics.median(kept)),
            "p90": round(kept[min(len(kept) - 1, math.ceil(0.9 * len(kept)) - 1)]), "max": round(kept[-1])}


# a page job's stages as `job_stages` tells them, in the order of the job
STAGE_KEYS = ("queued", "to_process", "fingerprint", "detect", "ocr", "order", "before_first_request", "gate_wait",
              "load_wait", "first_request", "first_prompt", "first_answer", "requests", "prompt", "answer",
              "between_requests", "between_units", "after_requests", "tighten", "review", "large", "drafts_wait",
              "translate", "store",
              "render", "process", "result_to_window", "settle", "save", "keep_shown", "drafts_lettering",
              "first_answer_to_lettered", "ocr_beside", "ocr_cpu", "ocr_gpu")


def job_stages(job: dict[str, Any], requests: list[dict[str, Any]], lettered_t: float | None) -> dict[str, Any] | None:
    """Where the page job *job*'s time went, in ms (`Notes.span`, on the thread that ran its `Pipeline.process`
    unless said): from its start to its worker (queued), to its page's reading (to_process: the cache's files, the
    model named, the job's gate held); the fingerprints and the look at other sizes; the detection; the OCR (its
    worker's; ``ocr_beside``: a spread's next unit read beside; ``ocr_cpu``/``ocr_gpu``: the readers' reads by the
    device they ran on, any thread); the reading order and the rooms; from the translation's start to its first
    request's HTTP (before_first_request: the gate's wait and the model's load in it, and the lines reused), the first
    request (whole, its prompt and its answer by the server's counters), all requests, the time between them, from the
    last to the translation's end (the drafts waited for, tighten, review, the larger part); the store; the render; the
    page's whole reading; to the window's handling of the result; the gate waited for after it; the save; the next
    showing lettered (keep_shown); the drafts' lettering (their thread); and from the first answer to the first lettered
    bubble on show (*lettered_t*). With the job's requests: how many, how many computed in full (`full_computed`), and
    why each parted from what the server held (`ServerState`). None for a job that read no page."""
    spans = job.get("spans") or []
    procs = [s for s in spans if s[0] == "process"]
    if not procs:
        return None
    worker, p0, p1 = procs[0][3], procs[0][1], procs[0][2]

    outer = [(a, b) for lab, a, b, th, _x in spans if th == worker and lab in ("translate", "render", "keep_shown",
                                                                               "early_look")]

    def total(*labels: str, mine: bool | None = True, lo: float | None = None, hi: float | None = None,
              alone: bool = False) -> int:
        return round(sum(b - a for lab, a, b, th, _x in spans if lab in labels
                         and (mine is None or (th == worker) == mine)
                         and (lo is None or a >= lo) and (hi is None or b <= hi)
                         and not (alone and any(o0 <= a and b <= o1 for o0, o1 in outer))))

    reqs = sorted((r for r in requests if r["job"] == job["id"]), key=lambda r: r["t"])
    trs = [s for s in spans if s[0] == "translate" and s[3] == worker and s[2] <= p1]
    t0 = trs[0][1] if trs else None
    t1 = trs[-1][2] if trs else None
    first = reqs[0] if reqs else None
    ends = [r["end_t"] for r in reqs if r["end_t"] is not None]
    sent = first["http_t"] or first["t"] if first is not None else None
    ran = sum(r["end_t"] - r["t"] for r in reqs if r["end_t"] is not None)
    gaps = units_gap = 0.0  # (between two requests of a unit's translation; between two units' translations)
    for k, (_lab, a, b, _th, _x) in enumerate(trs):
        inside = [r for r in reqs if a <= r["t"] and r["end_t"] is not None and r["end_t"] <= b]
        if inside:
            gaps += (max(r["end_t"] for r in inside) - inside[0]["t"]
                     - sum(r["end_t"] - r["t"] for r in inside))
        if k:
            units_gap += a - trs[k - 1][2]
    out: dict[str, Any] = {
        "queued": ms(job.get("work_t"), job["t"]), "to_process": ms(p0, job.get("work_t")),
        "fingerprint": total("units", "resolve", hi=p1), "detect": total("detect", "annotate", hi=p1),
        "ocr": total("ocr", hi=p1), "order": total("order", hi=p1, alone=True),
        "before_first_request": ms(sent, t0) if first is not None and t0 is not None and sent >= t0 else None,
        "gate_wait": total("gate_wait", lo=t0, hi=sent) if t0 is not None and sent is not None else None,
        "load_wait": total("ensure_loaded", lo=t0, hi=sent) if t0 is not None and sent is not None else None,
        "first_request": ms(first["end_t"], first["t"]) if first is not None else None,
        "first_prompt": first.get("prompt_ms") if first is not None else None,
        "first_answer": first.get("answer_ms") if first is not None else None,
        "requests": round(ran) if reqs else None,
        "prompt": round(sum(r.get("prompt_ms") or 0 for r in reqs)) if reqs else None,
        "answer": round(sum(r.get("answer_ms") or 0 for r in reqs)) if reqs else None,
        "between_requests": round(gaps) if reqs else None,
        "between_units": round(units_gap) if len(trs) > 1 else None,
        "after_requests": ms(t1, max(ends)) if ends and t1 is not None else None,
        "tighten": total("tighten", hi=p1), "review": total("review", hi=p1), "large": total("large", hi=p1),
        "drafts_wait": total("drafts_wait", hi=p1),
        "translate": total("translate", hi=p1), "store": total("store", hi=p1), "render": total("render", hi=p1),
        "process": ms(p1, p0), "result_to_window": ms(job.get("result_t"), p1),
        "settle": total("settle"), "save": total("save"), "keep_shown": total("keep_shown"),
        "drafts_lettering": total("letter", mine=False),
        "first_answer_to_lettered": ms(lettered_t, first["end_t"]) if first is not None and lettered_t else None,
        "ocr_beside": total("ocr", mine=False),
        "ocr_cpu": round(sum(b - a for lab, a, b, _th, x in spans if lab == "ocr_read" and x == "cpu")),
        "ocr_gpu": round(sum(b - a for lab, a, b, _th, x in spans if lab == "ocr_read" and x != "cpu")),
    }
    out["ocr_reads"] = {"cpu": sum(1 for s in spans if s[0] == "ocr_read" and s[4] == "cpu"),
                        "gpu": sum(1 for s in spans if s[0] == "ocr_read" and s[4] != "cpu")}
    out["requests_n"] = len(reqs)
    out["full_n"] = sum(1 for r in reqs if full_computed(r))
    out["full_ms"] = round(sum(r.get("prompt_ms") or 0 for r in reqs if full_computed(r)))
    out["why"] = dict(Counter(f"{r.get('why')}{' (full)' if full_computed(r) else ''}" for r in reqs))
    out["sides"] = dict(Counter(str(r.get("side")) for r in reqs if r.get("side")))
    if first is not None:
        out["first_why"], out["first_full"] = first.get("why"), full_computed(first)
        out["first_prompt_tokens"], out["first_kept_tokens"] = first.get("prompt_n"), first.get("kept_tokens_est")
    return out


def stage_split(rows: list[dict[str, Any]], turns: list[dict[str, Any]], notes: Notes,
                rel: Callable[[Any], Any]) -> dict[str, Any]:
    """Where the time of a page went, per turn the reader rested on (`REST_MS`): each turn's finishing job's stages
    (`job_stages`), as median, p90 and slowest per scenario and over all; the turns whose first request was computed
    in full, why, and the time to the first lettered bubble with and without that; the requests of the whole run by
    why they parted and whether computed in full, with the cuts of the pairs that only grow; the pages begun, left
    (their job cancelled or put back) and come back to - the requests the job that finished them made again (a line
    one of the page's jobs before had asked); the first page with requests after a whole-book run; the jobs of the
    window's first turns (scenario c)."""
    by_id = {j["id"]: j for j in notes.jobs}
    started = [j for j in notes.jobs if j["started"]]
    rested = [r for r in rows if (r["rest_ms"] or 0) >= REST_MS and r["finishing_job"] is not None]
    for row in rows:
        job = by_id.get(row["finishing_job"]) if row["finishing_job"] is not None else None
        lettered = (row["first_lettered_ms"] + turns[row["n"]]["sharp_t"]
                    if row["first_lettered_ms"] is not None else None)
        row["stages"] = job_stages(job, notes.requests, lettered) if job is not None else None
    out: dict[str, Any] = {"keys": list(STAGE_KEYS), "all": {}, "by_segment": {}}
    with_stages = [r for r in rested if r["stages"]]
    out["all"] = {k: tail([r["stages"].get(k) for r in with_stages]) for k in STAGE_KEYS}
    for seg in dict.fromkeys(r["segment"] for r in with_stages):
        mine = [r for r in with_stages if r["segment"] == seg]
        out["by_segment"][seg] = {k: tail([r["stages"].get(k) for r in mine]) for k in STAGE_KEYS}
        out["by_segment"][seg]["first_lettered_ms"] = tail([r["first_lettered_ms"] for r in mine])
        out["by_segment"][seg]["finished_ms"] = tail([r["finished_ms"] for r in mine])
    asked = [r for r in with_stages if r["stages"].get("requests_n")]
    full = [r for r in asked if r["stages"].get("first_full")]
    out["first_request_full"] = {
        "turns_with_requests": len(asked), "full": len(full),
        "why": dict(Counter(str(r["stages"].get("first_why")) for r in full)),
        "why_all": dict(Counter(f"{r['stages'].get('first_why')}{' (full)' if r['stages'].get('first_full') else ''}"
                                for r in asked)),
        "first_prompt_ms_full": tail([r["stages"].get("first_prompt") for r in full]),
        "first_prompt_ms_not_full": tail([r["stages"].get("first_prompt") for r in asked if r not in full]),
        "first_lettered_ms_full": tail([r["first_lettered_ms"] for r in full]),
        "first_lettered_ms_not_full": tail([r["first_lettered_ms"] for r in asked if r not in full]),
        "turns": [{"n": r["n"], "segment": r["segment"], "page": r["page"], "why": r["stages"].get("first_why"),
                   "prompt_ms": r["stages"].get("first_prompt"), "prompt_tokens": r["stages"].get("first_prompt_tokens"),
                   "first_lettered_ms": r["first_lettered_ms"]} for r in full]}
    reqs = [r for r in notes.requests if r.get("prompt_n")]
    out["requests"] = {
        "n": len(reqs), "full": sum(1 for r in reqs if full_computed(r)),
        "full_prompt_s": round(sum(r.get("prompt_ms") or 0 for r in reqs if full_computed(r)) / 1000, 1),
        "prompt_s": round(sum(r.get("prompt_ms") or 0 for r in reqs) / 1000, 1),
        "answer_s": round(sum(r.get("answer_ms") or 0 for r in reqs) / 1000, 1),
        "by_why": dict(Counter(f"{r.get('why')}{' (full)' if full_computed(r) else ''}" for r in reqs)),
        "in_jobs": sum(1 for r in reqs if r["job"] is not None),
        "extend_prompt_ms": tail([r.get("prompt_ms") for r in reqs if full_computed(r) is False]),
        "full_prompt_ms": tail([r.get("prompt_ms") for r in reqs if full_computed(r)]),
        "full_prompt_ms_per_token": tail([1000 * (r.get("prompt_ms") or 0) / r["prompt_n"] for r in reqs
                                          if full_computed(r)]),
        # each cut: at its job's first request (the next page's: known at the end of the page before) or later in
        # the job (a spread's next unit, a request asked again), or outside the page jobs (a whole-book run)
        "cuts": [{"t_s": rel(c["t"]), "job": c["job"], "before": c["before"], "after": c["after"],
                  "at": ("run" if c["job"] is None else "first request" if not any(
                      r["job"] == c["job"] and r["t"] < c["t"] for r in notes.requests) else "later in the job")}
                 for c in notes.cuts],
        "server_resets": [{"t_s": rel(s["t"]), "why": s["why"], "job": s["job"]} for s in notes.server_resets]}
    # pages begun, left and come back to: a turn whose screen had a job before that was cancelled or put back
    back = []
    for row in rows:
        job = by_id.get(row["finishing_job"]) if row["finishing_job"] is not None else None
        if job is None:
            continue
        scr = (row["page"], row["spread"])
        earlier = [j for j in started if j["id"] < job["id"] and (j["page"], bool(j["spread"])) == scr
                   and (j.get("cancelled_t") is not None or j.get("discarded")) and j["requests"]]
        if not earlier or not any(t["screen"] == scr and t["next_t"] <= job["t"] for t in turns):
            continue  # (a page left on its own turn - a soft frame given up for the sharp one - is no come-back)
        before = {notes.sources.get(r["n"]) for r in notes.requests if r["job"] in {j["id"] for j in earlier}}
        mine = [r for r in notes.requests if r["job"] == job["id"]]
        again = [r for r in mine if notes.sources.get(r["n"]) in before]
        back.append({"n": row["n"], "segment": row["segment"], "page": row["page"], "jobs_before": len(earlier),
                     "requests_before": sum(j["requests"] for j in earlier),
                     "requests": len(mine), "asked_again": len(again),
                     "asked_again_ms": round(sum((r["end_t"] or r["t"]) - r["t"] for r in again)),
                     "first_lettered_ms": row["first_lettered_ms"], "finished_ms": row["finished_ms"],
                     "rested": (row["rest_ms"] or 0) >= REST_MS})
    out["come_back"] = back
    ends = [e["t"] for e in notes.run_ends]
    after = []
    for end in ends:
        row = next((r for r in rows if r["finishing_job"] is not None and by_id[r["finishing_job"]]["t"] >= end
                    and by_id[r["finishing_job"]]["requests"]), None)
        if row is None:
            continue
        job = by_id[row["finishing_job"]]
        stages_ = row["stages"] or {}
        loads = [s for s in notes.server_resets if s["why"] == "load" and end <= s["t"] <= (job.get("done_t") or end)]
        after.append({"run_end_s": rel(end), "turn": row["n"], "segment": row["segment"], "page": row["page"],
                      "job_after_end_s": round((job["t"] - end) / 1000, 1), "load_in_job": bool(loads),
                      "load_wait": stages_.get("load_wait"), "before_first_request": stages_.get("before_first_request"),
                      "first_request": stages_.get("first_request"), "first_why": stages_.get("first_why"),
                      "first_lettered_ms": row["first_lettered_ms"], "finished_ms": row["finished_ms"]})
    out["after_a_run"] = after
    out["first_turns"] = [{"n": r["n"], "segment": r["segment"], "page": r["page"],
                           "first_lettered_ms": r["first_lettered_ms"], "finished_ms": r["finished_ms"],
                           **{k: (r["stages"] or {}).get(k) for k in ("load_wait", "before_first_request", "ocr",
                                                                       "ocr_cpu", "ocr_gpu", "ocr_reads", "first_why",
                                                                       "first_request")}}
                          for r in rows if r["segment"] == "c"]
    out["between_jobs"] = dict(Counter(s[0] for s in notes.spans_off))
    # the warming while the reader reads: its steps, and what of them a page job met - a step under way when the job
    # began, its end after the job's first request went out (that request waited at the server for it)
    steps = notes.warms
    met = []
    for job in started:
        first = min((r["t"] for r in notes.requests if r["job"] == job["id"]), default=None)
        under = [w for w in steps if w["t"] <= job["t"] < (w["end_t"] or w["t"])]
        if under:
            met.append({"job": job["id"], "step_left_ms": round(max((w["end_t"] or 0) - job["t"] for w in under)),
                        "first_request_waited_ms": round(max(0.0, max((w["end_t"] or 0) for w in under) - first))
                        if first is not None else None})
    out["warm"] = {"steps": len(steps), "failed": sum(1 for w in steps if w["outcome"] != "ok"),
                   "ms": tail([(w["end_t"] or w["t"]) - w["t"] for w in steps]),
                   "prompt_ms": round(sum(w.get("prompt_ms") or 0 for w in steps)),
                   "why": dict(Counter(str(w.get("why")) for w in steps)),
                   "met_by_jobs": met,
                   "first_request_waited": sum(1 for m in met if (m["first_request_waited_ms"] or 0) > 0),
                   "warmings": len(notes.warm_calls),
                   "warmings_did": dict(Counter(c["why"] or ("warmed" if c["steps"] else "nothing")
                                                for c in notes.warm_calls))}
    return out


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
            # (how long of it came after the window's first capture of the stand-in's screen: the rest was the
            # capture's own time; None: no capture of it within the spell)
            seen = next((c["t"] for c in notes.captures if spell["from"] <= c["t"] <= spell["to"]
                         and (c["page"], bool(c["spread"])) == tuple(spell["key"][2])), None)
            item["seen_ms"] = round(spell["to"] - seen) if seen is not None else None
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


JAPANESE_SCRIPT = re.compile("[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f]")  # kana, kanji, half-width kana


def keep_app_log(state: Path, folder: Path) -> str:
    """The app's log of a run with an incident (a stop, frames standing still, a request without an answer) copied to
    *folder* before the scratch state goes - unless a line of it holds a character of Japanese script (no Japanese
    text is written outside the state): then nothing is kept. What was done."""
    texts = {}
    for path in sorted(state.glob("log.txt*")):
        with contextlib.suppress(OSError):
            texts[path.name] = path.read_text(encoding="utf-8", errors="replace")
    if not texts:
        return "no log"
    if any(re.search(JAPANESE_SCRIPT, t) for t in texts.values()):
        return "not kept: it holds Japanese script"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (folder / name).write_bytes(text.encode("utf-8"))
    return f"kept: {', '.join(texts)}"


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
    count = pages_needed(names, args.k_turns)
    report: dict[str, Any] = {"scenarios": names, "seed": args.seed, "front": args.front, "scale": args.scale,
                              "front_for_order": getattr(args, "front_for_order", "as-is"),
                              "order_partly": getattr(args, "order_partly", "as-built")}
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
    k_plan = {"turns": args.k_turns, "read": args.k_read if args.k_read else args.k_turns,
              "soft": args.k_soft == "on", "narrow": bool(args.k_narrow), "backlog": args.k_backlog == "on",
              "read_ms": args.k_read_ms, "keys": bool(args.k_keys), "stay_ms": args.k_stay_ms}
    segments, steps = build_plan(names, count, cancel_first, args.cancel_soft_ms, args.wait_done, k_plan)
    if any(n in K_PACES for n in names):
        report["k_plan"] = k_plan
    sv.write_page_list(standin_dir, pictures)
    sv.write_control(standin_dir, 0)
    report["page_count"] = count

    found = sv.find_browser(args.browser)
    if found is None:
        raise SystemExit("neither Chrome nor Edge is installed here")
    report["browser"] = found[0]

    url = args.ollama_url.rstrip("/")
    canned: Canned | None = None
    ps_before: list[str] | None = None
    mode = "canned" if args.canned else "real"
    if args.start_ollama:  # the server TASlation starts, on a port of its own (see `parse`)
        url = f"http://127.0.0.1:{args.start_ollama}"
        if ollama_get(url, "/api/version") is not None:
            raise SystemExit(f"something answers at {url} already: --start-ollama needs a port where nothing does")
        os.environ["OLLAMA_HOST"] = f"127.0.0.1:{args.start_ollama}"
        os.environ["OLLAMA_NOPRUNE"] = "1"
        mode, ps_before = "real (the server TASlation starts)", []
    elif not args.canned:
        tags = ollama_get(url, "/api/tags")
        names_there = [str(m.get("name", "")) for m in (tags or {}).get("models", [])] if isinstance(tags, dict) else []
        if not any(n.split(":")[0] == PLAMO for n in names_there):
            mode = "canned (Ollama did not answer, or has no PLaMo)"
        else:
            ps_before = loaded_models(url)
    if not mode.startswith("real"):
        canned = Canned(args.canned_load_s, args.canned_ms)
        url = canned.url
    report["translator"] = mode
    report["ollama_loaded_before"] = ps_before

    sys.path.insert(0, str(ROOT))
    import taslation
    from taslation.capture import enable_dpi_awareness

    if not Path(taslation.__file__).resolve().is_relative_to(ROOT):
        raise SystemExit(f"taslation comes from {taslation.__file__}, not from {ROOT}: set PYTHONPATH")
    if args.start_ollama:
        from taslation import ollama_start

        ollama_start.DEFAULT_PORT = args.start_ollama  # (this process alone: the port its starter starts Ollama on)
        keep_server_log(ollama_start, out / "ollama_server.log")
    enable_dpi_awareness()
    standin_rect, app_rect = Monitors().places()
    narrow_rect = (standin_rect[0], standin_rect[1], NARROW_SIZE[0], NARROW_SIZE[1])
    token = "t" + secrets.token_hex(5)
    page = sv.page_url(token, steps, standin_dir, seed=args.seed)
    report["standin_draws_covered"] = bool(args.standin_draws_covered)
    browser = sv.StandinBrowser(found[1], page, standin_dir / "profile", standin_rect, token, args.scale,
                                draws_covered=args.standin_draws_covered)
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
    if args.start_ollama:
        report["server_started"] = stop_started(url, state)
    run_ = report.get("run") or {}
    keep = run_.get("failed") or run_.get("frame_stalls") or run_.get("no_answer") or (out / "stacks.txt").exists()
    report["cleanup"] = cleanup(report, closed, state, standin_dir, mode, url if mode == "real" else "", ps_before,
                                out / "app_log" if keep else None)
    path = out / "report.json"
    path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print_table(report, path)
    return 0 if not report["run"].get("failed") else 1


def stop_started(url: str, state: Path) -> dict[str, Any]:
    """``--start-ollama``, once the window has closed: what TASlation's starter chose for the server it started
    (`ollama_start.setup_of`), the models still loaded in it (none: the window let go of its model), and the server
    stopped as TASlation's own end stops it (`ollama_start.finish_all`; the scratch state still holds its record)."""
    from taslation import ollama_start

    setup = ollama_start.setup_of(url, state)
    out: dict[str, Any] = {"setup": setup.to_record() if setup is not None else None,
                           "readers_room_mib": list(setup.rooms) if setup is not None else None,
                           "loaded_at_close": loaded_models(url)}
    mine = [m for m in out["loaded_at_close"] or [] if m.split(":")[0] == PLAMO]
    if mine:
        out["unloaded_by_driver"] = [ollama_unload(url, m) for m in mine]
    out["finish"] = ollama_start.finish_all()
    out["stopped"] = ollama_get(url, "/api/version") is None
    return out


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
    watch_stuck(notes, out / "stacks.txt", url)
    watch_frames(notes, hwnd, os.getpid(), out / "stacks.txt", standin_pids=lambda: {pid, *browser.tree})
    watch_input(notes)
    state = demo_video.scratch_state()
    info = viewer_info()
    remember_role(state, BOOK, "reader")
    profiles = Profiles(state / "profiles.json")
    profiles.set_margins(info, area)
    profiles.set_margins(info, area, large=True)
    settings = Settings(state_dir=state, ui_language="en", target_language="English", over_book=False,
                        flash_when_done=False, sound_when_done=False, always_on_top=False, ui_scale=args.scale,
                        models_dir=Path(os.environ["TASLATION_MODELS_DIR"]), ollama_url=url,
                        ocr_runs_on=args.ocr_runs_on, ollama_window_cache=args.ollama_window_cache,
                        ollama_num_gpu=args.ollama_num_gpu,
                        **({"side_indicator": args.side_indicator} if args.side_indicator else {}))
    settings.validate()
    if getattr(settings, "side_indicator", "off") != "off":
        notes.side = SideCheck(notes)
    errorlog.setup(settings)
    tap = LogTap(notes, url if mode.startswith("real") else None)
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
    split = stage_split(rows, turns, notes, rel)
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
                 "cancelled_s": rel(j["cancelled_t"]), "discarded": j["discarded"], "done_s": rel(j["done_t"]),
                 "confirmed_s": rel(j.get("confirmed_t")), "settled": j.get("settled"), "soft_gate": j.get("soft_gate"),
                 "settled_by_s": rel(j.get("settled_by_t")), "reuse": j.get("reuse"), "sight": j.get("sight")}
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
                        "resize_within_1s": any(j["cancelled_t"] - 1000 <= s <= j["cancelled_t"] for s in sizes),
                        "resized_away": resized_away(j, sizes, notes.captures)})
    # (a job on a frame of the size before gives way to the new size's frame of the same page: no false cancel)
    false_cancels = [c for c in cancels if c["page_on_show"] and c["frame"] == "sharp"
                     and c["gate_end"] in ("confirmed", None) and not c["resize_within_1s"]
                     and not c["resized_away"]]
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
             "driver_acts": [{**{k: v for k, v in a.items() if k != "t"}, "t_s": rel(a["t"])} for a in notes.acts],
             "hot_keys": [{**{k: v for k, v in h.items() if k != "t"}, "t_s": rel(h["t"])} for h in notes.hotkeys]}
    run_requests = [r for r in requests if r["job"] is None]
    whole_book = {
        "decisions": dict(Counter(f"{f['kind']}:{f['state']}" for f in notes.run_frames)),
        "frames_got": dict(Counter(f["state"] for f in notes.run_reads)),
        # (a frame whose reading was thrown away for the sharper picture that took its place is no frame the run read)
        "frames_got_not_sharp": sorted({str(f["key"]) for f in notes.run_reads
                                        if f["state"] != "sharp" and not f.get("thrown_away")}),
        "readings_thrown_away": dict(Counter(f["state"] for f in notes.run_reads if f.get("thrown_away"))),
        **run_gets(notes.run_reads, notes.run_frames, rel),
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
                                "wasted", "side", "why", "full", "prompt_n", "prompt_ms", "answer_n", "answer_ms",
                                "pairs", "joined", "kept_tokens_est", "prompt_tokens_est"],
                    "rows": [[rel(r["t"]), r["job"], r["frame"], r["gate"], r["outcome"], ms(r["end_t"], r["t"]),
                              r["server_ms"], server_wait(r), wasted_why(by_id.get(r["job"]))
                              if r["job"] is not None else None, r.get("side"), r.get("why"), full_computed(r),
                              r.get("prompt_n"), r.get("prompt_ms"), r.get("answer_n"), r.get("answer_ms"),
                              r.get("pairs"), r.get("joined"), r.get("kept_tokens_est"), r.get("prompt_tokens_est")]
                             for r in requests]}
    k_facts = k_block(notes, turns, rows, requests, spells, rel)
    pump = sorted(ms_ for ms_, _busy in notes.timings.get("_poll_events", []))
    side_facts = {"setting": getattr(director.app.settings, "side_indicator", None),
                  "poll_events_ms": {"n": len(pump), "median": round(statistics.median(pump), 3),
                                     "p90": round(pump[int(0.9 * (len(pump) - 1))], 2),
                                     "p99": round(pump[int(0.99 * (len(pump) - 1))], 2),
                                     "max": round(pump[-1], 1)} if pump else None,
                  **({"looked": notes.side.report()} if notes.side is not None else {})}
    return {
        **({"scenario_k": k_facts} if k_facts else {}),
        "side_indicator": side_facts,
        "latency_rested": latency,
        "stage_split": split,
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
        "soft_looks": soft_looks_summary(notes.soft_looks, rel),
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
        **({"waits": director.waits_report()} if director.wait_done is not None else {}),
        "page_keys": {name: {k: v for k, v in facts.items() if k != "at"} for name, facts in director.keyed.items()},
        "k_keys": director.k_keys_facts(rel),
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
        "capture_route": capture_route(notes),
        "capture_sizes": [[rel(c["t"]), *c["size"]] for k, c in enumerate(notes.captures)
                          if k == 0 or c["size"] != notes.captures[k - 1]["size"]],
        "ocr": {"placements": [{**o, "t": rel(o["t"])} for o in notes.ocr],
                "log": [{**o, "t": rel(o["t"])} for o in notes.ocr_log], "loads": loads,
                "system_page": director.facts},
        "front_owner_counts": dict(notes.owners),
        "errors": {"hooks": dict(notes.errors), "log_records": dict(tap.levels)},
        "no_answer": [{**n, "t": rel(n["t"])} for n in tap.no_answer],
        "window_order": [{**n, "t": rel(n["t"])} for n in tap.window_order],
        "frame_stalls": stalls_report(notes, rel),
        "input_spells": [[rel(a), rel(b)] for a, b in notes.inputs],
        "tool_cover": None if notes.tool_cover is None else {
            **notes.tool_cover, "shown_t": rel(notes.tool_cover["shown_t"]), "gone_t": rel(notes.tool_cover["gone_t"]),
            "under_t": rel(notes.tool_cover.get("under_t"))},
        "guard": {"patched": patched, "refused": guard.refused, "chosen": sorted(set(notes.selected)),
                  "stand_in": browser.hwnd, "reached_the_stand_in": guard.used,
                  "only_the_stand_in_chosen": set(notes.selected) <= {browser.hwnd}},
        "shots": director.shots,
        "stand_in_events": dict(Counter(e["ev"] for e in events)),
        "rested_pages": rested_pages(rows),
    }


def capture_route(notes: Notes) -> dict[str, Any]:
    """Which capture gave the stand-in's frames: Windows.Graphics.Capture as TASlation finds it (`wgc.route`: its name,
    or PrintWindow and why), how often a look at it gave a frame and how often none (the capture went on with
    PrintWindow then: a session's first look, a look right after a change of size, or every look where it does not
    work), and the one that gave the most."""
    from taslation.capture import wgc

    try:
        route = wgc.route()
    except Exception as e:  # noqa: BLE001 - said by its type
        route = f"unknown ({type(e).__name__})"
    looks = dict(notes.compositor)
    frames, none = looks.get("frames", 0), looks.get("none", 0)
    used = wgc.ROUTE if frames > none else "PrintWindow" if none else "none"
    return {"route": route, "looks": looks, "used": used}


def k_block(notes: Notes, turns: list[dict[str, Any]], rows: list[dict[str, Any]], requests: list[dict[str, Any]],
            spells: dict[str, list[dict[str, Any]]], rel: Callable[[float | None], float | None]) -> dict[str, Any]:
    """Scenario k, per pace (`K_PACES`): each page flipped past - how long its sharp frame stayed (the stand-in's
    log, and from the window's first capture of it), its screen as the window told it on show (``page_on_show``),
    whether the backlog caught it -; the pages told as gone by and merged; the time from the turn back until the
    backlog had nothing left (``backlog`` pages 0); the first lettered bubble of the pages read back while the backlog
    held pages; lettering on a soft frame or on another page; the backlog's steps, what a stopped one held the worker
    after the stop, and the next page request's wait at the server; its requests computed in full; the frames' bytes
    it held. Empty without scenario k."""
    readings = notes.readings
    shows = [r for r in readings if r["kind"] == "page_on_show"]
    totals = [r for r in readings if r["kind"] == "backlog"]
    catches = [b for b in notes.backlog if b["what"] == "catch"]
    steps = [b for b in notes.backlog if b["what"] == "step"]
    mb = 1024 * 1024

    def pages_at(t: float) -> int:
        before = [r for r in totals if r["t"] <= t]
        return int(before[-1]["pages"] or 0) if before else 0

    paces: dict[str, Any] = {}
    for name in K_PACES:
        index = [k for k, r in enumerate(rows) if r["segment"] == name]
        if not index:
            continue
        mine = [(turns[k], rows[k]) for k in index]
        lo = mine[0][0]["soft_t"]
        upto = turns[index[-1] + 1]["soft_t"] if index[-1] + 1 < len(turns) else float("inf")
        back = next((i for i in range(1, len(mine)) if mine[i][0]["why"] == "jump"), len(mine))
        flips, reads = mine[1:back], mine[back:]
        flip_rows: list[dict[str, Any]] = []
        reads_t = reads[0][0]["soft_t"] if reads else float("inf")
        for turn, row in flips:
            # (a screen is told on show once confirmed, which can come just after the next turn: the page before
            # claims it first)
            before = flip_rows[-1]["seq"] if flip_rows else None
            seq = next((r["seq"] for r in shows if turn["soft_t"] <= r["t"] < turn["next_t"] + 400 and r["seq"]
                        and r["seq"] != before), None)
            # (caught once turned past: before the screen is on show again, when it is read back)
            again = next((r["t"] for r in shows if r["seq"] == seq and r["t"] >= reads_t), float("inf"))
            caught = seq is not None and any(c["caught"] and c["seq"] == seq and turn["soft_t"] <= c["t"] < again
                                             for c in catches)
            # (... or its page finished while it was on show: nothing left to catch)
            done = seq is not None and not caught and any(
                r["kind"] == "page_stage" and r["seq"] == seq and r["stage"] == "translate"
                and r["state"] in ("done", "skipped") and turn["soft_t"] <= r["t"] < turn["next_t"] + 400
                for r in readings)
            stayed = row["rest_ms"]
            look = (stayed - row["captured_sharp_ms"]
                    if stayed is not None and row["captured_sharp_ms"] is not None else None)
            flip_rows.append({"page": row["page"], "rest_ms": stayed, "from_look_ms": look, "seq": seq,
                              "caught": caught, "done_on_show": done})
        stayed_n = sum(1 for f in flip_rows if (f["rest_ms"] or 0) >= K_STAYED_MS)
        caught_n = sum(1 for f in flip_rows if f["caught"])
        told = [r for r in readings if r["kind"] == "page_stage" and lo <= r["t"] < upto]
        back_t = reads[0][0]["soft_t"] if reads else None
        empty = None
        if back_t is not None:
            empty = back_t if pages_at(back_t) == 0 else next(
                (r["t"] for r in totals if r["t"] >= back_t and not r["pages"]), None)
        flip_end = flips[-1][0]["next_t"] if flips else lo
        with_backlog = [(t, r) for t, r in reads if pages_at(t["soft_t"]) > 0]
        bg = [b for b in steps if lo <= b["began"] < upto]
        held = [b for b in notes.backlog if lo <= b["t"] < upto]
        reqs = [r for r in requests if lo <= r["t"] < upto]
        bg_reqs = [r for r in reqs if r.get("side") == "backlog"]
        page_reqs = [r for r in reqs if r["job"] is not None]
        slot = []
        for b in bg:
            if b["did"] != "stopped":
                continue
            nxt = next((r for r in requests if r["t"] >= b["t"] - 50 and r["job"] is not None), None)
            if nxt is not None:
                slot.append(server_wait(nxt))
        jobs = [j for j in notes.jobs if j["started"] and lo <= j["t"] < upto]
        thumbs = [r["thumb"] for r in told if r["thumb"]]
        by_id = {j["id"]: j for j in notes.jobs}
        flipped = {row["page"]: (f, row) for f, (_t, row) in zip(flip_rows, flips)}

        def read_back(row: dict[str, Any]) -> str:
            """How a page read back began: wholly from the cache, from what the backlog read, or read again on show
            (and why)."""
            lent = [x for x in row["reuse"] if x]
            if "reused" in lent:
                return "read reused"
            if "partial" in lent:
                return "read in part reused"
            if row["cached"]:
                return "from the cache wholly"
            why = lent[-1] if lent else "none"
            if why == "frame":
                return "read again: entry still a frame"
            if why == "size":
                return "read again: other size"
            if why in ("units", "settings"):
                return f"read again: {why}"
            flip = flipped.get(row["page"])
            if flip is None:
                return "read again: not turned past"
            if flip[0]["caught"]:
                return "read again: caught, nothing held"
            soft = any(by_id.get(i, {}).get("soft_gate") for i in flip[1]["job_ids"])
            return "read again: soft gate" if soft else "read again: not caught"

        backs = [(row, read_back(row)) for _t, row in reads]
        caught_pages = {f["page"] for f in flip_rows if f["caught"]}
        # the steps stopped by a turn to the very page they worked on (the next page job's screen), what they held
        # the worker after the stop, and that page's first bubble
        same_page_waits: list[Any] = []
        same_page_first: list[Any] = []
        for b in bg:
            if b["did"] != "stopped" or b.get("sight") is None:
                continue
            # (the job that stopped it: the first one started after the step began - a step begins with no job on)
            nxt = next((j for j in notes.jobs if j["started"] and j["t"] >= b["began"]), None)
            if nxt is not None and nxt.get("sight") == b["sight"]:
                same_page_waits.append(b.get("waited_ms"))
                row = next((r for _t, r in reads if nxt["id"] in r["job_ids"]), None)
                if row is not None:
                    same_page_first.append(row["first_lettered_ms"])
        paces[name] = {
            "pace_ms": K_PACES[name], "flips": len(flip_rows), "stayed": stayed_n, "caught": caught_n,
            "caught_share": round(caught_n / len(flip_rows), 2) if flip_rows else None,
            "done_on_show": sum(1 for f in flip_rows if f["done_on_show"]),
            # (a page stayed 800 ms or more and caught or finished on show, or neither and caught nowhere)
            "agree": sum(1 for f in flip_rows
                         if (f["caught"] or f["done_on_show"]) == ((f["rest_ms"] or 0) >= K_STAYED_MS)),
            "agree_from_look": sum(1 for f in flip_rows
                                   if (f["caught"] or f["done_on_show"]) == ((f["from_look_ms"] or 0) >= K_STAYED_MS)),
            "told_on_show": sum(1 for f in flip_rows if f["seq"] is not None),
            "told_gone_by": sum(1 for r in told if r["stage"] == "read" and r["state"] == "missed"),
            # (... and of them those whose screen was told nothing else after: a placeholder left as gone by)
            "gone_by_left": sum(1 for r in told if r["stage"] == "read" and r["state"] == "missed"
                                and not any(x["seq"] == r["seq"] and x["t"] > r["t"] for x in readings
                                            if x["kind"] == "page_stage")),
            "merged": sum(1 for r in told if r["state"] == "merged"),
            "states": dict(Counter(f"{r['stage']}:{r['state']}" for r in told)),
            "backlog_pages_most": max((int(r["pages"] or 0) for r in totals if lo <= r["t"] < upto), default=0),
            "drain_s": round((empty - back_t) / 1000, 1) if empty is not None and back_t is not None else None,
            "drain_from_flips_end_s": round((empty - flip_end) / 1000, 1) if empty is not None else None,
            "first_lettered_with_backlog": tail([r["first_lettered_ms"] for _t, r in with_backlog]),
            "first_lettered_with_backlog_not_cached": tail([r["first_lettered_ms"] for _t, r in with_backlog
                                                            if not r["cached"]]),
            "first_lettered_read_back": tail([r["first_lettered_ms"] for _t, r in reads]),
            "read_back_cached": sum(1 for _t, r in reads if r["cached"]), "read_back": len(reads),
            # (point C: each page read back, how it began; of those caught when turned past, how many began with no
            # new read - from the cache or from what the backlog read)
            "read_back_how": dict(Counter(how for _row, how in backs)),
            "read_back_caught": sum(1 for row, _how in backs if row["page"] in caught_pages),
            "read_back_caught_no_new_read": sum(1 for row, how in backs if row["page"] in caught_pages
                                                and how in ("from the cache wholly", "read reused")),
            "first_lettered_read_back_by_how": {how: tail([row["first_lettered_ms"] for row, h in backs if h == how])
                                                for how in sorted({h for _r, h in backs})},
            "same_page_turn_waits_ms": tail(same_page_waits),
            "same_page_turn_first_lettered_ms": tail(same_page_first),
            "frame_wait_ms": tail([b.get("frame_wait_ms") for b in bg]),
            "steps_on": dict(Counter(f"{b.get('on')}:{b['did']}" for b in bg)),
            # (the reads that followed one stopped before: taken up where it stopped, or begun again and why)
            "reads_after_a_stop": dict(Counter(f"{b['resumed']}:{b['did']}" for b in bg
                                               if b.get("on") == "read" and b.get("resumed"))),
            "lettered_soft_turns": sum(1 for _t, r in mine if r["lettered_soft_ms"]),
            "stale": sum(1 for x in spells.get("stale", []) if lo <= x["from_t"] < upto),
            "old_lettering_ms_max": max((r["old_lettering_ms"] or 0 for _t, r in mine), default=0),
            "results_not_sharp": sum(1 for j in jobs if j["state"] != "sharp" and j.get("result_t")
                                     and j.get("result_translated")),
            "results_unconfirmed": sum(1 for j in jobs if j["gate"] and j.get("gate_end") != "confirmed"
                                       and j.get("result_t") and j.get("result_translated")),
            "steps": dict(Counter(b["did"] for b in bg)),
            # (the steps run in a page job's hold - a read only, `Pipeline.behind_reads_allowed` -, by what they did)
            "steps_in_hold": dict(Counter(b["did"] for b in bg if b.get("in_hold"))),
            "steps_busy_s": round(sum(b["t"] - b["began"] for b in bg) / 1000, 1),
            # (the backlog's first step after a page job that showed its page - none started between -: from the page
            # shown, and from the job's end; and each such job's time after it showed its page, `keep_shown` within)
            **first_steps(jobs, bg, notes.jobs),
            "waits_ms": tail([b.get("waited_ms") for b in bg]),
            "next_page_request_server_wait_ms": tail(slot),
            "background_requests": len(bg_reqs), "background_full": sum(1 for r in bg_reqs if full_computed(r)),
            "page_requests": len(page_reqs), "page_full": sum(1 for r in page_reqs if full_computed(r)),
            "peak_mb": round(max((b.get("peak", 0) for b in held), default=0) / mb, 1),
            "regions_mb_most": round(max((b.get("regions", 0) or 0 for b in held), default=0) / mb, 2),
            "frames_held_after_read_most": max((b.get("framed_after_read", 0) for b in held), default=0),
            "bytes_at_end": held[-1].get("bytes") if held else 0,
            "thumb_height_most": max((t[1] for t in thumbs), default=None),
            "flip_list": flip_rows,
            "back_s": rel(back_t), "empty_s": rel(empty)}
    if not paces:
        return {}
    return {"paces": paces, "events": dict(Counter(r["kind"] for r in readings)),
            "step_list": {"columns": ["began_s", "t_s", "did", "on", "sight", "here", "waited_ms", "frame_wait_ms",
                                      "next_job", "next_job_sight"],
                          "rows": [[rel(b["began"]), rel(b["t"]), b["did"], b.get("on"), b.get("sight"), b.get("here"),
                                    b.get("waited_ms"), b.get("frame_wait_ms"),
                                    *((lambda j: [j["id"], j.get("sight")] if j else [None, None])(
                                        next((j for j in notes.jobs if j["started"] and j["t"] >= b["began"]), None)
                                        if b["did"] == "stopped" else None))]
                                   for b in steps]},
            "event_list": {"columns": ["t_s", "kind", "seq", "stage", "state", "pages", "thumb"],
                           "rows": [[rel(r["t"]), r["kind"], r["seq"], r["stage"], r["state"], r["pages"],
                                     r["thumb"]] for r in readings]},
            "told": told_states(readings),
            "catches": {"caught": sum(1 for c in catches if c["caught"]),
                        "not_caught": sum(1 for c in catches if not c["caught"]),
                        "from_regions": sum(1 for c in catches if c["caught"] and c["read"])},
            "thumbs_with_first_event_only": len({r["seq"] for r in readings if r["thumb"]})
            == sum(1 for r in readings if r["thumb"])}


def first_steps(jobs: list[dict[str, Any]], steps: list[dict[str, Any]], every: list[dict[str, Any]]
                ) -> dict[str, Any]:
    """Of *jobs* (page jobs of a pace) that showed their page: the backlog's first step (of *steps*) begun after the
    job's end with no other job of *every* started between - how long after the page was shown and after the job
    ended -, and how long each such job went on after showing its page."""
    after_shown: list[Any] = []
    after_end: list[Any] = []
    on_after: list[Any] = []
    for j in jobs:
        shown, over = j.get("result_t"), j.get("over_t")
        if shown is None or over is None:
            continue
        on_after.append(round(over - shown))
        step = next((b for b in steps if b["began"] >= over), None)
        if step is None:
            continue
        if any(x["started"] and over < x["t"] < step["began"] for x in every if x is not j):
            continue
        after_shown.append(round(step["began"] - shown))
        after_end.append(round(step["began"] - over))
    return {"first_step_after_shown_ms": tail(after_shown), "first_step_after_job_end_ms": tail(after_end),
            "job_after_shown_ms": tail(on_after)}


def told_states(readings: list[dict[str, Any]]) -> dict[str, Any]:
    """The states the window was told of its screens (``page_stage``): those a screen was left at work in at the end
    of the run - none should be, with nothing at work on it once the run is over -, and how often a stage told done
    or skipped was told at work again (a page shown translated, its bar back at work)."""
    last: dict[tuple[Any, str], str] = {}
    again = 0
    for r in readings:
        if r["kind"] != "page_stage" or r["state"] == "merged":
            continue
        key = (r["seq"], r["stage"])
        if r["state"] == "working" and last.get(key) in ("done", "skipped"):
            again += 1
        last[key] = r["state"]
    left = sorted(f"{seq}:{stage}" for (seq, stage), state in last.items() if state == "working")
    return {"left_working": left, "done_told_working_again": again}


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
            ps_before: list[str] | None, keep_log_in: Path | None = None) -> dict[str, Any]:
    """What the state holds at the end (any turn times a profile keeps - none -, the pages in the cache, the log's
    errors), read before it goes; the scratch folders deleted; what the window loaded in Ollama checked gone (and let
    go of if not). *keep_log_in*: the app's log copied there first (`keep_app_log`)."""
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
    if keep_log_in is not None:
        out["app_log_kept"] = keep_app_log(state, keep_log_in)
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
    if run_.get("capture_route"):
        route = run_["capture_route"]
        print(f"capture: {route['used']} (looks {route['looks']}; {route['route']}); frames {run_.get('captures')}")
    said = run_.get("no_answer") or []
    if said:
        print(f"no answer: {sum(1 for n in said if ', silence ' in n['line'])} silence(s), "
              f"{sum(1 for n in said if 'was stopped' in n['line'])} restart(s), "
              f"{sum(1 for n in said if ' ended (' in n['line'])} request(s) ended with the sentence")
    kept = run_.get("window_order") or []
    if kept:
        print(f"window order: the stand-in put under the window {sum(1 for n in kept if 'put directly under' in n['line'])}"
              f" time(s), left as it was {sum(1 for n in kept if 'left as it is' in n['line'])} time(s), "
              f"refused {sum(1 for n in kept if 'did not put' in n['line'])} time(s); hidden wholly with its frames "
              f"standing still {sum(1 for n in kept if n['line'].startswith('the viewer is hidden wholly'))} time(s)")
    cover = run_.get("tool_cover") or {}
    if cover:
        part = cover.get("part", 1.0)
        print(f"the tool's cover over {'all' if part >= 1 else f'the left {part:.0%}'} of the stand-in from "
              f"{cover.get('shown_t')} s to {cover.get('gone_t')} s: the "
              f"stand-in put over it at {cover.get('under_t')} s; the cover found over it {cover.get('over_looks', 0)} of "
              f"{cover.get('looks', 0)} looks")
    stalls = run_.get("frame_stalls") or []
    if stalls:
        print(f"frames standing still: {len(stalls)}, longest {max((s['lasted_s'] or 0) for s in stalls)} s"
              f"{' (one still standing at the end)' if any(s['until'] is None for s in stalls) else ''}; "
              f"what covered the stand-in: {[p.get('cover', {}).get('points') for s in stalls for p in s['probes'][:1]]}")
    if run_.get("input_spells"):
        print(f"input to the computer from anyone: {len(run_['input_spells'])} spell(s)")
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
    for name, k in (run_.get("scenario_k") or {}).get("paces", {}).items():
        print(f"{name}: flips {k['flips']}, stayed {K_STAYED_MS} ms {k['stayed']}, caught {k['caught']} "
              f"(agree {k['agree']}/{k['flips']}), told gone by {k['told_gone_by']}, drain {k['drain_s']} s, "
              f"first bubble with a backlog {k['first_lettered_with_backlog']}, peak {k['peak_mb']} MB, "
              f"background requests {k['background_requests']} ({k['background_full']} in full), "
              f"waits {k['waits_ms']}; read back {k['read_back_how']}, caught and begun with no new read "
              f"{k['read_back_caught_no_new_read']}/{k['read_back_caught']}, turns to the page worked on: waits "
              f"{k['same_page_turn_waits_ms']}, first bubble {k['same_page_turn_first_lettered_ms']}; "
              f"frames held {k['frame_wait_ms']} ms; steps {k['steps_on']}, busy {k['steps_busy_s']} s, reads after "
              f"a stop {k['reads_after_a_stop']}")
    side = run_.get("side_indicator") or {}
    looked = side.get("looked")
    print(f"indicator {side.get('setting')}: event pump {side.get('poll_events_ms')}" + (
        f"; looked at {looked['checks']} times {looked['layouts']}, wrong {looked['wrong']}, screens told "
        f"{looked['screens_told']}, gone by {looked['missed_told']} (drawn so {looked['missed_drawn_as_missed']}), "
        f"on show outlined {looked['on_show_outlined']}, drops {looked['drops']}, a look {looked['check_ms']} ms"
        if looked else ""))
    split = run_.get("stage_split") or {}
    if split.get("all"):
        print("where a rested page's time went (ms, median/p90/max over the finishing jobs): " + "; ".join(
            f"{k} {v['median']}/{v['p90']}/{v['max']}" for k, v in split["all"].items() if v.get("n")))
        full = split["first_request_full"]
        print(f"first request computed in full: {full['full']} of {full['turns_with_requests']} rested turns "
              f"{full['why']}; first lettered with it {full['first_lettered_ms_full']}, without "
              f"{full['first_lettered_ms_not_full']}")
        req = split["requests"]
        print(f"requests {req['n']}: computed in full {req['full']} ({req['full_prompt_s']} s of {req['prompt_s']} s "
              f"prompt; answers {req['answer_s']} s); by why {req['by_why']}; cuts {len(req['cuts'])}")
        print(f"come back to: {split['come_back']}")
        print(f"after a run: {split['after_a_run']}")
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
          f"{len(cancels['page_still_on_show'])} (given over to the page at a new size "
          f"{sum(1 for c in cancels['list'] if c['resized_away'])})")
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
        print(f"whole-book run: decisions {whole['decisions']}; frames got {whole['frames_got_by']}, not sharp "
              f"{[(f['key'], f['by'], f['sharper_taken_after_ms']) for f in whole['frames_got_not_sharp_list']]}; "
              f"readings thrown away for a sharper picture {whole.get('readings_thrown_away')}; "
              f"ended {whole['ends']}; requests {whole['requests']}")
    cancel = run_["cancel_in_flight"]
    if cancel["turns"]:
        print(f"cancelled in flight (soft {cancel['soft_ms']} ms): jobs on soft {cancel['jobs_on_soft']}, requests "
              f"on soft {cancel['requests_on_soft']}, cancelled while running {cancel['cancelled_in_flight']}; ran on "
              f"after the cancel {cancel['ran_on_after_cancel_ms']}; next real request after "
              f"{cancel['next_real_after_ms']}, its server wait {cancel['next_real_server_wait_ms']}")
    waits = run_.get("waits")
    if waits:
        print(f"--wait-done {waits['cap_s']} s: rests held {len(waits['holds'])} {waits['holds_by_why']}, held ms "
              f"{waits['held_ms']}; soft frames kept {len(waits['keeps'])} {waits['keeps_by_why']}, kept ms "
              f"{waits['kept_ms']}")


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / f"taslation-standin-{os.getpid()}",
                    help="the scratch folder (the state, the stand-in's files, report.json, shots/)")
    ap.add_argument("--scenario", default="all",
                    help="all, or some of c,a,b,d,e,r,o,z,w,x,f,f2,k (f brings f2 with it, w brings w2; k is "
                         "k5,k1,k2 and never in all)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="the display scale the stand-in's browser draws at, and TASlation's text size (1 to 3)")
    ap.add_argument("--cancel-soft-ms", type=int, default=700,
                    help="scenario x: how long the screens of little text stay soft")
    ap.add_argument("--canned", action="store_true", help="the canned translator, not the Ollama on this computer")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434",
                    help="the Ollama the window asks, on this computer (default: the app's; a second server of the "
                         "developer's own on another port, set up otherwise, is never started or stopped here)")
    ap.add_argument("--ocr-runs-on", default="auto", choices=("auto", "cpu", "gpu"),
                    help="the setting ocr_runs_on of the window (default: the app's, auto)")
    ap.add_argument("--ollama-num-gpu", default="",
                    help="the setting ollama_num_gpu of the window (default: empty, the server decides; 0: the model "
                         "on the processor only - with CUDA_VISIBLE_DEVICES=-1 and --ocr-runs-on cpu, a computer "
                         "without a GPU)")
    ap.add_argument("--start-ollama", type=int, metavar="PORT",
                    help="the window's own starter starts Ollama on this loopback port, where nothing answers (instead "
                         "of --ollama-url), with the environment it chooses; stopped at the end")
    ap.add_argument("--ollama-window-cache", default="auto", choices=("auto", "off", "on"),
                    help="the setting ollama_window_cache of the window (default: the app's, auto)")
    ap.add_argument("--canned-ms", type=int, default=350, help="the canned translator's answer time per line")
    ap.add_argument("--canned-load-s", type=float, default=5.0, help="the canned translator's load time")
    ap.add_argument("--browser", default="auto", choices=("auto", "chrome", "edge"))
    ap.add_argument("--seed", type=int, default=1, help="the stand-in's draws (soft times, waits)")
    ap.add_argument("--series", type=int, default=1, help="the dataset's series, by its place in the sorted list")
    ap.add_argument("--first", type=int, default=1, help="its first page (from 1)")
    ap.add_argument("--synthetic", action="store_true", help="the repository's test pages, not the dataset")
    ap.add_argument("--front-for-order", default="as-is", choices=("as-is", "own"),
                    help="own: the window keeps the viewer under its own as with it in front (`ui.order`), whoever is "
                         "in front (nothing is brought to the front; the window order of the stand-in alone changes)")
    ap.add_argument("--order-partly", default="as-built", choices=("as-built", "on", "off"),
                    help="`ui.order.PARTLY_COVERED_TOO` for this run: on, a window over a part of the viewer sends it "
                         "up too; off, only windows that hide all of it (default: as built)")
    ap.add_argument("--front", default="viewer", choices=("viewer", "as-is"),
                    help="viewer: the window is told the viewer is in front (the reader's case); as-is: as it is")
    ap.add_argument("--models", default="", help="the models folder (default: TASLATION_MODELS_DIR)")
    ap.add_argument("--timeout", type=float, default=180.0, help="seconds a scenario may wait for the window's rest")
    ap.add_argument("--wait-done", type=float, metavar="CAP_S",
                    help="a computer slower than the scenarios' rests were written for: the rests of a, d, e, r, o, z, "
                         "x, f and f2, the one at each one's end too, held until the page on show is finished (or "
                         "the window at rest without it), CAP_S at most, and x's soft frames kept until the window "
                         f"asked on them ({KEEP_SOFT_S:g} s at most); the holds in the report (run.waits). Without it "
                         "the scenarios are as written")
    ap.add_argument("--k-turns", type=int, default=20, help="scenario k: the pages flipped past at each pace")
    ap.add_argument("--k-read", type=int, default=0, help="scenario k: the pages read back after (default: all)")
    ap.add_argument("--k-read-ms", type=int, default=K_READ_MS,
                    help=f"scenario k: ms a page read back stays (default {K_READ_MS}; longer for a computer without "
                         "a GPU, whose page on show takes longer)")
    ap.add_argument("--k-keys", action="store_true",
                    help="scenario k: each turn released by the window's next page key once the window hands it on "
                         "(pressed on its page, as a reader turns by TASlation's keys), not by the stand-in's own "
                         "clock; the window's raise of the viewer before a key left out (with --standin-draws-covered)")
    ap.add_argument("--k-stay-ms", type=int, default=0,
                    help="scenario k: ms the last page flipped to stays before the turn back (default: the pace) - a "
                         "page read afresh on show while the pages turned past wait")
    ap.add_argument("--k-soft", default="on", choices=("on", "off"),
                    help="scenario k: the stand-in draws each page soft first (on, its own soft time) or sharp at once")
    ap.add_argument("--standin-draws-covered", action="store_true",
                    help="the stand-in browser goes on drawing while other windows hide it wholly (its occlusion "
                         "tracking off): a run that does not depend on the windows of a person at the machine")
    ap.add_argument("--cover", type=cover_plan, default=None, metavar="SEGMENT:AT:FOR",
                    help="the tool's own plain window laid over the stand-in AT seconds after SEGMENT began, for FOR "
                         "seconds (a viewer wholly covered, on purpose; no key, no activation)")
    ap.add_argument("--cover-part", type=cover_part, default=1.0, metavar="F",
                    help="--cover over the left F of the stand-in's width alone (0 < F <= 1; default 1: all of it)")
    ap.add_argument("--k-backlog", default="on", choices=("on", "off"),
                    help="off: no page is caught behind the reader (the baseline of the same turns)")
    ap.add_argument("--k-narrow", action="store_true",
                    help="scenarios k and w: in the narrow window (single pages), the stand-in placed at NARROW_SIZE "
                         "first")
    ap.add_argument("--side-indicator", default=None, choices=("column", "rail", "off"),
                    help="the setting side_indicator of the window (default: the app's, column); not off: the "
                         "indicator beside the page is looked at from the window as the events come (`SideCheck`), "
                         "pictured after the flips and the reads back of scenario k, and dropped at the end to see "
                         "it cleared")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        raise SystemExit("the stand-in needs Windows (window capture)")
    args = parse(argv)
    if not 1.0 <= args.scale <= 3.0:
        raise SystemExit("--scale is 1 to 3")
    if args.wait_done is not None and args.wait_done <= 0:
        raise SystemExit("--wait-done is a number of seconds above 0")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
