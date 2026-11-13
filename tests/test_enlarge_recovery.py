"""A viewer's window left enlarged by a session that ended without closing TASlation's window (a crash, the process
ended): the window and its rectangle before are kept in the state folder's ui.json while it is enlarged, and the next
start puts it back - only a window that still exists with the same process and class and still has the size it was
given -, then forgets it. No key is pressed for it, and Windows' side is a fake."""
from __future__ import annotations

import json

import pytest
from test_enlarge import SMALL, WORK, Win, desk  # noqa: F401 - desk is test_enlarge's fixture

from taslation import recovery
from taslation.capture import Enlarged
from taslation.i18n import load_ui_table, save_ui_entry
from taslation.ui import viewers

TABLE = recovery.ENLARGED_TABLE


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


@pytest.fixture
def kept(monkeypatch, screen):
    """The window's real keeping, onto the stand-in's state folder (conftest makes it a no-op elsewhere)."""
    monkeypatch.setattr(viewers, "keep_enlarged", recovery.keep_enlarged)
    monkeypatch.setattr(viewers, "forget_enlarged", recovery.forget_enlarged)
    monkeypatch.setattr(viewers, "put_back_enlarged", recovery.put_back_enlarged)
    return screen


def test_the_window_keeps_the_enlarged_viewer_while_it_is_large_and_forgets_it_once_put_back(hidden_root, tmp_path,
                                                                                            desk, kept):
    w = Win(hidden_root, tmp_path)
    state = w.settings.state_dir
    w._enlarge_first()
    assert json.loads(load_ui_table(state, TABLE)["7"])["before"] == list(SMALL)  # kept as it is enlarged
    w.run_later()
    assert json.loads(load_ui_table(state, TABLE)["7"])["given"] == list(WORK)  # the size it took
    w._restore_enlarged()
    assert load_ui_table(state, TABLE) == {}


def test_a_start_after_a_session_that_did_not_close_puts_the_viewer_back(hidden_root, tmp_path, desk, kept,
                                                                         monkeypatch):
    monkeypatch.setattr(Win, "_put_back_left_enlarged", viewers.ViewerMixin._put_back_left_enlarged, raising=False)
    crashed = Win(hidden_root, tmp_path)
    crashed._enlarge_first()
    crashed.run_later()  # ... and the session ends here, without closing the window
    later = Win(hidden_root, tmp_path)
    later._put_back_left_enlarged()
    assert [e.hwnd for e in kept["restored"]] == [7] and load_ui_table(later.settings.state_dir, TABLE) == {}
