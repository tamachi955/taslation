"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the real TASlation window checked end to end on the browser-type
stand-in viewer (`tools/standin_viewer`), with no real book and no real viewer - a developer's debugging aid, never
part of a release.

    python tools/standin_e2e.py --out SCRATCH [--scenario all | c,a,b,d,e,x,f2] [--canned] [--scale 1.0]
                                [--browser auto|chrome|edge] [--seed 1] [--series 1] [--first 1] [--synthetic]
                                [--front viewer|as-is] [--cancel-soft-ms 700] [--ollama-url http://127.0.0.1:11435]
                                [--ocr-runs-on auto|cpu|gpu] [--start-ollama PORT] [--ollama-window-cache auto|off|on]
                                [--wait-done CAP_S] [--soft-first on|off] [--standin-slider 0|1|2]
                                [--standin-profile dark|light] [--standin-option NAME=VALUE ...]
                                [--see-truth] [--see-indicators on|off] [--see-edit] [--editing]
                                [--standin-size WxH] [--standin-monitor N] [--standin-maximised]
                                [--standin-full-screen] [--no-viewer-s S] [--book-asked]
                                [--start-behind cover|part|max|front|minimised] [--behind-s S] [--behind-before-s S]
                                [--behind-end close|raise] [--chooser] [--standin-bars-held MS]
                                [--standin-start-tab plain|japanese] [--pages PNG[,PNG...]]
                                [--see-margin-as-before]

What runs, all on this computer:

* the stand-in: `standin_viewer`'s page in a throwaway Chrome or Edge window of its own (``--app``, a scratch profile
  under *--out*, deleted at the end), drawing sample pages as a browser-based reader does - a band at the top, a dark
  ground, spreads right to left, every turn soft first and sharp a while later, black for a while now and then, a
  spinner. Its pages are the OpenMantra dataset's (``~/.taslation/datasets/openmantra``, read in place by file URL:
  the series chosen by its place in the sorted list, *--series*, never by name; no picture is copied), or with
  *--synthetic* (or no dataset) the repository's two test pages, turned and flipped, with *--pages* made-up pages of
  the developer's (`make_sample_page.py --layout edges`: a case reproduced on pages made for it;
  *--see-margin-as-before* compares the same run with the patches' margins as they were before they kept to the
  page's own pixels). The page
  TURNS BY ITSELF from a
  script in its URL, released part by part through a control file in the scratch folder: no key, no click, nothing
  is sent to any window by this tool, and TASlation sends none either (its key and click functions refuse here);
* TASlation in this process (`ui.app.App`, as ``taslation gui --book NAME`` opens it: its one mode, see-through -
  the lettering laid over the stand-in's own window by a click-through window of TASlation's, its own window hidden -,
  Auto on, early start and the load of the model at the start as the defaults have them, Reader mode on unless
  *--see-edit* or *--editing* - the latter editing with nothing done on the page, for timing editing against Reader
  mode -), on a scratch
  state folder (TASLATION_STATE_DIR under *--out*: the legal notice dismissed as the tests do, the window in
  English; the reader's capture area 0,85,0,0 as on the owner's browser reader, its top scaled with *--scale*),
  with the real OCR models
  (TASLATION_MODELS_DIR) and the default translator through the Ollama at *--ollama-url* on this computer -
  127.0.0.1:11435 by default, a second server of the developer's own; Ollama's usual port 11434, where the person's
  own server is likely to be, is refused without *--usual-port* - (requests only: it is never started, stopped or
  set up here; what the window loaded it lets go of at its close, and the end checks /api/ps). *--canned* (or an Ollama that does not answer or lacks the model) answers from a small server of this
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
  This tool never changes the foreground (but between its own windows with --start-behind and --chooser: below): the
  window follows a viewer in front, which is the reader's case, and with
  *--front viewer* (the default) it is told the viewer is in front whoever is (the report counts who really was);
* *--scale* other than 1: the stand-in's browser draws as on a display of that scale (``--force-device-scale-factor``,
  its own window and the page's devicePixelRatio), TASlation's text size (`Settings.ui_scale`) is set to it and the
  reader's capture area scaled with it; no setting of the system's is changed.

The scenarios, in this order (each released once the window has come to rest after the one before), every turn the
stand-in's own:
  c  turns while the model still loads at the start         a  slow reading: 9 turns 6-8 s apart
  b  fast flipping: 10 turns 0.3-0.5 s apart, then a rest   d  black flashes and spinners between turns
  e  turning back to pages translated (cache hits)
  x  a request cancelled in flight at the translator: screens of little text (the dataset's pages with one or two
     lines, by its annotation's counts) drawn soft for --cancel-soft-ms at half resolution, so that the window reads
     the soft frame and asks on it before the sharp one comes; then back (needs the dataset)
  f2 the stand-in's window made narrow (single pages)
  f3 (by its name only) a's slow reading in the narrow window: the timing figures' screens of one page
  k  (by its name only: k5, k1, k2; k3 by its own name) pages flipped past at a pace, then read back
  h  (by its name only, with --start-behind) two turns once the stand-in, out of sight at the start, is back
  m  (by its name only: m0-m4) the stand-in's window over this computer's monitors as they are: where it began, moved
     to the other monitor, straddling two, maximised on the second (never on the primary), back where it began; at
     each, once at rest, the window's dialogs and menus opened through their own objects and measured
     (`standin_monitors.Tour`), then a turn
  resize (by its name only: r1-r8) the stand-in's window resized as a drag of its edge or corner resizes it - many sizes
     over 1.5 s with the watch's own button held (the real one never pressed), then let go: its right edge narrower
     (with --editing, the region editor open on the first region) and wider, its bottom edge taller, its corner
     smaller -, then without a button: snapped to its monitor's left half, maximised, restored, its corner resized in
     steps; then a turn. *--standin-monitor N* starts the stand-in on monitor N, *--standin-maximised* maximised there
     (never on the primary). The tables are in ``run.monitors`` (`standin_monitors.WindowRun.report`)
  tab (by its name only: tab1-tab6; tab0 by its own name, with --standin-start-tab) a second tab of the stand-in's
     browser window, its page's own (standin.html's "the tabs", `standin_tabs`): another tab shown and the book's tab
     again, one of made-up Japanese lines, one closed, one shown while the page is read, their titles late, the book's
     tab moved out into a window of its own (always last); *--standin-start-tab plain|japanese* has the other tab on
     show before the window starts. The table is in ``run.tabs`` (`standin_tabs.TabRun.report`)

The rests are written for a computer of the owner's speed. *--wait-done CAP_S* is for a slower one (GitHub's runners:
the OCR on four logical processors, the model on them too): each rest of a, d, e, x, f2 and f3, the one at its end
too (the driver changes the stand-in for the next scenario as soon as it waits for it), is held until
the page on show is finished - the window shows it translated -, or the window has been at rest without it, or CAP_S
has gone by (``hN`` in the stand-in's script, let go through its control file); x's screens of little text are kept
soft until the window asked on the soft frame (``kN``, KEEP_SOFT_S at most) instead of --cancel-soft-ms. Each hold and
kept frame, why it ended and how long it held, is in the report (``run.waits``). Without it the script and the
control file are what they always were.

*--soft-first off* is for the timing figures: the stand-in draws every turn sharp at once and nothing after it
(``soft_first=0`` in its page's query), so that no wait of the viewer's is in what is timed. The window starts in a
process of its own on a scratch state with a browser window it has never seen, and what it learns of a viewer that
draws soft first (`App._drew_soft`) is held for that window in memory only, so it starts not knowing; the report says
what the stand-in drew (no soft draw) and how often the window learnt it all the same (``run.timing``: must be never).
Scenario x (a request cancelled on a soft frame) is left out of all and refused by name; c, a, b, f2, f3 and k are
timed from the sharp draw, which is the turn; d's flashes and spinners and e's turns back to cached pages change only
in that their turns have no soft time; --k-soft changes nothing. The default, on, keeps the scenarios and the
runners' checks exactly as they are.

*--standin-profile dark|light* has the stand-in behave as one of two kinds of web viewer (standin.html says how: the
page fitted to the height of the viewer's area, the cover alone, bars over the page, side arrows, a slider in the
bottom bar, a jump drawn black with a spinner or washed out first), each of its parts given another value by
*--standin-option NAME=VALUE*; it draws every turn sharp at once unless *--soft-first on* is given. The screens
foreseen follow its cover alone. Scenario q (by its name only) is written for it: turns, two jumps by the script's
``j``, the bars shown at rest, just after a turn and as a turn comes (``v``), the side arrows shown (``a``), and a jump
with the bars held over the page for 15 s. The report keeps what the stand-in said of its bars, arrows, spinner,
washed-out pictures, turns, jumps, sizes and draws, with their times (``run.stand_in_profile_events``). Without it
the stand-in is what it always was.

The see-through window is watched by `standin_seethrough.SeeWatch` (``run.see_through``: the time from the
stand-in's change of screen to the old page's patches gone, the hits, the foreground, the frames a second, the CPU;
with *--see-truth* copies of the stand-in's place on the screen in memory, checked for old patches over a new page,
two of them into shots/; *--see-indicators off* with the indicators' pane switched off,
``Settings.see_through_indicators``; *--see-edit* editing (Reader mode off), the region under the pointer measured,
``run.see_through.edit``). *--standin-size
WxH* gives the stand-in's window another size, *--standin-full-screen* starts it in the browser's own full screen (the
reader's area the whole frame). TASlation's own window is never on the screen: the watch reads its handle once a
second (on no monitor, alpha 0, an application's window with its taskbar button titled TASlation:
``run.see_through.hidden_window``). *--no-viewer-s S*
gives the window no viewer to find for its first S seconds (it names the stand-in, ``window_query``, as gui --window
does: no viewer chooser comes, the window looks for the window named until it is listed), and
*--book-asked* starts it with a name that names no book, so that the start dialog asks it at Auto's first page; the
driver answers it through the dialog's own object (``run.no_viewer``, ``run.book_asked``).

*--start-behind MODE* has the stand-in out of sight before the window is made, as a viewer behind the reader's other
windows is when TASlation starts (`Behind`): covered by a plain window of a process of its own
(`tools/standin_cover.py`: another program's to the window, which tells its own by the process) over all of it
("cover"), its left half ("part"), its monitor's work area ("max", a maximised window), or over all of it and in front
("front": the foreground taken from the stand-in only); or minimised ("minimised"); *--behind-before-s S* so long
first (a browser behind other windows a while has stopped drawing). *--behind-s S* after the window chose it, it is
back in sight (*--behind-end*: "close", the cover goes; "raise", the stand-in put over the cover and given the
foreground, as a click on it does - only while the stand-in, the cover or TASlation is in front: over a window the
person uses meanwhile nothing is raised, the cover only goes). *--chooser* names no viewer: the viewer chooser comes
and the driver answers it through its own object, first giving it the foreground as a click on it does (only while
the stand-in or the cover is in front). *--standin-bars-held MS* has a stand-in with a profile come with its bars up,
held MS ms (with *--standin-option bar_key_hide=0* its turns leave them up: the pointer resting on them). The side
panes are looked at every PANE_SAMPLE_S - whether the window wants each shown, has it shown, its window visible,
topmost and above the stand-in; the panes' ground and the room beside the page; the lettering; the windows over the
viewer; who is in front - and the report keeps them as they changed, with the time from back in sight to both panes
on the screen (``run.behind``). These are the only times this tool moves the foreground, between its own windows.

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
it); the lines sent to the translator as they were read (`streaming.LineStream`): how many stood and how many were
taken back once their unit was read, the requests so thrown away (counted apart from those sent for nothing), how
long a taken-back lettering stayed on show, and that nothing of one was in the page's lines or on show at its result
(``streamed_lines``); the jobs on a soft frame whose frame was confirmed, those of them whose confirmation was taken back (while they
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
stand-in rested on; the window's role (Reader mode or editing) as it changed; the requests of scenario x sent for nothing and what
their cancel cost. Into *--out*: report.json
(with the lines of the rule for a request without an answer and of the backlog's pause for it, ``no_answer``, each silence with what the server answered just then: `LogTap`); stacks.txt
when a request to the translator stays under way too long (`watch_stuck`: the threads' stacks, files, lines and
functions only); with --start-ollama the server's own log, ollama_server.log (no prompt or answer in it); and shots/ -
pictures of
TASlation's OWN window only (PrintWindow of its handle, the client area, hidden as it is; never a copy of the screen)
at chosen moments: they show the sample pages (CC BY-NC) and the model's lettering, for the developer's eyes; delete
them after.
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
import importlib
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
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import standin_viewer as sv  # noqa: E402

REAL_STATE = Path.home() / ".taslation"
DATASET = REAL_STATE / "datasets" / "openmantra"  # read only: its pages, by file URL
FIXTURES = ROOT / "tests" / "fixtures"
BOOK = "Stand-in sample"
BOOK_UNNAMED = "untitled"  # --book-asked: the name the window begins with, which names no book (the start asks)
BOOK_ANSWER_S = 1.5  # --book-asked: the start dialog is answered so long after it is on the screen
PLAMO = "taslation-plamo3-translate-2b"
USUAL_PORT = 11434  # Ollama's usual port: the person's own server is likely there (refused without --usual-port)
SPARE_URL = "http://127.0.0.1:11435"  # --ollama-url's default: a second server of the developer's own
AREA = (0, 85, 0, 0)  # the owner's capture area on the browser reader: the browser's title bar and the band
TICK_MS = 40  # the director looks this often (the Tk loop)
OCR_EVERY_S = 0.1
IDLE_S = 2.0  # the window at rest so long before the next scenario is released
REST_MS = 2000  # a screen on show sharp so long is one the reader rested on
STALE_MS = 1000  # a page lettered on show this long after the stand-in left it is an overlay left behind
LAG_MS = 1000  # ... any page of the window's this long: the window did not follow
LONG_CAPTURE_MS = 100  # a capture that took longer is noted with when it was
TOP_SEARCH_PX, TOP_TRIES = 40, 30  # a frame's code looked for so many rows about the start's place, in so many frames
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
    "x": ("cancelled in flight", []),  # (its steps: `cancel_steps`, on the screens of little text added for it)
    "f2": ("narrow window", ["n", "w6000", "n", "w6000"]),
    # (by its name only: a's slow reading on single pages - the stand-in made narrow first, as for f2, after the
    # window has had its viewer's window as large as it makes it; the timing figures' screens of one page)
    "f3": ("narrow window, slow reading", ["n", "w6000-8000"] * 9),
    # (scenario k: its steps from `k_steps`, on pages no scenario before it turned to)
    "k5": ("flipped past at 0.5 s a page, read back", []),
    "k1": ("flipped past at 1 s a page, read back", []),
    "k2": ("flipped past at 2 s a page, read back", []),
    "k3": ("flipped past at 3 s a page, read back (by its name only)", []),
    # (by its name only; for a stand-in with a profile, --standin-profile: its bars come over the page at rest, just
    # after a turn and as a turn comes, its jumps draw its black with the spinner or its washed-out picture, its side
    # arrows come before a turn; at the end a jump with the bars held over the page for 15 s, then gone)
    "q": ("profile: jumps, bars and arrows", ["n", "w7000", "v2500", "w6000", "n", "w300", "v1500", "w7000", "j30",
                                             "w9000", "a", "w500", "n", "w7000", "v2000", "w600", "n", "w7000", "j44",
                                             "w9000", "p", "w6000", "j56", "v15000", "w17000"]),
    # (by its name only; no profile) the page pressed and slid with the pointer, as a viewer that moves the whole page
    # along with a drag does: to the window's edge and let go (the next screen), slid a little and let go (it snaps
    # back - drawn 400 ms after the release, as a viewer on a busy computer answers it: the frame left as it was held
    # meanwhile is no page at rest, `live.RELEASE_ANSWER_MS`), to the other edge (the screen before; the pointer held
    # on the left pane's lettering switch meanwhile, `SeeWatch._follow_slides`), and a slow slide held long; the
    # pointer the window reads follows each slide
    "s": ("the page slid with the pointer", ["n", "w6000", "r700", "w1500", "o", "w7000", "r600-150", "w1500", "o400",
                                             "w5000", "l700", "w1500", "o", "w7000", "r1500", "w3000", "o", "w8000"]),
    # (by its name only) one page held long: room for what is measured on a page done (--see-add)
    "g": ("one page held long", ["n", "w90000"]),
    # (by its name only; with --start-behind) the first turns once the stand-in, out of sight at the start, is back
    "h": ("turns after a start behind other windows", ["n", "w6000", "n", "w6000"]),
    # (by their names only, "m" asks for m0-m4) the stand-in's window over this computer's monitors
    # (`standin_monitors`): each place taken while the window is at rest, then every dialog and menu of the window's
    # opened there and measured (`standin_monitors.Tour`), then a turn
    "m0": ("where it began", ["n", "w7000"]),
    "m1": ("moved to the other monitor", ["n", "w7000"]),
    "m2": ("straddling two monitors", ["n", "w7000"]),
    "m3": ("maximised on the second monitor", ["n", "w7000"]),
    "m4": ("back where it began", ["n", "w7000"]),
    # (by their names only, "r" asks for r1-r8) the stand-in's window resized: as a drag of an edge or a corner
    # resizes it, the mouse's button held (r1-r4, `standin_monitors.Drag`), and with no button (r5-r8); the window at
    # rest before each, a turn after
    "r1": ("its right edge dragged narrower", ["n", "w7000"]),
    "r2": ("its right edge dragged wider", ["n", "w7000"]),
    "r3": ("its bottom edge dragged taller", ["n", "w7000"]),
    "r4": ("its corner dragged smaller", ["n", "w7000"]),
    "r5": ("snapped to its monitor's left half", ["n", "w7000"]),
    "r6": ("maximised", ["n", "w7000"]),
    "r7": ("restored", ["n", "w7000"]),
    "r8": ("resized in steps with no button", ["n", "w7000"]),
    # (by their names only, "tab" asks for tab1-tab6; tab0 with --standin-start-tab) a second tab of the stand-in's
    # browser window (`standin_tabs`, standin.html's "the tabs"): shown and back, of made-up Japanese lines, closed,
    # shown while the page is read, its titles late, the book's tab moved out into a window of its own (always last)
    "tab0": ("the book's tab brought to the front after a start with another tab", ["w3000", "y", "w7000", "n",
                                                                                     "w7000"]),
    "tab1": ("another tab shown, then the book's tab again", ["n", "w7000", "x0", "w6000", "y", "w7000"]),
    "tab2": ("another tab of made-up Japanese lines", ["n", "w7000", "x1", "w8000", "y", "w7000"]),
    "tab3": ("another tab closed", ["n", "w7000", "x0", "w5000", "c", "w7000"]),
    "tab4": ("another tab shown while the page is read", ["n", "w700", "x1", "w7000", "y", "w7000"]),
    "tab5": ("the titles late: the other tab's after its page, the book's before", ["n", "w7000", "x1-400", "w7000",
                                                                                   "y400", "w7000"]),
    "tab6": ("the book's tab moved out into a window of its own", ["n", "w7000", "z0", "w4000", "n", "w7000"]),
}
ORDER = ["c", "a", "b", "d", "e", "x", "f2"]
K_PACES = {"k5": 500, "k1": 1000, "k2": 2000, "k3": 3000}  # scenario k: ms a page (never in "all")
K_ASKED = ("k5", "k1", "k2")  # what "k" asks for (k3 only by its name)
M_STEPS = ("m0", "m1", "m2", "m3", "m4")  # what "m" asks for: the window's places over the monitors
R_STEPS = ("r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8")  # what "resize" asks for: the window resized
WINDOW_STEPS = (*M_STEPS, *R_STEPS)
TAB_STEPS_ASKED = ("tab1", "tab2", "tab3", "tab4", "tab5", "tab6")  # what "tab" asks for (tab0 only by its name)
TAB_SCENARIOS = ("tab0", *TAB_STEPS_ASKED)  # (tab6 moves the book into a window of its own: always the last)
NAMED_ONLY = ("q", "f3", "s", "g", "h", *WINDOW_STEPS, *TAB_SCENARIOS)  # scenarios never in "all", by their names
SLIDE = re.compile(r"([rl])\d*(-\d+)?")  # a slide of the page with the pointer (to the edge without its "-D")
RELEASE = re.compile(r"o\d*")  # its release ("oN": the stand-in's answer drawn N ms after it)
NARROW = ("f2", "f3")  # the scenarios in the narrow window (the stand-in made narrow by the first of them asked)
# a stand-in with a profile: what it said of its bars, arrows, spinner, washed-out pictures, turns, jumps, sizes and
# draws, kept in the report with its time (`stand_in_profile_events`; words and numbers only)
PROFILE_EVENTS = ("bars", "bars_done", "arrows", "spinner", "preview", "turn", "jump", "size", "draw", "key", "anim",
                  "painted")
PROFILE_EVENT_WORDS = ("on", "why", "by", "dir", "side", "state", "kind", "page", "pages", "ms", "full", "band", "box",
                       "from", "to", "frames", "median", "p90", "max")
K_READ_MS = 8000  # ... the pages read back at this pace
K_STAYED_MS = 800  # ... a flipped page whose sharp frame stayed this long is caught (the gate's confirmation)
# the turns whose soft frame and sharp frame drawn quickly are pictured (turns that come to a window at rest), and
# (scenario, turn) -> (seconds after the turn began, name): the other pictures of a turn
SOFT_SHOTS = {"a": (1,), "e": (3,), "x": (1,), "f2": (1,)}
SHOTS = {("c", 2): (1.0, "c_loading"), ("a", 1): (5.2, "a_turn1_rest"), ("a", 5): (5.2, "a_turn5_rest"),
         ("b", 10): (6.0, "b_after_flipping"), ("d", 3): (5.0, "d_rest"), ("e", 1): (1.5, "e_back_cached"),
         ("x", 1): (4.0, "x_rest"), ("f2", 1): (1.5, "f_narrow_turn1"),
         ("f2", 2): (5.0, "f_narrow_rest"), ("q", 1): (8.0, "q_bars_at_rest"), ("q", 2): (1.0, "q_bars_after_a_turn"),
         ("q", 4): (0.3, "q_arrows"), ("q", 8): (9.0, "q_bars_held")}
RESIZE_SHOT_S = 3.0  # the picture of the window this long after the stand-in drew its page at a new size
CANCEL_SCREENS = 3  # scenario x: the screens of little text (spreads of pages with 1 to CANCEL_LINES lines of text)
CANCEL_LINES = 2
CANCEL_FACTOR = 2  # ... drawn soft this many times smaller (a soft frame the window can read)
# --wait-done (a slower computer than the one the rests were written for): the rests of these scenarios held until
# their page is finished (`held`, `hold_over`), and scenario x's soft frames kept until the window asked on them,
# KEEP_SOFT_S at most. Not c (turns while the model loads) nor b (quick turns).
HOLD_SCENARIOS = ("a", "d", "e", "x", "f2", "f3")
KEEP_SOFT_S = 15.0


@dataclass
class Segment:
    name: str
    go: int
    steps: list[str]
    screens: list[tuple[int, bool]] = field(default_factory=list)  # the screen after each turn, as foreseen


def wanted(text: str) -> list[str]:
    """The scenarios asked for, in `ORDER` ("k" asks for `K_ASKED`). The scenarios of TASlation's own window that
    went with it in 2.0.0 (r, t, t2, o, z, f) are unknown ones."""
    if text.strip().lower() in ("", "all"):
        return list(ORDER)
    asked = {p.strip().lower() for p in text.split(",") if p.strip()}
    for group, members in (("k", K_ASKED), ("m", M_STEPS), ("resize", R_STEPS), ("tab", TAB_STEPS_ASKED)):
        # (not "r": the former own window's)
        if group in asked:
            asked = (asked - {group}) | set(members)
    unknown = asked - set(SCENARIOS)
    if unknown:
        raise SystemExit(f"unknown scenario(s): {', '.join(sorted(unknown))}")
    return [n for n in [*ORDER, *K_PACES, *NAMED_ONLY] if n in asked]


def tab_order(names: list[str]) -> list[str]:
    """*names* with tab0 first (the book's tab brought back after a start with another tab on show: nothing before
    it is read) and tab6 last (after it the book is in a window of its own), the others as they were."""
    head = [n for n in names if n == "tab0"]
    tail = [n for n in names if n == "tab6"]
    return [*head, *(n for n in names if n not in ("tab0", "tab6")), *tail]


def soft_first_scenarios(names: list[str], text: str, soft_first: bool) -> tuple[list[str], str | None]:
    """The scenarios *names* (`wanted` of *text*) as a run with the stand-in's soft first drawing (*soft_first*) or
    without it can have them, and why x was left out (None: it was not). Without soft frames scenario x (a request
    cancelled on a soft frame) has nothing to do: left out of all, refused when named."""
    if soft_first or "x" not in names:
        return names, None
    if "x" in {p.strip().lower() for p in text.split(",")}:
        raise SystemExit("scenario x needs the stand-in's soft frames: not with --soft-first off")
    return [n for n in names if n != "x"], "needs the stand-in's soft frames (--soft-first off)"


def k_steps(name: str, fresh: int, width: int, turns: int, read: int, soft: bool,
            read_ms: int = K_READ_MS, stay_ms: int = 0) -> list[str]:
    """Scenario k's steps at the pace of *name* (`K_PACES`): to page *fresh* (one no scenario before turned to) and a
    rest there, *turns* pages flipped past, the last of them kept *stay_ms* (0: the pace), back to the first of them,
    and *read* of them read at *read_ms* a page (K_READ_MS); without *soft*, every page drawn sharp at once (the
    stand-in's soft time and blur off, and back after). Every turn is the stand-in's own."""
    pace = K_PACES[name]
    pre, post = ([], []) if soft else (["t0", "b1"], ["t", "b"])
    flips = ["n", f"w{pace}"] * turns
    if stay_ms and flips:
        flips[-1] = f"w{stay_ms}"
    steps = [*pre, f"j{fresh}", f"w{read_ms}", *flips, f"j{fresh + width}", f"w{read_ms}"]
    steps += ["n", f"w{read_ms}"] * max(0, read - 1)
    return [*steps, *post]


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
    (`hold_over`). (The rest at the end is held as well because the driver changes the stand-in as soon as it waits
    for the next scenario - its size changed for f2 -, before the window is at rest: a page still being translated
    then was cut short, as the last of the dark theme's scenario of 1.0.1 was on a runner, by f2's narrow window.)"""
    out, n = [], first
    for step in steps:
        out.append(step)
        if step.startswith("w") and int(step[1:].split("-")[0]) >= REST_MS:
            out.append(f"h{n}")
            n += 1
    return out


def profile_screen(n: int, count: int, spread: bool) -> int:
    """The first page of the screen that holds page *n* on a stand-in with a profile: the cover alone, then the
    spreads 1-2, 3-4, ... (as standin.html's ``screenOf`` with cover 1)."""
    n = max(0, min(count - 1, n))
    return n if not spread or n == 0 else n - (n - 1) % 2


def build_plan(names: list[str], count: int, cancel_first: int | None = None, soft_ms: int = 700,
               wait_done: float | None = None, k: dict[str, Any] | None = None, cover: bool = False,
               lead: list[str] | None = None) -> tuple[list[Segment], list[sv.Step]]:
    """The segments of the stand-in's script (each held at ``gN`` until the driver releases it, ``mN`` to mark it)
    and the script; the screen each turn will show, foreseen as the page turns (spreads until the narrow window).
    Scenario x turns to the screens of little text from page *cancel_first* on (`cancel_steps`); scenario k's
    segments (`k_steps`, *k*: turns, read, soft, narrow) to pages after the farthest one turned to before. With
    *wait_done* (--wait-done's cap, seconds) the rests of HOLD_SCENARIOS are held (`held`) and x's soft frames kept
    until the window asked (KEEP_SOFT_S at most, and the cap); without it the script is the same as ever. *cover*: the
    screens of a stand-in with a profile, the cover alone (`profile_screen`). *lead*: steps of no turn run as the page
    loads, before the first segment (``--standin-bars-held``: the bars up from the start)."""
    segments: list[Segment] = []
    index, spread, farthest = 0, True, 0
    text: list[str] = list(lead or [])
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
                            bool(k.get("soft", True)), int(k.get("read_ms") or K_READ_MS), int(k.get("stay_ms") or 0))
        else:
            steps = SCENARIOS[name][1]
        if wait_done is not None and name in HOLD_SCENARIOS:
            steps = held(steps, holds + 1)
            holds += sum(1 for s in steps if s.startswith("h"))
        segment = Segment(name, go, steps)
        if name in NARROW:
            spread = False
        slid: re.Match[str] | None = None  # (the slide the next "o" lets go: to the edge, a turn)
        for step in steps:
            if SLIDE.fullmatch(step):
                slid = SLIDE.fullmatch(step)
                continue
            if RELEASE.fullmatch(step):
                turn, slid = (slid.group(1) if slid is not None and slid.group(2) is None else None), None
                if turn is None:
                    continue
                step = "n" if turn == "r" else "p"
            if step in ("n", "p") or (step.startswith("j") and step[1:].isdigit()):
                width = 2 if spread else 1
                if cover:
                    shown = 1 if not spread or index == 0 or index + 1 >= count else 2
                    to = int(step[1:]) if step.startswith("j") else index + shown if step == "n" else index - 1
                    index = profile_screen(to, count, spread)
                    width = 1 if not spread or index == 0 or index + 1 >= count else 2
                else:
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
    turns = sum(sum(1 for s in SCENARIOS[n][1] if s == "n" or RELEASE.fullmatch(s)) * (1 if n in NARROW else 2)
                for n in names)
    turns += sum(2 * (k_turns + 2) for n in names if n in K_PACES)
    turns += max((int(s[1:]) for n in names for s in SCENARIOS[n][1] if s[:1] == "j" and s[1:].isdigit()), default=0)
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
        self.areas.sort(key=lambda a: (not a[1], a[0][0], a[0][1]))  # (as `standin_monitors.Screens` numbers them)

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
def _where(e: BaseException) -> str:
    """Where *e* rose, as " (file:line in function < file:line in function)", its two innermost frames: a failure of
    the tool's own names its place in the report, never its message (which may hold a path or a text)."""
    frames = traceback.extract_tb(e.__traceback__)[-2:]
    if not frames:
        return ""
    return " (" + " < ".join(f"{Path(f.filename).name}:{f.lineno} in {f.name}" for f in reversed(frames)) + ")"


class Notes:
    """What the hooks see, as numbers and codes (`standin_viewer.Shown` of every picture): the page jobs, the
    translator's requests, the pictures the page area was given, the frames captured, the loads of the model, the OCR
    readers' place, who was in front, the errors. Written from the Tk thread, the worker and the pipeline's threads."""

    def __init__(self, top: int, dpr: float):
        self.top, self.dpr = top, dpr
        self.tops: dict[tuple[int, int], int] = {}  # (`shown`: the rows above the page's content, by frame size)
        self.top_tries: Counter[tuple[int, int]] = Counter()
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
        # the start's dialog on the GPU's memory as the driver met and answered it (`--gpu-short-answer`), and the
        # window's "Loading the models..." (``_models_loading``) as it came and went
        self.gpu_dialogs: list[dict[str, Any]] = []
        self.models_loading: list[list[Any]] = []
        # --book-asked: the start dialog asking the book's name, as the driver met and answered it; --no-viewer-s: when
        # the stand-in was first offered to the window's look for windows, and when the window chose it
        self.book_dialogs: list[dict[str, Any]] = []
        self.no_viewer: dict[str, Any] = {}
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
        self.long_steps: list[dict[str, Any]] = []  # the looks at the viewer that took over LONG_STEP_MS (`step_call`)
        self.soft_looks: list[dict[str, Any]] = []  # each frame the window judged soft or sharp (`soft_look`)
        # each time the window learnt that the viewer draws a page soft first (`App._drew_soft`): when, and what the
        # stand-in drew on the two frames it took for the soft and the sharp picture
        self.drew_soft: list[dict[str, Any]] = []
        self.margins: list[dict[str, Any]] = []  # the capture area in force and the frame's own, as they changed
        self.modes: list[dict[str, Any]] = []  # the role (Reader mode: reader, editing: translator), as changed
        # what the driver changed between scenarios (the stand-in's size), and when: a rest on the page before ends
        # there (`turn_rows`)
        self.acts: list[dict[str, Any]] = []
        self.lookups: list[dict[str, Any]] = []  # each page unit a page job looked for in the cache, and what it found
        self.resolves: list[dict[str, Any]] = []  # ... and each look for the page as read at other sizes
        self.decides: list[dict[str, Any]] = []  # each page job kept for now, decided (`Pipeline.decide_kept`): how
        self.on_display: Callable[[dict[str, Any]], None] | None = None
        # where a page job's time went (`span`: its stages, by thread), the cuts of the pairs that only grow
        # (`GrowingContext.take`), and the loads and unloads of the model that leave the server holding nothing
        self.spans_off: list[tuple[str, float, float, str, Any]] = []  # (spans while no page job ran)
        self.cuts: list[dict[str, Any]] = []
        self.server_resets: list[dict[str, Any]] = []
        self.warms: list[dict[str, Any]] = []  # each step of the warming while the reader reads (no job's request)
        self.readings: list[dict[str, Any]] = []  # normal reading's events (`backlog`: no thumbnail, no text)
        self.backlog: list[dict[str, Any]] = []  # the backlog's catches and steps, with what it held after each
        self.warm_calls: list[dict[str, Any]] = []  # each warming begun (`PlamoTranslator.warm_prefix`): what it did
        self.priority: list[dict[str, Any]] = []  # the server lowered for the backlog and set back (`watch_priority`)
        # (memory only, never written or printed: a request's line as a number, to find a line asked for again)
        self.sources: dict[int, int] = {}

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
        """What the frame *image* shows (`standin_viewer.decode`), its code read below the browser's own rows at the
        top of the client area: as many as at the start (*top*), or as many as were found for a frame of its size
        (`tops`). A frame of a size whose code is not where the start's rows put it - the browser's window maximised
        draws its title rows lower or higher, and every frame of it was "unknown" - is read at the rows TOP_SEARCH_PX
        about that place, the nearest first, until a place reads (TOP_TRIES frames of a size at most); the rows kept
        for the size are the middle of the places that read there (the code's cells are some rows high: the first
        place found reads at their edge)."""
        if image is None:
            return sv.Shown()
        try:
            size = image.size
            top = self.tops.get(size, self.top)
            found = sv.decode(image, top, self.dpr)
            if found.known or size in self.tops or self.top_tries[size] >= TOP_TRIES:
                return found
            self.top_tries[size] += 1
            cell = max(1, round(sv.CELL * self.dpr))
            for step in range(1, TOP_SEARCH_PX + 1):
                for other in (self.top - step, self.top + step):
                    there = sv.decode(image, other, self.dpr) if other >= 0 else sv.Shown()
                    if there.known and not there.black:
                        away, end = (-1 if other < self.top else 1), other
                        for _ in range(2 * cell):  # (on, away from the start's place, while it reads the same)
                            if end + away < 0 or sv.decode(image, end + away, self.dpr) != there:
                                break
                            end += away
                        self.tops[size] = (other + end + 1) // 2  # (as `decode` reads a cell: below its middle row)
                        return there
            return found
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
        """A normal reading event (`backlog`), numbers only."""
        rec = {"t": now_ms(), "kind": kind, **{k: data.get(k) for k in ("seq", "stage", "state", "into", "pages",
                                                                       "lines", "paused", "dropped")}}
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
                # the drafts layer of a unit's lines sent as they were read (`PageFill.early_draft`): a lettering it
                # showed, and how long one taken back stayed on show
                index, early = data.get("index"), bool(data.get("early")) and not data.get("early_end")
                shown = job.setdefault("_early_at", {})
                if early and data.get("text"):
                    job["early_translated"] = job.get("early_translated", 0) + 1
                    job["first_early_t"] = job.get("first_early_t") or t
                    shown.setdefault(index, t)
                if data.get("withdrawn"):
                    job["withdrawn"] = job.get("withdrawn", 0) + 1
                    if index in shown:
                        job.setdefault("withdrawn_ms", []).append(round(t - shown.pop(index), 1))
                elif not early:
                    shown.pop(index, None)
                job.setdefault("_last_early", {})[index] = early and bool(data.get("text"))
            elif kind == "result":
                result = data.get("result")
                job["result_t"] = t
                job["early_left_at_result"] = sum(1 for v in job.get("_last_early", {}).values() if v)
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
                   "side": getattr(self.local, "side", None), "n": len(self.requests),
                   # (a run of a unit's lines sent as they were read, `streaming.LineStream`: its number, which the
                   # stream's counts name when it was taken back)
                   "stream": stream_token()}
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
        """The window's role (Reader mode or editing), noted as it changes."""
        rec = {"t": now_ms(), "role": str(app.role_var.get())}
        with self.lock:
            last = self.modes[-1] if self.modes else None
            if last is None or any(last[k] != rec[k] for k in rec if k != "t"):
                self.modes.append(rec)

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

    def act(self, segment: str, what: str) -> None:
        with self.lock:
            self.acts.append({"t": now_ms(), "segment": segment, "act": what})

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
               "room": getattr(placement, "room", None), "engines": list(engines), "loading": self.load_depth > 0}
        with self.lock:
            last = self.ocr[-1] if self.ocr else None
            if last is None or any(last[k] != rec[k] for k in ("device", "why", "engines", "loading")):
                self.ocr.append(rec)


# status lines said with `say` that speak of a page: of the page the job read, of the viewer's page on show
JOB_KEYS = ("Stopped: this page was not translated",)


def status_kind(render: Any, key: str | None) -> tuple[str, str | None, Any]:
    """What a status line is, from the window's record of it (*render*, the callable that says it again in the
    window's language, and *key*, its template when it was said with `say`): its kind - "page_summary" (a page's
    summary), "progress" (a page job at work), "say:" and the template's first words, "message:" and a Message's
    code, "other" -, never its text; which page it speaks of ("result": the page in its words, "job": the page the
    running job reads, None: no page); and the page's result for "result"."""
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
    if key:
        about = "job" if key.startswith(JOB_KEYS) else None
        return "say:" + "_".join(re.findall(r"[A-Za-z]+", key)[:4]), about, None
    message = next((c for c in cells if type(c).__name__ == "Message"), None)
    if message is not None:
        return "message:" + str(getattr(message, "code", "?")), None, None
    return "other", None, None


def tk_error() -> type[Exception]:
    """Tk's error class (imported where it is used: the tool's top imports no Tk)."""
    import tkinter as tk

    return tk.TclError


def _user32() -> Any:
    """user32 of this tool's own (its functions' argument types set here touch no other module's)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32")
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    return user32


def root_of(widget: Any) -> int:
    """The top-level window (Windows' handle) of the Tk widget *widget*."""
    return int(_user32().GetAncestor(widget.winfo_id(), 2) or 0)  # GA_ROOT


class LogTap(logging.Handler):
    """The app's log records: where the OCR readers went (the template's codes, never a text of a page), and the
    warnings and errors by logger, level and type name."""

    # (the session's plan, `ocr.place.settle`: parts on the GPU, parts sent to the processor, why, short by, left;
    # the readers' placement: device, why, MiB left at the peak; the net: the part, the failure's type name)
    TEMPLATES = (("the GPU for this session:", "plan"), ("the OCR readers run on the %s (%s", "run_on"),
                 ("the %s failed on the GPU", "failed"), ("where the OCR runs could not be decided", "undecided"))

    # the lines of the rule for a request without an answer (`translate.ollama`, `ollama_start.OllamaStarter.restart`,
    # `pipeline.LoadAhead`) and of the backlog's pause for it: fixed words, numbers and a thread's name, never a line
    NO_ANSWER_PREFIXES = ("no answer:", "backlog paused: the translation program", "backlog goes on:")
    # the window's lines of the viewer kept under it (`ui.order`): fixed words and numbers only
    WINDOW_ORDER_PREFIXES = ("window order:",)

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
                    words = [str(a) for a in args if isinstance(a, (str, int, float))][:5]
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


# A look at the viewer on the Tk thread (`STEP_CALLS`) that took over LONG_STEP_MS is noted whole (`long_steps`): each
# call made in it (`STEP_PARTS` of the window's, `STEP_FUNCS` elsewhere) timed apart - how often, wall ms, the Tk
# thread's CPU ms; a call within another counts in both -, the CPU ms of the whole process in it (all its threads: with
# the wall long and both low, the window waited for the processor, not for a thread of its own) and the requests to
# the translator under way then; the LONG_STEPS_KEPT longest are reported
STEP_CALLS = ("_poll", "_look", "_follow_step")
STEP_PARTS = ("_viewer_shows_book", "_frame_count", "_capture", "_drew_nothing", "_turn_seen", "_show_live",
              "_redisplay", "_check_sharper", "_take_at_once", "_all_cached", "_looks_soft", "_take", "_begin_follow",
              "_early_start", "_look_over_job")
STEP_FUNCS = (("ui.live", "window_exists"), ("ui.live", "_thumb"), ("ui.live", "_detail"),
              ("ui.preview", "ImageCanvas.set_image"))
LONG_STEP_MS = 300
LONG_STEPS_KEPT = 12


def step_call(notes: Notes, name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    def call(self: Any, *a: Any, **k: Any) -> Any:
        if getattr(notes.local, "step", None) is not None:
            return original(self, *a, **k)  # (within another look: its parts are that one's)
        step: dict[str, Any] = {"call": name, "t": now_ms(), "busy": bool(getattr(self, "busy", False)), "parts": {}}
        notes.local.step = step
        wall, cpu, process = time.perf_counter(), time.thread_time(), time.process_time()
        try:
            return original(self, *a, **k)
        finally:
            notes.local.step = None
            step["ms"] = (time.perf_counter() - wall) * 1000
            if step["ms"] > LONG_STEP_MS:
                step["cpu_ms"] = (time.thread_time() - cpu) * 1000
                step["process_cpu_ms"] = (time.process_time() - process) * 1000
                with notes.lock:
                    notes.long_steps.append(step)

    call.__name__ = name
    return call


def part_call(notes: Notes, name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    def call(*a: Any, **k: Any) -> Any:
        step = getattr(notes.local, "step", None)
        if step is None:
            return original(*a, **k)
        wall, cpu = time.perf_counter(), time.thread_time()
        try:
            return original(*a, **k)
        finally:
            part = step["parts"].setdefault(name, [0, 0.0, 0.0])
            part[0] += 1
            part[1] += (time.perf_counter() - wall) * 1000
            part[2] += (time.thread_time() - cpu) * 1000

    call.__name__ = name.rsplit(".", 1)[-1]
    return call


def long_steps_report(notes: Notes, requests: list[dict[str, Any]], rel: Callable[[Any], Any]) -> dict[str, Any]:
    """The longest looks at the viewer (`STEP_CALLS` over LONG_STEP_MS, the longest first): when, which, how long, a
    page job running, the Tk thread's and the whole process's CPU ms, each call in it ([how often, wall ms, CPU ms]),
    and the requests under way then (their side - "page" for a page job's own -, why the server computed what it did,
    when each began)."""
    with notes.lock:
        steps = sorted(notes.long_steps, key=lambda s: -s["ms"])
    out = []
    for s in steps[:LONG_STEPS_KEPT]:
        t0, t1 = s["t"], s["t"] + s["ms"]
        under = [{"t_s": rel(r["t"]), "side": r.get("side") or ("page" if r.get("job") is not None else "none"),
                  "why": r.get("why")} for r in requests if r["t"] <= t1 and (r.get("end_t") or t1) >= t0]
        parts = sorted(s["parts"].items(), key=lambda kv: -kv[1][1])
        out.append({"t_s": rel(t0), "call": s["call"], "ms": round(s["ms"]), "job_running": s["busy"],
                    "cpu_ms": round(s["cpu_ms"]), "process_cpu_ms": round(s["process_cpu_ms"]),
                    "parts": {name: [n, round(w, 1), round(c, 1)] for name, (n, w, c) in parts},
                    "requests": under})
    return {"over_ms": LONG_STEP_MS, "count": len(steps), "longest": out}


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
          ("pipeline", "ReadBeside", "take", "beside_wait"), ("pipeline", "Pipeline", "_measure_slants", "slants"),
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
COVER_EX = "plain"  # the cover's extended style: "plain" (none: a window as any program's, shown with no activation all
# the same), "noactivate" (WS_EX_NOACTIVATE: Chromium's occlusion tracking was seen not to count it - the stand-in drew
# on under it; `--cover-style`)
COVER_FRONT_S = 3.0  # --front-for-order own: the window put at the top of the order (no activation) so long after the
# cover came, as a person's click on TASlation puts it (the frames under the cover stand still for that long first;
# --cover-front-s)


class CoverWindow:
    """A plain opaque window of this tool's own process laid over the stand-in's window and directly above it in the
    order of windows (`--cover`): what a reader's other program over the viewer is, made on purpose. Shown with no
    activation and no key; any window that lay above the stand-in stays above the cover. *part* below 1 (`--cover-part`):
    only the left part of the stand-in so wide is covered (a note or a dictionary laid over a part of the viewer), the
    rest stays in sight. *rect* (x, y, w, h): that place instead (a window maximised on the stand-in's monitor: its work
    area). *front*: given the foreground as it shows - only while the stand-in has it (the tool's own window to the
    tool's own window; never taken from another program) -, as another program the reader brought to the front over
    the viewer is (``front_taken`` says whether it was). Its own thread and message loop; `close` ends it."""

    def __init__(self, standin: int, part: float = 1.0, style: str = COVER_EX,
                 rect: tuple[int, int, int, int] | None = None, front: bool = False):
        self.standin, self.hwnd, self.part = standin, 0, part
        self.rect, self.front, self.front_taken = rect, front, False
        self.no_activate_style = style == "noactivate"
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
        if self.rect is not None:
            x, y, w, h = self.rect
        style = 0x00C00000 | 0x00080000  # WS_CAPTION | WS_SYSMENU: a window as any program's (not shown yet)
        ex = 0x08000000 if getattr(self, "no_activate_style", False) else 0  # [WS_EX_NOACTIVATE] (see COVER_EX)
        self.hwnd = int(user32.CreateWindowExW(ex, COVER_CLASS, "stand-in cover", style, x, y, w, h,
                                               None, None, instance, None) or 0)
        if self.hwnd:
            user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetWindow.restype = wintypes.HWND
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, wintypes.UINT]
            above = user32.GetWindow(self.standin, 3)  # GW_HWNDPREV: the window just above the stand-in, if any
            after = above if above and int(above) != self.hwnd else wintypes.HWND(0)  # (else HWND_TOP)
            user32.SetWindowPos(self.hwnd, after, x, y, w, h, 0x0010 | 0x0040)  # SWP_NOACTIVATE | SWP_SHOWWINDOW
            # (then moved by a pixel, SWP_NOZORDER: a window shown with no activation and not moved is not seen by
            # Chromium's occlusion tracking until some other window event; a person's window that comes over the
            # viewer comes with a change of the window in front or a move)
            user32.SetWindowPos(self.hwnd, None, x + 1, y, w, h, 0x0010 | 0x0004)  # SWP_NOACTIVATE | SWP_NOZORDER
            if self.front and int(user32.GetForegroundWindow() or 0) == int(self.standin):
                self.front_taken = bool(user32.SetForegroundWindow(self.hwnd))
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


BEHIND_MODES = ("cover", "part", "max", "front", "minimised")
BEHIND_S = 8.0  # --start-behind: the stand-in back in sight so long after the window chose it (--behind-s)
BEHIND_ENDS = ("close", "raise")
PANE_SAMPLE_S = 0.25  # --start-behind: the side panes' state looked at this often (kept where it changed)
CHOOSER_ANSWER_MS = 400  # --chooser: the chooser answered so long after it was given the foreground


def monitor_work_area(hwnd: int) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the work area of the monitor *hwnd* lies on most (a window maximised there fills it)."""
    user32 = ctypes.WinDLL("user32")

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))  # MONITOR_DEFAULTTONEAREST
    r = info.rcWork
    return r.left, r.top, r.right - r.left, r.bottom - r.top


class Behind:
    """``--start-behind MODE``: the stand-in out of sight before the window is made, as a viewer behind the reader's
    other windows is when TASlation starts - "cover": a plain window of a process of its own over all of it
    (`tools/standin_cover.py`: another program's, never TASlation's - the window tells its own by the process), shown
    with no activation (the stand-in keeps the foreground); "part": over its left half; "max": over the whole work area
    of its monitor, as a maximised window is; "front": over all of it and given the foreground (taken from the stand-in
    only): another program in front over the viewer; "minimised": the stand-in minimised with no activation. `end`
    puts it back in sight (``--behind-end``): "close" - the cover gone (with "front" the foreground given back to the
    stand-in first, so that nothing of the reader's gets it); "raise" - the stand-in put over the cover, which stays
    under it, and given the foreground when the cover held it: a person's click on the viewer; a minimised stand-in
    either way restored with no activation and put at the top of the order (made topmost and ordinary again, as
    `capture.raise_window` does). The cover goes at the run's end (`close`). Only the tool's own windows are touched."""

    def __init__(self, mode: str, standin: int, how: str = "close"):
        self.mode, self.standin, self.how = mode, int(standin), how
        self.cover: subprocess.Popen[str] | None = None
        self.cover_hwnd = 0
        self.facts: dict[str, Any] = {"mode": mode, "end": how, "made_t": None, "ended_t": None}

    def start(self) -> None:
        user32 = ctypes.WinDLL("user32")
        self.facts["front_before"] = "standin" if int(user32.GetForegroundWindow() or 0) == self.standin else "other"
        if self.mode == "minimised":
            user32.ShowWindow(self.standin, 7)  # SW_SHOWMINNOACTIVE
            self.facts["made"] = bool(user32.IsIconic(self.standin))
        else:
            argv = [sys.executable, "-I", str(Path(__file__).with_name("standin_cover.py")), "--over",
                    str(self.standin), "--tool-pid", str(os.getpid())]
            if self.mode == "part":
                argv += ["--part", "0.5"]
            if self.mode == "max":
                argv += ["--rect", ",".join(str(v) for v in monitor_work_area(self.standin))]
            if self.mode == "front":
                argv.append("--front")
            self.cover = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            line = (self.cover.stdout.readline() if self.cover.stdout else "").split()
            if len(line) == 3 and line[0] == "ready":
                self.cover_hwnd = int(line[1])
                self.facts["front_taken"] = line[2] == "1"
            self.facts["made"] = bool(self.cover_hwnd)
            self.facts["cover_pid_other"] = bool(self.cover.pid and self.cover.pid != os.getpid())
        self.facts["made_t"] = now_ms()

    def _say(self, word: str) -> str:
        cover = self.cover
        if cover is None or cover.stdin is None or cover.poll() is not None:
            return ""
        try:
            cover.stdin.write(word + "\n")
            cover.stdin.flush()
            return (cover.stdout.readline() if cover.stdout else "").strip()
        except OSError:
            return ""

    def end(self) -> None:
        """The stand-in back in sight (see the class)."""
        if self.facts.get("ended_t") is not None:
            return
        # (put over the other windows only while the stand-in, the cover or TASlation is in front: never over a window
        # the person is using meanwhile - then the cover only goes, the stand-in stays where it lies)
        ours = front_kind(self.standin, self.cover_hwnd) in ("standin", "cover", "own")
        self.facts["front_at_end"] = front_kind(self.standin, self.cover_hwnd)
        if self.cover is not None:
            raise_it = self.how == "raise" and ours
            if self.how == "raise" and not ours:
                self.facts["raise_skipped"] = True
            self.facts["answer"] = self._say("raise" if raise_it else "end")
            if not raise_it:
                self.close()
        else:
            user32 = ctypes.WinDLL("user32")
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, wintypes.UINT]
            stay = 0x0001 | 0x0002 | 0x0010  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
            user32.ShowWindow(self.standin, 4)  # SW_SHOWNOACTIVATE: restored, not activated
            if ours:
                user32.SetWindowPos(self.standin, -1, 0, 0, 0, 0, stay)  # HWND_TOPMOST: to the top of the screen ...
                user32.SetWindowPos(self.standin, -2, 0, 0, 0, 0, stay)  # HWND_NOTOPMOST: ... ordinary again
            else:
                self.facts["raise_skipped"] = True
        self.facts["ended_t"] = now_ms()

    def close(self) -> None:
        """The cover gone (the run's end; `end` with "close")."""
        cover, self.cover = self.cover, None
        if cover is None:
            return
        try:
            if cover.poll() is None and cover.stdin is not None:
                cover.stdin.write("end\n")
                cover.stdin.flush()
                cover.stdin.close()
            cover.wait(5.0)
        except (OSError, subprocess.TimeoutExpired):
            cover.kill()


def pane_state(app: Any, standin: int, cover: int = 0) -> dict[str, Any]:
    """The side panes as they are now (--start-behind): per side whether the Tk thread wants it shown, whether the
    see-through window has it shown, whether its window is visible, topmost and above the stand-in in the order of the
    windows; the Tk thread's ground and the left pane's room; whether the lettering shows; the windows found over the
    viewer; the stand-in's state. Flags and counts only."""
    from taslation.ui import seethrough as see_ui

    user32 = ctypes.WinDLL("user32")
    over = getattr(app, "_see_through", None)
    out: dict[str, Any] = {"ground": getattr(app, "_see_ground", None) is not None, "left_room": see_ui.left_room(app),
                           "standin_topmost": is_topmost(standin), "standin_iconic": bool(user32.IsIconic(standin)),
                           "cover_above": cover_over(cover, standin) if cover and user32.IsWindow(cover) else None,
                           "front": front_kind(standin, cover),
                           "bars": getattr(app, "_see_bars_since", None) is not None}
    ground = getattr(app, "_see_ground", None)
    if ground is not None:
        from taslation import panes as pn

        size, page, _band, _colour, columns = ground
        dpi = getattr(app, "_see_dpi", 96)
        out["ground_at"] = {"size": list(size), "page": list(page) if page else None,
                            "columns": list(columns) if columns else None, "dpi": dpi,
                            "rooms": list(pn.rooms(size, page, dpi, columns))}
        out["memo"] = {side: [m[1] is not None, m[2] is not None]
                       for side, m in (getattr(app, "_see_pane_memo", None) or {}).items()}
    if over is None:
        return out
    for side in ("left", "right"):
        h = int(over.panes.get(side, 0) or 0)
        out[side] = {"want": over._pane_want.get(side) is not None, "shown": over.pane_shown(side) is not None,
                     "visible": bool(user32.IsWindowVisible(h)) if h else None,
                     "topmost": is_topmost(h) if h else None, "above_standin": cover_over(h, standin) if h else None}
    out["lettering"] = over.shown() is not None
    out["covers"] = len(getattr(over, "_covers", ()) or ())
    return out


def front_kind(standin: int, cover: int = 0) -> str:
    """Which window is in front: "standin", "cover" (`Behind`'s), "own" (one of this process's: TASlation's), "other"
    or "none". Read only."""
    user32 = ctypes.WinDLL("user32")
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    fg = int(user32.GetForegroundWindow() or 0)
    if not fg:
        return "none"
    if fg == int(standin):
        return "standin"
    if cover and fg == int(cover):
        return "cover"
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(wintypes.HWND(fg), ctypes.byref(pid))
    return "own" if pid.value == os.getpid() else "other"


def own_to_top(own: int) -> bool:
    """`--front-for-order own`: TASlation's own window put at the top of the order of the windows (of its band), with
    no activation and no change of the window in front: the order a click on it gives. Only the tool's own window."""
    user32 = ctypes.WinDLL("user32")
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT]
    return bool(own) and bool(user32.SetWindowPos(own, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010))  # HWND_TOP


def order_depth(hwnd: int) -> int:
    """How many windows lie above *hwnd* in the order of the windows (-1: not found)."""
    user32 = ctypes.WinDLL("user32")
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetTopWindow.argtypes = [wintypes.HWND]
    user32.GetTopWindow.restype = wintypes.HWND
    h, n = user32.GetTopWindow(None), 0
    while h and n < 8192:
        if int(h) == int(hwnd):
            return n
        h, n = user32.GetWindow(h, 2), n + 1
    return -1


def is_topmost(hwnd: int) -> bool:
    """Whether the window *hwnd* is a topmost one (WS_EX_TOPMOST)."""
    user32 = ctypes.WinDLL("user32")
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    return bool(user32.GetWindowLongW(hwnd, -20) & 0x8)


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


def watch_priority(notes: Notes) -> None:
    """The server TASlation started computing the backlog's work at below-normal priority (`ollama_start.yield_server`,
    from a step's start) and set back (`unyield_server`, at the next request that is not the backlog's): each, when,
    and what came of it, for `priority_report`."""
    from taslation import ollama_start

    lower, back = ollama_start.yield_server, ollama_start.unyield_server

    def lowered(url: Any) -> bool:
        done = lower(url)
        with notes.lock:
            notes.priority.append({"t": now_ms(), "kind": "low", "done": bool(done)})
        return done

    def set_back() -> int:
        count = back()
        with notes.lock:
            notes.priority.append({"t": now_ms(), "kind": "back", "done": int(count)})
        return count

    ollama_start.yield_server, ollama_start.unyield_server = lowered, set_back


def priority_report(notes: Notes, rel: Callable[[Any], Any]) -> dict[str, Any]:
    """The backlog's requests computed low, and none of anyone else's: the spans in which the server was lowered (from
    a lowering to the next setting back), the backlog's requests begun in one, and every other request computed wholly
    in one (it was not set back before it went out: `ollama_start.before_request`)."""
    spans: list[tuple[float, float]] = []
    since: float | None = None
    for p in notes.priority:
        if p["kind"] == "low" and p["done"] and since is None:
            since = p["t"]
        elif p["kind"] == "back" and since is not None:
            spans.append((since, p["t"]))
            since = None
    if since is not None:
        spans.append((since, float("inf")))
    behind = [r for r in notes.requests if r.get("side") == "backlog"]
    others = [r for r in notes.requests if r.get("side") != "backlog"]
    low_others = [r for r in others if any(a <= r["t"] and (r["end_t"] or r["t"]) < b for a, b in spans)]
    return {"lowered": sum(1 for p in notes.priority if p["kind"] == "low" and p["done"]),
            "not_lowered": sum(1 for p in notes.priority if p["kind"] == "low" and not p["done"]),
            "set_back": sum(1 for p in notes.priority if p["kind"] == "back" and p["done"]),
            "processes_set_back": sum(p["done"] for p in notes.priority if p["kind"] == "back"),
            "low_ms": round(sum((min(b, now_ms()) - a) for a, b in spans)),
            "backlog_requests": len(behind),
            "backlog_requests_low": sum(1 for r in behind if any(a <= r["t"] < b for a, b in spans)),
            "other_requests_low": [{"t_s": rel(r["t"]), "side": r.get("side"), "job": r.get("job")}
                                   for r in low_others][:20]}


def install(notes: Notes, args: argparse.Namespace, guard: Any, viewer_infos: Callable[[], list[Any]]
            ) -> dict[str, Any]:
    """The guard (`demo_video`'s, keys and clicks refused), and the hooks that take the notes; what was replaced.
    The window's list of windows is *viewer_infos*() (the stand-in's window, and the book's own once its tab was
    moved out: `standin_tabs`)."""
    import demo_video

    import taslation.capture.wgc as wgc
    import taslation.capture.windows as windows
    from taslation import fingerprint, frames
    from taslation import linememo
    from taslation import pipeline as pipeline_mod
    from taslation.ocr import place
    from taslation.translate import ollama as ollama_mod
    from taslation.translate import plamo as plamo_mod
    from taslation.ui import app as app_mod
    from taslation.ui import live

    table = {name: (("never" if allow == "viewer" else allow), target)
             for name, (allow, target) in demo_video.GUARDED.items()}  # (TASlation sends no key, no click here)
    hidden_for = float(getattr(args, "no_viewer_s", 0) or 0)
    hidden_until = time.monotonic() + hidden_for  # (--no-viewer-s: no window to choose until then)

    def listed(include_own: bool = False) -> list[Any]:
        if hidden_for and time.monotonic() < hidden_until:
            return []
        if hidden_for and "offered_t" not in notes.no_viewer:
            notes.no_viewer["offered_t"] = now_ms()
        return [w for w in viewer_infos() if w]

    done = {"list_windows": demo_video.replace_everywhere(windows.list_windows, listed)}
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
    watch_priority(notes)

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
        elif kind in ("page_on_show", "backlog") or (kind == "page_stage" and data.get("reading")):
            notes.reading(kind, data)
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

    App._start_translate, App._job_translate, App._handle_event = started, worked, handled
    App._redisplay, App._capture, App._on_window_selected = drawn, captured, selected
    looks_soft, judge, viewer_sharp = App._looks_soft, frames.SharpSeen.judge, live.looks_sharp
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

    App._looks_soft, frames.SharpSeen.judge, live.looks_sharp = soft_look, judged, by_viewer
    drew_soft = App._drew_soft

    def learnt_soft(self: Any, soft: Any, sharp: Any) -> Any:  # the window learns that the viewer draws soft first
        try:
            rec = {"t": now_ms(), "soft": notes.code(notes.shown(soft)), "sharp": notes.code(notes.shown(sharp))}
            with notes.lock:
                notes.drew_soft.append(rec)
        except Exception as e:  # noqa: BLE001 - noted, never in the app's way
            notes.error("drew soft hook", type(e).__name__)
        return drew_soft(self, soft, sharp)

    App._drew_soft = learnt_soft
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
    for name in STEP_PARTS:  # ... and, in a look that took long, each call made in it (`step_call`)
        if hasattr(App, name):
            setattr(App, name, part_call(notes, name, getattr(App, name)))
    for module_name, name in STEP_FUNCS:
        holder: Any = importlib.import_module(f"taslation.{module_name}")
        *owner, attr = name.split(".")
        for part in owner:
            holder = getattr(holder, part, None)
        if holder is not None and hasattr(holder, attr):
            setattr(holder, attr, part_call(notes, name, getattr(holder, attr)))
    for name in STEP_CALLS:
        if hasattr(App, name):
            setattr(App, name, step_call(notes, name, getattr(App, name)))

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
    for cls in (plamo_mod.PlamoTranslator, ollama_mod.OllamaTranslator):  # a load or a warm-up of the model: its span
        if "warm_up" not in vars(cls):
            continue

        def load(self: Any, *a: Any, _original: Callable[..., Any] = vars(cls)["warm_up"], **k: Any) -> Any:
            notes.load_begin()
            try:
                return _original(self, *a, **k)
            finally:
                notes.load_end()

        cls.warm_up = load
    real_owner = live.foreground_owner

    def owner(hwnd: int, viewer: int, *a: Any, **k: Any) -> str:
        got = real_owner(hwnd, viewer, *a, **k)
        with notes.lock:
            notes.owners[got] += 1
        return "viewer" if args.front == "viewer" else got

    live.foreground_owner = owner
    from taslation.ui import order as order_mod

    if getattr(args, "order_partly", "as-built") != "as-built":  # (`ui.order`'s switch, for this run alone)
        order_mod.PARTLY_COVERED_TOO = args.order_partly == "on"
    if getattr(args, "front_for_order", "as-is") == "own":  # (the viewer kept under the window as with it in front)

        def order_owner(hwnd: Any, viewer: int, *a: Any, **k: Any) -> str:
            real_owner(hwnd, viewer, *a, **k)
            with notes.lock:  # (the cover's program in front until the window is put at the top: `cover_step`)
                c = notes.tool_cover
                covered = c is not None and c.get("gone_t") is None and "own_top_t" not in c
            return "other" if covered else "own"

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
                 narrow_rect: tuple[int, int, int, int], app_rect: tuple[int, int, int, int]):
        self.app, self.browser, self.guard, self.selection = app, browser, guard, selection
        self.notes, self.segments, self.args, self.out, self.standin_dir = notes, segments, args, out, standin_dir
        self.narrow_rect, self.app_rect = narrow_rect, app_rect
        self.resized_at, self.resizes_seen = float("-inf"), 0  # the stand-in's last draw at a new size, pictured after
        self.mono0, self.epoch0 = time.monotonic(), now_ms()
        self.cover: CoverWindow | None = None  # (`cover_step`)
        self.cover_from: float | None = None
        self.own_topped = False  # (`cover_step`: the window put at the top of the order)
        self.behind: Behind | None = None  # (--start-behind: `behind_step`)
        self.see: Any = None  # (the see-through watch: the run's end waits for a scene of its being acted, `step`)
        self.mon: Any = None  # (`standin_monitors.WindowRun`: the m and r scenarios' window steps and tours)
        self.tabs: Any = None  # (`standin_tabs.TabRun`: the tab scenarios' events and looks)
        self.client_size: tuple[int, int] | None = None  # (the stand-in's client area at its last draw: `pull`)
        self.behind_samples: list[dict[str, Any]] = []  # (the side panes' state where it changed: `behind_step`)
        self.behind_sampled = 0.0
        self.chooser_rows: list[dict[str, Any]] = []  # (--chooser: `chooser_step`)
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
        self.shots: list[dict[str, Any]] = []
        self.taken: set[str] = set()
        self.due: list[tuple[float, str]] = []
        self.watch: dict[tuple[str, int, bool], list[str]] = {}
        self.turns_in: Counter[str] = Counter()
        self.segment_of_go = {s.go: s.name for s in segments}
        self.current = ""
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
            self.start_dialog()
            self.book_dialog()
            self.chooser_step()
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
                self.behind_step()
                if self.mon is not None:
                    self.mon.tick()
                if self.tabs is not None:
                    self.tabs.tick()
        except Exception as e:  # noqa: BLE001 - said by its type and where it rose (no message: no text), and the run ends
            self.stop(f"{type(e).__name__} in the driver{_where(e)}")
        if not self.over:
            self.app.after(TICK_MS, self.tick)

    def start_dialog(self) -> None:
        """The start's dialog on the GPU's memory (`ui.dialogs.gpu_short`), when the window shows it: noted (its MB,
        what it would send to the processor, when) and answered through the window's own object as ``--gpu-short-answer``
        says (`GpuShortDialog.choose`: no input to the computer; "none" leaves it open); and the window's "Loading the
        models..." noted as it comes and goes."""
        app, notes = self.app, self.notes
        on = bool(getattr(app, "_models_loading", False))
        with notes.lock:
            if not notes.models_loading or notes.models_loading[-1][1] != on:
                notes.models_loading.append([now_ms(), on])
        dialog = getattr(app, "_gpu_dialog", None)
        if dialog is None or getattr(dialog, "answered", ""):
            return
        answer = str(getattr(self.args, "gpu_short_answer", "processor") or "processor")
        if answer == "release" and getattr(dialog, "release_btn", None) is None:
            answer = "processor"  # (no model of TASlation's to release: as by default)
        with notes.lock:
            if not notes.gpu_dialogs or notes.gpu_dialogs[-1].get("dialog") != id(dialog):
                named = [{"name": m.name, "mib": m.mib, "ours": m.ours} for m in getattr(dialog, "loaded", ()) or ()]
                notes.gpu_dialogs.append({"t": now_ms(), "dialog": id(dialog), "short_mb": getattr(dialog, "shown_mb", None),
                                          "parts": list(getattr(dialog, "parts", ()) or ()), "answer": answer,
                                          "named": named})
        if answer != "none":
            dialog.choose(answer)

    def book_dialog(self) -> None:
        """--book-asked: the start dialog that asks the book's name (`ui.dialogs.start.StartDialog`: the window began
        with a name that names no book), noted as it comes (when, whether Tk shows it, its place on a monitor and
        whether it is topmost, read from its handle; which of TASlation's windows had the foreground then) and
        answered BOOK_ANSWER_S later through the dialog's own object - its Series field set to BOOK, its OK (no input
        to the computer). --no-viewer-s: when the window chose the stand-in."""
        app, notes = self.app, self.notes
        if getattr(self.args, "no_viewer_s", 0) and "chosen_t" not in notes.no_viewer \
                and getattr(app, "selected", None) is not None:
            notes.no_viewer["chosen_t"] = now_ms()
        if not getattr(self.args, "book_asked", False):
            return
        from taslation.ui.dialogs.start import StartDialog

        dialog = getattr(app, "_start_dialog", None)
        if not isinstance(dialog, StartDialog) or dialog.answered:
            return
        row = notes.book_dialogs[-1] if notes.book_dialogs and notes.book_dialogs[-1]["dialog"] == id(dialog) else None
        if row is None:
            row = {"t": now_ms(), "dialog": id(dialog), "answered_t": None}
            notes.book_dialogs.append(row)
        try:
            viewable = bool(dialog.winfo_viewable())
        except Exception:  # noqa: BLE001 - (gone meanwhile)
            return
        if viewable and "shown_t" not in row:
            from taslation.capture import seethrough as window

            hwnd = int(dialog.wm_frame(), 16)
            facts = window.window_facts(hwnd) or {}
            ex = int(ctypes.windll.user32.GetWindowLongW(hwnd, -20)) & 0xFFFFFFFF
            front = int(ctypes.windll.user32.GetForegroundWindow() or 0)
            row.update({"shown_t": now_ms(), "on_monitor": facts.get("on_monitor"), "tool": facts.get("tool"),
                        "topmost": bool(ex & 0x8), "front_is_dialog": front == hwnd,
                        "front_is_standin": front == self.browser.hwnd})
        if "shown_t" in row and now_ms() - row["shown_t"] >= BOOK_ANSWER_S * 1000:
            dialog.fields.set_parts(BOOK, "")
            dialog._answer("ok")
            row["answered_t"] = now_ms()
            row["answered"] = bool(dialog.answered)

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
            self.cover = CoverWindow(self.browser.hwnd, getattr(self.args, "cover_part", 1.0),
                                     getattr(self.args, "cover_style", COVER_EX))
            with self.notes.lock:
                self.notes.tool_cover = {"segment": segment, "shown_t": self.cover.shown_t, "gone_t": None,
                                         "made": bool(self.cover.hwnd), "part": self.cover.part,
                                         "style": "noactivate" if self.cover.no_activate_style else "plain"}
        elif self.cover is not None and since >= at + lasts:
            gone = self.cover.close()
            with self.notes.lock:
                self.notes.tool_cover["gone_t"] = gone
        elif self.cover is not None and self.cover.hwnd:
            if (getattr(self.args, "front_for_order", "as-is") == "own" and not self.own_topped
                    and since >= at + getattr(self.args, "cover_front_s", COVER_FRONT_S)):
                self.own_topped = True
                own = self.app._own_hwnd()
                before = (order_depth(own), order_depth(self.browser.hwnd))
                done = own_to_top(own)
                with self.notes.lock:
                    self.notes.tool_cover["own_top_t"] = now_ms() if done else None
                    self.notes.tool_cover["depths"] = {"before": before, "after": (order_depth(own),
                                                                                   order_depth(self.browser.hwnd))}
            over = cover_over(self.cover.hwnd, self.browser.hwnd)
            with self.notes.lock:
                c = self.notes.tool_cover
                c["looks"] = c.get("looks", 0) + 1
                c["over_looks"] = c.get("over_looks", 0) + (1 if over else 0)
                c["standin_topmost_looks"] = c.get("standin_topmost_looks", 0) + (1 if is_topmost(self.browser.hwnd) else 0)
                state = getattr(self.app, "_order_state", None)
                said = getattr(state, "last", None)
                lasts = c.setdefault("order_said", {})  # (what `capture.keep_viewer_under` said last, at each look)
                lasts[str(said)] = lasts.get(str(said), 0) + 1
                from taslation.ui import order as order_mod

                busy = order_mod._busy_with_the_viewer(self.app)
                c["busy_looks"] = c.get("busy_looks", 0) + (1 if busy else 0)  # (raised for a look, or resizing)
                c["order_spell"] = {"front": getattr(state, "front", None), "placed": getattr(state, "placed", None),
                                    "spells": getattr(state, "spells", None)}
                c["own_over_standin_looks"] = c.get("own_over_standin_looks", 0) + (
                    1 if cover_over(self.app._own_hwnd(), self.browser.hwnd) else 0)
                if not over and c.get("under_t") is None:
                    c["under_t"] = now_ms()  # (the stand-in first found over the cover: put under the window)

    def behind_step(self) -> None:
        """--start-behind: the stand-in back in sight --behind-s after the window chose it (`Behind.end`); the side
        panes' state (`pane_state`) every PANE_SAMPLE_S, kept where it changed."""
        behind = self.behind
        if behind is None:
            return
        chosen = getattr(getattr(self.app, "selected", None), "hwnd", None) == self.browser.hwnd
        if chosen and behind.facts.get("chosen_t") is None:
            behind.facts["chosen_t"] = now_ms()
        since = behind.facts.get("chosen_t")
        if since is not None and behind.facts.get("ended_t") is None \
                and now_ms() - since >= float(getattr(self.args, "behind_s", BEHIND_S)) * 1000:
            behind.end()
        now = time.monotonic()
        if now - self.behind_sampled < PANE_SAMPLE_S:
            return
        self.behind_sampled = now
        state = pane_state(self.app, self.browser.hwnd, behind.cover_hwnd)
        if not self.behind_samples or {k: v for k, v in self.behind_samples[-1].items() if k != "t"} != state:
            self.behind_samples.append({"t": now_ms(), **state})

    def chooser_step(self) -> None:
        """--chooser: the viewer chooser (`ui.see_menu.ViewerDialog`), when the window shows it, noted (when, the
        windows listed, which was preselected, whether OK was greyed) and answered through its own object: the
        stand-in's entry chosen and OK (no input to the computer)."""
        if not getattr(self.args, "chooser", False):
            return
        dialog = getattr(self.app, "_see_chooser", None)
        if dialog is None:
            return
        row = self.chooser_rows[-1] if self.chooser_rows and self.chooser_rows[-1]["dialog"] == id(dialog) else None
        if row is None:
            index = dialog.box.current()
            row = {"t": now_ms(), "dialog": id(dialog), "listed": len(dialog.windows),
                   "preselected_standin": 0 <= index < len(dialog.windows)
                   and dialog.windows[index].hwnd == self.browser.hwnd,
                   "ok_greyed": dialog.ok_button.instate(["disabled"]), "answered_t": None}
            self.chooser_rows.append(row)
        if row["answered_t"] is not None:
            return
        at = next((i for i, w in enumerate(dialog.windows) if w.hwnd == self.browser.hwnd), None)
        if at is None:
            return  # (not listed yet: looked at again at the next tick)
        if row.get("activated_t") is None:  # (first the dialog given the foreground, as a person's click on it does)
            row["activated_t"] = now_ms()
            row["activated"] = self.chooser_activate(dialog)
            return
        if now_ms() - row["activated_t"] < CHOOSER_ANSWER_MS:
            return
        dialog.box.current(at)
        dialog._picked()
        dialog.ok()
        row["answered_t"] = now_ms()

    def chooser_activate(self, dialog: Any) -> bool:
        """The viewer chooser given the foreground before it is answered, as the person's click on it gives it - only
        while the stand-in or the tool's own cover (`Behind`) is in front, never taken from another window. Whether it
        came to the front."""
        user32 = ctypes.WinDLL("user32")
        fg = int(user32.GetForegroundWindow() or 0)
        cover = self.behind.cover_hwnd if self.behind is not None else 0
        if fg not in {int(self.browser.hwnd), int(cover or 0)}:
            return False
        try:
            dialog.focus_force()
            dialog.update_idletasks()
            top = int(dialog.wm_frame(), 16)
        except Exception:  # noqa: BLE001 - (gone meanwhile)
            return False
        return int(user32.GetForegroundWindow() or 0) in {top, int(dialog.winfo_id())}

    def behind_report(self) -> dict[str, Any] | None:
        """--start-behind / --chooser: what was done (times from the run's start) and the side panes' state as it
        changed."""
        if self.behind is None and not self.chooser_rows:
            return None
        t0 = self.epoch0

        def rel(t: Any) -> Any:
            return None if t is None else round(float(t) - t0)

        facts = {k: (rel(v) if k.endswith("_t") else v) for k, v in (self.behind.facts if self.behind else {}).items()}
        samples = [{**s, "t": rel(s["t"])} for s in self.behind_samples]

        def on_screen(s: dict[str, Any]) -> bool:
            return all(isinstance(s.get(side), dict) and s[side].get("shown") and s[side].get("visible")
                       and s[side].get("above_standin") for side in ("left", "right"))

        ended = facts.get("ended_t")
        back = next((s["t"] for s in samples if ended is not None and s["t"] >= ended and on_screen(s)), None)
        after = [s for s in samples if ended is not None and s["t"] >= (back if back is not None else ended)]
        return {"behind": facts, "chooser": [{k: (rel(v) if k.endswith("_t") or k == "t" else v)
                                              for k, v in r.items() if k != "dialog"} for r in self.chooser_rows],
                # (in sight again -> both panes on the screen, to within PANE_SAMPLE_S; and whether they stayed so)
                "panes_back_ms": None if back is None else back - ended,
                "panes_stayed": bool(after) and back is not None and all(on_screen(s) for s in after),
                "panes": samples[-40:], "pane_samples": len(samples)}

    def stop(self, why: str) -> None:
        if self.over:
            return
        self.over = True
        if self.mon is not None:  # (a region editor or a tour left open closed, the hand-overs put back)
            try:
                self.mon.close()
            except Exception as e:  # noqa: BLE001 - said by its type
                self.notes.error("window steps' close", type(e).__name__)
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
                    if self.mon is not None:  # (the page's place at this frame size: `standin_monitors.region_fit`)
                        from taslation.capture import windows as capture_windows

                        _cx, _cy, cw, ch = capture_windows._client_box(self.browser.hwnd)
                        self.mon.sampler.page_rects[(cw, ch, int(e["page"]), e.get("spread") == "1")] = self.page_rect
                with contextlib.suppress(KeyError, ValueError), self.notes.lock:  # (`watch_frames`)
                    self.notes.drawn_last = {"t": e["recv"], "page": int(e["page"]), "spread": e["spread"] == "1",
                                             "state": e["state"], "capture_n": self.notes.capture_n}
            elif ev == "black" and e.get("on") == "1":
                with self.notes.lock:
                    self.notes.drawn_last = None
            if self.tabs is not None and ev == "tab":  # (the stand-in's other tab: `standin_tabs.TabRun`)
                self.tabs.event(e, self.current)
            elif self.tabs is not None and ev == "draw":
                self.tabs.drawn(e)
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

    # the scenarios
    def idle(self) -> bool:
        app = self.app
        f = getattr(app, "_following", None)
        return bool(app.ready and not app.busy and app._queued is None
                    and (f is None or f.op is None) and getattr(app, "_early", None) is None)

    def step(self) -> None:
        now = time.monotonic()
        self.idle_since = (self.idle_since or now) if self.idle() else None
        rested = self.idle_since is not None and now - self.idle_since >= IDLE_S
        waited = now - self.phase_at
        if self.wait_done is not None:
            self.waits(now)
        if self.index >= len(self.segments):
            if self.phase != "end":
                self.phase, self.phase_at = "end", now
                return
            acting = self.see is not None and self.see.acting()  # (a scene of the watch's - editing's, say - not cut)
            if (self.ended and rested and self.backlog_done() and not acting) or waited > self.args.timeout:
                if waited > self.args.timeout:
                    self.released["end"] = {"timed_out": True}
                self.finish()
            return
        seg = self.segments[self.index]
        if self.phase == "prepare":
            if seg.name in WINDOW_STEPS and self.mon is not None and waited <= self.args.timeout \
                    and not self.mon.may_begin(rested and (self.index > 0 or self.first_page_done())):
                return  # (a window step waits for the window at rest and the watch's pointer scene over)
            self.before(seg)
            self.phase, self.phase_at = "settle", now
            return
        if self.phase == "settle":
            if getattr(self.args, "no_viewer_s", 0) and getattr(self.app, "selected", None) is None:
                return  # (--no-viewer-s: nothing is released before the window has found the stand-in)
            behind = self.behind
            if behind is not None and (behind.facts.get("ended_t") is None
                                       or now_ms() - behind.facts["ended_t"] < IDLE_S * 1000):
                return  # (--start-behind: nothing is released before the stand-in is back in sight)
            ready_go = self.waiting_go >= seg.go
            app = self.app
            if seg.name == "c":
                go = ready_go and getattr(app, "selected", None) is not None
            elif seg.name == "tab0":  # (a start with another tab on show: no page read before the book's tab is back)
                go = ready_go and rested
            elif seg.name in NARROW:
                go = ready_go and rested and self.resized()
            elif seg.name in WINDOW_STEPS and self.mon is not None:
                go = ready_go and self.mon.ready(seg.name, rested)
            elif seg.name in K_PACES:  # (each pace on its own: the backlog of the one before done)
                first = seg is next(x for x in self.segments if x.name in K_PACES)
                go = (ready_go and rested and self.backlog_done() and (self.index > 0 or self.first_page_done())
                      and not (first and self.args.k_narrow and not self.resized()))
            else:
                go = ready_go and rested and (self.index > 0 or self.first_page_done())
            timed_out = ready_go and waited > self.args.timeout
            if timed_out and not app.ready:
                self.stop("the window was not ready within --timeout")
                return
            if go or timed_out:
                self.released[seg.name] = {"waited_s": round(waited, 1), "timed_out": bool(timed_out and not go),
                                           "t": now_ms()}
                self.release(go=seg.go)
                self.phase, self.phase_at = "running", now
            return
        if self.phase == "running" and self.tabs is not None and self.tabs.second_facts.get("failed"):
            self.stop("the book's window of its own did not come")  # (its steps after the "z" would never run)
            return
        if self.phase == "running" and (self.waiting_go > seg.go or self.ended):
            self.index += 1
            self.phase, self.phase_at = "prepare", now

    def release(self, go: int | None = None, hold: int | None = None, sharp: int | None = None) -> None:
        """The control file written: the stand-in's script released to *go* (``gN``); with --wait-done, its holds to
        *hold* (``hN``) and its turns kept soft to *sharp* (``kN``) as well; a value not given as it was. Without the
        option the file is what it always was (the go alone)."""
        for key, value in (("go", go), ("hold", hold), ("sharp", sharp)):
            if value is not None:
                self.control[key] = int(value)
        out = self.control.get("out")  # (the book's own window told to go on: kept in every write from then on)
        if self.wait_done is None:
            sv.write_control(self.standin_dir, self.control["go"], out=out)
        else:
            sv.write_control(self.standin_dir, self.control["go"], hold=self.control["hold"],
                             sharp=self.control["sharp"], out=out)

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

    def before(self, seg: Segment) -> None:
        """The stand-in made narrow for the first of f2 and f3 asked, and for scenario k with --k-narrow (its own
        window's place: TASlation never moves nor resizes it); the step of an m or r scenario (`standin_monitors`)."""
        if seg.name in WINDOW_STEPS and self.mon is not None:
            self.resize_from = len(self.events)
            self.notes.act(seg.name, SCENARIOS[seg.name][0])
            self.mon.begin(seg.name)
        elif seg.name in NARROW and seg is next(x for x in self.segments if x.name in NARROW):
            self.resize_from = len(self.events)  # (f3 after f2: the stand-in is narrow already, resized since)
            hwnd = self.browser.hwnd
            if hwnd and self.guard.is_viewer(hwnd):
                self.notes.act(seg.name, "narrow window")
                place_own(hwnd, self.narrow_rect)
        elif seg.name in K_PACES and self.args.k_narrow and seg is next(x for x in self.segments if x.name in K_PACES):
            self.resize_from = len(self.events)
            hwnd = self.browser.hwnd
            if hwnd and self.guard.is_viewer(hwnd):
                place_own(hwnd, self.narrow_rect)

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
    is now, the page panel found within it, the part of the picture the page view draws (its crop) and the picture's
    size, the viewer's window size."""
    from taslation.capture import window_rect

    out: dict[str, Any] = {}
    for name, get in (("margins", lambda: app.settings.margins), ("hand", lambda: app._hand_area),
                      ("inner", lambda: app._inner_margins()), ("manual", lambda: app._manual_area),
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


def stream_token() -> int | None:
    """The number of the run of a unit's lines sent as they were read (`streaming.current_token`) that the calling
    thread asks for, or None (a request of a page job's own, or a program without the stream)."""
    try:
        from taslation import streaming
    except ImportError:
        return None
    return streaming.current_token()


def streamed_lines(stream_log: list[dict[str, Any]], requests: list[dict[str, Any]],
                   jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """The units whose lines were sent to the translator as they were read (`Pipeline.stream_log`, one entry a unit):
    lines sent early, lines that stood and lines taken back (the first line of a unit among them), the requests whose
    answers were thrown away so (each counted once, by the stream's numbers - not in `wasted_requests`, whose jobs
    are dropped or soft), the time a taken-back lettering stayed on show, and the two ends a finished page must meet:
    no answer of a taken-back run in the page's final lines (`final_from_taken_back`) and no early lettering still
    on show when the page's result came (`early_left_at_result`)."""
    back_tokens = {t for e in stream_log for t in e.get("tokens_taken_back") or ()}
    by_id = {j["id"]: j for j in jobs}
    back = [r for r in requests if r.get("stream") is not None and r["stream"] in back_tokens]
    finished = [e for e in stream_log if e.get("outcome") == "done"]  # (`LineStream.close`: the unit was asked)
    withdrawn = [v for j in jobs for v in j.get("withdrawn_ms") or ()]
    first_early = [ms(j["first_early_t"], j["t"]) for j in jobs if j.get("first_early_t") and j["started"]]

    def total(key: str, of: list[dict[str, Any]] = stream_log) -> int:
        return sum(int(e.get(key) or 0) for e in of)

    return {"units": len(stream_log), "outcomes": dict(Counter(e.get("outcome") for e in stream_log)),
            "lines_sent_early": total("lines_sent_early"), "lines_stood": total("lines_stood"),
            "lines_taken_back": total("lines_taken_back"), "runs_taken_back": total("runs_taken_back"),
            "units_first_line_taken_back": sum(1 for e in stream_log if e.get("first_taken_back")),
            "units_any_taken_back": sum(1 for e in stream_log if e.get("runs_taken_back")),
            "why_taken_back": dict(Counter(e["why_taken_back"] for e in stream_log if e.get("why_taken_back"))),
            "requests_taken_back": len(back),
            "requests_taken_back_ms": dist([ms(r["end_t"], r["t"]) for r in back if r["end_t"] is not None]),
            "requests_stream": total("requests"),
            "early_lettered": total("early_lettered"), "early_withdrawn": total("early_withdrawn"),
            "withdrawn_on_show_ms": dist(withdrawn),
            "first_early_lettering_ms": dist(first_early),
            # the lines a classical candidate not read yet held back (`streaming.HOLD_FOR_CLASSICAL`), and for how long
            # after the earlier rule would have known them
            "lines_held": total("lines_held"),
            "held_ms": dist([v for e in stream_log for v in e.get("held_ms") or ()]),
            # what foreseeing the unit's order once read cost a unit (`streaming.ORDER_AS_READ`, on the reading's thread)
            "order_ms": dist([e["order_ms"] for e in stream_log if e.get("order_ms") is not None]),
            "final_from_taken_back": total("final_from_taken_back", finished),
            "early_left_at_close": total("early_left", finished),
            "early_left_at_result": sum(int(j.get("early_left_at_result") or 0) for j in by_id.values()
                                        if j.get("result_t") is not None),
            # each unit that took a run back: its counts, why, and the page jobs its taken-back requests were for
            "units_taken_back": [
                {**{k: e.get(k) for k in UNIT_KEYS},
                 "jobs": sorted({r.get("job") for r in requests if r.get("stream") in set(e.get("tokens_taken_back")
                                                                                          or ())} - {None})}
                for e in stream_log if e.get("runs_taken_back")]}


UNIT_KEYS = ("unit", "outcome", "runs_sent_early", "lines_sent_early", "runs_stood", "lines_stood", "runs_taken_back",
             "lines_taken_back", "requests_taken_back", "first_taken_back", "why_taken_back", "first_answer_ms",
             "reconciled_ms", "taken_back_as")


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
    it, and its finished page. Its rest ends at the next turn or where the driver changed the stand-in before it (its
    size: `Notes.acts`), whichever comes first: what the window showed then is the page at rest (`at_rest`), not what
    the next scenario made of it."""
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
        seen = next((c["t"] for c in notes.captures if c["t"] >= lo and (c["page"], c["spread"]) == scr
                     and c["state"] in ("soft", "sharp")), None)
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
            # the same from the turn (the stand-in's first draw of it), and what lies between the turn and the
            # finishing job's start: the window's first capture of the screen (soft or sharp), its first capture of
            # the sharp picture, from there to the job's start (the window's decision) and the job's wait for its
            # worker (`timing_summary`)
            "first_request_from_turn_ms": ms(first_request, lo), "finished_from_turn_ms": ms(finished, lo),
            "captured_from_turn_ms": ms(seen, lo),
            "job_after_sharp_capture_ms": ms(last["t"], seen_sharp) if last is not None else None,
            "job_queued_ms": ms(last.get("work_t"), last["t"]) if last is not None else None,
            "job_from_turn_ms": ms(last["t"], lo) if last is not None else None,
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


# the timing figures: per rested turn to a page the cache did not hold whole, from the turn and from the sharp
# picture's appearance, and the parts of the way from the turn to the finishing job's start
TIMING_KEYS = ("lettered_from_turn_ms", "first_lettered_ms", "finished_from_turn_ms", "finished_ms",
               "first_request_from_turn_ms", "first_request_ms", "job_from_turn_ms", "soft_to_sharp_ms",
               "captured_from_turn_ms", "captured_sharp_ms", "job_after_sharp_capture_ms", "job_queued_ms")
TIMING_LEFT_OUT = ("start", "c")  # the start's page is no turn; c's turns come while the model loads


def timing_summary(rows: list[dict[str, Any]], soft_first: bool, drew_soft: list[dict[str, Any]],
                   said: list[dict[str, str]], rel: Callable[[Any], Any]) -> dict[str, Any]:
    """The timing figures of a run (`--soft-first`): the turns the reader rested on (`REST_MS`) but the start's and
    c's, to a page the cache did not hold whole, on screens of one page and of two, and per scenario: the first
    lettered bubble and the finished page from the turn (the stand-in's first draw of it) and from its sharp picture's
    draw, the first request, and what lay between the turn and the finishing job's start (`turn_rows`). In sharp mode
    the turn is the sharp picture's draw, and the window must never have learnt that this viewer draws a page soft
    first: the stand-in's draws by state (none soft) and the times the window learnt it (`App._drew_soft`: none)
    say whether it did."""
    rested = [r for r in rows if (r["rest_ms"] or 0) >= REST_MS and r["segment"] not in TIMING_LEFT_OUT]
    fresh = [r for r in rested if not r["cached"]]

    def block(mine: list[dict[str, Any]]) -> dict[str, Any]:
        return {"turns": len(mine), **{k: tail([r[k] for r in mine]) for k in TIMING_KEYS}}

    draws = Counter(s.get("state") for s in said if s.get("ev") == "draw")
    ready = next((s for s in said if s.get("ev") == "ready"), {})
    return {
        "soft_first": "on" if soft_first else "off",
        "standin_said_soft_first": ready.get("soft_first"),
        "standin_draws": dict(draws),
        "window_learnt_soft_first": len(drew_soft),
        "learnt": [{"t_s": rel(d["t"]), "soft": d["soft"], "sharp": d["sharp"]} for d in drew_soft[:10]],
        "cached_turns_left_out": len(rested) - len(fresh),
        "one_page": block([r for r in fresh if not r["spread"]]),
        "two_pages": block([r for r in fresh if r["spread"]]),
        "by_segment": {s: block([r for r in fresh if r["segment"] == s])
                       for s in dict.fromkeys(r["segment"] for r in fresh)},
    }


# a page job's stages as `job_stages` tells them, in the order of the job
STAGE_KEYS = ("queued", "to_process", "fingerprint", "detect", "ocr", "order", "before_first_request", "gate_wait",
              "load_wait", "first_request", "first_prompt", "first_answer", "requests", "prompt", "answer",
              "between_requests", "between_units", "between_beside_wait", "between_store", "between_order",
              "between_ocr", "between_other", "requests_idle", "requests_idle_max", "after_requests", "tighten",
              "review", "large", "drafts_wait",
              "translate", "store",
              "render", "process", "result_to_window", "settle", "save", "keep_shown", "drafts_lettering",
              "first_answer_to_lettered", "ocr_beside", "ocr_cpu", "ocr_gpu", "slants", "slants_before_first_request")


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
    gap_parts: Counter[str] = Counter()  # (the worker's stages within the time between two units' translations)
    for k, (_lab, a, b, _th, _x) in enumerate(trs):
        inside = [r for r in reqs if a <= r["t"] and r["end_t"] is not None and r["end_t"] <= b]
        if inside:
            gaps += (max(r["end_t"] for r in inside) - inside[0]["t"]
                     - sum(r["end_t"] - r["t"] for r in inside))
        if k:
            g0 = trs[k - 1][2]
            units_gap += a - g0
            for lab, s0, s1, th, _x in spans:
                if th == worker and g0 <= s0 and s1 <= a and lab not in ("process",):
                    gap_parts[lab] += s1 - s0
    idle: list[float] = []  # (the model idle between the job's requests: from the end of those before to the next)
    reach: float | None = None
    for r in reqs:
        if reach is not None and r["t"] > reach:
            idle.append(r["t"] - reach)
        if r["end_t"] is not None:
            reach = r["end_t"] if reach is None else max(reach, r["end_t"])
    out: dict[str, Any] = {
        "queued": ms(job.get("work_t"), job["t"]), "to_process": ms(p0, job.get("work_t")),
        "requests_idle": round(sum(idle)) if reqs else None, "requests_idle_max": round(max(idle)) if idle else None,
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
        # what of it the worker spent waiting for the next unit read beside, in the stores, the order and the rooms,
        # and in nothing the stages tell
        "between_beside_wait": round(gap_parts["beside_wait"]) if len(trs) > 1 else None,
        "between_store": round(gap_parts["store"]) if len(trs) > 1 else None,
        "between_order": round(gap_parts["order"]) if len(trs) > 1 else None,
        "between_other": (round(units_gap - sum(v for lab, v in gap_parts.items() if lab in
                                                ("beside_wait", "store", "order", "ocr")))
                          if len(trs) > 1 else None),
        "between_ocr": round(gap_parts["ocr"]) if len(trs) > 1 else None,
        "after_requests": ms(t1, max(ends)) if ends and t1 is not None else None,
        "tighten": total("tighten", hi=p1), "review": total("review", hi=p1), "large": total("large", hi=p1),
        "drafts_wait": total("drafts_wait", hi=p1),
        "translate": total("translate", hi=p1), "store": total("store", hi=p1), "render": total("render", hi=p1),
        "process": ms(p1, p0), "result_to_window": ms(job.get("result_t"), p1),
        "settle": total("settle"), "save": total("save"), "keep_shown": total("keep_shown"),
        "drafts_lettering": total("letter", mine=False),
        "first_answer_to_lettered": ms(lettered_t, first["end_t"]) if first is not None and lettered_t else None,
        "ocr_beside": total("ocr", mine=False),
        # the slants measured by the worker (`Pipeline._measure_slants`), and of them those before the first request
        "slants": total("slants", hi=p1),
        "slants_before_first_request": total("slants", hi=first["t"]) if first is not None else None,
        "ocr_cpu": round(sum(b - a for lab, a, b, _th, x in spans if lab == "ocr_read" and x == "cpu")),
        "ocr_gpu": round(sum(b - a for lab, a, b, _th, x in spans if lab == "ocr_read" and x != "cpu")),
    }
    if os.environ.get("TASLATION_STAGE_TIMELINE"):  # (a developer's look: the job's spans and requests, ms from its start)
        out["timeline"] = {
            "spans": [(lab, round(a - p0), round(b - a), "worker" if th == worker else str(th)[-6:], x)
                      for lab, a, b, th, x in spans if lab != "process" and a >= p0 - 1 and b <= p1 + 1],
            "requests": [(round(r["t"] - p0), round((r["end_t"] or r["t"]) - r["t"])) for r in reqs]}
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
    one of the page's jobs before had asked); the jobs of the window's first turns (scenario c)."""
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
        # the job (a spread's next unit, a request asked again), or outside the page jobs (the backlog's)
        "cuts": [{"t_s": rel(c["t"]), "job": c["job"], "before": c["before"], "after": c["after"],
                  "at": ("backlog" if c["job"] is None else "first request" if not any(
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

    soft_first = getattr(args, "soft_first", "on") == "on"
    names, x_out = soft_first_scenarios(wanted(args.scenario), args.scenario, soft_first)
    names = tab_order(names)
    start_tab = {"plain": 0, "japanese": 1}.get(getattr(args, "standin_start_tab", None) or "")
    if (start_tab is not None or any(n in TAB_SCENARIOS for n in names)) and args.standin_profile:
        raise SystemExit("the stand-in's tabs are a stand-in's without a profile (no --standin-profile)")
    count = pages_needed(names, args.k_turns)
    report: dict[str, Any] = {"scenarios": names, "seed": args.seed, "front": args.front, "scale": args.scale,
                              "front_for_order": getattr(args, "front_for_order", "as-is"),
                              "order_partly": getattr(args, "order_partly", "as-built"),
                              "soft_first": "on" if soft_first else "off"}
    if x_out:
        report["x_left_out"] = x_out
    given = [Path(p) for p in (getattr(args, "pages", "") or "").split(",") if p.strip()]
    for path in given:
        if not path.is_file():
            raise SystemExit(f"--pages: no such picture: {path.name}")
    pictures: list[Any] | None = (None if args.synthetic or given else
                                  dataset_pages(args.series, args.first, count))
    report["pages"] = "dataset" if pictures else "given" if given else "synthetic"
    if given:
        pictures = [(given[k % len(given)], "") for k in range(count)]
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
              "soft": args.k_soft == "on" and soft_first, "narrow": bool(args.k_narrow),
              "backlog": args.k_backlog == "on",
              "read_ms": args.k_read_ms, "stay_ms": args.k_stay_ms}
    profile_options = sv.parse_options(args.standin_option)
    if profile_options and not args.standin_profile:
        raise SystemExit("--standin-option is for a stand-in with a profile (--standin-profile)")
    cover = bool(args.standin_profile) and profile_options.get("cover", "1") != "0"
    if "s" in names and args.standin_profile:
        raise SystemExit("scenario s slides the stand-in's page without a profile (no --standin-profile)")
    held_ms = int(getattr(args, "standin_bars_held", 0) or 0)
    if held_ms and not args.standin_profile:
        raise SystemExit("--standin-bars-held is for a stand-in with a profile (--standin-profile)")
    segments, steps = build_plan(names, count, cancel_first, args.cancel_soft_ms, args.wait_done, k_plan, cover,
                                 lead=[f"v{held_ms}"] if held_ms else None)
    if args.standin_profile:
        report["standin_profile"] = {"name": args.standin_profile, "options": profile_options}
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
    monitors = Monitors()
    standin_rect, app_rect = monitors.places()
    on = int(getattr(args, "standin_monitor", 1) or 1)
    if not 1 <= on <= max(1, len(monitors.areas)):
        raise SystemExit(f"--standin-monitor is 1 to {max(1, len(monitors.areas))} on this computer")
    (l_, t_, r_, b_), _p = monitors.areas[on - 1] if monitors.areas else ((0, 0, 1920, 1040), True)
    w_, h_ = STANDIN_SIZE
    if args.standin_size:
        w_, h_ = (int(v) for v in args.standin_size.lower().split("x"))
    if on != 1 or args.standin_size:
        standin_rect = (l_, t_, min(w_, r_ - l_), min(h_, b_ - t_))
    if getattr(args, "standin_maximised", False) and on == 1:
        raise SystemExit("--standin-maximised: not on the primary monitor (a run never covers it with a maximised "
                         "window); give --standin-monitor 2")
    report["standin_rect"] = list(standin_rect)
    report["standin_monitor"] = on
    report["see_through"] = True  # (the program's one mode since 2.0.0; the key is kept for the reports' readers)
    report["standin_full_screen"] = bool(args.standin_full_screen)
    narrow_rect = (standin_rect[0], standin_rect[1], NARROW_SIZE[0], NARROW_SIZE[1])
    token = "t" + secrets.token_hex(5)
    page = sv.page_url(token, steps, standin_dir, seed=args.seed, soft_first=soft_first, slider=args.standin_slider,
                       profile=args.standin_profile, options=profile_options, start_tab=start_tab)

    if start_tab is not None:
        report["standin_start_tab"] = args.standin_start_tab
    report["standin_draws_covered"] = bool(args.standin_draws_covered)
    browser = sv.StandinBrowser(found[1], page, standin_dir / "profile", standin_rect, token, args.scale,
                                draws_covered=args.standin_draws_covered, full_screen=args.standin_full_screen)
    closed: dict[str, Any] = {}
    try:
        hwnd = browser.wait_window()
        ready = browser.wait_event("ready", 30)
        since = len(browser.said())
        if not args.standin_full_screen:  # (the full screen is the browser's own place)
            place_own(hwnd, standin_rect, top=True)
        if getattr(args, "standin_maximised", False):
            import standin_monitors

            screens = standin_monitors.Screens()
            report["standin_maximised"] = standin_monitors.WindowSteps(
                hwnd, screens, lambda: set(browser.tree), sv.lock_foreground).maximise()
        ready = placed_view(browser, ready, since)
        browser._front_look("placed")  # (the stand-in shown and placed: it has not taken the foreground meanwhile)
        if any(s.op == "z" for s in steps):  # (the book's own window for the "z", opened now and held minimised)
            import standin_tabs

            x_, y_, sw_, sh_ = standin_rect
            gap = standin_tabs.SPACING_PX  # (within the first one's place: on its monitor as it is)
            args._held_rect = (x_ + gap, y_ + gap, sw_ - gap, sh_ - gap)
            held_url = sv.page_url(token, steps, standin_dir, seed=args.seed, soft_first=soft_first,
                                   slider=args.standin_slider, held=True)
            browser.open_held(found[1], held_url, args._held_rect)
            report["standin_held"] = dict(browser.more_facts)
        if start_tab is not None:  # (the other tab shown now, before the window starts: found by its title before)
            report["standin_start_tab_shown"] = start_other_tab(browser, standin_dir)
        report["browser_start"] = dict(browser.start_facts)
        report["run"] = run_app(args, report, browser, hwnd, ready, segments, out, standin_dir, url, app_rect,
                                narrow_rect, mode)
    except Exception as e:  # noqa: BLE001 - said (its type and where, no value), then everything is closed
        traceback.print_exc()
        report["run"] = {"failed": f"{type(e).__name__} in the driver{_where(e)}"}
        report.setdefault("browser_start", dict(browser.start_facts))  # (a window that came not even started again)
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


def start_other_tab(browser: sv.StandinBrowser, standin_dir: Path, seconds: float = 10.0) -> bool:
    """--standin-start-tab: the stand-in's other tab shown (its control file's ``tab``), and waited for until its
    window's title is the other tab's (no longer holding the token); whether it came."""
    since = len(browser.said())
    sv.write_control(standin_dir, 0, tab=1)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        shown = any(s.get("ev") == "tab" and s.get("on") == "other" for _t, s in browser.said(since))
        if shown and browser.hwnd and browser.token not in sv.window_text(browser.hwnd).split():
            return True
        time.sleep(0.05)
    return False


def stop_started(url: str, state: Path) -> dict[str, Any]:
    """``--start-ollama``, once the window has closed: what TASlation's starter chose for the server it started
    (`ollama_start.setup_of`), the models still loaded in it (none: the window let go of its model), and the server
    stopped as TASlation's own end stops it (`ollama_start.finish_all`; the scratch state still holds its record)."""
    from taslation import ollama_start
    from taslation.ocr import place

    setup = ollama_start.setup_of(url, state)
    plan = place.session()
    out: dict[str, Any] = {"setup": setup.to_record() if setup is not None else None,
                           "gpu_plan": None if plan is None else {
                               "gpu": list(plan.gpu), "cpu": list(plan.cpu), "short_mib": plan.short,
                               "left_mib": plan.left, "why": plan.why,
                               "failed": {p: place.failure(p) for p in place.TO_PROCESSOR if place.failure(p)}},
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
    from taslation import frames, pipeline  # noqa: F401
    from taslation.ui import jobs, live, trouble, viewers  # noqa: F401
    from taslation.ui.dialogs import caches, start  # noqa: F401

    guard = demo_video.Guard(hwnd)
    other_first = bool(getattr(args, "standin_start_tab", None)) and hwnd == browser.hwnd  # (no token in its title)
    if guard.is_own(hwnd) or (sv.find_window(browser.tree, browser.token) != hwnd and not other_first):
        raise SystemExit("the stand-in's window is not what it should be")
    _x, _y, _w, client_h = client_rect_on_screen(hwnd)
    dpr = float(ready.get("dpr", 1) or 1)
    top = client_h - round(float(ready["vh"]) * dpr)
    area = (AREA[0], round(AREA[1] * args.scale), AREA[2], AREA[3])  # (the reader's area, set at their scale)
    if getattr(args, "standin_full_screen", False):
        area = (0, 0, 0, 0)  # (no title bar, no band: the whole frame is the viewer's)
    report["area"] = list(area)
    sv.write_control(standin_dir, 0, band=round((area[1] - top) / dpr))
    selection = sv.SelectionGuard(hwnd)
    for more in browser.more:  # (the book's own window, opened at the start for a "z": the stand-in's as much)
        guard.also.add(int(more))
        selection.also.add(int(more))
    pid = next(p for w, p in sv.top_windows() if w == hwnd)

    def viewer_info(of: int = hwnd) -> Any:
        if not guard.is_viewer(of):
            return None
        own = pid if of == hwnd else next((p for w, p in sv.top_windows() if w == of), 0)
        if own not in browser.tree:
            return None
        return WindowInfo(of, sv.window_text(of), window_class(of), own, window_rect(of), program_name(own))

    def viewer_infos() -> list[Any]:  # (the book's own window too, held minimised until its tab is moved out)
        return [w for w in (viewer_info(), *(viewer_info(more) for more in browser.more)) if w is not None]

    notes = Notes(top, dpr)
    patched = install(notes, args, guard, viewer_infos)
    watch_stuck(notes, out / "stacks.txt", url)
    watch_frames(notes, hwnd, os.getpid(), out / "stacks.txt", standin_pids=lambda: {pid, *browser.tree})
    watch_input(notes)
    state = demo_video.scratch_state()
    info = viewer_info()
    edit = bool(getattr(args, "see_edit", False))
    editing = edit or bool(getattr(args, "editing", False))  # (--editing: the role alone, nothing done on the page)
    if getattr(args, "see_margin_as_before", False):  # (a comparison: the patches' margins as they were before)
        from taslation.ui import seethrough as see_ui

        see_ui.compared_by = lambda _original: (None, ())  # (the stamp is made and reported, not used)
        report["see_margin"] = "as before"
    remember_role(state, BOOK, "translator" if editing else "reader")  # (editing: the left pane's Reader mode off)
    report["role_kept"] = "translator" if editing else "reader"
    profiles = Profiles(state / "profiles.json")
    profiles.set_margins(info, area)
    settings = Settings(state_dir=state, ui_language="en", target_language="English", ui_scale=args.scale,
                        models_dir=Path(os.environ["TASLATION_MODELS_DIR"]), ollama_url=url,
                        ocr_runs_on=args.ocr_runs_on, ollama_window_cache=args.ollama_window_cache,
                        ollama_num_gpu=args.ollama_num_gpu,
                        see_through_indicators=getattr(args, "see_indicators", "on") == "on")
    settings.validate()
    errorlog.setup(settings)
    tap = LogTap(notes, url if mode.startswith("real") else None)
    logging.getLogger().addHandler(tap)
    netguard.install(settings.ollama_port)  # nothing but the translator's port on this computer, as the window has it
    front_before = int(ctypes.windll.user32.GetForegroundWindow() or 0)  # (read only: who is in front before the start)
    import standin_seethrough

    activations = standin_seethrough.Activations()  # (TASlation's own windows' activations, from before it is made)
    behind = None
    if getattr(args, "start_behind", None):  # (the stand-in out of sight before the window is made: `Behind`)
        behind = Behind(args.start_behind, hwnd, getattr(args, "behind_end", "close"))
        behind.start()
        time.sleep(max(0.0, float(getattr(args, "behind_before_s", 0.0) or 0.0)))  # (out of sight so long first)
    made_t = now_ms()  # (the window's start: what follows is timed from here, `start_clock`)
    query = "" if getattr(args, "chooser", False) else browser.token  # (--chooser: the window asks, `chooser_step`)
    app = app_mod.App(settings, window_query=query, book=BOOK_UNNAMED if args.book_asked else BOOK, auto=True)
    built_t = now_ms()
    see = standin_seethrough.SeeWatch(app, hwnd, lambda image: notes.shown(image).screen,
                                      truth=bool(args.see_truth),
                                      shots=out / "shots" if args.see_truth else None, front_before=front_before,
                                      activations=activations,
                                      pane_shot=out / "shots" if getattr(args, "see_pane_shot", False) else None,
                                      viewer_pids=lambda: {pid, *browser.tree}, edit=edit,
                                      add=bool(getattr(args, "see_add", False)), standin_said=browser.said,
                                      standin=browser if any(s.name == "s" for s in segments) else None, top=top,
                                      state_of=lambda image: notes.shown(image).state())
    see.install()
    see.start()
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
                        app_rect)
    director.behind = behind
    director.see = see
    mon = None
    if any(s.name in WINDOW_STEPS for s in segments):  # (the m and r scenarios: `standin_monitors`)
        import standin_monitors as sm

        screens = sm.Screens()
        window_steps = sm.WindowSteps(hwnd, screens, lambda: {pid, *browser.tree}, sv.lock_foreground)
        sampler = sm.Sampler(app, hwnd, screens, lambda: bool(director.mon is not None and director.mon.fast()),
                             screen_of=lambda image: notes.shown(image).screen)
        sampler.install()
        tour = sm.Tour(app, hwnd, screens, window_steps, sv.lock_foreground)
        mon = sm.WindowRun(app, hwnd, screens, window_steps, sampler, tour, tuple(report["standin_rect"]), see,
                           editing=editing)
        sampler.start()
        director.mon = mon
    tabs = None
    if any(s.name in TAB_SCENARIOS for s in segments) or getattr(args, "standin_start_tab", None):
        import standin_tabs

        from taslation.ui import constants as constants_mod

        # the right pane's one line while another tab shows (`constants.TAB_AWAY`); before it, the status line's
        lines = [constants_mod.TAB_AWAY] if hasattr(constants_mod, "TAB_AWAY") else [
            "Waiting: the browser shows another tab. Bring the book's tab back, or drag that tab out into a window of "
            "its own."]

        def away_line(app_: Any) -> bool:
            from taslation.i18n import _ as tr

            return any(standin_tabs.right_pane_says(app_, tr(line)) for line in lines)

        def release_out(at: int, to: int) -> None:  # (the book's own window goes on: the control file's *out*)
            director.control["out"] = (int(at), int(to))
            sv.write_control(standin_dir, director.control["go"], out=director.control["out"])

        held = int(browser.more[0]) if browser.more else 0
        tabs = standin_tabs.TabRun(app, browser, notes, held, release_out, lambda more, rect: place_own(more, rect),
                                   tuple(getattr(args, "_held_rect", None) or report["standin_rect"]), away_line)
        tabs.start()
        director.tabs = tabs
    director.start()
    began = now_ms()
    try:
        app.mainloop()
    finally:
        ended = now_ms()
        if mon is not None:
            mon.sampler.stop.set()
            mon.sampler.join(3.0)
        if tabs is not None:
            tabs.close()
        if director.failed and director.selection.stopped:
            try:
                app.destroy()  # (another window was chosen: nothing more is done with it)
            except Exception:  # noqa: BLE001
                pass
        else:
            demo_video.finish_app(app)
        director.close_saver()
        if behind is not None:
            behind.end()  # (never left out of sight or covered)
            behind.close()
        logging.getLogger().removeHandler(tap)
        see.close()
    run_ = summarise(director, notes, tap, browser, patched, guard, began, ended, top, dpr, mode,
                     cache_at_end(settings))
    lat = [e["recv"] - e["t"] for e in director.events]
    run_["see_through"] = see.report(director.events, min(lat) if lat else 0.0, ended)
    run_["see_through"]["guard_refused"] = dict(Counter(guard.refused))
    if see.standin is not None:  # (scenario s: the slides with the pointer, and the jobs and pictures of their frames)
        run_["see_through"]["slides"] = see.slide_report(slide_jobs(notes))
    see_pipeline = run_["see_through"].get("pipeline") or {}
    see_pipeline["present_to_display_ms"] = see_lags(notes, see_pipeline.get("presents_t", []))
    see_pipeline["displays_t"] = [round(d["t"]) for d in notes.displays if d.get("lettered")]
    run_["start_clock"] = start_clock(notes, see, made_t, built_t, began)
    if mon is not None:
        try:
            run_["monitors"] = mon.report(notes, top, ended)
        except Exception as e:  # noqa: BLE001 - said by its type and where, the rest of the report kept
            traceback.print_exc()
            run_["monitors"] = {"failed": f"{type(e).__name__}{_where(e)}"}
    if tabs is not None:
        try:
            run_["tabs"] = tabs.report(ended)
        except Exception as e:  # noqa: BLE001 - said by its type and where, the rest of the report kept
            traceback.print_exc()
            run_["tabs"] = {"failed": f"{type(e).__name__}{_where(e)}"}
    behind_facts = director.behind_report()
    if behind_facts is not None:
        notes_now = list(see.over().notes) if see.over() is not None else []
        behind_facts["pane_hides"] = dict(Counter(f"{n['side']}:{n.get('why')}" for n in notes_now
                                                  if n["ev"] == "pane_hide"))
        run_["behind"] = behind_facts
    return run_


def slide_jobs(notes: Notes) -> dict[str, Any]:
    """Scenario s: what the window made of the frames of a page slid out of its place (the stand-in's cells say
    "slide"): the page jobs started on one, the captures (each change of what they showed), and the pictures it
    showed that were read from one."""
    with notes.lock:
        jobs = [j for j in notes.jobs if j["started"] and j["state"] == "slide"]
        captures = Counter(c["state"] for c in notes.captures)
        displays = [d for d in notes.displays if d.get("from") == "slide"]
    return {"jobs_started": len(jobs), "requests": sum(j.get("requests", 0) for j in jobs),
            "capture_changes_by_state": dict(captures), "displays_read_from_one": len(displays),
            "lettered_displays_read_from_one": sum(1 for d in displays if lettered_shown(d))}


def see_lags(notes: Notes, presents: list[float]) -> dict[str, Any]:
    """See-through mode: from the set of patches handed to the see-through window last before each lettered display of
    the window (`ui.seethrough.present`, which `_redisplay` calls before it sets the page's picture) to that display,
    within 300 ms: what making the patches holds the window's own page back."""
    import bisect

    presents = sorted(presents)
    lags = []
    for d in notes.displays:
        if not d.get("lettered"):
            continue
        i = bisect.bisect_right(presents, d["t"]) - 1
        if i >= 0 and d["t"] - presents[i] < 300:
            lags.append(d["t"] - presents[i])
    return dist(lags)


def start_clock(notes: Notes, see: Any, made_t: float, built_t: float, began: float) -> dict[str, Any]:
    """The window's start, ms from the call that makes it (`App`): made, its main loop begun, the translator ready,
    the first page lettered in the window, and with the see-through watch the first side pane and the first patches
    shown over the viewer (the see-through window's own notes)."""
    def since(t: float | None) -> int | None:
        return None if t is None else round(t - made_t)

    ready = next((e["t"] for e in notes.app_events if e["kind"] == "ready"), None)
    lettered = next((d["t"] for d in notes.displays if d.get("lettered")), None)
    out: dict[str, Any] = {"built_ms": since(built_t), "loop_ms": since(began), "ready_ms": since(ready),
                           "first_lettered_ms": since(lettered), "began_epoch_ms": round(began)}
    over = see.over() if see is not None else None
    if over is not None:
        firsts: dict[str, float] = {}
        for n in list(over.notes):
            if n["ev"] in ("pane", "show") and n["ev"] not in firsts:
                firsts[n["ev"]] = n["t"] * 1000 + see.delta_ms
        out["first_pane_ms"] = since(firsts.get("pane"))
        out["first_patches_ms"] = since(firsts.get("show"))
    return out


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
                                     and r["old_lettering_ms"]]) for s in dict.fromkeys(r["segment"] for r in rows)}}
    old_page = {  # (the page before on the page area, lettered or not)
        "all": spread_of([r["old_page_ms"] for r in rows if r["old_page_ms"] is not None]),
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
    stream_log = list(getattr(getattr(director.app, "pipeline", None), "stream_log", None) or ())
    streamed = streamed_lines(stream_log, requests, jobs)
    back_tokens = {t for e in stream_log for t in e.get("tokens_taken_back") or ()}
    wasted_t = {w["t"] for w in wasted}  # (a taken-back request of a job that was dropped is in both)
    streamed["requests_taken_back_also_wasted"] = sum(
        1 for r in requests if r.get("stream") in back_tokens and r["t"] in wasted_t)
    # the page jobs cancelled after their result was shown (the page lettered once more for its next showing,
    # `Pipeline.keep_shown`, given way to the frame of another page): how long after the result the cancel came and
    # how long the job took after it to let go of the worker
    tails = []
    for j in started:
        if j["result_t"] is None or j.get("done_t") is None:
            continue
        cut = next((c for c in sorted(notes.cancels) if j["result_t"] <= c <= j["done_t"]), None)
        if cut is not None:
            tails.append((ms(cut, j["result_t"]), ms(j["done_t"], cut)))
    tail_summary = {"jobs": len(tails), "cancel_after_result_ms": dist([a for a, _b in tails]),
                    "done_after_cancel_ms": dist([b for _a, b in tails]),
                    "tail_uncut_ms": dist([ms(j["done_t"], j["result_t"]) for j in started
                                           if j["result_t"] is not None and j.get("done_t") is not None
                                           and not any(j["result_t"] <= c <= j["done_t"] for c in notes.cancels)])}
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
    modes = {"columns": ["t_s", "role"],
             "rows": [[rel(m["t"]), m["role"]] for m in notes.modes],
             "driver_acts": [{**{k: v for k, v in a.items() if k != "t"}, "t_s": rel(a["t"])} for a in notes.acts]}
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
                                "pairs", "joined", "kept_tokens_est", "prompt_tokens_est", "stream"],
                    "rows": [[rel(r["t"]), r["job"], r["frame"], r["gate"], r["outcome"], ms(r["end_t"], r["t"]),
                              r["server_ms"], server_wait(r), wasted_why(by_id.get(r["job"]))
                              if r["job"] is not None else None, r.get("side"), r.get("why"), full_computed(r),
                              r.get("prompt_n"), r.get("prompt_ms"), r.get("answer_n"), r.get("answer_ms"),
                              r.get("pairs"), r.get("joined"), r.get("kept_tokens_est"), r.get("prompt_tokens_est"),
                              r.get("stream")]
                             for r in requests]}
    k_facts = k_block(notes, turns, rows, requests, spells, rel)
    pump = sorted(ms_ for ms_, _busy in notes.timings.get("_poll_events", []))
    poll_events = {"n": len(pump), "median": round(statistics.median(pump), 3),
                   "p90": round(pump[int(0.9 * (len(pump) - 1))], 2),
                   "p99": round(pump[int(0.99 * (len(pump) - 1))], 2), "max": round(pump[-1], 1)} if pump else None
    return {
        **({"scenario_k": k_facts} if k_facts else {}),
        "poll_events_ms": poll_events,
        "timing": timing_summary(rows, getattr(director.args, "soft_first", "on") == "on", notes.drew_soft,
                                 [s for _t, s in browser.said()], rel),
        "latency_rested": latency,
        "stage_split": split,
        "status_line_of_the_page_before": status_summary,
        "resizes": resizes,
        "cache_across_sizes": across_sizes(job_list),
        "readings_on_a_miss": readings_on_a_miss(notes.resolves, rel),
        "modes": modes,
        "cancel_in_flight": cancel,
        "wasted_requests": wasted_summary,
        "streamed_lines": streamed,
        "jobs_cancelled_past_their_page": tail_summary,
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
        "long_steps": long_steps_report(notes, [*requests, *notes.warms], rel),
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
        "released": director.released,
        **({"waits": director.waits_report()} if director.wait_done is not None else {}),
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
        "gpu_start": {"dialogs": [{k: (rel(v) if k == "t" else v) for k, v in d.items() if k != "dialog"}
                                  for d in notes.gpu_dialogs],
                      "models_loading": [[rel(t), on] for t, on in notes.models_loading]},
        "book_asked": [{k: (rel(v) if k.endswith("_t") or k == "t" else v) for k, v in d.items() if k != "dialog"}
                       for d in notes.book_dialogs],
        "no_viewer": {k: rel(v) for k, v in notes.no_viewer.items()},
        "front_owner_counts": dict(notes.owners),
        "errors": {"hooks": dict(notes.errors), "log_records": dict(tap.levels)},
        "no_answer": [{**n, "t": rel(n["t"])} for n in tap.no_answer],
        "server_priority": priority_report(notes, rel),
        "window_order": [{**n, "t": rel(n["t"])} for n in tap.window_order],
        "frame_stalls": stalls_report(notes, rel),
        "input_spells": [[rel(a), rel(b)] for a, b in notes.inputs],
        "tool_cover": None if notes.tool_cover is None else {
            **notes.tool_cover, "shown_t": rel(notes.tool_cover["shown_t"]), "gone_t": rel(notes.tool_cover["gone_t"]),
            "under_t": rel(notes.tool_cover.get("under_t")), "own_top_t": rel(notes.tool_cover.get("own_top_t"))},
        "guard": {"patched": patched, "refused": guard.refused, "chosen": sorted(set(notes.selected)),
                  "stand_in": browser.hwnd, "reached_the_stand_in": guard.used,
                  # (the book's own window, tab6's, is the stand-in's as much: `standin_tabs`)
                  "only_the_stand_in_chosen": set(notes.selected) <= {browser.hwnd, *browser.more}},
        "shots": director.shots,
        "stand_in_events": dict(Counter(e["ev"] for e in events)),
        **({"stand_in_profile_events": [[rel(float(e["t"]) + offset), e["ev"],
                                         {k: e[k] for k in PROFILE_EVENT_WORDS if k in e}]
                                        for e in events if e["ev"] in PROFILE_EVENTS]}
           if getattr(director.args, "standin_profile", "") else {}),
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
            "event_list": {"columns": ["t_s", "kind", "seq", "stage", "state", "pages"],
                           "rows": [[rel(r["t"]), r["kind"], r["seq"], r["stage"], r["state"], r["pages"]]
                                    for r in readings]},
            "told": told_states(readings),
            "catches": {"caught": sum(1 for c in catches if c["caught"]),
                        "not_caught": sum(1 for c in catches if not c["caught"]),
                        "from_regions": sum(1 for c in catches if c["caught"] and c["read"])}}


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
              f"refused {sum(1 for n in kept if 'did not put' in n['line'])} time(s)")
    cover = run_.get("tool_cover") or {}
    if cover:
        part = cover.get("part", 1.0)
        print(f"the tool's cover over {'all' if part >= 1 else f'the left {part:.0%}'} of the stand-in from "
              f"{cover.get('shown_t')} s to {cover.get('gone_t')} s: the window put at the top at "
              f"{cover.get('own_top_t')} s, the stand-in put over it at {cover.get('under_t')} s; the cover found over "
              f"it {cover.get('over_looks', 0)} of {cover.get('looks', 0)} looks, the stand-in topmost "
              f"{cover.get('standin_topmost_looks', 0)}")
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
    timing = run_.get("timing")
    if timing:
        print(f"timing with the stand-in {'soft first' if timing['soft_first'] == 'on' else 'sharp at once'} (it said "
              f"soft_first={timing['standin_said_soft_first']}, drew {timing['standin_draws']}); the window learnt it "
              f"draws soft first {timing['window_learnt_soft_first']} time(s); cached turns left out "
              f"{timing['cached_turns_left_out']}")
        for kind in ("one_page", "two_pages"):
            b = timing[kind]
            cut = {k: (v["median"], v["p90"], v["max"]) for k, v in b.items() if isinstance(v, dict) and v.get("n")}
            print(f"  {kind.replace('_', ' ')}: {b['turns']} turns (median, p90, max ms) {cut}")
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
    print(f"event pump {run_.get('poll_events_ms')}")
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
    wasted = run_["wasted_requests"]
    print(f"wasted requests {wasted['count']} {wasted['by_why']} {wasted['by_outcome']}; ran {wasted['ran_ms']}; "
          f"ran on after the cancel {wasted['ran_on_after_cancel_ms']}; next real request's server wait "
          f"{wasted['next_real_server_wait_ms']} (all real: {wasted['real_server_wait_ms']})")
    st = run_.get("streamed_lines") or {}
    if st.get("units"):
        print(f"lines sent as read: {st['lines_sent_early']} in {st['units']} units {st['outcomes']}, stood "
              f"{st['lines_stood']}, taken back {st['lines_taken_back']} (first line in "
              f"{st['units_first_line_taken_back']} units), requests thrown away {st['requests_taken_back']}; "
              f"taken-back lettering on show {st['withdrawn_on_show_ms']}; left: final {st['final_from_taken_back']}, "
              f"on show at close {st['early_left_at_close']}, at result {st['early_left_at_result']}; why taken back "
              f"{st['why_taken_back']}; held for a classical candidate {st.get('lines_held')} lines, "
              f"{st.get('held_ms')} ms; order foreseen {st.get('order_ms')} ms a unit")
    tail = run_.get("jobs_cancelled_past_their_page") or {}
    print(f"jobs cancelled past their page {tail.get('jobs')}: cancel after the result {tail.get('cancel_after_result_ms')}"
          f", done after the cancel {tail.get('done_after_cancel_ms')}; not cancelled, result to done "
          f"{tail.get('tail_uncut_ms')}")
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
    print(f"the page before after a turn: {run_['old_page_after_a_turn']['all']}; by scenario "
          f"{run_['old_page_after_a_turn']['by_segment']}")
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
    print_monitors(run_.get("monitors"))
    print_tabs(run_.get("tabs"))


def print_tabs(tabs: dict[str, Any] | None) -> None:
    """The tab scenarios' table (`standin_tabs.TabRun.report`): one row per spell away from the book's tab."""
    if not tabs:
        return
    if tabs.get("failed"):
        print(f"tabs: report FAILED: {tabs['failed']}")
        return
    other = tabs["jobs_on_the_other_tab"]
    print(f"tabs: captures of the other tab {tabs['captures_of_the_other_tab']}; jobs on it {other['made']} (started "
          f"{other['started']}, requests {other['requests']}, translated {other['translated']}, stored "
          f"{other['stored']}, units {other['units_stored']}); lettering looks over it "
          f"{tabs['lettering_looks_over_the_other_tab']}; chosen by its title "
          f"{tabs['chosen_by_the_other_tab_s_title']}; "
          f"remembered {tabs['memory_holds_an_other_tab_title']}; a pick on trial {tabs.get('pick')}")
    for s in tabs["spells"]:
        away = s["while_away"]
        print(f"  {s['segment'] or 'start'} {s['kind']}/{s.get('how')} other {s['other']} late {s['title_late_ms']} "
              f"lead {s['title_lead_ms']}: away {s['away_ms']} ms; captures {away['captures']} (of it "
              f"{away['tab_captures']}), jobs {away['jobs_started']}/{away['jobs']} {s['away_jobs_by_frame']}, "
              f"requests {away['requests']} (its {s['away_requests_of_jobs_on_the_other_tab']}), lookups "
              f"{away['lookups']}, drew soft {away['drew_soft']}; lettering looks {s['lettering_looks_away']} (the "
              f"last over it {s.get('lettering_over_the_other_tab_last_ms')} ms after its title), "
              f"ground {s['ground_looks_away']}, mouse {s['mouse_taken_looks_away']} (the last "
              f"{s.get('mouse_over_the_other_tab_last_ms')} ms after its title) of {s['looks_away']}; panes "
              f"{s['panes_looks_away']}; follows {s['followed_away']}; line {s['right_pane_line_shown']}; status "
              f"{s['status_lines_away']}; areas changed {s['page_areas_changed']}, book changed {s['book_changed']}, "
              f"remembered +{s['memory_titles_added']}; back: lettered {s.get('back_to_lettered_ms')} ms, panes "
              f"{s.get('back_to_panes_ms')} ms"
              + (f"; followed its window {s.get('followed_the_book_s_window_ms')} ms, lettered there "
                 f"{s.get('lettered_on_the_book_s_window_ms')} ms, window {s.get('second_window')}"
                 if s["kind"] == "out" else ""))


def print_monitors(mon: dict[str, Any] | None) -> None:
    """The m and r scenarios' tables (`standin_monitors.WindowRun.report`), one block per window step."""
    if not mon:
        return
    if mon.get("failed"):
        print(f"monitors: report FAILED: {mon['failed']}")
        return
    print("monitors: " + "; ".join(f"{m['n']} {m['rect']} work {m['work']} dpi {m['dpi']}"
                                   + (" primary" if m["primary"] else "") for m in mon["screens"])
          + f"; buttons on {mon['taskbar'].get('buttons_on')}; start {mon['start']}; looks {mon['looks']}")
    for p in mon["places"]:
        if not p.get("looks"):
            print(f"  {p.get('segment')}: no looks")
            continue
        panes = "; ".join(f"{side} shown {v['shown_looks']} hidden {v['hidden_looks']} inside {v['inside_viewer']} "
                          f"on {v['monitors']} why {v['why_hidden']}" for side, v in p["panes"].items())
        print(f"  {p['segment']}: monitor {p['monitor']} met {p['met']} zoomed {p['zoomed']} client {p['client']}; "
              f"lettering offset px {p['lettering_offset_px']} stale place/scale {p['stale_place_looks']}/"
              f"{p['stale_scale_looks']} (last {p.get('stale_ms_after_the_step')} ms after the step, longest "
              f"{p.get('stale_longest_ms')} ms after the look that saw the client so, with patches "
              f"{p.get('stale_with_patches_looks')}); {panes}; "
              f"overlay hides {p['overlay_pane_hides']}; scales {p['scales']}; "
              f"root {p['root']}; monitor dpi {p['monitor_dpi']}")
        for t in p.get("tour") or []:
            first = t.get("first") or {}
            second = t.get("second") or {}
            print(f"    {t['item']}: " + (f"skipped ({t['skipped']})" if t.get("skipped") else
                                         f"monitor {first.get('monitor')} (viewer's {first.get('viewer_monitor')}) "
                                         f"in its work area {first.get('in_viewer_work_area')} tk dpi "
                                         f"{first.get('tk_dpi')} / monitor {first.get('monitor_dpi')}; again "
                                         f"{second.get('monitor', '-')}; root nearest "
                                         f"{first.get('root_monitor_nearest')}")
                  + f"; front {t.get('front_before')} -> {t.get('front_after')}"
                  + (f"; ERROR {t['error']} at {t.get('error_at')}" if t.get("error") else ""))
        r = p.get("resize")
        if r:
            print(f"    resize {r['edge']} button {r['button']} sizes {r['sizes_given']} over {r['drag_ms']} ms -> "
                  f"{r['end_size']}: stale place/scale {r['stale_place_looks']}/{r['stale_scale_looks']} (last "
                  f"{r['stale_ms']} ms, longest {r.get('stale_longest_ms')} ms after the look that saw the client "
                  f"so, with patches {r.get('stale_with_patches_looks')}); lettering hidden {r['lettering_hidden_ms_after_first_size']} ms, back "
                  f"{r['lettering_back_at_new_size_ms_after_release']} ms, page done "
                  f"{r['page_done_at_new_size_ms_after_release']} ms after the release")
            print(f"      panes {r['panes']}")
            print(f"      jobs pressed {r['jobs_started_while_pressed']} ({r['requests_while_pressed']} requests), on "
                  f"sizes between {r['jobs_on_sizes_between']} ({r['requests_on_sizes_between']}); first job after "
                  f"{r['first_job_after']}; frame sizes looked at during {r['frame_sizes_looked_at_during']}, new "
                  f"size looked at {r['new_size_looked_at_ms_after_release']} ms, own area "
                  f"{r['own_area_at_new_size_ms_after_release']} ms; marks {r['marks_looks']} (another size "
                  f"{r['marks_of_another_size_looks']}); editor {r['editor']}; left pane's room at the end "
                  f"{r.get('left_room_at_end')}; front {r['front_before']} -> {r['front_after']}")
    print(f"  hover {mon['hover']}")
    print(f"  region fit {mon['region_fit']}; hand-overs refused {mon['handed_over_refused']}")


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / f"taslation-standin-{os.getpid()}",
                    help="the scratch folder (the state, the stand-in's files, report.json, shots/)")
    ap.add_argument("--scenario", default="all",
                    help="all, or some of c,a,b,d,e,x,f2,k,q,m,resize (k is k5,k1,k2 and never in all, nor is q: for "
                         "--standin-profile; m is m0-m4, the stand-in over the monitors, and resize is r1-r8, its "
                         "window resized: never in all either, `standin_monitors`)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="the display scale the stand-in's browser draws at, and TASlation's text size (1 to 3)")
    ap.add_argument("--cancel-soft-ms", type=int, default=700,
                    help="scenario x: how long the screens of little text stay soft")
    ap.add_argument("--canned", action="store_true", help="the canned translator, not the Ollama on this computer")
    ap.add_argument("--ollama-url", default=SPARE_URL,
                    help="the Ollama the window asks, on this computer (default: 127.0.0.1:11435, a second server of "
                         "the developer's own, set up otherwise, never started or stopped here; Ollama's usual port "
                         "11434 only with --usual-port)")
    ap.add_argument("--usual-port", action="store_true",
                    help="Ollama's usual port 11434 is meant (--ollama-url, --start-ollama): the server there is "
                         "likely the person's own, so it is refused without this")
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
    ap.add_argument("--gpu-short-answer", default="processor",
                    choices=("processor", "again", "release", "quit", "none"),
                    help="the start's dialog on the GPU's memory, when the window shows it (the card short for "
                         "everything at the start): answered through the window's own object with this (default: "
                         "start on the processor; release: Release and check again where the dialog has it, else "
                         "start on the processor; none: left open), no input to the computer; noted in the report "
                         "(gpu_start, with the other models it named)")
    ap.add_argument("--canned-ms", type=int, default=350, help="the canned translator's answer time per line")
    ap.add_argument("--canned-load-s", type=float, default=5.0, help="the canned translator's load time")
    ap.add_argument("--browser", default="auto", choices=("auto", "chrome", "edge"))
    ap.add_argument("--seed", type=int, default=1, help="the stand-in's draws (soft times, waits)")
    ap.add_argument("--series", type=int, default=1, help="the dataset's series, by its place in the sorted list")
    ap.add_argument("--first", type=int, default=1, help="its first page (from 1)")
    ap.add_argument("--synthetic", action="store_true", help="the repository's test pages, not the dataset")
    ap.add_argument("--see-margin-as-before", action="store_true",
                    help="the patches' margins as they were before they kept to the page's own pixels "
                         "(`ui.seethrough.compared_by` gives nothing): the same run compared with the rule before")
    ap.add_argument("--pages", default="", metavar="PNG[,PNG...]",
                    help="made-up pages of the developer's (`tools/make_sample_page.py --layout ...`) in place of the "
                         "dataset's, again and again in this order: a case reproduced on pages made for it")
    ap.add_argument("--front-for-order", default="as-is", choices=("as-is", "own"),
                    help="own: the window keeps the viewer under its own as with it in front (`ui.order`), whoever is "
                         "in front (nothing is brought to the front); with --cover, as if the cover's program were in "
                         "front until COVER_FRONT_S after the cover came, when the window is put at the top of the "
                         "order, as a click on it puts it, with no activation")
    ap.add_argument("--order-partly", default="as-built", choices=("as-built", "on", "off"),
                    help="`ui.order.PARTLY_COVERED_TOO` for this run: on, a window over a part of the viewer sends it "
                         "up too; off, only windows that hide all of it (default: as built)")
    ap.add_argument("--front", default="viewer", choices=("viewer", "as-is"),
                    help="viewer: the window is told the viewer is in front (the reader's case); as-is: as it is")
    ap.add_argument("--models", default="", help="the models folder (default: TASLATION_MODELS_DIR)")
    ap.add_argument("--timeout", type=float, default=180.0, help="seconds a scenario may wait for the window's rest")
    ap.add_argument("--wait-done", type=float, metavar="CAP_S",
                    help="a computer slower than the scenarios' rests were written for: the rests of a, d, e, x and "
                         "f2, the one at each one's end too, held until the page on show is finished (or "
                         "the window at rest without it), CAP_S at most, and x's soft frames kept until the window "
                         f"asked on them ({KEEP_SOFT_S:g} s at most); the holds in the report (run.waits). Without it "
                         "the scenarios are as written")
    ap.add_argument("--k-turns", type=int, default=20, help="scenario k: the pages flipped past at each pace")
    ap.add_argument("--k-read", type=int, default=0, help="scenario k: the pages read back after (default: all)")
    ap.add_argument("--k-read-ms", type=int, default=K_READ_MS,
                    help=f"scenario k: ms a page read back stays (default {K_READ_MS}; longer for a computer without "
                         "a GPU, whose page on show takes longer)")
    ap.add_argument("--k-stay-ms", type=int, default=0,
                    help="scenario k: ms the last page flipped to stays before the turn back (default: the pace) - a "
                         "page read afresh on show while the pages turned past wait")
    ap.add_argument("--k-soft", default="on", choices=("on", "off"),
                    help="scenario k: the stand-in draws each page soft first (on, its own soft time) or sharp at once")
    ap.add_argument("--soft-first", default=None, choices=("on", "off"),
                    help="on (default without --standin-profile): the stand-in draws every turn soft first and sharp a "
                         "while later, as the correctness runs have it; off (default with a profile): every turn sharp "
                         "at once and nothing after it, for the timing figures (what TASlation takes, with no wait of "
                         "the viewer's in it); x is left out of all and refused by name, and --k-soft changes nothing")
    ap.add_argument("--standin-draws-covered", action="store_true",
                    help="the stand-in browser goes on drawing while other windows hide it wholly (its occlusion "
                         "tracking off): a run that does not depend on the windows of a person at the machine")
    ap.add_argument("--cover", type=cover_plan, default=None, metavar="SEGMENT:AT:FOR",
                    help="the tool's own plain window laid over the stand-in AT seconds after SEGMENT began, for FOR "
                         "seconds (a viewer wholly covered, on purpose; no key, no activation)")
    ap.add_argument("--cover-style", default=COVER_EX, choices=("plain", "noactivate"),
                    help="--cover's extended style: plain (default) or WS_EX_NOACTIVATE (either way shown with no "
                         "activation)")
    ap.add_argument("--cover-front-s", type=float, default=COVER_FRONT_S, metavar="S",
                    help="--front-for-order own with --cover: the window put at the top of the order S seconds after "
                         "the cover came (default %(default)s)")
    ap.add_argument("--cover-part", type=cover_part, default=1.0, metavar="F",
                    help="--cover over the left F of the stand-in's width alone (0 < F <= 1; default 1: all of it)")
    ap.add_argument("--k-backlog", default="on", choices=("on", "off"),
                    help="off: no page is caught behind the reader (the baseline of the same turns)")
    ap.add_argument("--k-narrow", action="store_true",
                    help="scenario k: in the narrow window (single pages), the stand-in placed at NARROW_SIZE first")
    ap.add_argument("--standin-slider", type=int, default=0, choices=(0, 1, 2),
                    help="the stand-in's page slider under the page: 0 none (default), 1 a bar with a knob, 2 the "
                         "pages drawn as the knob is dragged")
    ap.add_argument("--standin-profile", default="", choices=("", *sv.PROFILES),
                    help="the stand-in behaves as one of two kinds of web viewer (standin.html says how): dark or "
                         "light; default none, the stand-in as it always was (scenario q is written for a profile)")
    ap.add_argument("--standin-option", action="append", default=[], metavar="NAME=VALUE",
                    help="with --standin-profile: one of its parts given another value (again for more; the names: "
                         + ", ".join(sv.PROFILE_OPTIONS) + ")")
    ap.add_argument("--see-indicators", default="on", choices=("on", "off"),
                    help="the setting see_through_indicators (off: no indicators pane at the right)")
    ap.add_argument("--see-truth", action="store_true",
                    help="copies of the stand-in's place on the screen, every "
                         f"{1000 * 0.033:.0f} ms in memory, checked for old patches over a new page; two of them into "
                         "shots/ (they show the sample pages: delete them after)")
    ap.add_argument("--see-pane-shot", action="store_true",
                    help="one copy of the stand-in's place on the screen, taken the first time "
                         "both side panes show beside a spread whose page is done and the copy shows nothing of another "
                         "program's, into shots/ (it shows a sample page: delete it after)")
    ap.add_argument("--see-edit", action="store_true",
                    help="the book's role kept as editing (the program's default; without it a run sets Reader mode), "
                         "so that the left pane's Reader mode is off from the start; a click (it chooses), a double "
                         "click (the editor) and drags on a region, a click on its number plate with its place typed, "
                         "a rectangle drawn on the empty ground and the Delete key on it, posted to TASlation's own "
                         "windows, are measured in place of the patch under the pointer (run.see_through.edit)")
    ap.add_argument("--editing", action="store_true",
                    help="the book's role kept as editing, as --see-edit keeps it, but nothing is done on the page: the "
                         "patch under the pointer measured as in Reader mode (timing runs of editing against Reader "
                         "mode: what editing alone costs)")
    ap.add_argument("--see-add", action="store_true",
                    help="adding text areas measured in place of both (run.see_through.add), editing with --see-edit "
                         "and Reader mode without: once a page is done, the left pane's Add area and the Insert key's "
                         "message, each with a rectangle dragged on the page's empty space, then each way of giving "
                         "it up, all posted to TASlation's own windows, and who is in front against whether the key "
                         "is held (read only); best with scenario g")
    ap.add_argument("--standin-size", default="", metavar="WxH",
                    help=f"the stand-in's window size (default {STANDIN_SIZE[0]}x{STANDIN_SIZE[1]}), within the "
                         "primary monitor's work area")
    ap.add_argument("--standin-monitor", type=int, default=1, metavar="N",
                    help="the monitor the stand-in starts on: 1 the primary (default), 2 the next (the monitors in "
                         "the order `standin_monitors.Screens` gives them), at the top left of its work area")
    ap.add_argument("--standin-maximised", action="store_true",
                    help="the stand-in maximised on its monitor from the start (refused on the primary, which a "
                         "run never covers with a maximised window), the foreground locked meanwhile")
    ap.add_argument("--standin-full-screen", action="store_true",
                    help="the stand-in in the browser's own full screen from its start; the reader's area is then the "
                         "whole frame")
    ap.add_argument("--no-viewer-s", type=float, default=0.0, metavar="S",
                    help="the window finds no viewer for its first S seconds (its look for windows given none), then "
                         "the stand-in; nothing is released before it has chosen it (run.no_viewer; the stand-in is "
                         "named, window_query: no viewer chooser comes)")
    ap.add_argument("--book-asked", action="store_true",
                    help=f"the window begins with the name {BOOK_UNNAMED!r}, which names no book, so that Auto's first "
                         f"page asks it (the start dialog); answered {BOOK_ANSWER_S:g} s after it is on the screen, "
                         f"through its own object, with {BOOK!r} (run.book_asked)")
    ap.add_argument("--start-behind", default=None, choices=BEHIND_MODES,
                    help="the stand-in out of sight as the window starts (`Behind`: covered by the tool's own window - "
                         "all of it, its left half, its monitor's work area, or all of it with the cover in front -, "
                         "or minimised), back in sight --behind-s after the window chose it; nothing is released "
                         "before; the side panes' state as it changed in run.behind")
    ap.add_argument("--behind-s", type=float, default=BEHIND_S, metavar="S",
                    help="--start-behind: seconds from the window's choice of the stand-in to its being back in sight "
                         "(default %(default)s)")
    ap.add_argument("--chooser", action="store_true",
                    help="the window names no viewer (no window_query): its viewer chooser comes at the start, and "
                         "the driver chooses the stand-in in it through the dialog's own object (run.behind.chooser)")
    ap.add_argument("--standin-start-tab", choices=("plain", "japanese"), default=None,
                    help="the stand-in's other tab (a plain page with a neutral title, or one of made-up Japanese "
                         "lines) on show from before the window starts, as a browser showing another tab; scenario "
                         "tab0 brings the book's tab back (run.tabs, `standin_tabs`)")
    ap.add_argument("--standin-bars-held", type=int, default=0, metavar="MS",
                    help="a stand-in with a profile: its bars up over the page from its start, held MS ms (as while "
                         "the pointer rests on them; with --standin-option bar_key_hide=0 a turn leaves them up)")
    ap.add_argument("--behind-end", default="close", choices=BEHIND_ENDS,
                    help="--start-behind: how the stand-in comes back in sight: close (the cover goes) or raise (the "
                         "stand-in put over the cover and given the foreground, as a click on it does; the cover "
                         "stays under it until the run's end)")
    ap.add_argument("--behind-before-s", type=float, default=0.0, metavar="S",
                    help="--start-behind: the stand-in out of sight so long before the window is made (a viewer that "
                         "has lain behind the other windows a while: its browser's occlusion tracking has stopped it)")
    args = ap.parse_args(argv)
    if args.soft_first is None:
        args.soft_first = "off" if args.standin_profile else "on"
    if not args.usual_port:
        if args.start_ollama == USUAL_PORT:
            ap.error(f"--start-ollama {USUAL_PORT} is Ollama's usual port (the person's own server is likely there): "
                     "give a spare one, or add --usual-port if that is meant")
        if url_port(args.ollama_url) == USUAL_PORT and not args.start_ollama:
            ap.error(f"--ollama-url on port {USUAL_PORT} is Ollama's usual port (the person's own server is likely "
                     "there): give another, or add --usual-port if that is meant")
    return args


def url_port(url: str) -> int | None:
    """The port of an http address (None when it has none, or is not one)."""
    from urllib.parse import urlsplit

    try:
        return urlsplit(url).port
    except ValueError:
        return None


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
