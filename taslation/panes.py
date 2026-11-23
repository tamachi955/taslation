"""The side panes of see-through mode, pure (no Tk, no window): what goes into them, where they go beside the page,
and their pictures (`ui.seethrough` fills them, `capture.seethrough` shows them).

* Two panes on the viewer's ground beside the page: the LEFT one holds the controls (`Row`s a click acts on), the
  RIGHT one the indicators (rows of text only). Each is placed from the page box and the steady band of the viewer's
  frame (`place`): next to the page, GAP px from it and at least GAP px from the frame's edge, from the band's top
  down (the band: where a viewer's bars never come, so a pane never lies over them). A pane that does not fit its
  ground - narrower than the pane and two gaps, or the band shorter than it - is not placed (it hides) rather than
  cover the page.
* A pane's width (`width_for`): as wide as its widest row asks (the text at FONT_PX, a toggle's box, the arrows of a
  choice, PAD each side), between MIN_W and MAX_W, and no wider than the ground leaves (*room*); the words of a text
  row are wrapped to it, a control's never are, so the least a pane needs is its widest control, or MIN_W for words
  alone. In English at 100 % the controls take some 130-150 px (some 165 px in German), the words 120 px at the least:
  the ground beside a spread in a 1920 x 1080 window (about 294 px) and on its full screen (about 198 px) both give
  that and two gaps; a narrower ground (a narrow window, a wide page) hides the pane.
* A pane's picture (`render`): each row a rounded plate, the rows apart by ROW_GAP of nothing (alpha 0: where the
  viewer's ground shows, a click goes to the viewer); the colours follow the ground's (`colours`: light on a dark
  ground, dark on a light one). The hit boxes of the controls come with it, in the picture's pixels.

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

GAP = 8  # px between a pane and the page, and at least between a pane and the frame's edge
PAD = 8  # px of plate before and after a row's content
ROW_PAD = 5  # px of plate above and below a row's text
ROW_GAP = 4  # px of nothing between two rows (the viewer's ground: its clicks are the viewer's)
FONT_PX = 13  # the rows' text
TOGGLE_PX = 11  # a toggle's box
ARROW_PX = 14  # the room of each arrow of a choice
MIN_W, MAX_W = 120, 240  # a pane's width, whatever its rows ask
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
    translated)."""

    name: str
    text: str
    kind: str = "button"
    on: bool = False
    enabled: bool = True
    warn: bool = False


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
    """The width a pane of *rows* takes (at *dpi*): its widest row (its text, a toggle's box, a choice's arrows, PAD
    each side) - with *fill*, MAX_W whatever its rows say (the indicators: a width that does not change with what they
    say) -, between MIN_W and MAX_W, and no wider than *room* (the px its ground leaves it; None: any). A text row's
    words are wrapped to the width, a control's are not: so the least it needs is its widest control row, or MIN_W -
    None when *room* is less than that (the pane hides)."""
    face = font(language, scaled(FONT_PX, dpi))
    widest = 0
    need = scaled(MIN_W, dpi)
    for row in rows:
        text = _text_w(face, row.text)
        extra = _lead(row, dpi) + (scaled(ARROW_PX, dpi) if row.kind == "choice" else 0)
        width = text + extra + 2 * scaled(PAD, dpi)
        widest = max(widest, width)
        if row.kind == "choice":  # (a long name between the arrows is cut: "Portuguese (Bra...")
            need = max(need, min(width, extra + 2 * scaled(PAD, dpi) + scaled(CHOICE_LEAST, dpi)))
        elif row.kind != "text":
            need = max(need, width)
    width = max(need, scaled(MAX_W, dpi) if fill else min(scaled(MAX_W, dpi), widest))
    if room is not None:
        if room < need:
            return None
        width = min(width, room)
    return width


def rooms(size: tuple[int, int], page: Box, dpi: float) -> tuple[int, int]:
    """The px the ground left and right of *page* leaves a pane in a frame of *size* (GAP each side of it)."""
    gap = scaled(GAP, dpi)
    return page[0] - 2 * gap, size[0] - page[2] - 2 * gap


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
def render(rows: list[Row], width: int, language: str, dpi: float, scheme: Colours) -> Picture:
    """The picture of a pane of *rows*, *width* px wide (`width_for`), at *dpi*, in *scheme*'s colours."""
    face = font(language, scaled(FONT_PX, dpi))
    pad, gap = scaled(PAD, dpi), scaled(ROW_GAP, dpi)
    plates: list[tuple[Row, list[str], int]] = []
    for row in rows:
        lines = wrap(face, row.text, width - 2 * pad - _lead(row, dpi)) if row.kind == "text" else [row.text]
        plates.append((row, lines, row_height(face, dpi, len(lines))))
    height = sum(h for _r, _l, h in plates) + gap * max(0, len(plates) - 1)
    image = Image.new("RGBA", (width, max(1, height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    ascent, descent = face.getmetrics()
    line_h = ascent + descent
    hits: list[tuple[str, Box]] = []
    y = 0
    radius = scaled(RADIUS, dpi)
    for row, lines, h in plates:
        draw.rounded_rectangle((0, y, width - 1, y + h - 1), radius=radius, fill=(*scheme.plate, ALPHA))
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
            hits.append((row.name, (0, y, width, y + h)))
        y += h + gap
    rgba = np.asarray(image, dtype=np.uint8)
    alpha = rgba[..., 3:4].astype(np.uint16)
    bgra = np.empty_like(rgba)
    bgra[..., :3] = (rgba[..., 2::-1].astype(np.uint16) * alpha // 255).astype(np.uint8)  # premultiplied
    bgra[..., 3] = rgba[..., 3]
    return Picture(np.ascontiguousarray(bgra), tuple(hits))


# ------------------------------------------------------------------ where they go
def place(size: tuple[int, int], page: Box, band: tuple[int, int], left: tuple[int, int] | None,
          right: tuple[int, int] | None, dpi: float) -> tuple[Box | None, Box | None]:
    """The boxes of the left and right panes (frame pixels) in a frame of *size* whose page is *page* and whose steady
    band (where a viewer's bars never come) is the rows *band*, the panes being *left* and *right* (width, height; None:
    no such pane). Each goes beside the page, GAP px from it, at least GAP px from the frame's edge, from the band's
    top GAP px down; one that does not fit (its ground narrower than it and two gaps, the band shorter than it and two
    gaps) is None: a pane never covers the page."""
    width, height = size
    gap = scaled(GAP, dpi)
    top = max(0, band[0]) + gap
    bottom = min(height, band[1]) - gap

    def fits(pane: tuple[int, int] | None, ground: int) -> bool:
        return pane is not None and pane[0] + 2 * gap <= ground and pane[1] <= bottom - top

    out_left = out_right = None
    if fits(left, page[0]):
        assert left is not None
        out_left = (page[0] - gap - left[0], top, page[0] - gap, top + left[1])
    if fits(right, width - page[2]):
        assert right is not None
        out_right = (page[2] + gap, top, page[2] + gap + right[0], top + right[1])
    return out_left, out_right


def overlap(a: Box | None, b: Box) -> int:
    """The pixels box *a* (None: none) and box *b* share."""
    if a is None:
        return 0
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)
