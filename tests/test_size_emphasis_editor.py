"""The person's control over the part of a translation set larger (`TextRegion.large`): the setting that turns it off
(`size_emphasis`, a row of the Settings dialog that letters the page again), the region editor (the part shown larger
in its box, following the edits there and dropped by one that touches it, Set larger on the words selected, One size,
Save and the preview with it, Ask again's answer with its own part, none of it shown with the setting off), the
window's Save that stores a part changed alone (`Pipeline.set_large`: the translation stays whose it was, Ctrl+Z
takes it back), the preview lettered with the editor's part, and find and replace, which moves the part or drops it.
Invented lines only."""
from __future__ import annotations

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr

from taslation.annotations import BookAnnotations, RegionStyle
from taslation.cache import CacheStore, TextEdit
from taslation.i18n import CATALOGS
from taslation.pipeline import Pipeline, manual_region
from taslation.regions import box_iou
from taslation.size_mix import SizeMix
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui.dialogs import review
from taslation.ui.dialogs.settings import PAGE_SETTINGS, SHOWN_ROWS
from taslation.ui.history import EditHistory
from taslation.ui.replace import reletter
from taslation.ui.translator import LivePreview

TEXT = "You, get out right now!"
LARGE = (5, 12, 1.6)  # "get out"


def _region(text=TEXT, large=LARGE):
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text, r.font_size = "translated", text, "お前は今すぐ出て行け", 31
    r.large = large
    return r


def _tagged(d) -> str:
    """What the editor's box shows larger."""
    ranges = d.text.tag_ranges("large")
    return d.text.get(ranges[0], ranges[1]) if ranges else ""


# ------------------------------------------------------------------ the setting
def test_the_setting_is_a_lettering_row_that_letters_the_page_again_in_every_language():
    row = next(r for r in SHOWN_ROWS if r.key == "size_emphasis")
    assert row.section == "lettering" and row.page and "size_emphasis" in PAGE_SETTINGS
    words = [row.label, row.tip, *review.LARGER_WORDS.values(), *review.LARGER_TIPS.values(), review.LARGER_SELECT]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(w in catalog for w in words), (code, [w for w in words if w not in catalog])


# ------------------------------------------------------------------ the editor
def test_the_editor_shows_the_part_larger_and_it_follows_the_edits(hidden_root):
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None)
    assert _tagged(d) == "get out" and d._data()["large"] == LARGE and not d.changed()
    d.text.insert("1.0", "Hey! ")  # before it: it moves along
    d._text_changed()
    assert _tagged(d) == "get out" and d._data()["large"] == (10, 17, 1.6) and d.changed()
    d.text.insert("end-1c", " OK?")  # after it: as it was
    d._text_changed()
    assert d._data()["large"] == (10, 17, 1.6)
    start = d.text.search("out", "1.0")
    d.text.delete(start, f"{start} + 3 chars")  # inside it: gone
    d.text.insert(start, "lost")
    d._text_changed()
    assert _tagged(d) == "" and d._data()["large"] is None
    d.destroy()


def test_set_larger_takes_the_words_selected_and_one_size_clears_them(hidden_root):
    saved = []
    d = review.EditBubbleDialog(hidden_root, _region(large=None), [], on_save=saved.append, on_drop=lambda: None)
    assert _tagged(d) == "" and d._data()["large"] is None
    d.set_larger()  # nothing selected: a line says what to do
    assert d.busy_var.get() == review.LARGER_SELECT and d._data()["large"] is None
    d.text.tag_add("sel", "1.0", "end-1c")  # all of it: nothing set larger
    d.set_larger()
    assert d._data()["large"] is None
    d.text.tag_remove("sel", "1.0", "end")
    d.text.tag_add("sel", "1.4", "1.13")  # " get out ", the spaces round it left out
    d.set_larger()
    assert _tagged(d) == "get out" and d._data()["large"] == (5, 12, review.LARGER_RATIO) and d.busy_var.get() == ""
    assert d.changed()
    d.one_size()
    assert _tagged(d) == "" and d._data()["large"] is None
    d.text.tag_remove("sel", "1.0", "end")
    d.text.tag_add("sel", "1.0", "1.3")
    d.set_larger()
    d._save()
    assert saved[-1]["large"] == (0, 3, review.LARGER_RATIO) and saved[-1]["text"] == TEXT
    region = _region(large=None)  # where the original's lettering was measured, its ratio
    region.size_mix = SizeMix(start=6, end=10, ratio=1.8, base=20.0)
    d = review.EditBubbleDialog(hidden_root, region, [], on_save=saved.append, on_drop=lambda: None)
    d.text.tag_add("sel", "1.5", "1.12")
    d.set_larger()
    assert d._data()["large"] == (5, 12, 1.8)
    d.destroy()


def test_a_part_saved_is_a_range_of_the_text_without_the_spaces_round_it(hidden_root):
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None)
    d.text.insert("1.0", "  \n")
    d._text_changed()
    assert d._data()["text"] == TEXT and d._data()["large"] == LARGE
    d.destroy()


def test_with_the_setting_off_the_box_shows_no_part_and_the_bar_has_no_buttons(hidden_root):
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                sizes=False)
    assert _tagged(d) == "" and not hasattr(d, "larger_btn") and not hasattr(d, "one_size_btn")
    assert d._data()["large"] == LARGE  # (kept as it was: the lettering sets it at one size)
    d.destroy()
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None)
    assert d.larger_btn.winfo_exists() and d.one_size_btn.winfo_exists()
    d.destroy()


def test_the_preview_and_ask_again_carry_the_part(hidden_root):
    asked, old = [], []
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_preview=lambda text, style, large=None: asked.append((text, large)))
    d._preview()
    assert asked[-1] == (TEXT, LARGE)
    d.one_size()
    d._preview()
    assert asked[-1] == (TEXT, None)
    d.show_answers("again", ["Hey you, get out right now!"], [(9, 16, 1.6)])  # the window found its part
    assert _tagged(d) == "get out" and d._data()["large"] == (9, 16, 1.6) and d._data()["asked"]
    d.show_answers("again", ["Leave."])  # none found: one size
    assert _tagged(d) == "" and d._data()["large"] is None
    d.destroy()
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_preview=lambda text, style: old.append(text))  # one that takes text and style
    d._preview()
    assert old == [TEXT]
    d.destroy()


# ------------------------------------------------------------------ the window and the pipeline
class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


class Jobs:
    def put(self, job):
        job()


class Window:
    """The parts of the App that an edit, its preview and undo use, on the real pipeline; jobs run at once."""

    _record = app_mod.App._record
    _edit_region = app_mod.App._edit_region
    _preview_region = app_mod.App._preview_region
    _show_preview = app_mod.App._show_preview
    _end_preview = app_mod.App._end_preview
    undo_edit = app_mod.App.undo_edit
    redo_edit = app_mod.App.redo_edit
    _step_through = app_mod.App._step_through

    def __init__(self, pipeline, result):
        self.pipeline, self.last_result = pipeline, result
        self.history = EditHistory()
        self.role_var, self.book_var, self.lang_var = Var("translator"), Var("Book"), Var("English")
        self.reading = self.busy = False
        self._ordering = self._chosen_region = None
        self._editor = None
        self.said, self.shown = [], 0
        self._jobs = Jobs()

    def after(self, _ms, callback):
        callback()

    def _redisplay(self):
        self.shown += 1

    def _choose(self, region):
        self._chosen_region = region

    def _post(self, kind, **data):
        if kind == "result":
            self.last_result = data["result"]
        elif kind == "translate_done":
            self.busy = False
        elif kind == "status" and "key" in data:
            self.said.append(data["key"])

    def _go_busy(self):
        self.busy = True

    def say(self, key, **values):
        self.said.append(key)

    def _result_on_show(self):
        return True


@pytest.fixture
def window(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                        annotations=ann)
    return Window(pipeline, pipeline.process(sample_page, complete=True))


def _picture(w) -> np.ndarray:
    return np.asarray(w.last_result.image).copy()


def _bubble(w, region):
    unit = w.last_result.units[region.unit]
    page = w.pipeline._page_for(unit)
    nbox = unit.normalize(region.bbox)
    return max(page.bubbles, key=lambda b: box_iou(b.box, nbox))


def _data(text, large):
    return {"text": text, "speaker": "", "kind": "", "continues": False, "note": "", "reader_note": "", "style": None,
            "large": large}


def test_a_save_that_changes_only_the_part_stores_it_alone_and_undo_takes_it_back(window):
    w = window
    target = next(r for r in w.last_result.regions if r.translated_text == "It's fine.")
    before = _picture(w)
    w._edit_region(target, _data("It's fine.", (5, 10, 1.8)))  # "fine." larger
    bubble = _bubble(w, target)
    assert target.large == (5, 10, 1.8) and bubble.large == (5, 10, 1.8) and not bubble.edited
    assert target.translated_text == "It's fine." and not np.array_equal(_picture(w), before)
    w.undo_edit()
    assert target.large is None and _bubble(w, target).large is None and np.array_equal(_picture(w), before)
    w._edit_region(target, _data("Really fine.", (7, 12, 1.8)))  # the text and its part, together
    assert target.large == (7, 12, 1.8) and _bubble(w, target).large == (7, 12, 1.8) and _bubble(w, target).edited


def test_the_setting_off_letters_a_stored_part_at_one_size(window):
    w = window
    target = next(r for r in w.last_result.regions if r.translated_text == "It's fine.")
    before = _picture(w)
    w._edit_region(target, _data("It's fine.", (5, 10, 1.8)))
    assert not np.array_equal(_picture(w), before)
    w.pipeline.settings.size_emphasis = False
    w.pipeline.rerender(w.last_result)
    assert np.array_equal(_picture(w), before) and target.large == (5, 10, 1.8)


def test_the_preview_letters_the_editors_part(window):
    w = window
    result = w.last_result
    target = next(r for r in result.regions if r.translated_text == "It's fine.")
    before = _picture(w)
    w._editor = None
    preview = LivePreview(result, target)
    w._preview_region(preview, "It's fine.", RegionStyle(), (5, 10, 1.8))
    larger = _picture(w)
    assert not np.array_equal(larger, before) and target.large is None  # nothing stored
    w._preview_region(preview, "It's fine.", RegionStyle(), None)
    assert np.array_equal(_picture(w), before)
    w._preview_region(preview, "It's fine.", RegionStyle(), (5, 99, 1.8))  # not a range of the text: one size
    assert np.array_equal(_picture(w), before)
    w._end_preview(preview)


def test_find_and_replace_moves_the_part_or_drops_it(window):
    w = window
    result = w.last_result
    target = next(r for r in result.regions if r.translated_text == "It's fine.")
    w._edit_region(target, _data("It's fine.", (5, 10, 1.8)))
    unit = result.units[target.unit]
    box = _bubble(w, target).box
    made = w.pipeline.cache.put_texts([TextEdit(unit.fingerprint, box, "It's fine.", "Oh, it's fine.", mark=True)])
    assert reletter(w.pipeline, result, made)
    assert target.translated_text == "Oh, it's fine." and target.large == (9, 14, 1.8)
    made = w.pipeline.cache.put_texts([TextEdit(unit.fingerprint, box, "Oh, it's fine.", "Oh, it's OK.", mark=True)])
    assert reletter(w.pipeline, result, made)
    assert target.translated_text == "Oh, it's OK." and target.large is None
    back = w.pipeline.cache.put_texts([e.undone() for e in made])
    assert reletter(w.pipeline, result, back)
    assert target.translated_text == "Oh, it's fine." and target.large == (9, 14, 1.8)
