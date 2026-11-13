"""The page pipeline: fingerprint -> cache? -> detect -> OCR -> translate -> erase -> typeset.

Everything here works on in-memory images. The only things that persist are
the text-only translation cache (see ``taslation.cache``) and the reader's own
annotations and series sheet (see ``taslation.annotations``). A page that is
already in the cache is composited straight away without OCR or the language
model.

Two ways of working:

* ``process()``: one page now (live reading). Translates with the series sheet and
  the last pages as context.
* ``scan()`` + ``commit_unit()``: used by the whole-book batch. ``scan()``
  reads a page (detection + OCR) and keeps only text and geometry; the batch
  reads every page first and then translates runs of lines, and
  ``commit_unit()`` stores each result in the cache.

What was translated is always kept: a page unit with one real translation or
more is stored even when a bubble got none. The entry is then marked
(`CachedPage.incomplete`), the bubble stays untranslated on the page, and the
next reading of the page (``process()``) or whole-book run (``scan()``) asks
for what is missing, and only that.

``process(events=...)`` also tells a window how the page fills in while it is
translated (``PageFill``): the regions as soon as they are found, each one as
it is read, each one lettered as its translation arrives, then the finished
page.

Shown again: a page from the cache that this session lettered before comes back from memory
(``shown_pages``, `render.memo.ShownPages`) while its capture area has the very same pixels and nothing its
lettering is made from changed (`_shown_key`): no detection, no erase, no typesetting. A region's live erase is kept
too (``erased_regions``, by `erase_key`), so a page whose pixels changed elsewhere erases only what changed; a
page from the cache that must wait for the inpainting model is sent first as an early look (`_early_look`). All
of it in memory only.

Erased ahead: the whole-book batch erases every page it has read in the
background (``scan(keep_regions=True)`` gives the regions as the render will
see them, `erase_page` erases them) and keeps the erased pages in memory
(`pageimages.PageImages`, set as ``erased_ahead``). `_render` takes a region's
erase from there when its key matches (`erase_key`: the region, the settings of
the erase and the pixels round it, so the very page in the very place), and
erases the region itself otherwise. ``gpu_gate``, while set, is called before
LaMa runs on the GPU (the batch holds it while the reader turns pages); the
layout model does not wait for it (`_detect`).

What the pipeline says is a `taslation.messages.Message` (a ``str`` with a
``code`` and ``params``): the progress callback gets the stages of a page
(``pipeline.stage_finding``, ``pipeline.stage_reading`` {done, total},
``pipeline.stage_translating`` {bubbles, translator}, ``pipeline.stage_rendering``), ``PageResult.error`` is the Message of what went
wrong, and `summary` is a finished page's line (``pipeline.from_cache`` /
``pipeline.translated``). ``process(cancel=...)`` and ``scan(cancel=...)`` stop
between regions while reading, before and during the request to the model and
before rendering, and raise `Cancelled`; a page cancelled before its
translation came back leaves nothing in the cache.
"""

from __future__ import annotations

import copy
import functools
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import hashlib
import inspect
import math
import re
import threading
import time
import unicodedata
from collections import Counter, deque
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Sequence

import cv2
import numpy as np
from PIL import Image

from . import fingerprint as fp
from .pageimages import ErasedRegion, PageImages, packed_mask, region_digest
from .render.memo import ErasedRegions, ShownPages, changed_pixels, pixels_digest, signature
from .devices import StageTimes
from .cache import INDEXED_WITHIN, BookCache, CachedBubble, CachedPage
from .colophon import AUTHOR_LABELS, LABELS
from .detect import layout as layout_model
from .detect.beyond import ocr_view
from .detect.layout import LayoutModel, Shaper, cover_of, covered, model_regions, take_shape
from .detect.tilt import Upright, ink_frame, lettering_tilt, region_ink
from .annotations import (ERASE_ONLY, BookAnnotations, BookArea, Glossary, StyleGuide, clean_book_settings,
                          join_premises, page_side)
from .review import OCR_UNSURE, flags_for
from .textclean import clean_text
from .config import Settings
from PIL import ImageOps

from .detect import (
    BubbleDetector,
    DetectorConfig,
    TextBlockConfig,
    TextBlockDetector,
    drop_nested,
    focus_oversized,
    is_dark,
    merge_regions,
    order_on_page,
)
from .ocr.charspot import (CharspotReading, OcrEngine, charspot_accepts, looks_japanese, read_crop, size_sample,
                           usual_size)
from .regions import ERASED, apply_order_hints, region_meta, Box, PageResult, TextRegion, box_iou
from .render import artwork
from .render import (FontSpec, Lettering, balance_marks, erase_region, find_font, layout_text, make_lettering,
                     resolve_font, text_room)
from .annotations import LetteringStyle, RegionStyle, ink_of
from .render import covers, drawable, strip_marks
from .render.erase import LINK_LEVELS
from .render.typeset import QUARTER_TURNS, UNCAPPED_KINDS, Lettered, TextFormat, ink_rgb, letter_text, page_caps
from .render.vertical import layout_stacked, stacked_room
from .translate import TranslationError, Translator
from .translate import base as _base
from .translate.base import accepts, ask_again_romanised, ask_for_missing, worth_asking_again
from .translate.continuation import facts_of
from .translate.renderings import BookNames, NamedPremises
from .messages import Cancelled, Message, message_of

ProgressFn = Callable[[str], None]  # gets a Message (a str with .code and .params): the stage of the page
EventFn = Callable[[str, dict[str, Any]], None]  # (kind, data): how the page fills in, see PageFill
SlowFn = Callable[[float], None]  # the model has said nothing for this many seconds (once per request)


def check_cancel(cancel: threading.Event | None) -> None:
    """Raise `Cancelled` once *cancel* is set."""
    if cancel is not None and cancel.is_set():
        raise Cancelled()


class _Timer:
    def __init__(self) -> None:
        self.t = time.perf_counter()
        self.timings: dict[str, float] = {}

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.timings[name] = self.timings.get(name, 0.0) + (now - self.t)
        self.t = now


TITLE_SCALE = 3.0  # characters this many times the book's usual size, loose and without a mark of speech, are a title ...
TITLE_LINES = 3  # a title page: the title, the author's name, a badge or a line of credit
TITLE_SHARE = 0.03  # ... and so are characters this share of their page's height (dialogue a hundredth or so)
PRINT_LINES = 4  # lines set across in one block of the layout model's: print (a blurb), not lettering
SAME_BLOCK = 0.8  # ... a line this much inside the block's text box is one of its lines
GLYPH_REACH_ERASE = 4.0  # glyphs: ink a bubble's text box holds outside its mask is lettering up to this long ...
EDGE_KEEP = 4  # ... and off the box's edge by this many px (there, it is the outline)
CHAR_GROW = 0.15  # of a glyph: how far past the reading's character box the lettering of a plain box is painted out
LOOSE_KINDS = ("text", "text-dark")  # lettering with nothing round it (a closed block is "text-on-page", "text-on-dark")
ON_ART_KINDS = ("text", "text-dark", "text-on-page", "text-on-dark")  # lettering set on the page's ground
DISPLAY_KIND = "shout"  # (one of `UNCAPPED_KINDS`) the kind display lettering on the art is capped as
ROOM_GLYPHS = 2.0  # a model's single line of lettering on the page is lettered in a room grown by this many glyphs
ONE_LINE = 0.5  # a glyph this share of its lettering box's short side: the lettering is one column (or row)
LARGE_LETTERING = 2.0  # glyphs this many times the book's usual size (the readable one at least) are display lettering
ENCLOSED_LARGE = 2.0  # ... and this many times that again in a closed block (its enclosure is mostly a bubble's)
PANEL_SURE = 0.8  # a region this much inside the box of the panel it was put in is in that panel (its room stays in it)


def detector_from_settings(settings: Settings) -> BubbleDetector:
    return BubbleDetector(
        DetectorConfig(
            white_threshold=settings.white_threshold,
            dark_threshold=settings.dark_threshold,
            min_area_ratio=settings.min_bubble_area_ratio,
            max_area_ratio=settings.max_bubble_area_ratio,
            min_size=settings.min_bubble_size,
            take_columns_beyond=settings.take_columns_beyond,
            split_lobes=settings.split_joined_bubbles,
        )
    )


def mask_polygon(mask: np.ndarray) -> list[tuple[float, float]]:
    """Coarse outline of the mask (local pixel coordinates), used to re-create it later."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    contour = max(contours, key=cv2.contourArea)
    approx = cv2.approxPolyDP(contour, 0.01 * cv2.arcLength(contour, True), True)
    return [(float(p[0][0]), float(p[0][1])) for p in approx]


def polygon_mask(poly: Sequence[tuple[int, int]], width: int, height: int) -> np.ndarray:
    mask = np.zeros((max(1, height), max(1, width)), np.uint8)
    if len(poly) >= 3:
        pts = np.array([[int(x), int(y)] for x, y in poly], dtype=np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(mask, [pts], 255)
    return mask


# (not ・ and ー, full or half width: dots and a dash in a line of any language)
_KANA_RE = re.compile(r"[぀-ヺヽ-ヿｦ-ｯｱ-ﾟ]")
_HAN_RE = re.compile(r"[㐀-䶿一-鿿豈-\ufaff\U00020000-\U0003ffff]")
_HANGUL_RE = re.compile(r"[ᄀ-ᇿ\u3130-\u318fꥠ-\ua97f가-\ud7ff]")
# The targets written without Han and Hangul (`ui/constants.LANGUAGES` but Chinese and Korean; the alphabets and
# abugidas alike): those two scripts in a reply are the model not having translated. A target not named here, a
# Cantonese or a 日本語 a reader typed in, is not judged: Korean may hold hanja, Chinese names may hold anything.
_TARGETS_WITHOUT_HAN = frozenset({
    "english", "spanish", "portuguese", "french", "german", "italian", "polish", "dutch", "turkish", "indonesian",
    "vietnamese", "russian", "thai", "arabic", "hebrew", "hindi", "bengali"})
_SFX_RE = re.compile(r"^[ァ-ヺーヽヾｦ-ﾟっ！!？?…・、。ッー〜~ ]{1,6}$")
_LATIN_RE = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]")
_DIGIT_RE = re.compile(r"[0-9０-９]")
_SPEECH_MARK_RE = re.compile(r"[!?！？…‥。、〜～~―—ー]")


_JA_STANDARD_RE = re.compile(
    r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ"  # kana, kanji
    r"、-〃「-』〜‥…—―・ー"  # 、。〃「」『』〜‥…―ー・
    r"！（），．？～!?.,'\"\-~() ]"  # ！（），．？～ and ASCII punctuation
)


def is_sound_effect(text: str) -> bool:
    """Short katakana-only text (e.g. a drawn onomatopoeia) rather than dialogue."""
    return bool(_SFX_RE.match(text.strip()))


def japanese_share(text: str) -> float:
    """Share of characters that belong in Japanese dialogue (kana, kanji, usual punctuation)."""
    if not text:
        return 0.0
    return len(_JA_STANDARD_RE.findall(text)) / len(text)


def looks_like_print(text: str, text_box: Box) -> bool:
    """Horizontal text with Latin letters or several digits: viewer widgets, colophons, prices, URLs.

    Manga dialogue is almost always vertical and almost never mixes in Latin
    letters or strings of digits; the reader's own panels (ratings, store
    buttons) and the imprint page do. Those are not worth translating.
    """
    w, h = text_box[2] - text_box[0], text_box[3] - text_box[1]
    if w <= 1.5 * h:
        return False
    return len(_LATIN_RE.findall(text)) >= 2 or len(_DIGIT_RE.findall(text)) >= 3


def loose(r: TextRegion) -> bool:
    """Lettering with nothing round it: set on the page, or a model's bubble the classical detectors found no outline
    for (its classical shape, taken after the reading, is the plain box)."""
    return r.kind in LOOSE_KINDS or (r.after is not None and r.after.tier == 3) or (r.from_model and r.tier == 3)


def title_unit(read: Sequence[TextRegion], usual: float, height: int = 0) -> bool:
    """Whether the regions *read* as text on a page unit (*height* px tall) are its titles: a title page or a chapter's
    opening page (the title, its badge, the author's name). Every one is loose lettering (`loose`: set on the page, or
    a model's region the classical detectors found no outline for) with no mark of speech and no sound effect, and one
    at least is set far above the book's lettering (its largest character, a title's furigana aside): `TITLE_SCALE`
    times its *usual* size, or `TITLE_SHARE` of the unit's height (a book's first pages, with no lettering of its own
    to compare yet). A title stands nearly alone: at most
    `TITLE_LINES` lines on the unit. A unit with one line of speech is no title page (a shout set large on a page of
    dialogue stays), nor is a page of narration."""
    if not read or len(read) > TITLE_LINES or any(not loose(r) or _SPEECH_MARK_RE.search(r.source_text) or is_sound_effect(r.source_text)
                       for r in read):
        return False
    return any(r.char_size >= TITLE_SCALE * usual or (height and r.char_size >= TITLE_SHARE * height) for r in read)


def printed_lines(regions: Sequence[TextRegion]) -> list[TextRegion]:
    """The regions read as text that are lines of a printed block: `PRINT_LINES` or more horizontal lines (`looks_like_
    print`'s shape) lying in one text box of the layout model, which saw them as one block (a back cover's blurb, an
    advertisement, a colophon), with the model's region itself. Manga lettering runs down; a block of lines set across
    is print. Without the layout model there is no such box, and nothing changes."""
    read = [r for r in regions if r.status == "untranslated" and r.source_text and not r.kind.startswith("manual")]
    out: list[TextRegion] = []
    for m in regions:
        if not m.from_model or m.kind in ("bubble", "dark-bubble"):
            continue
        t = m.text_box
        lines = [r for r in read if r is not m and _across(r.text_box)
                 and _box_inter(r.text_box, t) >= SAME_BLOCK * max(1, _box_area(r.text_box))]
        lines_in = sum(max(1, round((r.text_box[3] - r.text_box[1]) / max(1.0, r.char_size or 1.0))) for r in lines)
        if lines_in >= PRINT_LINES:
            out.extend(r for r in [*lines, m] if r not in out and r in read)
    return out


def _across(box: Box) -> bool:
    return box[2] - box[0] > 1.5 * (box[3] - box[1])


def _box_area(b: Box) -> int:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _box_inter(a: Box, b: Box) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def looks_like_credit(text: str, text_box: Box) -> bool:
    """Lettering loose on the page that names rather than says: no kana and no mark of speech, set horizontally, or
    with a colophon's label in it (publisher, author, ...) whichever way it runs. Japanese speech carries kana or a
    mark; a name, a title or a publisher's line on a cover or a title page has neither. A caption in a box of its own
    is not asked (`Pipeline._judge`), and a reader's rectangle reads whatever it holds."""
    if _KANA_RE.search(text) or _SPEECH_MARK_RE.search(text):
        return False
    flat = unicodedata.normalize("NFKC", text).upper()
    if any(label in flat for label in (*LABELS, *AUTHOR_LABELS)):
        return True
    return text_box[2] - text_box[0] > 1.5 * (text_box[3] - text_box[1])


_WORDS_RE = re.compile(r"[぀-ヺヽ-ヿ㐀-䶿一-鿿々〆ｦ-ｯｱ-ﾟ]")  # kana and kanji: what a line has to translate


def sheet_renderings(sheet: Glossary | None) -> list[str]:
    """Every rendering *sheet* writes down: terms, names, forms of address. Longest first, for taking them out."""
    if sheet is None:
        return []
    found = {e.rendering for e in sheet.entries} | {c.rendering for c in sheet.characters}
    found |= {form for c in sheet.characters for form in c.addresses.values()}
    return sorted((r.strip() for r in found if r.strip()), key=len, reverse=True)


def foreign_script(output: str, target_language: str, sheet: Glossary | None = None) -> bool:
    """Whether *output* holds Han or Hangul in a target written without them (`_TARGETS_WITHOUT_HAN`), outside the
    renderings of *sheet* (a reader who wants 剣 kept in the English says so there)."""
    if target_language.split("(")[0].strip().lower() not in _TARGETS_WITHOUT_HAN:
        return False
    if not (_HAN_RE.search(output) or _HANGUL_RE.search(output)):
        return False
    for rendering in sheet_renderings(sheet):
        output = output.replace(rendering, "")
    return bool(_HAN_RE.search(output) or _HANGUL_RE.search(output))


def is_real_translation(source: str, output: str, target_language: str = "English",
                        sheet: Glossary | None = None) -> bool:
    """Reject outputs that are no translation: those must never reach the cache.

    The source again is a copy when the source has words in it (kana or kanji); a line without any (punctuation
    alone, "……" or "!?"; a number) is its own translation, as professional translations keep it. Kana in the
    output means the Japanese was copied (Chinese targets legitimately contain Han characters, so only kana
    counts); so does Han or Hangul in a target written without them, unless *sheet* has that rendering
    (`foreign_script`). A reply running in a loop is no translation either (`looping_reply`).
    """
    if output.replace(" ", "") == source.replace(" ", "") and (not output.strip() or _WORDS_RE.search(source)):
        return False
    lang = target_language.strip().lower()
    if _KANA_RE.search(output) and not lang.startswith(("japanese", "ja", "日本")):
        return False
    return not foreign_script(output, target_language, sheet) and not looping_reply(output, source)


def lettering_size(text_box: Box, source_text: str, lo: int, hi: int) -> int:
    """Size of the original lettering, from its box and its character count, within [lo, hi]."""
    area = max(1, (text_box[2] - text_box[0]) * (text_box[3] - text_box[1]))
    glyph = (area / max(1, len(source_text.replace(" ", "")))) ** 0.5
    return int(max(lo, min(hi, round(glyph))))


def direction_of(region: Any) -> str:
    """The text direction the reader set for *region* (`RegionStyle.direction`; "" for none)."""
    style = getattr(region, "style", None)
    return getattr(style, "direction", "") or ""


def translation_room(mask: np.ndarray, text_box: Box, source_text: str, settings: Settings, kind: str = "bubble",
                     x0: int = 0, y0: int = 0, font: str = "", direction: str = "") -> int:
    """Characters of translation a region has room for at the size of its original lettering (readable at
    least), or 0 when it has plenty (more than the translation of *source_text* is likely to need). *font* is
    the family name the series sheet suggests, if any; *direction* the region's text direction (turned a quarter:
    the room of the mask turned, its width and height swapped; stacked: the cells its columns hold)."""
    s = settings
    if not s.readable_font_size:
        return 0
    size = lettering_size(text_box, source_text, s.readable_font_size, max(s.readable_font_size, 18))
    spec = find_font(s.font_path, s.fonts_dir, "", s.target_language, font)
    centre = None
    if kind in ("text", "text-dark"):
        centre = ((text_box[0] + text_box[2]) / 2.0 - x0, (text_box[1] + text_box[3]) / 2.0 - y0)
    if direction in QUARTER_TURNS:
        mask = np.ascontiguousarray(mask.T)
        centre = (centre[1], centre[0]) if centre is not None else None
    if direction == "stacked":
        room = stacked_room(mask, size, s.line_spacing, centre)
    else:
        room = text_room(mask, spec.path, size, s.line_spacing, spec.bold_variation, centre)
    likely = 2 * len(source_text.replace(" ", ""))  # a translation runs to about twice the characters
    return max(4, room) if room < likely else 0


# --- scan results (text + geometry only; no pixels) -------------------------------

@dataclass
class ScannedRegion:
    bbox: Box
    text_box: Box
    poly: list[tuple[float, float]]  # bubble interior outline, local to bbox
    source_text: str
    status: str  # untranslated (= Japanese text) | not-japanese | ocr-empty | ocr-unavailable | erase (`ERASED`)
    order: int = 0
    kind: str = "bubble"
    ocr_confidence: float = 1.0
    pieces: int = 0  # dark pieces the detector counted in the region
    speaker: str = ""  # reader-made facts, handed to the model with the text
    tag: str = ""
    continues: bool = False
    remark: str = ""
    room: int = 0  # characters of translation the region has room for at the size of its lettering (0 = plenty)
    aliases: tuple[Box, ...] = ()  # the boxes of the regions it was read in place of (a classical repeat of its lettering)
    angle: float = 0.0  # degrees its lettering is turned counter-clockwise (`TextRegion.angle`)

    @property
    def is_japanese(self) -> bool:
        return self.status == "untranslated"

    @property
    def mask(self) -> np.ndarray:
        """The erase mask rebuilt from the outline (for fitting a translation without the page image)."""
        return polygon_mask([(int(x), int(y)) for x, y in self.poly], self.bbox[2] - self.bbox[0],
                            self.bbox[3] - self.bbox[1])


@dataclass
class ScannedUnit:
    index: int
    box: Box  # content box in capture coordinates
    fingerprint: str
    aspect: float
    regions: list[ScannedRegion] = field(default_factory=list)  # regions still to translate
    cached: bool = False  # every text region is already in the translation cache: nothing to translate
    kept: list[CachedBubble] = field(default_factory=list)  # cached bubbles confirmed by the current detection
    dropped: int = 0  # cached bubbles no current text region corresponds to (removed from the cache)
    stored_fingerprint: str = ""  # fingerprint of the cache entry this unit matched ("" = not in the cache yet)

    def japanese(self) -> list[ScannedRegion]:
        return [r for r in self.regions if r.is_japanese]

    def normalize(self, box: Box) -> tuple[float, float, float, float]:
        return fp.PageUnit(self.box, self.fingerprint, self.index).normalize(box)


@dataclass
class PageScan:
    width: int
    height: int
    units: list[ScannedUnit] = field(default_factory=list)
    # with *keep_regions*: the regions the render will erase once the page is translated, as it will see them
    # (`Pipeline.scan`), in memory only, for the erase ahead (`Pipeline.erase_page`)
    erasable: list[TextRegion] = field(default_factory=list)

    @property
    def fingerprints(self) -> list[str]:
        return [u.fingerprint for u in self.units]

    @property
    def bubbles(self) -> int:
        return sum(len(u.japanese()) for u in self.units)


def scanned_bubble(unit: ScannedUnit, region: ScannedRegion, text: str, flags: Sequence[str] = ()) -> CachedBubble:
    """The cached bubble of *region*, a region of the scanned *unit*, translated as *text*: its box and its outline in
    the unit's terms, as `Pipeline.commit_unit` stores it and `PageDraft` letters it before it is stored."""
    pu = fp.PageUnit(unit.box, unit.fingerprint, unit.index)
    x0, y0 = region.bbox[0], region.bbox[1]
    poly = [pu.normalize((int(x) + x0, int(y) + y0, int(x) + x0, int(y) + y0))[:2] for x, y in region.poly]
    return CachedBubble(box=pu.normalize(region.bbox), text=text, poly=poly, flags=list(flags), angle=region.angle)


def erases(region: Any) -> bool:
    """Whether the render erases *region*: a translation to letter in its place, or "erase only"."""
    return (region.status == "translated" and bool(region.translated_text)) or region.status == ERASED


class PageFill:
    """How a page fills in while it is translated, told through *emit*(kind, data) for a window to draw:

    * ``regions``: {"boxes": [(x0, y0, x1, y1), ...], "size": (width, height)} - the text regions about to be read,
      in capture coordinates, as soon as detection is done and the cache has had its say (a page that comes from
      the cache announces none);
    * ``read``: {"index", "status", "box"} - a region has been read; "untranslated" means Japanese to translate,
      any other status that it is left as it is; *box* is where it is now (reading can take back a column the
      detection had taken in);
    * ``translated``: {"index", "text", "box", "patch"} - a region lettered: *patch* is the page in *box* with the
      region erased and *text* typeset in it. A translation that arrives while the model is still writing the
      others is lettered at once; one that changes afterwards (shortened to fit, given the series sheet's
      renderings) comes again, and one that is dropped comes with "" and the region as it was;
    * ``page``: {"image"} - the finished page, rendered from scratch exactly as without the events. A page from the
      cache whose lettering waits for the inpainting model on the art comes twice (`Pipeline._early_look`): first
      with {"image", "early": True}, lettered at once with the paper fill there (after a ``regions`` with no boxes,
      so that a window takes it as a page filling in), then finished.

    The indices count the announced regions. The patches come from a working copy of the page on which each region
    is erased and lettered in turn, so where two regions overlap a patch can differ for a moment from the finished
    page; ``page`` is exact. Nothing here is written anywhere: the events carry pixels from memory to memory."""

    def __init__(self, pipeline: "Pipeline", rgb: np.ndarray, emit: EventFn):
        self.pipeline = pipeline
        self.rgb = rgb
        self.emit = emit
        self.regions: list[TextRegion] = []  # the announced regions (held, so their ids stay theirs)
        self.index: dict[int, int] = {}  # id(region) -> its index
        self.shown: dict[int, str] = {}  # index -> the text lettered on the working copy
        self.boxes: dict[int, Box] = {}  # index -> the part of the page its lettering changed
        self.work: np.ndarray | None = None

    def link(self, scanned: "ScannedRegion", region: TextRegion) -> None:
        """A scan's *scanned* region is the announced *region*: a translation of the one letters the other."""
        i = self.index.get(id(region))
        if i is not None:
            self.index[id(scanned)] = i

    def announce(self, regions: Sequence[TextRegion]) -> None:
        for r in regions:
            if id(r) not in self.index:
                self.index[id(r)] = len(self.regions)
                self.regions.append(r)
        if self.regions:
            h, w = self.rgb.shape[:2]
            self.emit("regions", {"boxes": [r.bbox for r in self.regions], "size": (w, h)})

    def read(self, region: TextRegion) -> None:
        i = self.index.get(id(region))
        if i is not None:
            self.emit("read", {"index": i, "status": region.status, "box": region.bbox})

    def draft(self, region: "TextRegion | ScannedRegion", text: str) -> None:
        """A translation that came in while the model is still writing: lettered now, when it is a real one. A
        failure here costs only the early look; it never reaches the translation."""
        try:
            i = self.index.get(id(region))
            text = balance_marks((text or "").strip())
            if i is None or not text or self.shown.get(i) == text:
                return
            if not self.pipeline.real_translation(region.source_text, text):
                return
            if i in self.shown:  # the model wrote the bubble twice: the page is lettered again with the new one
                self._reletter({i: text})
            else:
                self._letter(i, text)
        except Exception:  # noqa: BLE001 - the finished page is rendered on its own
            pass

    def settle(self, regions: Sequence[TextRegion]) -> None:
        """The final translations of *regions* (after `tighten`): the ones not lettered yet are lettered; when one
        that is lettered changed or went, the working copy is lettered again and the changed ones are sent."""
        self.settle_texts([(r, r.translated_text if r.status == "translated" and r.translated_text else "")
                           for r in regions])

    def settle_texts(self, finals: Sequence[tuple["TextRegion | ScannedRegion", str]]) -> None:
        """`settle` with the final text of each region given ("": none)."""
        final = {self.index[id(r)]: text for r, text in finals if id(r) in self.index}
        changed = {i: t for i, t in final.items() if i in self.shown and self.shown[i] != t}
        new = {i: t for i, t in final.items() if t and i not in self.shown}
        if changed:
            self._reletter({**changed, **new})
            return
        for i in sorted(new):
            self._letter(i, new[i])

    def finish(self, image: Image.Image) -> None:
        self.emit("page", {"image": image})

    def _cap_shown(self) -> None:
        self.pipeline.cap_sizes([self.regions[i] for i in self.shown], list(self.shown.values()))

    def _letter(self, i: int, text: str) -> None:
        if self.work is None:
            self.work = self.rgb.copy()
        self.shown[i] = text
        self._cap_shown()
        self.boxes[i] = self.pipeline.letter_region(self.work, self.regions[i], text, quick=True)
        self._send(i, text, self.boxes[i])

    def _reletter(self, texts: dict[int, str]) -> None:
        """The working copy lettered again from the page as captured, with *texts* (index -> text, "" = none) in
        place of what was shown; each of them is sent with the part of the page it changes now or changed before."""
        before = dict(self.boxes)
        for i, t in texts.items():
            if t:
                self.shown[i] = t
            else:
                self.shown.pop(i, None)
        self.work = self.rgb.copy()
        self._cap_shown()
        self.boxes = {i: self.pipeline.letter_region(self.work, self.regions[i], self.shown[i], quick=True)
                      for i in sorted(self.shown)}
        for i in sorted(texts):
            box = before.get(i, self.regions[i].bbox)
            if i in self.boxes:
                box = _union(box, self.boxes[i])
            self._send(i, texts[i], box)

    def _send(self, i: int, text: str, box: Box) -> None:
        assert self.work is not None
        x0, y0, x1, y1 = box
        patch = Image.fromarray(self.work[y0:y1, x0:x1].copy())
        self.emit("translated", {"index": i, "text": text, "box": box, "patch": patch})


DraftLines = Sequence[tuple[ScannedUnit, "dict[int, str]"]]  # a page's scanned units, each with lines: index -> text


class PageDraft:
    """A page of a whole-book run with lines the model has answered and the run has not stored yet, lettered for the
    window alone (`translation_view`): its start is the page as the cache letters it now (`Pipeline.page_picture`:
    its frame when the cache holds nothing of it), and each line given to `letter` is matched to the run's region of
    it as a cached bubble is (`scanned_bubble`, `Pipeline._apply_cached`), erased (the erase the run did ahead,
    `PageImages.find`, else the paper fill: never LaMa) and lettered on a working copy (`work`) as
    `Pipeline.translated_page` letters it. A line lettered once is not lettered again: the sizes of the page are kept
    alike over the lines given so far (`cap_sizes`), and the stored page, lettered afresh (`restart`), puts them right.
    Nothing is stored and nothing is written: the working copy is in memory only. *ok* is False when no image of the
    page is held any more (the memory cap made room): nothing can be shown of it then."""

    def __init__(self, pipeline: "Pipeline", store: PageImages, seq: int, storing: Any = None):
        self.pipeline, self.store, self.seq = pipeline, store, seq
        self.storing = storing  # the run's lock while it stores (`batch._storing`): held only to ask the cache
        self.frame = store.original(seq)
        self.regions: list[TextRegion] = store.regions(seq) or []
        self.ok = self.frame is not None
        self.drawn: dict[Any, str] = {}  # a lettered region (its index in `regions`) -> the text lettered in it
        self._keys: dict[Any, bytes] = {}  # its `erase_key`, taken on the frame
        self._pixels: dict[int, tuple[Any, np.ndarray]] = {}  # an erased page's pixels, unpacked once for the draft
        if not self.ok:
            return
        assert self.frame is not None
        self.rgb = np.asarray(self.frame.convert("RGB"))
        self.units = fp.analyze(self.rgb, pipeline.settings.margins)
        self.owners = pipeline._owners(self.rgb, self.regions, self.units)
        self.restart()

    def restart(self) -> None:
        """Start again from the page as the cache letters it now (lines of it stored meanwhile), nothing lettered. What
        the cache holds for the page is taken under *storing* (copies), the lettering done without it: the run that
        stores waits for no picture."""
        if not self.ok:
            return
        p = self.pipeline
        held: dict[tuple[Any, str], tuple[CachedPage, int] | None] = {}
        if p.cache is not None:
            with self.storing if self.storing is not None else nullcontext():
                for unit in self.units:
                    hit = p._lookup(unit)
                    held[(tuple(unit.box), unit.fingerprint)] = None if hit is None else (copy.deepcopy(hit[0]), hit[1])
        # (nothing of it stored yet: its frame, as `page_picture` gives it then)
        picture = p.page_picture(self.store, self.seq, lambda unit: held.get((tuple(unit.box), unit.fingerprint))
                                 ) if any(held.values()) else None
        self.start = np.array(picture.convert("RGB")) if picture is not None else self.rgb.copy()
        self.work = self.start.copy()
        self.drawn = {}

    def image(self) -> Image.Image | None:
        """The page as it is lettered now (a picture of its own), None when no image of it is held."""
        return Image.fromarray(self.work.copy()) if self.ok else None

    def _unit(self, scanned: ScannedUnit) -> fp.PageUnit | None:
        """The page unit of the frame that *scanned* was read from (the run read this very frame)."""
        for unit in self.units:
            if tuple(unit.box) == tuple(scanned.box) and unit.fingerprint == scanned.fingerprint:
                return unit
        for unit in self.units:
            if unit.index == scanned.index and fp.hamming(unit.fingerprint, scanned.fingerprint) <= INDEXED_WITHIN:
                return unit
        return None

    def _placed(self, lines: DraftLines) -> list[tuple[Any, TextRegion]]:
        """Every line of *lines* on the region it is lettered in (copies of the run's regions), keyed by the region."""
        p = self.pipeline
        placed: list[tuple[Any, TextRegion]] = []
        for scanned, texts in lines:
            unit = self._unit(scanned)
            regions = scanned.japanese()
            bubbles = [scanned_bubble(scanned, regions[i], text) for i, text in sorted(texts.items())
                       if 0 <= i < len(regions) and text]
            if unit is None or not bubbles:
                continue
            page = CachedPage(fingerprint=scanned.fingerprint, aspect=scanned.aspect, bubbles=bubbles, seq=-1)
            mine = [(n, copy.copy(r)) for n, r in enumerate(self.regions) if self.owners.get(id(r)) is unit]
            index = {id(r): n for n, r in mine}
            for r in p._apply_cached(unit, page, [r for _n, r in mine], self.rgb, p._areas_of(self.units, unit)):
                if r.status == "translated" and r.translated_text:
                    placed.append((index.get(id(r), ("cached", r.bbox)), r))
        return placed

    def letter(self, lines: DraftLines) -> bool:
        """The page with *lines* (all the lines of it not stored yet) lettered: those not lettered yet are erased and
        lettered on the working copy; when one lettered before is gone or reads otherwise, the page is lettered again
        from its start. True when the picture changed."""
        if not self.ok:
            return False
        p = self.pipeline
        placed = self._placed(lines)
        now = {key: r.translated_text for key, r in placed}
        if any(now.get(key) != text for key, text in self.drawn.items()):
            self.work = self.start.copy()
            self.drawn = {}
        new = [(key, r) for key, r in placed if key not in self.drawn]
        if not new:
            return False
        for key, r in new:
            if key not in self._keys:
                self._keys[key] = p.erase_key(self.rgb, r)
        found = self.store.find([self._keys[key] for key, _r in new], self.rgb.shape)
        backgrounds = []
        for n, (_key, r) in enumerate(new):
            hit = found.get(n)
            if hit is not None:  # erased ahead: that erase, as the render takes it
                erased, page = hit
                erased.paste(self.work, self._erased_pixels(page))
                erased.settle(r)
                backgrounds.append(erased.background)
            else:
                backgrounds.append(p._erase(self.work, r, quick=True))
        p.cap_sizes([r for _key, r in placed], [r.translated_text for _key, r in placed])
        pil = Image.fromarray(self.work)
        for (key, r), bg in zip(new, backgrounds):
            p._set_text(pil, r, r.translated_text, bg, r.style)
            self.drawn[key] = r.translated_text
        self.work = np.array(pil)
        return True

    def _erased_pixels(self, page: Callable[[], np.ndarray]) -> np.ndarray:
        """The pixels of the erased page `PageImages.find` gives *page* for, unpacked once while the draft lasts (not
        again for each line); only read from."""
        packed = getattr(page, "packed", None)
        if packed is None:
            return page()
        hit = self._pixels.get(id(packed))
        if hit is None or hit[0] is not packed:
            hit = self._pixels[id(packed)] = (packed, page())
        return hit[1]


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        ocr: OcrEngine | None = None,
        translator: Translator | None = None,
        detector: BubbleDetector | None = None,
        cache: BookCache | None = None,
        annotations: "BookAnnotations | None" = None,
    ):
        self._base_settings = settings
        self._save_errors: dict[str, str] = {}  # store ("cache", "annotations") -> why its last save failed
        self._overrides: dict[str, Any] = {}  # the book's own detection/OCR settings (from its annotations)
        self.annotations: BookAnnotations | None = None  # reader-made premises for the current book
        self.glossary_text: str = ""  # the series sheet (characters, glossary, style), rendered for the prompt
        self.glossary: Glossary | None = None  # the sheet itself, for checking the renderings in translations
        self._detector_given = detector
        self.detector: BubbleDetector = detector or detector_from_settings(settings)
        self.text_detector: TextBlockDetector | None = None
        # what lets go of a GPU model (a detector's or an inpainter's `release`): called before Ollama's model loads
        self.gpu_releases: list[Callable[[], Any]] = []
        # while set, called (it may wait) before LaMa runs on the GPU: the batch's pause while the reader turns pages
        # (`batch.GPU_QUIET_S`); the layout model does not wait (`_detect`)
        self.gpu_gate: Callable[[], None] | None = None
        # the pages the batch erased ahead (`erase_page`), in memory only: `_render` takes a region's erase from there,
        # for a page the viewer shows (what they are kept for after the run, and all: no page is shown from them)
        self.erased_ahead: PageImages | None = None
        # this session's lettered pages from the cache and live erases, in memory only (`render.memo`): a page shown
        # again comes back without detection, erase or typesetting
        self.shown_pages = ShownPages()
        self.erased_regions = ErasedRegions()
        self.stage_times = StageTimes()  # the seconds of each stage on the last pages lettered (Settings > System)
        self.art_eraser: artwork.ArtEraser | None = None
        self.layout: LayoutModel | None = None
        self._warming: threading.Thread | None = None  # `warm_page_models`, while it loads
        self._gpu_released = 0  # how many times `release_gpu_models` let the GPU models go
        self.shaper = Shaper()
        self._models_for: tuple[Any, ...] | None = None  # the settings `art_eraser` and `layout` were made for
        self._build_detectors()
        self.set_annotations(annotations)
        self.ocr = ocr
        self.translator = translator
        if hasattr(translator, "before_load"):
            translator.before_load = self.release_gpu_models
        self.cache = cache
        self._ocr_memo: dict[str, CharspotReading] = {}  # crop hash -> reading, memory only
        self._unanimous_memo: dict[str, bool] = {}  # crop hash and text -> all readers read it (`_unanimous`)
        self._book_sizes: deque[float] = deque(maxlen=400)  # usual-size samples of the pages so far (`_ocr_regions`)
        self._context: deque[list[tuple[str, str]]] = deque(maxlen=max(0, settings.context_pages))
        self.book_names = BookNames()  # the book's names and the renderings they keep (memory only, `premises`)
        self.last_seq: int | None = None

    # ------------------------------------------------------------------
    def _before_gpu(self) -> None:
        """A GPU model is about to run: the gate first, while one is set (`gpu_gate`)."""
        gate = self.gpu_gate
        if gate is not None:
            gate()

    def page_picture(self, store: PageImages, seq: int,
                     lookup: Callable[[fp.PageUnit], tuple[CachedPage, int] | None] | None = None) -> Image.Image | None:
        """The page *seq* of a whole-book run as the cache letters it now, for the run's translation view alone (the
        page being translated, `PageDraft.restart`: the window is shown no other page of the run's memory - reading is
        on the viewer): lettered with the translations the cache holds for it (`translated_page`, on its frame, in
        memory) when it is translated, else its frame as it was captured; never the bare erased page
        (`PageImages.original`). None when no image of it is held. A lettering that fails (the cache being written
        meanwhile) gives the frame. *lookup*: as for `translated_page`."""
        frame = store.original(seq)
        if frame is None:
            return None
        regions = store.regions(seq)
        if regions:
            try:
                lettered = self.translated_page(frame, regions, store, lookup)
            except Exception:  # noqa: BLE001 - the frame, as it was captured, is what is left to show
                lettered = None
            if lettered is not None:
                return lettered
        return frame

    def translated_page(self, frame: Image.Image, regions: Sequence[TextRegion], store: PageImages | None = None,
                        lookup: Callable[[fp.PageUnit], tuple[CachedPage, int] | None] | None = None
                        ) -> Image.Image | None:
        """*frame* lettered with the translations the cache holds for its page units, on *regions* (the run's regions of
        that frame, `PageImages.regions`), as `process` letters a page from the cache: each region's erase taken from
        *store*'s erased page when it holds it, else the paper fill (never LaMa: this is for showing, on the window's
        thread). None when the cache translates none of them. Nothing is stored, nothing of *regions* is changed.
        *lookup*: what the cache holds for a unit, taken beforehand (`PageDraft.restart`: under the run's lock, so
        that the lettering does not hold it); the cache itself (`_lookup`) when None."""
        if self.cache is None or not regions:
            return None
        rgb = np.asarray(frame.convert("RGB"))
        units = fp.analyze(rgb, self.settings.margins)
        if not units:
            return None
        live = [copy.copy(r) for r in regions]
        owners = self._owners(rgb, live, units)
        placed: list[TextRegion] = []
        for unit in units:
            hit = (lookup or self._lookup)(unit)
            if hit is not None:
                placed.extend(self._apply_cached(unit, hit[0], [r for r in live if owners[id(r)] is unit], rgb,
                                                 self._areas_of(units, unit)))
        todo = [r for r in placed if erases(r)]  # (an "erase only" region: erased, nothing set)
        if not todo:
            return None
        out = rgb.copy()
        found = store.find([self.erase_key(rgb, r) for r in todo], rgb.shape) if store is not None else {}
        backgrounds = []
        for i, r in enumerate(todo):
            hit_erased = found.get(i)
            if hit_erased is not None:  # erased ahead: that erase, as the render takes it
                erased, page = hit_erased
                erased.paste(out, page())
                erased.settle(r)
                backgrounds.append(erased.background)
            else:
                backgrounds.append(self._erase(out, r, quick=True))
        lettered = [(r, bg) for r, bg in zip(todo, backgrounds) if r.status != ERASED]
        self.cap_sizes([r for r, _bg in lettered], [r.translated_text for r, _bg in lettered])
        pil = Image.fromarray(out)
        for r, bg in lettered:
            self._set_text(pil, r, r.translated_text, bg, r.style)
        return pil

    def release_page_images(self) -> None:
        """Let go of the last whole-book run's page images (the window closes, another book): pages erase on show."""
        store, self.erased_ahead = self.erased_ahead, None
        if store is not None:
            store.clear()
        self.shown_pages.clear()
        self.erased_regions.clear()

    def warm_page_models(self) -> threading.Thread | None:
        """The layout model and LaMa loaded ahead, on a thread of their own at a lower priority, when the settings in
        force use them (`_build_models`: detect_model "on", or "auto" with the inpainting; art_erase on): the window
        calls it once it is up and a viewer is picked, so that the first page waits for neither (a fresh start's
        first cached page 5.3 s with "auto", 3.3 s without). Nothing is lettered or kept but the models. The first page
        that comes meanwhile waits only for what is still loading (each model's own lock). A release before Ollama's
        load (`release_gpu_models`) that comes meanwhile is done once the model at hand is loaded, and ends the
        warm-up: what is left loads on first use, after Ollama's model, so that the warm-up never takes the GPU memory
        Ollama is loading into. The thread, or None when there is nothing to warm (or it is warming already)."""
        running = self._warming
        if running is not None and running.is_alive():
            return None
        layout, eraser = self.layout, self.art_eraser
        s = self.settings
        if eraser is not None and (eraser.failed or not eraser.ready()):
            eraser = None
        if layout is not None and (getattr(layout, "failed", False)
                                   or (s.detect_model == "auto" and eraser is None)):
            layout = None  # ("auto" only runs it with the inpainting: `_detect`)
        models = [m for m in (layout, eraser) if m is not None and hasattr(m, "warm")]
        if not models:
            return None
        thread = threading.Thread(target=self._warm, args=(models, self._gpu_released), name="taslation-warm-models", daemon=True)
        self._warming = thread
        thread.start()
        return thread

    def _warm(self, models: Sequence[Any], released: int) -> None:
        try:
            from .batch import lower_priority  # (the batch imports the pipeline)

            lower_priority()
        except Exception:  # noqa: BLE001 - only a matter of speed
            pass
        for model in models:
            if self._gpu_released != released:
                return  # Ollama's model is loading: the rest loads on first use, after it
            model.warm()
            if model is not self.layout and model is not self.art_eraser:
                model.release()  # the settings changed meanwhile: this one is not used any more

    def release_gpu_models(self) -> None:
        """Every GPU model of `gpu_releases` lets go (each loads again when it is next needed). One that fails keeps
        neither the others nor the page from going on."""
        self._gpu_released += 1  # (a warm-up under way stops: `_warm`)
        for release in list(self.gpu_releases):
            try:
                release()
            except Exception:  # noqa: BLE001 - it stays in memory, no more than that
                pass

    def set_translator(self, translator: Translator | None) -> None:
        """Translate with *translator* from now on (the window's, when the target language needs another model:
        `taslation.translate.models`): the one before lets its model go (`release_translator`), and the new one lets
        the GPU models go before it loads its own, as the first one did."""
        if translator is self.translator:
            return
        self.release_translator()
        self.translator = translator
        if hasattr(translator, "before_load"):
            translator.before_load = self.release_gpu_models

    def release_translator(self) -> None:
        """The translator's model leaves memory now (`OllamaTranslator.release`), for a translator that has one. Never
        raises: the work it follows is done."""
        release = getattr(self.translator, "release", None)
        if release is not None:
            try:
                release()
            except Exception:  # noqa: BLE001 - Ollama's keep_alive ends it all the same
                pass

    def set_cache(self, cache: BookCache | None) -> None:
        self.cache = cache
        self.last_seq = None
        self._book_sizes.clear()
        self._save_errors.pop("cache", None)

    @property
    def pages_not_saved(self) -> str:
        """Why the last save of the translation cache failed ("": it went well). What was not written stays in
        memory, and the next save that works writes it."""
        return self._save_errors.get("cache", "")

    @property
    def save_error(self) -> str:
        """Why the last save of the cache, or of the book's annotations, failed ("": all is written). The operating
        system's words for it (no space left, permission denied), no path and nothing of the book."""
        return self.pages_not_saved or self._save_errors.get("annotations", "")

    def _save_store(self, name: str, store: Any) -> bool:
        """*store*.save(); a failure (a full disk, a locked file) is no reason to lose the page at hand, so it does
        not raise: it is kept in `save_error` for the window and the batch to say, until a save of *name* works."""
        try:
            store.save()
        except OSError as e:
            self._save_errors[name] = str(e.strerror or type(e).__name__)
            return False
        self._save_errors.pop(name, None)
        return True

    @property
    def settings(self) -> Settings:
        """The settings in force: the reader's, with the current book's own detection/OCR values on top."""
        base = self._base_settings
        return base.with_overrides(**self._overrides) if self._overrides else base

    def set_margins(self, margins: Sequence[int]) -> None:
        """The capture area read from here on (left, top, right, bottom): the margins of the settings the pipeline was
        given - in the window, the window's own, which it shows the page by. A whole-book run that follows the reader
        widens it as the pages come, between two pages it reads and never during one (`batch.BatchReader._read_in`):
        each step of a page's reading takes the margins afresh."""
        self._base_settings.margins = tuple(int(m) for m in margins)  # type: ignore[assignment]

    def _build_detectors(self) -> None:
        s = self.settings
        self.detector = self._detector_given or detector_from_settings(s)
        self.text_detector = (
            TextBlockDetector(TextBlockConfig(white_threshold=s.white_threshold, dark_threshold=s.dark_threshold))
            if s.detect_text_blocks else None
        )
        self.shaper = Shaper(s.white_threshold, s.dark_threshold)
        self._build_models()

    def _build_models(self) -> None:
        """The layout model and the erase on the art, as the settings in force ask and as far as they are installed;
        nothing is loaded here. The erase follows `artwork.available` (its rule, `artwork.runs_here`: art_erase "auto"
        only where torch has a CUDA GPU, "lama" on the CPU too). The layout model finds more on the art than the
        classical detectors do, and the paper fill damages the art there, so on "auto" it only comes with the
        inpainting: on a computer without a GPU, "auto" and "auto" use neither."""
        s = self.settings
        key = (str(s.models_dir), s.erase_mode, s.art_erase, s.detect_model)
        if key == self._models_for:
            return
        self._models_for = key
        for old in (self.layout, self.art_eraser):  # models made for other settings: let go, and out of the list
            if old is not None:
                old.release()
                self.gpu_releases[:] = [f for f in self.gpu_releases if getattr(f, "__self__", None) is not old]
        self.art_eraser = (artwork.ArtEraser(s.models_dir, s.art_erase, self._paper_erase)
                           if s.erase_mode == "fill" and artwork.available(s.models_dir, s.art_erase) else None)
        if self.art_eraser is not None:
            self.art_eraser.before_gpu = self._before_gpu
        wanted = s.detect_model == "on" or (s.detect_model == "auto" and self.art_eraser is not None)
        self.layout = (LayoutModel(s.models_dir)
                       if wanted and self._detector_given is None and layout_model.available(s.models_dir) else None)
        self.gpu_releases.extend(m.release for m in (self.layout, self.art_eraser) if m is not None)

    def set_annotations(self, annotations: "BookAnnotations | None") -> None:
        self.annotations = annotations
        self._save_errors.pop("annotations", None)
        self._overrides = clean_book_settings(annotations.settings) if annotations is not None else {}
        self._build_detectors()

    def set_book_settings(self, overrides: dict[str, Any] | None) -> dict[str, Any]:
        """Detection/OCR settings for the current book (kept with its annotations)."""
        if self.annotations is None:
            return {}
        applied = self.annotations.set_settings(overrides)
        self.save_annotations()
        self._overrides = dict(applied)
        self._build_detectors()
        return applied

    def save_annotations(self) -> None:
        if self.annotations is not None:
            self._save_store("annotations", self.annotations)

    @property
    def rtl(self) -> bool:
        return self.annotations.rtl if self.annotations is not None else True

    def check_sheet(self) -> Glossary | None:
        """The sheet translations are checked against: the reader's series sheet (None when there is none)."""
        return self.glossary

    def real_translation(self, source: str, output: str) -> bool:
        """`is_real_translation` for the book at hand: the sheet is looked at only for a reply that would fail."""
        language = self.settings.target_language
        return is_real_translation(source, output, language) or is_real_translation(source, output, language,
                                                                                     self.check_sheet())

    def premises(self) -> str:
        """What the model is told before translating: the reader's series sheet as text, carrying the sheet itself
        (`annotations.Premises`: the PLaMo translator takes its glossary from it, the chat prompt the entries the text
        was cut short of) and the book's names held so far (`renderings.NamedPremises`), which the translators add
        to each line's glossary and learn from."""
        return NamedPremises(join_premises("", self.glossary_text), self.check_sheet(), self.book_names)

    def reset_context(self) -> None:
        """Another book, or its translations forgotten: the earlier pages' pairs and the names held go."""
        self._context.clear()
        self.book_names.clear()

    def context_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for page in self._context:
            pairs.extend(page)
        return pairs[-40:]

    @property
    def font_path(self) -> str | None:
        """Font used for Latin text (informational)."""
        return self.font_for().path

    @property
    def suggested_font(self) -> str:
        """The lettering font the series sheet suggests (a family name), or ""."""
        return self.glossary.style.font if self.glossary is not None else ""

    def font_for(self, text: str = "") -> FontSpec:
        """The font *text* is set in: the series sheet's suggestion where it is installed and has the glyphs,
        else the reader's font file, else the automatic choice for the text's script."""
        s = self.settings
        return find_font(s.font_path, s.fonts_dir, text, s.target_language, self.suggested_font)

    def lettering_for(self, text: str = "", kind: str = "") -> Lettering:
        """How a region's text is set: the font the sheet names for its *kind* (the reader's thought, shout,
        narration, handwritten or sfx), else the sheet's lettering font, where installed and covering *text*;
        with the kind's italic and bold (thoughts italic, shouts heavier unless the sheet says otherwise)."""
        s = self.settings
        style = self.glossary.style if self.glossary is not None else StyleGuide()
        ls = style.lettering_for(kind)
        spec = find_font(s.font_path, s.fonts_dir, text, s.target_language, (ls.font, style.font))
        return make_lettering(spec, str(s.fonts_dir), ls.italic, ls.bold)

    def kind_lettering(self, kind: str = "") -> LetteringStyle:
        """What the series sheet says of the lettering of *kind* (`StyleGuide.lettering_for`: its font, faces and
        ink), a copy; the built-in default without a sheet."""
        return (self.glossary.style if self.glossary is not None else StyleGuide()).lettering_for(kind)

    def font_status(self) -> tuple[str, str | None]:
        """(the font the series sheet suggests, the installed file it resolves to, or None when this computer
        lacks it); ("", None) when the sheet suggests none."""
        name = self.suggested_font
        if not name:
            return "", None
        return name, resolve_font(name, self.settings.fonts_dir).path

    # ------------------------------------------------------------------ live
    def process(self, image: Image.Image, *, use_cache: bool = True, translate: bool = True,
                progress: ProgressFn | None = None, complete: bool = False,
                events: EventFn | None = None, cancel: threading.Event | None = None,
                on_slow: SlowFn | None = None) -> PageResult:
        """Translate one capture. Every text region found goes to a page unit (`unit_for`), a region below or beside
        a unit that stops short of its page too; only what lies outside the capture area is left out. With
        *complete* (translator mode), a cached page is also completed: live text regions the cache has no bubble
        for are read, translated and added to it; so is a cached page marked `CachedPage.incomplete`, in any mode and
        at each reading until the translation that is missing comes. What was translated is kept whatever else failed,
        the entry marked while a bubble lacks a translation. With *events*, the page is told as it fills in
        (`PageFill`): the regions to read once they are found, each one read, each one lettered as its translation
        arrives (while the model is still writing, with a translator that hands its translations over one by one),
        and the finished page last; a page from the cache gets only the finished page.

        *progress* gets the stages as Messages (see the module's docstring). Once *cancel* is set, `Cancelled` is
        raised: between regions while reading, before and during the request to the model, before rendering; a
        page cancelled before its translation came back leaves nothing in the cache. *on_slow*(seconds) is called
        (once per request) when the model has said nothing for a while, with a translator that can tell (it takes
        an ``on_slow`` argument)."""
        s = self.settings
        timer = _Timer()
        report = progress or (lambda _msg: None)
        original = image.convert("RGB")
        rgb = np.asarray(original)
        result = PageResult(image=original, original=original, regions=[])
        fill = PageFill(self, rgb, events) if events is not None else None

        units = fp.analyze(rgb, s.margins)
        result.fingerprints = [u.fingerprint for u in units]
        result.units = list(units)
        timer.lap("fingerprint")
        if not units:
            result.notes.append("no page content found in the capture")
            result.timings = timer.timings
            if fill is not None:
                fill.finish(result.image)
            return result

        shown_key = self._shown_key(rgb, units, translate, complete) if use_cache and self.cache is not None else None
        if shown_key is not None:
            got = self.shown_pages.get(shown_key)
            if got is not None:  # shown before this session, from the very pixels: its lettering laid over them
                regions, shown = got
                result.image = Image.fromarray(shown.lay_over(rgb))
                result.regions = regions
                result.notes.extend(shown.notes)
                result.cache_hits = len(units)
                if shown.seq is not None:
                    self.last_seq = shown.seq
                timer.lap("shown before")
                result.timings = timer.timings
                if fill is not None:
                    fill.finish(result.image)
                return result
        check_cancel(cancel)
        report(Message("pipeline.stage_finding"))
        _ON_SHOW.units, _ON_SHOW.rgb = units, rgb  # (`_detect`: a page on show, its units known)
        try:
            regions = self._annotate(rgb, self._detect(rgb), units)
        finally:
            _ON_SHOW.units = _ON_SHOW.rgb = None
        timer.lap("detect")

        # every unit's regions in reading order and its cache entry first, so that the regions to read are known
        # (and can be shown) before the first of them is read
        owners = self._owners(rgb, regions, units)
        before = _units_before(rgb, s.margins)

        def completes(page: CachedPage) -> bool:
            """This reading adds what the cached *page* lacks: in translator mode, and a page marked as lacking it."""
            return translate and (complete or (page.incomplete and self.translator is not None))

        plans: list[tuple[fp.PageUnit, list[TextRegion], CachedPage | None]] = []
        for unit in units:
            unit_regions = [r for r in regions if owners[id(r)] is unit]
            unit_regions = apply_order_hints(order_on_page(rgb, unit.box, unit_regions, self.rtl))
            for r in unit_regions:
                r.unit = unit.index
            page: CachedPage | None = None
            cached = self._lookup(unit, before) if use_cache and self.cache is not None else None
            if cached is not None:
                page, distance = cached
                self.last_seq = page.seq
                unit_regions = self._apply_cached(unit, page, unit_regions, rgb, self._areas_of(units, unit))
                result.cache_hits += 1
                result.notes.append(f"unit {unit.index}: cache hit (seq {page.seq}, distance {distance})")
            else:
                result.cache_misses += 1
            plans.append((unit, unit_regions, page))
        if fill is not None:
            fill.announce([r for _unit, unit_regions, page in plans for r in unit_regions
                           if page is None or (completes(page) and r.status == "unmatched")])

        out = rgb.copy()
        all_regions: list[TextRegion] = []
        for unit, unit_regions, page in plans:
            if page is not None:
                if completes(page):
                    err = self._complete_page(rgb, unit, page, unit_regions, report, fill, cancel, on_slow)
                    if err:
                        result.error = err
            elif unit_regions:
                self._ocr_regions(rgb, unit_regions, report, fill, cancel, unit_box=unit.box)
                self._order_read(rgb, unit.box, unit_regions)
                timer.lap("ocr")
                if translate:
                    err = self._translate_regions(unit_regions, report, fill, cancel, on_slow, unit.box)
                    timer.lap("translate")
                    if err:
                        result.error = err
                    if use_cache and self.cache is not None and self._cacheable(unit_regions):
                        self._store_regions(unit, unit_regions)
            all_regions.extend(unit_regions)

        for i, r in enumerate(all_regions):
            r.order = i
        check_cancel(cancel)
        report(Message("pipeline.stage_rendering"))
        if fill is not None and not fill.regions and self._erases_on_art(out, all_regions):
            self._early_look(rgb, all_regions, fill)  # a page from the cache: lettered at once, the art filled in after
            timer.lap("early look")
        self._render(out, all_regions)
        timer.lap("render")

        result.image = Image.fromarray(out)
        result.regions = all_regions
        result.timings = timer.timings
        self.stage_times.add(timer.timings)
        if shown_key is not None and not result.error:
            self.shown_pages.put(shown_key, rgb, out, all_regions, result.notes, self.last_seq)
        if fill is not None:
            fill.finish(result.image)
        return result

    def _shown_key(self, rgb: np.ndarray, units: Sequence[fp.PageUnit], translate: bool,
                   complete: bool) -> bytes | None:
        """The key of this capture's lettering in `shown_pages`: the digest of its pixels in the capture area and the
        signature of all the lettering is made from besides them - every unit's cache entry (its translations, notes,
        flags, boxes and shapes) and the reader's annotations of it (the areas ignored on every page that apply to it
        among them), the settings in force, the series sheet's lettering, the reading direction, which models erase
        and detect. None (the page is lettered from scratch, and not kept) when a unit is not in the cache, or the
        reading adds to a cached page (`process`'s *complete*, a page marked incomplete with a translator). Any change
        of these, or of one pixel, is another key: a page whose translation changed never comes back with the old
        text."""
        assert self.cache is not None
        s = self.settings
        seq = self.last_seq
        parts: list[Any] = []
        for unit in units:
            hit = self.cache.lookup(unit.fingerprint, unit.aspect, s.fingerprint_max_distance, seq)
            if hit is None:
                return None
            page, distance = hit
            if translate and (complete or (page.incomplete and self.translator is not None)):
                return None
            seq = page.seq
            notes = (self.annotations.lookup(unit.fingerprint, unit.aspect, s.fingerprint_max_distance)
                     if self.annotations is not None else None)
            parts.append((unit.index, unit.box, unit.fingerprint, distance, page, notes, self._areas_of(units, unit)))
        eraser, layout = self.art_eraser, self.layout
        sheet = self.glossary.style if self.glossary is not None else None
        sig = signature(parts, s, sheet, self.rtl, layout is not None and not getattr(layout, "failed", False),
                        (eraser.setting, eraser.failed) if eraser is not None else None, self._detector_given is None)
        return pixels_digest(rgb, self._capture(rgb)) + sig

    def _erases_on_art(self, page: np.ndarray, regions: Sequence[TextRegion]) -> bool:
        """Whether rendering *regions* on *page* (untouched) takes the inpainting model for one of them: a region
        on the art that neither the erased pages of a run nor this session's erases hold."""
        eraser = self.art_eraser
        if eraser is None or eraser.failed:
            return False
        todo = [r for r in regions if erases(r)]
        if not todo:
            return False
        keys = [self.erase_key(page, r) for r in todo]
        store = self.erased_ahead
        held = set(store.find(keys, page.shape)) if store is not None else set()
        return any(i not in held and not self.erased_regions.has(k) and artwork.on_art(page, r)
                   for i, (k, r) in enumerate(zip(keys, todo)))

    def _early_look(self, rgb: np.ndarray, regions: Sequence[TextRegion], fill: "PageFill") -> None:
        """The page lettered with the paper fill where the inpainting model will fill in the art, sent as an early
        ``page`` (`PageFill`): a page from the cache shows at once, the finished page follows. Made on copies of
        *regions*: nothing of them changes. A failure costs only the early look."""
        try:
            quick = rgb.copy()
            self._render(quick, copy.deepcopy(list(regions)), quick=True)
            h, w = rgb.shape[:2]
            fill.emit("regions", {"boxes": [], "size": (w, h)})
            fill.emit("page", {"image": Image.fromarray(quick), "early": True})
        except Cancelled:
            raise
        except Exception:  # noqa: BLE001 - the finished page is rendered on its own
            pass

    # ------------------------------------------------------------------ batch
    def scan(self, image: Image.Image, *, skip_cached: bool = True, progress: ProgressFn | None = None,
             fresh: bool = False, cancel: threading.Event | None = None,
             events: EventFn | None = None, keep_regions: bool = False) -> PageScan:
        """Detect and read a page; keep text and geometry only (the image is not retained). Once *cancel* is set,
        `Cancelled` is raised between regions.

        A page that is already in the cache is re-synchronised with the current
        detection: cached bubbles that no text region corresponds to any more are
        dropped (they were false detections of an earlier run), text regions the
        cache does not have yet are returned for translation, and the rest is kept
        with its translation.

        With *events*, the page is told as it fills in (`PageFill`): the regions of the units to translate once they
        are found, and each one read; a page from the cache announces nothing.

        With *keep_regions*, the scan's ``erasable`` holds the regions the render will erase once the page is
        translated, as the render will see them: the detection's regions as they were before the reading (a page from
        the cache is rendered without one), with the shape a model region takes (`take_shape`, as `_apply_cached`
        gives it), of those read as Japanese and those the reader made "erase only", in reading order (`erase_page`
        erases them ahead).
        """
        s = self.settings
        report = progress or (lambda _msg: None)
        rgb = np.asarray(image.convert("RGB"))
        scan = PageScan(width=rgb.shape[1], height=rgb.shape[0])
        fill = PageFill(self, rgb, events) if events is not None else None
        units = fp.analyze(rgb, s.margins)
        if not units:
            return scan
        report(Message("pipeline.stage_finding"))
        regions = self._annotate(rgb, self._detect(rgb), units)
        owners = self._owners(rgb, regions, units)
        before = _units_before(rgb, s.margins)
        if self.annotations is not None:
            for unit in units:
                self.annotations.record_sequence(unit.fingerprint, unit.aspect)
        plans: list[tuple[fp.PageUnit, list[TextRegion], tuple[CachedPage, int] | None]] = []
        for unit in units:
            hit = None
            if (skip_cached or fresh) and self.cache is not None:
                hit = self._lookup(unit, before)
            plans.append((unit, apply_order_hints(
                order_on_page(rgb, unit.box, [r for r in regions if owners[id(r)] is unit], self.rtl)), hit))
        if fill is not None:
            fill.announce([r for _unit, unit_regions, hit in plans if hit is None or fresh for r in unit_regions])
        unread = {id(r): copy.copy(r) for _unit, unit_regions, _hit in plans for r in unit_regions} if keep_regions else {}
        for unit, unit_regions, hit in plans:
            su = ScannedUnit(index=unit.index, box=unit.box, fingerprint=unit.fingerprint, aspect=unit.aspect)
            left_out = (self._ocr_regions(rgb, unit_regions, report, fill, cancel, unit_box=unit.box)
                        if unit_regions else [])
            self._order_read(rgb, unit.box, unit_regions)
            for r in unit_regions:
                if keep_regions and (r.status == "untranslated" and r.source_text or r.status == ERASED) \
                        and id(r) in unread:
                    seen = unread[id(r)]
                    take_shape(seen)
                    seen.panel = r.panel  # (found after the reading, `_order_read`)
                    scan.erasable.append(seen)
            stands_for: dict[int, list[Box]] = {}  # a region's id -> the boxes of the regions it repeated
            for gone in left_out or []:
                stands_for.setdefault(id(gone.repeats), []).append(gone.bbox)
            scanned = [ScannedRegion(bbox=r.bbox, text_box=r.letter_box or r.text_box, poly=mask_polygon(r.mask),
                                     source_text=r.source_text, status=r.status, order=r.order,
                                     kind=r.kind, ocr_confidence=r.ocr_confidence, pieces=r.pieces,
                                     speaker=r.speaker, tag=r.tag, continues=r.continues, remark=r.remark,
                                     room=translation_room(r.mask, r.letter_box or r.text_box, r.source_text,
                                                           self.settings, r.kind, r.x0, r.y0, self.suggested_font,
                                                           direction_of(r))
                                     if r.status == "untranslated" else 0,
                                     aliases=tuple(stands_for.get(id(r), ())), angle=r.angle)
                       for r in unit_regions]
            if fill is not None:
                for r, kept in zip(unit_regions, scanned):
                    fill.link(kept, r)
            if hit is None:
                su.regions = scanned
                scan.units.append(su)
                continue
            page, _distance = hit
            su.stored_fingerprint = page.fingerprint
            if fresh:
                # translate everything again; the page's entry is replaced (never duplicated) when the new one is saved
                su.regions = scanned
                su.kept = self._bubbles_held(unit, page.bubbles, scanned)  # nothing to translate them from
                held_ids = {id(cb) for cb in su.kept}
                su.kept.extend(self._kept_in_areas(units, unit, [cb for cb in page.bubbles if id(cb) not in held_ids]))
                if not su.japanese() and page.bubbles:
                    self._save_page(page.fingerprint, unit.aspect, su.kept)  # no text on this page any more
                scan.units.append(su)
                continue
            japanese = [r for r in scanned if r.is_japanese]
            matched: set[int] = set()
            scores = bubble_scores([[unit.normalize(b) for b in (r.bbox, *r.aliases)] for r in japanese],
                                   [cb.box for cb in page.bubbles], s.match_min_iou)
            for j, cb in enumerate(page.bubbles):
                best_i, best_iou = -1, 0.0
                for i, r in enumerate(japanese):
                    if i in matched:
                        continue
                    score = scores[i][j]
                    if score > best_iou:
                        best_i, best_iou = i, score
                if best_i >= 0 and best_iou > 0:
                    matched.add(best_i)
                    su.kept.append(cb)
            answered = {id(cb) for cb in su.kept}
            left = [cb for cb in page.bubbles if id(cb) not in answered]
            held = self._bubbles_held(unit, left, scanned)
            held_ids = {id(cb) for cb in held}
            held.extend(self._kept_in_areas(units, unit, [cb for cb in left if id(cb) not in held_ids]))
            su.kept.extend(held)
            su.dropped = len(left) - len(held)
            su.regions = [r for i, r in enumerate(japanese) if i not in matched]
            su.cached = not su.regions
            if su.cached and (su.dropped or page.incomplete):
                self._save_page(page.fingerprint, unit.aspect, su.kept)  # prune now; nothing to translate
            scan.units.append(su)
        return scan

    def _kept_in_areas(self, units: Sequence[fp.PageUnit], unit: fp.PageUnit,
                       bubbles: Sequence[CachedBubble]) -> list[CachedBubble]:
        """Those of *bubbles* (cached, no region found for them) that lie mostly inside an area ignored on every page
        (`_areas_of`): not stale - the area hides them (`_apply_cached` draws none) and kept in the cache, so that the
        area taken back brings their translations back."""
        areas = self._areas_of(units, unit)
        return [cb for cb in bubbles if areas and any(a.holds(cb.box) for a in areas)]

    def _bubbles_held(self, unit: fp.PageUnit, bubbles: Sequence[CachedBubble],
                      scanned: Sequence[ScannedRegion]) -> list[CachedBubble]:
        """Those of *bubbles* a scanned region that is not text to translate lies on (`match_min_iou`), each region
        taking one: a translation typed in the reader's own region the OCR reads nothing in, or one of a region a gate
        turns down this time (`usual_size` hangs on the sizes of the book so far). It stands: what a gate says of a
        reading is no word on a stored translation, and without a Japanese text no pass can make it again. A region
        lies on a bubble by its box or a box it stands for (`bubble_scores`: a page stored with the layout model's boxes
        and read now without it, or the other way round, loses nothing). Only a bubble no region of the page
        corresponds to at all is stale."""
        s = self.settings
        others = [r for r in scanned if not r.is_japanese]
        scores = bubble_scores([[unit.normalize(b) for b in (r.bbox, *r.aliases)] for r in others],
                               [cb.box for cb in bubbles], s.match_min_iou)
        held: list[CachedBubble] = []
        taken: set[int] = set()
        for j, cb in enumerate(bubbles):
            best, best_iou = -1, 0.0
            for i in range(len(others)):
                if i not in taken and scores[i][j] > best_iou:
                    best, best_iou = i, scores[i][j]
            if best >= 0:
                taken.add(best)
                held.append(cb)
        return held

    def _lookup(self, unit: fp.PageUnit,
                before: Callable[[], list[fp.PageUnit]] | None = None) -> tuple[CachedPage, int] | None:
        """Find the unit's page in the cache; on a miss, pick up pages another process (a batch run) saved meanwhile,
        then look for the page as a cache kept before 2026-10-31 holds it (*before*: the capture's units as analyze
        found them then, `_units_before`; `_lookup_before`)."""
        assert self.cache is not None
        s = self.settings
        hit = self.cache.lookup(unit.fingerprint, unit.aspect, s.fingerprint_max_distance, self.last_seq)
        if hit is None and self.cache.refresh():
            hit = self.cache.lookup(unit.fingerprint, unit.aspect, s.fingerprint_max_distance, self.last_seq)
        if hit is None and before is not None:
            hit = self._lookup_before(unit, before())
        return hit

    def _lookup_before(self, unit: fp.PageUnit, before: list[fp.PageUnit]) -> tuple[CachedPage, int] | None:
        """The unit's page in a cache kept before 2026-10-31, when the paper on a dark viewer was the large blobs
        alone (`fingerprint.analyze(grow=False)`): a page whose black panels the paper now grows through has another
        unit, and another fingerprint, than the cache kept for it. Each unit of *before* that lies in this one
        (`_inside_unit`) and has another fingerprint is looked for within INDEXED_WITHIN bits (the distance at which
        a page replaces another: at the window size it was read at, the unit as found then gives the very
        fingerprint kept, and two different pages come no closer than some 20 bits). The pages found are re-keyed:
        their bubbles moved from the old unit's box to this unit's (both in this capture), under this unit's
        fingerprint, with the first one's sequence number, in place of the old entries (`BookCache.remove`, which
        a merging save keeps), and saved; from then on the page is found as any other. None when nothing is found."""
        assert self.cache is not None
        found: list[tuple[CachedPage, int, fp.PageUnit]] = []
        for old in before:
            if not _inside_unit(old.box, unit.box) or fp.hamming(old.fingerprint, unit.fingerprint) <= INDEXED_WITHIN:
                continue
            hit = self.cache.lookup(old.fingerprint, old.aspect, INDEXED_WITHIN, self.last_seq)
            if hit is not None and all(hit[0] is not page for page, _d, _old in found):
                found.append((hit[0], hit[1], old))
        if not found:
            return None
        bubbles = [_moved(b, old.box, unit.box) for page, _d, old in found for b in page.bubbles]
        rekeyed = CachedPage(fingerprint=unit.fingerprint, aspect=unit.aspect, bubbles=bubbles,
                             seq=min(page.seq for page, _d, _old in found),
                             incomplete=any(page.incomplete for page, _d, _old in found))
        for page, _d, _old in found:
            self.cache.remove(page.fingerprint)
        rekeyed = self.cache.add(rekeyed)
        self._save_store("cache", self.cache)  # (a failure: kept in memory; saved with the next save)
        return rekeyed, min(d for _page, d, _old in found)

    def _save_page(self, fingerprint: str, aspect: float, bubbles: list[CachedBubble], incomplete: bool = False) -> None:
        """Store a page under *fingerprint*: the entry it matched when it is already cached (so that entry is
        replaced, never duplicated), otherwise the live one; *incomplete*: it lacks a translation
        (`CachedPage.incomplete`)."""
        assert self.cache is not None
        page = self.cache.add(CachedPage(fingerprint=fingerprint, aspect=aspect, bubbles=list(bubbles), seq=-1,
                                         incomplete=incomplete))
        self.last_seq = page.seq
        self._save_store("cache", self.cache)

    def commit_unit(self, unit: ScannedUnit, translations: dict[int, str],
                    flags: dict[int, list[str]] | None = None) -> bool:
        """Store translations (keyed by region index, with their review flags) for a scanned page unit. What is
        translated is always kept: whatever the unit has is stored, seen before or not, and a region without a
        translation stays untranslated. Only what `is_real_translation` accepts becomes a bubble. Returns True if
        complete: every region has its bubble; else the entry is marked `CachedPage.incomplete`, and the next reading
        or whole-book run asks for the rest."""
        if self.cache is None:
            return False
        new: list[CachedBubble] = []
        complete = True
        for i, r in enumerate(unit.japanese()):
            text = (translations.get(i) or "").strip()
            if text and self.real_translation(r.source_text, text):
                new.append(scanned_bubble(unit, r, text, (flags or {}).get(i, [])))
            else:
                complete = False  # that bubble stays untranslated; the next reading or run picks it up
        bubbles = list(unit.kept) + new
        if bubbles:
            self._save_page(unit.stored_fingerprint or unit.fingerprint, unit.aspect, bubbles, incomplete=not complete)
        return complete

    # ------------------------------------------------------------------ stages
    def _capture(self, rgb: np.ndarray) -> Box:
        """The capture area of *rgb*: what the margins leave of it, where text is looked for."""
        return fp.capture_area(rgb.shape[1], rgb.shape[0], self.settings.margins)

    def _owners(self, rgb: np.ndarray, regions: Sequence[TextRegion],
                units: Sequence[fp.PageUnit]) -> dict[int, fp.PageUnit | None]:
        """The page unit each region (by id) belongs to (`unit_for`): None only outside the capture area."""
        capture = self._capture(rgb)
        return {id(r): unit_for(units, r.bbox, capture, stored_unit(r)) for r in regions}

    def _detect(self, rgb: np.ndarray, units: Sequence[fp.PageUnit] | None = None,
                parallel: bool = False) -> list[TextRegion]:
        """The regions of the page: the layout model's first, each with the classical shape it takes once read, then
        the classical detectors'. Those alone when the model cannot be used, or the erase it needs cannot. *units*:
        the page units of *rgb* (`fingerprint.analyze`, found again when not given). With *parallel* (a page on show:
        `process` says so for its capture on this thread, with its units) the classical detectors run beside the
        layout model, in a worker thread of their own."""
        if getattr(_ON_SHOW, "rgb", None) is rgb:
            parallel = True
            units = units if units is not None else _ON_SHOW.units
        s = self.settings
        layout, eraser = self.layout, self.art_eraser  # (the window may build others meanwhile)
        if layout is None or (s.detect_model == "auto" and not (eraser is not None and eraser.ready())):
            return self._detect_classical(rgb)
        beside = _detect_pool().submit(self._detect_classical, rgb) if parallel else None
        try:
            # (no `gpu_gate` here: the layout model's 0.3 s a page on the GPU leaves a viewer's drawing alone, measured
            # in Chrome while the pages are turned, and waiting for it held every page's reading back until the reader
            # stopped turning; only LaMa waits)
            found = layout.boxes(rgb, [u.box for u in (units if units is not None else fp.analyze(rgb, s.margins))])
        finally:
            classical = beside.result() if beside is not None else None  # (waited for whatever happened)
        if classical is None:
            classical = self._detect_classical(rgb)
        if found is None:
            return classical
        model = model_regions(rgb, found)
        for r in model:
            r.after = self.shaper.rebuilt(rgb, r, classical)
        claimed = Counter(id(r.after.adopted) for r in model if r.after.adopted is not None)
        for r in model:  # a classical region two model regions claim joined two bubbles: neither takes its shape
            if r.after.adopted is not None and claimed[id(r.after.adopted)] > 1:
                r.after = self.shaper.rebuilt(rgb, r, ())
        return [*model, *classical]

    def _detect_classical(self, rgb: np.ndarray) -> list[TextRegion]:
        x0, y0, x1, y1 = self._capture(rgb)
        sub = rgb[y0:y1, x0:x1]
        gray = cv2.cvtColor(sub, cv2.COLOR_RGB2GRAY)
        dark = self.detector.cfg.dark_threshold
        regions = drop_nested(focus_oversized(self.detector.detect(sub)), gray, dark)
        if self.settings.detect_dark_bubbles:
            regions = merge_regions(regions, drop_nested(focus_oversized(self.detector.detect(sub, inverted=True)),
                                                         255 - gray, dark))
        if self.text_detector is not None:
            # text blocks are looked for outside the lettering of the bubbles (regions closed by an outline)
            bubbles = [r for r in regions if r.kind in ("bubble", "dark-bubble")]
            regions = merge_regions(regions, self.text_detector.detect(sub, taken=bubbles))
            if self.settings.detect_dark_bubbles:
                regions = merge_regions(regions, self.text_detector.detect(sub, inverted=True, taken=bubbles))
        if x0 or y0:
            for r in regions:
                r.x0 += x0
                r.x1 += x0
                r.y0 += y0
                r.y1 += y0
                tb = r.text_box
                r.text_box = (tb[0] + x0, tb[1] + y0, tb[2] + x0, tb[3] + y0)
                if r.core_box is not None:
                    cb = r.core_box
                    r.core_box = (cb[0] + x0, cb[1] + y0, cb[2] + x0, cb[3] + y0)
                if r.letter_box is not None:
                    lb = r.letter_box
                    r.letter_box = (lb[0] + x0, lb[1] + y0, lb[2] + x0, lb[3] + y0)
        return regions

    def _areas_of(self, units: Sequence[fp.PageUnit], unit: fp.PageUnit) -> list[BookArea]:
        """The areas the reader ignores on every page of the book (`annotations.BookArea`) that apply to *unit* of a
        capture of *units*: those of its side of a two-page spread (`page_side`) and of its shape."""
        if self.annotations is None or not self.annotations.areas:
            return []
        return self.annotations.areas_for(page_side(unit.index, len(units)), unit.aspect)

    def _annotate(self, rgb: np.ndarray, regions: list[TextRegion], units: list[fp.PageUnit]) -> list[TextRegion]:
        """Apply the reader's rectangles: drop detections mostly inside an area ignored on every page of the book
        (`BookArea.holds`, in the terms of the region's page unit) and inside an "ignore" box of the page, add a region
        for every "add" box (it belongs to the page unit it was stored under, wherever that unit's box now ends; an
        area leaves it alone). A page on show and the whole-book run's scan both come this way."""
        if self.annotations is None:
            return regions
        s = self.settings
        h, w = rgb.shape[:2]
        capture = self._capture(rgb)
        out = list(regions)
        if self.annotations.areas:
            def in_area(r: TextRegion) -> bool:
                unit = unit_for(units, r.bbox, capture, stored_unit(r))
                return unit is not None and any(a.holds(unit.normalize(r.bbox)) for a in self._areas_of(units, unit))

            out = [r for r in out if not in_area(r)]
        for unit in units:
            page = self.annotations.lookup(unit.fingerprint, unit.aspect, s.fingerprint_max_distance)
            if page is None:
                continue
            if page.skip:
                out = [r for r in out if unit_for(units, r.bbox, capture, stored_unit(r)) is not unit]
                continue
            for nbox in page.ignore:
                box = unit.denormalize(nbox)
                out = [r for r in out if not _inside(box, _center(r.text_box))]
            for nbox in page.add:
                bx0, by0, bx1, by1 = unit.denormalize(nbox)
                box = (max(0, bx0), max(0, by0), min(w, bx1), min(h, by1))
                if box[2] - box[0] < 6 or box[3] - box[1] < 6:
                    continue
                out = [r for r in out if box_iou(r.bbox, box) < 0.3 and not _inside(box, _center(r.text_box))]
                region = manual_region(rgb, box, s.dark_threshold)
                region.unit = unit.index
                out.append(region)
            if not page.notes and not page.order:
                continue
            for r in out:
                if unit_for(units, r.bbox, capture, stored_unit(r)) is not unit:
                    continue
                nb = unit.normalize(r.bbox)
                note = page.note_at(nb, s.match_min_iou) if page.notes else None
                if note is not None:
                    r.speaker, r.tag, r.continues, r.remark = note.speaker, note.kind, note.continues, note.note
                    r.style = None if note.style.is_empty else note.style
                if page.order:
                    best = max(range(len(page.order)), key=lambda i: box_iou(page.order[i], nb))  # type: ignore[arg-type]
                    if box_iou(page.order[best], nb) >= s.match_min_iou:  # type: ignore[arg-type]
                        r.order_hint = best
        return out

    def _complete_page(self, rgb: np.ndarray, unit: fp.PageUnit, page: CachedPage, regions: list[TextRegion],
                       report: ProgressFn, fill: PageFill | None = None, cancel: threading.Event | None = None,
                       on_slow: SlowFn | None = None) -> str:
        """Translator mode, and a page marked `CachedPage.incomplete`: read and translate the live regions a cached
        page has no bubble for, and add what the model gave, also when it failed for the others. The mark goes once
        no text is left without a translation, and comes when one is; a reading that added nothing to a marked page
        leaves it as it was. Returns "" or the Message of what went wrong."""
        todo = [r for r in regions if r.status == "unmatched"]
        err: str = ""
        if todo:
            self._ocr_regions(rgb, todo, report, fill, cancel, [r for r in regions if r.status == "translated"],
                              unit_box=unit.box)
            regions[:] = [r for r in regions if r.status != "repeated"]
            self._order_read(rgb, unit.box, regions)  # what was read now, in its place among the translations
            todo = [r for r in regions if any(r is t for t in todo)]
            err = self._translate_regions(todo, report, fill, cancel, on_slow, unit.box)
        new = [r for r in todo if r.status == "translated"]
        lacking = any(r.status in ("untranslated", "ocr-unavailable") for r in todo)
        if self.cache is None or (not new and lacking == page.incomplete):
            return err
        for r in new:
            poly = [unit.normalize((int(x) + r.x0, int(y) + r.y0, int(x) + r.x0, int(y) + r.y0))[:2]
                    for x, y in mask_polygon(r.mask)]
            page.bubbles.append(CachedBubble(box=unit.normalize(r.bbox), text=r.translated_text, poly=poly, flags=list(r.flags),
                                             note=r.reader_note, angle=r.angle))
            r.from_cache = not page.incomplete  # (a marked page's are new to the reader, and to a run's count)
        self._save_page(page.fingerprint, page.aspect, page.bubbles, lacking)
        return err

    # ------------------------------------------------------------------ translator mode
    def rerender(self, result: PageResult) -> None:
        """Draw the result's regions again over its original image (after an edit)."""
        out = np.asarray(result.original).copy()
        self._render(out, result.regions, recap=False)  # an edit of one region leaves the others' sizes alone
        result.image = Image.fromarray(out)

    def _page_for(self, unit: fp.PageUnit) -> CachedPage:
        assert self.cache is not None
        hit = self.cache.lookup(unit.fingerprint, unit.aspect, self.settings.fingerprint_max_distance, None)
        if hit is not None:
            return hit[0]
        return CachedPage(fingerprint=unit.fingerprint, aspect=unit.aspect, bubbles=[], seq=-1)

    def set_translation(self, result: PageResult, region: TextRegion, text: str) -> bool:
        """Store *text* as the translation of *region* (on its cached page) and redraw the result."""
        text = text.strip()
        if self.cache is None or region.unit >= len(result.units) or not text:
            return False
        unit = result.units[region.unit]
        page = self._page_for(unit)
        nbox = unit.normalize(region.bbox)
        best = max(page.bubbles, key=lambda b: box_iou(b.box, nbox), default=None)  # type: ignore[arg-type]
        if best is not None and box_iou(best.box, nbox) >= self.settings.match_min_iou:  # type: ignore[arg-type]
            best.text = text
            best.flags = []  # the reader has looked at it
        else:
            poly = [unit.normalize((int(x) + region.x0, int(y) + region.y0, int(x) + region.x0, int(y) + region.y0))[:2]
                    for x, y in mask_polygon(region.mask)]
            page.bubbles.append(CachedBubble(box=nbox, text=text, poly=poly, note=region.reader_note, angle=region.angle))
        # a page that enters the cache with this one line alone may lack the others: the next reading sees
        self._save_page(page.fingerprint, page.aspect, page.bubbles, page.incomplete or page.seq < 0)
        region.translated_text = text
        region.status = "translated"
        region.from_cache = True
        region.flags = []
        self._erase_only([region])  # (kept in the cache, set again once the region is no longer "erase only")
        self.rerender(result)
        return True

    def page_context(self, result: PageResult, region: TextRegion, limit: int = 12) -> list[tuple[str, str]]:
        """The page's translated lines before *region* in reading order, as (Japanese, translation)."""
        pairs: list[tuple[str, str]] = []
        for r in result.regions:
            if r is region:
                break
            if r.status == "translated" and r.source_text and r.translated_text:
                pairs.append((r.source_text, r.translated_text))
        return pairs[-limit:]

    def ask_again(self, result: PageResult, region: TextRegion) -> str:
        """One more translation of *region* from the model, with the page's earlier lines, the premises and the
        reader-made facts as context; "" when none came."""
        if self.translator is None or not region.source_text or region.tag == ERASE_ONLY:
            return ""
        meta = region_meta(region)
        outs = self.translator.translate_page([region.source_text], self.page_context(result, region), self.premises(),
                                              meta=[meta] if meta else None)
        text = balance_marks(((outs[0] if outs else "") or "").strip())
        return text if text and self.real_translation(region.source_text, text) else ""

    def read_source(self, result: PageResult, region: TextRegion) -> str:
        """The Japanese of *region* read again from the capture *result* was made from, as a page's reading reads it
        (charspot, then what all the readers settle on; memoised by the crop's pixels, in memory only): for the region
        editor of a page shown from the cache, whose regions carry no Japanese since the cache keeps none. The
        region's `source_text` and `ocr_confidence` take the reading; its status and translation stay, and nothing
        is stored. "" without the OCR, or when nothing is read there."""
        if self.ocr is None:
            return ""
        rgb = np.asarray(result.original)
        view = self._ocr_view(rgb, region)
        reading = self._read(rgb, region, region.text_box, view)
        reading = self._settle(rgb, region, region.text_box, reading, view)
        region.source_text = reading.text
        region.ocr_confidence = min(reading.score, SPLIT_CONFIDENCE) if reading.split else reading.score
        return reading.text

    def set_reader_note(self, result: PageResult, region: TextRegion, note: str) -> bool:
        """Store *note* (a note for the reader; "" for none) with the region's cached translation."""
        note = clean_text(note, 120)
        if self.cache is None or region.unit >= len(result.units):
            return False
        unit = result.units[region.unit]
        page = self._page_for(unit)
        nbox = unit.normalize(region.bbox)
        best = max(page.bubbles, key=lambda b: box_iou(b.box, nbox), default=None)  # type: ignore[arg-type]
        if best is None or box_iou(best.box, nbox) < self.settings.match_min_iou:  # type: ignore[arg-type]
            return False
        best.note = note
        self._save_page(page.fingerprint, page.aspect, page.bubbles, page.incomplete)
        region.reader_note = note
        return True

    def drop_region(self, result: PageResult, region: TextRegion) -> bool:
        """Forget *region*: its bubble leaves the cached page and the spot is remembered as not text."""
        if region.unit >= len(result.units):
            return False
        unit = result.units[region.unit]
        nbox = unit.normalize(region.bbox)
        if self.annotations is not None:
            removed = self.annotations.remove_box(unit.fingerprint, unit.aspect, nbox)  # an "add" box of the reader's own
            if not removed and not region.kind.startswith("manual"):
                self.annotations.add_box(unit.fingerprint, unit.aspect, nbox, "ignore")
            self.save_annotations()
        if self.cache is not None:
            page = self._page_for(unit)
            keep = [b for b in page.bubbles if box_iou(b.box, nbox) < self.settings.match_min_iou]  # type: ignore[arg-type]
            if len(keep) != len(page.bubbles) or page.seq >= 0:
                self._save_page(page.fingerprint, page.aspect, keep, page.incomplete)
        region.status = "dropped"
        region.translated_text = ""
        result.regions = [r for r in result.regions if r is not region]
        self.rerender(result)
        return True

    def set_region_note(self, result: PageResult, region: TextRegion, speaker: str = "", kind: str = "",
                        continues: bool = False, note: str = "") -> bool:
        """Record who says the region's text, what kind of text it is, whether it continues, and a remark. A region
        made "erase only" (`ERASE_ONLY`) is erased and nothing set (`_erase_only`); made something else again, it is
        lettered with its translation, or waits for one."""
        if self.annotations is None or region.unit >= len(result.units):
            return False
        unit = result.units[region.unit]
        page = self.annotations.page(unit.fingerprint, unit.aspect)
        page.set_note(unit.normalize(region.bbox), speaker, kind, continues, note, self.settings.match_min_iou)
        self.save_annotations()
        region.speaker, region.tag, region.continues, region.remark = speaker.strip(), kind, continues, note.strip()
        if kind == ERASE_ONLY:
            self._erase_only([region])
        elif region.status == ERASED:
            region.status = "translated" if region.translated_text else "untranslated"
        return True

    def set_region_style(self, result: PageResult, region: TextRegion, style: RegionStyle) -> bool:
        """Record how the reader formatted the region's lettering (*style*; an empty one: automatic again) with its
        other premises, and keep it on the region; the caller letters the page again. False without the book's
        premises (no name): nothing is recorded."""
        if self.annotations is None or region.unit >= len(result.units):
            return False
        unit = result.units[region.unit]
        page = self.annotations.page(unit.fingerprint, unit.aspect)
        nbox = unit.normalize(region.bbox)
        note = page.note_at(nbox, self.settings.match_min_iou)
        if (note.style if note is not None else RegionStyle()) != style:
            page.set_style(nbox, style, self.settings.match_min_iou)
            self.save_annotations()
        region.style = None if style.is_empty else style
        return True

    def set_reading_order(self, result: PageResult, ordered: list[TextRegion]) -> bool:
        """Remember the reading order the reader clicked (per page unit)."""
        if self.annotations is None or not ordered:
            return False
        by_unit: dict[int, list[TextRegion]] = {}
        for r in ordered:
            by_unit.setdefault(r.unit, []).append(r)
        for index, regions in by_unit.items():
            if index >= len(result.units):
                continue
            unit = result.units[index]
            page = self.annotations.page(unit.fingerprint, unit.aspect)
            page.order = [unit.normalize(r.bbox) for r in regions]
            for i, r in enumerate(regions):
                r.order_hint = i
        self.save_annotations()
        result.regions = apply_order_hints(result.regions)
        return True

    def set_page_skip(self, result: PageResult, skip: bool) -> bool:
        """Mark every page unit of this capture as skipped (nothing translated there) or not."""
        if self.annotations is None or not result.units:
            return False
        for unit in result.units:
            self.annotations.page(unit.fingerprint, unit.aspect).skip = skip
        self.save_annotations()
        return True

    def is_skipped(self, result: PageResult) -> bool:
        if self.annotations is None:
            return False
        s = self.settings
        pages = [self.annotations.lookup(u.fingerprint, u.aspect, s.fingerprint_max_distance) for u in result.units]
        return bool(pages) and all(p is not None and p.skip for p in pages)

    def forget_page(self, result: PageResult) -> int:
        """Drop the cached translations of this capture's page units (the premises stay); returns how many pages."""
        if self.cache is None:
            return 0
        gone = 0
        for unit in result.units:
            hit = self.cache.lookup(unit.fingerprint, unit.aspect, self.settings.fingerprint_max_distance, None)
            if hit is not None:
                gone += self.cache.remove(hit[0].fingerprint)
        if gone:
            self._save_store("cache", self.cache)
        self.reset_context()
        return gone

    def pages_of(self, result: PageResult) -> list[CachedPage]:
        """Copies of the cached pages of this capture's units, for `restore_pages` once they are forgotten."""
        if self.cache is None:
            return []
        hits = [self.cache.lookup(u.fingerprint, u.aspect, self.settings.fingerprint_max_distance, None)
                for u in result.units]
        return [copy.deepcopy(hit[0]) for hit in hits if hit is not None]

    def restore_pages(self, pages: Sequence[CachedPage]) -> None:
        """Put back pages `forget_page` took away (`pages_of`), but for one that has an entry again meanwhile: "Translate
        again" that came to nothing. The translations are the reader's until new ones take their place."""
        if self.cache is None:
            return
        back = [p for p in pages if self.cache.lookup(p.fingerprint, p.aspect, self.settings.fingerprint_max_distance,
                                                      None) is None]
        for page in back:
            self.cache.put_back(page)
        if back:
            self._save_store("cache", self.cache)

    def add_region(self, result: PageResult, box: Box) -> bool:
        """Remember *box* (capture coordinates) as text on its page (`unit_for`: below a page unit cut short, it is
        that unit's); the next processing reads and translates it."""
        if self.annotations is None or not result.units:
            return False
        unit = unit_for(result.units, box)
        if unit is None:
            return False
        self.annotations.add_box(unit.fingerprint, unit.aspect, unit.normalize(box), "add")
        return self._save_store("annotations", self.annotations)

    def move_region(self, result: PageResult, region: TextRegion, box: Box, progress: ProgressFn | None = None) -> bool:
        """Translator mode: *region* resized or moved to *box* (capture coordinates). It becomes a rectangle of the
        reader's, as `add_region` makes, and keeps its premises (speaker, kind, remark, place in the reading order)
        and its translation. Where the box now takes in more of the page it is read again, and translated again
        when the reading changed. False without the book's premises (no name) or for a box too small."""
        if self.annotations is None or region.unit >= len(result.units):
            return False
        s = self.settings
        report = progress or (lambda _msg: None)
        rgb = np.asarray(result.original)
        h, w = rgb.shape[:2]
        box = (max(0, int(box[0])), max(0, int(box[1])), min(w, int(box[2])), min(h, int(box[3])))
        if box[2] - box[0] < 6 or box[3] - box[1] < 6:
            return False
        old_unit = result.units[region.unit]
        unit = unit_for(result.units, box) or old_unit
        old_box, old_nbox, nbox = region.bbox, old_unit.normalize(region.bbox), unit.normalize(box)
        ann = self.annotations
        old_page = ann.page(old_unit.fingerprint, old_unit.aspect)
        if region.kind.startswith("manual"):  # the reader's own rectangle moves
            best = max(range(len(old_page.add)), key=lambda i: box_iou(old_page.add[i], old_nbox), default=None)  # type: ignore[arg-type]
            if best is not None and box_iou(old_page.add[best], old_nbox) >= 0.3:  # type: ignore[arg-type]
                del old_page.add[best]
        else:  # the detection is not looked for there again
            ann.add_box(old_unit.fingerprint, old_unit.aspect, old_unit.normalize(region.text_box), "ignore")
        new_page = ann.add_box(unit.fingerprint, unit.aspect, nbox, "add")
        note = old_page.note_at(old_nbox, s.match_min_iou)
        if note is not None:
            old_page.notes.remove(note)
            new_page.set_note(nbox, note.speaker, note.kind, note.continues, note.note, s.match_min_iou, note.style)
        if old_page.order:
            best = max(range(len(old_page.order)), key=lambda i: box_iou(old_page.order[i], old_nbox))  # type: ignore[arg-type]
            if box_iou(old_page.order[best], old_nbox) >= s.match_min_iou:  # type: ignore[arg-type]
                if new_page is old_page:
                    old_page.order[best] = nbox
                else:
                    del old_page.order[best]
        self.save_annotations()

        kept = (region.source_text, region.translated_text, region.status, list(region.flags), region.ocr_confidence)
        translated = region.status == "translated" and bool(region.translated_text)
        fresh = manual_region(rgb, box, s.dark_threshold)
        region.x0, region.y0, region.x1, region.y1 = box
        region.mask, region.text_box, region.kind = fresh.mask, fresh.text_box, fresh.kind
        region.core_box = region.letter_box = region.beyond_box = region.before_beyond = region.after = None
        region.from_model, region.tier = False, 0
        region.pieces = region.edge_pieces = 0
        region.glyph = 0.0
        region.unit = unit.index
        region.angle, region.tilt, region.char_quads = 0.0, None, []
        self._measure_slants(rgb, [region])  # (its lettering's slant in its new box)
        grew = box[0] < old_box[0] or box[1] < old_box[1] or box[2] > old_box[2] or box[3] > old_box[3]
        if self.ocr is not None and (grew or not translated):
            self._ocr_regions(rgb, [region], report)
            if translated and (region.status != "untranslated" or region.source_text == kept[0]):
                # nothing new came in: the translation stays
                region.source_text, region.translated_text, region.status, region.flags, region.ocr_confidence = kept
            elif region.status == "untranslated":
                region.translated_text = ""
                err = self._translate_regions([region], report)
                if err:
                    result.error = err

        if self.cache is not None:
            page = self._page_for(old_unit)
            rest = [b for b in page.bubbles if box_iou(b.box, old_nbox) < s.match_min_iou]  # type: ignore[arg-type]
            if len(rest) != len(page.bubbles):
                self._save_page(page.fingerprint, page.aspect, rest, page.incomplete)
            if region.status == "translated" and region.translated_text:
                page = self._page_for(unit)
                poly = [unit.normalize((int(x) + box[0], int(y) + box[1], int(x) + box[0], int(y) + box[1]))[:2]
                        for x, y in mask_polygon(region.mask)]
                bubbles = [b for b in page.bubbles if box_iou(b.box, nbox) < s.match_min_iou]  # type: ignore[arg-type]
                bubbles.append(CachedBubble(box=nbox, text=region.translated_text, poly=poly, flags=list(region.flags),
                                            note=region.reader_note, angle=region.angle))
                self._save_page(page.fingerprint, page.aspect, bubbles, page.incomplete)
                region.from_cache = True
        self.rerender(result)
        return True

    def _ocr_regions(self, rgb: np.ndarray, regions: list[TextRegion], report: ProgressFn,
                     fill: PageFill | None = None, cancel: threading.Event | None = None,
                     read: Sequence[TextRegion] = (), unit_box: Box | None = None) -> list[TextRegion]:
        """Read *regions*. Where the layout model found some, those first and together (one that repeats another of
        them read as text before it is left out); then the classical ones, each read only if it does not repeat what
        was read as text so far (or *read*, regions read before), all judged on the page's usual size. The model's
        regions then take their classical shape, and of two that took the same one only the first stays. What was left
        out leaves *regions* and is returned (each with the region it repeats in ``repeats``). A region the reader made
        "erase only" is read too (its reading shapes its erase) and then takes the status `ERASED`."""
        self._measure_slants(rgb, regions)
        usual = self._usual(rgb, regions, cancel) if self.ocr is not None else 0.0  # (from all its regions)
        first = [r for r in regions if r.from_model]
        among = [*regions, *read]  # (what a short line may lie on: `_on_lettering`)
        if not first:
            self._read_regions(rgb, regions, report, fill, cancel, usual=usual, among=among)
            self._titles(regions, usual, fill, unit_box or (0, 0, rgb.shape[1], rgb.shape[0]))
            self._erase_only(regions, fill)
            return []
        total = len(regions)
        self._read_regions(rgb, first, report, fill, cancel, total=total, usual=usual, among=among)
        got = list(read)
        repeated: list[TextRegion] = []

        def repeats(r: TextRegion) -> bool:
            r.repeats = cover_of(r, got)
            if r.repeats is None:
                return False
            r.status = "repeated"
            repeated.append(r)
            if fill is not None:
                fill.read(r)
            return True

        for r in first:  # the model's boxes of one lettering (two texts, a bubble and its text): the first read stays
            if r.status != "untranslated" or not r.source_text:
                continue
            twin = next((q for q in got if q.from_model and _same_lettering(q, r)), None)
            if twin is not None:
                r.status, r.repeats = "repeated", twin
                repeated.append(r)
                if fill is not None:
                    fill.read(r)
                continue
            got.append(r)
        for i, r in enumerate(r for r in regions if not r.from_model):
            if repeats(r):
                continue
            self._read_regions(rgb, [r], report, fill, cancel, done=len(first) + i, total=total, usual=usual,
                               among=among)
            if r.status == "untranslated" and r.source_text:
                got.append(r)
        for r in first:
            take_shape(r)
        lettered: list[TextRegion] = []
        for r in regions:  # two regions lettering one place: the first stays, and a shaped one before a plain box
            if r.status != "untranslated" or not r.source_text:
                continue
            twin = next((q for q in lettered if _same_lettering(q, r)), None)
            if twin is not None and _plain(twin) and not _plain(r):
                lettered[lettered.index(twin)] = r
                r, twin = twin, r
            if twin is not None:
                r.status, r.repeats = "repeated", twin
                repeated.append(r)
                continue
            lettered.append(r)
        regions[:] = [r for r in regions if r.status != "repeated"]
        for r in printed_lines(regions):
            r.status = "print"
            if fill is not None:
                fill.read(r)
        self._titles(regions, usual, fill, unit_box or (0, 0, rgb.shape[1], rgb.shape[0]))
        self._erase_only(regions, fill)
        return repeated

    @staticmethod
    def _erase_only(regions: Sequence[TextRegion], fill: PageFill | None = None) -> None:
        """The regions the reader made "erase only" (their kind `ERASE_ONLY`, from the book's annotations) take the
        status `ERASED`, whatever their reading said: the render erases their lettering and sets nothing (`erases`),
        and they are never translated (only "untranslated" regions are), flagged, or counted as untranslated."""
        for r in regions:
            if r.tag == ERASE_ONLY and r.status not in ("dropped", "repeated"):
                r.status, r.flags = ERASED, []
                if fill is not None:
                    fill.read(r)

    def _order_read(self, rgb: np.ndarray, unit_box: Box, regions: list[TextRegion]) -> None:
        """*regions* of the page unit *unit_box* put in reading order again once they are read, in place: the regions
        read as text (or translated: a cached page's) ordered among themselves (`order_on_page`: the panels found with
        only their lettering as what may sit on a gutter, the rows made of them alone), the others after them as they
        were; the reader's order first (`apply_order_hints`). Ordered before the reading, every candidate counted (the
        layout model's boxes, the classical regions of the same bubbles, a drawing read as nothing): a tall one that
        is no text joined two rows into one. A fresh page, a page from the cache and a marked page completed
        (`_complete_page`) are ordered alike."""
        text = [r for r in regions if (r.status == "untranslated" and r.source_text) or r.status == "translated"]
        if not text and not any(r.order_hint >= 0 for r in regions):
            return
        chosen = {id(r) for r in text}
        ordered = apply_order_hints(order_on_page(rgb, unit_box, text, self.rtl)
                                    + [r for r in regions if id(r) not in chosen])
        regions[:] = ordered
        for i, r in enumerate(regions):
            r.order = i

    def _titles(self, regions: list[TextRegion], usual: float, fill: PageFill | None,
                unit_box: Box = (0, 0, 0, 0)) -> None:
        """The regions read as text of a page unit (*unit_box*) that holds only its titles (`title_unit`) become print;
        their size is held to the book's usual one so far (the page's own, on a title page, is the title's)."""
        read = [r for r in regions if r.status == "untranslated" and r.source_text and not r.kind.startswith("manual")]
        book = float(np.median(self._book_sizes)) if self._book_sizes else usual
        if title_unit(read, min(usual, book), unit_box[3] - unit_box[1]):
            for r in read:
                r.status = "print"
                if fill is not None:
                    fill.read(r)

    def _usual(self, rgb: np.ndarray, regions: list[TextRegion], cancel: threading.Event | None = None) -> float:
        """The usual character size of the page from all of *regions* (`usual_size`), kept with the book's."""
        samples: list[float] = []
        for r in regions:
            check_cancel(cancel)
            size = size_sample(self._read(rgb, r, r.text_box, self._ocr_view(rgb, r)))
            if size is not None:
                samples.append(size)
        usual = usual_size(samples, self._book_sizes)
        self._book_sizes.extend(samples)
        return usual

    def _read_regions(self, rgb: np.ndarray, regions: list[TextRegion], report: ProgressFn,
                      fill: PageFill | None = None, cancel: threading.Event | None = None, done: int = 0,
                      total: int = 0, usual: float | None = None, among: Sequence[TextRegion] = ()) -> None:
        """Read *regions*: all of them first, for the page's usual character size (`usual_size`; *usual* when given),
        then each is judged on it, so that a region's fate does not hang on the order of reading. *done* of *total*
        went before them; *among* are the page unit's regions, read or not, that a short line may lie on
        (`_on_lettering`). A model region without a measured glyph size takes its reading's (what its lettering is sized
        from)."""
        if self.ocr is None:
            for r in regions:
                r.status = "ocr-unavailable"
                if fill is not None:
                    fill.read(r)
            return
        n = total or len(regions)
        if usual is None:
            usual = self._usual(rgb, regions, cancel)
        for i, r in enumerate(regions):
            check_cancel(cancel)
            report(Message("pipeline.stage_reading", done=done + i + 1, total=n))
            if r.beyond_box is not None and r.before_beyond is not None:
                # a column the detector took in past a dark bubble's interior is kept when the reading with it is the
                # reading without it plus more text; a drawing adds nothing, or garbles the rest
                a = self._read(rgb, r, r.text_box)
                b = self._read(rgb, r, r.before_beyond[1])
                if (not extends_reading(a.text, b.text) or a.score < b.score - BEYOND_CONFIDENCE_DROP
                        or self._verdict(r, a, r.pieces, usual) != "untranslated"):
                    self._revert_beyond(r)
            view = self._ocr_view(rgb, r)
            box, pieces = r.text_box, r.pieces
            reading = self._read(rgb, r, box, view)
            status = self._verdict(r, reading, pieces, usual)
            if r.core_box is not None and r.core_box != r.text_box:
                # Lettering against the outline was taken in: it completes the text, it does not decide whether
                # this is text. That is judged on the text box as detected before (artwork that was read as junk
                # stays junk); the completed reading is used when both readings pass.
                core = self._read(rgb, r, r.core_box, view)
                core_status = self._verdict(r, core, r.pieces - r.edge_pieces, usual)
                if core_status != "untranslated" or status != "untranslated":
                    reading, status, box, pieces = core, core_status, r.core_box, pieces - r.edge_pieces
            unanimous = False
            if (status == "ocr-noise" and self._short_line(r, reading.text, reading.score, pieces, unanimous=True)
                    and not self._on_lettering(r, among)):
                # a short line charspot alone does not carry (one character, or less sure): the others are asked
                unanimous = self._unanimous(rgb, r, box, reading, view)
                if unanimous:
                    status = self._verdict(r, reading, pieces, usual, unanimous=True)
            if status == "untranslated" or r.kind.startswith("manual"):  # the gate is charspot's: the others read the rest
                reading = self._settle(rgb, r, box, reading, view)
                status = self._verdict(r, reading, pieces, usual, unanimous)
            r.source_text = reading.text
            r.char_size = max((max(c.box[2] - c.box[0], c.box[3] - c.box[1]) for c in reading.chars), default=0.0)
            if r.from_model:
                if not r.glyph and reading.chars:
                    r.glyph = float(reading.size)
                r.char_boxes, r.char_quads = self._char_boxes(rgb, r, box, reading.chars, view)
            r.ocr_split = reading.split
            r.ocr_confidence = min(reading.score, SPLIT_CONFIDENCE) if reading.split else reading.score
            r.status = status
            if fill is not None:
                fill.read(r)

    @staticmethod
    def _revert_beyond(r: TextRegion) -> None:
        """The region as it was before the detector took a column in past the interior (the OCR saw no text there)."""
        (r.x0, r.y0, r.x1, r.y1), r.text_box, r.mask, taken = r.before_beyond
        r.pieces -= taken
        r.edge_pieces -= taken
        if r.core_box == r.text_box:
            r.core_box = None
        r.beyond_box = None
        r.before_beyond = None

    def _ocr_view(self, rgb: np.ndarray, r: TextRegion) -> np.ndarray | None:
        """For a light bubble whose text box reaches over the drawing (outlined glyphs on the hair): its pixels
        with everything outside the mask white and those glyphs' strokes black, so the OCR reads them."""
        if r.kind != "bubble":
            return None
        s = self.settings
        mask = r.mask
        if mask.shape != (r.height, r.width):
            mask = cv2.resize(mask, (r.width, r.height), interpolation=cv2.INTER_NEAREST)
        tb = r.text_box
        local = (tb[0] - r.x0, tb[1] - r.y0, tb[2] - r.x0, tb[3] - r.y0)
        return ocr_view(rgb[r.y0:r.y1, r.x0:r.x1], mask, local, s.dark_threshold, s.white_threshold)

    def _measure_slants(self, rgb: np.ndarray, regions: Sequence[TextRegion]) -> None:
        """The slant of the lettering of each of *regions* not measured yet (`lettering_tilt` of the ink in its text
        box, within its mask), with `Settings.slant_text`; a region whose slant came with it (``tilt`` set: the
        cache's, the reader's) keeps it. Without the setting nothing is measured and every region stays upright."""
        s = self.settings
        if not s.slant_text:
            return
        for r in regions:
            if r.tilt is not None:
                continue
            ink = region_ink(rgb, self._region_mask(r), r.text_box, (r.x0, r.y0), s.dark_threshold, is_dark(r))
            r.tilt = lettering_tilt(ink)
            r.angle = r.tilt.angle

    @staticmethod
    def _region_mask(r: TextRegion) -> np.ndarray:
        """The region's mask at the size of its box."""
        if r.mask.shape == (r.height, r.width):
            return r.mask
        return cv2.resize(r.mask, (r.width, r.height), interpolation=cv2.INTER_NEAREST)

    def _upright(self, rgb: np.ndarray, r: TextRegion, crop: Box) -> tuple[Upright, Box]:
        """For a slanted region: the turn that sets the page part *crop* (page box) upright (`Upright`), and the part
        of the turned picture the OCR reads - the frame of the ink of its text box in it (within the region's mask),
        padded as an upright crop is."""
        s = self.settings
        x0, y0, x1, y1 = crop
        turn = Upright((y1 - y0, x1 - x0), r.angle, (x0, y0))
        tb = r.text_box
        inside = (max(x0, tb[0]), max(y0, tb[1]), min(x1, tb[2]), min(y1, tb[3]))
        ink = np.zeros((y1 - y0, x1 - x0), bool)
        if inside[2] > inside[0] and inside[3] > inside[1]:
            ink[inside[1] - y0:inside[3] - y0, inside[0] - x0:inside[2] - x0] = region_ink(
                rgb, self._region_mask(r), inside, (r.x0, r.y0), s.dark_threshold, is_dark(r))
        fx0, fy0, fx1, fy1 = ink_frame(ink, r.angle)
        pad = max(4, int(0.08 * min(fx1 - fx0, fy1 - fy0)))
        frame = (max(0, int(fx0) - pad), max(0, int(fy0) - pad), min(turn.width, int(math.ceil(fx1)) + pad),
                 min(turn.height, int(math.ceil(fy1)) + pad))
        return turn, frame

    def _char_boxes(self, rgb: np.ndarray, r: TextRegion, box: Box, chars: Sequence[Any],
                    view: np.ndarray | None = None) -> tuple[list[Box], list[list[tuple[float, float]]]]:
        """Where the reading of *box* of *r* found each of *chars* on the page: their boxes, and for a slanted region
        read turned upright (`_chosen`) also the boxes as turned on the page (four corners each; the boxes are the
        upright boxes round them)."""
        ox, oy = self._crop_origin(r, box)
        chosen = self._chosen(rgb, r, box, view) if r.angle else None
        if chosen is None or not chosen[2]:
            return [(int(ox + c.box[0]), int(oy + c.box[1]), int(ox + c.box[2] + 0.999), int(oy + c.box[3] + 0.999))
                    for c in chars], []
        x1, y1 = self._crop_end(r, box)
        turn, (fx0, fy0, _fx1, _fy1) = self._upright(rgb, r, (ox, oy, x1, y1))
        quads = [[turn.back(fx0 + x, fy0 + y) for x, y in ((c.box[0], c.box[1]), (c.box[2], c.box[1]),
                                                           (c.box[2], c.box[3]), (c.box[0], c.box[3]))]
                 for c in chars]
        boxes = [(int(math.floor(min(p[0] for p in q))), int(math.floor(min(p[1] for p in q))),
                  int(math.ceil(max(p[0] for p in q))), int(math.ceil(max(p[1] for p in q)))) for q in quads]
        return boxes, quads

    @staticmethod
    def _crop_origin(r: TextRegion, box: Box) -> tuple[int, int]:
        """The page position of the corner of the crop `_ocr_crop` reads for *box* of *r*."""
        pad = max(4, int(0.08 * min(r.width, r.height)))
        return max(r.x0, box[0] - pad), max(r.y0, box[1] - pad)

    @staticmethod
    def _crop_end(r: TextRegion, box: Box) -> tuple[int, int]:
        """The page position of the far corner of that crop."""
        pad = max(4, int(0.08 * min(r.width, r.height)))
        return min(r.x1, box[2] + pad), min(r.y1, box[3] + pad)

    def _ocr_crop(self, rgb: np.ndarray, r: TextRegion, box: Box, view: np.ndarray | None = None,
                  turned: bool = False) -> tuple[Image.Image, str] | None:
        """The crop the OCR reads for the region's *box* (padded, within the region; from *view*, the region's
        prepared pixels, when given) and its memo key (the crop's pixels); None when nothing of the box lies in the
        region. *turned*: a slanted region's crop turned upright (`_upright`)."""
        s = self.settings
        pad = max(4, int(0.08 * min(r.width, r.height)))
        if view is None:
            crop = r.crop(rgb, box=box, pad=pad)
        else:
            bx0, by0, bx1, by1 = box
            x0, y0, x1, y1 = max(r.x0, bx0 - pad), max(r.y0, by0 - pad), min(r.x1, bx1 + pad), min(r.y1, by1 + pad)
            crop = Image.fromarray(view[y0 - r.y0:y1 - r.y0, x0 - r.x0:x1 - r.x0])
        if crop.width < 2 or crop.height < 2:
            return None
        if turned and r.angle:  # slanted lettering turned upright (the OCR's readers take upright text)
            ox, oy = self._crop_origin(r, box)
            turn, (fx0, fy0, fx1, fy1) = self._upright(rgb, r, (ox, oy, ox + crop.width, oy + crop.height))
            ground = (0, 0, 0) if is_dark(r) else (255, 255, 255)
            crop = Image.fromarray(turn.turn(np.asarray(crop), ground)[fy0:fy1, fx0:fx1])
            if crop.width < 2 or crop.height < 2:
                return None
        if is_dark(r):
            crop = ImageOps.invert(crop)  # the OCR model reads dark-on-light
        return crop, hashlib.sha1(crop.tobytes()).hexdigest() + f"{crop.size}"

    def _read(self, rgb: np.ndarray, r: TextRegion, box: Box, view: np.ndarray | None = None) -> CharspotReading:
        """OCR the region's *box* (`_chosen`); memoised by the crop's pixels (memory only)."""
        chosen = self._chosen(rgb, r, box, view)
        if chosen is None:
            return CharspotReading()  # nothing of the box lies in the region
        return self._memo_read(*chosen[:2])

    def _memo_read(self, crop: Image.Image, key: str) -> CharspotReading:
        memo = self._ocr_memo.get(key)
        if memo is None:
            memo = read_crop(self.ocr, crop)
            if len(self._ocr_memo) > 2000:
                self._ocr_memo.clear()
            self._ocr_memo[key] = memo
        return memo

    def _chosen(self, rgb: np.ndarray, r: TextRegion, box: Box,
                view: np.ndarray | None = None) -> tuple[Image.Image, str, bool] | None:
        """The crop the OCR reads for *box* of *r* (`_ocr_crop`), its key, and whether it is turned upright. A slanted
        region is read both ways, as cut and turned upright, and the reading charspot is surer of wins (a tie: as cut).
        The readers were trained on lettering turned a little, and read most slants as well as cut, some better (on
        the volume's slanted lettering, 24 lines, no line read better turned, five worse); turned by 12 degrees or
        more, real lettering is read far worse as cut (CER 6 to 22 % against about 4 % turned upright)."""
        straight = self._ocr_crop(rgb, r, box, view)
        if straight is None or not r.angle:
            return None if straight is None else (*straight, False)
        turned = self._ocr_crop(rgb, r, box, view, turned=True)
        if turned is None or self._memo_read(*turned).score <= self._memo_read(*straight).score:
            return (*straight, False)
        return (*turned, True)

    def _settle(self, rgb: np.ndarray, r: TextRegion, box: Box, reading: CharspotReading,
                view: np.ndarray | None = None) -> CharspotReading:
        """Charspot's *reading* of the region's *box* with the text all the readers settle on (`Readers.settle`), for
        an engine that has others; memoised like `_read`."""
        settle = getattr(self.ocr, "settle", None)
        prepared = self._chosen(rgb, r, box, view)
        if settle is None or prepared is None:
            return reading
        crop, key, _turned = prepared
        key += "|settled"
        memo = self._ocr_memo.get(key)
        if memo is None:
            memo = settle(crop, reading)
            self._ocr_memo[key] = memo
        return memo

    def _unanimous(self, rgb: np.ndarray, r: TextRegion, box: Box, reading: CharspotReading,
                   view: np.ndarray | None = None) -> bool:
        """Whether all the readers read charspot's *reading* of the region's *box* (`Readers.unanimous`), memoised
        like `_read`; False for an engine that reads alone."""
        unanimous = getattr(self.ocr, "unanimous", None)
        prepared = self._chosen(rgb, r, box, view)
        if unanimous is None or prepared is None or not reading.text:
            return False
        crop, key, _turned = prepared
        key += "|" + reading.text
        memo = self._unanimous_memo.get(key)
        if memo is None:
            memo = bool(unanimous(crop, reading.text))
            if len(self._unanimous_memo) > 2000:
                self._unanimous_memo.clear()
            self._unanimous_memo[key] = memo
        return memo

    def _verdict(self, r: TextRegion, reading: CharspotReading, pieces: int, usual: float,
                 unanimous: bool = False) -> str:
        """`_judge` of *reading*, and a reading that passed held to the page's lettering (`charspot_accepts`), but for
        a region the reader added and a short line all the readers read (*unanimous*, `_short_line`): one character
        is too short for the gate, and its size says nothing about a bubble's single word."""
        status = self._judge(r, reading.text, reading.score, pieces, unanimous)
        if status != "untranslated" or not reading.chars or r.kind.startswith("manual"):
            return status
        if not charspot_accepts(reading, usual) and not (
                unanimous and self._short_line(r, reading.text, reading.score, pieces, unanimous=True)):
            return "ocr-noise"
        return status

    def _judge(self, r: TextRegion, text: str, confidence: float, pieces: int, unanimous: bool = False) -> str:
        """What a reading of region *r* is: dialogue to translate ("untranslated") or why it is not.

        One or two characters from a region of many dark pieces, or from one smaller than `min_short_bubble`, are
        noise (a face, a highlight, a fleck of the drawing) unless they read as a short line in a region with an
        outline of its own (`_short_line`, *unanimous*: all the readers read *text*): a small bubble with an
        exclamation or a one-word reply is cut down to its lettering and ends up as small as a highlight."""
        s = self.settings
        if not text:
            return "ocr-empty"
        if not looks_japanese(text):
            return "not-japanese"
        if r.kind.startswith("manual"):
            return "untranslated"  # the reader marked this spot as text: no second-guessing
        if confidence < s.ocr_min_confidence:
            return "low-confidence"  # the model was guessing: probably not text at all
        if (r.kind in ("text", "text-dark") or r.from_model) and not s.translate_sfx and is_sound_effect(text):
            return "sfx"  # hand-lettered onomatopoeia outside bubbles: left as drawn
        short_line = self._short_line(r, text, confidence, pieces, unanimous)
        if pieces and not short_line and len(text) < max(2, pieces // (4 if r.kind in ("text", "text-dark") else 5)):
            return "ocr-noise"  # many dark pieces but hardly any text: a face or artwork, not lettering
        if japanese_share(text) < 0.6:
            return "ocr-noise"  # mostly symbols: the model was shown something that is not text
        if len(text) <= 2 and max(r.width, r.height) < s.min_short_bubble and not short_line:
            return "ocr-noise"  # a tiny blob read as one or two characters: a highlight, not a bubble
        if looks_like_print(text, r.text_box) or (loose(r) and looks_like_credit(text, r.text_box)):
            return "print"  # viewer widgets, imprint pages, prices, credits: not dialogue
        return "untranslated"

    # A short line: one or two characters the OCR is sure of, in a region with an outline of its own. Measured on the
    # OpenMantra pages and the test volume: 53 of the 55 such readings led by a hiragana or a kanji were a small
    # bubble's whole line (the 46 with a gold box read exactly; the other two began a longer column); hiragana read in
    # small regions without a line scored 0.94 at most, and katakana in small regions were pieces of sound effects.
    # One character never passed: charspot's gate wants two (`charspot_accepts`). A short line all three readers read
    # (`Readers.unanimous`) needs neither the two characters nor more than SHORT_LINE_UNANIMOUS_CONFIDENCE: in the
    # official OpenMantra runs that took the worded gold lines of one or two characters lost from 15 to 9 of 93 (10 to
    # 2 with the layout model) and added no reading where no gold line is (41 and 44, before and after); below 0.9 all
    # three read one where none is. Never on more lettering (`_on_lettering`): on the test volume all three read alike
    # two characters of a longer line, a small white area in its lettering.
    SHORT_LINE_KINDS = ("bubble", "dark-bubble", "text-on-page", "text-on-dark")  # closed (the detector or the model)
    SHORT_LINE_CONFIDENCE = 0.95
    SHORT_LINE_UNANIMOUS_CONFIDENCE = 0.9
    SHORT_LINE_ON_LETTERING = 0.5  # ... and never on another region's lettering (`_on_lettering`): a piece of its line
    SHORT_LINE_PIECES = 3  # dark pieces per character at most: a glyph and a mark, never a face
    _SHORT_LINE_LEAD = re.compile(r"[ぁ-ゖ㐀-䶿一-鿿]")  # a hiragana or a kanji ...
    _SMALL_KANA = frozenset("ぁぃぅぇぉっゃゅょゎゕゖ")  # ... but not a small kana (a gasp or a fragment)

    @classmethod
    def _on_lettering(cls, r: TextRegion, among: Sequence[TextRegion]) -> bool:
        """Whether *r*'s lettering lies on more lettering of another region of *among* (`SHORT_LINE_ON_LETTERING` of
        its text box or more inside a text box at least twice as large): then it is a piece of a longer line, which all
        the readers may read alike. (The other detector's region of the same lettering is about as large.)"""
        x0, y0, x1, y1 = r.text_box
        area = max(1, (x1 - x0) * (y1 - y0))
        for q in among:
            qx0, qy0, qx1, qy1 = q.text_box
            if (q is not r and (qx1 - qx0) * (qy1 - qy0) >= 2 * area
                    and (max(0, min(x1, qx1) - max(x0, qx0)) * max(0, min(y1, qy1) - max(y0, qy0))
                         >= cls.SHORT_LINE_ON_LETTERING * area)):
                return True
        return False

    @classmethod
    def _short_line(cls, r: TextRegion, text: str, confidence: float, pieces: int, unanimous: bool = False) -> bool:
        """Whether a one- or two-character reading of *r* is a short line of dialogue (see above): read with
        `SHORT_LINE_CONFIDENCE` or more (`SHORT_LINE_UNANIMOUS_CONFIDENCE` when all the readers read it, *unanimous*)
        in a region of one of `SHORT_LINE_KINDS`, led by a hiragana (not a small one) or a kanji, all of it standard
        Japanese, from at most `SHORT_LINE_PIECES` dark pieces a character."""
        bar = cls.SHORT_LINE_UNANIMOUS_CONFIDENCE if unanimous else cls.SHORT_LINE_CONFIDENCE
        return (1 <= len(text) <= 2 and r.kind in cls.SHORT_LINE_KINDS and confidence >= bar
                and bool(cls._SHORT_LINE_LEAD.match(text)) and text[0] not in cls._SMALL_KANA
                and japanese_share(text) == 1.0 and pieces <= cls.SHORT_LINE_PIECES * len(text))

    def _translate_regions(self, regions: list[TextRegion], report: ProgressFn, fill: PageFill | None = None,
                           cancel: threading.Event | None = None, on_slow: SlowFn | None = None,
                           unit_box: Box | None = None) -> str:
        """Translate the regions to translate (one request for all of them, in reading order), check and tighten
        the translations, and set the regions' texts, statuses and flags; "" or the Message of what went
        wrong. Lines the reply left without a usable translation (missing, empty, the Japanese copied) are asked
        for again, a few consecutive ones at a time with their neighbours as context, then each on its own
        (`ask_for_missing`); so are all of them when the request failed with an error that another request may not
        repeat (`worth_asking_again`), and the error is what comes back only when that does not translate them
        all. With *fill*, each translation is lettered as the translator hands it over (when it can,
        `takes_items`), and the final ones (some changed by `tighten`) are settled on the page afterwards. With
        *cancel*, `Cancelled` before the request, during it (a translator that takes ``cancel``) and after it."""
        todo = [r for r in regions if r.status == "untranslated"]
        if not todo:
            return ""
        if self.translator is None:
            return Message("pipeline.no_translator")
        check_cancel(cancel)
        texts = [r.source_text for r in todo]
        for r in todo:
            r.room = translation_room(r.mask, r.letter_box or r.text_box, r.source_text, self.settings, r.kind, r.x0,
                                      r.y0, self.suggested_font, direction_of(r))
        meta = facts_of(todo, [(r.unit, unit_box) for r in todo])  # with the page, a sentence going on
        report(Message("pipeline.stage_translating", bubbles=len(texts),
                       translator=str(getattr(self.translator, "name", "translator"))))
        call: dict[str, Any] = cancel_args(self.translator.translate_page, cancel, on_slow)
        extra = dict(call)
        on_item: Callable[[int, str], None] | None = None
        if fill is not None and takes_items(self.translator):
            def on_item(index: int, text: str) -> None:
                if 0 <= index < len(todo):
                    fill.draft(todo[index], text)

            extra["on_item"] = on_item
        failure: Message | str = ""
        try:
            outputs = self.translator.translate_page(texts, self.context_pairs(), self.premises(),
                                                     meta=meta if any(meta) else None, **extra)
        except TranslationError as e:
            failure = message_of(e)
            if not worth_asking_again(failure):
                return failure
            outputs = []  # every line is asked for again below, a few at a time
        check_cancel(cancel)
        outputs = [str(out or "").strip() for out in outputs[:len(todo)]] + [""] * max(0, len(todo) - len(outputs))

        def usable(i: int, text: str) -> bool:
            return bool(text) and self.real_translation(texts[i], text)

        missing = [i for i in range(len(todo)) if not usable(i, outputs[i])]
        if missing:
            again = ask_for_missing(self.translator, texts, outputs, usable, context=self.context_pairs(),
                                    notes=self.premises(), meta=meta, call_args=call, cancel=cancel,
                                    on_error=worth_asking_again, on_item=on_item)
            outputs = again.texts
            check_cancel(cancel)
        if _base.REASK_ROMANISED:  # a short kana line answered with its romaji alone: asked once more, with its neighbours
            outputs = ask_again_romanised(self.translator, texts, outputs, context=self.context_pairs(),
                                          notes=self.premises(), meta=meta, call_args=call, cancel=cancel)[0]
        entries = [{"ja": r.source_text, "text": out, "mask": r.mask, "kind": r.kind, "anchor": r.letter_box or r.text_box,
                    "x0": r.x0, "y0": r.y0, "meta": region_meta(r), "confidence": r.ocr_confidence,
                    "direction": direction_of(r)}
                   for r, out in zip(todo, outputs)]
        outputs = self.tighten(entries)
        flags = self.review(entries, outputs)
        pairs: list[tuple[str, str]] = []
        for r, out, fl in zip(todo, outputs, flags):
            if out and self.real_translation(r.source_text, out):
                r.translated_text = out
                r.status = "translated"
                r.flags = list(fl)
                pairs.append((r.source_text, out))
            else:
                r.status = "untranslated"
        if pairs and self._context.maxlen:
            self._context.append(pairs)
        if fill is not None:
            fill.settle(todo)
        if failure and any(r.status != "translated" for r in todo):
            return failure  # the request failed and asking again did not make up for it all
        return ""

    def review(self, entries: list[dict[str, Any]], texts: Sequence[str]) -> list[list[str]]:
        """The flags each translation gets for the reader (`taslation.review.REASONS`): set under the readable
        size, missing a rendering from the sheet, far longer or shorter than the Japanese, the OCR unsure."""
        s = self.settings
        sheet = self.check_sheet() if s.enforce_terms else None
        out: list[list[str]] = []
        for e, t in zip(entries, texts):
            t = str(t or "")
            if not t:
                out.append([])
                continue
            size = (self.set_size(e["mask"], t, e["kind"], e["anchor"], e["x0"], e["y0"], _tag(e), e.get("direction", ""))
                    if s.readable_font_size else 0)
            meta = dict(e.get("meta") or {})
            out.append(flags_for(str(e.get("ja", "")), t, size, s, sheet, str(meta.get("speaker", "")),
                                 float(e.get("confidence", 1.0))))
        return out

    def set_size(self, mask: np.ndarray, text: str, kind: str, anchor: Box, x0: int, y0: int, tag: str = "",
                 direction: str = "") -> int:
        """Font size *text* would be set at in a region (its mask, kind and lettering box in page coordinates;
        *tag* is the reader's kind, which chooses the lettering; *direction* its text direction: turned a quarter,
        the mask turned; stacked, the size of its columns)."""
        s = self.settings
        if not text:
            return 0
        local = (anchor[0] - x0, anchor[1] - y0, anchor[2] - x0, anchor[3] - y0)
        if direction in QUARTER_TURNS:
            mask = np.ascontiguousarray(mask.T)
            local = (local[1], local[0], local[3], local[2])
        if direction == "stacked":
            on_page = kind in ("text", "text-dark")
            centre = ((local[0] + local[2]) / 2.0, (local[1] + local[3]) / 2.0) if on_page else None
            size = layout_stacked(mask, text, self.lettering_for(text, tag), s.min_font_size, s.max_font_size,
                                  s.line_spacing, False, centre).size
        else:
            size = layout_text(mask, text, self.lettering_for(text, tag), s.min_font_size, s.max_font_size,
                               s.line_spacing, False, None, kind in ("text", "text-dark"), local)[2]
        if float(s.text_scale) < 1.0 and size:  # set smaller by the lettering size (`_scaled_top`)
            size = max(s.min_font_size, round(size * float(s.text_scale)))
        return size

    def tighten(self, entries: list[dict[str, Any]]) -> list[str]:
        """The translations of *entries* (per bubble "text", "" when there is none) as they are set: stray emphasis
        markers (an asterisk without its pair) dropped. Nothing is asked of the model: a line too long for its bubble
        is set smaller (down to ``min_font_size``) and flagged (`review`); one that misses a rendering of the series
        sheet is flagged too."""
        return [balance_marks(str(e.get("text", ""))) for e in entries]

    def _cacheable(self, regions: list[TextRegion]) -> bool:
        """A page with a genuine translation goes to the cache, marked while a bubble lacks one (`_store_regions`).

        One read without the OCR engine, or without any translation, must be looked at again next time.
        """
        return self.ocr is not None and any(r.status == "translated" for r in regions)

    def _store_regions(self, unit: fp.PageUnit, regions: list[TextRegion]) -> None:
        if self.cache is None:
            return
        bubbles: list[CachedBubble] = []
        for r in regions:
            if r.status != "translated":
                continue
            poly = [unit.normalize((int(x) + r.x0, int(y) + r.y0, int(x) + r.x0, int(y) + r.y0))[:2]
                    for x, y in mask_polygon(r.mask)]
            bubbles.append(CachedBubble(box=unit.normalize(r.bbox), text=r.translated_text, poly=poly, flags=list(r.flags),
                                        note=r.reader_note, angle=r.angle))
        page = CachedPage(fingerprint=unit.fingerprint, aspect=unit.aspect, bubbles=bubbles, seq=-1,
                          incomplete=any(r.status == "untranslated" for r in regions))
        page = self.cache.add(page)
        self.last_seq = page.seq
        self._save_store("cache", self.cache)

    def _apply_cached(self, unit: fp.PageUnit, page: CachedPage, live: list[TextRegion],
                      rgb: np.ndarray, areas: Sequence[BookArea] = ()) -> list[TextRegion]:
        """Attach cached translations to live bubbles (or rebuild bubbles from cached geometry); a cached bubble
        mostly inside one of *areas* (ignored on every page: `_areas_of`) is not drawn, its translation kept."""
        s = self.settings
        height, width = rgb.shape[:2]
        used: set[int] = set()
        regions: list[TextRegion] = []
        scores = bubble_scores([[unit.normalize(r.bbox)] for r in live], [cb.box for cb in page.bubbles], s.match_min_iou)
        for j, cb in enumerate(page.bubbles):
            if areas and any(a.holds(cb.box) for a in areas):
                continue
            best_i, best_iou = -1, 0.0
            for i, r in enumerate(live):
                if i in used:
                    continue
                score = scores[i][j]
                if score > best_iou:
                    best_i, best_iou = i, score
            if best_i >= 0 and best_iou > 0:
                r = live[best_i]
                used.add(best_i)
            elif not s.render_unmatched_cached:
                continue  # nothing on the live page where the cache has a bubble: a stale detection, not drawn
            else:
                bx0, by0, bx1, by1 = unit.denormalize(cb.box)
                x0, y0 = max(0, bx0), max(0, by0)
                x1, y1 = min(width, bx1), min(height, by1)
                if x1 - x0 < 4 or y1 - y0 < 4:
                    continue
                box = (x0, y0, x1, y1)
                if cb.poly:
                    pts = [(unit.denormalize((px, py, px, py))[0] - x0, unit.denormalize((px, py, px, py))[1] - y0)
                           for px, py in cb.poly]
                    mask = polygon_mask(pts, x1 - x0, y1 - y0)
                else:
                    mask = np.full((y1 - y0, x1 - x0), 255, np.uint8)
                r = TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=mask, text_box=box, kind="cached")
            take_shape(r)  # (a model's region: it was read when it was translated)
            r.translated_text = cb.text
            r.status = "translated"
            r.from_cache = True
            r.unit = unit.index
            r.flags = list(cb.flags)
            r.reader_note = cb.note
            r.angle, r.tilt = cb.angle, "set"  # (the slant it was lettered at: the cache's, never measured again)
            regions.append(r)
        known = [r for r in regions if r.status == "translated" and any(q.from_model for q in live)]
        for i, r in enumerate(live):
            if i not in used and not covered(r, known):  # (the layout model's and the classical region of one bubble)
                r.status = "unmatched"
                regions.append(r)
        self._erase_only(regions)  # (its translation, if the cache has one, kept for when it is lettered again)
        self._order_read(rgb, unit.box, regions)  # (the translations among themselves, as a fresh page's)
        return regions

    def _erase(self, out: np.ndarray, region: TextRegion, quick: bool = False) -> tuple[int, int, int]:
        """Erase *region* on the page *out*, by the inpainting model on the art (unless *quick*: an early look, soon
        replaced by the finished page), and return its paper's colour."""
        s = self.settings
        eraser = self.art_eraser  # (the window may build another meanwhile)
        erase = eraser.erase if eraser is not None and not quick else self._paper_erase
        return erase(out, region, s.erase_mode, s.white_threshold, s.dark_threshold, is_dark(region))

    @staticmethod
    def _paper_erase(image: np.ndarray, region: TextRegion, mode: str = "fill", white_threshold: int = 225,
                     dark_threshold: int = 140, dark: bool = False) -> tuple[int, int, int]:
        """`erase_region`; for a model region with no shape of its own (tier 3: its plain box, which holds the drawing
        as much as the lettering) only the lettering is painted out: where its reading found characters (`char_boxes`,
        a little grown), as lettering set on the page is, never the box. A model bubble with a classical shape also loses
        the lettering its text box holds that the shape left out (`_left_out`): a large glyph, a line by the outline.
        (Also a model region's text: a classical block may hold only part of it.)"""
        if not (region.from_model and mode == "fill"):
            return erase_region(image, region, mode, white_threshold, dark_threshold, dark)
        if region.tier != 3:
            extra = Pipeline._left_out(image, region, dark_threshold, dark)
            bg = erase_region(image, region, mode, white_threshold, dark_threshold, dark)
            if extra is not None:  # in the bubble's own paper colour (the outline guard would take a big glyph for a line)
                image[region.y0:region.y1, region.x0:region.x1][extra] = bg
            return bg
        q = copy.copy(region)
        q.kind = "text-dark" if dark else "text"  # lettering on the page: its strokes and the ground right round them
        mask = np.zeros((region.height, region.width), np.uint8)
        grow = max(2, int(CHAR_GROW * (region.glyph or 20.0)))
        if region.char_quads:  # slanted lettering: each character's own box as it is turned on the page, grown
            for quad in region.char_quads:
                pts = np.array(quad, np.float64) - (region.x0, region.y0)
                along = (pts[1] - pts[0]) / max(1e-6, float(np.hypot(*(pts[1] - pts[0]))))
                down = (pts[3] - pts[0]) / max(1e-6, float(np.hypot(*(pts[3] - pts[0]))))
                grown = pts + grow * np.array([-along - down, along - down, along + down, -along + down])
                cv2.fillPoly(mask, [np.round(grown).astype(np.int32)], 255)
        for x0, y0, x1, y1 in (() if region.char_quads else region.char_boxes):
            mask[max(0, y0 - grow - region.y0):max(0, y1 + grow - region.y0),
                 max(0, x0 - grow - region.x0):max(0, x1 + grow - region.x0)] = 255
        q.mask = mask if region.char_boxes else region.mask
        return erase_region(image, q, mode, white_threshold, dark_threshold, dark)

    @staticmethod
    def _left_out(image: np.ndarray, region: TextRegion, dark_threshold: int = 140, dark: bool = False) -> np.ndarray | None:
        """The lettering of a model region its classical mask leaves out (bool, the region's box): glyph-sized ink (at
        most `GLYPH_REACH_ERASE` glyphs long, also when it is joined `LINK_LEVELS` past the dark threshold: a thin
        outline broken by its anti-aliasing) that the model's text box holds, off the box's edge (`EDGE_KEEP` px: an
        outline); None when there is none."""
        crop = image[region.y0:region.y1, region.x0:region.x1]
        gray = cv2.cvtColor(np.ascontiguousarray(crop[..., :3]), cv2.COLOR_RGB2GRAY)
        ink = (gray > 255 - dark_threshold) if dark else (gray < dark_threshold)
        mask = region.mask if region.mask.shape == gray.shape else cv2.resize(region.mask, gray.shape[::-1], interpolation=cv2.INTER_NEAREST)
        n, labels, stats, _ = cv2.connectedComponentsWithStats((ink & (mask == 0)).astype(np.uint8), connectivity=8)
        tb = region.text_box
        tx0, ty0, tx1, ty1 = tb[0] - region.x0, tb[1] - region.y0, tb[2] - region.x0, tb[3] - region.y0
        h, w = gray.shape
        longest = GLYPH_REACH_ERASE * (region.glyph or 20.0)
        # a thin line's anti-aliasing breaks it at the dark threshold, not a little above it: a piece of a longer line
        # there is a stretch of the outline (or of the drawing), however short
        linked = (gray > 255 - dark_threshold - LINK_LEVELS) if dark else (gray < dark_threshold + LINK_LEVELS)
        nl, joined, joined_stats, _ = cv2.connectedComponentsWithStats((linked & (mask == 0)).astype(np.uint8),
                                                                        connectivity=8)
        line = np.zeros(nl, bool)
        line[1:] = np.maximum(joined_stats[1:, 2], joined_stats[1:, 3]) > longest
        out = np.zeros(gray.shape, bool)
        for i in range(1, n):
            x, y, bw, bh, area = (int(v) for v in stats[i])
            if (area < 8 or max(bw, bh) > longest or x < EDGE_KEEP or y < EDGE_KEEP or x + bw > w - EDGE_KEEP
                    or y + bh > h - EDGE_KEEP or x + bw <= tx0 or x >= tx1 or y + bh <= ty0 or y >= ty1):
                continue
            piece = labels == i
            if line[joined[piece]].any():
                continue
            out |= piece
        if not out.any():
            return None
        return cv2.dilate(out.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0

    def letter_region(self, out: np.ndarray, region: TextRegion, text: str, style: RegionStyle | None = None,
                      quick: bool = False) -> Box:
        """Erase *region* on the page *out* and letter *text* in it, in place, as `_render` does for each region
        (for a page that fills in region by region); returns the part of the page that changed: the region's box,
        grown where the lettering runs past it. *style* formats the lettering in place of the region's own (the
        region editor's preview; an empty one: automatic). *quick*: see `_erase`."""
        return self._letter_region(out, region, text, style, quick)[0]

    def _letter_region(self, out: np.ndarray, region: TextRegion, text: str,
                       style: RegionStyle | None = None, quick: bool = False) -> tuple[Box, Lettered]:
        """`letter_region`, and what the lettering did (its size, what it could not do as formatted)."""
        s = self.settings
        h, w = out.shape[:2]
        x0, y0 = max(0, region.x0 - region.width), max(0, region.y0 - region.height)
        x1, y1 = min(w, region.x1 + region.width), min(h, region.y1 + region.height)
        before = out[y0:y1, x0:x1].copy()
        bg = self._erase(out, region, quick)
        local = copy.copy(region)  # the region as seen from the corner of the part of the page around it
        local.x0, local.y0, local.x1, local.y1 = region.x0 - x0, region.y0 - y0, region.x1 - x0, region.y1 - y0
        local.text_box = _shift(region.text_box, -x0, -y0)
        local.letter_box = _shift(region.letter_box, -x0, -y0) if region.letter_box is not None else None
        local.panel = _shift(region.panel, -x0, -y0) if region.panel is not None else None
        around = Image.fromarray(out[y0:y1, x0:x1].copy())
        done = self._set_text(around, local, text, bg, region.style if style is None else style)
        out[y0:y1, x0:x1] = np.asarray(around)
        ys, xs = np.nonzero(np.any(out[y0:y1, x0:x1] != before, axis=2))
        box = region.bbox
        if xs.size:
            box = _union(box, (x0 + int(xs.min()), y0 + int(ys.min()), x0 + int(xs.max()) + 1, y0 + int(ys.max()) + 1))
        return box, done

    def region_lettering(self, text: str, kind: str = "", style: RegionStyle | None = None) -> tuple[Lettering, tuple[str, ...]]:
        """The lettering a region of *kind* is set in (`lettering_for`) as *style* formats it - its font family,
        where this computer has it and it has the glyphs of *text*, bold and italic forced on or off, the letter
        spacing - and what could not be done as asked: "font-missing" (the family is not installed here) or
        "font-glyphs" (it lacks letters of *text*); the lettering's own font is used then."""
        lettering = self.lettering_for(text, kind)
        if style is None or style.formats_nothing:
            return lettering, ()
        s = self.settings
        flags: tuple[str, ...] = ()
        if style.font:
            spec = resolve_font(style.font, s.fonts_dir)
            if not spec:
                flags = ("font-missing",)
            elif not covers(spec.path, strip_marks(text)):
                flags = ("font-glyphs",)
            else:
                lettering = make_lettering(spec, str(s.fonts_dir), lettering.italic, lettering.bold)
        return lettering.formatted(style.italic, style.bold, style.letter_spacing), flags

    def _set_text(self, image: Image.Image, region: TextRegion, text: str, background: tuple[int, int, int],
                  style: RegionStyle | None, scaled: bool = True) -> Lettered:
        """Letter *text* in *region* on *image* (erased already, *background* its colour): the one place a region's
        text is typeset, in the lettering of its kind as the series sheet gives it, formatted as the reader set it
        in the region editor (*style*; None or an empty one: the automatic lettering), at the slant the reader set
        there or else its own (`TextRegion.angle`: the lines in the region's own frame, `render.slant`), in the text
        direction set there (`RegionStyle.direction`: across, turned a quarter, or stacked), in the ink set there or
        else the one the sheet gives its kind (`annotations.ink_of`: the text colour, the outline and its colour, each
        automatic when neither sets it); with *scaled* at the lettering size (`_scaled_top`; `cap_sizes` measures the
        page's sizes without it, as they fit)."""
        s = self.settings
        colour, outline, outline_colour = ink_of(style, self.kind_lettering(region.tag))
        lettering, flags = self.region_lettering(text, region.tag, style)
        text = drawable(lettering.path, text)
        large = self._display_size()
        region = _art_room(region, image.size if image is not None else None, large)
        fmt = None if style is None or style.formats_nothing else TextFormat(style.align, style.valign, style.size,
                                                                           style.line_spacing, style.condense)
        if style is not None and style.slant is not None and style.slant != region.angle:
            region = copy.copy(region)
            region.angle = style.slant
        capped = region.size_cap and region.tag not in UNCAPPED_KINDS  # the reader may just have called it a shout
        top = min(s.max_font_size, region.size_cap) if capped else s.max_font_size
        direction = style.direction if style is not None else ""
        if scaled and (fmt is None or not fmt.size):  # (a size the reader set is kept as set)
            top = self._scaled_top(region, text, lettering, top, background, fmt, direction)
        done = letter_text(image, region, text, lettering, s.min_font_size, top, s.line_spacing, s.uppercase,
                           background, False, s.target_language, outline, fmt=fmt, direction=direction,
                           color=ink_rgb(colour), outline_color=ink_rgb(outline_colour))
        return Lettered(done.size, flags + done.flags, done.won)

    def _scaled_top(self, region: TextRegion, text: str, lettering: Any, top: int, background: tuple[int, int, int],
                    fmt: TextFormat | None, direction: str) -> int:
        """The largest size *text* may be set at in *region* with the lettering size (`Settings.text_scale`, the
        book's own when it has one) applied to *top*, the largest it may be set at as it fits: under 1.0 the size it
        would be set at (found without drawing) times the scale, over 1.0 *top* times the scale (the bubble still
        holds it to what fits), within ``min_font_size`` and ``max_font_size``. At 1.0 *top* itself, nothing done."""
        s = self.settings
        scale = float(s.text_scale)
        if scale == 1.0:
            return top
        if scale > 1.0:
            return max(s.min_font_size, min(s.max_font_size, round(top * scale)))
        size = letter_text(None, region, text, lettering, s.min_font_size, top, s.line_spacing, s.uppercase,
                           background, False, s.target_language, fmt=fmt, direction=direction).size
        return max(s.min_font_size, min(top, round(size * scale))) if size else top

    def _display_size(self) -> float:
        """The glyph size from which lettering on the page is display lettering (`_art_room`): `LARGE_LETTERING` times
        the book's usual character size so far (`_book_sizes`), and never under that many times the readable size."""
        s = self.settings
        usual = float(np.median(self._book_sizes)) if self._book_sizes else 0.0
        return LARGE_LETTERING * max(usual, s.readable_font_size, s.min_font_size)

    def cap_sizes(self, regions: Sequence[TextRegion], texts: Sequence[str]) -> None:
        """Keep the sizes of a page alike: each of *regions* gets the largest size it may be set at (`page_caps`) from
        what all of them, with *texts*, fit at in automatic lettering, so that the reader's formatting of one changes
        that one alone (a size the reader set is never capped). Kept on the region, so that one lettered on its own
        later comes out as on its page. Display lettering on the art that takes a room of its own (`_art_room`) counts
        as a shout: as large as it fits, and out of the sizes the page's speech is held to."""
        for r in regions:
            r.size_cap = 0
        large = self._display_size()
        sized = [(DISPLAY_KIND if _art_room(r, None, large) is not r else r.tag,
                  self._set_text(None, r, t, (255, 255, 255), None, scaled=False).size, r.glyph)
                 for r, t in zip(regions, texts)]
        for r, cap in zip(regions, page_caps(sized, self.settings.readable_font_size)):
            r.size_cap = cap

    def _render(self, out: np.ndarray, regions: list[TextRegion], record: bool = True, recap: bool = True,
                quick: bool = False) -> None:
        """Erase every translated region of *regions* on the page *out* and letter its translation, in place (a region
        made "erase only", `ERASED`, is erased and nothing set); with
        *record*, each region keeps the size it was set at and what its lettering could not do as formatted, and with
        *recap* too the sizes of the page are kept alike anew (`cap_sizes`). A region's erase comes from the erased
        pages of a run (`erased_ahead`) or this session's erases (`erased_regions`) when one of them holds it (its
        `erase_key`), else it is done here and kept in `erased_regions`; *quick*: the paper fill in place of the
        inpainting model (`_erase`; an early look, not kept)."""
        s = self.settings
        backgrounds: dict[int, tuple[int, int, int]] = {}
        todo = [i for i, r in enumerate(regions) if erases(r)]
        keys = [self.erase_key(out, regions[i]) for i in todo]
        ahead = self._erased_for(out, [regions[i] for i in todo], keys)
        place = {i: n for n, i in enumerate(todo)}
        for i, r in enumerate(regions):
            if i in place:
                n = place[i]
                hit = ahead.get(n) if ahead else None
                if hit is not None:  # erased ahead: the same erase, done already
                    erased, page = hit
                    erased.paste(out, page())
                    erased.settle(r)
                    backgrounds[i] = erased.background
                else:
                    kept = self.erased_regions.take(keys[n], out)
                    if kept is not None:  # erased so before this session: the same erase
                        kept.settle(r)
                        backgrounds[i] = kept.background
                    elif quick:
                        backgrounds[i] = self._erase(out, r, quick=True)
                    else:
                        backgrounds[i] = self._erase_kept(out, r, keys[n])
                if r.status == ERASED:  # erased, nothing set
                    del backgrounds[i]
                    if record:
                        r.letter_flags = ()
            elif record:
                r.letter_flags = ()
        if not backgrounds:
            return
        if record and recap:
            self.cap_sizes([regions[i] for i in backgrounds], [regions[i].translated_text for i in backgrounds])
        pil = Image.fromarray(out)
        for i, bg in backgrounds.items():
            r = regions[i]
            done = self._set_text(pil, r, r.translated_text, bg, r.style)
            if record:
                r.font_size, r.letter_flags = done.size, done.flags
        out[:] = np.asarray(pil)

    def _erased_for(self, page: np.ndarray, regions: Sequence[TextRegion], keys: Sequence[bytes] | None = None
                    ) -> dict[int, tuple[ErasedRegion, Callable[[], np.ndarray]]]:
        """Of *regions*, about to be erased on *page* (untouched yet), those an erased page in `erased_ahead` holds:
        index -> (what erasing it did, the erased page's pixels). Counted on the store (``reused``, ``erased_live``).
        *keys*: the regions' `erase_key`s, when they are known already."""
        store = self.erased_ahead
        if store is None or not regions:
            return {}
        found = store.find(list(keys) if keys is not None else [self.erase_key(page, r) for r in regions], page.shape)
        store.reused += len(found)
        store.erased_live += len(regions) - len(found)
        return found

    def _erase_reach(self, out: np.ndarray, r: TextRegion) -> tuple[int, int, int, int]:
        """The part of the page *out* erasing *r* may change: `ERASE_REACH` round its box, and with the inpainting
        model the window it sees and may fill in."""
        h, w = out.shape[:2]
        reach = self.ERASE_REACH
        x0, y0 = max(0, r.x0 - reach), max(0, r.y0 - reach)
        x1, y1 = min(w, r.x1 + reach), min(h, r.y1 + reach)
        if self.art_eraser is not None:  # what LaMa sees, and may fill in
            bx0, by0, bx1, by1 = artwork.box_of(out, r)
            wx0, wy0, wx1, wy1 = artwork.window(out.shape, bx0, by0, by1 - by0, bx1 - bx0)
            x0, y0, x1, y1 = min(x0, wx0), min(y0, wy0), max(x1, wx1), max(y1, wy1)
        return x0, y0, x1, y1

    def _erased_record(self, out: np.ndarray, r: TextRegion, key: bytes
                       ) -> tuple[tuple[int, int, int], ErasedRegion, np.ndarray | None]:
        """Erase *r* on *out* in place (`_erase`), and what that did (`ErasedRegion` under *key*, its `erase_key` on the
        page before any erase), with the mask of the pixels it changed in its box (None: none); *r* itself is erased as
        the render erases it (its mask may be cut back)."""
        x0, y0, x1, y1 = self._erase_reach(out, r)
        before = out[y0:y1, x0:x1].copy()
        mask = r.mask
        background = self._erase(out, r)
        (cx0, cy0, cx1, cy1), part = changed_pixels(before, out[y0:y1, x0:x1])
        box = (x0 + cx0, y0 + cy0, x0 + cx1, y0 + cy1) if part is not None else (0, 0, 0, 0)
        changed = np.packbits(part.ravel()).tobytes() if part is not None else b""
        new_mask, shape = packed_mask(mask, r.mask)
        bg = tuple(int(c) for c in background)
        record = ErasedRegion(key, bg, box, changed, new_mask, shape)  # type: ignore[arg-type]
        return bg, record, part

    def _erase_kept(self, out: np.ndarray, r: TextRegion, key: bytes) -> tuple[int, int, int]:
        """Erase *r* on *out* (`_erased_record`) and keep what that did in `erased_regions`; its paper colour."""
        background, record, part = self._erased_record(out, r, key)
        self.erased_regions.put(record, out, part)
        return background

    ERASE_KEY_MARGIN = 16  # px round a region's box (and a tenth of its short side) whose pixels its erase key holds
    ERASE_REACH = 64  # px past a region's box its paper fill is looked for changes in (it stays inside the box)

    def erase_key(self, page: np.ndarray, region: TextRegion) -> bytes:
        """What a region's erase depends on, as a key: the settings of the erase (the mode, the thresholds, whether LaMa
        erases on the art), the region (its boxes, kind, shape, mask, a model region's characters) and the page's
        pixels in its box and `ERASE_KEY_MARGIN` round it. Two regions with one key erase alike (LaMa also looks further
        out, as context: a toolbar there changes nothing of what it fills in that matters)."""
        s = self.settings
        eraser = self.art_eraser
        m = self.ERASE_KEY_MARGIN + min(region.width, region.height) // 10
        h, w = page.shape[:2]
        crop = page[max(0, region.y0 - m):min(h, region.y1 + m), max(0, region.x0 - m):min(w, region.x1 + m)]
        return region_digest(page.shape, s.erase_mode, s.white_threshold, s.dark_threshold,
                             eraser.setting if eraser is not None and not eraser.failed else "",
                             region.bbox, region.text_box, region.letter_box, region.kind, region.tier,
                             region.from_model, region.glyph, list(region.char_boxes), is_dark(region),
                             np.asarray(region.mask), crop,
                             *(("slant", region.angle, region.char_quads) if region.char_quads else ()))

    def erase_page(self, page: np.ndarray | Image.Image, regions: Sequence[TextRegion],
                   cancel: threading.Event | None = None) -> tuple[np.ndarray, list[ErasedRegion]]:
        """*page* with *regions* erased in their order, as `_render` erases them (`_erase`: the paper fill, and LaMa on
        the art when the settings have it), and for each region what its erase did (`ErasedRegion`, found again by
        `erase_key` taken on the page before any erase, as the render takes it). The regions are erased as copies:
        nothing of them changes. Once *cancel* is set, `Cancelled` is raised between regions."""
        out = np.array(page.convert("RGB") if isinstance(page, Image.Image) else page, dtype=np.uint8, copy=True)
        keys = [self.erase_key(out, r) for r in regions]
        records: list[ErasedRegion] = []
        for region, key in zip(regions, keys):
            check_cancel(cancel)
            records.append(self._erased_record(out, copy.copy(region), key)[1])
        return out, records

    def page_without(self, result: PageResult, region: TextRegion) -> np.ndarray:
        """*result*'s page lettered as `rerender` letters it, but for *region*, which is left as it was captured:
        what the region editor's preview letters the region on (nothing on the regions is changed)."""
        out = np.asarray(result.original).copy()
        self._render(out, [r for r in result.regions if r is not region], record=False)
        return out

    def preview_region(self, page: np.ndarray, region: TextRegion, text: str,
                       style: RegionStyle | None) -> tuple[np.ndarray, Lettered]:
        """A copy of *page* (`page_without`) with *region* erased and *text* lettered in it as *style* formats it
        (an empty style: automatic), and what the lettering did: the region editor's live preview. Nothing is
        stored, and the region is not changed."""
        out = page.copy()
        _box, done = self._letter_region(out, region, text, RegionStyle() if style is None else style)
        return out, done


# A reply's own loop. A translation may stretch a word
# ("Aaaaaah", seven letters in a row at most in the 11,604 lines stored on the test machine, 29 of them past the
# reading's limit of four) and a line said over and over stays that in any language.
REPLY_RUN = 12  # one character repeated more than this, and more than twice as often as in the Japanese
REPLY_LOOP_CHARS = 30  # the shortest reply judged by its repeated pieces ("Ha ha ha ha" is a laugh)


def repeated_pieces(text: str) -> bool:
    """Whether more than half of *text*'s three-character pieces are repeats."""
    t = "".join(ch for ch in text if not ch.isspace())
    if len(t) < 6:
        return False
    grams = [t[i:i + 3] for i in range(len(t) - 2)]
    return len(set(grams)) < 0.5 * len(grams)


def looping_reply(output: str, source: str = "") -> bool:
    """Whether a translation of *source* is the model running in a loop: one character repeated far past any
    stretched word and past the Japanese, or a long reply mostly of repeated pieces that the Japanese does not
    repeat itself."""
    t = "".join(ch for ch in output if not ch.isspace())
    if _longest_run(t) > max(REPLY_RUN, 2 * _longest_run(source)):
        return True
    return len(t) >= REPLY_LOOP_CHARS and repeated_pieces(t) and not repeated_pieces(source)


def _longest_run(text: str) -> int:
    best = run = 0
    last = ""
    for ch in text:
        run = run + 1 if ch == last else 1
        last = ch
        best = max(best, run)
    return best
SPLIT_CONFIDENCE = OCR_UNSURE - 0.01  # a region's confidence when the readers gave three different lines: flagged "ocr"
BEYOND_CONFIDENCE_DROP = 0.1  # how much the OCR's confidence may fall when a column taken in past the interior is read too


def extends_reading(with_column: str, without: str) -> bool:
    """True when the reading *with_column* is the reading *without* it plus at least two more characters: the
    column added text, and the rest still reads the same."""
    if len(with_column) < len(without) + 2:
        return False
    if not without:
        return True
    match = SequenceMatcher(None, with_column, without, autojunk=False).find_longest_match(0, len(with_column), 0, len(without))
    return match.size >= 0.7 * len(without)


def _tag(entry: dict[str, Any]) -> str:
    """The reader's kind of a tighten/review entry (its "meta" carries the facts given to the model)."""
    return str((entry.get("meta") or {}).get("kind", ""))


def manual_region(rgb: np.ndarray, box: Box, dark_threshold: int = 140) -> TextRegion:
    """A text region for a rectangle the reader drew: the whole rectangle is erased and lettered."""
    x0, y0, x1, y1 = box
    crop = rgb[y0:y1, x0:x1]
    gray = crop.mean(axis=2) if crop.ndim == 3 else crop
    dark = float(gray.mean()) < dark_threshold if gray.size else False
    mask = np.full((y1 - y0, x1 - x0), 255, np.uint8)
    return TextRegion(x0=x0, y0=y0, x1=x1, y1=y1, mask=mask, text_box=box, kind="manual-dark" if dark else "manual")


_POOL: list[ThreadPoolExecutor] = []
_ON_SHOW = threading.local()  # the capture `process` detects on this thread now, and its units
_POOL_LOCK = threading.Lock()


def _detect_pool() -> ThreadPoolExecutor:
    """The worker the classical detectors of a page on show run in beside the layout model (`Pipeline._detect`)."""
    with _POOL_LOCK:
        if not _POOL:
            _POOL.append(ThreadPoolExecutor(max_workers=2, thread_name_prefix="taslation-detect"))
        return _POOL[0]


def _units_before(rgb: np.ndarray, margins: tuple[int, int, int, int]) -> Callable[[], list[fp.PageUnit]]:
    """The units of the capture *rgb* as analyze found them before 2026-10-31 (``grow=False``), made the first time
    they are asked for (a unit's lookup that missed: `Pipeline._lookup`) and kept for the capture's other units."""
    return functools.cache(lambda: fp.analyze(rgb, margins, grow=False))


def _inside_unit(old: Box, unit: Box) -> bool:
    """Whether the box *old* (a unit as found before 2026-10-31) lies in *unit*: its centre within it, and at least
    80 % of its area."""
    cx, cy = (old[0] + old[2]) / 2, (old[1] + old[3]) / 2
    if not (unit[0] <= cx <= unit[2] and unit[1] <= cy <= unit[3]):
        return False
    w, h = max(0, min(old[2], unit[2]) - max(old[0], unit[0])), max(0, min(old[3], unit[3]) - max(old[1], unit[1]))
    area = max(1, (old[2] - old[0]) * (old[3] - old[1]))
    return w * h >= 0.8 * area


def _moved(bubble: CachedBubble, old: Box, unit: Box) -> CachedBubble:
    """*bubble*, normalised to the box *old*, normalised to *unit* instead (both boxes in one capture)."""
    ow, oh = old[2] - old[0], old[3] - old[1]
    uw, uh = max(1, unit[2] - unit[0]), max(1, unit[3] - unit[1])

    def point(x: float, y: float) -> tuple[float, float]:
        return (old[0] + x * ow - unit[0]) / uw, (old[1] + y * oh - unit[1]) / uh

    x0, y0 = point(bubble.box[0], bubble.box[1])
    x1, y1 = point(bubble.box[2], bubble.box[3])
    return replace(bubble, box=(x0, y0, x1, y1), poly=[point(x, y) for x, y in bubble.poly],
                   flags=list(bubble.flags))


def unit_for(units: Sequence[fp.PageUnit], box: Box, capture: Box | None = None,
             named: int | None = None) -> fp.PageUnit | None:
    """The page unit a region at *box* (capture coordinates) belongs to.

    A region that names its unit (*named*: the index of the unit a reader's rectangle was stored under) keeps it.
    Otherwise it is the unit whose box holds the region's centre. A unit is cropped to the page's ink and can stop
    short of the page (the page's black panels at the viewer's own level), so a centre anywhere else in the capture
    area *capture* (None: anywhere at all) goes to the unit whose columns hold it, else to the nearest unit sideways.
    None outside the capture area, where only the viewer's own lettering is, and without units."""
    if not units:
        return None
    if named is not None:
        for unit in units:
            if unit.index == named:
                return unit
    centre = _center(box)
    for unit in units:
        if _inside(unit.box, centre):
            return unit
    if capture is not None and not _inside(capture, centre):
        return None
    x = centre[0]
    for unit in units:
        if unit.box[0] <= x < unit.box[2]:
            return unit
    return min(units, key=lambda u: max(u.box[0] - x, x - u.box[2]))


def _plain(r: TextRegion) -> bool:
    """A model region with no shape of its own: its plain box."""
    return r.from_model and r.tier == 3


def _same_lettering(a: TextRegion, b: TextRegion) -> bool:
    """Whether two regions read as text letter the same place: one took its shape from the other, or their lettering
    boxes share `LETTERING_SHARED` of the smaller; `COVERED` (`detect.layout`) is enough between a plain box and a
    shaped region (the plain box is the same lettering seen roughly)."""
    if a.adopted is b or b.adopted is a:
        return True
    la, lb = a.letter_box or a.text_box, b.letter_box or b.text_box
    ix0, iy0, ix1, iy1 = max(la[0], lb[0]), max(la[1], lb[1]), min(la[2], lb[2]), min(la[3], lb[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return False
    shared = (ix1 - ix0) * (iy1 - iy0)
    need = layout_model.COVERED if _plain(a) != _plain(b) else LETTERING_SHARED
    return shared >= need * min(max(1, (la[2] - la[0]) * (la[3] - la[1])), max(1, (lb[2] - lb[0]) * (lb[3] - lb[1])))


LETTERING_SHARED = 0.5  # of the smaller lettering box: two lettering boxes this much on each other letter one place
SHARED_MOST = 0.5  # IoU: a pairing that shares more than half the union is the one bubble, whatever else lies near
CONTAINED = 0.9  # of the smaller box: a stored bubble and a live region one of which lies this much in the other


def _contains(a: Any, b: Any) -> bool:
    """Whether the smaller of two boxes lies all but wholly (`CONTAINED`) in the larger."""
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return False
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return smaller > 0 and (ix1 - ix0) * (iy1 - iy0) >= CONTAINED * smaller


def bubble_scores(live: Sequence[Sequence[Any]], stored: Sequence[Any], least_iou: float) -> list[list[float]]:
    """How well each live region (its box and those of the regions it stands for, normalised as the stored boxes)
    matches each stored bubble: the IoU where it reaches *least_iou*. Below it, one box lying within the other (the
    layout model's box of a bubble and a classical detector's, either way round) is the same bubble only when it is
    the one pairing of either: neither the live region nor the stored bubble lies so on another (two bubbles the
    detector now takes for one, one bubble it now cuts in two, are other bubbles than were stored: read again). Such
    a match scores below every IoU match; 0 is none. Where either has more than one such counterpart, only an IoU of
    `SHARED_MOST` counts (more than half of the two boxes' union is shared: that one is the bubble)."""
    iou = [[max((box_iou(b, s) for b in boxes), default=0.0) for s in stored] for boxes in live]
    inside = [[iou[i][j] < least_iou and any(_contains(b, s) for b in boxes) for j, s in enumerate(stored)]
              for i, boxes in enumerate(live)]
    related_live = [sum(1 for j in range(len(stored)) if inside[i][j] or iou[i][j] >= least_iou) for i in range(len(live))]
    related_stored = [sum(1 for i in range(len(live)) if inside[i][j] or iou[i][j] >= least_iou) for j in range(len(stored))]
    def score(i: int, j: int) -> float:
        alone = related_live[i] == 1 and related_stored[j] == 1
        if iou[i][j] >= least_iou:
            return iou[i][j] if alone or iou[i][j] >= SHARED_MOST else 0.0
        return least_iou * 1e-3 * (1 + iou[i][j]) if inside[i][j] and alone else 0.0

    return [[score(i, j) for j in range(len(stored))] for i in range(len(live))]


def stored_unit(region: TextRegion) -> int | None:
    """The page unit a reader's rectangle (a "manual" region) was stored under, as `Pipeline._annotate` and
    `Pipeline.move_region` set it; None for a region the detection found."""
    return region.unit if region.kind.startswith("manual") else None


def takes_items(translator: Any) -> bool:
    """Whether the translator's translate_page hands each translation over as it comes (an `on_item` argument)."""
    try:
        return "on_item" in inspect.signature(translator.translate_page).parameters
    except (AttributeError, TypeError, ValueError):
        return False


def cancel_args(method: Any, cancel: threading.Event | None, on_slow: SlowFn | None) -> dict[str, Any]:
    """The ``cancel`` and ``on_slow`` arguments for a translator's *method*, those of them it takes (a translator
    may leave them out) and that are given."""
    out: dict[str, Any] = {}
    if cancel is not None and accepts(method, "cancel"):
        out["cancel"] = cancel
    if on_slow is not None and accepts(method, "on_slow"):
        out["on_slow"] = on_slow
    return out


def summary(result: PageResult) -> Message:
    """A finished page's line: ``pipeline.from_cache`` (every page unit came from the cache) or
    ``pipeline.translated``, {bubbles, seconds, cached, new (page units from the cache / read now), review (the
    regions flagged for review), error (the Message of what went wrong, or "")}; ``pipeline.no_content`` when the
    capture showed no page, ``pipeline.no_text`` when the page has nothing to translate."""
    if not result.fingerprints:
        return Message("pipeline.no_content")
    if not result.translated and not result.error:
        if any(r.status == "ocr-unavailable" for r in result.regions):  # text was found, and nothing can read it
            return Message("ocr.model_missing", path="")
        return Message("pipeline.no_text")
    cached = bool(result.cache_hits and not result.cache_misses)
    return Message("pipeline.from_cache" if cached else "pipeline.translated", bubbles=len(result.translated),
                   seconds=round(sum(result.timings.values()), 1), cached=result.cache_hits, new=result.cache_misses,
                   review=sum(1 for r in result.regions if getattr(r, "flags", None)), error=result.error or "")


def _glyph_of(r: TextRegion) -> float:
    """The size of a region's original lettering: the detector's measure, and for a layout model's region its
    reading's largest character too (a classical block it took its shape from may have measured a dot or a mark)."""
    return max(r.glyph, r.char_size) if r.from_model else r.glyph


def _art_room(r: TextRegion, page: tuple[int, int] | None = None, large: float = 0.0) -> TextRegion:
    """The room a layout model's single line of lettering set on the page is lettered in (one column or row: its
    glyph, `_glyph_of`, at least `ONE_LINE` of the lettering box's short side): its box with the short side grown
    towards the long one by up to `ROOM_GLYPHS` glyphs, each side by no more than its own width and within *page*
    (width, height) when given, so that a column of big lettering takes its translation, set across, at a size near
    its own, when its glyph is *large* px or more (display lettering: a column of small lettering stays in its room,
    which the drawing holds close); a closed block (lettering in an enclosure of its own: a bubble's interior, a
    caption's frame, or big lettering ringed by white) only at `ENCLOSED_LARGE` times that. The room grows no further
    than the edge of the region's panel either (`TextRegion.panel`), when the region lies at least `PANEL_SURE` inside
    that panel's box: lettering grown past a frame lies on the next panel's drawing. Only the lettering's room grows:
    its erase is done. Any other region is returned as it is (a bubble has its interior)."""
    if not r.from_model or r.kind not in ON_ART_KINDS:
        return r
    glyph = _glyph_of(r)
    lb = r.letter_box or r.text_box
    if glyph < ONE_LINE * min(lb[2] - lb[0], lb[3] - lb[1]) or glyph < max(1.0, large) * (
            1.0 if r.kind in LOOSE_KINDS else ENCLOSED_LARGE):
        return r
    w, h = r.width, r.height
    grow = ROOM_GLYPHS * glyph
    gx = int(min(max(0, h - w), grow) / 2) if h > w else 0
    gy = int(min(max(0, w - h), grow) / 2) if w > h else 0
    gx, gy = min(gx, w), min(gy, h)
    x0, y0, x1, y1 = r.x0 - gx, r.y0 - gy, r.x1 + gx, r.y1 + gy
    if page is not None:
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(page[0], x1), min(page[1], y1)
    p = r.panel
    if p is not None and _area(_meet(r.bbox, p)) >= PANEL_SURE * _area(r.bbox):  # grown up to the panel's edge
        x0, y0 = max(x0, min(r.x0, p[0])), max(y0, min(r.y0, p[1]))
        x1, y1 = min(x1, max(r.x1, p[2])), min(y1, max(r.y1, p[3]))
    if (x0, y0, x1, y1) == r.bbox:
        return r
    q = copy.copy(r)
    q.x0, q.y0, q.x1, q.y1 = x0, y0, x1, y1
    mask = r.mask if r.mask.shape == (h, w) else cv2.resize(r.mask, (w, h), interpolation=cv2.INTER_NEAREST)
    q.mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
    q.mask[r.y0 - y0:r.y1 - y0, r.x0 - x0:r.x1 - x0] = mask
    # the room's band across the lettering: its own rows (columns), the full width
    band = (x0, lb[1], x1, lb[3]) if h > w else (lb[0], y0, lb[2], y1)
    q.mask[band[1] - y0:band[3] - y0, band[0] - x0:band[2] - x0] = 255
    return q


def _shift(box: Box, dx: int, dy: int) -> Box:
    return (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)


def _meet(a: Box, b: Box) -> Box:
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def _area(box: Box) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _union(a: Box, b: Box) -> Box:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _center(box: Box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _inside(box: Box, point: tuple[float, float]) -> bool:
    return box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]
