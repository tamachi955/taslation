"""A name or term the model spelt another way, put right as the series sheet spells it (`terms.spelt_right`, no model
request): in a page translated alone as in a whole-book run, by the same rules and the same guards (only what the
Japanese line names, never another of the sheet's renderings, never a name with an honorific after it). A page shown
from the cache keeps what is stored. Invented names only."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from helpers import EN_TEXTS, JA_TEXTS, FakeOcr

from taslation.annotations import Glossary
from taslation.cache import BookCache, CacheStore
from taslation.pipeline import Pipeline
from taslation.regions import PageResult, TextRegion
from taslation.terms import spelt_right
from taslation.translate import DictTranslator

SHEET = {
    "entries": [{"term": "魔法少女", "rendering": "magical girl"}],
    "characters": [{"name": "竜司", "rendering": "Ryūji"}, {"name": "春香", "rendering": "Haruka"},
                   {"name": "春樹", "rendering": "Haruki"}],
}
NAMED = "竜司が来た"  # a line that names a character of the sheet; the model below spells him "Ryuji"


def sheet() -> Glossary:
    g = Glossary(Path("sheet.json"), "Some Series", "English")
    g.apply_json(SHEET)
    return g


def _region(source: str, row: int = 0) -> TextRegion:
    y0 = 300 * row
    return TextRegion(0, y0, 400, y0 + 300, np.full((300, 400), 255, np.uint8), (100, y0 + 100, 300, y0 + 200),
                      status="untranslated", source_text=source)


def test_the_sheets_spelling_goes_in_and_what_only_resembles_it_stays():
    g = sheet()
    assert spelt_right(g, NAMED, "Ryuji is here.") == "Ryūji is here."
    assert spelt_right(g, "竜司の鞄", "That's Ryuji's bag.") == "That's Ryūji's bag."  # a possessive
    assert spelt_right(g, "魔法少女だ", "A magic girl.") == "A magical girl."  # a term, as the batch has it
    assert spelt_right(g, "竜神さまだ", "It's Ryujin.") == "It's Ryujin."  # the line names no one of the sheet
    assert spelt_right(g, "春香が来た", "Haruki is here.") == "Haruki is here."  # another character's rendering
    assert spelt_right(g, "竜司さん！", "Ryuji-san!") == "Ryuji-san!"  # a name with an honorific: the model's to say
    assert spelt_right(None, NAMED, "Ryuji is here.") == "Ryuji is here." and spelt_right(g, NAMED, "") == ""


def test_a_page_translated_alone_gets_the_sheets_spelling_without_a_model_request(settings):
    tr = DictTranslator({NAMED: "Ryuji is here.", "竜神さまだ": "It's Ryujin.", "春香が来た": "Haruki is here."})
    p = Pipeline(settings, ocr=None, translator=tr)
    p.glossary = sheet()
    named, lookalike, other = _region(NAMED), _region("竜神さまだ", 1), _region("春香が来た", 2)
    assert p._translate_regions([named, lookalike, other], lambda _m: None) == ""
    assert named.translated_text == "Ryūji is here." and "rendering" not in named.flags
    assert lookalike.translated_text == "It's Ryujin." and lookalike.flags == []
    assert other.translated_text == "Haruki is here." and "rendering" in other.flags  # flagged, not rewritten
    assert len(tr.calls) == 1  # the one request: nothing was asked again
    assert p.context_pairs()[0] == (NAMED, "Ryūji is here.")  # the next page's context has the sheet's spelling


def test_the_page_stores_the_sheets_spelling_and_a_cached_page_stays_as_stored(sample_page, settings):
    ocr = FakeOcr([NAMED, *JA_TEXTS[1:]])
    tr = DictTranslator({**EN_TEXTS, NAMED: "Ryuji is here."})
    cache = CacheStore(settings.cache_dir).open("Some Book", "dict")
    p = Pipeline(settings, ocr=ocr, translator=tr, cache=cache)
    p.glossary = sheet()
    res = p.process(sample_page)
    shown = [r.translated_text for r in res.translated]
    assert "Ryūji is here." in shown and "Ryuji is here." not in shown
    assert [b.text for b in cache.pages[0].bubbles].count("Ryūji is here.") == shown.count("Ryūji is here.")

    other = CacheStore(settings.cache_dir).open("Another Book", "dict")  # stored before the sheet had the name
    Pipeline(settings, ocr=FakeOcr([NAMED, *JA_TEXTS[1:]]), translator=tr, cache=other).process(sample_page)
    assert "Ryuji is here." in [b.text for b in other.pages[0].bubbles]
    asked = len(tr.calls)
    later = Pipeline(settings, ocr=FakeOcr([NAMED, *JA_TEXTS[1:]]), translator=tr, cache=BookCache.load(other.path))
    later.glossary = sheet()
    again = later.process(sample_page)
    assert again.cache_hits == 1 and len(tr.calls) == asked  # from the cache: no request, nothing respelt
    assert "Ryuji is here." in [r.translated_text for r in again.translated]


class _Viewer:
    """A book of two pages: the person at the viewer moves `index` (`helpers.read_book`)."""

    def __init__(self, pages):
        self.pages = pages
        self.index = 0

    def capture(self, hwnd):
        return self.pages[self.index]


def test_a_whole_book_run_and_a_page_by_page_run_spell_alike(sample_page, sample_page2, settings, monkeypatch):
    from helpers import read_book

    from taslation import batch as batch_mod
    from taslation.batch import BatchReader

    settings.settle_ms, settings.page_turn_wait_ms = 10, 300
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    stored = {}
    for whole in (True, False):
        viewer = _Viewer([sample_page, sample_page2])
        monkeypatch.setattr(batch_mod, "capture_window", viewer.capture)
        cache = CacheStore(settings.cache_dir).open(f"Book {whole}", "dict")
        p = Pipeline(settings, ocr=FakeOcr([NAMED, *JA_TEXTS[1:]]),
                     translator=DictTranslator({**EN_TEXTS, NAMED: "Ryuji is here."}), cache=cache)
        p.glossary = sheet()
        progress = read_book(BatchReader(p, hwnd=1, settings=settings, context_mode=whole))
        assert progress.finished and progress.pages == 2, progress
        stored[whole] = sorted(b.text for page in cache.pages for b in page.bubbles)
    assert stored[True] == stored[False] and "Ryūji is here." in stored[True] and "Ryuji is here." not in stored[True]


def test_asking_again_is_spelt_as_the_sheet_spells(settings):
    tr = DictTranslator({NAMED: "Ryuji is here."})
    p = Pipeline(settings, ocr=None, translator=tr)
    region = _region(NAMED)
    result = PageResult(image=None, original=None, regions=[region])
    assert p.ask_again(result, region) == "Ryuji is here."  # no sheet: as the model wrote it
    p.glossary = sheet()
    assert p.ask_again(result, region) == "Ryūji is here."
