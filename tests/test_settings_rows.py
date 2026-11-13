"""Other parts' settings in the Settings dialog, one line each (`settings.EXTRA_ROWS`): every row's words in the 16
languages, a row shown only where `Settings` has its key, a checkbox and a list of choices shown, saved and handed on
as the dialog's own rows are, and the bubble zoom and the whole-book run's flash and sound listed wherever this version has them."""

from __future__ import annotations

import pytest

from taslation.config import Settings
from taslation.i18n import FEATURE_LANGUAGES, _
from taslation.locales.features import settings_dialog as texts
from taslation.ui.dialogs import settings as dlg

OTHER_LANGUAGES = list(FEATURE_LANGUAGES)


@pytest.fixture
def in_force(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", config_path=tmp_path / "taslation.toml")


def _with_rows(monkeypatch, *rows):
    shown = dlg.shown_rows(rows)
    monkeypatch.setattr(dlg, "SHOWN_ROWS", shown)
    monkeypatch.setattr(dlg, "KEYS", (*dlg.KEYS, *(row.key for row in shown)))
    return shown


def test_every_row_s_words_are_in_every_language():
    for row in dlg.EXTRA_ROWS:
        for english in (row.label, row.tip, *(label for _value, label in row.choices)):
            if english:
                assert sorted(texts.TEXTS[english]) == sorted(OTHER_LANGUAGES), english
        assert row.section in ("lettering", "window")


@pytest.mark.parametrize("key", ["bubble_zoom", "flash_when_done", "sound_when_done"])
def test_the_other_parts_settings_are_listed_where_this_version_has_them(key):
    row = next(row for row in dlg.EXTRA_ROWS if row.key == key)
    assert row.section == "window" and not row.page and not row.choices  # a checkbox that leaves the page alone
    assert (key in dlg.KEYS) == (key in dlg.FIELDS)


def test_a_row_whose_setting_this_version_lacks_is_not_shown():
    rows = (dlg.SettingRow("no_such_setting", "Always on top"), dlg.SettingRow("over_book", "Always on top"))
    assert [row.key for row in dlg.shown_rows(rows)] == ["over_book"]


def test_a_checkbox_row_is_shown_saved_and_handed_on(hidden_root, in_force, monkeypatch):
    _with_rows(monkeypatch, dlg.SettingRow("over_book", "Always on top", "Keep this window above the others."))
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.values()["over_book"] is True and d.extra["over_book"].get() is True
    d.extra["over_book"].set(False)
    assert d.save() is True and got == [{"over_book": False}]
    assert Settings.from_toml(in_force.config_path).over_book is False


def test_a_row_of_choices_is_shown_in_the_window_s_language_and_saved_by_value(hidden_root, in_force, monkeypatch):
    _with_rows(monkeypatch, dlg.SettingRow("follow", "A book starts:", choices=(("events", "Page by page"),
                                                                              ("poll", "Whole book first")),
                                           section="lettering", page=True))
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.extra["follow"].get() == _("Page by page") and d.values()["follow"] == "events"
    d.extra["follow"].set(_("Whole book first"))
    assert d.save() is True and got == [{"follow": "poll"}]


def test_a_row_that_changes_the_page_letters_it_again_and_the_others_do_not():
    assert {row.key for row in dlg.SHOWN_ROWS if row.page} <= dlg.PAGE_SETTINGS
    assert not {row.key for row in dlg.SHOWN_ROWS if not row.page} & dlg.PAGE_SETTINGS
