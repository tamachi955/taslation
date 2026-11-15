"""The editor's "Read as:" field: the Japanese read in the region, which the person may correct where it was misread.
It is one line (Enter adds no line break, a paste drops them), Tab moves on, it can still be selected and copied, and
it grows to the lines its text takes. Ask again hands the model the reading as it stands there and Save hands it on;
nothing reaches the region before Save, and Cancel drops it. Where nothing was read, the field is there to type the
reading in once a reading was tried."""
from __future__ import annotations

import re
import tkinter as tk

import numpy as np

from taslation.pipeline import manual_region
from taslation.ui.dialogs import review

JA = "今日はいい天気だね"
FIXED = "今日はいい天気だな"


def _region(source=JA, status="translated"):
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text = status, "Nice weather today, huh?", source
    return r


def _editor(root, region, **kwargs):
    kwargs.setdefault("on_save", lambda data: None)
    return review.EditBubbleDialog(root, region, [], on_drop=lambda: None, **kwargs)


def _type(field, text):
    for ch in text:
        field.tk.call("tk::TextInsert", field, ch)  # what a key press does in a text box


def test_the_reading_can_be_corrected_and_reaches_the_region_only_on_save(hidden_root):
    saved = []
    region = _region()
    d = _editor(hidden_root, region, on_save=saved.append)
    field = d.source_field
    assert isinstance(field, tk.Text) and field.text() == JA and str(field.cget("state")) == "normal"
    assert d.source_label.winfo_manager() == "pack" and not d.changed()
    field.mark_set("insert", "end-2c")
    field.delete("insert")
    _type(field, "な")
    assert field.text() == FIXED and d._source() == FIXED and d.changed()
    assert region.source_text == JA  # not before Save
    d._save()
    assert saved[-1]["source"] == FIXED and saved[-1]["text"] == "Nice weather today, huh?"
    assert region.source_text == JA  # (the window takes it on: `Pipeline.correct_reading`)


def test_cancel_drops_the_corrected_reading(hidden_root):
    saved = []
    region = _region()
    d = _editor(hidden_root, region, on_save=saved.append)
    d.source_field.set_text(FIXED)
    d.destroy()
    assert not saved and region.source_text == JA


def test_ask_again_hands_the_model_the_reading_as_it_stands(hidden_root):
    asked = []
    d = _editor(hidden_root, _region(), on_ask=lambda mode, answer: (asked.append(dict(answer)), True)[1])
    d.ask_btns[0].invoke()
    assert asked[-1] == {"source": JA}
    d.show_answers("again", [])
    d.source_field.set_text("  " + FIXED + "\n")
    d.ask_btns[0].invoke()
    assert asked[-1] == {"source": FIXED}  # one line, its ends trimmed
    d.destroy()


def _fire(widget, sequence):
    """What the field's own binding of *sequence* does and returns ("break": the Text's own binding, which would put a
    line break or a tab character in, does not run). The hidden test window is given no key presses."""
    command = re.search(r"\[(\S+)", widget.bind(sequence)).group(1)
    fields = ["0"] * 19  # (%# %b %f %h %k %s %t %w %x %y %A %E %K %N %W %T %X %Y %D)
    fields[14] = str(widget)
    return widget.tk.call(command, *fields)


def test_the_field_is_one_line_and_tab_moves_on(hidden_root):
    saved = []
    d = _editor(hidden_root, _region(), on_save=saved.append)
    field = d.source_field
    field.mark_set("insert", "end-1c")
    assert _fire(field, "<Return>") == "break" and _fire(field, "<KP_Enter>") == "break"
    assert field.text() == JA  # no line break
    field.clipboard_clear()
    field.clipboard_append("だ\nね")
    field.event_generate("<<Paste>>")
    assert field.text() == JA + "だね"  # pasted on one line
    assert _fire(field, "<Tab>") == "break" and _fire(field, "<Shift-Tab>") == "break"
    assert field.text() == JA + "だね"  # no tab character: the focus moves on
    assert int(field.cget("borderwidth")) == 1 and str(field.cget("wrap")) == "char"
    assert str(field.cget("takefocus")) != "0"
    assert _fire(field, "<Control-Return>") == "break" and saved[-1]["source"] == JA + "だね"  # Ctrl+Enter saves


def test_the_reading_can_be_selected_and_copied(hidden_root):
    d = _editor(hidden_root, _region())
    field = d.source_field
    field.tag_add("sel", "1.0", "end-1c")
    assert field.selection_get() == JA  # what Ctrl+C copies
    assert "<<Copy>>" in field.bind_class("Text") and "<Control-Key-c>" in field.event_info("<<Copy>>")
    d.destroy()


def test_a_long_reading_takes_as_many_lines_as_it_needs(hidden_root):
    d = _editor(hidden_root, _region(JA * 12))
    d.update()
    assert int(d.source_field.cget("height")) >= 2
    d.destroy()


def test_a_reading_on_a_cached_page_shows_in_the_same_field_and_is_no_change(hidden_root):
    handed = []
    d = _editor(hidden_root, _region(source=""), on_read=lambda done: (handed.append(done), True)[1])
    assert not d.source_label.winfo_manager() and d.read_btn.winfo_manager() == "pack"
    d.read()
    handed[0](JA, "")
    assert d.source_label.winfo_manager() == "pack" and d.source_field.text() == JA
    assert not d.read_btn.winfo_manager() and not d.changed()  # read, not changed
    d.destroy()


def test_where_nothing_was_read_the_reading_can_be_typed_in(hidden_root):
    handed, asked = [], []
    d = _editor(hidden_root, _region(source=""), on_read=lambda done: (handed.append(done), True)[1],
                on_ask=lambda mode, answer: (asked.append(dict(answer)), True)[1])
    d.read()
    handed[0]("", "none")
    assert d.source_label.winfo_manager() == "pack" and d.source_field.text() == ""
    assert d.read_btn.winfo_manager() == "pack"  # (read once more, or type it in)
    _type(d.source_field, FIXED)
    d.ask_btns[0].invoke()
    assert asked == [{"source": FIXED}] and len(handed) == 1  # asked at once: not read first
    d.destroy()
    d = _editor(hidden_root, _region(source="", status="ocr-empty"), on_read=lambda done: True)
    assert d.source_label.winfo_manager() == "pack"  # read on this page, and nothing came: the field is there
    d.destroy()
