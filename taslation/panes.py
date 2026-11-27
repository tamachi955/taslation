"""The side panes of see-through mode, pure (no Tk, no window): what goes into them, where they go on the viewer's
ground, and their pictures (`ui.seethrough` fills them, `capture.seethrough` shows them).

* Two panes on the viewer's ground at the two outer edges of the capture area: the LEFT one holds the controls
  (`Row`s a click acts on), the RIGHT one the indicators (rows of text) under the bubble last under the pointer (three
  plates a click acts on, then its Japanese and its translation, each in its own script's font: `Row.lang`). Each is
  placed from the capture area's
  columns, a page box and the steady band of the viewer's frame (`place`), from the band's top GAP px down (the
  band: where a viewer's bars never come, so a pane never lies over them): inside the area GAP px in from its edge,
  its edge toward the page GAP px from that box at the least and MAX_FROM_PAGE px at the most (on an ultrawide
  monitor the area's edge is far from a page in the middle). The box is not the page on show but the widest the
  page has been in frames of that size (`reaches`: per side the farthest out a page's edge has come beside which
  the pane fitted - the spread, once one was shown), so that a pane stands still while the reader turns from spreads
  to a single page and back, however far that page is. Where it goes in that span: where it was in frames of that
  size while that is still in it; else - a wider page than any before - the span's end nearest to that (it moves
  once, only as far as it must); with no place before, as far from the page as the span lets it (the area's edge
  where that is within MAX_FROM_PAGE of the page). A pane that does not fit beside the page on show (it would come
  within GAP px of it), or that the band is too short for, is not placed (it hides) rather than cover the page.
* A pane's width (`width_for`): the left one as wide as its widest row asks (the text at FONT_PX, a toggle's box, the
  mark of a list, a row's square button, PAD each side), between MIN_W and MAX_W; the right one INDICATORS_W
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
* The right pane by its rule (`render_column`): a column as high as the band (`column_height`). What changes - the
  bubble's block, whole, then the status rows - grows from the column's top down; what lasts - the foot: how much of
  the page is done, the mode, where the translator runs, the viewer, the target language and the book - stands at
  its bottom, each row at its place whatever the rows say (a row's height is that of the longest text it may say:
  `Row.alike`; one with nothing to say keeps its room). The changing rows that do not fit above the foot are left
  out, in the order the caller gives (the oldest and least urgent first, the warnings last); the foot's spare rows
  go only where the column is short, by its height alone.

Every pixel size here is at 96 DPI and goes with the viewer's (`seethrough.scaled`)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .seethrough import scaled

Box = tuple[int, int, int, int]

GAP = 8  # px between a pane and the capture area's edge, and at least between a pane and the page
MAX_FROM_PAGE = 300  # px at the most between a pane and the page (`place`)
PAD = 8  # px of plate before and after a row's content
ROW_PAD = 5  # px of plate above and below a row's text
ROW_GAP = 4  # px of nothing between two rows (the viewer's ground: its clicks are the viewer's)
FONT_PX = 13  # the rows' text
TOGGLE_PX = 11  # a toggle's box
LIST_MARK_PX = 14  # the room of a list's arrowhead at its plate's right end
MIN_W, MAX_W = 120, 240  # a pane's width, whatever its rows ask
INDICATORS_W = 200  # the right pane's width (its ground less the gaps when that is less)
RADIUS = 5  # the plates' corners
ALPHA = 225  # the plates' opacity (of 255)
TEXT_LINES = 4  # the right pane's status text is wrapped into at most so many lines
FOOT_SHARE = 0.5  # the right pane's foot leaves its spare rows out where it would take more of the column than this
LIST_LEAST = 72  # px of a list's words at the least (a longer name is cut with an ellipsis to the pane's width)

# the window's language -> the system's fonts for its script (Windows; the first found); others: Segoe UI
FONTS = {"ja": ("YuGothM.ttc", "meiryo.ttc", "msgothic.ttc"), "zh": ("msyh.ttc", "simsun.ttc"),
         "zh-tw": ("msjh.ttc", "mingliu.ttc"), "ko": ("malgun.ttf", "gulim.ttc"), "th": ("leelawui.ttf", "tahoma.ttf")}
LATIN_FONTS = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")


@dataclass(frozen=True)
class Row:
    """A row of a pane: *name* what a click on it does ("" for none), *text* its words; *kind* "button" (drawn pressed
    when *on* - its plate in the accent colour: what it began is under way, Add area), "toggle" (a box ticked when
    *on*), "list" (a button that opens a list - the target languages -, its plate ending in a small arrowhead that
    says so: `LIST_MARK_PX`; a long text is cut with an ellipsis) or "text" (words only); a row not
    *enabled* is drawn dim and takes no click; a *warn* row's words are orange (the page that could not be
    translated). *square*: the name of a button at the row's right end, a square plate of the row's height with a
    glyph (`GLYPHS`) and no words ("" for none), dim and taking no click when not *square_enabled*. *lang*: the
    language whose script the words are set in (`font`; "" the pane's: the window's language) - a bubble's Japanese,
    its translation; *lines*: a text row wrapped into at most so many lines (0: TEXT_LINES). A row of the right
    pane's foot (`render_column`) keeps its height whatever it says: *alike* holds the other texts it may say, and
    its plate is as high as the longest of them all wraps to; one whose *text* is "" keeps its room with nothing
    drawn (the line of the page filling in, while none is); a *spare* one is left out where the foot would take
    more than FOOT_SHARE of the column."""

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
    alike: tuple[str, ...] = ()
    spare: bool = False


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
    """A pane's picture: premultiplied BGRA (H, W, 4) and the hit boxes of its controls, (name, box) in its pixels;
    for the right pane's column (`render_column`) the boxes of its foot's rows too, from the top down (*foot*: each
    row's room, whether it says anything now or not)."""

    bgra: np.ndarray
    hits: tuple[tuple[str, Box], ...]
    foot: tuple[Box, ...] = ()

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
    """The room before a row's text: a toggle's box and its gap."""
    if row.kind == "toggle":
        return scaled(TOGGLE_PX + 6, dpi)
    return 0


def row_height(face: Any, dpi: float, lines: int = 1) -> int:
    ascent, descent = face.getmetrics()
    return lines * (ascent + descent) + 2 * scaled(ROW_PAD, dpi)


def width_for(rows: list[Row], language: str, dpi: float, room: int | None = None, fill: bool = False) -> int | None:
    """The width a pane of *rows* takes (at *dpi*): its widest row (its text, a toggle's box, a list's mark, a
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
        extra = _lead(row, dpi) + (scaled(LIST_MARK_PX, dpi) if row.kind == "list" else 0) + \
            (square if row.square else 0)
        width = text + extra + 2 * scaled(PAD, dpi)
        widest = max(widest, width)
        if row.kind == "list":  # (a long name before the mark is cut: "Portuguese (Bra...")
            need = max(need, min(width, extra + 2 * scaled(PAD, dpi) + scaled(LIST_LEAST, dpi)))
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


Plate = tuple[Row, Any, list[str], int]  # a row, its font, its lines, its plate's height


def _measure(rows: list[Row], width: int, language: str, dpi: float) -> list[Plate]:
    """Each of *rows* as it is drawn *width* px wide: its font, its lines (a text row's wrapped), its plate's height
    (a row with *alike* texts: the most lines any of them takes)."""
    pane_face = font(language, scaled(FONT_PX, dpi))
    pad = scaled(PAD, dpi)
    plates: list[Plate] = []
    for row in rows:
        face = font(row.lang, scaled(FONT_PX, dpi)) if row.lang else pane_face
        if row.kind == "text":
            room, most = width - 2 * pad - _lead(row, dpi), row.lines or TEXT_LINES
            lines = wrap(face, row.text, room, most)
            count = max([len(lines)] + [len(wrap(face, text, room, most)) for text in row.alike])
        else:
            lines, count = [row.text], 1
        plates.append((row, face, lines, row_height(face, dpi, count)))
    return plates


def _stacked(plates: list[Plate], gap: int) -> int:
    return sum(h for _r, _f, _l, h in plates) + gap * max(0, len(plates) - 1)


def _picture_of(image: Image.Image, hits: list[tuple[str, Box]], foot: tuple[Box, ...] = ()) -> Picture:
    rgba = np.asarray(image, dtype=np.uint8)
    alpha = rgba[..., 3:4].astype(np.uint16)
    bgra = np.empty_like(rgba)
    bgra[..., :3] = (rgba[..., 2::-1].astype(np.uint16) * alpha // 255).astype(np.uint8)  # premultiplied
    bgra[..., 3] = rgba[..., 3]
    return Picture(np.ascontiguousarray(bgra), tuple(hits), foot)


def render(rows: list[Row], width: int, language: str, dpi: float, scheme: Colours) -> Picture:
    """The picture of a pane of *rows*, *width* px wide (`width_for`), at *dpi*, in *scheme*'s colours."""
    plates = _measure(rows, width, language, dpi)
    gap = scaled(ROW_GAP, dpi)
    image = Image.new("RGBA", (width, max(1, _stacked(plates, gap))), (0, 0, 0, 0))
    hits: list[tuple[str, Box]] = []
    _draw(image, plates, 0, width, dpi, scheme, hits)
    return _picture_of(image, hits)


def column_height(size: tuple[int, int], band: tuple[int, int], dpi: float) -> int:
    """The px a pane may be high in a frame of *size* whose steady band is the rows *band* (`place`: from the band's
    top GAP px down to GAP px above its bottom)."""
    gap = scaled(GAP, dpi)
    return max(0, (min(size[1], band[1]) - gap) - (max(0, band[0]) + gap))


def render_column(top: list[Row], changing: list[Row], foot: list[Row], width: int, height: int, language: str,
                  dpi: float, scheme: Colours, drop: tuple[int, ...] = ()) -> Picture | None:
    """The right pane as a column *height* px high (`column_height`; the band's height less its gaps): *top* (the
    bubble's block, whole) and the *changing* rows under it, from the column's top down, and the *foot* rows at its
    bottom, where they stay whatever the rest says (each keeps its height: `Row.alike`; its *spare* ones are left out
    where the foot would take more than FOOT_SHARE of the column - by the column's height alone, so they come and go
    with the viewer's size only). The changing rows that do not fit above the foot are left out in the order *drop*
    gives (indices of *changing*; those it does not name after it, the last first), the others keeping their order.
    With no foot the picture is as high as its rows. None when the foot and the block alone do not fit."""
    gap = scaled(ROW_GAP, dpi)
    feet = _measure(foot, width, language, dpi)
    if feet and _stacked(feet, gap) > height * FOOT_SHARE:
        feet = [p for p in feet if not p[0].spare]
    heads = _measure(top, width, language, dpi)
    middle = _measure(changing, width, language, dpi)
    order = [i for i in dict.fromkeys(drop) if 0 <= i < len(middle)]
    order += [i for i in range(len(middle) - 1, -1, -1) if i not in order]
    kept = list(range(len(middle)))

    def used() -> int:
        upper = heads + [middle[i] for i in kept]
        return _stacked(upper, gap) + _stacked(feet, gap) + (gap if upper and feet else 0)

    for i in order:
        if used() <= height:
            break
        kept.remove(i)
    if used() > height:
        return None
    upper = heads + [middle[i] for i in kept]
    total = height if feet else _stacked(upper, gap)
    image = Image.new("RGBA", (width, max(1, total)), (0, 0, 0, 0))
    hits: list[tuple[str, Box]] = []
    _draw(image, upper, 0, width, dpi, scheme, hits)
    boxes = _draw(image, feet, total - _stacked(feet, gap), width, dpi, scheme, hits)
    return _picture_of(image, hits, tuple(boxes))


def _draw(image: Image.Image, plates: list[Plate], y: int, width: int, dpi: float, scheme: Colours,
          hits: list[tuple[str, Box]]) -> list[Box]:
    """*plates* drawn on *image* one under the other from *y* down, ROW_GAP apart; the controls' hit boxes added to
    *hits*. A text row of no words keeps its room with nothing drawn. Each plate's box (its room), in order."""
    draw = ImageDraw.Draw(image)
    pad, gap = scaled(PAD, dpi), scaled(ROW_GAP, dpi)
    radius = scaled(RADIUS, dpi)
    boxes: list[Box] = []
    for row, face, lines, h in plates:
        boxes.append((0, y, width, y + h))
        if row.kind == "text" and not row.text:
            y += h + gap
            continue
        ascent, descent = face.getmetrics()
        line_h = ascent + descent
        plate_w = width - (h + gap if row.square else 0)  # (a square button takes the row's right end)
        pressed = row.kind == "button" and row.on  # (a button pressed: the accent's plate, the words in the plate's)
        draw.rounded_rectangle((0, y, plate_w - 1, y + h - 1), radius=radius,
                               fill=(*(scheme.accent if pressed else scheme.plate), ALPHA))
        if row.square:
            draw.rounded_rectangle((width - h, y, width - 1, y + h - 1), radius=radius, fill=(*scheme.plate, ALPHA))
            mark = glyph(row.square, h, scheme.text if row.square_enabled else scheme.dim, dpi)
            image.alpha_composite(mark, (width - h, y))
            if row.square_enabled:
                hits.append((row.square, (width - h, y, width, y + h)))
        ink = scheme.plate if pressed else scheme.warn if row.warn else scheme.text if row.enabled else scheme.dim
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
        if row.kind == "list":  # (its words from the left, cut before the mark; the arrowhead at the plate's end)
            mark = scaled(LIST_MARK_PX, dpi)
            mid = y + h // 2
            half = max(2, scaled(4, dpi))
            right = plate_w - pad
            draw.polygon([(right - half, mid - half), (right - half, mid + half), (right, mid)], fill=(*ink, 255))
            lines = [cut(face, row.text, plate_w - 2 * pad - mark)]
        for i, line in enumerate(lines):
            draw.text((x, top + i * line_h), line, font=face, fill=(*ink, 255))
        if row.kind in ("button", "toggle", "list") and row.enabled and row.name:
            hits.append((row.name, (0, y, plate_w, y + h)))
        y += h + gap
    return boxes


def middle_cut(text: str, fits: Any, mark: str = "…") -> str:
    """*text* as it is when it *fits* (a function of a text: whether it fits), else shortened in the middle - its
    start and its end kept, as much of them as fits, *mark* between them (the start one character longer than the
    end)."""
    if fits(text):
        return text

    def kept(n: int) -> str:
        head, tail = (n + 1) // 2, n // 2
        return text[:head].rstrip() + mark + (text[len(text) - tail:].lstrip() if tail else "")

    low, high = 0, len(text) - 1
    while low < high:
        middle = (low + high + 1) // 2
        if fits(kept(middle)):
            low = middle
        else:
            high = middle - 1
    return kept(low)


def fits_line(language: str, dpi: float, width: int | None = None) -> Any:
    """Whether a text fits one line of a text row of the right pane (INDICATORS_W wide unless *width*), at *dpi*."""
    face = font(language, scaled(FONT_PX, dpi))
    room = (width if width is not None else scaled(INDICATORS_W, dpi)) - 2 * scaled(PAD, dpi)
    return lambda text: _text_w(face, text) <= room


BADGE_PX = 13  # the text of a region's number plate in editing (`badge`)
BADGE_MIN_PX = 18  # the plate's least height and width: a click on it types the region's place in the reading order
BADGE_ALPHA = 235


def badge(text: str, colour: tuple[int, int, int], dpi: float) -> np.ndarray:
    """A region's number plate in editing (see-through mode): *text* (its place in the reading order) in black or
    white on a rounded plate of *colour* (RGB: the window's outline colours for what the region is), BADGE_MIN_PX
    high and wide at the least (a click on it types the place), premultiplied BGRA at *dpi*."""
    face = font("en", scaled(BADGE_PX, dpi))
    ascent, descent = face.getmetrics()
    pad = scaled(4, dpi)
    least = scaled(BADGE_MIN_PX, dpi)
    height = max(least, ascent + descent + scaled(2, dpi))
    width = max(least, max(ascent + descent, _text_w(face, text)) + 2 * pad)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=scaled(4, dpi), fill=(*colour, BADGE_ALPHA))
    ink = (0, 0, 0) if 0.299 * colour[0] + 0.587 * colour[1] + 0.114 * colour[2] >= 128 else (255, 255, 255)
    draw.text(((width - _text_w(face, text)) // 2, (height - ascent - descent) // 2), text, font=face,
              fill=(*ink, 255))
    return _picture_of(image, []).bgra


# ------------------------------------------------------------------ where they go
def place(size: tuple[int, int], page: Box, band: tuple[int, int], left: tuple[int, int] | None,
          right: tuple[int, int] | None, dpi: float, columns: tuple[int, int] | None = None,
          before: tuple[int | None, int | None] | None = None) -> tuple[Box | None, Box | None]:
    """The boxes of the left and right panes (frame pixels) in a frame of *size* whose page is *page* (the caller's:
    the widest the page has been, `reaches`; whatever is on show lies within it), whose capture
    area spans the *columns* (x from, x to; None: the whole frame) and whose steady band (where a viewer's bars never
    come) is the rows *band*, the panes being *left* and *right* (width, height; None: no such pane), each from the
    band's top GAP px down. A pane's edge toward the page (the left one's right edge, the right one's left edge) lies
    in a span: GAP px from the page at the least, MAX_FROM_PAGE px at the most, the pane inside the area GAP px in
    from its edge. In that span it is where *before* says it was (those two edges in frames of this size and these
    columns, `edges`; None: none), else at the span's end nearest to that - it moves only as far as it must -, and
    with no place before at the span's end farthest from the page (the area's edge where that is near enough). One
    whose span is empty (it would come within GAP px of the page) or that the band is too short for (and two gaps) is
    None: a pane never covers the page."""
    width, height = size
    first, last = columns if columns is not None else (0, width)
    first, last = max(0, first), min(width, last)
    gap, far = scaled(GAP, dpi), scaled(MAX_FROM_PAGE, dpi)
    top = max(0, band[0]) + gap
    bottom = min(height, band[1]) - gap
    was_left, was_right = before if before is not None else (None, None)

    def tall_enough(pane: tuple[int, int] | None) -> bool:
        return pane is not None and pane[1] <= bottom - top

    def within(was: int | None, near: int, away: int) -> int:
        """The edge in the span from *near* (GAP px from the page) to *away* (as far from it as may be): where it
        was, or the span's end nearest to that; with none, *away*."""
        low, high = min(near, away), max(near, away)
        return away if was is None else min(max(was, low), high)

    out_left = out_right = None
    if tall_enough(left):
        assert left is not None
        near, away = page[0] - gap, max(first + gap + left[0], page[0] - far)
        if away <= near:
            edge = within(was_left, near, away)
            out_left = (edge - left[0], top, edge, top + left[1])
    if tall_enough(right):
        assert right is not None
        near, away = page[2] + gap, min(last - gap - right[0], page[2] + far)
        if away >= near:
            edge = within(was_right, near, away)
            out_right = (edge, top, edge + right[0], top + right[1])
    return out_left, out_right


def edges(boxes: tuple[Box | None, Box | None],
          before: tuple[int | None, int | None] | None = None) -> tuple[int | None, int | None]:
    """The panes' edges toward the page (the left one's right edge, the right one's left edge) as `place` takes them
    back as *before*: of the *boxes* it gave, a hidden one's (None) as it was *before*, so that it comes back there."""
    was = before if before is not None else (None, None)
    return (boxes[0][2] if boxes[0] is not None else was[0], boxes[1][0] if boxes[1] is not None else was[1])


def reaches(size: tuple[int, int], page: Box, seen: tuple[int | None, int | None], fits: tuple[Any, Any],
            dpi: float, columns: tuple[int, int] | None = None) -> tuple[int | None, int | None]:
    """The page's left and right edges the two panes are placed by (`place`'s page box, its other edges *page*'s):
    per side the farthest out a page's edge has come in frames of this size, columns and DPI beside which that pane
    fitted - *seen* (the left edge, the right one; None: none yet), or *page*'s own where it comes farther out and
    the pane fits beside it there (*fits*: per side, whether the pane fits a room of so many px, `rooms`) - so the
    spread once one was shown, the single page before. None where the pane does not fit beside *page* (it hides; its
    edge seen stays as it was). A pane that no longer fits beside its edge seen (its rows grew) goes by *page*'s
    edge where it fits there."""
    gap = scaled(GAP, dpi)
    first, last = columns if columns is not None else (0, size[0])
    first, last = max(0, first), min(size[0], last)
    rooms_at = (lambda edge: edge - first - 2 * gap, lambda edge: last - edge - 2 * gap)
    out: list[int | None] = []
    for side, (now, was) in enumerate(((page[0], seen[0]), (page[2], seen[1]))):
        farther = was is None or (now < was if side == 0 else now > was)
        if not farther and fits[side](rooms_at[side](was)):
            out.append(was)
        else:
            out.append(now if fits[side](rooms_at[side](now)) else None)
    return out[0], out[1]


def seen_after(reached: tuple[int | None, int | None],
               seen: tuple[int | None, int | None]) -> tuple[int | None, int | None]:
    """The edges seen (`reaches`' *seen*) after a page placed by *reached*: a hidden pane's (None) as before."""
    return (reached[0] if reached[0] is not None else seen[0], reached[1] if reached[1] is not None else seen[1])


def overlap(a: Box | None, b: Box) -> int:
    """The pixels box *a* (None: none) and box *b* share."""
    if a is None:
        return 0
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)

