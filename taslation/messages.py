"""Messages: what TASlation's working parts tell the reader, as a stable code and its parameters.

Everything the batch, the pipeline, the OCR engine, the translator, the window capture and the health checks
say - a status line, the reason a batch ended, an error - is a `Message`: a dotted, stable *code* (for example
``batch.scanning_page``) and its *params* (plain numbers and short strings: page counts, seconds, a window
title, a model name, a URL, a key name; never the text of a book). A param may itself be a `Message` (the
error that made a request fail, the reason a batch ended).

The contract, for a window or anything else that shows them:

* ``message.code`` names what is said; ``PARAMS[code]`` lists the params its producers always supply (the
  registry; tests check that every code the package produces is registered and that each producer supplies
  exactly those params). ``message.params`` is a read-only mapping.
* A window maps ``code`` to a template of its own (same placeholders, in its language) and formats it with
  the params; `render` does exactly that for a catalog ``{code: template}``, the English template wherever the
  catalog has none, nested Messages rendered with the same catalog.
* Some codes are followed by a second sentence when one of their params is set (non-zero, non-empty):
  ``FOLLOW_UPS[code]`` lists (param, follow-up code) pairs; the follow-up takes its params from the message.
  `Message.sentences` gives the message and its follow-ups; each is rendered with its own code's template
  and they are joined with `JOINER`. `render` does that too.
* ``str(message)`` is the English text: ``TEMPLATES[code]`` formatted with the params, with its follow-ups.
  `Message` is a ``str`` subclass holding that text, so code that knows nothing of codes (today's window,
  the CLI, a log line) uses it as the string it always got.

Templates use ``str.format`` fields. Two additions: a format spec with a bar, ``{n:entry|entries}``, renders the
number and the singular or plural word ("1 entry", "3 entries"); a missing param or one of the wrong type never
raises (the field is shown as it is), so a message can never break the work it reports on.
"""

from __future__ import annotations

import string
import types
from typing import Any, Mapping

JOINER = " - "  # between a message and its follow-ups

# --- the registry ----------------------------------------------------------------------------------------
# code -> the params its producers always supply. Grouped by producer: batch.py, capture, pipeline.py,
# translate/ollama.py, translate/base.py, ocr/charspot.py, health.py.
PARAMS: dict[str, tuple[str, ...]] = {
    # batch: progress
    "batch.started": ("problems", "problem"),
    "batch.preflight_problems": ("problems", "problem"),
    "batch.not_started": ("reason",),
    "batch.book_back": (),
    "batch.waiting_other_tab": ("title",),
    "batch.viewer_draws_again": (),
    "batch.waiting_covered": (),
    "batch.waiting_behind": (),
    "batch.waiting_viewer_hidden": (),
    "batch.not_book": (),
    "batch.backlog_full": ("queued",),
    "batch.backlog_room": (),
    "batch.page_missed": ("pages",),
    "batch.missed_taken": (),
    "batch.note_missed": ("pages",),
    "batch.page_waits": ("queued",),
    "batch.finishing": ("queued",),
    "batch.erasing_ahead": ("pages",),
    "batch.finished_reading": (),
    "batch.read_so_far": (),
    "batch.viewer_lost": ("error",),
    "batch.waiting_capture": ("error",),
    "batch.viewer_loading": (),
    "batch.translating_page": ("page",),
    "batch.translated_page": ("page", "bubbles", "seconds", "error"),
    "batch.page_error": ("error",),
    "batch.scanning_page": ("page",),
    "batch.stale_dropped": ("dropped",),
    "batch.read_page": ("page", "lines", "pages", "bubbles", "cached", "seconds", "dropped"),
    "batch.page_cached": ("page", "lines", "seconds", "dropped"),
    "batch.pages_read": ("pages", "bubbles"),
    "batch.continuing": ("lines",),
    "batch.translating_chunk": ("chunk", "chunks", "bubbles"),
    "batch.translated_chunk": ("chunk", "chunks", "bubbles", "seconds"),
    # batch: how it ended (BatchProgress.summary, the last message)
    "batch.finished": ("pages", "bubbles", "seconds", "minutes", "failed", "error", "reason"),
    "batch.failures": ("failed", "error"),
    "batch.failed_requests": ("failed", "reason", "pages", "seconds"),
    "batch.stopped": ("page", "pages", "bubbles", "seconds"),
    # batch: why it ended (BatchProgress.reason)
    "batch.no_page_seen": (),
    "batch.page_limit": ("limit",),
    "batch.user_stop": (),
    "batch.stopped_reading": ("pages", "seconds", "kept", "again"),
    "batch.readings_kept": (),
    "batch.read_again": ("pages",),
    "batch.stopped_translating": ("done", "total", "pages", "seconds", "kept", "again"),
    "batch.continues_translating": (),
    "batch.stored_read_again": ("pages",),
    "batch.viewer_black": (),
    "batch.locked": ("pid",),
    "batch.nothing_new": ("reason",),
    "batch.scan_ended": (),
    "batch.save_failed": ("error",),
    "batch.reply_unusable": (),
    # batch: notes (BatchProgress.notes)
    "batch.note_gave_up": ("units",),
    "batch.note_retry_failed": ("bubbles", "error"),
    "batch.note_retry_unusable": ("bubbles",),
    "batch.note_unit_failed": ("unit", "error"),
    "batch.note_incomplete": ("incomplete", "units"),
    "batch.note_unit_incomplete": ("unit",),
    "batch.note_pruned": ("bubbles",),
    # window capture (CaptureError.message)
    "viewer.covered": (),
    "viewer.closed": (),
    "viewer.gone": (),
    "viewer.no_area": (),
    "viewer.windows_only": (),
    "viewer.unknown_key": ("key",),
    "viewer.api_failed": ("call",),
    "viewer.window_api_failed": ("call", "hwnd"),
    "viewer.empty_rect": (),
    "viewer.error": ("detail",),
    # pipeline: the stages of a page (the progress callback)
    "pipeline.stage_finding": (),
    "pipeline.stage_reading": ("done", "total"),
    "pipeline.stage_translating": ("bubbles", "translator"),
    "pipeline.stage_rendering": (),
    # pipeline: a page's outcome (PageResult.error, pipeline.summary)
    "pipeline.no_translator": (),
    "pipeline.cancelled": (),
    "pipeline.from_cache": ("bubbles", "seconds", "cached", "new", "review", "error"),
    "pipeline.translated": ("bubbles", "seconds", "cached", "new", "review", "error"),
    "pipeline.to_review": ("review",),
    "pipeline.page_error": ("error",),
    "pipeline.no_content": (),
    "pipeline.no_text": (),
    # the translator (TranslationError.message)
    "ollama.unreachable": ("url",),
    "ollama.model_missing": ("model",),
    "ollama.http_error": ("status", "path", "detail"),
    "ollama.timeout": ("seconds",),
    "ollama.connection_failed": ("url",),
    "ollama.bad_json": ("path",),
    "ollama.reported_error": ("path", "detail"),
    "ollama.broke_off": ("path",),
    "ollama.bad_answer": ("chars",),
    "ollama.not_loopback": ("url",),
    "ollama.slow": ("seconds",),
    "ollama.loaded": ("model", "seconds"),
    "ollama.loading": ("model",),
    "ollama.partly_on_gpu": ("model", "percent"),
    "translator.failed": ("detail",),
    # the model the target language chooses (translate/models.py, health.check, translate/plamo.py)
    "translator.model_missing": ("model", "name", "language"),
    "translator.other_model": ("model", "name", "language", "used"),
    "plamo.cannot_write": ("language",),
    # OCR (ModelNotInstalled.message)
    "ocr.model_missing": ("path",),
    "ocr.error": ("detail",),
    "ocr.one_reader": (),
    "layout.classical": (),
    # health checks (health.check, batch.preflight)
    "health.ollama_down": ("url",),
    "health.ollama_not_installed": (),
    "health.ollama_no_answer": (),
    "health.model_missing": ("model",),
    "health.chosen_model_missing": ("model", "command"),
    "health.ocr_missing": ("path",),
    "health.other_model": ("wanted", "used"),
    "health.chosen_other_model": ("wanted", "used", "command"),
    # a rename refused (RenameRefused.message)
    "rename.unreadable": ("path", "folder"),
    "rename.busy": ("path",),
    "rename.in_way": ("path", "folder"),
    "rename.no_name": (),
    "rename.same_name": ("book",),
}

# code -> its English text; the fallback for a window without a template of its own for the code
TEMPLATES: dict[str, str] = {
    "batch.started": "Whole-book run started",
    "batch.preflight_problems": "before the start {problems:problem was|problems were} found: {problem}",
    "batch.not_started": "Whole-book run not started: {reason}",
    "batch.book_back": "The book is back; carrying on",
    "batch.waiting_other_tab": ("Waiting: the viewer window shows {title!r} now, not the book. Bring the book's tab "
                                "back, or drag that tab out of the browser once so that it has a window of its own; "
                                "TASlation then finds the book while you use other tabs."),
    "batch.viewer_draws_again": "The viewer draws again; carrying on",
    "batch.waiting_covered": "Waiting: the viewer draws nothing behind TASlation; move TASlation aside",
    "batch.waiting_behind": "Waiting: the viewer draws nothing behind another window; move that window aside",
    "batch.waiting_viewer_hidden": "Waiting: the viewer's window is hidden or minimised; bring it back",
    "batch.not_book": "Waiting: this does not look like a page of the book, so it is not read. Go back to the book, or press Finished reading",
    "batch.backlog_full": "Please wait: {queued} pages are waiting to be read. Turn the next page when this line has gone",
    "batch.backlog_room": "Caught up: turn the next page when you like",
    "batch.page_missed": ("A page went by before it could be taken (not taken yet: {pages:page|pages}). Please turn back "
                          "one page; the strip marks which"),
    "batch.missed_taken": "The page that went by is taken now; carry on when you like",
    "batch.note_missed": "{pages:page|pages} went by before they could be taken, so they are not translated",
    "batch.page_waits": "Pages waiting to be read: {queued}",
    "batch.finishing": "Finished reading. Pages still to read: {queued}",
    "batch.erasing_ahead": "Getting the pages read ready to show. Pages still to erase: {pages}",
    "batch.finished_reading": "you finished reading",
    "batch.read_so_far": "you asked for the pages read so far",
    "batch.viewer_lost": "{error}. Finished reading translates what was read; Stop keeps it for the next run in this window",
    "batch.waiting_capture": "Waiting: {error}",
    "batch.viewer_loading": "The viewer is still loading; TASlation is waiting",
    "batch.translating_page": "Page {page}: translating...",
    "batch.translated_page": "Page {page}: {bubbles:line|lines}  [{seconds:.0f}s]",
    "batch.page_error": "{error}",
    "batch.scanning_page": "Scanning page {page}...",
    "batch.stale_dropped": "{dropped} old line(s) removed",
    "batch.read_page": "Page {page}: {lines:line|lines} read  [{seconds:.0f}s]",
    "batch.page_cached": "Page {page}: {lines:line|lines} translated before  [{seconds:.0f}s]",
    "batch.pages_read": "Every page is read: {pages:screen|screens}, {bubbles:line|lines}. The viewer is no longer needed; the translation comes now...",
    "batch.continuing": "Going on with the pages read earlier: {lines:line|lines} to translate",
    "batch.translating_chunk": "Translating chunk {chunk}/{chunks} ({bubbles:line|lines})...",
    "batch.translated_chunk": "Translated chunk {chunk}/{chunks}: {bubbles:line|lines} so far  [{seconds:.0f}s]",
    "batch.finished": "Whole-book scan done: {pages:page|pages}, {bubbles:line|lines} translated in {minutes:minute|minutes} - {reason}.",
    "batch.failures": ("{failed} part(s) could not be translated. They are done when you read those pages, or in the "
                       "next whole-book run."),
    "batch.failed_requests": ("Nothing could be translated: {reason} ({failed:request|requests} failed, "
                              "{pages:page|pages} read). Fix that, then run Read whole book... again."),
    "batch.stopped": ("Whole-book scan stopped at page {page}. The rest is translated page by page as you read; "
                      "Read whole book... scans again."),
    "batch.no_page_seen": ("no page of the book could be seen in the viewer; check that the book is on show, then start "
                           "again"),
    "batch.page_limit": "reached the page limit ({limit})",
    "batch.user_stop": "stopped",
    "batch.stopped_reading": "Stopped after reading {pages:page|pages}. Nothing is translated yet: the translation comes after Finished reading.",
    "batch.readings_kept": "Read whole book... goes on from the page on show, until you close TASlation.",
    "batch.read_again": "Those pages are read again next time: go back {pages:page|pages} in the viewer, then run Read whole book... again.",
    "batch.stopped_translating": "Stopped: {done} of {total} lines are translated and stored, and stay.",
    "batch.continues_translating": "Read whole book... translates the rest, until you close TASlation.",
    "batch.stored_read_again": "The rest needs reading again: go back {pages:page|pages} in the viewer, then run Read whole book... again; the pages translated are skipped.",
    "batch.viewer_black": "Waiting: the viewer shows nothing. Reload the book in its own window: click the book, then press its reload key (F5 in a browser; in TASlation's window F5 translates instead). TASlation carries on by itself",
    "batch.locked": "Another TASlation window is already reading this book. Close it, then try again.",
    "batch.nothing_new": "nothing new to translate ({reason})",
    "batch.scan_ended": "the scan ended",
    "batch.save_failed": ("stopped because the translations cannot be saved ({error}); free some disk space, or close "
                          "what holds the file, then run it again"),
    "batch.reply_unusable": "the model's reply could not be used",
    "batch.note_gave_up": ("{units} page unit(s) gave up after repeated failures; they are translated when their page "
                           "is read"),
    "batch.note_retry_failed": "request for {bubbles:line|lines} failed ({error}); retrying in two halves",
    "batch.note_retry_unusable": "request for {bubbles:line|lines} came back unusable; retrying in two halves",
    "batch.note_unit_failed": "page unit {unit}: {error}; it is translated when its page is read",
    "batch.note_incomplete": "{incomplete} of {units} page unit(s) came back incomplete; asking again for those",
    "batch.note_unit_incomplete": ("page unit {unit}: incomplete translation; what is missing is translated when its "
                                   "page is read"),
    "batch.note_pruned": "{bubbles} cached line(s) no longer matched a text region and were removed",
    "viewer.covered": ("The viewer stopped drawing because TASlation covers it completely. Un-maximise TASlation, or "
                       "move it so that a strip of the viewer stays visible."),
    "viewer.closed": "the viewer window was closed",
    "viewer.gone": "TASlation cannot see the viewer's window. Check it is open and not minimised.",
    "viewer.no_area": "TASlation cannot see the viewer's window. Check it is open and not minimised.",
    "viewer.windows_only": "window capture is only available on Windows",
    "viewer.unknown_key": "unknown key name: {key!r} (use Left, Right, PageDown, Space, ... or a single letter)",
    "viewer.api_failed": "TASlation cannot see the viewer's window. Check it is open and not minimised.",
    "viewer.window_api_failed": "TASlation cannot see the viewer's window. Check it is open and not minimised.",
    "viewer.empty_rect": "TASlation cannot see the viewer's window. Check it is open and not minimised.",
    "viewer.error": "{detail}",
    "pipeline.stage_finding": "Finding bubbles...",
    "pipeline.stage_reading": "Reading text {done}/{total}...",
    "pipeline.stage_translating": "Translating {bubbles} bubble(s) with {translator}...",
    "pipeline.stage_rendering": "Rendering...",
    "pipeline.no_translator": "no translator configured",
    "pipeline.cancelled": "cancelled",
    "pipeline.from_cache": "{bubbles} line(s) shown from earlier translations.",
    "pipeline.translated": "{bubbles} line(s) translated in {seconds:.0f} s.",
    "pipeline.to_review": "{review} worth a look (Translator role, Review...).",
    "pipeline.page_error": "{error}",
    "pipeline.no_content": "No page found in the viewer. Check the book is open, or use Set area... (Page menu).",
    "pipeline.no_text": "No text on this page.",
    "ollama.unreachable": ("TASlation could not reach the translation program. Press F5 in a moment; it starts it by "
                           "itself."),
    "ollama.model_missing": "The translation model {model} is not installed. Run install.cmd again to install it.",
    "ollama.http_error": "The translation program refused ({status}). Press F5 to try again; if it repeats, restart your PC.",
    "ollama.timeout": "The translation took too long. Press F5 to try again.",
    "ollama.connection_failed": "The translation program stopped answering. Press F5 to try again.",
    "ollama.bad_json": "The translation program gave an answer TASlation could not use. Press F5 to try again.",
    "ollama.reported_error": "The translation program gave an answer TASlation could not use. Press F5 to try again.",
    "ollama.broke_off": "The translation program gave an answer TASlation could not use. Press F5 to try again.",
    "ollama.bad_answer": "The translation program gave an answer TASlation could not use. Press F5 to try again.",
    "ollama.not_loopback": "Ollama URL must be a loopback http(s) address, got {url!r}",
    "ollama.slow": "The translation program is slow to answer (it may still be loading). Stop cancels this page.",
    "ollama.loaded": "Translator ready.",
    "ollama.loading": "Getting the translator ready...",
    "ollama.partly_on_gpu": "Only {percent}% of the translator fits on the graphics card, so translating will be slow. Close other programs that use the graphics card.",
    "translator.failed": "{detail}",
    "translator.model_missing": ("The translation model for this language, {name}, is not installed. Run install.cmd "
                                 "again to install it."),
    "translator.other_model": ("The translation model for this language, {name}, is not installed; translating with "
                               "{used} for now. Run install.cmd again to install {name}."),
    "plamo.cannot_write": ("The model chosen in the settings cannot translate into this language. Remove ollama_model "
                           "from the settings file, and TASlation chooses the right model by itself."),
    "ocr.model_missing": ("The part that reads Japanese is missing. Double-click install.cmd in the TASlation folder. "
                          "Pages already translated still show."),
    "ocr.error": "{detail}",
    "ocr.one_reader": "The Japanese reader is running in its basic form. Double-click install.cmd to read better.",
    "layout.classical": "Lettering on the drawing is looked for in the basic way. Double-click install.cmd to find more of it.",
    "health.ollama_down": ("The translation program is not running, so new pages cannot be translated. TASlation "
                           "tries to start it at the next page; if this stays, restart your PC. Pages already "
                           "translated can still be read."),
    "health.ollama_not_installed": ("The translation program is not installed. Double-click install.cmd in the "
                                    "TASlation folder."),
    "health.ollama_no_answer": ("The translation program did not start. Restart your PC, then open TASlation again. "
                                "Pages already translated can still be read."),
    "health.model_missing": "The translation model {model} is not installed. Run install.cmd again to install it.",
    "health.chosen_model_missing": ("The model {model} chosen in the settings is not installed in Ollama. Run in a "
                                    "terminal: {command}"),
    "health.ocr_missing": ("The part that reads Japanese is missing. Double-click install.cmd in the TASlation folder. "
                           "Pages already translated still show."),
    "health.other_model": ("{wanted} is not installed in Ollama; translating with {used} for now. Run install.cmd "
                           "again to install {wanted}."),
    "health.chosen_other_model": ("{wanted}, chosen in the settings, is not installed in Ollama; translating with "
                                  "{used} for now. To install {wanted}, run in a terminal: {command}"),
    "rename.unreadable": "{path} cannot be read. Move it out of {folder}, then try again.",
    "rename.busy": "{path} cannot be opened now. Close the program that holds it, then try again.",
    "rename.in_way": "{path} is in the way. Move it out of {folder}, then try again.",
    "rename.no_name": "That name names no book; give the book its own name.",
    "rename.same_name": "The book is called {book} already.",
}

# code -> (param, follow-up code): the follow-up's sentence comes after the message when the param is set
FOLLOW_UPS: dict[str, tuple[tuple[str, str], ...]] = {
    "batch.started": (("problems", "batch.preflight_problems"),),
    "batch.translated_page": (("error", "batch.page_error"),),
    "batch.read_page": (("dropped", "batch.stale_dropped"),),
    "batch.page_cached": (("dropped", "batch.stale_dropped"),),
    "batch.finished": (("failed", "batch.failures"),),
    "batch.stopped_reading": (("kept", "batch.readings_kept"), ("again", "batch.read_again")),
    "batch.stopped_translating": (("kept", "batch.continues_translating"), ("again", "batch.stored_read_again")),
    "pipeline.from_cache": (("review", "pipeline.to_review"), ("error", "pipeline.page_error")),
    "pipeline.translated": (("review", "pipeline.to_review"), ("error", "pipeline.page_error")),
}

class _Formatter(string.Formatter):
    """str.format that never raises: a missing field shows as it is, a param of the wrong type for its format
    spec as plain text; ``{n:one|many}`` gives the number and the word; a nested Message is rendered with the
    same catalog."""

    def __init__(self, catalog: Mapping[str, str] | None):
        super().__init__()
        self.catalog = catalog

    def get_value(self, key: Any, args: Any, kwargs: Mapping[str, Any]) -> Any:
        if isinstance(key, str) and key in kwargs:
            return kwargs[key]
        return _Missing(key)

    def convert_field(self, value: Any, conversion: str | None) -> Any:
        if isinstance(value, _Missing):
            return value
        if isinstance(value, Message):
            value = render(value, self.catalog)
        try:
            return super().convert_field(value, conversion)
        except ValueError:
            return value

    def format_field(self, value: Any, format_spec: str) -> str:
        if isinstance(value, _Missing):
            return "{" + str(value.key) + (":" + format_spec if format_spec else "") + "}"
        if "|" in format_spec:
            one, _, many = format_spec.partition("|")
            return f"{value} {one if value == 1 else many}"
        try:
            return format(value, format_spec)
        except (TypeError, ValueError):
            return str(value)


class _Missing:
    def __init__(self, key: Any):
        self.key = key


def _format(template: str, params: Mapping[str, Any], catalog: Mapping[str, str] | None) -> str:
    try:
        return _Formatter(catalog).vformat(template, (), params)
    except (ValueError, IndexError, KeyError, AttributeError, TypeError):  # a malformed template
        return template


def _own_text(code: str, params: Mapping[str, Any], catalog: Mapping[str, str] | None) -> str:
    """The message's own sentence (without follow-ups): the catalog's template, else the English one."""
    template = (catalog or {}).get(code) or TEMPLATES.get(code)
    if template is None:  # an unknown code: say what there is
        shown = ", ".join(f"{k}={v}" for k, v in params.items())
        return code + (f" ({shown})" if shown else "")
    return _format(template, params, catalog)


def render(message: "Message | str", catalog: Mapping[str, str] | None = None) -> str:
    """*message* in a catalog of templates (code -> template with the same placeholders), the English template
    for every code the catalog lacks, with its follow-ups joined by `JOINER`; a plain string as it is."""
    if not isinstance(message, Message):
        return str(message)
    return JOINER.join(_own_text(s.code, s.params, catalog) for s in message.sentences())


class Message(str):
    """A status line, a reason or an error: a stable dotted *code* and its *params*; as a string, its English
    text (`render` with no catalog). Immutable; equal to a string with the same text."""

    code: str
    params: Mapping[str, Any]

    def __new__(cls, code: str, params: Mapping[str, Any] | None = None, /, **kwargs: Any) -> "Message":
        merged = dict(params or {})
        merged.update(kwargs)
        frozen = types.MappingProxyType(merged)
        text = JOINER.join(_own_text(c, p, None) for c, p in _sentences(code, frozen))
        self = super().__new__(cls, text)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "params", frozen)
        return self

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("a Message cannot be changed")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("a Message cannot be changed")

    def __reduce__(self) -> tuple[Any, ...]:
        return (Message, (self.code, dict(self.params)))

    def __repr__(self) -> str:
        return f"Message({self.code!r}, {dict(self.params)!r})"

    def sentences(self) -> list["Message"]:
        """The message, then the follow-ups whose params are set (`FOLLOW_UPS`): each to be rendered with its own
        code's template and joined with `JOINER`."""
        out: list[Message] = [self]
        for code, params in _sentences(self.code, self.params)[1:]:
            out.append(Message(code, params))
        return out


def _sentences(code: str, params: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    out: list[tuple[str, Mapping[str, Any]]] = [(code, params)]
    for param, follow in FOLLOW_UPS.get(code, ()):
        if params.get(param):
            out.append((follow, {k: params[k] for k in PARAMS.get(follow, ()) if k in params}))
    return out


def as_message(value: Any, code: str) -> Message:
    """*value* when it is a Message already; otherwise a Message of *code* (a ``{detail}`` code) carrying its text,
    so ``str()`` of the result is the text it was given."""
    if isinstance(value, Message):
        return value
    return Message(code, detail="" if value is None else str(value))


def message_of(error: BaseException | str | None, code: str = "translator.failed") -> Message:
    """The Message an exception carries (its ``.message``), a Message as it is, or one of *code* made of the
    text."""
    if isinstance(error, Message):
        return error
    if error is None:
        return Message(code, detail="")
    carried = getattr(error, "message", None)
    if isinstance(carried, Message):
        return carried
    return as_message(str(error), code)


class Cancelled(Exception):
    """The work was cancelled (its ``cancel`` event was set): raised by the pipeline between stages and by a
    translator in the middle of a request. Nothing it was doing reached the cache. Not a TranslationError, so a
    handler of failed requests never takes it for one."""

    def __init__(self, message: Message | str | None = None):
        self.message = message if isinstance(message, Message) else Message("pipeline.cancelled")
        super().__init__(self.message)
