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
    m = Message("batch.scanning_page", page=3)
    assert isinstance(m, str) and m == "Scanning page 3..." and m.code == "batch.scanning_page"
    assert dict(m.params) == {"page": 3}
    assert m.startswith("Scanning") and m.strip() == "Scanning page 3..." and "page 3" in m
    assert "[" + m + "]" == "[Scanning page 3...]" and f"{m}" == "Scanning page 3..." and "{}".format(m) == m
    assert type(str(m)) is str and json.dumps(m) == '"Scanning page 3..."'
    assert repr(m) == "Message('batch.scanning_page', {'page': 3})"
    with pytest.raises(AttributeError):
        m.code = "x"  # type: ignore[misc]
    with pytest.raises(TypeError):
        m.params["page"] = 4  # type: ignore[index]
    for again in (pickle.loads(pickle.dumps(m)), copy.deepcopy(m), copy.copy(m)):
        assert isinstance(again, Message) and again.code == m.code and again == m


def test_rendering_never_breaks():
    assert str(Message("batch.continuing", lines=1)) == "Going on with the pages read earlier: 1 line to translate"
    assert "3 lines to translate" in Message("batch.continuing", lines=3)
    assert str(Message("batch.scanning_page")) == "Scanning page {page}..."  # a missing param shows as it is
    assert str(Message("pipeline.translated", bubbles=1, seconds="soon", review=0, error="")) == "1 line(s) translated in soon s."  # wrong type: as text
    assert str(Message("no.such_code", a=1)) == "no.such_code (a=1)" and str(Message("no.such_code")) == "no.such_code"
    assert str(Message("batch.waiting_other_tab", title="Store - Browser")).startswith(
        "Waiting: the viewer window shows 'Store - Browser' now")


def test_follow_ups_come_only_when_their_param_is_set():
    error = Message("ollama.timeout", seconds=900.0)
    done = dict(pages=3, bubbles=12, seconds=40.0, minutes=1, error="", reason=Message("batch.finished_reading"))
    clean = Message("batch.finished", failed=0, **done)
    assert str(clean) == ("Whole-book scan done: 3 pages, 12 lines translated in 1 minute - you finished reading.")
    assert [s.code for s in clean.sentences()] == ["batch.finished"]
    failed = Message("batch.finished", failed=2, **{**done, "error": error})
    assert [s.code for s in failed.sentences()] == ["batch.finished", "batch.failures"]
    assert dict(failed.sentences()[1].params) == {"failed": 2, "error": error}
    assert str(failed) == str(clean) + JOINER + (
        "2 part(s) could not be translated. They are done when you read those pages, or in the next "
        "whole-book run.")


def test_a_window_renders_with_its_own_catalog():
    catalog = {"batch.finished": "Fertig: {pages} Seite(n) - {reason}", "batch.finished_reading": "Ende des Buchs",
               "batch.failures": "{failed} Anfrage(n) fehlgeschlagen ({error})"}
    m = Message("batch.finished", pages=3, bubbles=12, seconds=40.0, failed=1,
                error=Message("ollama.unreachable", url="http://127.0.0.1:11434"), reason=Message("batch.finished_reading"))
    assert render(m, catalog) == ("Fertig: 3 Seite(n) - Ende des Buchs - 1 Anfrage(n) fehlgeschlagen "
                                  "(TASlation could not reach the translation program. Press F5 in a moment; it starts it by itself.)")  # no entry: English
    assert render(m) == str(m) and render("plain") == "plain"


def test_exceptions_carry_their_message():
    from taslation.capture import CaptureError, ViewerCovered
    from taslation.ocr import ModelNotInstalled
    from taslation.translate import TranslationError

    plain = TranslationError("Ollama timed out after 900s")
    assert str(plain) == "Ollama timed out after 900s" == str(plain.message) and plain.message.code == "translator.failed"
    coded = TranslationError(Message("ollama.unreachable", url="http://127.0.0.1:11434"))
    assert str(coded) == str(coded.message) == "TASlation could not reach the translation program. Press F5 in a moment; it starts it by itself."
    assert coded.message.code == "ollama.unreachable" and coded.message.params["url"] == "http://127.0.0.1:11434"
    assert pickle.loads(pickle.dumps(coded)).message.code == "ollama.unreachable"
    covered = ViewerCovered("the viewer draws nothing behind TASlation")  # as the window raises it today
    assert covered.message.code == "viewer.covered" and str(covered) == (  # the text given is not kept
        "The viewer stopped drawing because TASlation covers it completely. Un-maximise TASlation, or move it so that "
        "a strip of the viewer stays visible.")
    assert isinstance(covered, CaptureError)
    assert CaptureError("the viewer gives no picture").message.code == "viewer.error"
    assert ModelNotInstalled(Message("ocr.model_missing", path="x", missing="y", command="z")).message.code == "ocr.model_missing"
    stop = Cancelled()
    assert stop.message.code == "pipeline.cancelled" and str(stop) == "cancelled"
    assert not isinstance(stop, TranslationError)  # a handler of failed requests never takes a cancel for one


def test_capture_errors_name_what_failed():
    from taslation.capture import CaptureError
    from taslation.capture.windows import IS_WINDOWS, key_code

    if not IS_WINDOWS:
        pytest.skip("Windows only")
    with pytest.raises(CaptureError) as info:
        key_code("NoSuchKey")
    assert info.value.message.code == "viewer.unknown_key" and info.value.message.params["key"] == "NoSuchKey"
    assert str(info.value).startswith("unknown key name: 'NoSuchKey'")


def test_a_missing_ocr_model_says_how_to_get_it(tmp_path):
    from taslation.ocr import CharspotEngine, ModelNotInstalled

    with pytest.raises(ModelNotInstalled) as info:
        CharspotEngine(tmp_path / "nothing-here")
    m = info.value.message
    assert m.code == "ocr.model_missing" and m.params["path"] == str(tmp_path / "nothing-here")
    assert "install.cmd" in str(info.value)
