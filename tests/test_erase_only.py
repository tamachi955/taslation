"""The "erase only" kind of a region: its lettering is erased and nothing is set in its place, on a page read anew, a
page from the cache, a whole-book scan (and the page a run shows from it) alike; it never reaches the translator, is
never flagged or counted as untranslated, and the editor's Kind list makes it (the page behind the editor shows it)
as one change that Ctrl+Z takes back. Every other kind letters as before (`test_ink.py`'s golden hashes)."""

from __future__ import annotations

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from test_translator_mode import Window

from taslation.annotations import ERASE_ONLY, REGION_KINDS, BookAnnotations, RegionNote
from taslation.cache import CacheStore
from taslation.i18n import CATALOGS, set_language
from taslation.pipeline import Pipeline, erases, manual_region
from taslation.regions import ERASED
from taslation.translate import DictTranslator
from taslation.ui.dialogs import review
from taslation.ui.progress import STATUS_WORDS, status_word

LOWER_RIGHT = (850, 929, 1110, 1309)  # a bubble of the sample page: 今日はいい天気だね
JAPANESE = "今日はいい天気だね"


def _pipeline(settings, book):
    cache = CacheStore(settings.cache_dir).open(book, "m")
    path = settings.state_dir / "annotations" / f"{book}.json"
    ann = BookAnnotations.load(path) if path.is_file() else BookAnnotations(path, book)
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                    annotations=ann)


def _at(regions, where=LOWER_RIGHT):
    x0, y0, x1, y1 = where
    found = [r for r in regions if x0 <= (r.bbox[0] + r.bbox[2]) / 2 <= x1 and y0 <= (r.bbox[1] + r.bbox[3]) / 2 <= y1]
    assert len(found) == 1, found
    return found[0]


def _ink(image, box):
    """The dark pixels of *image* in *box*: the lettering there."""
    x0, y0, x1, y1 = box
    return int((np.asarray(image.convert("L"))[y0:y1, x0:x1] < 128).sum())


@pytest.fixture
def marked(sample_page, settings):
    """A book whose page has the bubble at LOWER_RIGHT made "erase only" before it was ever read: (pipeline, the
    region's text box on a plain reading)."""
    plain = _pipeline(settings, "Plain").process(sample_page, complete=True)
    region = _at(plain.regions)
    unit = plain.units[region.unit]
    p = _pipeline(settings, "Book")
    p.annotations.page(unit.fingerprint, unit.aspect).notes.append(RegionNote(box=unit.normalize(region.bbox),
                                                                              kind=ERASE_ONLY))
    p.save_annotations()
    return p, region.text_box


def test_erase_only_is_a_kind_of_its_own():
    assert ERASE_ONLY == "erase" and ERASE_ONLY in REGION_KINDS and REGION_KINDS[-1] == ERASE_ONLY
    assert RegionNote.from_json({"box": [0, 0, 0.5, 0.5], "kind": "erase"}).kind == ERASE_ONLY  # kept in the file
    assert status_word(ERASED) == "erase only" and review.kind_of("Erase only") == ERASE_ONLY


def test_a_page_read_anew_erases_it_sets_nothing_and_asks_the_translator_nothing(marked, sample_page):
    p, text_box = marked
    result = p.process(sample_page, complete=True)
    region = _at(result.regions)
    assert region.status == ERASED and region.tag == ERASE_ONLY and not region.flags and erases(region)
    assert all(JAPANESE not in texts for texts in p.translator.calls)  # never sent
    assert region not in result.translated and len(result.translated) == len(result.regions) - 1
    assert _ink(sample_page, text_box) > 100 and _ink(result.image, text_box) == 0  # erased, nothing set
    assert not any(row[0] is region for row in review.review_rows(result.regions))  # nothing to look at
    unit = result.units[region.unit]
    hit = p.cache.lookup(unit.fingerprint, unit.aspect, 36)
    assert len(hit[0].bubbles) == len(result.regions) - 1  # no translation kept for it
    # shown again from the cache: the same
    asked = len(p.translator.calls)
    again = p.process(sample_page, complete=True)
    assert _at(again.regions).status == ERASED and _ink(again.image, text_box) == 0
    assert len(p.translator.calls) == asked
    fresh = _pipeline(p.settings, "Book")  # a new window on the same stores: from the cache, not from memory
    shown = fresh.process(sample_page, complete=True)
    assert _at(shown.regions).status == ERASED and np.array_equal(np.asarray(shown.image), np.asarray(again.image))
    assert not fresh.translator.calls


def test_a_whole_book_scan_neither_translates_it_nor_counts_it_and_erases_it_ahead(marked, sample_page):
    p, text_box = marked
    scan = p.scan(sample_page, keep_regions=True)
    regions = [r for u in scan.units for r in u.regions]
    region = _at(regions)
    assert region.status == ERASED and not region.is_japanese
    assert all(r.source_text != JAPANESE for u in scan.units for r in u.japanese())  # the run never sends it
    assert scan.bubbles == len(regions) - 1
    assert _at(scan.erasable).tag == ERASE_ONLY  # erased ahead with the others
    # the page the run shows once the others are translated: erased there too
    p.process(sample_page, complete=True)
    shown = p.translated_page(sample_page, scan.erasable)
    assert shown is not None and _ink(shown, text_box) == 0
    # a page whose only region is "erase only" is still shown erased
    alone = [r for r in scan.erasable if r.tag == ERASE_ONLY]
    assert _ink(p.translated_page(sample_page, alone), text_box) == 0


def test_the_kind_set_and_taken_off_in_the_pipeline(sample_page, settings):
    p = _pipeline(settings, "Book")
    result = p.process(sample_page, complete=True)
    region = _at(result.regions)
    text = region.translated_text
    asked = len(p.translator.calls)
    assert p.set_region_note(result, region, kind=ERASE_ONLY)
    assert region.status == ERASED and region.translated_text == text  # its translation kept for later
    assert p.ask_again(result, region) == "" and len(p.translator.calls) == asked  # not even when asked
    assert p.set_translation(result, region, "Typed in.") and region.status == ERASED  # kept, not set
    p.rerender(result)
    assert _ink(result.image, region.text_box) == 0
    assert p.set_region_note(result, region, kind="speech")
    assert region.status == "translated" and region.translated_text == "Typed in."
    p.rerender(result)
    assert _ink(result.image, region.text_box) > 0  # lettered again
    region.translated_text = ""
    p.set_region_note(result, region, kind=ERASE_ONLY)
    p.set_region_note(result, region, kind="")
    assert region.status == "untranslated"  # nothing to set: it waits for a translation


# ------------------------------------------------------------------ translator mode and the editor
@pytest.fixture
def window(sample_page, settings):
    p = _pipeline(settings, "Book")
    return Window(p, p.process(sample_page, complete=True))


def _data(region, kind):
    return {"text": region.translated_text, "speaker": region.speaker, "kind": kind, "continues": False, "note": "",
            "reader_note": "", "style": None}


def test_the_editors_save_makes_it_erase_only_and_ctrl_z_takes_it_back(window):
    w = window
    start, picture = w.state(), np.asarray(w.last_result.image).copy()
    region = _at(w.last_result.regions)
    asked = len(w.pipeline.translator.calls)
    w._edit_region(region, _data(region, ERASE_ONLY))
    assert region.status == ERASED and _ink(w.last_result.image, region.text_box) == 0
    assert len(w.history) == 1 and len(w.pipeline.translator.calls) == asked
    made = w.state()
    w.undo_edit()
    assert region.status == "translated" and region.tag == "" and w.state() == start
    assert np.array_equal(np.asarray(w.last_result.image), picture)
    w.redo_edit()
    assert region.status == ERASED and w.state() == made and _ink(w.last_result.image, region.text_box) == 0
    again = w.pipeline.process(w.last_result.original, complete=True)  # and the next reading keeps it so
    assert _at(again.regions).status == ERASED and len(w.pipeline.translator.calls) == asked


def _region(tag=""):
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text, r.tag = "translated", "Nice weather today, huh?", JAPANESE, tag
    return r


def test_the_editors_kind_list_has_it_and_the_page_behind_shows_it_erased(hidden_root):
    shown = []
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_preview=lambda text, style: shown.append(text), place=(1, 2))
    assert "Erase only" in d.kind_box.cget("values") and d.kind_box.bind("<<ComboboxSelected>>")
    d.kind_var.set("Erase only")
    d._preview()
    assert shown[-1] == "" and d._data()["kind"] == ERASE_ONLY
    d.kind_var.set("Speech")
    d._preview()
    assert shown[-1] == "Nice weather today, huh?"
    d.destroy()
    set_language("ja")
    d = review.EditBubbleDialog(hidden_root, _region(ERASE_ONLY), [], on_save=lambda data: None, on_drop=lambda: None,
                                place=(1, 2))
    assert d.kind_var.get() == "消去のみ"
    d.destroy()
    set_language("en")


def test_the_review_list_and_the_counts_leave_it_out():
    r = _region(ERASE_ONLY)
    r.status, r.flags, r.reader_note = ERASED, ["ocr-unsure"], "a note"
    assert review.review_rows([r]) == []


def test_every_word_in_every_language():
    words = ["Erase only", review.ERASE_ONLY_TIP, STATUS_WORDS[ERASED], review.REGION_KIND_WORDS[ERASE_ONLY]]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(w in catalog for w in words), (code, [w[:40] for w in words if w not in catalog])
