"""A viewer's window left enlarged by a session of an older version that ended without closing TASlation's window (a
crash, the process ended): the window and its rectangle before are kept in the state folder's ui.json while it is
enlarged, and the next start puts it back - only a window that still exists with the same process and class and still
has the size it was given -, then forgets it. TASlation itself no longer enlarges a viewer: the entries are made by
hand here, as 1.0.1 left them. No key is pressed for it, and Windows' side is a fake."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from taslation import recovery
from taslation.capture import Enlarged, windows
from taslation.capture.windows import restore_window
from taslation.i18n import load_ui_table, save_ui_entry
from taslation.ui import viewers

TABLE = recovery.ENLARGED_TABLE
WORK = (0, 0, 1920, 1040)
SMALL = (100, 100, 900, 756)


@pytest.fixture
def screen(monkeypatch):
    """The windows that exist now: handle -> (process, class); what was put back."""
    s = {"windows": {7: (4100, "ViewerClass")}, "restored": [], "fits": True}
    monkeypatch.setattr(recovery, "window_exists", lambda hwnd: hwnd in s["windows"])
    monkeypatch.setattr(recovery, "window_pid", lambda hwnd: s["windows"].get(hwnd, (0, ""))[0])
    monkeypatch.setattr(recovery, "window_class", lambda hwnd: s["windows"].get(hwnd, (0, ""))[1])
    monkeypatch.setattr(recovery, "restore_window",
                        lambda enlarged: s["fits"] and (s["restored"].append(enlarged) or True))
    return s


def test_an_enlarged_window_is_kept_with_its_process_class_and_rectangles_until_it_is_forgotten(tmp_path, screen):
    recovery.keep_enlarged(tmp_path, Enlarged(7, SMALL, WORK))
    entry = json.loads(load_ui_table(tmp_path, TABLE)["7"])
    assert entry == {"pid": 4100, "class": "ViewerClass", "before": list(SMALL), "given": list(WORK)}
    recovery.forget_enlarged(tmp_path, 7)
    assert load_ui_table(tmp_path, TABLE) == {}
    recovery.forget_enlarged(tmp_path, 9)  # (nothing kept of it: nothing written)
    assert not (tmp_path / "ui.json").exists() or TABLE not in json.loads((tmp_path / "ui.json").read_text("utf-8"))


def test_the_next_start_puts_back_only_the_same_window_still_of_the_size_given_and_then_forgets_all(tmp_path, screen):
    recovery.keep_enlarged(tmp_path, Enlarged(7, SMALL, WORK))
    screen["windows"].update({8: (4200, "ViewerClass"), 9: (4300, "Other"), 10: (4400, "ViewerClass")})
    recovery.keep_enlarged(tmp_path, Enlarged(8, SMALL, WORK))
    recovery.keep_enlarged(tmp_path, Enlarged(9, SMALL, WORK))
    recovery.keep_enlarged(tmp_path, Enlarged(10, SMALL, WORK))
    screen["windows"][8] = (9999, "ViewerClass")  # the handle taken by another process's window since
    screen["windows"][9] = (4300, "Changed")  # ... or by a window of another class
    del screen["windows"][10]  # closed
    save_ui_entry(tmp_path, TABLE, "11", "not json")
    assert recovery.put_back_enlarged(tmp_path) == 1
    assert screen["restored"] == [Enlarged(7, SMALL, WORK)] and load_ui_table(tmp_path, TABLE) == {}
    assert recovery.put_back_enlarged(tmp_path) == 0  # once only


def test_a_window_the_person_resized_since_stays_as_it_is(tmp_path, screen):
    recovery.keep_enlarged(tmp_path, Enlarged(7, SMALL, WORK))
    screen["fits"] = False  # `capture.restore_window`: not of the size given any more
    assert recovery.put_back_enlarged(tmp_path) == 0 and load_ui_table(tmp_path, TABLE) == {}


class User32:
    """Only what putting a window back may call: a call that would touch the foreground, the order of the windows or
    a key is not here, and fails."""

    def __init__(self):
        self.zoomed = False

    def IsZoomed(self, hwnd):
        return self.zoomed


def test_only_a_window_of_the_size_it_was_given_is_put_back(monkeypatch):
    user32, place = User32(), {"rect": WORK}

    def move(hwnd, rect):
        place["rect"] = rect
        return True

    monkeypatch.setattr(windows, "user32", user32, raising=False)
    monkeypatch.setattr(windows, "window_shown", lambda hwnd: True)
    monkeypatch.setattr(windows, "window_rect", lambda hwnd: place["rect"])
    monkeypatch.setattr(windows, "move_window", move)
    enlarged = Enlarged(7, SMALL, WORK)
    assert restore_window(enlarged) and place["rect"] == SMALL  # back
    place["rect"] = (0, 0, 1200, 800)  # the reader made it smaller
    assert not restore_window(enlarged) and place["rect"] == (0, 0, 1200, 800)
    place["rect"] = (300, 0, 2220, 1040)  # moved, same size: put back
    assert restore_window(enlarged) and place["rect"] == SMALL
    place["rect"] = WORK
    user32.zoomed = True  # the reader maximised it
    assert not restore_window(enlarged)
    user32.zoomed = False
    monkeypatch.setattr(windows, "window_shown", lambda hwnd: False)  # closed or minimised
    assert not restore_window(enlarged)


def test_a_size_the_window_clamped_is_the_size_it_kept():
    enlarged = Enlarged(7, SMALL, WORK)
    enlarged.given = (0, 0, 800, 656)
    assert not enlarged.changed  # the same size: a window of a fixed size
    enlarged.given = (0, 0, 1920, 1000)
    assert enlarged.changed and enlarged.has_its_size((5, 5, 1925, 1005))


def test_a_start_after_an_older_session_that_did_not_close_puts_the_viewer_back(tmp_path, screen, monkeypatch):
    monkeypatch.setattr(viewers, "put_back_enlarged", recovery.put_back_enlarged)  # (conftest makes it a no-op)
    recovery.keep_enlarged(tmp_path, Enlarged(7, SMALL, WORK))  # ... and that session ended here
    later = SimpleNamespace(settings=SimpleNamespace(state_dir=tmp_path))
    viewers.ViewerMixin._put_back_left_enlarged(later)
    assert [e.hwnd for e in screen["restored"]] == [7] and load_ui_table(tmp_path, TABLE) == {}
