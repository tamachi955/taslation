"""The editor's "Read as:" line is text that can be selected with the mouse and copied with Ctrl+C, and never edited:
key presses, pasting and deleting change nothing, Tab passes it by, and it looks like the label it was."""
from __future__ import annotations

import tkinter as tk

import numpy as np

from taslation.pipeline import manual_region
from taslation.ui.dialogs import review

JA = "今日はいい天気だね"


def _region(source=JA):
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text = "translated", "Nice weather today, huh?", source
    return r


def _editor(root, region, **kwargs):
    return review.EditBubbleDialog(root, region, [], on_save=lambda data: None, on_drop=lambda: None, **kwargs)


def test_the_read_as_line_cannot_be_edited(hidden_root):
    d = _editor(hidden_root, _region())
    field = d.source_label
    assert isinstance(field, tk.Text) and field.text() == "Read as: " + JA
    assert str(field.cget("state")) == "disabled"
    field.focus_force()
    field.update()
    field.tk.call("tk::TextInsert", field, "x")  # what a key press does in a text box
    field.insert("end", "typed")
    field.delete("1.0", "end")
    for event in ("<<Paste>>", "<<Cut>>", "<<Clear>>", "<<Undo>>"):
        field.event_generate(event)
    field.event_generate("<KeyPress>", keysym="a")
    field.event_generate("<KeyPress-BackSpace>")
    field.update()
    assert field.text() == "Read as: " + JA and d.source_var.get() == "Read as: " + JA
    assert d.region.source_text == JA  # nothing reached the region either
    d.destroy()


def test_the_read_as_line_can_be_selected_and_read_back(hidden_root):
    d = _editor(hidden_root, _region())
    field = d.source_label
    field.tag_add("sel", "1.0", "end-1c")
    assert field.get("sel.first", "sel.last") == "Read as: " + JA
    assert field.selection_get() == "Read as: " + JA  # what Ctrl+C copies
    field.tag_remove("sel", "1.0", "end")
    start = len("Read as: ")
    field.tag_add("sel", f"1.{start}", "end-1c")  # the Japanese alone, as a drag over it takes it
    assert field.selection_get() == JA
    assert "<<Copy>>" in field.bind_class("Text") and "<Control-Key-c>" in field.event_info("<<Copy>>")
    d.destroy()


def test_the_read_as_line_looks_like_a_label_and_tab_passes_it_by(hidden_root):
    d = _editor(hidden_root, _region())
    field = d.source_label
    assert str(field.cget("takefocus")) == "0" and int(field.cget("borderwidth")) == 0  # Tab passes it by
    assert int(field.cget("highlightthickness")) == 0 and str(field.cget("relief")) == "flat"
    assert str(field.cget("wrap")) == "char" and int(field.cget("height")) >= 1
    d.destroy()


def test_a_long_reading_takes_as_many_lines_as_it_needs(hidden_root):
    d = _editor(hidden_root, _region(JA * 12))
    d.update()
    assert int(d.source_label.cget("height")) >= 2
    d.destroy()


def test_a_reading_on_a_cached_page_shows_in_the_same_field(hidden_root):
    handed = []
    d = _editor(hidden_root, _region(source=""), on_read=lambda done: (handed.append(done), True)[1])
    assert not d.source_label.winfo_manager()
    d.read()
    handed[0](JA, "")
    field = d.source_label
    assert field.winfo_manager() == "pack" and field.text() == "Read as: " + JA
    assert str(field.cget("state")) == "disabled"
    d.destroy()
