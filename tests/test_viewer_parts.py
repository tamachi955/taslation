"""What TASlation learns of the viewers on the reader's computer (`taslation.viewerparts`): TASlation lists no store
or viewer, so which window is the reader's viewer, and what of its title is the viewer's rather than the book's, is
learned from the reader's own choices and kept in the state folder's viewers.json only. The learning rules, a viewer
remembered and chosen by itself at the next start, a choice by mistake undone, a title that may be the viewer's own
name held back until the reader names the book, and a state folder of an earlier version (whose lists of names had
cut the viewers' names off the books') opened as before. Every store, viewer and book named here is invented."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from taslation import cli, viewerparts
from taslation.bookid import generic_book_name, last_name, remember_name
from taslation.cache import CachedBubble, CachedPage, CacheStore, book_key_from_title, viewer_key_from_title
from taslation.capture import WindowInfo, viewer_rank
from taslation.ui import viewers
from taslation.ui.viewers import choose_viewer

CHROME = "Chrome_WidgetWin_1"


def _win(hwnd: int, title: str, class_name: str = CHROME, program: str = "chrome.exe") -> WindowInfo:
    return WindowInfo(hwnd=hwnd, title=title, class_name=class_name, pid=hwnd, rect=(0, 0, 1000, 800),
                      program=program)


def _keep(store: CacheStore, book: str) -> None:
    cache = store.open(book, "m")
    cache.add(CachedPage("a" * 80, 0.7, [CachedBubble((0.1, 0.1, 0.2, 0.2), "Hello.")], seq=0))
    cache.save()


@pytest.fixture
def state(tmp_path) -> Path:
    """A scratch state folder this process goes by (never the reader's own)."""
    folder = tmp_path / "state"
    folder.mkdir()
    viewerparts.use(folder)
    return folder


def _kept(state: Path) -> dict:
    return json.loads((state / viewerparts.STATE_FILE).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the rules
def test_two_books_in_one_viewer_teach_what_their_titles_end_alike_with(state):
    assert viewerparts.chosen(_win(1, "見本の物語 1巻 - Yomizuq - Google Chrome")) == []  # one title says nothing yet
    assert book_key_from_title("見本の物語 1巻 - Yomizuq - Google Chrome") == "見本の物語 1巻 - Yomizuq"
    assert viewerparts.chosen(_win(2, "Star Road 2 - Yomizuq - Google Chrome")) == ["Yomizuq"]
    assert book_key_from_title("見本の物語 1巻 - Yomizuq - Google Chrome") == "見本の物語 1巻"
    assert book_key_from_title("Other Book | yomizuq") == "Other Book"
    assert generic_book_name(book_key_from_title("Yomizuq - Google Chrome"))
    kept = _kept(state)
    assert kept["parts"] == ["Yomizuq"] and kept["titles"][-1] == "Star Road 2 - Yomizuq"
    assert "Google Chrome" not in json.dumps(kept["parts"]) and kept["programs"] == []  # a browser: by title only


def test_what_is_never_learned_from_two_titles(state):
    viewerparts.chosen(_win(1, "見本の物語 - 第1話 - Yomizuq"))
    viewerparts.chosen(_win(2, "見本の物語 - 第2話 - Yomizuq"))  # another chapter of the book, not another book
    viewerparts.chosen(_win(3, "Star Road - page 12 - Google Chrome"))
    viewerparts.chosen(_win(4, "Star Road - page 13 - Google Chrome"))  # another page, and the browser
    viewerparts.chosen(_win(5, "Mekurix - Star Road 1", "MekurixWindow", "mekurix.exe"))
    viewerparts.chosen(_win(6, "Mekurix - Other Book", "MekurixWindow", "mekurix.exe"))  # the start: as often a book's
    assert viewerparts.current().parts == []
    assert viewerparts.trailing_parts("A - B - Yomizuq", "C - Yomizuq") == ["Yomizuq"]
    assert viewerparts.trailing_parts("Yomizuq", "A - Yomizuq") == []  # nothing before the shared end in one of them


def test_a_viewer_app_is_followed_through_the_changes_of_its_title(state):
    win = _win(7, "Star Road 1 - Mekurix", "MekurixWindow", "mekurix.exe")
    viewerparts.chosen(win)
    assert viewerparts.retitled("Star Road 1 - Mekurix", "Star Road 1 - Mekurix") == []
    assert viewerparts.retitled("Star Road 1 - Mekurix", "見本の物語 3 - Mekurix") == ["Mekurix"]
    assert book_key_from_title("Star Road 1 - Mekurix") == "Star Road 1" and _kept(state)["programs"] == ["mekurix.exe"]


def test_the_readers_own_naming_teaches_both_ways(state):
    learned, refused = viewerparts.named("Book C - Yomizuq - Google Chrome", "Book C")  # the rest is the viewer's
    assert (learned, refused) == (["Yomizuq"], []) and book_key_from_title("Book D - Yomizuq") == "Book D"
    viewerparts.change(lambda memory: memory.learn(["Folio"]))
    assert book_key_from_title("Night Folio - Folio") == "Night Folio"
    learned, refused = viewerparts.named("Night Folio - Folio", "Night Folio - Folio")  # put back: it is the book's
    assert (learned, refused) == ([], ["Folio"]) and book_key_from_title("Night Folio - Folio") == "Night Folio - Folio"
    assert viewerparts.current().learn(["Folio"]) == []  # never learned again
    learned, _refused = viewerparts.named("Mekurix for Windows 2 - Google Chrome", "Star Road 4")  # nothing of it
    assert learned == ["Mekurix for Windows 2"] and viewerparts.current().is_nameless("Google Chrome")


def test_a_title_that_may_be_the_viewers_own_name_is_held_until_the_reader_names_the_book(state):
    viewerparts.named("Lonely - Google Chrome", "Star Road 1")  # a one-segment title that named no book
    assert generic_book_name(book_key_from_title("Lonely - Google Chrome"))
    title = "Another Tab - Google Chrome"  # another one-segment title in that viewer: maybe the viewer's, maybe a book's
    name = viewerparts.book_for_title(title)
    assert name == "Another Tab" and viewerparts.unconfirmed(title, name)
    viewerparts.hold(name)
    assert generic_book_name(name)  # nothing is kept under it until the reader says
    viewerparts.named(title, "Another Tab")  # the reader took it: the book's
    assert not viewerparts.held(name) and not generic_book_name(name) and not viewerparts.unconfirmed(title, name)
    assert not viewerparts.unconfirmed("Two - Segments - Google Chrome", "Two - Segments")


def test_a_window_chosen_by_mistake_is_forgotten_with_what_it_taught(state):
    viewerparts.chosen(_win(1, "notes.txt - Notepad", "Notepad", "notepad.exe"))
    wrong = _win(2, "todo.txt - Notepad", "Notepad", "notepad.exe")
    learned = viewerparts.chosen(wrong)
    assert learned == ["Notepad"] and viewer_rank(_win(3, "a.txt - Notepad", "Notepad", "notepad.exe")) == 0
    viewerparts.corrected(wrong, learned)
    viewerparts.corrected(_win(1, "notes.txt - Notepad", "Notepad", "notepad.exe"))
    assert viewer_rank(_win(3, "a.txt - Notepad", "Notepad", "notepad.exe")) is None
    assert _kept(state)["parts"] == [] and _kept(state)["programs"] == []


def test_the_shared_programs_are_never_remembered_by_their_program(state):
    for program in ("chrome.exe", "msedge.exe", "python.exe", "applicationframehost.exe"):
        viewerparts.chosen(_win(9, f"Book - {program}", "X", program))
    assert _kept(state)["programs"] == []


# ------------------------------------------------------------------ the next start
def test_a_remembered_viewer_is_picked_automatically_at_the_next_start(state):
    chat = _win(1, "Yomizuq画面翻訳アプリ - Claude - Google Chrome")
    notepad = _win(2, "notes.txt - Notepad", "Notepad", "notepad.exe")
    first = _win(3, "見本の物語 1 - Yomizuq - Google Chrome")
    assert choose_viewer([chat, notepad, first]) == (None, [])  # first use on this computer: the reader picks it
    viewerparts.chosen(first)
    viewerparts.use(state)  # the next start: what was learned is read from the state folder
    again = _win(13, first.title)
    assert choose_viewer([chat, notepad, again]) == (again, [])  # the same tab: by its title
    second = _win(14, "Star Road 2 - Yomizuq - Google Chrome")  # another book in it: by the end the titles share
    assert viewer_rank(second) == 1 and choose_viewer([chat, notepad, second]) == (second, [])
    viewerparts.chosen(second)  # "Yomizuq" learned: every book in it is the viewer for sure
    viewerparts.use(state)
    third = _win(15, "Third Book - Yomizuq - Google Chrome")
    assert viewer_rank(third) == 0 and choose_viewer([chat, notepad, third]) == (third, [])
    assert choose_viewer([chat, notepad, third, _win(16, "Book club - Google Chrome")]) == (third, [])


def test_a_remembered_viewer_app_is_picked_by_its_program_whatever_its_title(state):
    viewerparts.chosen(_win(5, "Mekurix", "MekurixWindow", "mekurix.exe"))
    viewerparts.use(state)
    shown = _win(6, "Star Road 1", "MekurixWindow", "mekurix.exe")
    assert choose_viewer([_win(1, "notes.txt - Notepad", "Notepad", "notepad.exe"), shown]) == (shown, [])


def test_nothing_remembered_reading_words_or_the_readers_choice(state):
    notepad = _win(2, "notes.txt - Notepad", "Notepad", "notepad.exe")
    viewer = _win(3, "見本の物語 1 - Yomizuq - Google Chrome")
    shelf = _win(4, "見本の物語 1 - 電子書籍 - Google Chrome")
    assert choose_viewer([notepad, viewer]) == (None, [])
    assert choose_viewer([notepad, viewer, shelf]) == (shelf, [])
    assert not (state / viewerparts.STATE_FILE).read_text(encoding="utf-8").count("Yomizuq")


class Chooser:
    """What the window does as a viewer is chosen and its book named (`ViewerMixin`)."""

    _learn_viewer = viewers.ViewerMixin._learn_viewer
    _title_book = viewers.ViewerMixin._title_book
    _book_named = viewers.ViewerMixin._book_named
    _book_typed = viewers.ViewerMixin._book_typed

    def __init__(self, store=None):
        self.store, self.selected, self._book_given, self._book_edited = store, None, False, False
        self.book_var = SimpleNamespace(value="", get=lambda: self.book_var.value)

    def choose(self, win: WindowInfo, picked: bool) -> str:
        self._learn_viewer(win, picked)
        self.selected = win
        self.book_var.value = self._title_book(win)
        return self.book_var.value


def test_the_window_learns_from_what_the_reader_types_and_forgets_a_wrong_guess(state):
    w = Chooser()
    assert w.choose(_win(1, "Book C - Yomizuq - Google Chrome"), picked=True) == "Book C - Yomizuq"
    w.book_var.value, w._book_edited = "Book C", True  # typed in the Book box
    w._book_typed()
    assert book_key_from_title("Book D - Yomizuq - Google Chrome") == "Book D"
    w._book_typed()  # once only: the Book box holds the reader's name now
    guessed = _win(2, "a.txt - Notepad", "Notepad", "notepad.exe")
    w.choose(guessed, picked=False)  # chosen by the window itself, no page read from it yet
    w.choose(_win(3, "Book D - Yomizuq - Google Chrome"), picked=True)  # the reader picked another
    assert not viewerparts.current().chose("a.txt - Notepad") and not viewerparts.current().runs("notepad.exe")


# ------------------------------------------------------------------ the book found again
def test_a_book_kept_under_the_fuller_title_name_is_found_again_not_duplicated(state):
    store = CacheStore(state / "cache")
    _keep(store, "見本の物語 1 - Yomizuq")  # kept before "Yomizuq" was learned
    viewerparts.change(lambda memory: memory.learn(["Yomizuq"]))
    assert viewerparts.book_for_title("見本の物語 1 - Yomizuq - Google Chrome", store) == "見本の物語 1 - Yomizuq"
    assert viewerparts.book_for_title("見本の物語 2 - Yomizuq - Google Chrome", store) == "見本の物語 2"
    assert cli._book_name(None, "見本の物語 1 - Yomizuq - Google Chrome", SimpleNamespace(cache_dir=state / "cache")) == (
        "見本の物語 1 - Yomizuq")


def test_the_command_line_asks_for_the_book_where_the_title_may_be_the_viewers_name(state):
    viewerparts.named("Lonely - Google Chrome", "Star Road 1")
    with pytest.raises(SystemExit, match="may be the viewer's name rather than the book's; pass --book NAME"):
        cli._book_name(None, "Another Tab - Google Chrome")
    assert cli._book_name("Star Road 2", "Another Tab - Google Chrome") == "Star Road 2"


# ------------------------------------------------------------------ the state folder of an earlier version
def _earlier_version(folder: Path) -> CacheStore:
    """What an earlier version left: its lists of names had cut the viewers' names off the books' names, and the
    capture profiles and the names last given are kept under what was left of the titles."""
    (folder / "profiles.json").write_text(json.dumps({
        "Yomizuq - Google Chrome": {"margins": [0, 85, 0, 0]},  # "<book> - Yomizuq - Google Chrome"
        "Google Chrome": {"margins": [0, 80, 0, 0]},  # a tab titled with a viewer's name alone
        "Mekurix -  - Google Chrome": {"margins": [1, 2, 3, 4]},  # "Mekurix - <book> - Google Chrome": cut between
        "default_keys": {"next": "Left"},
    }), encoding="utf-8")
    (folder / "ui.json").write_text(json.dumps({"last_book": {"Google Chrome": "見本の物語 2"}, "language": "ja"}),
                                    encoding="utf-8")
    store = CacheStore(folder / "cache")
    for book in ("見本の物語 1", "見本の物語 2", "Star Road 3", "Star Road 5 - Mekurix"):
        _keep(store, book)
    return store


def test_an_earlier_versions_state_folder_opens_every_book_as_before(tmp_path):
    folder = tmp_path / "state"
    folder.mkdir()
    store = _earlier_version(folder)
    viewerparts.use(folder)  # the first start after the update
    kept = _kept(folder)
    assert kept["migrated"] is True and set(kept["parts"]) == {"Yomizuq", "Mekurix"}
    assert kept["nameless"] == ["Google Chrome"] and len(kept["old_books"]) == 4
    # the same titles give the names the caches were kept under, and the capture profiles' keys
    assert viewerparts.book_for_title("見本の物語 1 - Yomizuq - Google Chrome", store) == "見本の物語 1"
    assert viewer_key_from_title("見本の物語 1 - Yomizuq - Google Chrome") == "Yomizuq - Google Chrome"
    assert viewerparts.book_for_title("Mekurix - Star Road 3 - Google Chrome", store) == "Star Road 3"
    assert viewer_key_from_title("Mekurix - Star Road 3 - Google Chrome") == "Mekurix -  - Google Chrome"
    # a viewer the lists named that never showed up in a profile: its book found by its name with one segment fewer
    assert viewerparts.book_for_title("Star Road 3 - Pagecask", store) == "Star Road 3"
    assert viewerparts.current().is_part("Pagecask")
    assert viewerparts.book_for_title("Star Road 9 - Pagecask", store) == "Star Road 9"  # learned from then on
    # a book that was not kept then is not taken for one with a segment fewer
    assert viewerparts.book_for_title("Star Road 5 - Mekurix - Google Chrome", store) == "Star Road 5 - Mekurix"
    # the tab titled with the viewer's name alone: held, so the start asks once, offering the name last given
    name = viewerparts.book_for_title("Hondora - Google Chrome", store)
    assert name == "Hondora" and viewerparts.unconfirmed("Hondora - Google Chrome", name)
    assert last_name(folder, "Hondora - Google Chrome") == "見本の物語 2"
    viewerparts.hold(name)
    viewerparts.named("Hondora - Google Chrome", "見本の物語 2")  # the reader's answer
    remember_name(folder, "Hondora - Google Chrome", "見本の物語 2")
    viewerparts.use(folder)  # the start after that
    assert generic_book_name(book_key_from_title("Hondora - Google Chrome"))  # asked no more: it names no book
    assert viewer_key_from_title("Hondora - Google Chrome") == "Google Chrome"  # the same profile as before
    assert json.loads((folder / "profiles.json").read_text(encoding="utf-8"))["default_keys"] == {"next": "Left"}


def test_the_migration_runs_once_and_keeps_what_was_learned_since(tmp_path):
    folder = tmp_path / "state"
    folder.mkdir()
    _earlier_version(folder)
    viewerparts.use(folder)
    viewerparts.named("Night Folio - Yomizuq", "Night Folio - Yomizuq")  # the reader: "Yomizuq" is the book's here
    viewerparts.use(folder)
    assert not viewerparts.current().is_part("Yomizuq") and viewerparts.current().is_book("Yomizuq")


def test_what_is_learned_stays_in_the_state_folders_file(tmp_path, monkeypatch):
    folder = tmp_path / "state"
    folder.mkdir()
    store = _earlier_version(folder)
    before = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    viewerparts.use(folder)
    viewerparts.chosen(_win(1, "見本の物語 1 - Yomizuq - Google Chrome"))
    viewerparts.book_for_title("Star Road 3 - Pagecask", store)
    after = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    assert set(after) - set(before) == {folder / viewerparts.STATE_FILE}
    assert all(after[p] == data for p, data in before.items())  # no cache, profile or setting changed
    viewerparts.use(None)
    viewerparts.chosen(_win(2, "Star Road 2 - Yomizuq"))  # nothing kept anywhere without a state folder
    assert {p for p in folder.rglob("*") if p.is_file()} == set(after)


def test_a_damaged_file_starts_afresh_and_another_processs_change_is_kept(tmp_path):
    folder = tmp_path / "state"
    folder.mkdir()
    (folder / viewerparts.STATE_FILE).write_text("{not json", encoding="utf-8")
    viewerparts.use(folder)
    assert viewerparts.current().parts == []
    viewerparts.change(lambda memory: memory.learn(["Yomizuq"]))
    data = _kept(folder)
    data["parts"].append("Folio")  # the window and a command line learn at once
    (folder / viewerparts.STATE_FILE).write_text(json.dumps(data), encoding="utf-8")
    viewerparts.change(lambda memory: memory.learn(["Mekurix"]))
    assert _kept(folder)["parts"] == ["Yomizuq", "Folio", "Mekurix"]
