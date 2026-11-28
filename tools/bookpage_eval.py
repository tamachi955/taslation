"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: measure the judgement of whether a frame shows a page of a book
(`taslation.bookpage`) on pages of books and on made-up pages of no book.

    python tools/bookpage_eval.py              # all: the sample set, the made-up book pages and pages of no book
    python tools/bookpage_eval.py --set made   # only the made-up pages (book and no book; no dataset needed)
    python tools/bookpage_eval.py --holdout    # other window sizes and other seeds than the rules were set on

What is judged, all drawn in memory, nothing written:

* the sample set's pages (``~/.taslation/datasets/openmantra``, read in place; the series by their place in the sorted
  list, never by name) as a viewer shows them: a page fitted to the frame on a dark, white or black ground, a spread
  right to left, the page alone (a capture area that is the page), a window narrower than the page, and a soft first
  picture (the frame a quarter of its size and back);
* the repository's made-up book pages (`make_sample_page.py`'s layouts and the test pages), on a ground, alone, soft;
  a black page alone on the black ground, and beside a test page in a spread;
* a book's first five screens, made up (`book_screens.py`: the cover, a dark page beside a black one with a plate, a
  colour spread with a column of squares, a grey page beside a black one with a picture, a grey spread off the
  window's foot), each with its lettering of strokes and of a font, captured whole, with an area that trims the
  browser's bar and with one set about the spread;
* made-up pages of no book, each in several window sizes and seeds: a page of text (in Latin letters, in Japanese, dark,
  with a picture in colour or in grey, with a table and a side column, in two columns), a document page on a grey
  ground, a shop's grid of
  cards (plain, bordered, dark, one item, cards with outlined buttons), a shelf of covers (colour and grey), a grid of
  pictures (light and dark), a forum of bordered posts with quotes, a blank tab (light, dark, empty) and the stand-in's
  other tab (grey bars, Japanese lines). No real site's content or name.

Printed: per kind, how many came out "book", "not" and "unsure"; the false accepts (a page of no book judged "book"),
the false rejects (a page of a book judged "not") and the share of pages of books "unsure"; the time a judgement took.
"""

from __future__ import annotations

import argparse
import collections
import random
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import book_screens  # noqa: E402
import make_sample_page as msp  # noqa: E402
from taslation import bookpage  # noqa: E402

DATASET = Path.home() / ".taslation" / "datasets" / "openmantra" / "images"
FONT_DIRS = (Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/System/Library/Fonts"))
LATIN = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
LATIN_BOLD = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf")
SERIF = ("georgia.ttf", "times.ttf", "DejaVuSerif.ttf")
JAPANESE = ("YuGothM.ttc", "meiryo.ttc", "msgothic.ttc")
JAPANESE_BOLD = ("YuGothB.ttc", "meiryob.ttc", "msgothic.ttc")
W, H = 1900, 915  # the frame: a window 1900x1000 with its band (85 px) left out by the capture area
SIZES = ((W, H), (1280, 640), (900, 915), (640, 915))
HOLDOUT_SIZES = ((1600, 800), (1366, 600), (720, 1000), (1100, 915), (2560, 1300))
DARK_GROUND, WHITE, BLACK = (43, 43, 43), (255, 255, 255), (0, 0, 0)
WORDS = ("the of and a to in is was it for on with as by at from this that be are or an not have which one all were "
         "there their about more when what so up out if some into than them only other new time very after first way "
         "many these may then two most over down such through where much before good long little same right still "
         "between under never last while might great old year place small every found again house world without "
         "garden river morning evening window letter table summer winter market station village kitchen").split()


def font(names: tuple[str, ...], size: int) -> ImageFont.ImageFont:
    """The first of *names* found in the usual font folders, at *size*; Pillow's own font where none is."""
    for folder in FONT_DIRS:
        for name in names:
            if (folder / name).is_file():
                return ImageFont.truetype(str(folder / name), size)
    return ImageFont.load_default(size)


def sentence(rng: random.Random, n: int) -> str:
    return (" ".join(rng.choice(WORDS) for _ in range(n))).capitalize() + "."


def paragraph(draw: ImageDraw.ImageDraw, rng: random.Random, x: int, y: int, width: int, f: ImageFont.ImageFont,
              colour: tuple[int, int, int], lines: int, gap: int) -> int:
    for _ in range(lines):
        text = ""
        while True:
            more = (text + " " + rng.choice(WORDS)).strip()
            if draw.textlength(more, font=f) > width:
                break
            text = more
        draw.text((x, y), text, font=f, fill=colour)
        y += gap
    return y


def jp_lines(rng: random.Random, n: int) -> list[str]:
    pool = msp.LINES_A + msp.LINES_B + msp.LINES_NARROW
    return ["".join(rng.choice(pool) for _ in range(3)) for _ in range(n)]


# ------------------------------------------------------------------ pages of books as a viewer shows them
def fit(page: Image.Image, w: int, h: int) -> Image.Image:
    s = min(w / page.width, h / page.height)
    return page.resize((max(1, round(page.width * s)), max(1, round(page.height * s))), Image.LANCZOS)


def present(pages: list[Image.Image], mode: str, ground: tuple[int, int, int] = DARK_GROUND,
            size: tuple[int, int] = (W, H)) -> np.ndarray:
    """The frame of a viewer showing *pages* ("single", "spread": the first two right to left, "alone": the capture
    area is the page, "soft": a single page's frame a quarter of its size and back) on *ground*."""
    w, h = size
    if mode == "alone":
        return np.asarray(fit(pages[0], w, h).convert("RGB"))
    frame = Image.new("RGB", (w, h), ground)
    if mode == "spread" and len(pages) > 1:
        left, right = pages[1], pages[0]
        both = Image.new("RGB", (left.width + right.width, max(left.height, right.height)), WHITE)
        both.paste(left, (0, 0))
        both.paste(right, (left.width, 0))
        shown = fit(both, w, h)
    else:
        shown = fit(pages[0], w, h)
    frame.paste(shown.convert("RGB"), ((w - shown.width) // 2, (h - shown.height) // 2))
    if mode == "soft":
        frame = frame.resize((w // 4, h // 4), Image.BILINEAR).resize((w, h), Image.BILINEAR)
    return np.asarray(frame)


def sample_series() -> list[list[Path]]:
    if not DATASET.is_dir():
        return []
    out = []
    for series in sorted(p for p in DATASET.iterdir() if p.is_dir()):
        out.append(sorted(q for q in (series / "ja").iterdir() if q.suffix.lower() in (".jpg", ".png")))
    return out


def made_up_book_pages() -> list[Image.Image]:
    fixtures = ROOT / "tests" / "fixtures"
    pages = [Image.open(fixtures / n).convert("RGB") for n in ("sample_page.png", "sample_page2.png")]
    try:
        for seed in range(8):
            pages.append(msp.make_page(seed)[0])
        for seed in range(3):
            pages.append(msp.make_edge_page(seed)[0])
            pages.append(msp.make_narrow_page(seed)[0])
    except SystemExit:  # (no Japanese font: the test pages alone)
        pass
    return pages


# ------------------------------------------------------------------ pages of no book
def header(draw: ImageDraw.ImageDraw, w: int, colour: tuple[int, int, int], tall: int = 64,
           words: tuple[str, ...] = ("Home", "News", "Topics", "About", "Help")) -> None:
    draw.rectangle((0, 0, w, tall), fill=colour)
    ink = (30, 30, 30) if sum(colour) > 380 else (245, 245, 245)
    draw.rounded_rectangle((24, tall // 2 - 14, 130, tall // 2 + 14), radius=8, fill=ink)
    x = 220
    for word in words:
        draw.text((x, tall // 2 - 10), word, font=font(LATIN, 17), fill=ink)
        x += 110


def text_page(seed: int, size: tuple[int, int], dark: bool = False, japanese: bool = False, photo: bool = False,
              sidebar: bool = False, columns: int = 1, grey: bool = False) -> np.ndarray:
    rng = random.Random(seed)
    w, h = size
    bg, fg, soft = ((24, 24, 27), (230, 230, 230), (150, 150, 150)) if dark else (WHITE, (28, 28, 28), (110, 110, 110))
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    header(d, w, (40, 44, 52) if not dark else (36, 36, 40))
    col_w = min(760, int(w * 0.8))
    x0 = (w - col_w) // 2 - (120 if sidebar else 0)
    y = 110
    if japanese:
        d.text((x0, y), jp_lines(rng, 1)[0][:18], font=font(JAPANESE_BOLD, 34), fill=fg)
        y += 70
        body = font(JAPANESE, 20)
        for line in jp_lines(rng, 22):
            while line and d.textlength(line, font=body) > col_w:
                line = line[:-1]
            d.text((x0, y), line, font=body, fill=fg)
            y += 34
        return np.asarray(img)
    d.text((x0, y), sentence(rng, 6)[:-1], font=font(SERIF, 36), fill=fg)
    y += 60
    d.text((x0, y), "By A. Writer  -  4 min read", font=font(LATIN, 15), fill=soft)
    y += 40
    if photo:
        pic = Image.new("RGB", (col_w, 260), tuple(rng.randint(60, 200) for _ in range(3)))
        pd = ImageDraw.Draw(pic)
        for _ in range(12):
            cx, cy, r = rng.randint(0, col_w), rng.randint(0, 260), rng.randint(20, 120)
            pd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=tuple(rng.randint(0, 255) for _ in range(3)))
        pic = pic.filter(ImageFilter.GaussianBlur(6))
        img.paste(pic.convert("L").convert("RGB") if grey else pic, (x0, y))
        y += 284
    if sidebar:  # a table with ruled cells, and a column of links beside the text
        cw, rh = col_w // 4, 34
        for r in range(7):
            d.line((x0, y + r * rh, x0 + 4 * cw, y + r * rh), fill=(90, 90, 90), width=1)
        for c in range(5):
            d.line((x0 + c * cw, y, x0 + c * cw, y + 6 * rh), fill=(90, 90, 90), width=1)
        for r in range(6):
            for c in range(4):
                d.text((x0 + c * cw + 8, y + r * rh + 8), rng.choice(WORDS), font=font(LATIN, 15), fill=fg)
        y += 6 * rh + 24
        for k in range(8):
            d.text((x0 + col_w + 60, 120 + k * 44), sentence(rng, 3)[:24], font=font(LATIN, 16), fill=(30, 90, 200))
    cw = col_w if columns == 1 else (col_w - 30) // 2
    top = y
    for c in range(columns):
        y = top
        while y < h - 30:
            y = paragraph(d, rng, x0 + c * (cw + 30), y, cw, font(SERIF, 19), fg, rng.randint(3, 6), 30) + 18
    return np.asarray(img)


def document_page(seed: int, size: tuple[int, int]) -> np.ndarray:
    """A document of text shown as a page on a grey ground (a document viewer in a browser)."""
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", (w, h), (82, 86, 89))
    page_h = h - 40
    page_w = int(page_h / 1.414)
    page = Image.new("RGB", (page_w, page_h), WHITE)
    d = ImageDraw.Draw(page)
    m = int(page_w * 0.1)
    d.text((m, m), sentence(rng, 5)[:-1], font=font(LATIN_BOLD, 22), fill=BLACK)
    y = m + 50
    while y < page_h - m:
        y = paragraph(d, rng, m, y, page_w - 2 * m, font(LATIN, 12), BLACK, rng.randint(4, 8), 18) + 12
    img.paste(page, ((w - page_w) // 2, 20))
    return np.asarray(img)


def product_photo(rng: random.Random, pw: int, ph: int, dark: bool = False) -> Image.Image:
    pic = Image.new("RGB", (pw, ph), (rng.randint(20, 60),) * 3 if dark else (rng.randint(225, 250),) * 3)
    pd = ImageDraw.Draw(pic)
    kind = rng.randint(0, 2)
    c = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
    if kind == 0:
        pd.rounded_rectangle((pw * 0.25, ph * 0.15, pw * 0.75, ph * 0.85), radius=18, fill=c)
        pd.ellipse((pw * 0.4, ph * 0.3, pw * 0.6, ph * 0.45), fill=WHITE)
    elif kind == 1:
        pd.ellipse((pw * 0.15, ph * 0.15, pw * 0.85, ph * 0.85), fill=c)
        pd.ellipse((pw * 0.35, ph * 0.35, pw * 0.65, ph * 0.65), fill=(rng.randint(0, 90),) * 3)
    else:
        for k in range(5):
            x = pw * (0.1 + 0.16 * k)
            pd.rectangle((x, ph * (0.8 - 0.12 * k), x + pw * 0.12, ph * 0.85), fill=(c[0], (c[1] + 40 * k) % 255, c[2]))
    return pic


def shop_page(seed: int, size: tuple[int, int], dark_cards: bool = False, bordered: bool = False,
              detail: bool = False, outlined: bool = False) -> np.ndarray:
    """A shop's page: a search box, a row of categories, a grid of cards (a picture, a name, a price, a button) - or
    one item (*detail*); *outlined*: cards with dark borders, pictures of strokes and outlined buttons with a word."""
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", (w, h), WHITE)
    d = ImageDraw.Draw(img)
    header(d, w, rng.choice([(19, 25, 33), (232, 80, 40), (250, 250, 250)]), tall=70, words=("Deals", "New", "Cart"))
    d.rounded_rectangle((int(w * 0.3), 16, int(w * 0.68), 54), radius=6, fill=WHITE, outline=(60, 60, 60), width=2)
    d.text((int(w * 0.3) + 14, 24), "Search", font=font(LATIN, 17), fill=(90, 90, 90))
    d.rectangle((0, 70, w, 110), fill=(242, 242, 242))
    for k, word in enumerate(("All", "Kitchen", "Garden", "Toys", "Music", "Tools")):
        d.text((30 + 120 * k, 80), word, font=font(LATIN, 16), fill=(40, 40, 40))
    if detail:
        img.paste(product_photo(rng, 620, 620), (120, 150))
        d.text((800, 160), sentence(rng, 5)[:-1], font=font(LATIN_BOLD, 30), fill=(20, 20, 20))
        d.text((800, 220), "$ 24.99", font=font(LATIN_BOLD, 34), fill=(190, 30, 30))
        paragraph(d, rng, 800, 300, 800, font(LATIN, 18), (40, 40, 40), 8, 28)
        d.rounded_rectangle((800, 600, 1060, 650), radius=8, fill=(255, 200, 30))
        for k in range(4):
            img.paste(product_photo(rng, 120, 120), (120 + k * 140, 790))
        return np.asarray(img)
    cols = 5 if w > 1400 else 3
    cw = (w - 80 - (cols - 1) * 24) // cols
    ph = int(cw * 0.8)
    y = 130
    while y < h:
        for c in range(cols):
            x = 40 + c * (cw + 24)
            if dark_cards:
                d.rectangle((x, y, x + cw, y + ph + 140), fill=(30, 30, 30))
            if bordered or outlined:
                d.rectangle((x, y, x + cw, y + ph + 150), outline=(40, 40, 40), width=2)
            if outlined:
                pic = Image.new("RGB", (cw - 16, ph - 16), (245, 245, 245))
                pd = ImageDraw.Draw(pic)
                for _ in range(30):
                    pd.line((rng.randint(0, cw), rng.randint(0, ph), rng.randint(0, cw), rng.randint(0, ph)),
                            fill=(rng.randint(0, 80),) * 3, width=rng.randint(2, 5))
            else:
                pic = product_photo(rng, cw - 16, ph - 16, dark_cards)
            img.paste(pic, (x + 8, y + 8))
            fg = (230, 230, 230) if dark_cards else (30, 30, 30)
            d.text((x + 10, y + ph + 6), sentence(rng, 4)[:26], font=font(LATIN, 16), fill=fg)
            d.text((x + 10, y + ph + 34), f"$ {rng.randint(3, 99)}.{rng.randint(10, 99)}", font=font(LATIN_BOLD, 22),
                   fill=(190, 30, 30))
            if outlined:
                d.rectangle((x + 10, y + ph + 80, x + 150, y + ph + 124), fill=WHITE, outline=(40, 40, 40), width=2)
                d.text((x + 24, y + ph + 90), "Add to cart", font=font(LATIN, 17), fill=(30, 30, 30))
            else:
                d.rounded_rectangle((x + 10, y + ph + 96, x + 130, y + ph + 128), radius=6, fill=(255, 200, 30))
        y += ph + 180
    return np.asarray(img)


def covers_page(seed: int, size: tuple[int, int], grey: bool = False) -> np.ndarray:
    """A shelf of book covers (a store's library): pictures of strokes with a title, a white outlined label with a
    name in it, a title under each."""
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", (w, h), WHITE)
    d = ImageDraw.Draw(img)
    header(d, w, (35, 47, 62), tall=60, words=("Library", "Lists"))
    cols = 7 if w > 1400 else 4
    cw = (w - 100 - (cols - 1) * 28) // cols
    ch = int(cw * 1.42)
    y = 90
    while y < h:
        for c in range(cols):
            x = 50 + c * (cw + 28)
            cover = Image.new("RGB", (cw, ch), tuple(rng.randint(0, 255) for _ in range(3)))
            cd = ImageDraw.Draw(cover)
            for _ in range(40):
                colour = ((rng.randint(0, 60),) * 3 if rng.random() < 0.5
                          else tuple(rng.randint(0, 255) for _ in range(3)))
                cd.line((rng.randint(0, cw), rng.randint(0, ch), rng.randint(0, cw), rng.randint(0, ch)), fill=colour,
                        width=rng.randint(2, 6))
            cd.text((10, 10), "TITLE", font=font(LATIN_BOLD, max(14, cw // 6)), fill=WHITE)
            cd.rectangle((10, ch - 50, cw - 10, ch - 12), fill=WHITE, outline=(20, 20, 20), width=2)
            cd.text((18, ch - 44), jp_lines(rng, 1)[0][:5], font=font(JAPANESE, 18), fill=(20, 20, 20))
            if grey:
                cover = cover.convert("L").convert("RGB")
            img.paste(cover, (x, y))
            d.rectangle((x - 1, y - 1, x + cw, y + ch), outline=(120, 120, 120), width=1)
            d.text((x, y + ch + 8), sentence(rng, 3)[:18], font=font(LATIN, 15), fill=(30, 30, 30))
        y += ch + 60
    return np.asarray(img)


def gallery_page(seed: int, size: tuple[int, int], dark: bool = False) -> np.ndarray:
    """A grid of picture thumbnails with a title and a line under each (a video or picture site)."""
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", (w, h), (15, 15, 15) if dark else WHITE)
    d = ImageDraw.Draw(img)
    header(d, w, (33, 33, 33) if dark else WHITE, tall=56)
    cw = (w - 120 - 3 * 16) // 4
    ph = int(cw * 9 / 16)
    fg = (240, 240, 240) if dark else (15, 15, 15)
    y = 80
    while y < h:
        for c in range(4):
            x = 60 + c * (cw + 16)
            pic = Image.new("RGB", (cw, ph), tuple(rng.randint(0, 255) for _ in range(3)))
            pd = ImageDraw.Draw(pic)
            for _ in range(8):
                cx, cy, r = rng.randint(0, cw), rng.randint(0, ph), rng.randint(10, 90)
                pd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(rng.randint(0, 255),) * 3)
            img.paste(pic.filter(ImageFilter.GaussianBlur(3)), (x, y))
            d.text((x, y + ph + 8), sentence(rng, 5)[:34], font=font(LATIN_BOLD, 16), fill=fg)
            d.text((x, y + ph + 32), "1.2K views", font=font(LATIN, 14), fill=(120, 120, 120))
        y += ph + 70
    return np.asarray(img)


def forum_page(seed: int, size: tuple[int, int]) -> np.ndarray:
    """Posts in bordered boxes, quotes in boxes inside them, small square pictures."""
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", (w, h), (238, 240, 243))
    d = ImageDraw.Draw(img)
    header(d, w, (52, 73, 94), tall=56)
    x0, x1 = int(w * 0.12), int(w * 0.88)
    y = 80
    while y < h:
        bh = rng.randint(150, 260)
        d.rectangle((x0, y, x1, y + bh), fill=WHITE, outline=(70, 70, 70), width=1)
        d.rectangle((x0 + 14, y + 14, x0 + 74, y + 74), fill=(rng.randint(0, 255), rng.randint(0, 255), 120))
        d.text((x0 + 90, y + 14), "member" + str(rng.randint(1, 99)), font=font(LATIN_BOLD, 16), fill=(30, 30, 30))
        if rng.random() < 0.6:
            d.rectangle((x0 + 90, y + 44, x1 - 30, y + 104), fill=(248, 248, 248), outline=(60, 60, 60), width=1)
            paragraph(d, rng, x0 + 100, y + 52, x1 - x0 - 150, font(LATIN, 15), (60, 60, 60), 2, 22)
            paragraph(d, rng, x0 + 90, y + 116, x1 - x0 - 130, font(LATIN, 16), (30, 30, 30), 3, 24)
        else:
            paragraph(d, rng, x0 + 90, y + 44, x1 - x0 - 130, font(LATIN, 16), (30, 30, 30), 4, 24)
        y += bh + 16
    return np.asarray(img)


def blank_tab(seed: int, size: tuple[int, int], dark: bool = False, empty: bool = False) -> np.ndarray:
    """A new tab: a search box under a logo, a row of round shortcuts with a word under each - or nothing."""
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", (w, h), (32, 33, 36) if dark else WHITE)
    if empty:
        return np.asarray(img)
    d = ImageDraw.Draw(img)
    fg = (232, 234, 237) if dark else (60, 64, 67)
    d.rounded_rectangle((w // 2 - 110, int(h * 0.22), w // 2 + 110, int(h * 0.22) + 70), radius=20, fill=fg)
    box = (w // 2 - 290, int(h * 0.4), w // 2 + 290, int(h * 0.4) + 46)
    d.rounded_rectangle(box, radius=23, fill=(48, 49, 52) if dark else WHITE,
                        outline=(95, 99, 104) if dark else (218, 220, 224), width=1)
    for k in range(8):
        cx, cy = w // 2 - 280 + k * 80, int(h * 0.58)
        d.ellipse((cx - 24, cy - 24, cx + 24, cy + 24), fill=(53, 54, 58) if dark else (241, 243, 244))
        d.text((cx - 6, cy - 12), "ABCDEFGH"[k], font=font(LATIN, 18), fill=fg)
        d.text((cx - 22, cy + 32), rng.choice(WORDS)[:7], font=font(LATIN, 12), fill=fg)
    return np.asarray(img)


def standin_other(kind: int, size: tuple[int, int]) -> np.ndarray:
    """The stand-in's other tab as `standin_viewer`'s page draws it (under no band): kind 0 grey bars, kind 1 lines of
    made-up Japanese and two columns of it."""
    rng = random.Random(kind)
    w, h = size
    img = Image.new("RGB", (w, h), (0xf6, 0xf6, 0xf4))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, 56), fill=(0xdf, 0xe3, 0xe8))
    left, wide = max(40, int(w * 0.12)), int(w * 0.6)
    if kind == 1:
        for k, line in enumerate(jp_lines(rng, 5)):
            face = font(JAPANESE_BOLD if k == 0 else JAPANESE, 40 if k == 0 else 30)
            d.text((left, 96 + k * 64), line[:14], font=face, fill=(0x1c, 0x1c, 0x1c))
        for k, column in enumerate(jp_lines(rng, 2)):
            x = w - left - k * 52
            for i, ch in enumerate(column[:10]):
                d.text((x - 17, 110 + i * 37), ch, font=font(JAPANESE, 34), fill=(0x1c, 0x1c, 0x1c))
    else:
        for k in range(9):
            d.rectangle((left, 100 + k * 44, left + int(wide * (0.55 if k % 3 == 2 else 0.9)), 114 + k * 44),
                        fill=(0xc4, 0xc9, 0xd0))
    return np.asarray(img)


def no_book_frames(sizes: tuple[tuple[int, int], ...], seed0: int = 0):
    """(kind, frame) of every made-up page of no book, in each of *sizes*, three seeds each."""
    for k, size in enumerate(sizes):
        for seed in range(3):
            s = seed0 + seed + 10 * k
            yield from (("text", text_page(s, size)), ("text-japanese", text_page(s, size, japanese=True)),
                        ("text-dark", text_page(s, size, dark=True)), ("text-picture", text_page(s, size, photo=True)),
                        ("text-picture-grey", text_page(s, size, photo=True, grey=True)),
                        ("text-table", text_page(s, size, sidebar=True)), ("text-2col", text_page(s, size, columns=2)),
                        ("document", document_page(s, size)), ("shop", shop_page(s, size)),
                        ("shop-bordered", shop_page(s, size, bordered=True)),
                        ("shop-dark", shop_page(s, size, dark_cards=True)),
                        ("shop-item", shop_page(s, size, detail=True)),
                        ("shop-outlined", shop_page(s, size, outlined=True)), ("covers", covers_page(s, size)),
                        ("covers-grey", covers_page(s, size, grey=True)), ("gallery", gallery_page(s, size)),
                        ("gallery-dark", gallery_page(s, size, dark=True)), ("forum", forum_page(s, size)),
                        ("blank", blank_tab(s, size)), ("blank-dark", blank_tab(s, size, dark=True)))
        yield from (("blank-empty", blank_tab(0, size, empty=True)), ("standin-plain", standin_other(0, size)),
                    ("standin-japanese", standin_other(1, size)))


def book_frames(holdout: bool):
    """(kind, frame) of every page of a book as a viewer shows it."""
    shows = ((("single", DARK_GROUND, (1366, 600)), ("spread", BLACK, (2560, 1300)), ("single", WHITE, (720, 1000)),
              ("spread", WHITE, (1600, 800))) if holdout else
             (("single", DARK_GROUND, (W, H)), ("spread", DARK_GROUND, (W, H)), ("single", WHITE, (W, H)),
              ("single", BLACK, (W, H)), ("alone", BLACK, (W, H)), ("single", DARK_GROUND, (600, 915)),
              ("soft", DARK_GROUND, (W, H))))
    for n, files in enumerate(sample_series()):
        for i in range(len(files)):
            pages = [Image.open(f).convert("RGB") for f in files[i:i + 2]]
            for mode, ground, size in shows:
                if mode == "spread" and len(pages) < 2:
                    continue
                yield f"sample {mode} {size[0]}x{size[1]}", present(pages, mode, ground, size)


def made_book_frames():
    pages = made_up_book_pages()
    for page in pages:
        for mode in ("single", "alone", "soft"):
            yield f"made-up {mode}", present([page], mode)
    black = Image.new("RGB", pages[0].size, BLACK)  # (a black page of a book: a chapter's end, a night)
    yield "made-up black page alone", present([black], "single", BLACK)
    for page in pages[:2]:
        yield "made-up page beside a black one", present([black, page], "spread", BLACK)
        yield "made-up page beside a black one", present([page, black], "spread", BLACK)


def screen_frames():
    """(kind, frame) of the made-up screens (`book_screens.SCREENS`) as captured: the whole client area, an area
    that trims the browser's bar, one set about the spread; their lettering of strokes, and of a font where one is."""
    for lettering in book_screens.LETTERINGS:
        for name, make, _columns in book_screens.SCREENS:
            try:
                screen = make(lettering)
            except SystemExit:  # (no Japanese font: the strokes alone)
                break
            for area, (left, top, right, bottom) in (("whole", (0, 0, 0, 0)), ("bar trimmed", book_screens.BARS_ONLY),
                                                      ("area set", book_screens.HAND)):
                yield f"screen {name}, {area}", screen[top:screen.shape[0] - bottom, left:screen.shape[1] - right]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", choices=("all", "made", "samples"), default="all",
                    help="all (default); made: the made-up pages only, book and no book; samples: the sample set only")
    ap.add_argument("--holdout", action="store_true",
                    help="other window sizes and seeds than the rules were set on (the made-up book pages left out)")
    args = ap.parse_args()
    counts: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    times: list[float] = []

    def judge(group: str, kind: str, frame: np.ndarray) -> None:
        began = time.perf_counter()
        said = bookpage.judge(frame)
        times.append(time.perf_counter() - began)
        counts[(group, kind)][said] += 1

    if args.set in ("all", "samples"):
        if not sample_series():
            print(f"no sample set at {DATASET}: its pages left out")
        for kind, frame in book_frames(args.holdout):
            judge("book", kind, frame)
    if args.set in ("all", "made"):
        if not args.holdout:
            for kind, frame in made_book_frames():
                judge("book", kind, frame)
            for kind, frame in screen_frames():
                judge("book", kind, frame)
        sizes = HOLDOUT_SIZES if args.holdout else SIZES
        for kind, frame in no_book_frames(sizes, 100 if args.holdout else 0):
            judge("no book", kind, frame)
    totals: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for (group, kind), c in sorted(counts.items()):
        print(f"{group:8} {kind:30} book {c['book']:4}  not {c['not']:4}  unsure {c['unsure']:4}")
        totals[group].update(c)
    book, other = totals.get("book", collections.Counter()), totals.get("no book", collections.Counter())
    pages = sum(book.values())
    print(f"pages of books {pages}: false rejects (judged 'not') {book['not']}, unsure {book['unsure']}"
          + (f" ({100 * book['unsure'] / pages:.1f} %)" if pages else ""))
    print(f"pages of no book {sum(other.values())}: false accepts (judged 'book') {other['book']}, "
          f"'not' {other['not']}, unsure {other['unsure']}")
    if times:
        print(f"a judgement: median {1000 * statistics.median(times):.0f} ms, at most {1000 * max(times):.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
