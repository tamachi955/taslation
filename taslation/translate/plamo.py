"""Translation with PLaMo 3 Translate 2B (Preferred Networks) through the local Ollama: TASlation's default translator
for every target language it writes (`taslation.translate.models`).

PLaMo 3 Translate is a translation model, not an instruction model. It takes one text at a time in its own prompt
format, PFML3 (its README, "PFML3 Prompt Format"): a ``translation`` dataset tag, optional reference ``context``,
earlier source/translation pairs, a ``glossary`` for the text, then the text and the language to write, and it answers
with the bare translation. Ollama renders the model's own chat template for /api/chat; the template in the file of the
revision pinned first could not be given the target language that way (it fell back to Japanese), and the one in the
file pinned since 2026-11-14 takes it from a ``[plamo-translate]`` system message and builds the same prompt as
`pfml_prompt` (checked for plain, context, history and glossary inputs). The prompt is built here by hand all the same
and sent to /api/generate with ``raw: true``, as PFN recommend for applications, so no template is used; the
beginning-of-sequence token, which raw mode does not add, comes first, and the answer is stopped at the next
``<|plamo:tag|>`` or ``<|plamo:bos|>``.

What the pipeline hands a translator maps to it like this:

* the premises (the reader's series sheet as text: `Pipeline.premises`) -> ``context``, the same for every line of a
  request, so that Ollama reuses the cached beginning of the prompt; a speaker the reader gave a line is added to it
  for that line;
* the earlier bubbles (the ``context`` pairs, the book's own lines before these) and the lines of this request done so
  far -> the earlier pairs, the oldest left out first when the prompt would not fit (`PROMPT_SHARE`). The pipeline and
  the backlog give it pairs that only grow, cut back rarely (``grows_context``, `base.GrowingContext`, cut
  earlier when a request would not fit after them: `context_fits`), so that a request's first prompt extends the
  last prompt of the request before, which Ollama then does not compute again. A line done holds its pair as its
  request computed it (`_computed`, `base.SentPair`): a joined run one pair, a line per bubble, and the answer as the
  model wrote it; the request's ``computed`` list hands them to the caller's pairs (`base.grown_pairs`, which puts in
  the page's own line where the page sets it otherwise than by spaces and stray asterisks: a name respelt as the
  series sheet spells it). A run split into its lines left the next prompt otherwise than the server held it from
  there on (measured on 2026-11-20, docs/OFFLINE_VERIFICATION.md, "What a PLaMo request costs the server");
* the sheet's renderings that a line names (`terms._sheet_hits`: the reader's terms and names, the forms a speaker
  uses, a name with its honorific: what the review flags check a translation against), the parts of the sheet's
  names (`terms.name_words`), and the book's names held so far (`renderings.BookNames`: a name's first rendering, as
  the book showed it to be a name) -> its ``glossary``, with the Japanese as the line writes it;
* every line of the request -> one request of its own, in reading order; but a run of lines whose sentence goes on
  in the next bubble (the facts' ``continues``: the reader's mark, or the rule of `continuation`) -> one request, a
  line break between bubbles, its answer split back onto them (`continuation.split_back`), or, when it does not
  come back as one line per bubble, each line asked alone with the line after it as ``context``;
* the Japanese after a line (the request's own lines, then ``upcoming``) -> ``context`` for a line that goes on in
  the next bubble (`FOLLOW_OPEN`: the next one) and for a line asked alone, as a line asked again is
  (`FOLLOW_ALONE`: the next two), never past its page; not for the others, whose ``context`` stays the same from line
  to line;
* a region's hint for the model (the facts' ``note``) -> a paragraph of its own in the ``context`` of that line,
  after the speaker (`_hint`; that line's prompt then begins otherwise, and Ollama works it out anew);
  ``hint_support`` "sometimes", which the region editor says under the hint. Only the
  request of the line itself carries it: a run of bubbles joined into one request carries none (it would be the
  reference of the run's other bubbles as well), but when the joined answer does not split back and each bubble is
  asked by itself, that bubble's request does; and Ask again asks one bubble. No other line's prompt ever holds it:
  the earlier pairs are the Japanese and the translations, the Japanese after a line is the Japanese. The answer to
  a line with a hint is, like any answer, an earlier pair of the lines after it. A line without a hint goes as it
  went before, byte for byte. Measured on 2026-11-15 with invented lines, three seeds each
  (docs/OFFLINE_VERIFICATION.md, "A translator's hint and PLaMo"): the hint alone as a line of ``context``, the best
  of four ways tried, was followed in 38 of 78 answers (17 without it), mended 21 of the 61 the model got wrong and
  spoilt none; it did best for how a name or a term is read (which the series sheet settles every time, as
  ``glossary``) and now and then a pronoun or a number, never the register or the people addressed; and hints that
  should change nothing changed the words of 5 of 30 answers (a synonym, a full stop added): a hint can change the
  wording of its own line where it need not;
* a region's kind and its room -> nothing. As a line of ``context`` the kind "shout" gave 3 of 30 answers an
  exclamation mark (1 without it) and the room in characters brought none of 30 within it; the kind "sfx" made 14 of
  30 romanised sound effects English ones (Gashan: Crash) and 3 a wrong one.

Translating is all it does, as for the other translator: TASlation has no notes of the model's own, no review pass, no
shortening and no alternatives (removed 2026-11-06). A line whose reply copied the Japanese or came back empty is asked
for again by the pipeline (`base.ask_for_missing`); every request for a line this translator was asked for before goes
with another sampling seed (`_draw`), so that it is a new draw, not the same answer again.

Everything else is `OllamaTranslator`'s: the loopback-only connection without proxies, the model loaded on demand and
released (`ensure_loaded`, `release`, `release_now`, `warm_up`, `gpu_share`, ``on_status``,
``keep_alive``, the layers on the GPU ``num_gpu`` in every request and warm-up when it is set), Ollama
started again when a request finds it gone (``revive``), the fixed ``seed`` of the evaluation tools, and the same
`TranslationError` message codes; a model that is not installed is ``translator.model_missing`` when the target
language chose it (``auto_model``). A request given ``cancel`` or ``on_slow`` is streamed, so that Stop ends it at
once and a model still loading is noticed. No text of a book is ever put into an error.
"""

from __future__ import annotations

import random
import re
import threading
from collections import deque
from typing import Any, Callable, Sequence

from ..messages import Cancelled, Message
from ..ocr import place as ocr_place
from .base import CONTEXT_GROWS_TO, HINT_SOMETIMES, SentPair, TranslationError
from .continuation import MAX_JOINED, joined, runs, split_back
from .models import PLAMO, plamo_code
from .ollama import KEEP_ALIVE, OllamaTranslator, _ignore
from .renderings import learn, names_of

TAG, MSG, KEY, VAL = "<|plamo:tag|>", "<|plamo:msg|>", "<|plamo:key|>", "<|plamo:val|>"
INDEX, ITEM, BOS = "<|plamo:index|>", "<|plamo:item|>", "<|plamo:bos|>"
STOPS = [TAG, BOS]  # where an answer ends: the next element, or the next sequence
SOURCE_LANG = "ja"
NUM_CTX = 8192  # Ollama's context for PLaMo: a line's prompt is ~1,200 tokens with 40 earlier pairs (1.9 GB in all)
# the earlier pairs a request starts from, at most; the lines of the request done so far are added to them, never one
# taken off the front: the prompts of a request then share their beginning, which Ollama computes once (cutting the
# oldest pair at every line made each prompt new: prompt processing fell from 5,800 to 900 tokens a second). The
# pipeline and the backlog give it pairs that only grow from request to request and are cut back rarely
# (`base.GrowingContext`, ``grows_context``), never more than this
HISTORY_PAIRS = CONTEXT_GROWS_TO
# tokens (reckoned high, `tokens_about`) a request keeps for its own lines after the earlier pairs it is given: a page's
# lines (30 at most were asked at once by the whole-book run of earlier versions) with their answers and a line's room
# for its answer (`GrowingContext.take` cuts the pairs back when they would leave less: `context_fits`)
REQUEST_ROOM = 2400
# A line's prompt is kept within this share of the context, its answer's room taken off first; its length in tokens is
# reckoned high (`tokens_about`): a reserved token one, any other character outside ASCII one (Japanese, Chinese,
# Korean: fewer in fact), three ASCII characters one (English: four in fact). Counting characters instead took
# <|plamo:tag|> for 13 tokens and cut the earlier pairs of almost every line (and with them the shared beginning)
PROMPT_SHARE = 0.9
ASKED_KEPT = 4096  # how many lines `_draw` remembers having been asked for (then it starts again)
# the Japanese after a line given as its ``context`` (`_following`): the next line for a line that goes on in the
# next bubble and was not joined with it, the next two for a line asked for alone (asked again); none for the
# other lines, so that their ``context`` stays the same and Ollama reuses the prompt's beginning (a context that
# changed from line to line made the run 2.2 times as slow on OpenMantra). Tried there for the subjects and the
# addressees a line leaves out, and not kept: the page's lines as every line's context (+0.20 chrF, 95 % interval
# -0.37 to +0.81, the model's time per page 2.29 -> 4.54 s) and the next two lines as every line's (7 times as slow)
FOLLOW_OPEN = 1
FOLLOW_ALONE = 2
# The beginning the next page's first request will start with (the premises and the earlier pairs: `warm_prefix`) is
# computed while the reader reads when the server does not hold this many tokens of it (reckoned high), about half a
# second of the development machine's GPU; less is not worth a request
WARM_LEAST = 256
# ... in steps of this many tokens at most (reckoned high), each a request of its own that extends the one before: once
# a server has a prompt it computes it to its end, a request cancelled or dropped meanwhile too (measured 2026-11-20 on
# Ollama 0.40.16: a turn would have waited up to 4.9 s), so the reader's turn stops the warming between two steps and
# waits for none (a step takes 0.25 s or so there, while the page is found and read before its first request)
WARM_STEP = 128
WARM_STEP_MOST_S = 0.6  # a step that took longer (a slower machine): the warming stops after it
# ... and what the server may hold is reckoned from this many of the translator's last prompts (`_held_now`): the
# server keeps earlier prompts in RAM (``LLAMA_ARG_CACHE_RAM``, `ollama_start`) and computes a request from the one it
# shares most with; a warming where it held the beginning in one of them made the turn after it slower. A server that
# keeps none (its settings unknown) is warmed less often than it could be, never more
HELD_KEPT = 16
WARM_TIMEOUT = 10.0  # seconds a warming step may take at most
# the time a request's prompt is expected to take (`_expected_s`, the first byte's bound `ollama.NO_ANSWER_TIMES` it):
# the tokens the server does not hold of it times the seconds a prompt token took, the slowest of the last RATES_KEPT
# requests that computed RATE_LEAST_TOKENS tokens or more
RATES_KEPT = 8
RATE_LEAST_TOKENS = 64
_RESERVED = re.compile(r"<\|plamo:[a-z_]+\|>")
_NOTE_LINE = re.compile(r"^- (.+?) = (.+?)(?: \(.*\))?$")


def tokens_about(prompt: str) -> int:
    """About how many tokens *prompt* is, reckoned high (see `PROMPT_SHARE`)."""
    rest = _RESERVED.sub("", prompt)
    wide = sum(1 for ch in rest if ord(ch) > 127)
    return len(_RESERVED.findall(prompt)) + wide + (len(rest) - wide + 2) // 3


def clean(text: Any) -> str:
    """*text* without PLaMo's reserved tokens (a text that held one would break the prompt), trimmed."""
    return _RESERVED.sub("", str(text or "")).strip()


def one_line(text: Any) -> str:
    """A line's Japanese as a request gives it to the model, as the line itself and as an earlier pair alike (so that
    the pair a line leaves in a request's history is the pair the next page's request starts from): its spaces and
    line breaks made one space when it has a line break, else as it is."""
    text = str(text)
    return " ".join(text.split()) if "\n" in text else text


def earlier_pairs(pairs: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """*pairs* as a request's earlier pairs: each line's Japanese made one line (`one_line`), but a pair a request
    computed (`base.SentPair`: a joined run, a line per bubble) as it is, so that the prompt holds what the server
    computed."""
    return [p if isinstance(p, SentPair) else (one_line(p[0]), p[1]) for p in pairs]


def request_lines(texts: Sequence[str], meta: Sequence[dict[str, Any] | None] | None) -> tuple[list[str], list[dict[str, Any]]]:
    """A page request's lines as `PlamoTranslator.translate_page` asks them (`one_line`) and a copy of each one's facts
    (*meta*, {} where there is none)."""
    lines = [one_line(t) for t in texts]
    return lines, [dict((meta[i] or {}) if meta and i < len(meta) else {}) for i in range(len(lines))]


class PageSession:
    """`PlamoTranslator.translate_page`'s state between the runs of one page's lines (`continuation.runs`): the earlier
    pairs the next run starts from (the request's *context*, cut to the translator's ``history_pairs``, then each run
    as it computed it: `PlamoTranslator._computed`), and the *computed* list it hands them to. `run` asks one run as
    the page's request asks it; the names it shows are learnt there, before the next run's glossary is made. `mark`
    says where it stands - its pairs, the translator's draws (`PlamoTranslator.draws`) and the book's names
    (`renderings.BookNames`) - and `rewind` puts it back there: runs asked too soon (`streaming`), as though they had
    never been asked. One thread runs it at a time."""

    def __init__(self, translator: "PlamoTranslator", context: Sequence[tuple[str, str]] = (), notes: str = "",
                 computed: list[tuple[str, str]] | None = None):
        self.translator = translator
        self.notes = notes
        self.history = earlier_pairs(list(context)[-translator.history_pairs:])
        self.computed = computed
        self.requests = 0  # (requests made so far: the tools' count)

    def run(self, lines: Sequence[str], facts: Sequence[dict[str, Any]], follow: Sequence[str],
            took: Callable[[int, str], None], cancel: threading.Event | None = None,
            on_slow: Callable[[float], None] | None = None) -> None:
        """One run of a page's lines (*lines*, `request_lines`' with their *facts*; one line, or the lines whose
        sentence goes on in the next bubble): asked joined when they share their speaker, and each by itself when that
        answer does not split back onto them or they do not. *follow*: the Japanese after the run's last line as
        `PlamoTranslator._following` gives it on the page; the others' is the run's next line. *took*(index in the
        run, translation) for each line, "" for none, after the names it shows were learnt. `Cancelled` once *cancel*
        is set, before a request or during one."""
        t = self.translator
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        lines, facts = list(lines), list(facts)
        last = len(lines) - 1

        def took_one(i: int, got: str) -> None:
            if got:
                learn(self.notes, [(lines[i], got)])  # the book's names: what this line shows of them
            took(i, got)

        speaker = str(facts[0].get("speaker", "") or "")
        if len(lines) > 1 and all(str(f.get("speaker", "") or "") == speaker for f in facts):
            # (no hint: one bubble's hint would be the reference of the run's other bubbles too)
            source = joined(lines)
            self.requests += 1
            parts = split_back(t._line(source, self.notes, self.history, speaker, cancel, on_slow, list(follow)),
                               len(lines))
            if parts is not None:
                t._computed(self.history, source, self.computed)
                for i, part in enumerate(parts):
                    took_one(i, part)
                return
        for i in range(len(lines)):  # one bubble at a time: the run's joined answer could not be split back
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            following = list(follow) if i == last else t._following(lines, facts, lines, i)
            self.requests += 1
            got = t._line(lines[i], self.notes, self.history, str(facts[i].get("speaker", "") or ""), cancel, on_slow,
                          following, t._hint(facts[i]))
            if got:
                t._computed(self.history, lines[i], self.computed)
            took_one(i, got)

    def mark(self) -> tuple[Any, ...]:
        """Where the session stands now, for `rewind`."""
        names = names_of(self.notes)
        return (len(self.history), None if self.computed is None else len(self.computed), self.translator.draws(),
                names.state() if names is not None else None)

    def rewind(self, mark: tuple[Any, ...]) -> None:
        """The session as it stood at *mark* (`mark`): the pairs and the computed ones added since gone, the draws
        and the book's names as they were."""
        held, computed, draws, names = mark
        del self.history[held:]
        if self.computed is not None and computed is not None:
            del self.computed[computed:]
        self.translator.set_draws(draws)
        book = names_of(self.notes)
        if book is not None and names is not None:
            book.put_back(names)


def pfml_ends(target: str, context: str = "", history: Sequence[tuple[str, str]] = (),
              source_lang: str = SOURCE_LANG) -> list[str]:
    """The beginning every `pfml_prompt` with this *context* and *history* shares, as it stands at the end of the
    ``context`` element (the dataset tag alone without one) and then at the end of each earlier pair kept: each one
    the one before it and more, the last one the whole beginning, the line's glossary and the line itself after it
    (the same parts `pfml_prompt` puts first)."""
    parts = [BOS, TAG, "dataset", MSG, "translation"]
    if clean(context):
        parts += [TAG, "context", MSG, clean(context)]
    ends = ["".join(parts)]
    for src, dst in history:
        src, dst = clean(src), clean(dst)
        if src and dst:
            ends.append(ends[-1] + "".join([TAG, "input", KEY, "lang", VAL, source_lang, MSG, src,
                                            TAG, "output", KEY, "lang", VAL, target, MSG, dst]))
    return ends


def common_length(a: str, b: str) -> int:
    """How many characters *a* and *b* share from their start."""
    n = min(len(a), len(b))
    lo, step = 0, 1024
    while lo < n:  # (in blocks, then character by character)
        hi = min(n, lo + step)
        if a[lo:hi] == b[lo:hi]:
            lo = hi
            continue
        while lo < hi and a[lo] == b[lo]:
            lo += 1
        return lo
    return lo


def warm_steps(ends: Sequence[str], held: int, step: int = WARM_STEP) -> list[str]:
    """The prompts a warming sends, in order, so that the server holds the last of *ends* (`pfml_ends`) when it holds
    its first *held* characters now: each one ends where an element ends, extends the one before it, and adds about
    *step* tokens (reckoned high) at most - more only where a single element is longer (the premises, a long pair)."""
    out: list[str] = []
    at = held
    for i, end in enumerate(ends):
        if len(end) <= at:
            continue
        nxt = ends[i + 1] if i + 1 < len(ends) else None
        if nxt is not None and tokens_about(nxt[at:]) <= step:
            continue  # (the next end still fits in this step)
        out.append(end)
        at = len(end)
    return out


def pfml_prompt(source: str, target: str, context: str = "", history: Sequence[tuple[str, str]] = (),
                glossary: Sequence[tuple[str, str]] = (), source_lang: str = SOURCE_LANG) -> str:
    """The PFML3 prompt the model's chat template builds for these inputs, with the beginning-of-sequence token first
    (Ollama's raw mode does not add it): *source* to translate into the language *target* (PLaMo's code, "en"), the
    reference *context*, the earlier (source, translation) pairs *history* and the (source, rendering) pairs of the
    *glossary*. A pair with an empty side is left out. It begins with the last of `pfml_ends`."""
    parts = [BOS, TAG, "dataset", MSG, "translation"]
    if clean(context):
        parts += [TAG, "context", MSG, clean(context)]
    for src, dst in history:
        src, dst = clean(src), clean(dst)
        if src and dst:
            parts += [TAG, "input", KEY, "lang", VAL, source_lang, MSG, src,
                      TAG, "output", KEY, "lang", VAL, target, MSG, dst]
    pairs = [(clean(s), clean(d)) for s, d in glossary]
    pairs = [(s, d) for s, d in pairs if s and d]
    if pairs:
        parts += [TAG, "glossary"]
        for src, dst in pairs:
            parts += [INDEX, src, ITEM, dst]
    parts += [TAG, "input", KEY, "lang", VAL, source_lang, MSG, clean(source),
              TAG, "output", KEY, "lang", VAL, target, MSG]
    return "".join(parts)


def glossary_for(notes: str, source: str, speaker: str = "") -> list[tuple[str, str]]:
    """(the Japanese as *source* writes it, the rendering) for every entry of the premises' sheet (``notes.sheet``,
    `annotations.Premises`) that *source* names, as the term check finds them (`terms._sheet_hits`: terms, the forms
    *speaker* uses, names, a name with its honorific), and the parts of its names it knows (`terms.name_words`, as
    the chat translator's cut entries have them: 樫戸 alone where the sheet has 樫戸 as a part of a full name); without
    a sheet, the "- Japanese = rendering" lines of *notes* whose Japanese stands in *source*. Then the book's names
    held so far (`renderings.BookNames`, when *notes* carry them) that none of these covers. The longer Japanese
    first (樫戸さん before 樫戸), no pair twice."""
    from ..terms import FOLD_MIN_CHARS, _sheet_hits, find_term, name_words, occurs  # terms imports this package
    from .renderings import names_of

    out: list[tuple[str, str]] = []
    sheet = getattr(notes, "sheet", None)
    if sheet is not None and not sheet.is_empty:
        hits = _sheet_hits(sheet, source, speaker)
        for h in hits:
            src = source[h.at:h.end] or h.ja
            if src and h.rendering.strip():
                out.append((src, h.rendering.strip()))
        spans = [(h.at, h.end) for h in hits]
        for ja, word in name_words(sheet)[0].items():
            at = find_term(ja, source) if len(ja) >= FOLD_MIN_CHARS else -1
            if at >= 0 and word.strip() and not any(a <= at and at + len(ja) <= b for a, b in spans):
                spans.append((at, at + len(ja)))
                out.append((source[at:at + len(ja)], word.strip()))
    else:
        for line in str(notes or "").splitlines():
            m = _NOTE_LINE.match(line.strip())
            if m and occurs(m.group(1), source):
                out.append((m.group(1), m.group(2)))
    names = names_of(notes)
    if names is not None:
        out += names.glossary(source, [src for src, _dst in out])
    seen: set[tuple[str, str]] = set()
    return [p for p in sorted(out, key=lambda p: -len(p[0])) if not (p in seen or seen.add(p))]


class PlamoTranslator(OllamaTranslator):
    """PLaMo 3 Translate through raw PFML3 prompts (see the module's docstring). Takes what `OllamaTranslator` takes,
    with its own context size (`NUM_CTX`); *history_pairs*: the earlier pairs a line carries at most."""

    name = "plamo"
    hint_support = HINT_SOMETIMES  # a region's hint is in its line's context, followed about half the time (above)
    uses_room = False  # a line goes with its context alone: nothing of a bubble's room (`translate_page`)
    # the earlier pairs it is given only grow and are cut back rarely (`base.GrowingContext`): Ollama reuses a prompt's
    # beginning only for a prompt that extends the one before it
    grows_context = True

    def __init__(self, url: str = "http://127.0.0.1:11434", model: str = PLAMO.ollama_name, timeout: float = 900.0,
                 temperature: float = 0.2, num_ctx: int = NUM_CTX, target_language: str = "English",
                 slow_after: float = 20.0, keep_alive: Any = KEEP_ALIVE, seed: int | None = None,
                 history_pairs: int = HISTORY_PAIRS, num_gpu: int | None = None):
        super().__init__(url, model, timeout, temperature, num_ctx or NUM_CTX, target_language, slow_after, keep_alive,
                         seed, num_gpu)
        self.history_pairs = history_pairs
        self._asked: dict[str, int] = {}  # line -> how often it was asked for (`_draw`)
        self._asked_lock = threading.Lock()
        self._wrote = threading.local()  # (the last answer of this thread's request, as the model wrote it: `_written`)
        # the evaluation tools' record of every request (Ollama's statistics): None in the app, a list to fill there
        self.stats_log: list[dict[str, Any]] | None = None
        # what the server may hold of this translator's requests, as far as it can tell (`_held_now`): the prompts of
        # the last HELD_KEPT of them that did not extend the one before, each with the answer the server wrote (a
        # request cancelled: its prompt, which the server computes to its end); none after a load or a request that
        # failed. What a warming looks at (`warm_prefix`), in memory only, never written
        self._holds: list[tuple[str, str]] = []  # (prompt, prompt and answer), the newest last
        self._holds_lock = threading.Lock()
        self._warm_halt: threading.Event | None = None  # what ends the warming under way: any request sets it
        self.warm_log: list[dict[str, Any]] | None = None  # (the tools' record of each warming step, as `stats_log`)
        self._rates: deque[float] = deque(maxlen=RATES_KEPT)  # seconds a prompt token took (`_expected_s`)

    # --- the language ------------------------------------------------------------------------------------------
    @property
    def target_code(self) -> str:
        """PLaMo's code for the target language ("en", "zh-hans"). `TranslationError` (``plamo.cannot_write``) for a
        language it cannot write: Brazilian Portuguese and Turkish go to Qwen (`models.model_for_language`)."""
        code = plamo_code(self.target_language)
        if code is None:
            raise TranslationError(Message("plamo.cannot_write", language=str(self.target_language)))
        return code

    # --- requests ----------------------------------------------------------------------------------------------
    def _draw(self, source: str) -> int:
        """How many times *source* was asked for before (0 the first time), counted: the seed offset of this
        request, so that a line asked for again is drawn anew."""
        with self._asked_lock:
            if len(self._asked) >= ASKED_KEPT:
                self._asked.clear()
            n = self._asked.get(source, 0)
            self._asked[source] = n + 1
            return n

    def draws(self) -> dict[str, int]:
        """A copy of what `_draw` counts (each line's requests so far): a page job whose frame may yet change holds it
        (`pipeline.Provisional`), and puts it back when the frame does (`set_draws`)."""
        with self._asked_lock:
            return dict(self._asked)

    def set_draws(self, draws: dict[str, int]) -> None:
        """What `_draw` counts, as `draws` gave it."""
        with self._asked_lock:
            self._asked = dict(draws)

    def _options(self, max_tokens: int, offset: int = 0) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": self.temperature,
                                   "stop": list(STOPS), "num_predict": int(max_tokens)}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        self._gpu_option(options)  # (only with ``num_gpu`` set: the server decides otherwise)
        if self.seed is not None:
            options["seed"] = int(self.seed) + int(offset)
        elif offset:
            options["seed"] = random.randrange(1, 2**31)  # another draw than the one before, whatever Ollama's default
        return options

    def _generate(self, prompt: str, max_tokens: int, offset: int = 0, cancel: threading.Event | None = None,
                  on_slow: Callable[[float], None] | None = None) -> str:
        """The model's answer to the raw *prompt*, at most *max_tokens* tokens, reserved tokens taken out. Streamed
        when there is a *cancel* or an *on_slow* to serve (as `OllamaTranslator._chat` does)."""
        halt = self._warm_halt
        if halt is not None:
            halt.set()  # (a request: a warming under way sends no more steps, `warm_prefix`)
        self._used.add(self.model)
        payload: dict[str, Any] = {"model": self.model, "prompt": prompt, "raw": True,
                                   "options": self._options(max_tokens, offset),
                                   "keep_alive": self.keep_alive}
        sent = [False]  # (whether the prompt went out after the last load: what the server may hold of it)

        def load() -> None:
            sent[0] = False
            self.ensure_loaded(cancel, on_slow)

        def send() -> tuple[dict[str, Any], str]:
            sent[0] = True
            with ocr_place.translating():  # (the OCR reads on the CPU while the model computes, a stream to its end)
                if cancel is not None or on_slow is not None:
                    data = self._stream("/api/generate", {**payload, "stream": True}, _ignore, cancel, on_slow,
                                        first=self._no_answer_after(self._expected_s(prompt)),
                                        between=self._silent_after())
                    return data, str((data.get("message") or {}).get("content") or "")
                data = self._request("/api/generate", {**payload, "stream": False})
                return data, str(data.get("response") or "")

        try:
            # (the model made sure of first; no answer: both asked again as the module `ollama` says)
            data, raw = self._answer(send, cancel, load=load)
        except TranslationError:
            self._held_now(None)
            self._unsure()  # (the next request asks Ollama whether the model is loaded)
            raise
        except BaseException:
            if sent[0]:  # (cancelled: the server computes a prompt it has to its end, WARM_STEP)
                self._held_now(prompt, prompt)
            raise
        self._held_now(prompt + raw, prompt)
        self._answered(self.model)
        self.last_stats = {k: data.get(k) for k in ("prompt_eval_count", "eval_count", "prompt_eval_duration",
                                                    "eval_duration", "total_duration", "done_reason")}
        self._learn_rate(data)
        if self.stats_log is not None:
            self.stats_log.append(dict(self.last_stats))
        self._wrote.text = clean(raw)
        # each line's spaces made one; the line breaks kept (a joined request answers one line per bubble)
        return "\n".join(" ".join(line.split()) for line in clean(raw).splitlines() if line.strip())

    def _learn_rate(self, data: dict[str, Any]) -> None:
        """The seconds a prompt token took in a request's statistics (*data*), kept for `_expected_s` when it computed
        `RATE_LEAST_TOKENS` or more."""
        try:
            count, ns = int(data.get("prompt_eval_count") or 0), float(data.get("prompt_eval_duration") or 0)
        except (TypeError, ValueError):
            return
        if count >= RATE_LEAST_TOKENS and ns > 0:
            self._rates.append(ns / 1e9 / count)

    def _expected_s(self, prompt: str) -> float | None:
        """The seconds the server is expected to take for *prompt* before its first byte: the tokens it does not hold
        of it (`held_of`, `tokens_about`) times the slowest rate of the last requests (`_learn_rate`); None before one
        was measured."""
        rates = list(self._rates)
        if not rates:
            return None
        return tokens_about(prompt[self.held_of(prompt):]) * max(rates)

    def _lost(self) -> None:
        """(`OllamaTranslator._lost`) And nothing is taken to be held by the server any more (`_holds`)."""
        super()._lost()
        self._held_now(None)

    def _written(self) -> str:
        """The answer of this thread's last request as the model wrote it (reserved tokens out, trimmed): what the
        server holds after the prompt, so what an earlier pair of the next prompt holds for that line."""
        return str(getattr(self._wrote, "text", "") or "")

    @staticmethod
    def _hint(facts: dict[str, Any]) -> str:
        """The reader's hint for the model on a line (its facts' ``note``) as it goes into that line's ``context``:
        the hint alone, on one line ("" for none)."""
        return " ".join(str(facts.get("note", "") or "").split())

    def _context(self, notes: str, speaker: str = "", following: Sequence[str] = (), hint: str = "") -> str:
        """The reference text of a line: the premises; for a line the reader gave a speaker, who says it; the
        reader's hint for the model on the line (*hint*: `_hint`, for the request of that line alone); and the
        Japanese that follows it (*following*), as the surrounding text the format's ``context`` is for."""
        parts = [str(notes or "").strip()]
        if speaker:
            parts.append(f"Speaker of the line: {speaker}")
        if hint:
            parts.append(hint)
        after = "\n".join(" ".join(str(t).split()) for t in following if str(t).strip())
        if after:
            parts.append(after)
        return "\n\n".join(p for p in parts if p)

    def context_fits(self, pairs: Sequence[tuple[str, str]], notes: str = "") -> bool:
        """Whether a request may start from the earlier *pairs* with the premises *notes*: the prompt up to them, reckoned
        high (`tokens_about`), leaves `REQUEST_ROOM` tokens of the share of the context a prompt keeps within
        (`PROMPT_SHARE`). What `base.GrowingContext.take` asks before it gives the pairs to a request."""
        try:
            target = self.target_code
        except TranslationError:
            target = "en"
        head = pfml_prompt("", target, self._context(notes), earlier_pairs(pairs))
        return tokens_about(head) + REQUEST_ROOM <= int(self.num_ctx * PROMPT_SHARE)

    def _fit(self, source: str, target: str, context: str, history: list[tuple[str, str]],
             glossary: list[tuple[str, str]], max_tokens: int) -> str:
        """The prompt for *source*, kept within the context (`PROMPT_SHARE`): the oldest earlier pairs left out first,
        then the end of the reference text."""
        limit = max(512, int(self.num_ctx * PROMPT_SHARE) - max_tokens)
        pairs = list(history)
        prompt = pfml_prompt(source, target, context, pairs, glossary)
        while tokens_about(prompt) > limit and pairs:
            pairs = pairs[max(1, len(pairs) // 8):]
            prompt = pfml_prompt(source, target, context, pairs, glossary)
        if tokens_about(prompt) > limit:
            keep = max(0, len(context) - (tokens_about(prompt) - limit))
            prompt = pfml_prompt(source, target, context[:keep], pairs, glossary)
        return prompt

    def _line(self, source: str, notes: str, history: Sequence[tuple[str, str]], speaker: str = "",
              cancel: threading.Event | None = None,
              on_slow: Callable[[float], None] | None = None, following: Sequence[str] = (), hint: str = "") -> str:
        """One line translated (or a joined run of them, a line break between bubbles), after the earlier pairs
        *history*, with the premises *notes*, the reader's *hint* for this line and the Japanese *following* it as
        reference and the sheet's renderings it names as glossary; another seed when it was asked for before
        (`_draw`). A single line comes back on one line."""
        target = self.target_code
        max_tokens = max(128, 4 * len(source) + 64)
        prompt = self._fit(source, target, self._context(notes, speaker, following, hint), list(history),
                           glossary_for(notes, source, speaker), max_tokens)
        self._wrote.text = None
        got = self._generate(prompt, max_tokens, self._draw(source), cancel, on_slow)
        wrote = getattr(self._wrote, "text", None)
        self._wrote.text = wrote if isinstance(wrote, str) else got  # (a stand-in for the model keeps none: its answer)
        return got if "\n" in source else " ".join(got.split())

    def _computed(self, history: list[tuple[str, str]], source: str, computed: list[tuple[str, str]] | None) -> None:
        """The request this thread just made for *source* as an earlier pair of the next one, added to *history* (and
        to *computed*, a list when given): the Japanese as it was sent (a joined run as one pair, a line per bubble)
        and the answer as the model wrote it (`_written`), so that the next prompt holds what the server computed and
        extends this one. None for an answer with nothing in it."""
        answer = self._written()
        if not answer:
            return
        pair = SentPair(source, answer)
        history.append(pair)
        if computed is not None:
            computed.append(pair)

    # --- computed while the reader reads ----------------------------------------------------------------------
    def _held_now(self, state: str | None, prompt: str | None = None) -> None:
        """What the server may hold after a request of this translator (`_holds`): *state* (the request's *prompt*, or
        all of *state* when not given, and what the server wrote after it) beside what it held before - in place of
        the last one when *prompt* extends it (the server's prompt grew) -, HELD_KEPT at most, the oldest going first
        (as Ollama keeps a few earlier prompts in memory and computes a request from the one it shares most with); None:
        nothing (a load, a request that failed)."""
        with self._holds_lock:
            if state is None:
                self._holds = []
                return
            prompt = state if prompt is None else prompt
            held = self._holds
            if held and prompt.startswith(held[-1][0]):
                held.pop()
            held.append((prompt, state))
            del held[:-HELD_KEPT]

    def held_of(self, prompt: str) -> int:
        """How much of the start of *prompt* (characters) the server holds, as far as `_holds` tells: the most any of
        what it may hold shares with it."""
        with self._holds_lock:
            held = list(self._holds)
        return max((common_length(prompt, state) for _p, state in held), default=0)

    def warm_prefix(self, notes: str, pairs: Sequence[tuple[str, str]],
                    stop: threading.Event | None = None) -> dict[str, Any]:
        """(while the reader reads: no page job) The beginning the next page's first request will
        start with - the premises *notes* and the earlier *pairs* that request will be given (`GrowingContext.peek`) -
        computed by the server now, when it does not hold `WARM_LEAST` tokens of it or more in any of what it may hold
        (`held_of`: after the pairs were cut back, or a load): that request then extends it, as it extends the last
        request when nothing came between. A warming where the server holds it would only take its place, and one
        stopped after a step would leave the server a short beginning that the next request extends rather than the
        longer one it held (measured: a turn's first request computed in full, 1.2 to 3.3 s). Its prompt and its answer are what they are without it: the warming sends
        what any request sends, asks for one token and keeps nothing of it, and draws nothing (`_draw`). In steps
        (`warm_steps`): *stop* set ends it before the next step, and the step under way, which the server computes to
        its end whatever is done, is never waited for by anything but the warming. Only for a model Ollama holds
        wholly on the GPU (nothing is loaded for it, and none is warmed on the processor) and a ``keep_alive`` that
        keeps it after a request. What it did, for the tools: why it did nothing (``why``), or its steps; never
        raises."""
        from .ollama import FULL_GPU_SHARE, unloads_at_once

        facts: dict[str, Any] = {"why": "", "steps": 0, "tokens": 0, "left": 0, "ms": 0.0}
        stop = stop if stop is not None else threading.Event()
        self._warm_halt = stop  # (a request of this translator's sets it: `_generate`)
        try:
            if unloads_at_once(self.keep_alive):
                facts["why"] = "keep_alive"
                return facts
            target = self.target_code
            ends = pfml_ends(target, self._context(notes), earlier_pairs(list(pairs)[-self.history_pairs:]))
            held = self.held_of(ends[-1])
            facts["left"] = tokens_about(ends[-1][held:])
            if facts["left"] < WARM_LEAST:
                facts["why"] = "held"
                return facts
            if self._loading.locked():
                facts["why"] = "loading"
                return facts
            if self.silent:  # (a request was ended for want of an answer, and none came since: nothing is sent)
                facts["why"] = "not answering"
                return facts
            share = self.gpu_share()  # (/api/ps: nothing is loaded for a warming)
            if share is None or share < FULL_GPU_SHARE:
                facts["why"] = "not loaded" if share is None else "not on the GPU"
                return facts
            for prompt in warm_steps(ends, held):
                if stop.is_set():
                    facts["why"] = "stopped"
                    break
                took = self._warm_step(prompt)
                facts["steps"] += 1
                facts["tokens"] += int(took.get("prompt_n") or 0)
                facts["ms"] += float(took.get("ms") or 0.0)
                if self.warm_log is not None:
                    self.warm_log.append(dict(took))
                if float(took.get("ms") or 0.0) > WARM_STEP_MOST_S * 1000.0:
                    facts["why"] = "slow"
                    break
        except Exception as e:  # noqa: BLE001 - a warming that fails costs the next request its prompt, no more
            self._held_now(None)
            facts["why"] = f"failed: {type(e).__name__}"
        return facts

    def _warm_step(self, prompt: str) -> dict[str, Any]:
        """One step of `warm_prefix`: *prompt* to /api/generate as a request sends it (the same options, so that the
        model is never loaded again for it), one token asked for and nothing kept but what the server holds now. On
        this thread's own connection, never sent again (a server gone is left to the next request, which starts it).
        Ollama's counts of it and its time."""
        import time

        options = self._options(1)
        payload = {"model": self.model, "prompt": prompt, "raw": True, "stream": False, "options": options,
                   "keep_alive": self.keep_alive}
        t0 = time.monotonic()
        try:
            with ocr_place.translating():  # (as any request: the OCR reads on the CPU while the server computes)
                data = self._request_once("/api/generate", payload, WARM_TIMEOUT)
        except BaseException as e:
            self._held_now(None)
            self._unsure()
            if isinstance(e, TranslationError) and e.message.code == "ollama.timeout":
                # (no answer: a silence of the incident, said as any; the warming is not asked again, the next
                # request is - `ollama.OllamaTranslator._after_silence`)
                self._silence(time.monotonic() - t0, "warming step", "without an answer")
            raise
        self._held_now(prompt + str(data.get("response") or ""), prompt)
        self._answered(self.model)
        return {"ms": (time.monotonic() - t0) * 1000.0, "prompt_n": data.get("prompt_eval_count"),
                "prompt_ms": float(data.get("prompt_eval_duration") or 0) / 1e6,
                "answer_n": data.get("eval_count")}

    def warm_up(self, model: str | None = None, keep_alive: Any = None, timeout: float | None = None,
                cancel: threading.Event | None = None, on_slow: Callable[[float], None] | None = None) -> float:
        """*model* (default: this translator's) loaded in Ollama now: an empty prompt to /api/generate, which loads it
        and writes nothing, with the context size the requests ask for. As `OllamaTranslator.warm_up` otherwise."""
        import time

        from .ollama import WARM_UP_TIMEOUT, keep_alive_value

        options: dict[str, Any] = self._gpu_option({"num_ctx": self.num_ctx} if self.num_ctx else {})
        payload: dict[str, Any] = {"model": model or self.model, "prompt": "", "options": options,
                                   "keep_alive": self.keep_alive if keep_alive is None else keep_alive_value(keep_alive)}
        self._used.add(payload["model"])
        self._held_now(None)  # (a load: the server holds no prompt of this translator's)
        limit = timeout or min(self.timeout, WARM_UP_TIMEOUT)
        start = time.monotonic()
        if cancel is None and on_slow is None:
            self._request("/api/generate", {**payload, "stream": False}, limit)
        else:  # (the server looked at while it loads: `OllamaTranslator.warm_up`)
            self._stream("/api/generate", {**payload, "stream": True}, _ignore, cancel, on_slow, limit,
                         alive=self._ps_answers)
        if payload["keep_alive"] == self.keep_alive:
            self._answered(payload["model"])
        return time.monotonic() - start

    def _unload(self, name: str) -> None:
        """Ollama unloads *name* now: /api/generate with ``keep_alive`` 0 and no prompt (the chat would render the
        model's template, which wants a message)."""
        from .ollama import RELEASE_TIMEOUT

        self._held_now(None)
        self._request_once("/api/generate", {"model": name, "keep_alive": 0, "stream": False}, RELEASE_TIMEOUT)

    # --- the translator's interface ----------------------------------------------------------------------------
    def translate_page(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = (), notes: str = "",
                       upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None,
                       on_item: Callable[[int, str], None] | None = None,
                       cancel: threading.Event | None = None,
                       on_slow: Callable[[float], None] | None = None,
                       computed: list[tuple[str, str]] | None = None) -> list[str]:
        """One translation per text, one request each, in order: each line after the earlier pairs (*context*, then
        the lines of this request already done, each as its request computed it: `_computed`). *on_item*(index,
        translation) gets each as soon as it is there. A run of lines that go on in the next bubble is one request
        (see the module's docstring); *upcoming* is context for a line asked alone (`_following`). *computed*, a list
        when given, gets the earlier pairs this request added, in order: what the caller's next request starts from
        after *context*, so that its first prompt extends this request's last one. Once *cancel* is set `Cancelled`
        is raised, between two lines or during one; *on_slow* as for `OllamaTranslator.translate_page`.
        ``ollama.bad_answer`` when not one line got a translation."""
        if not texts:
            return []
        self.target_code  # noqa: B018 - a language PLaMo cannot write fails before any request
        session = self.page_session(context, notes, computed)
        lines, facts = request_lines(texts, meta)
        after = list(lines) + [str(t) for t in upcoming]  # what follows each line: the request's, then upcoming
        out: list[str] = [""] * len(lines)

        def took_in(run: list[int]) -> Callable[[int, str], None]:
            def took(i: int, got: str) -> None:
                out[run[i]] = got
                if got and on_item is not None:
                    on_item(run[i], got)
            return took

        for run in runs(facts, len(lines), MAX_JOINED):
            session.run([lines[k] for k in run], [facts[k] for k in run], self._following(lines, facts, after, run[-1]),
                        took_in(run), cancel, on_slow)
        if not any(out):
            raise TranslationError(Message("ollama.bad_answer", chars=0))
        return out

    def page_session(self, context: Sequence[tuple[str, str]] = (), notes: str = "",
                     computed: list[tuple[str, str]] | None = None) -> "PageSession":
        """What `translate_page` carries from one run of a page's lines to the next, as an object of its own
        (`PageSession`): the pipeline's line sender (`streaming`) asks a page's runs with it one by one as their lines
        are read, as `translate_page` would have asked them, and takes back runs it asked too soon (`PageSession.mark`,
        `PageSession.rewind`)."""
        return PageSession(self, context, notes, computed)

    def translate_aside(self, text: str, context: Sequence[tuple[str, str]] = (), notes: str = "",
                        cancel: threading.Event | None = None,
                        on_slow: Callable[[float], None] | None = None) -> str:
        """One request beside a page's own (`locate_large`: where a bubble's larger lettering is in its translation):
        *text* translated after the earlier pairs *context* with the premises *notes*, as a line of the page is
        (`_line`, without the Japanese after it), and nothing of it kept - no pair for the next request, no name
        learnt, no draw counted (a line asked for later is drawn as it would have been). Cancelled as a page is.
        *context* is taken whole, as the caller gives it (the pairs the next request starts from, never cut there):
        cut to the newest `HISTORY_PAIRS`, a request after a page that took the pairs past it began otherwise than
        the page's last prompt, and the server computed it all again (`_fit` still leaves the oldest out when they
        would not fit)."""
        target = self.target_code
        source = one_line(text)
        history = earlier_pairs(list(context))
        max_tokens = max(128, 4 * len(source) + 64)
        prompt = self._fit(source, target, self._context(notes), history, glossary_for(notes, source), max_tokens)
        return " ".join(self._generate(prompt, max_tokens, 0, cancel, on_slow).split())

    @staticmethod
    def _following(lines: Sequence[str], facts: Sequence[dict[str, Any]], after: Sequence[str], k: int) -> list[str]:
        """The Japanese given as the context of line *k* (or of the run that ends with it): the lines that follow it,
        `FOLLOW_OPEN` of them when it goes on in the next bubble, `FOLLOW_ALONE` when it is the request's only line
        (a line asked for again, with its neighbours), none otherwise; never past its page."""
        page = facts[k].get("page")
        n = FOLLOW_OPEN if facts[k].get("continues") else FOLLOW_ALONE if len(lines) == 1 else 0
        if n <= 0:
            return []
        out = []
        for j in range(k + 1, min(len(after), k + 1 + n)):
            if page is not None and j < len(facts) and facts[j].get("page") != page:
                break
            out.append(after[j])
        return out
