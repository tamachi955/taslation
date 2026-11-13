"""Translation through a local Ollama server.

The only network peer TASlation ever has. The client refuses any URL whose
host is not a loopback address, builds its own ``urllib`` opener with proxies
disabled, and the network guard independently blocks everything else.

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

The model is in GPU memory only while it is needed. Nothing loads it at the start:
the first request that wants it does (`OllamaTranslator.ensure_loaded`, from every
request to the model): /api/ps says whether it is loaded (a page in the cache sends no
request, so reading the cache never loads it); when it is not, the reader is told
(`on_status`), the pipeline's GPU models let go (`before_load`, which is
`Pipeline.release_gpu_models`) and `warm_up` loads it under its own timeout,
cancellable like a request. Every request carries ``keep_alive`` (the setting
``ollama_keep_alive``, in Ollama's own format: `keep_alive_value`): how long Ollama
keeps the model after it, so the pages that go on needing it keep it, and it goes by
itself after that; nothing asks for it periodically. `release` unloads it at once: the
end of a whole-book run or a command, the window's close. ``"-1"`` (never unload) is
the one setting that keeps the old way: loaded at the start, before the OCR model,
and never released (`never_unloads`).

A load is checked afterwards: a model that came up partly on the CPU (`gpu_share`) is
unloaded and loaded once more after the GPU models are let go; if that does not help
the reader is told (``ollama.partly_on_gpu``). What else holds GPU memory did not
change Ollama's share when measured (Windows, Ollama 0.40, a card of 6 GB): the model
came up whole next to 4.8 GB held by torch, idle, or 4 GB in constant use, with
Ollama reading 5.0 GB free throughout, since the driver moves the others' memory
aside. A model that does land partly on the CPU translates 4 times slower (14.5
against 63 tokens/s at 55 %). So the check is a net, for a card or a system that
behaves otherwise, and letting the GPU models go keeps them from being paged around.
"""

from __future__ import annotations

import functools
import http.client
import io
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Iterator, Sequence
from urllib.parse import urlparse

from ..health import is_default_model, pull_command
from ..messages import Cancelled, Message
from ..netguard import is_loopback_host
from .base import TranslationError

POLL_S = 0.1  # how often a streamed request looks at its cancel event while it waits for the answer
# How long Ollama keeps the model after a request (Settings.ollama_keep_alive). Long enough for a reader on
# untranslated pages, who needs it once or twice a minute, to pay for one load (3.4 s) only, and for a pause of a few
# minutes; short enough that a reader who has gone on to cached pages soon has the GPU memory (3.7 GB) back. It is
# Ollama's own default too.
KEEP_ALIVE = "5m"
WARM_UP_TIMEOUT = 300.0  # seconds a warm-up may take at most: a model loaded from a slow disk
WARM_UP_PROMPT = "Hi"  # what a warm-up asks (one token of answer)
PS_TIMEOUT = 3.0  # seconds /api/ps may take: it only looks
RELEASE_TIMEOUT = 3.0  # seconds a request to unload may take: the end of a run or the window's close wait for it
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


def same_model(name: Any, model: str) -> bool:
    """Whether Ollama's *name* of a model is *model*, which may leave out the tag (":latest")."""
    return str(name) == model or (":" not in model and str(name) == f"{model}:latest")


def loaded_message(model: str, seconds: float) -> Message:
    """What is said once Ollama has *model* loaded (``ollama.loaded``: the warm-up took *seconds*)."""
    return Message("ollama.loaded", model=str(model), seconds=round(float(seconds), 1))


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
        self.target_language = target_language
        self.keep_alive = keep_alive_value(keep_alive)  # every request's keep_alive, as Ollama takes it
        self._supports_think: bool | None = None  # learned from the server on the first request
        # brings Ollama back when a request finds it gone (`taslation.ollama_start.OllamaStarter.revive`): given the
        # request's cancel event, True when it answers again; None: a request that finds it gone fails, as doctor's do
        self.revive: Callable[[threading.Event | None], bool] | None = None
        # called before the model is loaded: what else is in GPU memory goes (`Pipeline.release_gpu_models`)
        self.before_load: Callable[[], Any] | None = None
        # told about a load as a Message: ``ollama.loading``, ``ollama.loaded``, ``ollama.partly_on_gpu``
        self.on_status: Callable[[Message], Any] | None = None
        self._used: set[str] = set()  # the models this translator had Ollama load or use (what `release` unloads)
        self.last_stats: dict[str, Any] = {}
        # the known model (`models.TranslatorModel`) the target language chose for this translator (`make_translator`
        # with ``ollama_model = "auto"``), None for a model set by hand: a model Ollama lacks is then said as
        # ``translator.model_missing``, the language's model to install
        self.auto_model: Any = None
        # No proxies, ever: a system proxy must never see the text of your books.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

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
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                body = resp.read()
        except (OSError, http.client.HTTPException) as e:
            raise self._failure(e, path, timeout or self.timeout) from e
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise TranslationError(Message("ollama.bad_json", path=path)) from e

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
                timeout: float | None = None) -> dict[str, Any]:
        """`_stream_once`; when it finds Ollama gone, sent once more after `_revived` (which *cancel* interrupts)."""
        try:
            return self._stream_once(path, payload, on_text, cancel, on_slow, timeout)
        except TranslationError as e:
            if not self._revived(e, cancel):
                if cancel is not None and cancel.is_set():
                    raise Cancelled() from e
                raise
        return self._stream_once(path, payload, on_text, cancel, on_slow, timeout)

    def _stream_once(self, path: str, payload: dict[str, Any], on_text: Callable[[str], None],
                     cancel: threading.Event | None = None, on_slow: Callable[[float], None] | None = None,
                     timeout: float | None = None) -> dict[str, Any]:
        """POST *payload* (``stream: true``) and read the answer as Ollama sends it, one JSON object per line,
        handing every piece of the message to *on_text* as it arrives. Returns the last object (the statistics)
        with the whole message in it. An answer that breaks off before its last object is an error, as a cut-off
        answer is in one piece.

        The answer is waited for in steps of ``POLL_S``: once *cancel* is set the connection is closed and
        `Cancelled` raised; *on_slow*(seconds) is called once when nothing has come for ``slow_after`` seconds; it
        gives up after *timeout* (default: the translator's) seconds without a byte.
        No proxy is ever involved (the connection goes straight to the loopback address)."""
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        data = json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/x-ndjson", "Content-Type": "application/json"}
        pieces: list[str] = []
        last: dict[str, Any] | None = None
        timeout = timeout or self.timeout
        watch = _Watch(cancel, on_slow, self.slow_after, timeout)
        conn = self._connection()
        resp: http.client.HTTPResponse | None = None
        try:
            conn.request("POST", self._prefix + path, body=data, headers=headers)
            if conn.sock is not None:
                conn.sock.settimeout(POLL_S)  # the answer is read in short waits (see _Watch)
            conn.response_class = functools.partial(_Response, watch=watch)  # type: ignore[assignment]
            resp = conn.getresponse()
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
        except (OSError, http.client.HTTPException) as e:
            if cancel is not None and cancel.is_set():
                raise Cancelled() from e
            raise self._failure(e, path, timeout) from e
        finally:
            if resp is not None:
                resp.close()
            conn.close()  # on a cancel: the connection goes, and Ollama stops writing
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

    def _chat(self, messages: list[dict[str, str]], fmt: Any, max_tokens: int = 0,
              on_text: Callable[[str], None] | None = None, cancel: threading.Event | None = None,
              on_slow: Callable[[float], None] | None = None) -> str:
        """The model's answer to *messages*; with *on_text*, read as it is written (each piece handed over). With
        *cancel* or *on_slow* the answer is streamed as well, so that it can be cancelled or found slow."""
        self.ensure_loaded(cancel, on_slow)
        self._used.add(self.model)
        stream = on_text is not None or cancel is not None or on_slow is not None
        options: dict[str, Any] = {"temperature": self.temperature}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
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
            if stream:
                return self._stream("/api/chat", payload, on_text or _ignore, cancel, on_slow)
            return self._request("/api/chat", payload)

        try:
            data = send()
        except TranslationError as e:
            if "think" in payload and refuses_think(e):
                self._supports_think = False  # older server or a model without a thinking mode
                payload.pop("think")
                data = send()
            else:
                raise
        self.last_stats = {k: data.get(k) for k in ("prompt_eval_count", "eval_count", "prompt_eval_duration", "eval_duration",
                                                    "total_duration", "done_reason")}
        return str(data.get("message", {}).get("content", ""))

    def _chat_once(self, payload: dict[str, Any], timeout: float | None = None, cancel: threading.Event | None = None,
                   on_slow: Callable[[float], None] | None = None) -> dict[str, Any]:
        """POST *payload* to /api/chat (``think`` off when the server knows it; once it refuses it, never again) and
        return Ollama's answer: in one piece, or streamed when there is a *cancel* or an *on_slow* to serve."""
        if self._supports_think is not False:
            payload["think"] = False

        def send() -> dict[str, Any]:
            if cancel is None and on_slow is None:
                return self._request("/api/chat", payload, timeout)
            return self._stream("/api/chat", {**payload, "stream": True}, _ignore, cancel, on_slow, timeout)

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
        `translate_page`."""
        options: dict[str, Any] = {"num_predict": 1, "temperature": 0}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        payload: dict[str, Any] = {"model": model or self.model,
                                   "messages": [{"role": "user", "content": WARM_UP_PROMPT}], "stream": False,
                                   "options": options,
                                   "keep_alive": self.keep_alive if keep_alive is None else keep_alive_value(keep_alive)}
        self._used.add(payload["model"])
        start = time.monotonic()
        self._chat_once(payload, timeout or min(self.timeout, WARM_UP_TIMEOUT), cancel, on_slow)
        return time.monotonic() - start  # (not last_stats: a warm-up must not stand in for a page's statistics)

    def _loaded(self, model: str) -> dict[str, Any] | None:
        """What Ollama's /api/ps says of *model*, None when it is not loaded. Raises `TranslationError`; never starts
        Ollama."""
        data = self._request_once("/api/ps", timeout=PS_TIMEOUT)
        for entry in data.get("models") or []:
            if isinstance(entry, dict) and same_model(entry.get("name") or entry.get("model"), model):
                return entry
        return None

    def gpu_share(self, model: str | None = None) -> float | None:
        """How much of the loaded *model* (default: the translator's) is in GPU memory: ``size_vram`` / ``size`` of
        /api/ps, 1.0 for all of it. None when that cannot be told (not loaded, or Ollama does not say)."""
        try:
            entry = self._loaded(model or self.model)
        except TranslationError:
            return None
        if entry is None or not entry.get("size") or entry.get("size_vram") is None:
            return None
        return float(entry["size_vram"]) / float(entry["size"])

    def _say(self, message: Message) -> None:
        if self.on_status is not None:
            try:
                self.on_status(message)
            except Exception:  # noqa: BLE001 - whoever listens must not end the request
                pass

    def _free_gpu(self) -> None:
        """What else is in GPU memory goes (`before_load`)."""
        if self.before_load is not None:
            try:
                self.before_load()
            except Exception:  # noqa: BLE001 - a model that stays must not end the request
                pass

    def ensure_loaded(self, cancel: threading.Event | None = None,
                      on_slow: Callable[[float], None] | None = None) -> None:
        """The model in memory before a request is sent (see the module's docstring). Nothing happens when it is
        loaded, when ``keep_alive`` would unload it right away, or when /api/ps does not answer: the request then goes
        out as it always did, and says what is wrong itself (and starts Ollama). A load that fails raises what the
        request would have raised; Stop raises `Cancelled`."""
        model = self.model
        if unloads_at_once(self.keep_alive):
            return
        try:
            if self._loaded(model) is not None:
                return
        except TranslationError:
            return
        self._say(Message("ollama.loading", model=model))
        self._free_gpu()
        seconds = self.warm_up(model, timeout=WARM_UP_TIMEOUT, cancel=cancel, on_slow=on_slow)
        share = self.gpu_share(model)
        if partly_on_gpu(share):
            self.release(model, wait=True)
            self._free_gpu()
            seconds += self.warm_up(model, timeout=WARM_UP_TIMEOUT, cancel=cancel, on_slow=on_slow)
            share = self.gpu_share(model)
        self._say(loaded_message(model, seconds))
        if partly_on_gpu(share):
            self._say(Message("ollama.partly_on_gpu", model=model, percent=round(float(share or 0) * 100)))

    def release(self, model: str | None = None, wait: bool = False) -> None:
        """Ollama unloads *model* now (default: the models this translator had it load or use; with none, nothing is
        sent, so that a session that read only cached pages leaves another program's model alone). With *wait*, until
        it is gone. Never with a ``keep_alive`` that keeps the model for good. Never raises: Ollama down holds nothing,
        and Ollama's own ``keep_alive`` ends what a request here could not. Starts nothing."""
        if never_unloads(self.keep_alive):
            return
        for name in [model] if model else sorted(self._used):
            self._used.discard(name)
            try:
                self._unload(name)
                end = time.monotonic() + RELEASE_WAIT_S
                while wait and self._loaded(name) is not None and time.monotonic() < end:
                    time.sleep(POLL_S)
            except TranslationError:
                continue

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


class _Watch:
    """Reads a streamed answer in short waits: between them it looks at the cancel event, tells once when nothing
    has come for *slow_after* seconds, and gives up (a timeout) after *timeout* seconds without a byte."""

    def __init__(self, cancel: threading.Event | None, on_slow: Callable[[float], None] | None,
                 slow_after: float, timeout: float):
        self.cancel = cancel
        self.on_slow = on_slow
        self.slow_after = slow_after
        self.timeout = timeout
        self.last = time.monotonic()  # when the request was sent, then when the last bytes came
        self.slow_told = False

    def receive(self, sock: socket.socket, buffer: Any) -> int:
        while True:
            if self.cancel is not None and self.cancel.is_set():
                raise Cancelled()
            try:
                n = sock.recv_into(buffer)
            except TimeoutError:  # a short wait ended without a byte
                waited = time.monotonic() - self.last
                if waited >= self.timeout:
                    raise
                if self.on_slow is not None and not self.slow_told and waited >= self.slow_after:
                    self.slow_told = True
                    try:
                        self.on_slow(waited)
                    except Exception:  # noqa: BLE001 - whoever listens must not end the request
                        pass
                continue
            self.last = time.monotonic()
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
