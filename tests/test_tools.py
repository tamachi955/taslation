"""The translator's tools: the review list's rows, one bubble asked again or given alternatives, and the edit history."""

from __future__ import annotations

from helpers import EN_TEXTS, JA_TEXTS, FakeOcr

from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui.history import EditHistory, Step


def test_edit_history_keeps_what_changed_and_gives_it_back_newest_first():
    h = EditHistory(limit=2)
    page, book = [("a" * 80, 0.7)], ("Book", "Book", "English")
    steps = [h.record(Step(kind, None, book, page)) for kind in ("edit", "move", "drop")]
    assert len(h) == 2 and [s.kind for s in h.done] == ["move", "drop"]  # the limit
    steps[2].state = "empty"  # nothing changed: not kept
    assert h.last(page, book) is steps[1] and len(h) == 1
    h.taken_back(steps[1])
    assert h.last(page, book) is None and h.last(page, book, undone=True) is steps[1]
    h.made_again(steps[1])
    assert h.last(page, book) is steps[1] and h.last(page, book, undone=True) is None


def test_one_bubble_asked_again(sample_page, settings):
    ja = JA_TEXTS[0]
    tr = DictTranslator(EN_TEXTS)
    cache = CacheStore(settings.cache_dir).open("Tools Book", "fake")
    p = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache)
    res = p.process(sample_page)
    region = next(r for r in res.regions if r.source_text == ja)
    assert region.translated_text == "Hello there!"
    assert not hasattr(p, "alternatives")  # no alternatives since 2026-11-06
    assert p.ask_again(res, region) == "Hello there!" and tr.calls[-1] == [ja]
    later = [r for r in res.regions if r.status == "translated"][-1]
    assert p.page_context(res, later) and all(src != later.source_text for src, _t in p.page_context(res, later))
    assert p.page_context(res, region) == []  # the first line has nothing before it
    region.source_text = ""
    assert p.ask_again(res, region) == ""
    p2 = Pipeline(settings, ocr=None, translator=None)
    assert p2.ask_again(res, region) == ""


def test_review_rows_list_the_regions_worth_a_look():
    from taslation.ui.app import review_rows

    class R:
        def __init__(self, order, status, flags=(), note="", text="t"):
            self.order, self.status, self.flags, self.reader_note, self.translated_text = order, status, list(flags), note, text

    rows = review_rows([R(0, "translated"), R(1, "translated", ["small"]), R(2, "untranslated"), R(3, "translated", note="a pun"),
                        R(4, "dropped", ["small"]), R(5, "not-japanese")])
    assert [r.order for r, _why, _t in rows] == [1, 2, 3]
    assert "readable size" in rows[0][1] and rows[1][1] == "untranslated" and rows[2][1] == "note for the reader"
