"""A book's name as Series and Volume (`taslation.bookname`): the parser that splits a name arriving as one string
(kanji numerals, full-width digits, circled numbers, counters, brackets, imprints, titles ending in a digit, 上/下,
decimals, no volume), the Volume field's normaliser, the one name the two fields make, the reader's own split kept
where the parser's differs, and names that name one book. Invented titles only."""
from __future__ import annotations

import pytest

from taslation import bookname
from taslation.bookname import (BookName, compose, entry_for, kanji_number, parse_name, same_book, split_name,
                                volume_of)
from taslation.i18n import load_ui_table
from taslation.notes import TEMPORARY_STAMP, legacy_series_key, series_key

# a name as one string -> its series and volume
SPLITS = [
    # digits after a separator, with and without counters and marks
    ("Some Title 3", "Some Title", "3"),
    ("Some Title 03", "Some Title", "3"),
    ("Some Title - 3", "Some Title", "3"),
    ("Some Title: 3", "Some Title", "3"),
    ("Some Title 3巻", "Some Title", "3"),
    ("Some Title 第3巻", "Some Title", "3"),
    ("Some Title第3巻", "Some Title", "3"),  # the counter says it: no separator needed
    ("Some Title Vol. 3", "Some Title", "3"),
    ("Some Title, v3", "Some Title", "3"),
    ("Some Title vol3", "Some Title", "3"),
    ("Some Title #3", "Some Title", "3"),
    ("Some Title No. 3", "Some Title", "3"),
    ("Some Title Volume 12", "Some Title", "12"),
    # full-width
    ("Some Title　３", "Some Title", "3"),
    ("Ｓｏｍｅ Ｔｉｔｌｅ ３巻", "Some Title", "3"),
    ("見本の物語　第１２巻", "見本の物語", "12"),
    # kanji numerals
    ("見本の物語 一", "見本の物語", "1"),
    ("見本の物語 第一巻", "見本の物語", "1"),
    ("見本の物語 二十", "見本の物語", "20"),
    ("見本の物語 十一巻", "見本の物語", "11"),
    ("見本の物語 第百巻", "見本の物語", "100"),
    ("見本の物語 第九百九十九巻", "見本の物語", "999"),
    ("見本の物語 一〇巻", "見本の物語", "10"),
    # circled numbers, with no separator too
    ("見本の物語③", "見本の物語", "3"),
    ("見本の物語 ❸", "見本の物語", "3"),
    ("見本の物語①", "見本の物語", "1"),
    ("見本の物語⑳", "見本の物語", "20"),
    # brackets
    ("Some Title (3)", "Some Title", "3"),
    ("見本の物語（３）", "見本の物語", "3"),
    ("見本の物語【第3巻】", "見本の物語", "3"),
    ("見本の物語 (上)", "見本の物語", "上"),
    # an imprint after the volume
    ("Some Title 3 (Some Comics)", "Some Title", "3"),
    ("見本の物語 3 (見本コミックス)", "見本の物語", "3"),
    # the volumes that are no number
    ("見本の物語 上", "見本の物語", "上"),
    ("見本の物語 下巻", "見本の物語", "下"),
    ("見本の物語 中巻", "見本の物語", "中"),
    ("見本の物語 前編", "見本の物語", "前編"),
    ("見本の物語 後篇", "見本の物語", "後編"),
    # decimals
    ("Some Title 10.5", "Some Title", "10.5"),
    ("Some Title Vol. 2.5", "Some Title", "2.5"),
    # other languages' counters
    ("星之路 第3卷", "星之路", "3"),
    ("星之路 3册", "星之路", "3"),
    ("별의 길 제3권", "별의 길", "3"),
    # what is part of a title stays
    ("Some Title13", "Some Title13", ""),  # a digit with no separator before it: the title ends in it
    ("見本の物語３", "見本の物語3", ""),
    ("Reno3", "Reno3", ""),
    ("Some Title (Remastered)", "Some Title (Remastered)", ""),
    ("Summer 2049", "Summer 2049", ""),  # four digits with no mark: a year, not a volume
    ("Some Title 1000", "Some Title 1000", ""),
    ("見本の物語 完全版", "見本の物語 完全版", ""),  # an edition belongs to the series
    ("見本の物語 完全版 3", "見本の物語 完全版", "3"),
    ("No Volume Here", "No Volume Here", ""),
    ("3日目の見本 2", "3日目の見本", "2"),
    ("", "", ""),
]


@pytest.mark.parametrize("name,series,volume", SPLITS)
def test_the_parser_splits_a_name_into_series_and_volume(name, series, volume):
    assert split_name(name) == (series, volume) == parse_name(name)
    assert split_name(name).name == compose(series, volume)


def test_a_temporary_name_is_a_series_of_its_own_with_no_volume():
    import time

    name = f"Untitled book {time.strftime(TEMPORARY_STAMP)}"
    assert split_name(name) == (name, "") and series_key(name) == name


@pytest.mark.parametrize("typed,kept", [
    ("3", "3"), ("03", "3"), ("３", "3"), ("③", "3"), ("❸", "3"), ("⓷", "3"), ("第3巻", "3"), ("3巻", "3"),
    ("Vol. 3", "3"), ("vol3", "3"), ("#3", "3"), ("No. 3", "3"), ("(3)", "3"), ("【第3巻】", "3"), ("三", "3"),
    ("第三巻", "3"), ("十一", "11"), ("二十", "20"), ("百五", "105"), ("九百九十九", "999"), ("一〇", "10"),
    ("10.5", "10.5"), ("2.50", "2.5"), ("010", "10"), ("上", "上"), ("上巻", "上"), ("下巻", "下"), ("前篇", "前編"),
    ("後編", "後編"), ("3권", "3"), ("제3권", "3"), ("第3卷", "3"), (" 3 ", "3"), ("", ""), ("  ", ""),
])
def test_the_volume_field_keeps_a_volume_in_one_spelling(typed, kept):
    assert volume_of(typed) == kept


@pytest.mark.parametrize("typed", ["完全版", "special", "千", "3-4", "v", "Vol.", "第", "上下", "12345", "二三十",
                                   "1.2345"])
def test_anything_else_in_the_volume_field_is_refused(typed):
    assert volume_of(typed) is None
    with pytest.raises(ValueError):
        compose("Some Title", typed)


def test_kanji_numerals():
    assert [kanji_number(t) for t in ("一", "十", "十一", "二十", "百", "百五", "三百五十五", "九百九十九", "二〇五")] == [
        1, 10, 11, 20, 100, 105, 355, 999, 205]
    assert [kanji_number(t) for t in ("", "千", "十十", "百百", "二三十", "〇十", "一二三四", "abc")] == [None] * 8


def test_the_two_fields_make_one_name_in_exactly_one_way():
    for series, volume in (("Some Title", "3"), (" Some   Title ", "第3巻"), ("Ｓｏｍｅ Title", "３"),
                           ("Some Title​", "Vol. 3"), ("Some\tTitle", "③"), ("Some Title", "三")):
        assert compose(series, volume) == "Some Title 3", (series, volume)
    assert compose("見本の物語", "") == "見本の物語" and compose("見本の物語", "下巻") == "見本の物語 下"
    assert compose("", "3") == "" and compose("  ", "") == ""
    assert BookName("見本の物語", "10.5").name == "見本の物語 10.5"


def test_names_that_name_one_book():
    spellings = ["Some Title 3", "Some Title 3巻", "Some Title 第三巻", "Some Title (3)", "some title  3",
                 "Some Title　３", "Some Title Vol. 3", "Some Title ③"]
    for a in spellings:
        for b in spellings:
            assert same_book(a, b), (a, b)
    assert not same_book("Some Title 3", "Some Title 4") and not same_book("Some Title 3", "Some Title")
    assert not same_book("Some Title 3", "Some Title 13") and not same_book("Some Title 1", "Some Title 上")
    assert not same_book("Some Title 3", "Other Title 3")
    assert same_book("見本の物語 3", "見本の物語３")  # as before the two fields: the same name but for its width
    assert same_book("見本の物語 第一巻", "見本の物語 1") and same_book("見本の物語 上巻", "見本の物語 上")


def test_old_series_keys_still_hold_and_kanji_volumes_join_their_series():
    for name in ("ある物語 3巻", "ある物語（３）", "ある物語 第12巻", "ある物語 上"):
        assert series_key(name) == legacy_series_key(name) == "ある物語"
    assert series_key("見本の物語 第一巻") == series_key("見本の物語 二") == series_key("見本の物語 1") == "見本の物語"
    assert legacy_series_key("見本の物語 第一巻") == "見本の物語 第一巻"  # the parser before kept it whole


def test_the_readers_own_split_is_kept_and_followed(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    bookname.use(state)
    assert split_name("Gate 51") == ("Gate", "51")  # the parser reads a volume
    assert bookname.remember("Gate 51", "") == "Gate 51"  # the reader's fields: a series of its own, no volume
    assert split_name("Gate 51") == ("Gate 51", "") and series_key("Gate 51") == "Gate 51"
    assert load_ui_table(state, bookname.SPLITS_TABLE) == {"Gate 51": "Gate 51"}
    bookname.use(None)  # another process: what the state folder keeps
    assert split_name("Gate 51") == ("Gate", "51")
    bookname.use(state)
    assert split_name("Gate 51") == ("Gate 51", "")
    assert bookname.remember("Gate 51", "2") == "Gate 51 2" and split_name("Gate 51 2") == ("Gate 51", "2")
    assert bookname.remember("Some Title 3", "") == "Some Title 3"
    assert split_name("Some Title 3") == ("Some Title 3", "")
    assert bookname.remember("Gate", "51") == "Gate 51"  # split as the parser does again: nothing is kept for it
    assert split_name("Gate 51") == ("Gate", "51")
    assert bookname.remember("Some Title", "3") == "Some Title 3"
    assert load_ui_table(state, bookname.SPLITS_TABLE) == {}  # (the parser's splits are never written)
    with pytest.raises(ValueError):
        bookname.remember("Some Title", "完全版")


def test_a_table_by_book_name_finds_what_an_older_spelling_kept():
    table = {"Some Title 3巻": "start", "見本の物語 第一巻": "translator"}
    assert entry_for(table, "Some Title 3巻") == "start" and entry_for(table, "Some Title 3") == "start"
    assert entry_for(table, "見本の物語 1") == "translator" and entry_for(table, "見本の物語 2") == ""
    assert entry_for({"Some Title 3": "page", "Some Title 3巻": "start"}, "Some Title 3") == "page"  # its own first
    assert entry_for(table, "", "none") == "none"
