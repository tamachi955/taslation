"""What TASlation's working parts say (`taslation.messages`) in the window's languages other than English.

One module per language (``ja.py``, ``es.py``, ..., ``zh_tw.py`` for "zh-tw", ``ko.py``, ``th.py``), each a ``TEMPLATES`` dict
from every code of `taslation.messages.TEMPLATES` (the follow-ups included) to its template in that language:

* the same placeholders as the English template; a count may carry the language's own ``{n:one|many}`` words
  where the language agrees a noun with two forms, and is phrased so that it needs no agreement where the language
  has none or more than two forms (Japanese, Chinese, Korean, Vietnamese, Indonesian, Turkish, Thai; Russian, Polish);
* the register of the window (Japanese desu/masu, German Sie, French vous, Spanish tú, ...) and the names of the
  window's buttons and menus exactly as that language's window catalog (`taslation.i18n`) has them;
* params, commands (``ollama pull ...``, ``python setup_models.py``), URLs, model names and TASlation as they are.

``catalog(lang)`` gives the catalog `taslation.messages.render` takes, for a window language code.
"""

from __future__ import annotations

import importlib

from ..messages import TEMPLATES as ENGLISH

LANGUAGES: tuple[str, ...] = ("ja", "es", "pt", "fr", "de", "it", "nl", "pl", "ru", "tr", "id", "vi", "zh", "zh-tw", "ko", "th")


def _language(lang: str | None) -> str:
    """*lang* as the window names its languages: lower case, a hyphen ("zh_TW" is "zh-tw")."""
    return str(lang or "").strip().lower().replace("_", "-")


def catalog(lang: str | None) -> dict[str, str]:
    """{code: template} for every code of `taslation.messages.TEMPLATES`, in the window language *lang* ("ja",
    "zh-tw", ...); English for "en" and for a language that has no module here. A new dict on every call."""
    code = _language(lang)
    if code not in LANGUAGES:
        return dict(ENGLISH)
    texts: dict[str, str] = importlib.import_module(f"{__name__}.{code.replace('-', '_')}").TEMPLATES
    return {key: texts.get(key) or english for key, english in ENGLISH.items()}


__all__ = ["LANGUAGES", "catalog"]
