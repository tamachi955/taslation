"""Translators that do not translate: for debugging, tests and OCR-only runs."""

from __future__ import annotations

import threading
from typing import Any, Callable, Mapping, Sequence

from .base import Cancelled, TranslationError  # noqa: F401 - TranslationError: what the tests' translators raise


def _check(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


class EchoTranslator:
    """Returns the source text unchanged (useful to check detection/OCR without Ollama)."""

    name = "echo"

    def translate_page(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = (), notes: str = "",
                       upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None,
                       cancel: threading.Event | None = None,
                       on_slow: Callable[[float], None] | None = None) -> list[str]:
        _check(cancel)
        return list(texts)


class NullTranslator:
    """Translates nothing; every bubble ends up 'untranslated'."""

    name = "none"

    def translate_page(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = (), notes: str = "",
                       upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None,
                       cancel: threading.Event | None = None,
                       on_slow: Callable[[float], None] | None = None) -> list[str]:
        _check(cancel)
        return ["" for _ in texts]


class DictTranslator:
    """Looks translations up in a mapping (tests): *mapping* source text -> translation, *default* for the others.
    Every request is kept: its lines in ``calls``, its other arguments in ``kwargs``."""

    name = "dict"

    def __init__(self, mapping: Mapping[str, str], default: str = ""):
        self.mapping = dict(mapping)
        self.default = default
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, Any]] = []

    def translate_page(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = (), notes: str = "",
                       upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None,
                       on_item: Callable[[int, str], None] | None = None,
                       cancel: threading.Event | None = None,
                       on_slow: Callable[[float], None] | None = None) -> list[str]:
        _check(cancel)  # a cancelled request answers nothing, as a model's would
        self.calls.append(list(texts))
        self.kwargs.append({"context": list(context), "notes": notes, "upcoming": list(upcoming),
                            "meta": [dict(m) for m in meta] if meta else [], "streamed": on_item is not None})
        out = [self.mapping.get(t, self.default) for t in texts]
        if on_item is not None:  # as a streaming model would: each translation in turn, before the list
            for i, text in enumerate(out):
                if text:
                    on_item(i, text)
        return out
