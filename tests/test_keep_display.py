"""The display and the PC stay on while the window is open, and go back to normal when it closes."""

import pytest

from taslation.ui import app as app_mod


class FakeApp:
    quit_before_start = False
    fail = False

    def __init__(self, *args, **kwargs):
        pass

    def mainloop(self):
        calls.append("mainloop")
        if self.fail:
            raise RuntimeError("the window fell over")

    def destroy(self):
        calls.append("destroy")


calls: list = []


@pytest.fixture(autouse=True)
def stand_ins(monkeypatch):
    calls.clear()
    monkeypatch.setattr(app_mod, "App", FakeApp)
    monkeypatch.setattr(app_mod, "keep_awake", lambda display: calls.append(("awake", display)))
    monkeypatch.setattr(app_mod, "release_awake", lambda: calls.append("release"))


def test_the_display_stays_on_for_as_long_as_the_window_is_open():
    assert app_mod.run_app(None) == 0
    assert calls == [("awake", True), "mainloop", "release"]


def test_it_is_released_when_the_window_fails(monkeypatch):
    monkeypatch.setattr(FakeApp, "fail", True)
    with pytest.raises(RuntimeError):
        app_mod.run_app(None)
    assert calls[-1] == "release"


def test_quitting_at_the_legal_notice_asks_for_nothing(monkeypatch):
    monkeypatch.setattr(FakeApp, "quit_before_start", True)
    assert app_mod.run_app(None) == 0
    assert calls == ["destroy"]
