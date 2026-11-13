"""A reader who is elsewhere is told when a whole-book run ends (`taslation.ui.attention`): the taskbar button
flashes (on by default) and the system's sound plays (off by default) when the run finished or stopped with a
problem while no window of TASlation's is in front - never for a run the reader stopped, never with focus taken."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_start_flow import Flow

from taslation.config import Settings
from taslation.messages import Message
from taslation.ui import attention

FINISHED = Message("batch.finished", pages=3, bubbles=12, seconds=40.0, minutes=1, failed=0, error="",
                   reason=Message("batch.finished_reading"))
FAILED = Message("batch.failed_requests", failed=2, reason=Message("batch.reply_unusable"), pages=3, seconds=1.0)
STOPPED = Message("batch.stopped_translating", done=3, total=9, pages=3, seconds=1.0, kept=1, again=0)


def test_what_is_worth_telling():
    assert attention.worth_telling(FINISHED) and attention.worth_telling(FAILED)
    assert attention.worth_telling(Message("batch.not_started", reason=Message("batch.no_page_seen")))
    assert attention.worth_telling(Message("batch.finished", pages=3, bubbles=0, seconds=1.0, minutes=1, failed=0,
                                           error="", reason=Message("batch.save_failed", error="disk full")))
    for code in ("batch.stopped", "batch.stopped_reading", "batch.stopped_translating"):
        assert not attention.worth_telling(Message(code))  # the reader stopped it: they are there
    assert not attention.worth_telling(None) and not attention.worth_telling("ended")


@pytest.fixture
def told(monkeypatch):
    calls = []
    monkeypatch.setattr(attention, "in_front", lambda hwnd: False)
    monkeypatch.setattr(attention, "flash", lambda hwnd: calls.append(("flash", hwnd)) or True)
    monkeypatch.setattr(attention, "beep", lambda: calls.append(("sound",)) or True)
    return calls


def _window(**settings):
    return SimpleNamespace(settings=Settings(**settings), _own_hwnd=lambda: 4711)


def test_the_flash_is_on_and_the_sound_off_by_default(told):
    assert Settings().flash_when_done and not Settings().sound_when_done
    example = Settings.from_toml(Path(__file__).resolve().parent.parent / "taslation.toml.example")
    assert example.flash_when_done and not example.sound_when_done
    assert attention.tell_run_ended(_window(), FINISHED) == ("flash",) and told == [("flash", 4711)]
    told.clear()
    assert attention.tell_run_ended(_window(sound_when_done=True), FAILED) == ("flash", "sound")
    assert told == [("flash", 4711), ("sound",)]
    told.clear()
    assert attention.tell_run_ended(_window(flash_when_done=False), FINISHED) == () and told == []
    assert attention.tell_run_ended(_window(sound_when_done=True), STOPPED) == () and told == []


def test_nothing_is_told_while_tasl_is_in_front(told, monkeypatch):
    monkeypatch.setattr(attention, "in_front", lambda hwnd: True)
    assert attention.tell_run_ended(_window(sound_when_done=True), FINISHED) == () and told == []


def test_the_end_of_a_run_in_the_window_tells(hidden_root, tmp_path, told):
    flow = Flow(hidden_root, tmp_path)
    flow._own_hwnd = lambda: 99
    flow._handle_event("batch_done", {"progress": SimpleNamespace(summary=FINISHED, reason="")})
    assert told == [("flash", 99)]
    told.clear()
    flow._handle_event("batch_done", {"progress": SimpleNamespace(summary=STOPPED, reason="")})
    assert told == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' FlashWindowEx")
def test_the_real_calls_never_raise(hidden_root):
    hidden_root.update_idletasks()
    assert isinstance(attention.in_front(None), bool)
    assert attention.flash(0) is False  # no window: nothing asked
    # a withdrawn test window has no taskbar button: the call is taken, nothing shows, no focus moves
    assert attention.flash(int(hidden_root.wm_frame(), 16)) is True
