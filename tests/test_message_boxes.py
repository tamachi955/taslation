"""TASlation's own message boxes in place of Windows' (`ui.dialogs.caches.ask` and `tell`): buttons in the window's
language that say what they do, above everything (a full-screen viewer too), the foreground back to the viewer when
it had it; a warning nobody asked for goes to the status line and the page while the reader reads, never into a box
over the book. No module of the window uses tkinter's message boxes any more."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from taslation.i18n import set_language
from taslation.ui import jobs
from taslation.ui.dialogs import caches

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def answered(monkeypatch):
    """Every box made is kept, never waited for on the screen; *press*: the button each one gets ("go", "stay")."""
    made: list[caches.WarningBox] = []
    press = ["go"]

    class Box(caches.WarningBox):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.withdraw()
            made.append(self)
            self.topmost: list[tuple] = []
            self.seen = dict(title=self.title(), text=self.message_text, buttons=_packed(self),
                             icon=[str(n) for n in self.icon.cget("image")], default=str(self.continue_btn.cget("default")))
            self.after(30, (self.continue_btn if press[0] == "go" else self.cancel_btn).invoke)

        def attributes(self, *a):
            self.topmost.append(a)
            return super().attributes(*a)

    monkeypatch.setattr(caches, "WarningBox", Box)
    return SimpleNamespace(made=made, press=press)


def _packed(box: caches.WarningBox) -> list[str]:
    return [str(b.cget("text")) for b in box.continue_btn.master.pack_slaves()]


def test_ask_names_its_buttons_and_says_what_was_chosen(hidden_root, answered, monkeypatch):
    monkeypatch.setattr(caches, "foreground_window", lambda: 0)
    assert caches.ask(hidden_root, "Delete the saved translations of Book?", "Delete", "Keep them") is True
    box = answered.made[-1]
    assert box.seen["title"] == "TASlation" and box.seen["text"].startswith("Delete the saved")
    assert box.seen["buttons"] == ["Keep them", "Delete"]  # (packed from the right: Keep them on the right)
    assert ("-topmost", True) in box.topmost  # above a full-screen viewer too
    assert box.seen["icon"] == ["::tk::icons::question"]
    answered.press[0] = "stay"
    assert caches.ask(hidden_root, "Change it now?", "Change it now", "Not now") is False
    assert caches.ask(hidden_root, "Go on?") is False and answered.made[-1].seen["buttons"] == ["Cancel", "Continue"]


def test_tell_has_one_ok_in_the_window_s_language(hidden_root, answered, monkeypatch):
    monkeypatch.setattr(caches, "foreground_window", lambda: 0)
    set_language("ja")
    caches.tell(hidden_root, "x")
    box = answered.made[-1]
    assert box.seen["buttons"] == ["OK"] and box.seen["default"] == "active"
    assert caches.ask(hidden_root, "y") is True and answered.made[-1].seen["buttons"] == ["キャンセル", "続ける"]
    caches.tell(hidden_root, "z", icon="info")
    assert answered.made[-1].seen["icon"] == ["::tk::icons::information"]


def test_the_viewer_that_had_the_foreground_gets_it_back(hidden_root, answered, monkeypatch):
    given: list[int] = []
    monkeypatch.setattr(caches, "give_foreground", lambda hwnd: given.append(hwnd) or True)
    monkeypatch.setattr(caches, "foreground_window", lambda: 77)
    hidden_root.selected = SimpleNamespace(hwnd=77)  # the viewer chosen in the window, in front
    try:
        caches.tell(hidden_root, "A warning nobody asked for.")
        box = answered.made[-1]
        assert len(given) == 2 and given[-1] == 77  # the box in front, then the viewer again
        given.clear()
        hidden_root.selected = SimpleNamespace(hwnd=5)  # another window in front: nothing given back
        caches.tell(hidden_root, "Asked for.")
        assert 5 not in given and 77 not in given
    finally:
        del hidden_root.selected


@pytest.mark.parametrize("state", ["reading", "over", "window"])
def test_a_warning_nobody_asked_for_never_comes_up_over_the_book(state, monkeypatch):
    told: list[tuple[str, bool]] = []
    monkeypatch.setattr(caches, "tell", lambda _parent, text, wait=True, **_k: told.append((text, wait)))
    notes: list[tuple[str, int]] = []
    w = SimpleNamespace(reading=state == "reading", _over_on=state == "over", statuses=[],
                        canvas=SimpleNamespace(set_note=lambda text, ms=0: notes.append((text, ms))))
    w.status = w.statuses.append
    jobs.JobsMixin._warn_unasked(w, "The model runs partly on the CPU.")
    if state == "window":
        assert told == [("The model runs partly on the CPU.", False)] and not w.statuses  # a box the window goes on past
    else:
        assert not told and w.statuses == ["The model runs partly on the CPU."]
        assert notes == ([] if state == "reading" else [("The model runs partly on the CPU.", jobs.WARNING_NOTE_MS)])


def test_no_part_of_the_window_uses_tkinter_s_message_boxes():
    calls = re.compile(r"messagebox\.(show|ask)\w*\(|from tkinter import [^\n]*messagebox|import tkinter\.messagebox")
    used = [str(p.relative_to(ROOT)) for p in (ROOT / "taslation").rglob("*.py") if calls.search(p.read_text("utf-8"))]
    assert used == []
