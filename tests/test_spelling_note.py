"""The spellcheck setting is off by default, as its word lists come from the optional pyspellchecker package, which
TASlation does not install; a settings file that turns it on keeps it on. Where the package is missing then, the
region editor says so once (ui.json), in words a person can act on without a command line, and nothing is fetched."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from taslation import review as checks
from taslation.config import Settings
from taslation.i18n import CATALOGS, load_ui_flag
from taslation.pipeline import manual_region
from taslation.ui import app as app_mod
from taslation.ui import translator
from taslation.ui.dialogs import review

EXAMPLE = Path(__file__).resolve().parents[1] / "taslation.toml.example"


def _window(tmp_path, **settings):
    values = {"spellcheck": True, "target_language": "English", "state_dir": tmp_path}
    values.update(settings)
    return SimpleNamespace(settings=SimpleNamespace(**values))


def _note(w):
    return app_mod.App._spelling_note(w)


def test_the_spellcheck_is_off_by_default_and_a_settings_file_that_turns_it_on_keeps_it_on(tmp_path):
    assert Settings().spellcheck is False
    assert Settings.from_toml(EXAMPLE).spellcheck is False  # the example states the default
    path = tmp_path / "taslation.toml"
    path.write_text("spellcheck = true\n", encoding="utf-8")
    loaded = Settings.from_toml(path)
    assert loaded.spellcheck is True and loaded.changed_from_defaults() == {"spellcheck": True}
    path.write_text("[taslation]\nspellcheck = true\n", encoding="utf-8")  # in the table too
    assert Settings.from_toml(path).spellcheck is True


def test_with_the_default_nothing_is_said_even_without_the_package(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "spell_checker", lambda language: None)  # the package is not installed
    w = SimpleNamespace(settings=Settings(state_dir=tmp_path, target_language="English"))
    assert _note(w) == "" and not load_ui_flag(tmp_path, translator.SPELLING_SAID)


def test_the_editor_says_once_that_spelling_is_not_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "spell_checker", lambda language: None)  # the package is not installed
    w = _window(tmp_path)
    assert _note(w) == translator.SPELLING_OFF and load_ui_flag(tmp_path, translator.SPELLING_SAID)
    assert _note(w) == ""  # said once
    assert _note(_window(tmp_path)) == ""  # and not after a restart either


def test_a_settings_file_that_turns_it_on_gets_the_line_once(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "spell_checker", lambda language: None)
    path = tmp_path / "taslation.toml"
    path.write_text("spellcheck = true\n", encoding="utf-8")
    settings = Settings.from_toml(path)
    settings.state_dir = tmp_path
    w = SimpleNamespace(settings=settings)
    assert _note(w) == translator.SPELLING_OFF and _note(w) == ""


def test_the_line_says_what_to_do_without_a_command_line():
    line = translator.SPELLING_OFF
    assert "pip" not in line and "pyspellchecker" not in line  # nothing a person without Python could run
    assert "not install" in line and "open Settings..." in line and "Open settings file" in line
    assert "spellcheck = false" in line


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
            text = catalog[translator.SPELLING_OFF]
            assert "pip" not in text and "pyspellchecker" not in text, code
            assert "spellcheck = true" in text and "spellcheck = false" in text, code
            assert catalog["Open settings file"] in text, code  # the button as the window names it
