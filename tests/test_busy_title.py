"""The window's title while a job runs: it says that TASlation is translating, in the window's language."""

from __future__ import annotations

import pytest

from taslation.i18n import CATALOGS, set_language
from taslation.message_texts import LANGUAGES
from taslation.ui.banner import busy_title

TRANSLATING = "TASlation - translating..."


def test_a_job_translates():
    assert busy_title() == TRANSLATING


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_language_has_the_title(lang):
    assert CATALOGS[lang][TRANSLATING].startswith("TASlation - ") and CATALOGS[lang][TRANSLATING] != TRANSLATING
    set_language(lang)
    try:
        assert busy_title() == CATALOGS[lang][TRANSLATING]
    finally:
        set_language("en")