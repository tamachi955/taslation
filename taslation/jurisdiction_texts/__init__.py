"""The country parts of the legal notice in the window languages that are not a country's own: one module per
language (``ja.py``, ``es.py``, ...), each a ``SECTIONS`` dict from the ISO country code to the text, translated
from the English section in ``taslation.jurisdictions`` with the same hedging. A language module may cover any
subset of the countries; what it does not cover is shown in English with a note.

``load()`` returns {language: {code: text}} for every module present; ``jurisdictions`` merges them in.
"""

from __future__ import annotations

import importlib
import pkgutil

LANGUAGES: tuple[str, ...] = ("ja", "es", "pt", "fr", "de", "it", "nl", "pl", "ru", "tr", "id", "vi", "zh", "zh_tw", "ko", "th")


def load() -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        sections = getattr(module, "SECTIONS", None)
        if isinstance(sections, dict):
            found[info.name.replace("_", "-")] = {str(k).upper(): str(v) for k, v in sections.items()}
    return found


__all__ = ["LANGUAGES", "load"]
