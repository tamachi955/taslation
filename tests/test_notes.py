"""A book's series (`taslation.notes.series_key`): the volume markers stripped as a window title or a typed name writes
them. (The translator's notes per series that this module also held were removed on 2026-11-06.)"""
from __future__ import annotations

from taslation.notes import series_key


def test_series_key_strips_volume_markers():
    assert series_key("ある物語 3巻") == "ある物語"
    assert series_key("ある物語（３）") == "ある物語"
    assert series_key("ある物語 第12巻") == "ある物語"
    assert series_key("Some Title Vol. 4") == "Some Title"
    assert series_key("Some Title 7") == "Some Title"
    assert series_key("Some Title - 2") == "Some Title"
    assert series_key("ある物語 上") == "ある物語"
    assert series_key("No Volume Here") == "No Volume Here"
    assert series_key("") == "untitled"


def test_a_typed_name_gives_the_series_a_window_title_gives():
    """The start dialog's name (spaces collapsed, as the dialog gives it) and the Book box's: the same series as the
    title of the window, however the volume is written."""
    from taslation import viewerparts
    from taslation.cache import book_key_from_title

    viewerparts.change(lambda memory: memory.learn(["Yomizuq"]))  # an invented viewer, learned on this computer
    title = series_key(book_key_from_title("見本の物語 3巻 - Yomizuq - Google Chrome"))
    assert title == "見本の物語"
    for typed in ("見本の物語 3巻", "見本の物語3巻", "見本の物語 第3巻", "見本の物語 (3)", "見本の物語（３）", "見本の物語(3)",
                  "見本の物語 3", "見本の物語　３", "見本の物語 第３巻", "見本の物語 3 巻", "見本の物語 【第3巻】",
                  "見本の物語 3 (見本コミックス)", "見本の物語（３） (見本コミックスDIGITAL)", "見本の物語 上"):
        assert series_key(typed) == title, typed
    for typed in ("Star Road Vol. 3", "Star Road vol.3", "Star Road Volume 3", "Star Road 3", "Star Road #3",
                  "Star Road - 3", "Star Road: 3", "Star Road, Vol. 3", "Star Road v3", "  Star Road   3  "):
        assert series_key(typed) == "Star Road", typed
    assert series_key("별의 길 3권") == series_key("별의 길 제3권") == "별의 길"  # a Korean reader's typing
    assert series_key("星之路 第3卷") == "星之路" and series_key("星之路 3册") == "星之路"  # Chinese counters
    # what stays: a number that is part of the title, brackets with no volume before them
    assert series_key("ネジマキ13") == "ネジマキ13" and series_key("Star Road (Remastered)") == "Star Road (Remastered)"
    assert series_key("3日目の見本 2") == "3日目の見本"
