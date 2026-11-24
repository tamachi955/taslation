"""Other parts' settings in the Settings dialog, one line each (`settings.EXTRA_ROWS`): every row's words in the 16
languages, a row shown only where `Settings` has its key, a checkbox and a list of choices shown, saved and handed on
as the dialog's own rows are, the indicators' row listed and none of the old window's rows."""

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


def test_the_indicators_row_is_listed_and_the_old_windows_rows_are_not():
    key = "see_through_indicators"
    row = next(row for row in dlg.EXTRA_ROWS if row.key == key)
    assert row.section == "window" and not row.page and not row.choices  # a checkbox that leaves the page alone
    assert key in dlg.KEYS and key in dlg.FIELDS
    gone = {"see_through", "bubble_zoom", "hover_shows", "hover_reveal", "side_indicator", "panel_font_size",
            "always_on_top", "over_book"}
    assert not gone & {row.key for row in (*dlg.EXTRA_ROWS, *dlg.NUMBER_ROWS)} and not gone & set(dlg.KEYS)


def test_a_row_whose_setting_this_version_lacks_is_not_shown():
    rows = (dlg.SettingRow("no_such_setting", "Translate sound effects"),
            dlg.SettingRow("over_book", "Translate sound effects"),  # (a setting an older version had)
            dlg.SettingRow("translate_sfx", "Translate sound effects"))
    assert [row.key for row in dlg.shown_rows(rows)] == ["translate_sfx"]


def test_a_checkbox_row_is_shown_saved_and_handed_on(hidden_root, in_force, monkeypatch):
    _with_rows(monkeypatch, dlg.SettingRow("translate_sfx", "Translate sound effects", "Also the sound effects."))
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.values()["translate_sfx"] is True and d.extra["translate_sfx"].get() is True
    d.extra["translate_sfx"].set(False)
    assert d.save() is True and got == [{"translate_sfx": False}]
    assert Settings.from_toml(in_force.config_path).translate_sfx is False


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
