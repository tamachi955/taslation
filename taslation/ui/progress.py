"""What the window says while a page is translated: the stage of the pipeline's progress messages in the window's
language (`stage_of`, `busy_line`, `progress_line`), whether a message means the page is read (`reads_page`), the
page filling in as the pipeline's page events come (`Filling`), the words for a region's state, the unsure
readings that are pieces of the drawing (`unsure_art`), and any
`taslation.messages.Message` in the window's language (`rendered`).

The pipeline's stages are Messages (``pipeline.stage_reading`` and the like): they are recognised by their code. A
plain string is still recognised by its English words (the text fallback, for a caller that passes text)."""

from __future__ import annotations

import re
import types
from dataclasses import dataclass, field
from functools import lru_cache
from statistics import median
from typing import Any, Mapping, Sequence

from PIL import Image

from ..i18n import _, current
from ..message_texts import catalog
from ..messages import Message, render

WORK_STAGES = ("Reading text", "Translating ")  # the pipeline reads or translates the page
# ... and the same stages by their codes
WORK_CODES = frozenset({"pipeline.stage_reading", "pipeline.stage_translating", "ollama.loading"})
SLOW = "ollama.slow"  # the model has said nothing for a while (the translator's on_slow)
FILL_COLOUR = "#2f9bff"  # the outlines of the regions of a page filling in
LOADING = "Getting the Japanese reader ready"  # the stage of a request that waits for the models to load
# A region's state as the region editor and translator mode's outlines name it (the pipeline's words are codes); one not
# listed shows as it is.
STATUS_WORDS = {"translated": "has a translation", "untranslated": "untranslated", "detected": "found",
                "ocr-empty": "no text read", "not-japanese": "not Japanese", "ocr-noise": "not lettering",
                "unmatched": "no longer matches this page", "ocr-unavailable": "Japanese reader missing", "dropped": "dropped",
                "low-confidence": "unsure reading", "sfx": "sound effect", "print": "printed text, not dialogue",
                "erase": "erase only"}


# An unsure reading ("low-confidence": the OCR was guessing) that is a piece of the drawing - a sweat drop, an eye, a
# chin, hair, a floor drain - and not a line: what translator mode neither outlines nor labels (`unsure_art`). Measured
# on the 385 unsure readings of the five OpenMantra series (dev-time, against their text boxes): 380 lie over no text,
# and these tests take some 320 of them while leaving the lines over text labelled (a scream five times the book's
# size read at 0.49, a title, "ここ！？"); only a lone "!" and a one-character piece of a longer line go with the
# drawing. (Page 11 of the end-to-end check: two bodies read as five large characters at 0.22.)
UNSURE_SHORT = 2  # characters: an unsure reading this short is no line (a sure one is: `Pipeline._short_line` asks 0.95)
UNSURE_THIN = 0.5  # a text box thinner than this share of the usual character holds no column or row of lettering
UNSURE_BIG = 2.0  # characters more than this many times the usual size ...
UNSURE_BIG_SHORT = 3  # ... in a reading this short: a stroke of the drawing read as a character or two ...
UNSURE_BIG_GUESS = 0.4  # ... or read with less confidence than this: a guess at shapes (the lines over text: 0.49 up)


def usual_char(regions: Sequence[Any], book_sizes: Sequence[float] = ()) -> float:
    """The usual character size of a page: the median size of the largest character of its regions read as text
    (translated or to translate, `TextRegion.char_size`); else the book's so far (*book_sizes*, the pipeline's
    samples); else the median glyph the detector measured in those regions; 0.0 when nothing tells."""
    text = [r for r in regions if getattr(r, "status", "") in ("translated", "untranslated")]
    sizes = [float(r.char_size) for r in text if getattr(r, "char_size", 0) > 0]
    if not sizes:
        sizes = [float(s) for s in book_sizes if s > 0]
    if not sizes:
        sizes = [float(r.glyph) for r in text if getattr(r, "glyph", 0) > 0]
    return float(median(sizes)) if sizes else 0.0


def unsure_art(region: Any, usual: float) -> bool:
    """Whether *region*, read with low confidence, is a piece of the drawing rather than an unsure line (see
    UNSURE_SHORT and the rest): its reading of UNSURE_SHORT characters or fewer, its text box thinner than UNSURE_THIN of
    the *usual* character, or characters each more than UNSURE_BIG times it in a reading of UNSURE_BIG_SHORT
    characters or fewer or one read with less confidence than UNSURE_BIG_GUESS.
    A region the reader added is never one; neither is a region with another state."""
    if getattr(region, "status", "") != "low-confidence" or str(getattr(region, "kind", "")).startswith("manual"):
        return False
    text = "".join(str(getattr(region, "source_text", "")).split())
    if len(text) <= UNSURE_SHORT:
        return True
    if usual <= 0:
        return False
    x0, y0, x1, y1 = region.text_box
    if min(x1 - x0, y1 - y0) < UNSURE_THIN * usual:
        return True
    if float(getattr(region, "char_size", 0.0)) <= UNSURE_BIG * usual:
        return False
    return len(text) <= UNSURE_BIG_SHORT or float(getattr(region, "ocr_confidence", 1.0)) < UNSURE_BIG_GUESS


@lru_cache(maxsize=None)
def _catalog(lang: str) -> Mapping[str, str]:
    """The message catalog of a window language, made once (read-only)."""
    return types.MappingProxyType(catalog(lang))


def rendered(message: Any) -> str:
    """*message* in the window's language: a `Message` rendered with the message catalog of the window's language
    (its follow-ups and the Messages in its params too); anything else as the text it is ("" for None)."""
    if isinstance(message, Message):
        return render(message, _catalog(current()))
    return "" if message is None else str(message)


def code_of(message: Any) -> str:
    """The code of a Message; "" for a plain string."""
    return str(getattr(message, "code", "") or "")


def status_word(status: str) -> str:
    return _(STATUS_WORDS[status]) if status in STATUS_WORDS else status


def _count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _stage_of_code(code: str, params: Mapping[str, Any], filled: int) -> str | None:
    if code == "pipeline.stage_reading":
        return _("reading {n} line(s)").format(n=_count(params.get("total")))
    if code == "pipeline.stage_finding":
        return _("finding the bubbles")
    if code == "pipeline.stage_translating":
        total = _count(params.get("bubbles"))
        if filled > 0:
            return _("{done} of {total} line(s) done").format(done=min(filled, total), total=total)
        return _("asking the model")
    return None


def stage_of(progress: Any, filled: int = 0) -> str | None:
    """The stage a pipeline progress message (a Message, by its code; a plain string by its English words) names, in a
    few words of the window's language; while the model's answer comes in, how many of the lines it was asked for
    are lettered already (*filled*). None for a message it does not know. Every count is of lines (the unit of the
    band, the strip and the run's messages)."""
    code = code_of(progress)
    if code:
        return _stage_of_code(code, progress.params, filled)
    p = str(progress or "").strip()
    reading = re.match(r"Reading text \d+/(\d+)", p)
    asked = re.match(r"Translating (\d+) bubble", p)
    if reading:
        return _("reading {n} line(s)").format(n=int(reading.group(1)))
    if p.startswith("Finding bubbles"):
        return _("finding the bubbles")
    if asked and filled > 0:
        total = int(asked.group(1))
        return _("{done} of {total} line(s) done").format(done=min(filled, total), total=total)
    if p.startswith("Translating "):
        return _("asking the model")
    if p.startswith(LOADING):
        return _("getting the Japanese reader ready")
    return None


def _renders(progress: Any) -> bool:
    """Whether a progress message says the page is typeset (the last stage)."""
    code = code_of(progress)
    return code == "pipeline.stage_rendering" if code else str(progress or "").strip().startswith("Rendering")


def slow_line() -> str:
    """The busy badge's line once the model has said nothing for a while during a page."""
    return _("The translation program is slow to answer (it may still be loading). Stop cancels this page.")


def busy_line(progress: Any, seconds: float, filled: int = 0, reading: bool = False) -> str:
    """The busy band's line: the stage of the pipeline's latest progress message in a few words (a message it
    does not know as it says it, in the window's language) and the seconds so far. In a run's *reading* pass nothing
    is translated: the stage alone."""
    s = int(seconds)
    if reading:
        return stage_of(progress, filled) or rendered(progress).strip()
    if code_of(progress) == SLOW:
        return slow_line()
    if _renders(progress):
        return _("Typesetting... ({seconds} s)").format(seconds=s)
    stage = stage_of(progress, filled)
    if stage is None:
        stage = rendered(progress).strip().rstrip(".")
    if not stage:
        return _("Translating... ({seconds} s)").format(seconds=s)
    return _("Translating... {stage} ({seconds} s)").format(stage=stage, seconds=s)


def _finds(progress: Any) -> bool:
    """Whether a progress message says the page's text is being looked for (the first stage, also of a page that
    comes from the cache: nothing is translated yet, maybe nothing will be)."""
    code = code_of(progress)
    return code == "pipeline.stage_finding" if code else str(progress or "").strip().startswith("Finding bubbles")


def progress_line(progress: Any, reading: bool = False) -> str:
    """The status bar's line for a pipeline progress message: its stage in the window's language, as the band
    says it; a message without a stage as it says it (in the window's language). In a run's *reading* pass: the
    stage alone. Looking for the text says "Looking at the page...", not "Translating...": a page from the cache
    is only looked at and drawn."""
    if reading:
        return stage_of(progress) or rendered(progress).strip()
    if code_of(progress) == SLOW:
        return slow_line()
    if _renders(progress):
        return _("Typesetting...")
    stage = stage_of(progress)
    if stage and _finds(progress):
        return _("Looking at the page... {stage}").format(stage=stage)
    return _("Translating... {stage}").format(stage=stage) if stage else rendered(progress).strip()


def reads_page(progress: Any) -> bool:
    """Whether a progress message says the page is being read or translated: a page from the cache is only found
    and drawn, and gets no busy band."""
    code = code_of(progress)
    if code:
        return code in WORK_CODES
    return str(progress or "").strip().startswith(WORK_STAGES)


def asks_model(progress: Any) -> bool:
    """Whether a progress message says the model is asked for the page's translations (the badge then counts the
    bubbles lettered from there)."""
    code = code_of(progress)
    return code == "pipeline.stage_translating" if code else str(progress or "").startswith("Translating ")


@dataclass
class Filling:
    """A page filling in on the window while it is translated (the pipeline's page events): the frame it is read
    from, the picture its regions are lettered on (that frame; or, when the page on show is translated again, the
    page as it was shown), the regions' boxes and how far each one is, and the finished page once it is there."""

    frame: Image.Image
    base: Image.Image
    boxes: list[tuple[int, int, int, int]]
    states: list[str] = field(default_factory=list)  # per box: "found", "read", "skipped" (no text) or "lettered"
    page: Image.Image | None = None  # the base with the regions lettered so far
    final: Image.Image | None = None  # the finished page
    mark: int = 0  # how many were lettered when the model was last asked (the badge counts from there)

    def __post_init__(self) -> None:
        if not self.states:
            self.states = ["found"] * len(self.boxes)

    @property
    def filled(self) -> int:
        return sum(1 for s in self.states if s == "lettered")

    def outlines(self) -> list[tuple[tuple[int, int, int, int], str, bool]]:
        """The boxes still waiting for a translation: dashed until read, solid once read."""
        return [(box, FILL_COLOUR, state == "found") for box, state in zip(self.boxes, self.states)
                if state in ("found", "read")]

    def letter(self, index: int, box: tuple[int, int, int, int], patch: Image.Image, text: str) -> None:
        """Region *index* lettered: its patch goes on the page (a region whose translation was dropped gets the
        page back as it was, and its outline)."""
        if self.page is None:
            self.page = self.base.copy()
        self.page.paste(patch, (int(box[0]), int(box[1])))
        self.states[index] = "lettered" if text else "read"
