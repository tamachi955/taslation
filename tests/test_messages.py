"""The message contract: every code the package produces is registered, every producer supplies exactly the params
its code declares, every template uses only those, and a Message behaves as the string it always was."""
from __future__ import annotations

import ast
import copy
import json
import pickle
import re
import string
from pathlib import Path

import pytest

from taslation import messages
from taslation.messages import FOLLOW_UPS, JOINER, PARAMS, TEMPLATES, Cancelled, Message, render

PACKAGE = Path(messages.__file__).resolve().parent
CODE_RE = re.compile(r"^[a-z]+(\.[a-z0-9_]+)+$")
BOOK_TEXT_NAMES = {"source_text", "translated_text", "texts", "outputs", "corpus", "pages_text", "group", "ja"}


def _fields(template: str) -> set[str]:
    return {name for _lit, name, _spec, _conv in string.Formatter().parse(template) if name}


def _producers() -> list[tuple[str, int, str, set[str] | None, ast.Call]]:
    """(file, line, code, the params the call supplies or None when it cannot be told, the call) of every
    ``Message("code", ...)`` and ``as_message(value, "code")`` in the package."""
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else "")
            first = node.args[0] if node.args else None
            codes = [first.value] if isinstance(first, ast.Constant) and isinstance(first.value, str) else []
            if isinstance(first, ast.IfExp) and all(isinstance(b, ast.Constant) for b in (first.body, first.orelse)):
                codes = [first.body.value, first.orelse.value]  # type: ignore[attr-defined]
            if name == "Message" and codes:
                keys: set[str] | None = {k.arg for k in node.keywords if k.arg is not None}
                if any(k.arg is None for k in node.keywords):
                    keys = None  # **params: not known here
                if len(node.args) > 1:
                    second = node.args[1]
                    if isinstance(second, ast.Dict) and all(isinstance(k, ast.Constant) for k in second.keys):
                        keys = (keys or set()) | {k.value for k in second.keys}  # type: ignore[union-attr]
                    else:
                        keys = None
                found.extend((path.name, node.lineno, code, keys, node) for code in codes)
            elif name == "as_message" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                found.append((path.name, node.lineno, node.args[1].value, {"detail"}, node))
    return found


def test_the_registry_is_consistent():
    assert set(TEMPLATES) == set(PARAMS)
    for code, template in TEMPLATES.items():
        assert CODE_RE.match(code), code
        assert _fields(template) <= set(PARAMS[code]), (code, _fields(template) - set(PARAMS[code]))
        assert len(set(PARAMS[code])) == len(PARAMS[code]), code
    for code, follows in FOLLOW_UPS.items():
        assert code in PARAMS
        for param, follow in follows:
            assert param in PARAMS[code] and follow in PARAMS, (code, param, follow)
            assert set(PARAMS[follow]) <= set(PARAMS[code]), (code, follow)  # the follow-up's params come from it


def test_every_producer_supplies_exactly_the_params_of_its_code():
    producers = _producers()
    assert len(producers) > 80  # the scan sees the package
    for file, line, code, keys, _call in producers:
        assert code in PARAMS, f"{file}:{line}: {code!r} is not registered"
        if keys is not None:
            assert keys == set(PARAMS[code]), f"{file}:{line}: {code} gets {sorted(keys)}, declares {PARAMS[code]}"


def test_every_registered_code_is_produced():
    produced = {code for _f, _l, code, _k, _c in _producers()}
    produced |= {follow for follows in FOLLOW_UPS.values() for _p, follow in follows}
    assert set(PARAMS) - produced == set()


def test_no_producer_hands_a_message_the_text_of_the_book():
    for file, line, code, _keys, call in _producers():
        for kw in call.keywords:
            value = kw.value
            name = value.id if isinstance(value, ast.Name) else value.attr if isinstance(value, ast.Attribute) else ""
            assert name not in BOOK_TEXT_NAMES, f"{file}:{line}: {code} gets {name} as {kw.arg}"


def test_every_template_renders_with_its_params():
    for code, params in PARAMS.items():
        text = str(Message(code, {p: 2 for p in params}))
        assert "{" not in text and "}" not in text, (code, text)


def test_a_message_is_the_string_it_says():
    m = Message("rename.same_name", book="Vol 3")
    text = "The book is called Vol 3 already."
    assert isinstance(m, str) and m == text and m.code == "rename.same_name"
    assert dict(m.params) == {"book": "Vol 3"}
    assert m.startswith("The book") and m.strip() == text and "Vol 3" in m
    assert "[" + m + "]" == f"[{text}]" and f"{m}" == text and "{}".format(m) == m
    assert type(str(m)) is str and json.dumps(m) == f'"{text}"'
    assert repr(m) == "Message('rename.same_name', {'book': 'Vol 3'})"
    with pytest.raises(AttributeError):
        m.code = "x"  # type: ignore[misc]
    with pytest.raises(TypeError):
        m.params["book"] = "Vol 4"  # type: ignore[index]
    for again in (pickle.loads(pickle.dumps(m)), copy.deepcopy(m), copy.copy(m)):
        assert isinstance(again, Message) and again.code == m.code and again == m


def test_rendering_never_breaks():
    assert str(Message("batch.note_retry_unusable", bubbles=1)) == (
        "request for 1 line came back unusable; retrying in two halves")
    assert "3 lines came back" in Message("batch.note_retry_unusable", bubbles=3)
    assert str(Message("rename.same_name")) == "The book is called {book} already."  # a missing param shows as it is
    assert str(Message("pipeline.translated", bubbles=1, seconds="soon", review=0, error="")) == "1 line(s) translated in soon s."  # wrong type: as text
    assert str(Message("no.such_code", a=1)) == "no.such_code (a=1)" and str(Message("no.such_code")) == "no.such_code"
    assert str(Message("ollama.not_loopback", url="http://x")) == (
        "Ollama URL must be a loopback http(s) address, got 'http://x'")  # a conversion


def test_follow_ups_come_only_when_their_param_is_set():
    error = Message("ollama.timeout", seconds=900.0)
    page = dict(bubbles=6, seconds=2.1, cached=0, new=1)
    clean = Message("pipeline.translated", review=0, error="", **page)
    assert str(clean) == "6 line(s) translated in 2 s."
    assert [s.code for s in clean.sentences()] == ["pipeline.translated"]
    failed = Message("pipeline.translated", review=2, error=error, **page)
    assert [s.code for s in failed.sentences()] == ["pipeline.translated", "pipeline.to_review", "pipeline.page_error"]
    assert dict(failed.sentences()[1].params) == {"review": 2} and dict(failed.sentences()[2].params) == {"error": error}
    assert str(failed) == str(clean) + JOINER + "2 worth a look (with Reader mode off, Menu > Review...)." + JOINER + (
        "The translation took too long. Press Translate to try again.")


def test_a_window_renders_with_its_own_catalog():
    catalog = {"pipeline.translated": "{bubbles} Zeile(n) übersetzt", "pipeline.to_review": "{review} ansehen"}
    m = Message("pipeline.translated", bubbles=3, seconds=4.0, cached=0, new=1, review=1,
                error=Message("ollama.unreachable", url="http://127.0.0.1:11434"))
    assert render(m, catalog) == ("3 Zeile(n) übersetzt - 1 ansehen - TASlation could not reach the translation program. "
                                  "Press Translate in a moment; it starts it by itself.")  # no entry: English
    assert render(m) == str(m) and render("plain") == "plain"


def test_exceptions_carry_their_message():
    from taslation.capture import CaptureError, ViewerCovered
    from taslation.ocr import ModelNotInstalled
    from taslation.translate import TranslationError

    plain = TranslationError("Ollama timed out after 900s")
    assert str(plain) == "Ollama timed out after 900s" == str(plain.message) and plain.message.code == "translator.failed"
    coded = TranslationError(Message("ollama.unreachable", url="http://127.0.0.1:11434"))
    assert str(coded) == str(coded.message) == "TASlation could not reach the translation program. Press Translate in a moment; it starts it by itself."
    assert coded.message.code == "ollama.unreachable" and coded.message.params["url"] == "http://127.0.0.1:11434"
    assert pickle.loads(pickle.dumps(coded)).message.code == "ollama.unreachable"
    covered = ViewerCovered()  # (said nowhere: the last good frame stays, `ui.live`)
    assert covered.message.code == "viewer.error" and str(covered) == "the viewer draws nothing behind a dialog of TASlation"
    assert isinstance(covered, CaptureError)
    assert CaptureError("the viewer gives no picture").message.code == "viewer.error"
    assert ModelNotInstalled(Message("ocr.model_missing", path="x", missing="y", command="z")).message.code == "ocr.model_missing"
    stop = Cancelled()
    assert stop.message.code == "pipeline.cancelled" and str(stop) == "cancelled"
    assert not isinstance(stop, TranslationError)  # a handler of failed requests never takes a cancel for one


def test_a_missing_ocr_model_says_how_to_get_it(tmp_path):
    from taslation.ocr import CharspotEngine, ModelNotInstalled

    with pytest.raises(ModelNotInstalled) as info:
        CharspotEngine(tmp_path / "nothing-here")
    m = info.value.message
    assert m.code == "ocr.model_missing" and m.params["path"] == str(tmp_path / "nothing-here")
    assert "install.cmd" in str(info.value)
