"""The lettering audit's codes by level (tools/audit_render.py: the owner's scale, S1 to S4) and its pieces of the
original (lettering, lines) where a glyph is joined to a bubble's outline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import audit_render  # noqa: E402


def test_every_code_has_a_level_on_the_owners_scale():
    codes = {**audit_render.CODES, **audit_render.PAGE_CODES}
    assert set(audit_render.CODE_LEVELS) == set(codes)
    assert set(audit_render.CODE_LEVELS.values()) <= set(audit_render.LEVEL_WORDS)
    levels = audit_render.CODE_LEVELS
    assert levels["UNTRANSLATED"] == levels["MISSED"] == "S1"
    assert levels["OVER_OTHER"] == levels["NOFIT"] == "S2"  # (a translation covered or cut)
    assert levels["LEFT_SHARED"] == levels["LEFT_BY_LINE"] == levels["HYPHEN"] == "S3"
    assert levels["TIGHT"] == "S4"


def test_the_summary_goes_by_level_the_worst_first_each_region_once_a_level(tmp_path):
    regions = [{"codes": ["OVER_OTHER", "INK_OTHER"], "m": {"ink_px": 5}},  # (two S2 codes: one region at S2)
               {"codes": ["HYPHEN"], "m": {"ink_px": 5}},
               {"codes": [], "m": {"ink_px": 5}}]
    page = {"item": "syn:L18@full", "set": "synthetic", "regions": regions, "texts": 3, "seconds": 1,
            "page_codes": [{"code": "MISSED", "truth": 0, "box": [0, 0, 1, 1]}]}
    part = tmp_path / "audit-0.json"
    part.write_text(json.dumps({"pages": [page], "shard": 0, "of": 1}), encoding="utf-8")
    summary, out = tmp_path / "summary.md", tmp_path / "merged.json"
    assert audit_render.merge([part], out, summary) == 0
    text = summary.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| code")]
    names = [row.split(" | ")[0][2:] for row in rows]
    assert names[:2] == ["**S1**", "MISSED"]
    assert names.index("**S2**") < names.index("OVER_OTHER") < names.index("**S3**") < names.index("HYPHEN")
    assert names.index("HYPHEN") < names.index("**S4**")
    cell = {row.split(" | ")[0][2:]: row.split(" | ")[1] for row in rows}
    assert cell["**S2**"] == "1/3, 1 p" and cell["OVER_OTHER"] == "1/3, 1 p" and cell["**S4**"] == "-"
    assert cell["**S1**"] == "-" and cell["MISSED"] == "1/3, 1 p"  # (a page's code: texts, not regions)
    assert json.loads(out.read_text(encoding="utf-8"))["levels"]["OVER_OTHER"] == "S2"


def test_a_glyph_joined_to_the_outline_inside_the_text_box_is_lettering_and_the_outline_a_line():
    page = np.zeros((300, 200), bool)
    outline = np.zeros((300, 200), np.uint8)
    cv2.ellipse(outline, (100, 150), (60, 140), 0, 0, 360, 255, 4)
    page |= outline > 0
    glyph = np.zeros((300, 200), bool)
    glyph[140:162, 140:160] = True  # (a glyph of the column by the outline's right side, x 158..160)
    glyph[142:160, 143:157] = False  # (hollow: a box's stroke 3 px wide)
    page |= glyph
    page[150:152, 120:136] = True  # (a glyph of the column beside it, free)
    letters, lines = audit_render._pieces(page, (110, 60, 160, 240), 22.0, (0, 0, 200, 300))
    # (the glyph's own strokes off the outline's run: those within 2 px of it stay with the line)
    assert letters[glyph & (outline == 0)].mean() > 0.75
    assert letters[150, 125] and not lines[150, 125]
    side = (outline > 0) & ~glyph
    side[:, :150] = False
    assert lines[side].mean() > 0.9  # (the outline's right side, straight on: a line)
    assert letters[(outline > 0) & ~glyph].mean() < 0.05  # (no stretch of the outline taken for lettering)
    # the lettering's box (BOX_SMALL, BOX_BIG) goes by the pieces alone, as up to the audit's version 8: the parts of
    # a line inside the grown text box - a stretch of a curved outline among them - carried it out to that box's edge
    alone, _lines = audit_render._pieces(page, (110, 60, 160, 240), 22.0, (0, 0, 200, 300), joined=False)
    assert alone[150, 125] and not alone[glyph].any() and not alone[outline > 0].any()


def test_a_glyph_of_the_neighbours_column_by_a_shared_outline_is_neither_lettering_nor_a_line():
    page = np.zeros((300, 200), bool)
    page[20:280, 100:103] = True  # (the outline two bubbles share)
    glyph = np.zeros((300, 200), bool)
    glyph[140:160, 84:100] = True  # (a glyph of the left one's column, joined to it)
    glyph[143:157, 87:97] = False
    page |= glyph
    letters, lines = audit_render._pieces(page, (104, 60, 160, 240), 20.0, (60, 0, 200, 300),
                                          others=[(40, 60, 102, 240)])
    assert not letters[glyph].any()
    # (but its stroke along the outline and the corners by it, which a run slanted along the outline takes)
    assert not lines[:, :95][glyph[:, :95]].any()
    assert lines[20:280, 100:103].mean() > 0.95


def test_an_outline_counts_as_cut_where_the_erase_broke_it_not_where_a_glyph_joined_to_it_went():
    still = np.zeros((300, 200), bool)
    still[20:280, 100:103] = True  # (the outline still on the erased page)
    lost = np.zeros((300, 200), bool)
    lost[140:160, 90:100] = True  # (a glyph joined to it, erased: the outline goes on past it)
    assert audit_render._cut(lost, still, (0, 0, 200, 300), 30.0) == 0
    still[120:126, 100:103] = False  # (a gap: the outline broken)
    lost[120:126, 100:103] = True
    assert audit_render._cut(lost, still, (0, 0, 200, 300), 30.0) == 18
    lost[200:240, 100:103] = True  # (a stretch of it gone, longer than a glyph and a half)
    still[200:240, 100:103] = False
    assert audit_render._cut(lost, still, (0, 0, 200, 300), 30.0) == 18 + 120
