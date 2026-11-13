"""What the pipeline says: its stages as Messages with the English of before, the error of a page, a page's line."""
from __future__ import annotations

from helpers import EN_TEXTS, FailingTranslator, FakeOcr

from taslation.messages import Message
from taslation.pipeline import Pipeline, summary
from taslation.translate import DictTranslator


def test_the_stages_are_messages_with_the_words_of_before(sample_page, settings):
    said: list[Message] = []
    res = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS)).process(
        sample_page, use_cache=False, progress=said.append)
    codes = [m.code for m in said]
    assert codes[0] == "pipeline.stage_finding" and codes[-1] == "pipeline.stage_rendering"
    reading = [m for m in said if m.code == "pipeline.stage_reading"]
    n = len(res.regions)
    assert [dict(m.params) for m in reading] == [{"done": i + 1, "total": n} for i in range(n)]
    assert reading[0] == f"Reading text 1/{n}..." and said[0] == "Finding bubbles..." and said[-1] == "Rendering..."
    (asked,) = [m for m in said if m.code == "pipeline.stage_translating"]
    assert dict(asked.params) == {"bubbles": len(res.translated), "translator": "dict"}
    assert asked == f"Translating {len(res.translated)} bubble(s) with dict..."


def test_a_failed_page_carries_the_message_of_its_error(sample_page, settings):
    res = Pipeline(settings, ocr=FakeOcr(), translator=FailingTranslator()).process(sample_page, use_cache=False)
    assert isinstance(res.error, Message) and res.error.code == "translator.failed"
    assert res.error == "cannot reach Ollama (test)"
    res = Pipeline(settings, ocr=FakeOcr(), translator=None).process(sample_page, use_cache=False)
    assert res.error.code == "pipeline.no_translator" and res.error == "no translator configured"


def test_a_page_s_line(sample_page, settings):
    from taslation.cache import CacheStore

    cache = CacheStore(settings.cache_dir).open("Summary", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    first = summary(pipeline.process(sample_page))
    assert first.code == "pipeline.translated" and first.params["bubbles"] >= 6 and first.params["new"] == 1
    assert first.params["error"] == "" and [s.code for s in first.sentences()] == ["pipeline.translated"]
    again = summary(pipeline.process(sample_page))
    assert again.code == "pipeline.from_cache" and again.params["cached"] == 1 and again.params["new"] == 0
    assert str(again) == f"{again.params['bubbles']} line(s) shown from earlier translations."
    failed = summary(Pipeline(settings, ocr=FakeOcr(), translator=FailingTranslator()).process(sample_page,
                                                                                               use_cache=False))
    assert [s.code for s in failed.sentences()] == ["pipeline.translated", "pipeline.page_error"]
    assert str(failed).endswith(" - cannot reach Ollama (test)")
