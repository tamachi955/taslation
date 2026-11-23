"""The side panes of see-through mode, pure (no Tk, no window): what goes into them, where they go on the viewer's
ground, and their pictures (`ui.seethrough` fills them, `capture.seethrough` shows them).

* Two panes on the viewer's ground at the two outer edges of the capture area: the LEFT one holds the controls
  (`Row`s a click acts on), the RIGHT one the indicators (rows of text) under the bubble last under the pointer (three
  plates a click acts on, then its Japanese and its translation, each in its own script's font: `Row.lang`). Each is
  placed from the capture area's
  columns and the steady band of the viewer's frame (`place`): the left one GAP px in from the area's left edge, the
  right one GAP px in from its right edge, from the band's top GAP px down (the band: where a viewer's bars never
  come, so a pane never lies over them). So a pane stays where it is whatever the page's width (a cover alone, a
  spread); the page box only says whether it may show: a pane that would come within GAP px of the page, or that the
  band is too short for, is not placed (it hides) rather than cover the page.
* A pane's width (`width_for`): the left one as wide as its widest row asks (the text at FONT_PX, a toggle's box, the
  arrows of a choice, a row's square button, PAD each side), between MIN_W and MAX_W; the right one INDICATORS_W
  whatever its words say (a width that does not change with them); either no wider than its ground leaves (*room*).
  The words of a text row are wrapped to it, a control's never are, so the least a pane needs is its widest control,
  or MIN_W for words alone. In English at 100 % the controls take some 130-150 px (some 165 px in German), the words
  120 px at the least: the ground beside a spread in a 1920 x 1080 window (about 294 px) and on its full screen (about
  198 px) both give that and two gaps; a narrower ground (a narrow window, a wide page) hides the pane.
* A pane's picture (`render`): each row a rounded plate, the rows apart by ROW_GAP of nothing (alpha 0: where the
  viewer's ground shows, a click goes to the viewer); a row may end in a square plate of its own, a button drawn as a
  glyph (`Row.square`: the circular arrow of "translate this page again"); the colours follow the ground's
  (`colours`: light on a dark ground, dark on a light one). The hit boxes of the controls come with it, in the
  picture's pixels.
* The words the right pane shows from the window (its status line, its status slot) name no key (`without_keys`):
  in see-through mode the keys go to the viewer, so "F5 tries again" and the like are left out.

Every pixel size here is at 96 DPI and goes with the viewer's (`seethrough.scaled`)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .seethrough import scaled

Box = tuple[int, int, int, int]

GAP = 8  # px between a pane and the capture area's edge, and at least between a pane and the page
PAD = 8  # px of plate before and after a row's content
ROW_PAD = 5  # px of plate above and below a row's text
ROW_GAP = 4  # px of nothing between two rows (the viewer's ground: its clicks are the viewer's)
FONT_PX = 13  # the rows' text
TOGGLE_PX = 11  # a toggle's box
ARROW_PX = 14  # the room of each arrow of a choice
MIN_W, MAX_W = 120, 240  # a pane's width, whatever its rows ask
INDICATORS_W = 200  # the right pane's width (its ground less the gaps when that is less)
RADIUS = 5  # the plates' corners
ALPHA = 225  # the plates' opacity (of 255)
TEXT_LINES = 4  # the right pane's status text is wrapped into at most so many lines
CHOICE_LEAST = 72  # px of a choice's words at the least (a longer name is cut with an ellipsis to the pane's width)

# the window's language -> the system's fonts for its script (Windows; the first found); others: Segoe UI
FONTS = {"ja": ("YuGothM.ttc", "meiryo.ttc", "msgothic.ttc"), "zh": ("msyh.ttc", "simsun.ttc"),
         "zh-tw": ("msjh.ttc", "mingliu.ttc"), "ko": ("malgun.ttf", "gulim.ttc"), "th": ("leelawui.ttf", "tahoma.ttf")}
LATIN_FONTS = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")


@dataclass(frozen=True)
class Row:
    """A row of a pane: *name* what a click on it does ("" for none), *text* its words; *kind* "button", "toggle" (a box
    ticked when *on*), "choice" (an arrow each side: *name* + "_prev" / "_next") or "text" (words only); a row not
    *enabled* is drawn dim and takes no click; a *warn* row's words are orange (the page that could not be
    translated). *square*: the name of a button at the row's right end, a square plate of the row's height with a
    glyph (`GLYPHS`) and no words ("" for none), dim and taking no click when not *square_enabled*. *lang*: the
    language whose script the words are set in (`font`; "" the pane's: the window's language) - a bubble's Japanese,
    its translation; *lines*: a text row wrapped into at most so many lines (0: TEXT_LINES)."""

    name: str
    text: str
    kind: str = "button"
    on: bool = False
    enabled: bool = True
    warn: bool = False
    square: str = ""
    square_enabled: bool = True
    lang: str = ""
    lines: int = 0


@dataclass(frozen=True)
class Colours:
    plate: tuple[int, int, int]
    text: tuple[int, int, int]
    dim: tuple[int, int, int]
    accent: tuple[int, int, int]
    warn: tuple[int, int, int]  # a warn row's words (orange: Okabe-Ito's on dark, a darker one to read on light)


DARK = Colours(plate=(36, 36, 36), text=(232, 232, 232), dim=(140, 140, 140), accent=(86, 180, 233),
               warn=(230, 159, 0))
LIGHT = Colours(plate=(232, 232, 232), text=(28, 28, 28), dim=(110, 110, 110), accent=(0, 114, 178),
                warn=(166, 86, 0))


def colours(ground: tuple[int, int, int] | None) -> Colours:
    """The panes' colours on the viewer's *ground* (RGB; None: not one colour - taken as dark)."""
    if ground is None:
        return DARK
    r, g, b = ground
    return LIGHT if 0.299 * r + 0.587 * g + 0.114 * b >= 128 else DARK


@dataclass(frozen=True)
class Picture:
    """A pane's picture: premultiplied BGRA (H, W, 4) and the hit boxes of its controls, (name, box) in its pixels."""

    bgra: np.ndarray
    hits: tuple[tuple[str, Box], ...]

    @property
    def size(self) -> tuple[int, int]:
        return int(self.bgra.shape[1]), int(self.bgra.shape[0])

    def hit(self, x: int, y: int) -> str:
        """The control at (*x*, *y*) of the picture, "" for none."""
        for name, (left, top, right, bottom) in self.hits:
            if left <= x < right and top <= y < bottom:
                return name
        return ""


# ------------------------------------------------------------------ fonts
def _font_dirs() -> list[Path]:
    from .render.fonts import _system_font_dirs

    return _system_font_dirs()


@lru_cache(maxsize=16)
def font_path(language: str) -> str | None:
    """The system font the panes' text in the window's *language* is set in; None: Pillow's own."""
    names = FONTS.get(language, ()) + LATIN_FONTS
    for name in names:
        for folder in _font_dirs():
            path = folder / name
            if path.is_file():
                return str(path)
    return None


@lru_cache(maxsize=32)
def font(language: str, px: int) -> Any:
    path = font_path(language)
    if path is not None:
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            pass
    return ImageFont.load_default(px)


# ------------------------------------------------------------------ sizes
def _text_w(face: Any, text: str) -> int:
    return int(np.ceil(face.getlength(text))) if text else 0


def _lead(row: Row, dpi: float) -> int:
    """The room before a row's text: a toggle's box and its gap, an arrow."""
    if row.kind == "toggle":
        return scaled(TOGGLE_PX + 6, dpi)
    if row.kind == "choice":
        return scaled(ARROW_PX, dpi)
    return 0


def row_height(face: Any, dpi: float, lines: int = 1) -> int:
    ascent, descent = face.getmetrics()
    return lines * (ascent + descent) + 2 * scaled(ROW_PAD, dpi)


def width_for(rows: list[Row], language: str, dpi: float, room: int | None = None, fill: bool = False) -> int | None:
    """The width a pane of *rows* takes (at *dpi*): its widest row (its text, a toggle's box, a choice's arrows, a
    square button, PAD each side), between MIN_W and MAX_W - with *fill*, INDICATORS_W whatever its rows say (the
    indicators: a width that does not change with what they say) -, and no wider than *room* (the px its ground leaves
    it; None: any). A text row's
    words are wrapped to the width, a control's are not: so the least it needs is its widest control row, or MIN_W -
    None when *room* is less than that (the pane hides)."""
    face = font(language, scaled(FONT_PX, dpi))
    widest = 0
    need = scaled(MIN_W, dpi)
    square = row_height(face, dpi) + scaled(ROW_GAP, dpi)  # (a row's square button and the gap before it)
    for row in rows:
        text = _text_w(font(row.lang, scaled(FONT_PX, dpi)) if row.lang else face, row.text)
        extra = _lead(row, dpi) + (scaled(ARROW_PX, dpi) if row.kind == "choice" else 0) + \
            (square if row.square else 0)
        width = text + extra + 2 * scaled(PAD, dpi)
        widest = max(widest, width)
        if row.kind == "choice":  # (a long name between the arrows is cut: "Portuguese (Bra...")
            need = max(need, min(width, extra + 2 * scaled(PAD, dpi) + scaled(CHOICE_LEAST, dpi)))
        elif row.kind != "text":
            need = max(need, width)
    width = max(need, scaled(INDICATORS_W, dpi) if fill else min(scaled(MAX_W, dpi), widest))
    if room is not None:
        if room < need:
            return None
        width = min(width, room)
    return width


def rooms(size: tuple[int, int], page: Box, dpi: float, columns: tuple[int, int] | None = None) -> tuple[int, int]:
    """The px the ground left and right of *page* leaves a pane in a frame of *size* whose capture area spans the
    *columns* (x from, x to; None: the whole frame): from the area's edge to the page, less GAP each side."""
    gap = scaled(GAP, dpi)
    first, last = columns if columns is not None else (0, size[0])
    return page[0] - first - 2 * gap, last - page[2] - 2 * gap


def wrap(face: Any, text: str, width: int, most: int = TEXT_LINES) -> list[str]:
    """*text* broken into lines no wider than *width* at *face* (at spaces; a word wider than that, or text with no
    spaces - Japanese, Chinese, Thai -, at any character), at most *most* lines, the last cut with an ellipsis."""
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for piece in _pieces(paragraph):
            trial = line + piece
            if line and _text_w(face, trial.rstrip()) > width:
                lines.append(line.rstrip())
                line = piece.lstrip()
            else:
                line = trial
        lines.append(line.rstrip())
    if len(lines) > most:
        lines = lines[:most]
        last = lines[-1]
        while last and _text_w(face, last + "...") > width:
            last = last[:-1]
        lines[-1] = last + "..."
    return [ln for ln in lines if ln] or [""]


def cut(face: Any, text: str, width: int) -> str:
    """*text* as it fits *width* at *face*: whole, or cut with an ellipsis."""
    if _text_w(face, text) <= width:
        return text
    while text and _text_w(face, text.rstrip() + "...") > width:
        text = text[:-1]
    return text.rstrip() + "..."


def _pieces(text: str) -> list[str]:
    """*text* as the pieces a line may break after: words with their space, or single characters where a script
    writes no spaces."""
    out: list[str] = []
    word = ""
    for ch in text:
        if ch == " ":
            out.append(word + " ")
            word = ""
        elif ord(ch) >= 0x0E00 and not ch.isascii():  # (Thai, CJK and the like: a break may come anywhere)
            if word:
                out.append(word)
                word = ""
            out.append(ch)
        else:
            word += ch
    if word:
        out.append(word)
    return out


# ------------------------------------------------------------------ the picture
GLYPHS = ("again",)  # the glyphs a square button may have (`glyph`)


@lru_cache(maxsize=16)
def glyph(name: str, size: int, ink: tuple[int, int, int], dpi: float) -> Image.Image:
    """A square button's glyph, *size* px square, in *ink* (RGBA, transparent around it), drawn here at four times
    the size and brought down (smooth edges). "again": a circular arrow - a ring open at its top right, the arrow's
    head at its upper end pointing on round the ring, clockwise (translate this page again)."""
    if name not in GLYPHS:
        raise ValueError(f"no glyph {name!r}")
    big = size * 4
    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)
    centre = big / 2
    radius = big * 0.23
    stroke = max(4, round(big * 0.075))
    start, end = -40.0, 250.0  # (degrees from three o'clock, clockwise: the ring from half past one round to eleven)
    draw.arc((centre - radius - stroke / 2, centre - radius - stroke / 2, centre + radius + stroke / 2,
              centre + radius + stroke / 2), start, end, fill=255, width=stroke)
    theta = np.radians(end)
    at = np.array((centre + radius * np.cos(theta), centre + radius * np.sin(theta)))
    on = np.array((-np.sin(theta), np.cos(theta)))  # (the way round the ring, clockwise on the screen)
    out = np.array((np.cos(theta), np.sin(theta)))  # (away from the centre)
    length, half = big * 0.17, big * 0.14
    head = [tuple(at + on * length), tuple(at + out * half - on * length * 0.25),
            tuple(at - out * half - on * length * 0.25)]
    draw.polygon(head, fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    mark = Image.new("RGBA", (size, size), (*ink, 0))
    mark.putalpha(mask)
    return mark


def render(rows: list[Row], width: int, language: str, dpi: float, scheme: Colours) -> Picture:
    """The picture of a pane of *rows*, *width* px wide (`width_for`), at *dpi*, in *scheme*'s colours."""
    pane_face = font(language, scaled(FONT_PX, dpi))
    pad, gap = scaled(PAD, dpi), scaled(ROW_GAP, dpi)
    plates: list[tuple[Row, Any, list[str], int]] = []
    for row in rows:
        face = font(row.lang, scaled(FONT_PX, dpi)) if row.lang else pane_face
        lines = (wrap(face, row.text, width - 2 * pad - _lead(row, dpi), row.lines or TEXT_LINES)
                 if row.kind == "text" else [row.text])
        plates.append((row, face, lines, row_height(face, dpi, len(lines))))
    height = sum(h for _r, _f, _l, h in plates) + gap * max(0, len(plates) - 1)
    image = Image.new("RGBA", (width, max(1, height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    hits: list[tuple[str, Box]] = []
    y = 0
    radius = scaled(RADIUS, dpi)
    for row, face, lines, h in plates:
        ascent, descent = face.getmetrics()
        line_h = ascent + descent
        plate_w = width - (h + gap if row.square else 0)  # (a square button takes the row's right end)
        draw.rounded_rectangle((0, y, plate_w - 1, y + h - 1), radius=radius, fill=(*scheme.plate, ALPHA))
        if row.square:
            draw.rounded_rectangle((width - h, y, width - 1, y + h - 1), radius=radius, fill=(*scheme.plate, ALPHA))
            mark = glyph(row.square, h, scheme.text if row.square_enabled else scheme.dim, dpi)
            image.alpha_composite(mark, (width - h, y))
            if row.square_enabled:
                hits.append((row.square, (width - h, y, width, y + h)))
        ink = scheme.warn if row.warn else scheme.text if row.enabled else scheme.dim
        x = pad
        top = y + scaled(ROW_PAD, dpi)
        if row.kind == "toggle":
            size = scaled(TOGGLE_PX, dpi)
            by = y + (h - size) // 2
            box = (x, by, x + size - 1, by + size - 1)
            if row.on:
                draw.rectangle(box, fill=(*scheme.accent, 255))
                draw.line((box[0] + size * 0.2, by + size * 0.5, box[0] + size * 0.42, by + size * 0.75,
                           box[0] + size * 0.8, by + size * 0.25), fill=(*scheme.plate, 255),
                          width=max(1, scaled(2, dpi)))
            else:
                draw.rectangle(box, outline=(*ink, 255), width=max(1, scaled(1, dpi)))
            x += _lead(row, dpi)
        if row.kind == "choice":
            arrow = scaled(ARROW_PX, dpi)
            mid = y + h // 2
            half = max(2, scaled(4, dpi))
            draw.polygon([(pad + half, mid - half), (pad + half, mid + half), (pad, mid)], fill=(*ink, 255))
            right = width - pad
            draw.polygon([(right - half, mid - half), (right - half, mid + half), (right, mid)], fill=(*ink, 255))
            lines = [cut(face, row.text, width - 2 * pad - 2 * arrow)]
            text_w = _text_w(face, lines[0])
            x = pad + arrow + max(0, (width - 2 * pad - 2 * arrow - text_w) // 2)
            if row.enabled and row.name:
                hits.append((row.name + "_prev", (0, y, width // 2, y + h)))
                hits.append((row.name + "_next", (width // 2, y, width, y + h)))
        for i, line in enumerate(lines):
            draw.text((x, top + i * line_h), line, font=face, fill=(*ink, 255))
        if row.kind in ("button", "toggle") and row.enabled and row.name:
            hits.append((row.name, (0, y, plate_w, y + h)))
        y += h + gap
    rgba = np.asarray(image, dtype=np.uint8)
    alpha = rgba[..., 3:4].astype(np.uint16)
    bgra = np.empty_like(rgba)
    bgra[..., :3] = (rgba[..., 2::-1].astype(np.uint16) * alpha // 255).astype(np.uint8)  # premultiplied
    bgra[..., 3] = rgba[..., 3]
    return Picture(np.ascontiguousarray(bgra), tuple(hits))


# ------------------------------------------------------------------ where they go
def place(size: tuple[int, int], page: Box, band: tuple[int, int], left: tuple[int, int] | None,
          right: tuple[int, int] | None, dpi: float,
          columns: tuple[int, int] | None = None) -> tuple[Box | None, Box | None]:
    """The boxes of the left and right panes (frame pixels) in a frame of *size* whose page is *page*, whose capture
    area spans the *columns* (x from, x to; None: the whole frame) and whose steady band (where a viewer's bars never
    come) is the rows *band*, the panes being *left* and *right* (width, height; None: no such pane). The left one goes
    GAP px in from the area's left edge, the right one GAP px in from its right edge - where they are whatever the
    page's width -, each from the band's top GAP px down; one that would come within GAP px of the page, or that the
    band is too short for (and two gaps), is None: a pane never covers the page."""
    width, height = size
    first, last = columns if columns is not None else (0, width)
    first, last = max(0, first), min(width, last)
    gap = scaled(GAP, dpi)
    top = max(0, band[0]) + gap
    bottom = min(height, band[1]) - gap

    def tall_enough(pane: tuple[int, int] | None) -> bool:
        return pane is not None and pane[1] <= bottom - top

    out_left = out_right = None
    if tall_enough(left):
        assert left is not None
        box = (first + gap, top, first + gap + left[0], top + left[1])
        if box[2] + gap <= page[0]:
            out_left = box
    if tall_enough(right):
        assert right is not None
        box = (last - gap - right[0], top, last - gap, top + right[1])
        if box[0] - gap >= page[2]:
            out_right = box
    return out_left, out_right


def overlap(a: Box | None, b: Box) -> int:
    """The pixels box *a* (None: none) and box *b* share."""
    if a is None:
        return 0
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


# ------------------------------------------------------------------ words that name no key
_KEY = r"(?:F(?:1[0-2]|[1-9])|Esc)"
KEY = re.compile(r"(?<![A-Za-z0-9])" + _KEY + r"(?![A-Za-z0-9])")  # a key named in a text ("F5", "F11", "Esc")
_ASIDE = re.compile(r"\s*[(（][^()（）]*[)）]")  # a bracketed aside
_ENDS = re.compile(r"(?<=[.!?])\s+"  # the end of a sentence (and the spaces after it)
                   r"|(?<=[。！？])"  # ... in Chinese and Japanese
                   r"|\s*[·・]\s*|\s+-\s+"  # the points between a line's parts, the joiner of a message's follow-ups
                   r"|(?<=[฀-๿)）])\s+(?=[฀-๿])"  # a space before a Thai word (Thai's sentences)
                   r"|(?<=[฀-๿])(?<!กด)(?<!และ)(?<!ปุ่ม)\s+(?=" + _KEY + r"\s)"  # ... before "F5 ..." in Thai
                   r"|\s+(?=" + _KEY + r"\s*[:：])")  # before "F5: ..."
_CLAUSE = re.compile(r"^(.*[^\s:：])\s*[:：]\s*(.*?)([.。!！]?)(\s*)$", re.S)  # (up to its last colon, after it)
_TRIM = " \t\n　·・-"


def without_keys(text: str) -> str:
    """*text* (in any of the window's languages) with what it says of keys left out, for see-through mode, where every
    key goes to the viewer: a bracketed aside naming a key goes ("(F5 in a browser)"); a sentence - or a part of a line
    between its points, or a Thai phrase - naming one goes, except that one naming it only after its last colon keeps
    what comes before ("2 line(s) not translated yet: press F5." -> "2 line(s) not translated yet."). "" when nothing
    is left."""
    if not KEY.search(text):
        return text
    text = _ASIDE.sub(lambda m: "" if KEY.search(m.group()) else m.group(), text)
    pieces: list[str] = []
    start = 0
    for match in _ENDS.finditer(text):
        if match.end() > start:
            pieces.append(text[start:match.end()])
            start = match.end()
    pieces.append(text[start:])
    kept: list[str] = []
    for piece in pieces:
        if not KEY.search(piece):
            kept.append(piece)
            continue
        clause = _CLAUSE.match(piece)
        if clause is not None and not KEY.search(clause.group(1)) and KEY.search(clause.group(2)):
            kept.append(clause.group(1) + clause.group(3) + clause.group(4))
    return "".join(kept).strip(_TRIM)


# a bracketed aside that names one of the window's menus, in the window's languages ("(Page menu)", "(menú Página)",
# "（ページメニュー）", ...): the panes have no menu bar - Set area... and the rest are in the controls at the left
_MENU_WORD = re.compile(r"(?i)men[uúü]|меню|メニュー|菜单|選單|메뉴|เมนู")


def pane_words(text: str) -> str:
    """*text* as a side pane says it (see-through mode, where TASlation's own window is not on the screen): what it
    says of keys left out (`without_keys`), and a bracketed aside that names one of the window's menus too. "" when
    nothing is left."""
    text = without_keys(text)
    if not _MENU_WORD.search(text):
        return text
    text = _ASIDE.sub(lambda m: "" if _MENU_WORD.search(m.group()) else m.group(), text)
    return re.sub(r"\s+([.,;:。、])", r"\1", text).strip(_TRIM)
