"""The Settings dialog (Tools > Settings...) and the settings file it writes: the writer keeps the file's notes and
other lines, a new file is the example with every setting a note, the keys this version does not know are named once
(by name only), what Save and Open settings file do, and how the window applies what was saved. Dialogs on the shared
hidden root, never mapped where it can be helped."""

from __future__ import annotations

import re
import tkinter as tk
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from taslation import cli
from taslation.config import (NEW_FILE_HEADER, ConfigError, Settings, create_settings_file, edit_settings_text,
                              new_settings_text, setting_names, settings_file, toml_value, write_settings)
from taslation.i18n import _, set_language
from taslation.pipeline import Pipeline
from taslation.render import artwork
from taslation.ui import app as app_mod
from taslation.ui.dialogs import settings as dlg
from taslation.ui.dialogs.caches import ERROR_COLOUR

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "taslation.toml.example"


# ------------------------------------------------------------------ the writer
def test_a_setting_s_own_line_takes_the_new_value_and_keeps_its_note_where_it_was():
    text = 'ollama_model = "mine"  # mine\nmin_font_size = 9         # the smallest\n'
    out = edit_settings_text(text, {"min_font_size": 14}).splitlines()
    assert out[0] == 'ollama_model = "mine"  # mine'
    assert out[1].startswith("min_font_size = 14 ") and out[1].endswith("# the smallest")
    assert out[1].index("#") == text.splitlines()[1].index("#")


def test_a_setting_that_is_a_note_becomes_the_setting_and_a_missing_one_goes_at_the_end_of_the_settings():
    text = 'ollama_model = "mine"\n# min_font_size = 9   # note\n\n[other]\nx = 1\n'
    out = edit_settings_text(text, {"min_font_size": 14, "uppercase": True})
    lines = out.splitlines()
    assert lines[1].startswith("min_font_size = 14") and lines[1].endswith("# note")
    assert lines[2] == "uppercase = true" and lines[3] == "" and lines[4] == "[other]"
    assert tomllib.loads(out) == {"ollama_model": "mine", "min_font_size": 14, "uppercase": True, "other": {"x": 1}}


def test_a_file_with_a_taslation_table_is_written_in_that_table():
    text = '[taslation]\nmin_font_size = 9 # n\n\n[other]\nmin_font_size = 5\n'
    data = tomllib.loads(edit_settings_text(text, {"min_font_size": 14, "uppercase": True}))
    assert data == {"taslation": {"min_font_size": 14, "uppercase": True}, "other": {"min_font_size": 5}}


def test_strings_with_quotes_and_hashes_and_arrays_are_written_as_toml():
    text = 'target_language = "a#b"   # c\nmargins = [0, 0, 0, 0]  # m\n'
    out = edit_settings_text(text, {"target_language": 'x"y #z', "margins": (1, 2, 3, 4)})
    assert tomllib.loads(out) == {"target_language": 'x"y #z', "margins": [1, 2, 3, 4]}
    assert out.splitlines()[0].endswith("# c") and out.splitlines()[1].endswith("# m")
    assert [toml_value(v) for v in (True, 3, 1.25, 2.0, "日本", [1, 2])] == [
        "true", "3", "1.25", "2.0", '"日本"', "[1, 2]"]


def test_write_settings_changes_the_lines_of_its_settings_alone(tmp_path):
    path = tmp_path / "taslation.toml"
    before = EXAMPLE.read_text(encoding="utf-8")
    path.write_text(before, encoding="utf-8")
    values = {"min_font_size": 10, "uppercase": True, "ui_scale": 1.25, "scan_mode": "book", "always_on_top": True,
              "detect_model": "on", "art_erase": "lama"}
    assert write_settings(path, values) == path
    old, new = before.splitlines(), path.read_text(encoding="utf-8").splitlines()
    assert len(old) == len(new)
    differ = [(a, b) for a, b in zip(old, new) if a != b]
    assert {b.split("=")[0].strip() for _a, b in differ} == set(values)
    for a, b in differ:
        if "#" in a:
            assert b.split("#", 1)[1] == a.split("#", 1)[1]  # the note stays
    loaded = Settings.from_toml(path)
    assert {key: getattr(loaded, key) for key in values} == values and loaded.ignored_keys == ()


def test_write_settings_refuses_what_does_not_fit_and_leaves_the_file_as_it_was(tmp_path):
    path = tmp_path / "taslation.toml"
    path.write_text("# mine\nmin_font_size = 9\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        write_settings(path, {"no_such_setting": 1})
    with pytest.raises(ConfigError):
        write_settings(path, {"min_font_size": 30, "max_font_size": 20})
    with pytest.raises(ConfigError):
        write_settings(path, {"ui_scale": 9.0})
    assert path.read_text(encoding="utf-8") == "# mine\nmin_font_size = 9\n"


def test_a_file_with_windows_line_ends_keeps_them(tmp_path):
    path = tmp_path / "taslation.toml"
    path.write_bytes(b"# mine\r\nmin_font_size = 9\r\n")
    write_settings(path, {"min_font_size": 10, "uppercase": True})
    assert path.read_bytes() == b"# mine\r\nmin_font_size = 10\r\nuppercase = true\r\n"


# ------------------------------------------------------------------ a new file
def test_a_new_file_is_the_example_with_every_setting_a_note(tmp_path):
    path = tmp_path / "state" / "taslation.toml"
    assert create_settings_file(path, EXAMPLE) is True
    text = path.read_text(encoding="utf-8")
    assert text.startswith(NEW_FILE_HEADER)
    assert tomllib.loads(text) == {}  # nothing is held at a default
    active = [line for line in EXAMPLE.read_text(encoding="utf-8").splitlines() if re.match(r"^[a-z_]+ *=", line)]
    assert len(active) > 40 and all("# " + line in text.splitlines() for line in active)
    loaded = Settings.from_toml(path)
    assert loaded.changed_from_defaults() == {} and loaded.ignored_keys == ()
    path.write_text("min_font_size = 12\n", encoding="utf-8")
    assert create_settings_file(path, EXAMPLE) is False  # an existing file is never replaced
    assert path.read_text(encoding="utf-8") == "min_font_size = 12\n"
    assert new_settings_text(tmp_path / "no example") == NEW_FILE_HEADER


def test_the_example_names_every_setting_of_the_dialog_and_no_key_this_version_does_not_know():
    keys = set(re.findall(r"^([a-z_]+) *=", EXAMPLE.read_text(encoding="utf-8"), re.M))
    assert set(dlg.KEYS) <= keys and keys <= setting_names()


def test_the_settings_file_is_the_one_read_else_the_one_found_else_in_the_state_folder(tmp_path, monkeypatch):
    read = tmp_path / "read.toml"
    assert settings_file(Settings(state_dir=tmp_path, config_path=read)) == read
    found = tmp_path / "found.toml"
    monkeypatch.setattr(Settings, "config_file", staticmethod(lambda *a, **k: found))
    assert settings_file(Settings(state_dir=tmp_path)) == found
    monkeypatch.setattr(Settings, "config_file", staticmethod(lambda *a, **k: None))
    assert settings_file(Settings(state_dir=tmp_path / "state")) == tmp_path / "state" / "taslation.toml"


# ------------------------------------------------------------------ the keys this version does not know
def test_unknown_keys_are_named_once_by_name_alone(tmp_path, hidden_root):
    path = tmp_path / "taslation.toml"
    path.write_text('b_key = "a title of mine"\na_key = 1\nmin_font_size = 10\n', encoding="utf-8")
    settings = Settings.from_toml(path).with_overrides(state_dir=tmp_path / "state")
    assert settings.ignored_keys == ("a_key", "b_key") and settings.min_font_size == 10
    told = []

    def tell(master, text, **kw):
        told.append((text, kw))

    assert dlg.warn_ignored(hidden_root, settings, tell) is True
    assert told == [("TASlation does not know these settings in taslation.toml and leaves them out: a_key, b_key. "
                     "Tools > Settings... opens the file.", {"icon": "info", "wait": False})]
    assert "a title of mine" not in told[0][0]
    assert dlg.warn_ignored(hidden_root, settings, tell) is False and len(told) == 1  # (the next start too)
    other = settings.with_overrides(ignored_keys=("c_key",))
    assert dlg.warn_ignored(hidden_root, other, tell) is True and "c_key" in told[-1][0]
    assert dlg.warn_ignored(hidden_root, Settings(state_dir=tmp_path), tell) is False
    set_language("ja")
    assert "ツール > 設定..." in dlg.ignored_note(settings) and "a_key, b_key" in dlg.ignored_note(settings)


def test_the_command_line_names_unknown_keys_and_not_their_values(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    path = tmp_path / "taslation.toml"
    path.write_text('no_such = "a title of mine"\n', encoding="utf-8")
    settings = cli.load_settings(cli.build_parser().parse_args(["--config", str(path), "doctor"]))
    err = capsys.readouterr().err
    assert settings.ignored_keys == ("no_such",)
    assert "no_such" in err and "a title of mine" not in err


def test_always_on_top_in_the_file_starts_the_window_on_top(tmp_path, monkeypatch):
    import taslation.capture as capture_mod

    started = []
    monkeypatch.setattr(capture_mod, "enable_dpi_awareness", lambda: None)
    monkeypatch.setattr(app_mod, "run_app", lambda settings, **kw: started.append(kw["on_top"]) or 0)
    args = cli.build_parser().parse_args(["gui"])
    cli.cmd_gui(args, Settings(state_dir=tmp_path, always_on_top=True))
    cli.cmd_gui(args, Settings(state_dir=tmp_path))
    assert started == [True, False]


# ------------------------------------------------------------------ the dialog
@pytest.fixture
def in_force(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", config_path=tmp_path / "taslation.toml")


def test_the_dialog_shows_the_settings_in_force(hidden_root, in_force):
    in_force.art_erase = "lama"
    d = dlg.SettingsDialog(hidden_root, in_force)
    assert d.title() == "Settings" and d.resizable() == (False, False)
    assert d.values() == {key: getattr(in_force, key) for key in dlg.KEYS}  # (lama stays lama)
    assert d.path == in_force.config_path and d.path_field.get() == str(in_force.config_path)
    assert d.models_line == "Not installed on this computer: run install.cmd again and agree to them."
    assert d.scale.get() == "100 %" and dlg.scale_of("125 %") == 1.25 and dlg.scale_label(1.75) == "175 %"
    assert d.terms_label.winfo_manager() == ""  # page by page: no note on a store's terms
    d.mode.set("book")
    d._show_terms()
    assert d.terms_label.winfo_manager() == "grid" and str(d.terms_label.cget("text"))


def test_save_writes_what_changed_and_hands_it_on(hidden_root, in_force):
    got = []

    def saved(changed):
        got.append(changed)
        for key, value in changed.items():  # as App._settings_saved does
            setattr(in_force, key, value)

    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=saved)
    d.sizes["min_font_size"].set("10")
    d.uppercase.set(True)
    d.mode.set("book")
    d.on_top.set(True)
    d.detect.set(_("Always used"))
    assert d.save() is True
    changed = {"min_font_size": 10, "uppercase": True, "scan_mode": "book", "always_on_top": True,
               "detect_model": "on"}
    assert got == [changed] and d.message_var.get() == "Saved. The changes apply now."
    text = in_force.config_path.read_text(encoding="utf-8")
    assert text.startswith(NEW_FILE_HEADER) and '# ollama_url = "http://127.0.0.1:11434"' in text
    loaded = Settings.from_toml(in_force.config_path)
    assert {key: getattr(loaded, key) for key in changed} == changed
    assert d.save() is True and d.message_var.get() == "Nothing changed." and len(got) == 1
    d.scale.set("125 %")
    assert d.save() is True and got[-1] == {"ui_scale": 1.25}
    assert d.message_var.get().replace("\n", " ") == (
        "Saved. The changes apply now. The new text size shows in full after a restart.")


@pytest.mark.parametrize("low, high, readable", [("30", "20", "0"), ("3", "20", "0"), ("9", "64", "70"),
                                                  ("x", "64", "11")])
def test_save_refuses_sizes_that_do_not_fit_together(hidden_root, in_force, low, high, readable):
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    for key, value in zip(dlg.SIZE_KEYS, (low, high, readable)):
        d.sizes[key].set(value)
    assert d.save() is False and got == [] and not in_force.config_path.exists()
    assert d.message_var.get().replace("\n", " ") == dlg.size_problem(-1, -1, -1)
    assert str(d.message_label.cget("foreground")) == ERROR_COLOUR


def test_open_settings_file_makes_the_file_first_and_opens_it(hidden_root, in_force, monkeypatch):
    opened = []
    monkeypatch.setattr(dlg, "open_in_editor", opened.append)
    d = dlg.SettingsDialog(hidden_root, in_force)
    assert d.open_file() == in_force.config_path and opened == [in_force.config_path]
    assert in_force.config_path.read_text(encoding="utf-8").startswith(NEW_FILE_HEADER)
    assert d.message_var.get().replace("\n", " ") == (
        'The file was made: every setting in it is a note until you delete its "#".')
    assert d.open_file() == in_force.config_path and len(opened) == 2
    assert d.message_var.get() == "Changes made in the file apply at the next start."

    def refused(path):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(dlg, "open_in_editor", refused)
    assert d.open_file() is None and d.message_var.get() == "Could not open the file: Access is denied"


def test_the_dialog_in_japanese(hidden_root, in_force):
    set_language("ja")
    d = dlg.SettingsDialog(hidden_root, in_force)
    assert d.title() == "設定" and d.detect.get() == "使わない"
    d.detect.set(_("Always used"))
    d.erase.set(_("Always, also on the CPU"))
    assert d.values()["detect_model"] == "on" and d.values()["art_erase"] == "lama"
    assert d.erase.get() == "いつも使う（CPU でも）"


@pytest.mark.parametrize("value", ["off", "auto", "lama"])
def test_the_inpainting_s_three_choices_come_back_as_they_were_saved(hidden_root, in_force, value):
    got = []
    in_force.art_erase = "off" if value != "off" else "lama"
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    d.erase.set(_(dict(dlg.ERASE_CHOICES)[value]))
    assert d.values()["art_erase"] == value and d.save() is True and got == [{"art_erase": value}]
    loaded = Settings.from_toml(in_force.config_path)
    assert loaded.art_erase == value
    again = dlg.SettingsDialog(hidden_root, loaded)
    assert again.erase.get() == _(dict(dlg.ERASE_CHOICES)[value]) and again.values()["art_erase"] == value
    assert again.changed() == {}


def test_the_inpainting_row_says_when_this_computer_has_no_gpu(hidden_root, in_force, monkeypatch):
    assert in_force.art_erase == "auto"  # the default: only with a GPU (the suite's computer has none)
    d = dlg.SettingsDialog(hidden_root, in_force)
    assert d.erase.get() == "Only with a GPU" and d.gpu_line_shown() and d.gpu_label.winfo_manager() == "grid"
    assert str(d.gpu_label.cget("text")).replace("\n", " ") == dlg.NO_GPU_TEXT
    d.erase.set(_("Always, also on the CPU"))
    assert not d.gpu_line_shown() and d.gpu_label.winfo_manager() == ""
    d.erase.set(_("Not used"))
    assert d.gpu_label.winfo_manager() == ""
    monkeypatch.setattr(artwork, "_cuda", True)  # a computer with a GPU: nothing to say
    d.erase.set(_("Only with a GPU"))
    assert not d.gpu_line_shown() and d.gpu_label.winfo_manager() == ""
    assert dlg.SettingsDialog(hidden_root, in_force).gpu_label.winfo_manager() == ""


# ------------------------------------------------------------------ the window
def _window(hidden_root, tmp_path):
    done = []
    w = SimpleNamespace(
        settings=Settings(state_dir=tmp_path), top_var=tk.BooleanVar(hidden_root, value=False),
        _apply_on_top=lambda: done.append("on top"), _dpi_watch=SimpleNamespace(rescale=lambda: done.append("scale")),
        _jobs=SimpleNamespace(put=lambda job: done.append(("job", job))), _job_settings_changed="rebuild",
        last_result=SimpleNamespace(original="the page"), busy=False, batch=None,
        _start_translate=lambda original, complete=False: done.append(("again", original, complete)))
    return w, done


def test_saved_settings_are_set_on_the_window_and_applied_at_once(hidden_root, tmp_path):
    w, done = _window(hidden_root, tmp_path)
    app_mod.App._settings_saved(w, {"always_on_top": True, "ui_scale": 1.25, "uppercase": True})
    assert w.settings.always_on_top and w.settings.ui_scale == 1.25 and w.settings.uppercase and w.top_var.get()
    assert done == ["on top", "scale", ("job", "rebuild"), ("again", "the page", True)]
    done.clear()
    app_mod.App._settings_saved(w, {"scan_mode": "book"})  # nothing on the page changes
    assert w.settings.scan_mode == "book" and done == []
    w.busy = True
    app_mod.App._settings_saved(w, {"detect_model": "on"})
    assert done == [("job", "rebuild")]  # a page under way: the next one is made with the new models


def test_the_worker_makes_the_page_models_for_the_new_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(artwork, "available", lambda models_dir, setting="auto", cuda=None: setting != "off")
    settings = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", art_erase="off")
    pipeline = Pipeline(settings, translator=None, cache=None)
    assert pipeline.art_eraser is None
    warmed = []
    w = SimpleNamespace(pipeline=pipeline, _warm_page_models=lambda: warmed.append(True))
    settings.art_erase = "lama"  # as App._settings_saved sets it: the pipeline shares the window's settings
    app_mod.App._job_settings_changed(w)
    assert pipeline.art_eraser is not None and warmed == [True] and len(pipeline.shown_pages) == 0
    app_mod.App._job_settings_changed(SimpleNamespace(pipeline=None))  # no pipeline yet: nothing to do


def test_tools_settings_opens_one_dialog(tmp_path, monkeypatch):
    made = []

    def dialog(master, settings, on_saved=None, keymap=None, on_keys=None, pipeline=None):
        made.append((on_saved, keymap, on_keys, pipeline().stage_times))
        return SimpleNamespace(winfo_exists=lambda: True, lift=lambda: made.append("lift"))

    monkeypatch.setattr(app_mod, "SettingsDialog", dialog)
    w = SimpleNamespace(settings=Settings(state_dir=tmp_path), _settings_saved="saved", keymap="keys",
                        _shortcuts_saved="keys saved", pipeline=SimpleNamespace(stage_times="times"))
    app_mod.App.open_settings(w)
    app_mod.App.open_settings(w)
    assert made == [("saved", "keys", "keys saved", "times"), "lift"]  # the System page reads the window's pipeline


def test_the_window_names_unknown_keys_once_no_dialog_holds_it(tmp_path, monkeypatch):
    held = [True]
    later, said = [], []
    monkeypatch.setattr(app_mod, "modal_up", lambda w: held[0])
    monkeypatch.setattr(app_mod, "warn_ignored", lambda master, settings, tell: said.append(tell))
    w = SimpleNamespace(settings=Settings(state_dir=tmp_path), reading=False, after=lambda ms, fn: later.append(ms))
    w._warn_ignored = lambda: app_mod.App._warn_ignored(w)
    app_mod.App._warn_ignored(w)
    assert later == [app_mod.FIRST_STEPS_RETRY_MS] and said == []
    held[0] = False
    app_mod.App._warn_ignored(w)
    assert said == [app_mod.boxes.tell]
