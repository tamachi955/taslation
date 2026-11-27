"""The sound words (`taslation.soundwords`): the list's forms through the normaliser, the readings that are candidates,
a sound word found among the readers' readings - what they read alike, else one of theirs or one with a kana they mix
up changed -; and the pipeline's part (`Pipeline._sound_word`): lettering on the page whose short kana reading is one
takes it and the kind "sfx", one each reader read otherwise and none matches is left as drawn, a bubble's lettering
and a reading the gate dropped are as read; and the audit's counts. Fake readers stand in
(tests/test_judge_at_read.py's way); the measurement on the sample set is in docs/DEVELOPMENT.md ("Sound words")."""

from __future__ import annotations

import numpy as np
import pytest

from taslation import soundwords as sw
from taslation.config import Settings
from taslation.ocr.charspot import CharspotChar, CharspotReading
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion


@pytest.mark.parametrize("reading, skeleton", [
    ("ドッカーーン！！", "ドカン"), ("どきどき", "ドキ"), ("ドキッ", "ドキ"), ("ハァァ", "ハ"), ("ハアア…", "ハ"),
    ("ゴゴゴゴ", "ゴ"), ("アハハハ", "アハ"), ("キャーキャー", "キャ"), ("ギャアアア", "ギャ"), ("ウォオオ", "ウオ"),
    ("力タン", "カタン"), ("ｶﾞﾀｯ", "ガタ"), ("ズ一ン", "ズン"), ("ザワ ザワ", "ザワ"), ("", ""), ("ーー！", ""),
    ("今日は", ""),
])
def test_a_reading_s_skeleton_folds_lengthening_repeats_and_lookalikes_away(reading, skeleton):
    assert sw.skeleton(reading) == skeleton


def test_the_list_holds_its_forms_and_their_voicings_and_not_words():
    for word in ("ドーン", "どーん", "トン", "ガタガタ", "かたかた", "パタン", "バタン", "ドキドキ", "ゴゴゴ",
                 "キャー", "ぎゅっ", "シーン", "ハッ"):
        assert sw.known(word), word
    for word in ("ハイ", "ヤメロ", "コンビニ", "ありがとう", "トモダチ"):
        assert not sw.known(word), word
    assert len(sw.BASES.split()) >= 400 and len(set(sw.BASES.split())) == len(sw.BASES.split())


def test_a_candidate_is_short_kana_alone():
    assert sw.candidate("ドドドドドド") and sw.candidate("うわあああ") and sw.candidate("力タン")
    assert not sw.candidate("お前は誰だ") and not sw.candidate("ABC") and not sw.candidate("！？")
    assert not sw.candidate("ア" + "イウエオカキクケ") and not sw.candidate("")


def test_what_readers_read_alike_stands_and_only_a_split_is_set_right():
    assert sw.find(["ドキッ", "ドキッ", ""]) == sw.Found("ドキッ", "read", 2)
    assert sw.find(["力タン", "カタン"]) == sw.Found("カタン", "read", 2)  # (a look-alike read as its kana)
    # readers that read alike: the first reader's reading when it is among them (its dots and marks as read), else
    # the one most of them read
    assert sw.find(["ドキッ．．．", "ドキッ", "ドキッ"]) == sw.Found("ドキッ．．．", "read", 3)
    assert sw.find(["ドウーン", "ドカーン", "ドカァーン"]) == sw.Found("ドカーン", "read", 2)
    assert sw.find(["ゴロ", "ドスン", "ドスン"]) == sw.Found("ドスン", "read", 2)
    # ... and short kana they read alike that is no sound word is no reading to set right (a line of narration)
    assert sw.find(["ーそれなら", "それなら", "それなら"]) is None and sw.find(["ヤメロ", "ヤメロ"]) is None
    assert sw.find(["ドウーン"]) is None  # (one reading alone: as read)
    # each read another thing: a reading that is a sound word (the earlier first), else one kana changed
    assert sw.find(["ヤメ", "ドキッ"]) == sw.Found("ドキッ", "read", 1)
    assert sw.find(["ゴソッ", "ドスン"]) == sw.Found("ゴソッ", "read", 1)
    assert sw.find(["ドウーン", "ヤメ"]) == sw.Found("ドカーン", "changed", 1)  # ウ for カ, as measured
    assert sw.find(["ソキッ", "ンキッ"]) is None
    assert sw.find(["お前は誰だ"]) is None and sw.find([]) is None


def test_readers_agree_when_two_of_them_read_alike():
    assert sw.agree(["ドン", "ドン"]) and sw.agree(["ドン"]) and sw.agree(["ドン", "ドソ", "ドン"])
    assert not sw.agree(["ドン", "ドソ"]) and not sw.agree(["ドン", "ドソ", "トン"])


# ------------------------------------------------------------------ the pipeline's part
class Engine:
    """Charspot's reading of each region (told by its crop's first pixel) and the others' readings when settled."""

    def __init__(self, readings: list[tuple[str, float, tuple[str, ...]]]):
        self.readings = readings

    @staticmethod
    def index(image) -> int:
        return image.convert("RGB").getpixel((5, 5))[0] - 1

    def read_chars(self, image) -> CharspotReading:
        text, score, _others = self.readings[self.index(image)]
        return CharspotReading(text, tuple(CharspotChar(c, (0.0, 0.0, 30.0, 30.0), score) for c in text), score)

    def settle(self, image, read: CharspotReading) -> CharspotReading:
        others = self.readings[self.index(image)][2]
        text = others[0] if others and others[0] == read.text else (others[1] if len(others) > 1 else read.text)
        return CharspotReading(text, read.chars, read.score, readings=(read.text, *others))


def run(readings, kind="text", tag="", settings=None):
    n = len(readings)
    rgb = np.full((90 * n + 20, 300, 3), 255, np.uint8)
    regions = []
    for i in range(n):
        y0 = 10 + 90 * i
        rgb[y0:y0 + 80, 10:290] = (i + 1, 200, 200)
        regions.append(TextRegion(10, y0, 290, y0 + 80, np.full((80, 280), 255, np.uint8), (10, y0, 290, y0 + 80),
                                  kind=kind, tag=tag))
    p = Pipeline(settings or Settings(), ocr=Engine(readings), translator=None)
    p._add_sizes((30.0,))
    p._ocr_regions(rgb, regions, lambda _m: None)
    return regions


def test_a_sound_word_on_the_page_takes_the_kind_and_its_reading_is_set_right():
    a, b, c, d = run([("ドキッ", 0.95, ("ドキッ",)), ("ソキッ", 0.95, ("ドキッ", "ドキッ")),
                      ("ソキッ", 0.95, ("ドキッ", "ンキッ")), ("ドウーン", 0.95, ("ヤメテ", "ムリ"))])
    assert (a.status, a.tag, a.sound, a.source_text) == ("untranslated", "sfx", "read", "ドキッ")
    # (the other two readers read alike: the settled reading, as read)
    assert (b.status, b.tag, b.sound, b.source_text) == ("untranslated", "sfx", "read", "ドキッ")
    # each read another thing: the one that is a sound word, else one kana changed - for the reading settled on
    assert (c.status, c.tag, c.sound, c.source_text) == ("untranslated", "sfx", "corrected", "ドキッ")
    assert (d.status, d.tag, d.sound, d.source_text) == ("untranslated", "sfx", "corrected", "ドカーン")
    (e,) = run([("ガーッ", 0.95, ("ガッ", "ガッ"))])  # (the same sound word: the reading settled on, as it is)
    assert (e.tag, e.sound, e.source_text) == ("sfx", "read", "ガッ")


def test_short_kana_each_reader_read_otherwise_and_no_sound_word_is_left_as_drawn():
    split, alike = run([("ヤメロ", 0.95, ("ヤメテ", "ヤメル")), ("ヤメロ", 0.95, ("ヤメロ",))])
    assert (split.status, split.sound, split.tag) == ("sfx", "unsure", "")
    assert (alike.status, alike.sound, alike.tag) == ("untranslated", "none", "")
    (two,) = run([("ーそれなら", 0.95, ("それなら", "それなら"))])  # (no sound word made of what two read alike)
    assert (two.sound, two.tag, two.source_text) == ("none", "", "それなら") and two.status != "sfx"


def test_a_bubble_a_reader_s_kind_a_longer_line_and_a_reading_the_gate_dropped_are_as_read():
    (bubble,) = run([("ソキッ", 0.95, ("ドキッ", "ンキッ"))], kind="bubble")
    assert (bubble.sound, bubble.tag) == ("", "")
    (told,) = run([("ヤメロ", 0.95, ("ヤメテ", "ヤメル"))], tag="narration")
    assert (told.status, told.sound, told.tag) == ("untranslated", "", "narration")
    (line,) = run([("お前は誰だ", 0.95, ("お前は誰か", "お前は誰だ"))])
    assert line.sound == "" and line.status != "sfx"
    (dropped,) = run([("キャー", 0.2, ("キャー", "キャー"))])  # (asked again, mostly drawing: `_sound_word`)
    assert (dropped.status, dropped.sound, dropped.tag) == ("low-confidence", "", "")


def test_without_translate_sfx_a_sound_word_found_is_left_as_drawn():
    s = Settings()
    s.translate_sfx = False
    (a,) = run([("どきっ", 0.95, ("どきっ",))], settings=s)  # (hiragana: not the short katakana `_judge` leaves)
    assert (a.status, a.tag, a.sound) == ("sfx", "sfx", "read")


def test_the_audit_counts_the_sound_words_and_the_codes_on_them():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import audit_render

    regions = [{"sound": "read", "sfx": True, "codes": ["ART_CUT"], "m": {"ink_px": 9}},
               {"sound": "corrected", "sfx": True, "codes": [], "m": {"ink_px": 3}},
               {"sound": "unsure", "sfx": False, "codes": [], "m": {}},
               {"sound": "read", "sfx": True, "codes": ["ART_CUT", "SMALL"], "m": {"ink_px": 1}},
               {"sound": "", "sfx": False, "codes": ["SMALL"], "m": {"ink_px": 4}}]
    lines = audit_render.sound_lines([{"set": "openmantra", "item": "om:1:1@full", "regions": regions}],
                                     [("openmantra", "full")])
    rows = {line.split(" | ")[0]: line.split(" | ")[1] for line in lines if line.startswith("| ")}
    assert rows["| found"] == "3" and rows["| corrected"] == "1"
    assert rows["| as_drawn"] == "1" and rows["| lettered"] == "3"
    assert rows["| on them: ART_CUT"] == "2/3" and rows["| on them: SMALL"] == "1/3"
    assert audit_render.sound_lines([{"set": "s", "item": "x@full", "regions": [{"codes": [], "m": {}}]}],
                                    [("s", "full")]) == []  # (a version before them)
