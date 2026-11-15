"""Lettering styles on top of a font file: italic, bold, stressed words, and room between the characters.

A style guide may set thought bubbles in italic, shouts in a heavier face and narration in another font, and a
translation may mark a stressed word *like this*. Each style is a real cut of the font's family when this
computer has one (the italic or the heavier face, found by the names in the font files) and a synthetic one
otherwise: a shear for italic, a thin stroke for bold. So every font works, in every script, and the markers
never show on the page. The region editor may also add room between the characters (letter spacing, *tracking*):
each character is then set at its place in the run plus that room, with the marks that combine with it. A text that
would otherwise drop a size may be set condensed (*condense*, at most 8 % narrower): the line is drawn at twice the
size and brought back to size narrower than it is high, so it works with every font. A run in Devanagari or Bengali is
measured and drawn shaped (`shaping`: its conjuncts and vowel signs as the font forms them), with the same styles; a
conjunct then keeps its letters together under letter spacing.
"""

from __future__ import annotations

import functools
import math
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw

from . import shaping
from .fonts import FontSpec, FontT, _key, face_of, font_faces, load_font

ITALIC_SHEAR = 0.21  # tangent of the lean of a synthetic italic
STROKE_FROM = 12  # a synthetic bold adds a stroke from this size on (one pixel, two from 36)
HEAVY_WEIGHT = 900  # the instance a variable font gives for bold on top of its bold instance
MARK = "*"
_ITALIC_WORDS = ("italic", "oblique", "slanted")
_BOLD_WORDS = ("bold", "black", "heavy", "semibold", "demibold", "extrabold", "ultrabold")
_HEAVY_WORDS = ("black", "heavy", "extrabold", "ultrabold")


def _named(words: tuple[str, ...], name: str) -> bool:
    low = name.lower()
    return any(w in low for w in words)


@dataclass(frozen=True)
class Lettering:
    """How a region's text is set: the font file, italic and bold for the whole text, and the family's cuts."""

    path: str | None
    bold_variation: bool = False  # a variable font: its bold instance is selected
    italic: bool = False
    bold: bool = False
    italic_path: str | None = None  # the family's italic cut at the base weight (None: a shear)
    bold_path: str | None = None  # the family's heavier upright cut (None: a heavier weight, or a stroke)
    bold_italic_path: str | None = None  # the family's heavier italic cut
    emphasis: bool = True  # *stressed words* are set in bold italic
    tracking: int = 0  # pixels added between two characters (letter spacing; 0 = none, below 0 = tighter)
    condense: float = 1.0  # the width the glyphs are set at, of their own (0.92: 8 % narrower; 1.0: as drawn)

    def formatted(self, italic: bool | None = None, bold: bool | None = None, tracking: int | None = None,
                  condense: float | None = None) -> "Lettering":
        """This lettering with italic, bold, the letter spacing or the condensing as a region's formatting or a fit
        sets them (None: as it is)."""
        return replace(self, italic=self.italic if italic is None else italic, bold=self.bold if bold is None else bold,
                       tracking=self.tracking if tracking is None else tracking,
                       condense=self.condense if condense is None else condense)


@functools.lru_cache(maxsize=256)
def make_lettering(spec: FontSpec, fonts_dir: str = "", italic: bool = False, bold: bool = False,
                   emphasis: bool = True) -> Lettering:
    """The lettering for the font *spec* with *italic* and *bold*, using the cuts of its family this computer has."""
    base = face_of(spec.path) if spec.path else None
    italic_path = bold_path = bold_italic_path = None
    if base is not None:
        base_bold = spec.bold_variation or _named(_BOLD_WORDS, base.subfamily)
        family = [f for f in font_faces(Path(fonts_dir) if fonts_dir else None)
                  if _key(f.family) == _key(base.family) and f.path != spec.path]
        italics = [f for f in family if _named(_ITALIC_WORDS, f.subfamily)]
        same_weight = [f for f in italics if _named(_BOLD_WORDS, f.subfamily) == base_bold]
        italic_path = (same_weight or italics)[0].path if italics else None
        heavy = _HEAVY_WORDS if base_bold else _BOLD_WORDS
        uprights = [f for f in family if _named(heavy, f.subfamily) and not _named(_ITALIC_WORDS, f.subfamily)]
        bold_path = uprights[0].path if uprights else None
        heavy_italics = [f for f in italics if _named(heavy, f.subfamily)]
        bold_italic_path = heavy_italics[0].path if heavy_italics else None
    return Lettering(spec.path, spec.bold_variation, italic, bold, italic_path, bold_path, bold_italic_path, emphasis)


def _shape(text: str, i: int) -> tuple[bool, bool]:
    """Of the asterisk at *i*: (a word ends before it, a word starts after it)."""
    n = len(text)
    return (i > 0 and not text[i - 1].isspace() and text[i - 1] != MARK,
            i + 1 < n and not text[i + 1].isspace() and text[i + 1] != MARK)


def _marks(text: str) -> list[int]:
    return [i for i, ch in enumerate(text) if ch == MARK and any(_shape(text, i))]


def emphasis_marks(text: str) -> list[int]:
    """Where in *text* the emphasis markers stand (an asterisk with spaces on both sides is just a character)."""
    return _marks(text)


def split_runs(text: str) -> list[tuple[str, bool]]:
    """The (text, stressed) runs of a line whose stressed words are marked *like this*.

    A marker at the start of a word opens a span and one at the end closes it; a line that begins inside a span
    (its opener on the line before) has a closer first. An asterisk with spaces on both sides is just a character.
    """
    n = len(text)
    marks = _marks(text)
    if not marks:
        return [(text, False)] if text else []
    before, after = _shape(text, marks[0])
    on = before and not after
    runs: list[tuple[str, bool]] = []
    pos = 0
    for i in marks:
        if i > pos:
            runs.append((text[pos:i], on))
        on = not on
        pos = i + 1
    if pos < n:
        runs.append((text[pos:], on))
    return runs


def strip_marks(text: str) -> str:
    """The text without its emphasis markers."""
    return "".join(run for run, _ in split_runs(text))


def balance_marks(text: str) -> str:
    """*text* as it is when its emphasis markers pair up, without any of them when they do not: a stray asterisk
    from the model would otherwise stress half a line."""
    marks = _marks(text)
    if len(marks) % 2 == 0:
        return text
    gone = set(marks)
    return "".join(ch for i, ch in enumerate(text) if i not in gone)


def _length(font: FontT, text: str) -> float:
    try:
        return float(font.getlength(text))
    except AttributeError:  # pragma: no cover - a bitmap font
        left, _, right, _ = font.getbbox(text)
        return float(right - left)


def _joins(ch: str) -> bool:
    """Whether *ch* is drawn on the character before it (a combining mark, a joiner, a variation selector)."""
    return (unicodedata.category(ch) in ("Mn", "Me", "Mc") or unicodedata.combining(ch) > 0
            or ch in "‍︎️")


_VIRAMAS = frozenset("\u094d\u09cd")  # Devanagari's and Bengali's: the letter after one makes a conjunct with it


def clusters(text: str) -> list[tuple[int, str]]:
    """The characters of *text* as letter spacing sets them apart: each with the marks that combine with it (and,
    where the script is shaped, a conjunct's letters together: a letter after a virama), and where it starts in
    *text*."""
    out: list[tuple[int, str]] = []
    viramas = _VIRAMAS if shaping.available() else frozenset()  # (drawn letter by letter: as before)
    for i, ch in enumerate(text):
        if out and (_joins(ch) or out[-1][1].endswith("‍") or (out[-1][1][-1] in viramas and ch.isalpha())):
            start, cur = out[-1]
            out[-1] = (start, cur + ch)
        else:
            out.append((i, ch))
    return out


def _metrics(font: FontT) -> tuple[int, int]:
    try:
        ascent, descent = font.getmetrics()
    except AttributeError:  # pragma: no cover - a bitmap font
        _, top, _, bottom = font.getbbox("Hg")
        ascent, descent = bottom, 0
    return int(ascent), int(descent)


@dataclass(frozen=True)
class Face:
    """A face in use: the file and weight to load, the shear of a synthetic italic, the stroke of a synthetic bold."""

    path: str | None
    bold_variation: bool = False
    weight: int = 700
    shear: float = 0.0
    stroke: int = 0

    def font(self, size: int) -> FontT:
        return load_font(self.path, size, self.bold_variation, self.weight)


def _run_length(face: Face, size: int, text: str) -> float:
    """*text*'s advance in *face* at *size*: shaped where its script needs it (`shaping.for_text`), else as Pillow lays
    it out."""
    shaper = shaping.for_text(face.path, size, face.bold_variation, face.weight, text)
    return shaper.length(text) if shaper is not None else _length(face.font(size), text)


def _put(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, face: Face, size: int, fill: object,
         stroke_width: int = 0, stroke_fill: object = None) -> None:
    """`ImageDraw.text` of *text* in *face* at *size*, shaped where its script needs it (`shaping.for_text`)."""
    shaper = shaping.for_text(face.path, size, face.bold_variation, face.weight, text)
    if shaper is not None:
        shaper.draw(draw, xy, text, fill, stroke_width, stroke_fill)
    else:
        draw.text(xy, text, font=face.font(size), fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)


def shaped_rows(face: Face, size: int, text: str) -> tuple[int, int] | None:
    """The rows *text*'s ink covers below a line's top in *face* at *size* when its script is shaped
    (`shaping.Shaper.rows`); None when Pillow lays it out (its own ``getbbox`` then says)."""
    shaper = shaping.for_text(face.path, size, face.bold_variation, face.weight, text)
    return shaper.rows(text) if shaper is not None else None


class StyledFont:
    """A lettering at one size: it measures and draws text whose stressed words are marked *like this*, so the
    typesetter can treat it as a font (``width``, ``getlength``, ``draw``)."""

    def __init__(self, lettering: Lettering, size: int):
        self.lettering = lettering
        self.size = max(1, int(size))
        self.base = self._face(lettering.italic, lettering.bold)
        self.emph = self._face(True, True) if lettering.emphasis else self.base
        self._widths: dict[str, float] = {}  # text -> its width uncondensed (the typesetter asks again and again)

    def _face(self, italic: bool, bold: bool) -> Face:
        """The face for a style: a real cut of the family when there is one, else a shear and a stroke. Stressed
        words in a bold region keep its weight (the heavy cut leant) rather than taking a lighter italic cut."""
        lt, size = self.lettering, self.size
        stroke = max(1, round(size / 24)) if size >= STROKE_FROM else 0
        if italic and bold:
            if lt.bold_italic_path:
                return Face(lt.bold_italic_path, True)
            if lt.bold and lt.bold_path:
                return Face(lt.bold_path, True, shear=ITALIC_SHEAR)
            if lt.italic_path:
                return Face(lt.italic_path, True, stroke=stroke)
            if lt.bold_variation:
                return Face(lt.path, True, HEAVY_WEIGHT, ITALIC_SHEAR)
            return Face(lt.path, lt.bold_variation, shear=ITALIC_SHEAR, stroke=stroke)
        if italic:
            if lt.italic_path:
                return Face(lt.italic_path, True)
            return Face(lt.path, lt.bold_variation, shear=ITALIC_SHEAR)
        if bold:
            if lt.bold_path:
                return Face(lt.bold_path, True)
            if lt.bold_variation:
                return Face(lt.path, True, HEAVY_WEIGHT)
            return Face(lt.path, lt.bold_variation, stroke=stroke)
        return Face(lt.path, lt.bold_variation)

    def width(self, text: str) -> int:
        if self.lettering.condense != 1.0:  # as wide as uncondensed, times the factor
            plain = _styled(replace(self.lettering, condense=1.0), self.size)
            return int(round(plain._natural(text) * self.lettering.condense))
        return int(round(self._natural(text)))

    def _natural(self, text: str) -> float:
        """*text*'s width uncondensed (remembered)."""
        total = self._widths.get(text)
        if total is not None:
            return total
        total = 0.0
        runs = split_runs(text)
        for run, stressed in runs:
            face = self.emph if stressed else self.base
            total += _run_length(face, self.size, run) + 2 * face.stroke
        if self.lettering.tracking:  # the room between two characters, the last one's after it left out
            total += self.lettering.tracking * max(0, len(clusters("".join(run for run, _ in runs))) - 1)
        if len(self._widths) >= 4096:
            self._widths.clear()
        self._widths[text] = total
        return total

    def getlength(self, text: str) -> float:  # as a Pillow font
        return float(self.width(text))

    def getmetrics(self) -> tuple[int, int]:
        return _metrics(self.base.font(self.size))

    def draw(self, image: Image.Image, x: float, y: float, text: str, fill: tuple[int, int, int],
             outline: tuple[tuple[int, int, int], int] | None = None) -> None:
        """Draw *text* with its top left at (x, y), the stressed runs in the emphasis face, no markers; with
        *outline* (a colour and a width in pixels), a contour of that colour around every glyph, for text set on a
        drawing. With letter spacing, each character (with its combining marks) is set at its place in the run plus
        the room before it; condensed, the line is as narrow as `width` says (`_draw_condensed`)."""
        if self.lettering.condense != 1.0:
            self._draw_condensed(image, x, y, text, fill, outline)
            return
        draw = ImageDraw.Draw(image)
        tracking = self.lettering.tracking
        size = self.size
        for run, stressed in split_runs(text):
            face = self.emph if stressed else self.base
            if tracking:
                pieces = [(cluster, _run_length(face, size, run[:start]) + n * tracking)
                          for n, (start, cluster) in enumerate(clusters(run))]
                if outline is not None:
                    colour, width = outline
                    for cluster, dx in pieces:
                        if face.shear:
                            _draw_sheared(image, face, size, x + dx, y, cluster, colour, face.stroke + width)
                        else:
                            _put(draw, (x + dx + face.stroke, y), cluster, face, size, colour, face.stroke + width,
                                 colour)
                for cluster, dx in pieces:
                    if face.shear:
                        _draw_sheared(image, face, size, x + dx, y, cluster, fill)
                    else:
                        _put(draw, (x + dx + face.stroke, y), cluster, face, size, fill, face.stroke, fill)
                x += _run_length(face, size, run) + 2 * face.stroke + tracking * len(pieces)
                continue
            if outline is not None:
                colour, width = outline
                if face.shear:
                    _draw_sheared(image, face, size, x, y, run, colour, face.stroke + width)
                else:
                    _put(draw, (x + face.stroke, y), run, face, size, colour, face.stroke + width, colour)
            if face.shear:
                _draw_sheared(image, face, size, x, y, run, fill)
            else:
                _put(draw, (x + face.stroke, y), run, face, size, fill, face.stroke, fill)
            x += _run_length(face, size, run) + 2 * face.stroke

    def _draw_condensed(self, image: Image.Image, x: float, y: float, text: str, fill: tuple[int, int, int],
                        outline: tuple[tuple[int, int, int], int] | None) -> None:
        """A condensed line: drawn uncondensed at twice the size into masks (the contour's, when there is one, then
        the glyphs'), each brought back to size exactly as wide as `width` measures the line, and pasted in its
        colour."""
        lt = self.lettering
        big = _styled(replace(lt, condense=1.0, tracking=2 * lt.tracking), 2 * self.size)
        ascent, descent = big.getmetrics()
        reach = 2 * (outline[1] if outline is not None else 0) + max(big.base.stroke, big.emph.stroke)
        pad = 4 + reach + int(ITALIC_SHEAR * (ascent + descent))  # room for the contour, the strokes, a lean
        wide = max(1, big.width(text))
        across = self.width(text) / wide  # the horizontal scale: twice the size, condensed, to the width measured
        w, h = wide + 2 * pad, ascent + descent + 2 * pad
        size = (max(1, int(round(w * across))), max(1, int(round(h / 2))))
        # rounded half up, so that the line lands on the same pixels on a part of the page as on all of it
        at = (math.floor(x - pad * across + 0.5), math.floor(y - pad / 2 + 0.5))
        layers = ([(outline[0], (255, 2 * outline[1]))] if outline is not None else []) + [(fill, None)]
        for colour, contour in layers:
            mask = Image.new("L", (max(2, w), max(2, h)), 0)
            big.draw(mask, pad, pad, text, 255, contour)  # type: ignore[arg-type]
            image.paste(colour, at, mask.resize(size, Image.LANCZOS))


def _draw_sheared(image: Image.Image, face: Face, size: int, x: float, y: float, text: str,
                  fill: tuple[int, int, int], stroke_px: int | None = None) -> None:
    """A synthetic italic: the run is drawn at twice the size into a mask, leant right about its baseline, brought
    back to size and pasted in *fill* (the doubling keeps the weight of the strokes through the resampling).
    *stroke_px* widens the strokes beyond the face's own (an outline pass)."""
    big = face.font(2 * size)
    own = face.stroke if stroke_px is None else stroke_px
    stroke = 2 * own
    ascent, descent = _metrics(big)
    h = ascent + descent + 2 * stroke + 4
    lean = int(face.shear * h) + 4
    w = int(round(_run_length(face, 2 * size, text))) + 2 * stroke + lean + 4
    mask = Image.new("L", (max(2, w), max(2, h)), 0)
    _put(ImageDraw.Draw(mask), (stroke, stroke), text, face, 2 * size, 255, stroke, 255)
    baseline = ascent + stroke
    leant = mask.transform(mask.size, Image.AFFINE, (1, face.shear, -face.shear * baseline, 0, 1, 0),
                           resample=Image.BILINEAR)
    small = leant.resize((max(1, mask.width // 2), max(1, mask.height // 2)), Image.LANCZOS)
    image.paste(fill, (int(round(x)) + face.stroke - own, int(round(y)) - own), small)


@functools.lru_cache(maxsize=512)
def _styled(lettering: Lettering, size: int) -> StyledFont:
    return StyledFont(lettering, size)


def styled_font(font: str | Lettering | None, size: int, bold_variation: bool = False) -> StyledFont:
    """The StyledFont for a font file (plain lettering) or a Lettering, at *size*."""
    lettering = font if isinstance(font, Lettering) else Lettering(font, bold_variation)
    return _styled(lettering, max(1, int(size)))
