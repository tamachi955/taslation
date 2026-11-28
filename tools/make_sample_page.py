"""Generate a synthetic manga-style test page (no copyrighted material involved).

Produces a page with panels, scribbled "artwork", speech bubbles containing
vertical Japanese text, and a caption box, plus a JSON file with the ground
truth (bubble boxes and texts) used by the tests.

    python tools/make_sample_page.py --out tests/fixtures/sample_page.png
    python tools/make_sample_page.py --seed 7 --out tests/fixtures/sample_page2.png
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

JP_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]

LINES_A = [
    "こんにちは", "今日はいい天気だね", "ありがとう", "どこへ行くの", "まだ終わってない", "大丈夫だよ",
]
LINES_B = [
    "本当に行くのか", "急いで", "ここで待ってて", "やっぱりそうか", "明日また来るよ", "気をつけて",
]


def find_jp_font(size: int) -> ImageFont.FreeTypeFont:
    for cand in JP_FONT_CANDIDATES:
        if Path(cand).is_file():
            return ImageFont.truetype(cand, size)
    sys.exit("no Japanese font found; add one to JP_FONT_CANDIDATES")


def draw_vertical_text(draw: ImageDraw.ImageDraw, text: str, cx: float, top: float, font: ImageFont.FreeTypeFont,
                       size: int, max_rows: int, col_gap: float = 1.15) -> tuple[int, int, int, int]:
    """Draw text in vertical columns, right to left, *col_gap* sizes apart. Returns the text bounding box."""
    columns: list[str] = [text[i : i + max_rows] for i in range(0, len(text), max_rows)]
    col_w = size * col_gap
    total_w = col_w * len(columns)
    x = cx + total_w / 2 - col_w / 2
    boxes = []
    for col in columns:
        y = top
        for ch in col:
            bbox = draw.textbbox((0, 0), ch, font=font)
            w = bbox[2] - bbox[0]
            draw.text((x - w / 2 - bbox[0], y - bbox[1]), ch, font=font, fill=(0, 0, 0))
            boxes.append((x - w / 2, y, x + w / 2, y + size))
            y += size * 1.05
        x -= col_w
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    return (int(x0), int(y0), int(math.ceil(x1)), int(math.ceil(y1)))


def scribble(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], rng: random.Random) -> None:
    x0, y0, x1, y1 = box
    for _ in range(rng.randint(25, 45)):
        ax, ay = rng.uniform(x0, x1), rng.uniform(y0, y1)
        bx, by = rng.uniform(x0, x1), rng.uniform(y0, y1)
        draw.line((ax, ay, bx, by), fill=(rng.randint(0, 90),) * 3, width=rng.randint(2, 5))
    for _ in range(rng.randint(3, 6)):
        cx, cy = rng.uniform(x0, x1), rng.uniform(y0, y1)
        r = rng.uniform(25, 90)
        shade = rng.randint(60, 200)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(shade,) * 3, outline=(0, 0, 0), width=3)
    # a "screentone" patch: fine dots on white (a white region with many small dark pieces)
    px0, py0 = rng.uniform(x0, x1 - 160), rng.uniform(y0, y1 - 120)
    draw.rectangle((px0, py0, px0 + 150, py0 + 110), fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    for i in range(0, 150, 9):
        for j in range(0, 110, 9):
            draw.ellipse((px0 + i + 2, py0 + j + 2, px0 + i + 4.5, py0 + j + 4.5), fill=(40, 40, 40))


def make_page(seed: int, width: int = 1240, height: int = 1754) -> tuple[Image.Image, list[dict]]:
    rng = random.Random(seed)
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    margin, gutter = 60, 24
    mid_y = height // 2
    split_x = width // 2 + rng.randint(-120, 120)
    panels = [
        (split_x + gutter // 2, margin, width - margin, mid_y - gutter // 2),  # top right
        (margin, margin, split_x - gutter // 2, mid_y - gutter // 2),  # top left
        (margin, mid_y + gutter // 2, width - margin, height - margin),  # bottom (wide)
    ]
    for p in panels:
        scribble(draw, (p[0] + 10, p[1] + 10, p[2] - 10, p[3] - 10), rng)
        draw.rectangle(p, outline=(0, 0, 0), width=6)

    lines = list(LINES_A if seed % 2 == 0 else LINES_B)
    rng.shuffle(lines)
    size = 34
    font = find_jp_font(size)
    truth: list[dict] = []

    def bubble(cx: float, cy: float, rx: float, ry: float, text: str, tail: tuple[float, float] | None = None,
               shape: str = "ellipse") -> None:
        box = (cx - rx, cy - ry, cx + rx, cy + ry)
        if tail:
            tx, ty = tail
            draw.polygon([(cx - rx * 0.2, cy + ry * 0.6), (cx + rx * 0.2, cy + ry * 0.6), (tx, ty)],
                         fill=(255, 255, 255), outline=(0, 0, 0), width=4)
        if shape == "ellipse":
            draw.ellipse(box, fill=(255, 255, 255), outline=(0, 0, 0), width=5)
        else:
            draw.rectangle(box, fill=(255, 255, 255), outline=(0, 0, 0), width=5)
        if tail:
            inner = (cx - rx + 4, cy - ry + 4, cx + rx - 4, cy + ry - 4)
            if shape == "ellipse":
                draw.ellipse(inner, fill=(255, 255, 255))
            else:
                draw.rectangle(inner, fill=(255, 255, 255))
        max_rows = max(3, int((ry * 2 * 0.72) / (size * 1.05)))
        tb = draw_vertical_text(draw, text, cx, cy - min(len(text), max_rows) * size * 1.05 / 2, font, size, max_rows)
        truth.append({"bbox": [int(box[0]), int(box[1]), int(math.ceil(box[2])), int(math.ceil(box[3]))],
                      "text_box": list(tb), "text": text, "shape": shape})

    tr = panels[0]
    tl = panels[1]
    bt = panels[2]
    bubble((tr[0] + tr[2]) / 2 + 60, tr[1] + 190, 120, 165, lines[0], tail=((tr[0] + tr[2]) / 2 + 160, tr[1] + 420))
    bubble(tr[0] + 150, tr[3] - 230, 110, 150, lines[1])
    bubble((tl[0] + tl[2]) / 2, tl[1] + 200, 115, 170, lines[2], tail=((tl[0] + tl[2]) / 2 - 90, tl[1] + 430))
    bubble(bt[2] - 200, bt[1] + 230, 130, 190, lines[3])
    bubble(bt[0] + 220, bt[1] + 260, 125, 175, lines[4], tail=(bt[0] + 300, bt[1] + 500))
    bubble((bt[0] + bt[2]) / 2 + 40, bt[3] - 170, 170, 120, lines[5], shape="rect")  # caption box
    return img, truth


EDGE_GAP = 5  # (`make_edge_page`) px between a page's edge and the text of the bubble cut by it


def make_edge_page(seed: int, width: int = 1240, height: int = 1754) -> tuple[Image.Image, list[dict]]:
    """A page whose bubbles are cut by its four edges, their text EDGE_GAP px from the edge (as a bubble running off
    the page in a book is), and one whole bubble in the middle; panels of scribbles between them. For the lettering of
    a bubble at the page's edge (`--layout edges`)."""
    rng = random.Random(seed)
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    inner = (220, 260, width - 220, height - 260)
    scribble(draw, (inner[0] + 10, inner[1] + 10, inner[2] - 10, inner[3] - 10), rng)
    draw.rectangle(inner, outline=(0, 0, 0), width=6)
    lines = list(LINES_A if seed % 2 == 0 else LINES_B)
    rng.shuffle(lines)
    size = 34
    font = find_jp_font(size)
    truth: list[dict] = []

    def ink(text: str, rows: int) -> Image.Image:  # the text's columns alone, cut to their ink
        cols = math.ceil(len(text) / rows)
        sheet = Image.new("RGB", (int(cols * size * 1.15 + 2 * size), int(rows * size * 1.05 + 2 * size)),
                          (255, 255, 255))
        draw_vertical_text(ImageDraw.Draw(sheet), text, sheet.width / 2, size, font, size, rows)
        grey = sheet.convert("L")
        return grey.crop(Image.eval(grey, lambda v: 255 - v).getbbox())

    def cut_bubble(cx: float, cy: float, rx: float, ry: float, text: str, rows: int, edge: str) -> None:
        draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(255, 255, 255), outline=(0, 0, 0), width=5)
        piece = ink(text, rows)
        x = {"left": EDGE_GAP, "right": width - EDGE_GAP - piece.width}.get(edge, int(cx - piece.width / 2))
        y = {"top": EDGE_GAP, "bottom": height - EDGE_GAP - piece.height}.get(edge, int(cy - piece.height / 2))
        x, y = int(x), int(y)
        under = img.crop((x, y, x + piece.width, y + piece.height)).convert("L")
        img.paste(Image.merge("RGB", [Image.composite(piece, under, Image.eval(piece, lambda v: 255 - v))] * 3),
                  (x, y))
        box = (max(0, cx - rx), max(0, cy - ry), min(width, cx + rx), min(height, cy + ry))
        truth.append({"bbox": [int(box[0]), int(box[1]), int(math.ceil(box[2])), int(math.ceil(box[3]))],
                      "text_box": [x, y, x + piece.width, y + piece.height], "text": text, "shape": "ellipse",
                      "edge": edge})

    cut_bubble(width * 0.68, -40, 150, 260, lines[0], 5, "top")
    cut_bubble(width * 0.30, height + 40, 150, 260, lines[1], 5, "bottom")
    cut_bubble(-60, height * 0.38, 230, 170, lines[2], 4, "left")
    cut_bubble(width + 60, height * 0.62, 230, 170, lines[3], 4, "right")
    cut_bubble(width * 0.5, height * 0.5, 120, 170, lines[4], 5, "")
    return img, truth


LINES_NARROW = ["まさかここまで来るなんて", "それはないだろう普通", "そりゃな", "ちょっと待ってくれよ", "確かにな"]
LINES_NARROW_BIG = "そういうことなら仕方ないけど本当にいいの"


def make_narrow_page(seed: int, width: int = 1240, height: int = 1754) -> tuple[Image.Image, list[dict]]:
    """A page of tall narrow bubbles, each with one column of bold characters (as a long line set in one column is),
    and two bubbles joined side by side: a large oval and a small one tucked behind its right side, the large one's
    outline between them, with a short column of large characters. For the erase and the lettering of narrow bubbles
    and of a bubble that shares an outline, at the page's size and scaled down (`--layout narrow`)."""
    rng = random.Random(seed)
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    margin, gutter = 60, 24
    mid_y = height // 2 + 40
    panels = [(margin, margin, width - margin, mid_y - gutter // 2),
              (margin, mid_y + gutter // 2, width - margin, height - margin)]
    for p in panels:
        scribble(draw, (p[0] + 10, p[1] + 10, p[2] - 10, p[3] - 10), rng)
        draw.rectangle(p, outline=(0, 0, 0), width=6)
    truth: list[dict] = []

    def column(text: str, cx: float, cy: float, size: int) -> tuple[int, int, int, int]:
        return draw_vertical_text(draw, text, cx, cy - len(text) * size * 1.05 / 2, find_jp_font(size), size,
                                  len(text))

    def narrow(cx: float, cy: float, rx: float, ry: float, text: str, size: int) -> None:
        draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(255, 255, 255), outline=(0, 0, 0), width=4)
        tb = column(text, cx, cy, size)
        truth.append({"bbox": [int(cx - rx), int(cy - ry), int(math.ceil(cx + rx)), int(math.ceil(cy + ry))],
                      "text_box": list(tb), "text": text, "shape": "ellipse", "kind": "narrow"})

    top = panels[0]
    narrow(top[2] - 150, top[1] + 300, 52, 205, LINES_NARROW[0], 27)  # 11 characters in one column
    narrow(top[2] - 330, top[1] + 280, 48, 180, LINES_NARROW[1], 26)
    narrow(top[0] + 170, top[1] + 270, 44, 160, LINES_NARROW[3], 24)
    # the joined pair: the small bubble first, the large one over its left side (its outline between them)
    bottom = panels[1]
    bx, by, brx, bry = bottom[0] + 520, bottom[1] + 330, 175, 215
    sx, sy, srx, sry = bx + brx + 25, by - 60, 60, 110
    draw.ellipse((sx - srx, sy - sry, sx + srx, sy + sry), fill=(255, 255, 255), outline=(0, 0, 0), width=5)
    draw.ellipse((bx - brx, by - bry, bx + brx, by + bry), fill=(255, 255, 255), outline=(0, 0, 0), width=5)
    big = draw_vertical_text(draw, LINES_NARROW_BIG, bx, by - 5 * 34 * 1.05 / 2 - 20, find_jp_font(34), 34, 5)
    truth.append({"bbox": [bx - brx, by - bry, bx + brx, by + bry], "text_box": list(big), "text": LINES_NARROW_BIG,
                  "shape": "ellipse", "kind": "joined-large"})
    small = column(LINES_NARROW[2], (bx + brx + sx + srx) / 2, sy, 36)  # (between the shared outline and its own)
    truth.append({"bbox": [bx + brx, sy - sry, sx + srx, sy + sry], "text_box": list(small), "text": LINES_NARROW[2],
                  "shape": "ellipse", "kind": "joined-small", "ellipse": [sx, sy, srx, sry],
                  "big": [bx, by, brx, bry]})
    # a second pair, the small one's column of large characters nearly as wide as its free interior and a tail at its
    # lower right
    bx, by, brx, bry = bottom[0] + 840, bottom[1] + 570, 120, 150
    sx, sy, srx, sry = bx + brx + 20, by - 40, 48, 140
    draw.polygon([(sx + 10, sy + sry * 0.8), (sx + 34, sy + sry * 0.62), (sx + 75, sy + sry + 55)],
                 fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    draw.ellipse((sx - srx, sy - sry, sx + srx, sy + sry), fill=(255, 255, 255), outline=(0, 0, 0), width=5)
    draw.ellipse((sx - srx + 4, sy - sry + 4, sx + srx - 4, sy + sry - 4), fill=(255, 255, 255))
    draw.ellipse((bx - brx, by - bry, bx + brx, by + bry), fill=(255, 255, 255), outline=(0, 0, 0), width=5)
    big = draw_vertical_text(draw, LINES_NARROW_BIG[:10], bx, by - 5 * 30 * 1.05 / 2, find_jp_font(30), 30, 5)
    truth.append({"bbox": [bx - brx, by - bry, bx + brx, by + bry], "text_box": list(big),
                  "text": LINES_NARROW_BIG[:10], "shape": "ellipse", "kind": "joined-large2"})
    small = column(LINES_NARROW[4], (bx + brx + sx + srx) / 2 - 2, sy, 46)
    truth.append({"bbox": [bx + brx, sy - sry, sx + srx, sy + sry], "text_box": list(small), "text": LINES_NARROW[4],
                  "shape": "ellipse", "kind": "joined-small2", "ellipse": [sx, sy, srx, sry],
                  "big": [bx, by, brx, bry]})
    return img, truth


LINES_PAIRS = ["まさかそんなことって︙︙", "えっ︙", "ちょっと待ってよ", "やっぱりそうかここで待っててね", "気をつけて︙",
               "今日はいい天気だね明日また来るよ", "急いで", "信じられない︙", "うそでしょ", "信じられないそんなことって︙",
               "うそでしょ本当にそうなの"]


def make_pairs_page(seed: int, width: int = 1240, height: int = 1754) -> tuple[Image.Image, list[dict]]:
    """A page of bubbles joined in pairs, each drawn over the one before it (its outline the one they share), as a
    page shown small has them: a tall narrow bubble of two columns (the left one by its outline, ending in an
    ellipsis) with a narrower one over its upper right corner; a bubble of three columns with a tall narrow one over
    its left side; one with a smaller one over its foot; two tall narrow ones side by side, the right one over the
    left one's right side; a tall narrow bubble by the page's right edge; and two tall narrow ones side by side
    lettered from outline to outline, three columns each, the columns by the outline they share touching it. For the
    erase, the rooms and the patches of joined bubbles (`--layout pairs`; the lettering audit's layouts 18 and 19 are
    the same with their layers apart)."""
    rng = random.Random(seed)
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    margin, gutter, mid_y, split_x = 60, 24, height // 2, width // 2
    tr = (split_x + gutter // 2, margin, width - margin, mid_y - gutter // 2)
    tl = (margin, margin, split_x - gutter // 2, mid_y - gutter // 2)
    bt = (margin, mid_y + gutter // 2, width - margin, height - margin)
    for p in (tr, tl, bt):
        scribble(draw, (p[0] + 10, p[1] + 10, p[2] - 10, p[3] - 10), rng)
        draw.rectangle(p, outline=(0, 0, 0), width=6)
    truth: list[dict] = []
    bubbles: list[tuple[float, float, float, float]] = []

    def bubble(cx: float, cy: float, rx: float, ry: float) -> None:  # (drawn over the ones before it)
        draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(255, 255, 255), outline=(0, 0, 0), width=5)
        bubbles.append((cx, cy, rx, ry))

    def text(k: int, cx: float, cy: float, size: int, rows: int, kind: str, col_gap: float = 1.15) -> None:
        line = LINES_PAIRS[k]
        n = min(len(line), rows)
        tb = draw_vertical_text(draw, line, cx, cy - n * size * 1.05 / 2, find_jp_font(size), size, rows, col_gap)
        bx, by, brx, bry = bubbles[k]
        truth.append({"bbox": [int(bx - brx), int(by - bry), int(math.ceil(bx + brx)), int(math.ceil(by + bry))],
                      "text_box": list(tb), "text": line, "shape": "ellipse", "kind": kind,
                      "ellipse": [bx, by, brx, bry]})

    bubble(tr[0] + 150, tr[1] + 400, 46, 160)
    bubble(tr[0] + 200, tr[1] + 250, 30, 118)
    bubble(tr[2] - 58, tr[1] + 360, 31, 140)
    bubble(tl[0] + 380, tl[1] + 330, 88, 135)
    bubble(tl[0] + 262, tl[1] + 370, 40, 165)
    bubble(bt[0] + 260, bt[1] + 200, 95, 120)
    bubble(bt[0] + 300, bt[1] + 372, 70, 95)
    bubble(bt[0] + 640, bt[1] + 330, 40, 170)
    bubble(bt[0] + 708, bt[1] + 310, 36, 160)
    bubble(bt[0] + 900, bt[1] + 330, 42, 170)
    bubble(bt[0] + 975, bt[1] + 310, 42, 160)
    text(0, tr[0] + 150, tr[1] + 440, 25, 6, "pair-corner-big")
    text(1, tr[0] + 206, tr[1] + 236, 24, 6, "pair-corner-small")
    text(2, tr[2] - 58, tr[1] + 360, 24, 12, "narrow-edge")
    text(3, tl[0] + 392, tl[1] + 330, 25, 5, "pair-side-big")
    text(4, tl[0] + 258, tl[1] + 370, 25, 12, "pair-side-narrow")
    text(5, bt[0] + 260, bt[1] + 190, 25, 6, "pair-below-top")
    text(6, bt[0] + 305, bt[1] + 385, 25, 6, "pair-below-foot")
    text(7, bt[0] + 634, bt[1] + 340, 26, 12, "pair-narrow-left")
    text(8, bt[0] + 712, bt[1] + 310, 26, 12, "pair-narrow-right")
    text(9, bt[0] + 900, bt[1] + 330, 22, 5, "pair-tight-left", col_gap=1.12)
    text(10, bt[0] + 975, bt[1] + 310, 22, 4, "pair-tight-right", col_gap=1.12)
    return img, truth


LAYOUTS = {"panels": make_page, "edges": make_edge_page, "narrow": make_narrow_page, "pairs": make_pairs_page}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--layout", choices=sorted(LAYOUTS), default="panels",
                    help="panels: the test pages' (the default); edges: bubbles cut by the page's four edges; narrow: "
                         "tall narrow bubbles with one column each, and bubbles joined side by side; pairs: bubbles "
                         "joined in pairs, each drawn over the one before it (tall narrow ones side by side, one over "
                         "another's upper corner, over a side, over a foot)")
    args = ap.parse_args()
    img, truth = LAYOUTS[args.layout](args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    with open(args.out.with_suffix(".json"), "w", encoding="utf-8") as f:
        json.dump({"seed": args.seed, "size": list(img.size), "bubbles": truth}, f, ensure_ascii=False, indent=1)
    print(f"wrote {args.out} and {args.out.with_suffix('.json')} ({len(truth)} bubbles)")


if __name__ == "__main__":
    main()
