"""Which window is the viewer: a browser window's tab title, the rules a --window query is matched by (one window or
the several it fits, never a guess), what looks like a viewer - by what was learned on this computer, or by a reading
word of its title when nothing was - and the incident behind them: `taslation batch --window <viewer>` drove a chat
page whose title began with the viewer's name instead of the reader's tab. The titles below have the shapes of real
windows'; every store and viewer in them is invented (test data)."""
from __future__ import annotations

import pytest

from taslation import capture as capture_mod
from taslation import cli as cli_mod
from taslation import viewerparts
from taslation.capture import (
    WindowInfo,
    find_window,
    looks_like_viewer,
    match_windows,
    tab_title,
    viewer_candidates,
    viewer_rank,
)
from taslation.ui.viewers import choose_viewer

CHROME, FIREFOX = "Chrome_WidgetWin_1", "MozillaWindowClass"


def _win(hwnd: int, title: str, class_name: str = CHROME, size: int = 1000, program: str = "") -> WindowInfo:
    return WindowInfo(hwnd=hwnd, title=title, class_name=class_name, pid=hwnd, rect=(0, 0, size, size),
                      program=program)


def _learned(*parts: str) -> None:
    """*parts* are viewers' parts, as choosing their windows teaches (tests/test_viewer_parts.py)."""
    viewerparts.change(lambda memory: memory.learn(parts))


CHAT = _win(1, "Yomizuq画面翻訳アプリ - Claude - Google Chrome", size=1600)  # the larger one, as in the incident
READER = _win(2, "Yomizuq - Google Chrome", size=1200)  # a store's reader whose tab is titled with its name alone
NOTEPAD = _win(3, "Yomizuqメモ.txt - Notepad", "Notepad", size=600)  # "Yomizuq" in a longer run: no viewer
STORE = _win(4, "見本の物語 1 - FOLIO☆QAT - Microsoft\u200b Edge", size=900)  # "<book> - <store>"; Edge's zero-width space
APP = _win(5, "Yomizuq for PC", "Qt5QWindowIcon", size=800, program="yomizuq.exe")  # the store's own program
VIEWERS = ("Yomizuq", "FOLIO☆QAT", "ズモリカ")


def test_a_browser_windows_tab_title():
    assert READER.tab_title == "Yomizuq" and CHAT.tab_title == "Yomizuq画面翻訳アプリ - Claude"
    assert STORE.tab_title == "見本の物語 1 - FOLIO☆QAT"
    assert tab_title("Yomizuq — Mozilla Firefox", FIREFOX) == "Yomizuq"
    assert tab_title("Yomizuq — Mozilla Firefox Private Browsing", FIREFOX) == "Yomizuq"
    assert tab_title("Yomizuq - 個人 - Microsoft\u200b Edge", CHROME) == "Yomizuq"  # Edge's profile before its name
    assert tab_title("Yomizuq and 2 more pages - Personal - Microsoft Edge", CHROME) == "Yomizuq"
    assert tab_title("Yomizuq - Google Chrome - Work", CHROME) == "Yomizuq"  # a profile after the browser's name
    assert tab_title("A - B - Google Chrome", CHROME) == "A - B"  # a tab title of its own with " - " in it
    # windows of other programs, and a Chromium window that names no browser (an app, Electron): the whole title
    assert tab_title("Yomizuq - Google Chrome", "Notepad") == "Yomizuq - Google Chrome"
    assert tab_title("main.py - TASlation - Visual Studio Code", CHROME) == "main.py - TASlation - Visual Studio Code"
    assert NOTEPAD.tab_title == NOTEPAD.title and APP.tab_title == "Yomizuq for PC"


NEVER = ("Facebook - Google Chrome", "Book1 - Excel", "Bookmarks", "Notebook - OneNote", "e-book",
         "Bookshelf design - Google Chrome")


def test_with_nothing_learned_only_a_reading_word_of_the_title_looks_like_a_viewer():
    for title in ("My Book | Reader", "見本の物語 1 - Yomizuq Books", "電子書籍｜見本の物語", "本棚 - 見本の物語",
                  "The ebook shelf"):
        assert looks_like_viewer(title), title
    # a viewer used for the first time on this computer: nothing tells it from any other window (the reader picks it)
    for title in ("Yomizuq", "Yomizuq - Google Chrome", "Yomizuq for PC", "見本の物語 1 - FOLIO☆QAT", "FOLIO☆QAT",
                  "ズモリカ", "Yomizuq｜見本の物語", *NEVER, "電子書籍ストアの使い方"):
        assert not looks_like_viewer(title), title
    assert not any(looks_like_viewer(w) for w in (READER, STORE, APP, CHAT, NOTEPAD))


def test_a_learned_viewers_name_or_book_must_be_a_word_of_the_title():
    _learned(*VIEWERS)
    for title in ("Yomizuq", "Yomizuq - Google Chrome", "Yomizuq for PC", "見本の物語 1 - FOLIO☆QAT", "FOLIO☆QAT",
                  "ズモリカ", "My Book | Reader", "Yomizuq｜見本の物語", "Yomizuq：見本の物語", "YOMIZUQ"):
        assert looks_like_viewer(title), title
    for title in ("Yomizuq画面翻訳アプリ", "Yomizuq画面翻訳アプリ - Claude - Google Chrome", "Yomizuqアプリの使い方",
                  "Yomizuqs", *NEVER):
        assert not looks_like_viewer(title), title
    assert looks_like_viewer(READER) and looks_like_viewer(STORE) and looks_like_viewer(APP)
    assert not looks_like_viewer(CHAT) and not looks_like_viewer(NOTEPAD)


def test_how_surely_a_window_is_the_viewer():
    club = _win(6, "Book club - Google Chrome")
    assert viewer_rank(READER) is None and viewer_rank(club) == 1  # nothing learned: a reading word only
    _learned(*VIEWERS)
    assert viewer_rank(READER) == 0 and viewer_rank(STORE) == 0  # a viewer's part at an end of the tab title
    assert viewer_rank(APP) == 1  # its name in the title, not a segment of it
    assert viewer_rank(club) == 1
    assert viewer_rank(_win(7, "Yomizuq: 見本の物語 1 - Google Chrome")) == 1  # "Yomizuq", but not the title's end
    assert viewer_rank(CHAT) is None and viewer_rank(NOTEPAD) is None
    assert viewer_candidates([CHAT, NOTEPAD, READER]) == [READER]
    assert viewer_candidates([READER, STORE, club]) == [READER, STORE]
    assert viewer_candidates([CHAT, NOTEPAD]) == []


def test_a_window_chosen_before_is_the_viewer_by_its_title_or_its_program():
    other = _win(9, "見本の物語 2", "Qt5QWindowIcon", program="yomizuq.exe")  # the program on another book
    stranger = _win(10, "見本の物語 2", "Qt5QWindowIcon", program="other.exe")
    assert viewer_rank(APP) is None and viewer_rank(other) is None
    viewerparts.chosen(APP)
    assert viewer_rank(APP) == 0 and viewer_rank(other) == 0 and viewer_rank(stranger) is None
    viewerparts.chosen(_win(11, "見本の物語 3 - Google Chrome", program="chrome.exe"))  # a browser: by its title only
    assert viewer_rank(_win(12, "見本の物語 3 - Google Chrome", program="chrome.exe")) == 0
    assert viewer_rank(_win(13, "Search - Google Chrome", program="chrome.exe")) is None


def test_the_incident_a_query_names_the_readers_tab_not_the_chat_page():
    wins = [CHAT, READER, NOTEPAD]
    assert find_window("Yomizuq", wins) == READER and find_window("yomizuq", wins) == READER  # the exact tab title
    assert find_window("Yomizuq画面", wins) == CHAT  # the start of the chat page's tab title
    assert find_window("Yomizuq - Google Chrome", wins) == READER  # the exact title
    assert find_window("  YOMIZUQ画面翻訳アプリ - claude - google chrome ", wins) == CHAT


def test_the_rules_in_their_order_and_several_windows_named_alike():
    wins = [CHAT, READER, NOTEPAD, STORE, APP]
    for learned in (False, True):  # what was learned changes none of the rules' answers here
        if learned:
            _learned(*VIEWERS)
        assert match_windows("yomizuq for", wins) == [APP]  # a tab title (here a whole title) that starts so
        assert match_windows("見本", wins) == [STORE]
        assert match_windows("FOLIO☆QAT", wins) == [STORE]  # in a viewer's tab title (or any title)
        assert match_windows("メモ.txt", wins) == [NOTEPAD]  # any title, last
        assert match_windows("Google Chrome", wins) == [CHAT, READER]  # in two titles: several, none chosen
        assert find_window("Google Chrome", wins) is None
        assert match_windows("yomi", wins) == [CHAT, READER, NOTEPAD, APP]  # four tab titles start so
        twin = _win(8, "Yomizuq - Google Chrome")
        assert match_windows("Yomizuq", [READER, twin]) == [READER, twin]
        assert find_window("Yomizuq", [READER, twin]) is None
        assert match_windows("nothing like it", wins) == [] and match_windows("  ", wins) == []


def test_with_nothing_learned_the_window_chooses_by_a_reading_word_or_leaves_the_choice_to_the_reader():
    shelf = _win(9, "見本の物語 1 - Yomizuq Books - Google Chrome")
    assert choose_viewer([CHAT, NOTEPAD, READER]) == (None, [])  # the reader picks it in the Viewer list
    assert choose_viewer([CHAT, NOTEPAD, READER, shelf]) == (shelf, [])  # "Books": a reading word
    assert choose_viewer([CHAT, READER], "Yomizuq画面") == (CHAT, [])  # named: taken, whatever it looks like
    assert choose_viewer([NOTEPAD, READER], "Yomizuq - Google") == (READER, [])


def test_the_windows_own_choice_takes_the_remembered_viewer_and_never_guesses():
    _learned(*VIEWERS)
    assert choose_viewer([CHAT, NOTEPAD, READER]) == (READER, [])
    assert choose_viewer([CHAT, NOTEPAD]) == (None, [])
    assert choose_viewer([READER, STORE, NOTEPAD]) == (None, [READER, STORE])
    assert choose_viewer([CHAT, READER], "Yomizuq画面") == (CHAT, [])  # named: taken, whatever it looks like
    assert choose_viewer([NOTEPAD, READER], "yomiz") == (READER, [])  # named alike: the viewer among them
    assert choose_viewer([CHAT, READER, STORE], "nothing like it") == (None, [READER, STORE])


# ------------------------------------------------------------------ the command line
def _screen(monkeypatch, windows):
    monkeypatch.setattr(capture_mod, "list_windows", lambda include_own=False: list(windows))
    monkeypatch.setattr(cli_mod, "WINDOW_POLL_S", 0.01)


def test_the_command_line_drives_the_readers_tab_in_the_incident(monkeypatch):
    _screen(monkeypatch, [CHAT, READER])
    assert cli_mod._pick_window("Yomizuq") == READER
    assert cli_mod._pick_window("Yomizuq画面") == CHAT


def test_several_matching_windows_end_the_command_with_their_titles(monkeypatch, capsys):
    twin = _win(8, "Yomizuq - Google Chrome", size=700)
    _screen(monkeypatch, [READER, twin, NOTEPAD])
    with pytest.raises(SystemExit) as stop:
        cli_mod._pick_window("Yomizuq", wait=5.0)  # no waiting: more windows will not make it fewer
    assert stop.value.code == 2
    out = capsys.readouterr().out
    assert out.startswith("several windows match 'Yomizuq':") and READER.label() in out and twin.label() in out
    assert NOTEPAD.label() not in out and "fuller title" in out and "waiting" not in out
