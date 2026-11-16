from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

from ..messages import Cancelled, Message, as_message  # noqa: F401 - Cancelled: raised by translators on cancel


class TranslationError(RuntimeError):
    """A request to the translator failed. ``.message`` says what went wrong as a `Message` (a code and its
    params); ``str(error)`` is its English text. Given a plain string, the message is ``translator.failed``
    carrying that text."""

    message: Message

    def __init__(self, message: Message | str = ""):
        self.message = as_message(message, "translator.failed")
        super().__init__(self.message)


class Translator(Protocol):
    name: str

    def translate_page(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = (), notes: str = "",
                       upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None,
                       on_item: Callable[[int, str], None] | None = None,
                       cancel: threading.Event | None = None,
                       on_slow: Callable[[float], None] | None = None) -> list[str]:
        """Translate bubbles (in reading order). Returns one string per input.

        ``context``: previous (source, translation) pairs; ``notes``: the premises, the
        reader's series sheet as text (names, terms, honorifics: `Pipeline.premises`,
        an `annotations.Premises` that carries the sheet itself as ``.sheet``);
        ``upcoming``: later bubbles, for context only (a translator may leave them out);
        ``meta``: per bubble, reader-made facts (speaker, kind, continues, note, room).

        Translating is all a translator does (2026-11-06: the model's notes, the review
        pass, shortening and alternatives were removed, for both translators alike).
        ``on_item`` (optional; a translator may leave the argument out): called with
        (index, translation) for each bubble as soon as its translation is there,
        while the others are still being written. Those are early looks; the list
        returned is what counts.
        ``cancel`` (optional, may be left out too): once the event is set, the request
        ends as soon as it can (a streamed one between two pieces of the answer) and
        `Cancelled` is raised; nothing is returned.
        ``on_slow`` (optional, may be left out): called once, with the seconds waited,
        when the request has produced nothing for a while (the translator's
        ``slow_after``; a model that is still loading, say).

        A translator may leave facts of ``meta`` unused; how far its model follows a
        region's hint (``note``) it says with ``hint_support`` (`hint_support`), and
        the region editor tells the reader.
        """
        ...


HINT_FOLLOWS = "follows"  # the model is given the hint with its bubble and follows it (the chat translator)
HINT_SOMETIMES = "sometimes"  # the model is given the hint and follows it only now and then (PLaMo, measured)


def hint_support(translator: Any) -> str:
    """How far the model of *translator* follows a region's hint for the model (the reader's ``note`` in ``meta``):
    `HINT_FOLLOWS` for the chat translator (`ollama.OllamaTranslator`: the bubble's "note"), `HINT_SOMETIMES` for PLaMo
    (`plamo.PlamoTranslator.hint_support`: a line of its ``context``, followed in about half of the answers of a
    test), which the region editor says under the hint. One that does not say is taken to follow it (a test's
    stand-in, the echo)."""
    return str(getattr(translator, "hint_support", HINT_FOLLOWS) or HINT_FOLLOWS)


def uses_room(translator: Any) -> bool:
    """Whether *translator* puts a region's room (``room`` in ``meta``: the characters of translation its bubble has
    space for) in its request: the chat translator does (`ollama.OllamaTranslator.uses_room`: the bubble's "room"),
    PLaMo does not (`plamo.PlamoTranslator.uses_room`: a line and its context, nothing of its length). One that does
    not say is taken to (a test's stand-in, the echo): the pipeline measures the rooms before its request then."""
    return bool(getattr(translator, "uses_room", True))


# --- earlier pairs that only grow, cut back rarely ------------------------------------------------------------
# A translator whose server reuses the beginning of a prompt only when the next prompt extends it byte for byte (PLaMo
# on Ollama: a prompt that differs anywhere, even in its last earlier pair, is computed from its start again) is given
# earlier pairs that only grow, from request to request and from page to page, and are cut back to the newest
# `CONTEXT_CUT_TO` only once they pass `CONTEXT_GROWS_TO` (or no longer leave a request room: `GrowingContext.take`).
# Sliding them by a page at every page made the first request of every page compute its whole prompt again (1,050 ms
# against 142 ms for the later ones). Measured on OpenMantra (2026-11-16, PLaMo 3 Translate 2B on a 6 GB GPU): the
# model's time 63.7 -> 49.0 s for 30 pages read one by one, 73.9 -> 57.7 s for the whole book; chrF 41.6 -> 41.2 and
# 41.8 -> 42.0 (paired differences -0.19 +- 0.34 and -0.59 +- 0.41, a seed's own noise 0.45); no line left untranslated.
CONTEXT_GROWS_TO = 60
CONTEXT_CUT_TO = 20


def grows_context(translator: Any) -> bool:
    """Whether *translator* is given earlier pairs that only grow (`GrowingContext`): one that says so
    (``grows_context``, `plamo.PlamoTranslator`). The chat translator, and one that does not say, gets the pairs of the
    last pages or runs as before."""
    return bool(getattr(translator, "grows_context", False))


class GrowingContext:
    """The earlier (Japanese, translation) pairs of a translator that `grows_context`: what is added stays, in its
    order, so that a request's prompt extends the one before it; once they pass *grows_to* pairs, or the translator
    finds that a request would have no room left after them (`take`'s *fits*), they are cut back to the newest
    *cut_to* (fewer when even those do not fit). Memory only. Not shared between threads (the page's worker, or a
    whole-book run's translation thread, has its own)."""

    def __init__(self, grows_to: int = CONTEXT_GROWS_TO, cut_to: int = CONTEXT_CUT_TO):
        self.grows_to = max(0, int(grows_to))
        self.cut_to = max(0, min(int(cut_to), self.grows_to))
        self._pairs: list[tuple[str, str]] = []
        self.cuts = 0  # how many times they were cut back (for the tests and the evaluation)

    maxlen = None  # (as a deque says it: no bound of its own)

    def __len__(self) -> int:
        return len(self._pairs)

    def __iter__(self) -> Any:
        return iter(list(self._pairs))

    def append(self, pair: tuple[str, str]) -> None:
        self._pairs.append((str(pair[0]), str(pair[1])))

    def extend(self, pairs: Any) -> None:
        for pair in pairs:
            self.append(pair)

    def clear(self) -> None:
        self._pairs.clear()

    def take(self, fits: Callable[[Sequence[tuple[str, str]]], bool] | None = None) -> list[tuple[str, str]]:
        """The pairs a request starts from (a copy), cut back first when they passed `grows_to` or *fits*(pairs) says
        a request would not fit after them; a cut halves them on from `cut_to` while *fits* still says no."""
        if not self._pairs:
            return []
        if len(self._pairs) > self.grows_to or (fits is not None and not fits(self._pairs)):
            self._pairs = self._pairs[-self.cut_to:] if self.cut_to else []
            self.cuts += 1
            while self._pairs and fits is not None and not fits(self._pairs):
                self._pairs = self._pairs[-(len(self._pairs) // 2):] if len(self._pairs) > 1 else []
        return list(self._pairs)


def context_fits(translator: Any, notes: str) -> Callable[[Sequence[tuple[str, str]]], bool] | None:
    """What `GrowingContext.take` asks of *translator* with the premises *notes*: its ``context_fits`` (whether a
    request may start from the pairs), None for a translator that has none."""
    fits = getattr(translator, "context_fits", None)
    if fits is None:
        return None
    return lambda pairs: bool(fits(pairs, notes))


def accepts(fn: Any, name: str) -> bool:
    """Whether the callable *fn* takes a keyword argument *name* (or any keyword: ``**kwargs``)."""
    import inspect

    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


# --- asking again for the lines a reply left without a translation ------------------------------------------
REASK_GROUP = 4  # consecutive lines asked for again in one request, at most (then each line still missing alone)
REASK_BEFORE = 10  # translated lines before a group shown as the earlier bubbles
REASK_AFTER = 6  # lines after a group shown as the bubbles that come next


@dataclass
class Reasked:
    """What `ask_for_missing` did: the translations with the lines it filled, and how many lines it asked for (each
    time counted), in how many requests, how many of them failed, how many lines it filled, and whether it was
    stopped (`on_error` said so) before it was done."""

    texts: list[str]
    asked: int = 0
    requests: int = 0
    failed: int = 0
    filled: int = 0
    stopped: bool = False


# a failed request after which no lines are asked for again: the next request would fail the same way (Ollama not
# running, the model missing, no translator) or wait as long (a timeout)
NO_REASK_CODES = frozenset({"ollama.timeout", "ollama.unreachable", "ollama.model_missing", "health.chosen_model_missing",
                            "translator.model_missing", "plamo.cannot_write", "ollama.not_loopback",
                            "pipeline.no_translator"})



# a request for lines asked for again that failed with one of these was answered, with nothing usable in it (every
# line left empty, or nothing that reads): the model's answer for those lines, not a failed request
ANSWERED_CODES = frozenset({"ollama.bad_answer"})


def worth_asking_again(error: Any) -> bool:
    """Whether lines are worth asking for again after a request failed with *error* (a Message, or an exception
    carrying one): not when the next request would fail the same way or wait as long (`NO_REASK_CODES`)."""
    message = getattr(error, "message", error)
    return getattr(message, "code", "") not in NO_REASK_CODES and not any(text in str(message) for text in ("reach the translation program", "cannot reach Ollama"))


def reask_groups(missing: Sequence[int], size: int) -> list[list[int]]:
    """*missing* (indices, ascending) in runs of consecutive indices, each cut into groups of at most *size*."""
    groups: list[list[int]] = []
    for i in missing:
        if groups and groups[-1][-1] == i - 1 and len(groups[-1]) < max(1, size):
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def ask_for_missing(translator: Any, texts: Sequence[str], outputs: Sequence[str],
                    usable: Callable[[int, str], bool], *, context: Sequence[tuple[str, str]] = (), notes: str = "",
                    upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None,
                    call_args: dict[str, Any] | None = None, cancel: threading.Event | None = None,
                    on_error: Callable[[TranslationError], bool] | None = None,
                    on_item: Callable[[int, str], None] | None = None, group: int = REASK_GROUP,
                    before: int = REASK_BEFORE, after: int = REASK_AFTER) -> Reasked:
    """Ask *translator* again for the lines of *texts* whose translation in *outputs* is not usable
    (``usable(index, text)`` says which are): first the runs of consecutive such lines, at most *group* lines a
    request, then each line still without one on its own (unless it was asked alone already and answered). Each
    request carries the lines' neighbours: the translated lines before them (after *context*, the pairs before
    *texts*), at most *before*, and the lines after them (then *upcoming*), at most *after*; *notes*, *meta* (per
    line) and *call_args* (``cancel``/``on_slow``, those the translator takes) go with it as with the first
    request. *on_item*(index, text) gets each filled line as it comes, when the translator hands translations
    over (an ``on_item`` argument).

    A request that fails is counted and handed to *on_error*, which says whether to go on (False: stop asking, a
    failure the next requests would repeat); without *on_error* the asking stops at the first failure. A reply
    with nothing usable in it (`ANSWERED_CODES`) is no failure: it is the model's answer for those lines. Once
    *cancel* is set `Cancelled` is raised before the next request (the translator raises it during one). Only
    usable translations replace a line: a line the model gives nothing usable for, even asked alone, stays as
    it was."""
    n = len(texts)
    out = [str(o or "").strip() for o in list(outputs)[:n]] + [""] * max(0, n - len(outputs))
    result = Reasked(texts=out)
    todo = [i for i in range(n) if not usable(i, out[i])]
    if not todo:
        return result
    answered_alone: set[int] = set()
    rounds: list[list[list[int]] | None] = [reask_groups(todo, group), None]
    for groups in rounds:
        if groups is None:  # second round: each line still missing on its own
            groups = [[i] for i in range(n) if not usable(i, out[i]) and i not in answered_alone]
        for g in groups:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            earlier = list(context) + [(texts[j], out[j]) for j in range(g[0]) if usable(j, out[j])]
            later = [texts[j] for j in range(g[-1] + 1, n)] + list(upcoming)
            lines = [texts[i] for i in g]
            facts = [dict(meta[i]) if meta and i < len(meta) and meta[i] else {} for i in g]
            kwargs = dict(call_args or {})
            if on_item is not None and accepts(translator.translate_page, "on_item"):
                kwargs["on_item"] = lambda k, text, g=g: on_item(g[k], text) if 0 <= k < len(g) else None
            result.requests += 1
            result.asked += len(g)
            try:
                got = translator.translate_page(lines, earlier[-before:] if before > 0 else [], notes,
                                                later[:max(0, after)], meta=facts if any(facts) else None, **kwargs)
            except TranslationError as e:
                if getattr(e.message, "code", "") in ANSWERED_CODES:
                    if len(g) == 1:  # the model answered this line alone, with nothing usable: so be it
                        answered_alone.add(g[0])
                    continue
                result.failed += 1
                if on_error is None or not on_error(e):
                    result.stopped = True
                    return result
                continue
            if len(g) == 1:
                answered_alone.add(g[0])
            for k, i in enumerate(g):
                text = str((got[k] if k < len(got) else "") or "").strip()
                if usable(i, text):
                    out[i] = text
                    result.filled += 1
    return result


# --- a short kana line answered with its romaji alone ------------------------------------------------------
ROMANISED_MAX_KANA = 3  # a line of up to this many kana answered with its romaji alone is asked for once more
REASK_ROMANISED = True  # whether such a line is asked for again (`ask_again_romanised`)
# an answer that spells one of these is a translation, though it reads as the romaji too ("Oh!" for おっ!, "Eh?")
INTERJECTIONS = frozenset({"a", "ah", "ahh", "aah", "o", "oh", "ohh", "ooh", "e", "eh", "u", "uh", "ha", "hah", "heh",
                           "haha", "ahaha", "hehe", "ho", "hm", "hmm", "mm", "um", "umm", "oi", "huh", "hey", "wow",
                           "ow", "yo", "no", "so"})


def bare_romanisation(source: str, output: str) -> bool:
    """Whether *output* is nothing but the romaji of *source*, a line of 1-3 kana (dots, dashes and marks aside):
    "Nani?" for なに?, "Hai" for はい: a word the model did not translate. An interjection the target language writes
    the same way ("Oh!" for おっ!, `INTERJECTIONS`) is a translation."""
    import re
    import unicodedata

    from .renderings import fold_latin, romaji

    kana = "".join(ch for ch in unicodedata.normalize("NFKC", str(source or ""))
                   if "ぁ" <= ch <= "ヺ" and ch not in "ー・")
    rest = "".join(ch for ch in unicodedata.normalize("NFKC", str(source or ""))
                   if ch.isalnum() and not "ぁ" <= ch <= "ー")
    if not 1 <= len(kana) <= ROMANISED_MAX_KANA or rest:
        return False
    if re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", str(output or "").lower())) in INTERJECTIONS:
        return False
    out = fold_latin(str(output or ""))
    latin = fold_latin(romaji(kana))
    return bool(out) and bool(latin) and re.sub(r"[^a-z]", "", out) == latin


def _after_on_page(texts: Sequence[str], meta: Sequence[dict[str, Any]] | None, i: int,
                   upcoming: Sequence[str]) -> list[str]:
    """The lines after line *i* of *texts* on its page (each line's facts ``page``, when *meta* has them), then
    *upcoming* when the page does not end within *texts*."""
    page = (meta[i] or {}).get("page") if meta and i < len(meta) else None
    out = []
    for j in range(i + 1, len(texts)):
        if page is not None and meta and j < len(meta) and (meta[j] or {}).get("page") != page:
            return out
        out.append(texts[j])
    return out + list(upcoming)


def ask_again_romanised(translator: Any, texts: Sequence[str], outputs: Sequence[str], *,
                        context: Sequence[tuple[str, str]] = (), notes: str = "", upcoming: Sequence[str] = (),
                        meta: Sequence[dict[str, Any]] | None = None, call_args: dict[str, Any] | None = None,
                        cancel: threading.Event | None = None, before: int = REASK_BEFORE,
                        after: int = REASK_AFTER) -> tuple[list[str], int, int]:
    """The lines of *texts* answered with their bare romanisation (`bare_romanisation`) asked for once more, each
    alone, with its neighbours: the lines before it with their translations (after *context*), at most *before*, as
    the earlier pairs, and the lines after it (then *upcoming*), at most *after*, as what follows. The new answer is
    taken when it is something else (a translation that reads: not empty); otherwise, or when the request fails,
    the first answer stays. Returns (the translations, how many lines were asked again, how many are still bare
    romanisations). Once *cancel* is set `Cancelled` is raised before the next request."""
    out = [str(o or "").strip() for o in list(outputs)[:len(texts)]] + [""] * max(0, len(texts) - len(outputs))
    todo = [i for i, (t, o) in enumerate(zip(texts, out)) if o and bare_romanisation(t, o)]
    for i in todo:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        earlier = list(context) + [(texts[j], out[j]) for j in range(i) if out[j]]
        later = _after_on_page(texts, meta, i, upcoming)
        facts = [dict(meta[i])] if meta and i < len(meta) and meta[i] else None
        try:
            got = translator.translate_page([texts[i]], earlier[-before:] if before > 0 else [], notes,
                                            later[:max(0, after)], meta=facts, **dict(call_args or {}))
        except TranslationError:
            continue
        text = str((got[0] if got else "") or "").strip()
        if text and text != texts[i] and not bare_romanisation(texts[i], text):
            out[i] = text
    left = sum(1 for t, o in zip(texts, out) if o and bare_romanisation(t, o))
    return out, len(todo), left
