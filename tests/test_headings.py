"""The judging rules for lettering beside digits and Latin letters, chapter labels and a contents page's words
(`taslation.headings`, `Pipeline._judge`, `words_carry`, `looks_like_print`, `title_unit`, `printed_lines`), on
invented text: what a reading is, whatever its shape, and what stays as it was (prices, addresses, a colophon's lines,
a viewer's panel, a title page's title and its author's name)."""
from __future__ import annotations

import numpy as np
import pytest

from taslation.headings import heading, labels_in
from taslation.pipeline import Pipeline, japanese_share, looks_like_print, printed_lines, words_carry
from taslation.regions import TextRegion

ACROSS, DOWN = (100, 100, 260, 124), (100, 100, 124, 300)  # a short line set across, a column


def region(kind: str = "text", box=ACROSS, **more) -> TextRegion:
    x0, y0, x1, y1 = box
    return TextRegion(x0=x0 - 6, y0=y0 - 6, x1=x1 + 6, y1=y1 + 6, mask=np.full((y1 - y0 + 12, x1 - x0 + 12), 255, np.uint8),
                      text_box=box, kind=kind, **more)


def judge(settings, text: str, confidence: float = 0.93, kind: str = "text", box=ACROSS, pieces: int = 0) -> str:
    return Pipeline(settings, ocr=None, translator=None, cache=None)._judge(region(kind, box), text, confidence, pieces)


# ------------------------------------------------------------------ the patterns
@pytest.mark.parametrize("text", [
    "第3話", "第十二章", "第2部", "第一夜", "第5幕", "第1楽章", "第4巻", "第七回", "第3.5話", "第３話", "第 1 話",
    "3話", "12章", "その1", "其ノ弐", "其の三", "エピソード4", "目次", "もくじ", "プロローグ", "エピローグ", "序章", "終章",
    "最終話", "最終回", "番外編", "特別編", "外伝", "読み切り", "描き下ろし", "おまけ", "前編", "中編", "後編", "上巻",
    "下巻", "総集編", "幕間", "閑話", "あとがき", "まえがき", "登場人物", "次巻予告",
    "第3話 雨の日の約束", "第3話雨の日の約束",  # the label runs on into its title
    "―第4話―", "【第2章】", "・目次", "一第3話",  # a rule, a bracket, a dot before it; a rule read as the kanji one
])
def test_a_chapter_label_or_a_contents_word_is_a_heading(text):
    assert heading(text), text


@pytest.mark.parametrize("text", [
    "第3話 500円", "第1巻 好評発売中", "無料 第1話", "第2話 試し読み", "第1話 www.example.jp",  # trade, an address
    "第1話 月刊ハルカ2019年5月号", "第2話 ハルカ12号掲載", "初出一覧",  # the record of where the chapters first ran
    "完", "おわり", "上", "下", "Chapter 3", "CONTENTS", "003", "そうだね", "第三者だから", "第一印象",
    "あの第3話", "MIDNIGHT 第3話",  # a label not at the start: no heading (`labels_in` counts it)
])
def test_other_readings_are_no_heading(text):
    assert not heading(text), text


def test_labels_are_counted_anywhere_in_a_reading():
    assert labels_in("第1話第2話第3話第4話第5話") == 5  # a contents list read as one block
    assert labels_in("目次第1話第2話") == 3
    assert labels_in("MIDNIGHT 第3話") == 1
    assert labels_in("そうだね") == 0


# ------------------------------------------------------------------ the judge
@pytest.mark.parametrize("text, box, kind", [
    ("第1話", ACROSS, "text-dark"),  # set across, no kana, a digit: was print (a credit's shape)
    ("目次", ACROSS, "text-dark"),  # the contents word set loose across: was print
    ("第1話第2話第3話第4話第5話", DOWN, "text-dark"),  # the list read as one block, the numerals stacked: was noise
    ("最終話", ACROSS, "text"),
    ("プロローグ", DOWN, "text"),  # katakana alone: was a sound effect
    ("第8話", ACROSS, "bubble"),
])
def test_headings_are_translated_wherever_they_stand(settings, text, box, kind):
    assert judge(settings, text, 0.93, kind, box) == "untranslated"


def test_a_heading_among_many_pieces_of_a_decorated_band_is_still_one(settings):
    assert judge(settings, "第1話", 0.9, "text-dark", ACROSS, pieces=24) == "untranslated"
    assert judge(settings, "そう", 0.9, "text-dark", ACROSS, pieces=24) == "ocr-noise"  # (the pieces rule, as before)


def test_an_unsure_heading_is_still_unsure(settings):
    assert judge(settings, "第1話", 0.5, "text-dark") == "low-confidence"


@pytest.mark.parametrize("text", [
    "3年B組の教室", "100万円あれば", "OKです", "第5試合はAブロック", "Wi-Fiがない", "2人で行こう",
])
def test_digits_and_latin_letters_beside_japanese_read_surely_are_lettering(settings, text):
    """Judged on the kana and kanji read (two or more, read surely), not on their share alone."""
    assert words_carry(text, 0.9)
    assert judge(settings, text, 0.9, "bubble", DOWN) == "untranslated"


def test_a_drawing_read_as_symbols_or_unsure_is_still_thrown_out(settings):
    """A drawing's reading: mostly symbols, or few kana and kanji, or read unsure."""
    for text in ("ロ◇◆※＃〓", "一｜｜ーー＝＝", "ミ＊＊＃＃％"):
        assert japanese_share(text) < 0.6 and not words_carry(text, 0.95)
        assert judge(settings, text, 0.95, "bubble", DOWN) == "ocr-noise", text
    assert not words_carry("AB12CD34の", 0.95)  # one kana: too few to carry it
    assert not words_carry("OKです", 0.75)  # read unsure: judged on its share, as before
    assert judge(settings, "OKです", 0.75, "bubble", DOWN) == "ocr-noise"
    assert not words_carry("木木◇◆※＃〓＊＊", 0.95)  # two kanji among symbols: not written lettering


def test_a_japanese_heading_with_a_latin_subtitle_is_translated(settings):
    text = "時計塔の決まりについてRulesoftheClockTower"  # a heading and its subtitle in Latin letters, read as one
    assert not looks_like_print(text, ACROSS)
    assert judge(settings, text, 0.9, "text", ACROSS) == "untranslated"
    assert judge(settings, "第2章 THE LONG NIGHT", 0.9, "text", ACROSS) == "untranslated"  # (a heading, first)


@pytest.mark.parametrize("text", [
    "Ｓｈｏｐでシリーズを見る", "この巻をAppで読む", "フォローするFollow123",  # a panel: a Latin word first or in it
    "RulesoftheClockTower時計塔の決まり",  # a subtitle read before its heading: as before
    "ABCです",  # too few kana and kanji before the Latin letters
])
def test_a_panel_naming_a_store_or_a_format_in_latin_letters_stays_print(text):
    assert looks_like_print(text, ACROSS), text


@pytest.mark.parametrize("text", [
    "ポイント 120pt", "価格 660円(税込)", "公式サイト https://www.example.jp", "お問い合わせ share@example.com",
    "評価4.5(123件)", "発行日 2019年5月1日", "コード ISBN978-4-00-000000-0", "TVアニメ2024年4月放送開始",
])
def test_prices_addresses_ratings_and_colophon_lines_stay_print(settings, text):
    assert judge(settings, text, 0.95, "text", ACROSS) == "print", text


def test_a_name_set_across_without_kana_stays_a_credit(settings):
    assert judge(settings, "山田太郎", 0.95, "text", ACROSS) == "print"  # an author's name on a title page
    assert judge(settings, "星海書房", 0.95, "text-dark", ACROSS) == "print"  # a publisher's name


def test_a_title_page_keeps_its_title_and_author_but_not_a_chapter_label(settings):
    def read_as(r, text, size):
        r.status, r.source_text, r.char_size = "untranslated", text, size
        return r

    p = Pipeline(settings, translator=None, cache=None)
    title = read_as(region("text", (100, 100, 700, 200), from_model=True), "夜明丸", 80.0)
    author = read_as(region("text", (300, 300, 420, 340)), "山田太郎", 30.0)
    label = read_as(region("text", (300, 50, 420, 90)), "第8話", 30.0)
    regions = [title, author, label]
    p._titles(regions, 12.0, None)
    assert [r.status for r in regions] == ["print", "print", "untranslated"]


def test_a_contents_list_in_one_block_of_the_model_is_no_print():
    def line(y, text):
        r = region("text", (100, y, 300, y + 16))
        r.status, r.source_text, r.char_size = "untranslated", text, 14.0
        return r

    block = region("text", (90, 90, 310, 200), from_model=True)
    block.status = "low-confidence"
    rows = [line(y, f"第{n}話") for n, y in enumerate((100, 125, 150, 175), 1)]
    assert printed_lines([block, *rows]) == []
    blurb = [line(y, "ある日のこと") for y in (100, 125, 150, 175)]
    assert printed_lines([block, *blurb]) == blurb  # a blurb's lines stay print, as before
