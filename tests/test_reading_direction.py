"""A book's reading direction (`BookAnnotations.reading_direction`, Book settings' row): right to left until it is set,
kept in the book's annotations; left to right puts the left page of a spread first (`fingerprint.split_spread`) and
the bubbles of a page in left-to-right order, on a fresh page and on one from the cache alike, while every page keeps
its fingerprint; right to left reads as it always did. On the real pipeline and stores, with stand-in OCR and
translator."""

from __future__ import annotations

import string

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image

from taslation import fingerprint as fp
from taslation.annotations import AnnotationStore, BookAnnotations, page_side, unit_side
from taslation.cache import CacheStore
from taslation.detect.bubbles import order_on_page
from taslation.i18n import CATALOGS
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui.dialogs import book_settings as book_dlg


def _spread(right: Image.Image, left: Image.Image) -> Image.Image:
    """The two pages side by side on a dark viewer, *right* on the right, a gutter between them."""
    w, h = right.size
    spread = Image.new("RGB", (w * 2 + 60, h + 40), (30, 30, 30))
    spread.paste(left, (0, 20))
    spread.paste(right, (w + 60, 20))
    return spread


def _pipeline(settings, direction: str = "", book: str = "Book"):
    ann = BookAnnotations(settings.state_dir / f"{book}.json", book)
    ann.reading_direction = direction
    cache = CacheStore(settings.cache_dir).open(book, "m")
    tr = DictTranslator(EN_TEXTS, default="ok")
    return Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache, annotations=ann), ann, cache, tr


def _texts(result) -> list:
    return [r for r in result.regions if r.status == "translated"]


# ------------------------------------------------------------------ the setting
def test_a_book_reads_right_to_left_until_its_direction_is_set(settings, tmp_path):
    ann = BookAnnotations(tmp_path / "Book.json", "Book")
    assert ann.reading_direction == "" and ann.rtl
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS))
    assert pipeline.annotations is None and pipeline.rtl  # no book's annotations: right to left
    assert not pipeline.set_reading_direction("ltr")  # nothing to keep it in
    ann.reading_direction = "sideways"
    ann.save()
    assert BookAnnotations.load(ann.path).reading_direction == ""  # what is no direction loads as none


def test_the_direction_is_saved_with_the_book_and_loaded_again(settings):
    store = AnnotationStore(settings.annotations_dir)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), annotations=store.open("Book 1"))
    assert not pipeline.set_reading_direction("rtl")  # the direction in force already: nothing changes
    assert not pipeline.set_reading_direction("up") and not pipeline.set_reading_direction("")
    assert not (settings.annotations_dir).exists() or store.list() == []  # nothing written for nothing
    assert pipeline.set_reading_direction("ltr") and not pipeline.rtl
    again = store.open("Book 1")
    assert again.reading_direction == "ltr" and not again.rtl
    assert store.open("Book 2").reading_direction == ""  # another book keeps its own
    pipeline.set_annotations(again)
    assert pipeline.set_reading_direction("rtl") and pipeline.rtl
    assert store.open("Book 1").reading_direction == "rtl"


# ------------------------------------------------------------------ a spread's pages
def test_a_left_to_right_spread_comes_left_page_first_with_the_same_fingerprints(sample_page, sample_page2):
    rgb = np.asarray(_spread(sample_page, sample_page2))
    rtl, ltr = fp.analyze(rgb), fp.analyze(rgb, rtl=False)
    assert [u.index for u in ltr] == [0, 1] and ltr[0].box[2] < ltr[1].box[0]  # the left page first
    assert [(u.box, u.fingerprint) for u in ltr] == [(u.box, u.fingerprint) for u in reversed(rtl)]
    gray = np.asarray(_spread(sample_page, sample_page2).convert("L"))
    box = (0, 0, gray.shape[1], gray.shape[0])
    assert fp.split_spread(gray, box, rtl=False) == fp.split_spread(gray, box)[::-1]
    # the sides of a spread are where the pages lie, whichever comes first
    assert [unit_side(u, ltr) for u in ltr] == ["left", "right"]
    assert [unit_side(u, rtl) for u in rtl] == ["right", "left"]
    assert [page_side(i, 2, rtl=False) for i in (0, 1)] == ["left", "right"]
    assert unit_side(rtl[0], rtl[:1]) == "" and unit_side(rtl[0], [ltr[0], ltr[1]]) == ""  # alone; not one of them


def test_a_right_to_left_book_reads_its_spread_and_bubbles_as_before(settings, sample_page, sample_page2):
    rgb = np.asarray(_spread(sample_page, sample_page2))
    before = fp.analyze(rgb)
    assert [(u.index, u.box, u.fingerprint) for u in fp.analyze(rgb, rtl=True)] == \
        [(u.index, u.box, u.fingerprint) for u in before]
    assert before[0].box[0] > before[1].box[2]  # the right page first
    assert [page_side(i, 2) for i in (0, 1)] == ["right", "left"] == [unit_side(u, before) for u in before]
    unknown, _ann, cache, _tr = _pipeline(settings, "", "Unknown")
    told, _ann2, _cache2, _tr2 = _pipeline(settings, "rtl", "Told")
    a, b = unknown.process(_spread(sample_page, sample_page2)), told.process(_spread(sample_page, sample_page2))
    assert a.fingerprints == b.fingerprints == [u.fingerprint for u in before]
    assert [(r.bbox, r.unit) for r in a.regions] == [(r.bbox, r.unit) for r in b.regions]
    assert {p.fingerprint: p.seq for p in cache.pages} == {before[0].fingerprint: 0, before[1].fingerprint: 1}


def test_a_left_to_right_spread_is_read_kept_and_recorded_left_page_first(settings, sample_page, sample_page2):
    pipeline, ann, cache, tr = _pipeline(settings, "ltr")
    spread = _spread(sample_page, sample_page2)
    left, right = fp.analyze(np.asarray(spread), rtl=False)
    result = pipeline.process(spread)
    assert result.fingerprints == [left.fingerprint, right.fingerprint]
    units = [r.unit for r in result.regions]
    assert units == sorted(units) and set(units) == {0, 1}  # the left page's bubbles first
    assert all(r.bbox[2] <= left.box[2] + 2 for r in result.regions if r.unit == 0)
    assert {p.fingerprint: p.seq for p in cache.pages} == {left.fingerprint: 0, right.fingerprint: 1}
    pipeline.scan(spread, skip_cached=False)
    assert [f for f, _a in ann.sequence] == [left.fingerprint, right.fingerprint]


# ------------------------------------------------------------------ a page's bubbles
def test_left_to_right_orders_the_bubbles_from_the_left_fresh_and_from_the_cache(settings, sample_page):
    pipeline, _ann, cache, tr = _pipeline(settings)
    rgb = np.asarray(sample_page)
    rtl = _texts(pipeline.process(sample_page))
    assert len(rtl) >= 3 and len(tr.calls) == 1
    (unit,) = fp.analyze(rgb)
    assert [r.bbox for r in rtl] == [r.bbox for r in order_on_page(rgb, unit.box, list(rtl), rtl=True)]
    assert pipeline.set_reading_direction("ltr")
    cached = _texts(pipeline.process(sample_page))  # from the cache: nothing translated again ...
    assert len(tr.calls) == 1 and all(r.from_cache for r in cached)
    expected = [r.bbox for r in order_on_page(rgb, unit.box, list(cached), rtl=False)]
    assert [r.bbox for r in cached] == expected != [r.bbox for r in rtl]  # ... in the new order
    assert {r.bbox: r.translated_text for r in cached} == {r.bbox: r.translated_text for r in rtl}
    fresh = _texts(pipeline.process(sample_page, use_cache=False))  # read and translated anew: the same order
    assert [r.bbox for r in fresh] == expected and [r.order for r in fresh] == list(range(len(fresh)))
    assert len(cache.pages) == 1 and cache.pages[0].seq == 0  # the page keeps its entry and its number


# ------------------------------------------------------------------ Book settings
@pytest.fixture
def no_placing(monkeypatch):
    monkeypatch.setattr(book_dlg, "place_window", lambda win, parent=None: None)


def test_book_settings_sets_the_reading_direction(hidden_root, settings, no_placing):
    pipeline, ann, _cache, _tr = _pipeline(settings)
    ann.save()
    changes = []
    d = book_dlg.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: changes.append(1))
    d.withdraw()
    assert d.direction_var.get() == book_dlg.DIRECTIONS["rtl"] and d.direction() == "rtl"
    assert list(d.direction_box.cget("values")) == list(book_dlg.DIRECTIONS.values())
    d._apply()  # as it was: the book's direction stays unset
    assert ann.reading_direction == "" and changes == [1]
    d = book_dlg.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: changes.append(2))
    d.withdraw()
    d.direction_var.set(book_dlg.DIRECTIONS["ltr"])
    d._apply()
    assert not pipeline.rtl and changes == [1, 2] and BookAnnotations.load(ann.path).reading_direction == "ltr"
    d = book_dlg.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: None)
    d.withdraw()
    assert d.direction() == "ltr" and d.direction_var.get() == book_dlg.DIRECTIONS["ltr"]
    d.destroy()


def test_book_settings_shows_the_direction_in_the_window_language(hidden_root, settings, no_placing):
    from taslation.i18n import set_language

    pipeline, ann, _cache, _tr = _pipeline(settings, "ltr")
    set_language("ja")
    d = book_dlg.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: None)
    d.withdraw()
    assert d.direction_var.get() == CATALOGS["ja"][book_dlg.DIRECTIONS["ltr"]] and d.direction() == "ltr"
    d.direction_var.set(CATALOGS["ja"][book_dlg.DIRECTIONS["rtl"]])
    d._apply()
    assert pipeline.rtl and ann.reading_direction == "rtl"


def test_the_direction_s_words_are_in_every_language():
    words = [book_dlg.DIRECTION_LABEL, *book_dlg.DIRECTIONS.values(), book_dlg.DIRECTION_TIP]

    def fields(text):
        return sorted(f for _lit, f, _spec, _conv in string.Formatter().parse(text) if f is not None)

    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(w in catalog for w in words), (code, [w[:40] for w in words if w not in catalog])
            assert all(fields(catalog[w]) == fields(w) for w in words), code
