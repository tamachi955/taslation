"""The translation models TASlation knows, and which of them a target language is translated with.

Two models, of which only one need be installed (they take 1.8 and 3.3 GB of disk; the installer fetches the one the
reader's language needs and swaps them when the language changes):

* `PLAMO`: PLaMo 3 Translate 2B (Preferred Networks, the PLaMo Community License), Q4_K_M, imported into Ollama under
  the name ``taslation-plamo3-translate-2b``. A translation model, not an instruction model: it translates one line
  at a time, given earlier pairs, reference text and a glossary (`taslation.translate.plamo.PlamoTranslator`). On
  OpenMantra (ja->en, whole book, 3 runs each) it scored chrF +5.9 above Qwen3.5 4B, twice as fast, in 1.9 GB of GPU
  memory. It writes no notes and does no review, shortening or alternatives of its own.
* `QWEN`: Qwen3.5 4B (Alibaba, Apache-2.0) through Ollama's chat (`taslation.translate.ollama.OllamaTranslator`), for
  the languages PLaMo cannot write: Brazilian Portuguese and Turkish (asked for them, it wrote Indonesian, Thai,
  Spanish or Azerbaijani; Tatoeba chrF 23 to 41 below Qwen).

`model_for_language` is that rule. The setting ``ollama_model`` keeps working for anyone who wants another model: its
default ``"auto"`` (`AUTO`) means "the model for the target language", anything else is an Ollama model name translated
with the chat prompts as before (`make_translator`). `choose` is what the window and the commands use: the model to
translate with given what Ollama has, and what to tell the reader when the language's own model is not installed
(``translator.model_missing`` or, when Qwen can stand in for PLaMo meanwhile, ``translator.other_model``; both carry
``model``, the Ollama name to install, ``name``, the name a reader knows, and ``language``).

Nothing here talks to Ollama; `choose` is given the list of installed models (`taslation.health.installed_models`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, NamedTuple

from ..messages import Message

AUTO = "auto"  # the setting ``ollama_model`` that lets the target language choose
MODEL_MISSING = "translator.model_missing"  # the code of `missing_message` {model, name, language}
OTHER_MODEL = "translator.other_model"  # Qwen translates meanwhile {model, name, language, used}


@dataclass(frozen=True)
class TranslatorModel:
    """One translation model: *kind* ("plamo" or "qwen": which translator class drives it), *ollama_name* (what Ollama
    calls it once installed), *display_name* (what the reader reads), *licence* (an SPDX id, or the licence's own name
    where it has none) and *size_gb* (on disk, as Ollama keeps it)."""

    kind: str
    ollama_name: str
    display_name: str
    licence: str
    size_gb: float


PLAMO = TranslatorModel(kind="plamo", ollama_name="taslation-plamo3-translate-2b",
                        display_name="PLaMo 3 Translate 2B", licence="PLaMo-Community-License", size_gb=1.8)
QWEN = TranslatorModel(kind="qwen", ollama_name="qwen3.5:4b", display_name="Qwen3.5 4B", licence="Apache-2.0",
                       size_gb=3.3)
MODELS = (PLAMO, QWEN)

# The target languages PLaMo 3 Translate cannot write (the window's names, `taslation.ui.constants.LANGUAGES`, and
# the other ways a settings file may spell them, lower case): they go to Qwen.
QWEN_LANGUAGES = frozenset({"portuguese (brazil)", "portuguese", "brazilian portuguese", "portuguese (brazilian)",
                            "pt", "pt-br", "turkish", "tr"})

# A target language (lower case: the window's names and a few other spellings) -> PLaMo's code for it, as its chat
# template wants one: lower case, two or three letters, a script after a hyphen where it needs one. Every target
# language of the window but the two of `QWEN_LANGUAGES` is here; a language PLaMo has no code for goes to Qwen too.
PLAMO_CODES: dict[str, str] = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de", "italian": "it", "russian": "ru",
    "polish": "pl", "dutch": "nl", "indonesian": "id", "vietnamese": "vi", "thai": "th",
    "chinese (simplified)": "zh-hans", "simplified chinese": "zh-hans", "chinese": "zh-hans",
    "chinese (traditional)": "zh-hant", "traditional chinese": "zh-hant",
    "korean": "ko", "arabic": "ar", "hebrew": "he", "hindi": "hi", "bengali": "bn", "japanese": "ja",
    # beyond the window's list, for a settings file that names them (PLaMo's README, "Supported Languages")
    "azerbaijani": "az", "belarusian": "be", "bulgarian": "bg", "catalan": "ca", "cebuano": "ceb", "estonian": "et",
    "basque": "eu", "persian": "fa", "gujarati": "gu", "croatian": "hr", "hungarian": "hu", "armenian": "hy",
    "javanese": "jv", "georgian": "ka", "kazakh": "kk", "khmer": "km", "lithuanian": "lt", "latvian": "lv",
    "malayalam": "ml", "marathi": "mr", "malay": "ms", "burmese": "my", "nepali": "ne", "punjabi": "pa",
    "sinhala": "si", "slovak": "sk", "slovenian": "sl", "serbian": "sr", "swahili": "sw", "tamil": "ta",
    "telugu": "te", "tagalog": "tl", "urdu": "ur", "uzbek": "uz",
}


def _key(language: Any) -> str:
    return " ".join(str(language or "").split()).lower()


def plamo_code(target_language: str) -> str | None:
    """PLaMo's language code for *target_language* (``"Chinese (Simplified)"`` -> ``"zh-hans"``); None for a language
    PLaMo cannot write or has no code for. A language given as a code PLaMo knows ("en", "zh-hant") is that code."""
    key = _key(target_language)
    if key in QWEN_LANGUAGES:
        return None
    if key in PLAMO_CODES:
        return PLAMO_CODES[key]
    return key if key in PLAMO_CODES.values() else None


def model_for_language(target_language: str) -> TranslatorModel:
    """The model *target_language* is translated with: `QWEN` for Brazilian Portuguese and Turkish (and any language
    PLaMo has no code for), `PLAMO` for every other."""
    return PLAMO if plamo_code(target_language) is not None else QWEN


def is_auto(setting: Any) -> bool:
    """Whether the setting ``ollama_model`` leaves the choice to the target language (``"auto"``, or nothing)."""
    return _key(setting) in ("", AUTO)


def by_ollama_name(name: Any) -> TranslatorModel | None:
    """The known model Ollama calls *name* (with or without its ":latest" tag); None for any other."""
    text = str(name or "").strip()
    for model in MODELS:
        if text == model.ollama_name or (":" not in model.ollama_name and text == f"{model.ollama_name}:latest"):
            return model
    return None


def wanted_name(setting: Any, target_language: str) -> str:
    """The Ollama name of the model the setting ``ollama_model`` asks for with *target_language*: the language's model
    (`model_for_language`) for ``"auto"``, else the setting itself."""
    return model_for_language(target_language).ollama_name if is_auto(setting) else str(setting).strip()


def _installed(models: Iterable[str] | None, name: str) -> bool:
    from ..health import has_model  # (health imports this package)

    return models is not None and has_model(list(models), name)


class Choice(NamedTuple):
    """What `choose` decided: *name*, the Ollama model to translate with (the wanted one when nothing can be used:
    the request then says it is missing); *model*, the known model it is (None for one of the reader's own);
    *problem*, what to tell the reader (None when all is well)."""

    name: str
    model: TranslatorModel | None
    problem: Message | None = None


def missing_message(model: TranslatorModel, target_language: str) -> Message:
    """``translator.model_missing``: the model *target_language* needs is not installed, and nothing can stand in."""
    return Message("translator.model_missing", model=model.ollama_name, name=model.display_name,
                   language=str(target_language))


def choose(setting: Any, target_language: str, installed: Iterable[str] | None) -> Choice:
    """The model to translate *target_language* with, given the setting ``ollama_model`` and the models Ollama has
    (*installed*; None when Ollama did not answer, which decides nothing: the wanted model then).

    With ``"auto"``: the language's model when it is installed; else, for a language PLaMo writes, Qwen when that is
    installed (``translator.other_model``: Qwen writes every language, a little less well); else the language's model
    all the same, and ``translator.model_missing`` (PLaMo cannot stand in for Qwen: it cannot write those languages).
    Any other setting is the reader's own model, as it always was: that one, or - when Ollama lacks it - the first one
    Ollama has (what ``health.chosen_other_model`` says)."""
    if not is_auto(setting):
        name = str(setting).strip()
        models = list(installed) if installed is not None else None
        if models and not _installed(models, name):
            return Choice(models[0], by_ollama_name(models[0]))
        return Choice(name, by_ollama_name(name))
    wanted = model_for_language(target_language)
    if installed is None or _installed(installed, wanted.ollama_name):
        return Choice(wanted.ollama_name, wanted)
    if wanted is PLAMO and _installed(installed, QWEN.ollama_name):
        return Choice(QWEN.ollama_name, QWEN, Message("translator.other_model", model=PLAMO.ollama_name,
                                                      name=PLAMO.display_name, language=str(target_language),
                                                      used=QWEN.display_name))
    return Choice(wanted.ollama_name, wanted, missing_message(wanted, target_language))


def make_translator(settings: Any, model: TranslatorModel | str | None = None, *, seed: int | None = None) -> Any:
    """The translator for *model* (a `TranslatorModel` or an Ollama name; default: the one the settings want for their
    target language, `wanted_name`), set up from *settings* (URL, timeout, temperature, keep_alive, target language):
    a `PlamoTranslator` for PLaMo, an `OllamaTranslator` (the chat prompts) for Qwen and for any
    other Ollama model. A known model chosen by the language carries it as ``auto_model``, so that a missing model is
    said as ``translator.model_missing``. *seed*: Ollama's sampling seed for every request (the evaluation tools; the
    app sends none)."""
    from .ollama import OllamaTranslator
    from .plamo import PlamoTranslator

    if model is None:
        model = wanted_name(settings.ollama_model, settings.target_language)
    known = model if isinstance(model, TranslatorModel) else by_ollama_name(model)
    name = model.ollama_name if isinstance(model, TranslatorModel) else str(model)
    common = dict(timeout=settings.ollama_timeout, temperature=settings.ollama_temperature,
                  target_language=settings.target_language, keep_alive=settings.ollama_keep_alive, seed=seed)
    if known is PLAMO:
        translator: Any = PlamoTranslator(settings.ollama_url, name, **common)
    else:
        translator = OllamaTranslator(settings.ollama_url, name, num_ctx=settings.ollama_num_ctx, **common)
    translator.auto_model = known if is_auto(settings.ollama_model) else None
    return translator


def kind_of(translator: Any) -> str:
    """"plamo" for a PLaMo translator, "ollama" for one of Ollama's chat, else the translator's name ("echo",
    "none", a stand-in's): whether a model change needs another translator (`needs_rebuild`)."""
    from .ollama import OllamaTranslator
    from .plamo import PlamoTranslator

    if isinstance(translator, PlamoTranslator):
        return "plamo"
    if isinstance(translator, OllamaTranslator):
        return "ollama"
    return str(getattr(translator, "name", type(translator).__name__))


def follow(translator: Any, settings: Any, name: str, target_language: str) -> Any:
    """The translator to translate *target_language* with the Ollama model *name* (what `choose` decided), given the
    one in use, *translator*: that one itself, its ``model`` and ``target_language`` set, while its class is the one
    for *name* (`needs_rebuild`); else a new one (`make_translator`, with *settings* and that language) that takes over
    what the window hung on the old one (``revive``, ``on_status``, ``before_load``) and its ``seed``. The caller hands a
    new one to the pipeline (`Pipeline.set_translator`, which lets the old one's model go). A translator that is no
    Ollama one (echo, a test's stand-in) only has ``model`` and ``target_language`` set."""
    if name and needs_rebuild(translator, name):
        fresh = make_translator(settings.with_overrides(target_language=target_language), name,
                                seed=getattr(translator, "seed", None))
        for hook in ("revive", "on_status", "before_load"):
            if getattr(translator, hook, None) is not None:
                setattr(fresh, hook, getattr(translator, hook))
        return fresh
    if name:
        translator.model = name
        if kind_of(translator) in ("plamo", "ollama"):
            translator.auto_model = by_ollama_name(name) if is_auto(settings.ollama_model) else None
    translator.target_language = target_language
    return translator


def needs_rebuild(translator: Any, name: str) -> bool:
    """Whether translating with the Ollama model *name* needs another translator than *translator*: one of Ollama's
    whose class is not the one for *name* (PLaMo or the chat prompts). Any other translator (echo, a test's stand-in)
    is left alone, its ``model`` set as before."""
    kind = kind_of(translator)
    if kind not in ("plamo", "ollama"):
        return False
    return (kind == "plamo") != (by_ollama_name(name) is PLAMO)
