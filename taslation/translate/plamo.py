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
  far -> the earlier pairs, the oldest left out first when the prompt would not fit (`PROMPT_SHARE`);
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
  to line.

Translating is all it does, as for the other translator: TASlation has no notes of the model's own, no review pass, no
shortening and no alternatives (removed 2026-11-06). A line whose reply copied the Japanese or came back empty is asked
for again by the pipeline (`base.ask_for_missing`); every request for a line this translator was asked for before goes
with another sampling seed (`_draw`), so that it is a new draw, not the same answer again.

Everything else is `OllamaTranslator`'s: the loopback-only connection without proxies, the model loaded on demand and
released (`ensure_loaded`, `release`, `warm_up`, `gpu_share`, ``before_load``, ``on_status``, ``keep_alive``), Ollama
started again when a request finds it gone (``revive``), the fixed ``seed`` of the evaluation tools, and the same
`TranslationError` message codes; a model that is not installed is ``translator.model_missing`` when the target
language chose it (``auto_model``). A request given ``cancel`` or ``on_slow`` is streamed, so that Stop ends it at
once and a model still loading is noticed. No text of a book is ever put into an error.
"""

from __future__ import annotations

import random
import re
import threading
from typing import Any, Callable, Sequence

from ..messages import Cancelled, Message
from .base import TranslationError
from .continuation import MAX_JOINED, joined, runs, split_back
from .models import PLAMO, plamo_code
from .ollama import KEEP_ALIVE, OllamaTranslator, _ignore
from .renderings import learn

TAG, MSG, KEY, VAL = "<|plamo:tag|>", "<|plamo:msg|>", "<|plamo:key|>", "<|plamo:val|>"
INDEX, ITEM, BOS = "<|plamo:index|>", "<|plamo:item|>", "<|plamo:bos|>"
STOPS = [TAG, BOS]  # where an answer ends: the next element, or the next sequence
SOURCE_LANG = "ja"
NUM_CTX = 8192  # Ollama's context for PLaMo: a line's prompt is ~1,200 tokens with 40 earlier pairs (1.9 GB in all)
# the earlier pairs a request starts from, at most; the lines of the request done so far are added to them, never one
# taken off the front: the prompts of a request then share their beginning, which Ollama computes once (cutting the
# oldest pair at every line made each prompt new: prompt processing fell from 5,800 to 900 tokens a second)
HISTORY_PAIRS = 60
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


def pfml_prompt(source: str, target: str, context: str = "", history: Sequence[tuple[str, str]] = (),
                glossary: Sequence[tuple[str, str]] = (), source_lang: str = SOURCE_LANG) -> str:
    """The PFML3 prompt the model's chat template builds for these inputs, with the beginning-of-sequence token first
    (Ollama's raw mode does not add it): *source* to translate into the language *target* (PLaMo's code, "en"), the
    reference *context*, the earlier (source, translation) pairs *history* and the (source, rendering) pairs of the
    *glossary*. A pair with an empty side is left out."""
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

    def __init__(self, url: str = "http://127.0.0.1:11434", model: str = PLAMO.ollama_name, timeout: float = 900.0,
                 temperature: float = 0.2, num_ctx: int = NUM_CTX, target_language: str = "English",
                 slow_after: float = 20.0, keep_alive: Any = KEEP_ALIVE, seed: int | None = None,
                 history_pairs: int = HISTORY_PAIRS):
        super().__init__(url, model, timeout, temperature, num_ctx or NUM_CTX, target_language, slow_after, keep_alive,
                         seed)
        self.history_pairs = history_pairs
        self._asked: dict[str, int] = {}  # line -> how often it was asked for (`_draw`)
        self._asked_lock = threading.Lock()
        # the evaluation tools' record of every request (Ollama's statistics): None in the app, a list to fill there
        self.stats_log: list[dict[str, Any]] | None = None

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

    def _options(self, max_tokens: int, offset: int = 0) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": self.temperature,
                                   "stop": list(STOPS), "num_predict": int(max_tokens)}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        if self.seed is not None:
            options["seed"] = int(self.seed) + int(offset)
        elif offset:
            options["seed"] = random.randrange(1, 2**31)  # another draw than the one before, whatever Ollama's default
        return options

    def _generate(self, prompt: str, max_tokens: int, offset: int = 0, cancel: threading.Event | None = None,
                  on_slow: Callable[[float], None] | None = None) -> str:
        """The model's answer to the raw *prompt*, at most *max_tokens* tokens, reserved tokens taken out. Streamed
        when there is a *cancel* or an *on_slow* to serve (as `OllamaTranslator._chat` does)."""
        self.ensure_loaded(cancel, on_slow)
        self._used.add(self.model)
        payload: dict[str, Any] = {"model": self.model, "prompt": prompt, "raw": True,
                                   "options": self._options(max_tokens, offset),
                                   "keep_alive": self.keep_alive}
        if cancel is not None or on_slow is not None:
            data = self._stream("/api/generate", {**payload, "stream": True}, _ignore, cancel, on_slow)
            raw = str((data.get("message") or {}).get("content") or "")
        else:
            data = self._request("/api/generate", {**payload, "stream": False})
            raw = str(data.get("response") or "")
        self.last_stats = {k: data.get(k) for k in ("prompt_eval_count", "eval_count", "prompt_eval_duration",
                                                    "eval_duration", "total_duration", "done_reason")}
        if self.stats_log is not None:
            self.stats_log.append(dict(self.last_stats))
        # each line's spaces made one; the line breaks kept (a joined request answers one line per bubble)
        return "\n".join(" ".join(line.split()) for line in clean(raw).splitlines() if line.strip())

    def _context(self, notes: str, speaker: str = "", following: Sequence[str] = ()) -> str:
        """The reference text of a line: the premises; for a line the reader gave a speaker, who says it; and the
        Japanese that follows it (*following*), as the surrounding text the format's ``context`` is for."""
        parts = [str(notes or "").strip()]
        if speaker:
            parts.append(f"Speaker of the line: {speaker}")
        after = "\n".join(" ".join(str(t).split()) for t in following if str(t).strip())
        if after:
            parts.append(after)
        return "\n\n".join(p for p in parts if p)

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
              on_slow: Callable[[float], None] | None = None, following: Sequence[str] = ()) -> str:
        """One line translated (or a joined run of them, a line break between bubbles), after the earlier pairs
        *history*, with the premises *notes* and the Japanese *following* it as reference and the sheet's renderings
        it names as glossary; another seed when it was asked for before (`_draw`). A single line comes back on one
        line."""
        target = self.target_code
        max_tokens = max(128, 4 * len(source) + 64)
        prompt = self._fit(source, target, self._context(notes, speaker, following), list(history),
                           glossary_for(notes, source, speaker), max_tokens)
        got = self._generate(prompt, max_tokens, self._draw(source), cancel, on_slow)
        return got if "\n" in source else " ".join(got.split())

    def warm_up(self, model: str | None = None, keep_alive: Any = None, timeout: float | None = None,
                cancel: threading.Event | None = None, on_slow: Callable[[float], None] | None = None) -> float:
        """*model* (default: this translator's) loaded in Ollama now: an empty prompt to /api/generate, which loads it
        and writes nothing, with the context size the requests ask for. As `OllamaTranslator.warm_up` otherwise."""
        import time

        from .ollama import WARM_UP_TIMEOUT, keep_alive_value

        options: dict[str, Any] = {"num_ctx": self.num_ctx} if self.num_ctx else {}
        payload: dict[str, Any] = {"model": model or self.model, "prompt": "", "options": options,
                                   "keep_alive": self.keep_alive if keep_alive is None else keep_alive_value(keep_alive)}
        self._used.add(payload["model"])
        limit = timeout or min(self.timeout, WARM_UP_TIMEOUT)
        start = time.monotonic()
        if cancel is None and on_slow is None:
            self._request("/api/generate", {**payload, "stream": False}, limit)
        else:
            self._stream("/api/generate", {**payload, "stream": True}, _ignore, cancel, on_slow, limit)
        return time.monotonic() - start

    def _unload(self, name: str) -> None:
        """Ollama unloads *name* now: /api/generate with ``keep_alive`` 0 and no prompt (the chat would render the
        model's template, which wants a message)."""
        from .ollama import RELEASE_TIMEOUT

        self._request_once("/api/generate", {"model": name, "keep_alive": 0, "stream": False}, RELEASE_TIMEOUT)

    # --- the translator's interface ----------------------------------------------------------------------------
    def translate_page(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = (), notes: str = "",
                       upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None,
                       on_item: Callable[[int, str], None] | None = None,
                       cancel: threading.Event | None = None,
                       on_slow: Callable[[float], None] | None = None) -> list[str]:
        """One translation per text, one request each, in order: each line after the earlier pairs (*context*, then
        the lines of this request already done). *on_item*(index, translation) gets each as soon as it is there.
        A run of lines that go on in the next bubble is one request (see the module's docstring); *upcoming* is
        context for a line asked alone (`_following`). Once *cancel* is set `Cancelled` is raised, between
        two lines or during one; *on_slow* as for `OllamaTranslator.translate_page`. ``ollama.bad_answer`` when not
        one line got a translation."""
        if not texts:
            return []
        self.target_code  # noqa: B018 - a language PLaMo cannot write fails before any request
        history = list(context)[-self.history_pairs:]
        lines = [" ".join(str(t).split()) if "\n" in str(t) else str(t) for t in texts]
        facts = [dict((meta[i] or {}) if meta and i < len(meta) else {}) for i in range(len(lines))]
        after = list(lines) + [str(t) for t in upcoming]  # what follows each line: the request's, then upcoming
        out: list[str] = [""] * len(lines)

        def took(i: int, got: str) -> None:
            out[i] = got
            if got:
                history.append((lines[i], got))
                learn(notes, [(lines[i], got)])  # the book's names: what this line shows of them
                if on_item is not None:
                    on_item(i, got)

        for run in runs(facts, len(lines), MAX_JOINED):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            speaker = str(facts[run[0]].get("speaker", "") or "")
            if len(run) > 1 and all(str(facts[k].get("speaker", "") or "") == speaker for k in run):
                parts = split_back(self._line(joined([lines[k] for k in run]), notes, history, speaker, cancel,
                                              on_slow, self._following(lines, facts, after, run[-1])), len(run))
                if parts is not None:
                    for k, part in zip(run, parts):
                        took(k, part)
                    continue
            for k in run:  # one bubble at a time: the run's joined answer could not be split back
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                took(k, self._line(lines[k], notes, history, str(facts[k].get("speaker", "") or ""), cancel, on_slow,
                                   self._following(lines, facts, after, k)))
        if not any(out):
            raise TranslationError(Message("ollama.bad_answer", chars=0))
        return out

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
