"""What the window says, in plain words: no jargon where a reader meets it, what to do next, the menus' lines in the status
bar, the empty states, the book's three plain settings, and refusals in the window's language."""
from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest
from PIL import Image

from taslation import notice
from taslation.cache import CacheStore
from taslation.config import Settings
from taslation.i18n import CATALOGS, set_language
from taslation.message_texts import LANGUAGES, catalog
from taslation.messages import TEMPLATES, Message, render
from taslation.pipeline import summary
from taslation.regions import PageResult
from taslation.rename import RenameRefused
from taslation.ui.dialogs.book_settings import CHOICES, BookSettingsDialog
from taslation.ui.dialogs.caches import CachesDialog
from taslation.ui.dialogs.help import TOPICS
from taslation.ui.progress import rendered
from taslation.ui.status import StatusMixin
from taslation.ui.tooltip import menu_tip, tip_menu

ALL = ("en", *LANGUAGES)
SEEN_BY_EVERY_READER = ("batch.finished", "batch.failures", "batch.locked", "pipeline.from_cache", "pipeline.translated",
                        "pipeline.to_review", "pipeline.no_content", "pipeline.no_text", "ollama.unreachable", "ollama.http_error",
                        "ollama.timeout", "ollama.connection_failed", "ollama.bad_json", "ollama.reported_error", "ollama.broke_off",
                        "ollama.bad_answer", "ollama.slow", "ollama.loaded", "ocr.model_missing", "health.ocr_missing", "health.ollama_down",
                        "health.ollama_not_installed", "health.ollama_no_answer", "viewer.gone", "viewer.no_area", "viewer.api_failed",
                        "viewer.window_api_failed", "viewer.empty_rect")
JARGON = ("ollama", "ocr", "cache", "http", "json", "fingerprint", "hwnd", "printwindow", "{call}", "{path}", "{url}", "{pid}", "pip ")


@pytest.mark.parametrize("code", SEEN_BY_EVERY_READER)
def test_what_every_reader_meets_has_no_jargon_in_any_language(code):
    for lang in ALL:
        text = catalog(lang)[code].lower()
        assert not any(word in text for word in JARGON), (lang, code, text)


def test_the_english_says_what_to_do_next():
    for code in ("ollama.http_error", "ollama.timeout", "ollama.connection_failed", "ollama.bad_answer"):
        assert "Press F5 to try again" in TEMPLATES[code]
    assert "F5" in TEMPLATES["ollama.unreachable"] and "install.cmd" in TEMPLATES["ocr.model_missing"]


@pytest.mark.parametrize("lang", ALL)
def test_a_whole_book_run_is_told_in_minutes(lang):
    done = Message("batch.finished", pages=3, bubbles=12, seconds=125.0, minutes=2, failed=0, error="",
                   reason=Message("batch.finished_reading"))
    text = render(done, catalog(lang))
    assert "125" not in text and "2" in text


def test_the_legal_notice_names_no_command_and_no_program_in_any_language():
    assert notice.NOTICE_VERSION >= 5
    assert set(LANGUAGES) | {"en"} <= set(notice.TEXTS)
    for lang, text in notice.TEXTS.items():
        assert "taslation notice" not in text and "Ollama" not in text, lang


def test_a_page_without_text_says_so():
    page = Image.new("RGB", (8, 8))
    empty = PageResult(image=page, original=page, regions=[], fingerprints=["a"])
    assert summary(empty) == Message("pipeline.no_text") and str(summary(empty)) == "No text on this page."
    assert "0" not in StatusMixin._summary(empty)
    failed = PageResult(image=page, original=page, regions=[], fingerprints=["a"], error="something broke")
    assert summary(failed).code == "pipeline.translated"  # what went wrong is said, not "no text"
    assert summary(PageResult(image=page, original=page, regions=[])).code == "pipeline.no_content"


@pytest.mark.parametrize("lang", ("ja", "de", "th"))
def test_a_refused_rename_is_said_in_the_windows_language(lang, hidden_root):
    set_language(lang)
    refused = RenameRefused("C:/x is in the way of the cache of 'A'", Message("rename.in_way", path="C:/x", folder="C:/"))
    assert "is in the way" in str(refused)  # the command line's sentence stays
    text = rendered(refused.message)
    assert "C:/x" in text and "in the way" not in text


# ------------------------------------------------------------------ the menus' lines
class Bar(tk.Toplevel):
    def __init__(self, root):
        super().__init__(root)
        self.withdraw()
        self.status_var = tk.StringVar(self, value="the line before")
        self.later = []

    def after(self, ms, func=None, *args):  # kept, run by the test
        self.later.append(func)
        return "after#test"


TIPS = {0: "What one does", 2: "What two does"}


def _menu(window):
    menu = tk.Menu(window, tearoff=0)
    menu.add_command(label="One")
    menu.add_separator()
    menu.add_command(label="Two")
    tip_menu(window, menu, "What one does", "What two does")
    return menu


def _point(window, menu, index):
    menu.activate("none" if index is None else index)
    menu_tip(window, str(menu), TIPS)


def test_a_menu_entry_says_what_it_does_in_the_status_line_and_the_line_comes_back(hidden_root):
    w = Bar(hidden_root)
    menu = _menu(w)
    assert "<<MenuSelect>>" in menu.bind()  # bound before the menu goes on a window: its clone gets it
    _point(w, menu, 0)
    assert w.status_var.get() == "What one does"
    _point(w, menu, 2)  # the separator between them has no tip
    assert w.status_var.get() == "What two does"
    _point(w, menu, None)
    assert w.status_var.get() == "the line before"
    w.destroy()


def test_a_job_speaking_meanwhile_keeps_its_line(hidden_root):
    w = Bar(hidden_root)
    menu = _menu(w)
    _point(w, menu, 0)
    w.status_var.set("Page 3 translated")
    _point(w, menu, None)
    assert w.status_var.get() == "Page 3 translated"
    w.destroy()


# ------------------------------------------------------------------ the empty list, the book's settings
def test_the_saved_translations_say_when_nothing_is_kept(hidden_root, tmp_path):
    d = CachesDialog(hidden_root, CacheStore(tmp_path))
    d.withdraw()
    assert d.empty_var.get() == "Nothing is kept yet."
    d.destroy()


def _book_dialog(hidden_root, current, **settings):
    applied = []
    pipeline = SimpleNamespace(annotations=SimpleNamespace(settings=current), _base_settings=Settings(**settings),
                               set_book_settings=applied.append)
    d = BookSettingsDialog(hidden_root, pipeline, on_change=lambda: None)
    d.withdraw()
    return d, applied


def _texts(top):
    found, stack = [], [top]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        try:
            found.append(str(w.cget("text")))
        except tk.TclError:
            pass
    return found


def test_book_settings_are_three_plain_choices(hidden_root):
    d, applied = _book_dialog(hidden_root, {"white_threshold": 200, "translate_sfx": False})
    assert set(d.choices) == set(CHOICES) == {"detect_text_blocks", "detect_dark_bubbles", "translate_sfx"}
    assert d.choices["translate_sfx"].get() is False and d.choices["detect_text_blocks"].get() is True
    assert d.vars == {} and not any("white_threshold" in t for t in _texts(d))
    d.choices["detect_dark_bubbles"].set(False)
    d._apply()
    assert applied == [{"white_threshold": 200, "translate_sfx": False, "detect_dark_bubbles": False}]  # the number stays


def test_a_choice_as_your_own_setting_is_no_value_of_the_book(hidden_root):
    d, applied = _book_dialog(hidden_root, {})
    d._apply()
    assert applied == [{}]


def test_the_numbers_show_only_with_the_debug_setting(hidden_root):
    d, applied = _book_dialog(hidden_root, {"white_threshold": 200}, debug=True)
    assert "white_threshold" in d.vars and "translate_sfx" not in d.vars
    assert any("white_threshold" == t for t in _texts(d))
    d.vars["white_threshold"].set("")
    d._apply()
    assert applied == [{}]


def test_the_new_help_is_in_the_topics_and_in_every_language():
    keys = [key for heading, paragraphs in TOPICS for key in (heading, *paragraphs)]
    assert "The Translator role" in keys and "Keys" in keys
    for key in keys:
        for code in LANGUAGES:
            assert CATALOGS[code][key].strip(), (code, key)
