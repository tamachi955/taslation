"""The lettering size (`Settings.text_scale`, Tools > Settings... and a book's own in Book settings...): at 100 % the
page is lettered as it was before there was one (no extra pass, the same pixels); under it every translation smaller
by so much, never under the smallest size; over it larger only where the page's sizes held it back, never past its
bubble or the largest size; the page's sizes measured at 100 % (no double scaling); a book's own size and largest
size on top of the reader's, and the page lettered anew when they change."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr

from taslation import pipeline as pipeline_mod
from taslation.annotations import BOOK_SETTING_KEYS, BookAnnotations, RegionStyle, clean_book_settings
from taslation.cache import CacheStore
from taslation.config import ConfigError, Settings
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion
from taslation.translate import DictTranslator
from taslation.ui.dialogs import book_settings as book_dlg
from taslation.ui.dialogs import settings as dlg


def _pipeline(settings, annotations=None):
    cache = CacheStore(settings.cache_dir).open("Scale Book", "fake")
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache, annotations=annotations)


def _lettered(settings, page, annotations=None):
    p = _pipeline(settings, annotations)
    p.process(page)  # translated and kept
    return p, p.process(page)  # from the cache, lettered anew


def _sizes(result):
    return [r.font_size for r in result.translated]


# ------------------------------------------------------------------ 100 %: as before
@pytest.mark.parametrize("page", ["sample_page", "sample_page2"])
def test_at_100_percent_the_page_is_lettered_as_before_with_no_extra_pass(settings, page, request, monkeypatch):
    image = request.getfixturevalue(page)
    calls = []
    real = pipeline_mod.letter_text
    monkeypatch.setattr(pipeline_mod, "letter_text", lambda *a, **k: calls.append(a[0] is None) or real(*a, **k))
    _p, now = _lettered(settings, image)
    counted = list(calls)
    calls.clear()
    # the code before the lettering size: no scaling at all
    monkeypatch.setattr(Pipeline, "_scaled_top", lambda self, region, text, lettering, top, *rest: top)
    _p, before = _lettered(Settings(state_dir=settings.state_dir.parent / "before"), image)
    assert np.array_equal(np.asarray(now.image), np.asarray(before.image))
    assert _sizes(now) == _sizes(before) and calls == counted


def test_at_100_percent_nothing_is_measured_for_the_scale(settings, monkeypatch):
    p = Pipeline(settings, ocr=None, translator=None)
    monkeypatch.setattr(pipeline_mod, "letter_text", lambda *a, **k: pytest.fail("measured at 100 %"))
    assert p._scaled_top(None, "Hi", None, 37, (255, 255, 255), None, "") == 37


# ------------------------------------------------------------------ smaller and larger
def test_a_smaller_size_letters_every_translation_smaller_and_never_under_the_smallest(settings, sample_page):
    _p, full = _lettered(settings, sample_page)
    small = Settings(state_dir=settings.state_dir.parent / "small", text_scale=0.8)
    _p, scaled = _lettered(small, sample_page)
    assert _sizes(scaled) == [max(small.min_font_size, round(size * 0.8)) for size in _sizes(full)]
    assert all(a < b for a, b in zip(_sizes(scaled), _sizes(full)))
    assert [r.size_cap for r in scaled.translated] == [r.size_cap for r in full.translated]  # measured at 100 %
    assert not np.array_equal(np.asarray(scaled.image), np.asarray(full.image))


def test_the_scaled_size_keeps_within_the_smallest_and_the_largest_size(settings, monkeypatch):
    settings.text_scale = 0.8
    p = Pipeline(settings, ocr=None, translator=None)
    fits = SimpleNamespace(size=30)
    monkeypatch.setattr(pipeline_mod, "letter_text", lambda *a, **k: fits)
    assert p._scaled_top(None, "Hi", None, 40, (255, 255, 255), None, "") == 24  # 80 % of the size it fits at
    fits.size = 10
    assert p._scaled_top(None, "Hi", None, 40, (255, 255, 255), None, "") == settings.min_font_size
    fits.size = 0  # nothing set (no room at all): left as it fits
    assert p._scaled_top(None, "Hi", None, 40, (255, 255, 255), None, "") == 40
    settings.text_scale = 1.3
    monkeypatch.setattr(pipeline_mod, "letter_text", lambda *a, **k: pytest.fail("measured over 100 %"))
    assert p._scaled_top(None, "Hi", None, 20, (255, 255, 255), None, "") == 26
    assert p._scaled_top(None, "Hi", None, 60, (255, 255, 255), None, "") == settings.max_font_size


def test_a_larger_size_lifts_what_the_page_held_back_and_the_bubble_still_holds_it(settings, sample_page):
    p, res = _lettered(settings, sample_page)
    region = max(res.translated, key=lambda r: r.font_size)
    region.size_cap, region.tag = 20, ""
    held = p._set_text(None, region, region.translated_text, (255, 255, 255), None).size
    settings.text_scale = 1.3  # (the pipeline shares the reader's settings)
    lifted = p._set_text(None, region, region.translated_text, (255, 255, 255), None).size
    assert held == 20 and lifted == 26
    region.size_cap = 0
    assert p._set_text(None, region, region.translated_text, (255, 255, 255), None).size == region.font_size


def test_a_size_the_reader_set_in_the_editor_is_kept_as_set(settings):
    settings.text_scale = 0.8
    p = Pipeline(settings, ocr=None, translator=None)
    mask = np.full((200, 400), 255, np.uint8)
    region = TextRegion(0, 0, 400, 200, mask, (100, 50, 300, 150), translated_text="Hi there")
    assert p._set_text(None, region, "Hi there", (255, 255, 255), RegionStyle(size=30)).size == 30


def test_the_review_size_is_the_scaled_one(settings):
    mask = np.full((200, 400), 255, np.uint8)
    p = Pipeline(settings, ocr=None, translator=None)
    full = p.set_size(mask, "A few words", "bubble", (0, 0, 400, 200), 0, 0)
    settings.text_scale = 0.8
    assert p.set_size(mask, "A few words", "bubble", (0, 0, 400, 200), 0, 0) == max(9, round(full * 0.8))


# ------------------------------------------------------------------ the settings and a book's own
@pytest.mark.parametrize("scale", [0.3, 2.5])
def test_a_size_out_of_bounds_is_refused(tmp_path, scale):
    with pytest.raises(ConfigError, match="text_scale"):
        Settings(state_dir=tmp_path, text_scale=scale).validate()


def test_a_book_keeps_its_own_size_and_largest_size_within_bounds():
    assert {"text_scale", "max_font_size"} <= set(BOOK_SETTING_KEYS)
    assert clean_book_settings({"text_scale": 0.9, "max_font_size": 40.0}) == {"text_scale": 0.9, "max_font_size": 40}
    assert clean_book_settings({"text_scale": 5, "max_font_size": True}) == {}
    assert clean_book_settings({"text_scale": "big", "max_font_size": 2}) == {}


def test_a_book_s_own_size_letters_its_pages_and_the_page_on_show_is_lettered_anew(settings, sample_page):
    p, full = _lettered(settings, sample_page, BookAnnotations(settings.state_dir / "ann.json", "Scale Book"))
    p.set_book_settings({"text_scale": 0.8})
    smaller = p.process(sample_page)  # the same capture, not the page lettered before (`shown_pages`)
    assert _sizes(smaller) == [max(9, round(size * 0.8)) for size in _sizes(full)]
    assert settings.text_scale == 1.0  # the reader's own stays
    p.set_book_settings({"max_font_size": 40})
    capped = p.process(sample_page)
    assert max(_sizes(capped)) <= 40 < max(_sizes(full))
    p.set_book_settings({})
    assert _sizes(p.process(sample_page)) == _sizes(full)


# ------------------------------------------------------------------ the dialogs
@pytest.fixture
def in_force(tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    monkeypatch.setattr(book_dlg, "place_window", lambda win, parent=None: None)
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models", config_path=tmp_path / "taslation.toml")


def test_the_settings_dialog_offers_80_to_130_percent_and_saves_the_size(hidden_root, in_force):
    got = []
    d = dlg.SettingsDialog(hidden_root, in_force, on_saved=got.append)
    assert d.text_scale.get() == "100 %" and "text_scale" in dlg.KEYS and "text_scale" in dlg.PAGE_SETTINGS
    assert dlg.text_scale_choices(1.0) == [f"{n} %" for n in range(80, 135, 5)]
    assert dlg.text_scale_choices(0.72)[0] == "72 %" and dlg.percent_of("85 %") == 0.85
    d.text_scale.set("90 %")
    assert d.save() is True and got == [{"text_scale": 0.9}]
    assert Settings.from_toml(in_force.config_path).text_scale == 0.9


def _book_pipeline(settings, current):
    applied = []
    return SimpleNamespace(annotations=SimpleNamespace(settings=dict(current)), _base_settings=settings,
                           set_book_settings=applied.append), applied


def test_the_book_dialog_sets_the_book_s_own_size_and_largest_size(hidden_root, in_force):
    pipeline, applied = _book_pipeline(in_force, {"detect_model": "on"})
    changed = []
    d = book_dlg.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: changed.append(True))
    assert d.scale_var.get() == "As in Settings (100 %)" and d.top_var.get() == "" and d.sizes() == {}
    d.scale_var.set("85 %")
    d.top_var.set("30")
    assert d.sizes() == {"text_scale": 0.85, "max_font_size": 30}
    d._apply()
    assert applied == [{"detect_model": "on", "text_scale": 0.85, "max_font_size": 30}] and changed == [True]


@pytest.mark.parametrize("raw", ["5", "x", "300", "10.5"])
def test_the_book_dialog_refuses_a_largest_size_that_does_not_fit(hidden_root, in_force, raw):
    pipeline, applied = _book_pipeline(in_force, {})
    d = book_dlg.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: None)
    d.top_var.set(raw)
    d._apply()
    assert applied == [] and str(d.problem.cget("text")) == (
        "The largest size: a whole number from 11 to 200 pixels, or empty for yours.")


def test_the_book_dialog_shows_the_book_s_own_values(hidden_root, in_force):
    pipeline, applied = _book_pipeline(in_force, {"text_scale": 1.2, "max_font_size": 48})
    d = book_dlg.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: None)
    assert d.scale_var.get() == "120 %" and d.top_var.get() == "48" and d.kept == {}
    d.scale_var.set(d.yours_scale)
    d.top_var.set("")
    d._apply()
    assert applied == [{}]  # back to the reader's own
