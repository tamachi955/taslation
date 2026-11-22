"""A command given a window title that matches no window lists the windows that can be captured and ends."""
from __future__ import annotations

import pytest

from taslation import capture as capture_mod
from taslation import cli as cli_mod


def test_pick_window_with_no_match_lists_the_windows_and_ends(monkeypatch, capsys):
    monkeypatch.setattr(capture_mod, "list_windows", lambda include_own=False: [])
    with pytest.raises(SystemExit) as ended:
        cli_mod._pick_window("yomizuq")
    assert ended.value.code == 2 and "no window title contains" in capsys.readouterr().out
