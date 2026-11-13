"""`taslation glossary` on the command line, and the gui mode/role options."""
from __future__ import annotations

import pytest

from taslation import netguard
from taslation.cli import build_parser, main


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.chdir(tmp_path)
    yield
    netguard.uninstall()


def test_gui_options_parse():
    args = build_parser().parse_args(["gui", "--mode", "page", "--role", "translator"])
    assert args.mode == "page" and args.role == "translator"
    assert build_parser().parse_args(["gui"]).mode is None


def test_glossary_set_show_list_and_delete(capsys):
    assert main(["glossary", "set", "Some Series", "ピーヨ", "Piiyo", "--note", "mascot"]) == 0
    assert main(["glossary", "show", "Some Series"]) == 0
    out = capsys.readouterr().out
    assert "ピーヨ = Piiyo (mascot)" in out
    assert main(["glossary", "list"]) == 0
    assert "Some Series" in capsys.readouterr().out
    assert main(["glossary", "delete", "Some Series", "ピーヨ"]) == 0
    assert "removed" in capsys.readouterr().out


def test_there_is_no_share_command():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["share", "export", "Some Series 1"])


def test_glossary_font_is_kept_in_the_sheet_and_checked_on_this_computer(capsys):
    assert main(["glossary", "font", "Some Series", "No Such Font 12345"]) == 0
    out = capsys.readouterr().out
    assert "Lettering font: No Such Font 12345" in out and "NOT installed" in out
    assert main(["glossary", "show", "Some Series"]) == 0
    assert "Lettering font: No Such Font 12345" in capsys.readouterr().out
    assert main(["glossary", "font", "Some Series"]) == 0
    assert "NOT installed" in capsys.readouterr().out
    assert main(["glossary", "font", "Some Series", "--clear"]) == 0
    assert "no suggested font" in capsys.readouterr().out


def test_glossary_lettering_per_kind(capsys):
    assert main(["glossary", "lettering", "Some Series", "thought"]) == 0
    assert "thought: italic (the built-in style)" in capsys.readouterr().out
    assert main(["glossary", "lettering", "Some Series", "thought", "--no-italic", "--family", "No Such Font 12345"]) == 0
    out = capsys.readouterr().out
    assert "thought: plain, font No Such Font 12345" in out and "NOT installed" in out
    assert main(["glossary", "lettering", "Some Series", "shout", "--italic"]) == 0
    assert "shout: italic bold" in capsys.readouterr().out
    assert main(["glossary", "lettering", "Some Series", "thought", "--reset"]) == 0
    assert "thought: italic (the built-in style)" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["glossary", "lettering", "Some Series", "speech"])
