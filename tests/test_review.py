"""Review flags on translations, the listing of flagged ones, and a rendering changed by the reader's edit."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from taslation.annotations import Glossary
from taslation.cache import CachedBubble, CachedPage, CacheStore
from taslation.cli import cmd_review
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion
from taslation.review import REASONS, flags_for, rendering_changes, sheet_item_for
from taslation.translate import DictTranslator

SHEET = {
    "entries": [{"term": "魔法少女", "rendering": "magical girl"}],
    "characters": [{"name": "穂杉季和", "rendering": "Hosugi Nowa"},
                   {"name": "ピョ", "rendering": "Pyo", "addresses": {"季和": "Nowa-chan"}}],
}


def sheet() -> Glossary:
    g = Glossary(Path("eval.json"), "test")
    g.apply_json(SHEET)
    return g


def test_flags_for_each_reason(settings):
    g = sheet()
    assert flags_for("魔法少女だ", "A magical girl.", 14, settings, g) == []
    assert flags_for("魔法少女だ", "A magical girl.", 9, settings, g) == ["small"]
    assert flags_for("魔法少女だ", "A magic girl.", 14, settings, g) == ["rendering"]
    assert flags_for("はい", "Yes, of course, absolutely, whatever you say, my dear friend.", 14, settings) == ["long"]  # 61 characters for two: padded
    assert flags_for("はい", "Yes, of course, I will.", 14, settings) == []  # a short line may take a long rendering (3 x 2 + 20)
    assert flags_for("はいそうです", "Yes, of course, absolutely, whatever you say, my dear friend, I agree.", 14, settings) == ["long"]
    assert flags_for("ありがとうございました", "Ok.", 14, settings) == ["short"]
    assert flags_for("魔法少女だ", "A magical girl.", 14, settings, g, confidence=0.4) == ["ocr"]
    assert flags_for("魔法少女だ", "", 9, settings, g) == []
    settings.readable_font_size = 0
    assert flags_for("魔法少女だ", "A magical girl.", 9, settings, g) == []
    assert set(REASONS) >= {"small", "rendering", "long", "short", "ocr"}


def test_rendering_changes_find_what_the_reader_wrote_instead():
    g = sheet()
    assert rendering_changes(g, "魔法少女だ", "She's a magical girl.", "She's a mahou shoujo.") == [("magical girl", "mahou shoujo")]
    assert rendering_changes(g, "季和、行くよ", "Let's go, Nowa-chan!", "Let's go, Nowa!", speaker="ピョ") == [("Nowa-chan", "Nowa")]
    assert rendering_changes(g, "魔法少女だ", "She's a magical girl.", "She is a magical girl!") == []  # the rendering stays
    assert rendering_changes(g, "魔法少女だ", "She's a magical girl.", "She's one of them.") == []  # no replacement to name
    assert rendering_changes(g, "魔法少女だ", "Pyo's magical girl.", "Pyo's sparkle maiden.") == [("magical girl", "sparkle maiden")]
    assert rendering_changes(None, "魔法少女だ", "a", "b") == [] and rendering_changes(g, "魔法少女だ", "", "x") == []
    assert sheet_item_for(g, "magical girl") == ("term", "魔法少女")
    assert sheet_item_for(g, "Hosugi Nowa") == ("character", "穂杉季和") and sheet_item_for(g, "Nobody") is None


def test_flags_survive_the_cache_and_the_listing(tmp_path, settings, capsys):
    store = CacheStore(settings.cache_dir)
    cache = store.open("Some Book", "m", "English")
    cache.add(CachedPage(fingerprint="a" * 80, aspect=0.7, seq=0, bubbles=[
        CachedBubble(box=(0.1, 0.1, 0.3, 0.3), text="Fine.", flags=[]),
        CachedBubble(box=(0.5, 0.1, 0.7, 0.3), text="A magic girl.", flags=["rendering", "small"])]))
    cache.save()
    again = store.open("Some Book", "m", "English")
    assert [b.flags for b in again.pages[0].bubbles] == [[], ["rendering", "small"]]
    assert "flags" not in again.pages[0].bubbles[0].to_json() and again.pages[0].bubbles[1].to_json()["flags"] == ["rendering", "small"]
    settings.ollama_model = "m"
    assert cmd_review(argparse.Namespace(book="Some Book", language=""), settings) == 0
    out = capsys.readouterr().out
    assert "page 1 bubble 2" in out and "misses a rendering" in out and "readable size" in out and "A magic girl." in out
    assert "1 of 2 cached translation(s) flagged" in out and "Fine." not in out


def _region(x0, y0, x1, y1, text_box, source="魔法少女だ") -> TextRegion:
    return TextRegion(x0, y0, x1, y1, np.full((y1 - y0, x1 - x0), 255, np.uint8), text_box, status="untranslated",
                      source_text=source)


def test_live_mode_flags_its_translations(settings):
    long = "Honestly, I cannot believe a magical girl would ever do something like this to me of all people, really."
    tr = DictTranslator({"魔法少女だ": "A magic girl.", "はいそうです": long})
    p = Pipeline(settings, ocr=None, translator=tr)
    p.glossary = sheet()
    a = _region(0, 0, 400, 300, (100, 100, 300, 200))
    b = _region(0, 300, 400, 600, (100, 400, 300, 500), source="はいそうです")
    assert p._translate_regions([a, b], lambda _m: None) == ""
    assert a.flags == ["rendering"] and b.flags == ["long"]  # nothing is asked again: the miss is flagged


def test_every_reason_has_a_label_in_every_language_of_the_window():
    from taslation.i18n import CATALOGS
    from taslation.review import reason_label

    for code, catalog in CATALOGS.items():
        for reason, english in REASONS.items():
            label = reason_label(reason, code)
            assert label.strip(), (code, reason)
            assert (label == english) == (code == "en"), (code, reason, label)  # translated everywhere but English
    assert reason_label("small", "ja") == "読みやすい大きさより小さい文字"
    assert reason_label("revised", "ja") == "revised"  # a flag of before 2026-11-06 in an old cache: shown as its code
    assert reason_label("draft", "ja") == "draft"  # the mark of a first draft went on 2026-11-06: no reason
    assert reason_label("small", "en") == "set under the readable size" == reason_label("small", "xx")
    assert reason_label("no-such-code", "ja") == "no-such-code"


def test_the_review_list_says_the_reasons_in_the_windows_language(settings):
    from taslation import i18n
    from taslation.ui.dialogs.review import review_rows

    region = _region(0, 0, 400, 300, (100, 100, 300, 200))
    region.status, region.translated_text, region.flags = "translated", "A magic girl.", ["rendering", "ocr"]
    try:
        i18n.set_language("en")
        assert review_rows([region]) == [(region, "misses a rendering from the series sheet; TASlation may have misread the "
                                                  "Japanese", "A magic girl.")]
        i18n.set_language("ja")
        assert review_rows([region]) == [(region, "シリーズ設定の表記が使われていない; TASlation が日本語を読み間違えたかもしれません",
                                          "A magic girl.")]
    finally:
        i18n.set_language("en")
    assert region.flags == ["rendering", "ocr"]  # the region keeps the codes


def test_the_listing_prints_the_label_in_the_ui_language_and_the_code(settings, capsys):
    from taslation.i18n import save_ui_language

    cache = CacheStore(settings.cache_dir).open("Some Book", "m", "English")
    cache.add(CachedPage(fingerprint="a" * 80, aspect=0.7, seq=0, bubbles=[
        CachedBubble(box=(0.5, 0.1, 0.7, 0.3), text="A magic girl.", flags=["rendering", "small"])]))
    cache.save()
    settings.ollama_model = "m"
    assert cmd_review(argparse.Namespace(book="Some Book", language=""), settings) == 0
    assert ("page 1 bubble 1: misses a rendering from the series sheet (rendering); set under the readable size (small)"
            "\n    A magic girl.") in capsys.readouterr().out
    save_ui_language(settings.state_dir, "ja")  # the language chosen in the window
    assert cmd_review(argparse.Namespace(book="Some Book", language=""), settings) == 0
    assert ("page 1 bubble 1: シリーズ設定の表記が使われていない (rendering); 読みやすい大きさより小さい文字 (small)"
            "\n") in capsys.readouterr().out
    assert CacheStore(settings.cache_dir).open("Some Book", "m", "English").pages[0].bubbles[0].flags == ["rendering", "small"]
