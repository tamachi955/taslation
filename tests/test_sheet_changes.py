"""A rendering changed in the series sheet reaches the lines already translated: the renderings that changed between
two copies of a sheet, the edits that rename them (whole words, nothing written), the offer with its count from the
series sheet dialog, made as one change that Ctrl+Z takes back, and the editor's own rename of a rendering, which
Ctrl+Z now takes back too."""
from __future__ import annotations

import pytest
from helpers import EN_TEXTS, FakeOcr
from test_translator_mode import Window

from taslation.annotations import BookAnnotations, GlossaryStore
from taslation.cache import CachedBubble, CachedPage, CacheStore
from taslation.i18n import CATALOGS
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import translator
from taslation.ui.dialogs import caches, glossary
from taslation.ui.sheet_changes import rename_edits, renamed_pairs, shown_pairs

TEXTS = {**EN_TEXTS, "こんにちは": "Hello there, Piyo!", "ありがとう": "Thank you, Piyo.",
         "どこへ行くの": "Where is Piyoko going?"}


def _sheet(entries=(), characters=()):
    return {"entries": [{"term": t, "rendering": r} for t, r in entries],
            "characters": [{"name": n, "rendering": r} for n, r in characters]}


def test_the_renderings_that_changed_between_two_sheets():
    before = _sheet([("魔法", "magic"), ("剣", "sword")], [("ピヨ", "Piyo"), ("ノワ", "")])
    after = _sheet([("魔法", "sorcery"), ("盾", "shield")], [("ピヨ", "Pyo"), ("ノワ", "Nowa")])
    assert renamed_pairs(before, after) == [("magic", "sorcery"), ("Piyo", "Pyo")]  # added, removed, first given: none
    assert renamed_pairs(after, before) == [("sorcery", "magic"), ("Pyo", "Piyo")]
    assert renamed_pairs(before, before) == [] and renamed_pairs({}, after) == []


def test_rename_edits_take_whole_words_and_change_nothing(tmp_path):
    cache = CacheStore(tmp_path).open("Book", "m")
    cache.add(CachedPage(fingerprint="0" * 80, aspect=0.7, bubbles=[
        CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text="Piyo! Piyoko, Piyo."),
        CachedBubble(box=(0.5, 0.5, 0.7, 0.6), text="Nobody here."),
        CachedBubble(box=(0.1, 0.7, 0.3, 0.8), text="It is Piyo\\1."),
    ]))
    edits = rename_edits(cache, [("Piyo", "Pyo"), ("same", "same")])
    assert [e.new for e in edits] == ["Pyo! Piyoko, Pyo.", "It is Pyo\\1."]  # a backslash stays a backslash
    assert [b.text for b in cache.pages[0].bubbles][0] == "Piyo! Piyoko, Piyo."  # nothing changed yet
    assert len(edits) == cache.rename([("Piyo", "Pyo")])  # the lines the cache's own rename changes
    assert shown_pairs([("a", "b")]) == "a → b"
    assert shown_pairs([(str(i), "x") for i in range(7)]).endswith(", ...")


# ------------------------------------------------------------------ the window
class Renames(Window):
    """Translator mode with what the series sheet's offer and a replacement across the book use."""

    _offer_sheet_renames = app_mod.App._offer_sheet_renames
    _rename_in_book = app_mod.App._rename_in_book
    _propose_renderings = app_mod.App._propose_renderings
    _refresh_premises = app_mod.App._refresh_premises
    _stored = app_mod.App._stored
    _carry_replacement = app_mod.App._carry_replacement

    def __init__(self, pipeline, result, glossary_store=None):
        super().__init__(pipeline, result)
        self.batch, self._batching = None, False
        self.glossary_store = glossary_store
        self.later = []

    def after(self, _ms, job):
        self.later.append(job)

    def _post(self, kind, **data):
        super()._post(kind, **data)
        if kind == "find":
            self.said.extend(key for key, _values in data.get("lines", ()))

    def _job_refresh_premises(self, book, language):
        pass

    def lines(self):
        hit = self.pipeline.cache.pages
        return sorted(b.text for page in hit for b in page.bubbles)


@pytest.fixture
def renames(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(TEXTS, default="ok"), cache=cache,
                        annotations=ann)
    result = pipeline.process(sample_page, complete=True)
    assert sum("Piyo" in b.text for b in cache.pages[0].bubbles) == 3
    return Renames(pipeline, result, GlossaryStore(settings.state_dir / "glossary"))


def _answer(monkeypatch, yes):
    asked = []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append((text, a)) or yes)
    return asked


def test_the_offer_says_how_many_lines_and_applies_as_one_change_ctrl_z_takes_back(renames, monkeypatch):
    w = renames
    start = w.lines()
    asked = _answer(monkeypatch, True)
    w._offer_sheet_renames([("Piyo", "Pyo")], "Book", "English")
    (text, buttons), = asked
    assert text == translator.SHEET_OFFER.format(n=2, changes="Piyo → Pyo")  # "Piyoko" is another word
    assert buttons == (translator.SHEET_APPLY.format(n=2), translator.SHEET_LEAVE)
    assert sum("Pyo" in t for t in w.lines()) == 2 and w.said[-1] == translator.SHEET_APPLIED
    assert sum("Pyo" in (r.translated_text or "") for r in w.last_result.regions) == 2  # the page on show, lettered
    assert CacheStore(w.pipeline.cache.path.parent).open("Book", "m").pages  # written
    w.undo_edit()
    assert w.lines() == start and w.said[-1] == "Replacement taken back in {n} text area(s)."
    w.redo_edit()
    assert sum("Pyo" in t for t in w.lines()) == 2


def test_leave_them_and_no_line_to_change_change_nothing(renames, monkeypatch):
    w = renames
    start = w.lines()
    asked = _answer(monkeypatch, False)
    w._offer_sheet_renames([("Piyo", "Pyo")], "Book", "English")
    assert asked and w.lines() == start and not w.history.done
    asked.clear()
    w._offer_sheet_renames([("Nowa", "Nowe")], "Book", "English")
    assert not asked and not w.history.done  # nothing translated with it: nothing asked


def test_during_a_run_nothing_is_offered_and_a_line_says_why(renames, monkeypatch):
    w = renames
    asked = _answer(monkeypatch, True)
    w._batching = True
    w._offer_sheet_renames([("Piyo", "Pyo")], "Book", "English")
    assert not asked and w.said[-1] == translator.SHEET_IN_A_RUN


def test_the_offer_waits_for_a_page_at_work_and_for_the_books_cache(renames, monkeypatch):
    w = renames
    asked = _answer(monkeypatch, True)
    w.busy = True
    w._offer_sheet_renames([("Piyo", "Pyo")], "Book", "English")
    assert not asked and len(w.later) == 1
    w.busy = False
    w.later.pop()()
    assert len(asked) == 1
    cache, opened = w.pipeline.cache, []
    w.pipeline.set_cache(None)  # another book's, or none yet: the worker opens it first
    w.model_var = type(w.role_var)("m")
    w._ensure_cache = lambda book, model, language: opened.append(book) or w.pipeline.set_cache(cache)
    w._offer_sheet_renames([("Pyo", "Piyo")], "Book", "English")
    assert opened == ["Book"] and len(asked) == 1
    w.later.pop()()
    assert len(asked) == 2


def test_the_series_sheet_dialog_offers_a_changed_rendering_and_its_undo(hidden_root, tmp_path, monkeypatch):
    store = GlossaryStore(tmp_path / "glossary")
    sheet = store.open("Series", "English")
    sheet.set("ピヨ", "Piyo")
    sheet.save()
    offered = []
    d = glossary.GlossaryDialog(hidden_root, store, "Series", "English", on_change=lambda: None,
                                on_renamed=lambda pairs, parent: offered.append((pairs, parent)))
    d.withdraw()
    d.term_var.set("ピヨ")
    d.rend_var.set("Pyo")
    d._set()
    assert offered == [([("Piyo", "Pyo")], d)]
    d.term_var.set("魔法")
    d.rend_var.set("magic")
    d._set()  # a new term: no line has it yet
    assert len(offered) == 1
    d.undo()  # the new term goes: nothing to offer
    assert len(offered) == 1
    d.term_var.set("ピヨ")
    d.rend_var.set("Piyoo")
    d._set()
    d.undo()  # back from "Piyoo": offered the other way
    assert offered[-1][0] == [("Piyoo", "Pyo")]
    d.destroy()


def test_the_editors_rename_of_a_rendering_is_one_change_for_ctrl_z(renames, monkeypatch, settings):
    w = renames
    sheet = w.glossary_store.open("Book", "English")
    sheet.set("ピヨ", "Piyo")
    sheet.save()
    start = w.lines()
    monkeypatch.setattr(translator, "series_key", lambda book: book)
    monkeypatch.setattr(translator, "sheet_item_for", lambda merged, old: ("term", "ピヨ") if old == "Piyo" else None)
    w.pipeline.check_sheet = lambda: sheet
    _answer(monkeypatch, True)
    w._propose_renderings([("Piyo", "Pyo")])
    assert w.glossary_store.open("Book", "English").get("ピヨ").rendering == "Pyo"
    assert sum("Pyo" in t for t in w.lines()) == 2
    assert w.said[-1] == "Series sheet updated; changed in {n} translated line(s). New translations use it."
    w.undo_edit()
    assert w.lines() == start  # the lines; the sheet keeps its new rendering, as it always did


def test_the_offers_lines_are_in_every_language():
    keys = [translator.SHEET_OFFER, translator.SHEET_APPLY, translator.SHEET_LEAVE, translator.SHEET_APPLIED,
            translator.SHEET_IN_A_RUN]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(k in catalog for k in keys), (code, [k for k in keys if k not in catalog])
