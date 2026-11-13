"""The names a translation renders in more than one way (`taslation.name_variants`): found where the Japanese marks a
name with an honorific and the translation gives it two renderings that never stand together, with every gate leaning
to saying nothing (a title, a common word, a second name beside the first, a script without capitals); and put right
on the name's lines only. Synthetic lines only."""
from __future__ import annotations

from types import SimpleNamespace

from taslation.batch import BatchProgress, BatchReader
from taslation.name_variants import RunLine, changes, find_variants, romaji_like, unify_text
from taslation.pipeline import ScannedRegion, ScannedUnit


def _lines(*pairs):
    return [RunLine(ja, en, ("f", (0.1, 0.1 * i, 0.3, 0.1 * i + 0.05))) for i, (ja, en) in enumerate(pairs)]


FILLER = [("おはよう", "Good morning."), ("時間がない", "There is no time."), ("行こう", "Let's go."),
          ("隠れて", "Hide here."), ("待って", "Wait for me.")]


def test_romaji_names_and_not_titles():
    for name in ("Nando", "Ryūji", "Ryuuji", "Shiruma", "Gen'ichi", "Kouta", "Shinji", "Matcha"):
        assert romaji_like(name), name
    for word in ("Queen", "Boss", "Majesty", "Manager", "Lily", "Brother", "Mom"):
        assert not romaji_like(word), word


def test_two_spellings_of_a_kanji_name_are_found_with_their_lines():
    lines = _lines(("竜司さん、おはよう", "Morning, Ryuji-san."), ("竜司さんは？", "Where's Ryuji-san?"),
                   ("竜司さん！", "Ryūji-san!"), ("竜司が来た", "Ryuji is here."), ("竜司くんか", "Ryūji, huh."),
                   *FILLER)
    found = find_variants(lines)
    assert len(found) == 1
    v = found[0]
    assert v.source == "竜司" and v.counts() == [("Ryuji", 3), ("Ryūji", 2)] and v.lines == [0, 1, 2, 3, 4]
    assert v.to_change("Ryūji") == 3 and v.to_change("Ryuji") == 2 and v.to_change("Ryuuji") == 5
    made = changes(v, lines, "Ryūji")
    assert [line.text for line, _new in made] == ["Morning, Ryuji-san.", "Where's Ryuji-san?", "Ryuji is here."]
    assert [new for _line, new in made] == ["Morning, Ryūji-san.", "Where's Ryūji-san?", "Ryūji is here."]


def test_two_readings_of_a_name_each_on_lines_of_their_own():
    lines = _lines(("樫戸さん、おはよう", "Morning, Nando-san."), ("樫戸さんは？", "Where's Nando-san?"),
                   ("樫戸さん！", "Nando-san!"), ("樫戸さん、待って", "Wait, Kashido-san!"), ("樫戸が来た", "Kashido is here."),
                   *FILLER)
    (v,) = find_variants(lines)
    assert v.counts() == [("Nando", 3), ("Kashido", 2)]


def test_a_name_rendered_one_way_is_not_offered():
    lines = _lines(("樫戸さん、おはよう", "Morning, Nando-san."), ("樫戸さんは？", "Where's Nando-san?"),
                   ("樫戸さん！", "Nando-san!"), ("樫戸が来た", "Nando is here."), *FILLER)
    assert find_variants(lines) == []


def test_a_title_before_an_honorific_is_no_name():
    lines = _lines(("女王様、お茶を", "Your Majesty, some tea."), ("女王様！", "My Queen!"), ("女王様は？", "Where is the Queen?"),
                   ("社長さん", "Boss!"), ("社長さんが", "The Boss said so."), ("社長さんの車", "The Manager's car."), *FILLER)
    assert find_variants(lines) == []


def test_a_second_name_beside_the_first_is_not_its_rendering():
    lines = _lines(("樫戸さん、紗緒ちゃんは", "Nando-san, where's Sao?"), ("樫戸さん", "Nando-san."),
                   ("樫戸さん！", "Nando-san!"), ("樫戸さんと紗緒ちゃん", "Nando-san and Sao."),
                   ("紗緒ちゃんだ", "It's Sao."), ("紗緒ちゃん、おいで", "Come, Sao."), ("紗緒ちゃん", "Sao!"), *FILLER)
    assert find_variants(lines) == []


def test_a_word_beside_the_name_that_is_not_like_it_is_not_its_rendering():
    # "Tokyo" stands where the translation left the name out, once: no rendering of it
    lines = _lines(("樫戸さん、おはよう", "Morning, Nando-san."), ("樫戸さんは？", "Where's Nando-san?"),
                   ("樫戸さん！", "Nando-san!"), ("樫戸さん、東京へ", "Off to Tokyo!"), *FILLER)
    assert find_variants(lines) == []


def test_a_common_word_is_no_rendering():
    # "Time" comes in lower case elsewhere: a word, not a name, however often it stands where the name is left out
    lines = _lines(("樫戸さん、おはよう", "Morning, Nando-san."), ("樫戸さんは？", "Where's Nando-san?"),
                   ("樫戸さん！", "Nando-san!"), ("樫戸さん、時間", "Time to go."), ("樫戸さん、時間だ", "Time is up."),
                   *FILLER)
    assert find_variants(lines) == []


def test_a_script_without_capitals_gives_nothing():
    lines = _lines(("竜司さん、おはよう", "早上好，龙司。"), ("竜司さんは？", "龙二呢？"), ("竜司さん！", "龙司！"),
                   ("竜司が来た", "龙二来了。"), *FILLER)
    assert find_variants(lines) == []


def test_a_katakana_name_and_the_sheets_rendering():
    lines = _lines(("シルマちゃん、おはよう", "Morning, Shiruma."), ("シルマちゃん！", "Shiruma!"),
                   ("シルマちゃんは？", "Where's Siruma?"), ("シルマが", "Siruma did it."), ("シルマ、待って", "Wait, Shiruma!"),
                   *FILLER)
    sheet = SimpleNamespace(get_character=lambda name: SimpleNamespace(rendering="Siruma") if name == "シルマ" else None)
    (v,) = find_variants(lines, sheet)
    assert v.source == "シルマ" and v.counts() == [("Shiruma", 3), ("Siruma", 2)] and v.sheet == "Siruma"


def test_unify_keeps_honorifics_possessives_and_capitals():
    assert unify_text("Ryuji-san, Ryuji's bag. RYUJI! Ryujin", ["Ryuji"], "Ryūji") == \
        "Ryūji-san, Ryūji's bag. RYŪJI! Ryujin"
    assert unify_text("Nando and Kashido", ["Kashido"], "Nando") == "Nando and Nando"
    assert unify_text("Nando", ["Nando"], "Nando") == "Nando"


# ------------------------------------------------------------------ the run's lines
def test_a_run_keeps_its_lines_and_offers_the_names_without_the_japanese():
    reader = BatchReader.__new__(BatchReader)
    reader._said = {}
    reader.progress = BatchProgress()
    reader.pipeline = SimpleNamespace(check_sheet=lambda: None, real_translation=lambda ja, text: bool(text))
    pairs = [("竜司さん、おはよう", "Morning, Ryuji-san."), ("竜司さんは？", "Where's Ryuji-san?"),
             ("竜司さん！", "Ryūji-san!"), ("竜司が来た", "Ryuji is here."), ("竜司くんか", "Ryūji, huh."), *FILLER]
    regions = [ScannedRegion(bbox=(10, 10 + 30 * i, 60, 30 + 30 * i), text_box=(10, 10 + 30 * i, 60, 30 + 30 * i),
                             poly=[], source_text=ja, status="untranslated", order=i) for i, (ja, _en) in enumerate(pairs)]
    unit = ScannedUnit(index=0, box=(0, 0, 400, 600), fingerprint="ab" * 8, aspect=0.66, regions=regions)
    reader._keep_said(unit, {i: f" {en} " for i, (_ja, en) in enumerate(pairs)})
    assert len(reader._said) == len(pairs)
    reader._find_names()
    p = reader.progress
    assert [v.source for v in p.names] == ["竜司"] and p.names[0].counts() == [("Ryuji", 3), ("Ryūji", 2)]
    assert all(line.source == "" for line in p.name_lines)  # no Japanese leaves the run
    assert p.name_lines[0].text == "Morning, Ryuji-san." and p.name_lines[0].where[0] == "ab" * 8
    assert p.name_lines[0].where[1] == unit.normalize(regions[0].bbox)
