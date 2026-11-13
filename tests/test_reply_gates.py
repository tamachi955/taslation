"""What is no translation (`is_real_translation`): Han or Hangul in a target written without them, unless the series
sheet has that rendering; a reply running in a loop; the same line stretched is none of those. A line that fails is
asked for again, and one that still fails stays unstored, its page marked incomplete. The translation pass carries the last pairs along, so
that a request extends the last one's prompt."""
from __future__ import annotations

import pytest
from helpers import EN_TEXTS, JA_TEXTS, FakeOcr, read_book
from test_batch import _fake_viewer
from test_reask import Scripted

from taslation.annotations import CharacterSheet, Glossary, GlossaryEntry
from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline, foreign_script, is_real_translation, looping_reply
from taslation.translate import DictTranslator
from taslation.ui.constants import LANGUAGES

LETTERS = {"Chinese (Simplified)": "没事的", "Chinese (Traditional)": "沒事的", "Korean": "괜찮아", "Russian": "Всё хорошо",
           "Thai": "ไม่เป็นไร", "Arabic": "لا بأس", "Hebrew": "זה בסדר", "Hindi": "कोई बात नहीं", "Bengali": "ঠিক আছে",
           "Vietnamese": "Không sao đâu", "Turkish": "Sorun değil", "Polish": "Wszystko dobrze"}


def sheet(tmp_path, rendering="剣") -> Glossary:
    g = Glossary(tmp_path / "s.json", "s")
    g.entries.append(GlossaryEntry("つるぎ", rendering))
    return g


# ---------------------------------------------------------------------------------------- the target's own script
@pytest.mark.parametrize("language", LANGUAGES)
def test_a_good_line_passes_in_every_target(language):
    assert is_real_translation("大丈夫だよ", LETTERS.get(language, "It's all right."), language)


@pytest.mark.parametrize("language", LANGUAGES)
def test_han_and_hangul_are_judged_only_where_the_target_has_neither(language):
    in_writing = language.startswith(("Chinese", "Korean"))
    assert is_real_translation("大丈夫だよ", "OK 没事的", language) is in_writing
    assert is_real_translation("大丈夫だよ", "OK 괜찮아", language) is in_writing


@pytest.mark.parametrize("language", ["Cantonese", "日本語", "Japanese", "ja", "繁體中文", "한국어", "Klingon", ""])
def test_a_target_not_known_to_lack_them_is_not_judged(language):
    assert not foreign_script("没事的", language) and not foreign_script("괜찮아", language)


def test_kana_still_fails_for_chinese_and_korean():
    assert not is_real_translation("こんにちは", "你好です", "Chinese (Simplified)")
    assert not is_real_translation("こんにちは", "안녕ね", "Korean")


def test_the_sheet_may_keep_a_rendering(tmp_path):
    g = sheet(tmp_path)
    assert not is_real_translation("つるぎだ", "It is the 剣.")
    assert is_real_translation("つるぎだ", "It is the 剣.", sheet=g)
    assert not is_real_translation("つるぎだ", "It is the 剣 of 王.", sheet=g)  # the rest is not on the sheet
    named = Glossary(tmp_path / "n.json", "n")
    named.characters.append(CharacterSheet("あおい", rendering="葵", addresses={"れん": "蓮君"}))
    assert is_real_translation("あおい", "葵 and 蓮君", sheet=named)
    assert not is_real_translation("あおい", "葵 and 蓮", sheet=named)  # 蓮君 is the rendering, 蓮 alone is not


def test_the_pipeline_reads_its_own_sheet(tmp_path, settings):
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS))
    assert not pipeline.real_translation("つるぎだ", "It is the 剣.")
    pipeline.glossary = sheet(tmp_path)
    assert pipeline.real_translation("つるぎだ", "It is the 剣.")


# ------------------------------------------------------------------------------------------ a reply in a loop
@pytest.mark.parametrize("line", ["Aaaaaaah!", "Hmmmmmmm...", "Zzzzzzz", "NOOOOOOOOOO!", "Ha ha ha ha ha!", "Hahahahaha!",
                                  "Stop, stop, stop, stop!", "No no no no no!", "........", "I'm sorry, I'm sorry."])
def test_a_stretched_word_is_no_loop(line):
    assert not looping_reply(line, "ああっ") and is_real_translation("ああっ", line)


def test_the_reading_rule_stays_stricter_than_the_replys():
    assert not looping_reply("Aaaaaaah!")


@pytest.mark.parametrize("line", ["N" + "o" * 40, "!" * 20, "I will always be with you " * 4, "ab" * 40,
                                  "It was fine. " + "Yes and no. " * 12])
def test_a_reply_in_a_loop_fails(line):
    assert looping_reply(line, "ああっ") and not is_real_translation("ああっ", line)


def test_a_line_the_japanese_repeats_may_repeat():
    source = "ごめん" * 8
    assert not looping_reply("I'm sorry, " * 8, source)
    assert not looping_reply("A" * 30, "あ" * 20) and looping_reply("A" * 41, "あ" * 20)


# --------------------------------------------------------------------------------------- what a failing line gets
def looped(answers):
    """A translator whose first reply loops on the first line; asked again, *answers* says what comes."""
    def answer(texts, call):
        if call == 1:
            return ["No " * 40 if i == 0 else f"line {i}" for i in range(len(texts))]
        return [answers for _ in texts]
    return Scripted(answer)


def test_a_failing_line_is_asked_for_again(sample_page, settings):
    tr = looped("Fine now.")
    res = Pipeline(settings, ocr=FakeOcr(), translator=tr).process(sample_page, use_cache=False)
    assert len(tr.calls) == 2 and len(tr.calls[1]["texts"]) == 1
    assert "Fine now." in [r.translated_text for r in res.translated] and not res.error


def test_a_line_that_still_fails_stays_unstored_and_marks_the_page(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Gate Book", "fake")
    tr = looped("没事的")
    res = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache).process(sample_page)
    assert sum(r.status == "untranslated" for r in res.regions) == 1
    page = cache.pages[0] if isinstance(cache.pages, list) else next(iter(cache.pages.values()))
    assert page.incomplete and len(page.bubbles) == len(res.translated)
    assert not any("没" in b.text or "No No" in b.text for b in page.bubbles)


# -------------------------------------------------------------------------------------------------- the batch
class Recording(DictTranslator):
    """Remembers the context of each request; *bad* (a function of the line) gives a reply the gates refuse."""

    def __init__(self, *args, bad=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.contexts: list[list[tuple[str, str]]] = []
        self.bad = bad

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, **kwargs):
        self.contexts.append(list(context))
        out = super().translate_page(texts, context, notes, upcoming, meta=meta, **kwargs)
        return ["没事的" if self.bad and self.bad(t) else o for t, o in zip(texts, out)]


def test_the_translation_pass_carries_the_last_pairs(sample_page, sample_page2, settings, monkeypatch):
    viewer = _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    settings.chunk_bubbles = 6  # a run a page
    settings.context_pairs = 4
    tr = Recording(EN_TEXTS)
    cache = CacheStore(settings.cache_dir).open("Steps", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache)
    assert read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True)).finished
    assert [len(c) for c in tr.contexts[:3]] == [0, 4, 4]
    settings.context_pairs, viewer.index = 40, 0
    tr = Recording(EN_TEXTS)
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=CacheStore(settings.cache_dir).open("Grows", "fake"))
    assert read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True)).finished
    assert [len(c) for c in tr.contexts[:3]] == [0, 6, 12] and tr.contexts[2][:6] == tr.contexts[1]


def test_a_refused_line_of_the_batch_stays_unstored_and_marks_its_page(sample_page, sample_page2, settings, monkeypatch):
    _fake_viewer(sample_page, sample_page2, settings, monkeypatch)
    line = JA_TEXTS[0]
    tr = Recording(EN_TEXTS, bad=lambda t: t == line)
    cache = CacheStore(settings.cache_dir).open("Refused", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=tr, cache=cache)
    assert read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False)).finished
    assert any(page.incomplete for page in cache.pages)
    assert not any("没" in b.text for page in cache.pages for b in page.bubbles)
    assert sum(1 for call in tr.contexts) > len(cache.pages)  # it was asked for again
