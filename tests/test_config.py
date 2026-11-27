"""Where the settings come from: --config, ./taslation.toml, the state folder's taslation.toml, else the defaults;
`taslation doctor` names the file it read."""
from __future__ import annotations

import pytest

from taslation import cli, config
from taslation.config import ConfigError, Settings


@pytest.fixture
def places(tmp_path, monkeypatch):
    """A working directory, a checkout root and a state folder, all empty."""
    work, root, state = tmp_path / "work", tmp_path / "root", tmp_path / "state"
    for folder in (work, root, state):
        folder.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setattr(config, "REPO_DIR", root)
    monkeypatch.setenv("TASLATION_STATE_DIR", str(state))
    return work, root, state


def _write(folder, model: str, more: str = ""):
    path = folder / "taslation.toml"
    path.write_text(f'ollama_model = "{model}"\n{more}', encoding="utf-8")
    return path


def test_no_file_anywhere_gives_the_defaults(places):
    assert Settings.config_file() is None
    assert Settings.load().ollama_model == Settings().ollama_model
    assert cli._config_line(None) == "none (the defaults)"


def test_the_state_folder_holds_an_installed_programs_file(places):
    _work, _root, state = places
    path = _write(state, "from-state")
    assert Settings.config_file() == path
    assert Settings.load().ollama_model == "from-state"
    assert cli._config_line(None) == str(path)


def test_the_working_directory_comes_before_the_state_folder(places):
    work, root, state = places
    _write(state, "from-state")
    _write(root, "from-checkout")
    assert Settings.load().ollama_model == "from-checkout"  # a checkout's own file, before the state folder's
    path = _write(work, "from-cwd")
    assert Settings.config_file() == path and Settings.load().ollama_model == "from-cwd"


def test_config_comes_first_and_must_exist(places, tmp_path):
    work, _root, state = places
    _write(work, "from-cwd")
    _write(state, "from-state")
    given = tmp_path / "elsewhere.toml"
    given.write_text('ollama_model = "given"\n', encoding="utf-8")
    assert Settings.load(given).ollama_model == "given" and Settings.config_file(given) == given
    with pytest.raises(ConfigError, match="not found"):
        Settings.load(tmp_path / "missing.toml")
    assert "not found" in cli._config_line(tmp_path / "missing.toml")


def test_doctor_names_the_file_it_read(places, capsys, monkeypatch):
    """(doctor looks at Ollama too: at a fake on a port of its own - the file's address -, never at the server on
    Ollama's usual port)"""
    from fake_ollama import FakeOllama

    _work, _root, state = places
    monkeypatch.setattr(cli, "build_translator", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("no Ollama here")))
    with FakeOllama() as server:
        path = _write(state, "qwen3.5:4b", f'ollama_url = "{server.url}"\n')
        try:
            cli.main(["doctor"])
        finally:
            cli.netguard.uninstall()
    out = capsys.readouterr().out
    assert f"Config file: {path}" in out and f"(loopback:{server.port} only;" in out  # (the file's address)


@pytest.mark.parametrize("style", ["chat", "mt", "index"])
def test_a_settings_file_with_the_prompt_style_of_an_older_version_still_loads(tmp_path, style):
    path = tmp_path / "taslation.toml"
    path.write_text(f'ollama_model = "mine:7b"\nollama_prompt_style = "{style}"\n', encoding="utf-8")
    s = Settings.load(path)
    s.validate()
    assert s.ollama_model == "mine:7b" and not hasattr(s, "ollama_prompt_style")


RUN_SETTINGS = {"scan_mode": '"sequential"', "context_mode": '"chunk"', "chunk_bubbles": "12", "lookahead_bubbles": "4",
                "batch_max_pages": "300", "batch_memory_mb": "1024", "flash_when_done": "true",
                "sound_when_done": "false"}


def test_a_settings_file_of_the_whole_book_run_of_earlier_versions_loads_without_a_word(tmp_path):
    path = tmp_path / "taslation.toml"
    path.write_text('ollama_model = "mine:7b"\ncontext_pairs = 6\n'
                    + "".join(f"{key} = {value}\n" for key, value in RUN_SETTINGS.items()), encoding="utf-8")
    s = Settings.load(path)
    s.validate()
    assert s.ollama_model == "mine:7b" and s.context_pairs == 6
    assert s.ignored_keys == ()  # dropped silently: nothing for the window or the command line to tell
    assert not any(hasattr(s, key) for key in RUN_SETTINGS) and set(RUN_SETTINGS) <= config.DROPPED_SETTINGS
