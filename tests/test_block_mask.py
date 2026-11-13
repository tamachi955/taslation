"""The erase mask of lettering set straight on the page takes the lettering, never the drawing around it."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from taslation.detect import TextBlockDetector
from taslation.detect.textblocks import block_mask
from taslation.regions import TextRegion
from taslation.render import letter_text, find_font, grown_rect, inner_rect
from taslation.render.erase import erase_region

JP_FONTS = [r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\meiryob.ttc", r"C:\Windows\Fonts\msgothic.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
SIZE = 18


def _jp_font(size: int):
    for p in JP_FONTS:
        if Path(p).is_file():
            return ImageFont.truetype(p, size)
    pytest.skip("no Japanese font available")


def _page(draw_art=None, step: float = 1.4):
    """Two columns of vertical lettering on white, with *draw_art* drawing on a layer of its own.

    Returns the gray page and the pixels of the lettering and of the drawing (darker than 200).
    """
    text = Image.new("L", (900, 700), 255)
    art = Image.new("L", (900, 700), 255)
    font = _jp_font(SIZE)
    dt = ImageDraw.Draw(text)
    for col, line in enumerate(["オイ人間", "オレのエサだ"]):
        for i, ch in enumerate(line):
            dt.text((700 - col * int(SIZE * step), 80 + i * int(SIZE * 1.08)), ch, font=font, fill=0)
    if draw_art is not None:
        draw_art(ImageDraw.Draw(art))
    gray = np.minimum(np.asarray(text), np.asarray(art))
    return gray, np.asarray(text) < 200, np.asarray(art) < 200


def _mascot(d: ImageDraw.ImageDraw) -> None:
    """A face in thin lines left of the text, its whiskers ending a few pixels short of the lettering."""
    cx, cy = 600, 150
    d.ellipse((cx - 40, cy - 35, cx + 40, cy + 35), outline=20, width=2)
    d.line((cx - 30, cy - 25, cx - 38, cy - 60, cx - 10, cy - 33), fill=20, width=2)
    d.line((cx + 30, cy - 25, cx + 38, cy - 60, cx + 10, cy - 33), fill=20, width=2)
    for k in (-1, 1):
        d.line((cx + k * 20, cy + 5, cx + k * 70, cy - 2), fill=20, width=1)
        d.line((cx + k * 20, cy + 10, cx + k * 72, cy + 14), fill=20, width=1)
    d.arc((cx - 12, cy + 5, cx + 12, cy + 20), 0, 180, fill=20, width=2)


def _only_block(gray: np.ndarray, inverted: bool = False):
    blocks = TextBlockDetector().detect(np.stack([gray] * 3, axis=2), inverted=inverted)
    assert len(blocks) == 1, [b.bbox for b in blocks]
    b = blocks[0]
    page_mask = np.zeros(gray.shape, bool)
    page_mask[b.y0:b.y1, b.x0:b.x1] = b.mask > 0
    return b, page_mask


@pytest.mark.parametrize("inverted", [False, True])
def test_line_art_next_to_loose_text_is_left_alone(inverted):
    gray, text_px, art_px = _page(_mascot)
    b, mask = _only_block(255 - gray if inverted else gray, inverted)
    assert (mask & art_px).sum() == 0  # not one pixel of the drawing (the old 5x5 closing took the whisker tips)
    assert (mask & text_px).sum() == text_px.sum()  # all of the lettering, with its anti-aliasing
    tx0, ty0, tx1, ty1 = b.text_box
    assert mask[ty0:ty1, tx0:tx1].all()  # counters and gaps too: the text box is free for the translation


def test_line_crossing_the_text_box_is_not_cut():
    """A line of the drawing running between the columns, through the text box, without touching a glyph."""
    probe, _t, _a = _page(step=1.7)
    left_col = probe[:, 650:700].min(axis=0) < 140
    gap_x = 650 + int(np.nonzero(left_col)[0].max()) + 6  # in the gap between the two columns
    gray, text_px, art_px = _page(lambda d: d.line((gap_x, 20, gap_x, 300), fill=20, width=1), step=1.7)
    b, mask = _only_block(gray)
    assert b.text_box[0] < gap_x < b.text_box[2]
    assert (mask & art_px).sum() == 0
    assert (mask & text_px).sum() == text_px.sum()


def test_dot_screen_beside_the_text_is_not_wiped():
    def tone(d: ImageDraw.ImageDraw) -> None:
        for x in range(600, 655, 6):
            for y in range(80, 200, 6):
                d.rectangle((x, y, x + 2, y + 2), fill=40)

    gray, text_px, art_px = _page(tone)
    b, mask = _only_block(gray)
    assert b.x0 < 655  # the region reaches into the tone
    assert (mask & art_px).sum() == 0
    assert (mask & text_px).sum() == text_px.sum()


def test_dash_after_the_last_glyph_is_erased_with_the_text():
    probe, _t, _a = _page()
    b0, _m = _only_block(probe)
    tx0, _ty0, tx1, ty1 = b0.text_box
    cols = np.nonzero(probe[ty1 - 10:ty1, tx0:tx1].min(axis=0) < 140)[0]
    x = tx0 + int(cols.min()) + 6  # under the last glyph of the long (left) column
    y0, y1 = ty1 + 2, min(b0.y1 - 1, ty1 + 12)
    gray, text_px, art_px = _page(lambda d: d.rectangle((x, y0, x + 1, y1), fill=0))
    b, mask = _only_block(gray)
    assert b.text_box == b0.text_box  # too thin to be a glyph of its own
    assert (mask & art_px).sum() == art_px.sum()  # a mark of the lettering, not part of the drawing
    assert (mask & text_px).sum() == text_px.sum()


def test_erase_and_draw_keep_the_drawing():
    gray, text_px, art_px = _page(_mascot)
    rgb = np.stack([gray] * 3, axis=2)
    b, _mask = _only_block(gray)
    out = rgb.copy()
    bg = erase_region(out, b)
    pil = Image.fromarray(out)
    font_path = find_font()
    size = letter_text(pil, b, "Hey, human. That's my food.", str(font_path) if font_path else None, 9, 60,
                       background=bg).size
    done = np.asarray(pil)[:, :, 0]
    assert (done[art_px] == gray[art_px]).all()  # the drawing is untouched, and nothing was lettered over it
    assert size >= 16


def test_grown_rect_takes_the_room_beside_artwork():
    mask = np.full((120, 200), 255, np.uint8)
    mask[40:80, 0:60] = 0  # artwork reaching in from the left, beside the text
    start = (90, 20, 130, 100)  # where the original text was
    centred = inner_rect(mask, center=(110, 60))
    grown = grown_rect(mask, start)
    assert grown is not None
    for x0, y0, x1, y1 in (centred, grown):
        assert mask[y0:y1, x0:x1].min() == 255
    assert grown[0] <= start[0] and grown[2] >= start[2] - 10  # contains (most of) the text area
    area = lambda r: (r[2] - r[0]) * (r[3] - r[1])  # noqa: E731
    assert area(grown) > 1.5 * area(centred)
    assert grown_rect(np.zeros((50, 50), np.uint8), (10, 10, 20, 20)) is None


def test_text_region_letters_in_the_bigger_room():
    mask = np.full((120, 200), 255, np.uint8)
    mask[40:80, 0:60] = 0
    region = TextRegion(0, 0, 200, 120, mask, (90, 20, 130, 100), kind="text")
    bubble = TextRegion(0, 0, 200, 120, mask, (90, 20, 130, 100), kind="bubble")
    font_path = find_font()
    fp = str(font_path) if font_path else None
    text = "I told you that was mine, didn't I?"
    page_img, bubble_img = Image.new("RGB", (200, 120), "white"), Image.new("RGB", (200, 120), "white")
    on_page = letter_text(page_img, region, text, fp, 9, 60).size
    in_bubble = letter_text(bubble_img, bubble, text, fp, 9, 60).size
    assert on_page >= 23 and in_bubble >= 13  # the centred rectangle alone gave 14 and 13
    for img in (page_img, bubble_img):  # and nothing is lettered over the artwork
        assert not (np.asarray(img.convert("L"))[40:80, 0:60] < 128).any()


def _as_detected(gray: np.ndarray, members_box: tuple[int, int, int, int] | None = None):
    """Components and glyph-sized pieces the way the detector sees them (pieces inside *members_box* if given)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats((gray < 140).astype(np.uint8), connectivity=8,
                                                           ltype=cv2.CV_32S)
    members, boxes = [], []
    for k in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[k])
        if 5 <= max(w, h) <= 56 and min(w, h) >= 2 and area >= 6 and max(w, h) / min(w, h) <= 4:
            if members_box is None or (members_box[0] <= x and members_box[1] <= y and x + w <= members_box[2]
                                       and y + h <= members_box[3]):
                members.append(k)
                boxes.append((x, y, x + w, y + h))
    text_box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    glyph = float(np.median([max(b[2] - b[0], b[3] - b[1]) for b in boxes]))
    return labels, stats, members, boxes, text_box, glyph


def test_drawing_the_block_took_in_stays():
    """Under the text a face whose eyes and hands look like glyphs: the block's text box spans the face, and its
    outline (longer than any glyph) shows that a drawing is in there. Only the lettering around the lines goes."""
    def face(d: ImageDraw.ImageDraw) -> None:
        d.ellipse((662, 225, 732, 295), outline=20, width=2)
        for x in (682, 706):
            d.ellipse((x, 252, x + 7, 259), fill=20)
        d.ellipse((650, 286, 658, 294), fill=20)
        d.ellipse((738, 286, 746, 294), fill=20)

    gray, text_px, art_px = _page(face)
    labels, stats, members, boxes, text_box, glyph = _as_detected(gray)
    assert text_box[3] > 290 and text_box[0] < 655  # the face's marks are among the block's pieces
    region = (text_box[0] - 12, text_box[1] - 12, text_box[2] + 12, text_box[3] + 12)
    mask, letter_box = block_mask(gray, labels, stats, members, boxes, text_box, region, glyph)
    page_mask = np.zeros(gray.shape, bool)
    page_mask[region[1]:region[3], region[0]:region[2]] = mask > 0
    assert (page_mask & art_px).sum() == 0
    assert (page_mask & text_px).sum() == text_px.sum()
    assert letter_box[3] < 225  # the translation goes where the lettering was, not onto the face


def test_long_dash_inside_a_column_is_lettering():
    """A wavy dash longer than any glyph between a column's glyphs is set in the line: erased, and no sign of a
    drawing in the block."""
    text = Image.new("L", (900, 700), 255)
    font = _jp_font(SIZE)
    d = ImageDraw.Draw(text)
    for i, ch in enumerate("あれ"):
        d.text((700, 80 + i * int(SIZE * 1.08)), ch, font=font, fill=0)
    for i, ch in enumerate("なにそれ"):
        d.text((675, 80 + i * int(SIZE * 1.08)), ch, font=font, fill=0)
    d.line([(709 + (3 if j % 2 else -3), 122 + j * 6) for j in range(12)], fill=0, width=2)  # wavy, 66 px
    d.text((700, 196), "!?", font=font, fill=0)
    gray = np.asarray(text)
    labels, stats, members, boxes, text_box, glyph = _as_detected(gray)
    region = (text_box[0] - 12, text_box[1] - 12, text_box[2] + 12, text_box[3] + 12)
    mask, _letter_box = block_mask(gray, labels, stats, members, boxes, text_box, region, glyph)
    page_mask = np.zeros(gray.shape, bool)
    page_mask[region[1]:region[3], region[0]:region[2]] = mask > 0
    ink = gray < 200
    assert (page_mask & ink).sum() == ink.sum()


def test_text_on_the_page_is_never_set_over_the_drawing():
    """When the centre of the lettering lies on the drawing no centred rectangle fits; its fallback is not used."""
    mask = np.zeros((120, 200), np.uint8)
    mask[10:110, 30:170] = 255  # only narrow light bands are left around ...
    mask[30:90, 60:140] = 0  # ... a piece of the drawing right in the middle of where the text was
    region = TextRegion(0, 0, 200, 120, mask, (40, 15, 160, 105), kind="text")
    img = Image.new("RGB", (200, 120), "white")
    font_path = find_font()
    letter_text(img, region, "Yeah, yeah.", str(font_path) if font_path else None, 9, 60)
    ink = np.asarray(img.convert("L")) < 128
    assert ink.any() and not ink[30:90, 60:140].any()


def test_small_face_among_the_lettering_stays():
    """A small figure's face (an outline far bigger than the glyphs round its eyes and mouth) is not lettering."""
    def face(d: ImageDraw.ImageDraw) -> None:
        d.ellipse((610, 150, 652, 192), outline=20, width=2)
        d.ellipse((620, 163, 626, 169), fill=20)
        d.ellipse((636, 163, 642, 169), fill=20)
        d.arc((622, 172, 640, 184), 0, 180, fill=20, width=2)

    gray, text_px, art_px = _page(face)
    labels, stats, members, boxes, text_box, glyph = _as_detected(gray)
    assert text_box[0] <= 610  # the face is among the block's pieces
    region = (text_box[0] - 12, text_box[1] - 12, text_box[2] + 12, text_box[3] + 12)
    mask, _letter_box = block_mask(gray, labels, stats, members, boxes, text_box, region, glyph)
    page_mask = np.zeros(gray.shape, bool)
    page_mask[region[1]:region[3], region[0]:region[2]] = mask > 0
    assert (page_mask & art_px).sum() == 0
    assert (page_mask & text_px).sum() == text_px.sum()
