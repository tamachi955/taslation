"""The series sheet's renderings checked against each translation: one that misses a rendering is flagged "rendering"
(nothing is asked of the model again since 2026-11-06); finding terms, names and honorifics; what a request adds."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from taslation.annotations import Glossary
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion
from taslation.terms import (REQUEST_TERMS_CHARS, _honorific_hits, contains_rendering, cut_entries, find_term,
                             fold_kana, name_words, occurs, required_renderings, term_misses)
from taslation.translate import DictTranslator

def honorific_forms(glossary: Glossary, source: str) -> list[str]:
    """The name-with-honorific forms the sheet asks for in *source*, each once."""
    return list(dict.fromkeys(hit.rendering for hit in _honorific_hits(glossary, source)))


SHEET = {
    "entries": [{"term": "魔法少女", "rendering": "magical girl"}, {"term": "祝福", "rendering": "blessing / boon"}],
    "characters": [
        {"name": "穂杉季和", "rendering": "Hosugi Nowa", "addresses": {"ピョ": "Pyo"}},
        {"name": "ピョ", "rendering": "Pyo", "addresses": {"季和": "Nowa-chan"}},
        {"name": "樫戸朔", "rendering": "Kashido Saku", "addresses": {"季和": "Hosugi-san"}},
    ],
}
KEEP = {  # a sheet that keeps honorifics and knows a first name on its own
    "entries": [],
    "characters": [
        {"name": "穂杉季和", "rendering": "Hosugi Nowa", "addresses": {"樫戸朔": "Kashido"}},
        {"name": "季和", "rendering": "Nowa"},
        {"name": "樫戸朔", "rendering": "Kashido Saku"},
        {"name": "ピョ", "rendering": "Pyo"},
    ],
    "style": {"honorifics": "keep"},
}


def sheet(data: dict = SHEET) -> Glossary:
    g = Glossary(Path("eval.json"), "test")
    g.apply_json(data)
    return g


def test_required_renderings_come_from_terms_names_and_the_speakers_forms():
    g = sheet()
    assert required_renderings(g, "魔法少女になれ") == ["magical girl"]
    assert required_renderings(g, "穂杉季和、十九歳") == ["Hosugi Nowa"]  # the full name, written out
    assert required_renderings(g, "季和、行くよ", speaker="ピョ") == ["Nowa-chan"]  # how this speaker calls her
    assert required_renderings(g, "季和、行くよ", speaker="樫戸朔") == ["Hosugi-san"]
    assert required_renderings(g, "季和、行くよ") == []  # no speaker: the sheets disagree, so nothing is insisted on
    assert required_renderings(g, "ピョ、来て", speaker="穂杉季和") == ["Pyo"]
    assert required_renderings(g, "祝福を") == []  # "A / B" lists alternatives: guidance only
    assert required_renderings(None, "魔法少女") == [] and required_renderings(g, "") == []


def test_contains_rendering_allows_uppercase_lettering_and_a_capital_at_a_sentence_start():
    assert contains_rendering("She's a magical girl.", "magical girl")
    assert contains_rendering("SHE'S A MAGICAL GIRL!", "magical girl")
    assert contains_rendering("Magical girl? Me?", "magical girl")  # a sentence starts with it
    assert contains_rendering("Wait. Magical girls are real?", "magical girl")
    assert not contains_rendering("She's a Magical Girl.", "magical girl")  # capitalised as a title
    assert not contains_rendering("A magic girl.", "magical girl")
    assert contains_rendering("It's Pyo's fault.", "Pyo") and not contains_rendering("It's pyo's fault.", "Pyo")


def test_misses_ignore_possessives_and_honorifics():
    g = sheet()
    assert term_misses(g, "魔法少女だ", "She's a magic girl.") == ["magical girl"]
    assert term_misses(g, "ピョのせい", "It's Pyo's fault.", speaker="穂杉季和") == []
    assert term_misses(g, "季和、行くよ", "Let's go, Nowa-chan!", speaker="ピョ") == []


def test_name_words_and_the_halves_of_a_full_name():
    words, family_first = name_words(sheet(KEEP))
    assert family_first
    assert words["穂杉季和"] == "Hosugi Nowa" and words["季和"] == "Nowa" and words["穂杉"] == "Hosugi"
    assert words["樫戸朔"] == "Kashido Saku" and words["ピョ"] == "Pyo"  # a full name keeps its rendering
    western = sheet({"characters": [{"name": "山田太郎", "rendering": "Taro Yamada"}, {"name": "太郎", "rendering": "Taro"}],
                     "style": {"honorifics": "keep"}})
    words, family_first = name_words(western)
    assert not family_first and words["山田"] == "Yamada"
    assert honorific_forms(western, "山田さん、おはよう") == ["Yamada-san"]


def test_honorifics_the_sheet_keeps_are_required():
    g = sheet(KEEP)
    assert honorific_forms(g, "樫戸さん、ありがとう") == ["Kashido-san"]  # two characters from the start of his name
    assert honorific_forms(g, "季和ちゃんは可愛い") == ["Nowa-chan"]  # a first name the sheet knows
    assert honorific_forms(g, "穂杉さん、ちょっと") == ["Hosugi-san"]  # the other half of her full name
    assert honorific_forms(g, "ピョ様！") == ["Pyo-sama"]
    assert honorific_forms(g, "先生、さようなら") == []  # an honorific with no name before it
    assert required_renderings(g, "樫戸さん、ありがとう") == ["Kashido-san"]
    assert term_misses(g, "樫戸さん、ありがとう", "Mr. Kashido, thank you.") == ["Kashido-san"]
    assert term_misses(g, "樫戸さん、ありがとう", "Kashido-san, thank you.") == []
    assert honorific_forms(sheet(), "樫戸さん") == []  # the sheet says nothing about honorifics


def _region(x0, y0, x1, y1, text_box, **kw) -> TextRegion:
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box, status="untranslated",
                      source_text="魔法少女だ", **kw)


def test_a_missed_rendering_is_flagged_and_nothing_is_asked_again(settings):
    tr = DictTranslator({"魔法少女だ": "A magic girl."})
    p = Pipeline(settings, ocr=None, translator=tr)
    p.glossary = sheet()
    big = _region(0, 0, 400, 300, (100, 100, 300, 200))
    assert p._translate_regions([big], lambda _m: None) == ""
    assert big.translated_text == "A magic girl." and "rendering" in big.flags and len(tr.calls) == 1


def test_no_flag_when_the_check_is_off_or_there_is_no_sheet(settings):
    settings.enforce_terms = False
    tr = DictTranslator({"魔法少女だ": "A magic girl."})
    p = Pipeline(settings, ocr=None, translator=tr)
    p.glossary = sheet()
    big = _region(0, 0, 400, 300, (100, 100, 300, 200))
    p._translate_regions([big], lambda _m: None)
    assert big.translated_text == "A magic girl." and "rendering" not in big.flags
    settings.enforce_terms = True
    p = Pipeline(settings, ocr=None, translator=tr)  # no sheet handed over
    big = _region(0, 0, 400, 300, (100, 100, 300, 200))
    p._translate_regions([big], lambda _m: None)
    assert big.translated_text == "A magic girl." and "rendering" not in big.flags and len(tr.calls) == 2




_sheet = sheet


def test_fold_kana_keeps_every_position():
    assert fold_kana("ピョ") == fold_kana("ピヨ") == fold_kana("ぴよ") == "ぴよ"
    assert fold_kana("チャッカ、ヴァ") == "ちやつか、ゔあ"
    assert fold_kana("魔法ー少女A") == "魔法ー少女A"
    assert len(fold_kana("ァィゥェォッャュョヮヵヶぁぃぅぇぉっゃゅょゎゕゖ")) == 24


def test_a_term_is_found_through_the_kana_the_ocr_gets_wrong():
    assert find_term("ピョ", "おいピヨ、起きろ") == 2
    assert occurs("ピョ", "おいぴよ") and occurs("シャーク", "シヤークだ")
    assert not occurs("ピョ", "ピカリ")  # no edit distance
    assert not occurs("ャ", "ヤ") and occurs("ャ", "ャ")  # one character: as written only
    assert not occurs("", "ピヨ")


def test_a_required_rendering_survives_an_ocr_kana_error_and_the_source_is_left_alone():
    sheet = _sheet({"entries": [{"term": "ピョ", "rendering": "Pyo"}, {"term": "魔", "rendering": "demon"}], "characters": []})
    source = "おいピヨ、起きろ"
    assert required_renderings(sheet, source) == ["Pyo"]
    assert source == "おいピヨ、起きろ"
    assert term_misses(sheet, source, "Hey, wake up") == ["Pyo"]
    assert required_renderings(sheet, "マ") == []


def test_a_term_written_as_it_stands_beats_another_that_only_folds_to_it():
    sheet = _sheet({"entries": [{"term": "ヒャ", "rendering": "Hya"}, {"term": "ヒヤ", "rendering": "Hiya"}], "characters": []})
    assert required_renderings(sheet, "ヒャ！") == ["Hya"]
    assert required_renderings(sheet, "ヒヤ！") == ["Hiya"]


def test_addresses_full_names_and_honorifics_go_through_the_fold_too():
    sheet = _sheet({"entries": [], "style": {"honorifics": "keep"},
                    "characters": [{"name": "ジュン", "rendering": "Jun"},
                                   {"name": "穂杉", "rendering": "Hosugi", "addresses": {"ミャコ": "Myako"}},
                                   {"name": "ミャコ", "rendering": "Myako"}]})
    assert required_renderings(sheet, "ジユンが来た") == ["Jun"]
    assert required_renderings(sheet, "ミヤコだ", "穂杉") == ["Myako"]
    assert honorific_forms(sheet, "ジユンさん") == ["Jun-san"]
    assert honorific_forms(sheet, "ジュンちやん") == ["Jun-chan"]  # the honorific's own small kana


LONG = {
    "entries": [{"term": f"用語{n:03d}", "rendering": f"Term {n}"} for n in range(120)]
    + [{"term": "魔法少女", "rendering": "magical girl", "note": "her job"}, {"term": "ピョ", "rendering": "Pyo"}],
    "characters": [{"name": f"人物{n:03d}", "rendering": f"Person {n}"} for n in range(100)]
    + [{"name": "樫戸朔", "rendering": "Kashido Saku", "gender": "female", "addresses": {"季和": "Nowa-chan"}},
       {"name": "穂杉季和", "rendering": "Hosugi Nowa"}, {"name": "季和", "rendering": "Nowa"}],
    "style": {"honorifics": "keep"},
}


def test_the_entries_the_block_cut_come_by_first_appearance_and_those_it_shows_do_not():
    sheet = _sheet(LONG)
    block = sheet.format()
    assert "魔法少女" not in block and "樫戸朔" not in block and "用語000" in block
    lines = ["用語000と人物000", "魔法少女だ", "ピヨ！", "樫戸朔です", "魔法少女だった"]
    assert cut_entries(sheet, block, lines) == ["- 魔法少女 = magical girl (her job)", "- ピョ = Pyo",
                                                "- 樫戸朔 = Kashido Saku (female; calls 季和 \"Nowa-chan\")"]
    assert cut_entries(sheet, block + "\n- 魔法少女 = magical girl", lines[1:2]) == []
    assert cut_entries(sheet, block, ["何でもない"]) == cut_entries(None, block, lines) == []
    sheet_before = sheet.to_json()
    cut_entries(sheet, block, lines)
    assert sheet.to_json() == sheet_before  # never a word of the lines in the sheet


def test_cut_entries_know_honorifics_name_parts_and_the_speakers_form():
    sheet = _sheet(LONG)
    block = sheet.format()
    assert cut_entries(sheet, block, ["樫戸さん"]) == ["- 樫戸さん = Kashido-san"]
    assert cut_entries(sheet, block, ["季和が"], ["穂杉季和"]) == ["- 季和 = Nowa"]
    assert cut_entries(sheet, block, ["樫戸が"]) == []  # half a name, nothing says which half or what it is
    assert cut_entries(sheet, block, ["季和！"], ["樫戸朔"]) == ["- 季和 = Nowa-chan"]
    assert cut_entries(sheet, block, ["季和さん"]) == ["- 季和さん = Nowa-san"]  # not 季和 as well


def test_a_request_cannot_grow_without_bound():
    sheet = _sheet({"entries": [{"term": f"用語{n:03d}", "rendering": f"A rendering of some length {n}", "note": "n" * 300}
                                for n in range(400)], "characters": []})
    lines = [f"用語{n:03d}" for n in range(400)]
    cut = cut_entries(sheet, "", lines)
    assert sum(len(x) + 1 for x in cut) <= REQUEST_TERMS_CHARS
    assert cut[0] == "- 用語000 = A rendering of some length 0"  # too long a note: the bare rendering
    assert [x.split()[1] for x in cut] == lines[: len(cut)]  # the first to appear


def test_the_pipeline_premises_carry_their_sheet(tmp_path):
    from taslation.annotations import Premises
    from taslation.config import Settings

    p = Pipeline(Settings(), ocr=None, translator=None, cache=None)
    assert p.check_sheet() is None and p.premises() == "" and p.premises().sheet is None
    p.glossary = sheet()
    p.glossary_text = p.glossary.format()
    premises = p.premises()
    assert isinstance(premises, Premises) and premises == p.glossary_text and "magical girl" in premises
    assert premises.sheet is p.glossary and premises.sheet.get("魔法少女").rendering == "magical girl"
