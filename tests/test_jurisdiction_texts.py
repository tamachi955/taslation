"""The country parts of the notice: every window language has a version of every country's part, each starting
with the country's name, the same hedges kept, and the texts of a country's own languages taken as written."""
from __future__ import annotations

from taslation import jurisdiction_texts, jurisdictions
from taslation.i18n import UI_LANGUAGES


def test_every_language_covers_every_country():
    found = jurisdiction_texts.load()
    codes = set(jurisdictions.JURISDICTIONS)
    for lang in UI_LANGUAGES:
        if lang == "en":
            continue
        own = {code for code, j in jurisdictions.JURISDICTIONS.items() if lang in j.languages}
        assert set(found.get(lang, {})) | own >= codes, (lang, sorted(codes - set(found.get(lang, {})) - own))
    for lang in UI_LANGUAGES:
        for code, j in jurisdictions.JURISDICTIONS.items():
            text = j.sections.get(lang)
            assert text and text.strip(), (lang, code)
            assert jurisdictions.section(code, lang) == text


def test_the_parts_keep_their_shape():
    for code, j in jurisdictions.JURISDICTIONS.items():
        en = j.sections["en"]
        assert en.startswith(j.name + ".") and "Content:" in en, code
        for lang, text in j.sections.items():
            assert "TASlation" in text or "TASlation" not in en, (lang, code)
            assert 0.4 * len(en) <= len(text) <= 2.5 * len(en) or lang in ("ja", "zh", "zh-tw", "ko"), (lang, code)
            assert "http" not in text, (lang, code)


def test_a_country_language_is_the_written_one():
    de = jurisdictions.JURISDICTIONS["DE"]
    assert de.sections["de"].startswith("Deutschland.")
    assert jurisdictions.section("de", "de") == de.sections["de"]
    assert jurisdictions.default_language("ch") == "de" and jurisdictions.default_language("other") is None
