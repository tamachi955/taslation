"""The window's languages: catalog lookups, the remembered choice, every language covers every key, and the
per-feature catalogs (locales/features) are found, complete and clash with nothing."""
from __future__ import annotations

import ast
import importlib
import io
import re
import sys
import tokenize
from pathlib import Path

from taslation import i18n, locales
from taslation.i18n import (
    CATALOGS,
    FEATURE_LANGUAGES,
    JA,
    UI_LANGUAGES,
    load_ui_language,
    save_ui_language,
    set_language,
    tr,
)
from taslation.locales import KEYS, features

UI = Path(__file__).resolve().parents[1] / "taslation" / "ui"
PLACEHOLDER = re.compile(r"\{(\w+)(?::[^}]*)?\}")


def test_lookup_and_fallback():
    assert set_language("ja") == "ja" and tr("Viewer:") == "ビューア:"
    assert set_language("es") == "es" and tr("Viewer:") == "Visor:"
    assert set_language("zh-tw") == "zh-tw" and tr("Book:") == "書名："
    assert set_language("th") == "th" and tr("Book:") == "ชื่อหนังสือ:"
    assert tr("not in the catalog at all") == "not in the catalog at all"
    assert set_language("xx") == "en" and tr("Viewer:") == "Viewer:"
    assert i18n.current() == "en"


def test_choice_is_remembered(tmp_path):
    assert load_ui_language(tmp_path) is None
    save_ui_language(tmp_path, "pt")
    assert load_ui_language(tmp_path) == "pt"
    (tmp_path / "ui.json").write_text('{"language": "klingon"}', encoding="utf-8")
    assert load_ui_language(tmp_path) is None


def _keys_used_in_window() -> set[str]:
    """Every key the window shows, in every module of taslation/ui: _("..."), the status lines said by key
    (say("...") on the Tk side, key="..." from the worker), and the words and messages it keeps by name."""
    keys: set[str] = set()
    for path in sorted(UI.rglob("*.py")):
        toks = list(tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline))
        for i, tok in enumerate(toks[:-2]):
            called = tok.string in ("_", "say") and toks[i + 1].string == "("
            named = tok.string == "key" and toks[i + 1].string == "="
            if tok.type == tokenize.NAME and (called or named) and toks[i + 2].type == tokenize.STRING:
                keys.add(ast.literal_eval(toks[i + 2].string))
    from taslation.ui import app

    keys |= set(app.STATUS_WORDS.values()) | {app.READY, app.NO_VIEWER, *app.READING_ONLY}
    return keys


def test_every_key_in_the_window_is_in_every_language():
    used = _keys_used_in_window()
    assert len(used) > 100
    for code, catalog in CATALOGS.items():
        if code == "en":
            continue
        missing = sorted(k for k in used if k not in catalog)
        assert not missing, (code, missing)
        assert all(v.strip() for v in catalog.values()), code


def test_key_list_matches_the_japanese_catalog():
    assert set(KEYS) == set(JA) and len(KEYS) == len(set(KEYS))


def test_placeholders_match_between_languages():
    for code, catalog in CATALOGS.items():
        for key, value in catalog.items():
            assert set(PLACEHOLDER.findall(key)) == set(PLACEHOLDER.findall(value)), (code, key)


def test_language_list():
    assert UI_LANGUAGES["en"] == "English" and UI_LANGUAGES["ja"] == "日本語"
    assert {"es", "pt", "fr", "de", "it", "nl", "pl", "ru", "tr", "id", "vi", "zh", "zh-tw", "ko", "th"} <= set(UI_LANGUAGES)
    assert set(CATALOGS) == set(UI_LANGUAGES)


# ------------------------------------------------------------------ per-feature catalogs (locales/features)
def _feature_homes() -> dict[str, list[str]]:
    """Each key of the feature modules -> the modules that define it."""
    homes: dict[str, list[str]] = {}
    for name, texts in i18n.FEATURES.items():
        for key in texts:
            homes.setdefault(key, []).append(name)
    return homes


def test_every_key_in_the_window_is_in_the_lists_or_in_one_feature_module():
    homes = _feature_homes()
    for key in sorted(_keys_used_in_window()):
        assert (key in KEYS) + len(homes.get(key, [])) == 1, (key, key in KEYS, homes.get(key, []))


def test_every_feature_string_has_every_language_and_its_placeholders():
    assert len(FEATURE_LANGUAGES) == 16 and set(FEATURE_LANGUAGES) == set(UI_LANGUAGES) - {"en"}
    assert not i18n.FEATURE_CLASHES  # no key both in the lists and in a feature module, nor in two feature modules
    assert all(len(modules) == 1 for modules in _feature_homes().values())
    for name, texts in i18n.FEATURES.items():
        for key, translations in texts.items():
            assert isinstance(key, str) and key.strip() and key not in KEYS, (name, key)
            odd = sorted(set(FEATURE_LANGUAGES) ^ set(translations))  # missing, or not a language of the window
            assert not odd, (name, key, odd)
            for code, text in translations.items():
                assert isinstance(text, str) and text.strip(), (name, key, code)
                assert set(PLACEHOLDER.findall(key)) == set(PLACEHOLDER.findall(text)), (name, key, code)
                assert CATALOGS[code][key] == text  # in the window's catalogs


def test_a_module_put_into_the_features_package_is_found_and_merged(tmp_path, monkeypatch):
    """The loader finds a module dropped into locales/features and its strings join the catalogs after the lists; a
    key the lists or another feature module have already is reported and not taken."""
    probe = {"Probe: {n} thing(s)": {code: f"[{code}] {{n}}" for code in FEATURE_LANGUAGES}}
    clash = {"Viewer:": {code: "?" for code in FEATURE_LANGUAGES}, "Probe: {n} thing(s)": {"ja": "?"}}
    modules = {"zz_probe": f"TEXTS = {probe!r}\n", "zz_probe_clash": f"TEXTS = {clash!r}\n",
               "zz_probe_empty": "# a module without TEXTS adds nothing\n"}
    for name, source in modules.items():
        (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    monkeypatch.setattr(features, "__path__", [*features.__path__, str(tmp_path)])
    importlib.invalidate_caches()
    try:
        found = i18n.load_features()
    finally:  # the probe modules leave no trace for the tests after this one
        for name in modules:
            sys.modules.pop(f"{features.__name__}.{name}", None)
            if name in vars(features):
                delattr(features, name)
    assert [name for name in found if name.startswith("zz_probe")] == list(modules)  # in name order
    assert found["zz_probe"] == probe and found["zz_probe_clash"] == clash and found["zz_probe_empty"] == {}
    catalogs = {"en": {}, "ja": dict(JA), **{code: dict(texts) for code, texts in locales.CATALOGS.items()}}
    clashes = i18n.merge_features(catalogs, {name: found[name] for name in modules})
    assert all(catalogs[code]["Probe: {n} thing(s)"] == f"[{code}] {{n}}" for code in FEATURE_LANGUAGES)
    assert catalogs["en"] == {} and catalogs["ja"]["Viewer:"] == JA["Viewer:"]  # the lists' translation stays
    assert len(clashes) == 2 and "'Viewer:' is in the positional lists" in clashes[0]
    assert "features/zz_probe.py and in features/zz_probe_clash.py" in clashes[1]
    monkeypatch.setattr(i18n, "CATALOGS", catalogs)
    try:
        assert set_language("ko") == "ko" and tr("Probe: {n} thing(s)") == "[ko] {n}" and tr("Viewer:") != "?"
    finally:
        set_language("en")
