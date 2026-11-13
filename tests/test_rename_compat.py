"""What still works from the SelfTrans days: the old state folder is carried over, the old environment variables
are read, an export with the old first line still imports, and the window's title carries the expansion."""
from pathlib import Path

import pytest

from taslation import backup, config
from taslation.ui import constants


def test_old_environment_variables_are_still_read(monkeypatch, tmp_path):
    for name in ("TASLATION_MODELS_DIR", "SELFTRANS_MODELS_DIR", "TASLATION_STATE_DIR", "SELFTRANS_STATE_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SELFTRANS_MODELS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("SELFTRANS_STATE_DIR", str(tmp_path / "s"))
    assert config.default_models_dir() == tmp_path / "m" and config.default_state_dir() == tmp_path / "s"
    monkeypatch.setenv("TASLATION_MODELS_DIR", str(tmp_path / "m2"))  # the new name wins
    monkeypatch.setenv("TASLATION_STATE_DIR", str(tmp_path / "s2"))
    assert config.default_models_dir() == tmp_path / "m2" and config.default_state_dir() == tmp_path / "s2"


def test_the_old_state_folder_is_carried_over_once(monkeypatch, tmp_path):
    for name in ("TASLATION_STATE_DIR", "SELFTRANS_STATE_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    old = tmp_path / ".selftrans"
    (old / "cache").mkdir(parents=True)
    (old / "cache" / "x.json").write_text("{}", encoding="utf-8")
    assert config.default_state_dir() == tmp_path / ".taslation"
    assert not old.exists() and (tmp_path / ".taslation" / "cache" / "x.json").is_file()
    assert config.default_state_dir() == tmp_path / ".taslation"  # and stays
    (tmp_path / ".selftrans").mkdir()  # with the new folder present, an older one is left alone
    assert config.default_state_dir() == tmp_path / ".taslation" and (tmp_path / ".selftrans").is_dir()


def test_an_export_with_the_old_first_line_still_imports():
    pytest.importorskip("cryptography")
    passphrase = "a passphrase of twelve"
    payload = b'{"pages": []}'
    blob = backup.encrypt(payload, passphrase)
    assert blob.startswith(backup.MAGIC + b"\n")
    old = b"SELFTRANS-CACHE-1" + blob[len(backup.MAGIC):]
    assert backup.decrypt(old, passphrase) == payload
    with pytest.raises(backup.BackupError):
        backup.decrypt(b"OTHER-CACHE-1" + blob[len(backup.MAGIC):], passphrase)


def test_the_title_carries_the_expansion():
    assert constants.APP_TITLE == "TASlation - Tool Assisting Self-translation"
    root = Path(__file__).resolve().parents[1] / "taslation" / "ui"
    assert "self.title(APP_TITLE)" in (root / "app.py").read_text(encoding="utf-8")
    assert "self.title(APP_TITLE)" in (root / "status.py").read_text(encoding="utf-8")
