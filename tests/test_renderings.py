"""Names held fixed through a book (`taslation.translate.renderings`): which words the book itself shows to be names
(a name before an honorific, as the name helper finds it, rendered with its honorific; a reading in brackets), the
rendering each keeps, and the glossary a line gets from them and from the series sheet (`plamo.glossary_for`,
`ollama.request_terms`)."""

from __future__ import annotations

from pathlib import Path

from taslation.annotations import CharacterSheet, Glossary, Premises
from taslation.translate.ollama import request_terms
from taslation.translate.plamo import glossary_for
from taslation.translate.renderings import (BookNames, NamedPremises, bracketed_readings, honorific_names, reads_as,
                                            romaji)


def test_romaji_and_reading_as():
    assert romaji("つばな") == "tsubana" and romaji("シルマ") == "shiruma" and romaji("あしふじ") == "ashifuji"
    assert romaji("きゃー") == "kya" and romaji("えっ") == "e"
    assert reads_as("ツバナ", "Tsubana") and reads_as("シルマ", "Siruma") and reads_as("りゅうじ", "Ryūji")
    assert reads_as("りゅうじ", "Ryuji") and not reads_as("つばな", "Sparrow") and not reads_as("がつばな", "Tsubana")


def test_a_name_is_what_takes_an_honorific_and_keeps_it_in_the_translation():
    assert honorific_names("芦藤さんが来た", "Ashifuji-san came") == [("芦藤", "Ashifuji")]
    assert honorific_names("また芦藤くんか", "Ashifuji-kun again?") == [("芦藤", "Ashifuji")]
    assert honorific_names("メルちゃん", "Mel-chan!") == [("メル", "Mel")]  # katakana as it stands
    assert honorific_names("柚葉様!", "Lady Yuzuha-sama!") == [("柚葉", "Yuzuha")]


def test_no_name_without_the_honorific_in_the_translation_and_none_for_kin_titles_or_kana():
    assert honorific_names("芦藤さん", "Ashifuji") == []  # nothing shows which word renders it
    assert honorific_names("ママさん", "Mama-san") == [] and honorific_names("店長さん", "Tencho-san") == []
    assert honorific_names("つばなさん", "Tsubana-san") == []  # a name in hiragana: the name helper takes none
    # two kanji names with one honorific: which rendering is whose is not known
    assert honorific_names("田中さんと山田さん", "Tanaka-san and Yamada-san") == []
    # ... with two honorifics, each has its own; two katakana names: each reads as its own
    assert honorific_names("田中さんと山田くん", "Tanaka-san and Yamada-kun") == [("田中", "Tanaka"), ("山田", "Yamada")]
    assert honorific_names("ツバナさんとツバメさん", "Tsubana-san and Tsubame-san") == [("ツバナ", "Tsubana"),
                                                                                  ("ツバメ", "Tsubame")]


def test_a_reading_in_brackets_is_the_names_rendering():
    assert bracketed_readings("芦藤（あしふじ）和也（かずや）だ") == [("芦藤", "Ashifuji"), ("和也", "Kazuya")]
    assert bracketed_readings("芦藤(アシフジ)") == [("芦藤", "Ashifuji")]
    assert bracketed_readings("芦藤だ") == [] and bracketed_readings("（あしふじ）") == []


def test_the_first_rendering_is_held_and_a_reading_outranks_it():
    names = BookNames()
    names.learn("ツバナさん", "Tsubana-san")
    names.learn("ツバナさん!", "Tsubané-san!")  # another rendering later: the first one stays
    assert names.held == {"ツバナ": "Tsubana"}
    names.learn("芦藤さん", "Roto-san")
    names.learn("芦藤（あしふじ）", "Roto")  # the book gives the reading: it wins
    names.learn("芦藤さん", "Ashitou-san")
    assert names.held["芦藤"] == "Ashifuji"
    assert names.glossary("芦藤とツバナが") == [("ツバナ", "Tsubana"), ("芦藤", "Ashifuji")]  # the longer first
    assert names.glossary("何もない") == []
    names.clear()
    assert names.held == {} and len(names) == 0 and bool(names)


def test_the_glossary_takes_the_sheet_first_then_the_names_held():
    sheet = Glossary(Path("s.json"), "series", "English")
    sheet.set_character(CharacterSheet(name="樫戸", rendering="Kashido"))
    names = BookNames()
    names.learn("樫戸さん", "Kashito-san")  # the model's rendering never outranks the sheet's
    names.learn("ツバナさん", "Tsubana-san")
    notes = NamedPremises(sheet.format(), sheet, names)
    assert glossary_for(notes, "樫戸とツバナ") == [("ツバナ", "Tsubana"), ("樫戸", "Kashido")]
    # without a sheet: the names held alone
    assert glossary_for(NamedPremises("", None, names), "ツバナ") == [("ツバナ", "Tsubana")]
    assert glossary_for(Premises("", None), "ツバナ") == []  # premises without the book's names: as before


def test_the_glossary_has_the_parts_of_a_full_name_the_sheet_knows():
    sheet = Glossary(Path("s.json"), "series", "English")
    sheet.set_character(CharacterSheet(name="樫戸二郎", rendering="Jiro Kashido"))
    sheet.set_character(CharacterSheet(name="二郎", rendering="Jiro"))  # so the other half is 樫戸, "Kashido"
    notes = Premises(sheet.format(), sheet)
    assert ("樫戸", "Kashido") not in glossary_for(notes, "樫戸二郎だ")  # within the whole name: not again
    assert glossary_for(notes, "樫戸が来た") == [("樫戸", "Kashido")]  # the part alone, as the chat's cut entries


def test_the_chat_translator_gets_the_names_held_after_its_bubbles():
    names = BookNames()
    names.learn("ツバナさん", "Tsubana-san")
    notes = NamedPremises("", None, names)
    assert request_terms(notes, [{"ja": "ツバナが来た"}, {"ja": "何"}]) == ["- ツバナ = Tsubana"]
    assert request_terms(Premises("", None), [{"ja": "ツバナが来た"}]) == []
    # a name the premises' text shows already is not repeated
    shown = NamedPremises("- ツバナ = Tsubana", None, names)
    assert request_terms(shown, [{"ja": "ツバナが来た"}]) == []


def test_both_translators_learn_from_what_they_translate():
    from taslation.translate.renderings import learn

    names = BookNames()
    learn(NamedPremises("", None, names), [("柚葉さん", "Yuzuha-san"), ("何", "What")])
    learn(Premises("", None), [("芦藤さん", "Roto-san")])  # premises without a memory: nothing to learn into
    assert names.held == {"柚葉": "Yuzuha"}
