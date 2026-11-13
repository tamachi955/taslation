"""tools/ocr_gold.py's position-free yardstick: gold lines and readings pair up by their text, closest first."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import ocr_gold  # noqa: E402


def reading(text, box=(0, 0, 10, 10)):
    return SimpleNamespace(source_text=text, text_box=box)


def test_lines_pair_by_their_text_whatever_the_box():
    items = [{"text": "こんにちは", "box": [0, 0, 50, 50]}, {"text": "さようなら", "box": [100, 0, 150, 50]},
             {"text": "", "box": [200, 0, 250, 50]}]
    read = [reading("さようなら", (500, 500, 510, 510)), reading("こんにちわ"), reading("まったく別", (205, 5, 245, 45))]
    lines, paired, cers, left, on_item = ocr_gold.position_free(items, read)
    assert (lines, paired, left, on_item) == (2, 2, 1, 1)
    assert sorted(cers) == [0.0, 0.2]


def test_a_reading_far_from_every_line_pairs_with_none_and_each_pairs_once():
    items = [{"text": "あいうえお", "box": [0, 0, 5, 5]}]
    lines, paired, cers, left, _ = ocr_gold.position_free(items, [reading("かきくけこ"), reading("あいうえお"), reading("あいうえお")])
    assert (lines, paired, cers, left) == (1, 1, [0.0], 2)
