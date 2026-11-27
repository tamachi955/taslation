"""The README's introduction made into one animated GIF (dev tool, never part of a release): scenes recorded from the
screen over the stand-in viewer's window - the viewer chooser, TASlation's lettering over the window and its two side
panes, Reader mode and editing -, numbered, between a title card and a closing card; every sentence in it follows
docs/MANUAL.md.

    python tools/intro_video.py record --out SCRATCH/intro.zip [--start-ollama 11435] [--standin-monitor 2]
    python tools/intro_video.py render SCRATCH/intro.zip --out SCRATCH/taslation-intro.gif [--fit]
    python tools/intro_video.py render --sample --out SCRATCH/sample.gif [--frames-png SCRATCH/frames]

``record`` runs `tools/standin_e2e.py` - its stand-in viewer (a page in a browser window of its own) on the
OpenMantra sample pages, drawn sharp at once (``--soft-first off``); the real program, OCR models and translator,
the translator's server started by TASlation's own starter on a port of its own (``--start-ollama``, 11435 by
default: never the port of an Ollama already running); TASlation starting editing (``--editing``, as it starts for
a book not chosen for before) and asking for the viewer (``--chooser``), the stand-in remembered in the run's scratch
state as the viewer chosen before (`remember_viewer`), so that the chooser comes over it with it preselected; its
guard, scratch state and cleanup - on a scenario of its own (`SCRIPT`: held, one turn, held to the end) and drives
the scenes of `SCENES` from that run's loop:

1. ``chooser``: the tool's pointer to the chooser's list and to OK, the chooser answered through its own object;
2. ``reader``: Reader mode checked in the left pane, the page's boxes gone;
3. ``turn``: the stand-in turns its page by its own script (nothing is sent to it), and the page fills in;
4. ``panes``: the pointer goes down the left pane's controls and over to the right pane;
5. ``foot``: it rests on the right pane's foot (outlined in the GIF);
6. ``language``: a click on the left pane's language lists every language beside the pane, and the list is ended
   with no change (`EndMenu`, as Windows ends a menu; an Esc posted to the list's own window should it stay up);
7. ``original``: it rests on a bubble the hover delay and HOVER_REST_S more - the original in its place, the
   bubble's block in the right pane - and goes on to that block;
8. ``edit``: Reader mode unchecked; a click on a box (selected, its corner handles), a double click (the region
   editor beside it, closed again), the box dragged and dragged back, a click on its number plate (the place entry)
   given up by a click on the page's empty ground.

The stand-in goes on monitor ``--standin-monitor`` (STANDIN_MONITOR by default), at the top left of its work area:
``record`` refuses before anything starts where a window of another program lies on that place or within
PLACE_MARGIN of it (no clean place), and the take is given up and deleted as soon as one meets the stand-in's window
while the run lasts (looked at with every frame, and every CHECK_S between them: every shown top-level window, above
or below it, click-through or not, the desktop's own left out; no title is read). The pointer is the tool's own: the
see-through window is told where it is (`standin_seethrough.SeeWatch`'s fake point, whose own measures that would
move it or click a pane are left out here); the real pointer never moves. The clicks are messages POSTED to
TASlation's own windows (its panes, its lettering, the region editor's close, an Esc to its own list of languages:
`post_raw` refuses any window of another process); nothing is sent to the stand-in nor to any other window, and no
key or click of the system's is made. Nothing takes the foreground from another program's window: the stand-in's
browser opens without taking it (as in every stand-in run), what TASlation would take it with while the run lasts
(`windows.give_foreground`, `see_menu._front`, Tk's ``focus -force``) does nothing while the window in front is not
one of ours (`ForegroundGuard`), Windows' lock on changes of the window in front is asked for every LOCK_EVERY_S (a
key or click of the person's lifts it), and a take in which the foreground came to a window of ours from another
program's is given up. ``record`` says what was refused so (``foreground_refused``) and who had the foreground.

The frames are copies of the screen in the stand-in's client area (`standin_seethrough.screen_copy`; its sides and
foot, EDGE px, left out: the window's rounded corners show what lies behind it), RECORD_FPS a second while the scenes
run; each is kept only when no other program's window lies over the stand-in (`capture.seethrough.cover_rects`,
every window of TASlation's - the chooser, the region editor, a place entry, the list of languages - counted as its
own) and, from the see-through window on, outside where TASlation's own windows draw (the patches, the panes, Edit's
boxes, its other windows: `own_masks`, `window_masks`), it shows the stand-in's own frame of that moment
(`standin_seethrough.foreign_tiles`, as the pane shot of a stand-in run is checked); the chooser's frames, before
the stand-in's window is captured, are kept on the checks of the windows alone. A frame that fails is never kept nor
looked at again, and REFUSED_IN_A_ROW of them in a row stop the run, the recording deleted. The recording - a ZIP
of JPEG frames and ``meta.json``, numbers and ids only, never a line of a page's text (`check_no_text`) - goes into
a scratch folder; the run's own scratch folder beside it is deleted at the end (``--keep-run`` keeps its
report.json). What the screen was used for, from the stand-in's start to its close, is said in seconds
(``screen_s``).

``render`` makes the GIF of a recording, 960x620 by default and about 30 to 60 s long: a title card, the scenes
numbered in their order (the stand-in's window below its band as the screen showed it, the side panes outlined in
their scene and the right pane's foot in its own, the tool's pointer drawn in, the step under the picture), then the
closing card. The page's turn is shown as it was; in the other scenes a wait with nothing changing is cut to
LONGEST_S. The GIF costs each visitor of the page as little as it can: one palette of COLOURS colours with the
panes' and the boxes' colours kept apart, no dither; each frame stores only what changed; where only the screen's
picture changes, at most STILL_FPS frames a second; a card is one frame. ``--fit [BYTES]`` makes it with the first
of FIT_LADDER's settings (frames a second where only the picture changes, colours, frames a second) that keeps it
within BYTES (AIM_BYTES by default: the README's recording it replaces) and says what each try came to. A GIF over
5 MB is refused (``--allow-large`` writes it and says by how much it is over); either way the scenes that take the
most bytes are said. The recording file is deleted once the GIF is written (``--keep-recording`` keeps it); it
holds pictures of the sample pages, as the GIF does: both are CC BY-NC 4.0 material ("Sample pages: OpenMantra
dataset (Mantra Inc., CC BY-NC 4.0), modified" on every frame with a page), never part of a release. The GIF goes
where git ignores it (``promo/``) or outside the repository; the recording into a scratch folder. ``render
--sample`` renders made-up frames (no window, no model, no manga page)."""

from __future__ import annotations

import argparse
import bisect
import importlib.util
import io
import json
import os
import shutil
import sys
import threading
import time
import zipfile
from collections import Counter, OrderedDict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
for _path in (str(TOOLS), str(ROOT)):  # (this checkout's package first, whatever is installed)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import promo_video as pv  # noqa: E402

FORMAT = "intro-3"  # the recording's ``intro_format`` (intro-1: TASlation's own window, before 2.0.0; intro-2: four
# scenes, no viewer chooser, Reader mode at the start)
GIF_LIMIT = 5_000_000  # bytes: a GIF over this is refused without --allow-large (every visitor of the page loads it)
AIM_BYTES = 654_681  # bytes: the README's recording before this one (four scenes, 47.8 s): --fit keeps the GIF within
SIZE = (960, 620)
LENGTH_AIM = (30.0, 60.0)  # s: the GIF's length aimed at (said when it is outside)
MAX_SPEED = 8.0
LONGEST_S = 1.0  # a wait with nothing changing is cut to this long (not in the page's turn)
COLOURS = 48  # the GIF's palette: the pages are black and white with greys, the panes' and boxes' colours kept apart
STILL_FPS = 2.0  # frames where only the screen's picture changes (lettering, waiting): at most this many a second
RENDER_FPS = 10.0
FIT_LADDER = ((STILL_FPS, COLOURS, RENDER_FPS), (1.5, 40, 8.0), (1.0, 32, 8.0), (1.0, 32, 6.0), (0.75, 24, 6.0))
# (--fit: still frames a second, colours, frames a second; tried in turn until the GIF is small enough)
TITLE_S, CARD_S = 3.5, 5.0

# colours (the dark ground of promo_video's)
BG, TEXT, DIM, AMBER = pv.BG, pv.TEXT, pv.DIM, pv.AMBER
PANEL = (28, 29, 33)
BLUE = (58, 128, 232)
SOFT_TEXT = (205, 207, 212)


# ---------------------------------------------------------------------------------------------------- the scenes
def has_module(name: str) -> bool:
    """Whether this checkout's package has the module *name* (looked up, not imported)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def always() -> bool:
    return True


def chooser_present() -> bool:
    """The viewer chooser at the start (`taslation.ui.see_menu`)."""
    return has_module("taslation.ui.see_menu")


def panes_present() -> bool:
    """The side panes beside the page (`taslation.panes`)."""
    return has_module("taslation.panes")


def edit_present() -> bool:
    """Editing on the lettering over the viewer and Reader mode (`taslation.ui.see_edit`)."""
    return has_module("taslation.ui.see_edit")


MANUAL = "docs/MANUAL.md"
DOCS = (MANUAL,)  # the documents a line of the recording may follow


@dataclass(frozen=True)
class Cite:
    """A sentence of a document that a line of the recording follows (or several sentences): *doc* is the document's
    path from the checkout's root, and *quote* stands in it word for word once the facts of `code_facts` are put in
    ({name}, as in the lines), a run of white space reading as one space. The tool's tests check that every quote
    still stands, so a line cannot go stale silently when its document changes."""

    doc: str
    quote: str


def cites(doc: str, *quotes: str) -> tuple[Cite, ...]:
    """*quotes* of the document *doc*, as `Cite`s."""
    return tuple(Cite(doc, quote) for quote in quotes)


@dataclass(frozen=True)
class Scene:
    """A step of the introduction: its id, its title and description (no number: numbers are given at render time;
    {name} is a fact of `code_facts`), its share of the GIF in seconds, whether a wait with nothing changing in it is
    cut (`cut`: not in the page's turn, shown as it was), whether this checkout has what it shows, and what its
    description follows: the sentences of the documents it says (`follows`) and, for the tool's own words, what they
    say and where that comes from (`own`; a description has one or the other, or both)."""

    id: str
    title: str
    description: str
    budget_s: float
    cut: bool = True
    present: Callable[[], bool] = always
    follows: tuple[Cite, ...] = ()
    own: str = ""


SCENES: tuple[Scene, ...] = (
    Scene("chooser", "Choose the viewer",
          "At the start, TASlation asks which window is the viewer. The viewer chosen before comes first in the list "
          "and is already selected: OK is enough.", 5.0, present=chooser_present,
          follows=cites(MANUAL, "TASlation asks which window is the viewer: a small dialog with a \"Viewer\" list of "
                                "the windows on the screen",
                        "TASlation never chooses a window by itself.",
                        "the viewer you chose before comes first in the list and is already selected, so Enter or "
                        "\"OK\" is enough")),
    Scene("reader", "Reader mode",
          "TASlation starts editing, every region of the page outlined. Check Reader mode in the left pane to only "
          "read: the boxes go, and every click goes to the viewer.", 5.0, present=edit_present,
          follows=cites(MANUAL, "TASlation starts editing.",
                        "\"Reader mode\" in the left pane (checked: you only read) switches editing off, and "
                        "unchecked again, on.",
                        "While editing, every region of the page on show is outlined over the viewer in its colour, "
                        "with its number in the reading order on a small plate of that colour",
                        "In Reader mode it takes no click and no key: every click and key goes to the viewer, as "
                        "without TASlation")),
    Scene("turn", "Real-time translation",
          "Turn the page in the viewer, as ever. The page fills in while you look at it: its bubbles are translated "
          "in reading order, each lettered as soon as its translation is ready.", 9.0, cut=False,
          follows=cites(MANUAL, "Read in the viewer as it is: turn the pages there, with its own keys, buttons or "
                                "clicks.",
                        "An untranslated page fills in while you look at it.",
                        "The bubbles are translated in the order the page's bubbles are read, each with the lines "
                        "before it as context.",
                        "Each bubble is lettered as soon as its translation is ready.")),
    Scene("panes", "The side panes",
          "TASlation's controls and indicators lie in two panes on the viewer's ground beside the page: the controls "
          "on the left, the indicators on the right.", 6.0, present=panes_present,
          follows=cites(MANUAL, "TASlation's controls and indicators lie in two panes on the viewer's ground beside "
                                "the page, at the left and right edges of the capture area",
                        "**The left pane** holds the controls",
                        "**The right pane** (while \"Indicators\" is on) shows, at its top, the bubble last under the "
                        "pointer")),
    Scene("foot", "The right pane's foot",
          "The foot of the right pane keeps its rows in their places: how far the page on show is, the mode, where "
          "the translator runs and the viewer followed.", 4.0, present=panes_present,
          follows=cites(MANUAL, "Its foot keeps its rows in their places whatever the rest says: how far the page on "
                                "show is, the mode (\"Editing: turn pages with the keys\" or \"Reader mode\"), where "
                                "the translator runs",
                        "the viewer followed (\"Viewer: <title>\", a long title shortened in the middle)")),
    Scene("language", "Your language",
          "A click on the language in the left pane lists every language at the right side of the pane; a click on "
          "one takes it at once, and a click elsewhere, or Esc, closes the list with no change.", 5.0,
          present=panes_present,
          follows=cites(MANUAL, "the target language (a click lists every language at the right side of the pane, "
                                "and a click on one takes it at once; a click elsewhere, or Esc, closes the list with "
                                "no change)")),
    Scene("original", "The original under the pointer",
          "Rest the pointer on a bubble: its lettering gives way to the original lettering in its place, and the right "
          "pane shows that bubble's Japanese and its translation.", 7.0, present=panes_present,
          follows=cites(MANUAL, "Rest the pointer on a bubble, and after a moment (`hover_delay_ms`, 450 milliseconds "
                                "by default; \"Delay under the pointer\" in \"Settings...\", 0 to 3000, 0 at once) its "
                                "lettering gives way to the original lettering in its place.",
                        "With \"Indicators\" on, the right pane shows that bubble at its top: \"Copy the Japanese\", "
                        "\"Copy the translation\" and \"Ask again\", then its Japanese and its translation (up to five "
                        "lines each).")),
    Scene("edit", "Editing",
          "Uncheck Reader mode to edit. A click on a box selects it, with its corner handles; a double click opens "
          "the region editor beside it. Drag a box to move it; a click on its number opens a field for its place in "
          "the reading order.", 16.0, present=edit_present,
          follows=cites(MANUAL, "\"Reader mode\" (checked: the mouse is the viewer's; unchecked: editing)",
                        "a click on a box selects it: it gets a stronger outline with its corner handles. A double "
                        "click opens the region editor beside it.",
                        "Like shapes in office software, a region is moved by dragging and resized with its corner "
                        "handles",
                        "a click on a box's number opens a small field over it to type the region's place in the "
                        "reading order",
                        "Esc, or a click anywhere else, gives it up.")),
)
SCENE_IDS = tuple(s.id for s in SCENES)


def scene_of(scene_id: str) -> Scene | None:
    return next((s for s in SCENES if s.id == scene_id), None)


# ---------------------------------------------------------------------------------------------------- the cards
def code_facts() -> dict[str, Any]:
    """The figures the cards and the steps say, from the code's own constants (never written by hand)."""
    import taslation

    return {"version": str(taslation.__version__)}


@dataclass(frozen=True)
class Line:
    """A line of a card: its text ({name} is a fact of `code_facts`; a line whose fact is missing is left out), its
    style ("title", "lead", "body", "small" or "bullet"), and what it follows: the sentences of the documents it says
    (`follows`) or, for the tool's own words, what they say and where that comes from (`own`)."""

    text: str
    style: str
    follows: tuple[Cite, ...] = ()
    own: str = ""


REAL_TIME = ("TASlation does real-time translation: you read the book in its viewer as it is, and each page you turn "
             "there is lettered in your language over the viewer's window.")  # (docs/MANUAL.md, at its top)

# card id -> (heading, lines)
CARDS: dict[str, tuple[str, tuple[Line, ...]]] = {
    "title": ("", (
        Line("TASlation", "title", own="the program's name"),
        Line("Real-time translation", "lead", cites(MANUAL, REAL_TIME)),
        Line("Read the book in its viewer as it is: each page you turn there is lettered in your language over the "
             "viewer's window.", "body", cites(MANUAL, REAL_TIME)),
        Line("Recorded with version {version}", "small",
             own="the version of the checkout the recording was made with (taslation.__version__)"),
    )),
    "points": ("On your own computer", (
        Line("There is no account to make and no limit on the pages it translates.", "bullet",
             cites(MANUAL, "There is no account to make and no limit on the pages it translates.")),
        Line("Nothing of your books leaves this computer: the pages are read and translated on it.", "bullet",
             cites(MANUAL, "Nothing of your books leaves this computer: the pages are read and translated on it")),
        Line("You read in the viewer as it is: TASlation presses no key and sends no click to the viewer, turns no "
             "page by itself, and reads only the page the viewer shows.", "bullet",
             cites(MANUAL, "Read in the viewer as it is: turn the pages there, with its own keys, buttons or clicks.",
                   "TASlation presses no key and sends no click to the viewer, turns no page by itself, and reads "
                   "only the page the viewer shows.")),
        Line(pv.PROJECT, "small", own="the repository's address (promo_video.PROJECT)"),
    )),
}
CARD_ORDER = ("points",)  # the cards after the scenes (the title card comes first)


def filled(text: str, facts: dict[str, Any]) -> str | None:
    """*text* with its facts put in; None when one of them is missing."""
    try:
        return text.format(**facts)
    except (KeyError, IndexError, ValueError):
        return None


def card_lines(kind: str, facts: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    """The card *kind*'s heading and its lines with the facts put in (a line whose fact is missing left out)."""
    heading, lines = CARDS[kind]
    out = [(t, line.style) for t, line in ((filled(line.text, facts), line) for line in lines) if t is not None]
    return heading, out


def step_texts(scene: Scene, facts: dict[str, Any]) -> tuple[str, str]:
    return filled(scene.title, facts) or scene.title, filled(scene.description, facts) or scene.description


# ---------------------------------------------------------------------------------------------------- no text kept
FORBIDDEN_KEYS = {"text", "texts", "translated_text", "translation", "translations", "source", "line", "lines", "words",
                  "term", "rendering", "japanese", "original_text", "ocr_text"}
LONGEST_VALUE = 120


def check_no_text(meta: Any, where: str = "meta") -> None:
    """Raises ValueError where *meta* could hold a page's text: a key named for text, a string with Japanese in it,
    or a string longer than an id or a path would be."""
    if isinstance(meta, dict):
        for key, value in meta.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"{where}: a key named {key!r}")
            check_no_text(value, f"{where}.{key}")
    elif isinstance(meta, (list, tuple)):
        for i, value in enumerate(meta):
            check_no_text(value, f"{where}[{i}]")
    elif isinstance(meta, str):
        if any(0x3000 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF or 0xFF00 <= ord(c) <= 0xFFEF for c in meta):
            raise ValueError(f"{where}: Japanese in a string")
        if len(meta) > LONGEST_VALUE:
            raise ValueError(f"{where}: a string of {len(meta)} characters")


# ---------------------------------------------------------------------------------------------------- record
SCENARIO = "iv"  # the stand-in run's scenario of this tool's (named only)
SCRIPT = ("h1", "n", "h2")  # its steps once released: held until the first scene, one turn, held to the end
RECORD_FPS = 8.0
REFUSED_IN_A_ROW = 6  # frames in a row refused by the check stop the run
STANDIN_SIZE = "1500x900"  # the stand-in's window: room for both panes beside a spread, and clear of the screen's
# right-hand column where notifications stay until they are put away (a 1920 px screen)
STANDIN_MONITOR = 2  # the monitor the stand-in goes on, at the top left of its work area (the primary is 1, the others
# by their left edge, as standin_e2e numbers them): the primary is the one the person most likely works on
PLACE_MARGIN = 8  # px round the stand-in's place that no window of another program may meet either, before the start
RECORD_PORT = 11435  # the translator's server TASlation's starter starts for the run (not the usual 11434)
FIRST_PAGE = 4  # the sample series' page the stand-in opens on (past its title pages)
FIRST_PAGE_S = 300.0  # the first page (the models loaded at the start) waited for so long at the most
PAGE_S = 90.0  # a page turned to, and Edit's page read again, waited for so long at the most
CHOOSER_S = 30.0  # the stand-in listed in the viewer chooser waited for so long at the most
TICK_S = 0.04  # the run's loop (standin_e2e.TICK_MS)
PATCH_PAD, PANE_PAD, OWN_PAD = 3, 2, 2  # px round TASlation's patches, panes, other windows the check leaves out
EDGE = 16  # px of the stand-in's client area left out at its sides and foot (the window's rounded corners)
EDIT_PAD = 30  # px (at 96 DPI) round Edit's boxes: their number plates, outlines and handles
DRAG = (64, 30)  # px (at 96 DPI) a box is dragged by in the edit scene, and back
DRAG_S = 0.8
MIN_BOX = 40  # px (at 96 DPI): the least side of a box the edit scene takes
HOVER_REST_S = 0.6  # the pointer rests on a bubble the hover delay and so much more before the original is looked for
CHECK_S = 0.25  # the screen's windows looked at so often while no frame is taken (and at every frame)
LOCK_EVERY_S = 2.0  # Windows' lock on changes of the window in front asked for again so often while the run lasts
ESC_AFTER_S = 3.0  # the list of languages, still up so long after it was ended, gets an Esc posted to its own window
JPEG_QUALITY = 90
DESKTOP_CLASSES = ("Progman", "WorkerW")  # the desktop's own windows (its wallpaper and icons): never in the way
FOREIGN = "a window of another program's met the stand-in"
TAKEN = "the foreground came to a window of ours from another program's"
WM_CLOSE, WM_KEYDOWN, WM_KEYUP, VK_ESCAPE = 0x0010, 0x0100, 0x0101, 0x1B

Box = tuple[int, int, int, int]


class SceneFailed(RuntimeError):
    """A scene could not be acted (its words: what was waited for, numbers only)."""


# the screen's windows, read only (no title is read; nothing is moved, raised or sent anything)
@dataclass(frozen=True)
class Shown:
    """A shown top-level window: its handle, its process, its rectangle as the compositor shows it, and whether it is
    the desktop's own (its wallpaper, its icons)."""

    hwnd: int
    pid: int
    rect: Box
    desktop: bool = False


_DLLS: dict[str, Any] = {}


def _user32() -> Any:
    """user32 of this tool's own (its functions' argument types set here, not shared with any other module)."""
    if "user32" not in _DLLS:
        import ctypes
        from ctypes import wintypes

        u = ctypes.WinDLL("user32")
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.IsIconic.argtypes = [wintypes.HWND]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        _DLLS["user32"] = u
    return _DLLS["user32"]


def _dwmapi() -> Any:
    if "dwmapi" not in _DLLS:
        import ctypes

        _DLLS["dwmapi"] = ctypes.WinDLL("dwmapi")
    return _DLLS["dwmapi"]


def window_pid(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes

    pid = wintypes.DWORD(0)
    _user32().GetWindowThreadProcessId(int(hwnd or 0), ctypes.byref(pid))
    return int(pid.value)


def frame_rect(hwnd: int) -> Box:
    """The window's rectangle as the compositor shows it (without the invisible resize borders)."""
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    if _dwmapi().DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        _user32().GetWindowRect(hwnd, ctypes.byref(rect))
    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))


def windows_now() -> list[Shown]:
    """Every shown top-level window of the screen - not minimised nor cloaked, more than a pixel each way -, from the
    top of the order of the windows down. No title is read (the class only, to tell the desktop's own)."""
    import ctypes
    from ctypes import wintypes

    u, dwm = _user32(), _dwmapi()
    out: list[Shown] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _lparam):  # type: ignore[no-untyped-def]
        try:
            h = int(hwnd or 0)
            if not h or not u.IsWindowVisible(h) or u.IsIconic(h):
                return True
            cloaked = wintypes.DWORD(0)
            if dwm.DwmGetWindowAttribute(wintypes.HWND(h), 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 \
                    and cloaked.value:
                return True
            r = frame_rect(h)
            if r[2] - r[0] <= 1 or r[3] - r[1] <= 1:
                return True
            name = ctypes.create_unicode_buffer(32)
            u.GetClassNameW(h, name, 32)
            out.append(Shown(h, window_pid(h), r, name.value in DESKTOP_CLASSES))
        except Exception:  # noqa: BLE001 - a window gone meanwhile
            pass
        return True

    u.EnumWindows(each, 0)
    return out


def meets(a: Sequence[int], b: Sequence[int]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def foreign_windows(rects: Sequence[Sequence[int]], pids: set[int], shown: Sequence[Shown] | None = None
                    ) -> list[Shown]:
    """The shown windows of no process of *pids* that meet one of *rects* (screen px): above the stand-in or below
    it, click-through or not, the desktop's own left out."""
    shown = windows_now() if shown is None else shown
    return [w for w in shown if not w.desktop and w.pid not in pids and any(meets(w.rect, r) for r in rects)]


def monitor_areas() -> list[tuple[Box, bool]]:
    """The monitors' work areas (screen px, the process DPI aware as TASlation makes it) with whether each is the
    primary: the primary first, then by their left edge (as standin_e2e numbers them)."""
    import ctypes
    from ctypes import wintypes

    u = ctypes.WinDLL("user32")
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # (per monitor v2, as `enable_dpi_awareness` sets it)
    except (AttributeError, OSError):
        pass

    class Info(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    areas: list[tuple[Box, bool]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def each(handle, _dc, _rect, _lparam):  # type: ignore[no-untyped-def]
        info = Info()
        info.cbSize = ctypes.sizeof(Info)
        if u.GetMonitorInfoW(handle, ctypes.byref(info)):
            w = info.rcWork
            areas.append(((int(w.left), int(w.top), int(w.right), int(w.bottom)), bool(info.dwFlags & 1)))
        return True

    u.EnumDisplayMonitors(None, None, each, 0)
    areas.sort(key=lambda a: (not a[1], a[0][0], a[0][1]))
    return areas


def planned_place(size: str, monitor: int, areas: Sequence[tuple[Box, bool]] | None = None) -> Box:
    """Where the stand-in's window will lie (screen px): *size* at the top left of the work area of *monitor*, as
    standin_e2e places it with --standin-size and --standin-monitor."""
    areas = monitor_areas() if areas is None else areas
    if not 1 <= int(monitor) <= len(areas):
        raise SystemExit(f"there is no monitor {monitor} on this computer ({len(areas)} found)")
    (left, top, right, bottom), _primary = areas[int(monitor) - 1]
    w, h = (int(v) for v in str(size).lower().split("x"))
    return (left, top, left + min(w, right - left), top + min(h, bottom - top))


def front_pid() -> int:
    """The process of the window in front (0: none); no title is read."""
    import standin_viewer as sv

    return int(sv.foreground()[1])


def lock_foreground(on: bool) -> bool:
    """Windows' lock on changes of the window in front (`standin_viewer.lock_foreground`): taken only where any
    program could change it now (the person has given no input for a while), and lifted by their next key or click."""
    import standin_viewer as sv

    return sv.lock_foreground(on)


class ForegroundGuard:
    """While the recording runs, what TASlation could take the foreground with - `windows.give_foreground` wherever
    TASlation holds it, `see_menu._front`, Tk's ``focus -force`` - acts only while the window in front is already
    one of *ours* (this process's, the stand-in's): it is never taken from another program's window. What was not
    done is counted (`refused`)."""

    def __init__(self, ours: Callable[[], set[int]], front: Callable[[], int] = front_pid) -> None:
        self.ours, self.front = ours, front
        self.refused: Counter[str] = Counter()
        self._undo: list[Callable[[], Any]] = []

    def allowed(self) -> bool:
        try:
            return int(self.front()) in self.ours()
        except Exception:  # noqa: BLE001 - not known: not allowed
            return False

    def wrap(self, original: Callable[..., Any], name: str, refused: Any = False) -> Callable[..., Any]:
        def guarded(*a: Any, **k: Any) -> Any:
            if self.allowed():
                return original(*a, **k)
            self.refused[name] += 1
            return refused

        guarded.__wrapped__ = original  # type: ignore[attr-defined]
        return guarded

    def install(self) -> None:
        import tkinter

        import demo_video
        from taslation.capture import windows
        from taslation.ui import see_menu

        current = windows.give_foreground
        given = self.wrap(current, "give_foreground")
        demo_video.replace_everywhere(current, given)
        self._undo.append(lambda: demo_video.replace_everywhere(given, current))
        front = see_menu._front
        see_menu._front = self.wrap(front, "menu_front")
        self._undo.append(lambda: setattr(see_menu, "_front", front))
        force = tkinter.Misc.focus_force
        tkinter.Misc.focus_force = self.wrap(force, "focus_force", None)  # type: ignore[method-assign]
        self._undo.append(lambda: setattr(tkinter.Misc, "focus_force", force))

    def undo(self) -> None:
        while self._undo:
            self._undo.pop()()


class Run:
    """One recording: the recording file being written, what the frames' thread and the scenes note (numbers only),
    and the checks' verdicts. The frames' thread (`frames_loop`) belongs to the see-through watch of the stand-in run
    (`attach`); the scenes are acted on the run's loop (`chooser_program`, `scenes_program`)."""

    def __init__(self, out: Path, fps: float = RECORD_FPS):
        self.writer = pv.RecordingWriter(out, quality=JPEG_QUALITY)
        self.period = 1.0 / max(1.0, float(fps))
        self.fps = float(fps)
        self.on = threading.Event()
        self.ended = threading.Event()
        self.watch: Any = None
        self.director: Any = None
        self.browser: Any = None
        self.thread: threading.Thread | None = None
        self.down = False  # (the tool's pointer pressed: drawn with a ring)
        self.drag_box: Box | None = None  # (page-area px) the sweep of a drag, left out
        self.serials: tuple[int, ...] = ()  # the sets shown at the last two frames (their patches left out)
        self.crop_top = 0
        self.client: list[int] = []
        self.pointer: list[list[float]] = []  # [t, x, y, down] in the copy's px (x -1: none)
        self.panes: list[list[float]] = []  # [t, left box, right box] in the copy's px (-1: hidden)
        self.foot: list[list[float]] = []  # [t, the right pane's foot] in the copy's px (-1: none)
        self.scenes: list[dict[str, Any]] = []
        self.kept = 0
        self.refused: Counter[str] = Counter()
        self.refused_where: list[list[int]] = []
        self.in_a_row = 0
        self.failed = ""
        self.copy_ms: list[float] = []
        self.times: dict[str, float] = {}
        self.checks = 0  # the screen's windows looked at
        self.foreign = 0  # ... with a window of another program's on the stand-in
        self.foreign_where: list[list[int]] = []  # (their rectangles: numbers only)
        self.front: int | None = None  # the process in front at the last look
        self.fronts_taken = 0
        self.locked_at = float("-inf")
        self.guard: ForegroundGuard | None = None
        self.viewer_remembered = False

    def pids(self) -> set[int]:
        """Our processes: this one (TASlation's windows) and the stand-in browser's."""
        return {os.getpid(), *(int(p) for p in (getattr(self.browser, "tree", None) or ()))}

    # the scenes' marks
    def begin(self, scene_id: str) -> None:
        self.scenes.append({"id": scene_id, "t0": round(time.time() * 1000, 1), "t1": None, "fast": [], "failed": ""})

    def end(self, scene_id: str) -> None:
        entry = next(s for s in reversed(self.scenes) if s["id"] == scene_id)
        entry["t1"] = round(time.time() * 1000, 1)

    def fail(self, why: str) -> None:
        if not self.failed:
            self.failed = why
        for entry in self.scenes:
            if entry["t1"] is None:
                entry["t1"], entry["failed"] = round(time.time() * 1000, 1), why[:LONGEST_VALUE]

    # the frames
    def attach(self, watch: Any) -> None:
        self.watch = watch
        self.thread = threading.Thread(target=self.frames_loop, name="intro-frames", daemon=True)
        self.thread.start()

    def detach(self) -> None:
        self.on.clear()
        self.ended.set()
        if self.thread is not None:
            self.thread.join(5.0)

    def frames_loop(self) -> None:
        due = checked = time.monotonic()
        while not self.ended.is_set():
            now = time.monotonic()
            if self.failed:  # (nothing more is looked at: the take is given up)
                self.ended.wait(0.05)
                continue
            if not self.on.is_set():
                if now - checked >= CHECK_S:
                    checked = now
                    try:
                        self.check_screen()
                    except Exception:  # noqa: BLE001 - a look that failed is looked at again
                        pass
                self.ended.wait(0.02)
                due = time.monotonic()
                continue
            if now < due:
                self.ended.wait(min(0.01, due - now))
                continue
            due = max(due + self.period, now)  # (no burst to catch up)
            try:
                self.grab()
            except Exception as e:  # noqa: BLE001 - a frame that could not be taken is one refused
                self.refuse(f"{type(e).__name__} while taking a frame")

    def check_screen(self) -> list[Shown] | None:
        """The screen's windows looked at: the run fails (None) where a window of another program's meets the
        stand-in's window, or the foreground came to one of ours from another program's window; else the windows
        shown (Windows' lock on foreground changes asked for again every LOCK_EVERY_S meanwhile)."""
        watch = self.watch
        if watch is None:
            return []
        pids = self.pids()
        shown = windows_now()
        self.checks += 1
        found = foreign_windows([frame_rect(int(watch.hwnd))], pids, shown)
        if found:
            self.foreign += 1
            if len(self.foreign_where) < 10:
                self.foreign_where.append([int(v) for v in found[0].rect])
            self.fail(FOREIGN)
            return None
        front = front_pid()
        if self.front is not None and self.front not in pids and front in pids:
            self.fronts_taken += 1
            self.fail(TAKEN)
            return None
        self.front = front
        now = time.monotonic()
        if now - self.locked_at >= LOCK_EVERY_S:
            self.locked_at = now
            lock_foreground(True)
        return shown

    def grab(self) -> None:
        """One frame: the screen in the stand-in's client area, kept when the checks pass (see the module's notes)."""
        import standin_seethrough as ss

        from taslation.capture import seethrough as window
        from taslation.capture import windows

        watch = self.watch
        if watch is None:
            return
        shown = self.check_screen()
        if shown is None:
            return
        over = watch.over()
        cx, cy, cw, ch = windows._client_box(watch.hwnd)
        x, y, w, h = cx + EDGE, cy, cw - 2 * EDGE, ch - EDGE  # (the window's rounded bottom corners left out)
        mine = {s.hwnd: s.rect for s in shown if s.pid == os.getpid()}  # (TASlation's windows on the screen)
        started = time.perf_counter()
        point = watch.fake_point
        if over is None:  # (the viewer chooser, before the stand-in's window is captured: on the window checks)
            t = time.time() * 1000
            copy = ss.screen_copy(x, y, w, h)
            if self.check_screen() is None:
                del copy  # (never kept, never looked at again)
                return
            self.keep(t, copy, point, (x, y, w, h), None, started)
            return
        covers = window.cover_rects(watch.hwnd, (cx, cy, cx + cw, cy + ch), set(over.own_windows()) | set(mine))

        def cut(frame: Any) -> Any:
            return None if frame is None or frame.shape[:2] != (ch, cw) else frame[:h, EDGE:EDGE + w]

        before = cut(watch._viewer_frame())
        t = time.time() * 1000
        copy = ss.screen_copy(x, y, w, h)
        after = cut(watch._viewer_frame())
        masks = own_masks(over, x, y, self) + window_masks(mine, over, x, y)
        tiles, where = (-2, None) if covers else ss.foreign_tiles(copy, [before, after], masks)
        del before, after
        why = verdict(len(covers), tiles)
        if not why and self.check_screen() is None:
            del copy
            return
        if why:
            del copy  # (never kept, never looked at again)
            if where is not None and len(self.refused_where) < 20:
                self.refused_where.append([int(v) for v in where])  # (the squares' box: numbers only)
            self.refuse(why)
            return
        self.keep(t, copy, point, (x, y, w, h), over, started)

    def keep(self, t: float, copy: Any, point: tuple[int, int] | None, area: Box, over: Any, started: float) -> None:
        """A frame kept: its picture, the tool's pointer and (from the see-through window on) the panes and the right
        pane's foot where they were, in the copy's px."""
        x, y, w, h = area
        self.in_a_row = 0
        self.kept += 1
        self.writer.add(t, Image.fromarray(copy))
        self.copy_ms.append((time.perf_counter() - started) * 1000)
        self.client = [w, h]
        self.pointer.append([round(t, 1), *((point[0] - x, point[1] - y) if point is not None else (-1, -1)),
                             int(self.down)])
        if over is None:
            return
        boxes = []
        for side in ("left", "right"):
            b = over.pane_shown(side)
            boxes += [b[0] - x, b[1] - y, b[2] - x, b[3] - y] if b is not None else [-1, -1, -1, -1]
        if not self.panes or self.panes[-1][1:] != boxes:
            self.panes.append([round(t, 1), *boxes])
        f = foot_box(getattr(self.director, "app", None), over)
        foot = [f[0] - x, f[1] - y, f[2] - x, f[3] - y] if f is not None else [-1, -1, -1, -1]
        if not self.foot or self.foot[-1][1:] != foot:
            self.foot.append([round(t, 1), *foot])

    def refuse(self, why: str) -> None:
        self.refused[why] += 1
        self.in_a_row += 1
        if self.in_a_row >= REFUSED_IN_A_ROW:
            self.fail(f"{why}: {self.in_a_row} frames in a row")

    def meta(self, facts: dict[str, Any]) -> dict[str, Any]:
        copy_ms = sorted(self.copy_ms)
        return {"intro_format": FORMAT, "version": facts.get("version"), "facts": facts, "made_up": False,
                "client": self.client, "crop_top": self.crop_top, "scenes": self.scenes, "pointer": self.pointer,
                "panes": self.panes, "foot": self.foot,
                "check": {"kept": self.kept, "refused": dict(self.refused), "refused_where": self.refused_where,
                          "fps": self.fps, "windows_looked_at": self.checks, "foreign": self.foreign,
                          "fronts_taken": self.fronts_taken,
                          "foreground_refused": dict(self.guard.refused) if self.guard is not None else {},
                          "frame_ms_median": round(copy_ms[len(copy_ms) // 2], 1) if copy_ms else None},
                "screen_s": self.screen_s()}

    def screen_s(self) -> float | None:
        a, b = self.times.get("standin_started"), self.times.get("standin_closed")
        return round(b - a, 1) if a is not None and b is not None else None


RUN: Run | None = None  # the recording under way (`record`)


def verdict(covers: int, tiles: int) -> str:
    """Why a frame is refused ("" when it is kept): a window of another program's over the stand-in (*covers*),
    no frame of the stand-in's to tell it by (*tiles* -1), or squares of the copy that are neither the stand-in's own
    frame nor TASlation's drawing (*tiles* above 0)."""
    if covers:
        return "a window over the stand-in"
    if tiles < 0:
        return "no frame of the stand-in's to tell it by"
    if tiles > 0:
        return "another program's pixels"
    return ""


def own_masks(over: Any, x: int, y: int, run: Run | None = None) -> list[Box]:
    """Where TASlation's own see-through windows draw over the stand-in, in the copy's px (its client area at *x*,
    *y*): every patch of the set shown and of the one shown at the frame before (all of them, shown or given way: a
    look may change that between the copy and the frames it is told by), the panes, and while editing its boxes with
    their plates and handles (and the sweep of a drag); the check leaves those out."""
    from taslation import seethrough as st

    out: list[Box] = []
    shown = over.shown()
    look = getattr(over, "_last_look", None)
    origin = shown[2] if shown is not None else (look[5] if look is not None else None)
    if origin is not None:
        dx, dy = origin[0] - x, origin[1] - y
        with over._lock:
            sets = list(over._store.sets)
        serials = tuple(dict.fromkeys([*([shown[0]] if shown is not None else []),
                                       *(run.serials if run is not None else ())]))[:2]
        if run is not None:
            run.serials = serials
        for s in sets:
            if s.serial not in serials:
                continue
            for p in s.patches:
                b = p.box
                out.append((b[0] + dx - PATCH_PAD, b[1] + dy - PATCH_PAD, b[2] + dx + PATCH_PAD, b[3] + dy + PATCH_PAD))
        marks = getattr(over, "_marks_live", None)
        if marks is not None and getattr(over, "_edit_takes", False):
            e = st.scaled(EDIT_PAD, getattr(over, "_dpi", st.BASE_DPI))
            ghost = getattr(over, "_ghost", None)
            boxes = [*marks.boxes, *getattr(marks, "ghosts", ()), *(ghost[1] if ghost is not None else ())]
            if run is not None and run.drag_box is not None:
                boxes.append(run.drag_box)
            for b in boxes:
                out.append((b[0] + dx - e, b[1] + dy - e, b[2] + dx + e, b[3] + dy + e))
            for plate in getattr(marks, "plates", ()) or ():
                if plate is not None:
                    pixels, (px, py) = plate
                    ph, pw = pixels.shape[:2]
                    out.append((px + dx - PATCH_PAD, py + dy - PATCH_PAD, px + pw + dx + PATCH_PAD,
                                py + ph + dy + PATCH_PAD))
    for side in ("left", "right"):
        b = over.pane_shown(side)
        if b is not None:
            out.append((b[0] - x - PANE_PAD, b[1] - y - PANE_PAD, b[2] - x + PANE_PAD, b[3] - y + PANE_PAD))
    return out


def window_masks(mine: dict[int, Box], over: Any, x: int, y: int) -> list[Box]:
    """Where TASlation's other windows lie (this process's shown top-level windows *mine*, screen px: the viewer
    chooser, the region editor, a place entry, the list of languages), in the copy's px; not the lettering's own
    window, which lies over the whole client area while editing (what it draws is `own_masks`')."""
    skip = int(getattr(over, "hwnd", 0) or 0)
    return [(r[0] - x - OWN_PAD, r[1] - y - OWN_PAD, r[2] - x + OWN_PAD, r[3] - y + OWN_PAD)
            for hwnd, r in mine.items() if int(hwnd) != skip]


# the scenes, acted on the stand-in run's loop
def ease(u: float) -> float:
    return u * u * (3 - 2 * u)


def glide(run: Run, to: tuple[int, int], seconds: float) -> Iterator[Any]:
    """The tool's pointer moved to *to* (screen px) in *seconds*; it appears there when it was nowhere."""
    watch = run.watch
    start = watch.fake_point or to
    n = max(1, round(seconds / TICK_S))
    for k in range(1, n + 1):
        u = ease(k / n)
        watch.fake_point = (round(start[0] + (to[0] - start[0]) * u), round(start[1] + (to[1] - start[1]) * u))
        yield TICK_S


def post_raw(hwnd: int, message: int, wparam: int, lparam: int) -> None:
    """A message POSTED to one of TASlation's own windows (this process's): any other window is refused."""
    if not hwnd or window_pid(int(hwnd)) != os.getpid():
        raise SceneFailed("a message for a window that is not TASlation's")
    _user32().PostMessageW(int(hwnd), message, wparam, lparam)


def post(hwnd: int, message: int, wparam: int, x: int, y: int) -> None:
    """A mouse message POSTED to one of TASlation's own windows (its pane, its lettering): nothing else."""
    post_raw(hwnd, message, wparam, (int(y) & 0xFFFF) << 16 | (int(x) & 0xFFFF))


def final_set(over: Any) -> Any:
    """The set of patches shown when it is a finished page's (not one filling in), else None."""
    shown = over.shown()
    if shown is None:
        return None
    with over._lock:
        sets = list(over._store.sets)
    chosen = next((s for s in sets if s.serial == shown[0]), None)
    return chosen if chosen is not None and chosen.final else None


def page_done(director: Any, over: Any, before: int | None = None) -> bool:
    """The page on show finished (a finished set, two patches or more, of another serial than *before*) and the
    window at rest."""
    chosen = final_set(over)
    shown = over.shown()
    return (chosen is not None and shown is not None and len(shown[1]) >= 2
            and (before is None or chosen.serial != before) and director.idle())


def held(director: Any, n: int) -> bool:
    return any(e.get("ev") == "hold" and str(e.get("id")) == str(n) for e in director.events)


def release_hold(director: Any, n: int) -> None:
    import standin_viewer as sv

    director.control["hold"] = int(n)
    sv.write_control(director.standin_dir, director.control["go"], hold=int(n))


def crop_of(director: Any) -> int:
    """The rows of a copy above the stand-in's page: its own band (as it said when it drew the page) and above."""
    notes = director.notes
    return int(getattr(notes, "top", 0) + round(float(getattr(director, "band_px", 0) or 0) *
                                                float(getattr(notes, "dpr", 1.0) or 1.0)))


def pane_point(app: Any, over: Any, side: str, name: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Where the pane's control *name* is: (screen px, the pane's own px), or None."""
    memo = (getattr(app, "_see_pane_memo", None) or {}).get(side)
    box = over.pane_shown(side)
    hit = dict(memo[1].hits).get(name) if memo is not None and memo[1] is not None else None
    if box is None or hit is None:
        return None
    local = ((hit[0] + hit[2]) // 2, (hit[1] + hit[3]) // 2)
    return (box[0] + local[0], box[1] + local[1]), local


def foot_box(app: Any, over: Any) -> Box | None:
    """The right pane's foot on the screen (its rows' boxes together, `panes.Picture.foot`, of the column shown: the
    indicators', or the one with a bubble's block), or None."""
    if app is None or over is None:
        return None
    memo = (getattr(app, "_see_pane_memo", None) or {}).get(str(getattr(app, "_see_right_used", "right") or "right"))
    shown = over.pane_shown("right")
    foot = tuple(getattr(memo[1], "foot", ()) or ()) if memo is not None else ()
    if shown is None or not foot:
        return None
    return (shown[0] + min(b[0] for b in foot), shown[1] + min(b[1] for b in foot),
            shown[0] + max(b[2] for b in foot), shown[1] + max(b[3] for b in foot))


def click_pane(run: Run, over: Any, side: str, local: tuple[int, int]) -> Iterator[Any]:
    """A click POSTED to the pane's own window at *local* (its px), the tool's pointer drawn pressed meanwhile."""
    import standin_seethrough as ss

    pane = over.panes.get(side, 0)
    if not pane:
        raise SceneFailed(f"the {side} pane has no window")
    run.down = True
    post(pane, ss.WM_LBUTTONDOWN, ss.MK_LBUTTON, *local)
    yield 0.12
    post(pane, ss.WM_LBUTTONUP, 0, *local)
    run.down = False
    yield TICK_S


def click_at(run: Run, over: Any, point: tuple[int, int]) -> Iterator[Any]:
    """A click POSTED to the lettering's own window at *point* (page-area px), the pointer drawn pressed."""
    import standin_seethrough as ss

    over._edit_held = lambda: None  # (a posted press holds no button of the system's: not given up for that)
    run.down = True
    post(over.hwnd, ss.WM_LBUTTONDOWN, ss.MK_LBUTTON, *point)
    yield 0.1
    post(over.hwnd, ss.WM_LBUTTONUP, 0, *point)
    run.down = False
    yield TICK_S


def double_click_at(run: Run, over: Any, point: tuple[int, int]) -> Iterator[Any]:
    """A double click POSTED to the lettering's own window at *point*: two presses and releases at once, as
    `standin_seethrough.SeeWatch._edit_measure` posts them."""
    import standin_seethrough as ss

    over._edit_held = lambda: None
    run.down = True
    for _twice in range(2):
        post(over.hwnd, ss.WM_LBUTTONDOWN, ss.MK_LBUTTON, *point)
        post(over.hwnd, ss.WM_LBUTTONUP, 0, *point)
    yield 0.12
    run.down = False
    yield TICK_S


def double_click_s() -> float:
    """The system's double-click time, s."""
    from taslation.capture import seethrough as window

    return float(window.double_click()[0])


def menu_window() -> int:
    """TASlation's own popup menu on the screen (the list of languages), 0 while none is."""
    from taslation.capture import seethrough as window

    return int(window.own_menu() or 0)


def end_menu() -> None:
    """The list of languages ended as Windows ends a menu (`EndMenu`: the menu of the calling thread, the Tk
    thread's, where the scenes are acted); an Esc posted to the menu's own window after ESC_AFTER_S should it still
    be up."""
    import ctypes

    ctypes.WinDLL("user32").EndMenu()

    def escape() -> None:
        time.sleep(ESC_AFTER_S)
        hwnd = menu_window()
        if hwnd:
            post_raw(hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
            post_raw(hwnd, WM_KEYUP, VK_ESCAPE, 0)

    threading.Thread(target=escape, name="intro-menu-escape", daemon=True).start()


def biggest_patch(over: Any, panes: Sequence[tuple[int, ...]]) -> tuple[int, int, tuple[int, int]] | None:
    """The biggest patch shown whose middle is on no pane: (set serial, index, its middle in screen px)."""
    shown = over.shown()
    chosen = final_set(over)
    if shown is None or chosen is None:
        return None
    serial, indices, origin, _size = shown
    best = None
    for i in indices:
        b = chosen.patches[i].box
        middle = (origin[0] + (b[0] + b[2]) // 2, origin[1] + (b[1] + b[3]) // 2)
        if any(p[0] <= middle[0] < p[2] and p[1] <= middle[1] < p[3] for p in panes):
            continue
        area = (b[2] - b[0]) * (b[3] - b[1])
        if best is None or area > best[0]:
            best = (area, i, middle)
    return None if best is None else (serial, best[1], best[2])


def edit_settled(director: Any, over: Any) -> bool:
    """Editing, its boxes taking the mouse, no press held, no change being stored, the window at rest."""
    marks = getattr(over, "_marks_live", None)
    return (bool(getattr(over, "_edit_takes", False)) and marks is not None and not marks.locked
            and getattr(over, "_press", None) is None and getattr(over, "_last_look", None) is not None
            and director.idle())


def edit_ready(director: Any, over: Any) -> bool:
    """`edit_settled` on a finished page's set (not one filling in)."""
    return edit_settled(director, over) and final_set(over) is not None


def drag_box_pick(over: Any) -> tuple[int, Box] | None:
    """The biggest of Edit's boxes that the edit scene can take (its middle in no other box nor on a pane, room for
    the drag on the page): (index, box in page-area px)."""
    from taslation import seethrough as st

    look, marks = over._last_look, over._marks_live
    origin, size = look[5], look[6]
    dpi = getattr(over, "_dpi", st.BASE_DPI)
    dx, dy, least = st.scaled(DRAG[0], dpi), st.scaled(DRAG[1], dpi), st.scaled(MIN_BOX, dpi)
    panes = [b for b in (over.pane_shown(s) for s in ("left", "right")) if b is not None]
    best = None
    for i, b in enumerate(marks.boxes):
        if i in over._left_out or b[2] - b[0] < least or b[3] - b[1] < least:
            continue
        cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
        if any(j != i and o[0] <= cx < o[2] and o[1] <= cy < o[3] for j, o in enumerate(marks.boxes)):
            continue
        if b[2] + dx > size[0] or b[3] + dy > size[1]:
            continue
        if any(p[0] <= origin[0] + cx < p[2] and p[1] <= origin[1] + cy < p[3] for p in panes):
            continue
        area = (b[2] - b[0]) * (b[3] - b[1])
        if best is None or area > best[0]:
            best = (area, i, tuple(int(v) for v in b))
    return None if best is None else (best[1], best[2])  # type: ignore[return-value]


def box_near(over: Any, box: Sequence[int], px: int = 2) -> Box | None:
    marks = getattr(over, "_marks_live", None)
    if marks is None:
        return None
    return next((tuple(int(v) for v in o) for o in marks.boxes if max(abs(a - b) for a, b in zip(o, box)) <= px),
                None)  # type: ignore[return-value]


def index_near(over: Any, box: Sequence[int], px: int = 2) -> int | None:
    """The index of Edit's box within *px* of *box*, or None."""
    marks = getattr(over, "_marks_live", None)
    boxes = marks.boxes if marks is not None else ()
    return next((i for i, o in enumerate(boxes) if max(abs(a - b) for a, b in zip(o, box)) <= px), None)


def selected(app: Any, over: Any, index: int, box: Sequence[int]) -> bool:
    """The region of Edit's box *index* chosen, alone, its corner handles on it."""
    region = getattr(app, "_chosen_region", None)
    marks = getattr(over, "_marks_live", None)
    return (region is not None and tuple(int(v) for v in region.bbox) == tuple(int(v) for v in box)
            and marks is not None and tuple(marks.chosen) == (index,))


def plate_point(over: Any, index: int) -> tuple[int, int] | None:
    """The middle of the number plate of Edit's box *index* (page-area px), where a press takes the plate itself
    (`seethrough.edit_grip`: no corner of a box there); None where it has none."""
    from taslation import seethrough as st

    marks = getattr(over, "_marks_live", None)
    if marks is None or index >= len(marks.plates):
        return None
    plate = st.plate_box(marks.plates[index])
    if plate is None:
        return None
    point = ((plate[0] + plate[2]) // 2, (plate[1] + plate[3]) // 2)
    reach = st.scaled(st.GRIP_PX, getattr(over, "_dpi", st.BASE_DPI))
    return point if st.edit_grip(marks, point, reach, over._left_out) == (index, st.PLATE) else None


def ground_point(over: Any) -> tuple[int, int] | None:
    """A point of the page's empty ground (page-area px): no box, plate nor handle within 8 px, no pane on it."""
    from taslation import seethrough as st

    look, marks = over._last_look, over._marks_live
    origin, size = look[5], look[6]
    reach = st.scaled(st.GRIP_PX, getattr(over, "_dpi", st.BASE_DPI)) + 8
    panes = [b for b in (over.pane_shown(s) for s in ("left", "right")) if b is not None]
    plates = [p for p in (st.plate_box(q) for q in getattr(marks, "plates", ()) or ()) if p is not None]
    for x, y in ((size[0] // 2, size[1] - 8), (12, size[1] * 93 // 100), (size[0] - 12, size[1] * 93 // 100)):
        near = (x - reach, y - reach, x + reach, y + reach)
        if any(meets(near, b) for b in (*marks.boxes, *plates)):
            continue
        if any(p[0] <= origin[0] + x < p[2] and p[1] <= origin[1] + y < p[3] for p in panes):
            continue
        return x, y
    return None


def place_entry(app: Any) -> Any:
    """The place entry open over a number plate (`see_edit.PlaceEntry`), or None."""
    entry = getattr(app, "_see_place_entry", None)
    return entry if entry is not None and not getattr(entry, "closed", False) else None


def drag(run: Run, over: Any, box: Sequence[int], by: tuple[int, int]) -> Iterator[Any]:
    """Edit's box *box* (page-area px) dragged by *by*: a press, the moves and the release POSTED to the lettering's
    own window, the tool's pointer following (pressed); the box where it went is returned."""
    import standin_seethrough as ss

    origin = over._last_look[5]
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    over._edit_held = lambda: None  # (a posted press holds no button of the system's: not given up for that)
    run.down = True
    post(over.hwnd, ss.WM_LBUTTONDOWN, ss.MK_LBUTTON, cx, cy)
    yield 0.12
    n = max(2, round(DRAG_S / TICK_S))
    for k in range(1, n + 1):
        u = ease(k / n)
        ox, oy = round(by[0] * u), round(by[1] * u)
        post(over.hwnd, ss.WM_MOUSEMOVE, ss.MK_LBUTTON, cx + ox, cy + oy)
        run.watch.fake_point = (origin[0] + cx + ox, origin[1] + cy + oy)
        run.drag_box = (min(box[0], box[0] + ox), min(box[1], box[1] + oy), max(box[2], box[2] + ox),
                        max(box[3], box[3] + oy))
        yield TICK_S
    post(over.hwnd, ss.WM_LBUTTONUP, 0, cx + by[0], cy + by[1])
    run.down = False
    yield TICK_S
    return (box[0] + by[0], box[1] + by[1], box[2] + by[0], box[3] + by[1])


def names_browser(text: str) -> bool:
    """Whether *text* (a window as a list names it) names a browser in one of its parts ("<tab> - <browser>")."""
    from taslation.capture import windows

    return any(windows._is_browser_name(part) for part in windows.SEPARATOR.split(str(text or "")) if part.strip())


def listed(dialog: Any, hwnd: int) -> int | None:
    """Where the window *hwnd* is in the viewer chooser's list, or None."""
    return next((i for i, w in enumerate(getattr(dialog, "windows", ()) or ()) if int(w.hwnd) == int(hwnd)), None)


def widget_box(widget: Any) -> Box | None:
    """A Tk widget's box on the screen, or None (gone)."""
    try:
        x, y = int(widget.winfo_rootx()), int(widget.winfo_rooty())
        return (x, y, x + int(widget.winfo_width()), y + int(widget.winfo_height()))
    except Exception:  # noqa: BLE001 - (gone meanwhile)
        return None


def middle(box: Sequence[int]) -> tuple[int, int]:
    return ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)


def chooser_program(director: Any, run: Run, dialog: Any) -> Iterator[Any]:
    """The viewer chooser as the first scene: the tool's pointer to its list - the stand-in preselected in it, as the
    viewer chosen before (`remember_viewer`) - and to OK, and the chooser answered through its own object as
    standin_e2e answers it (the stand-in's entry, OK: no input, no window activated). It fails where the stand-in is
    not preselected, the chooser lies off the stand-in's client area, or the list names the stand-in's browser."""
    from taslation.capture import taskbar_title
    from taslation.capture import windows

    app, hwnd = director.app, int(director.browser.hwnd)
    yield (lambda: run.watch is not None and listed(dialog, hwnd) is not None, CHOOSER_S,
           "the stand-in listed in the viewer chooser")
    for _ in range(round(3.0 / TICK_S)):  # (the stand-in's band, as it said when it drew its page)
        if getattr(director, "band_px", 0):
            break
        yield TICK_S
    at = listed(dialog, hwnd)
    if at is None:
        raise SceneFailed("the stand-in left the viewer chooser")
    if names_browser(taskbar_title(dialog.windows[at])) or names_browser(str(dialog.box.get())):
        raise SceneFailed("the viewer chooser names the stand-in's browser")
    if dialog.box.current() != at:
        raise SceneFailed("the stand-in is not preselected in the viewer chooser")
    cx, cy, cw, ch = windows._client_box(hwnd)
    box = widget_box(dialog)
    if box is None or not (cx <= box[0] and cy <= box[1] and box[2] <= cx + cw and box[3] <= cy + ch):
        raise SceneFailed("the viewer chooser is not over the stand-in")
    row = {"t": time.time() * 1000, "dialog": id(dialog), "listed": len(dialog.windows), "preselected_standin": True,
           "ok_greyed": bool(dialog.ok_button.instate(["disabled"])), "answered_t": None, "activated": False}
    rows = getattr(director, "chooser_rows", None)
    if isinstance(rows, list):
        rows.append(row)
    run.crop_top = crop_of(director)
    list_box, ok_box = widget_box(dialog.box), widget_box(dialog.ok_button)
    if list_box is None or ok_box is None:
        raise SceneFailed("the viewer chooser has gone")
    run.watch.fake_point = (middle(box)[0], min(box[3] + 60, cy + ch - EDGE - 12))
    run.begin("chooser")
    run.on.set()
    yield 1.0
    yield from glide(run, middle(list_box), 0.7)
    yield 0.9
    yield from glide(run, middle(ok_box), 0.6)
    yield 0.35
    run.down = True
    yield 0.12
    dialog.box.current(at)
    dialog._picked()
    dialog.ok()
    row["answered_t"] = time.time() * 1000
    run.down = False
    yield (lambda: getattr(app, "selected", None) is not None and getattr(app, "_see_chooser", None) is None, 10.0,
           "the stand-in chosen as the viewer")
    yield 1.0
    run.end("chooser")
    run.on.clear()
    run.watch.fake_point = None


def scenes_program(director: Any, run: Run) -> Iterator[Any]:
    """The scenes after the chooser on the stand-in run's loop: each step yields a wait - seconds, or (until, at most
    seconds, what) - and raises `SceneFailed` where what it needs is not there."""
    from taslation import seethrough as st
    from taslation.ui import see_edit
    from taslation.ui import seethrough as see_ui

    app = director.app

    def over() -> Any:
        o = run.watch.over() if run.watch is not None else None
        if o is None:
            raise SceneFailed("the see-through window is gone")
        return o

    def first_page() -> bool:  # (the see-through window may not be made yet)
        o = run.watch.over() if run.watch is not None else None
        return o is not None and held(director, 1) and page_done(director, o)

    def screen(o: Any, point: Sequence[int]) -> tuple[int, int]:
        origin = o._last_look[5]
        return int(origin[0] + point[0]), int(origin[1] + point[1])

    yield (first_page, FIRST_PAGE_S, "the first page translated")
    yield (lambda: edit_ready(director, over()), PAGE_S, "editing, the page's boxes")  # (TASlation starts editing)
    yield 1.0
    run.crop_top = crop_of(director)
    o = over()
    left, right = o.pane_shown("left"), o.pane_shown("right")
    if left is None or right is None:
        raise SceneFailed("a side pane has no room beside the page")
    run.watch.fake_point = ((left[0] + left[2]) // 2, max(left[1] - 24, 0))
    run.on.set()
    yield 0.4

    # Reader mode checked: the page's boxes go
    run.begin("reader")
    yield 1.4
    at = pane_point(app, over(), "left", "edit")
    if at is None:
        raise SceneFailed("no Reader mode in the left pane")
    yield from glide(run, at[0], 0.8)
    yield 0.3
    yield from click_pane(run, over(), "left", at[1])
    yield (lambda: not getattr(over(), "_edit_takes", False) and see_edit.reader_mode(app) and director.idle(), 15.0,
           "Reader mode")
    yield 1.4
    run.end("reader")

    # a page turned, filling in
    run.begin("turn")
    yield 0.6
    first = final_set(over())
    before = first.serial if first is not None else None
    since = len(director.events)
    release_hold(director, 1)
    yield (lambda: any(e.get("ev") == "draw" and e.get("why") == "next" for e in director.events[since:]), 10.0,
           "the stand-in's turn")
    yield (lambda: page_done(director, over(), before), PAGE_S, "the page turned to, translated")
    yield 1.5
    run.end("turn")

    # the side panes
    o = over()
    left, right = o.pane_shown("left"), o.pane_shown("right")
    if left is None or right is None:
        raise SceneFailed("a side pane has no room beside the page")
    run.begin("panes")
    yield 0.3
    for name in ("translate", "auto", "language", "lettering", "indicators", "edit"):
        at = pane_point(app, o, "left", name)
        if at is not None:
            yield from glide(run, at[0], 0.35)
            yield 0.25
    yield from glide(run, ((right[0] + right[2]) // 2, (right[1] + right[3]) // 2), 0.9)
    yield 1.2
    run.end("panes")

    # the right pane's foot
    run.begin("foot")
    foot = foot_box(app, over())
    if foot is None:
        raise SceneFailed("the right pane shows no foot")
    yield from glide(run, (foot[0] + (foot[2] - foot[0]) // 3, (foot[1] + foot[3]) // 2), 0.7)
    yield 2.4
    run.end("foot")

    # the list of languages beside the left pane, closed with no change
    run.begin("language")
    language = see_ui.target(app)
    at = pane_point(app, over(), "left", "language")
    if at is None:
        raise SceneFailed("no language in the left pane")
    yield from glide(run, at[0], 0.9)
    yield 0.3
    yield from click_pane(run, over(), "left", at[1])
    yield (lambda: menu_window() != 0, 5.0, "the list of languages")
    yield 2.2
    end_menu()
    yield (lambda: menu_window() == 0, ESC_AFTER_S + 3.0, "the list of languages closed")
    if see_ui.target(app) != language:
        raise SceneFailed("the target language changed")
    yield 1.0
    run.end("language")

    # the original under the pointer, the bubble's block in the right pane
    run.begin("original")
    o = over()
    picked = biggest_patch(o, [b for b in (o.pane_shown("left"), o.pane_shown("right")) if b is not None])
    if picked is None:
        raise SceneFailed("no bubble lettered on the page")
    serial, index, spot = picked
    yield from glide(run, spot, 0.9)
    yield float(getattr(o, "_hover_delay", 0.0) or 0.0) + HOVER_REST_S  # (resting past the hover delay)
    yield (lambda: (lambda s: s is not None and s[0] == serial and index not in s[1])(over().shown())
           and getattr(app, "_see_right_used", "") == "bubble", 4.0, "the original under the pointer")
    yield 2.0
    right = over().pane_shown("right") or right
    yield from glide(run, ((right[0] + right[2]) // 2, right[1] + min(60, (right[3] - right[1]) // 4)), 0.8)
    yield 1.6
    run.end("original")

    # editing: a click selects a box, a double click opens the region editor, a drag moves it, its number plate
    run.begin("edit")
    at = pane_point(app, over(), "left", "edit")
    if at is None:
        raise SceneFailed("no Reader mode in the left pane")
    yield from glide(run, at[0], 0.8)
    yield 0.3
    yield from click_pane(run, over(), "left", at[1])
    yield (lambda: edit_ready(director, over()), PAGE_S, "editing, the page's boxes")
    yield 1.0
    o = over()
    picked_box = drag_box_pick(o)
    if picked_box is None:
        raise SceneFailed("no box the scene can take")
    index, box = picked_box
    inside = middle(box)
    yield from glide(run, screen(o, inside), 0.8)
    yield 0.4
    yield from click_at(run, o, inside)
    clicked = time.monotonic()
    yield (lambda: selected(app, over(), index, box), 10.0, "the box selected, its handles")
    yield 1.4
    rest = double_click_s() + 0.2 - (time.monotonic() - clicked)  # (no double click with the click before)
    if rest > 0:
        yield rest
    yield from double_click_at(run, over(), inside)
    yield (lambda: run.watch._editor_window() != 0, 20.0, "the region editor")
    yield 2.4
    post_raw(run.watch._editor_window(), WM_CLOSE, 0, 0)
    yield (lambda: run.watch._editor_window() == 0 and edit_settled(director, over()), 15.0,
           "the region editor closed")
    yield 0.8
    o = over()
    dpi = getattr(o, "_dpi", st.BASE_DPI)
    by = (st.scaled(DRAG[0], dpi), st.scaled(DRAG[1], dpi))
    to = yield from drag(run, o, box, by)
    yield (lambda: box_near(over(), to) is not None and edit_settled(director, over()), PAGE_S,
           "the box moved, the page lettered again")
    yield 1.6
    run.drag_box = None
    moved = box_near(over(), to)
    back = yield from drag(run, over(), moved, (-by[0], -by[1]))
    yield (lambda: box_near(over(), back) is not None and edit_settled(director, over()), PAGE_S,
           "the box back, the page lettered again")
    yield 1.0
    run.drag_box = None
    o = over()
    where = index_near(o, back)
    plate = plate_point(o, where) if where is not None else None
    if plate is None:
        raise SceneFailed("no number plate the scene can click")
    yield from glide(run, screen(o, plate), 0.6)
    yield 0.3
    yield from click_at(run, o, plate)
    yield (lambda: place_entry(app) is not None, 5.0, "the place entry")
    yield 0.5  # (an entry that never gets the keys goes by itself after see_edit.PLACE_FOCUS_S)
    ground = ground_point(over())
    if ground is None:
        raise SceneFailed("no empty ground on the page")
    yield from glide(run, screen(over(), ground), 0.35)
    yield from click_at(run, over(), ground)
    yield (lambda: place_entry(app) is None and edit_settled(director, over()), 5.0, "the place entry given up")
    yield 1.2
    run.end("edit")
    run.on.clear()
    run.watch.fake_point = None
    yield 0.2


class Act:
    """A program of waits (`chooser_program`, `scenes_program`) acted a step at each tick of the run's loop."""

    def __init__(self, program: Iterator[Any]) -> None:
        self.program = program
        self.waiting: tuple[Any, ...] | None = None
        self.until = 0.0

    def advance(self) -> bool:
        """One tick's step: whether the program has ended. Raises `SceneFailed` (its own, or a wait that timed out)."""
        if self.waiting is not None and not self.waited():
            return False
        try:
            got = next(self.program)
        except StopIteration:
            return True
        if isinstance(got, (int, float)):
            self.waiting, self.until = ("time", None, ""), time.monotonic() + float(got)
        else:
            until, limit, what = got
            self.waiting, self.until = ("until", until, what), time.monotonic() + float(limit)
        return False

    def waited(self) -> bool:
        kind, until, what = self.waiting  # type: ignore[misc]
        if kind == "time":
            return time.monotonic() >= self.until
        if until():
            return True
        if time.monotonic() >= self.until:
            raise SceneFailed(f"timed out: {what}")
        return False


def director_class(e2e: Any) -> type:
    """standin_e2e's Director with the viewer chooser acted as a scene (`chooser_program`, in place of its own answer
    to it) and the other scenes (`scenes_program`) in place of its scenarios once its first release is made; the run
    ends when the scenes are done, or stops when one fails or a check stopped it."""

    class IntroDirector(e2e.Director):
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            self.act: Act | None = None
            self.pre: Act | None = None
            self.chosen = False
            if RUN is not None:
                RUN.director = self

        def chooser_step(self) -> None:
            run = RUN
            if run is None or self.over:
                return
            if self.pre is None:
                dialog = getattr(self.app, "_see_chooser", None)
                if dialog is None or self.chosen:
                    return
                self.pre = Act(chooser_program(self, run, dialog))
            try:
                done = self.pre.advance()
            except SceneFailed as e:
                run.fail(str(e))
                self.stop(run.failed)
                return
            if done:
                self.pre, self.chosen = None, True

        def step(self) -> None:
            run = RUN
            if run is None or self.over:
                return
            if run.failed:
                self.stop(run.failed)
                return
            if self.act is None:
                super().step()
                if SCENARIO in self.released and self.phase == "running" and not self.over:
                    self.act = Act(scenes_program(self, run))
                return
            try:
                done = self.act.advance()
            except SceneFailed as e:
                run.fail(str(e))
                self.stop(run.failed)
                return
            if done:
                self.finish()

        def stop(self, why: str) -> None:
            if RUN is not None:
                RUN.on.clear()  # (no frame is taken while the window closes)
                if why != "done":
                    RUN.fail(why)
            super().stop(why)

    return IntroDirector


def watch_class(ss: Any) -> type:
    """standin_seethrough's SeeWatch with its own measures that would move the tool's pointer or click a pane left
    out (the scenes do that), and the recording's frames' thread with it."""

    class IntroWatch(ss.SeeWatch):
        def _click_lettering(self) -> None:
            self.pane_click = {"left_to": "intro_video"}

        def _hover_safe(self) -> None:
            self.hover = {"left_to": "intro_video"}

        def _edit_safe(self) -> None:
            self.edit_result = {"left_to": "intro_video"}

        def start(self) -> None:
            super().start()
            if RUN is not None:
                RUN.attach(self)

        def close(self) -> None:
            if RUN is not None:
                RUN.detach()
            super().close()

    return IntroWatch


def remember_viewer(state: Path, hwnd: int) -> bool:
    """The stand-in's window remembered as the viewer chosen before, in the run's scratch state (its viewers.json,
    `viewerparts`): the viewer chooser then lists it first, preselected, and comes centred over it - on the
    stand-in's monitor, in the recording - as it comes over a viewer chosen before. Its title only (its program is
    every browser window's). Whether it was remembered."""
    import standin_viewer as sv

    from taslation import viewerparts
    from taslation.capture import windows

    title = " ".join(windows.tab_title(sv.window_text(int(hwnd)), sv.window_class(int(hwnd))).split())
    if not title:
        return False
    viewerparts.use(Path(state))
    viewerparts.change(lambda memory: memory.remember(title))
    return True


def e2e_argv(args: argparse.Namespace, work: Path) -> list[str]:
    """The stand-in run's command line: this tool's scenario, the stand-in sharp at once, its window's size and
    monitor, the translator's server started on a port of its own, TASlation starting editing and asking for the
    viewer (its flags last)."""
    argv = ["--out", str(work), "--scenario", SCENARIO, "--soft-first", "off", "--standin-size", args.standin_size,
            "--standin-monitor", str(args.standin_monitor), "--browser", args.browser, "--series", str(args.series),
            "--first", str(args.first), "--start-ollama", str(args.start_ollama)]
    if args.models:
        argv += ["--models", args.models]
    return [*argv, "--editing", "--chooser"]


def clean_place(args: argparse.Namespace) -> Box:
    """The stand-in's place (`planned_place`) when no window of another program lies on it nor within PLACE_MARGIN of
    it; else SystemExit (nothing has started: no clean place, no recording)."""
    place = planned_place(args.standin_size, args.standin_monitor)
    m = PLACE_MARGIN
    found = foreign_windows([(place[0] - m, place[1] - m, place[2] + m, place[3] + m)], {os.getpid()})
    if found:
        raise SystemExit(f"no clean place for the stand-in: {len(found)} window(s) of other programs lie on its place "
                         f"{list(place)} (monitor {args.standin_monitor}); nothing was started")
    return place


def record(args: argparse.Namespace) -> int:
    """The recording (see the module's notes); what was made, said as JSON."""
    global RUN
    if sys.platform != "win32":
        raise SystemExit("record needs Windows (the stand-in run)")
    out = pv.check_scratch_path(args.out)
    if out.suffix.lower() != ".zip":
        raise SystemExit("--out is a .zip")
    if out.exists():
        raise SystemExit(f"{out} is there already")
    if int(args.start_ollama) == pv.DEFAULT_PORT:
        raise SystemExit(f"--start-ollama {pv.DEFAULT_PORT} is Ollama's usual port: give one where nothing answers")
    work = out.with_name(out.stem + "-run")
    if work.exists():
        raise SystemExit(f"{work} is there from a run before: delete it, or give another --out")
    place = clean_place(args)
    out.parent.mkdir(parents=True, exist_ok=True)
    import demo_video
    import standin_e2e as e2e
    import standin_seethrough as ss
    import standin_viewer as sv

    e2e.SCENARIOS[SCENARIO] = ("the README's introduction (tools/intro_video.py)", list(SCRIPT))
    if SCENARIO not in e2e.NAMED_ONLY:
        e2e.NAMED_ONLY = (*e2e.NAMED_ONLY, SCENARIO)
    run = RUN = Run(out, args.fps)
    guard = run.guard = ForegroundGuard(run.pids)
    e2e.Director = director_class(e2e)
    ss.SeeWatch = watch_class(ss)
    browser_init, browser_close = sv.StandinBrowser.__init__, sv.StandinBrowser.close
    scratch_state = demo_video.scratch_state

    def started(self: Any, *a: Any, **k: Any) -> None:
        run.times.setdefault("standin_started", time.monotonic())
        run.browser = self
        browser_init(self, *a, **k)

    def closed(self: Any, *a: Any, **k: Any) -> Any:
        try:
            return browser_close(self, *a, **k)
        finally:
            run.times["standin_closed"] = time.monotonic()

    def state_made() -> Path:  # (the run's scratch state, just before TASlation's window is made)
        state = scratch_state()
        if run.browser is not None and getattr(run.browser, "hwnd", None):
            run.viewer_remembered = remember_viewer(state, int(run.browser.hwnd))
        guard.install()
        return state

    sv.StandinBrowser.__init__, sv.StandinBrowser.close = started, closed  # type: ignore[method-assign]
    demo_video.scratch_state = state_made
    try:
        code = e2e.main(e2e_argv(args, work))
    except BaseException:
        run.writer.abandon()
        clear_run_folder(work, args.keep_run)
        raise
    finally:
        run.detach()
        guard.undo()
        lock_foreground(False)
        demo_video.scratch_state = scratch_state
        sv.StandinBrowser.__init__, sv.StandinBrowser.close = browser_init, browser_close  # type: ignore[method-assign]
        RUN = None
    facts = code_facts()
    done = [s for s in run.scenes if s["t1"] is not None and not s["failed"]]
    director_failed = str(getattr(run.director, "failed", "") or "") if run.director is not None else "no run"
    ok = not run.failed and not director_failed and len(done) == len(SCENES)
    meta = run.meta(facts)
    check_no_text(meta)
    fronts = getattr(run.watch, "fronts", None) or []
    report = {"recording": str(out), "kept": run.kept, "refused": dict(run.refused),
              "refused_where": run.refused_where, "screen_s": meta["screen_s"],
              "frame_ms_median": meta["check"]["frame_ms_median"],
              "standin_place": list(place), "standin_monitor": args.standin_monitor,
              "viewer_remembered": run.viewer_remembered,
              "windows_looked_at": run.checks, "foreign_windows": run.foreign, "foreign_where": run.foreign_where,
              "fronts_taken": run.fronts_taken, "foreground_refused": dict(guard.refused),
              "scenes": [{"id": s["id"], "seconds": round((s["t1"] - s["t0"]) / 1000, 1) if s["t1"] else None,
                          "failed": s["failed"]} for s in run.scenes],
              # (who had the foreground: just before TASlation's window was made, then each change while it ran)
              "front_before_start": getattr(run.watch, "front_before_who", None),
              "fronts": [str(w) for _t, w in fronts][:12],
              "stand_in_run_exit": code,
              "failed": run.failed or director_failed or ("" if ok else "a scene was not acted")}
    if ok:
        run.writer.finish(meta)
    else:
        run.writer.abandon()
        report["recording"] = None
    report["run_folder_deleted"] = clear_run_folder(work, args.keep_run)
    print(json.dumps(report, indent=1, default=str))
    return 0 if ok else 1


def clear_run_folder(work: Path, keep_report: bool) -> bool:
    """The stand-in run's scratch folder deleted (its state, the stand-in's profile, its pictures); with
    *keep_report* its report.json (numbers only) stays. Whether the folder is gone."""
    if keep_report and (work / "report.json").is_file():
        for child in work.iterdir():
            if child.name != "report.json":
                shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
        return False
    shutil.rmtree(work, ignore_errors=True)
    return not work.exists()


# ---------------------------------------------------------------------------------------------------- the sources
class Source:
    """What a GIF is made from: the recording's facts (`meta`) and its pictures by name."""

    meta: dict[str, Any]

    def __init__(self) -> None:
        self.frames: list[tuple[float, str]] = []
        self.frame_times: list[float] = []
        self.pointer: list[list[float]] = []
        self.pointer_times: list[float] = []
        self.panes: list[list[float]] = []
        self.pane_times: list[float] = []
        self.foot: list[list[float]] = []
        self.foot_times: list[float] = []
        self._cache: OrderedDict[str, Image.Image] = OrderedDict()

    def index(self) -> None:
        meta = self.meta
        self.frames = [(float(t), str(n)) for t, n in meta.get("frames", [])]
        self.frame_times = [t for t, _ in self.frames]
        self.pointer = sorted(meta.get("pointer", []), key=lambda p: p[0])
        self.pointer_times = [float(p[0]) for p in self.pointer]
        self.panes = sorted(meta.get("panes", []), key=lambda p: p[0])
        self.pane_times = [float(p[0]) for p in self.panes]
        self.foot = sorted(meta.get("foot", []), key=lambda p: p[0])
        self.foot_times = [float(p[0]) for p in self.foot]

    def load(self, name: str) -> Image.Image:
        raise NotImplementedError

    def image(self, name: str) -> Image.Image:
        if name in self._cache:
            self._cache.move_to_end(name)
            return self._cache[name]
        image = self.load(name).convert("RGB")
        self._cache[name] = image
        while len(self._cache) > 6:
            self._cache.popitem(last=False)
        return image

    def frame_at(self, t: float) -> str | None:
        i = bisect.bisect_right(self.frame_times, t) - 1
        return self.frames[max(0, i)][1] if self.frames else None

    def pointer_at(self, t: float) -> tuple[int, int, bool] | None:
        i = bisect.bisect_right(self.pointer_times, t) - 1
        if i < 0:
            return None
        p = self.pointer[i]
        return None if p[1] < 0 else (int(p[1]), int(p[2]), bool(p[3]))

    def panes_at(self, t: float) -> tuple[tuple[int, int, int, int], ...]:
        """The side panes shown at *t* (the copy's px)."""
        i = bisect.bisect_right(self.pane_times, t) - 1
        if i < 0:
            return ()
        p = [int(v) for v in self.panes[i][1:]]
        return tuple(tuple(p[k:k + 4]) for k in (0, 4) if p[k] >= 0)  # type: ignore[misc]

    def foot_at(self, t: float) -> tuple[tuple[int, int, int, int], ...]:
        """The right pane's foot shown at *t* (the copy's px): one box, or none."""
        i = bisect.bisect_right(self.foot_times, t) - 1
        if i < 0:
            return ()
        p = [int(v) for v in self.foot[i][1:5]]
        return (tuple(p),) if p[0] >= 0 else ()  # type: ignore[return-value]

    def close(self) -> None:
        pass


class ZipSource(Source):
    def __init__(self, path: Path):
        super().__init__()
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self.meta = json.loads(self.zip.read("meta.json"))
        if self.meta.get("intro_format") != FORMAT:
            raise SystemExit(f"{path} is no recording of this tool's (recordings of TASlation's own window, before "
                             "2.0.0, are not made into a GIF any more)")
        kept = set(self.zip.namelist())
        self.meta["frames"] = [f for f in self.meta.get("frames", []) if f[1] in kept]
        self.index()

    def load(self, name: str) -> Image.Image:
        return Image.open(io.BytesIO(self.zip.read(name)))

    def close(self) -> None:
        self.zip.close()


class MemorySource(Source):
    def __init__(self, meta: dict[str, Any], images: dict[str, Image.Image]):
        super().__init__()
        self.meta, self.images = meta, images
        self.index()

    def load(self, name: str) -> Image.Image:
        return self.images[name]


SAMPLE_CLIENT = (800, 440)  # the made-up stand-in's client area


def made_up_panes(size: tuple[int, int]) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Where the made-up frames draw their two side panes (left, right)."""
    w, h = size
    s = w / 720
    bar = max(12, round(44 * s))
    return ((round(10 * s), bar + round(24 * s), round(110 * s), bar + round(220 * s)),
            (w - round(110 * s), bar + round(24 * s), w - round(10 * s), bar + round(160 * s)))


def sample_source(scene_ids: Sequence[str] | None = None, seconds: float = 4.0, fps: float = 5.0) -> MemorySource:
    """Made-up recordings of every scene present (or of *scene_ids*): drawn frames (`promo_video.made_up_window`,
    marked MADE-UP FRAMES, with two drawn panes), bubbles lettered one by one in the page's turn, a pointer; no window,
    no model, no manga page."""
    facts = code_facts()
    chosen = [s for s in SCENES if (scene_ids is None and s.present()) or (scene_ids is not None and s.id in scene_ids)]
    size = SAMPLE_CLIENT
    t = 1_700_000_000_000.0
    images: dict[str, Image.Image] = {}
    frames: list[list[Any]] = []
    left, right = made_up_panes(size)
    foot = (right[0], right[3] - (right[3] - right[1]) // 4, right[2], right[3])
    meta: dict[str, Any] = {"intro_format": FORMAT, "version": facts["version"], "facts": facts, "made_up": True,
                            "client": list(size), "crop_top": max(12, round(44 * size[0] / 720)), "scenes": [],
                            "pointer": [], "panes": [[t, *left, *right]], "foot": [[t, *foot]],
                            "check": {"kept": 0, "refused": {}}}
    step = 1000.0 / fps
    count = max(3, int(seconds * fps))
    for k, scene in enumerate(chosen):
        page = k + 1
        t0 = t
        for i in range(count):
            lettered = min(6, (i * 7) // count) if scene.id == "turn" else 6
            name = f"frames/{page:02d}-{lettered}.jpg"
            if name not in images:
                image = pv.made_up_window(size, page, 6, lettered, False, f"Made-up step: {scene.id}")
                draw = ImageDraw.Draw(image)
                for box in (left, right):
                    draw.rectangle(box, fill=(52, 54, 60))
                draw.rectangle(foot, fill=(66, 68, 74))
                if scene.id == "chooser":  # (a made-up dialog in the middle, as the chooser comes over the viewer)
                    w, h = size
                    draw.rectangle((w // 3, h // 3, 2 * w // 3, 2 * h // 3), fill=(240, 240, 240), outline=(90, 90, 90))
                images[name] = image
            frames.append([round(t, 1), name])
            u = i / max(1, count - 1)
            meta["pointer"].append([round(t, 1), int(size[0] * (0.2 + 0.6 * u)), int(size[1] * (0.3 + 0.4 * u)),
                                    int(i == count // 2)])
            t += step
        meta["scenes"].append({"id": scene.id, "t0": round(t0, 1), "t1": round(t, 1), "fast": [], "failed": ""})
        t += 500.0
    meta["frames"] = frames
    return MemorySource(meta, images)


# ---------------------------------------------------------------------------------------------------- the plan
@dataclass
class Part:
    """A stretch of the GIF: a card, or a scene's real time shown through *segments* (real start, real end, speed,
    whether it is a stretch shown faster)."""

    kind: str
    ms: float
    card: str = ""
    entry: dict[str, Any] | None = None
    scene: Scene | None = None
    number: int = 0
    segments: list[tuple[float, float, float, bool]] = field(default_factory=list)
    factor: float = 1.0

    @property
    def id(self) -> str:
        return self.card if self.kind == "card" else self.entry["id"]  # type: ignore[index]

    def real(self, local_ms: float) -> tuple[float, bool]:
        """The real time shown at *local_ms* into the scene, and whether that stretch is shown faster."""
        shown = 0.0
        for a, b, f, fast in self.segments:
            length = (b - a) / f
            if local_ms < shown + length:
                return a + (local_ms - shown) * f, fast and f > 1.05
            shown += length
        last = self.segments[-1] if self.segments else (0.0, 0.0, 1.0, False)
        return last[1], False


def changes_of(source: Source, t0: float, t1: float) -> list[float]:
    """The times something changed in [t0, t1]: the screen's picture, the pointer, the panes."""
    out: list[float] = []
    last = None
    for t, name in source.frames:
        if t0 <= t <= t1 and name != last:
            out.append(t)
        last = name
    out += [float(p[0]) for p in source.pointer if t0 <= p[0] <= t1]
    out += [t for t in source.pane_times if t0 <= t <= t1]
    return sorted(set(out))


def scene_segments(entry: dict[str, Any], changes: Sequence[float], budget_ms: float, longest_ms: float,
                   max_speed: float = MAX_SPEED) -> tuple[list[tuple[float, float, float, bool]], float]:
    """The scene's real time as shown: a wait with nothing changing longer than *longest_ms* cut to that, and the
    stretches marked as waiting (``fast``) shown *f* times faster, f = max(1, R / max(budget - S, 0.3 budget))
    (R: those stretches' time, S: the rest's), to a tenth, at most *max_speed*."""
    t0, t1 = float(entry["t0"]), float(entry["t1"])
    points = sorted({t0, t1, *[c for c in changes if t0 < c < t1]})
    kept: list[list[float]] = []
    for a, b in zip(points, points[1:]):
        pieces = [(a, b)] if b - a <= longest_ms else [(a, a + longest_ms / 2), (b - longest_ms / 2, b)]
        for p, q in pieces:
            if kept and abs(kept[-1][1] - p) < 1e-6:
                kept[-1][1] = q
            else:
                kept.append([p, q])
    spans = [(max(t0, float(a)), min(t1, float(b if b is not None else t1))) for a, b in entry.get("fast", [])]
    spans = [(a, b) for a, b in spans if b > a]
    pieces: list[tuple[float, float, bool]] = []
    for a, b in kept:
        marks = sorted({a, b, *[x for s in spans for x in s if a < x < b]})
        for p, q in zip(marks, marks[1:]):
            mid = (p + q) / 2
            pieces.append((p, q, any(s[0] <= mid <= s[1] for s in spans)))
    slow = sum(q - p for p, q, fast in pieces if not fast)
    fast_ms = sum(q - p for p, q, fast in pieces if fast)
    factor = 1.0
    if fast_ms > 0:
        factor = max(1.0, fast_ms / max(budget_ms - slow, 0.3 * budget_ms))
        factor = min(max_speed, round(factor, 1))
    return [(p, q, factor if fast else 1.0, fast) for p, q, fast in pieces], factor


@dataclass
class Options:
    size: tuple[int, int] = SIZE
    fps: float = RENDER_FPS
    longest_s: float = LONGEST_S
    max_speed: float = MAX_SPEED
    title_s: float = TITLE_S
    card_s: float = CARD_S
    colours: int = COLOURS
    still_fps: float | None = STILL_FPS
    scenes: Sequence[str] | None = None
    allow_large: bool = False
    limit: int | None = None
    frames_png: Path | None = None


def plan(source: Source, opts: Options) -> list[Part]:
    """The GIF's parts in order: the title card, the scenes recorded (not failed; *opts.scenes* where given) numbered
    from 1, the cards."""
    parts = [Part("card", opts.title_s * 1000, card="title")]
    number = 0
    for entry in source.meta.get("scenes", []):
        scene = scene_of(entry["id"])
        if scene is None or entry.get("failed") or entry.get("t0") is None or entry.get("t1") is None:
            continue
        if opts.scenes is not None and entry["id"] not in opts.scenes:
            continue
        number += 1
        longest = opts.longest_s * 1000 if scene.cut else float("inf")
        segments, factor = scene_segments(entry, changes_of(source, entry["t0"], entry["t1"]), scene.budget_s * 1000,
                                          longest, opts.max_speed)
        parts.append(Part("scene", sum((b - a) / f for a, b, f, _ in segments), entry=entry, scene=scene,
                          number=number, segments=segments, factor=factor))
    parts += [Part("card", opts.card_s * 1000, card=kind) for kind in CARD_ORDER]
    return parts


# ---------------------------------------------------------------------------------------------------- the layout
def lines_at(text: str, size: int, bold: bool, width: float) -> list[str]:
    return pv.wrap(text, pv.font(size, bold), width)


def fit_text(text: str, largest: int, smallest: int, bold: bool, width: float, max_lines: int) -> tuple[int, list[str]]:
    """The largest size from *largest* down to *smallest* at which *text* wraps to *max_lines* or fewer within
    *width*; at *smallest* where none does (more lines then)."""
    for size in range(largest, smallest - 1, -1):
        lines = lines_at(text, size, bold, width)
        if len(lines) <= max_lines:
            return size, lines
    return smallest, lines_at(text, smallest, bold, width)


class Layout:
    """Where everything goes in a frame of *size* (laid out for 960x620, in proportion at any other size): the
    picture of the screen at the top, the step under it, the foot."""

    TITLE_LINES, DESC_LINES = 1, 3

    def __init__(self, size: tuple[int, int] = SIZE):
        self.W, self.H = size
        s = self.s = self.W / 960
        self.m = round(12 * s)
        self.foot = round(26 * s)
        self.step_h = round(92 * s)
        self.picture = (self.m, self.m, self.W - self.m, self.H - self.foot - self.step_h)
        self.step_box = (self.m, self.H - self.foot - self.step_h + round(8 * s), self.W - self.m, self.H - self.foot)
        self.title_px = (round(17 * s), round(14 * s))
        self.desc_px = (round(14 * s), round(12 * s))
        self.small_px = (round(11 * s), max(8, round(9 * s)))
        self.circle = round(26 * s)

    def text_width(self) -> float:
        return self.step_box[2] - self.step_box[0] - self.circle - round(10 * self.s)

    def step(self, title: str, description: str) -> tuple[tuple[int, list[str]], tuple[int, list[str]]]:
        return (fit_text(title, self.title_px[0], self.title_px[1], True, self.text_width(), self.TITLE_LINES),
                fit_text(description, self.desc_px[0], self.desc_px[1], False, self.text_width(), self.DESC_LINES))

    def step_fits(self, title: str, description: str) -> bool:
        (_ts, tl), (_ds, dl) = self.step(title, description)
        return len(tl) <= self.TITLE_LINES and len(dl) <= self.DESC_LINES


def frame_texts(kind: str, facts: dict[str, Any], part: Part | None = None) -> list[str]:
    """The texts a frame of *kind* ("scene" or a card's id) carries, as drawn."""
    if kind == "scene":
        out = [pv.CREDIT]
        if part is not None and part.scene is not None:
            out += list(step_texts(part.scene, facts))
        return out
    heading, lines = card_lines(kind, facts)
    return ([heading] if heading else []) + [t for t, _ in lines]


def has_page(kind: str) -> bool:
    """Whether a frame of *kind* shows a sample page (the scenes)."""
    return kind == "scene"


# ---------------------------------------------------------------------------------------------------- drawing
class Painter:
    """Draws the frames of a plan."""

    def __init__(self, source: Source, opts: Options):
        self.source, self.opts = source, opts
        self.layout = Layout(opts.size)
        self.facts = dict(source.meta.get("facts") or code_facts())
        self.crop_top = int(source.meta.get("crop_top") or 0)
        self._scaled: OrderedDict[tuple[str, int, int], Image.Image] = OrderedDict()
        self._cards: dict[str, Image.Image] = {}
        self.bottoms: dict[str, int] = {}  # where each card's text ended (the tests hold it above the foot)

    def scaled(self, name: str, w: int, h: int) -> Image.Image:
        key = (name, w, h)
        if key in self._scaled:
            return self._scaled[key]
        image = self.source.image(name)
        top = min(self.crop_top, max(0, image.height - 1))
        image = image.crop((0, top, image.width, image.height)).resize((max(1, w), max(1, h)), Image.LANCZOS)
        self._scaled[key] = image
        while len(self._scaled) > 8:
            self._scaled.popitem(last=False)
        return image

    # the state of a frame
    def state(self, part: Part, local_ms: float) -> tuple[Any, ...]:
        """What a frame shows, as a key: two frames with the same key are the same."""
        if part.kind == "card":
            return ("card", part.card)
        t, fast = part.real(local_ms)
        src = self.source
        frame = src.frame_at(t)
        placed = self.place(frame)
        pointer = src.pointer_at(t)
        drawn_pointer = None
        if pointer is not None and placed is not None:
            x, y = self.to_out(pointer[0], pointer[1], placed)
            if placed[0] <= x <= placed[0] + placed[2] and placed[1] <= y <= placed[1] + placed[3]:
                drawn_pointer = (int(round(x)), int(round(y)), pointer[2])
        outlined: tuple[tuple[int, int, int, int], ...] = ()
        boxes = (src.panes_at(t) if part.scene is not None and part.scene.id == "panes" else
                 src.foot_at(t) if part.scene is not None and part.scene.id == "foot" else ())
        if placed is not None:  # (the side panes in their scene, the right pane's foot in its own)
            outlined = tuple(tuple(int(round(v)) for v in (*self.to_out(b[0], b[1], placed),
                                                            *self.to_out(b[2], b[3], placed)))
                             for b in boxes)  # type: ignore[misc]
        badge = part.factor if fast else None
        return ("scene", part.number, frame, drawn_pointer, outlined, badge)

    def place(self, frame: str | None) -> tuple[int, int, int, int] | None:
        """Where the screen's picture (below the stand-in's band) goes: x, y, width, height."""
        if frame is None:
            return None
        image = self.source.image(frame)
        lay = self.layout
        x0, y0, x1, y1 = lay.picture
        ih = max(1, image.height - min(self.crop_top, image.height - 1))
        k = min((x1 - x0) / image.width, (y1 - y0) / ih)
        w, h = max(1, int(image.width * k)), max(1, int(ih * k))
        return (x0 + (x1 - x0 - w) // 2, y0 + (y1 - y0 - h) // 2, w, h)

    def to_out(self, x: float, y: float, placed: tuple[int, int, int, int]) -> tuple[float, float]:
        """A point of the copy (its px) as drawn in the GIF."""
        frame = self.source.frames[0][1] if self.source.frames else None
        width = self.source.image(frame).width if frame is not None else placed[2]
        k = placed[2] / max(1, width)
        return placed[0] + x * k, placed[1] + (y - self.crop_top) * k

    # a frame
    def draw(self, part: Part, key: tuple[Any, ...]) -> Image.Image:
        if part.kind == "card":
            if part.card not in self._cards:
                self._cards[part.card] = self.card(part.card)
            return self._cards[part.card]
        return self.scene_frame(part, key)

    def scene_frame(self, part: Part, key: tuple[Any, ...]) -> Image.Image:
        _kind, number, frame, pointer, outlined, badge = key
        lay = self.layout
        s = lay.s
        img = Image.new("RGB", (lay.W, lay.H), BG)
        d = ImageDraw.Draw(img)
        placed = self.place(frame)
        if frame is not None and placed is not None:
            px, py, pw, ph = placed
            img.paste(self.scaled(frame, pw, ph), (px, py))
            for x0, y0, x1, y1 in outlined:
                pad = round(4 * s)
                d.rounded_rectangle((x0 - pad, y0 - pad, x1 + pad, y1 + pad), radius=round(6 * s), outline=AMBER,
                                    width=max(2, round(3 * s)))
            if pointer is not None:
                self.pointer(d, pointer)
            if badge is not None:
                text = f"{badge:.1f}x"
                face = pv.font(round(14 * s), True)
                w = pv.text_width(text, face) + round(14 * s)
                bx, by = px + pw - w - round(8 * s), py + round(8 * s)
                d.rounded_rectangle((bx, by, bx + w, by + round(24 * s)), radius=round(6 * s), fill=AMBER)
                d.text((bx + w / 2, by + round(12 * s)), text, fill=(20, 20, 20), font=face, anchor="mm")
        # the step
        assert part.scene is not None
        x0, y, _x1, _y1 = lay.step_box
        title, description = step_texts(part.scene, self.facts)
        (tsize, tlines), (dsize, dlines) = lay.step(title, description)
        c = lay.circle
        d.ellipse((x0, y, x0 + c, y + c), fill=BLUE)
        d.text((x0 + c / 2, y + c / 2), str(number), fill=TEXT, font=pv.font(round(15 * s), True), anchor="mm")
        tx = x0 + c + round(10 * s)
        ty = y + max(0, (c - round(tsize * 1.25)) // 2)
        for line in tlines:
            d.text((tx, ty), line, fill=TEXT, font=pv.font(tsize, True))
            ty += round(tsize * 1.25)
        ty = max(y + c, ty) + round(4 * s)
        for line in dlines:
            d.text((tx, ty), line, fill=SOFT_TEXT, font=pv.font(dsize))
            ty += round(dsize * 1.35)
        self.foot(d, f"shown at {badge:.1f}x speed" if badge is not None else "", True)
        return img

    def pointer(self, d: ImageDraw.ImageDraw, pointer: tuple[int, int, bool]) -> None:
        x, y, down = pointer
        k = self.layout.s * 1.1
        shape = [(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)]
        points = [(x + px * k, y + py * k) for px, py in shape]
        if down:
            r = 11 * k
            d.ellipse((x - r, y - r, x + r, y + r), outline=AMBER, width=max(2, round(2 * k)))
        d.polygon(points, fill=(255, 255, 255), outline=(0, 0, 0))

    def foot(self, d: ImageDraw.ImageDraw, left: str, credit: bool) -> None:
        lay = self.layout
        y = lay.H - lay.foot / 2
        size = lay.small_px[0]
        room = lay.W - 2 * lay.m - (pv.text_width(left, pv.font(size)) + round(16 * lay.s) if left else 0)
        csize = size
        while credit and csize > lay.small_px[1] and pv.text_width(pv.CREDIT, pv.font(csize)) > room:
            csize -= 1
        if left:
            d.text((lay.m, y), left, fill=AMBER, font=pv.font(size, True), anchor="lm")
        if credit:
            d.text((lay.W - lay.m, y), pv.CREDIT, fill=DIM, font=pv.font(csize), anchor="rm")

    # the cards
    def card(self, kind: str) -> Image.Image:
        lay = self.layout
        s = lay.s
        img = Image.new("RGB", (lay.W, lay.H), BG)
        d = ImageDraw.Draw(img)
        heading, lines = card_lines(kind, self.facts)
        if kind == "title":
            y = round(lay.H * 0.28)
            for text, style in lines:
                size, bold, colour = {"title": (round(54 * s), True, TEXT), "lead": (round(22 * s), True, TEXT),
                                      "body": (round(16 * s), False, SOFT_TEXT),
                                      "small": (round(11 * s), False, DIM)}[style]
                if style == "small":
                    d.text((lay.W / 2, lay.H - round(40 * s)), text, fill=colour, font=pv.font(size), anchor="mm")
                    continue
                for line in lines_at(text, size, bold, lay.W * 0.72):
                    d.text((lay.W / 2, y), line, fill=colour, font=pv.font(size, bold), anchor="ma")
                    y += round(size * 1.35)
                y += round(14 * s)
            self.bottoms[kind] = y
            return img
        x = round(48 * s)
        y = round(48 * s)
        d.text((x, y), heading, fill=TEXT, font=pv.font(round(28 * s), True))
        y += round(60 * s)
        width = lay.W - 2 * x
        size = round(20 * s)
        for text, style in lines:
            if style == "small":
                d.text((x, lay.H - round(44 * s)), text, fill=DIM, font=pv.font(round(12 * s)))
                continue
            indent = round(30 * s)
            r = round(3 * s)
            d.ellipse((x + round(8 * s) - r, y + size * 0.65 - r, x + round(8 * s) + r, y + size * 0.65 + r), fill=BLUE)
            for line in lines_at(text, size, False, width - indent):
                d.text((x + indent, y), line, fill=(222, 224, 228), font=pv.font(size))
                y += round(size * 1.38)
            y += round(14 * s)
        self.bottoms[kind] = y
        return img


# ---------------------------------------------------------------------------------------------------- the GIF
class TooLarge(RuntimeError):
    def __init__(self, report: dict[str, Any]):
        super().__init__(f"the GIF would be {report['bytes']} bytes, {report['over_by']} over the limit")
        self.report = report


def gif_frames(data: bytes) -> list[tuple[int, int]]:
    """Each image of the GIF *data*: its delay (ms) and its bytes (from its control block to its last data block)."""
    flags = data[10]
    pos = 13 + (3 * (2 ** ((flags & 7) + 1)) if flags & 0x80 else 0)
    start, delay, out = pos, 0, []
    while pos < len(data):
        block = data[pos]
        if block == 0x3B:
            break
        if block == 0x21:
            q = pos + 2
            if data[pos + 1] == 0xF9:
                delay = int.from_bytes(data[q + 2:q + 4], "little") * 10
            while data[q] != 0:
                q += data[q] + 1
            pos = q + 1
            continue
        if block == 0x2C:
            local = data[pos + 9]
            q = pos + 10 + (3 * (2 ** ((local & 7) + 1)) if local & 0x80 else 0) + 1
            while data[q] != 0:
                q += data[q] + 1
            pos = q + 1
            out.append((delay, pos - start))
            start, delay = pos, 0
            continue
        break
    return out


def used_colours(image: Image.Image) -> list[tuple[int, int, int]]:
    """The colours a paletted *image* uses, in the order of their index."""
    palette = image.getpalette() or []
    return [tuple(palette[3 * i:3 * i + 3]) for _count, i in sorted(image.getcolors(256) or [], key=lambda c: c[1])]


DRAWN = (BG, TEXT, DIM, AMBER, BLUE, PANEL, SOFT_TEXT, (255, 255, 255), (0, 0, 0))  # the colours drawn over
VIVID_SPREAD = 64  # a pixel whose channels differ by this much is a colour (the boxes, their plates, the panes' marks)


def palette_of(frames: Sequence[Image.Image], colours: int = 255) -> Image.Image:
    """One palette of *colours* entries for the whole GIF: the colours drawn over the frames (`DRAWN`), about an
    eighth for the vivid colours of *frames* at full size (a region's thin frame and its handles keep their colour:
    in a palette made of the pages and the panes' greys they would come out dull), the rest from a montage of
    *frames*. Index `TRANSPARENT` (255) is never one of them."""
    colours = max(len(DRAWN) + 2, min(255, colours))
    entries: list[tuple[int, int, int]] = list(DRAWN)
    pixels = np.concatenate([np.asarray(f.convert("RGB")).reshape(-1, 3) for f in frames])
    vivid = pixels[(pixels.max(axis=1).astype(np.int16) - pixels.min(axis=1)) >= VIVID_SPREAD]
    if len(vivid):
        vivid = vivid[:: max(1, len(vivid) // 250_000)]
        side = int(np.ceil(np.sqrt(len(vivid))))
        strip = np.zeros((side * side, 3), np.uint8)
        strip[:len(vivid)] = vivid
        strip[len(vivid):] = vivid[0]
        entries += used_colours(Image.fromarray(strip.reshape(side, side, 3), "RGB").quantize(
            colors=max(1, colours // 8), method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    w, h = frames[0].size
    cols = min(4, len(frames))
    montage = Image.new("RGB", (w // 2 * cols, h // 2 * ((len(frames) + cols - 1) // cols)), BG)
    for k, frame in enumerate(frames):
        montage.paste(frame.resize((w // 2, h // 2), Image.BOX), ((k % cols) * (w // 2), (k // cols) * (h // 2)))
    entries += used_colours(montage.quantize(colors=max(1, colours - len(entries)), method=Image.Quantize.MEDIANCUT,
                                             dither=Image.Dither.NONE))
    palette = Image.new("P", (1, 1))
    palette.putpalette([v for colour in entries[:colours] for v in colour])
    return palette


TRANSPARENT = 255  # the GIF's transparent index (the one palette has 255 colours, so it is free)


def changes_only(frames: Iterator[Image.Image]) -> Iterator[Image.Image]:
    """*frames* (paletted, one palette) with every pixel the frame before already shows made `TRANSPARENT`: kept
    under it (disposal 1), so the GIF stores only what changed - a bubble lettered, the pointer - and not the page
    round it again; the first frame whole."""
    previous: np.ndarray | None = None
    for frame in frames:
        now = np.asarray(frame)
        if previous is None:
            yield frame
        else:
            delta = Image.fromarray(np.where(now == previous, TRANSPARENT, now).astype(np.uint8), "P")
            delta.putpalette(frame.getpalette())
            yield delta
        previous = now


def render(source: Source, out: Path, opts: Options) -> dict[str, Any]:
    """The GIF of *source* into *out* (see the module's docstring); what was made. Raises `TooLarge` (nothing
    written) for a GIF over the limit without *opts.allow_large*."""
    out = Path(out)
    limit = opts.limit if opts.limit is not None else GIF_LIMIT
    parts = plan(source, opts)
    if not any(p.kind == "scene" for p in parts):
        raise SystemExit("no scene to show (none recorded, or all failed)")
    painter = Painter(source, opts)
    step = 1000.0 / opts.fps
    total = sum(p.ms for p in parts)
    count = max(1, int(round(total / step)))
    keys: list[tuple[int, tuple[Any, ...]]] = []  # (part index, key) of each output frame
    starts = np.cumsum([0.0] + [p.ms for p in parts])
    for k in range(count):
        at = k * step
        i = min(len(parts) - 1, int(np.searchsorted(starts, at, side="right") - 1))
        keys.append((i, painter.state(parts[i], at - starts[i])))
    durations = pv.gif_durations(count, opts.fps)
    merged: list[list[Any]] = []  # [part index, key, ms]
    for (i, key), ms in zip(keys, durations):
        if merged and merged[-1][0] == i and merged[-1][1] == key:
            merged[-1][2] += ms
        else:
            merged.append([i, key, ms])
    merged = thinned(merged, opts.still_fps)
    sample_at = sorted({int(v) for v in np.linspace(0, len(merged) - 1, min(len(merged), 20))})
    sample = [painter.draw(parts[merged[j][0]], merged[j][1]) for j in sample_at]
    palette = palette_of(sample, opts.colours)
    if opts.frames_png is not None:
        save_pngs(painter, parts, merged, Path(opts.frames_png))

    def paletted() -> Iterator[Image.Image]:
        for i, key, _ms in merged:
            yield painter.draw(parts[i], key).quantize(palette=palette, dither=Image.Dither.NONE)

    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(out.stem + ".part.gif")
    frames = changes_only(paletted())
    first = next(frames)
    first.save(temporary, save_all=True, append_images=frames, duration=[m[2] for m in merged], loop=0,
               optimize=False, disposal=1, transparency=TRANSPARENT)
    size = temporary.stat().st_size
    per_part = part_bytes(temporary.read_bytes(), parts)
    report: dict[str, Any] = {
        "bytes": size, "limit": limit, "width": opts.size[0], "height": opts.size[1], "fps": opts.fps,
        "seconds": round(sum(m[2] for m in merged) / 1000, 1), "frames": len(merged),
        "parts": [{"id": p.id, "number": p.number or None, "seconds": round(p.ms / 1000, 1),
                   "speed": p.factor if p.kind == "scene" else None, "bytes": per_part[k]}
                  for k, p in enumerate(parts)],
        "largest": sorted(({"id": p.id, "bytes": per_part[k]} for k, p in enumerate(parts)),
                          key=lambda r: -r["bytes"])[:5]}
    if not LENGTH_AIM[0] <= report["seconds"] <= LENGTH_AIM[1]:
        report["length_note"] = f"{report['seconds']} s: aimed at {LENGTH_AIM[0]:g} to {LENGTH_AIM[1]:g} s"
    if size > limit:
        report["over_by"] = size - limit
        if not opts.allow_large:
            temporary.unlink()
            raise TooLarge(report)
    os.replace(temporary, out)
    report["gif"] = str(out)
    return report


def fit_render(source: Source, out: Path, opts: Options, aim: int = AIM_BYTES) -> dict[str, Any]:
    """The GIF of *source* (`render`) at the first of FIT_LADDER's settings - frames a second where only the screen's
    picture changes, colours, frames a second - that keeps it within *aim* bytes; its report says what each try came
    to (``fit``). Raises `TooLarge` (nothing written; the last try's report) when none does."""
    tried: list[dict[str, Any]] = []
    last: TooLarge | None = None
    for still, colours, fps in FIT_LADDER:
        attempt = replace(opts, still_fps=still, colours=colours, fps=fps, limit=int(aim), allow_large=False)
        setting = {"still_fps": still, "colours": colours, "fps": fps}
        try:
            report = render(source, out, attempt)
        except TooLarge as e:
            tried.append({**setting, "bytes": e.report["bytes"]})
            last = e
            continue
        tried.append({**setting, "bytes": report["bytes"]})
        report["fit"] = {"aim": int(aim), "chose": setting, "tried": tried}
        return report
    assert last is not None
    last.report["fit"] = {"aim": int(aim), "chose": None, "tried": tried}
    raise last


def only_window_moved(a: Sequence[Any], b: Sequence[Any]) -> bool:
    """Whether frame *b* (part index, key, ms) differs from *a* in the screen's picture alone: the same scene, the
    same pointer, outlines and badge."""
    if a[0] != b[0] or a[1][0] != "scene" or b[1][0] != "scene":
        return False
    return a[1][:2] == b[1][:2] and a[1][3:] == b[1][3:]


def thinned(merged: list[list[Any]], still_fps: float | None) -> list[list[Any]]:
    """*merged* with frames where only the screen's picture changed shown at most *still_fps* a second: such a
    frame is left out (the one before shown on for its time) while the last one kept is younger than 1/*still_fps*
    and the next frame changes the picture alone too - the last of each such stretch is always kept, so it ends on
    the picture as it was. Frames with the pointer or the outlines moving are all kept."""
    if not still_fps:
        return merged
    period = 1000.0 / still_fps
    out: list[list[Any]] = []
    since = 0.0
    for k, m in enumerate(merged):
        nxt = merged[k + 1] if k + 1 < len(merged) else None
        if out and since < period and only_window_moved(out[-1], m) and nxt is not None \
                and only_window_moved(m, nxt):
            out[-1][2] += m[2]
            since += m[2]
            continue
        out.append(list(m))
        since = m[2]
    return out


def part_bytes(data: bytes, parts: Sequence[Part]) -> list[int]:
    """The GIF's bytes per part, by where each of its images begins in time."""
    starts = np.cumsum([0.0] + [p.ms for p in parts])
    out = [0] * len(parts)
    at = 0.0
    for delay, size in gif_frames(data):
        i = min(len(parts) - 1, max(0, int(np.searchsorted(starts, at + 1e-6, side="right") - 1)))
        out[i] += size
        at += delay
    return out


def save_pngs(painter: Painter, parts: Sequence[Part], merged: Sequence[Sequence[Any]], folder: Path) -> list[str]:
    """A frame of each part (three of a scene: early, middle, late) as PNG in *folder* (a scratch folder)."""
    folder = pv.check_scratch_path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, part in enumerate(parts):
        mine = [m for m in merged if m[0] == i]
        if not mine:
            continue
        picks = [mine[len(mine) // 2]] if part.kind == "card" else \
            [mine[min(len(mine) - 1, int(len(mine) * f))] for f in (0.2, 0.55, 0.9)]
        for j, m in enumerate(picks):
            path = folder / f"{i:02d}_{part.id}{'' if part.kind == 'card' else f'_{j}'}.png"
            painter.draw(part, m[1]).save(path)
            saved.append(str(path))
    return saved


# ---------------------------------------------------------------------------------------------------- the command line
def size_arg(text: str) -> tuple[int, int]:
    w, h = (int(v) for v in text.lower().split("x"))
    return w, h


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="record the scenes on the stand-in viewer (a run of tools/standin_e2e.py)")
    rec.add_argument("--out", type=Path, required=True,
                     help="the recording (a .zip in a scratch folder: never a repository, never ~/.taslation); the "
                          "run's own scratch folder goes beside it and is deleted at the end")
    rec.add_argument("--start-ollama", type=int, default=RECORD_PORT, metavar="PORT",
                     help=f"the loopback port TASlation's starter starts the translator's server on (default "
                          f"{RECORD_PORT}; one where nothing answers)")
    rec.add_argument("--fps", type=float, default=RECORD_FPS, help="copies of the screen a second while the scenes run")
    rec.add_argument("--standin-size", default=STANDIN_SIZE, metavar="WxH",
                     help="the stand-in's window (room for both panes beside a spread)")
    rec.add_argument("--standin-monitor", type=int, default=STANDIN_MONITOR, metavar="N",
                     help=f"the monitor the stand-in goes on, at the top left of its work area (default "
                          f"{STANDIN_MONITOR}; the primary is 1): no window of another program may lie there")
    rec.add_argument("--browser", default="auto", choices=("auto", "chrome", "edge"))
    rec.add_argument("--series", type=int, default=1, help="the sample dataset's series, by its place in the sorted list")
    rec.add_argument("--first", type=int, default=FIRST_PAGE, help="its first page (from 1)")
    rec.add_argument("--models", default="", help="the models folder (default: TASLATION_MODELS_DIR)")
    rec.add_argument("--keep-run", action="store_true",
                     help="keep the run's report.json (numbers only) in its scratch folder")
    ren = sub.add_parser("render", help="make the GIF of a recording (and delete the recording)")
    ren.add_argument("recording", type=Path, nargs="?", default=None,
                     help="a recording (a ZIP in a scratch folder, made by record); deleted once the GIF is written")
    ren.add_argument("--out", type=Path, required=True, help="the GIF (where git ignores it, or outside the repository)")
    ren.add_argument("--sample", action="store_true", help="made-up frames in place of a recording")
    ren.add_argument("--scenes", default=None, help="a,b,c: these of the recorded scenes only")
    ren.add_argument("--size", type=size_arg, default=SIZE)
    ren.add_argument("--fps", type=float, default=RENDER_FPS)
    ren.add_argument("--longest", type=float, default=LONGEST_S, help="seconds a wait with nothing changing is shown")
    ren.add_argument("--max-speed", type=float, default=MAX_SPEED)
    ren.add_argument("--title-seconds", type=float, default=TITLE_S)
    ren.add_argument("--card-seconds", type=float, default=CARD_S)
    ren.add_argument("--colours", type=int, default=COLOURS, help="the palette's colours (at most 255)")
    ren.add_argument("--still-fps", type=float, default=STILL_FPS,
                     help="frames where only the screen's picture changes, at most this many a second (0: all)")
    ren.add_argument("--fit", type=int, nargs="?", const=AIM_BYTES, default=None, metavar="BYTES",
                     help=f"the first of the settings tried in turn (frames a second where only the picture changes, "
                          f"colours, frames a second) that keeps the GIF within BYTES (default {AIM_BYTES}: the "
                          f"README's recording it replaces); --still-fps, --colours and --fps are not used then")
    ren.add_argument("--allow-large", action="store_true", help=f"write a GIF over {GIF_LIMIT} bytes all the same")
    ren.add_argument("--keep-recording", action="store_true", help="keep the recording file after the GIF")
    ren.add_argument("--frames-png", type=Path, default=None, help="a scratch folder for a few frames as PNG")
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse(list(sys.argv[1:] if argv is None else argv))
    if args.command == "record":
        return record(args)
    out = pv.check_video_path(args.out)
    if out.suffix.lower() != ".gif":
        raise SystemExit("--out is a .gif")
    opts = Options(size=args.size, fps=args.fps, longest_s=args.longest, max_speed=args.max_speed,
                   title_s=args.title_seconds, card_s=args.card_seconds, colours=args.colours,
                   still_fps=args.still_fps or None,
                   scenes=[s.strip() for s in args.scenes.split(",")] if args.scenes else None,
                   allow_large=args.allow_large, frames_png=args.frames_png)
    if args.sample:
        source: Source = sample_source()
    elif args.recording is None:
        raise SystemExit("render needs a recording (or --sample)")
    else:
        source = ZipSource(pv.check_scratch_path(args.recording))
    try:
        report = render(source, out, opts) if args.fit is None else fit_render(source, out, opts, args.fit)
    except TooLarge as e:
        print(json.dumps({"refused": str(e), **e.report}, indent=1, default=str))
        return 1
    finally:
        source.close()
    if not args.sample and args.recording is not None and not args.keep_recording:
        Path(args.recording).unlink(missing_ok=True)
        report["recording_deleted"] = not Path(args.recording).exists()
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
