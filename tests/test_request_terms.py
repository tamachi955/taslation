"""The sheet's entries the premises block cut come after the bubbles of a request, and only there."""

from __future__ import annotations

from pathlib import Path

import pytest

from taslation.annotations import Glossary, Premises
from taslation.translate import OllamaTranslator
from taslation.translate.ollama import REQUEST_TERMS_HEADING

SHEET = {"entries": [{"term": f"用語{n:03d}", "rendering": f"Term {n}"} for n in range(150)]
         + [{"term": "魔法少女", "rendering": "magical girl"}]}


def sheet() -> Glossary:
    g = Glossary(Path("t.json"), "t")
    g.apply_json(SHEET)
    return g


def translator() -> OllamaTranslator:
    return OllamaTranslator("http://127.0.0.1:1", "m", 1.0, 0.0, 4096, "English")


def premises() -> Premises:
    g = sheet()
    return Premises(g.format(), g)


def user_text(messages: list[dict[str, str]]) -> str:
    return messages[-1]["content"]


@pytest.mark.parametrize("build", [
    lambda t, n: t.build_messages(["魔法少女だ"], [], n),
])
def test_the_cut_entry_comes_after_the_bubbles_and_all_before_them_is_the_stable_prefix(build):
    tr = translator()
    notes = premises()
    with_cut = user_text(build(tr, notes))
    plain = user_text(build(tr, str(notes)))
    assert "- 魔法少女 = magical girl" in with_cut and "魔法少女 = " not in plain
    assert with_cut.startswith(plain + "\n\n" + REQUEST_TERMS_HEADING)


def test_a_line_that_names_nothing_cut_asks_nothing_more():
    tr = translator()
    notes = premises()
    assert user_text(tr.build_messages(["用語000だ"], [], notes)) == user_text(tr.build_messages(["用語000だ"], [], str(notes)))


def test_the_speaker_of_a_bubble_chooses_the_form():
    g = Glossary(Path("t.json"), "t")
    g.apply_json({"characters": [{"name": f"人物{n:03d}", "rendering": f"Person {n}"} for n in range(120)]
                  + [{"name": "季和", "rendering": "Nowa"}, {"name": "朔", "rendering": "Saku", "addresses": {"季和": "Nowa-chan"}}]})
    text = user_text(translator().build_messages(["季和！"], [], Premises(g.format(), g), meta=[{"speaker": "朔"}]))
    assert text.endswith("- 季和 = Nowa-chan")

