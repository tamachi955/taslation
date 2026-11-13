"""The window's message catalogs (`taslation.message_texts`): every language has every code, with exactly the
placeholders of the English template; each renders through `messages.render` with params of every kind and with every
count; what is never translated stays; and a message names the window's buttons as the window itself names them."""
from __future__ import annotations

import importlib
import re
import string

import pytest

from taslation.message_texts import LANGUAGES, catalog
from taslation.messages import FOLLOW_UPS, JOINER, PARAMS, TEMPLATES, Message, render

COUNTS = (0, 1, 2, 5, 21, 1000)
URL = "http://127.0.0.1:11434"
# languages that phrase counts so that no word agrees with the number: no plural, or more than two forms
NO_AGREEMENT = {"ja", "zh", "zh-tw", "ko", "th", "vi", "id", "tr", "ru", "pl"}
# never translated: the product, Ollama, commands, file and protocol names, key names
KEEP = ("TASlation", "Ollama", "> Ollama", "install.cmd", "ollama pull {model}", "`{command}`", "manga-ocr", "OCR", "HTTP", "JSON",
        "http(s)", "Windows", "hwnd", "Left", "Right", "PageDown", "Space")
# code -> the window's buttons it names, by their English keys in the window catalogs (taslation.i18n)
BUTTONS = {
    "batch.failed_requests": ("Read whole book...",),
    "batch.stopped": ("Read whole book...",),
    "batch.readings_kept": ("Read whole book...",),
    "batch.read_again": ("Read whole book...",),
    "batch.continues_translating": ("Read whole book...",),
    "batch.stored_read_again": ("Read whole book...",),
    "batch.not_book": ("Finished reading",),
    "batch.viewer_lost": ("Finished reading", "Stop"),
    "batch.stopped_reading": ("Finished reading",),
    "ollama.slow": ("Stop (Esc)",),
}
KEY_HINT = re.compile(r"\s*[(（](?:Esc|Échap|F\d+)[)）]\s*$")  # "Stop (Esc)" is the Stop button

MESSAGE_PARAMS = {"error", "reason", "problem"}
TEXT_PARAMS = {"title", "key", "call", "detail", "translator", "url", "model", "path", "missing", "command", "wanted",
               "used", "unit", "device", "folder", "book", "name", "language"}
FLOAT_PARAMS = {"seconds"}
INT_PARAMS = {"percent", "page", "pages", "bubbles", "new", "cached", "dropped", "done", "total", "characters", "terms", "chunk",
              "chunks", "failed", "limit", "minutes", "pid", "units", "incomplete", "group", "entries",
              "translations", "review", "status", "chars", "hwnd", "problems", "mb", "free", "need", "batch",
              "lines", "kept", "again", "queued", "files"}
TEXTS = {"title": "Store - Browser", "key": "Left", "call": "PrintWindow", "detail": "something broke",
         "translator": "ollama:qwen3.5:4b", "url": URL, "model": "qwen3.5:4b", "path": "/models/manga-ocr",
         "missing": "config.json", "command": "ollama pull qwen3.5:4b", "wanted": "qwen3.5:4b", "used": "gemma3:4b",
         "unit": "0a1b2c3d", "device": "GPU", "folder": "/keep", "book": "A book", "name": "PLaMo 3 Translate 2B",
         "language": "English"}
NESTED = {"error": Message("ollama.timeout", seconds=900.0), "reason": Message("batch.finished_reading"),
          "problem": Message("health.ollama_down", url=URL)}
ALL = ("en", *LANGUAGES)


def _module(lang: str):
    return importlib.import_module(f"taslation.message_texts.{lang.replace('-', '_')}")


def _fields(template: str) -> list[tuple[str, str, str | None]]:
    """(name, format spec, conversion) of every placeholder in *template*."""
    return [(name, spec or "", conv) for _lit, name, spec, conv in string.Formatter().parse(template) if name is not None]


def _kind(spec: str) -> str:
    return "plural" if "|" in spec else "number" if spec else "plain"


def _letters(template: str) -> bool:
    """Whether *template* says anything besides its placeholders."""
    return any(re.search(r"[^\W\d_]", lit) for lit, *_rest in string.Formatter().parse(template))


def _params(code: str, count: int = 3) -> dict[str, object]:
    out: dict[str, object] = {}
    for name in PARAMS[code]:
        if name in MESSAGE_PARAMS:
            out[name] = NESTED[name]
        elif name in TEXT_PARAMS:
            out[name] = TEXTS[name]
        elif name in FLOAT_PARAMS:
            out[name] = 12.34
        else:
            out[name] = count
    return out


def _expected(name: str, spec: str, conv: str | None, value: object, cat: dict[str, str]) -> str:
    """What the placeholder (*name*, *spec*, *conv*) shows for *value*."""
    if isinstance(value, Message):
        return render(value, cat)
    if "|" in spec:
        one, _, many = spec.partition("|")
        return f"{value} {one if value == 1 else many}"
    if spec:
        return format(value, spec)
    return repr(value) if conv == "r" else str(value)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_code_and_follow_up_has_a_template(lang):
    texts = _module(lang).TEMPLATES
    assert set(texts) - set(TEMPLATES) == set(), f"{lang}: unknown codes"
    assert set(TEMPLATES) - set(texts) == set(), f"{lang}: missing codes"
    follow_ups = {follow for follows in FOLLOW_UPS.values() for _param, follow in follows}
    assert follow_ups <= set(texts)
    for code, template in texts.items():
        assert isinstance(template, str) and template.strip() == template and template, (lang, code)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_placeholders_are_those_of_the_english_template(lang):
    for code, template in _module(lang).TEMPLATES.items():
        english = _fields(TEMPLATES[code])
        mine = _fields(template)
        assert {n for n, _s, _c in mine} == {n for n, _s, _c in english}, (lang, code, mine, english)
        for name, spec, conv in mine:
            assert name.isidentifier() and name in PARAMS[code], (lang, code, name)
            theirs = [(s, c) for n, s, c in english if n == name]
            kinds = {_kind(s) for s, _c in theirs}
            if _kind(spec) == "number":  # the same digits as in English (seconds: "{seconds:.1f}")
                assert spec in {s for s, _c in theirs}, (lang, code, name, spec)
            elif "number" in kinds:
                pytest.fail(f"{lang} {code}: {{{name}}} drops the number format of the English template")
            if _kind(spec) == "plural":
                one, _, many = spec.partition("|")
                assert one.strip() and many.strip() and "|" not in many, (lang, code, spec)
            assert conv is None or conv in {c for _s, c in theirs}, (lang, code, name, conv)
        if _letters(TEMPLATES[code]):
            assert template != TEMPLATES[code], f"{lang} {code} is not translated"


@pytest.mark.parametrize("lang", ALL)
def test_what_install_cmd_provides_is_never_a_command(lang):
    cat = catalog(lang)
    for code in ("health.model_missing", "health.other_model", "health.ocr_missing"):
        assert "install.cmd" in cat[code] and "{command}" not in cat[code], (lang, code)
    for code in ("health.chosen_model_missing", "health.chosen_other_model"):
        assert "install.cmd" not in cat[code] and "{command}" in cat[code], (lang, code)


@pytest.mark.parametrize("lang", ALL)
def test_every_template_renders_with_params_of_its_kind(lang):
    cat = catalog(lang)
    for code, template in cat.items():
        params = _params(code)
        text = render(Message(code, params), cat)
        assert "{" not in text and "}" not in text, (lang, code, text)
        for name, spec, conv in _fields(template):
            assert _expected(name, spec, conv, params[name], cat) in text, (lang, code, name, text)


@pytest.mark.parametrize("lang", ALL)
def test_every_count_renders(lang):
    cat = catalog(lang)
    for code, template in cat.items():
        counted = [f for f in _fields(template) if f[0] in INT_PARAMS]
        if not counted:
            continue
        for n in COUNTS:
            params = _params(code, n)
            text = render(Message(code, params), cat)
            assert "{" not in text and "}" not in text, (lang, code, n, text)
            for name, spec, conv in counted:
                assert _expected(name, spec, conv, n, cat) in text, (lang, code, n, text)


def test_counts_need_no_agreement_where_the_language_has_none_or_several_forms():
    for lang in NO_AGREEMENT:
        for code, template in _module(lang).TEMPLATES.items():
            assert not [f for f in _fields(template) if "|" in f[1]], f"{lang} {code}: a plural word in {template!r}"


def test_every_param_has_a_kind():
    names = {name for params in PARAMS.values() for name in params}
    assert names <= MESSAGE_PARAMS | TEXT_PARAMS | FLOAT_PARAMS | INT_PARAMS, names - (
        MESSAGE_PARAMS | TEXT_PARAMS | FLOAT_PARAMS | INT_PARAMS)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_what_is_never_translated_stays(lang):
    for code, template in _module(lang).TEMPLATES.items():
        for token in KEEP:
            if token in TEMPLATES[code]:
                assert token in template, f"{lang} {code}: {token!r} is missing from {template!r}"


def test_messages_name_the_buttons_as_the_window_does():
    from taslation import i18n

    for lang in ALL:
        window = i18n.CATALOGS.get(lang, {})
        cat = catalog(lang)
        for code, keys in BUTTONS.items():
            for key in keys:
                label = KEY_HINT.sub("", window.get(key) or key)
                assert label in cat[code], f"{lang} {code}: the window calls the button {label!r}: {cat[code]!r}"


def test_every_window_language_has_a_catalog():
    from taslation import i18n

    assert set(LANGUAGES) == set(i18n.UI_LANGUAGES) - {"en"}
    for lang in LANGUAGES:
        assert catalog(lang) == {**TEMPLATES, **_module(lang).TEMPLATES}


def test_english_for_en_and_for_any_other_code():
    before = dict(TEMPLATES)
    for lang in ("en", "xx", "", None, "ja-xx"):
        assert catalog(lang) == TEMPLATES
    english = catalog("en")
    english["batch.started"] = "changed"
    assert TEMPLATES == before and catalog("en") == before  # a copy every time, the registry untouched
    assert catalog("ZH_TW") == catalog("zh-tw") != catalog("zh")
    assert catalog("ja") is not catalog("ja")


@pytest.mark.parametrize("lang", LANGUAGES)
def test_a_message_and_its_nested_messages_render_in_one_language(lang):
    cat = catalog(lang)
    reason, error = Message("batch.finished_reading"), Message("ollama.unreachable", url=URL)
    done = Message("batch.finished", pages=3, bubbles=12, seconds=40.0, minutes=1, failed=1, error=error, reason=reason)
    text = render(done, cat)
    assert render(reason, cat) in text
    assert text.endswith(JOINER + render(Message("batch.failures", failed=1, error=error), cat))  # the follow-up
    assert str(reason) not in text  # nothing of it in English
    stopped = render(Message("batch.not_started", reason=error), cat)
    assert render(error, cat) in stopped and str(error) not in stopped
    page = render(Message("pipeline.translated", bubbles=3, seconds=4.0, cached=0, new=1, review=0, error=error), cat)
    assert page.endswith(JOINER + render(error, cat)) and str(error) not in page


def test_japanese_reads_as_the_review_asked():
    ja = catalog("ja")
    page = dict(cached=1, new=0, review=0, error="")
    assert render(Message("pipeline.from_cache", bubbles=6, seconds=0.1, **page), ja) == "6 行を以前の翻訳から表示しました。"
    assert render(Message("pipeline.translated", bubbles=6, seconds=2.1, **{**page, "review": 2}), ja) == (
        "6 行を翻訳しました（2 秒）。" + JOINER + "確認するとよいものが 2 件あります（翻訳者の役割、「レビュー...」）。")
    assert "1冊まるごと読み取り" in ja["batch.stopped"] and "1ページずつ翻訳" in ja["batch.stopped"]
    assert ja["translator.model_missing"].startswith("この言語の翻訳モデル")
    assert render(Message("batch.scanning_page", page=3), ja) == "3 ページ目を読み取り中..."


def test_plural_words_follow_the_count():
    es = catalog("es")
    one = render(Message("batch.failed_requests", failed=1, reason=Message("batch.reply_unusable"), pages=1, seconds=1.0,
                         turns=0), es)
    many = render(Message("batch.failed_requests", failed=5, reason=Message("batch.reply_unusable"), pages=21,
                          seconds=1.0, turns=20), es)
    assert "(1 solicitud fallida, 1 página leída)" in one and "(5 solicitudes fallidas, 21 páginas leídas)" in many
    ru = render(Message("pipeline.translated", bubbles=21, seconds=2.0, cached=0, new=1, review=0, error=""),
                catalog("ru"))
    assert ru == "Переведено строк: 21 (2 с)."
    done = dict(seconds=40.0, minutes=1, error=Message("ollama.unreachable", url=URL), reason=Message("batch.finished_reading"))
    de = render(Message("batch.finished", pages=3, bubbles=12, failed=1, **done), catalog("de"))
    assert de.startswith("Einlesen des ganzen Buchs fertig: 3 Seiten, 12 Zeilen übersetzt in 1 min - fertig gelesen.")
    assert "1 Teil konnte nicht übersetzt werden." in de
    de = render(Message("batch.finished", pages=1, bubbles=1, failed=2, **done), catalog("de"))
    assert de.startswith("Einlesen des ganzen Buchs fertig: 1 Seite, 1 Zeile übersetzt in 1 min")
    assert "2 Teile konnten nicht übersetzt werden." in de
