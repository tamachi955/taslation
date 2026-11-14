"""--language at the command line with a language whose translator model is not installed: the same offer as the
window's (`cli.ensure_translator`), at the console: the size, the room freed, PLaMo's licence first, a model the
person had asked about on its own; no console to ask, or a no, and the command translates nothing."""

from __future__ import annotations

import io
import sys
from types import SimpleNamespace

import pytest

from taslation import cli, health
from taslation import translator_install as ti
from taslation.translate.models import PLAMO, QWEN


class Console(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def console(monkeypatch, tmp_path):
    """Ollama's models (``.models``), the console's answers in order (``.answers``), the installs run (``.runs``) and
    the models removed (``.removed``)."""
    seen = SimpleNamespace(models=[], answers=[], asked=[], runs=[], removed=[], outcome="done")
    monkeypatch.setattr(health, "installed_models", lambda url, timeout=1.0: seen.models)
    monkeypatch.setattr(sys, "stdin", Console())

    def answer(question=""):
        seen.asked.append(question)
        return seen.answers.pop(0) if seen.answers else ""

    monkeypatch.setattr("builtins.input", answer)

    class Installer:
        def __init__(self, language, models_dir, state_dir, url=None, on_progress=None, where="window", **_k):
            self.language, self.where, self.on_progress = language, where, on_progress

        def run(self):
            seen.runs.append((self.language, self.where))
            self.on_progress({"phase": "download", "done": 5, "total": 10})
            return ti.Outcome(seen.outcome)

        def cancel(self):
            pass

    monkeypatch.setattr(ti, "Installer", Installer)
    monkeypatch.setattr(ti, "find_ollama", lambda: "ollama.exe")
    monkeypatch.setattr(ti, "remove_model", lambda exe, name, state_dir, url=None: seen.removed.append(name) or True)
    seen.settings = SimpleNamespace(ollama_model="auto", state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                                    ollama_url="http://127.0.0.1:11434")
    return seen


def test_turkish_with_taslation_s_plamo_downloads_qwen_and_frees_plamo(console, capsys):
    console.models = [PLAMO.ollama_name + ":latest"]
    console.answers = ["y"]
    assert cli.ensure_translator(console.settings, "Turkish")
    out = capsys.readouterr().out
    assert "needs the translation model Qwen3.5 4B, which is not installed: about 3.3 GB to download." in out
    assert "PLaMo 3 Translate 2B is not needed for Turkish and is then removed, which frees about 1.8 GB." in out
    assert console.runs == [("Turkish", "console")] and console.removed == [PLAMO.ollama_name + ":latest"]
    assert "download:  50 %" in out


def test_english_asks_the_licence_and_keeps_the_person_s_qwen_on_enter(console, capsys):
    console.models = [QWEN.ollama_name]
    console.answers = ["y", "y", ""]
    assert cli.ensure_translator(console.settings, "English")
    out = capsys.readouterr().out
    assert "PLaMo Community License" in out and "article 5" in out
    assert console.asked[1].startswith("Do you agree to the PLaMo Community License?")
    assert "before TASlation installed anything" in console.asked[2]
    assert console.removed == [] and ti.has_agreed(console.settings.state_dir)


def test_a_no_translates_nothing_and_says_how(console, capsys):
    console.answers = ["n"]
    assert not cli.ensure_translator(console.settings, "English")
    assert console.runs == [] and "Translation is off: English needs PLaMo 3 Translate 2B" in capsys.readouterr().out


def test_no_console_is_a_no(console, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert not cli.ensure_translator(console.settings, "English")
    assert "n (no console to ask)" in capsys.readouterr().out and console.runs == []


def test_a_stopped_install_translates_nothing(console, capsys):
    console.answers = ["y", "y"]
    console.outcome = "cancelled"
    assert not cli.ensure_translator(console.settings, "French")
    assert "Stopped. Nothing was left on the disk." in capsys.readouterr().out and console.removed == []


def test_a_refused_file_says_trying_again_will_not_help(console, capsys):
    console.answers = ["y", "y"]
    console.outcome = "refused"
    assert not cli.ensure_translator(console.settings, "French")
    out = capsys.readouterr().out
    assert "refused the download or no longer has this file. Trying again will not help: update TASlation" in out
    assert "Translation is off: French needs PLaMo 3 Translate 2B, which is not installed." in out
    assert "Run the command again" not in out and "Check the network" not in out


def test_a_model_that_is_there_asks_nothing(console):
    console.models = [PLAMO.ollama_name + ":latest"]
    assert cli.ensure_translator(console.settings, "German") and console.asked == []


def test_the_command_does_not_run_after_a_no(console, monkeypatch, tmp_path):
    ran = []
    monkeypatch.setitem(cli.COMMANDS, "translate", lambda args, settings: ran.append(args) or 0)
    monkeypatch.setattr(cli.netguard, "install", lambda port: None)
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "state"))
    console.answers = ["n"]
    assert cli.main(["--language", "Turkish", "translate", str(tmp_path / "page.png")]) == 1 and ran == []
    console.models = [QWEN.ollama_name]
    assert cli.main(["--language", "Turkish", "translate", str(tmp_path / "page.png")]) == 0 and len(ran) == 1
