"""Reader-made premises: where the text is, who says it, what things are called, how the book should read.

Text-only files kept on the reader's own machine. None of them contains a line
of the book or a translation of one; they hold structure and facts that help
the model, which still produces every translation on the reader's machine:

* **Annotations** per book (``~/.taslation/annotations/<book>.json``). Per page
  (identified by its fingerprint): rectangles marked as text the detector
  misses ("add") or as places where it is wrong ("ignore"); per region a
  speaker, a kind (speech, thought, shout, narration, sfx, handwritten),
  whether its sentence continues in the next bubble, a short remark (a pun,
  who is addressed), and how the reader formatted its lettering in the region
  editor (`RegionStyle`: alignment, font family, size, bold, italic, line and
  letter spacing, slant, text direction, text colour, outline and its colour);
  the reading order of the regions; whether the whole page is
  skipped (an advertisement).
  Per book: detection settings that suit the book, the sequence of page
  fingerprints, the reading direction, and the areas the reader ignores on
  every page of it (`BookArea`: a watermark, a page number, a banner).
* **Series sheet** per series (``~/.taslation/glossary/<series>[.<language>].json``):
  the glossary (terms as written in the book with the rendering to use), the
  character sheet (gender, age, first-person pronoun, speech style, role, how
  they address others) and a style guide (honorifics, tone, house rules, the
  lettering font, and per kind of text its font, faces and ink: `LetteringStyle`).

Each file records the book (or the series and language) it belongs to; when the
plain file name holds another one whose name gives the same file name, the file
is ``<book>-<hash>.json`` (``<series>-<hash>[.<language>].json``) instead
(`names.py`). Each is written protected at rest, so that only the Windows user
who saved it can open it, on this computer (`protect.py`; a plain file of an
earlier version is read as it is). Neither has an export: they stay on the
computer they were made on. A file this version cannot read (damaged, written
by a newer TASlation, or protected for another Windows user or computer) is
kept beside as ``<file stem>.unreadable-<date>.json`` before a fresh one takes
its place, never written over (`names.set_aside`).

Two series sheets can be compared (`compare_sheets`): when a rename joins a
book's sheet to the sheet the new series has already (`rename.py`), what the
book's sheet adds is taken over as it is, and where the two say otherwise (a
term's rendering or note, a character's fact or how they call someone, a policy
of the style guide, the lettering of a kind) is a `Conflict` the reader answers
(keep the series' value, or take the book's: `apply_review`).
"""

from __future__ import annotations

import copy
import json
import math
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from . import protect
from .config import TEXT_SCALE_RANGE
from .fingerprint import FINGERPRINT_HEX_LEN, hamming
from .names import StoreFiles, load_object, read_object
from .regions import box_iou
from .textclean import clean_text

SCHEMA_VERSION = 1
NBox = tuple[float, float, float, float]
NOTE = ("Reader-made premises: where text is on pages identified by fingerprints, who speaks, how names and terms are "
        "rendered, how the book should read. No page images, no page text, no translations.")
# what kind of text a region is (a premise the model is told); "erase" is no text to translate: the lettering is
# erased and nothing is set in its place (`ERASE_ONLY`; the pipeline gives such a region the status "erase")
ERASE_ONLY = "erase"
REGION_KINDS = ("", "speech", "thought", "shout", "narration", "sfx", "handwritten", ERASE_ONLY)
HONORIFIC_POLICIES = ("", "keep", "drop", "adapt")
LETTERING_KINDS = ("thought", "shout", "narration", "handwritten", "sfx")  # kinds whose lettering a sheet may style
READING_DIRECTIONS = ("", "rtl", "ltr")
# detection and OCR settings a book may override, and the size of its lettering (never anything network related)
BOOK_SETTING_KEYS = (
    "white_threshold", "dark_threshold", "min_bubble_area_ratio", "max_bubble_area_ratio", "min_bubble_size",
    "min_short_bubble", "ocr_min_confidence", "detect_text_blocks", "detect_dark_bubbles", "split_joined_bubbles", "take_columns_beyond", "translate_sfx",
    "erase_mode", "art_erase", "detect_model", "text_scale", "max_font_size",
)
BOOK_SETTING_BOUNDS = {"text_scale": TEXT_SCALE_RANGE, "max_font_size": (4, 200)}  # a number out of them is left out
# bounds on what a file is read with (a volume with every page annotated stays far below them)
MAX_PAGES = 5000
MAX_BOXES_PER_PAGE = 200
MAX_TERMS = 2000
MAX_CHARACTERS = 500
# a region's formatting (`RegionStyle`): where its lines sit, and the bounds of its numbers
ALIGNS = ("left", "center", "right")
VALIGNS = ("top", "middle", "bottom")
STYLE_SIZES = (4, 200)  # a fixed font size, in the pixels the lettering is set in
LINE_SPACINGS = (0.5, 4.0)  # times the font size
LETTER_SPACINGS = (-10, 50)  # pixels between two characters
DIRECTIONS = ("", "horizontal", "down", "up", "stacked")  # a region's text direction ("": Auto, horizontal)
SLANTS = (-89.0, 89.0)  # degrees the lettering may be turned counter-clockwise (the cache and `render.slant` take |angle| < 90)
# a text or outline colour (`RegionStyle.colour`, `LetteringStyle.colour`): automatic (""), black, white, or a colour of
# the reader's as "#rrggbb" (`ink_code`)
INK_NAMES = ("", "black", "white")
STORE_KINDS = ("annotations", "glossary")
CONFLICT_AREAS = ("term", "character", "style")  # what two series sheets may say otherwise (`compare_sheets`)
CHARACTER_FIELDS = ("rendering", "gender", "age", "pronoun", "style", "role")
STYLE_FIELDS = ("honorifics", "tone", "font")  # the style guide's policies compared one by one (and the lettering)
# whose a store file is (`names.StoreFiles`): an annotations file records the book, a series sheet its series and
# language; each says its schema number and its kind
ANNOTATION_FILES = StoreFiles("the annotations", "book", schema=SCHEMA_VERSION, kind="annotations")
SHEET_FILES = StoreFiles("the series sheet", "series", "language", schema=SCHEMA_VERSION, kind="glossary")


# An area the reader ignores on every page of the book (`BookArea`): made from a region they dropped, grown a little
# so that the same mark found a little larger or a little off on another page still lies in it.
AREA_SIDES = ("", "right", "left")  # every page; the pages on that side of a two-page spread (and pages shown alone)
AREA_INSIDE = 0.7  # a region with this share of its box's area inside an area is not looked at (`BookArea.holds`)
AREA_MARGIN = 0.25  # the area: the dropped region's box grown by this share of its width and height on each side ...
AREA_MIN_MARGIN = 0.01  # ... and by at least this share of the page's
AREA_ASPECT = 0.12  # an area applies to the pages whose width / height is within this share of its page's
MAX_AREAS = 50


# How far outside its page unit a region's box may lie, in the unit's own terms: a unit is cropped to its page's ink
# and can stop short of the page (black at the viewer's own level), and every region belongs to one
# (`pipeline.unit_for`), so a box below a unit cut short reaches past 1 - a reader's file holds one at y 1.71.
NBOX_REACH = (-1.0, 2.0)


def _nbox(values: Any) -> NBox:
    box = tuple(float(v) for v in values)
    lo, hi = NBOX_REACH
    if len(box) != 4 or not all(lo <= v <= hi for v in box) or box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("bad box")
    return box  # type: ignore[return-value]


def _nboxes(values: Any) -> list[NBox]:
    """The boxes of a file's list *values* that are boxes, at most MAX_BOXES_PER_PAGE: one that is not (out of
    reach, malformed) is left out, never the page with it."""
    out: list[NBox] = []
    for raw in values if isinstance(values, list) else []:
        try:
            out.append(_nbox(raw))
        except (TypeError, ValueError):
            continue
    return out[:MAX_BOXES_PER_PAGE]


def _same_box(a: NBox, b: NBox, min_iou: float = 0.8) -> bool:
    return box_iou(a, b) >= min_iou  # type: ignore[arg-type]


def _text(value: Any, limit: int) -> str:
    return clean_text(value, limit)  # no control characters, no links, one line, bounded


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """*data* as the file at *path*, protected for this Windows user (`protect.write`), all or nothing
    (`atomic.write_atomic`: never through a temporary name another process or a file of the reader's may have)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    protect.write(path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


def _load_json(path: Path) -> Any:
    """The JSON object of the store file at *path*, opened when it is protected (`names.load_object`):
    FileNotFoundError when there is none, `names.Unreadable` (a ValueError) when it holds no JSON object or cannot be
    opened here."""
    data = load_object(path)
    if data is None:
        raise FileNotFoundError(2, "No such file or directory", str(path))
    return data


# --- annotations ----------------------------------------------------------------------------

def _number(value: Any) -> float | None:
    """*value* as a finite number, or None (a bool is not a number here)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _within(value: float, bounds: tuple[float, float]) -> float:
    return min(max(value, bounds[0]), bounds[1])


def ink_code(value: Any) -> str:
    """*value* as a colour code a style keeps: "", "black", "white" (`INK_NAMES`) or "#rrggbb" in lower case; anything
    else is automatic ("")."""
    if not isinstance(value, str):
        return ""
    code = value.strip().lower()
    if code in INK_NAMES:
        return code
    if len(code) == 7 and code[0] == "#" and all(c in "0123456789abcdef" for c in code[1:]):
        return code
    return ""


def _tristate(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def ink_of(style: "RegionStyle | None", lettering: "LetteringStyle | None" = None) -> tuple[str, bool | None, str]:
    """The text colour, the outline and the outline's colour a region is lettered with: each the region's own
    (*style*, the region editor's) where it is set, else the one its kind has in the series sheet (*lettering*), else
    automatic ("", None, ""): black or white from the ground, an outline on a drawing, the outline the opposite of
    the text."""
    out: list[Any] = []
    for name, auto in (("colour", ""), ("outline", None), ("outline_colour", "")):
        own = getattr(style, name, auto) if style is not None else auto
        kind = getattr(lettering, name, auto) if lettering is not None else auto
        out.append(own if own != auto else kind)
    return out[0], out[1], out[2]


@dataclass(frozen=True)
class RegionStyle:
    """How the reader formatted one region's lettering in the region editor, as a word processor's text box: the
    lines aligned left, centred or right and the block at the top, middle or bottom, a font family (looked up on each
    reader's computer by its name, as the series sheet's font), a fixed size that is never shrunk to fit, bold and
    italic forced on or off, the line spacing and the room between characters, whether the text may be condensed
    to fit (by default with an automatic size, never at a fixed one), and the slant it is set at (by default the one
    measured on the lettering, `detect.tilt`; 0 sets it straight), and the text direction (a word processor's: Auto and
    horizontal across, "down" turned a quarter clockwise to read from the top, "up" a quarter the other way to read
    from the bottom, "stacked" in columns of upright glyphs, `render.vertical`; within the frame the slant turns), and
    its ink: the text colour (automatic: black on a light ground, white on a dark one; black, white or "#rrggbb"), the
    outline round the letters forced on or off (automatic: on a drawing or a tone) and the outline's colour (automatic:
    the opposite of the text's). The ink never moves a line: a style with only a colour or an outline set lays the
    text out as the automatic lettering does (`formats_nothing`). Where the region's own ink is automatic, its kind's
    in the series sheet is used (`ink_of`).
    A field at its default leaves that part of the lettering automatic, and all of them at their defaults are the
    automatic lettering itself; only the fields set are written. The line breaks are the translation's own ("\\n")."""

    align: str = "center"  # one of ALIGNS
    valign: str = "middle"  # one of VALIGNS
    font: str = ""  # a family name ("" = the lettering the series sheet gives the region's kind)
    size: int = 0  # the font size, within STYLE_SIZES (0 = the largest that fits)
    bold: bool | None = None  # forced on or off (None = as the series sheet says for the region's kind)
    italic: bool | None = None
    line_spacing: float = 0.0  # times the font size, within LINE_SPACINGS (0 = the setting)
    letter_spacing: int = 0  # pixels added between characters, within LETTER_SPACINGS (0 = none)
    condense: bool | None = None  # may be condensed to fit (None = only when the size is automatic)
    slant: float | None = None  # degrees counter-clockwise, within SLANTS (None = as measured on the lettering)
    direction: str = ""  # one of DIRECTIONS ("" = Auto: across, as without a style)
    colour: str = ""  # the text colour: "", "black", "white" or "#rrggbb" (`ink_code`; "" = from the ground)
    outline: bool | None = None  # the outline round the letters forced on or off (None = on a drawing or a tone)
    outline_colour: str = ""  # the outline's colour, as *colour* ("" = the opposite of the text colour)

    @property
    def is_empty(self) -> bool:
        """All automatic: the lettering as without a style."""
        return self == RegionStyle()

    @property
    def formats_nothing(self) -> bool:
        """The lines as the automatic lettering sets them (a slant and a text direction aside, which only turn or
        stack them, and the ink, which only colours them)."""
        return replace(self, slant=None, direction="", colour="", outline=None, outline_colour="").is_empty

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.align != "center":
            d["align"] = self.align
        if self.valign != "middle":
            d["valign"] = self.valign
        if self.font:
            d["font"] = self.font
        if self.size:
            d["size"] = self.size
        if self.bold is not None:
            d["bold"] = self.bold
        if self.italic is not None:
            d["italic"] = self.italic
        if self.line_spacing:
            d["line_spacing"] = self.line_spacing
        if self.letter_spacing:
            d["letter_spacing"] = self.letter_spacing
        if self.condense is not None:
            d["condense"] = self.condense
        if self.slant is not None:
            d["slant"] = self.slant
        if self.direction:
            d["direction"] = self.direction
        if self.colour:
            d["colour"] = self.colour
        if self.outline is not None:
            d["outline"] = self.outline
        if self.outline_colour:
            d["outline_colour"] = self.outline_colour
        return d

    @classmethod
    def from_json(cls, d: Any) -> "RegionStyle":
        """The style *d* describes, every field checked: an unknown alignment, a value that is not a number or a
        tri-state, a colour that is not one (`ink_code`), is left automatic; a number beyond its bounds is brought
        within them (0 stays automatic)."""
        if not isinstance(d, dict):
            return cls()
        align, valign = d.get("align"), d.get("valign")
        size = _number(d.get("size"))
        line = _number(d.get("line_spacing"))
        letter = _number(d.get("letter_spacing"))
        bold, italic, condense = d.get("bold"), d.get("italic"), d.get("condense")
        slant = _number(d.get("slant"))
        return cls(align=align if align in ALIGNS else "center", valign=valign if valign in VALIGNS else "middle",
                   font=_text(d.get("font"), 60),
                   size=int(round(_within(size, STYLE_SIZES))) if size is not None and size > 0 else 0,
                   bold=bold if isinstance(bold, bool) else None, italic=italic if isinstance(italic, bool) else None,
                   line_spacing=round(_within(line, LINE_SPACINGS), 2) if line is not None and line > 0 else 0.0,
                   letter_spacing=int(round(_within(letter, LETTER_SPACINGS))) if letter is not None else 0,
                   condense=condense if isinstance(condense, bool) else None,
                   slant=round(_within(slant, SLANTS), 1) if slant is not None else None,
                   direction=d.get("direction") if d.get("direction") in DIRECTIONS else "",
                   colour=ink_code(d.get("colour")), outline=_tristate(d.get("outline")),
                   outline_colour=ink_code(d.get("outline_colour")))

    @classmethod
    def make(cls, **values: Any) -> "RegionStyle":
        """A style from field values, checked as a file's are (`from_json`)."""
        return cls.from_json(values)


@dataclass
class RegionNote:
    """What a reader knows about one text region (matched to live regions by position), and how they formatted its
    lettering."""

    box: NBox
    speaker: str = ""  # who says it (a character name as in the series sheet)
    kind: str = ""  # one of REGION_KINDS
    continues: bool = False  # the sentence goes on in the next bubble
    note: str = ""  # a remark for the translator: a pun, who is addressed; never a line of the book
    style: RegionStyle = field(default_factory=RegionStyle)  # the region editor's formatting

    @property
    def is_empty(self) -> bool:
        return not (self.speaker or self.kind or self.continues or self.note or not self.style.is_empty)

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"box": [round(v, 4) for v in self.box]}
        if self.speaker:
            d["speaker"] = self.speaker
        if self.kind:
            d["kind"] = self.kind
        if self.continues:
            d["continues"] = True
        if self.note:
            d["note"] = self.note
        if not self.style.is_empty:
            d["style"] = self.style.to_json()
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "RegionNote":
        kind = _text(d.get("kind"), 20)
        return cls(box=_nbox(d["box"]), speaker=_text(d.get("speaker"), 80), kind=kind if kind in REGION_KINDS else "",
                   continues=bool(d.get("continues", False)), note=_text(d.get("note"), 200),
                   style=RegionStyle.from_json(d.get("style")))


@dataclass
class PageAnnotations:
    fingerprint: str
    aspect: float
    add: list[NBox] = field(default_factory=list)  # text the detector misses
    ignore: list[NBox] = field(default_factory=list)  # places the detector gets wrong
    notes: list[RegionNote] = field(default_factory=list)  # speaker, kind, continuation, remark per region
    order: list[NBox] = field(default_factory=list)  # the reading order the reader set: region boxes in order
    skip: bool = False  # nothing on this page is translated (an advertisement, the viewer's own panel)

    @property
    def is_empty(self) -> bool:
        return not (self.add or self.ignore or self.notes or self.order or self.skip)

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "fp": self.fingerprint,
            "aspect": round(self.aspect, 4),
            "add": [[round(v, 4) for v in b] for b in self.add],
            "ignore": [[round(v, 4) for v in b] for b in self.ignore],
        }
        if self.notes:
            d["notes"] = [n.to_json() for n in self.notes if not n.is_empty]
        if self.order:
            d["order"] = [[round(v, 4) for v in b] for b in self.order]
        if self.skip:
            d["skip"] = True
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "PageAnnotations":
        fp = str(d["fp"]).lower()
        if len(fp) != FINGERPRINT_HEX_LEN or any(c not in "0123456789abcdef" for c in fp):
            raise ValueError("bad fingerprint")
        notes: list[RegionNote] = []
        for raw in d.get("notes", []):
            try:
                n = RegionNote.from_json(raw)  # a note whose box (or style) is no box of a region is left out
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
            if not n.is_empty:
                notes.append(n)
        return cls(fingerprint=fp, aspect=float(d.get("aspect", 0.0)), add=_nboxes(d.get("add", [])),
                   ignore=_nboxes(d.get("ignore", [])), notes=notes[:MAX_BOXES_PER_PAGE],
                   order=_nboxes(d.get("order", [])), skip=bool(d.get("skip", False)))

    def note_at(self, box: NBox, min_iou: float = 0.4) -> RegionNote | None:
        best = max(self.notes, key=lambda n: box_iou(n.box, box), default=None)  # type: ignore[arg-type]
        return best if best is not None and box_iou(best.box, box) >= min_iou else None  # type: ignore[arg-type]

    def set_note(self, box: NBox, speaker: str = "", kind: str = "", continues: bool = False, note: str = "",
                 min_iou: float = 0.4, style: RegionStyle | None = None) -> RegionNote | None:
        """Record what the reader knows about the region at *box*, with *style* as its formatting (None: the
        formatting the entry there has, if any); an all-empty note removes the entry."""
        fresh = RegionNote.from_json({"box": box, "speaker": speaker, "kind": kind, "continues": continues, "note": note})
        existing = self.note_at(box, min_iou)
        if existing is not None:
            self.notes.remove(existing)
        if style is not None:
            fresh.style = style
        elif existing is not None:
            fresh.style = existing.style
        if not fresh.is_empty:
            self.notes.append(fresh)
            return fresh
        return None

    def set_style(self, box: NBox, style: RegionStyle, min_iou: float = 0.4) -> RegionNote | None:
        """The region at *box* formatted with *style* (an empty one: automatic again), its other facts as they are;
        an entry left with nothing in it goes."""
        existing = self.note_at(box, min_iou)
        if existing is None:
            if style.is_empty:
                return None
            existing = RegionNote.from_json({"box": box})
            self.notes.append(existing)
        existing.style = style
        if existing.is_empty:
            self.notes.remove(existing)
            return None
        return existing


def page_side(index: int, units: int) -> str:
    """The side of a two-page spread the page unit *index* of a capture's *units* is on: "right" or "left"
    (`fingerprint.split_spread` gives the right page first); "" for a page shown alone, whose side is not known."""
    return ("right", "left")[index] if units == 2 and index in (0, 1) else ""


@dataclass(frozen=True)
class BookArea:
    """A place the reader ignores on every page of the book - a watermark, a page number, a banner: a box in the
    page's own terms (0..1 of its width and height, as the rectangles of one page are kept), the side of a two-page
    spread it was set on (`AREA_SIDES`: "" from a page shown alone, every page; "right" or "left", the pages on that
    side of a spread and every page shown alone, whose side is not known: `applies`) and the page's width / height
    (0: any; a page of another shape, a spread drawn as one picture, is left alone). A region found with `AREA_INSIDE`
    of its box or more inside the area is not looked at (`holds`); a rectangle the reader added always is."""

    box: NBox
    side: str = ""
    aspect: float = 0.0

    @classmethod
    def around(cls, box: Any, side: str = "", aspect: float = 0.0) -> "BookArea":
        """The area made from a dropped region's *box* (page terms): the box grown by `AREA_MARGIN` of its size on
        each side, at least `AREA_MIN_MARGIN` of the page, kept within the reach of a page's boxes."""
        x0, y0, x1, y1 = (float(v) for v in box)
        dx = max(AREA_MARGIN * (x1 - x0), AREA_MIN_MARGIN)
        dy = max(AREA_MARGIN * (y1 - y0), AREA_MIN_MARGIN)
        lo, hi = NBOX_REACH
        grown = (round(max(lo, x0 - dx), 4), round(max(lo, y0 - dy), 4), round(min(hi, x1 + dx), 4),
                 round(min(hi, y1 + dy), 4))
        return cls(box=_nbox(grown), side=side if side in AREA_SIDES else "",
                   aspect=round(max(0.0, float(aspect)), 4))

    def applies(self, side: str, aspect: float) -> bool:
        """Whether the area is one of a page on *side* (`page_side`) of width / height *aspect*."""
        if self.side and side and side != self.side:
            return False
        return not (self.aspect and aspect and abs(self.aspect - aspect) / max(self.aspect, aspect) > AREA_ASPECT)

    def holds(self, box: Any) -> bool:
        """Whether `AREA_INSIDE` of the area of *box* (page terms) or more lies inside the area."""
        x0, y0, x1, y1 = (float(v) for v in box)
        area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        if area <= 0.0:
            return False
        ix = min(x1, self.box[2]) - max(x0, self.box[0])
        iy = min(y1, self.box[3]) - max(y0, self.box[1])
        return ix > 0 and iy > 0 and ix * iy >= AREA_INSIDE * area

    def same(self, other: "BookArea") -> bool:
        """Two areas alike: the same side, about the same box."""
        return self.side == other.side and _same_box(self.box, other.box)

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"box": [round(v, 4) for v in self.box]}
        if self.side:
            d["side"] = self.side
        if self.aspect:
            d["aspect"] = round(self.aspect, 4)
        return d

    @classmethod
    def from_json(cls, d: Any) -> "BookArea":
        """The area *d* describes; ValueError (TypeError, KeyError) for one that is no area."""
        side = d.get("side", "")
        aspect = _number(d.get("aspect"))
        return cls(box=_nbox(d["box"]), side=side if side in AREA_SIDES else "",
                   aspect=round(aspect, 4) if aspect is not None and aspect > 0 else 0.0)


def _areas(values: Any) -> list[BookArea]:
    """The areas of a file's list *values* that are areas, at most MAX_AREAS (one that is not is left out)."""
    out: list[BookArea] = []
    for raw in values if isinstance(values, list) else []:
        try:
            area = BookArea.from_json(raw)
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
        if not any(area.same(a) for a in out):
            out.append(area)
    return out[:MAX_AREAS]


def clean_book_settings(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only the settings a book may override, with sane value types (and the lettering's size within
    `BOOK_SETTING_BOUNDS`, a whole number for its largest size)."""
    out: dict[str, Any] = {}
    for key, value in (overrides or {}).items():
        if key not in BOOK_SETTING_KEYS:
            continue
        bounds = BOOK_SETTING_BOUNDS.get(key)
        if bounds is not None:
            if isinstance(value, (int, float)) and not isinstance(value, bool) and bounds[0] <= value <= bounds[1]:
                out[key] = type(bounds[0])(value)
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            out[key] = value
        elif isinstance(value, str) and value.strip():
            out[key] = value.strip()[:40]
    return out


class BookAnnotations:
    """Everything readers recorded about one book (one JSON file)."""

    def __init__(self, path: Path, book: str):
        self.path = Path(path)
        self.book = book
        self.pages: list[PageAnnotations] = []
        self.settings: dict[str, Any] = {}  # detection/OCR overrides for this book (BOOK_SETTING_KEYS)
        self.sequence: list[tuple[str, float]] = []  # (fingerprint, aspect) of the pages in the order first scanned
        self.reading_direction: str = ""  # "" (unknown = rtl) | "rtl" | "ltr"
        self.areas: list[BookArea] = []  # the areas ignored on every page of the book
        self.updated = _now()

    @classmethod
    def load(cls, path: Path) -> "BookAnnotations":
        """The annotations in the file at *path* (protected or plain, `_load_json`); ValueError for another schema."""
        return cls.from_json(_load_json(path), path)

    @classmethod
    def from_json(cls, data: Any, path: Path) -> "BookAnnotations":
        """The annotations a file's JSON *data* holds, kept at *path*; ValueError for another schema."""
        if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
            raise ValueError(f"unsupported annotations schema in {path}")
        ann = cls(path, str(data.get("book", "untitled")))
        ann.updated = str(data.get("updated", ann.updated))
        ann.apply_json(data)
        return ann

    def apply_json(self, data: dict[str, Any]) -> None:
        for raw in (data.get("pages") or [])[:MAX_PAGES]:
            try:
                self.pages.append(PageAnnotations.from_json(raw))
            except (ValueError, TypeError, KeyError):
                continue
        self.settings = clean_book_settings(data.get("settings") if isinstance(data.get("settings"), dict) else None)
        seq: list[tuple[str, float]] = []
        for raw in (data.get("sequence") or [])[:MAX_PAGES]:
            try:
                fp = str(raw["fp"]).lower()
                if len(fp) == FINGERPRINT_HEX_LEN:
                    seq.append((fp, float(raw.get("aspect", 0.0))))
            except (TypeError, KeyError, ValueError):
                continue
        self.sequence = seq
        direction = _text(data.get("reading_direction"), 3)
        self.reading_direction = direction if direction in READING_DIRECTIONS else ""
        self.areas = _areas(data.get("areas"))

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema": SCHEMA_VERSION,
            "app": "taslation",
            "kind": "annotations",
            "note": NOTE,
            "book": self.book,
            "updated": self.updated,
            "pages": [p.to_json() for p in self.pages if not p.is_empty],
            "settings": dict(self.settings),
            "sequence": [{"fp": fp, "aspect": round(aspect, 4)} for fp, aspect in self.sequence],
            "reading_direction": self.reading_direction,
        }
        if self.areas:  # (a file without any stays as it was)
            d["areas"] = [a.to_json() for a in self.areas]
        return d

    def save(self) -> None:
        """Write the file, all or nothing. When it is the book's own file and another process gave it to another book
        meanwhile (two names with one file name, both opened while it was free), the book's other file name instead
        (`names.claim`); FileExistsError when that holds another book too. A file there that this version cannot
        read (written meanwhile) is set aside first, never written over (`StoreFiles.claim`)."""
        self.updated = _now()
        self.path = ANNOTATION_FILES.claim(self.path, self.book)
        _write_json(self.path, self.to_json())

    def __len__(self) -> int:
        return sum(1 for p in self.pages if not p.is_empty)

    @property
    def box_count(self) -> int:
        return sum(len(p.add) + len(p.ignore) for p in self.pages)

    @property
    def note_count(self) -> int:
        return sum(len(p.notes) + (1 if p.order else 0) + (1 if p.skip else 0) for p in self.pages)

    @property
    def rtl(self) -> bool:
        return self.reading_direction != "ltr"

    def lookup(self, fingerprint: str, aspect: float, max_distance: int, aspect_tolerance: float = 0.12
               ) -> PageAnnotations | None:
        """The annotations of the page whose fingerprint is nearest within *max_distance* bits."""
        best: tuple[int, PageAnnotations] | None = None
        for page in self.pages:
            if aspect and page.aspect and abs(page.aspect - aspect) / max(page.aspect, aspect) > aspect_tolerance:
                continue
            d = hamming(fingerprint, page.fingerprint)
            if d <= max_distance and (best is None or d < best[0]):
                best = (d, page)
        return None if best is None else best[1]

    def page(self, fingerprint: str, aspect: float, max_distance: int = 6) -> PageAnnotations:
        """The page's annotations, created when missing (a near-identical fingerprint counts as the same page)."""
        found = self.lookup(fingerprint, aspect, max_distance)
        if found is None:
            found = PageAnnotations(fingerprint=fingerprint, aspect=aspect)
            self.pages.append(found)
        return found

    def add_box(self, fingerprint: str, aspect: float, box: NBox, kind: str = "add") -> PageAnnotations:
        if kind not in ("add", "ignore"):
            raise ValueError("kind must be 'add' or 'ignore'")
        page = self.page(fingerprint, aspect)
        boxes: list[NBox] = getattr(page, kind)
        if not any(_same_box(box, b) for b in boxes):
            boxes.append(box)
        return page

    def remove_box(self, fingerprint: str, aspect: float, box: NBox, max_distance: int = 6) -> int:
        """Forget every reader-made rectangle overlapping *box* on that page; returns how many were removed."""
        page = self.lookup(fingerprint, aspect, max_distance)
        if page is None:
            return 0
        removed = 0
        for kind in ("add", "ignore"):
            boxes: list[NBox] = getattr(page, kind)
            keep = [b for b in boxes if box_iou(b, box) < 0.3]  # type: ignore[arg-type]
            removed += len(boxes) - len(keep)
            setattr(page, kind, keep)
        return removed

    def add_area(self, area: BookArea) -> bool:
        """*area* ignored on every page of the book from now on; False when one alike is there already, or the book
        has `MAX_AREAS` of them."""
        if any(area.same(a) for a in self.areas) or len(self.areas) >= MAX_AREAS:
            return False
        self.areas.append(area)
        return True

    def remove_area(self, area: BookArea) -> bool:
        """The area alike *area* (`BookArea.same`) no longer ignored; False when there is none."""
        keep = [a for a in self.areas if not a.same(area)]
        removed = len(keep) != len(self.areas)
        self.areas = keep
        return removed

    def areas_for(self, side: str, aspect: float) -> list[BookArea]:
        """The areas that apply to a page on *side* (`page_side`) of width / height *aspect*."""
        return [a for a in self.areas if a.applies(side, aspect)]

    def set_settings(self, overrides: dict[str, Any] | None) -> dict[str, Any]:
        self.settings = clean_book_settings(overrides)
        return dict(self.settings)

    def record_sequence(self, fingerprint: str, aspect: float, max_distance: int = 6) -> bool:
        """Note a page in the order it was first scanned; returns True when it was new."""
        for fp, _a in self.sequence:
            if hamming(fp, fingerprint) <= max_distance:
                return False
        self.sequence.append((fingerprint, aspect))
        return True


class AnnotationStore:
    """The reader's annotations, one JSON file per book: ``<book>.json``, or ``<book>-<hash>.json`` when that one holds
    another book whose name gives the same file name (`names.pick`, by the book each file records). No file is
    renamed."""

    def __init__(self, annotations_dir: Path):
        self.annotations_dir = Path(annotations_dir)

    def path_for(self, book: str) -> Path:
        """The annotations file of *book*: the plain name while there is none or it holds this very book (or records
        none), else the hashed one; FileExistsError when both hold other books (two names, one hash)."""
        return ANNOTATION_FILES.pick(self.annotations_dir, book)

    def open(self, book: str) -> BookAnnotations:
        """The annotations of *book* from its file (`path_for`), or new ones a save puts there. A file this version
        cannot read (damaged, of another kind, written by a newer TASlation) is first set aside as ``<file
        stem>.unreadable-<date>.json``, never written over (`StoreFiles.load`). A file of another book is never read
        as this one's (FileExistsError); one that records no book is this one's and gets its name at the next save.
        OSError when the file cannot be opened."""
        path = self.path_for(book)
        loaded = ANNOTATION_FILES.load(path, book, None, lambda data: BookAnnotations.from_json(data, path))
        if loaded is None:
            return BookAnnotations(path, book)
        ann, _owner = loaded
        ann.book = book
        return ann

    def list(self) -> list[dict[str, Any]]:
        """The annotations of every book: the files `path_for` gives, plain and hashed, not copies kept beside them
        nor files this version cannot read. Counts only, never a note's or a speaker's text: per book its pages with
        rectangles or facts (*pages*), the rectangles (*boxes*: *add* + *ignore*), *notes* (`note_count`: the region
        notes, reading orders and skipped pages together) and each of those apart (*region_notes*, *orders*,
        *skipped*), the areas ignored on every page (*areas*), the pages in scan order (*sequence*), *updated* and the
        *file*."""
        out: list[dict[str, Any]] = []
        if not self.annotations_dir.is_dir():
            return out
        for path in sorted(self.annotations_dir.glob("*.json")):
            data = read_object(path)
            if data is None or not ANNOTATION_FILES.listed(path, data):
                continue
            try:
                ANNOTATION_FILES.check(data)
                ann = BookAnnotations.from_json(data, path)
            except Exception:  # names.Unreadable among them
                continue
            out.append({"file": str(path), "book": ann.book, "pages": len(ann), "boxes": ann.box_count,
                        "add": sum(len(p.add) for p in ann.pages), "ignore": sum(len(p.ignore) for p in ann.pages),
                        "notes": ann.note_count, "region_notes": sum(len(p.notes) for p in ann.pages),
                        "orders": sum(1 for p in ann.pages if p.order), "skipped": sum(1 for p in ann.pages if p.skip),
                        "areas": len(ann.areas), "sequence": len(ann.sequence), "updated": ann.updated})
        return out

    def delete(self, book: str) -> bool:
        """Delete the annotations of *book*: the files that record exactly this book, under either name `path_for`
        gives, with what a save that stopped halfway left beside them; a file that cannot be read or records no book
        goes only under one of the book's own two file names, or as a copy set aside from one of them. Another book
        whose name starts the same or gives the same file name keeps its annotations."""
        return ANNOTATION_FILES.delete(self.annotations_dir, book)


# --- series sheet: glossary, characters, style ------------------------------------------------

@dataclass
class GlossaryEntry:
    term: str  # as written in the book
    rendering: str  # how to write it in the target language
    note: str = ""  # who or what it is, tone, anything the translator should know

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"term": self.term, "rendering": self.rendering}
        if self.note:
            d["note"] = self.note
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "GlossaryEntry":
        term, rendering = _text(d.get("term"), 80), _text(d.get("rendering"), 120)
        if not term or not rendering:
            raise ValueError("empty glossary entry")
        return cls(term=term, rendering=rendering, note=_text(d.get("note"), 200))


@dataclass
class CharacterSheet:
    """Facts about a character that decide how their lines read: nothing they say, only how they say it."""

    name: str  # as written in the book
    rendering: str = ""  # the name in the target language
    gender: str = ""
    age: str = ""  # child, teen, adult, elderly, or a few words
    pronoun: str = ""  # first-person pronoun they use (俺, 私, 僕, ...)
    style: str = ""  # how they talk: polite, rough, dialect, verbal tics
    role: str = ""  # who they are, relationships
    addresses: dict[str, str] = field(default_factory=dict)  # how they call others: name as in the book -> form to use

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name}
        for key in ("rendering", "gender", "age", "pronoun", "style", "role"):
            if getattr(self, key):
                d[key] = getattr(self, key)
        if self.addresses:
            d["addresses"] = dict(self.addresses)
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "CharacterSheet":
        name = _text(d.get("name"), 80)
        if not name:
            raise ValueError("a character needs a name")
        raw = d.get("addresses") or {}
        addresses = {_text(k, 80): _text(v, 120) for k, v in raw.items() if _text(k, 80) and _text(v, 120)} \
            if isinstance(raw, dict) else {}
        return cls(name=name, rendering=_text(d.get("rendering"), 120), gender=_text(d.get("gender"), 40),
                   age=_text(d.get("age"), 40), pronoun=_text(d.get("pronoun"), 40), style=_text(d.get("style"), 200),
                   role=_text(d.get("role"), 200), addresses=addresses)

    def format(self) -> str:
        head = f"- {self.name}" + (f" = {self.rendering}" if self.rendering else "")
        facts = [x for x in (self.gender, self.age) if x]
        parts: list[str] = []
        if facts:
            parts.append(", ".join(facts))
        if self.pronoun:
            parts.append(f"first person {self.pronoun}")
        if self.style:
            parts.append(self.style)
        if self.role:
            parts.append(self.role)
        for other, form in self.addresses.items():
            parts.append(f"calls {other} \"{form}\"")
        return head + (f" ({'; '.join(parts)})" if parts else "")

    def fill_from(self, other: "CharacterSheet") -> int:
        """Take over facts this sheet lacks; returns how many fields were filled."""
        filled = 0
        for key in ("rendering", "gender", "age", "pronoun", "style", "role"):
            if not getattr(self, key) and getattr(other, key):
                setattr(self, key, getattr(other, key))
                filled += 1
        for k, v in other.addresses.items():
            if k not in self.addresses:
                self.addresses[k] = v
                filled += 1
        return filled


@dataclass
class LetteringStyle:
    """How the regions of one kind are lettered: a font family (empty = the sheet's lettering font), italic, bold, and
    the kind's ink, which a region's own in the region editor overrides (`ink_of`): the text colour, the outline forced
    on or off and its colour (automatic each: "", None, "", as `RegionStyle`'s)."""

    font: str = ""
    italic: bool = False
    bold: bool = False
    colour: str = ""  # `ink_code`
    outline: bool | None = None
    outline_colour: str = ""

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.font:
            d["font"] = self.font
        if self.italic:
            d["italic"] = True
        if self.bold:
            d["bold"] = True
        if self.colour:
            d["colour"] = self.colour
        if self.outline is not None:
            d["outline"] = self.outline
        if self.outline_colour:
            d["outline_colour"] = self.outline_colour
        return d

    @classmethod
    def from_json(cls, d: Any) -> "LetteringStyle":
        if not isinstance(d, dict):
            return cls()
        return cls(font=_text(d.get("font"), 60), italic=bool(d.get("italic")), bold=bool(d.get("bold")),
                   colour=ink_code(d.get("colour")), outline=_tristate(d.get("outline")),
                   outline_colour=ink_code(d.get("outline_colour")))


# what a kind gets when the sheet says nothing about it: thoughts in italic, shouts in a heavier face
DEFAULT_LETTERING: dict[str, LetteringStyle] = {"thought": LetteringStyle(italic=True), "shout": LetteringStyle(bold=True)}


@dataclass
class StyleGuide:
    """How the series should read in the target language: a policy, not a text."""

    honorifics: str = ""  # one of HONORIFIC_POLICIES: keep (-san, -chan), drop, adapt (Mr., Big bro, ...)
    tone: str = ""  # a few words: light comedy, keep the puns; period drama, formal
    rules: list[str] = field(default_factory=list)  # short house rules
    font: str = ""  # the lettering font the series suggests: a family name, looked up on each reader's computer
    lettering: dict[str, LetteringStyle] = field(default_factory=dict)  # per kind (LETTERING_KINDS); absent = default

    @property
    def is_empty(self) -> bool:
        return not (self.honorifics or self.tone or self.rules or self.font or self.lettering)

    def lettering_for(self, kind: str) -> LetteringStyle:
        """How regions of *kind* are set: the sheet's entry, else the built-in default (a copy either way)."""
        return replace(self.lettering.get(kind) or DEFAULT_LETTERING.get(kind) or LetteringStyle())

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.honorifics:
            d["honorifics"] = self.honorifics
        if self.tone:
            d["tone"] = self.tone
        if self.rules:
            d["rules"] = list(self.rules)
        if self.font:
            d["font"] = self.font
        if self.lettering:
            d["lettering"] = {k: v.to_json() for k, v in self.lettering.items()}
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "StyleGuide":
        if not isinstance(d, dict):
            return cls()
        hon = _text(d.get("honorifics"), 10)
        rules = [_text(r, 200) for r in (d.get("rules") or []) if _text(r, 200)][:40]
        raw = d.get("lettering")
        lettering = ({k: LetteringStyle.from_json(v) for k, v in raw.items() if k in LETTERING_KINDS and isinstance(v, dict)}
                     if isinstance(raw, dict) else {})
        return cls(honorifics=hon if hon in HONORIFIC_POLICIES else "", tone=_text(d.get("tone"), 200), rules=rules,
                   font=_text(d.get("font"), 60), lettering=lettering)

    def format(self) -> str:
        """The policies for the prompt; the font is for the lettering, not for the model."""
        if not (self.honorifics or self.tone or self.rules):
            return ""
        lines = ["Style guide (from the reader):"]
        if self.honorifics == "keep":
            lines.append("- Honorifics: keep them as in Japanese (-san, -chan, -sensei).")
        elif self.honorifics == "drop":
            lines.append("- Honorifics: drop them; use plain names.")
        elif self.honorifics == "adapt":
            lines.append("- Honorifics: adapt them to natural equivalents in the target language.")
        if self.tone:
            lines.append(f"- Tone: {self.tone}")
        lines.extend(f"- {r}" for r in self.rules)
        return "\n".join(lines)

    def fill_from(self, other: "StyleGuide") -> int:
        filled = 0
        if not self.honorifics and other.honorifics:
            self.honorifics = other.honorifics
            filled += 1
        if not self.tone and other.tone:
            self.tone = other.tone
            filled += 1
        for r in other.rules:
            if r not in self.rules:
                self.rules.append(r)
                filled += 1
        if not self.font and other.font:
            self.font = other.font
            filled += 1
        for kind, style in other.lettering.items():
            if kind not in self.lettering:
                self.lettering[kind] = replace(style)
                filled += 1
        return filled


class Glossary:
    """The series sheet: glossary terms, character sheets and the style guide (one JSON file per series and language)."""

    def __init__(self, path: Path, series: str, language: str = "English"):
        self.path = Path(path)
        self.series = series
        self.language = language
        self.entries: list[GlossaryEntry] = []
        self.characters: list[CharacterSheet] = []
        self.style = StyleGuide()
        self.updated = _now()

    @classmethod
    def load(cls, path: Path) -> "Glossary":
        """The sheet in the file at *path* (protected or plain, `_load_json`); ValueError for another schema."""
        return cls.from_json(_load_json(path), path)

    @classmethod
    def from_json(cls, data: Any, path: Path) -> "Glossary":
        """The sheet a file's JSON *data* holds, kept at *path*; ValueError for another schema."""
        if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
            raise ValueError(f"unsupported glossary schema in {path}")
        g = cls(path, str(data.get("series", "untitled")), str(data.get("language", "English")))
        g.updated = str(data.get("updated", g.updated))
        g.apply_json(data)
        return g

    def apply_json(self, data: dict[str, Any]) -> None:
        for raw in (data.get("entries") or [])[:MAX_TERMS]:
            try:
                self.entries.append(GlossaryEntry.from_json(raw))
            except (ValueError, TypeError, AttributeError):
                continue
        for raw in (data.get("characters") or [])[:MAX_CHARACTERS]:
            try:
                self.characters.append(CharacterSheet.from_json(raw))
            except (ValueError, TypeError, AttributeError):
                continue
        self.style = StyleGuide.from_json(data.get("style") or {})

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "app": "taslation",
            "kind": "glossary",
            "note": "Terms and names with the rendering to use, character sheets and a style guide. "
                    "No page text, no translations of dialogue.",
            "series": self.series,
            "language": self.language,
            "updated": self.updated,
            "entries": [e.to_json() for e in self.entries],
            "characters": [c.to_json() for c in self.characters],
            "style": self.style.to_json(),
        }

    def save(self) -> None:
        """Write the file, all or nothing. When it is the series' own file and another process gave it to another
        series meanwhile (two names with one file name, both opened while it was free), the series' other file name
        instead (`names.claim`); FileExistsError when that holds another series too. A file there that this version
        cannot read (written meanwhile) is set aside first, never written over (`StoreFiles.claim`)."""
        self.updated = _now()
        self.path = SHEET_FILES.claim(self.path, self.series, self.language)
        _write_json(self.path, self.to_json())

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def is_empty(self) -> bool:
        return not (self.entries or self.characters) and self.style.is_empty

    # terms
    def get(self, term: str) -> GlossaryEntry | None:
        term = term.strip()
        return next((e for e in self.entries if e.term == term), None)

    def set(self, term: str, rendering: str, note: str = "") -> GlossaryEntry:
        entry = GlossaryEntry.from_json({"term": term, "rendering": rendering, "note": note})
        existing = self.get(entry.term)
        if existing is None:
            self.entries.append(entry)
            return entry
        existing.rendering, existing.note = entry.rendering, entry.note
        return existing

    def remove(self, term: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.term != term.strip()]
        return len(self.entries) < before

    # characters
    def get_character(self, name: str) -> CharacterSheet | None:
        name = name.strip()
        return next((c for c in self.characters if c.name == name or (c.rendering and c.rendering == name)), None)

    def set_character(self, sheet: CharacterSheet) -> CharacterSheet:
        existing = next((c for c in self.characters if c.name == sheet.name), None)
        if existing is None:
            self.characters.append(sheet)
            return sheet
        self.characters[self.characters.index(existing)] = sheet
        return sheet

    def remove_character(self, name: str) -> bool:
        before = len(self.characters)
        self.characters = [c for c in self.characters if c.name != name.strip()]
        return len(self.characters) < before

    def speaker_names(self) -> list[str]:
        names: list[str] = []
        for c in self.characters:
            for n in (c.name, c.rendering):
                if n and n not in names:
                    names.append(n)
        return names

    def merge(self, other: "Glossary") -> int:
        """Take over what this sheet lacks (own renderings and facts are kept); returns how many items were added."""
        added = 0
        for e in other.entries:
            if self.get(e.term) is None:
                self.entries.append(GlossaryEntry(e.term, e.rendering, e.note))
                added += 1
        for c in other.characters:
            mine = next((m for m in self.characters if m.name == c.name), None)
            if mine is None:
                self.characters.append(CharacterSheet.from_json(c.to_json()))
                added += 1
            else:
                added += mine.fill_from(c)
        added += self.style.fill_from(other.style)
        return added

    def format(self, limit_chars: int = 3500) -> str:
        return format_sheet(self, limit_chars)


def format_glossary(entries: list[GlossaryEntry], limit_chars: int = 2000) -> str:
    """Render the glossary terms for the prompt (empty string when there is nothing)."""
    if not entries:
        return ""
    lines = ["Glossary (provided by the reader; use these renderings exactly):"]
    for e in entries:
        line = f"- {e.term} = {e.rendering}" + (f" ({e.note})" if e.note else "")
        if sum(len(x) + 1 for x in lines) + len(line) > limit_chars:
            break
        lines.append(line)
    return "\n".join(lines)


def format_sheet(sheet: Glossary, limit_chars: int = 3500) -> str:
    """Characters, glossary and style guide as one block for the prompt."""
    blocks: list[str] = []
    if sheet.characters:
        lines = ["Characters (provided by the reader; use these names and keep each voice):"]
        for c in sheet.characters:
            line = c.format()
            if sum(len(x) + 1 for x in lines) + len(line) > limit_chars // 2:
                break
            lines.append(line)
        blocks.append("\n".join(lines))
    blocks.append(format_glossary(sheet.entries, max(500, limit_chars // 3)))
    blocks.append(sheet.style.format())
    return join_premises(*blocks)


def join_premises(*parts: str) -> str:
    """The parts of the premises (the series sheet's text) as one block for the prompt."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


class Premises(str):
    """The premises block as it goes in every request, a stable prompt prefix, and the *sheet* behind it: what the
    block's limits cut and a request's lines name then comes after that request's bubbles (`terms.cut_entries`)."""

    sheet: Glossary | None

    def __new__(cls, text: str, sheet: Glossary | None = None) -> "Premises":
        self = super().__new__(cls, text)
        self.sheet = sheet
        return self


class GlossaryStore:
    """The series sheets, one JSON file per series and target language: ``<series>[.<language>].json``, or
    ``<series>-<hash>[.<language>].json`` when that one holds another series whose name gives the same file name
    (`names.pick`, by the series and language each file records). No file is renamed."""

    def __init__(self, glossary_dir: Path):
        self.glossary_dir = Path(glossary_dir)

    def path_for(self, series: str, language: str = "English") -> Path:
        """The sheet file of *series* in *language*: the plain name while there is none or it holds this very series
        (or records none), else the hashed one; FileExistsError when both hold other series (two names, one hash)."""
        return SHEET_FILES.pick(self.glossary_dir, series, language)

    def open(self, series: str, language: str = "English") -> Glossary:
        """The sheet of *series* in *language* from its file (`path_for`), or a new one a save puts there. A file
        this version cannot read (damaged, of another kind, written by a newer TASlation) is first set aside as
        ``<file stem>.unreadable-<date>.json``, never written over (`StoreFiles.load`). A file of another series is
        never read as this one's (FileExistsError); one that records no series (or no language) is this one's and
        gets them at the next save. OSError when the file cannot be opened."""
        path = self.path_for(series, language)
        loaded = SHEET_FILES.load(path, series, language, lambda data: Glossary.from_json(data, path))
        if loaded is None:
            return Glossary(path, series, language)
        sheet, (_series, recorded_language) = loaded
        sheet.series = series
        if recorded_language is None:
            sheet.language = language
        return sheet

    def list(self) -> list[dict[str, Any]]:
        """The sheet of every series in every language: the files `path_for` gives, plain and hashed, not copies kept
        beside them nor files this version cannot read."""
        out: list[dict[str, Any]] = []
        if not self.glossary_dir.is_dir():
            return out
        for path in sorted(self.glossary_dir.glob("*.json")):
            data = read_object(path)
            if data is None or not SHEET_FILES.listed(path, data):
                continue
            try:
                SHEET_FILES.check(data)
                g = Glossary.from_json(data, path)
            except Exception:  # names.Unreadable among them
                continue
            out.append({"file": str(path), "series": g.series, "language": g.language, "entries": len(g),
                        "characters": len(g.characters), "style": not g.style.is_empty, "updated": g.updated})
        return out

    def delete(self, series: str) -> bool:
        """Delete the sheet of *series* in every language: the files that record exactly this series, under either
        name `path_for` gives, with what a save that stopped halfway left beside them; a file that cannot be read or
        records no series goes only under one of the series' own file names, or as a copy set aside from one of
        them. Another series whose name starts the same or gives the same file name keeps its sheet."""
        return SHEET_FILES.delete(self.glossary_dir, series)


# --- two series sheets compared (a rename joining the new series' sheet) ---------------------------------------

@dataclass
class Conflict:
    """Something one series sheet says otherwise than another (`compare_sheets`): a term's rendering (or its note), a
    character's fact or how they call someone, a policy of the style guide, the lettering of a kind. *mine* and
    *theirs* are the two values as the sheets keep them (texts as the readers wrote them: renderings, names, notes,
    never a line of the book); the reader's answer is *take* (False: keep mine)."""

    area: str  # one of CONFLICT_AREAS
    key: str = ""  # the term, the character's name, the style guide's field
    field: str = ""  # a character's field (CHARACTER_FIELDS, or "addresses")
    sub: str = ""  # whom the character calls (addresses), the kind of region (the style guide's lettering)
    mine: Any = None
    theirs: Any = None
    take: bool = False

    def apply(self, sheet: Glossary) -> bool:
        """The other sheet's value put into *sheet* (in memory); False when the item is not there any more."""
        if self.area == "term":
            rendering, note = self.theirs
            entry = sheet.get(self.key)
            if entry is None:
                sheet.set(self.key, rendering, note)
            else:
                entry.rendering = rendering
                entry.note = note or entry.note
            return True
        if self.area == "character":
            character = next((c for c in sheet.characters if c.name == self.key), None)
            if character is None:
                return False
            if self.field == "addresses":
                character.addresses[self.sub] = self.theirs
            else:
                setattr(character, self.field, self.theirs)
            return True
        if self.area == "style":
            if self.key == "lettering":
                sheet.style.lettering[self.sub] = replace(self.theirs)
            else:
                setattr(sheet.style, self.key, self.theirs)
            return True
        return False


@dataclass
class Review:
    """What joining one series sheet into another would do (`compare_sheets`), before anything is changed: how many
    terms, characters, facts and policies it adds that the other lacks (*terms*, taken over as they are), where the two
    say otherwise (*conflicts*, answered in the review), and the sheet that joins (*sheet*)."""

    terms: int = 0
    conflicts: list[Conflict] = field(default_factory=list)
    sheet: Glossary | None = None


def _compare_sheets(own: Glossary, theirs: Glossary, review: Review) -> None:
    for e in theirs.entries:
        m = own.get(e.term)
        if m is not None and (e.rendering != m.rendering or (e.note and e.note != m.note)):
            review.conflicts.append(Conflict("term", key=e.term, mine=(m.rendering, m.note), theirs=(e.rendering, e.note)))
    for c in theirs.characters:
        m = next((x for x in own.characters if x.name == c.name), None)
        if m is None:
            continue
        for name in CHARACTER_FIELDS:
            a, b = getattr(m, name), getattr(c, name)
            if a and b and a != b:
                review.conflicts.append(Conflict("character", key=c.name, field=name, mine=a, theirs=b))
        for other, form in c.addresses.items():
            if other in m.addresses and m.addresses[other] != form:
                review.conflicts.append(Conflict("character", key=c.name, field="addresses", sub=other,
                                                 mine=m.addresses[other], theirs=form))
    for name in STYLE_FIELDS:
        a, b = getattr(own.style, name), getattr(theirs.style, name)
        if a and b and a != b:
            review.conflicts.append(Conflict("style", key=name, mine=a, theirs=b))
    for kind, style in theirs.style.lettering.items():
        mine_style = own.style.lettering.get(kind)
        if mine_style is not None and mine_style != style:
            review.conflicts.append(Conflict("style", key="lettering", sub=kind, mine=replace(mine_style),
                                             theirs=replace(style)))
    review.sheet = theirs
    review.terms = copy.deepcopy(own).merge(theirs)


def compare_sheets(mine: Glossary, theirs: Glossary) -> Review:
    """What joining the sheet *theirs* into *mine* would do; neither is changed. What the join takes over as it is -
    terms, characters, facts and policies *mine* lacks - is counted; a conflict is a term with another rendering (or
    note), a character's fact or how they call someone, a policy of the style guide or the lettering of a kind that
    *mine* has otherwise."""
    review = Review()
    _compare_sheets(mine, theirs, review)
    return review


def apply_review(review: Review, sheet: Glossary) -> dict[str, int]:
    """The join as the reader answered its review, into *sheet* (in memory; the caller saves it): what the other sheet
    adds, and its values where a conflict says take theirs. Returns {"terms", "taken"}."""
    counts = {"terms": 0, "taken": 0}
    if review.sheet is not None:
        counts["terms"] = sheet.merge(review.sheet)
    for c in review.conflicts:
        if c.take and c.apply(sheet):
            counts["taken"] += 1
    return counts


__all__ = [
    "ALIGNS", "AREA_INSIDE", "AREA_SIDES", "AnnotationStore", "BOOK_SETTING_KEYS", "BookAnnotations", "BookArea",
    "CHARACTER_FIELDS", "CONFLICT_AREAS", "ERASE_ONLY",
    "CharacterSheet", "Conflict", "DEFAULT_LETTERING", "Glossary", "GlossaryEntry", "GlossaryStore",
    "HONORIFIC_POLICIES", "INK_NAMES", "LETTERING_KINDS", "LETTER_SPACINGS", "LINE_SPACINGS", "LetteringStyle",
    "MAX_BOXES_PER_PAGE", "MAX_CHARACTERS", "MAX_PAGES", "MAX_TERMS", "NBOX_REACH", "PageAnnotations", "Premises",
    "REGION_KINDS",
    "RegionNote", "RegionStyle", "Review", "STORE_KINDS", "STYLE_FIELDS", "STYLE_SIZES", "StyleGuide", "VALIGNS",
    "apply_review", "clean_book_settings", "compare_sheets", "format_glossary", "format_sheet", "ink_code", "ink_of",
    "join_premises", "page_side",
]
