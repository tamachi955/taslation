from __future__ import annotations

import tkinter as tk

import numpy as np
import pytest
from conftest import windows_only

from taslation import capture


@windows_only
def test_list_and_find_windows():
    wins = capture.list_windows(include_own=True)
    assert isinstance(wins, list)
    for w in wins:
        assert w.title and w.width > 0 and w.height > 0
    if wins:  # another window of the same title, or starting the same, makes them several (find_window: none)
        assert wins[0] in capture.match_windows(wins[0].title, wins)
        assert capture.match_windows(wins[0].title[:5].lower(), wins)
        named = capture.match_windows(wins[0].title, wins)
        assert capture.find_window(wins[0].title, wins) == (wins[0] if len(named) == 1 else None)
    assert capture.find_window("", wins) is None and capture.match_windows("", wins) == []


@windows_only
def test_capture_a_tk_window_by_handle(tk_root):
    import time

    root = tk.Toplevel(tk_root)  # its own window handle; a second Tk root in the process is what fails now and then
    try:
        root.geometry("320x240+200+200")
        root.configure(bg="#ff0000")
        root.update()
        hwnd = root.winfo_id()
        arr = None
        for _ in range(40):  # the window may not be painted yet (white), or another app may be stealing the foreground
            root.update()
            img = capture.capture_window(hwnd, allow_screen_fallback=False)
            arr = np.asarray(img)
            if arr.shape[0] > 100 and arr[..., 0].mean() > 200 and arr[..., 1].mean() < 60:
                break
            time.sleep(0.1)
        assert arr is not None and arr.shape[2] == 3 and arr.shape[0] > 100 and arr.shape[1] > 100
        assert arr[..., 0].mean() > 200 and arr[..., 1].mean() < 60 and arr[..., 2].mean() < 60
        x, y, w, h = capture.client_rect_on_screen(hwnd)
        assert w == arr.shape[1] and h == arr.shape[0]
        shot = capture.capture_screen_rect(x, y, w, h)
        assert shot.size == (w, h)
    finally:
        root.destroy()


def test_a_flat_frame_is_blank():
    from PIL import Image

    assert capture.is_blank(Image.new("RGB", (640, 480), (0, 0, 0)))
    assert capture.is_blank(Image.new("RGB", (640, 480), (250, 250, 250)))
    page = np.full((480, 640, 3), 255, np.uint8)
    page[100:300, 200:260] = 20  # some ink
    assert not capture.is_blank(Image.fromarray(page))


def test_a_copy_of_the_screen_never_reads_taslation_own_windows():
    viewer = (100, 100, 1300, 1000)  # left, top, right, bottom
    assert capture.rects_overlap(viewer, (0, 0, 1920, 1040))  # TASlation maximised over it
    assert capture.rects_overlap(viewer, (1299, 999, 1400, 1100))  # one pixel in common
    assert not capture.rects_overlap(viewer, (1300, 100, 1900, 1000))  # side by side: right and bottom are exclusive
    assert not capture.rects_overlap(viewer, (100, 1000, 1300, 1200))
    assert capture.screen_shows_own(viewer, [(1400, 0, 1900, 500), (500, 500, 700, 700)])  # a dialog of ours over it
    assert not capture.screen_shows_own(viewer, [(1400, 0, 1900, 500)])
    assert not capture.screen_shows_own(viewer, [(-32000, -32000, -31840, -31972)])  # minimised: parked off screen
    assert not capture.screen_shows_own(viewer, [(200, 200, 200, 900)])  # an empty rectangle
    assert not capture.screen_shows_own(viewer, [])


def test_another_window_over_the_viewer_is_seen_but_no_overlay_or_hidden_one(monkeypatch):
    """`behind_others`: a window above the viewer in the order of the windows that covers part of it, never one that
    is hidden, minimised or lets the clicks through (the see-through window's own bars, a tooltip's shadow)."""
    from types import SimpleNamespace

    from taslation.capture import windows

    above = {1: 2, 2: 3, 3: 4, 4: 0}
    state = {2: (False, False, 0, (0, 0, 2000, 2000)), 3: (True, True, 0, (0, 0, 2000, 2000)),
             4: (True, False, 0x20, (0, 0, 2000, 2000))}  # hidden, minimised, click-through
    fake = SimpleNamespace(IsWindow=lambda h: True, GetAncestor=lambda h, f: h, GetWindow=lambda h, f: above[h],
                           IsWindowVisible=lambda h: state[h][0], IsIconic=lambda h: state[h][1],
                           GetWindowLongW=lambda h, i: state[h][2])
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "user32", fake, raising=False)
    monkeypatch.setattr(windows, "GWL_EXSTYLE", -20, raising=False)
    monkeypatch.setattr(windows, "client_rect_on_screen", lambda hwnd: (100, 100, 800, 600))
    monkeypatch.setattr(windows, "_is_cloaked", lambda hwnd: False)
    monkeypatch.setattr(windows, "_window_rect", lambda hwnd: state[hwnd][3])
    assert not windows.behind_others(1)
    state[3] = (True, False, 0, (950, 0, 1000, 50))  # on the screen, beside the viewer
    assert not windows.behind_others(1)
    state[3] = (True, False, 0, (850, 0, 1000, 150))  # over a corner of it
    assert windows.behind_others(1)


@windows_only
def test_the_rectangle_of_a_tk_window_takes_in_its_client_area(tk_root):
    top = tk.Toplevel(tk_root)
    try:
        top.geometry("320x240+200+200")
        top.update()
        left, upper, right, lower = capture.window_rect(top.winfo_id())  # its top-level window's, frame included
        x, y, w, h = capture.client_rect_on_screen(top.winfo_id())
        assert left <= x and upper <= y and right >= x + w and lower >= y + h
        assert capture.screen_shows_own((x, y, x + w, y + h), [(left, upper, right, lower)])
    finally:
        top.destroy()
