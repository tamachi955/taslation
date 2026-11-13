"""Two series sheets compared, as a rename joins a book's sheet to the sheet its new series has already
(`annotations.compare_sheets`): each kind of conflict found and neither sheet changed, what the joining sheet adds
counted, the answers applied (`apply_review`); the rows the rename's review shows them in (`ui.dialogs.conflicts`)
in the window's language; and the cleaning of the short texts the premises keep (`textclean`)."""
from __future__ import annotations

import json
from pathlib import Path

from taslation.annotations import (
    CONFLICT_AREAS,
    CharacterSheet,
    Glossary,
    LetteringStyle,
    StyleGuide,
    apply_review,
    compare_sheets,
)
from taslation.i18n import CATALOGS, set_language
from taslation.textclean import clean_text, looks_like_a_line
from taslation.ui.dialogs import conflicts


def _mine() -> Glossary:
    sheet = Glossary(Path(), "Book", "English")
    sheet.set("ピーヨ", "Piiyo", "the mascot")
    sheet.set("先輩", "senpai")
    sheet.set_character(CharacterSheet(name="ピヨ", rendering="Piyo", pronoun="私", style="polite",
                                       addresses={"ゾリ": "Zori-kun"}))
    sheet.style = StyleGuide(honorifics="keep", tone="light", font="Comic Neue",
                             lettering={"thought": LetteringStyle(italic=True)})
    return sheet


def _theirs() -> Glossary:
    sheet = Glossary(Path(), "Book", "English")
    sheet.set("ピーヨ", "Peeyo", "")  # another rendering
    sheet.set("先輩", "senpai", "an older pupil")  # the same rendering, a note
    sheet.set("魔法", "magic")  # a new term
    sheet.set_character(CharacterSheet(name="ピヨ", rendering="Piyo", pronoun="僕", style="rough", gender="female",
                                       addresses={"ゾリ": "Zori", "ピーヨ": "Pii"}))
    sheet.set_character(CharacterSheet(name="ゾリ", rendering="Zori"))
    sheet.style = StyleGuide(honorifics="drop", tone="dark", font="Wild Words", rules=["Short SFX."],
                             lettering={"thought": LetteringStyle(italic=False, bold=True),
                                        "sfx": LetteringStyle(bold=True)})
    return sheet


def _snapshot(sheet: Glossary) -> str:
    return json.dumps(sheet.to_json(), ensure_ascii=False, sort_keys=True, default=str)


def test_each_kind_of_conflict_is_found_and_neither_sheet_changes():
    mine, theirs = _mine(), _theirs()
    before, theirs_before = _snapshot(mine), _snapshot(theirs)
    review = compare_sheets(mine, theirs)
    assert _snapshot(mine) == before and _snapshot(theirs) == theirs_before
    found = {(c.area, c.key, c.field, c.sub) for c in review.conflicts}
    assert found == {
        ("term", "ピーヨ", "", ""), ("term", "先輩", "", ""),  # another rendering; the same one with a note
        ("character", "ピヨ", "pronoun", ""), ("character", "ピヨ", "style", ""),
        ("character", "ピヨ", "addresses", "ゾリ"),
        ("style", "honorifics", "", ""), ("style", "tone", "", ""), ("style", "font", "", ""),
        ("style", "lettering", "", "thought"),
    }
    assert {c.area for c in review.conflicts} == set(CONFLICT_AREAS)
    term = next(c for c in review.conflicts if c.key == "ピーヨ")
    assert term.mine == ("Piiyo", "the mascot") and term.theirs == ("Peeyo", "")
    # what the join takes over as it is: the new term, the new character, the gender, the new address, the rule and
    # the sfx lettering
    assert review.terms == 6 and review.sheet is theirs
    assert compare_sheets(mine, Glossary(Path(), "Book", "English")).conflicts == []


def test_the_answers_are_applied_and_the_rest_kept():
    mine = _mine()
    review = compare_sheets(mine, _theirs())
    for c in review.conflicts:
        c.take = c.area == "term" or (c.area, c.field) == ("character", "pronoun") or c.key == "lettering"
    counts = apply_review(review, mine)
    assert counts == {"terms": 6, "taken": 4}
    assert mine.get("ピーヨ").rendering == "Peeyo" and mine.get("ピーヨ").note == "the mascot"  # theirs had none
    assert mine.get("先輩").note == "an older pupil" and mine.get("魔法").rendering == "magic"
    piyo = mine.get_character("ピヨ")
    assert (piyo.pronoun, piyo.style, piyo.gender, piyo.addresses) == ("僕", "polite", "female",
                                                                        {"ゾリ": "Zori-kun", "ピーヨ": "Pii"})
    assert mine.style.honorifics == "keep" and mine.style.tone == "light" and mine.style.rules == ["Short SFX."]
    assert mine.style.lettering["thought"] == LetteringStyle(italic=False, bold=True)
    assert mine.style.lettering["sfx"] == LetteringStyle(bold=True)


def test_a_conflict_whose_item_is_gone_is_not_taken():
    mine = _mine()
    review = compare_sheets(mine, _theirs())
    mine.remove_character("ピヨ")
    applied = [c.apply(mine) for c in review.conflicts]
    assert applied.count(False) == 3  # the three of ピヨ: the character is not there any more
    assert all(ok for c, ok in zip(review.conflicts, applied) if c.area != "character")


def test_the_rows_say_what_each_conflict_is_in_the_windows_language():
    review = compare_sheets(_mine(), _theirs())
    rows = {(c.area, c.key, c.field, c.sub): conflicts.conflict_texts(c) for c in review.conflicts}
    assert rows["term", "ピーヨ", "", ""] == ("Term: ピーヨ", "Piiyo (the mascot)", "Peeyo")
    assert rows["character", "ピヨ", "addresses", "ゾリ"] == ("Character ピヨ: how they call ゾリ", "Zori-kun", "Zori")
    assert rows["character", "ピヨ", "pronoun", ""][0] == "Character ピヨ: First person"
    assert rows["style", "lettering", "", "thought"] == ("Style guide: lettering of Thought", "italic", "bold")
    assert rows["style", "font", "", ""] == ("Style guide: Lettering font", "Comic Neue", "Wild Words")
    set_language("ja")
    try:
        what = conflicts.conflict_texts(next(c for c in review.conflicts if c.key == "honorifics"))[0]
        assert what == CATALOGS["ja"]["Style guide: {policy}"].format(policy=CATALOGS["ja"]["Honorifics"])
    finally:
        set_language("en")
    assert conflicts.cut("x" * 100) == "x" * 79 + "…" and conflicts.cut(" a \n b ") == "a b"


def test_every_word_the_rows_show_is_in_every_language():
    words = [*conflicts.FACT_WORDS.values(), *conflicts.POLICY_WORDS.values(), "plain", "italic", "bold"]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(w in catalog for w in words), (code, [w for w in words if w not in catalog])


def test_clean_text():
    assert clean_text("  hello\x00 ​world  see https://example.com/x now\n", 100) == "hello world see now"
    assert clean_text("x" * 500, 10) == "x" * 10
    assert clean_text(None, 5) == ""
    assert looks_like_a_line("あ" * 30) and not looks_like_a_line("ピーヨ")
