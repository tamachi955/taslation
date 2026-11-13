"""A browser window's title is the title of its active tab: tell whether it still shows the book."""
from __future__ import annotations

from taslation import viewerparts
from taslation.capture import same_book_window

YOMIZUQ = "Yomizuq - Google Chrome"  # an invented viewer, its tab titled with its name alone


def test_same_window_other_tab():
    assert same_book_window(YOMIZUQ, YOMIZUQ)
    assert not same_book_window("ホーム / X - Google Chrome", YOMIZUQ)
    assert not same_book_window("Some chat - Claude - Google Chrome", YOMIZUQ)
    assert not same_book_window("", YOMIZUQ)


def test_query_still_matches():
    assert same_book_window(YOMIZUQ, YOMIZUQ, query="yomizuq")
    assert not same_book_window("ホーム / X - Google Chrome", YOMIZUQ, query="yomizuq")
    # the tab switched to a chat page about the viewer: its name is not a word of that title, so the book is not there
    assert not same_book_window("Yomizuq画面翻訳アプリ - Claude - Google Chrome", YOMIZUQ, query="yomizuq")
    assert same_book_window("Yomizuq: 見本の物語 1 - Google Chrome", YOMIZUQ, query="Yomizuq")
    chat = "Yomizuq画面翻訳アプリ - Claude - Google Chrome"  # picked by its own name, it stays itself
    assert same_book_window(chat, chat, query="Yomizuq画面")


def test_page_numbers_in_the_title_do_not_count_as_a_change():
    a = "Some Title - page 12 | FOLIO☆QAT - Google Chrome"
    b = "Some Title - page 13 | FOLIO☆QAT - Google Chrome"
    for learned in (False, True):  # whether or not the viewer's part was learned on this computer
        if learned:
            viewerparts.change(lambda memory: memory.learn(["FOLIO☆QAT"]))
        assert same_book_window(b, a)
        assert same_book_window("Some Title - p. 14/200 | FOLIO☆QAT - Google Chrome", a)
        assert not same_book_window("Other Title - page 1 | FOLIO☆QAT - Google Chrome", a)
        assert not same_book_window("Some Title - 2 | FOLIO☆QAT - Google Chrome",
                                    "Some Title - 1 | FOLIO☆QAT - Google Chrome")  # a bare number: maybe a volume


def test_standalone_viewer():
    assert same_book_window("Yomizuq", "Yomizuq")
    assert not same_book_window("Yomizuq", "")
