"""A word the dictionary does not know flags the translation, with an optional dictionary; names and renderings
from the series sheet never do."""

from __future__ import annotations

from pathlib import Path

from taslation.annotations import Glossary
from taslation.review import REASONS, flags_for, known_words, misspelt, spell_checker

KNOWN = {"hello", "there", "a", "magical", "girl", "is", "here", "she", "s", "it", "isn", "t", "over", "yet"}


class FakeChecker:
    def unknown(self, words):
        return {w for w in words if w not in KNOWN}


def _sheet() -> Glossary:
    g = Glossary(Path("eval.json"), "test")
    g.apply_json({"entries": [{"term": "魔法少女", "rendering": "magical girl"}],
                  "characters": [{"name": "穂杉季和", "rendering": "Hosugi Nowa", "addresses": {"ピョ": "Pyo-chan"}}]})
    return g


def test_unknown_words_are_found_and_the_sheets_words_are_not():
    checker = FakeChecker()
    assert misspelt("Helo there", checker) == ["Helo"]
    assert misspelt("Hello there", checker) == []
    assert misspelt("Hosugi Nowa is here", checker) == ["Hosugi", "Nowa"]
    assert misspelt("Hosugi Nowa is here", checker, known_words(_sheet())) == []
    assert misspelt("Pyo-chan, it isn't over yet", checker, known_words(_sheet())) == []  # the address form, the contraction
    assert misspelt("The NASA girl, 3rd", checker) == ["The"]  # an acronym and a word with a digit are left alone
    assert misspelt("HELO THERE", checker) == ["HELO"]  # scanlation capitals are still checked
    assert misspelt("A *magical* girl", checker) == []  # the markers are not words
    assert misspelt("", checker) == [] and misspelt("...!?", checker) == []


def test_the_spelling_flag_follows_the_setting_and_the_dictionary(settings):
    g = _sheet()
    assert flags_for("魔法少女だ", "A magicl girl.", 14, settings, g, checker=FakeChecker()) == ["rendering", "spelling"]
    assert flags_for("魔法少女だ", "A magical girl.", 14, settings, g, checker=FakeChecker()) == []
    settings.spellcheck = False
    assert flags_for("魔法少女だ", "A magicl girl.", 14, settings, g, checker=FakeChecker()) == ["rendering"]
    settings.spellcheck = True
    assert spell_checker("Klingon") is None and spell_checker("") is None
    assert "spelling" in REASONS
    # without the optional package there is no dictionary and no flag
    if spell_checker("English") is None:
        assert flags_for("魔法少女だ", "A magicl girl.", 14, settings, g) == ["rendering"]
