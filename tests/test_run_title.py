"""The window's title while a job runs says what is done: a whole-book run's reading pass reads (nothing is translated
yet), then the lines translated; a page's job and a page-by-page run translate."""

from __future__ import annotations

import pytest

from taslation.i18n import CATALOGS, set_language
from taslation.message_texts import LANGUAGES
from taslation.ui.banner import ScanState, busy_title

READING, TRANSLATING = "TASlation - reading...", "TASlation - translating..."


@pytest.mark.parametrize("phase, title", [("", READING), ("read", READING), ("translate", TRANSLATING),
                                          ("done", TRANSLATING)])
def test_a_whole_book_run_names_its_pass(phase, title):
    assert busy_title(ScanState(context=True, phase=phase)) == title


def test_a_page_job_and_a_page_by_page_run_translate():
    assert busy_title(None) == TRANSLATING
    assert busy_title(ScanState(context=False, phase="read")) == TRANSLATING


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_language_has_the_titles(lang):
    assert CATALOGS[lang][READING].startswith("TASlation - ") and CATALOGS[lang][READING] != CATALOGS[lang][TRANSLATING]
    set_language(lang)
    try:
        assert busy_title(ScanState(context=True, phase="read")) == CATALOGS[lang][READING]
    finally:
        set_language("en")
