"""The spellcheck setting is on by default, but its word lists come from the optional pyspellchecker package: where
it is missing, the region editor says so once (ui.json), and nothing is fetched."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from taslation import review as checks
from taslation.i18n import CATALOGS, load_ui_flag
from taslation.pipeline import manual_region
from taslation.ui import app as app_mod
from taslation.ui import translator
from taslation.ui.dialogs import review


def _window(tmp_path, **settings):
    values = {"spellcheck": True, "target_language": "English", "state_dir": tmp_path}
    values.update(settings)
    return SimpleNamespace(settings=SimpleNamespace(**values))


def _note(w):
    return app_mod.App._spelling_note(w)


def test_the_editor_says_once_that_spelling_is_not_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "spell_checker", lambda language: None)  # the package is not installed
    w = _window(tmp_path)
    assert _note(w) == translator.SPELLING_OFF and load_ui_flag(tmp_path, translator.SPELLING_SAID)
    assert _note(w) == ""  # said once
    assert _note(_window(tmp_path)) == ""  # and not after a restart either


def test_nothing_is_said_where_spelling_is_checked_or_not_asked_for(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "spell_checker", lambda language: object())  # installed
    assert _note(_window(tmp_path)) == ""
    monkeypatch.setattr(checks, "spell_checker", lambda language: None)
    assert _note(_window(tmp_path, spellcheck=False)) == ""
    assert _note(_window(tmp_path, target_language="Thai")) == ""  # no word list for it anyway
    assert _note(_window(tmp_path, target_language="")) == ""
    assert not load_ui_flag(tmp_path, translator.SPELLING_SAID)  # nothing said, nothing kept


def test_the_editor_shows_the_note_under_its_header(hidden_root):
    region = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    region.status, region.translated_text = "translated", "Nice weather today, huh?"
    d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None,
                                note=translator.SPELLING_OFF)
    assert d.note_label is not None and d.note_label.cget("text") == translator.SPELLING_OFF
    d.destroy()
    d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None)
    assert d.note_label is None
    d.destroy()


def test_the_note_is_in_every_language():
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert translator.SPELLING_OFF in catalog, code
