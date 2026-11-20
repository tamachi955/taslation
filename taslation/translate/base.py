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
# A translator whose server reuses the beginning of a prompt only as far as the next prompt repeats it (PLaMo on
# Ollama, run by llama.cpp's server; measured on 2026-11-20, docs/OFFLINE_VERIFICATION.md, "What a PLaMo request costs
# the server": a prompt that parts from the last one within its last few pairs costs its tail only, about 0.1 s more,
# from the snapshots the server keeps of the last requests' ends; one that parts further back, a pair in the middle
# changed or the oldest ones cut, is computed from its start again, about 2.2 s per 1,000 tokens on a 6 GB GPU) is
# given earlier pairs that only grow, from request to request and from page to page, and are cut back to the newest
# `CONTEXT_CUT_TO` only once they pass `CONTEXT_GROWS_TO` (or no longer leave a request room: `GrowingContext.take`).
# Sliding them by a page at every page made the first request of every page compute its whole prompt again (1,050 ms
# against 142 ms for the later ones). Measured on OpenMantra (2026-11-16, PLaMo 3 Translate 2B on a 6 GB GPU): the
# model's time 63.7 -> 49.0 s for 30 pages read one by one, 73.9 -> 57.7 s for the whole book; chrF 41.6 -> 41.2 and
# 41.8 -> 42.0 (paired differences -0.19 +- 0.34 and -0.59 +- 0.41, a seed's own noise 0.45); no line left untranslated.
# A joined run of bubbles is one pair since 2026-11-20 (`SentPair`, as its request computed it), so the bounds count it
# once: the pairs hold a few more lines than they did when these were measured (prompts 3 to 6 % longer on OpenMantra).
CONTEXT_GROWS_TO = 60
CONTEXT_CUT_TO = 20


def grows_context(translator: Any) -> bool:
    """Whether *translator* is given earlier pairs that only grow (`GrowingContext`): one that says so
    (``grows_context``, `plamo.PlamoTranslator`). The chat translator, and one that does not say, gets the pairs of the
    last pages or runs as before."""
    return bool(getattr(translator, "grows_context", False))


class SentPair(tuple):
    """An earlier (Japanese, translation) pair as a translator's request computed it (`plamo.PlamoTranslator`): the
    Japanese as it was sent (a joined run of bubbles as one pair, a line per bubble) and the answer as the model wrote
    it. Given to the next request as it is (never made one line), so that the prompt holds what the server holds."""

    __slots__ = ()

    def __new__(cls, source: str, answer: str) -> "SentPair":
        return super().__new__(cls, (str(source), str(answer)))


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
        self._pairs.append(pair if isinstance(pair, SentPair) else (str(pair[0]), str(pair[1])))

    def extend(self, pairs: Any) -> None:
        for pair in pairs:
            self.append(pair)

    def clear(self) -> None:
        self._pairs.clear()

    def take(self, fits: Callable[[Sequence[tuple[str, str]]], bool] | None = None) -> list[tuple[str, str]]:
        """The pairs a request starts from (a copy), cut back first when they passed `grows_to` or *fits*(pairs) says
        a request would not fit after them; a cut halves them on from `cut_to` while *fits* still says no."""
        pairs, cut = self._taken(fits)
        if cut:
            self._pairs = pairs
            self.cuts += 1
        return list(pairs)

    def peek(self, fits: Callable[[Sequence[tuple[str, str]]], bool] | None = None) -> list[tuple[str, str]]:
        """What `take` would give now (cut back as it would cut them), changing nothing: the pairs the next request
        starts from while nothing is added meanwhile (`plamo.PlamoTranslator.warm_prefix`)."""
        return list(self._taken(fits)[0])

    def _taken(self, fits: Callable[[Sequence[tuple[str, str]]], bool] | None) -> tuple[list[tuple[str, str]], bool]:
        """(the pairs `take` gives, whether it cuts them back to give them)"""
        pairs = list(self._pairs)
        if not pairs:
            return [], False
        if len(pairs) > self.grows_to or (fits is not None and not fits(pairs)):
            pairs = pairs[-self.cut_to:] if self.cut_to else []
            while pairs and fits is not None and not fits(pairs):
                pairs = pairs[-(len(pairs) // 2):] if len(pairs) > 1 else []
            return pairs, True
        return pairs, False


class StoryContext(GrowingContext):
    """`GrowingContext` in story order: each pair is kept with its page's place in the story (`place`: a page's key,
    the order its screen was first seen in, `backlog.Screen.sight`), and a request at a page gets the pairs since the
    last cut of the pages up to it, in story order (a page's pairs in their own order) - the nearest translated pages
    before it, whichever were translated first. With nothing placed (None) a pair joins the last page and a request
    gets them all, so that pages that come in order are exactly what `GrowingContext` gives: what is added stays, and a
    request's prompt extends the one before it.

    A cut (past *grows_to* pairs, or *fits* says no) keeps the newest *cut_to* pairs of the request's own pages and
    every pair of the pages after it. With *switch_to* set (a request behind the reader, `backlog`), a request whose
    pairs part from the last request's after a common beginning gets that beginning and the newest *switch_to* of the
    rest at most, kept for that request alone: what the server recomputes for it stays small; the next such request,
    whose pairs grow those of that one, gets what that one was given and what came since (its prompt extends the one
    the server holds). The pairs are never changed in place (a page job's `Provisional` holds a shallow copy)."""

    def __init__(self, grows_to: int = CONTEXT_GROWS_TO, cut_to: int = CONTEXT_CUT_TO):
        super().__init__(grows_to, cut_to)
        self._held: list[tuple[float, int, tuple[str, str]]] = []  # (page key, order added, pair) since the last cut
        self._added = 0
        self.at: float | None = None  # the page placed: where pairs go and what a request starts from
        self.last: list[tuple[str, str]] = []  # the pairs the last request was given (`take`)
        self._last_full: list[tuple[str, str]] = []  # ... and its pairs before *switch_to* left some out
        self.switch_to: int | None = None

    def place(self, key: float | None) -> None:
        """The page requests are made for from now on (None: after every page so far)."""
        self.at = None if key is None else float(key)

    def _key(self) -> float:
        if self.at is not None:
            return self.at
        return max((k for k, _n, _p in self._held), default=0.0)

    def append(self, pair: tuple[str, str]) -> None:
        self.extend([pair])

    def extend(self, pairs: Any) -> None:
        key = self._key()
        added: list[tuple[float, int, tuple[str, str]]] = []
        for pair in pairs:
            added.append((key, self._added, pair if isinstance(pair, SentPair) else (str(pair[0]), str(pair[1]))))
            self._added += 1
        if added:
            self._held = self._held + added  # (a new list: never changed in place)

    def clear(self) -> None:
        self._held = []
        self.last = []
        self._last_full = []

    def _entries(self) -> list[tuple[float, int, tuple[str, str]]]:
        """The pairs since the last cut of the pages up to the one placed, in story order."""
        at = self.at
        return sorted((e for e in self._held if at is None or e[0] <= at), key=lambda e: (e[0], e[1]))

    def __len__(self) -> int:
        return len(self._entries())

    def __iter__(self) -> Any:
        return iter([e[2] for e in self._entries()])

    def _cut(self, fits: Callable[[Sequence[tuple[str, str]]], bool] | None
             ) -> tuple[list[tuple[float, int, tuple[str, str]]], bool]:
        entries = self._entries()
        if not entries:
            return [], False
        pairs = [e[2] for e in entries]
        if len(pairs) > self.grows_to or (fits is not None and not fits(pairs)):
            entries = entries[-self.cut_to:] if self.cut_to else []
            while entries and fits is not None and not fits([e[2] for e in entries]):
                entries = entries[-(len(entries) // 2):] if len(entries) > 1 else []
            return entries, True
        return entries, False

    def _switched(self, pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """(*switch_to* set) *pairs* with what parts from the last request's beyond *switch_to* left out (see the
        class's docstring)."""
        limit = self.switch_to
        last = self.last
        if limit is None or not last or pairs[:len(last)] == last:
            return pairs  # (it extends the last one)
        full = self._last_full
        if full != last and pairs[:len(full)] == full:
            return last + pairs[len(full):]  # (it grows a request that left pairs out: what that one was given, grown)
        common = 0
        for a, b in zip(pairs, last):
            if a != b:
                break
            common += 1
        if len(pairs) - common <= limit:
            return pairs  # (it parts from the last one by little)
        return pairs[:common] + (pairs[-limit:] if limit else [])

    def switches(self, fits: Callable[[Sequence[tuple[str, str]]], bool] | None = None) -> bool:
        """Whether the next request at the page placed, *switch_to* set, would not extend the last request's pairs
        (what the server holds): it parts from them, or stops short of them - the server's pairs of the page after it
        are left for its own, and the next request there computes them again."""
        pairs = [e[2] for e in self._cut(fits)[0]]
        last, full = self.last, self._last_full
        if not last or pairs[:len(last)] == last:
            return False
        return not (full != last and pairs[:len(full)] == full)

    def take(self, fits: Callable[[Sequence[tuple[str, str]]], bool] | None = None) -> list[tuple[str, str]]:
        entries, cut = self._cut(fits)
        if cut:
            at = self.at
            ahead = [e for e in self._held if at is not None and e[0] > at]
            self._held = entries + ahead
            self.cuts += 1
        full = [e[2] for e in entries]
        pairs = self._switched(full)
        self.last, self._last_full = list(pairs), full
        return list(pairs)

    def peek(self, fits: Callable[[Sequence[tuple[str, str]]], bool] | None = None) -> list[tuple[str, str]]:
        return self._switched([e[2] for e in self._cut(fits)[0]])


def tells_computed(translator: Any) -> bool:
    """Whether *translator* says which earlier pairs its prompts computed (``computed``, a list its ``translate_page``
    fills: `plamo.PlamoTranslator`): the pairs its server holds, which the caller's pairs that only grow take
    (`grown_pairs`)."""
    return grows_context(translator) and accepts(getattr(translator, "translate_page", None), "computed")


def _one_line(text: str) -> str:
    return " ".join(text.split()) if "\n" in text else text


def _as_set(text: str) -> str:
    """*text* without what setting a line on the page takes out of an answer: its spaces made one, stray emphasis
    asterisks (`Pipeline.tighten`)."""
    return " ".join(str(text).replace("*", "").split())


def grown_pairs(computed: Sequence[tuple[str, str]], finals: Sequence[tuple[str, str]],
                usable: Callable[[str, str], bool]) -> list[tuple[str, str]]:
    """What the pairs that only grow (`GrowingContext`) take after a request whose translator said what its prompts
    computed (*computed*, in order: a joined run as one pair, a line per bubble, the answer as the model wrote it),
    given *finals*, the lines asked as (Japanese, translation as the page sets it), in their order. Each computed pair
    whose every line *usable*(Japanese, translation) takes (a joined run's answer split back onto its lines,
    `continuation.split_back`) comes as it is, so that the next request's prompt extends the last one; but where the
    page sets one of its lines otherwise than by its spaces and stray asterisks (a name respelt as the series sheet
    spells it, `terms.spelt_right`), with the page's lines in its place (a line per bubble still), so that the lines
    after it read the sheet's spelling, as before (the next prompt then parts from what the server holds at that
    pair, which costs its tail only while the pair is recent). Then, at the end, each line of *finals* that none of
    them holds: a line filled by asking it again, or one whose first answer was not taken."""
    from collections import Counter, defaultdict, deque

    from .continuation import split_back

    shown_as: dict[str, deque[str]] = defaultdict(deque)  # each line's translations as the page sets them, in order
    for src, dst in finals:
        shown_as[_one_line(str(src))].append(str(dst))
    out: list[tuple[str, str]] = []
    held: Counter[str] = Counter()
    for pair in computed:
        src, dst = str(pair[0]), str(pair[1])
        parts = src.split("\n")
        answers = [dst] if len(parts) == 1 else split_back(dst, len(parts))
        if answers is None or not all(usable(s, " ".join(d.split())) for s, d in zip(parts, answers)):
            continue
        shown = [shown_as[s][held[s]] if held[s] < len(shown_as[s]) else None for s in parts]
        if all(f is not None for f in shown) and any(_as_set(f) != _as_set(d) for f, d in zip(shown, answers)):
            out.append(SentPair(src, "\n".join(str(f) for f in shown)))  # (as the page sets it)
        else:
            out.append(pair if isinstance(pair, SentPair) else SentPair(src, dst))
        held.update(parts)
    for src, dst in finals:
        key = _one_line(str(src))
        if held[key] > 0:
            held[key] -= 1
        else:
            out.append((str(src), str(dst)))
    return out


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
# running, the model missing, no translator) or wait as long (a timeout, a translation program that does not answer)
NO_REASK_CODES = frozenset({"ollama.timeout", "ollama.unreachable", "ollama.model_missing", "health.chosen_model_missing",
                            "translator.model_missing", "plamo.cannot_write", "ollama.not_loopback",
                            "pipeline.no_translator", "ollama.not_answering"})



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
                        after: int = REASK_AFTER,
                        on_answer: Callable[[int, str], None] | None = None) -> tuple[list[str], int, int]:
    """The lines of *texts* answered with their bare romanisation (`bare_romanisation`) asked for once more, each
    alone, with its neighbours: the lines before it with their translations (after *context*), at most *before*, as
    the earlier pairs, and the lines after it (then *upcoming*), at most *after*, as what follows. The new answer is
    taken when it is something else (a translation that reads: not empty); otherwise, or when the request fails,
    the first answer stays. *on_answer*(index, translation) is told each line's final translation once its request
    is over. Returns (the translations, how many lines were asked again, how many are still bare romanisations).
    Once *cancel* is set `Cancelled` is raised before the next request."""
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
            got = None
        text = str((got[0] if got else "") or "").strip()
        if text and text != texts[i] and not bare_romanisation(texts[i], text):
            out[i] = text
        if on_answer is not None:
            on_answer(i, out[i])
    left = sum(1 for t, o in zip(texts, out) if o and bare_romanisation(t, o))
    return out, len(todo), left
