"""Line reuse (`taslation.linememo`): a short line translated before in the book or its series takes that translation
again without a request. What is merged before a line is keyed and what is never reused; the memo sealed in the
book's cache with no Japanese in it, before or after unsealing; a later page and a line repeated in one request; a
person's correction winning; "Translate again" asking every line and keeping the new answers; another model, language or series never reusing; a kept translation held to the series
sheet as it is now; the setting off; export, import, two windows saving the same book, and deletion. The lines and
names are invented."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from helpers import FakeOcr, store_json, store_text

from taslation import linememo, protect
from taslation.annotations import Glossary
from taslation.cache import BookCache, CacheStore
from taslation.linememo import LineMemo, Plan, SeriesLines, material, normalise, scope
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

JAPANESE = re.compile(r"[぀-ヿ㐀-䶿一-鿿！-｠]")
LONG = "今日は本当にいい天気だから海まで歩こう。"  # more than `MAX_CHARS`: never reused
PAGE_1 = ["えっ！", "待って！", "ありがとう。", "行くぞ！", "そうだね。", LONG]
PAGE_2 = ["えっ！", "待って！", "知らない。", "行くぞ！", "そうだね。", LONG]
ENGLISH = {"えっ！": "Huh?!", "待って！": "Wait!", "ありがとう。": "Thanks.", "行くぞ！": "Let's go!",
           "そうだね。": "Yeah.", "知らない。": "No idea.", LONG: "It's such a nice day, let's walk to the sea."}


@pytest.fixture
def on(settings):
    settings.reuse_lines = True
    return settings


def _pipeline(settings, book="Harbor Lights 1", texts=PAGE_1 + PAGE_2, model="m1", mapping=None, sheets=None):
    tr = DictTranslator(dict(mapping or ENGLISH))
    tr.model = model
    store = CacheStore(settings.cache_dir)
    cache = store.open(book, model, settings.target_language)
    pipeline = Pipeline(settings, ocr=FakeOcr(list(texts)), translator=tr, cache=cache)
    pipeline.series_lines = linememo.series_lines(store, cache, sheets=sheets)
    return pipeline, tr, store


def _asked(tr) -> list[str]:
    return [t for call in tr.calls for t in call]


def _by_source(result) -> dict[str, object]:
    return {r.source_text: r for r in result.regions if r.source_text}


# ------------------------------------------------------------------ what a line is keyed by
def test_only_merges_that_change_no_reading_are_made():
    assert normalise("えっ！？") == normalise("えっ!?") == normalise("えっ？！！") == normalise(" え っ !? ") == "えっ!?"
    assert normalise("えっ……") == normalise("えっ...") == normalise("えっ・・・") == normalise("えっ‥") == "えっ…"
    assert normalise("ちょっと〜〜") == normalise("ちょっとー") == normalise("ちょっと～") == "ちょっとー"
    assert normalise("好き♡♡") == "好き♡" and normalise("はい。") == normalise("はい") == "はい"
    assert normalise("ｱﾘｶﾞﾄｳ") == "アリガトウ"  # half-width katakana is katakana (NFKC)
    for a, b in (("えっ", "エッ"), ("えっ!", "えっ?"), ("あっ", "あつ"), ("はい", "はい…"), ("ねえ", "ねぇ")):
        assert normalise(a) != normalise(b), (a, b)  # kana kinds, ! against ?, small kana, a trailing ellipsis


def test_long_lines_open_sentences_hints_and_marks_alone_are_never_keyed():
    assert material("待って！") is not None
    assert material(LONG) is None and material("あ" * 11) is None and material("あ" * 10) is not None
    assert material("！？") is None and material("…") is None and material("") is None
    assert material("待って", {"continues": True}) is None  # a piece of a sentence that goes on
    assert material("待って", after_open=True) is None  # ... or one that goes on from the bubble before
    assert material("待って", {"note": "a pun on her name"}) is None
    assert material("待って", {"speaker": "Rio"}) != material("待って", {"speaker": "Kai"}) != material("待って")
    assert material("待って", {"kind": "thought"}) != material("待って")
    texts = ["それは", "待って", "待って"]
    keys = linememo.materials(texts, [{"continues": True}, {}, {}])
    assert keys[0] is None and keys[1] is None and keys[2] == material("待って")


def test_a_scope_is_one_translator_model_and_language():
    a = SimpleNamespace(name="plamo", model="m1")
    assert scope(a, "English") == scope(a, " english ")
    assert scope(a, "English") != scope(SimpleNamespace(name="plamo", model="m2"), "English")
    assert scope(a, "English") != scope(a, "French")
    assert scope(a, "English") != scope(SimpleNamespace(name="ollama", model="m1"), "English")


# ------------------------------------------------------------------ the memo and its file
def test_the_memo_is_sealed_in_the_cache_with_no_japanese_in_it(settings):
    store = CacheStore(settings.cache_dir)
    cache = store.open("Harbor Lights 1", "m1")
    key = material("待って！")
    assert cache.lines.put("s", key, "Wait!") and cache.dirty
    cache.lines.put("s", material("えっ！"), "Huh?!", edited=True)
    cache.save()
    raw = cache.path.read_bytes()
    if protect.available():
        assert protect.is_protected(raw)
    for line in ("待って！", "待って", "えっ！", "えっ"):
        assert line.encode("utf-8") not in raw
    text = store_text(cache.path)  # unsealed
    assert not JAPANESE.search(text)
    lines = store_json(cache.path)["lines"]
    assert lines["v"] == linememo.KEY_VERSION and len(lines["rings"]) == 1
    ring = lines["rings"][0]
    assert len(bytes.fromhex(ring["key"])) == linememo.SECRET_BYTES
    entries = ring["scopes"]["s"]
    assert sorted(entries.values()) == [["Huh?!", 1], ["Wait!"]]
    assert all(len(d) == 2 * linememo.DIGEST_BYTES for d in entries)
    again = BookCache.load(cache.path)
    assert again.lines.find("s", key).text == "Wait!" and again.lines.find("s", material("えっ！")).edited
    assert store.list()[0]["lines"] == 2
    other = store.open("Harbor Lights 2", "m1")  # another book: another secret, so the same line hashes otherwise
    other.lines.put("s", key, "Wait!")
    assert other.lines.rings[0].secret != again.lines.rings[0].secret
    assert set(other.lines.rings[0].scopes["s"]).isdisjoint(again.lines.rings[0].scopes["s"])


def test_a_person_s_translation_is_never_replaced_by_the_model_s():
    memo = LineMemo()
    key = material("待って！")
    memo.put("s", key, "Wait!")
    assert memo.put("s", key, "Hold it!", edited=True) and memo.find("s", key).text == "Hold it!"
    assert not memo.put("s", key, "Stop!") and memo.find("s", key).text == "Hold it!"
    assert memo.put("s", key, "Hang on!", edited=True) and memo.find("s", key).text == "Hang on!"


def test_a_damaged_or_foreign_lines_field_is_left_out():
    for data in (None, [], {"v": 99, "rings": []}, {"v": 1, "rings": "x"},
                 {"v": 1, "rings": [{"key": "zz", "scopes": {}}]},
                 {"v": 1, "rings": [{"key": "a" * 64, "scopes": {"s": {"short": ["x"], "b" * 32: [5]}}}]}):
        assert len(LineMemo.from_json(data)) == 0
    ok = LineMemo.from_json({"v": 1, "rings": [{"key": "a" * 64, "scopes": {"s": {"b" * 32: ["Hi\x07 there", 1]}}}]})
    assert len(ok) == 1 and next(iter(ok.rings[0].scopes["s"].values())).text == "Hi there"


def test_two_windows_saving_one_book_keep_both_their_lines(settings):
    store = CacheStore(settings.cache_dir)
    first = store.open("Harbor Lights 1", "m1")
    first.lines.put("s", material("えっ！"), "Huh?!")
    first.save()
    a, b = BookCache.load(first.path), BookCache.load(first.path)
    a.lines.put("s", material("待って！"), "Wait!")
    b.lines.put("s", material("行くぞ！"), "Let's go!")
    a.save()
    b.save()
    merged = BookCache.load(first.path).lines
    assert {merged.find("s", material(t)).text for t in ("えっ！", "待って！", "行くぞ！")} == {"Huh?!", "Wait!", "Let's go!"}
    # two windows that opened the book before it kept any line each make a secret: both rings kept, nothing lost
    c, d = store.open("Harbor Lights 2", "m1"), store.open("Harbor Lights 2", "m1")
    c.lines.put("s", material("そうだね。"), "Yeah.")
    d.lines.put("s", material("えっ！"), "Eh?!")
    c.save()
    d.save()
    both = BookCache.load(d.path).lines
    assert len(both.rings) == 2 and both.find("s", material("そうだね。")).text == "Yeah."
    assert both.find("s", material("えっ！")).text == "Eh?!"
    d.lines.put("s", material("そうだね。"), "Yep.")  # the line again: the older ring's entry gives way
    d.save()
    again = BookCache.load(d.path).lines
    assert again.find("s", material("そうだね。")).text == "Yep." and len(again) == 2


# ------------------------------------------------------------------ page by page
def test_a_later_page_reuses_the_short_lines_and_keeps_its_own(on, sample_page, sample_page2):
    pipeline, tr, _store = _pipeline(on)
    first = pipeline.process(sample_page)
    assert sorted(_asked(tr)) == sorted(PAGE_1) and not any(r.reused for r in first.regions)
    second = pipeline.process(sample_page2)
    assert sorted(tr.calls[-1]) == sorted(["知らない。", LONG])  # only the new line and the long one are sent
    got = _by_source(second)
    assert {t: got[t].translated_text for t in PAGE_2} == {t: ENGLISH[t] for t in PAGE_2}
    assert {t for t in PAGE_2 if got[t].reused} == {"えっ！", "待って！", "行くぞ！", "そうだね。"}
    assert (pipeline.line_tally.reused, pipeline.line_tally.asked) == (4, 8)  # (the model translated 6, then 2)
    cached = [b for p in pipeline.cache.pages for b in p.bubbles]
    assert sum(b.reused for b in cached) == 4  # kept with the page: the editor says so when it comes from the cache
    again = pipeline.process(sample_page2)  # from the cache
    assert sum(r.reused for r in again.regions) == 4 and len(tr.calls) == 2


def test_a_line_repeated_on_one_page_is_asked_once(on, sample_page):
    page = ["えっ！", "待って！", "えっ！", "行くぞ！", "えっ！", LONG]
    pipeline, tr, _store = _pipeline(on, texts=page)
    result = pipeline.process(sample_page)
    assert sorted(_asked(tr)) == sorted(["えっ！", "待って！", "行くぞ！", LONG])
    assert [r.translated_text for r in result.regions if r.source_text == "えっ！"] == ["Huh?!"] * 3
    assert sum(r.reused for r in result.regions) == 2


def test_a_correction_wins_for_the_lines_to_come(on, sample_page, sample_page2):
    pipeline, tr, _store = _pipeline(on)
    first = pipeline.process(sample_page)
    wait = _by_source(first)["待って！"]
    assert pipeline.set_translation(first, wait, "Hold on!")
    entry = pipeline.cache.lines.find(scope(tr, on.target_language), material("待って！"))
    assert entry.text == "Hold on!" and entry.edited
    second = pipeline.process(sample_page2)
    got = _by_source(second)["待って！"]
    assert got.translated_text == "Hold on!" and got.reused and "待って！" not in tr.calls[-1]
    assert pipeline.set_translation(second, got, "Hang on!") and not got.reused  # its own now


def test_undo_takes_back_the_line_an_edit_kept_and_redo_keeps_it_again(on, sample_page):
    from taslation.ui.history import carry, unit_states

    pipeline, tr, _store = _pipeline(on)
    first = pipeline.process(sample_page)
    s, key = scope(tr, on.target_language), material("待って！")
    before = unit_states(pipeline, first.units)
    pipeline.set_translation(first, _by_source(first)["待って！"], "Hold on!")
    after = unit_states(pipeline, first.units)
    pipeline.cache.lines.put(s, material("知らない。"), "No idea.")  # meanwhile, another page's line
    assert carry(pipeline, after, before) == []
    entry = BookCache.load(pipeline.cache.path).lines.find(s, key)
    assert (entry.text, entry.edited) == ("Wait!", False)  # the model's again, and saved so
    assert pipeline.cache.lines.find(s, material("知らない。")).text == "No idea."  # what came meanwhile stays
    carry(pipeline, before, after)
    entry = pipeline.cache.lines.find(s, key)
    assert (entry.text, entry.edited) == ("Hold on!", True)


def test_an_edit_of_a_page_from_the_cache_reads_its_japanese_first():
    memo = LineMemo()
    region = SimpleNamespace(source_text="", speaker="", tag="", continues=False, remark="", room=0, unit=0,
                             status="translated", bbox=(0, 0, 10, 10))
    pipeline = SimpleNamespace(cache=SimpleNamespace(lines=memo), settings=SimpleNamespace(reuse_lines=True,
                               target_language="English"), translator=SimpleNamespace(name="t", model="m"),
                               ocr=object(), read_source=lambda result, r: "待って！")
    result = SimpleNamespace(regions=[region], units=[])
    assert linememo.remember_edit(pipeline, result, region, "Hold on!")
    assert memo.find(scope(pipeline.translator, "English"), material("待って！")).edited
    pipeline.read_source = lambda result, r: ""  # nothing read: the edit stays the page's alone
    assert not linememo.remember_edit(pipeline, result, region, "Hold it!")


def test_translate_again_asks_every_line_and_keeps_the_new_answers(on, sample_page, sample_page2):
    pipeline, tr, _store = _pipeline(on)
    first = pipeline.process(sample_page)
    pipeline.set_translation(first, _by_source(first)["行くぞ！"], "Here we go!")
    tr.mapping["えっ！"] = "What?!"
    tr.mapping["行くぞ！"] = "Move out!"
    again = pipeline.process(sample_page2, reuse=False)
    assert sorted(tr.calls[-1]) == sorted(PAGE_2) and not any(r.reused for r in again.regions)
    s = scope(tr, on.target_language)
    assert pipeline.cache.lines.find(s, material("えっ！")).text == "What?!"  # the model's entry replaced
    assert pipeline.cache.lines.find(s, material("行くぞ！")).text == "Here we go!"  # a person's stays
    third = pipeline.process(sample_page.transpose(0))
    assert _by_source(third)["えっ！"].translated_text == "What?!"


def test_a_page_read_without_the_cache_neither_reuses_nor_keeps(on, sample_page):
    pipeline, tr, _store = _pipeline(on)
    pipeline.process(sample_page, use_cache=False)
    assert len(pipeline.cache.lines) == 0


def test_another_model_or_language_never_reuses(on, sample_page, sample_page2):
    pipeline, tr, _store = _pipeline(on)
    pipeline.process(sample_page)
    other = DictTranslator(ENGLISH)
    other.model = "m2"
    pipeline.translator = other
    pipeline.process(sample_page2)
    assert sorted(other.calls[-1]) == sorted(PAGE_2)
    pipeline.translator = tr
    on.target_language = "French"
    pipeline.process(sample_page2.transpose(0))
    assert sorted(tr.calls[-1]) == sorted(PAGE_1)  # (the OCR has gone round to its first page's lines)


def test_the_series_reuses_its_volumes_lines_and_no_other_series_does(on, sample_page, sample_page2):
    pipeline, tr, store = _pipeline(on, book="Harbor Lights 1")
    first = pipeline.process(sample_page)
    pipeline.set_translation(first, _by_source(first)["そうだね。"], "Yep.")
    pipeline.cache.save()
    volume_2, tr2, _ = _pipeline(on, book="Harbor Lights 2", texts=PAGE_2)
    got = _by_source(volume_2.process(sample_page2))
    assert sorted(tr2.calls[-1]) == sorted(["知らない。", LONG])
    assert got["そうだね。"].translated_text == "Yep." and got["えっ！"].reused
    assert len(store.open("Harbor Lights 1", "m1").lines) == 5  # the other volume is read, never written
    stranger, tr3, _ = _pipeline(on, book="Quiet Field 1", texts=PAGE_2)
    stranger.process(sample_page2)
    assert sorted(tr3.calls[-1]) == sorted(PAGE_2)


def test_the_series_is_the_series_sheet_s_with_old_and_new_spellings_of_its_volumes(on, sample_page, sample_page2):
    """A volume kept under a name typed before the Series and Volume fields ("Harbor Lights 3巻") and one named by
    them ("Harbor Lights 4", "harbor  lights 5") are one series, as their series sheet is one; another series shares
    nothing, and a volume whose sheet is still kept under the key an older parser gave it reads that sheet alone, and
    so its own lines alone (`notes.sheet_key`)."""
    from taslation.annotations import GlossaryStore

    sheets = GlossaryStore(on.glossary_dir)
    old, _tr, store = _pipeline(on, book="Harbor Lights 3巻", sheets=sheets)
    first = old.process(sample_page)
    old.set_translation(first, _by_source(first)["そうだね。"], "Yep.")
    old.cache.save()
    for book, asked in (("Harbor Lights 4", ["知らない。", LONG]), ("harbor  lights 5", [LONG])):  # (5: 4's too)
        new, tr_new, _ = _pipeline(on, book=book, texts=PAGE_2, sheets=sheets)
        got = _by_source(new.process(sample_page2))
        assert sorted(tr_new.calls[-1]) == sorted(asked), book
        assert got["そうだね。"].translated_text == "Yep." and got["えっ！"].reused, book
    stranger, tr_other, _ = _pipeline(on, book="Quiet Field 3巻", texts=PAGE_2, sheets=sheets)
    stranger.process(sample_page2)
    assert sorted(tr_other.calls[-1]) == sorted(PAGE_2)
    sheets.open("Harbor Lights 第一巻", on.target_language).save()  # a sheet kept under the older parser's key
    own_sheet, tr_own, _ = _pipeline(on, book="Harbor Lights 第一巻", texts=PAGE_2, sheets=sheets)
    own_sheet.process(sample_page2)
    assert sorted(tr_own.calls[-1]) == sorted(PAGE_2)
    assert linememo.same_series("Harbor  lights", "harbor Lights") and not linememo.same_series("", "")


def test_fresh_answers_are_kept_as_the_series_sheet_spells_them(on, sample_page, sample_page2):
    """What the model answers is spelt as the sheet spells (`terms.spelt_right`) before the page and the memo get it:
    the later identical line is given the sheet's spelling, without a request."""
    page_1 = ["ミカ！", "待って！", "ありがとう。", "行くぞ！", "そうだね。", LONG]
    page_2 = ["ミカ！", "レン！", "知らない。", "行くぞ！", "そうだね。", LONG]
    pipeline, tr, _store = _pipeline(on, texts=page_1 + page_2, mapping=dict(ENGLISH, **{"ミカ！": "Mikka!",
                                                                                        "レン！": "Len!"}))
    sheet = Glossary(Path("sheet.json"), "Harbor Lights")
    sheet.set("ミカ", "Mika")
    pipeline.glossary, pipeline.glossary_text = sheet, sheet.format()
    assert _by_source(pipeline.process(sample_page))["ミカ！"].translated_text == "Mika!"
    key = material("ミカ！", {})
    assert pipeline.cache.lines.find(scope(tr, on.target_language), key).text == "Mika!"
    got = _by_source(pipeline.process(sample_page2))
    assert got["ミカ！"].translated_text == "Mika!" and got["ミカ！"].reused and "ミカ！" not in tr.calls[-1]


def test_a_kept_translation_is_held_to_the_series_sheet_as_it_is_now(on, sample_page, sample_page2):
    page_1 = ["ミカ！", "待って！", "ありがとう。", "行くぞ！", "そうだね。", LONG]
    page_2 = ["ミカ！", "レン！", "知らない。", "行くぞ！", "そうだね。", LONG]
    mapping = dict(ENGLISH, **{"ミカ！": "Mikka!", "レン！": "Len!"})
    pipeline, tr, _store = _pipeline(on, texts=page_1 + page_2, mapping=mapping)
    pipeline.process(sample_page)
    sheet = Glossary(Path("sheet.json"), "Harbor Lights")
    sheet.set("ミカ", "Mika")  # a near spelling of what was kept: put right, as a fresh answer is put right
    sheet.set("行く", "Sail")  # nothing near it in "Let's go!": the line is asked for again, with the sheet
    pipeline.glossary, pipeline.glossary_text = sheet, sheet.format()
    tr.mapping["行くぞ！"] = "Sail out!"
    got = _by_source(pipeline.process(sample_page2))
    assert got["ミカ！"].translated_text == "Mika!" and got["ミカ！"].reused
    assert "行くぞ！" in _asked(tr)[6:] and got["行くぞ！"].translated_text == "Sail out!"
    assert "ミカ！" not in _asked(tr)[7:]  # a name kept as its romaji is not asked again as a bare romanisation


def test_reuse_off_asks_every_line_and_keeps_nothing(settings, sample_page, sample_page2):
    settings.reuse_lines = False
    pipeline, tr, _store = _pipeline(settings)
    pipeline.process(sample_page)
    pipeline.process(sample_page2)
    assert sorted(tr.calls[-1]) == sorted(PAGE_2) and len(pipeline.cache.lines) == 0
    assert (pipeline.line_tally.reused, pipeline.line_tally.asked) == (0, 0)


def test_the_setting_is_on_by_default_and_in_the_example_file():
    from taslation.config import Settings

    assert Settings().reuse_lines is True
    example = (Path(__file__).resolve().parents[1] / "taslation.toml.example").read_text(encoding="utf-8")
    assert re.search(r"^reuse_lines = true\b", example, re.M)


# ------------------------------------------------------------------ what the window says
def test_the_editor_says_a_translation_was_reused_until_it_is_another(tmp_path):
    from taslation.i18n import CATALOGS
    from taslation.regions import TextRegion
    from taslation.ui import app as app_mod
    from taslation.ui import translator

    w = SimpleNamespace(settings=SimpleNamespace(spellcheck=False, target_language="English", state_dir=tmp_path))
    w._spelling_note = lambda: app_mod.App._spelling_note(w)
    region = TextRegion(0, 0, 10, 10, mask=None, text_box=(0, 0, 10, 10), translated_text="Huh?!", reused_text="Huh?!")
    assert app_mod.App._editor_note(w, region) == translator.REUSED_NOTE
    region.translated_text = "What?!"  # asked again, or edited: its own now
    assert app_mod.App._editor_note(w, region) == ""
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert translator.REUSED_NOTE in catalog, code


def test_the_reused_note_stands_with_the_hint_line_and_never_widens_the_editor(hidden_root):
    """Under the header, the note that a translation was reused; under the hint, the line that the model follows a hint
    only sometimes: both at once, in every window language, the editor as wide as without the note (measured: one or
    two lines of text, 21 to 36 pixels)."""
    import numpy as np

    from taslation import i18n
    from taslation.i18n import CATALOGS, _
    from taslation.pipeline import manual_region
    from taslation.ui.dialogs import review
    from taslation.ui.translator import REUSED_NOTE

    def editor(note):
        region = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
        region.status, region.translated_text, region.source_text = "translated", "Huh?!", "えっ！"
        d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None,
                                    on_ask=lambda mode, answer: True, hint_support="sometimes", note=note)
        d.update_idletasks()
        return d

    try:
        for code in CATALOGS:
            i18n.set_language(code)
            plain, noted = editor(""), editor(_(REUSED_NOTE))
            assert noted.note_label is not None and noted.hint_line is not None, code
            assert str(noted.note_label.cget("text")) == _(REUSED_NOTE), code
            assert noted.winfo_reqwidth() == plain.winfo_reqwidth(), code
            assert 0 < noted.winfo_reqheight() - plain.winfo_reqheight() <= 60, code
            plain.destroy()
            noted.destroy()
    finally:
        i18n.set_language("en")


def test_the_report_counts_the_lines_reused(settings):
    """Copy a report's translator line says how many short lines were reused this session (counts only; the System
    page no longer says it)."""
    from taslation.ui import report

    pipeline = SimpleNamespace(line_tally=linememo.Tally(reused=4, asked=8), stage_times=None,
                               translator=SimpleNamespace(model="m"), ocr=None, layout=None, art_eraser=None)
    app = SimpleNamespace(settings=settings, pipeline=pipeline, _compute_where="GPU")
    assert report._models(app)["translator"] == "m; on GPU; short lines reused 4 of 12"
    pipeline.line_tally = linememo.Tally()
    assert report._models(app)["translator"] == "m; on GPU"


# ------------------------------------------------------------------ export, import, delete
def test_the_lines_travel_in_the_export_and_go_with_the_cache(on, tmp_path, sample_page):
    pytest.importorskip("cryptography")
    from taslation import backup

    pipeline, tr, store = _pipeline(on)
    pipeline.process(sample_page)
    pipeline.cache.save()
    s = scope(tr, on.target_language)
    out = tmp_path / "harbor.taslation"
    backup.export_cache(store, "Harbor Lights 1", out, "correct horse battery staple", on.target_language)
    other = CacheStore(tmp_path / "elsewhere")
    backup.import_cache(other, out, "correct horse battery staple")  # merged into a new cache
    merged = other.open("Harbor Lights 1", "m1")
    assert merged.lines.find(s, material("えっ！")).text == "Huh?!" and len(merged.lines) == 5
    merged.lines.put(s, material("待って！"), "Hold on!", edited=True)
    merged.save()
    backup.import_cache(other, out, "correct horse battery staple")  # a merge never undoes what the cache has
    assert other.open("Harbor Lights 1", "m1").lines.find(s, material("待って！")).text == "Hold on!"
    backup.import_cache(other, out, "correct horse battery staple", replace=True)
    assert other.open("Harbor Lights 1", "m1").lines.find(s, material("待って！")).text == "Wait!"
    assert store.delete("Harbor Lights 1")
    assert store.line_memos("Harbor Lights", on.target_language) == []
    assert len(store.open("Harbor Lights 1", "m1").lines) == 0


# ------------------------------------------------------------------ the plan itself
def test_a_failed_request_still_gives_the_reused_lines():
    memo = LineMemo()
    memo.put("s", material("えっ！"), "Huh?!")
    plan = Plan(SeriesLines(memo), "s", ["えっ！", "知らない。"])
    told = []

    def failing(texts, *args, meta=None, on_item=None):
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        plan.ask(failing, on_item=lambda i, t: told.append((i, t)))
    assert told == [(0, "Huh?!")] and plan.fill([]) == ["Huh?!", ""]


def test_answers_are_told_in_the_request_s_own_numbering():
    memo = LineMemo()
    memo.put("s", material("えっ！"), "Huh?!")
    plan = Plan(SeriesLines(memo), "s", ["知らない。", "えっ！", "待って！", "待って！"])
    told, sent = [], []

    def translate(texts, *args, meta=None, on_item=None):
        sent.append((list(texts), meta))
        out = [ENGLISH[t] for t in texts]
        for k, t in enumerate(out):
            on_item(k, t)
        return out

    answers = plan.ask(translate, meta=[{}, {}, {"speaker": "Rio"}, {"speaker": "Rio"}],
                       on_item=lambda i, t: told.append((i, t)))
    assert sent == [(["知らない。", "待って！"], [{}, {"speaker": "Rio"}])]
    assert sorted(told) == [(0, "No idea."), (1, "Huh?!"), (2, "Wait!"), (3, "Wait!")]
    assert plan.fill(answers) == ["No idea.", "Huh?!", "Wait!", "Wait!"]
