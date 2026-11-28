"""tools/screens_read.py, the developer's reading of kept screens: which pictures it takes and in what order, the
margins it takes from a measuring session's page file (those alone), what it refuses (beside another TASlation too),
and its watch. No model."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import screens_read  # noqa: E402


def _picture(path: Path, size=(64, 48)) -> Path:
    Image.new("RGB", size, "white").save(path)
    return path


def test_a_folder_s_pictures_are_taken_by_name_and_picked_by_their_first_number_in_the_order_given(tmp_path):
    for n in (3, 12, 7):
        _picture(tmp_path / f"p{n:04d}-frame.png")
        _picture(tmp_path / f"p{n:04d}-lettered.png")
    (tmp_path / "p0003.json").write_text("{}", encoding="utf-8")
    frames = screens_read.screens_of([str(tmp_path)], "p*-frame.png", [])
    assert [p.name for p in frames] == ["p0003-frame.png", "p0007-frame.png", "p0012-frame.png"]
    picked = screens_read.screens_of([str(tmp_path)], "p*-frame.png", [12, 3])
    assert [screens_read.number_of(p) for p in picked] == [12, 3]
    with pytest.raises(SystemExit, match=r"no picture numbered \[5\]"):
        screens_read.screens_of([str(tmp_path)], "p*-frame.png", [5])
    single = screens_read.screens_of([str(tmp_path / "p0007-frame.png")], "*.png", [])
    assert [p.name for p in single] == ["p0007-frame.png"]
    with pytest.raises(SystemExit, match="no such folder or picture: the 1. given"):  # (its name never said)
        screens_read.screens_of([str(tmp_path / "secret-name.png")], "*.png", [])
    assert screens_read.number_of(Path("frame.png")) == -1


def test_the_margins_come_from_the_page_file_beside_and_nothing_else_of_it(tmp_path):
    frame = _picture(tmp_path / "p0005-frame.png")
    (tmp_path / "p0005.json").write_text(json.dumps({"analysis": {"margins": [0, 85, 0, 0], "size": [1920, 1032]},
                                                     "regions": [{"text": "x"}]}), encoding="utf-8")
    assert screens_read.margins_beside(frame) == (0, 85, 0, 0)
    other = _picture(tmp_path / "p0006-frame.png")
    assert screens_read.margins_beside(other) is None  # (no file)
    (tmp_path / "p0006.json").write_text(json.dumps({"analysis": {"margins": ["a", 1, 2, 3]}}), encoding="utf-8")
    assert screens_read.margins_beside(other) is None  # (not four numbers)
    assert screens_read.margins_arg("1,2,3,4") == (1, 2, 3, 4) and screens_read.margins_arg("beside") == "beside"
    assert screens_read.margins_arg("") is None
    with pytest.raises(Exception):
        screens_read.margins_arg("1,2,3")


def test_it_never_uses_ollama_s_usual_port_nor_the_program_s_state_folder(tmp_path, monkeypatch):
    picture = str(_picture(tmp_path / "s.png"))
    with pytest.raises(SystemExit, match="usual port"):
        screens_read.main([picture, "--port", "11434"])
    with pytest.raises(SystemExit, match="one translator"):
        screens_read.main([picture])
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(SystemExit, match="never the program's own"):
        screens_read.main([picture, "--canned", "10", "--state", str(tmp_path / ".taslation" / "x")])
    assert not (tmp_path / ".taslation").exists()


def test_it_does_not_start_beside_another_taslation(tmp_path, monkeypatch, capsys):
    import standin_viewer as sv

    picture = str(_picture(tmp_path / "s.png"))
    monkeypatch.setattr(sv, "command_lines", lambda: [(4242, "pythonw.exe -m taslation gui")])  # (a person's window)
    monkeypatch.setattr(sv, "processes", lambda: [])
    assert screens_read.main([picture, "--canned", "10", "--state", str(tmp_path / "state")]) == sv.REFUSED
    assert not (tmp_path / "state").exists() and "4242" in capsys.readouterr().err  # (nothing made, nothing started)


@pytest.mark.parametrize("mode", ["compare", "same"])
def test_the_watch_looks_at_the_screen_on_show_and_the_window_s_own_look_compares_it_once(mode):
    rgb = np.random.default_rng(1).integers(0, 256, (120, 160, 3), dtype=np.uint8)
    watch = screens_read.Watch(mode, 200.0)
    with watch:
        watch.show(rgb, (0, 10, 0, 0))
        deadline = time.monotonic() + 5
        while watch.looks < 5 and time.monotonic() < deadline:
            time.sleep(0.01)
    assert watch.looks >= 5 and len(watch.sets) == 1
    if mode == "same":
        counts = watch._window.counts
        assert counts["compares"] == 1 and counts["same"] == watch.looks - 1  # (the same bytes each look)
