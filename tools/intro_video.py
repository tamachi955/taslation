"""The README's introduction made into one animated GIF (dev tool, never part of a release): the scenes of a
recording of the real TASlation window beside a stand-in viewer, numbered, then cards of facts taken from the code.

    python tools/intro_video.py render SCRATCH/intro.zip --out promo/taslation-intro.gif
    python tools/intro_video.py render --sample --out SCRATCH/sample.gif [--frames-png SCRATCH/frames]

The recordings were made by this tool's ``record`` before 2.0.0: TASlation's own window, driven through the scenes of
`SCENES` on its own Tk widgets, pictured with PrintWindow beside a stand-in viewer that turned its pages on the page
keys the window passed on. From 2.0.0 on that window is hidden - the lettering lies over the viewer's own window
(see-through mode, the program's one mode) and no key is passed on -, so there is nothing of it to record and
``record`` went with it; a recording of an earlier version can still be rendered. A recording holds numbers and ids
only besides its pictures, never a line of a page's text, Japanese or translated (`check_no_text`).

``render`` makes a GIF of the recording, 960x540 by default and about 90 to 140 s long: a title card, the scenes
numbered in their order (the window on the right, the stand-in viewer and the step on the left, the key pressed in a
key cap), then the cards "How a page is translated", "The models", "On your own computer" and "Before you use it" -
their figures from the code's constants (`code_facts`), their sentences those of README.md, docs/MANUAL.md,
docs/THIRD_PARTY.md and docs/LEGAL.md. Long waits are cut; a stretch marked as waiting for the models is shown faster, with a badge and
"shown at N.Nx speed" under it. The GIF costs each visitor of the page as little as it can: one palette of 64
colours with the window's own colours kept apart, no dither; each frame stores only what changed; where only the
window's picture changes (a bubble lettered, a word typed, a wait) at most 4 frames a second; a card is one frame.
A GIF over 5 MB is refused (``--allow-large`` writes it and says by how much it is over); either way the scenes that
take the most bytes are said. The recording file is deleted
once the GIF is written (``--keep-recording`` keeps it); it holds pictures of the sample pages, as the GIF does: both
are CC BY-NC 4.0 material ("Sample pages: OpenMantra dataset (Mantra Inc., CC BY-NC 4.0), modified" on every frame
with a page), never part of a release. The GIF goes where git ignores it (``promo/``) or outside the repository; the
recording into a scratch folder. ``render --sample`` renders made-up frames (no window, no model, no manga page)."""

from __future__ import annotations

import argparse
import bisect
import importlib.util
import io
import json
import os
import sys
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
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
GIF_LIMIT = 5_000_000  # bytes: a GIF over this is refused without --allow-large (every visitor of the page loads it)
SIZE = (960, 540)
WINDOW_SIZE = (1240, 860)  # the window's size in a recording
KEY_CAP_MS = 1600.0  # a key cap shows this long (as shown)
MAX_SPEED = 8.0
LONGEST_S = 1.0  # a wait with nothing changing is cut to this long
COLOURS = 64  # the GIF's palette: the pages are black and white with greys, the window's colours are kept apart
STILL_FPS = 4.0  # frames where only the window's picture changes (lettering, typing, waiting): at most this many a second
TITLE_S, CARD_S = 5.0, 5.5
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


README, MANUAL, THIRD_PARTY, LEGAL = "README.md", "docs/MANUAL.md", "docs/THIRD_PARTY.md", "docs/LEGAL.md"
DOCS = (README, MANUAL, THIRD_PARTY, LEGAL)  # the documents a line of the recording may follow


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
    Scene("next_page", "Real-time translation",
          "When you turn a page, its bubbles are replaced by their translations there and then, in reading order. "
          "Press the page key in TASlation; it is passed on to your viewer.", 8.0,
          follows=cites(README, "**Real-time translation**: when you turn a page, its bubbles are replaced by their "
                                "translations there and then, in reading order (from the top right).",
                        "A page key you press in TASlation is passed on to the viewer.")),
    Scene("original", "See the original",
          "Rest the pointer on a bubble: the original lettering shows in its place, and the right pane shows its "
          "Japanese and its translation.",
          6.0,
          follows=cites(MANUAL, "Rest the pointer on a bubble, and after a moment (`hover_delay_ms`, 450 milliseconds "
                                "by default; \"Delay under the pointer\" in \"Settings...\", 0 to 3000, 0 at once) its "
                                "lettering gives way to the original lettering in its place.",
                        "With \"Indicators\" on, the right pane shows that bubble at its top: \"Copy the Japanese\", "
                        "\"Copy the translation\" and \"Ask again\", then its Japanese and its translation (up to five "
                        "lines each).")),
    Scene("turned_past", "Pages you turn past",
          "Turn on before a page is done: the pages you turned past go on being translated, and the right pane shows "
          "how many are left. Turn back, and they are there.", 13.0, present=backlog_present,
          follows=cites(MANUAL, "While you read, TASlation goes on reading and translating the pages you have turned "
                                "past.",
                        "The right pane says how many pages and lines are still to go, and how many pages were turned "
                        "too fast to be taken; turn back to such a page in the viewer and it is read like any other.",
                        "Back on a page done behind you, its lettering shows as soon as the viewer shows it.")),
    Scene("language", "Another language",
          "Choose another language in the left pane - one of {languages}. The page on show follows it.", 8.0,
          follows=cites(MANUAL, "The target language is chosen in the language row of the left pane (or with "
                                "`--language`, or the setting `target_language`).",
                        "Translations can be into any of the {languages} languages of the left pane's language row."),
          own="\"The page on show follows it\": what TASlation does, with Auto on, when the language in the left pane "
              "changes (ui.app, _target_picked)"),
    Scene("sheet", "The series sheet",
          "With Edit on, keep the series' names and terms in its sheet. The circular arrow translates the page again "
          "with them.", 10.0, role="translator",
          follows=cites(README, EDITING_TOOLS)
          + cites(MANUAL, "Everything except the typefaces is told to the model before it translates.",
                  "\"Skip page\" marks a page with nothing to translate, such as an advertisement or the viewer's own "
                  "panel, and the circular arrow (not using the cache) translates the page again with the current "
                  "premises.")),
    Scene("edit", "Rewrite a translation",
          "With Edit on, click a bubble and rewrite its translation. The page follows what you type.", 9.0,
          role="translator",
          follows=cites(README, EDITING_TOOLS)
          + cites(MANUAL, "**Editing a region**: a click on its box opens the region editor beside it.",
                  "After a change, the lettering over the viewer follows a moment later.")),
    Scene("region", "Move or resize a region",
          "Drag a region's box to move it, or a corner of it to resize it.", 6.0, role="translator",
          follows=cites(README, EDITING_TOOLS)
          + cites(MANUAL, "Like shapes in office software, a region is moved by dragging and resized with its corner "
                          "handles, and it is read again only when the new frame covers a larger area (a right click "
                          "during a drag gives the drag up).")),
    Scene("undo", "Undo", "Undo (Ctrl+Z) takes back a change to the page.", 4.0, role="translator",
          follows=cites(README, "Ctrl+Z takes back a change to a page or to this book's translations.")),
    Scene("add_region", "Add a region",
          "Text that was not found: draw a rectangle around it, and it is read and translated.", 8.0,
          role="translator",
          follows=cites(MANUAL, "Draw a rectangle around text that was not detected, and it is read, translated and "
                                "added to the page (later readings use it too).")),
    Scene("full_screen", "Full screen",
          "Put the viewer on its own full screen, inside the viewer: the lettering and the panes follow it.", 6.0,
          role="translator",
          follows=cites(MANUAL, "The viewer can be a window of any size, maximised, or on its own full screen (switch "
                                "it there yourself, inside the viewer; TASlation never does): the lettering and the "
                                "panes follow it.")),
)
SCENE_IDS = tuple(s.id for s in SCENES)


def scene_of(scene_id: str) -> Scene | None:
    return next((s for s in SCENES if s.id == scene_id), None)


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
             cites(README, "The TASlation (Tool Assisting Self-translation of manga) window reads the manga page your "
                           "viewer is showing, translates it on this computer, and shows the translation laid over "
                           "the page.")),
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
             cites(MANUAL, "The bubbles are translated in the order the page's bubbles are read, each with the lines "
                           "before it as context.",
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
        Line("The network is used only when installing and updating.", "bullet",
             cites(README, "| Network | Used only when installing and updating |")),
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
             cites(LEGAL, "the terms of use of the large e-book stores are a contract between the reader and the store.",
                   "Terms differ from store to store, so check them yourself.")),
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


# ---------------------------------------------------------------------------------------------------- a recording's views
def view_at(views: Sequence[dict[str, Any]], t: float) -> dict[str, Any] | None:
    """How the window's page canvas showed its picture at *t* (the last ``views`` entry at *t* or before)."""
    return next((v for v in reversed(views) if float(v["t"]) <= t), None)


def filling_moment(meta: dict[str, Any]) -> float | None:
    """The "how" card's middle moment where the window did not note one: halfway through the lettering of the page
    job the "original" moment shows (the letters noted, numbers only), or None."""
    moments = meta.get("moments") or {}
    t0, t1 = moments.get("original"), moments.get("translated")
    if t0 is None:
        return None
    fill = next((f for f in meta.get("fills", []) if float(f["t"]) >= float(t0) - 1.0), None)
    if fill is None:
        return None
    times = sorted(float(x["t"]) for x in meta.get("letters", [])
                   if x.get("n") == fill["n"] and x.get("on") and (t1 is None or float(x["t"]) <= float(t1)))
    if len(times) < 2:
        return None
    return round(times[(len(times) - 1) // 2] + 60.0, 1)  # (just after the middle bubble was lettered)


def page_on_capture(view: dict[str, Any], pic: Image.Image | None) -> tuple[float, float, float, float]:
    """Where the page is on the picture of the stand-in the window shows (its client area, *view*'s ``image``): the
    stand-in fits each screen with 20 px round it and centres it (it did so); the screen's shape from the
    viewer's picture *pic* (the screen and a margin of the ground round it). The whole picture where *pic* is
    missing."""
    W, H = (float(v) for v in view["image"])
    if pic is None:
        return (0.0, 0.0, W, H)
    ground = np.array([int(dv.GROUND[i:i + 2], 16) for i in (1, 3, 5)], np.int16)
    a = np.asarray(pic.convert("RGB"), np.int16)
    off = np.abs(a - ground).max(axis=2) > 40
    cols, rows = np.flatnonzero(off.mean(axis=0) > 0.02), np.flatnonzero(off.mean(axis=1) > 0.02)
    if len(cols) < 2 or len(rows) < 2:
        return (0.0, 0.0, W, H)
    shape = (cols[-1] - cols[0] + 1) / (rows[-1] - rows[0] + 1)
    h = min(H - 40.0, (W - 40.0) / shape)
    w = h * shape
    return ((W - w) / 2, (H - h) / 2, (W + w) / 2, (H + h) / 2)


def on_picture(box: Sequence[float], view: dict[str, Any]) -> tuple[float, float, float, float]:
    """*box* (pixels of the picture the canvas shows) in pixels of the window: the canvas's scale and offset, then
    where the canvas is in the window."""
    k, (ox, oy), (cx, cy) = float(view["scale"]), view["offset"], view["origin"]
    return (cx + ox + box[0] * k, cy + oy + box[1] * k, cx + ox + box[2] * k, cy + oy + box[3] * k)


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
        if scene.id in ("next_page", "turned_past"):
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
        moments = dict(self.source.meta.get("moments") or {})
        if moments.get("filling") is None:
            moments["filling"] = filling_moment(self.source.meta)
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
        pic = src.pic_at(t)
        page = on_picture(page_on_capture(view, src.image(pic) if pic is not None else None), view)
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


def used_colours(image: Image.Image) -> list[tuple[int, int, int]]:
    """The colours a paletted *image* uses, in the order of their index."""
    palette = image.getpalette() or []
    return [tuple(palette[3 * i:3 * i + 3]) for _count, i in sorted(image.getcolors(256) or [], key=lambda c: c[1])]


DRAWN = (BG, TEXT, DIM, AMBER, BLUE, PANEL, CAP_BG, CAP_EDGE, (255, 255, 255), (0, 0, 0))  # the colours drawn over
VIVID_SPREAD = 64  # a pixel whose channels differ by this much is a colour (the window's frames, bars, badges)


def palette_of(frames: Sequence[Image.Image], colours: int = 255) -> Image.Image:
    """One palette of *colours* entries for the whole GIF: the colours drawn over the frames (`DRAWN`), about an
    eighth for the vivid colours of *frames* at full size (a region's thin frame and its handles keep their colour:
    in a palette made of the pages and the window's greys they would come out dull), the rest from a montage of
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
    sample_at =sorted({int(v) for v in np.linspace(0, len(merged) - 1, min(len(merged), 20))})
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


def only_window_moved(a: Sequence[Any], b: Sequence[Any]) -> bool:
    """Whether frame *b* (part index, key, ms) differs from *a* in the window's picture alone: the same scene, the
    same viewer picture, pointer, key cap, badge and masks."""
    if a[0] != b[0] or a[1][0] != "scene" or b[1][0] != "scene":
        return False
    return a[1][:2] == b[1][:2] and a[1][3:] == b[1][3:]


def thinned(merged: list[list[Any]], still_fps: float | None) -> list[list[Any]]:
    """*merged* with frames where only the window's picture changed shown at most *still_fps* a second: such a
    frame is left out (the one before shown on for its time) while the last one kept is younger than 1/*still_fps*
    and the next frame changes the window alone too - the last of each such stretch is always kept, so it ends on
    the window as it was. Frames with the pointer, a key cap or the viewer moving are all kept."""
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
    ren = sub.add_parser("render", help="make the GIF of a recording (and delete the recording)")
    ren.add_argument("recording", type=Path, nargs="?", default=None,
                     help="a recording (a ZIP in a scratch folder, made before 2.0.0); deleted once the GIF is written")
    ren.add_argument("--out", type=Path, required=True, help="the GIF (where git ignores it, or outside the repository)")
    ren.add_argument("--sample", action="store_true", help="made-up frames in place of a recording")
    ren.add_argument("--scenes", default=None, help="a,b,c: these of the recorded scenes only")
    ren.add_argument("--size", type=size_arg, default=SIZE)
    ren.add_argument("--fps", type=float, default=10.0)
    ren.add_argument("--longest", type=float, default=LONGEST_S, help="seconds a wait with nothing changing is shown")
    ren.add_argument("--max-speed", type=float, default=MAX_SPEED)
    ren.add_argument("--title-seconds", type=float, default=TITLE_S)
    ren.add_argument("--card-seconds", type=float, default=CARD_S)
    ren.add_argument("--colours", type=int, default=COLOURS, help="the palette's colours (at most 255)")
    ren.add_argument("--still-fps", type=float, default=STILL_FPS,
                     help="frames where only the window's picture changes, at most this many a second (0: all)")
    ren.add_argument("--allow-large", action="store_true", help=f"write a GIF over {GIF_LIMIT} bytes all the same")
    ren.add_argument("--keep-recording", action="store_true", help="keep the recording file after the GIF")
    ren.add_argument("--frames-png", type=Path, default=None, help="a scratch folder for a few frames as PNG")
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse(list(sys.argv[1:] if argv is None else argv))
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
