"""An area ignored on all pages of a book (a watermark, a page number, a banner): the area itself (its box grown from
the dropped region's, what it holds, the pages it applies to, its place in the book's file), detection leaving out
what lies in it on a page on show and in a whole-book scan alike (a rectangle the reader added stays, a cached
translation in it is kept but not drawn), translator mode's Page menu entry and the question after a drop at a place
dropped on another page before, each one change that Ctrl+Z takes back, and Book settings' list with Remove area and
its Undo. On the real pipeline and stores; the window's parts are borrowed onto stand-ins whose jobs run at once."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, store_json
from test_translator_mode import Window

from taslation.annotations import AREA_INSIDE, BookAnnotations, BookArea, page_side
from taslation.cache import CacheStore
from taslation.config import Settings
from taslation.i18n import CATALOGS
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import book_areas
from taslation.ui.dialogs import book_settings, caches

# where the sample pages have a bubble at the same place (pixels of the 1240 x 1754 fixtures)
LOWER_RIGHT = (850, 929, 1110, 1309)
LOWER_LEFT = (155, 974, 405, 1324)


class AreaWindow(Window):
    """`test_translator_mode.Window` with translator mode's areas ignored on all pages and timers that run at once."""

    _editing = app_mod.App._editing
    ignore_area_everywhere = app_mod.App.ignore_area_everywhere
    _offer_ignore_everywhere = app_mod.App._offer_ignore_everywhere
    _ask_ignore_everywhere = app_mod.App._ask_ignore_everywhere
    _add_book_area = app_mod.App._add_book_area
    _carry_book_areas = app_mod.App._carry_book_areas
    _carry_area = app_mod.App._carry_area

    def after(self, _ms, callback):
        callback()


def _pipeline(settings, book="Book"):
    cache = CacheStore(settings.cache_dir).open(book, "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / f"{book}.json", book)
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                    annotations=ann)


def _at(result, where):
    """The region of *result* whose middle lies in the box *where* (pixels)."""
    x0, y0, x1, y1 = where
    found = [r for r in result.regions
             if x0 <= (r.bbox[0] + r.bbox[2]) / 2 <= x1 and y0 <= (r.bbox[1] + r.bbox[3]) / 2 <= y1]
    assert len(found) == 1, found
    return found[0]


def _near(result, where):
    x0, y0, x1, y1 = where
    return [r for r in result.regions
            if x0 <= (r.bbox[0] + r.bbox[2]) / 2 <= x1 and y0 <= (r.bbox[1] + r.bbox[3]) / 2 <= y1]


def _area_of(result, region):
    area = book_areas.area_for(result, region)
    assert area is not None
    return area


# ------------------------------------------------------------------ the area itself
def test_an_area_is_the_dropped_box_grown_and_holds_what_lies_mostly_inside():
    area = BookArea.around((0.4, 0.9, 0.6, 0.96), "right", 0.7071)
    x0, y0, x1, y1 = area.box
    assert (x0, x1) == (0.35, 0.65)  # a quarter of its width more on each side
    assert y0 == pytest.approx(0.885) and y1 == pytest.approx(0.975)
    assert area.holds((0.4, 0.9, 0.6, 0.96)) and area.holds((0.3, 0.9, 0.6, 0.96))  # 5/6 of it inside
    assert not area.holds((0.2, 0.9, 0.6, 0.96))  # 5/8 is not enough
    assert not area.holds((0.0, 0.0, 0.1, 0.1)) and not area.holds((0.5, 0.5, 0.5, 0.6))  # elsewhere; no box
    assert area.holds((0.58, 0.9, 0.68, 0.96)) and not area.holds((0.582, 0.9, 0.682, 0.96))  # 0.7: 0.7 and 0.68
    tiny = BookArea.around((0.5, 0.5, 0.5001, 0.5001))
    assert tiny.box[2] - tiny.box[0] == pytest.approx(0.0201)  # at least a hundredth of the page on each side
    edge = BookArea.around((-0.95, 1.9, -0.5, 1.99))
    assert edge.box[0] == -1.0 and edge.box[3] == 2.0  # kept within the reach of a page's boxes
    # the pages it applies to: its side of a spread and pages shown alone, of about its shape
    assert area.applies("right", 0.7071) and area.applies("", 0.69) and not area.applies("left", 0.7071)
    assert not area.applies("right", 1.4142)  # a spread drawn as one picture
    assert BookArea.around((0.1, 0.1, 0.2, 0.2)).applies("left", 2.0)  # no side, no shape: every page
    assert [page_side(i, 2) for i in (0, 1)] == ["right", "left"] and page_side(0, 1) == ""


def test_areas_are_kept_in_the_books_file_and_a_file_without_any_stays_as_it_was(tmp_path):
    path = tmp_path / "Book.json"
    ann = BookAnnotations(path, "Book")
    ann.save()
    assert "areas" not in store_json(path)
    area = BookArea.around((0.4, 0.9, 0.6, 0.96), "left", 0.7)
    assert ann.add_area(area) and not ann.add_area(BookArea.around((0.401, 0.9, 0.6, 0.96), "left", 0.7))
    assert ann.add_area(BookArea.around((0.4, 0.9, 0.6, 0.96)))  # the same place on every page is another area
    ann.save()
    data = store_json(path)
    assert data["areas"][0] == {"box": list(area.box), "side": "left", "aspect": 0.7}
    assert data["areas"][1] == {"box": list(BookArea.around((0.4, 0.9, 0.6, 0.96)).box)}
    again = BookAnnotations.load(path)
    assert again.areas == ann.areas and again.areas_for("right", 0.7) == [ann.areas[1]]
    data["areas"] += [{"box": [0.5, 0.5, 0.4, 0.6]}, {"box": "x"}, {"side": "left"}, 7, {"box": [0, 0, 1, 1],
                                                                                            "side": "top"}]
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = BookAnnotations.load(path).areas  # what is no area is left out, never the book
    assert loaded[:2] == ann.areas and loaded[2] == BookArea(box=(0.0, 0.0, 1.0, 1.0)) and len(loaded) == 3
    assert ann.remove_area(BookArea(box=area.box, side="left")) and ann.areas == again.areas[1:]
    assert not ann.remove_area(area)


# ------------------------------------------------------------------ detection leaves the area out
def test_a_page_on_show_leaves_out_what_lies_in_an_area_and_keeps_its_translation(sample_page, settings):
    p = _pipeline(settings)
    first = p.process(sample_page, complete=True)
    victim = _at(first, LOWER_RIGHT)
    text, count = victim.translated_text, len(first.regions)
    assert text and p.process(sample_page, complete=True).regions  # the page shown again comes from memory
    p.annotations.add_area(_area_of(first, victim))
    shown = p.process(sample_page, complete=True)  # another key: the area is part of what the page is made from
    assert not _near(shown, LOWER_RIGHT) and len(shown.regions) == count - 1
    unit = first.units[0]
    hit = p.cache.lookup(unit.fingerprint, unit.aspect, 36)
    assert len(hit[0].bubbles) == count  # the translation stays in the cache, only not drawn
    # a rectangle the reader added there is theirs: it stays
    box = unit.normalize(victim.bbox)
    p.annotations.add_box(unit.fingerprint, unit.aspect, box, "add")
    added = p.process(sample_page, complete=True)
    assert [r.kind.startswith("manual") for r in _near(added, LOWER_RIGHT)] == [True]
    # taken away, the place is read again and its translation comes back from the cache
    p.annotations.remove_box(unit.fingerprint, unit.aspect, box)
    p.annotations.remove_area(_area_of(first, victim))
    asked = len(p.translator.calls)
    back = p.process(sample_page, complete=True)
    assert _at(back, LOWER_RIGHT).translated_text == text and len(p.translator.calls) == asked


def test_a_whole_book_scan_leaves_out_what_lies_in_an_area_and_keeps_its_cached_translation(sample_page,
                                                                                            sample_page2, settings):
    plain = _pipeline(settings, "Plain").scan(sample_page2)
    found = [r for u in plain.units for r in u.japanese()]
    p = _pipeline(settings)
    first = p.process(sample_page, complete=True)
    area = _area_of(first, _at(first, LOWER_RIGHT))  # made on one page, it applies to the other
    p.annotations.add_area(area)
    scan = p.scan(sample_page2)
    left = [r for u in scan.units for r in u.japanese()]
    assert len(left) == len(found) - 1
    unit = scan.units[0]
    assert not any(area.holds(unit.normalize(r.bbox)) for r in left)
    # a page in the cache keeps the translation it has there: hidden, not stale
    p.annotations.remove_area(area)
    second = p.process(sample_page2, complete=True)
    n = len(second.regions)
    p.annotations.add_area(area)
    again = p.scan(sample_page2)
    su = again.units[0]
    assert su.cached and su.dropped == 0 and len(su.kept) == n
    hit = p.cache.lookup(su.fingerprint, su.aspect, 36)
    assert len(hit[0].bubbles) == n
    assert len(p.process(sample_page2, complete=True).regions) == n - 1


# ------------------------------------------------------------------ translator mode
@pytest.fixture
def two_pages(sample_page, sample_page2, settings):
    """The window on page 1 of a book whose page 2 was translated before (in the cache and its annotations)."""
    p = _pipeline(settings)
    second = p.process(sample_page2, complete=True)
    first = p.process(sample_page, complete=True)
    return AreaWindow(p, first), second


def test_the_page_menu_ignores_the_selected_regions_place_as_one_change_ctrl_z_takes_back(two_pages, sample_page2):
    w, _second = two_pages
    victim = _at(w.last_result, LOWER_RIGHT)
    text, count = victim.translated_text, len(w.last_result.regions)
    w.ignore_area_everywhere()
    assert w.said[-1] == book_areas.SELECT_FIRST and not w.pipeline.annotations.areas
    w._chosen_region = victim
    w.ignore_area_everywhere()
    assert len(w.pipeline.annotations.areas) == 1 and len(w.history) == 1 and w.read_again == 1
    assert w.said[-1] == book_areas.AREA_ADDED and not _near(w.last_result, LOWER_RIGHT)
    assert len(w.last_result.regions) == count - 1
    saved = BookAnnotations.load(w.pipeline.annotations.path)
    assert saved.areas == w.pipeline.annotations.areas  # stored at once
    assert not _near(w.pipeline.process(sample_page2, complete=True), LOWER_RIGHT)  # every page of the book
    w._chosen_region = w.last_result.regions[0]
    w.ignore_area_everywhere()
    w._chosen_region = None
    asked = len(w.pipeline.translator.calls)
    w.undo_edit()  # the newest change first: the second area ...
    w.undo_edit()  # ... then the first, whichever page is on show
    assert w.said[-1] == book_areas.AREA_BACK and not w.pipeline.annotations.areas
    assert _at(w.last_result, LOWER_RIGHT).translated_text == text and len(w.last_result.regions) == count
    assert len(w.pipeline.translator.calls) == asked  # its translation came back from the cache
    assert not BookAnnotations.load(w.pipeline.annotations.path).areas
    w.redo_edit()
    assert w.said[-1] == book_areas.AREA_AGAIN and len(w.pipeline.annotations.areas) == 1
    assert not _near(w.last_result, LOWER_RIGHT)


def test_the_same_place_twice_is_said_and_no_change(two_pages):
    w, _second = two_pages
    victim = _at(w.last_result, LOWER_RIGHT)
    w._chosen_region = victim
    w.pipeline.annotations.add_area(_area_of(w.last_result, victim))
    w.ignore_area_everywhere()
    assert w.said[-1] == book_areas.AREA_THERE and len(w.history) == 0 and w.read_again == 0
    w._add_book_area(_area_of(w.last_result, victim), w.last_result)  # (a question answered after the entry)
    assert w.said[-1] == book_areas.AREA_THERE and len(w.history) == 0 and len(w.pipeline.annotations.areas) == 1


def test_not_during_a_run_and_not_in_reader_mode(two_pages):
    w, _second = two_pages
    w._chosen_region = _at(w.last_result, LOWER_RIGHT)
    w._batching = True
    w.ignore_area_everywhere()
    assert w.said[-1] == book_areas.AREA_IN_A_RUN and not w.pipeline.annotations.areas
    w._batching = False
    w.role_var.set("reader")
    w.ignore_area_everywhere()
    assert not w.pipeline.annotations.areas and len(w.history) == 0


def test_a_drop_where_one_was_dropped_on_another_page_asks_once(two_pages, sample_page2, monkeypatch):
    w, second = two_pages
    asked = []
    answers = [False, True]
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append((text, a)) or answers.pop(0))
    w._drop_region(_at(w.last_result, LOWER_LEFT))
    assert not asked  # nowhere else dropped there: no question
    first = w.last_result
    w.last_result = second  # page 2, at the same place
    w._drop_region(_at(second, LOWER_LEFT))
    (text, buttons), = asked
    assert text == book_areas.AREA_QUESTION and buttons == (book_areas.AREA_YES, book_areas.AREA_NO)
    assert not w.pipeline.annotations.areas  # Only this page: the drop alone
    w.last_result = first  # page 1 again, its region found there once more
    w.pipeline.annotations.page(first.units[0].fingerprint, first.units[0].aspect).ignore.clear()
    w.pipeline.save_annotations()
    shown = w.pipeline.process(w.last_result.original, complete=True)
    w.last_result = shown
    w._drop_region(_at(shown, LOWER_LEFT))
    assert len(asked) == 1  # the place said no to is not asked about again in this window
    w._areas_declined = []
    w.pipeline.annotations.page(shown.units[0].fingerprint, shown.units[0].aspect).ignore.clear()
    shown = w.pipeline.process(shown.original, complete=True)
    w.last_result = shown
    drops = len(w.history)
    w._drop_region(_at(shown, LOWER_LEFT))
    assert len(asked) == 2 and len(w.pipeline.annotations.areas) == 1
    assert w.said[-1] == book_areas.AREA_ADDED and len(w.history) == drops + 2  # the drop, then the area
    w.undo_edit()  # the area first
    assert not w.pipeline.annotations.areas and w.said[-1] == book_areas.AREA_BACK
    w.undo_edit()  # then the drop
    assert w.said[-1] == "The dropped region is back." and _near(w.last_result, LOWER_LEFT)


def test_a_rectangle_of_the_readers_own_dropped_asks_nothing(two_pages, monkeypatch):
    w, _second = two_pages
    asked = []
    monkeypatch.setattr(caches, "ask", lambda *a, **k: asked.append(a) or True)
    unit = w.last_result.units[0]
    for page_fp in (unit.fingerprint, "f" * len(unit.fingerprint)):  # dropped on another page before, too
        w.pipeline.annotations.add_box(page_fp, unit.aspect, unit.normalize(LOWER_LEFT), "ignore")
    region = SimpleNamespace(kind="manual", unit=0, bbox=LOWER_LEFT)
    w._offer_ignore_everywhere(region, w.last_result)
    assert not asked
    region.kind = "bubble"
    w._offer_ignore_everywhere(region, w.last_result, SimpleNamespace(state="failed"))
    assert not asked  # a drop that failed asks nothing either
    w._offer_ignore_everywhere(region, w.last_result, SimpleNamespace(state="done"))
    assert len(asked) == 1


# ------------------------------------------------------------------ Book settings
def _book(hidden_root, tmp_path, areas):
    ann = BookAnnotations(tmp_path / "Book.json", "Book")
    for area in areas:
        ann.add_area(area)
    saved, changes = [], []

    def set_book_settings(values):
        ann.settings = dict(values or {})
        return ann.settings

    pipeline = SimpleNamespace(annotations=ann, _base_settings=Settings(), set_book_settings=set_book_settings,
                               save_annotations=lambda: saved.append(1) or ann.save())
    d = book_settings.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: changes.append(1))
    d.withdraw()
    return d, ann, saved, changes


def test_book_settings_lists_the_areas_and_removes_one_with_undo(hidden_root, tmp_path):
    right = BookArea.around((0.4, 0.9, 0.6, 0.96), "right", 0.7)
    every = BookArea(box=(0.05, 0.02, 0.2, 0.06))
    d, ann, saved, changes = _book(hidden_root, tmp_path, [right, every])
    assert d.areas_list.get(0, "end") == ("Right-hand pages: 35-65 % across, 88-98 % down",
                                          "All pages: 5-20 % across, 2-6 % down")
    assert d.areas_list.curselection() == (0,) and not d.no_areas.winfo_manager()
    d._remove_area()
    assert ann.areas == [every] and saved and changes == [1] and d.said_var.get() == book_settings.AREA_REMOVED
    assert BookAnnotations.load(tmp_path / "Book.json").areas == [every]
    assert str(d.undo_btn.cget("state")) == "normal"
    d._undo()
    assert ann.areas == [every, right] and changes == [1, 1] and d.said_var.get() == book_settings.AREA_BACK
    assert str(d.undo_btn.cget("state")) == "disabled" and d.areas_list.size() == 2
    d.areas_list.selection_clear(0, "end")
    d._sync_areas()
    assert "disabled" in d.remove_area_btn.state()
    d._remove_area()  # nothing selected: nothing goes
    assert len(ann.areas) == 2
    d.areas_list.selection_set(0)
    d._remove_area()
    d.areas_list.selection_set(0)
    d._remove_area()
    assert not ann.areas and d.no_areas.winfo_manager() == "pack"  # the line that says there are none
    d.destroy()


def test_book_settings_without_areas_says_how_to_add_one(hidden_root, tmp_path):
    d, _ann, _saved, _changes = _book(hidden_root, tmp_path, [])
    assert d.areas_list.size() == 0 and d.no_areas.winfo_manager() == "pack"
    assert d.no_areas.cget("text") == book_settings.NO_AREAS
    d.destroy()


# ------------------------------------------------------------------ the words
def test_every_word_in_every_language():
    words = [book_areas.IGNORE_EVERYWHERE, book_areas.IGNORE_TIP, book_areas.AREA_QUESTION, book_areas.AREA_YES,
             book_areas.AREA_NO, book_areas.AREA_ADDED, book_areas.AREA_THERE, book_areas.AREA_BACK,
             book_areas.AREA_AGAIN, book_areas.AREA_IN_A_RUN, book_areas.SELECT_FIRST, book_areas.NO_BOOK,
             book_areas.SAVE_FAILED, "Storing your changes...", book_settings.AREAS_HEADING, book_settings.AREA_ROW,
             *book_settings.SIDE_WORDS.values(), book_settings.NO_AREAS, book_settings.REMOVE_AREA,
             book_settings.REMOVE_AREA_TIP, book_settings.AREA_REMOVED, book_settings.AREA_BACK,
             book_settings.AREA_UNDO_TIP]
    import string

    def fields(text):
        return sorted(f for _lit, f, _spec, _conv in string.Formatter().parse(text) if f is not None)

    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(w in catalog for w in words), (code, [w[:40] for w in words if w not in catalog])
            assert all(fields(catalog[w]) == fields(w) for w in words), code
    assert book_settings.AREA_BACK == book_areas.AREA_AGAIN  # one sentence for one thing


def test_the_page_menu_entry_and_its_tip_are_the_windows_own():
    assert app_mod.App.ignore_area_everywhere is book_areas.AreaMixin.ignore_area_everywhere
    assert np.isclose(AREA_INSIDE, 0.7)
