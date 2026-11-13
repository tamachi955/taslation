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
                       size: int, max_rows: int) -> tuple[int, int, int, int]:
    """Draw text in vertical columns, right to left. Returns the text bounding box."""
    columns: list[str] = [text[i : i + max_rows] for i in range(0, len(text), max_rows)]
    col_w = size * 1.15
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    img, truth = make_page(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    with open(args.out.with_suffix(".json"), "w", encoding="utf-8") as f:
        json.dump({"seed": args.seed, "size": list(img.size), "bubbles": truth}, f, ensure_ascii=False, indent=1)
    print(f"wrote {args.out} and {args.out.with_suffix('.json')} ({len(truth)} bubbles)")


if __name__ == "__main__":
    main()
