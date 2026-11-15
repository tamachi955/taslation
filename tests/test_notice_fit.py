"""The legal notice on a small screen (1366 x 768 at 125 %, say): its text box only as tall as the work area leaves
room for, the choosers above it and the buttons below it whole, the window inside the work area at the start and from
the Help menu alike. The layout is a sum (`fitted_lines`); the dialog is measured on the hidden root with the work
area made small, never shown on the real screen at that place."""

from __future__ import annotations

import re

import pytest

from taslation import notice
from taslation.ui import layout
from taslation.ui.dialogs import notice as notice_dlg

BIG = (0, 0, 4000, 3000)


def test_the_box_keeps_its_lines_while_the_dialog_fits():
    assert notice_dlg.fitted_lines(31, 700, 20, 900) == 31
    assert notice_dlg.fitted_lines(31, 708, 20, 708) == 31  # exactly as tall as the work area


def test_on_a_small_screen_the_box_loses_as_many_lines_as_the_dialog_is_too_tall():
    # 1366 x 768 at 125 %: a work area some 708 pixels tall, a line of the window's font some 20 pixels; the dialog
    # with 31 lines some 840 pixels tall with its title bar: 132 too tall, so 7 lines fewer, and then it fits
    lines = notice_dlg.fitted_lines(31, 840, 20, 708)
    assert lines == 24 and 840 - (31 - lines) * 20 <= 708
    assert notice_dlg.fitted_lines(31, 709, 20, 708) == 30  # a pixel too tall is a line fewer
    # never fewer than FEWEST_LINES (the box scrolls), nor more than it had
    assert notice_dlg.fitted_lines(31, 3000, 20, 400) == notice_dlg.FEWEST_LINES
    assert notice_dlg.fitted_lines(5, 3000, 20, 400) == 5
    assert notice_dlg.fitted_lines(31, 840, 0, 708) == notice_dlg.FEWEST_LINES  # a line of no height: no division


def _work_area(monkeypatch, area):
    """The work area of every monitor made *area* (what `place_window` and the dialog look at)."""
    monkeypatch.setattr(notice_dlg, "work_area", lambda widget, x=None, y=None: area)
    monkeypatch.setattr(layout, "work_area", lambda widget, x=None, y=None: area)


def _outer(d) -> tuple[int, int, int, int]:
    """The dialog's place and size on the screen with its title bar and borders: left, top, width, height."""
    d.update_idletasks()
    border, caption = layout.frame_extents()
    m = re.search(r"\+(-?\d+)\+(-?\d+)$", d.wm_geometry())
    x, y = int(m.group(1)), int(m.group(2))
    return x, y, d.winfo_reqwidth() + 2 * border, d.winfo_reqheight() + caption + border


@pytest.mark.parametrize("startup", [True, False])
def test_the_dialog_fits_a_small_work_area_and_stays_inside_it(tmp_path, monkeypatch, hidden_root, startup):
    monkeypatch.setattr(notice, "default_country", lambda: None)
    _work_area(monkeypatch, BIG)
    roomy = notice_dlg.NoticeDialog(hidden_root, tmp_path, "en", startup=startup)
    roomy.withdraw()
    assert int(roomy.text.cget("height")) == notice_dlg.TEXT_LINES
    _x, _y, _w, tall = _outer(roomy)
    roomy.destroy()
    line = int(notice_dlg.tkfont.nametofont("TkDefaultFont").metrics("linespace"))
    small = (100, 40, 1466, 40 + tall - 5 * line - 3)  # 5 lines and a bit too short for the dialog, off the origin
    _work_area(monkeypatch, small)
    d = notice_dlg.NoticeDialog(hidden_root, tmp_path, "en", startup=startup)
    d.withdraw()
    assert int(d.text.cget("height")) == notice_dlg.TEXT_LINES - 6
    x, y, width, height = _outer(d)
    left, top, right, bottom = small
    assert height <= bottom - top  # the whole dialog, its buttons at the bottom included, fits the work area ...
    if startup:  # ... and lies in it (from the Help menu over the hidden root it is placed over nothing)
        assert left <= x and x + width <= right and top <= y and y + height <= bottom, (x, y, width, height)
    for widget in (d.ok_btn, d.leave_btn, d.never_box, d.country_box, d.language_box):
        assert widget.winfo_manager()  # every control still there
    d.destroy()
