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


@windows_only
def test_key_codes():
    assert capture.windows.key_code("Left") == 0x25
    assert capture.windows.key_code("pagedown") == 0x22
    assert capture.windows.key_code("a") == ord("A")
    with pytest.raises(capture.CaptureError):
        capture.windows.key_code("NoSuchKey")


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
