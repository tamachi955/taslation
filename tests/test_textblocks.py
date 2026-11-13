from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from taslation.detect import BubbleDetector, TextBlockDetector, merge_regions

JP_FONTS = [r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\meiryob.ttc", r"C:\Windows\Fonts\msgothic.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]


def _jp_font(size: int):
    for p in JP_FONTS:
        if Path(p).is_file():
            return ImageFont.truetype(p, size)
    pytest.skip("no Japanese font available")


def _vertical_text(draw, text, x, y, font, size):
    for i, ch in enumerate(text):
        draw.text((x, y + i * int(size * 1.08)), ch, font=font, fill=(0, 0, 0))


def _page_with_loose_text(size=18, seed=0):
    rng = random.Random(seed)
    img = Image.new("RGB", (900, 700), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _jp_font(size)
    # artwork: hatching lines and a dot screen, no bubble
    for _ in range(60):
        x0, y0 = rng.uniform(40, 400), rng.uniform(40, 650)
        draw.line((x0, y0, x0 + rng.uniform(-80, 80), y0 + rng.uniform(-80, 80)), fill=(30, 30, 30), width=2)
    for i in range(0, 150, 8):
        for j in range(0, 120, 8):
            draw.ellipse((500 + i, 450 + j, 503 + i, 453 + j), fill=(40, 40, 40))
    # dialogue lettered straight onto the page, two vertical columns (columns about 1.4 glyphs apart)
    step = int(size * 1.4)
    _vertical_text(draw, "オイ人間", 700, 80, font, size)
    _vertical_text(draw, "オレのエサだ", 700 - step, 80, font, size)
    return img


def test_text_on_white_is_found_and_art_is_not():
    img = _page_with_loose_text()
    rgb = np.asarray(img)
    assert BubbleDetector().detect(rgb) == []  # nothing closed around the text
    blocks = TextBlockDetector().detect(rgb)
    assert len(blocks) == 1, [b.bbox for b in blocks]
    b = blocks[0]
    tx0, ty0, tx1, ty1 = b.text_box
    assert 665 <= tx0 <= 682 and tx1 >= 712 and ty0 <= 90 and ty1 >= 80 + 5 * 19
    assert b.kind == "text" and b.mask.shape == (b.height, b.width) and b.mask.max() == 255
    assert b.x0 < tx0 and b.x1 > tx1  # room for the translation


def test_print_guard_skips_widgets_and_imprints_but_not_dialogue():
    from taslation.pipeline import looks_like_print

    wide, tall = (0, 0, 300, 40), (0, 0, 40, 300)
    assert looks_like_print("ＩＳＢＮ９７８−４−１２３４５", wide)
    assert looks_like_print("Ｋｉｎｄｌｅストアでシリーズを見る", wide)
    assert looks_like_print("２０２６年１０月２５日発行", wide)
    assert not looks_like_print("今日はいい天気だね", wide)  # horizontal dialogue without digits or Latin
    assert not looks_like_print("３年Ｂ組", tall)  # vertical text is never treated as print
    assert not looks_like_print("ＯＫ", (0, 0, 40, 40))


def test_widely_spaced_horizontal_lines_become_separate_regions():
    """A contents page: one horizontal title per line, lines far apart -> one region per line, not one block."""
    img = Image.new("RGB", (900, 700), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _jp_font(22)
    titles = ["誰だてめえ", "まあ上がれよ", "タバコ吸いてえ", "我慢できない", "脳パイ殺す"]
    for i, t in enumerate(titles):
        draw.text((200, 100 + i * 60), t, font=font, fill=(0, 0, 0))
    blocks = TextBlockDetector().detect(np.asarray(img))
    assert len(blocks) == len(titles), [b.text_box for b in blocks]
    tops = sorted(b.text_box[1] for b in blocks)
    assert all(55 <= b - a <= 65 for a, b in zip(tops, tops[1:]))
    # tightly set horizontal lines (a Western-style bubble) stay one block
    img2 = Image.new("RGB", (900, 400), (255, 255, 255))
    d2 = ImageDraw.Draw(img2)
    for i, t in enumerate(["今日はいい", "天気だね", "散歩しよう"]):
        d2.text((300, 100 + i * 28), t, font=font, fill=(0, 0, 0))
    assert len(TextBlockDetector().detect(np.asarray(img2))) == 1


def test_japanese_share():
    from taslation.pipeline import japanese_share

    assert japanese_share("あ…あの…タバコはダメです") == 1.0
    assert japanese_share("は〜ぁあ〜．．．生き返るわ〜") == 1.0
    assert japanese_share("３５〈む〉＠") < 0.6
    assert japanese_share("") == 0.0


def test_sound_effect_guard():
    from taslation.pipeline import is_sound_effect

    assert is_sound_effect("ドンッ")
    assert is_sound_effect("ゴゴゴ")
    assert is_sound_effect("カチッ…")
    assert not is_sound_effect("えっ")  # hiragana: dialogue
    assert not is_sound_effect("オイ人間")
    assert not is_sound_effect("タバコはダメ")


def test_blocks_inside_bubbles_are_not_duplicated(sample_page):
    rgb = np.asarray(sample_page)
    bubbles = BubbleDetector().detect(rgb)
    blocks = TextBlockDetector().detect(rgb)
    merged = merge_regions(bubbles, blocks)
    assert len(merged) == len(bubbles)  # every text block lies inside a detected bubble


def test_small_text_still_found():
    img = _page_with_loose_text(size=12, seed=3)
    blocks = TextBlockDetector().detect(np.asarray(img))
    assert len(blocks) == 1


@pytest.mark.skipif(sys.platform != "win32", reason="font paths are Windows ones")
def test_dot_screen_alone_gives_nothing():
    img = Image.new("RGB", (400, 400), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for i in range(0, 200, 7):
        for j in range(0, 200, 7):
            draw.ellipse((100 + i, 100 + j, 104 + i, 104 + j), fill=(20, 20, 20))
    assert TextBlockDetector().detect(np.asarray(img)) == []
