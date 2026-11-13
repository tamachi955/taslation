"""Draw TASlation's application icon with Pillow alone (shapes only: no text, no font files).

Two speech bubbles overlap on a transparent ground: the one behind is white with a dark outline and holds three
short vertical bars (Japanese set in columns), the one in front is green and holds three white horizontal bars
(the translation). Each size is drawn on its own, four times larger and then scaled down, with lines that never
get thinner than about one pixel, so the icon still reads at 16 px.

Writes taslation/ui/assets/taslation.ico (16, 24, 32, 48, 64, 128 and 256 px) and taslation/ui/assets/taslation.png
(256 px). Run it again after changing the drawing: python tools/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "taslation" / "ui" / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)
SUPERSAMPLE = 4
DESIGN = 256  # the drawing below is made on a 256 x 256 grid

INK = (27, 31, 35, 255)  # the outlines and the vertical bars
PAPER = (255, 255, 255, 255)
GREEN = (26, 143, 83, 255)  # #1a8f53: the app's green (#3ddc84) darkened until white bars on it and the bubble on
#                              a dark or a light taskbar all keep a contrast of about 4:1

BACK_BODY = (12, 14, 168, 146)  # the bubble behind: left, top, right, bottom
BACK_TAIL = ((42, 128), (22, 190), (96, 140))
FRONT_BODY = (84, 92, 244, 214)  # the bubble in front
FRONT_TAIL = ((182, 200), (236, 246), (220, 192))


def _stroke(size: int) -> float:
    """The outline's width in design units: 10 at 256 px, never under about a pixel at small sizes."""
    return max(10.0, 1.15 * DESIGN / size)


def _bar(size: int) -> float:
    """The bars' thickness in design units: 14 at 256 px, at least about 1.3 pixels at small sizes."""
    return max(14.0, 1.3 * DESIGN / size)


def _offset_triangle(points: tuple[tuple[float, float], ...], distance: float) -> list[tuple[float, float]]:
    """The triangle with every side moved outward by *distance* (inward when it is negative): scaled about its
    incentre, whose distance to each side is the inradius."""
    (ax, ay), (bx, by), (cx, cy) = points
    a = ((bx - cx) ** 2 + (by - cy) ** 2) ** 0.5  # the side facing each corner
    b = ((ax - cx) ** 2 + (ay - cy) ** 2) ** 0.5
    c = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    perimeter = a + b + c
    ix, iy = (a * ax + b * bx + c * cx) / perimeter, (a * ay + b * by + c * cy) / perimeter
    area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2
    radius = 2 * area / perimeter
    factor = max(0.05, (radius + distance) / radius)
    return [(ix + (x - ix) * factor, iy + (y - iy) * factor) for x, y in points]


def _bubble(draw: ImageDraw.ImageDraw, body: tuple[float, float, float, float],
            tail: tuple[tuple[float, float], ...], fill: tuple[int, int, int, int], stroke: float, k: float) -> None:
    """A rounded box with a tail, outlined: the box and the tail grown by half the outline in ink, then shrunk by
    half the outline in *fill* (the tail's base lies inside the box, so the two insides join without a line)."""
    x0, y0, x1, y1 = (v * k for v in body)
    radius = min(x1 - x0, y1 - y0) * 0.34
    corners = tuple((x * k, y * k) for x, y in tail)
    half = stroke * k / 2
    draw.rounded_rectangle((x0 - half, y0 - half, x1 + half, y1 + half), radius + half, fill=INK)
    draw.polygon(_offset_triangle(corners, half), fill=INK)
    draw.rounded_rectangle((x0 + half, y0 + half, x1 - half, y1 - half), max(1.0, radius - half), fill=fill)
    draw.polygon(_offset_triangle(corners, -half), fill=fill)


def _bars(draw: ImageDraw.ImageDraw, bars: list[tuple[float, float, float, float]], fill: tuple[int, int, int, int],
          k: float) -> None:
    for x0, y0, x1, y1 in bars:
        r = min(x1 - x0, y1 - y0) / 2
        draw.rounded_rectangle((x0 * k, y0 * k, x1 * k, y1 * k), r * k, fill=fill)


def _rounded_box(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int, fill: tuple[int, int, int, int]) -> None:
    """A one-pixel ink outline from (x0, y0) to (x1, y1) inclusive, its corner pixels left out, filled."""
    draw.rectangle((x0 + 1, y0, x1 - 1, y1), fill=INK)
    draw.rectangle((x0, y0 + 1, x1, y1 - 1), fill=INK)
    draw.rectangle((x0 + 1, y0 + 1, x1 - 1, y1 - 1), fill=fill)


def draw_icon_16() -> Image.Image:
    """The 16 px icon drawn pixel by pixel: at this size scaled-down shapes blur the bars into one grey patch."""
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    _rounded_box(draw, 0, 0, 10, 9, PAPER)  # the bubble behind ...
    draw.point([(2, 10), (1, 11)], fill=INK)  # ... its tail, down and to the left
    draw.point([(3, 10)], fill=INK)
    draw.point([(2, 9)], fill=PAPER)
    for x, bottom in ((7, 5), (5, 5), (3, 6)):  # three short columns, read right to left
        draw.line((x, 2, x, bottom), fill=INK)
    _rounded_box(draw, 5, 5, 15, 13, GREEN)  # the bubble in front ...
    draw.point([(13, 14), (14, 15), (12, 14)], fill=INK)  # ... its tail, down and to the right
    draw.point([(13, 13)], fill=GREEN)
    for y, right in ((7, 13), (9, 12), (11, 10)):  # three lines of the translation
        draw.line((7, y, right, y), fill=PAPER)
    return image


def draw_icon(size: int) -> Image.Image:
    """The icon at *size* x *size* pixels, transparent around the bubbles."""
    if size == 16:
        return draw_icon_16()
    big = size * SUPERSAMPLE
    k = big / DESIGN
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    stroke, bar = _stroke(size), _bar(size)

    _bubble(draw, BACK_BODY, BACK_TAIL, PAPER, stroke, k)
    # three short columns, read right to left, the last one shortest
    column_top = BACK_BODY[1] + 26
    columns = []
    for i, length in enumerate((62, 50, 36)):
        cx = 128 - i * 30
        columns.append((cx - bar / 2, column_top, cx + bar / 2, column_top + length))
    _bars(draw, columns, INK, k)

    _bubble(draw, FRONT_BODY, FRONT_TAIL, GREEN, stroke, k)
    rows = []
    for i, length in enumerate((112, 96, 68)):
        cy = 124 + i * 30
        rows.append((108, cy - bar / 2, 108 + length, cy + bar / 2))
    _bars(draw, rows, PAPER, k)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    frames = {size: draw_icon(size) for size in SIZES}
    largest = frames[max(SIZES)]
    largest.save(ASSETS / "taslation.png", format="PNG", optimize=True)
    others = [frames[size] for size in SIZES if size != max(SIZES)]
    largest.save(ASSETS / "taslation.ico", format="ICO", sizes=[(s, s) for s in SIZES], append_images=others)
    print(f"wrote {ASSETS / 'taslation.ico'} ({', '.join(str(s) for s in SIZES)} px) and {ASSETS / 'taslation.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
