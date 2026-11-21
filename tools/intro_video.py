"""The README's introduction recorded again from the code this checkout holds (dev tool, never part of a release): the
real TASlation window, in English, beside a stand-in viewer of its own, going through numbered steps, then cards of
facts taken from the code - made into one animated GIF.

    python tools/intro_video.py record --out SCRATCH/intro.zip [--scenes viewer,next_page] [--start-ollama 11438]
    python tools/intro_video.py record --list
    python tools/intro_video.py render SCRATCH/intro.zip --out promo/taslation-intro.gif
    python tools/intro_video.py render --sample --out SCRATCH/sample.gif [--frames-png SCRATCH/frames]

``record`` runs, all on this computer:

* the stand-in viewer: a Tk window of a child process of this tool (``--serve-viewer``, the same file), titled
  ``Sample Viewer - OpenMantra sample``, showing *--pages* pages of the OpenMantra title *--title* from page *--first*
  (one page a screen; ``--spread`` two). It turns its pages on the page keys it is posted - TASlation's own "pass the
  key on" path - which it reads from its own thread's message queue; the tool never sends it a key itself;
* TASlation's window in this process (`ui.app.App`), in English, with the offline guard on, the real OCR from
  TASLATION_MODELS_DIR and PLaMo through an Ollama that TASlation's own starter starts on the loopback port
  *--start-ollama* (11438 by default; 11434, the owner's own server, and 11435 to 11437 are refused) and that is stopped
  at the end. The scenes of `SCENES` act on its own Tk widgets - a button's ``invoke``, a list posted and an entry
  picked, Tk's key and pointer events generated on the page, a bound command called - as a person's clicks and keys
  would; the pointer the GIF shows is drawn in afterwards from the positions the tool gave the window;
* pictures of TASlation's own window and of this process's own windows over it (its dialogs, lists and panels), with
  PrintWindow, about *--fps* a second, and the pictures the stand-in draws (it sends them itself), into the recording
  file *--out*: a ZIP in a scratch folder, with the times, the scenes, the pointer's positions, the keys pressed, the
  boxes of the regions acted on and how the page was placed in the window - numbers and ids only, never a line of a
  page's text, Japanese or translated (`check_no_text`).

What it touches, and what not: nothing but the stand-in and this process's own windows is ever listed, chosen,
captured, moved, raised, focused or sent a key or a click (`tools/demo_video.py`'s guard, imported: the window list
holds the stand-in alone, every function of ``capture.windows`` that acts on a window checks it, a key may be posted to
the stand-in alone, a real key press, a posted click and a copy of the screen never; a refused call ends the run). No
system-wide keyboard or mouse input is made: no key is pressed for real, the pointer never moves. The state folder is a
scratch one (TASLATION_STATE_DIR, the legal notice dismissed, the window in English), deleted at the end; nothing of
``~/.taslation`` is read but the dataset's pages. Nothing goes to the network but Ollama on this computer.

``render`` makes a GIF of the recording, 960x540 by default and about 90 to 140 s long: a title card, the scenes
numbered in their order (the window on the right, the stand-in viewer and the step on the left, the key pressed in a
key cap), then the cards "How a page is translated", "The models", "On your own computer" and "Before you use it" -
their figures from the code's constants (`code_facts`), their sentences those of README.md, docs/MANUAL.md and
docs/THIRD_PARTY.md. Long waits are cut; a stretch marked as waiting for the models is shown faster, with a badge and
"shown at N.Nx speed" under it. One palette, no dither. A GIF over 9 MB is refused (``--allow-large`` writes it and
says by how much it is over); either way the scenes that take the most bytes are said. The recording file is deleted
once the GIF is written (``--keep-recording`` keeps it); it holds pictures of the sample pages, as the GIF does: both
are CC BY-NC 4.0 material ("Sample pages: OpenMantra dataset (Mantra Inc., CC BY-NC 4.0), modified" on every frame
with a page), never part of a release. The GIF goes where git ignores it (``promo/``) or outside the repository; the
recording into a scratch folder. ``render --sample`` renders made-up frames (no window, no model, no manga page)."""

from __future__ import annotations

import argparse
import base64
import bisect
import contextlib
import ctypes
import faulthandler
import importlib.util
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from collections import OrderedDict
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Sequence

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
for _path in (str(TOOLS), str(ROOT)):  # (this checkout's package first, whatever is installed)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import demo_video as dv  # noqa: E402
import promo_video as pv  # noqa: E402

FORMAT = "intro-1"  # the recording's ``intro_format``
BOOK = "balloon_dream (OpenMantra)"
DEFAULT_PORT = 11438
REFUSED_PORTS = range(11434, 11438)  # the owner's own Ollama, and ports other tools use
GIF_LIMIT = 9_000_000  # bytes: a GIF over this is refused without --allow-large
SIZE = (960, 540)
WINDOW_SIZE = (1240, 860)
WINDOW_AT = (380, 40)
VIEWER_RECT = (0, 0, 900, 1000)  # the stand-in at first (TASlation makes it as large as its monitor's work area)
TICK_MS = 15
CLOSE_WAIT_S = 60  # the window not closed this long after the scenes: every thread's stack is said (stderr)
GLIDE_HZ = 30
KEY_CAP_MS = 1600.0  # a key cap shows this long (as shown)
MAX_SPEED = 8.0
LONGEST_S = 1.2  # a wait with nothing changing is cut to this long
TITLE_S, CARD_S = 5.0, 5.5
PIC_HEIGHT = 560  # the stand-in's pictures, at most this high
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}

# colours (the dark ground of promo_video's)
BG, TEXT, DIM, AMBER = pv.BG, pv.TEXT, pv.DIM, pv.AMBER
PANEL = (28, 29, 33)
BLUE = (58, 128, 232)
CAP_BG = (236, 236, 238)
CAP_EDGE = (120, 122, 128)

HEADER_LABEL = (205, 207, 212)  # a column header's label (its note is DIM)
HEADER_SEP = " - "  # between a header's bold label and its lighter note
LEFT_HEADER = "YOUR VIEWER - the book stays here, untouched"
RIGHT_HEADER = "TASLATION - reads that window and shows the translation"
CAP_PRESSED = "key pressed in TASlation"
CAP_PASSED_ONCE = "passed on to the viewer, once"
CAP_PASSED = "passed on to the viewer"
KEY_GLYPHS = {"Left": "\u2190", "Right": "\u2192", "Up": "\u2191", "Down": "\u2193", "PageUp": "PgUp",
              "PageDown": "PgDn", "Home": "Home", "End": "End", "Space": "Space", "Escape": "Esc"}


# ---------------------------------------------------------------------------------------------------- the scenes
def has_module(name: str) -> bool:
    """Whether this checkout's package has the module *name* (looked up, not imported)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def always() -> bool:
    return True


def backlog_present() -> bool:
    """The pages turned past are worked on behind the reader, and shown beside the page."""
    return has_module("taslation.backlog") and has_module("taslation.ui.side")


def whole_book_present() -> bool:
    """The whole-book command (Read whole book...) is there."""
    return has_module("taslation.batch") and has_module("taslation.ui.dialogs.batch")


README, MANUAL, THIRD_PARTY = "README.md", "docs/MANUAL.md", "docs/THIRD_PARTY.md"
DOCS = (README, MANUAL, THIRD_PARTY)  # the documents a line of the recording may follow


@dataclass(frozen=True)
class Cite:
    """A sentence of a document that a line of the recording follows (or several sentences, or a table's cells):
    *doc* is the document's path from the checkout's root, and *quote* stands in it word for word once the facts of
    `code_facts` are put in ({name}, as in the lines), a run of white space reading as one space. The tool's tests
    check that every quote still stands, so a line cannot go stale silently when its document changes."""

    doc: str
    quote: str


def cites(doc: str, *quotes: str) -> tuple[Cite, ...]:
    """*quotes* of the document *doc*, as `Cite`s."""
    return tuple(Cite(doc, quote) for quote in quotes)


EDITING_TOOLS = ("**Tools for editing a translation**: add, move, resize and turn the regions that are read; rewrite a "
                 "translation; choose its font, bold and italic; keep a list of names and terms (the series sheet); "
                 "find and replace.")  # (README.md, Features)


@dataclass(frozen=True)
class Scene:
    """A step of the introduction: its id, its title and description (no number: numbers are given at render
    time; {name} is a fact of `code_facts`), its share of the GIF in seconds, the role the window is in for it
    ("reader", "translator" or "" for either), whether this checkout has what it shows, and what its description
    follows: the sentences of the documents it says (`follows`) and, for the tool's own words, what they say and
    where that comes from (`own`; a description has one or the other, or both)."""

    id: str
    title: str
    description: str
    budget_s: float
    role: str = "reader"
    present: Callable[[], bool] = always
    follows: tuple[Cite, ...] = ()
    own: str = ""


SCENES: tuple[Scene, ...] = (
    Scene("viewer", "Choose your viewer",
          "Choose your viewer's window in the Viewer list. Its page fills in while you look at it.", 12.0,
          follows=cites(MANUAL, "Choose the viewer's window in the \"Viewer\" list.",
                        "An untranslated page fills in while you look at it.")),
    Scene("next_page", "On-the-fly translation",
          "When you turn a page, its bubbles are replaced by their translations there and then, in reading order. "
          "Press the page key in TASlation; it is passed on to your viewer.", 8.0,
          follows=cites(README, "**On-the-fly translation**: when you turn a page, its bubbles are replaced by their "
                                "translations there and then, in reading order (from the top right).",
                        "A page key you press in TASlation is passed on to the viewer.")),
    Scene("original", "See the original",
          "Rest the pointer on a bubble: a small window beside it shows the original bubble and the translation.",
          6.0,
          follows=cites(MANUAL, "In the window and on the full screen, in either role, resting the pointer on a bubble "
                                "shows that bubble's \"other side\" (how the Translator role differs is under \"In the "
                                "Translator role\" below).",
                        "| Translation | Panel | A small window beside it shows an enlargement of the original bubble "
                        "and the translation at a readable size. |")),
    Scene("turned_past", "Pages you turn past",
          "Turn on before a page is done: the pages you turned past go on being translated, and the margin shows how "
          "far it is. Turn back, and they are there.", 13.0, present=backlog_present,
          follows=cites(MANUAL, "While you read, TASlation goes on reading and translating the pages you have turned "
                                "past.",
                        "How far it is shows in the margin on the side the page turns to (the left in a book read "
                        "right to left, the right in a book read left to right), in both roles, in the window and on "
                        "the full screen.",
                        "A page whose translations are all in the cache is shown from the cache as soon as the new "
                        "picture arrives, without an untranslated picture in between.")),
    Scene("language", "Another language",
          "Choose another language in the To: box - one of {languages}. The page on show follows it.", 8.0,
          follows=cites(MANUAL, "The target language is chosen in the \"To:\" box (or with `--language`, or the "
                                "setting `target_language`).",
                        "Translations can be into any of the {languages} languages of the \"To:\" box."),
          own="\"The page on show follows it\": what the window does when the To: box changes (ui.app, "
              "_target_picked)"),
    Scene("sheet", "The series sheet",
          "In the Translator role, keep the series' names and terms in its sheet. Translate again translates the page "
          "with them.", 10.0, role="translator",
          follows=cites(README, EDITING_TOOLS)
          + cites(MANUAL, "Everything except the typefaces is told to the model before it translates.",
                  "\"Skip page\" marks a page with nothing to translate, such as an advertisement or the viewer's own "
                  "panel, and \"Translate again\" (not using the cache) translates the page again with the current "
                  "premises.")),
    Scene("edit", "Rewrite a translation",
          "Double-click a bubble and rewrite its translation. The page follows what you type.", 9.0,
          role="translator",
          follows=cites(README, EDITING_TOOLS)
          + cites(MANUAL, "**Editing a region**: opens with a double-click (or Enter while a region is selected).",
                  "After a change, the page behind is lettered again a moment later.")),
    Scene("region", "Move or resize a region",
          "Drag a region to move it, or a handle of its frame to resize it.", 6.0, role="translator",
          follows=cites(README, EDITING_TOOLS)
          + cites(MANUAL, "Like shapes in office software, a region is selected with a click, moved by dragging, and "
                          "resized with its handles, and it is read again only when the new frame covers a larger "
                          "area.")),
    Scene("undo", "Undo", "Undo (Ctrl+Z) takes back a change to the page.", 4.0, role="translator",
          follows=cites(README, "Ctrl+Z takes back a change to a page or to this book's translations.")),
    Scene("add_region", "Add a region",
          "Text that was not found: draw a rectangle around it, and it is read and translated.", 8.0,
          role="translator",
          follows=cites(MANUAL, "Draw a rectangle around text that was not detected, and it is read, translated and "
                                "added to the page (later readings and batches use it too).")),
    Scene("full_screen", "Full screen",
          "Full screen (F11) shows the page alone on the whole screen, in the role you chose. F11 takes you back to "
          "the window.", 6.0, role="translator",
          follows=cites(MANUAL, "\"Full screen\" (the toolbar button, or F11) shows the page alone on the whole "
                                "screen, in the role you chose.",
                        "F11 takes you back to the window, and so does Esc (in the Translator role Esc first lets go "
                        "of a selected region).")),
    Scene("whole_book", "The whole book",
          "Read whole book... reads the pages you turn, then translates them all together. Turn back, and every page "
          "is shown at once.", 14.0, present=whole_book_present,
          follows=cites(MANUAL, "\"Read whole book...\" reads the pages you turn and translates them all together "
                                "once you have finished reading, in two stages.",
                        "Once you have read the whole book with the whole-book reading, every page is shown at once, "
                        "which makes reading comfortable.")),
)
SCENE_IDS = tuple(s.id for s in SCENES)


def scene_of(scene_id: str) -> Scene | None:
    return next((s for s in SCENES if s.id == scene_id), None)


def scene_rows() -> list[dict[str, Any]]:
    """`--list`: each scene's id, title and whether this checkout has what it shows."""
    return [{"id": s.id, "title": s.title, "present": bool(s.present())} for s in SCENES]


def pick_scenes(text: str | None) -> list[Scene]:
    """The scenes *text* names (``a,b,c``), in the table's order; all those present without one. A name the table
    does not have, or a scene this checkout cannot show, ends the run."""
    if not text:
        return [s for s in SCENES if s.present()]
    wanted = [w.strip() for w in text.split(",") if w.strip()]
    unknown = [w for w in wanted if w not in SCENE_IDS]
    if unknown:
        raise SystemExit(f"no such scene: {', '.join(unknown)} (record --list lists them)")
    absent = [w for w in wanted if not scene_of(w).present()]  # type: ignore[union-attr]
    if absent:
        raise SystemExit(f"not in this checkout: {', '.join(absent)}")
    return [s for s in SCENES if s.id in wanted]


# ---------------------------------------------------------------------------------------------------- the cards
def and_list(names: Sequence[str]) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def code_facts() -> dict[str, Any]:
    """The figures the cards and the steps say, from the code's own constants (never written by hand)."""
    import taslation
    from taslation import jurisdictions
    from taslation.config import LAMA_MODEL, OCR_MODELS
    from taslation.i18n import UI_LANGUAGES
    from taslation.translate.models import PLAMO, QWEN, model_for_language
    from taslation.ui.constants import LANGUAGES

    ocr = len(OCR_MODELS)
    return {"version": str(taslation.__version__), "languages": len(LANGUAGES), "ui_languages": len(UI_LANGUAGES),
            "ocr_models": ocr, "ocr_word": NUMBER_WORDS.get(ocr, str(ocr)),
            "plamo": PLAMO.display_name, "plamo_gb": f"{PLAMO.size_gb:g}",
            "qwen": QWEN.display_name, "qwen_gb": f"{QWEN.size_gb:g}",
            "qwen_languages": and_list([lang for lang in LANGUAGES if model_for_language(lang).kind == QWEN.kind]),
            "lama_licence": str(LAMA_MODEL.licence), "countries": len(jurisdictions.JURISDICTIONS)}


@dataclass(frozen=True)
class Line:
    """A line of a card: its text ({name} is a fact of `code_facts`; a line whose fact is missing is left out), its
    style ("title", "lead", "body", "small", "step" (numbered) or "bullet"), and what it follows: the sentences of
    the documents it says (`follows`) or, for the tool's own words, what they say and where that comes from
    (`own`)."""

    text: str
    style: str
    follows: tuple[Cite, ...] = ()
    own: str = ""


JAPAN_LAW = ("In Japan, the Copyright Act allows copying a work for your own private use (Article 30) and translating "
             "it for that use (Article 47-6); [docs/LEGAL.md](docs/LEGAL.md) sums up what {countries} countries "
             "allow.")  # (README.md, the first paragraph)
ERASING = ("Lettering is erased in two ways (a white bubble is filled with the colour of its paper; under lettering on "
           "the drawing, the inpainting model LaMa fills the drawing in).")  # (README.md, Features)
BUILT_WITH = ("Built with PLaMo: translation uses {plamo} by Preferred Networks (PLaMo Community License, revised "
              "November 9, 2026).")  # (README.md, Licence)

# card id -> (heading, lines)
CARDS: dict[str, tuple[str, tuple[Line, ...]]] = {
    "title": ("", (
        Line("TASlation", "title", cites(README, "# TASlation")),
        Line("A tool for reading your own manga on your own computer, translating as you read", "lead",
             cites(README, "**A tool for reading your own manga on your own computer, translating as you read**")),
        Line("The window reads the manga page your viewer is showing, translates it on this computer, and shows the "
             "translation laid over the page.", "body",
             cites(README, "The TASlation (Tool Assisting Self-translation) window reads the manga page your viewer is "
                           "showing, translates it on this computer, and shows the translation laid over the page.")),
        Line("Recorded with version {version}", "small",
             own="the version of the checkout the recording was made with (taslation.__version__)"),
    )),
    "how": ("How a page is translated", (
        Line("TASlation captures your viewer's window as the screen shows it.", "step",
             cites(README, "**Any viewer**: TASlation captures the viewer's window as the screen shows it and lays the "
                           "translation over that picture.")),
        Line("The text is read by {ocr_word} OCR models; where their readings differ, the one closest to the other "
             "two is taken.", "step",
             cites(README, "**Accurate translation**: the text is read by {ocr_word} OCR models, and where their "
                           "readings differ, the one closest to the other two is taken.")),
        Line("{plamo} translates, given the pages before as context and your list of names and terms.", "step",
             cites(README, "The translation is made by {plamo}, a model built for translation, which is given the pages "
                           "before as context and your list of names and terms.")),
        Line("The lettering is erased: a white bubble is filled with the colour of its paper; on the drawing, LaMa "
             "fills the drawing in.", "step", cites(README, ERASING)),
        Line("Each bubble is lettered as soon as its translation is ready, in reading order.", "step",
             cites(MANUAL, "The bubbles found are marked with frames (dashed; solid once read; gone once they turn out "
                           "not to be text), and they are translated in the order the page's bubbles are read, each "
                           "with the lines before it as context.",
                   "Each bubble is lettered as soon as its translation is ready.")),
    )),
    "models": ("The models", (
        Line("The weights of the {ocr_word} OCR models are under CC BY-NC-SA 4.0, and each person agrees to them and "
             "fetches them when installing.", "bullet",
             cites(README, "The weights of the {ocr_word} OCR models are under CC BY-NC-SA 4.0, and each person agrees "
                           "to them and fetches them when installing.")),
        Line("Under lettering on the drawing, the inpainting model LaMa fills the drawing in ({lama_licence}).",
             "bullet",
             cites(README, ERASING)
             + cites(THIRD_PARTY, "| {lama_licence} | Big LaMa ([advimman/lama](https://github.com/advimman/lama), "
                                  "Apache-2.0) fine-tuned on manga and anime.")),
        Line("Translation uses {plamo} by Preferred Networks (PLaMo Community License), about {plamo_gb} GB.",
             "bullet",
             cites(README, BUILT_WITH,
                   "| Free disk space | About 7.5 GB (the translation model, about {plamo_gb} GB, included). On a "
                   "computer with an NVIDIA GPU, about 3.7 GB more |")),
        Line("{qwen_languages} use {qwen} (Apache-2.0), about {qwen_gb} GB.", "bullet",
             cites(README, "{qwen_languages} use {qwen} (Apache-2.0).",
                   "Translating into Portuguese (Brazil) or Turkish uses another translation model (about {qwen_gb} "
                   "GB), and then about 9.0 GB of free disk space is needed.")),
        Line("{languages} languages to translate into, and {ui_languages} languages for the window itself.", "bullet",
             cites(README, "**Many languages**: {languages} languages to translate into (English, Spanish, Portuguese "
                           "(Brazil), French, German, Italian, Russian, Polish, Dutch, Turkish, Indonesian, "
                           "Vietnamese, Thai, Chinese (Simplified), Chinese (Traditional), Korean, Arabic, Hebrew, "
                           "Hindi, Bengali), and {ui_languages} languages for the window itself.")),
        Line("Built with PLaMo", "small", cites(README, BUILT_WITH)),
    )),
    "privacy": ("On your own computer", (
        Line("The reading and the translating happen on this computer, and no page and no translation is sent "
             "outside.", "bullet",
             cites(README, "**Fully local**: the reading and the translating happen on this computer, and no page and "
                           "no translation is sent outside.")),
        Line("No model is trained further.", "bullet", cites(README, "No model is trained further.")),
        Line("The network is used only while installing.", "bullet",
             cites(README, "| Network | Used only while installing |")),
        Line("It has none of these: saving page images, operating the viewer by itself, getting round capture "
             "protection, sharing over a network.", "bullet",
             cites(README, "For that reason it has none of these:\n\n* saving page images\n* operating the viewer by "
                           "itself\n* getting round capture protection\n* sharing over a network")),
    )),
    "before": ("Before you use it", (
        Line("In Japan, the Copyright Act allows copying a work for your own private use (Article 30) and translating "
             "it for that use (Article 47-6).", "bullet", cites(README, JAPAN_LAW)),
        Line("docs/LEGAL.md sums up what {countries} countries allow.", "bullet", cites(README, JAPAN_LAW)),
        Line("A store's terms of use are a contract between you and the store, so check them.", "bullet",
             cites(MANUAL, "A store's terms of use are a contract between you and the store.",
                   "That does not settle what your store's terms allow, so check them and use this mode knowing "
                   "that.")),
        Line("It is free, with no advertising, no donations and no paid version.", "bullet",
             cites(README, "It is free, with no advertising, no donations and no paid version.")),
        Line("Windows 10 / 11 (64-bit). An NVIDIA GPU with 6 GB of memory is enough; it runs without one too.",
             "bullet",
             cites(README, "| OS | Windows 10 / 11 (64-bit) |",
                   "**Runs on a modest computer**: an NVIDIA GPU with 6 GB of memory is enough.",
                   "It runs without a GPU too, and translating then takes about 4 times as long.")),
        Line(pv.PROJECT, "small",
             cites(README, "[Download the ZIP](https://" + pv.PROJECT + "/archive/refs/heads/main.zip) and extract all "
                           "of it.")),
    )),
}
CARD_ORDER = ("how", "models", "privacy", "before")
HOW_CAPTIONS = ("Your viewer", "Filling in", "Translated")  # the "how" card's three pictures


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


# ---------------------------------------------------------------------------------------------------- the guard
def guard_table(windows: Any = None) -> dict[str, tuple[str, Callable[..., Any]]]:
    """Who each guarded function of ``capture.windows`` may act on in this tool: `tools/demo_video.py`'s table as the
    promo tool has it (no key, no click: "viewer" made "never"), but a posted key may go to the stand-in - the key the
    window passes on, which turns its page; the functions an older package has besides (`promo_video.older_guarded`)
    never."""
    table = {name: (("never" if allow == "viewer" else allow), target) for name, (allow, target) in dv.GUARDED.items()}
    table["post_key"] = ("viewer", dv.first_arg)
    if windows is not None:
        table.update(pv.older_guarded(windows, table, dv.first_arg))
    return table


def install(guard: Any, viewer_info: Callable[[], Any], hotkeys: Any, probe: Any) -> dict[str, Any]:
    """The promo tool's install (`promo_video.install`: the guard, the window list holding the stand-in alone, the
    compositor, this tool's hot keys, the window told the viewer is in front, the probe on the page), then the key the
    window passes on opened to the stand-in alone (`guard_table`); what was replaced."""
    import taslation.capture.windows as windows

    done = pv.install(guard, viewer_info, hotkeys, probe)
    if not PROMO_NOTES_PAGES:  # (an older promo tool: the page's jobs and the canvas noted here)
        done.update(note_pages(probe))
    done.update(blank_file_lines())
    closed = windows.post_key
    original = getattr(closed, "__wrapped__", closed)
    allow, target = guard_table()["post_key"]
    done["post_key_to_the_stand_in"] = dv.replace_everywhere(closed, guard.wrap("post_key", original, allow, target))
    return done


PROMO_NOTES_PAGES = hasattr(pv.Probe, "page_event") and hasattr(pv.Probe, "view")  # (the promo tool hooks them)


class Probe(pv.Probe):
    """`promo_video.Probe`, with what this tool reads on any checkout: each page job of the window (``fills``) and
    each region lettered (``letters``: its job, index and box, whether it was lettered - never a text), and how the
    page canvas showed its picture (``views``: scale, offset, where the canvas is, each time that changed). A newer
    promo tool notes the same itself, and its install hooks these methods; an older one has `note_pages` do it."""

    def __init__(self, notes: Any):
        super().__init__(notes)
        self.fills: list[dict[str, Any]] = []
        self.letters: list[dict[str, Any]] = []
        self.views: list[dict[str, Any]] = []
        self._view: dict[str, Any] | None = None

    def page_event(self, app: Any, kind: str, data: dict[str, Any]) -> None:
        try:
            fill = getattr(app, "_fill", None)
            if fill is None:
                return
            n = getattr(fill, "_intro_n", None)
            if n is None:
                if kind != "regions":
                    return
                n = fill._intro_n = len(self.fills) + 1  # (on the job itself: a later job never takes its number)
                self.fills.append({"t": pv.now_ms(), "n": n, "boxes": len(fill.boxes)})
            if kind != "translated":
                return
            i = int(data["index"])
            if 0 <= i < len(fill.boxes):
                self.letters.append({"t": pv.now_ms(), "n": n, "i": i,
                                     "box": [round(float(v), 1) for v in fill.boxes[i]], "on": bool(data.get("text"))})
        except Exception as e:  # noqa: BLE001 - noted, never in the window's way
            self.error("page event", e)

    def view(self, canvas: Any) -> None:
        try:
            top = canvas.winfo_toplevel()
            image = getattr(canvas, "_image", None)
            if image is None or getattr(top, "canvas", None) is not canvas:
                return
            ox, oy = getattr(canvas, "offset", (0.0, 0.0))
            now = {"scale": round(float(canvas.scale), 6), "offset": [round(float(ox), 2), round(float(oy), 2)],
                   "origin": [int(canvas.winfo_rootx() - top.winfo_rootx()),
                              int(canvas.winfo_rooty() - top.winfo_rooty())], "image": list(image.size)}
            if now != self._view:
                self._view = now
                self.views.append({"t": pv.now_ms(), **now})
        except Exception as e:  # noqa: BLE001
            self.error("view", e)


def note_pages(probe: Probe) -> dict[str, Any]:
    """The window's page events (`App._on_page_event`) and its page canvas's drawing (`ImageCanvas._draw_picture`)
    told to *probe* after they ran; what was replaced."""
    from taslation.ui import app as app_mod
    from taslation.ui import preview

    App, Canvas = app_mod.App, preview.ImageCanvas
    page_event, draw_picture = App._on_page_event, Canvas._draw_picture

    def paged(self: Any, kind: str, data: dict[str, Any]) -> Any:
        out = page_event(self, kind, data)
        probe.page_event(self, kind, data)
        return out

    def pictured(canvas: Any, *a: Any, **k: Any) -> Any:
        out = draw_picture(canvas, *a, **k)
        probe.view(canvas)
        return out

    App._on_page_event, Canvas._draw_picture = paged, pictured
    return {"_on_page_event": 1, "_draw_picture": 1}


def blank_file_lines() -> dict[str, Any]:
    """The series sheet's line that names its file - a path of this computer - left empty, in this process only (the
    dialog lays it out with `break_lines`, which is given an empty text for it): no picture can hold it, however soon
    after the dialog opens it is taken; what was replaced."""
    from taslation.ui.dialogs import glossary

    original = glossary.break_lines
    prefix = getattr(glossary, "_", lambda s: s)("File: {path}").split("{", 1)[0]

    def quiet(text: str, *a: Any, **k: Any) -> Any:
        return "" if str(text).startswith(prefix) else original(text, *a, **k)

    glossary.break_lines = quiet
    return {"series_sheet_file_line": 1}


def name_like(source: str, translated: str) -> tuple[str, str] | None:
    """(term, rendering) where a region reads as a name: two to four kanji in its Japanese, one to three capitalised
    words in its translation; else None."""
    term = "".join(source.split())
    words = translated.strip().rstrip(".!?…").split()
    if not (2 <= len(term) <= 4 and all(0x4E00 <= ord(c) <= 0x9FFF for c in term)):
        return None
    if not (1 <= len(words) <= 3 and all(w[:1].isupper() and w.isalpha() for w in words)):
        return None
    return term, " ".join(words)


def view_at(views: Sequence[dict[str, Any]], t: float) -> dict[str, Any] | None:
    """How the window's page canvas showed its picture at *t* (the last ``views`` entry at *t* or before)."""
    return next((v for v in reversed(views) if float(v["t"]) <= t), None)


def on_picture(box: Sequence[float], view: dict[str, Any]) -> tuple[float, float, float, float]:
    """*box* (pixels of the picture the canvas shows) in pixels of the window: the canvas's scale and offset, then
    where the canvas is in the window."""
    k, (ox, oy), (cx, cy) = float(view["scale"]), view["offset"], view["origin"]
    return (cx + ox + box[0] * k, cy + oy + box[1] * k, cx + ox + box[2] * k, cy + oy + box[3] * k)


class QuietNotes:
    """What `promo_video.Probe` and `standin_e2e.HotKeys` note into, kept quiet: no screen code of a stand-in page."""

    displays: list[Any] = []

    def display(self, _app: Any) -> None:
        pass

    def shown(self, _frame: Any) -> Any:
        return SimpleNamespace(screen=False, page=None, spread=False)

    def held(self, _names: Any) -> None:
        pass

    def pressed(self, _name: str, _taken: bool) -> None:
        pass


def check_port(port: int) -> int:
    if port in REFUSED_PORTS:
        raise SystemExit(f"--start-ollama {port}: 11434 is the owner's own Ollama and 11435 to 11437 are other tools'"
                         f" (use {DEFAULT_PORT})")
    pv.started_url(port)  # (refuses a port that is no spare one)
    return port


# ---------------------------------------------------------------------------------------------------- the stand-in
WM_KEYDOWN, PM_REMOVE, WH_GETMESSAGE = 0x0100, 1, 3
KEY_TURNS = {0x25: 1, 0x28: 1, 0x22: 1, 0x20: 1,  # Left, Down, PageDown, Space: the next page (a book read right to left)
             0x27: -1, 0x26: -1, 0x21: -1}  # Right, Up, PageUp: the previous one
KEY_ENDS = {0x24: "first", 0x23: "last"}  # Home, End


def key_hook(keys: queue.Queue[int]) -> Any:
    """The keys posted to this thread's windows (WM_KEYDOWN, a first press), each put on *keys* as it is taken from
    the message queue (a hook on this thread alone: nothing of another program's is seen). What to keep alive."""
    user32, kernel32 = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")
    lresult = ctypes.c_ssize_t
    hookproc = ctypes.WINFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hookproc, wintypes.HINSTANCE, wintypes.DWORD]
    user32.CallNextHookEx.restype = lresult
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]

    def proc(code: int, wparam: int, lparam: int) -> int:
        try:
            if code >= 0 and wparam == PM_REMOVE and lparam:
                msg = ctypes.cast(lparam, ctypes.POINTER(wintypes.MSG)).contents
                if msg.message == WM_KEYDOWN and not (int(msg.lParam) >> 30) & 1:
                    keys.put(int(msg.wParam))
        except Exception:  # noqa: BLE001 - never in the way of the window's own messages
            pass
        return user32.CallNextHookEx(None, code, wparam, lparam)

    callback = hookproc(proc)
    handle = user32.SetWindowsHookExW(WH_GETMESSAGE, callback, None, kernel32.GetCurrentThreadId())
    return callback, handle


def serve_viewer(argv: Sequence[str]) -> int:
    """The stand-in viewer (the child process): the screens on a dark ground, fitted with 20 px round them, turned by
    the page keys posted to it (`key_hook`) and by "next", "prev", "goto N" and "quit" on its standard input. It says
    "ready HWND PID" once its first screen has been drawn at a steady size, "shown N" at each screen, "key VK" at each
    key taken, and "pic N JPEG-BASE64" with what it draws (the page and a little of the ground round it)."""
    import tkinter as tk

    from PIL import ImageTk

    ap = argparse.ArgumentParser()
    ap.add_argument("--serve-viewer", action="store_true")
    ap.add_argument("--title", default="balloon_dream")
    ap.add_argument("--first", type=int, default=4)
    ap.add_argument("--pages", type=int, default=12)
    ap.add_argument("--spread", action="store_true")
    ap.add_argument("--rect", default=",".join(map(str, VIEWER_RECT)))
    args = ap.parse_args(list(argv))
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor, as TASlation's window
    except (AttributeError, OSError):
        pass
    screens = dv.screens_of(dv.page_files(args.title, args.first, args.pages), not args.spread)
    x, y, w, h = (int(v) for v in args.rect.split(","))
    root = tk.Tk()
    root.title(dv.VIEWER_TITLE)
    root.configure(bg=dv.GROUND)
    root.geometry(f"{w}x{h}+{x}+{y}")
    canvas = tk.Canvas(root, bg=dv.GROUND, highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    ground = tuple(int(dv.GROUND[i:i + 2], 16) for i in (1, 3, 5))
    state: dict[str, Any] = {"index": 0, "photo": None, "size": None, "ready": False, "steady": 0}
    told: queue.Queue[str] = queue.Queue()
    keys: queue.Queue[int] = queue.Queue()
    hook = key_hook(keys)  # noqa: F841 - kept alive with the window

    def say(line: str) -> None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def picture(shown: Image.Image) -> None:
        m = max(4, shown.height // 40)
        pic = Image.new("RGB", (shown.width + 2 * m, shown.height + 2 * m), ground)
        pic.paste(shown, (m, m))
        k = min(1.0, PIC_HEIGHT / pic.height)
        if k < 1:
            pic = pic.resize((max(1, round(pic.width * k)), max(1, round(pic.height * k))), Image.LANCZOS)
        buffer = io.BytesIO()
        pic.save(buffer, format="JPEG", quality=88)
        say(f"pic {state['index']} {base64.b64encode(buffer.getvalue()).decode('ascii')}")

    def draw(force: bool = False) -> None:
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if cw < 50 or ch < 50 or (not force and state["size"] == (cw, ch)):
            return
        state["size"] = (cw, ch)
        page = screens[state["index"]]
        scale = min((cw - 40) / page.width, (ch - 40) / page.height)
        shown = page.resize((max(1, int(page.width * scale)), max(1, int(page.height * scale))), Image.LANCZOS)
        state["photo"] = ImageTk.PhotoImage(shown)
        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, image=state["photo"])
        picture(shown)

    def show(index: int) -> None:
        state["index"] = max(0, min(len(screens) - 1, index))
        draw(force=True)
        root.update_idletasks()
        say(f"shown {state['index']}")

    def listen() -> None:  # (a thread: Tk is left to its own loop, which takes the lines from the queue)
        for line in sys.stdin:
            told.put(line.strip())
        told.put("quit")

    def take() -> None:
        while True:
            try:
                vk = keys.get_nowait()
            except queue.Empty:
                break
            say(f"key {vk}")
            if vk in KEY_TURNS:
                show(state["index"] + KEY_TURNS[vk])
            elif vk in KEY_ENDS:
                show(0 if KEY_ENDS[vk] == "first" else len(screens) - 1)
        while True:
            try:
                line = told.get_nowait()
            except queue.Empty:
                break
            if line == "next":
                show(state["index"] + 1)
            elif line == "prev":
                show(state["index"] - 1)
            elif line.startswith("goto "):
                show(int(line.split()[1]))
            elif line == "quit":
                root.destroy()
                return
        if not state["ready"]:  # drawn at its size for 0.3 s
            drawn = state["size"] == (canvas.winfo_width(), canvas.winfo_height())
            state["steady"] = state["steady"] + 1 if drawn else 0
            if state["steady"] >= 15:
                state["ready"] = True
                say(f"ready {int(root.wm_frame(), 16)} {os.getpid()}")
                say(f"shown {state['index']}")
        root.after(20, take)

    root.bind("<Configure>", lambda _e: draw())
    root.after(50, take)
    threading.Thread(target=listen, daemon=True).start()
    root.mainloop()
    return 0


class StandIn:
    """The stand-in viewer seen from this tool: the child process, its window's handle and process, the screen on
    show, the keys it took and the pictures it drew (written into the recording as they come)."""

    def __init__(self, args: argparse.Namespace, rect: tuple[int, int, int, int], writer: Any = None):
        command = [sys.executable, str(Path(__file__).resolve()), "--serve-viewer", "--title", args.title,
                   "--first", str(args.first), "--pages", str(args.pages), "--rect", ",".join(map(str, rect))]
        command += ["--spread"] if args.spread else []
        self.writer = writer
        self.lock = threading.Lock()
        self.index = 0
        self.screens = args.pages if not args.spread else (args.pages + 1) // 2
        self.keys: list[list[float]] = []  # [t, vk] of each key taken
        self.shown: list[list[float]] = []  # [t, screen]
        self.pics: list[list[Any]] = []  # [t, screen, name in the recording]
        self.ready_lines: queue.Queue[str] = queue.Queue()
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                     encoding="utf-8", bufsize=1)
        threading.Thread(target=self._read, name="intro-standin", daemon=True).start()
        self.hwnd, self.pid = self._ready()

    def _read(self) -> None:
        for raw in self.proc.stdout:  # type: ignore[union-attr]
            word, _sep, rest = raw.strip().partition(" ")
            t = round(pv.now_ms(), 1)
            try:
                if word == "ready":
                    self.ready_lines.put(rest)
                elif word == "shown":
                    with self.lock:
                        self.index = int(rest)
                        self.shown.append([t, int(rest)])
                elif word == "key":
                    with self.lock:
                        self.keys.append([t, int(rest)])
                elif word == "pic":
                    index, data = rest.split(" ", 1)
                    self._keep(t, int(index), base64.b64decode(data))
            except (ValueError, OSError):
                continue

    def _keep(self, t: float, index: int, data: bytes) -> None:
        with self.lock:
            name = f"viewer/{len(self.pics):04d}.jpg"
            self.pics.append([t, index, name])
        writer = self.writer
        if writer is not None:
            with writer.lock, contextlib.suppress(ValueError, OSError):
                writer.zip.writestr(name, data)

    def _ready(self, seconds: float = 30.0) -> tuple[int, int]:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                line = self.ready_lines.get(timeout=0.2)
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise SystemExit("the stand-in viewer did not start") from None
                continue
            hwnd, pid = line.split()
            return int(hwnd), int(pid)
        raise SystemExit("the stand-in viewer did not come up")

    def taken(self) -> int:
        with self.lock:
            return len(self.keys)

    def tell(self, line: str) -> None:
        """A line to the child ("next", "prev", "goto N"): no key goes anywhere."""
        with contextlib.suppress(OSError, ValueError):
            self.proc.stdin.write(line + "\n")  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]

    def alive(self) -> bool:
        return self.proc.poll() is None or dv._process_alive(self.pid)

    def close(self) -> None:
        self.tell("quit")
        with contextlib.suppress(OSError, ValueError):
            self.proc.stdin.close()  # type: ignore[union-attr]
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        if dv._process_alive(self.pid):  # (a venv's python.exe starts the interpreter as a process of its own)
            dv._end_process(self.pid)


# ---------------------------------------------------------------------------------------------------- the pictures
def _user32() -> Any:
    user32 = ctypes.WinDLL("user32")
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    return user32


def own_windows_above(main: int) -> list[int]:
    """This process's own visible top-level windows above *main* (its dialogs, lists, panels, tips), the top one
    first; another program's window is never among them."""
    user32 = _user32()
    pid = os.getpid()
    found: list[int] = []
    enum = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(hwnd: Any, _lparam: Any) -> bool:
        h = int(hwnd or 0)
        if h == main:
            return False
        if h and user32.IsWindowVisible(h) and not user32.IsIconic(h):
            owner = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
            if owner.value == pid:
                found.append(h)
        return True

    user32.EnumWindows(enum(each), 0)
    return found


def frame_of(hwnd: int) -> tuple[int, int, int, int]:
    """The window *hwnd* as the compositor shows it (without its invisible borders), on the screen."""
    from taslation.capture import windows

    bounds = getattr(windows, "_frame_bounds", None)
    box = bounds(hwnd) if bounds is not None else windows.window_rect(hwnd)
    return tuple(int(v) for v in box)  # type: ignore[return-value]


class Grabber:
    """Pictures of TASlation's window (*hwnd*: this process's, never the stand-in) with this process's own windows over
    it pasted where they are, about *fps* a second from a thread of its own, into the recording; where the window was
    on the screen (`boxes`: its frame and its client area's top left, each time they change). Paused between the
    scenes."""

    def __init__(self, hwnd: int, guard: Any, writer: Any, fps: float, client_only: bool = False):
        if not guard.is_own(hwnd) or guard.is_viewer(hwnd):
            raise SystemExit("the window to picture is not TASlation's own")
        self.hwnd, self.writer, self.period, self.client_only = hwnd, writer, 1.0 / fps, client_only
        self.boxes: list[list[float]] = []
        self.on = False
        self.active = False
        self.failed = ""
        self.taken = self.missed = 0
        self.wake = threading.Event()
        self.saving: queue.Queue[Any] = queue.Queue(maxsize=120)
        self.thread = threading.Thread(target=self._loop, name="intro-grab", daemon=True)
        self.saver = threading.Thread(target=self._save, name="intro-save", daemon=True)

    def start(self) -> None:
        self.on = True
        self.saver.start()
        self.thread.start()

    def resume(self) -> None:
        self.active = True
        self.wake.set()

    def pause(self) -> None:
        self.active = False

    def stop(self) -> None:
        self.on = self.active = False
        self.wake.set()
        if self.thread.is_alive():
            self.thread.join(10)
        if self.saver.is_alive():
            self.saving.put(None)
            self.saver.join(120)

    def picture(self) -> tuple[Image.Image, list[int]]:
        """The window and this process's windows over it, and [left, top, right, bottom, client x, client y]."""
        from taslation.capture import windows

        cx, cy, cw, ch = windows.client_rect_on_screen(self.hwnd)
        if self.client_only:
            box = (cx, cy, cx + cw, cy + ch)
            base = windows.capture_window(self.hwnd, client_only=True, allow_screen_fallback=False)
        else:
            box = frame_of(self.hwnd)
            whole = windows.window_rect(self.hwnd)
            raw = windows.capture_window(self.hwnd, client_only=False, allow_screen_fallback=False)
            base = raw.crop((box[0] - whole[0], box[1] - whole[1], box[2] - whole[0], box[3] - whole[1]))
        base = base.convert("RGB")
        for other in reversed(own_windows_above(self.hwnd)):
            try:
                fb, whole = frame_of(other), windows.window_rect(other)
                if fb[2] <= box[0] or fb[0] >= box[2] or fb[3] <= box[1] or fb[1] >= box[3]:
                    continue
                img = windows.capture_window(other, client_only=False, allow_screen_fallback=False)
                part = img.crop((fb[0] - whole[0], fb[1] - whole[1], fb[2] - whole[0], fb[3] - whole[1]))
                base.paste(part.convert("RGB"), (fb[0] - box[0], fb[1] - box[1]))
            except Exception as e:  # noqa: BLE001 - a window going as it is pictured; a refused call is not that
                if type(e).__name__ == "Refused":
                    raise
        return base, [*box, cx, cy]

    def _grab(self) -> None:
        t = round(pv.now_ms(), 1)
        try:
            image, box = self.picture()
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ == "Refused":
                self.failed = "a picture was refused"
                self.on = False
            self.missed += 1
            return
        self.taken += 1
        if not self.boxes or self.boxes[-1][1:] != box:
            self.boxes.append([t, *box])
        try:
            self.saving.put((t, image), timeout=2)
        except queue.Full:
            self.missed += 1

    def _loop(self) -> None:
        while self.on:
            if not self.active:
                self.wake.wait(0.1)
                self.wake.clear()
                continue
            began = time.perf_counter()
            self._grab()
            self.wake.wait(max(0.0, self.period - (time.perf_counter() - began)))
            self.wake.clear()

    def _save(self) -> None:
        while True:
            item = self.saving.get()
            if item is None:
                return
            try:
                self.writer.add(*item)
            except Exception:  # noqa: BLE001 - said once
                self.failed = self.failed or "a picture could not be saved"

    def facts(self) -> dict[str, Any]:
        return {"taken": self.taken, "missed": self.missed, "kept": self.writer.stored, "failed": self.failed}


# ---------------------------------------------------------------------------------------------------- the director
class SceneFailed(RuntimeError):
    """A scene that could not go on (what it waited for did not come)."""


@dataclass
class Until:
    test: Callable[[], bool]
    timeout: float
    what: str
    deadline: float = 0.0


class Pointer:
    """The pointer the window is told about (`winfo_pointerxy` and its two halves answer with it while it is set):
    the real one never moves. Set from the first scene on."""

    NAMES = ("winfo_pointerxy", "winfo_pointerx", "winfo_pointery")

    def __init__(self) -> None:
        self.at: tuple[float, float] | None = None
        self.saved: dict[str, Any] = {}

    def install(self) -> None:
        import tkinter

        self.saved = {name: getattr(tkinter.Misc, name) for name in self.NAMES}
        real = self.saved
        me = self

        def xy(widget: Any) -> tuple[int, int]:
            return (int(me.at[0]), int(me.at[1])) if me.at is not None else real["winfo_pointerxy"](widget)

        tkinter.Misc.winfo_pointerxy = xy  # type: ignore[method-assign]
        tkinter.Misc.winfo_pointerx = lambda w: xy(w)[0]  # type: ignore[method-assign]
        tkinter.Misc.winfo_pointery = lambda w: xy(w)[1]  # type: ignore[method-assign]

    def remove(self) -> None:
        import tkinter

        for name, original in self.saved.items():
            setattr(tkinter.Misc, name, original)


def find_widget(root: Any, cls: str, text_starts: str = "") -> Any:
    """The first widget of Tk class *cls* under *root* whose text starts with *text_starts*."""
    for widget in [root, *dv.walk(root)]:
        with contextlib.suppress(Exception):
            if widget.winfo_class() == cls and str(widget.cget("text")).startswith(text_starts):
                return widget
    return None


def post_list(box: Any) -> str:
    """The list of the combobox *box* shown as a click on it shows it - its own -postcommand run first, the list
    filled, placed under the box and raised (ttk's own steps) - but without the grab ttk takes then: nothing of the
    system's pointer or keyboard is held. The path of its listbox; "" where it could not be shown."""
    t = box.tk
    try:
        t.eval(f"uplevel #0 [{box} cget -postcommand]")
        popdown = str(t.eval(f"ttk::combobox::PopdownWindow {box}"))
        t.eval(f"ttk::combobox::ConfigureListbox {box}")
        t.call("update", "idletasks")
        t.eval(f"ttk::combobox::PlacePopdown {box} {popdown}")
        t.call("wm", "transient", popdown, str(box.winfo_toplevel()))
        t.call("wm", "deiconify", popdown)
        t.call("raise", popdown)
        box.state(["pressed"])
        return f"{popdown}.f.l"
    except Exception:  # noqa: BLE001 - the entry is picked without the list shown
        unpost_list(box)
        return ""


def unpost_list(box: Any) -> None:
    """The combobox *box*'s list put away where it shows (ttk's own Unpost)."""
    with contextlib.suppress(Exception):
        if int(box.tk.eval(f"winfo exists {box}.popdown")) and int(box.tk.eval(f"winfo ismapped {box}.popdown")):
            box.tk.eval(f"ttk::combobox::Unpost {box}")
    with contextlib.suppress(Exception):
        box.state(["!pressed"])


class Director:
    """The scenes on the Tk loop, each a generator that yields a wait (seconds, or `Until`), acting on the window's own
    widgets; what it did, numbers only (`records`)."""

    def __init__(self, app: Any, standin: StandIn, guard: Any, probe: Any, grabber: Grabber, pointer: Pointer,
                 args: argparse.Namespace, scenes: Sequence[Scene], term: tuple[str, str] | None):
        self.app, self.standin, self.guard, self.probe = app, standin, guard, probe
        self.grabber, self.pointer, self.args, self.scenes, self.term = grabber, pointer, args, scenes, term
        self.failed = ""
        self.done = False
        self.gen: Iterator[Any] | None = None
        self.waiting: Any = None
        self.scene: dict[str, Any] | None = None
        self.on_canvas = False
        self.down = False
        self.off_page = False  # a dialog of the window's is over the page: the pointer's moves are the dialog's
        self.stepping = False
        self.watch_from: float | None = None
        self.name: tuple[str, str] | None = None  # a name read on a page and its rendering (`note_name`; memory only)
        self.records: dict[str, Any] = {"scenes": [], "skipped": [], "pointer": [], "keys": [], "regions": [],
                                        "masks": [], "moments": {}, "turned_by_tool": 0}
        self.began = time.monotonic()

    # the loop
    def start(self) -> None:
        self.gen = self.program()
        self.app.after(TICK_MS, self._loop)

    def _loop(self) -> None:
        """A tick: the next one is due whatever this one does (one chain of ticks only); a tick that comes while a
        step is under way (a call of the window's that runs Tk's loop inside it) does nothing. What may hold the
        window with a dialog of its own is never called from a step but from Tk's loop (`later`)."""
        if self.done or self.failed:
            return
        self.app.after(TICK_MS, self._loop)
        if self.stepping:
            return
        self.stepping = True
        try:
            problem = self.check()
            if problem:
                self.fail(problem)
                return
            self.follow_window()
            self.watch()
            self.note_name()
            self._step()
        except Exception as e:  # noqa: BLE001 - said, and the run ends
            traceback.print_exc()
            self.fail(f"{type(e).__name__} in the director")
        finally:
            self.stepping = False

    def later(self, call: Callable[[], Any]) -> None:
        """*call* from Tk's loop, as a click's command runs: one that holds the window with a dialog of its own does
        not hold the director, which goes on in the dialog's own loop."""
        self.app.after(0, call)

    def follow_window(self) -> None:
        """The window's handle given to the pictures again where Tk made it anew (the full screen does)."""
        try:
            hwnd = int(self.app.wm_frame(), 16)
        except Exception:  # noqa: BLE001
            return
        if hwnd != self.grabber.hwnd and self.guard.is_own(hwnd) and not self.guard.is_viewer(hwnd):
            self.grabber.hwnd = hwnd

    def _step(self) -> None:
        now = time.monotonic()
        w = self.waiting
        if isinstance(w, float):
            if now < w:
                return
        elif isinstance(w, Until):
            try:
                ok = bool(w.test())
            except Exception:  # noqa: BLE001 - not yet
                ok = False
            if not ok:
                if now < w.deadline:
                    return
                self.waiting = None
                self._took(lambda: self.gen.throw(SceneFailed(f"timed out: {w.what}")))  # type: ignore[union-attr]
                return
        self.waiting = None
        self._took(lambda: next(self.gen))  # type: ignore[arg-type]

    def _took(self, advance: Callable[[], Any]) -> None:
        try:
            value = advance()
        except StopIteration:
            self.finish()
            return
        if isinstance(value, Until):
            value.deadline = time.monotonic() + value.timeout
            self.waiting = value
        else:
            self.waiting = time.monotonic() + float(value or 0.0)

    def check(self) -> str:
        """Why the run must end now: a call refused, a window other than the stand-in chosen, the stand-in gone."""
        selected = getattr(self.app, "selected", None)
        if selected is not None and int(selected.hwnd) != self.standin.hwnd:
            return "a window other than the stand-in was chosen"
        if self.guard.refused:
            return f"a call was refused: {', '.join(sorted(set(self.guard.refused)))}"
        if self.grabber.failed:
            return self.grabber.failed
        if not self.standin.alive():
            return "the stand-in viewer closed"
        return ""

    def fail(self, why: str) -> None:
        if not self.failed:
            self.failed = why
            print(f"intro ended: {why}", file=sys.stderr, flush=True)
        self.finish()

    def finish(self) -> None:
        """No picture after this one; Tk's loop goes on a moment (a picture under way may need the window's thread to
        draw it), then ends."""
        self.done = True
        self.grabber.pause()
        self.grabber.on = False
        self.grabber.wake.set()
        faulthandler.dump_traceback_later(CLOSE_WAIT_S)  # (where it hangs, should the window not close)
        self.app.after(500, self.app.quit)

    def say(self, what: str) -> None:
        print(f"{time.monotonic() - self.began:7.1f} s  {what}", file=sys.stderr, flush=True)

    # what is noted
    def watch(self) -> None:
        """The three moments of the first page translated in a scene (for the "how" card's pictures): its page shown,
        half its bubbles lettered, all of them."""
        if self.watch_from is None:
            return
        moments = self.records["moments"]
        fills = [f for f in self.probe.fills if f["t"] >= self.watch_from]
        if fills:
            fill = fills[-1]
            moments.setdefault("original", fill["t"])
            done = sum(1 for x in self.probe.letters if x["n"] == fill["n"] and x["on"])
            if "filling" not in moments and fill["boxes"] and max(1, fill["boxes"] // 2) <= done < fill["boxes"]:
                moments["filling"] = round(pv.now_ms(), 1)
        results = [r for r in self.probe.results if r["t"] >= self.watch_from]
        if results and not self.app.busy and "original" in moments:
            moments.setdefault("translated", round(pv.now_ms() + 300, 1))
            self.watch_from = None

    def fast(self, on: bool) -> None:
        """A stretch of waiting for the models begins (*on*) or ends: shown faster where the scene is long."""
        if self.scene is None:
            return
        spans = self.scene["fast"]
        if on and (not spans or spans[-1][1] is not None):
            spans.append([round(pv.now_ms(), 1), None])
        elif not on and spans and spans[-1][1] is None:
            spans[-1][1] = round(pv.now_ms(), 1)

    def note_region(self, what: str, region: Any) -> None:
        box = self.region_box(region)
        if box is not None:
            self.records["regions"].append({"t": round(pv.now_ms(), 1), "what": what, "box": [round(v) for v in box]})

    # the program
    def program(self) -> Iterator[Any]:
        app = self.app
        yield Until(lambda: bool(getattr(app, "ready", False)), self.args.ready_timeout, "the window ready")
        self.say("the window is ready")
        yield 1.0
        self.pointer.at = self.park_point()
        self.grabber.start()
        for scene in self.scenes:
            entry: dict[str, Any] = {"id": scene.id, "t0": None, "t1": None, "fast": [], "failed": ""}
            try:
                yield from self.prepare(scene)
            except SceneFailed as e:
                self.records["skipped"].append({"id": scene.id, "why": str(e)[:100]})
                continue
            self.grabber.resume()
            yield 0.4
            entry["t0"] = round(pv.now_ms(), 1)
            self.scene = entry
            self.say(f"scene {scene.id}")
            try:
                yield from getattr(self, f"act_{scene.id}")()
                yield 0.5
            except SceneFailed as e:
                entry["failed"] = str(e)[:100]
                self.say(f"scene {scene.id} failed: {e}")
            self.fast(False)
            entry["t1"] = round(pv.now_ms(), 1)
            self.scene = None
            self.records["scenes"].append(entry)
            self.grabber.pause()
            after = getattr(self, f"after_{scene.id}", None)
            if after is not None and not entry["failed"]:  # (what a scene leaves put back, with no picture taken)
                try:
                    yield from after()
                except SceneFailed as e:
                    self.say(f"after {scene.id}: {e}")
                    yield from self.reset()
            if entry["failed"]:
                yield from self.reset()
        yield from self.reset()
        try:  # (nothing under way as the window closes: a page still read or translated waits for it)
            yield 1.5
            yield Until(lambda: not app.busy, 90, "the window idle")
            yield 1.0
        except SceneFailed as e:
            self.say(f"closing while busy: {e}")
        self.say("scenes over")

    def prepare(self, scene: Scene) -> Iterator[Any]:
        """What a scene begins from, done before its pictures: the stand-in chosen and its page translated, no dialog
        open, the window out of the full screen, the Reader role for a Reader's scene."""
        app = self.app
        yield from self.reset()
        if scene.id == "viewer" and getattr(app, "selected", None) is not None:
            raise SceneFailed("the stand-in was chosen already")
        if scene.id != "viewer" and getattr(app, "selected", None) is None:
            self.choose_quietly()
            yield Until(lambda: getattr(app, "selected", None) is not None, 15, "the stand-in chosen")
        if scene.role == "reader" and str(app.role_var.get()) != "reader":
            self.choose_role("reader")
            yield 1.0
        if scene.id != "viewer":
            yield Until(lambda: not app.busy and app.last_result is not None, self.args.timeout, "a page translated")
        yield 0.3

    def reset(self) -> Iterator[Any]:
        """The lists put away, the panel beside a bubble hidden, the dialogs this tool opens closed as their own
        Close closes them (from Tk's loop), the full screen left, the selection let go."""
        from taslation.ui.dialogs.batch import BatchDialog
        from taslation.ui.dialogs.caches import WarningBox
        from taslation.ui.dialogs.glossary import GlossaryDialog
        from taslation.ui.dialogs.review import EditBubbleDialog

        app = self.app
        self.off_page = self.down = False
        self.unmask()
        for box in (getattr(app, "window_box", None), getattr(app, "lang_box", None)):
            if box is not None:
                unpost_list(box)
        with contextlib.suppress(Exception):
            app._zoom_hide()
        for top in list(app.winfo_children()):
            with contextlib.suppress(Exception):
                if isinstance(top, WarningBox):
                    self.later(top.cancel_btn.invoke)
                elif isinstance(top, GlossaryDialog):
                    self.later(top._close)
                elif isinstance(top, (EditBubbleDialog, BatchDialog)) and top.winfo_exists():
                    self.later(top.destroy)
        yield 0.5
        if getattr(app, "reading", False):
            self.later(app.toggle_reading)
            yield 1.5
        with contextlib.suppress(Exception):
            app._choose(None)
        yield 0.2

    # the pointer
    def park_point(self) -> tuple[float, float]:
        app = self.app
        return (app.winfo_rootx() + app.winfo_width() - 40, app.winfo_rooty() + app.winfo_height() - 60)

    def to_canvas(self, sx: float, sy: float) -> tuple[int, int]:
        canvas = self.app.canvas
        return int(round(sx - canvas.winfo_rootx())), int(round(sy - canvas.winfo_rooty()))

    def move_to(self, sx: float, sy: float) -> None:
        """The pointer at (sx, sy) on the screen: noted, told to the window, and a motion on the page where it is on
        it (Tk's event, never the system's pointer)."""
        self.pointer.at = (sx, sy)
        self.records["pointer"].append([round(pv.now_ms(), 1), int(round(sx)), int(round(sy)), int(self.down)])
        canvas = self.app.canvas
        cx, cy = self.to_canvas(sx, sy)
        inside = (not self.off_page and bool(canvas.winfo_viewable()) and 0 <= cx < canvas.winfo_width()
                  and 0 <= cy < canvas.winfo_height())
        if inside:
            canvas.event_generate("<B1-Motion>" if self.down else "<Motion>", x=cx, y=cy, rootx=int(sx),
                                  rooty=int(sy))
        elif self.on_canvas and not self.down:
            canvas.event_generate("<Leave>", x=cx, y=cy)
        self.on_canvas = inside

    def glide(self, sx: float, sy: float, seconds: float = 0.7) -> Iterator[Any]:
        x0, y0 = self.pointer.at or (sx, sy)
        steps = max(1, int(seconds * GLIDE_HZ))
        for i in range(1, steps + 1):
            u = i / steps
            e = u * u * (3 - 2 * u)
            self.move_to(x0 + (sx - x0) * e, y0 + (sy - y0) * e)
            yield 1.0 / GLIDE_HZ

    def centre(self, widget: Any) -> tuple[float, float]:
        return (widget.winfo_rootx() + widget.winfo_width() / 2, widget.winfo_rooty() + widget.winfo_height() / 2)

    def glide_to(self, widget: Any, seconds: float = 0.7) -> Iterator[Any]:
        yield from self.glide(*self.centre(widget), seconds=seconds)

    def mark_press(self) -> Iterator[Any]:
        """The pointer drawn pressed a moment (a click on a widget that is then invoked)."""
        self.down = True
        self.move_to(*self.pointer.at)  # type: ignore[misc]
        yield 0.12
        self.down = False
        self.move_to(*self.pointer.at)  # type: ignore[misc]

    def click_widget(self, widget: Any, seconds: float = 0.7) -> Iterator[Any]:
        """Glide to *widget*, press, and its command run as a click runs it (from Tk's loop: a command that holds
        the window with a dialog of its own does not hold the director)."""
        yield from self.glide_to(widget, seconds)
        yield 0.15
        yield from self.mark_press()
        self.app.after(0, widget.invoke)
        yield 0.2

    def editing(self) -> None:
        """A press on the page is the Translator's only while the page is the one its regions belong to; any other
        press goes on to the viewer as a click, which this tool never makes (the guard would refuse it)."""
        if not self.app._editing():
            raise SceneFailed("the page is not one the Translator edits")

    def press_on_page(self, sx: float, sy: float) -> None:
        self.editing()
        cx, cy = self.to_canvas(sx, sy)
        self.down = True
        self.records["pointer"].append([round(pv.now_ms(), 1), int(sx), int(sy), 1])
        self.app.canvas.event_generate("<ButtonPress-1>", x=cx, y=cy, rootx=int(sx), rooty=int(sy),
                                       time=self.event_time())

    def release_on_page(self, sx: float, sy: float) -> None:
        cx, cy = self.to_canvas(sx, sy)
        self.app.canvas.event_generate("<ButtonRelease-1>", x=cx, y=cy, rootx=int(sx), rooty=int(sy),
                                       time=self.event_time())
        self.down = False
        self.records["pointer"].append([round(pv.now_ms(), 1), int(sx), int(sy), 0])

    @staticmethod
    def event_time() -> int:
        return int(time.monotonic() * 1000) & 0x7FFFFFFF

    def drag(self, start: tuple[float, float], end: tuple[float, float], seconds: float = 0.9) -> Iterator[Any]:
        """A drag on the page from *start* to *end* (Tk's press, motions and release)."""
        yield from self.glide(*start, seconds=0.5)
        yield 0.15
        self.press_on_page(*start)
        yield 0.15
        yield from self.glide(*end, seconds=seconds)
        yield 0.15
        self.release_on_page(*end)
        yield 0.2

    # keys
    def key(self, label: str, passed_on: bool) -> dict[str, Any]:
        rec = {"t": round(pv.now_ms(), 1), "key": label, "passed_on": passed_on, "posted": 0, "taken": 0}
        self.records["keys"].append(rec)
        return rec

    def press_page_key(self, meaning: str, may_fail: bool = False) -> Iterator[Any]:
        """The window's next or previous page key pressed on its page (Tk's key event, whose binding hands it to
        `forward_key`; the binding's own call where Tk does not deliver it), once; the key the window passes on turns
        the stand-in. *may_fail*: where it does not (a run that does not pass keys on), the stand-in is told to turn
        instead and no key cap is kept."""
        from taslation.ui.constants import FORWARDED_KEYS

        app = self.app
        pair = app._page_key_pair()
        key = getattr(pair[1], meaning, "") if pair is not None else ""
        key = key or ("Left" if meaning == "next" else "Right")
        keysym = next((k for k, v in FORWARDED_KEYS.items() if v == key), key)
        index, posted, taken = self.standin.index, self.guard.used.get("post_key", 0), self.standin.taken()
        rec = self.key(key, True)
        calls: list[str] = []

        def counted(k: str) -> None:
            calls.append(k)
            type(app).forward_key(app, k)

        app.forward_key = counted
        try:
            app.canvas.event_generate(f"<KeyPress-{keysym}>")
            app.canvas.event_generate(f"<KeyRelease-{keysym}>")
        finally:
            del app.forward_key
        if not calls:
            app.forward_key(key)
        try:
            yield Until(lambda: self.standin.index != index, 4.0, "the stand-in turned by the page key")
        except SceneFailed:
            if not may_fail:
                raise
            self.records["keys"].remove(rec)
            self.records["turned_by_tool"] += 1
            self.standin.tell("next" if meaning == "next" else "prev")
            yield Until(lambda: self.standin.index != index, 4.0, "the stand-in turned")
        yield 0.3
        rec["posted"] = self.guard.used.get("post_key", 0) - posted
        rec["taken"] = self.standin.taken() - taken

    def press_key(self, keysym: str, label: str, fallback: Callable[[], Any], done: Callable[[], bool]) -> Iterator[Any]:
        """A key of the window's own (not passed on) pressed on its page, queued as Tk queues a key (Tk drops it
        while another program has the keyboard); the command bound to it, from Tk's loop, where it did nothing."""
        self.key(label, False)
        self.app.canvas.event_generate(f"<KeyPress-{keysym}>", when="tail")
        self.app.canvas.event_generate(f"<KeyRelease-{keysym}>", when="tail")
        yield 0.4
        if not done():
            self.later(fallback)
            yield 0.3

    # the window's state
    def results(self) -> int:
        return len(self.probe.results)

    def page_after(self, count: int, before: Any) -> Callable[[], bool]:
        app = self.app
        return lambda: (self.results() > count or app.last_result is not before) and not app.busy

    def choose_quietly(self) -> None:
        """The stand-in chosen in the Viewer list as a pick in it chooses it (before a scene's pictures)."""
        app = self.app
        app._rescan_windows()
        index = next((i for i, w in enumerate(app.windows) if int(w.hwnd) == self.standin.hwnd), None)
        if index is None:
            raise SceneFailed("the stand-in is not in the Viewer list")
        app.window_box.current(index)
        self.later(lambda: app.window_box.event_generate("<<ComboboxSelected>>"))

    def role_radio(self, value: str) -> Any:
        app = self.app
        return next((w for w in dv.walk(app) if w.winfo_class() == "TRadiobutton" and str(w.cget("value")) == value
                     and str(w.cget("variable")) == str(app.role_var)), None)

    def choose_role(self, value: str) -> Any:
        app = self.app
        radio = self.role_radio(value)
        if radio is None:
            app.role_var.set(value)
            self.later(app._on_role_changed)
        else:
            self.later(radio.invoke)
        return radio

    def role_shown(self, value: str) -> Iterator[Any]:
        """The role chosen with its button, the pointer going there (nothing where it is chosen already)."""
        app = self.app
        if str(app.role_var.get()) == value:
            return
        radio = self.role_radio(value)
        if radio is None:
            self.choose_role(value)
        else:
            yield from self.click_widget(radio)
        yield Until(lambda: str(app.role_var.get()) == value, 5, f"the {value} role")
        yield 0.8

    def regions(self, translated: bool = True) -> list[Any]:
        app = self.app
        try:
            found = list(app._page_regions())
        except Exception:  # noqa: BLE001
            return []
        found = [r for r in found if app.canvas.inside(*self.canvas_point(r))]
        if translated:
            found = [r for r in found if getattr(r, "status", "") == "translated"] or found
        return sorted(found, key=lambda r: -(r.bbox[2] - r.bbox[0]) * (r.bbox[3] - r.bbox[1]))

    def canvas_point(self, region: Any, at: tuple[float, float] = (0.5, 0.5)) -> tuple[float, float]:
        from taslation.ui import area

        x0, y0, x1, y1 = region.bbox
        return area.to_canvas(x0 + (x1 - x0) * at[0], y0 + (y1 - y0) * at[1], self.app.canvas.scale,
                              self.app.canvas.offset)

    def screen_point(self, region: Any, at: tuple[float, float] = (0.5, 0.5)) -> tuple[float, float]:
        cx, cy = self.canvas_point(region, at)
        canvas = self.app.canvas
        return canvas.winfo_rootx() + cx, canvas.winfo_rooty() + cy

    def region_box(self, region: Any) -> tuple[float, float, float, float] | None:
        try:
            a = self.screen_point(region, (0.0, 0.0))
            b = self.screen_point(region, (1.0, 1.0))
        except Exception:  # noqa: BLE001
            return None
        return (a[0], a[1], b[0], b[1])

    def toplevel(self, cls: Any) -> Any:
        return next((w for w in self.app.winfo_children() if isinstance(w, cls) and w.winfo_exists()), None)

    def wait_page(self, count: int, before: Any, what: str) -> Iterator[Any]:
        self.fast(True)
        yield Until(self.page_after(count, before), self.args.timeout, what)
        self.fast(False)

    # the scenes
    def act_viewer(self) -> Iterator[Any]:
        """The Viewer list opened (its own rescan), the stand-in picked in it, the page translated bubble by bubble."""
        app = self.app
        box = app.window_box
        yield 0.6
        yield from self.glide_to(box, 0.9)
        yield 0.2
        yield from self.mark_press()
        listbox = post_list(box)  # (its -postcommand looks for the windows again)
        yield 0.8
        index = next((i for i, w in enumerate(app.windows) if int(w.hwnd) == self.standin.hwnd), None)
        if index is None:
            unpost_list(box)
            raise SceneFailed("the stand-in is not in the Viewer list")
        count, before = self.results(), app.last_result
        self.watch_from = pv.now_ms()
        picked = yield from self.pick_in_list(box, listbox, index, 160)
        if not picked:
            box.current(index)
            self.later(lambda: box.event_generate("<<ComboboxSelected>>"))
        yield Until(lambda: getattr(app, "selected", None) is not None and int(app.selected.hwnd) == self.standin.hwnd,
                    10, "the stand-in chosen")
        yield from self.glide(*self.park_point(), seconds=0.8)
        yield from self.wait_page(count, before, "the first page translated")
        yield 1.5

    def pick_in_list(self, box: Any, listbox: str, index: int, width: int) -> Iterator[Any]:
        """The pointer to the list's entry *index*, the entry chosen and the list left as a click in it leaves it
        (ttk's own LBSelected: the box's <<ComboboxSelected>> comes from Tk's queue). False where it could not be."""
        if not listbox:
            return False
        try:
            box.tk.call(listbox, "see", index)
            yield 0.3
            x, y, w, h = (int(v) for v in box.tk.splitlist(box.tk.call(listbox, "bbox", index)))
            rx, ry = int(box.tk.call("winfo", "rootx", listbox)), int(box.tk.call("winfo", "rooty", listbox))
            yield from self.glide(rx + x + min(w, width) / 2, ry + y + h / 2, 0.6)
            box.tk.call(listbox, "selection", "clear", 0, "end")
            box.tk.call(listbox, "selection", "set", index)
            box.tk.call(listbox, "activate", index)
            yield 0.5
            yield from self.mark_press()
            box.tk.call("ttk::combobox::LBSelected", listbox)
            return True
        except Exception:  # noqa: BLE001 - picked as the list's own selection would
            unpost_list(box)
            return False

    def act_next_page(self) -> Iterator[Any]:
        app = self.app
        yield from self.glide(app.canvas.winfo_rootx() + app.canvas.winfo_width() * 0.85,
                              app.canvas.winfo_rooty() + app.canvas.winfo_height() * 0.5, 0.6)
        yield 0.3
        count, before = self.results(), app.last_result
        if "translated" not in self.records["moments"]:
            self.watch_from = pv.now_ms()
        yield from self.press_page_key("next")
        yield from self.wait_page(count, before, "the next page translated")
        yield 1.5

    def act_original(self) -> Iterator[Any]:
        app = self.app
        found = self.regions()
        if not found:
            raise SceneFailed("no translated bubble on the page")
        width = max(1, app.canvas.winfo_width())
        left = [r for r in found if self.canvas_point(r)[0] < 0.6 * width]  # (its panel goes beside it, in the window)
        region = (left or found)[0]
        self.note_region("hovered", region)
        yield from self.glide(*self.screen_point(region), seconds=0.9)
        for _ in range(8):  # the pointer at rest, as a hand's is: a motion now and then where it is
            yield 0.25
            self.move_to(*self.pointer.at)  # type: ignore[misc]
        yield Until(lambda: getattr(app, "_zoom_popup", None) is not None, 4.0, "the panel with the original")
        yield 2.5
        yield from self.glide(*self.park_point(), seconds=0.8)
        yield 0.6

    def act_turned_past(self) -> Iterator[Any]:
        """Three pages turned before each is done, the margin filling, then two turned back: there at once."""
        from taslation.backlog import backlog_of

        app = self.app
        yield from self.glide(app.canvas.winfo_rootx() + app.canvas.winfo_width() * 0.85,
                              app.canvas.winfo_rooty() + app.canvas.winfo_height() * 0.5, 0.5)
        for _ in range(3):
            busy_before = self.results()
            yield from self.press_page_key("next")
            yield Until(lambda: bool(app.busy) or self.results() > busy_before, 10, "the page begun")
            yield 1.6
        count, before = self.results(), app.last_result
        self.fast(True)
        yield Until(self.page_after(count, before), self.args.timeout, "the last page translated")

        def behind_done() -> bool:
            backlog = backlog_of(app, make=False)
            return backlog is None or not backlog.has_work()

        yield Until(behind_done, self.args.timeout, "the pages turned past translated")
        self.fast(False)
        yield 1.2
        for _ in range(2):
            count, before = self.results(), app.last_result
            yield from self.press_page_key("prev")
            yield Until(self.page_after(count, before), 15, "a page turned back to")
            yield 1.3

    def act_language(self) -> Iterator[Any]:
        from taslation.ui.app import shown_target

        app = self.app
        box = app.lang_box
        values = list(box.tk.splitlist(box.cget("values")))
        target = shown_target("Spanish")
        if target not in values:
            raise SceneFailed("no Spanish in the list")
        index = values.index(target)
        yield from self.glide_to(box, 0.8)
        yield 0.2
        yield from self.mark_press()
        count, before = self.results(), app.last_result
        listbox = post_list(box)
        yield 0.5
        picked = yield from self.pick_in_list(box, listbox, index, 120)
        if not picked:
            app.lang_shown.set(target)
            self.later(app._target_picked)
        yield from self.glide(*self.park_point(), seconds=0.6)
        yield from self.wait_page(count, before, "the page in Spanish")
        yield 2.0

    def after_language(self) -> Iterator[Any]:
        """Back to English for the scenes after it, out of the pictures."""
        from taslation.ui.app import shown_target

        app = self.app
        count, before = self.results(), app.last_result
        app.lang_shown.set(shown_target("English"))
        self.later(app._target_picked)
        yield Until(self.page_after(count, before), self.args.timeout, "the page in English again")

    def act_sheet(self) -> Iterator[Any]:
        from taslation.ui.dialogs.caches import WarningBox
        from taslation.ui.dialogs.glossary import GlossaryDialog

        app = self.app
        yield from self.role_shown("translator")
        button = next((b for b in app.tool_btns if str(b.cget("text")).startswith("Series sheet")), None)
        if button is None:
            raise SceneFailed("no Series sheet... button")
        yield from self.click_widget(button)
        yield Until(lambda: self.toplevel(GlossaryDialog) is not None, 10, "the series sheet")
        dialog = self.toplevel(GlossaryDialog)
        self.off_page = True
        yield 0.6
        self.mask_path(dialog)
        if self.term is not None or self.name is not None:
            term, rendering = self.term or self.name  # type: ignore[misc]
            entries = [w for w in dv.walk(dialog) if w.winfo_class() == "TEntry"]
            for var, text, entry in ((dialog.term_var, term, entries[0] if entries else None),
                                     (dialog.rend_var, rendering, entries[1] if len(entries) > 1 else None)):
                if entry is not None:
                    yield from self.glide_to(entry, 0.5)
                    yield from self.mark_press()
                yield from self.type_into(var, text)
                yield 0.3
            add = find_widget(dialog, "TButton", "Add / update")
        else:
            notebook = next((w for w in dv.walk(dialog) if w.winfo_class() == "TNotebook"), None)
            if notebook is None:
                raise SceneFailed("the sheet has no tabs")
            notebook.select(len(notebook.tabs()) - 1)  # (no name read on the page: a choice of the sheet's own words)
            yield 0.8
            box = next((w for w in dv.walk(dialog) if w.winfo_class() == "TCombobox"
                        and str(w.cget("textvariable")) == str(dialog.hon_var)), None)
            if box is None:
                raise SceneFailed("the style guide has no Honorifics list")
            values = list(box.tk.splitlist(box.cget("values")))
            index = next((i for i, v in enumerate(values) if v != dialog.hon_var.get()), None)
            if index is None:
                raise SceneFailed("the Honorifics list has one choice")
            yield from self.glide_to(box, 0.5)
            yield from self.mark_press()
            listbox = post_list(box)
            yield 0.5
            if not (yield from self.pick_in_list(box, listbox, index, 120)):
                dialog.hon_var.set(values[index])
            add = find_widget(dialog, "TButton", "Save style guide")
        if add is None:
            raise SceneFailed("no button to keep it")
        yield from self.click_widget(add, 0.5)
        yield 0.8
        close = find_widget(dialog, "TButton", "Close")
        if close is not None:
            yield from self.click_widget(close, 0.6)
        else:
            self.later(dialog._close)
        yield Until(lambda: self.toplevel(GlossaryDialog) is None, 5, "the series sheet closed")
        self.unmask()
        self.off_page = False
        again = next((b for b in app.tool_btns if str(b.cget("text")).startswith("Translate again")), None)
        if again is None:
            raise SceneFailed("no Translate again button")
        yield Until(lambda: not app.busy, self.args.timeout, "the sheet taken up")
        count, before = self.results(), app.last_result
        yield from self.click_widget(again)
        yield Until(lambda: self.toplevel(WarningBox) is not None, 5, "the question")
        box = self.toplevel(WarningBox)
        self.off_page = True
        yield 0.6
        yield from self.click_widget(box.continue_btn, 0.5)
        self.off_page = False
        yield from self.glide(*self.park_point(), seconds=0.6)
        yield from self.wait_page(count, before, "the page translated again")
        yield 1.5

    def note_name(self) -> None:
        """A name the page on show holds (`name_like`: its Japanese and the model's rendering of it), kept in memory
        for the series sheet scene - the sample's own words and the model's, never written anywhere."""
        if self.name is not None:
            return
        result = getattr(self.app, "last_result", None)
        for region in getattr(result, "regions", None) or ():
            found = name_like(getattr(region, "source_text", "") or "", getattr(region, "translated_text", "") or "")
            if found is not None:
                self.name = found
                return

    def type_into(self, var: Any, text: str, per_char: float = 0.06) -> Iterator[Any]:
        """*text* typed into *var* a character at a time (a name of the page and the model's rendering of it, or the
        owner's --term)."""
        for i in range(1, len(text) + 1):
            var.set(text[:i])
            yield per_char

    def mask_path(self, dialog: Any) -> None:
        """The line of the sheet that names its file (a path of the scratch folder) blanked in the GIF."""
        label = next((w for w in dv.walk(dialog) if w.winfo_class() == "TLabel"
                      and str(w.cget("text")).startswith("File:")), None)
        if label is not None:
            x, y = label.winfo_rootx(), label.winfo_rooty()
            self.records["masks"].append({"t0": round(pv.now_ms(), 1), "t1": None,
                                          "box": [x, y, x + label.winfo_width(), y + label.winfo_height()]})

    def unmask(self) -> None:
        for mask in self.records["masks"]:
            if mask["t1"] is None:
                mask["t1"] = round(pv.now_ms() + 200, 1)

    def select_region(self, region: Any) -> Iterator[Any]:
        """A click on *region* (Tk's press and release on the page): selected."""
        point = self.screen_point(region)
        yield from self.glide(*point, seconds=0.7)
        yield 0.15
        self.press_on_page(*point)
        yield 0.08
        self.release_on_page(*point)
        yield Until(lambda: getattr(self.app, "_chosen_region", None) is region, 3, "the region selected")
        yield 0.4

    def act_edit(self) -> Iterator[Any]:
        app = self.app
        yield from self.role_shown("translator")
        found = self.regions()
        if not found:
            raise SceneFailed("no translated region")
        region = found[0]
        self.note_region("edited", region)
        point = self.screen_point(region)
        yield from self.glide(*point, seconds=0.8)
        yield 0.2
        self.editing()
        cx, cy = self.to_canvas(*point)
        t = self.event_time()
        for k, kind in enumerate(("ButtonPress-1", "ButtonRelease-1", "ButtonPress-1", "ButtonRelease-1")):
            self.down = kind.startswith("ButtonPress")
            self.records["pointer"].append([round(pv.now_ms(), 1), int(point[0]), int(point[1]), int(self.down)])
            app.canvas.event_generate(f"<{kind}>", x=cx, y=cy, rootx=int(point[0]), rooty=int(point[1]),
                                      time=t + 40 * k)
            yield 0.05
        self.down = False
        yield 0.4
        if getattr(app, "_editor", None) is None or not app._editor.winfo_exists():
            self.later(lambda: app._on_double(SimpleNamespace(x=cx, y=cy, state=0)))  # (the binding's own call)
        yield Until(lambda: getattr(app, "_editor", None) is not None and app._editor.winfo_exists(), 5,
                    "the editor")
        editor = app._editor
        self.off_page = True
        self.beside(editor, point)
        yield 0.8
        # the model's own words typed in again, a word at a time, as the page follows (in memory only: never noted;
        # no word of the tool's own goes into a bubble)
        new = editor.text.get("1.0", "end-1c").strip()
        if not new:
            raise SceneFailed("the region has no translation to type")
        yield from self.glide_to(editor.text, 0.5)
        yield from self.mark_press()
        editor.text.tag_add("sel", "1.0", "end-1c")
        yield 0.5
        editor.text.delete("1.0", "end")
        words = new.split(" ")
        for i, word in enumerate(words):
            editor.text.insert("end", word if i == len(words) - 1 else word + " ")
            yield 0.45 if i % 3 == 2 else 0.12
        yield 1.0
        yield from self.click_widget(editor.save_btn, 0.6)
        yield Until(lambda: not editor.winfo_exists(), 5, "the editor closed")
        self.off_page = False
        yield Until(lambda: not app.busy, self.args.timeout, "the page lettered")
        yield from self.glide(*self.park_point(), seconds=0.6)
        yield 1.0

    def beside(self, dialog: Any, point: tuple[float, float]) -> None:
        """*dialog* (a window of this process's) moved to the side of TASlation's window away from *point*, so that
        the bubble it edits stays in sight as the page follows it."""
        app = self.app
        with contextlib.suppress(Exception):
            dialog.update_idletasks()
            w = dialog.winfo_width()
            left, right = app.winfo_rootx() + 8, app.winfo_rootx() + app.winfo_width() - w - 8
            x = left if point[0] > app.winfo_rootx() + app.winfo_width() / 2 else right
            y = max(app.winfo_rooty() + 8, min(dialog.winfo_rooty(), app.winfo_rooty() + app.winfo_height()
                                                - dialog.winfo_height() - 8))
            dialog.geometry(f"+{int(x)}+{int(y)}")

    def act_region(self) -> Iterator[Any]:
        from taslation.ui import area

        app = self.app
        yield from self.role_shown("translator")
        found = self.regions()
        if not found:
            raise SceneFailed("no region")
        region = found[min(1, len(found) - 1)]
        yield from self.select_region(region)
        self.note_region("moved from", region)
        start = self.screen_point(region, (0.5, 0.5))
        end = (start[0] + 22, start[1] + 14)
        yield from self.drag(start, end, 0.9)
        yield Until(lambda: not app.busy, self.args.timeout, "the region moved")
        yield 0.8
        moved = app._region_at(*app.canvas.to_image_coords(*self.to_canvas(*end)))
        if moved is None:
            raise SceneFailed("no region where it was moved to")
        if getattr(app, "_chosen_region", None) is not moved:
            yield from self.select_region(moved)
        region = moved
        corners = [area.to_canvas(x, y, app.canvas.scale, app.canvas.offset) for x, y in app._frame_of(region)]
        handle = None
        for cx, cy in sorted(corners, key=lambda c: -(c[0] + c[1])):
            for dx, dy in ((0, 0), (-2, -2), (2, 2), (-3, 0), (0, -3)):
                if app._grip_of(cx + dx, cy + dy) in area.HANDLES:
                    handle = (cx + dx, cy + dy)
                    break
            if handle is not None:
                break
        if handle is None:
            raise SceneFailed("no handle on the region's frame")
        sx, sy = app.canvas.winfo_rootx() + handle[0], app.canvas.winfo_rooty() + handle[1]
        yield from self.drag((sx, sy), (sx + 26, sy + 18), 0.8)
        yield 0.8  # (a larger frame is read again: that begins a moment after the release)
        yield Until(lambda: not app.busy, self.args.timeout, "the region resized")
        self.note_region("resized", getattr(app, "_chosen_region", None) or region)
        yield 1.0

    def act_undo(self) -> Iterator[Any]:
        app = self.app
        yield from self.role_shown("translator")
        button = next((b for b in app.tool_btns if str(b.cget("text")).startswith("Undo")), None)
        if button is None:
            raise SceneFailed("no Undo button")
        yield from self.click_widget(button, 0.9)
        yield Until(lambda: not app.busy, self.args.timeout, "the change taken back")
        yield 1.5

    def act_add_region(self) -> Iterator[Any]:
        app = self.app
        yield from self.role_shown("translator")
        found = self.regions()
        if len(found) < 2:
            raise SceneFailed("too few regions")
        region = found[min(2, len(found) - 1)]
        box = self.region_box(region)
        yield from self.select_region(region)
        yield 0.3
        yield from self.press_key("Delete", "Delete", app._drop_chosen,
                                  lambda: getattr(app, "_chosen_region", None) is not region)
        yield Until(lambda: not app.busy, self.args.timeout, "the region dropped")
        yield 1.2
        if box is None:
            raise SceneFailed("no box for the region")
        corners = self.free_corners(box, 8)
        if corners is None:
            raise SceneFailed("no free corner to draw the rectangle from")
        start, end = corners
        count = len(self.regions(translated=False))
        yield from self.drag(start, end, 1.0)
        self.records["regions"].append({"t": round(pv.now_ms(), 1), "what": "added",
                                        "box": [round(v) for v in (*start, *end)]})
        self.fast(True)
        yield Until(lambda: not app.busy and len(self.regions(translated=False)) >= count + 1, self.args.timeout,
                    "the new region")
        yield Until(lambda: not app.busy, self.args.timeout, "the new region translated")
        self.fast(False)
        yield from self.glide(*self.park_point(), seconds=0.6)
        yield 1.5

    def free_corners(self, box: Sequence[float], pad: float) -> tuple[tuple[float, float], tuple[float, float]] | None:
        """A rectangle round *box* (screen pixels) *pad* wider, from a corner where no other region is - a press on
        a region would take hold of it - to the corner across; None where every corner is on one."""
        app = self.app
        x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
        for start, end in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0)), ((x1, y0), (x0, y1)), ((x0, y1), (x1, y0))):
            cx, cy = self.to_canvas(*start)
            if app.canvas.inside(cx, cy) and app._region_at(*app.canvas.to_image_coords(cx, cy)) is None:
                return start, end
        return None

    def act_full_screen(self) -> Iterator[Any]:
        app = self.app
        yield from self.click_widget(app.reading_btn, 0.9)
        yield Until(lambda: bool(getattr(app, "reading", False)), 5, "the full screen")
        yield 1.0
        yield from self.glide(app.canvas.winfo_rootx() + app.canvas.winfo_width() * 0.7,
                              app.canvas.winfo_rooty() + app.canvas.winfo_height() * 0.6, 0.8)
        yield 2.0
        yield from self.press_key("F11", "F11", app.toggle_reading, lambda: not getattr(app, "reading", False))
        yield Until(lambda: not getattr(app, "reading", False), 5, "the full screen left")
        self.pointer.at = self.park_point()
        yield 1.5

    def act_whole_book(self) -> Iterator[Any]:
        from taslation.ui.dialogs.batch import BatchDialog

        app = self.app
        yield from self.role_shown("reader")
        yield from self.click_widget(app.batch_btn, 0.9)
        yield Until(lambda: self.toplevel(BatchDialog) is not None, 10, "the whole-book dialog")
        dialog = self.toplevel(BatchDialog)
        yield 1.0
        start = find_widget(dialog, "TButton", "Start")
        if start is None:
            raise SceneFailed("the dialog has no Start")
        first = self.standin.index
        yield from self.click_widget(start, 0.7)
        yield Until(lambda: app.batch is not None and bool(getattr(app, "_strip_model").pages), 20, "the run begun")
        yield from self.glide(app.canvas.winfo_rootx() + app.canvas.winfo_width() * 0.85,
                              app.canvas.winfo_rooty() + app.canvas.winfo_height() * 0.5, 0.6)
        last = min(self.standin.screens - 1, first + max(1, self.args.book_pages) - 1)

        def read_over() -> bool:
            cell = getattr(app, "_strip_model").pages.get(self.standin.index - first + 1)
            return cell is not None and cell.stages.get("read") in ("done", "skipped", "failed")

        while True:
            self.fast(True)
            yield Until(read_over, self.args.timeout, "the screen on show read")
            self.fast(False)
            yield 0.8
            if self.standin.index >= last:
                break
            yield from self.press_page_key("next", may_fail=True)
        band = getattr(app, "scan_band", None)
        button = find_widget(band, "TButton", "Finished reading") if band is not None else None
        if button is None:
            raise SceneFailed("no Finished reading")
        yield from self.click_widget(button, 0.8)
        yield from self.glide(*self.park_point(), seconds=0.6)
        self.fast(True)
        yield Until(lambda: app.batch is None and not app._batching, max(self.args.timeout, 600), "the run over")
        yield Until(lambda: not app.busy, 30, "the page on show")
        self.fast(False)
        yield 1.5
        for _ in range(min(3, last - first)):  # (read on: each page there at once)
            count, before = self.results(), app.last_result
            try:
                yield from self.press_page_key("prev")
                yield Until(self.page_after(count, before), 15, "a page of the book")
            except SceneFailed as e:
                self.say(f"reading on stopped: {e}")
                break
            yield 1.2


# ---------------------------------------------------------------------------------------------------- record
def parse_term(text: str | None) -> tuple[str, str] | None:
    if not text:
        return None
    term, sep, rendering = text.partition("=")
    if not sep or not term.strip() or not rendering.strip():
        raise SystemExit("--term is TERM=RENDERING")
    return term.strip(), rendering.strip()


def models_dir(given: str) -> str:
    models = given or os.environ.get("TASLATION_MODELS_DIR") or ""
    if not models:
        guess = [ROOT / "models", ROOT.parent / "models", Path("C:/Temp/CleranTrans/models")]
        models = str(next((g for g in guess if g.is_dir()), ""))
    if not models or not Path(models).is_dir():
        raise SystemExit("set TASLATION_MODELS_DIR (or --models) to the folder of the installed models")
    return models


def record(args: argparse.Namespace) -> int:
    """The run (see the module's docstring): the recording into *args.out*, its facts printed (numbers only)."""
    if args.list:
        print(json.dumps(scene_rows(), indent=1))
        return 0
    if args.out is None:
        raise SystemExit("record needs --out FILE (in a scratch folder)")
    if sys.platform != "win32":
        raise SystemExit("the record needs Windows")
    out = pv.check_scratch_path(args.out)
    if out.exists():
        raise SystemExit(f"{out} is there already: give another --out")
    out.parent.mkdir(parents=True, exist_ok=True)
    port = check_port(args.start_ollama)
    url = pv.started_url(port)
    scenes = pick_scenes(args.scenes)
    term = parse_term(args.term)
    models = models_dir(args.models)
    dv.page_files(args.title, args.first, args.pages)  # (ends the run where the dataset lacks them)

    scratch = Path(tempfile.mkdtemp(prefix="intro-run-", dir=out.parent))
    state = scratch / "state"
    state.mkdir()
    os.environ["TASLATION_STATE_DIR"] = str(state)  # (before TASlation's modules are imported)
    os.environ.pop("SELFTRANS_STATE_DIR", None)
    os.environ["TASLATION_MODELS_DIR"] = models
    os.environ["OLLAMA_HOST"] = f"127.0.0.1:{port}"  # (this process alone: the server its starter starts)
    os.environ["OLLAMA_NOPRUNE"] = "1"
    import taslation

    import standin_e2e as e2e

    if not Path(taslation.__file__).resolve().is_relative_to(ROOT):
        shutil.rmtree(scratch, ignore_errors=True)
        raise SystemExit(f"taslation comes from {taslation.__file__}, not from {ROOT}")
    from taslation import ollama_start
    from taslation.capture import enable_dpi_awareness

    ollama_start.DEFAULT_PORT = port
    if e2e.ollama_get(url, "/api/version") is not None:
        shutil.rmtree(scratch, ignore_errors=True)
        raise SystemExit(f"something answers at {url} already: --start-ollama needs a port where nothing does")
    enable_dpi_awareness()
    writer = pv.RecordingWriter(out, quality=args.quality)
    report: dict[str, Any] = {"version": str(taslation.__version__), "scenes_asked": [s.id for s in scenes]}
    standin: StandIn | None = None
    meta: dict[str, Any] | None = None
    try:
        standin = StandIn(args, VIEWER_RECT, writer)
        meta = run_window(args, standin, writer, url, scenes, term, models)
        faulthandler.cancel_dump_traceback_later()
    except BaseException as e:  # noqa: BLE001 - said, then everything is closed
        if not isinstance(e, SystemExit):
            traceback.print_exc()
        report["failed"] = str(e) if isinstance(e, SystemExit) else f"{type(e).__name__} in the tool"
    finally:
        if standin is not None:
            standin.close()
        try:
            report["server_started"] = pv.server_summary(e2e.stop_started(url, state))
        except Exception as e:  # noqa: BLE001 - said; the cleanup below still runs
            report["server_started"] = {"error": type(e).__name__}
        report["cleanup"] = pv.cleanup(state, scratch, url, [])
    if meta is None or meta.get("failed"):
        writer.abandon()
        report["failed"] = report.get("failed") or (meta or {}).get("failed")
        print(json.dumps(report, indent=1, default=str))
        return 1
    assert standin is not None
    server = report.get("server_started")
    meta.update(intro_format=FORMAT, version=str(taslation.__version__), facts=code_facts(),
                viewer_pics=list(standin.pics), viewer_shown=list(standin.shown), viewer_keys=len(standin.keys),
                title=args.title, first=args.first, pages=args.pages, spread=bool(args.spread), made_up=False,
                term_given=term is not None,
                server={k: (v[:LONGEST_VALUE] if isinstance(v, str) else v) for k, v in (server or {}).items()})
    try:
        check_no_text(meta)
    except ValueError as e:
        writer.abandon()
        report["failed"] = f"the recording's facts would hold text: {e}"
        print(json.dumps(report, indent=1, default=str))
        return 1
    writer.finish(meta)
    report.update({"recording": str(out), "scenes": [{"id": s["id"], "seconds": round((s["t1"] - s["t0"]) / 1000, 1),
                                                      "failed": s["failed"]} for s in meta["scenes"]],
                   "skipped": meta["skipped"], "frames": writer.stored, "viewer_pictures": len(standin.pics),
                   "keys": [{k: r[k] for k in ("key", "passed_on", "posted", "taken")} for r in meta["keys"]],
                   "turned_by_tool": meta["turned_by_tool"], "guard": meta["guard"],
                   "bytes": out.stat().st_size})
    print(json.dumps(report, indent=1, default=str))
    return 0


def run_window(args: argparse.Namespace, standin: StandIn, writer: Any, url: str, scenes: Sequence[Scene],
               term: tuple[str, str] | None, models: str) -> dict[str, Any]:
    """TASlation's window beside the stand-in, driven by the `Director` through *scenes*; the recording's facts."""
    import standin_e2e as e2e

    from taslation import errorlog, netguard
    from taslation.capture import WindowInfo, program_name, window_class, window_rect, window_title
    from taslation.config import Settings
    from taslation.ui import app as app_mod

    # every module in place before the guard replaces what they import
    from taslation import batch, pipeline, translation_view  # noqa: F401
    from taslation.ui import jobs, live, overbook, reading, strip, trouble, viewers  # noqa: F401
    from taslation.ui.dialogs import batch as batch_dialog, caches, start, stop  # noqa: F401

    hwnd, pid = standin.hwnd, standin.pid
    guard = dv.Guard(hwnd)
    if guard.is_own(hwnd) or window_title(hwnd) != dv.VIEWER_TITLE:
        raise SystemExit("the stand-in's window is not what it should be")

    def viewer_info() -> Any:
        if not guard.is_viewer(hwnd) or not standin.alive():
            return None
        return WindowInfo(hwnd, window_title(hwnd), window_class(hwnd), pid, window_rect(hwnd), program_name(pid))

    notes = QuietNotes()
    hotkeys = e2e.HotKeys(notes)
    probe = Probe(notes)
    patched = install(guard, viewer_info, hotkeys, probe)
    state = dv.scratch_state()
    with contextlib.suppress(Exception):
        from taslation.ui.translator import remember_role

        remember_role(state, BOOK, "reader")
    settings = pv.settings_for(Settings, state_dir=state, ui_language="en", target_language="English",
                               over_book=False, flash_when_done=False, sound_when_done=False, always_on_top=False,
                               models_dir=Path(models), ollama_url=url)
    settings.validate()
    errorlog.setup(settings)
    netguard.install(settings.ollama_port)  # nothing but the translator's port on this computer
    app = app_mod.App(settings, book=BOOK, auto=True)
    w, h = args.size
    x, y = args.at
    app.geometry(f"{w}x{h}+{x}+{y}")
    app.after(600, lambda: app.geometry(f"{w}x{h}+{x}+{y}"))
    app.update_idletasks()
    own = int(app.wm_frame(), 16)
    grabber = Grabber(own, guard, writer, args.fps, args.client_only)
    pointer = Pointer()
    pointer.install()
    director = Director(app, standin, guard, probe, grabber, pointer, args, scenes, term)
    director.start()
    try:
        app.mainloop()
    finally:
        grabber.stop()
        pointer.remove()
        dv.finish_app(app)
    records = director.records
    failed = director.failed or ("" if writer.stored else "no picture was taken")
    if not failed and not [s for s in records["scenes"] if not s["failed"]]:
        failed = "no scene was recorded"
    return {"failed": failed, **records, "views": list(probe.views), "frame_boxes": list(grabber.boxes),
            "pictures": grabber.facts(), "probe_errors": probe.errors,
            "guard": {"patched": patched, "refused": guard.refused, "reached_the_stand_in": guard.used,
                      "chosen": sorted(probe.chosen), "stand_in": hwnd,
                      "only_the_stand_in_chosen": probe.chosen <= {hwnd},
                      "hot_keys_held_at_the_end": sorted(hotkeys.registered)}}


# ---------------------------------------------------------------------------------------------------- the sources
class Source:
    """What a GIF is made from: the recording's facts (`meta`) and its pictures by name."""

    meta: dict[str, Any]

    def __init__(self) -> None:
        self.frames: list[tuple[float, str]] = []
        self.frame_times: list[float] = []
        self.pics: list[list[Any]] = []
        self.pic_times: list[float] = []
        self.boxes: list[list[float]] = []
        self.box_times: list[float] = []
        self.pointer: list[list[float]] = []
        self.pointer_times: list[float] = []
        self._cache: OrderedDict[str, Image.Image] = OrderedDict()

    def index(self) -> None:
        meta = self.meta
        self.frames = [(float(t), str(n)) for t, n in meta.get("frames", [])]
        self.frame_times = [t for t, _ in self.frames]
        self.pics = sorted(meta.get("viewer_pics", []), key=lambda p: p[0])
        self.pic_times = [float(p[0]) for p in self.pics]
        self.boxes = sorted(meta.get("frame_boxes", []), key=lambda b: b[0])
        self.box_times = [float(b[0]) for b in self.boxes]
        self.pointer = sorted(meta.get("pointer", []), key=lambda p: p[0])
        self.pointer_times = [float(p[0]) for p in self.pointer]

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

    def pic_at(self, t: float) -> str | None:
        i = bisect.bisect_right(self.pic_times, t) - 1
        return self.pics[max(0, i)][2] if self.pics else None

    def box_at(self, t: float) -> list[float] | None:
        i = bisect.bisect_right(self.box_times, t) - 1
        return self.boxes[max(0, i)][1:] if self.boxes else None

    def pointer_at(self, t: float) -> tuple[int, int, bool] | None:
        i = bisect.bisect_right(self.pointer_times, t) - 1
        if i < 0:
            return None
        p = self.pointer[i]
        return int(p[1]), int(p[2]), bool(p[3])

    def close(self) -> None:
        pass


class ZipSource(Source):
    def __init__(self, path: Path):
        super().__init__()
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self.meta = json.loads(self.zip.read("meta.json"))
        if self.meta.get("intro_format") != FORMAT:
            raise SystemExit(f"{path} is no recording of this tool")
        kept = set(self.zip.namelist())  # (a picture the stand-in sent as the recording closed is not in it)
        self.meta["frames"] = [f for f in self.meta.get("frames", []) if f[1] in kept]
        self.meta["viewer_pics"] = [p for p in self.meta.get("viewer_pics", []) if p[2] in kept]
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


SAMPLE_WINDOW = (744, 516)  # the made-up window's size (as WINDOW_SIZE, smaller: the sample's pictures are in memory)
SAMPLE_WAIT = 6.0  # the middle of each made-up scene: a picture every this many steps, marked as waiting


def made_up_sheet(size: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    """Where `promo_video.made_up_window` of *size* draws its page: the sheet's top left and its size (as it lays
    them out; every promo tool's version does the same)."""
    w, h = size
    s = w / 720
    bar, foot = max(12, round(44 * s)), max(10, round(30 * s))
    room_w, room_h = w - 40 * s, h - foot - bar - 40 * s
    pw = max(20, int(min(room_w, room_h * 830 / 1170)))
    ph = max(28, int(pw * 1170 / 830))
    return (int((w - pw) // 2), int(bar + 20 * s + (room_h - ph) // 2)), (pw, ph)


def sample_source(scene_ids: Sequence[str] | None = None, seconds: float = 4.0, fps: float = 5.0) -> MemorySource:
    """Made-up recordings of every scene present (or of *scene_ids*): drawn windows (`promo_video.made_up_window`,
    marked MADE-UP FRAMES), drawn viewer pages, a pointer, a key, and a middle stretch marked as waiting for the models
    (pictures SAMPLE_WAIT steps apart) that a short scene shows faster; no window, no model, no manga page."""
    facts = code_facts()
    chosen = [s for s in SCENES if (scene_ids is None and s.present()) or (scene_ids is not None and s.id in scene_ids)]
    size = SAMPLE_WINDOW
    t = 1_700_000_000_000.0
    images: dict[str, Image.Image] = {}
    frames: list[list[Any]] = []
    meta: dict[str, Any] = {"intro_format": FORMAT, "version": facts["version"], "facts": facts, "made_up": True,
                            "scenes": [], "skipped": [], "pointer": [], "keys": [], "regions": [], "masks": [],
                            "moments": {}, "views": [], "viewer_pics": [], "frame_boxes": [[t, 0, 0, *size, 0, 0]],
                            "turned_by_tool": 0}
    step = 1000.0 / fps
    count = max(3, int(seconds * fps))
    third = count // 3
    for k, scene in enumerate(chosen):
        page = k + 1
        (x0, y0), (pw, ph) = made_up_sheet(size)
        blank = pv.made_up_window(size, page, 6, 0, False, "")
        name = f"viewer/{len(meta['viewer_pics']):04d}.jpg"
        images[name] = blank.crop((x0 - 6, y0 - 6, x0 + pw + 6, y0 + ph + 6))
        meta["viewer_pics"].append([t, page, name])
        meta["views"].append({"t": t, "scale": 1.0, "offset": [0.0, 0.0], "origin": [x0, y0], "image": [pw, ph]})
        t0 = t
        waiting: list[float] = []
        for i in range(count):
            lettered = min(6, (i * 7) // count)
            name = f"frames/{page:02d}-{lettered}.jpg"
            if name not in images:
                images[name] = pv.made_up_window(size, page, 6, lettered, False, f"Made-up step: {scene.id}")
            frames.append([round(t, 1), name])
            u = i / max(1, count - 1)
            meta["pointer"].append([round(t, 1), int(size[0] * (0.25 + 0.5 * u)), int(size[1] * (0.3 + 0.4 * u)),
                                    int(i == 1)])
            if k == 0 and lettered >= 3 and "filling" not in meta["moments"]:
                meta["moments"]["filling"] = round(t, 1)
            wait = third <= i < count - third
            if wait:
                waiting.append(t)
            t += step * (SAMPLE_WAIT if wait else 1.0)
        if k == 0:
            meta["moments"].update(original=t0, translated=round(t - step, 1))
        if scene.id in ("next_page", "turned_past", "whole_book"):
            meta["keys"].append({"t": round(t0 + step, 1), "key": "Left", "passed_on": True, "posted": 1, "taken": 1})
        elif scene.id in ("full_screen", "add_region"):
            meta["keys"].append({"t": round(t0 + step, 1), "key": "F11" if scene.id == "full_screen" else "Delete",
                                 "passed_on": False, "posted": 0, "taken": 0})
        fast = [[round(waiting[0], 1), round(waiting[-1] + step * SAMPLE_WAIT, 1)]] if waiting else []
        meta["scenes"].append({"id": scene.id, "t0": round(t0, 1), "t1": round(t, 1), "fast": fast, "failed": ""})
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
    keys: list[tuple[float, dict[str, Any]]] = field(default_factory=list)

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

    def shown(self, real_t: float) -> float:
        """Where the real time *real_t* is shown, from the scene's start (a time in a cut: where the cut is)."""
        shown = 0.0
        for a, b, f, _fast in self.segments:
            if real_t < a:
                return shown
            if real_t <= b:
                return shown + (real_t - a) / f
            shown += (b - a) / f
        return shown


def changes_of(source: Source, t0: float, t1: float) -> list[float]:
    """The times something changed in [t0, t1]: the window's picture, the pointer, a key, the viewer's picture."""
    out: list[float] = []
    last = None
    for t, name in source.frames:
        if t0 <= t <= t1 and name != last:
            out.append(t)
        last = name
    out += [float(p[0]) for p in source.pointer if t0 <= p[0] <= t1]
    out += [float(k["t"]) for k in source.meta.get("keys", []) if t0 <= k["t"] <= t1]
    out += [t for t in source.pic_times if t0 <= t <= t1]
    return sorted(set(out))


def scene_segments(entry: dict[str, Any], changes: Sequence[float], budget_ms: float, longest_ms: float,
                   max_speed: float = MAX_SPEED) -> tuple[list[tuple[float, float, float, bool]], float]:
    """The scene's real time as shown: a wait with nothing changing longer than *longest_ms* cut to that, and the
    stretches marked as waiting for the models shown *f* times faster, f = max(1, R / max(budget - S, 0.3 budget))
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
    fps: float = 10.0
    longest_s: float = LONGEST_S
    max_speed: float = MAX_SPEED
    title_s: float = TITLE_S
    card_s: float = CARD_S
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
        if scene is None or entry.get("failed") or entry.get("t0") is None:
            continue
        if opts.scenes is not None and entry["id"] not in opts.scenes:
            continue
        number += 1
        segments, factor = scene_segments(entry, changes_of(source, entry["t0"], entry["t1"]), scene.budget_s * 1000,
                                          opts.longest_s * 1000, opts.max_speed)
        part = Part("scene", sum((b - a) / f for a, b, f, _ in segments), entry=entry, scene=scene, number=number,
                    segments=segments, factor=factor)
        part.keys = [(part.shown(float(k["t"])), k) for k in source.meta.get("keys", [])
                     if entry["t0"] <= k["t"] <= entry["t1"]]
        parts.append(part)
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
    """Where everything goes in a frame of *size* (laid out for 960x540, in proportion at any other size)."""

    def __init__(self, size: tuple[int, int] = SIZE):
        self.W, self.H = size
        s = self.s = self.W / 960
        self.m = round(12 * s)
        self.gap = round(12 * s)
        self.foot = round(26 * s)
        self.left = (self.m, self.m, round(self.W * 0.25), self.H - self.foot)
        self.right = (self.left[2] + self.gap, self.m, self.W - self.m, self.H - self.foot)
        self.col = self.left[2] - self.left[0]
        self.header_px = (round(11 * s), max(8, round(9 * s)))
        self.title_px = (round(16 * s), round(13 * s))
        self.desc_px = (round(13 * s), round(11 * s))
        self.small_px = (round(11 * s), max(8, round(9 * s)))
        self.circle = round(26 * s)
        self.key_h = round(70 * s)
        self.viewer_h = round(self.H * 0.46)

    def header(self, text: str, width: float) -> tuple[int, str, str]:
        """A column's header on one line within *width*: its size (the largest from the first of `header_px` down
        to the second; the smallest where none fits), its label (bold) and its note (lighter, after " - ")."""
        label, _sep, note = text.partition(HEADER_SEP)
        size = self.header_px[0]
        while size > self.header_px[1] and self.header_width(label, note, size) > width:
            size -= 1
        return size, label, note

    @staticmethod
    def header_width(label: str, note: str, size: int) -> float:
        width = pv.text_width(label, pv.font(size, True))
        return width + (pv.text_width(HEADER_SEP + note, pv.font(size)) if note else 0.0)

    def header_fits(self, text: str, width: float) -> bool:
        size, label, note = self.header(text, width)
        return self.header_width(label, note, size) <= width

    def title_width(self) -> float:
        return self.col - self.circle - round(8 * self.s)

    def step(self, title: str, description: str) -> tuple[tuple[int, list[str]], tuple[int, list[str]]]:
        return (fit_text(title, self.title_px[0], self.title_px[1], True, self.title_width(), 2),
                fit_text(description, self.desc_px[0], self.desc_px[1], False, self.col, 5))

    def step_fits(self, title: str, description: str) -> bool:
        (_ts, tl), (_ds, dl) = self.step(title, description)
        return len(tl) <= 2 and len(dl) <= 5

    def cap_lines(self) -> tuple[int, list[str]]:
        return fit_text(CAP_PASSED_ONCE, self.small_px[0], self.small_px[1], False, self.col, 1)


def frame_texts(kind: str, facts: dict[str, Any], part: Part | None = None) -> list[str]:
    """The texts a frame of *kind* ("scene" or a card's id) carries, as drawn."""
    if kind == "scene":
        out = [LEFT_HEADER, RIGHT_HEADER, dv.VIEWER_TITLE, pv.CREDIT]
        if part is not None and part.scene is not None:
            out += list(step_texts(part.scene, facts))
        return out
    heading, lines = card_lines(kind, facts)
    out = ([heading] if heading else []) + [t for t, _ in lines]
    if kind == "how":
        out += [*HOW_CAPTIONS, pv.CREDIT]
    return out


def has_page(kind: str) -> bool:
    """Whether a frame of *kind* shows a sample page (the scenes, and the card with their pictures)."""
    return kind in ("scene", "how")


# ---------------------------------------------------------------------------------------------------- drawing
class Painter:
    """Draws the frames of a plan."""

    def __init__(self, source: Source, opts: Options):
        self.source, self.opts = source, opts
        self.layout = Layout(opts.size)
        self.facts = dict(source.meta.get("facts") or code_facts())
        self._scaled: OrderedDict[tuple[str, int, int], Image.Image] = OrderedDict()
        self._cards: dict[str, Image.Image] = {}
        self.bottoms: dict[str, int] = {}  # where each card's text ended (the tests hold it above the foot)

    def scaled(self, name: str, w: int, h: int) -> Image.Image:
        key = (name, w, h)
        if key in self._scaled:
            return self._scaled[key]
        image = self.source.image(name).resize((max(1, w), max(1, h)), Image.LANCZOS)
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
        frame, pic, box = src.frame_at(t), src.pic_at(t), src.box_at(t)
        pointer = src.pointer_at(t)
        placed = self.place(frame, box)
        drawn_pointer = None
        if pointer is not None and placed is not None and box is not None:
            x, y = self.to_out(pointer[0], pointer[1], box, placed)
            if placed[0] <= x <= placed[0] + placed[2] and placed[1] <= y <= placed[1] + placed[3]:
                drawn_pointer = (int(round(x)), int(round(y)), pointer[2])
        cap = next((k for s, k in part.keys if s <= local_ms < s + KEY_CAP_MS), None)
        cap_key = (cap["key"], bool(cap["passed_on"]), int(cap.get("posted") or 0), int(cap.get("taken") or 0)) \
            if cap is not None else None
        masks = tuple(tuple(m["box"]) for m in src.meta.get("masks", [])
                      if m["t0"] <= t <= (m["t1"] if m.get("t1") is not None else float("inf")))
        badge = part.factor if fast else None
        return ("scene", part.number, frame, pic, drawn_pointer, cap_key, badge, masks, tuple(box or ()))

    def place(self, frame: str | None, box: Sequence[float] | None) -> tuple[int, int, int, int] | None:
        """Where the window's picture goes in the right area: x, y, width, height."""
        if frame is None:
            return None
        image = self.source.image(frame)
        lay = self.layout
        x0, y0, x1, y1 = lay.right
        top = y0 + self.header_height(lay.right[2] - lay.right[0])
        k = min((x1 - x0) / image.width, (y1 - top - round(4 * lay.s)) / image.height)
        w, h = max(1, int(image.width * k)), max(1, int(image.height * k))
        return (x0 + (x1 - x0 - w) // 2, top, w, h)

    def to_out(self, sx: float, sy: float, box: Sequence[float], placed: tuple[int, int, int, int]
               ) -> tuple[float, float]:
        """A point on the screen as drawn in the GIF."""
        left, top, right, bottom = box[:4]
        return (placed[0] + (sx - left) * placed[2] / max(1.0, right - left),
                placed[1] + (sy - top) * placed[3] / max(1.0, bottom - top))

    def header_height(self, width: float) -> int:
        size = self.layout.header(RIGHT_HEADER, width)[0]
        return round(size * 1.3) + round(6 * self.layout.s)

    def header(self, d: Any, x: float, y: float, text: str, width: float) -> int:
        """Draws a column's header on one line at (x, y), its label bold and its note lighter; the y under it."""
        size, label, note = self.layout.header(text, width)
        bold = pv.font(size, True)
        d.text((x, y), label, fill=HEADER_LABEL, font=bold)
        if note:
            d.text((x + pv.text_width(label, bold), y), HEADER_SEP + note, fill=DIM, font=pv.font(size))
        return round(y + size * 1.3)

    # a frame
    def draw(self, part: Part, key: tuple[Any, ...]) -> Image.Image:
        if part.kind == "card":
            if part.card not in self._cards:
                self._cards[part.card] = self.card(part.card)
            return self._cards[part.card]
        return self.scene_frame(part, key)

    def scene_frame(self, part: Part, key: tuple[Any, ...]) -> Image.Image:
        _kind, number, frame, pic, pointer, cap, badge, masks, box = key
        lay = self.layout
        s = lay.s
        img = Image.new("RGB", (lay.W, lay.H), BG)
        d = ImageDraw.Draw(img)
        # the left column: the viewer
        x0, y0, x1, _y1 = lay.left
        y = self.header(d, x0, y0, LEFT_HEADER, lay.col) + round(4 * s)
        strip = round(16 * s)
        d.rectangle((x0, y, x1, y + strip), fill=PANEL)
        d.text((x0 + round(5 * s), y + strip / 2), dv.VIEWER_TITLE, fill=DIM, font=pv.font(lay.small_px[1]),
               anchor="lm")
        room_top, room_h = y + strip, lay.viewer_h - (y + strip - y0)
        d.rectangle((x0, room_top, x1, room_top + room_h), fill=(43, 43, 43))
        if pic is not None:
            picture = self.source.image(pic)
            k = min(lay.col / picture.width, room_h / picture.height)
            pw, ph = max(1, int(picture.width * k)), max(1, int(picture.height * k))
            img.paste(self.scaled(pic, pw, ph), (x0 + (lay.col - pw) // 2, room_top + (room_h - ph) // 2))
        # the step
        y = room_top + room_h + round(14 * s)
        assert part.scene is not None
        title, description = step_texts(part.scene, self.facts)
        (tsize, tlines), (dsize, dlines) = lay.step(title, description)
        c = lay.circle
        d.ellipse((x0, y, x0 + c, y + c), fill=BLUE)
        d.text((x0 + c / 2, y + c / 2), str(number), fill=TEXT, font=pv.font(round(15 * s), True), anchor="mm")
        ty = y + max(0, (c - round(tsize * 1.25)) // 2) if len(tlines) == 1 else y
        for line in tlines:
            d.text((x0 + c + round(8 * s), ty), line, fill=TEXT, font=pv.font(tsize, True))
            ty += round(tsize * 1.25)
        y = max(y + c, ty) + round(8 * s)
        for line in dlines:
            d.text((x0, y), line, fill=(205, 207, 212), font=pv.font(dsize))
            y += round(dsize * 1.35)
        # the key cap
        if cap is not None:
            self.key_cap(d, cap)
        # the right: TASlation's window
        rx0, ry0, rx1, _ry1 = lay.right
        self.header(d, rx0, ry0, RIGHT_HEADER, rx1 - rx0)
        placed = self.place(frame, box)
        if frame is not None and placed is not None:
            px, py, pw, ph = placed
            img.paste(self.scaled(frame, pw, ph), (px, py))
            for mask in masks:
                if box:
                    a = self.to_out(mask[0], mask[1], box, placed)
                    b = self.to_out(mask[2], mask[3], box, placed)
                    colour = img.getpixel((max(0, int(a[0]) - 2), int((a[1] + b[1]) / 2)))
                    d.rectangle((a[0], a[1], b[0], b[1]), fill=colour)
            if pointer is not None:
                self.pointer(d, pointer)
            if badge is not None:
                text = f"{badge:.1f}x"
                face = pv.font(round(14 * s), True)
                w = pv.text_width(text, face) + round(14 * s)
                bx, by = px + pw - w - round(8 * s), py + round(8 * s)
                d.rounded_rectangle((bx, by, bx + w, by + round(24 * s)), radius=round(6 * s), fill=AMBER)
                d.text((bx + w / 2, by + round(12 * s)), text, fill=(20, 20, 20), font=face, anchor="mm")
        self.foot(d, f"shown at {badge:.1f}x speed" if badge is not None else "", True)
        return img

    def key_cap(self, d: ImageDraw.ImageDraw, cap: tuple[Any, ...]) -> None:
        key, passed_on, posted, taken = cap
        lay = self.layout
        s = lay.s
        x0, _y0, _x1, y1 = lay.left
        top = y1 - lay.key_h
        label = KEY_GLYPHS.get(key, key)
        face = pv.font(round(16 * s), True)
        w = max(round(44 * s), int(pv.text_width(label, face)) + round(18 * s))
        h = round(30 * s)
        d.rounded_rectangle((x0, top, x0 + w, top + h), radius=round(5 * s), fill=CAP_BG, outline=CAP_EDGE,
                            width=max(1, round(2 * s)))
        d.text((x0 + w / 2, top + h / 2), label, fill=(30, 30, 34), font=face, anchor="mm")
        size = lay.cap_lines()[0]
        y = top + h + round(5 * s)
        d.text((x0, y), CAP_PRESSED, fill=TEXT, font=pv.font(size))
        if passed_on and posted:
            text = CAP_PASSED_ONCE if posted == 1 and taken == 1 else CAP_PASSED
            d.text((x0, y + round(size * 1.35)), text, fill=AMBER, font=pv.font(size))

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
            y = round(lay.H * 0.26)
            for text, style in lines:
                size, bold, colour = {"title": (round(54 * s), True, TEXT), "lead": (round(21 * s), True, TEXT),
                                      "body": (round(15 * s), False, (205, 207, 212)),
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
        y = round(40 * s)
        d.text((x, y), heading, fill=TEXT, font=pv.font(round(28 * s), True))
        y += round(52 * s)
        width = (lay.W * 0.52) if kind == "how" else (lay.W - 2 * x)
        size = round((17 if kind == "how" else 19) * s)
        n = 0
        for text, style in lines:
            if style == "small":
                d.text((x, lay.H - round(44 * s)), text, fill=DIM, font=pv.font(round(12 * s)))
                continue
            indent = round(30 * s)
            if style == "step":
                n += 1
                c = round(22 * s)
                d.ellipse((x, y, x + c, y + c), fill=BLUE)
                d.text((x + c / 2, y + c / 2), str(n), fill=TEXT, font=pv.font(round(13 * s), True), anchor="mm")
            else:
                r = round(3 * s)
                d.ellipse((x + round(8 * s) - r, y + size * 0.65 - r, x + round(8 * s) + r, y + size * 0.65 + r),
                          fill=BLUE)
            for line in lines_at(text, size, False, width - indent):
                d.text((x + indent, y), line, fill=(222, 224, 228), font=pv.font(size))
                y += round(size * 1.38)
            y += round(10 * s)
        self.bottoms[kind] = y
        if kind == "how":
            self.how_pictures(img, d)
            self.foot(d, "", True)
        return img

    def how_pictures(self, img: Image.Image, d: ImageDraw.ImageDraw) -> None:
        lay = self.layout
        s = lay.s
        moments = self.source.meta.get("moments") or {}
        pictures = [self.moment_picture(i, moments.get(key)) for i, key in
                    enumerate(("original", "filling", "translated"))]
        x0, x1 = lay.W * 0.58, lay.W - round(28 * s)
        gap = round(10 * s)
        w = int((x1 - x0 - 2 * gap) / 3)
        h = int(lay.H * 0.58)
        y = round(lay.H * 0.2)
        for i, (picture, caption) in enumerate(zip(pictures, HOW_CAPTIONS)):
            x = int(x0 + i * (w + gap))
            d.rectangle((x, y, x + w, y + h), fill=PANEL)
            if picture is not None:
                k = min(w / picture.width, h / picture.height)
                shown = picture.resize((max(1, int(picture.width * k)), max(1, int(picture.height * k))),
                                       Image.LANCZOS)
                img.paste(shown, (x + (w - shown.width) // 2, y + (h - shown.height) // 2))
            d.text((x + w / 2, y + h + round(8 * s)), caption, fill=TEXT, font=pv.font(round(12 * s), True),
                   anchor="ma")
            if i < 2:
                d.text((x + w + gap / 2, y + h / 2), "\u203a", fill=DIM, font=pv.font(round(18 * s), True),
                       anchor="mm")

    def moment_picture(self, i: int, t: float | None) -> Image.Image | None:
        """The "how" card's picture *i* at the moment *t*: the viewer's page (0), else the page in TASlation's
        window (cut out as the window placed it)."""
        src = self.source
        if t is None:
            return None
        if i == 0:
            pic = src.pic_at(t)
            return src.image(pic) if pic is not None else None
        frame, box = src.frame_at(t), src.box_at(t)
        if frame is None:
            return None
        image = src.image(frame)
        view = view_at(src.meta.get("views", []), t)
        if view is None or box is None:
            return image
        left, top, right, bottom, cx, cy = box
        page = on_picture((0, 0, view["image"][0], view["image"][1]), view)
        kx = image.width / max(1.0, right - left)
        crop = ((cx - left + page[0]) * kx, (cy - top + page[1]) * kx, (cx - left + page[2]) * kx,
                (cy - top + page[3]) * kx)
        crop = (max(0, int(crop[0])), max(0, int(crop[1])), min(image.width, int(crop[2])),
                min(image.height, int(crop[3])))
        if crop[2] - crop[0] < 20 or crop[3] - crop[1] < 20:
            return image
        return image.crop(crop)


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


def palette_of(frames: Sequence[Image.Image]) -> Image.Image:
    """One palette for the whole GIF: from a montage of *frames* and a swatch of the colours drawn over them."""
    w, h = frames[0].size
    cols = min(4, len(frames))
    montage = Image.new("RGB", (w // 2 * cols, h // 2 * ((len(frames) + cols - 1) // cols) + 16), BG)
    for k, frame in enumerate(frames):
        montage.paste(frame.resize((w // 2, h // 2), Image.BOX), ((k % cols) * (w // 2), (k // cols) * (h // 2)))
    d = ImageDraw.Draw(montage)
    for i, colour in enumerate((BG, TEXT, DIM, AMBER, BLUE, PANEL, CAP_BG, CAP_EDGE, (255, 255, 255), (0, 0, 0))):
        d.rectangle((i * 16, montage.height - 16, i * 16 + 15, montage.height), fill=colour)
    return montage.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)


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
    sample_at = sorted({int(v) for v in np.linspace(0, len(merged) - 1, min(len(merged), 20))})
    sample = [painter.draw(parts[merged[j][0]], merged[j][1]) for j in sample_at]
    palette = palette_of(sample)
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
    if not 90 <= report["seconds"] <= 140:
        report["length_note"] = f"{report['seconds']} s: aimed at 90 to 140 s"
    if size > limit:
        report["over_by"] = size - limit
        if not opts.allow_large:
            temporary.unlink()
            raise TooLarge(report)
    os.replace(temporary, out)
    report["gif"] = str(out)
    return report


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


def at_arg(text: str) -> tuple[int, int]:
    x, y = (int(v) for v in text.split(","))
    return x, y


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="run the window through the scenes and keep what it showed")
    rec.add_argument("--out", type=Path, default=None,
                     help="the recording file: a ZIP in a scratch folder (outside every repository and ~/.taslation), "
                          "holding pictures of the sample pages; render deletes it once the GIF is written")
    rec.add_argument("--list", action="store_true", help="list the scenes (id, title, present or not) and stop")
    rec.add_argument("--scenes", default=None, help="a,b,c: these scenes only (in the table's order)")
    rec.add_argument("--title", default="balloon_dream", help="the OpenMantra title")
    rec.add_argument("--first", type=int, default=4, help="the first page (the dataset's page number, from 1)")
    rec.add_argument("--pages", type=int, default=12)
    rec.add_argument("--spread", action="store_true", help="two pages a screen, right to left (default: one)")
    rec.add_argument("--book-pages", type=int, default=5, help="the pages the whole-book scene reads")
    rec.add_argument("--start-ollama", type=int, default=DEFAULT_PORT, metavar="PORT",
                     help="TASlation's own starter starts Ollama on this loopback port, where nothing may answer; "
                          "stopped at the end (11434 to 11437 are refused)")
    rec.add_argument("--term", default=None, metavar="TERM=RENDERING",
                     help="the series sheet scene adds this term (else it sets the style guide's tone)")
    rec.add_argument("--timeout", type=float, default=180.0, help="seconds a page may take")
    rec.add_argument("--ready-timeout", type=float, default=600.0, help="seconds the window may take to be ready")
    rec.add_argument("--fps", type=float, default=8.0, help="pictures of the window a second")
    rec.add_argument("--quality", type=int, default=88, help="the pictures' JPEG quality")
    rec.add_argument("--size", type=size_arg, default=WINDOW_SIZE, help="TASlation's window, WIDTHxHEIGHT")
    rec.add_argument("--at", type=at_arg, default=WINDOW_AT, help="TASlation's window's place, X,Y")
    rec.add_argument("--client-only", action="store_true", help="picture the window without its title bar and menus")
    rec.add_argument("--models", default="", help="the models folder (default: TASLATION_MODELS_DIR)")
    ren = sub.add_parser("render", help="make the GIF of a recording (and delete the recording)")
    ren.add_argument("recording", type=Path, nargs="?", default=None)
    ren.add_argument("--out", type=Path, required=True, help="the GIF (where git ignores it, or outside the repository)")
    ren.add_argument("--sample", action="store_true", help="made-up frames in place of a recording")
    ren.add_argument("--scenes", default=None, help="a,b,c: these of the recorded scenes only")
    ren.add_argument("--size", type=size_arg, default=SIZE)
    ren.add_argument("--fps", type=float, default=10.0)
    ren.add_argument("--longest", type=float, default=LONGEST_S, help="seconds a wait with nothing changing is shown")
    ren.add_argument("--max-speed", type=float, default=MAX_SPEED)
    ren.add_argument("--title-seconds", type=float, default=TITLE_S)
    ren.add_argument("--card-seconds", type=float, default=CARD_S)
    ren.add_argument("--allow-large", action="store_true", help=f"write a GIF over {GIF_LIMIT} bytes all the same")
    ren.add_argument("--keep-recording", action="store_true", help="keep the recording file after the GIF")
    ren.add_argument("--frames-png", type=Path, default=None, help="a scratch folder for a few frames as PNG")
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--serve-viewer"]:
        return serve_viewer(argv)
    args = parse(argv)
    if args.command == "record":
        return record(args)
    out = pv.check_video_path(args.out)
    if out.suffix.lower() != ".gif":
        raise SystemExit("--out is a .gif")
    opts = Options(size=args.size, fps=args.fps, longest_s=args.longest, max_speed=args.max_speed,
                   title_s=args.title_seconds, card_s=args.card_seconds,
                   scenes=[s.strip() for s in args.scenes.split(",")] if args.scenes else None,
                   allow_large=args.allow_large, frames_png=args.frames_png)
    if args.sample:
        source: Source = sample_source()
    elif args.recording is None:
        raise SystemExit("render needs a recording (or --sample)")
    else:
        source = ZipSource(pv.check_scratch_path(args.recording))
    try:
        report = render(source, out, opts)
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
