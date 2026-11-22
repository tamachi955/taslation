"""The text an input method is composing, shown in the box it goes into (`ui.ime`): what Windows' IME gives read
as text, the clause being converted and the cursor; the picture over the box with the keys, at its caret, and gone
when the composition ends or the box loses the keys; nothing written into the box meanwhile (the start dialog's
fields and the name they make stay as they were, nothing answered); the IME's own window given the picture's place
and the box's font; every text box of the window and of its dialogs, once per interpreter; the window's keys never
run in a dialog's boxes. On withdrawn windows of the shared hidden root only, with what the IME says stood in for
(Windows itself is only asked, for a window that is not shown, what is composed there): no window is shown, no key
is sent, no real window is touched. Invented titles only."""
from __future__ import annotations

import inspect
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest
from conftest import windows_only

from taslation.ui import app as app_mod
from taslation.ui import ime, theme
from taslation.ui.book_fields import BookFields
from taslation.ui.dialogs.start import StartDialog

FOCUS = 1234  # the window with the keys, as the stand-in says


def utf16(text: str) -> bytes:
    return text.encode("utf-16-le")


def _event(widget) -> SimpleNamespace:
    return SimpleNamespace(widget=widget)


class FakeIme:
    """What Windows and its IME say, stood in for: the window with the keys (*FOCUS*), what is being composed there,
    and what the window told the IME's own window."""

    def __init__(self, monkeypatch):
        self.composition: ime.Composition | None = None
        self.focus = FOCUS
        self.placed: list[tuple[int, int, int]] = []
        self.fonts: list[tuple[int, tuple]] = []
        monkeypatch.setattr(ime, "focus_in_window", lambda widget: self.focus)
        monkeypatch.setattr(ime, "read_composition", lambda hwnd: self.composition if hwnd == FOCUS else None)
        monkeypatch.setattr(ime, "place_ime_window", lambda hwnd, x, y: self.placed.append((hwnd, x, y)) or True)
        monkeypatch.setattr(ime, "set_ime_font", lambda hwnd, *font: self.fonts.append((hwnd, font)) or True)


@pytest.fixture
def view(hidden_root):
    shown = ime.CompositionView(hidden_root)
    yield shown
    shown._cancel()
    shown._drop()


# ------------------------------------------------------------------ what the IME gives
def test_a_composition_is_read_as_its_text_the_clause_being_converted_and_the_cursor():
    assert ime.parse_composition(b"") is None
    typed = ime.parse_composition(utf16("ものがたり"), bytes(5), 3)
    assert typed == ime.Composition("ものがたり", None, 3) and typed.parts() == [("ものがたり", False)]
    # the first clause converted, the second being converted (ATTR_CONVERTED 2, ATTR_TARGET_CONVERTED 1)
    converting = ime.parse_composition(utf16("見本の物語"), bytes([2, 2, 2, 1, 1]), 3)
    assert converting.target == (3, 5) and converting.parts() == [("見本の", False), ("物語", True)]
    # a character outside the BMP is two UTF-16 units: the clause and the cursor are counted in characters
    wide = ime.parse_composition(utf16("\U0001F600あい"), bytes([0, 0, 3, 0]), 3)
    assert wide.text == "\U0001F600あい" and wide.target == (1, 2) and wide.cursor == 2
    assert wide.parts() == [("\U0001F600", False), ("あ", True), ("い", False)]
    assert ime.parse_composition(utf16("あ") + b"\x00").text == "あ"  # half a unit is dropped
    assert ime.parse_composition(utf16("あい"), b"", -1).cursor == 2  # no cursor given: at the end


def test_the_picture_starts_at_the_caret_and_moves_left_only_to_keep_its_end_in_the_window():
    assert ime.anchor_x(40, 30, 200) == 40
    assert ime.anchor_x(180, 30, 200) == 170
    assert ime.anchor_x(180, 300, 200) == -100  # wider than the room: its end shows, where the typing goes on
    assert ime.anchor_x(180, 30, None) == 180  # a window not on the screen keeps nothing in


def test_the_caret_is_found_in_an_empty_box_in_the_middle_and_after_the_last_character(hidden_root):
    top = tk.Toplevel(hidden_root)
    top.withdraw()
    try:
        box = ttk.Entry(top)
        box.pack()
        empty = ime.caret_box(box)
        assert empty is not None
        box.insert(0, "見本の物語")
        box.icursor("end")
        x, _y, height = ime.caret_box(box)
        last = box.bbox(4)
        assert x == last[0] + last[2] > empty[0] and height == last[3]
        box.icursor(2)
        assert ime.caret_box(box)[0] == box.bbox(2)[0]
        # a text box (of several lines: a withdrawn one shows none, so its answer is stood in for)
        shown = {"insert": (14, 20, 7, 16)}
        text = SimpleNamespace(winfo_class=lambda: "Text", bbox=lambda index: shown.get(index))
        assert ime.caret_box(text) == (14, 20, 16)  # the caret's own line
        shown.clear()
        assert ime.caret_box(text) is None  # a caret out of sight: no picture
        assert not ime.typable(ttk.Combobox(top, state="readonly")) and ime.typable(box)
    finally:
        top.destroy()


# ------------------------------------------------------------------ the box with the keys
def test_the_book_name_dialog_shows_the_text_being_composed_and_leaves_its_fields_alone(hidden_root, monkeypatch,
                                                                                      view):
    fake = FakeIme(monkeypatch)
    answers = []
    d = StartDialog(hidden_root, "Yomizuq", generic=True, on_answer=lambda *a: answers.append(a))
    d.withdraw()
    try:
        d.fields.series_var.set("見本")
        d.entry.icursor("end")
        written = []
        for var in (d.name_var, d.fields.series_var, d.fields.volume_var):
            var.trace_add("write", lambda *_a: written.append(1))
        view.focus_in(_event(d.entry))
        assert fake.fonts and fake.fonts[0][0] == FOCUS and fake.fonts[0][1][1] > 0  # the box's font, in pixels
        view.tick()
        assert view.shown() == "" and view.canvas is None  # nothing composed: no picture
        fake.composition = ime.Composition("ものがたり", None, 5)
        view.key(_event(d.entry))  # a key the IME took (Tk gets it as VK_PROCESSKEY)
        view.tick()
        assert view.shown() == "ものがたり"
        canvas = view.canvas
        assert canvas.master is d and canvas.place_info()["in"] is d.entry  # over the Series box, in the dialog
        assert str(canvas.cget("takefocus")) == "0" and canvas.find_withtag("cursor")
        assert fake.placed and fake.placed[-1][0] == FOCUS  # the IME's own window put where the picture is
        fake.composition = ime.Composition("物語", (0, 2), 2)  # converted: the clause in the selection's colours
        view.tick()
        assert view.shown() == "物語" and not canvas.find_withtag("cursor")
        fills = {canvas.itemcget(item, "fill") for item in canvas.find_all() if canvas.type(item) == "rectangle"}
        assert fills == {theme.colour("selection")}
        # all the while the fields and the name are as they were: nothing written into them, nothing answered
        assert (d.entry.get(), d.fields.volume.get(), d.name_var.get()) == ("見本", "", "見本")
        assert int(d.entry.index("insert")) == 2 and not written and not answers and d.winfo_exists()
        fake.composition = None  # committed (the IME's key presses bring the text in) or cancelled: the picture goes
        view.tick()
        assert view.shown() == "" and view.canvas is None and not canvas.winfo_exists()
        fake.composition = ime.Composition("か")
        view.tick()
        assert view.shown() == "か"
        view.focus_out(_event(d.fields.volume))  # another box's focus going is not this one's
        assert view.shown() == "か"
        view.focus_out(_event(d.entry))  # the box lost the keys
        assert view.shown() == "" and view.widget is None and view._job is None
    finally:
        d.destroy()


def test_nothing_shows_in_a_box_that_takes_no_typing_or_while_another_window_has_the_keys(hidden_root, monkeypatch,
                                                                                         view):
    fake = FakeIme(monkeypatch)
    fake.composition = ime.Composition("あ")
    d = StartDialog(hidden_root, "Yomizuq", generic=True, on_answer=lambda *a: None,
                    matches=["Star Road 1", "Star Road 2"], hint="several")
    d.withdraw()
    try:
        d.from_colophon.set(True)  # the colophon is to give the name: the fields rest
        d._sync()
        view.focus_in(_event(d.entry))
        view.tick()
        assert view.shown() == ""
        d.from_colophon.set(False)
        d._sync()
        view.tick()
        assert view.shown() == "あ" and view.canvas.place_info()["in"] is d.entry  # the Series list's box too
        fake.focus = 0  # the keys are another window's (or another program's)
        view.tick()
        assert view.shown() == ""
    finally:
        d.destroy()


def test_the_toolbars_fields_show_it_too_and_a_box_that_goes_takes_its_picture_along(hidden_root, monkeypatch, view):
    fake = FakeIme(monkeypatch)
    fake.composition = ime.Composition("見本", (0, 2), 2)
    frame = ttk.Frame(hidden_root)
    fields = BookFields(frame, tk.StringVar(hidden_root), series_chars=10, short=True)
    fields.pack()
    frame.pack()
    view.key(_event(fields.volume))  # a key in a box the view did not know had the keys
    assert view.widget is fields.volume
    view.tick()
    assert view.shown() == "見本" and view.canvas.master is hidden_root
    frame.destroy()
    view.tick()
    assert view.shown() == "" and view.widget is None and view._job is None


# ------------------------------------------------------------------ every box, and the window's keys
def test_every_text_box_of_the_window_and_its_dialogs_gets_the_view_once(hidden_root):
    sequences = [(cls, seq) for cls in ime.TYPING_CLASSES for seq in ("<FocusIn>", "<FocusOut>", "<KeyPress>")]
    before = {key: hidden_root.bind_class(*key) for key in sequences}
    destroy = hidden_root.bind("<Destroy>")
    interp = str(hidden_root.tk.interpaddr())
    try:
        assert ime.install(hidden_root, enabled=False) is None and interp not in ime._views
        view = ime.install(hidden_root, enabled=True)
        assert view is not None and ime.install(hidden_root, enabled=True) is view
        for (cls, seq), script in before.items():
            now = hidden_root.bind_class(cls, seq)
            assert script in now  # the box's own binding first, as it was ...
            name = {"<FocusIn>": "focus_in", "<FocusOut>": "focus_out", "<KeyPress>": "key"}[seq]
            assert now.count(f"{name} %#") == 1, (cls, seq)  # ... then the view's, once
    finally:
        for (cls, seq), script in before.items():
            hidden_root.tk.call("bind", cls, seq, script)
        hidden_root.tk.call("bind", str(hidden_root), "<Destroy>", destroy)
        ime._views.pop(interp, None)


def test_the_window_installs_it_before_any_dialog_of_its_start():
    source = inspect.getsource(app_mod.App.__init__)
    assert source.index("ime.install(self)") < source.index("NoticeDialog(")


def test_the_windows_own_keys_never_run_in_a_dialogs_boxes(hidden_root):
    """The window's keys are bound on the main window and its page (`App._bind_shortcuts`, the page keys): a dialog's
    boxes carry their own window in their binding tags, not the main window."""
    d = StartDialog(hidden_root, "Yomizuq", generic=True, on_answer=lambda *a: None)
    d.withdraw()
    try:
        for box in (d.fields.series, d.fields.volume):
            tags = box.bindtags()
            assert str(hidden_root) not in tags and tags[2] == str(d) and tags[-1] == "all"
    finally:
        d.destroy()


# ------------------------------------------------------------------ Windows itself
@windows_only
def test_windows_is_only_asked_and_says_nothing_is_composed_for_a_window_without_the_keys(hidden_root):
    top = tk.Toplevel(hidden_root)
    top.withdraw()
    try:
        assert ime.read_composition(top.winfo_id()) is None  # read only: nothing is composed there
        assert ime.read_composition(0) is None and ime.focus_in_window(top) == 0  # the tests' windows never have the keys
        assert not ime.place_ime_window(0, 0, 0) and not ime.set_ime_font(0, "Yu Gothic UI", 12)  # nothing touched
        api = ime._load()
        assert len(api.imm.ImmSetCompositionFontW.argtypes) == 2 and len(api.imm.ImmSetCompositionWindow.argtypes) == 2
        family, pixels, bold, italic = ime.ime_font(top, "TkTextFont")
        assert family and pixels > 0 and not bold and not italic
    finally:
        top.destroy()
