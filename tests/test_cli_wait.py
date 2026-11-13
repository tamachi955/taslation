"""`taslation batch` can be started before the book is open: it waits for the viewer window."""
from __future__ import annotations

import pytest

from taslation import capture as capture_mod
from taslation import cli as cli_mod
from taslation.capture import WindowInfo

WIN = WindowInfo(hwnd=1, title="Yomizuq - Google Chrome", class_name="Chrome_WidgetWin_1", pid=1, rect=(0, 0, 100, 100))


def test_pick_window_waits_for_the_viewer(monkeypatch, capsys):
    calls = {"n": 0}

    def fake_list(include_own=False):
        calls["n"] += 1
        return [WIN] if calls["n"] >= 3 else []

    monkeypatch.setattr(capture_mod, "list_windows", fake_list)
    monkeypatch.setattr(cli_mod, "WINDOW_POLL_S", 0.01)
    assert cli_mod._pick_window("yomizuq", wait=5.0).hwnd == 1
    out = capsys.readouterr().out.lower()
    assert "waiting" in out and "found" in out and calls["n"] == 3


def test_pick_window_gives_up_without_wait(monkeypatch, capsys):
    monkeypatch.setattr(capture_mod, "list_windows", lambda include_own=False: [])
    monkeypatch.setattr(cli_mod, "WINDOW_POLL_S", 0.01)
    with pytest.raises(SystemExit):
        cli_mod._pick_window("yomizuq")
    assert "no window title contains" in capsys.readouterr().out


def test_batch_parser_has_wait():
    parser = cli_mod.build_parser() if hasattr(cli_mod, "build_parser") else None
    if parser is None:
        pytest.skip("no build_parser")
    args = parser.parse_args(["batch", "--window", "Yomizuq"])
    assert args.wait == 600.0
    assert parser.parse_args(["batch", "--window", "Yomizuq", "--wait", "0"]).wait == 0.0
