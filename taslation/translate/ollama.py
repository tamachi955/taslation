"""Translation through a local Ollama server.

The only network peer TASlation ever has. The client refuses any URL whose
host is not a loopback address, talks to it over ``http.client`` straight to that
address (no proxy is ever involved), with one connection kept per thread that talks
to it (`OllamaTranslator._held`: a new one costs ~15 ms; one the server closed
meanwhile is opened again and the request sent once more, nothing of it answered),
and the network guard independently blocks everything else.

Requests are page- or chunk-sized: all bubbles of the pages in question go to
the model together, in reading order, with the reader's series sheet (names,
terms, honorifics: the prompt's "translator's notes"), the previous translations
and the upcoming bubbles as context, so pronouns, running jokes and names stay
coherent. The model answers in JSON (Ollama structured output) and the reply is
matched back to bubbles by id. It does nothing but translate: no notes of its own,
no review, no shortening, no alternatives (removed 2026-11-06, so that it does
what the PLaMo translator does, `taslation.translate.plamo`).

This is the translator for the target languages PLaMo cannot write (Brazilian
Portuguese, Turkish: `taslation.translate.models`) and for a model the reader
sets by hand (``ollama_model``).

A page for the window is asked for in the same single request, but the reply
is read as the model writes it (``stream: true``): ``ItemStream`` follows the
JSON piece by piece and hands over each bubble's translation the moment its
object is complete, so the bubbles fill in while the model is still writing.
The whole reply is still parsed at the end, and that is what counts.

A request given a ``cancel`` event or an ``on_slow`` callback is streamed too, and
read in short waits (``POLL_S``): once the event is set the connection is closed
(Ollama then stops generating) and `Cancelled` is raised; when nothing has come
for ``slow_after`` seconds (a model that is still loading), ``on_slow(seconds)``
is called once. What goes wrong is a `TranslationError` whose ``.message`` is a
`taslation.messages.Message` (``ollama.unreachable``, ``ollama.model_missing`` or, for a model the target language
chose (``auto_model``), ``translator.model_missing``, or, for a model of the reader's, ``health.chosen_model_missing``,
``ollama.timeout``, ...); its English text never carries the operating system's
own (localised) error text, nor any text of the book.

A streamed request that gets no answer (`NoAnswer`: no first byte within `NO_ANSWER_S`, or `NO_ANSWER_TIMES` the time
its prompt is expected to take when that is longer, `_no_answer_after`; or a stream silent `NO_ANSWER_S` once it began;
a stream that is still writing is left alone; the wait for a first byte is counted over the requests in a row that got
none - a reader who turns every few seconds cancels each before its own bound -, the time with none under way left out,
and any byte of any request to the model starts it again, `_Waits`) is ended: its connection closed (the server then
stops the task), what the client knew of the server's state made unsure, and the window told once per incident
(``ollama.no_answer``, through `on_status`, whichever thread asked: the page on show's job, the backlog - the window
says what a request of the backlog's tells in its status line only, never as the page on show's
(`backlog.in_step`) -, a load). The backlog's requests are counted as any (`_Waits`): a turn that stops one keeps
what it waited. The same request is asked once more
on a new connection after one /api/ps look (`_answer`, `_after_silence`). No answer a second time in the incident (until
an answer comes), or /api/ps silent: the server TASlation started is stopped and started again by `ollama_start`'s own
ways (``restart``, `OllamaStarter.restart`: at most once in ten minutes, never a server the person runs, said as
``ollama.restarting`` once the restart is under way - never of a server it leaves alone), the model loaded, the
request asked again - once; else, or after that, the request ends with ``ollama.not_answering`` (the translation
program on this computer does not answer: restart it, then F5) and ``silent`` names the incident until the next
answer of any request (the backlog pauses meanwhile; ``endings`` counts such ends). Nothing asks for ever: each request makes one restart at most and the incident's second
silence ends it. A load is not bounded by a first byte outside an incident (it comes once the model is in memory,
from a slow disk late): it asks /api/ps every `ALIVE_EVERY_S` on a connection of its own while nothing comes and ends
as no answer when the server is silent `ALIVE_MISSES` times in a row; within an incident its first byte has a bound
too (`NO_ANSWER_LOAD_S`, `_load_bound`: a server whose model process hangs loads it again and again while /api/ps
answers) - a request's own load is taken as
the request itself (`_answer`), the load ahead of a page (`taslation.pipeline.LoadAhead`) leaves it to the page's
request, and its join ends with it; a request waiting for another thread's load gets its slow note as any request
does. A warming step (`plamo.PlamoTranslator.warm_prefix`) that times
out counts as a silence of the incident and is not asked again: the next request is. Requests made in one piece (no
cancel, no slow note: the commands and the tools) keep ``timeout``. The log names each incident - which request (its
thread), how long, what was done - and never a line.

The model is in GPU memory only while it is needed. The window loads it at its start,
while the OCR model loads (``load_model_at_start``, on by default: `ensure_loaded` with
*quiet*, on a thread of its own, after Ollama was started as ever), so that the first
page does not wait for it; the commands and a window with the setting off leave it to
the first request that wants it (`OllamaTranslator.ensure_loaded`, from every
request to the model): /api/ps says whether it is loaded as the requests ask for it
(`loaded_as_asked`: at their context size, and on the processor alone where they ask for that - a model loaded
otherwise, by another program or another version, the server loads again at the next request, so it is loaded again
here, at the start rather than at the first page) (a page in the cache sends no
request, so reading the cache never loads it; it is not asked while the model answered
within `PS_RECHECK_S`, half its ``keep_alive`` when that is shorter, and a request that
failed or a release makes the next request ask again); when it is not, the reader is told
(`on_status`) and `warm_up` loads it under its own timeout, cancellable like a request:
beside the page models and the OCR readers, which stay (the judgement at the start counted
the model whole beside them: `taslation.ocr.place`). Every request carries ``keep_alive`` (the setting
``ollama_keep_alive``, in Ollama's own format: `keep_alive_value`): how long Ollama
keeps the model after it, so the pages that go on needing it keep it, and it goes by
itself after that; nothing asks for it periodically. `release` unloads it at once: the
end of a command, Menu > Release the model now, the window's close. ``"-1"`` (never unload) is
the one setting that keeps the old way: loaded at the start, before the OCR model,
and never released (`never_unloads`); a model found loaded as asked and kept for good (`kept_for_good`) is only
looked at then.

Every request to the model (`_chat`, PLaMo's `_generate`) runs within `taslation.ocr.place.translating`, a streamed
one to its end: the OCR readers on the GPU stay there meanwhile (19 to 39 ms a crop through the requests with their
CUDA graphs, 23 to 47 without, against 182 to 487 on the CPU), but one without its graphs where the start was short of
room and went on all the same reads on the CPU then, for its many small steps wait on a card past its memory (0.7 s a
crop instead of 0.13: `place.plain_beside_requests`). A load moves nothing: a crop on the GPU during a load reads as
fast as on an idle GPU.

A load is checked afterwards: a model that came up partly on the CPU (`gpu_share`) is said to the reader
(``ollama.partly_on_gpu``), and nothing else is done. What else holds GPU memory did not change Ollama's share when
measured (Windows, Ollama 0.40, a card of 6 GB): the model came up whole next to 4.8 GB held by torch, idle, or 4 GB
in constant use, with Ollama reading 5.0 GB free throughout, since the driver moves the others' memory aside. A model
that does land partly on the CPU translates 4 times slower (14.5 against 63 tokens/s at 55 %). ``num_gpu`` 0 (the
judgement at the start sent the model to the processor: `taslation.translate.models`) is not checked.

``num_gpu`` (the setting ``ollama_num_gpu``, `num_gpu_value`): None, the default, sends nothing and leaves it to the
server, as before (the requests are what they were, byte for byte); a number goes with every request and every
warm-up as Ollama's ``num_gpu`` option, the number of the model's layers it puts on the GPU (0: the processor only).
The option's name is the one Ollama's own options carry (``NumGPU json:"num_gpu"``); a model split on purpose is
neither loaded again nor said to be partly on the CPU. `release_now` (Menu > Release the model now) unloads the
models this translator had Ollama load or use, whatever ``keep_alive`` says, and names those that were loaded.
"""

from __future__ import annotations

import functools
import http.client
import io
import json
import logging
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable, Iterator, Sequence
from urllib.parse import urlparse

from .. import analysis
from ..health import is_default_model, pull_command
from ..messages import Cancelled, Message
from ..netguard import is_loopback_host
from ..ocr import place as ocr_place
from .base import HINT_FOLLOWS, TranslationError

LOG = logging.getLogger(__name__)

POLL_S = 0.1  # how often a streamed request looks at its cancel event while it waits for the answer
# How long Ollama keeps the model after a request (Settings.ollama_keep_alive). Long enough for a reader on
# untranslated pages, who needs it once or twice a minute, to pay for one load (3.4 s) only, and for a pause of a few
# minutes; short enough that a reader who has gone on to cached pages soon has the GPU memory (3.7 GB) back. It is
# Ollama's own default too.
KEEP_ALIVE = "5m"
WARM_UP_TIMEOUT = 300.0  # seconds a warm-up may take at most: a model loaded from a slow disk
WARM_UP_PROMPT = "Hi"  # what a warm-up asks (one token of answer)
PS_TIMEOUT = 3.0  # seconds /api/ps may take: it only looks
# A model that answered a request or loaded this many seconds ago at most (and less than half its keep_alive) counts
# as loaded: `ensure_loaded` asks /api/ps only when it is older than that, or after a request failed (15 ms of the
# ~27 a request took on the client's side, 2026-11-16)
PS_RECHECK_S = 30.0
TAIL_WAIT_S = 2.0  # how long the end of a streamed answer is waited for after its last object (it follows at once)
# A streamed request that gets no answer (`NoAnswer`, see the module's docstring): no first byte within NO_ANSWER_S -
# or NO_ANSWER_TIMES the time its prompt is expected to take, when that is longer (`_no_answer_after`) - or a stream
# silent NO_ANSWER_S once it began; NO_ANSWER_CPU_S for either with every layer on the processor where the expected
# time is not known. Measured on the development machine (2026-11-20/21): a page request's first byte 0.07 to 3.2 s on
# the GPU, a whole prompt 10 to 13 s on the processor alone, a load 3.4 to 4.9 s (made before the request, never in it)
NO_ANSWER_S = 30.0
NO_ANSWER_CPU_S = 60.0
NO_ANSWER_TIMES = 3.0
# a load (whose first byte comes once the model is in memory) asks /api/ps this often while nothing comes, on a
# connection of its own, and ends as no answer when the server is silent ALIVE_MISSES times in a row
ALIVE_EVERY_S = 10.0
ALIVE_MISSES = 2
# ... and within an incident (a request got no answer, and none answered since) its first byte is bounded too: within
# NO_ANSWER_LOAD_S, or NO_ANSWER_TIMES the longest load this translator measured when that is longer (`_load_bound`).
# A server whose model process hangs loads the model again and again while /api/ps answers: the load of the request
# asked again was waited for WARM_UP_TIMEOUT and ended as a timeout, the server never started again (2026-11-21)
NO_ANSWER_LOAD_S = 60.0
RELEASE_TIMEOUT = 3.0  # seconds a request to unload may take: the end of a command or the window's close wait for it
RELEASE_WAIT_S = 10.0  # how long `release(wait=True)` waits for the model to be gone (0.3 s as a rule)
FULL_GPU_SHARE = 0.99  # the share of the model in GPU memory (`gpu_share`) from which it counts as being on the GPU
_SECONDS_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
_DURATION_RE = re.compile(r"[-+]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:ns|us|µs|μs|ms|s|m|h))+")  # as Go writes a duration


def keep_alive_value(value: Any) -> int | float | str:
    """*value* (``ollama_keep_alive``: "30m", "-1", 600, ...) as Ollama's ``keep_alive`` takes it: a duration as Go
    writes one ("30m", "1h30m", "90s", "-1m") as it is; a number of seconds - also one written as a string, such as
    "-1" (never unloads) or "0" (unloads after each request) - as a JSON number, since Ollama reads a string only as
    a duration and "-1" is none. ValueError for anything else."""
    if isinstance(value, bool):
        raise ValueError(f"not a keep_alive: {value!r}")
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if _SECONDS_RE.fullmatch(text):
        number = float(text)
        return int(number) if number.is_integer() else number
    if _DURATION_RE.fullmatch(text):
        return text
    raise ValueError(f"not a keep_alive: {value!r} (a duration such as \"30m\" or \"2h\", or seconds such as \"-1\")")


NUM_GPU_MOST = 999  # the most layers ``ollama_num_gpu`` may name (Ollama puts no more on the GPU than the model has)


def num_gpu_value(value: Any) -> int | None:
    """*value* (``ollama_num_gpu``: "", "0", "20", 20) as Ollama's ``num_gpu`` option takes it: None for an empty
    value (nothing sent: the server decides), else the number of the model's layers on the GPU, 0 to `NUM_GPU_MOST`
    (0: the processor only). ValueError for anything else."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"not a number of layers: {value!r}")
    if isinstance(value, int):
        number = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if not text.isdigit() or not text.isascii():
            raise ValueError(f"not a number of layers: {value!r}")
        number = int(text)
    if not 0 <= number <= NUM_GPU_MOST:
        raise ValueError(f"not a number of layers: {value!r} (0 to {NUM_GPU_MOST})")
    return number


def never_unloads(value: Any) -> bool:
    """Whether a ``keep_alive`` (as `keep_alive_value` takes it) keeps the model for good: a negative number or
    duration."""
    kept = keep_alive_value(value)
    return kept.startswith("-") if isinstance(kept, str) else kept < 0


def unloads_at_once(value: Any) -> bool:
    """Whether a ``keep_alive`` unloads the model after every request: nothing loaded beforehand would be there for
    the request."""
    kept = keep_alive_value(value)
    return not any(c in "123456789" for c in kept) if isinstance(kept, str) else kept == 0


_UNIT_SECONDS = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "μs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
_PART_RE = re.compile(r"(\d+(?:\.\d*)?|\.\d+)(ns|us|µs|μs|ms|s|m|h)")


def keep_alive_seconds(value: Any) -> float:
    """How long a ``keep_alive`` keeps the model after a request, in seconds: ``inf`` for one that keeps it for good,
    0 for one that unloads it at once."""
    kept = keep_alive_value(value)
    if never_unloads(kept):
        return float("inf")
    if not isinstance(kept, str):
        return float(kept)
    return sum(float(n) * _UNIT_SECONDS[unit] for n, unit in _PART_RE.findall(kept))


def same_model(name: Any, model: str) -> bool:
    """Whether Ollama's *name* of a model is *model*, which may leave out the tag (":latest")."""
    return str(name) == model or (":" not in model and str(name) == f"{model}:latest")


def entry_name(entry: dict[str, Any]) -> str:
    """The name of the model of an /api/ps *entry*."""
    return str(entry.get("name") or entry.get("model") or "")


def of_model(entries: Iterable[dict[str, Any]], model: str) -> dict[str, Any] | None:
    """The /api/ps entry of *model* among *entries* (`OllamaTranslator._ps_models`), None when it is not loaded."""
    for entry in entries:
        if same_model(entry_name(entry), model):
            return entry
    return None


KEPT_FOR_GOOD_YEARS = 100  # /api/ps's ``expires_at`` of a model loaded with keep_alive -1: some 290 years ahead


def kept_for_good(entry: dict[str, Any] | None) -> bool:
    """Whether the model of the /api/ps *entry* is kept loaded for good (``keep_alive`` -1: its ``expires_at`` more
    than `KEPT_FOR_GOOD_YEARS` ahead); False for no entry or a date that cannot be read."""
    text = str((entry or {}).get("expires_at") or "")
    if len(text) < 4 or not text[:4].isdigit():
        return False
    return int(text[:4]) - time.gmtime().tm_year > KEPT_FOR_GOOD_YEARS


def loaded_message(model: str, seconds: float) -> Message:
    """What is said once Ollama has *model* loaded (``ollama.loaded``: the warm-up took *seconds*)."""
    return Message("ollama.loaded", model=str(model), seconds=round(float(seconds), 1))


class NoAnswer(TranslationError):
    """A streamed request that got no answer (`_Watch`): no first byte within its bound, a stream silent past its
    bound, or (*load*) a load past its bound within an incident or (*ps_silent*) whose server stopped answering
    /api/ps. Its message is the sentence a request the rule ends with is given (``ollama.not_answering``); *waited*:
    the seconds of silence; *began*: whether bytes of the answer had come."""

    def __init__(self, waited: float = 0.0, began: bool = False, load: bool = False, ps_silent: bool = False):
        super().__init__(Message("ollama.not_answering"))
        self.waited, self.began, self.load = float(waited), bool(began), bool(load or ps_silent)
        self.ps_silent = bool(ps_silent)


def _start_again(on_text: Callable[[str], None] | None) -> None:
    """A handler of an answer's pieces that can start again (`ItemStream.feed`: its object's ``reset``) made to, before
    the request is asked once more."""
    reset = getattr(getattr(on_text, "__self__", None), "reset", None)
    if callable(reset):
        reset()


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["id", "text"],
            },
        }
    },
    "required": ["translations"],
}

SYSTEM_PROMPT = """You are a professional manga translator working from Japanese into {language}.
You receive the speech bubbles of consecutive manga pages as JSON, in reading order (right to left, top to bottom), sometimes with translator's notes, the previous translations and the bubbles that come next.
Translate each bubble into natural, concise {language} that fits a speech bubble and reads as one continuous conversation.

Rules:
- Write {language} in its own normal script and spelling; never romanize or transliterate the whole line.
- Follow the translator's notes and the glossary for character names, terms and tone; keep names consistent with the earlier translations.
- Keep character names as names (transcribe them the way {language} normally writes Japanese names); do not translate names.
- Use the surrounding bubbles to resolve who is speaking to whom, omitted subjects and pronouns, and callbacks to earlier lines.
- A bubble may carry reader-made facts: "speaker" (who says it: keep that character's voice and gender), "kind" (speech, thought, shout, narration, sfx, handwritten: match the style), "continues" (its sentence goes on in the next bubble: translate the two as one sentence split at the same point) and "note" (a remark to follow). Trust them.
- A bubble may carry "room": the number of characters, spaces included, it has space for at a readable size. Stay within it by being concise (short words, contractions, no filler), never by dropping meaning.
- Keep the register and emotion: casual stays casual, polite stays polite, shouting stays short and loud.
- Keep ellipses, "!?" style punctuation and trailing sounds (e.g. "...", "!!").
- Sound effects become a short onomatopoeia (e.g. "BANG", "THUD").
- OCR noise happens: if a bubble is garbled beyond meaning, return an empty string for it; never copy the Japanese.
- No explanations outside the JSON, no alternatives, no honorific glossaries.
Respond with JSON only: {{"translations": [{{"id": 1, "text": "..."}}, ...]}} with exactly one entry per input id."""

REQUEST_TERMS_HEADING = "Names and terms in these bubbles that the notes above leave out (follow these renderings):"

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


class OllamaTranslator:
    name = "ollama"
    hint_support = HINT_FOLLOWS  # a region's hint goes with its bubble as "note" (`build_messages`)
    uses_room = True  # a bubble's room goes with it as "room" (`build_messages`): measured before the request

    def __init__(
        self,
        url: str = "http://127.0.0.1:11434",
        model: str = "qwen3.5:4b",
        timeout: float = 900.0,
        temperature: float = 0.2,
        num_ctx: int = 16384,
        target_language: str = "English",
        slow_after: float = 20.0,
        keep_alive: Any = KEEP_ALIVE,
        seed: int | None = None,
        num_gpu: int | None = None,
    ):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not is_loopback_host(parsed.hostname):
            raise TranslationError(Message("ollama.not_loopback", url=url))
        self.base = url.rstrip("/")
        self._scheme = parsed.scheme
        self._host = parsed.hostname or "127.0.0.1"
        try:
            self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as e:
            raise TranslationError(Message("ollama.not_loopback", url=url)) from e
        self._prefix = parsed.path.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.slow_after = slow_after  # seconds without a word from Ollama before on_slow is called
        self.temperature = temperature
        self.num_ctx = num_ctx
        # Ollama's sampling seed (``options.seed``) for every request; None (the app): none is sent and every answer
        # is a fresh draw. The evaluation tools fix it so that two runs of the same prompts agree
        self.seed = seed
        # Ollama's ``num_gpu`` (the layers on the GPU, 0: the processor only) for every request and warm-up; None (the
        # default): none is sent and the server decides, as before (``ollama_num_gpu``, `num_gpu_value`)
        self.num_gpu = num_gpu_value(num_gpu)
        self.target_language = target_language
        self.keep_alive = keep_alive_value(keep_alive)  # every request's keep_alive, as Ollama takes it
        self._supports_think: bool | None = None  # learned from the server on the first request
        # brings Ollama back when a request finds it gone (`taslation.ollama_start.OllamaStarter.revive`): given the
        # request's cancel event, True when it answers again; None: a request that finds it gone fails, as doctor's do
        self.revive: Callable[[threading.Event | None], bool] | None = None
        # the server TASlation started stopped and started again when a request got no answer twice, or /api/ps was
        # silent (`OllamaStarter.restart`, given the request's cancel event): True when it answers again, False when it
        # did not come back (or was started again within ten minutes), None when it is not one TASlation started (never
        # touched then); None: no restart (the request ends with the sentence)
        self.restart: Callable[[threading.Event | None], bool | None] | None = None
        # the incident under way (a request got no answer, and none answered since: `_after_silence`), its number and
        # its silences; ``silent``: the number of the incident a request was ended in with ``ollama.not_answering``,
        # 0 once an answer came (`_answered`) - what the backlog pauses for (`backlog.Backlog.tick`)
        self._incident: dict[str, int] | None = None
        self._incidents = 0
        self.silent = 0
        self.endings = 0  # (the requests ended so, all told: a pause the reader lifted comes back at the next one)
        self._incident_lock = threading.Lock()
        self._waits = _Waits()  # the seconds the requests waited for a first byte in a row, none coming (`_Watch`)
        self._load_most = 0.0  # the longest load this translator measured (`_load_bound`)
        self._share: float | None = None  # the model's share on the GPU last seen (`gpu_share`; 0.0: the processor)
        # told about a load as a Message: ``ollama.loading``, ``ollama.loaded``, ``ollama.partly_on_gpu``
        self.on_status: Callable[[Message], Any] | None = None
        self._used: set[str] = set()  # the models this translator had Ollama load or use (what `release` unloads)
        self._loading = threading.Lock()  # one `ensure_loaded` at a time: another waits, then finds the model loaded
        self._quietly = False  # the `ensure_loaded` under way tells nothing (the window's load at the start)
        self.last_stats: dict[str, Any] = {}
        # the known model (`models.TranslatorModel`) the target language chose for this translator (`make_translator`
        # with ``ollama_model = "auto"``), None for a model set by hand: a model Ollama lacks is then said as
        # ``translator.model_missing``, the language's model to install
        self.auto_model: Any = None
        # No proxies, ever: a system proxy must never see the text of your books. The requests go straight to the
        # loopback address over http.client, one connection kept per thread that talks to the server (`_held`)
        self._local = threading.local()
        # (model, until): the model answered a request or loaded lately, so that `ensure_loaded` does not ask /api/ps
        # before every request (`PS_RECHECK_S`)
        self._fresh: tuple[str, float] = ("", 0.0)

    # --- plumbing -----------------------------------------------------------
    def _revived(self, error: TranslationError, cancel: threading.Event | None = None) -> bool:
        """Whether a request that failed with *error* is worth sending once more: nothing answered, and `revive` has
        brought Ollama back. Nothing of an answer has come then (the connection was refused)."""
        return (self.revive is not None and error.message.code == "ollama.unreachable"
                and bool(self.revive(cancel)))

    def _request(self, path: str, payload: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        """Ollama's answer to one request; when it finds Ollama gone, sent once more after `_revived`."""
        try:
            return self._request_once(path, payload, timeout)
        except TranslationError as e:
            if not self._revived(e):
                raise
        return self._request_once(path, payload, timeout)

    def _request_once(self, path: str, payload: dict[str, Any] | None = None,
                      timeout: float | None = None) -> dict[str, Any]:
        """Ollama's answer to one request, in one piece, on this thread's connection (`_held`): one the server closed
        while it was kept (Ollama's own idle close, a restart) is opened anew and the request sent once more, nothing of
        it having been answered."""
        _own_priority(path)
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        limit = timeout or self.timeout
        for _attempt in range(2):
            conn, kept = self._held(limit)
            try:
                conn.response_class = http.client.HTTPResponse
                conn.request("POST" if data else "GET", self._prefix + path, body=data, headers=headers)
                resp = conn.getresponse()
                _answer_began(getattr(self, "base", ""), path)
                status, body = resp.status, resp.read()
                if resp.will_close:
                    self._drop()
            except (OSError, http.client.HTTPException) as e:
                self._drop()
                if kept and _stale(e):
                    continue  # (kept, and closed by the server: the request never reached it)
                raise self._failure(e, path, limit) from e
            break
        if status >= 300:
            raise self._http_failure(status, body, path)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise TranslationError(Message("ollama.bad_json", path=path)) from e

    def _held(self, timeout: float) -> tuple[http.client.HTTPConnection, bool]:
        """This thread's connection to Ollama, with *timeout* for each wait on it, and whether it was kept from an
        earlier request (a new one connects with the request). Never shared between threads: the page's worker, a load
        ahead, the backlog and the window's own requests each have theirs (a new connection costs
        ~15 ms, a kept one 0.2)."""
        conn = getattr(self._local, "conn", None)
        kept = conn is not None and conn.sock is not None
        if conn is None:
            conn = self._local.conn = self._connection()
        conn.timeout = timeout
        if conn.sock is not None:
            conn.sock.settimeout(timeout)
        return conn, kept

    def _drop(self) -> None:
        """This thread's connection closed and let go (after an error, a cancel, or a server that closes it)."""
        conn = getattr(self._local, "conn", None)
        self._local.conn = None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - a connection that will not close is let go all the same
                pass

    def _failure(self, e: BaseException, path: str, timeout: float) -> TranslationError:
        """What went wrong with a request, as the TranslationError to raise (never with the operating system's
        own error text, which is in the system's language)."""
        if isinstance(e, urllib.error.HTTPError):
            body = b""
            try:
                body = e.read()
            except Exception:
                pass
            return self._http_failure(e.code, body, path)
        if isinstance(e, urllib.error.URLError):
            if isinstance(e.reason, TimeoutError):
                return TranslationError(Message("ollama.timeout", seconds=float(timeout)))
            return TranslationError(Message("ollama.unreachable", url=self.base))
        if isinstance(e, TimeoutError):
            return TranslationError(Message("ollama.timeout", seconds=float(timeout)))
        if isinstance(e, (ConnectionRefusedError, socket.gaierror)):
            return TranslationError(Message("ollama.unreachable", url=self.base))
        # reset, or a body cut short, while Ollama restarts
        return TranslationError(Message("ollama.connection_failed", url=self.base))

    def _http_failure(self, status: int, body: bytes, path: str) -> TranslationError:
        """An answer with an error status: a model Ollama does not have, or what the server says."""
        detail = error_text(body)
        if status == 404 and "model" in detail.lower() and "not found" in detail.lower():
            if self.auto_model is not None:
                from .models import missing_message

                return TranslationError(missing_message(self.auto_model, self.target_language))
            if is_default_model(self.model):
                return TranslationError(Message("ollama.model_missing", model=self.model))  # install.cmd fetches it
            return TranslationError(Message("health.chosen_model_missing", model=self.model,
                                            command=pull_command(self.model)))
        return TranslationError(Message("ollama.http_error", status=int(status), path=path, detail=detail))

    def _connection(self) -> http.client.HTTPConnection:
        cls = http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
        return cls(self._host, self._port, timeout=self.timeout)

    def _stream(self, path: str, payload: dict[str, Any], on_text: Callable[[str], None],
                cancel: threading.Event | None = None, on_slow: Callable[[float], None] | None = None,
                timeout: float | None = None, first: float | None = None, between: float | None = None,
                alive: Callable[[], bool] | None = None) -> dict[str, Any]:
        """`_stream_once`; when it finds Ollama gone, sent once more after `_revived` (which *cancel* interrupts)."""
        try:
            return self._stream_once(path, payload, on_text, cancel, on_slow, timeout, first, between, alive)
        except TranslationError as e:
            if not self._revived(e, cancel):
                if cancel is not None and cancel.is_set():
                    raise Cancelled() from e
                raise
        return self._stream_once(path, payload, on_text, cancel, on_slow, timeout, first, between, alive)

    def _stream_once(self, path: str, payload: dict[str, Any], on_text: Callable[[str], None],
                     cancel: threading.Event | None = None, on_slow: Callable[[float], None] | None = None,
                     timeout: float | None = None, first: float | None = None, between: float | None = None,
                     alive: Callable[[], bool] | None = None) -> dict[str, Any]:
        """POST *payload* (``stream: true``) and read the answer as Ollama sends it, one JSON object per line,
        handing every piece of the message to *on_text* as it arrives. Returns the last object (the statistics)
        with the whole message in it. An answer that breaks off before its last object is an error, as a cut-off
        answer is in one piece.

        The answer is waited for in steps of ``POLL_S``: once *cancel* is set the connection is closed and
        `Cancelled` raised; *on_slow*(seconds) is called once when nothing has come for ``slow_after`` seconds; it
        gives up after *timeout* (default: the translator's) seconds without a byte. *first*, *between*, *alive*: the
        no-answer bounds (`_Watch`): past them the connection is closed and `NoAnswer` raised.
        No proxy is ever involved (the connection goes straight to the loopback address)."""
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        _own_priority(path)
        data = json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/x-ndjson", "Content-Type": "application/json"}
        pieces: list[str] = []
        last: dict[str, Any] | None = None
        timeout = timeout or self.timeout
        if alive is not None and first is None:  # (a load: bounded within an incident only)
            first = self._load_bound()
        for _attempt in range(2):
            watch = _Watch(cancel, on_slow, self.slow_after, timeout, first, between, alive, self._waits)
            conn, kept = self._held(timeout)
            resp: http.client.HTTPResponse | None = None
            whole = False  # the answer read to its end: the connection may be kept for the next request
            began = False  # something of the answer came (the request reached the server)
            try:
                conn.response_class = http.client.HTTPResponse
                conn.request("POST", self._prefix + path, body=data, headers=headers)
                if conn.sock is not None:
                    conn.sock.settimeout(POLL_S)  # the answer is read in short waits (see _Watch)
                conn.response_class = functools.partial(_Response, watch=watch)  # type: ignore[assignment]
                resp = conn.getresponse()
                began = True
                _answer_began(getattr(self, "base", ""), path)
                if resp.status >= 300:
                    raise self._http_failure(resp.status, resp.read(65536), path)
                for raw in resp:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as e:
                        raise TranslationError(Message("ollama.bad_json", path=path)) from e
                    if not isinstance(obj, dict):
                        raise TranslationError(Message("ollama.bad_json", path=path))
                    if obj.get("error"):
                        raise TranslationError(Message("ollama.reported_error", path=path,
                                                       detail=str(obj["error"])[:300]))
                    # a chat's piece is in its message; /api/generate's (`PlamoTranslator`) in its "response"
                    piece = str((obj.get("message") or {}).get("content") or obj.get("response") or "")
                    if piece:
                        pieces.append(piece)
                        on_text(piece)
                    if obj.get("done"):
                        last = obj
                        break
                if last is not None:  # the end of the chunked answer read, so that the connection is clean for the
                    watch.timeout = min(timeout, TAIL_WAIT_S)  # next request (not waited for long: closed then)
                    watch.first = watch.between = watch.alive = None  # (the answer is whole: no no-answer now)
                    try:
                        resp.read()
                        whole = not resp.will_close
                    except (OSError, http.client.HTTPException, Cancelled):
                        whole = False
            except (OSError, http.client.HTTPException) as e:
                if cancel is not None and cancel.is_set():
                    raise Cancelled() from e
                if kept and not began and _stale(e):
                    self._drop()
                    continue  # (kept, and closed by the server: the request never reached it)
                raise self._failure(e, path, timeout) from e
            finally:
                watch.close()
                if resp is not None:
                    resp.close()
                if whole and conn.sock is not None:
                    conn.response_class = http.client.HTTPResponse
                    conn.sock.settimeout(self.timeout)
                else:
                    self._drop()  # on a cancel: the connection goes, and Ollama stops writing
            break
        if last is None:
            raise TranslationError(Message("ollama.broke_off", path=path))
        return {**last, "message": {**dict(last.get("message") or {}), "content": "".join(pieces)}}

    def ping(self) -> bool:
        try:
            self._request("/api/tags", timeout=3.0)
            return True
        except TranslationError:
            return False

    def version(self) -> str:
        try:
            return str(self._request("/api/version", timeout=3.0).get("version", "?"))
        except TranslationError:
            return ""

    def list_models(self) -> list[str]:
        data = self._request("/api/tags", timeout=5.0)
        names = [m.get("name", "") for m in data.get("models", [])]
        return [n for n in names if n]

    def has_model(self, name: str | None = None) -> bool:
        want = name or self.model
        models = self.list_models()
        if want in models:
            return True
        return ":" not in want and any(m.split(":", 1)[0] == want for m in models)

    def _gpu_option(self, options: dict[str, Any]) -> dict[str, Any]:
        """*options* with ``num_gpu`` when the translator has one (`num_gpu`); left as they are when it has none."""
        if self.num_gpu is not None:
            options["num_gpu"] = int(self.num_gpu)
        return options

    def _chat(self, messages: list[dict[str, str]], fmt: Any, max_tokens: int = 0,
              on_text: Callable[[str], None] | None = None, cancel: threading.Event | None = None,
              on_slow: Callable[[float], None] | None = None) -> str:
        """The model's answer to *messages*; with *on_text*, read as it is written (each piece handed over). With
        *cancel* or *on_slow* the answer is streamed as well, so that it can be cancelled or found slow. The model is
        made sure of first (`ensure_loaded`), within the rule for a request without an answer (`_answer`)."""
        self._used.add(self.model)
        stream = on_text is not None or cancel is not None or on_slow is not None
        options: dict[str, Any] = {"temperature": self.temperature}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        self._gpu_option(options)
        if self.seed is not None:
            options["seed"] = int(self.seed)
        if max_tokens > 0:
            # A runaway generation (a model looping inside the JSON) must end well
            # before the request timeout; a missing id is retried, a stall is not.
            options["num_predict"] = int(max_tokens)
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": stream,
                                   "format": fmt, "options": options, "keep_alive": self.keep_alive}
        if self._supports_think is not False:
            # Hybrid "thinking" models must answer directly: a reasoning monologue
            # before the JSON is slow and sometimes never ends.
            payload["think"] = False

        def send() -> dict[str, Any]:
            with ocr_place.translating():  # (counted as the model computes, to its end: `place.plain_beside_requests`)
                if stream:
                    return self._stream("/api/chat", payload, on_text or _ignore, cancel, on_slow,
                                        first=self._no_answer_after(), between=self._silent_after())
                return self._request("/api/chat", payload)

        def asked() -> dict[str, Any]:
            try:
                return send()
            except TranslationError as e:
                if "think" in payload and refuses_think(e):
                    self._supports_think = False  # older server or a model without a thinking mode
                    payload.pop("think")
                    return send()
                raise

        try:
            data = self._answer(asked, cancel, on_text, load=lambda: self.ensure_loaded(cancel, on_slow))
        except TranslationError:
            self._unsure()
            raise
        self._answered(self.model)
        self.last_stats = {k: data.get(k) for k in ("prompt_eval_count", "eval_count", "prompt_eval_duration", "eval_duration",
                                                    "total_duration", "done_reason")}
        content = str(data.get("message", {}).get("content", ""))
        analysis.request(lambda: {"translator": "chat", "messages": [dict(m) for m in messages], "raw": content,
                                  "stats": dict(self.last_stats)})  # (developer measuring alone)
        return content

    def _chat_once(self, payload: dict[str, Any], timeout: float | None = None, cancel: threading.Event | None = None,
                   on_slow: Callable[[float], None] | None = None,
                   alive: Callable[[], bool] | None = None) -> dict[str, Any]:
        """POST *payload* to /api/chat (``think`` off when the server knows it; once it refuses it, never again) and
        return Ollama's answer: in one piece, or streamed when there is a *cancel* or an *on_slow* to serve (*alive*:
        a load's look at the server, `_Watch`)."""
        if self._supports_think is not False:
            payload["think"] = False

        def send() -> dict[str, Any]:
            if cancel is None and on_slow is None:
                return self._request("/api/chat", payload, timeout)
            return self._stream("/api/chat", {**payload, "stream": True}, _ignore, cancel, on_slow, timeout,
                                alive=alive)

        try:
            return send()
        except TranslationError as e:
            if "think" in payload and refuses_think(e):
                self._supports_think = False
                payload.pop("think")
                return send()
            raise

    def warm_up(self, model: str | None = None, keep_alive: Any = None, timeout: float | None = None,
                cancel: threading.Event | None = None, on_slow: Callable[[float], None] | None = None) -> float:
        """Load *model* (default: the translator's) in Ollama now, with a one-token request (``num_predict`` 1), and
        keep it loaded *keep_alive* (default: the translator's ``keep_alive``) after it; the seconds it took (the load,
        when the model was not loaded yet; a few hundredths when it was). The request asks for the context size every
        request asks for (a model loaded with another would be loaded again by the first page). Raises
        `TranslationError` as every request does; never longer than ``WARM_UP_TIMEOUT``. *cancel* and *on_slow* as for
        `translate_page`; streamed, the server is looked at while it loads (`_ps_answers`: `NoAnswer` when it is
        silent `ALIVE_MISSES` times in a row)."""
        options: dict[str, Any] = {"num_predict": 1, "temperature": 0}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        self._gpu_option(options)  # (loaded with the layers the requests ask for, so that none loads it again)
        payload: dict[str, Any] = {"model": model or self.model,
                                   "messages": [{"role": "user", "content": WARM_UP_PROMPT}], "stream": False,
                                   "options": options,
                                   "keep_alive": self.keep_alive if keep_alive is None else keep_alive_value(keep_alive)}
        self._used.add(payload["model"])
        start = time.monotonic()
        self._chat_once(payload, timeout or min(self.timeout, WARM_UP_TIMEOUT), cancel, on_slow, alive=self._ps_answers)
        if payload["keep_alive"] == self.keep_alive:
            self._answered(payload["model"])
        return time.monotonic() - start  # (not last_stats: a warm-up must not stand in for a page's statistics)

    def _ps_models(self) -> list[dict[str, Any]]:
        """Every model Ollama's /api/ps says is loaded now (its entries). Raises `TranslationError`; never starts
        Ollama, never loads a model."""
        data = self._request_once("/api/ps", timeout=PS_TIMEOUT)
        return [entry for entry in data.get("models") or [] if isinstance(entry, dict)]

    def _loaded(self, model: str) -> dict[str, Any] | None:
        """What Ollama's /api/ps says of *model*, None when it is not loaded. Raises `TranslationError`; never starts
        Ollama."""
        return of_model(self._ps_models(), model)

    def loaded_as_asked(self, entry: dict[str, Any] | None) -> bool:
        """Whether the model of the /api/ps *entry* is loaded as this translator's requests ask for it, so that the
        server serves them without loading it again: at their context size (``num_ctx``; or a multiple of it, a
        server's parallel slots) where /api/ps says one (``context_length``; an older server that does not: as
        asked), and with none of it on the GPU where they ask for the processor alone (``num_gpu`` 0). A model a
        request asks for with another context or on the processor alone is loaded again by the server (its runner's
        options differ); a number of layers set by hand is not looked at (/api/ps does not say them). False for no
        entry."""
        if not entry:
            return False
        context = entry.get("context_length")
        try:
            context, asked = int(context or 0), int(self.num_ctx or 0)
        except (TypeError, ValueError):
            context, asked = 0, 0
        if context and asked and (context < asked or context % asked):
            return False
        return not (self.num_gpu == 0 and entry.get("size_vram"))

    def has_loaded(self, model: str | None = None, for_good: bool = False) -> bool:
        """Whether Ollama has *model* (default: the translator's) loaded as the requests ask for it
        (`loaded_as_asked`) and, with *for_good*, kept loaded for good (`kept_for_good`): /api/ps only, nothing
        loaded; False when it does not answer."""
        try:
            entry = self._loaded(model or self.model)
        except TranslationError:
            return False
        return self.loaded_as_asked(entry) and (not for_good or kept_for_good(entry))

    def gpu_share(self, model: str | None = None) -> float | None:
        """How much of the loaded *model* (default: the translator's) is in GPU memory: ``size_vram`` / ``size`` of
        /api/ps, 1.0 for all of it. None when that cannot be told (not loaded, or Ollama does not say)."""
        try:
            entry = self._loaded(model or self.model)
        except TranslationError:
            return None
        if entry is None or not entry.get("size") or entry.get("size_vram") is None:
            return None
        share = float(entry["size_vram"]) / float(entry["size"])
        if model is None or model == self.model:
            self._share = share
        return share

    def _say(self, message: Message) -> None:
        if self.on_status is not None:
            try:
                self.on_status(message)
            except Exception:  # noqa: BLE001 - whoever listens must not end the request
                pass

    def ensure_loaded(self, cancel: threading.Event | None = None,
                      on_slow: Callable[[float], None] | None = None, quiet: bool = False) -> None:
        """The model in memory before a request is sent (see the module's docstring). Nothing happens when it is
        loaded, when ``keep_alive`` would unload it right away, or when /api/ps does not answer: the request then goes
        out as it always did, and says what is wrong itself (and starts Ollama). A load that fails raises what the
        request would have raised; Stop raises `Cancelled`. One at a time: a call while another loads (the page's
        model loaded ahead while the page is read, `pipeline.LoadAhead`) waits for it - Stop ends the wait - and then
        finds the model loaded, so that the model is loaded once and the GPU models let go once. A call that waits gets
        its slow note (*on_slow*) after ``slow_after`` seconds, as a request does; the load it waits for ends by its own
        bounds (`warm_up`: ``WARM_UP_TIMEOUT``, and a server silent to /api/ps ends it), and so does the wait.

        *quiet* (the window's load at the start, ``load_model_at_start``): the load is not told (``ollama.loading``,
        ``ollama.loaded``), only a model partly on the CPU is; a call that comes to wait for it tells the load as its
        own, from when it began to wait to when the model is there."""
        if unloads_at_once(self.keep_alive):
            return
        began, told, slow = time.monotonic(), False, False
        while not self._loading.acquire(timeout=POLL_S):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if not told and self._quietly and not quiet:  # (what it waits for says nothing: it says it)
                told = True
                self._say(Message("ollama.loading", model=self.model))
            waited = time.monotonic() - began
            if on_slow is not None and not slow and waited >= self.slow_after:
                slow = True  # (said once: its own load, if it makes one, says nothing more of it)
                try:
                    on_slow(waited)
                except Exception:  # noqa: BLE001 - whoever listens must not end the request
                    pass
        try:
            self._quietly = quiet
            loaded = self._ensure_loaded(cancel, None if slow else on_slow, quiet=quiet, told=told)
        finally:
            self._quietly = False
            self._loading.release()
        if told and not loaded:
            self._say(loaded_message(self.model, time.monotonic() - began))

    def _ensure_loaded(self, cancel: threading.Event | None, on_slow: Callable[[float], None] | None,
                       quiet: bool = False, told: bool = False) -> bool:
        """`ensure_loaded`, its turn come: nothing asked while the model answered lately (`_answered`), nothing loaded
        while /api/ps has it loaded as asked (`loaded_as_asked`; loaded otherwise, it is loaded again now with the
        requests' options). Whether it loaded the model (and said so, unless *quiet*; *told*: the load was told
        already)."""
        model = self.model
        held, until = self._fresh
        if held == model and time.monotonic() < until:
            return False
        try:
            if self.loaded_as_asked(self._loaded(model)):
                return False
        except TranslationError:
            return False
        if not (quiet or told):
            self._say(Message("ollama.loading", model=model))
        # (streamed whatever the caller gave, so that the server is looked at while it loads: `warm_up`)
        watched = cancel if cancel is not None else threading.Event()
        seconds = self.warm_up(model, timeout=WARM_UP_TIMEOUT, cancel=watched, on_slow=on_slow)
        self._load_most = max(self._load_most, seconds)
        share = self.gpu_share(model)
        checked = self.num_gpu is None  # (layers set by hand: a model split on purpose is as it should be)
        if not quiet:
            self._say(loaded_message(model, seconds))
        if checked and partly_on_gpu(share):
            self._say(Message("ollama.partly_on_gpu", model=model, percent=round(float(share or 0) * 100)))
        return True

    def _answered(self, model: str) -> None:
        """*model* answered a request (or a warm-up) just now: it is loaded for its ``keep_alive`` from now, and
        `ensure_loaded` takes it for loaded for `PS_RECHECK_S` (half the ``keep_alive`` when that is shorter) without
        asking /api/ps."""
        try:
            fresh = min(PS_RECHECK_S, keep_alive_seconds(self.keep_alive) / 2)
        except ValueError:
            fresh = 0.0
        self._fresh = (model, time.monotonic() + fresh) if fresh > 0 else ("", 0.0)
        self._waits.came()  # (an answer: the waits without one are counted from nothing)
        with self._incident_lock:  # (an answer: a request without one is an incident of its own from now on)
            if self._incident is not None:
                LOG.warning("no answer: the translation program answers again (incident %d)", self._incident["n"])
            self._incident, self.silent = None, 0

    def _unsure(self, model: str | None = None) -> None:
        """A request failed, or *model* (default: any) was unloaded: the next `ensure_loaded` asks /api/ps again."""
        if model is None or self._fresh[0] == model:
            self._fresh = ("", 0.0)

    # --- a request that gets no answer (the module's docstring) -----------------------------------------------
    def _lost(self) -> None:
        """What the client knew of the server's state is gone (a request without an answer, a server started again):
        the next request asks /api/ps whether the model is loaded, and the waits without a byte are counted from
        nothing (`_Waits`: the incident takes it from here)."""
        self._unsure()
        self._waits.clear()

    def _on_cpu(self) -> bool:
        """Whether every layer of the model is on the processor (``num_gpu`` 0, or none of it on the GPU last seen)."""
        return self.num_gpu == 0 or self._share == 0.0

    def _expected_s(self, prompt: str) -> float | None:
        """The seconds the server is expected to take for *prompt* before its first byte; None when that cannot be
        worked out (here: never; `plamo.PlamoTranslator` reckons it)."""
        return None

    def _no_answer_after(self, expected: float | None = None) -> float:
        """The seconds a request's first byte may take (`NoAnswer`): `NO_ANSWER_TIMES` the *expected* time of its
        prompt (`_expected_s`), `NO_ANSWER_S` at least; where that cannot be worked out `NO_ANSWER_S`, or
        `NO_ANSWER_CPU_S` with every layer on the processor."""
        if expected is None or expected <= 0:
            return self._silent_after()
        return max(NO_ANSWER_S, NO_ANSWER_TIMES * float(expected))

    def _load_bound(self) -> float | None:
        """The seconds a load's first byte - the model in memory - may take (`NoAnswer`): no bound outside an incident
        (a load from a slow disk keeps ``WARM_UP_TIMEOUT``); within one `NO_ANSWER_LOAD_S`, or `NO_ANSWER_TIMES` the
        longest load this translator measured when that is longer."""
        with self._incident_lock:
            if self._incident is None:
                return None
        return max(NO_ANSWER_LOAD_S, NO_ANSWER_TIMES * self._load_most)

    def _silent_after(self) -> float:
        """The seconds a stream may be silent once it began (`NoAnswer`)."""
        return NO_ANSWER_CPU_S if self._on_cpu() else NO_ANSWER_S

    def _ps_answers(self, timeout: float | None = None) -> bool:
        """Whether the server answers /api/ps at all (any HTTP status), within *timeout* (default: `PS_TIMEOUT`), on a
        connection of its own - never this thread's kept one, which a stream may be reading."""
        conn = self._connection()
        conn.timeout = PS_TIMEOUT if timeout is None else timeout
        try:
            conn.request("GET", self._prefix + "/api/ps", headers={"Accept": "application/json"})
            conn.getresponse().read()
            return True
        except (OSError, http.client.HTTPException):
            return False
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - a connection that will not close is let go all the same
                pass

    def _silence(self, waited: float, kind: str, how: str) -> tuple[int, int, bool]:
        """A request got no answer: the incident under way (a new one when none is: said once, ``ollama.no_answer``)
        counts it, and the client's knowledge of the server is gone (`_lost`). (its number, its silences so far, whether
        it is new); the log names it."""
        self._lost()
        with self._incident_lock:
            new = self._incident is None
            if new:
                self._incidents += 1
                self._incident = {"n": self._incidents, "silences": 0}
            incident = self._incident
            incident["silences"] += 1
            n, silences = incident["n"], incident["silences"]
        if new:
            self._say(Message("ollama.no_answer", seconds=round(float(waited), 1)))
        LOG.warning("no answer: %s (%s), %.1f s %s (incident %d, silence %d)", kind,
                    threading.current_thread().name, waited, how, n, silences)
        return n, silences, new

    def _answer(self, send: Callable[[], Any], cancel: threading.Event | None,
                on_text: Callable[[str], None] | None = None, load: Callable[[], Any] | None = None,
                kind: str = "request") -> Any:
        """What *send*() - one request to the model - returns, *load*() before it (the model made sure of,
        `ensure_loaded`); a load or a request that gets no answer (`NoAnswer`) is taken as the module's docstring says
        (`_after_silence`) and both asked again on a new connection (*on_text*, a handler that can start again, starts
        again), or ends with ``ollama.not_answering``. A server started again once at most for it."""
        tried = {"restart": False}
        while True:
            try:
                if load is not None:
                    load()
                return send()
            except NoAnswer as e:
                self._after_silence(e, cancel, tried, kind)
            _start_again(on_text)

    def _after_silence(self, e: NoAnswer, cancel: threading.Event | None, tried: dict[str, bool], kind: str) -> None:
        """(a request that got no answer, *e*) Returns when the request is to be asked again on a new connection - the
        incident's first silence and /api/ps answers; or the server TASlation started was started again (`restart`,
        once for a request: *tried*) -, raises ``ollama.not_answering`` else: the incident is ``silent`` then, until
        the next answer. A cancel ends it as `Cancelled`. That the server is started again (``ollama.restarting``) is
        said once the restart is under way (the hook's *on_restarting*), never of a server it leaves as it is."""
        how = ("after its first bytes" if e.began else "while it loaded, the server silent to /api/ps" if e.ps_silent
               else "while it loaded" if e.load else "without a byte")
        n, silences, _new = self._silence(e.waited, kind, how)
        alive = self._ps_answers()
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if silences == 1 and alive:
            LOG.warning("no answer: %s asked again on a new connection (/api/ps answers)", kind)
            return
        if not tried["restart"] and self.restart is not None:
            tried["restart"] = True
            began = time.monotonic()
            try:
                done = self.restart(cancel, on_restarting=lambda: self._say(Message("ollama.restarting")))
            except Exception:  # noqa: BLE001 - a restart that fails ends the request as one that did not come back
                LOG.exception("no answer: starting the translation program again failed")
                done = False
            LOG.warning("no answer: /api/ps %s; the translation program %s (%.1f s)", "answers" if alive else "silent",
                        {True: "was started again", False: "was not started again (it did not come back, or it was "
                         "within ten minutes of the last time)", None: "is not one TASlation started: left as it is"}
                        .get(done, "?"), time.monotonic() - began)
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if done:
                self._lost()
                return
        with self._incident_lock:
            self.silent = n
            self.endings += 1
        LOG.warning("no answer: %s ended (/api/ps %s): the reader is told the translation program does not answer",
                    kind, "answers" if alive else "silent")
        raise TranslationError(Message("ollama.not_answering"))

    def release(self, model: str | None = None, wait: bool = False) -> None:
        """Ollama unloads *model* now (default: the models this translator had it load or use; with none, nothing is
        sent, so that a session that read only cached pages leaves another program's model alone). With *wait*, until
        it is gone. Never with a ``keep_alive`` that keeps the model for good. Never raises: Ollama down holds nothing,
        and Ollama's own ``keep_alive`` ends what a request here could not. Starts nothing."""
        if never_unloads(self.keep_alive):
            return
        for name in [model] if model else sorted(self._used):
            self._release(name, wait)

    def _release(self, name: str, wait: bool) -> bool:
        """Ollama unloads *name* now (with *wait*, until /api/ps no longer has it, `RELEASE_WAIT_S` at most); whether
        the request to unload was answered. Never raises; starts nothing."""
        self._used.discard(name)
        self._unsure(name)
        try:
            self._unload(name)
            end = time.monotonic() + RELEASE_WAIT_S
            while wait and self._loaded(name) is not None and time.monotonic() < end:
                time.sleep(POLL_S)
        except TranslationError:
            return False
        return True

    def release_now(self) -> list[str]:
        """Menu > Release the model now: every model this translator had Ollama load or use this session unloaded at
        once, whatever ``keep_alive`` says (even "-1": the next request loads it again, `ensure_loaded`), and waited
        for; the names of those Ollama had loaded (asked /api/ps first: one gone already is not named, and nothing is
        sent for it). A model this translator never used is never asked to go, so another program's model stays.
        Never raises: Ollama not answering holds nothing. Starts nothing."""
        released: list[str] = []
        for name in sorted(self._used):
            try:
                held = self._loaded(name) is not None
            except TranslationError as e:  # down: it holds nothing; a server without /api/ps: asked all the same
                held = e.message.code == "ollama.http_error"
            if not held:
                self._used.discard(name)
                self._unsure(name)
                continue
            if self._release(name, wait=True):
                released.append(name)
        return released

    def _unload(self, name: str) -> None:
        """Ollama unloads *name* now: a chat with no message and ``keep_alive`` 0. Raises `TranslationError`."""
        self._request_once("/api/chat", {"model": name, "messages": [], "stream": False, "keep_alive": 0},
                           RELEASE_TIMEOUT)

    def _chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any], max_tokens: int = 0,
                   on_text: Callable[[str], None] | None = None, cancel: threading.Event | None = None,
                   on_slow: Callable[[float], None] | None = None) -> str:
        try:
            return self._chat(messages, schema, max_tokens, on_text, cancel, on_slow)
        except TranslationError as e:
            # Older servers do not accept a JSON schema; plain JSON mode still works.
            if not http_status_is(e, 400):
                raise
            return self._chat(messages, "json", max_tokens, on_text, cancel, on_slow)

    @staticmethod
    def output_budget(texts: Sequence[str]) -> int:
        """Cap on the tokens a translation of *texts* can need (JSON overhead included).

        A normal reply uses roughly 10 tokens of JSON per bubble plus about one token
        per Japanese character; the cap leaves headroom for that and stops a looping
        reply at well under twice the normal length.
        """
        chars = sum(len(t) for t in texts)
        return max(512, 12 * len(texts) + 2 * chars)

    # --- translation ----------------------------------------------------------
    def build_messages(self, texts: Sequence[str], context: Sequence[tuple[str, str]], notes: str = "",
                       upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None) -> list[dict[str, str]]:
        items: list[dict[str, Any]] = []
        for i, t in enumerate(texts):
            item: dict[str, Any] = {"id": i + 1, "ja": t}
            if meta and i < len(meta) and meta[i]:
                item.update({k: v for k, v in meta[i].items() if k in ("speaker", "kind", "continues", "note", "room") and v})
            items.append(item)
        cut = request_terms(notes, items)
        system = SYSTEM_PROMPT.format(language=self.target_language)
        parts: list[str] = []
        if notes.strip():
            parts.append("Translator's notes (follow these renderings):")
            parts.append(notes.strip())
            parts.append("")
        if context:
            parts.append("Earlier bubbles, for context only (already translated, do not repeat them):")
            for src, dst in context:
                parts.append(f"- {src} => {dst}")
            parts.append("")
        if upcoming:
            parts.append("Bubbles that come next, for context only (do not translate them):")
            for src in upcoming:
                parts.append(f"- {src}")
            parts.append("")
        parts.append("Bubbles to translate:")
        parts.append(json.dumps(items, ensure_ascii=False))
        parts.extend(request_terms_part(cut))
        return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(parts)}]

    def translate_page(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = (), notes: str = "",
                       upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None,
                       on_item: Callable[[int, str], None] | None = None,
                       cancel: threading.Event | None = None,
                       on_slow: Callable[[float], None] | None = None) -> list[str]:
        """One translation per text, from one request. With *on_item*, the reply is read as the model writes it and
        on_item(index, translation) is called the moment a bubble's JSON object is complete (an early look: the
        list returned, parsed from the whole reply, is what counts). A reply that is not a list of objects gives no
        early looks; it is only parsed at the end, as without *on_item*. Once *cancel* is set the request ends and
        `Cancelled` is raised; *on_slow*(seconds) is called once when Ollama has said nothing for ``slow_after``
        seconds."""
        if not texts:
            return []
        messages = self.build_messages(texts, context, notes, upcoming, meta)
        on_text = None
        if on_item is not None:
            count = len(texts)

            def hand_over(obj: dict[str, Any], pos: int) -> None:
                item = item_of(obj, pos, count)
                if item is not None:
                    on_item(*item)

            on_text = ItemStream(hand_over).feed
        content = self._chat_json(messages, RESPONSE_SCHEMA, self.output_budget(texts), on_text, cancel, on_slow)
        result = parse_translations(content, len(texts))
        if all(not t for t in result):
            # No book text in the message: it may end up in a terminal or a log.
            raise TranslationError(Message("ollama.bad_answer", chars=len(content)))
        from .renderings import learn

        learn(notes, zip(texts, result))  # the book's names: what these lines show of them
        return result

    def translate_aside(self, text: str, context: Sequence[tuple[str, str]] = (), notes: str = "",
                        cancel: threading.Event | None = None,
                        on_slow: Callable[[float], None] | None = None) -> str:
        """One request beside a page's own (`locate_large`: where a bubble's larger lettering is in its translation):
        *text* translated as a page of one bubble after the earlier pairs *context*, with the premises *notes*, and
        nothing of it kept (no name learnt). "" when the answer holds no translation."""
        messages = self.build_messages([text], context, notes, (), None)
        content = self._chat_json(messages, RESPONSE_SCHEMA, self.output_budget([text]), None, cancel, on_slow)
        result = parse_translations(content, 1)
        return result[0] if result else ""


def request_terms(notes: str, rows: Sequence[dict[str, Any]]) -> list[str]:
    """The sheet's entries for the bubbles in *rows* that the premises *notes* were cut short of
    (`terms.cut_entries`; none unless *notes* carry their sheet, `annotations.Premises`), then the book's names held
    so far that the bubbles name and neither covers (`renderings.BookNames`), as "- Japanese = rendering"."""
    from .renderings import names_of

    sheet = getattr(notes, "sheet", None)
    lines = [str(r.get("ja", "")) for r in rows]
    out: list[str] = []
    if sheet is not None:
        from ..terms import cut_entries  # terms imports this package

        out = cut_entries(sheet, notes, lines, [str(r.get("speaker", "")) for r in rows])
    names = names_of(notes)
    if names is not None:
        shown = "\n".join([str(notes), *out])
        for line in lines:
            for ja, rendering in names.glossary(line):
                entry = f"- {ja} = {rendering}"
                if entry not in out and not (ja in shown and rendering in shown):
                    out.append(entry)
    return out


def request_terms_part(cut: Sequence[str]) -> list[str]:
    """The lines *cut* as the end of a request: after its bubbles, so that all before them stays a stable prefix."""
    return ["", REQUEST_TERMS_HEADING, *cut] if cut else []


def partly_on_gpu(share: float | None) -> bool:
    """Whether a model with this `gpu_share` is split between the GPU and the CPU. None of it on the GPU is a machine
    that has no GPU for Ollama, as it was: nothing to retry or to say."""
    return share is not None and 0.0 < share < FULL_GPU_SHARE


def _ignore(_text: str) -> None:
    pass


def _own_priority(path: str) -> None:
    """(before each request) The server TASlation started back at its own priority when the backlog's work had lowered
    it and this request has it compute for something else (`ollama_start.before_request`)."""
    from ..ollama_start import before_request

    before_request(path)


def _answer_began(url: str, path: str) -> None:
    """(as an answer begins) The runner of the model the server loaded for it put at the server's own priority class,
    never above normal, when TASlation started the server (`ollama_start.after_answer`: Ollama starts it above
    normal, over the viewer)."""
    try:
        from ..ollama_start import after_answer

        after_answer(url, path)
    except Exception:  # noqa: BLE001 - the answer is read all the same
        pass


def _stale(e: BaseException) -> bool:
    """Whether *e*, met on a connection kept from an earlier request before anything of the answer came, says that
    the server had closed it meanwhile (its idle close, a restart): the request is sent once more on a new one."""
    return isinstance(e, (http.client.RemoteDisconnected, http.client.CannotSendRequest, http.client.BadStatusLine,
                          ConnectionResetError, ConnectionAbortedError, BrokenPipeError))


def error_text(body: bytes) -> str:
    """What an error answer of Ollama says: the "error" of its JSON (``{"error": "..."}``), else the body as text;
    at most 300 characters."""
    text = body.decode("utf-8", "replace").strip()
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict) and data.get("error"):
        text = str(data["error"]).strip()
    return text[:300]


def http_status_is(error: TranslationError, status: int) -> bool:
    """Whether a request failed with this HTTP status."""
    m = error.message
    return m.code == "ollama.http_error" and m.params.get("status") == status


def refuses_think(error: TranslationError) -> bool:
    """Whether the server refused the request for its "think" option (an older server, or a model without a
    thinking mode): an HTTP 400 that says so."""
    return http_status_is(error, 400) and "think" in str(error.message.params.get("detail", "")).lower()


class _Waits:
    """The seconds the requests to the model waited for their first byte in a row, none coming (`NoAnswer`): the time
    while one at least waits for its first byte, over every request since the last byte of any - a reader who turns
    every few seconds cancels each request before its own bound, and the server that takes them and answers none is
    found all the same -, the time with none waiting not counted. Back to nothing at any byte of any request to the
    model (a load's too), any answer, a request ended as no answer and a server started again. One for a translator,
    shared by its threads; a look at /api/ps is no request to the model and changes nothing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._banked = 0.0  # the seconds of the requests that ended without a byte since the last byte
        self._since: float | None = None  # since when one request at least waits for its first byte
        self._waiting = 0  # the requests waiting for their first byte

    def begin(self) -> None:
        """A request waits for its first byte from now on."""
        with self._lock:
            if self._waiting == 0:
                self._since = time.monotonic()
            self._waiting += 1

    def end(self) -> None:
        """A request that waited for its first byte ended without one (cancelled, failed, ended as no answer)."""
        with self._lock:
            self._waiting = max(0, self._waiting - 1)
            if self._waiting == 0 and self._since is not None:
                self._banked += time.monotonic() - self._since
                self._since = None

    def came(self, first: bool = False) -> None:
        """A byte came, or an answer (*first*: the first byte of a request that waited for it): from nothing again."""
        with self._lock:
            if first:
                self._waiting = max(0, self._waiting - 1)
            self._banked = 0.0
            self._since = time.monotonic() if self._waiting else None

    def clear(self) -> None:
        """The count served (a request ended as no answer, a server started again): from nothing again."""
        self.came()

    def waited(self) -> float:
        """The seconds counted so far."""
        with self._lock:
            return self._banked + (time.monotonic() - self._since if self._since is not None else 0.0)


class _Watch:
    """Reads a streamed answer in short waits: between them it looks at the cancel event, tells once when nothing
    has come for *slow_after* seconds, and gives up (a timeout) after *timeout* seconds without a byte. The no-answer
    bounds (the module's docstring): *first*, the seconds the first byte may take - counted with *waits* over the
    requests in a row that got none (`_Waits`), or this request's alone without -, and *between*, those the stream
    may be silent once it began - past either it raises `NoAnswer` (None: *timeout* alone); *alive* (a load, whose
    first byte comes once the model is in memory): asked every `ALIVE_EVERY_S` while nothing comes whether the server
    answers at all, and silent `ALIVE_MISSES` times in a row, `NoAnswer` (*load*). Its bytes count in *waits* as any
    (`_Waits.came`); `close` once the request ended."""

    def __init__(self, cancel: threading.Event | None, on_slow: Callable[[float], None] | None,
                 slow_after: float, timeout: float, first: float | None = None, between: float | None = None,
                 alive: Callable[[], bool] | None = None, waits: _Waits | None = None):
        self.cancel = cancel
        self.on_slow = on_slow
        self.slow_after = slow_after
        self.timeout = timeout
        self.first, self.between, self.alive = first, between, alive
        self.last = time.monotonic()  # when the request was sent, then when the last bytes came
        self.slow_told = False
        self.began = False  # a byte of the answer came
        self.asked = self.last  # (when *alive* was asked last)
        self.misses = 0
        self.waits = waits
        self.waiting = waits is not None and first is not None  # counted in *waits* until its first byte
        if self.waiting:
            waits.begin()

    def close(self) -> None:
        """The request ended: one that still waited for its first byte is counted no more (`_Waits.end`)."""
        if self.waiting:
            self.waiting = False
            self.waits.end()

    def receive(self, sock: socket.socket, buffer: Any) -> int:
        while True:
            if self.cancel is not None and self.cancel.is_set():
                raise Cancelled()
            try:
                n = sock.recv_into(buffer)
            except TimeoutError:  # a short wait ended without a byte
                now = time.monotonic()
                waited = now - self.last
                if self.began:
                    if self.between is not None and waited >= self.between:
                        raise NoAnswer(waited, True) from None
                elif self.first is not None:
                    # (the count is started again by the incident, `OllamaTranslator._silence`; a request cancelled as
                    # it ends so leaves it as it is, and the next request ends at once)
                    silent = self.waits.waited() if self.waiting else waited
                    if silent >= self.first:
                        raise NoAnswer(silent, False, load=self.alive is not None) from None
                if waited >= self.timeout:
                    raise
                if self.alive is not None and now - self.asked >= ALIVE_EVERY_S:
                    self.misses = 0 if self.alive() else self.misses + 1
                    self.asked = time.monotonic()
                    if self.misses >= ALIVE_MISSES:
                        raise NoAnswer(time.monotonic() - self.last, self.began, ps_silent=True) from None
                if self.on_slow is not None and not self.slow_told and waited >= self.slow_after:
                    self.slow_told = True
                    try:
                        self.on_slow(waited)
                    except Exception:  # noqa: BLE001 - whoever listens must not end the request
                        pass
                continue
            self.last = time.monotonic()
            if n > 0:
                self.began = True
                if self.waits is not None:
                    self.waits.came(self.waiting)
                    self.waiting = False
            return n


class _Reader(io.RawIOBase):
    """The bytes of a response as `_Watch` receives them. It holds the reader http.client opened on the socket,
    so that the socket lives as long as the response (closing this closes that)."""

    def __init__(self, held: Any, sock: socket.socket, watch: _Watch):
        super().__init__()
        self._held = held
        self._sock = sock
        self._watch = watch

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        return self._watch.receive(self._sock, buffer)

    def close(self) -> None:
        if not self.closed:
            try:
                self._held.close()
            finally:
                super().close()


class _Response(http.client.HTTPResponse):
    """An HTTP response read through `_Reader`: cancellable while it waits for every byte, headers included."""

    def __init__(self, sock: socket.socket, *args: Any, watch: _Watch, **kwargs: Any):
        super().__init__(sock, *args, **kwargs)
        self.fp = io.BufferedReader(_Reader(self.fp, sock, watch))


class ItemStream:
    """Follows a JSON reply piece by piece as the model writes it and hands every object that is an element of a
    list to *on_object*(object, position) the moment its closing brace arrives: {"translations": [{"id": 1, "text":
    ...}, ...]} gives up its translations one by one. Strings are followed (braces, brackets and escaped quotes in
    them change nothing), a reasoning block (<think>...</think>) or a code fence before the JSON is skipped, and
    whatever follows the JSON is ignored, as is everything after a bracket that does not match. A reply that is not
    a list of objects ("1. ...", a list of strings) gives nothing; it is parsed whole at the end in any case."""

    def __init__(self, on_object: Callable[[dict[str, Any], int], None]):
        self.on_object = on_object
        self.reset()

    def reset(self) -> None:
        """Back to before the reply's first piece (the request asked once more: `_start_again`)."""
        self.count = 0  # objects handed over
        self._lead = ""  # what came before the JSON
        self._started = self._done = False
        self._stack: list[str] = []  # the open braces and brackets
        self._in_string = self._escape = False
        self._item: list[str] | None = None  # the text of the object being read, while one is
        self._item_depth = 0  # how many braces and brackets were open around it

    def feed(self, text: str) -> None:
        for ch in text:
            if self._done:
                return
            if not self._started and not self._begins(ch):
                continue
            self._step(ch)

    def _begins(self, ch: str) -> bool:
        """Before the JSON: whether *ch* opens it (not inside a reasoning block)."""
        if ch in "{[":
            lead = self._lead.lstrip()
            if not lead.startswith("<think>") or "</think>" in lead:
                self._started = True
                self._lead = ""
                return True
        self._lead += ch
        return False

    def _step(self, ch: str) -> None:
        if self._item is not None:
            self._item.append(ch)
        if self._in_string:
            if self._escape:
                self._escape = False
            elif ch == "\\":
                self._escape = True
            elif ch == '"':
                self._in_string = False
            return
        if ch == '"':
            self._in_string = True
        elif ch in "{[":
            if ch == "{" and self._item is None and self._stack and self._stack[-1] == "[":
                self._item = [ch]
                self._item_depth = len(self._stack)
            self._stack.append(ch)
        elif ch in "}]":
            if not self._stack or self._stack[-1] != ("{" if ch == "}" else "["):
                self._done = True  # not the JSON it looked like: nothing more from this reply
                return
            self._stack.pop()
            if self._item is not None and len(self._stack) == self._item_depth:
                text, self._item = "".join(self._item), None
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    obj = None
                if isinstance(obj, dict):
                    self.on_object(obj, self.count)
                    self.count += 1
            if not self._stack:
                self._done = True


def item_of(obj: dict[str, Any], pos: int, count: int) -> tuple[int, str] | None:
    """(index, text) of one object of a translations list - its "id" (else its place) and its "text" - as the whole
    reply is read by `parse_translations`; None when it is not one of the *count* bubbles."""
    try:
        idx = int(obj.get("id", pos + 1)) - 1
    except (TypeError, ValueError):
        idx = pos
    value = obj.get("text", obj.get("en", obj.get("translation", "")))
    if 0 <= idx < count and isinstance(value, str):
        return idx, value.strip()
    return None


def _unwrap(content: str) -> str:
    """A reply without the reasoning block and the code fence a model may put around its JSON."""
    text = _THINK_RE.sub("", content).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    return text


def drop_trailing_commas(text: str) -> str:
    """*text* without the commas that stand right before a closing bracket or brace (``[1, 2,]``), outside
    strings: the one slip that keeps a list a model wrote by hand from being JSON."""
    out: list[str] = []
    in_string = escape = False
    comma = -1  # where in *out* a comma stands that only whitespace has followed so far
    for ch in text:
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch in "]}":
            if comma >= 0:
                del out[comma]
            comma = -1
        elif ch == ",":
            comma = len(out)
        elif ch == '"':
            in_string = True
            comma = -1
        elif not ch.isspace():
            comma = -1
        out.append(ch)
    return "".join(out)


def _json_values(text: str) -> Iterator[Any]:
    """The JSON values *text* may hold, the likeliest first: the whole text (as it is, else with the commas before
    a closing bracket dropped), then every object or list that reads from where it opens (past a stray prefix,
    before a stray suffix), in order."""
    candidates = list(dict.fromkeys((text, drop_trailing_commas(text))))
    for candidate in candidates:
        try:
            yield json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue
    decoder = json.JSONDecoder()
    for candidate in candidates:
        failures = 0
        for m in re.finditer(r"[\[{]", candidate):
            try:
                value, _end = decoder.raw_decode(candidate, m.start())
            except json.JSONDecodeError:
                failures += 1
                if failures > 50:  # not JSON at all: no point in reading it from every bracket
                    break
                continue
            yield value


TEXT_KEYS = ("text", "en", "translation", "english", "translated", "output")  # where an item's translation may be
_NOT_TEXT_KEYS = frozenset({"id", "ja", "jp", "jpn", "japanese", "source", "src", "original", "source_text",
                            "original_text", "japanese_text", "note", "speaker", "kind", "room", "use", "continues"})


def _numbered(data: dict[str, Any]) -> list[Any]:
    """The items of an object keyed by number ({"1": "Hello", "2": "Bye"}, or objects under the numbers); [] when
    it is not one."""
    if not data or not all(str(k).strip().isdigit() for k in data):
        return []
    items: list[Any] = []
    for k, v in data.items():
        if isinstance(v, str):
            items.append({"id": int(str(k).strip()), "text": v})
        elif isinstance(v, dict):
            items.append({**v, "id": int(str(k).strip())})
    return items


def find_items(data: Any, depth: int = 0) -> list[Any]:
    """The list of translations in a reply's JSON: {"translations": [...]} as asked for; also a bare list, a list
    under "items" or under the one key of an object ({"result": [...]}), the same one level down
    ({"data": {"translations": [...]}}), and objects keyed by number. [] when there is none."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict) or depth > 2:
        return []
    for key in ("translations", "items"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return value
        if isinstance(value, dict) and value:
            return _numbered(value) or find_items(value, depth + 1)
    numbered = _numbered(data)
    if numbered:
        return numbered
    if len(data) == 1:
        (value,) = data.values()
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return find_items(value, depth + 1)
    return []


def _text_of(item: dict[str, Any]) -> Any:
    """An item's translation: under "text" (or another key a model uses for it), else its one string that is not
    the id, the Japanese or a fact about the bubble; None when it has none."""
    for key in TEXT_KEYS:
        if key in item:
            return item[key]
    rest = [v for k, v in item.items() if str(k).lower() not in _NOT_TEXT_KEYS and isinstance(v, str)]
    return rest[0] if len(rest) == 1 else None


def _entries(items: Sequence[Any]) -> list[tuple[int | None, Any, Any]]:
    """(id or None, translation, note) of every item that is an object or a string, in the reply's order. An
    object with one numbered key ({"3": "Hello"}) is the item of that id."""
    out: list[tuple[int | None, Any, Any]] = []
    for item in items:
        if isinstance(item, str):
            out.append((None, item, ""))
            continue
        if not isinstance(item, dict):
            continue
        if "id" not in item and len(item) == 1 and str(next(iter(item))).strip().isdigit():
            (key, value), = item.items()
            note = value.get("note", "") if isinstance(value, dict) else ""
            out.append((int(str(key).strip()), _text_of(value) if isinstance(value, dict) else value, note))
            continue
        try:
            ident: int | None = int(item["id"]) if "id" in item else None
        except (TypeError, ValueError):
            ident = None
        out.append((ident, _text_of(item), item.get("note", "")))
    return out


def place_entries(entries: Sequence[tuple[int | None, Any, Any]], count: int) -> list[tuple[int, Any, Any]]:
    """(index, translation, note) of the entries that belong to one of the *count* inputs.

    The ids decide, as they were asked for (1 to *count*); an entry without one takes its place in the reply. Ids
    numbered from 0, or running on from elsewhere (one entry per input, in a row), are moved back to 1 to
    *count*. Where an id comes twice, the first entry has it: the second is most often the next line under a
    wrong number, and a line left without a translation is asked for again, a wrong one would stay."""
    ids = [e[0] for e in entries if e[0] is not None]
    unique = len(set(ids)) == len(ids)
    shift = 0
    if ids and unique and not all(1 <= i <= count for i in ids):
        low, high = min(ids), max(ids)
        if low == 0 and high < count:
            shift = 1  # numbered from 0
        elif high - low + 1 == len(ids) == len(entries) == count:
            shift = 1 - low  # one entry per input, numbered on from somewhere else
    placed: list[tuple[int, Any, Any]] = []
    taken: set[int] = set()
    for pos, (ident, value, note) in enumerate(entries):
        idx = pos if ident is None else ident + shift - 1
        if 0 <= idx < count and idx not in taken:
            taken.add(idx)
            placed.append((idx, value, note))
    return placed


def _list_objects(text: str) -> list[dict[str, Any]]:
    """Every complete object that is an element of a list in *text*, in order (`ItemStream`): what is left of a
    reply cut off by the output cap, or broken further on."""
    got: list[dict[str, Any]] = []
    ItemStream(lambda obj, _pos: got.append(obj)).feed(text)
    return got


def reply_items(content: str) -> list[Any]:
    """The list of translations in a reply, read as leniently as is safe: JSON as asked for, past a reasoning
    block, a code fence, a stray prefix or suffix, with a trailing comma, wrapped in another object or keyed by
    number (`find_items`); else the complete objects of a list cut off (`_list_objects`), or the objects with an
    id and a text that stand on their own (one per line, say). [] when nothing reads."""
    text = _unwrap(content)
    loose: list[dict[str, Any]] = []
    for value in _json_values(text):
        items = find_items(value)
        if items and any(isinstance(it, (dict, str)) for it in items):
            return items
        if isinstance(value, dict) and "id" in value and _text_of(value) is not None:
            loose.append(value)
    listed = _list_objects(text)
    return listed if len(listed) >= len(loose) else loose


def parse_translations(content: str, count: int) -> list[str]:
    """The translations of the model's JSON reply, mapped back onto the input ids (`reply_items`, `place_entries`);
    tolerates sloppy output."""
    out = [""] * count
    placed = place_entries(_entries(reply_items(content)), count)
    for idx, value, _note in placed:
        if isinstance(value, str):
            out[idx] = value.strip()
    if not placed:  # last resort: "1. text" / "1: text" lines
        for m in re.finditer(r"^\s*(\d+)\s*[.:)]\s*(.+)$", _unwrap(content), re.M):
            idx = int(m.group(1)) - 1
            if 0 <= idx < count and not out[idx]:
                out[idx] = m.group(2).strip()
    return out
