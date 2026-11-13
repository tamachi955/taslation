"""Catalogs of the window's languages, assembled from per-language lists that follow keys.KEYS.

New strings for a feature go into a module of their own, ``features/<feature>.py``, as a dict ``TEXTS`` of the
English key -> {language code: translation} for the 16 other languages (see `features`), and touch none of the
lists here: branches that add strings in modules of their own never conflict. `taslation.i18n` adds every feature
module's strings to its catalogs after these lists. A key is in the lists or in one feature module, never in both;
tests/test_i18n.py checks that, the languages and the placeholders."""

from __future__ import annotations

from .cjk import KO, ZH, ZH_TW
from .germanic_slavic import DE, NL, PL, RU
from .keys import KEYS
from .romance import ES, FR, IT, PT
from .turkic_sea import ID, TH, TR, VI

# code -> (name in its own language, translations)
_LISTS: dict[str, tuple[str, list[str]]] = {
    "es": ("Español", ES),
    "pt": ("Português (Brasil)", PT),
    "fr": ("Français", FR),
    "de": ("Deutsch", DE),
    "it": ("Italiano", IT),
    "nl": ("Nederlands", NL),
    "pl": ("Polski", PL),
    "ru": ("Русский", RU),
    "tr": ("Türkçe", TR),
    "id": ("Bahasa Indonesia", ID),
    "vi": ("Tiếng Việt", VI),
    "zh": ("简体中文", ZH),
    "zh-tw": ("繁體中文", ZH_TW),
    "ko": ("한국어", KO),
    "th": ("ไทย", TH),
}

NAMES: dict[str, str] = {code: name for code, (name, _values) in _LISTS.items()}
CATALOGS: dict[str, dict[str, str]] = {}
for _code, (_name, _values) in _LISTS.items():
    if len(_values) != len(KEYS):
        raise ImportError(f"locale {_code}: {len(_values)} strings for {len(KEYS)} keys")
    CATALOGS[_code] = dict(zip(KEYS, _values))

__all__ = ["CATALOGS", "KEYS", "NAMES"]
