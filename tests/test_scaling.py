"""The size of the window's text: the monitor's DPI times the reader's UI scale, at the start and again when the window
moves to a monitor of another DPI. Everything stays on the shared hidden root, whose scaling is put back after each
test."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from types import SimpleNamespace

import pytest

from taslation.config import ConfigError, Settings
from taslation.ui import scaling
from taslation.ui.scaling import DpiWatch, apply_scale, clamp_scale

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def scaled_root(hidden_root, monkeypatch):
    """The hidden root, its scaling as it was put back afterwards (other tests measure in it)."""
    before = float(hidden_root.tk.call("tk", "scaling"))
    monkeypatch.setattr(scaling, "window_dpi", lambda widget: None)  # (a hidden root's monitor: whatever it is)
    yield hidden_root
    hidden_root.tk.call("tk", "scaling", before)
    scaling.refresh_fonts(hidden_root)


def _zero(root) -> int:
    return tkfont.nametofont("TkDefaultFont", root).measure("0" * 20)


def test_the_ui_scale_makes_the_text_larger_and_back(scaled_root):
    base = scaling.base_dpi(scaled_root)
    assert apply_scale(scaled_root, 1.0) == pytest.approx(base / 72.0)
    usual = _zero(scaled_root)
    label = tk.Label(scaled_root, text="0" * 20, font="TkDefaultFont")
    label.update_idletasks()
    width = label.winfo_reqwidth()
    assert apply_scale(scaled_root, 2.0) == pytest.approx(2 * base / 72.0)
    assert _zero(scaled_root) == pytest.approx(2 * usual, rel=0.15)  # a font sized in points follows ...
    label.update_idletasks()
    assert label.winfo_reqwidth() > 1.6 * width  # ... and the widget that uses it is laid out anew
    assert scaling.base_dpi(scaled_root) == base  # Tk's inch follows the scaling; the start's DPI is kept
    apply_scale(scaled_root, 1.0)
    assert _zero(scaled_root) == pytest.approx(usual, rel=0.05)
    label.destroy()


def test_the_monitors_dpi_comes_first(scaled_root):
    assert apply_scale(scaled_root, 1.0, dpi=144) == pytest.approx(2.0)
    assert apply_scale(scaled_root, 1.25, dpi=96) == pytest.approx(96 / 72 * 1.25)


def test_a_move_to_another_monitor_scales_again_once(scaled_root, monkeypatch):
    dpi = {"now": 96}
    monkeypatch.setattr(scaling, "window_dpi", lambda widget: dpi["now"])
    seen = []
    watch = DpiWatch(scaled_root, lambda: 1.5, on_change=seen.append)
    assert watch.dpi == 96
    assert watch.check() is False and seen == []  # the same monitor: nothing
    dpi["now"] = 144
    assert watch.check() is True and seen == [144]
    assert float(scaled_root.tk.call("tk", "scaling")) == pytest.approx(144 / 72 * 1.5, rel=0.01)  # (Tk keeps it to its own precision)
    assert watch.check() is False and seen == [144]
    dpi["now"] = None  # (the window not on the screen): nothing changes
    assert watch.check() is False


def test_the_check_waits_for_the_moves_to_stop(scaled_root, monkeypatch):
    watch = DpiWatch(scaled_root, lambda: 1.0)
    planned = []
    monkeypatch.setattr(scaled_root, "after", lambda ms, func: planned.append((ms, func)) or f"job{len(planned)}")
    monkeypatch.setattr(scaled_root, "after_cancel", lambda job: planned.append(("cancel", job)))
    child = tk.Frame(scaled_root)
    watch._moved(SimpleNamespace(widget=child))  # a child laid out is no move
    assert planned == []
    watch._moved(SimpleNamespace(widget=scaled_root))
    watch._moved(SimpleNamespace(widget=scaled_root))
    assert planned[0][0] == scaling.CHECK_MS and planned[1] == ("cancel", "job1") and planned[2][0] == scaling.CHECK_MS
    child.destroy()


def test_the_setting_has_bounds():
    assert Settings().ui_scale == 1.0
    Settings(ui_scale=2.0).validate()
    for bad in (0.2, 3.5):
        with pytest.raises(ConfigError, match="ui_scale"):
            Settings(ui_scale=bad).validate()
    assert clamp_scale("x") == 1.0 and clamp_scale(9) == 3.0 and clamp_scale(0.1) == 0.5
    assert clamp_scale(float("nan")) == 1.0
    assert all(0.5 <= s <= 3.0 for s in scaling.UI_SCALES) and 1.0 in scaling.UI_SCALES
    example = Settings.from_toml(ROOT / "taslation.toml.example")
    assert example.ui_scale == 1.0


def test_the_window_applies_the_scale_before_it_measures_and_watches_the_monitor():
    source = (ROOT / "taslation" / "ui" / "app.py").read_text(encoding="utf-8")
    assert source.index("apply_scale(self, settings.ui_scale)") < source.index("initial_geometry(self)")
    assert "DpiWatch(self" in source
    assert '"tk", "scaling", self.winfo_fpixels' not in source  # (the old one-off scaling, from the start's DPI)
