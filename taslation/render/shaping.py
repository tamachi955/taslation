"""Devanagari and Bengali shaped as their fonts' own rules shape them.

Pillow without libraqm lays text out one character after another: no conjuncts, a vowel sign drawn after the
consonant it stands before, a reph on the line instead of above it. (Pillow's Windows build has libraqm inside but
looks for a FriBiDi DLL at run time, which is LGPL and which TASlation does not ship, so raqm is off there.) Here
HarfBuzz, through ``uharfbuzz`` (Apache-2.0; HarfBuzz itself is under its MIT-style "Old MIT" licence), shapes a run
into the font's glyphs and the place of each, and Pillow's own FreeType renderer draws them: from a copy of the font,
made in memory and never written anywhere, whose character map gives every glyph a Private Use code point of its
own (``PUA`` + its number), so that each glyph is drawn by its number at the place HarfBuzz gives it. A run is as
wide as HarfBuzz's advances and its glyphs are drawn at those advances, so the width the typesetter measures is the
width drawn. Outlines, a synthetic bold's stroke, a synthetic italic's shear and condensing work as before: they are
done on what is drawn (`lettering`).

Only a run with Devanagari or Bengali letters is shaped (`script_tag`); every other run is laid out by Pillow as
before, byte for byte. Where uharfbuzz cannot be imported (`available` False), the two scripts are drawn letter by
letter as before, and the window says so (`letter_by_letter`).
"""

from __future__ import annotations

import functools
import io
import math
import re
import struct
from pathlib import Path
from typing import Any

from PIL import ImageFont, features

from .fonts import load_font, split_face, weight_axes

PUA = 0xF0000  # glyph n of a font is code point PUA + n in its copy (plane 15, Supplementary Private Use Area-A)
_LAST_PUA = 0xFFFFD
SHAPED_LANGUAGES = frozenset({"Hindi", "Bengali"})  # the target languages written in them (`ui.constants.LANGUAGES`)
_INDIC = re.compile("[\u0900-\u09ff]")
_DANDAS = frozenset("\u0964\u0965")  # in the Devanagari block, but Bengali writes them too: they decide nothing
_RUNS_KEPT = 8192  # shaped runs remembered (the typesetter measures the same words at many sizes)


@functools.lru_cache(maxsize=1)
def _harfbuzz() -> Any:
    try:  # Apache-2.0 binding, HarfBuzz built in (MIT-style)
        import uharfbuzz  # type: ignore
    except Exception:  # noqa: BLE001 - missing or broken: the scripts are drawn letter by letter, and said so
        return None
    return uharfbuzz


def available() -> bool:
    """Whether runs can be shaped here (uharfbuzz imports)."""
    return _harfbuzz() is not None


def letter_by_letter(language: str) -> bool:
    """Whether a translation into *language* (an English name of the "To:" list) would be drawn letter by letter on
    this computer: it is written in a script that needs shaping, uharfbuzz is not there, and neither is a Pillow with
    libraqm (which shapes by itself)."""
    return language in SHAPED_LANGUAGES and not available() and not _raqm()


@functools.lru_cache(maxsize=1)
def _raqm() -> bool:
    try:
        return bool(features.check_feature("raqm"))
    except Exception:  # noqa: BLE001
        return False


def script_tag(text: str) -> str | None:
    """HarfBuzz's tag of the script *text* is shaped in ("deva", "beng"), by the letters of the two scripts it holds
    (the more frequent wins); None when it holds none, and so is laid out as before."""
    if _INDIC.search(text) is None:
        return None
    deva = beng = 0
    for ch in text:
        if "\u0900" <= ch <= "\u097f" and ch not in _DANDAS:
            deva += 1
        elif "\u0980" <= ch <= "\u09ff":
            beng += 1
    if not deva and not beng:
        return None
    return "beng" if beng > deva else "deva"


# --- the font's copy whose character map names every glyph ---------------------------------------------------

def _sfnt(data: bytes, index: int, cmap: bytes | None = None, drop: frozenset[bytes] = frozenset()) -> bytes:
    """The face *index* of the font file *data* (a .ttc's face, or the one face of a .ttf / .otf) as a font file of
    its own, its 'cmap' table replaced by *cmap* when given and the tables *drop* names left out. The tables are
    copied as they are (their checksums made again; FreeType and HarfBuzz check neither them nor the whole file's)."""
    offset = 0
    if data[:4] == b"ttcf":
        count = struct.unpack_from(">I", data, 8)[0]
        if index >= count:
            raise ValueError("no such face")
        offset = struct.unpack_from(">I", data, 12 + 4 * index)[0]
    version = data[offset:offset + 4]
    num = struct.unpack_from(">H", data, offset + 4)[0]
    tables: dict[bytes, bytes] = {}
    for i in range(num):
        tag, _check, start, length = struct.unpack_from(">4sIII", data, offset + 12 + 16 * i)
        if start + length > len(data):
            raise ValueError("a table past the end of the file")
        tables[tag] = data[start:start + length]
    if b"maxp" not in tables:
        raise ValueError("no maxp table")
    if cmap is not None:
        tables[b"cmap"] = cmap
    for tag in drop:
        tables.pop(tag, None)
    tags = sorted(tables)
    n = len(tags)
    selector = max(i for i in range(17) if 2 ** i <= n)
    search = 16 * 2 ** selector
    head = version + struct.pack(">HHHH", n, search, selector, 16 * n - search)
    at = 12 + 16 * n
    records, blobs = [], []
    for tag in tags:
        table = tables[tag]
        padded = table + b"\0" * (-len(table) % 4)
        checksum = sum(struct.unpack(f">{len(padded) // 4}I", padded)) & 0xFFFFFFFF
        records.append(struct.pack(">4sIII", tag, checksum, at, len(table)))
        blobs.append(padded)
        at += len(padded)
    return head + b"".join(records) + b"".join(blobs)


def _glyph_cmap(glyphs: int) -> bytes:
    """A 'cmap' table with one subtable (Windows, Unicode full repertoire, format 12) that maps PUA + n to glyph n."""
    last = min(PUA + max(1, glyphs) - 1, _LAST_PUA)
    subtable = struct.pack(">HHIIIIII", 12, 0, 28, 0, 1, PUA, last, 0)
    return struct.pack(">HHHHI", 0, 1, 3, 10, 12) + subtable


# Tables FreeType does not read to draw a glyph: left out of the drawing copy, which Pillow holds once per size
_LAYOUT_TABLES = frozenset({b"GSUB", b"GPOS", b"GDEF", b"BASE", b"JSTF", b"MATH", b"DSIG", b"morx", b"kerx", b"feat"})


@functools.lru_cache(maxsize=4)
def _source(path: str) -> tuple[Any, bytes] | None:
    """For the font at *path* (a .ttc's face as "path#index"): HarfBuzz's face of it, and the bytes of its drawing
    copy (the character map naming every glyph); None when it cannot be read or shaping is not available."""
    hb = _harfbuzz()
    if hb is None:
        return None
    file, index = split_face(path)
    try:
        own = _sfnt(Path(file).read_bytes(), index)
        glyphs = struct.unpack_from(">H", own, _table_at(own, b"maxp") + 4)[0]
        named = _sfnt(own, 0, _glyph_cmap(glyphs), drop=_LAYOUT_TABLES)
        face = hb.Face(hb.Blob(own))
    except (OSError, ValueError, struct.error):
        return None
    return face, named


def _table_at(font: bytes, tag: bytes) -> int:
    num = struct.unpack_from(">H", font, 4)[0]
    for i in range(num):
        name, _check, start, _length = struct.unpack_from(">4sIII", font, 12 + 16 * i)
        if name == tag:
            return start
    raise ValueError(f"no {tag!r} table")


def _coords(path: str, bold_variation: bool, weight: int) -> tuple[float, ...] | None:
    """The design coordinates of a variable font's axes as `fonts.load_font` sets them (None: the default
    instance, as for a static font)."""
    if not bold_variation:
        return None
    try:
        return tuple(float(v) for v in weight_axes(load_font(path, 12), weight))
    except Exception:  # noqa: BLE001 - a static font: no axes, as `load_font` leaves it
        return None


@functools.lru_cache(maxsize=16)
def _hb_font(path: str, coords: tuple[float, ...] | None) -> Any:
    hb = _harfbuzz()
    face = _source(path)[0]  # type: ignore[index]
    font = hb.Font(face)
    if coords:
        font.set_var_coords_design(list(coords))
    return font


@functools.lru_cache(maxsize=_RUNS_KEPT)
def _shaped(path: str, coords: tuple[float, ...] | None, tag: str,
            text: str) -> tuple[tuple[tuple[int, int, int], ...], int]:
    """*text* shaped left to right in *tag*'s script: ((glyph, x, y) from the run's start, in font units, y up), and
    the run's advance."""
    hb = _harfbuzz()
    buf = hb.Buffer()
    buf.add_str(text)
    buf.direction = "ltr"
    buf.script = tag
    hb.shape(_hb_font(path, coords), buf, {})
    pen = 0
    glyphs = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        glyphs.append((int(info.codepoint), pen + pos.x_offset, pos.y_offset))
        pen += pos.x_advance
    return tuple(glyphs), pen


@functools.lru_cache(maxsize=4096)
def _extents(path: str, coords: tuple[float, ...] | None, gid: int) -> tuple[int, int]:
    """(top, bottom) of glyph *gid*'s ink above the baseline, in font units ((0, 0): no ink)."""
    extents = _hb_font(path, coords).get_glyph_extents(gid)
    if extents is None or not extents.height:
        return 0, 0
    return int(extents.y_bearing), int(extents.y_bearing + extents.height)


@functools.lru_cache(maxsize=16)
def _drawing_font(path: str, size: int, coords: tuple[float, ...] | None) -> ImageFont.FreeTypeFont:
    """The drawing copy at *size*. Pillow keeps its own copy of the font's bytes for each size, so only the sizes
    drawn at are made (measuring needs HarfBuzz alone), and only the last few are kept."""
    font = ImageFont.truetype(io.BytesIO(_source(path)[1]), size,  # type: ignore[index]
                              layout_engine=ImageFont.Layout.BASIC)
    if coords:
        font.set_variation_by_axes(list(coords))
    return font


class Shaper:
    """A font at one size, shaping runs and drawing their glyphs: what `lettering` asks instead of Pillow for a run
    `script_tag` names a script of."""

    def __init__(self, path: str, size: int, coords: tuple[float, ...] | None, ascent: int):
        self.path, self.size, self.coords, self.ascent = path, size, coords, ascent
        self.scale = size / _source(path)[0].upem  # type: ignore[index]

    def glyphs(self, text: str) -> list[tuple[int, float, float]]:
        """The glyphs of *text* as drawn: (glyph id, x, y) in pixels from the run's start, y down."""
        tag = script_tag(text) or "deva"
        placed, _advance = _shaped(self.path, self.coords, tag, text)
        k = self.scale
        return [(gid, x * k, -y * k) for gid, x, y in placed]

    def length(self, text: str) -> float:
        """The advance of *text*, shaped."""
        return _shaped(self.path, self.coords, script_tag(text) or "deva", text)[1] * self.scale

    def rows(self, text: str) -> tuple[int, int]:
        """The rows the ink of *text* covers below a line's top (its ascender line, where Pillow's anchor "la" puts
        it), shaped, from the glyphs' outlines: what `typeset._rows_of` measures from Pillow's boxes, to a pixel."""
        top, bottom = math.inf, -math.inf
        for gid, _x, y in self.glyphs(text):
            high, low = _extents(self.path, self.coords, gid)
            if high > low:
                top, bottom = min(top, y - high * self.scale), max(bottom, y - low * self.scale)
        if bottom <= top:
            return 0, 0
        return self.ascent + int(math.floor(top)), self.ascent + int(math.ceil(bottom))

    def draw(self, draw: Any, xy: tuple[float, float], text: str, fill: Any, stroke_width: float = 0,
             stroke_fill: Any = None) -> None:
        """Draw *text* shaped with its line's top left at *xy*, as `ImageDraw.text` draws a string: with
        *stroke_width*, every glyph's stroke in *stroke_fill* (None: *fill*) first, then the glyphs in *fill* when that
        is another colour."""
        font = _drawing_font(self.path, self.size, self.coords)
        x0, y0 = xy
        placed = [(chr(PUA + gid), (x0 + x, y0 + y)) for gid, x, y in self.glyphs(text)]
        if stroke_width:
            ink = fill if stroke_fill is None else stroke_fill
            for ch, at in placed:
                draw.text(at, ch, font=font, fill=ink, stroke_width=stroke_width, stroke_fill=ink)
            if ink == fill:
                return
        for ch, at in placed:
            draw.text(at, ch, font=font, fill=fill)


@functools.lru_cache(maxsize=512)
def shaper(path: str | None, size: int, bold_variation: bool = False, weight: int = 700) -> Shaper | None:
    """The Shaper of the font at *path* at *size* (a variable font at *weight* with *bold_variation*, as
    `fonts.load_font` loads it); None without a font file, where the font cannot be read, or without uharfbuzz."""
    if not path or _source(path) is None:
        return None
    size = max(1, int(size))
    ascent = load_font(path, size, bold_variation, weight).getmetrics()[0]  # a line's top, as Pillow draws it
    return Shaper(path, size, _coords(path, bold_variation, weight), int(ascent))


def for_text(path: str | None, size: int, bold_variation: bool, weight: int, text: str) -> Shaper | None:
    """The Shaper for drawing *text* in that font when *text* needs one (`script_tag`), else None: Pillow lays it out
    as before."""
    if script_tag(text) is None:
        return None
    return shaper(path, size, bold_variation, weight)
