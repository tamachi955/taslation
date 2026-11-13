"""The English README and manual beside their Japanese originals (docs/DEVELOPMENT.md, "The README and the manual")."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAIRS = (("README.md", "README.ja.md"), ("docs/MANUAL.md", "docs/MANUAL.ja.md"))


def _levels(path: Path) -> list[int]:
    """The heading levels in order, outside the code blocks."""
    levels, fence = [], False
    for line in path.read_text("utf-8").splitlines():
        if line.startswith("```"):
            fence = not fence
        elif not fence and (m := re.match(r"(#{1,6}) ", line)):
            levels.append(len(m.group(1)))
    return levels


@pytest.mark.parametrize("english, japanese", PAIRS)
def test_each_english_text_stands_beside_its_japanese_original(english, japanese):
    en, ja = ROOT / english, ROOT / japanese
    en_head = en.read_text("utf-8").splitlines()[:6]
    ja_head = ja.read_text("utf-8").splitlines()[:4]
    assert f"日本語: [{ja.name}]({ja.name})" in en_head
    assert f"English: [{en.name}]({en.name})" in ja_head
    assert any("is the original, and it prevails where the two differ" in line for line in en_head)
    assert _levels(en) == _levels(ja)  # the same headings in the same order
