from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from taslation import size_mix
from taslation.size_mix import Glyph, SizeMix, category, find_mix, measure


def _column(chars: str, x: float, y: float, pitch: float, side: float) -> list[Glyph]:
    """A column of *chars* centred on *x* from *y* down, a cell of *pitch* each, each box *side* tall (a kana's a
    little smaller, as set)."""
    out = []
    for i, ch in enumerate(chars):
        s = side * (size_mix.CELL_SHARE.get(category(ch), 1.0) / size_mix.CELL_SHARE["K"])
        if category(ch) in "ECD":  # punctuation: small, in its cell's corner
            s = side * 0.4
        cy = y + (i + 0.5) * pitch
        out.append(Glyph(ch, (x - s / 2, cy - s / 2, x + s / 2, cy + s / 2), s, s))
    return out


def _columns(parts: list[tuple[str, float, float]], x: float = 300.0, y: float = 20.0) -> list[Glyph]:
    """Columns right to left, each (characters, pitch, box side)."""
    out: list[Glyph] = []
    for chars, pitch, side in parts:
        out += _column(chars, x, y, pitch, side)
        x -= 1.3 * pitch
    return out


def _row(chars: str, x: float, y: float, pitch: float, side: float) -> list[Glyph]:
    out = []
    for i, ch in enumerate(chars):
        cx = x + (i + 0.5) * pitch
        out.append(Glyph(ch, (cx - side / 2, y - side / 2, cx + side / 2, y + side / 2), side, side))
    return out


def test_category_tells_the_kinds_of_character_apart():
    assert [category(c) for c in "漢あアっー！、…「A1♪"] == list("KHTsLECDQA9O")
    assert category("!?") == "E"


def test_one_size_of_lettering_is_no_mix():
    chars = _columns([("今日は", 20, 18.9), ("いい天気", 20, 18.9), ("ですね", 20, 18.9)])
    assert measure(chars, "今日はいい天気ですね") is None


def test_a_larger_column_is_the_big_part():
    chars = _columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最高だ", 32, 30.2)])
    found = measure(chars, "今日は本当に最高だ")
    assert found is not None
    assert (found.start, found.end) == (6, 9)
    assert abs(found.ratio - 1.6) < 0.01 and abs(found.base - 20) < 0.01
    assert 0 < found.base_share <= 1.0


def test_the_big_part_may_stand_first_or_in_the_middle():
    first = measure(_columns([("待て", 30, 28.3), ("どこへ", 20, 18.9), ("行く", 20, 18.9)]), "待てどこへ行く")
    assert first is not None and (first.start, first.end) == (0, 2)
    middle = measure(_columns([("それは", 20, 18.9), ("秘密", 30, 28.3), ("だよ", 20, 18.9)]), "それは秘密だよ")
    assert middle is not None and (middle.start, middle.end) == (3, 5)


def test_the_punctuation_that_ends_the_big_line_goes_with_it():
    chars = _columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最高！！", 32, 30.2)])
    found = measure(chars, "今日は本当に最高！！")
    assert found is not None and (found.start, found.end) == (6, 10)


def test_the_ratio_is_capped():
    chars = _columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最高だ", 56, 52.8)])
    found = measure(chars, "今日は本当に最高だ")
    assert found is not None and found.ratio == size_mix.CAP
    uncapped = measure(chars, "今日は本当に最高だ", cap=0)
    assert uncapped is not None and uncapped.ratio > 2.5


def test_a_small_step_up_is_no_mix():
    chars = _columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最高だ", 23, 21.7)])
    assert measure(chars, "今日は本当に最高だ") is None  # 1.15 times: under `RATIO`


def test_a_column_set_farther_apart_is_not_larger_lettering():
    chars = _columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最高だ", 30, 18.9)])
    assert find_mix(chars).spans == []  # the glyphs themselves the base's size: `CONFIRM`


def test_one_large_character_or_a_lone_small_one_is_no_mix():
    assert measure(_columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最", 32, 30.2)]), "今日は本当に最") is None
    assert measure(_columns([("今", 20, 18.9), ("本当に", 32, 30.2), ("最高だ", 32, 30.2)]), "今本当に最高だ") is None


def test_rows_of_horizontal_lettering_measure_alike():
    chars = _row("今日は本当に", 20, 30, 20, 18.9) + _row("最高だ", 20, 70, 32, 30.2)
    found = measure(chars, "今日は本当に最高だ")
    assert found is not None and (found.start, found.end) == (6, 9)


def test_the_part_maps_onto_a_reading_the_other_readers_changed():
    chars = _columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最高だ", 32, 30.2)])
    found = measure(chars, "今日は本当にさい高だ")  # one character read otherwise, one more
    assert found is not None and "高だ" in "今日は本当にさい高だ"[found.start:found.end]
    assert found.start >= 6
    corrected = found.on("今日はほんとうに最高だ")
    assert corrected is not None and "今日はほんとうに最高だ"[corrected.start:corrected.end] == "最高だ"


def test_a_part_that_would_be_the_whole_text_is_none():
    chars = _columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最高だ", 32, 30.2)])
    assert measure(chars, "最高だ") is None
    assert SizeMix(0, 1, 1.5, 20.0).on("今日は") is None  # without its characters it maps onto nothing


def test_the_pipeline_measures_a_region_from_its_reading(tmp_path):
    from taslation.config import Settings
    from taslation.ocr.charspot import CharspotChar, CharspotReading
    from taslation.pipeline import Pipeline
    from taslation.regions import TextRegion

    glyphs = _columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最高だ", 32, 30.2)])
    chars = tuple(CharspotChar(g.char, g.box, 0.9, 0.99) for g in glyphs)
    reading = CharspotReading("今日は本当に最高だ", chars, 0.9)
    pipe = Pipeline(Settings(state_dir=tmp_path), ocr=None, translator=None, cache=None)
    r = TextRegion(0, 0, 400, 300, np.full((300, 400), 255, np.uint8), (100, 10, 330, 140))
    found = pipe._size_mix(np.zeros((300, 400, 3), np.uint8), r, r.text_box, reading, None,
                           [tuple(int(v) for v in g.box) for g in glyphs])
    assert found is not None and (found.start, found.end) == (6, 9)
    short = CharspotReading("最高", chars[-2:], 0.9)
    assert pipe._size_mix(np.zeros((300, 400, 3), np.uint8), r, r.text_box, short, None, []) is None


def test_a_corrected_reading_keeps_the_part_where_it_maps(tmp_path):
    from taslation.config import Settings
    from taslation.pipeline import Pipeline
    from taslation.regions import TextRegion

    glyphs = _columns([("今日は", 20, 18.9), ("本当に", 20, 18.9), ("最高だ", 32, 30.2)])
    pipe = Pipeline(Settings(state_dir=tmp_path), ocr=None, translator=None, cache=None)
    r = TextRegion(0, 0, 400, 300, np.full((300, 400), 255, np.uint8), (100, 10, 330, 140),
                   source_text="今日は本当に最高だ", status="untranslated")
    r.size_mix = measure(glyphs, r.source_text)
    result = SimpleNamespace(units=[])
    assert pipe.correct_reading(result, r, "今日はほんとうに最高だ")
    assert r.source_text[r.size_mix.start:r.size_mix.end] == "最高だ"
    assert pipe.correct_reading(result, r, "今日は本当に最高だ")  # back to what the OCR read
    assert (r.size_mix.start, r.size_mix.end) == (6, 9)
