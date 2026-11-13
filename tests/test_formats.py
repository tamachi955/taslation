"""Copy format and Paste format (Ctrl+Shift+C, Ctrl+Shift+V), also on every region of a kind in the book, and a
region copied and pasted (Ctrl+C, Ctrl+V): on the real pipeline, each one change that Ctrl+Z takes back."""

from __future__ import annotations

import numpy as np
import pytest

from test_formatting import Window
from helpers import EN_TEXTS, FakeOcr

from taslation import pipeline as pipeline_mod
from taslation.annotations import BookAnnotations, PageAnnotations, RegionNote, RegionStyle
from taslation.cache import CachedBubble, CacheStore
from taslation.i18n import CATALOGS, set_language
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import formats, shortcuts
from taslation.ui import translator as translator_mod
from taslation.ui.dialogs import review

RED = RegionStyle(colour="#c03030", outline=True, size=30, align="left")


class FormatWindow(Window):
    """`test_formatting.Window` with the window's copy and paste, Delete and the rectangle drawn on the page."""

    _format_clip = None
    format_clip = app_mod.App.format_clip
    _format_targets = app_mod.App._format_targets
    copy_format = app_mod.App.copy_format
    paste_format = app_mod.App.paste_format
    _paste_styles = app_mod.App._paste_styles
    paste_format_on_kind = app_mod.App.paste_format_on_kind
    _carry_book_styles = app_mod.App._carry_book_styles
    copy_region = app_mod.App.copy_region
    paste_region = app_mod.App.paste_region
    _add_region = app_mod.App._add_region
    _drop_region = app_mod.App._drop_region
    _editing = app_mod.App._editing


def _pipeline(settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                    annotations=ann)


@pytest.fixture
def two_pages(sample_page, sample_page2, settings):
    """The window on page 1 of a book whose page 2 was translated before (in the cache and its annotations)."""
    p = _pipeline(settings)
    second = p.process(sample_page2, complete=True)
    first = p.process(sample_page, complete=True)
    return FormatWindow(p, first), second


def _by_text(result, text):
    return next(r for r in result.regions if r.translated_text == text)


def _picture(w):
    return np.asarray(w.last_result.image).copy()


def _notes(p, result):
    unit = result.units[0]
    page = p.annotations.lookup(unit.fingerprint, unit.aspect, 6)
    return [(n.box, n.kind, n.style) for n in page.notes] if page is not None else []


# ------------------------------------------------------------------ copy and paste on the page
def test_copy_format_and_paste_it_on_another_region_one_change_without_the_kind(two_pages):
    w, _second = two_pages
    result = w.last_result
    source, target = _by_text(result, "Nice weather today, huh?"), _by_text(result, "Thank you.")
    w._chosen_region = source
    w.paste_format()
    assert w.said[-1] == formats.NOTHING_COPIED
    w._edit_region(source, {"text": source.translated_text, "speaker": "", "kind": "shout", "continues": False,
                            "note": "", "reader_note": "", "style": RED})
    picture, steps = _picture(w), len(w.history)
    w.copy_format()
    assert w.said[-1] == formats.FORMAT_COPIED and w.format_clip().style == RED
    w._chosen_region = target
    w.paste_format()
    assert target.style == RED and target.tag == "" and source.tag == "shout"  # the kind is a premise: not pasted
    assert w.said[-1] == formats.FORMAT_PASTED and len(w.history) == steps + 1
    assert not np.array_equal(_picture(w), picture)
    w.paste_format()  # the same again: nothing to change, no step
    assert w.said[-1] == formats.FORMAT_SAME and len(w.history) == steps + 1
    w.undo_edit()
    assert w.said[-1] == "Paste format taken back." and target.style is None and source.style == RED
    assert np.array_equal(_picture(w), picture)
    w.redo_edit()
    assert w.said[-1] == "Paste format made again." and target.style == RED
    again = w.pipeline.process(result.original, complete=True)  # kept with the book's premises
    assert _by_text(again, "Thank you.").style == RED


def test_paste_on_several_targets_is_one_change(two_pages):
    w, _second = two_pages
    result = w.last_result
    targets = [_by_text(result, "Thank you."), _by_text(result, "It's fine.")]
    picture = _picture(w)
    w.format_clip().style = RegionStyle(colour="white", outline=False)
    w._format_targets = lambda: list(targets)  # (a selection of several regions, as the multi-select gives it)
    w.paste_format()
    assert all(r.style == RegionStyle(colour="white", outline=False) for r in targets)
    assert w.said[-1] == formats.FORMAT_PASTED and len(w.history) == 1
    w.undo_edit()
    assert all(r.style is None for r in targets) and np.array_equal(_picture(w), picture)
    w.undo_edit()
    assert w.said[-1] == "Nothing to undo."


def test_without_a_selection_copy_and_paste_ask_for_one(two_pages):
    w, _second = two_pages
    w.copy_format()
    assert w.said[-1] == formats.SELECT_FIRST and w.format_clip().style is None
    w.format_clip().style = RED
    w.paste_format()
    assert w.said[-1] == formats.SELECT_FIRST
    w.copy_region()
    assert w.said[-1] == formats.SELECT_FIRST
    w.paste_region()
    assert w.said[-1] == formats.NO_REGION_COPIED
    w.role_var.set("reader")  # reader mode: the keys do nothing
    said = len(w.said)
    w.paste_format()
    w.copy_format()
    assert len(w.said) == said


# ------------------------------------------------------------------ every region of a kind, across the book
def test_paste_format_on_every_region_of_a_kind_across_the_book_and_take_it_back(two_pages, monkeypatch):
    w, second = two_pages
    p, result = w.pipeline, w.last_result
    here, other = _by_text(result, "Nice weather today, huh?"), _by_text(result, "Thank you.")
    there = second.regions[0]
    for page, region in ((result, here), (second, there)):
        assert p.set_region_note(page, region, kind="shout")
    p.rerender(result)  # the page as an edit letters it (`rerender`), to compare with
    before_second, picture = _notes(p, second), _picture(w)
    asked = []
    monkeypatch.setattr(formats.boxes, "ask", lambda parent, text, yes=None, no=None, **kw: asked.append((text, yes)))
    w._chosen_region = here
    w.format_clip().style = RED
    w.paste_format_on_kind()  # declined: nothing changes
    assert asked == [(
        "Put the copied formatting on every region of the kind Shout in this book: 2 region(s) on 2 page(s)? "
        "Ctrl+Z takes it back.", "Paste on 2 region(s)")]
    assert here.style is None and _notes(p, second) == before_second and not len(w.history)
    monkeypatch.setattr(formats.boxes, "ask", lambda *a, **kw: True)
    w.paste_format_on_kind()
    assert w.said[-1] == formats.KIND_DONE and here.style == RED and other.style is None
    assert [s for _b, k, s in _notes(p, second) if k == "shout"] == [RED]
    assert not np.array_equal(_picture(w), picture)
    saved = BookAnnotations.load(p.annotations.path)  # written
    assert sum(1 for page in saved.pages for n in page.notes if n.style == RED) == 2
    w.paste_format_on_kind()
    assert w.said[-1] == formats.KIND_NONE
    w.undo_edit()  # whichever page is on show
    assert w.said[-1] == formats.KIND_BACK and here.style is None and _notes(p, second) == before_second
    assert np.array_equal(_picture(w), picture)
    w.redo_edit()
    assert w.said[-1] == formats.KIND_AGAIN and here.style == RED
    assert [s for _b, k, s in _notes(p, second) if k == "shout"] == [RED]
    shown = p.process(second.original, complete=True)  # page 2 read again: its shout has the formatting
    assert next(r for r in shown.regions if r.tag == "shout").style == RED


def test_not_during_a_run_and_not_without_a_book(two_pages, monkeypatch):
    w, _second = two_pages
    monkeypatch.setattr(formats.boxes, "ask", lambda *a, **kw: pytest.fail("asked"))
    w._chosen_region = w.last_result.regions[0]
    w.format_clip().style = RED
    w._batching = True
    w.paste_format_on_kind()
    assert w.said[-1] == formats.KIND_IN_A_RUN
    w._batching = False
    w.pipeline.annotations = None
    w.paste_format_on_kind()
    assert w.said[-1] == formats.NO_BOOK


def test_the_regions_of_a_kind_in_the_stores():
    style = RegionStyle(bold=True)
    ann = BookAnnotations.__new__(BookAnnotations)
    ann.pages = []
    fp1, fp2, fp3 = "0" * 64, "f" * 64, "0f" * 32
    one = PageAnnotations(fp1, 0.7, ignore=[(0.6, 0.6, 0.8, 0.8)], notes=[
        RegionNote((0.1, 0.1, 0.3, 0.3), kind="shout"), RegionNote((0.4, 0.1, 0.5, 0.3), kind="thought"),
        RegionNote((0.6, 0.6, 0.8, 0.8), kind="shout"),  # a region dropped: its note stays, it is no region
        RegionNote((0.1, 0.5, 0.3, 0.7), kind="shout", style=style)])  # already so
    two = PageAnnotations(fp2, 0.7, notes=[RegionNote((0.2, 0.2, 0.4, 0.4), speaker="A")])
    ann.pages = [one, two]

    class Cache:
        pages = [type("P", (), {"fingerprint": fp2, "aspect": 0.7, "bubbles": [
                     CachedBubble(box=(0.2, 0.2, 0.4, 0.4), text="a"), CachedBubble(box=(0.5, 0.5, 0.7, 0.7), text="b")]})(),
                 type("P", (), {"fingerprint": fp3, "aspect": 0.7, "bubbles": [
                     CachedBubble(box=(0.1, 0.1, 0.3, 0.3), text="c")]})()]

    assert formats.book_spots(ann, Cache(), ["shout"], style) == [(fp1, 0.7, [(0.1, 0.1, 0.3, 0.3)])]
    unset = formats.book_spots(ann, Cache(), [""], style)  # "(not set)": the cached bubbles without a kind
    assert unset == [(fp2, 0.7, [(0.2, 0.2, 0.4, 0.4), (0.5, 0.5, 0.7, 0.7)]), (fp3, 0.7, [(0.1, 0.1, 0.3, 0.3)])]
    pages = formats.style_spots(ann, unset, style)
    assert [p.fingerprint for p in pages] == [fp2, fp3] and len(ann.pages) == 3  # page 3 got its annotations
    assert {n.speaker: n.style for n in two.notes} == {"A": style, "": style}
    ann.pages[1].notes.append(RegionNote((0.8, 0.8, 0.9, 0.9), note="written later"))
    assert formats.carry_styles(ann, pages, back=True) == 2
    assert sorted((n.speaker, n.note) for n in two.notes) == [("", "written later"), ("A", "")]
    assert all(n.style == RegionStyle() for n in two.notes)
    assert ann.pages[2].notes == []
    assert formats.carry_styles(ann, pages, back=False) == 2 and len(two.notes) == 3


# ------------------------------------------------------------------ a region copied and pasted
def test_a_region_copied_and_pasted_where_it_is_not_with_its_formatting(two_pages, sample_page2):
    w, _second = two_pages
    p, result = w.pipeline, w.last_result
    source = _by_text(result, "Thank you.")
    w._edit_region(source, {"text": source.translated_text, "speaker": "", "kind": "", "continues": False,
                            "note": "", "reader_note": "", "style": RED})
    w._chosen_region = source
    w.copy_region()
    box = tuple(source.bbox)
    assert w.said[-1] == formats.REGION_COPIED and w.format_clip().region == (box, result.original.size, RED)
    w.paste_region()
    assert w.said[-1] == formats.REGION_THERE  # it is here already
    w._drop_region(source)
    w._chosen_region = None
    assert not any(r.bbox == box for r in w.last_result.regions)
    steps = len(w.history)
    w.paste_region()  # where nothing is now: added, read and translated, with its formatting, one change
    pasted = next(r for r in w.last_result.regions if r.bbox == box)
    assert pasted.style == RED and len(w.history) == steps + 1
    w.undo_edit()
    assert not any(r.bbox == box and r.style == RED for r in w.last_result.regions)
    w.redo_edit()
    assert next(r for r in w.last_result.regions if r.bbox == box).style == RED
    w.last_result = p.process(sample_page2.resize((sample_page2.width // 2, sample_page2.height // 2)), complete=True)
    w.paste_region()
    assert w.said[-1] == formats.REGION_ELSEWHERE


# ------------------------------------------------------------------ the region editor, the keys, the words
def test_the_editor_copies_and_pastes_the_bar(hidden_root):
    from taslation.pipeline import manual_region

    region = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    region.status, region.translated_text, region.font_size = "translated", "Nice weather today, huh?", 31
    clip = formats.FormatClip()
    d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None, clip=clip)
    assert d.paste_btn.instate(["disabled"]) and not d.bar.winfo_manager()
    d.paste_format()  # nothing copied: nothing happens
    assert d.style() == RegionStyle()
    d.set_style(RegionStyle(colour="white", italic=True))
    d.copy_btn.invoke()
    assert clip.style == RegionStyle(colour="white", italic=True) and d.paste_btn.instate(["!disabled"])
    d.destroy()
    region.style = None
    other = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None, clip=clip)
    other.paste_btn.invoke()
    assert other.style() == RegionStyle(colour="white", italic=True) and other.bar.winfo_manager()
    assert other.changed()
    other.destroy()
    plain = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None)
    assert not hasattr(plain, "copy_btn")  # a window with no clip: no Copy and Paste format
    plain.destroy()


def test_the_keys_and_every_word_in_every_language():
    keymap = shortcuts.Keymap()  # the keys are the shortcuts table's, named as the keyboard names them
    assert [keymap.shown(name) for name in ("copy_format", "paste_format", "copy_region", "paste_region")] == [
        "Ctrl+Shift+C", "Ctrl+Shift+V", "Ctrl+C", "Ctrl+V"]
    lines = shortcuts.help_lines(keymap)
    assert "Ctrl+Shift+C: Copy format" in lines and "Ctrl+V: Paste region" in lines
    words = [formats.FORMAT_COPIED, formats.NOTHING_COPIED, formats.FORMAT_PASTED, formats.FORMAT_SAME,
             formats.SELECT_FIRST, formats.NO_BOOK, formats.KIND_QUESTION, formats.KIND_APPLY, formats.KIND_NONE,
             formats.KIND_DONE, formats.KIND_IN_A_RUN, formats.KIND_BACK, formats.KIND_AGAIN, formats.SAVE_FAILED,
             formats.REGION_COPIED, formats.NO_REGION_COPIED, formats.REGION_THERE, formats.REGION_ELSEWHERE,
             *formats.PAGE_FORMAT_TIPS, translator_mod.TAKEN_BACK["paste"], translator_mod.MADE_AGAIN["paste"],
             *review.FORMAT_TIPS.values(), "Copy format", "Paste format",
             "Paste format on every region of this kind...", "Copy region", "Paste region"]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(w in catalog for w in words), (code, [w for w in words if w not in catalog])
    set_language("de")
    assert keymap.shown("copy_format") == "Strg+Umschalt+C" and keymap.shown("paste_region") == "Strg+V"
    set_language("en")
    for word in words:  # the placeholders kept
        for code, catalog in CATALOGS.items():
            if word in catalog:
                assert sorted(_fields(catalog[word])) == sorted(_fields(word)), (code, word)


def _fields(text):
    import string

    return [name for _lit, name, _spec, _conv in string.Formatter().parse(text) if name]


def test_pipeline_unit_for_is_what_the_translator_imports():
    assert translator_mod.unit_for is pipeline_mod.unit_for
