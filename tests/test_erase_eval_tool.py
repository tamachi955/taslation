"""tools/erase_eval.py's grounds set: lettering drawn on a clean ground as outlined lettering is, and the score of an
erase against that ground (no dataset needed)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import erase_eval  # noqa: E402


def matte():
    a = np.zeros((40, 30), np.uint8)
    a[5:35, 8:12] = 255  # two strokes
    a[18:22, 4:26] = 255
    return a


def sample(outline, light=False, value=120):
    ground = np.full((erase_eval.SIDE, erase_eval.SIDE, 3), value, np.uint8)
    comp, exact, strokes = erase_eval.lettered(ground, matte(), outline, light)
    return {"bg": "flat", "outline": outline, "comp": comp, "page": ground, "exact": exact, "strokes": strokes,
            "light": light}


def test_the_lettering_is_black_and_its_outline_white():
    s = sample(6)
    luma = erase_eval.luma(s["comp"])
    assert (luma[s["strokes"] & (np.asarray(s["comp"]).min(axis=2) < 150)] < 60).any()
    ring = s["exact"] & ~s["strokes"]
    assert (luma[ring] > 240).mean() > 0.5  # (weighed in uint8, 255 times the outline wrapped round: a dark ring)
    light = sample(0, light=True, value=30)
    assert erase_eval.luma(light["comp"])[light["strokes"]].max() > 240


def test_the_region_is_a_text_blocks_box_round_the_strokes_alone():
    s = sample(6)
    r = erase_eval.ground_region(s)
    ys, xs = np.nonzero(s["exact"])
    assert r.letter_box[0] > xs.min() and r.letter_box[2] <= xs.max()  # the outline lies past it
    assert r.kind == "text"


def test_the_score_of_a_perfect_erase_and_of_none():
    s = sample(3)
    clean = erase_eval.ground_score(s["page"].copy(), s)
    assert clean["mae"] == 0 and clean["ink"] == 0 and clean["ghost"] == 0 and clean["left"] == 0
    left = erase_eval.ground_score(s["comp"].copy(), s)
    assert left["ink"] > 0 and left["ghost"] > 0 and left["left"] > 0 and np.isnan(left["step"])
