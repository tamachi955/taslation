"""Every key TASlation passes on is the person's, at the person's pace: no gap of its own between keys, and none for a
window that is not in front (nothing forces the foreground, so no ALT tap of TASlation's)."""

from __future__ import annotations

from types import SimpleNamespace

from taslation.capture import windows


def setup(monkeypatch, front):
    sleeps, sent = [], []
    monkeypatch.setattr(windows, "user32", SimpleNamespace(GetForegroundWindow=lambda: front))
    monkeypatch.setattr(windows, "_send_key", lambda vk, up: sent.append((vk, up)))
    monkeypatch.setattr(windows.time, "sleep", sleeps.append)
    monkeypatch.setattr(windows, "_require_windows", lambda: None)
    return sleeps, sent


def test_the_persons_keys_come_at_the_persons_pace(monkeypatch):
    sleeps, sent = setup(monkeypatch, 5)
    assert windows.press_key(5, "Left") and windows.press_key(5, "Left")
    assert max(sleeps) < 0.1 and [vk for vk, up in sent if not up] == [0x25, 0x25]
    assert not hasattr(windows, "KEY_GAP_S") and not hasattr(windows, "key_gap_left")


def test_a_window_not_in_front_gets_no_key_and_no_alt_tap(monkeypatch):
    _sleeps, sent = setup(monkeypatch, 9)
    assert not windows.press_key(5, "Left") and sent == []
