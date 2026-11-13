"""The premises evaluation harness: its checks and scoring (no model needed)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import premises_eval  # noqa: E402


def test_checks():
    assert premises_eval.passes(["has", "Pyo"], "Pyo! Hi")
    assert not premises_eval.passes(["has", "Pyo"], "Pio! Hi")
    assert premises_eval.passes(["lacks", "Hja"], "Hya")
    assert premises_eval.passes(["noword", "he"], "She is here") and not premises_eval.passes(["noword", "he"], "He is")
    assert premises_eval.passes(["regex", r"\b[Ss]he\b"], "She's pissed")
    assert premises_eval.passes(["no_end_punct"], "The parts you stole,") and not premises_eval.passes(["no_end_punct"], "Done.")


def test_set_is_well_formed_and_scoring_counts():
    data = json.loads((ROOT / "tools" / "premises_eval_set.json").read_text(encoding="utf-8"))
    items = data["items"]
    assert len(items) == 24 and all(item["checks"] for item in items)
    outputs = ["" for _ in items]
    passed, total, failures = premises_eval.score(items, outputs)
    assert total == sum(len(i["checks"]) for i in items) == 45
    assert passed == sum(1 for i in items for c in i["checks"] if c[0] in ("lacks", "noword", "no_end_punct"))
    assert len(failures) == total - passed
    from taslation.annotations import Glossary

    sheet = Glossary(Path("eval.json"), "eval")
    sheet.apply_json(data["sheet"])
    text = sheet.format()
    assert "Hokari Kiwa" in text and "Hyo" in text and "Honorifics: keep" in text


def test_the_long_sheet_cuts_the_real_entries_from_the_block():
    from taslation.annotations import Glossary
    from taslation.terms import cut_entries

    data = json.loads((ROOT / "tools" / "premises_eval_set.json").read_text(encoding="utf-8"))
    padded = premises_eval.long_sheet(data["sheet"], 200)
    assert len(padded["characters"]) + len(padded["entries"]) == 200
    assert padded["entries"][-1] == data["sheet"]["entries"][-1]
    sheet = Glossary(Path("eval.json"), "eval")
    sheet.apply_json(padded)
    block = sheet.format()
    assert "Hokari Kiwa" not in block and "scrap hunter" not in block and "Honorifics: keep" in block
    lines = [item["ja"] for item in data["items"]]
    assert any("scrap hunter" in line for line in cut_entries(sheet, block, lines))
