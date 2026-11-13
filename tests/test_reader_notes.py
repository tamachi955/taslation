"""Notes for the reader: the translator's own notes kept with a cached translation, which the reader writes and changes
in the editor, and `taslation review --notes` lists. (The model wrote none of its own after 2026-11-06.)"""

from __future__ import annotations

import argparse

from helpers import EN_TEXTS, JA_TEXTS, FakeOcr

from taslation.cache import CachedBubble, CachedPage, CacheStore
from taslation.cli import cmd_review
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.translate.ollama import RESPONSE_SCHEMA, SYSTEM_PROMPT


def test_the_model_is_asked_for_no_notes():
    assert "note" not in RESPONSE_SCHEMA["properties"]["translations"]["items"]["properties"]
    assert "for the reader" not in SYSTEM_PROMPT


def test_the_reader_writes_a_note_and_the_cache_keeps_it(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Note Book", "fake")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    res = p.process(sample_page)
    assert not any(r.reader_note for r in res.regions)  # the model writes none
    r = next(r for r in res.regions if r.source_text == JA_TEXTS[0])
    assert p.set_reader_note(res, r, "a pun on dogs") and r.reader_note == "a pun on dogs"
    stored = CacheStore(settings.cache_dir).open("Note Book", "fake")
    assert [b.note for pg in stored.pages for b in pg.bubbles if b.note] == ["a pun on dogs"]
    again = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator({}), cache=stored)
    res2 = again.process(sample_page)
    assert res2.cache_hits and [x.reader_note for x in res2.regions if x.reader_note] == ["a pun on dogs"]
    r2 = next(x for x in res2.regions if x.reader_note)
    assert again.set_translation(res2, r2, "New words.") and r2.reader_note == "a pun on dogs"  # an edit keeps it
    assert again.set_reader_note(res2, r2, "") and r2.reader_note == ""
    assert not any(b.note for pg in CacheStore(settings.cache_dir).open("Note Book", "fake").pages for b in pg.bubbles)


def test_review_lists_the_notes_on_request(settings, capsys):
    cache = CacheStore(settings.cache_dir).open("Some Book", "m", "English")
    cache.add(CachedPage(fingerprint="a" * 80, aspect=0.7, seq=0, bubbles=[
        CachedBubble(box=(0.1, 0.1, 0.3, 0.3), text="Fine.", note="a pun on cats"),
        CachedBubble(box=(0.5, 0.1, 0.7, 0.3), text="Ok.")]))
    cache.save()
    assert cmd_review(argparse.Namespace(book="Some Book", language="", notes=True), settings) == 0
    out = capsys.readouterr().out
    assert "page 1 bubble 1: note for the reader" in out and "a pun on cats" in out and "1 note(s) for the reader" in out
    assert cmd_review(argparse.Namespace(book="Some Book", language="", notes=False), settings) == 0
    assert "a pun on cats" not in capsys.readouterr().out
