"""The worker thread and its jobs (`_job_*`: every heavy step runs there; Tk only draws), the events they post and
how the window takes them (`_handle_event`), and the requests - Translate (F5), a page Auto found, the batch -
which wait while the models load or a job runs (`_queue`, `_run_queued`).

Around them:

* Ollama started when it does not answer (`taslation.ollama_start`), at the start of the window, before a setup check
  that decides on a whole-book scan, and when a request finds it gone (`_revive_ollama`). At the start a failure is said
  in a popup, once (the "ollama_failed" event); the window stays usable, and the banner says what stands. An Ollama
  the window started is stopped once the window has closed (`run_app`), unless another TASlation or another program
  still uses it;
* Ollama's model in memory only while pages need it (`taslation.translate.ollama`): the first page that needs it loads
  it, which the status line and the badge say (`_model_status`); the window's close releases it (`_release_model`);
* the setup checks: `health.check` at the start and, while a problem stands, every `HEALTH_RECHECK_MS` in a thread
  of their own (never on the Tk thread); the setup banner shows what they find and loses a line by itself once it is
  fixed (`_set_health`);
* the start of a book (`_begin_book`, from Auto's first page of a book not in its cache): in whole-book mode the
  setup is checked first (`batch.preflight`, in the worker) - with a problem nothing is scanned and the window goes
  on page by page - then the start dialog asks for the book's name (when the window's title gives none) and whether
  to read the whole book first; a whole-book scan checks the setup once more right before it reads the first page
  (`_job_batch`). Whole-book mode here is the `scan_mode` setting (`gui --mode book`): the window has no choice of
  it, and page by page is what Auto and F5 do; the batch's dialog starts a whole-book scan by hand;
* the book's name: a Book box that names no book (`bookid.generic_book_name`: a viewer's name, a browser, nothing) never
  reaches a store - `_ensure_cache` opens none for it, and F5, the batch's Start, Series sheet... and Book
  settings... ask for the name first (`_ask_name`); the start dialog offers the books whose caches hold the
  page on screen (`bookid.recognise`, looked for in the worker: `_recognise_then`; the dialog opens once they are
  known), and the colophon of the book, found on a page with no text to
  translate (`_look_for_colophon`) or by the whole-book scan (`BatchProgress.colophon`), offers its name once
  (`_offer_colophon`; with files kept under the book's name, Use renames them: `_plan_rename`, where the book's
  series sheet says otherwise than the sheet of the new name's series the review asks first, `RenameReviewDialog`,
  then `_rename_book`) and leaves its details in the cache's header;
* the scan band while a scan runs and after it (`ScanState`), with Stop: a whole-book run that holds more than
  `FEW_PAGES` pages asks first, and Esc in a run always does (`_ask_stop`, `dialogs.stop`: Keep reading, Stop
  without translating, Translate the pages read), and a stopped run's readings are translated from the band
  (`translate_readings`);
* a page translation that Stop and Esc cancel (`Pipeline.process(cancel=...)`; nothing of it is cached), that a new
  page Auto sees meanwhile cancels and replaces (`_watch_page`), and whose silent model turns the badge to say so
  (``on_slow``);
* a book's stores whose file exists but cannot be opened now (locked, no permission, another book's): said in the
  status line, and the page or the scan that needed them reads nothing (`_ensure_cache`)."""

from __future__ import annotations

import itertools
import logging
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Any, Callable, NamedTuple

import numpy as np
from PIL import Image

from .. import health, viewerparts
from ..batch import BatchProgress, BatchReader, Readings, frames_differ, preflight, thumbnail
from ..bookid import generic_book_name, identity_of, recognise, same_book_name
from ..cache import CacheStore, language_key
from ..capture import IS_WINDOWS, CaptureError, WindowInfo, is_black
from ..colophon import MAX_READS as COLOPHON_READS
from ..colophon import Colophon, find_colophon
from ..colophon import precheck as colophon_precheck
from ..i18n import _, load_ui_table, save_ui_entry
from ..messages import Cancelled, Message, message_of
from ..notes import is_temporary_name, series_key
from ..ollama_start import POPUP_CODES, OllamaStarter, count_as_own, own_models
from . import area, name_check
from .attention import tell_run_ended
from .banner import ScanState, blocking, busy_title, group_digits
from .constants import (EVENTS_BUSY_MS, EVENTS_IDLE_MS, QUEUE_RANK, READING_NOTE_MS, READY, VIEWER_BLACK,
                        VIEWER_LOADING, VIEWER_RESTORED, in_a_run)
from .dialogs import caches as boxes
from .dialogs.batch import BatchDialog
from .dialogs.rename_review import RenameReviewDialog
from .dialogs.review import review_rows
from .dialogs.start import ColophonOffer, StartDialog
from .dialogs.stop import ask_stop
from .trouble import DOWN_CODES, cpu_page_seconds, ollama_compute
from .progress import LOADING, SLOW, Filling, asks_model, code_of, progress_line, reads_page, rendered
from .strip import end_follow, hide_strip, new_run
from .viewers import show_minimised

LOG = logging.getLogger(__name__)

HEALTH_RECHECK_MS = 10_000  # while a setup problem stands, it is looked at again this often
# A whole-book run that holds more pages read than this asks before Stop ends it (`JobsMixin.stop_batch`): a few
# pages are turned again in a minute, more may be an hour of reading. Esc never ends a run without asking.
FEW_PAGES = 3
# ui.json: lines a second of the last whole-book translation per model, where the next run's estimate starts
PACE_TABLE = "pace"
PACE_KEPT = 8
# ui.json: the start dialog's answer per book ("start": read it whole; "page": page by page), the latest kept
BOOK_STARTS = "book_starts"
BOOK_STARTS_KEPT = 200
# ui.json: how many saved files this Windows user cannot open here the window last said in a box ("not_here"), so
# that the box comes again only when that number changes (`JobsMixin._tell_not_here`)
SAVED_FILES = "saved_files"


class Recognition(NamedTuple):
    """What recognising the book on screen needs (`JobsMixin._recognition`, taken on the Tk thread; the worker reads
    it in `recognised_books`)."""

    cached: bool  # the cache is on: the caches are looked at
    store: CacheStore
    language: str  # the target language read in
    colophon: Colophon | None  # the colophon found on a page of this book under its generic name
    frames: tuple[Any, ...]  # the captures to fingerprint, each once
    areas: list[tuple[int, int, int, int]]  # the capture areas to fingerprint them in (`bookid.page_groups` adds more)


class Recognising:
    """The start dialog while the book on screen is being recognised in the worker (`JobsMixin._recognise_then`): a
    dialog of the start asks already, and the start's next page waits for it; the dialog itself opens once the
    books are known."""


def recognised_books(request: Recognition) -> tuple[list[str], str]:
    """The books *request* finds, and how: the one book whose cache header has the colophon's ISBN ("colophon");
    else the books whose caches hold a page of *request*'s frames (`bookid.recognise`, best first: "recognised", or
    "several"), those with the colophon's ISBN first; ([], "") for none. The heavy part of recognising a book (the
    frames fingerprinted in every area, every cache's pages looked through), safe in the worker: it reads only
    *request* and the caches' files (`CacheStore.identities`). A store that cannot be read recognises nothing."""
    found = request.colophon
    try:
        by_isbn = [m.book for m in recognise(request.store, [], request.language, isbn=found.isbn)] \
            if found is not None and found.isbn else []
        if len(by_isbn) == 1:
            return by_isbn, "colophon"
        names = by_isbn or [m.book for m in recognise(request.store, list(request.frames), request.language,
                                                      margins=request.areas)]
    except Exception:  # noqa: BLE001 - a store that cannot be read recognises nothing; the name is typed
        names = []
    if not names:
        return [], ""
    return names, ("several" if len(names) > 1 else "recognised")


WARNING_NOTE_MS = 3 * READING_NOTE_MS  # how long a warning stays on the page over the book (`JobsMixin._warn_unasked`)


def pump_soon(window: Any) -> None:
    """A job has started: *window*'s worker events are looked at EVENTS_BUSY_MS from now, not at the idle pace
    (`JobsMixin._poll_events`)."""
    job = getattr(window, "_events_job", None)
    if job is None:
        return
    try:
        window.after_cancel(job)
    except tk.TclError:
        pass
    window._events_job = window.after(EVENTS_BUSY_MS, window._poll_events)


class JobsMixin:
    """The worker, its events and the requests. A part of `app.App` (no `__init__`: the state it uses is made by
    `App.__init__` and `_init_flow_state`; the other parts are reached through ``self``)."""

    def _init_flow_state(self) -> None:
        """The state of the setup checks, a book's start, the scan band and a page translation that can be cancelled
        (made by `App.__init__`, and by a test's stand-in)."""
        self._ollama: OllamaStarter | None = None  # starts Ollama when it does not answer (made by `_job_init`)
        self._before_loading: Any = None  # what the page was doing when Ollama's model began to load
        self._partial_said = False  # the popup about a model partly on the CPU was shown (once a session)
        self._health: list[Any] = []  # the setup's problems and notices on show (health.check's Messages)
        self._health_after: str | None = None  # the next look at them while one stands
        self._health_checking = False  # a check runs (in a thread of its own)
        self._scan_held = False  # a whole-book scan waits for the setup (the banner says so after the problems)
        self._ocr_loading = False  # the OCR model, missing at the start and there now, is loaded
        self._ocr_failed = False  # the OCR model is there and could not be loaded: not tried again by itself
        self._checks: dict[int, Callable[[list[Any]], None]] = {}  # pre-flight checks under way -> what follows
        self._check_ids = itertools.count(1)
        # books being recognised in the worker (`_recognise_then`) -> what was asked and what follows
        self._recognising: dict[int, tuple[Recognition, Callable[[list[str], str], None]]] = {}
        self._start_pending: tuple[Image.Image, np.ndarray | None] | None = None  # a book's start is under way
        self._start_dialog: Any = None  # the start dialog on show (a book's start, or a name asked for: `_ask_name`)
        self._start_first: Image.Image | None = None  # the frame a book's start began with (the later one waits)
        self._start_whole: bool | None = None  # a book's start that waits for the name being asked for (whole-book?)
        self._scanned_book = ""  # the book _book_scanned was decided for
        self._batch_for: tuple[str, str, str] = ("", "", "")  # the book, model and language the batch reads
        # (book, model, language) a whole-book run finished reading in this session: it read every region of its
        # pages, so translator mode has nothing left to complete on one the cache holds whole (`_all_cached`)
        self._run_read: tuple[str, str, str] = ("", "", "")
        self._colophon_found: tuple[str, str, str, Colophon] | None = None  # (book, model, language, colophon) to offer
        self._colophon_asked: set[str] = set()  # books whose colophon's name was offered (or said) this session
        self._colophon_reads: dict[str, int] = {}  # book -> its pages read in full as a colophon this session (worker)
        self._page_cancel: threading.Event | None = None  # the page translation that runs (Stop cancels it)
        self._cancel_why = ""  # "stop" or "page": why it was cancelled
        self._watch_due = 0.0  # when Auto looks at the viewer again while a page is translated ...
        self._watch_candidate: np.ndarray | None = None  # ... and the new page it saw last time
        self._job_area: np.ndarray | None = None  # the capture area's thumbnail of the frame being translated
        self._slow_before: Any = None  # the stage before the model was found slow
        self._busy_signs = False  # the title and the bar say busy (only after BUSY_SIGNS_S)
        self._scan: ScanState | None = None  # the whole-book scan that runs
        # what a whole-book run read and did not store, per (book, model, language): in memory only, for the next run
        self._readings: tuple[tuple[str, str, str], Readings] | None = None
        self._band: dict[str, Any] | None = None  # what the scan band shows (None: nothing)
        self._auto_before_batch: bool | None = None  # Auto before the batch turned it off
        self._batch_stop_asked = False  # Stop pressed before the batch's reader was made
        self._stop_asking = False  # the question before Stop is on show (`_ask_stop`)

    # ------------------------------------------------------------------ worker
    def _post(self, kind: str, **data: Any) -> None:
        self._events.put((kind, data))

    def _worker_loop(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                job()
            except Cancelled:
                pass  # a stop, not a failure: the job has told the window
            except Exception as e:  # noqa: BLE001 - surface anything unexpected in the UI
                carried = getattr(e, "message", None)
                if isinstance(carried, Message):
                    self._post("error", message=carried)
                else:
                    LOG.exception("a job of the window failed")  # (the reader gets what to do; the log what happened)
                    self._post("error", text=_("Something went wrong on this page. Press F5 to try again; if it repeats, restart TASlation."))
            finally:
                self._post("idle")

    def _check_setup(self) -> tuple[list[Message], list[str] | None]:
        """`health.check` of the settings and, when Ollama answers, the models it has (None when it does not)."""
        s = self.settings
        problems = health.check(s, language=getattr(self, "_check_language", "") or None)
        down = any(code_of(m) == "health.ollama_down" for m in problems)
        return problems, None if down else health.installed_models(s.ollama_url)

    def _revive_ollama(self, cancel: threading.Event | None = None) -> bool:
        """A request found Ollama gone (`OllamaTranslator.revive`, in the thread of the request): it is started
        (`OllamaStarter.start`: not more often than that allows). Whether it answers again; when it does not, the banner
        says so from now on, and what asked fails as it always did."""
        if self._ollama.revive(cancel):
            return True
        self._check_in_background()
        return False

    def restart_translator(self) -> None:
        """The banner's Start translator again: Ollama started now (`OllamaStarter`: a starter of its own, so that the
        person's press is not held back by the gap between the window's own tries), in a thread of its own; the setup
        is checked again after it, and the status line says how it went ("translator_restarted")."""
        if getattr(self, "_restarting", False):
            return
        self._restarting = True
        self.say("Starting the translation program...")
        s = self.settings

        def run() -> None:
            try:
                failed = OllamaStarter(s.ollama_url, state_dir=s.state_dir, own=own_models(s)).start()
            except Exception as e:  # noqa: BLE001 - said; the banner stays
                failed = message_of(f"{type(e).__name__}: {e}")
            self._post("translator_restarted", message=failed)
            self._check_in_background()

        threading.Thread(target=run, name="taslation-start-ollama", daemon=True).start()

    def _ollama_back(self) -> None:
        """Before a setup check that decides on a whole-book scan: Ollama, gone since the start, is started first."""
        if self._ollama is not None:
            self._ollama.start()

    def _job_init(self) -> None:
        """The start, in this order: Ollama started when it does not answer (what stands in the way said in a popup,
        once), the setup check (the banner from the start on), then the OCR model. Ollama's model is left for the first
        page that needs it (`OllamaTranslator.ensure_loaded`), unless ``ollama_keep_alive`` keeps it for good: it is
        loaded then, when Ollama runs and has it, before the OCR model and while the OCR's libraries are imported, and
        once ready the status line says what loaded where."""
        from ..ocr import ModelNotInstalled, Readers
        from ..ocr.charspot import import_libraries
        from ..pipeline import Pipeline
        from ..translate import TranslationError
        from ..translate.models import choose, make_translator
        from ..translate.ollama import loaded_message, never_unloads

        s = self.settings
        self._ollama = OllamaStarter(s.ollama_url,
                                     lambda: self._post("status", key="Starting the translation program..."),
                                     state_dir=s.state_dir, own=own_models(s))
        failed = self._ollama.start()
        if failed is not None and failed.code in POPUP_CODES:
            self._post("ollama_failed", message=failed)
        problems, models = self._check_setup()  # the setup banner from the start on (nothing is loaded for it)
        self._post("health", problems=problems)
        # the model the target language needs (or Qwen for a PLaMo not installed yet: `translate.models.choose`); the
        # translator follows the language from here on (`_use_model`)
        chosen = choose(s.ollama_model, s.target_language, models)
        self.translator = make_translator(s, chosen.name)
        self.translator.revive = self._revive_ollama
        self.translator.on_status = lambda message: self._post("model_status", message=message)
        loaded: list[Message] = []  # what loaded where: said once, when the window is ready
        model = chosen.name if models and health.has_model(models, chosen.name) else None
        if model and never_unloads(s.ollama_keep_alive):
            self._post("status", key="Getting the translator ready...")
            importing = threading.Thread(target=import_libraries, name="taslation-import", daemon=True)
            importing.start()
            try:
                loaded.append(loaded_message(model, self.translator.warm_up(model)))
            except TranslationError:
                pass  # the first page's request loads it, or says what is wrong
            importing.join()
        ocr = None
        try:
            self._post("status", key="Getting the Japanese reader ready (the first time takes a few seconds)...")
            ocr = Readers(s.models_dir, s.ocr_threads)
        except ModelNotInstalled as e:
            self._post("error", message=message_of(e, "ocr.error"))
        except Exception as e:  # noqa: BLE001 - said; the window starts all the same, as without the model
            self._ocr_failed = True
            self._post("error", message=message_of(f"{type(e).__name__}: {e}", "ocr.error"), cached_note=True)
        self.pipeline = Pipeline(s, ocr=ocr, translator=self.translator)
        self._warm_page_models()
        if s.cache_enabled:
            try:  # the caches' fingerprints read once here, so that recognising a book later reads only what changed
                self.store.identities()
            except Exception:  # noqa: BLE001 - recognising then reads them itself
                pass
        self._post("models", models=models or [])
        self._post("ready", ocr=ocr is not None)
        self._tell_protection(loaded)  # (after ready: opening each protected file to count takes a moment)
        if not problems or not any(code_of(m) in DOWN_CODES for m in problems):
            self._post("compute", where=ollama_compute())  # the translator on the processor: one line at the start
        if getattr(ocr, "missing", ()):
            loaded.append(Message("ocr.one_reader"))
        if health.page_models_missing(s):
            loaded.append(Message("layout.classical"))
        if loaded:
            self._post("status", text=self._loaded_line(loaded))

    def _tell_protection(self, loaded: list[Message]) -> None:
        """At the start, in the worker: what the window's start did to the saved files with text of a book still in
        plain text (``_protection``, `protect.migrate` in `App.__init__`), for the status line once the window is
        ready (*loaded*), counts only; then how many saved files this Windows user cannot open on this computer
        (`protect.survey`, each protected file opened: a few milliseconds for a cache of 200 pages), which the
        "not_here" event says in a box when that number is new (`_tell_not_here`)."""
        from .. import protect

        done = getattr(self, "_protection", None)
        if done is not None:
            if done.protected:
                loaded.append(Message("store.protected", files=done.protected))
            if done.plain or done.unreadable:
                loaded.append(Message("store.not_protected", files=done.plain + done.unreadable))
        if not protect.available():
            return
        try:
            found = protect.survey(self.settings.state_dir)
            told = load_ui_table(self.settings.state_dir, SAVED_FILES).get("not_here")
        except Exception as e:  # noqa: BLE001 - a store that opens such a file says so itself (`_watch_set_aside`)
            LOG.warning("the saved files could not be looked at: %s", type(e).__name__)
            return
        if found.not_here or told:  # (none now, and none said before: nothing to say or to forget)
            self._post("not_here", files=found.not_here)

    def _tell_not_here(self, files: int) -> None:
        """The saved files this Windows user cannot open on this computer (*files*, from `_tell_protection`): copied
        from another computer or another Windows user's folder, or damaged. Said in a box (`store.not_here`: what
        happened, that they are never written over, how to bring the translations here) when the number differs from
        the one said last (ui.json `SAVED_FILES`), so that the same files do not bring the box at every start; nothing
        when there are none."""
        state_dir = self.settings.state_dir
        try:
            told = load_ui_table(state_dir, SAVED_FILES).get("not_here", "0")
        except OSError:
            told = "0"
        if str(files) == told:
            return
        try:
            save_ui_entry(state_dir, SAVED_FILES, "not_here", str(files) if files else None)
        except OSError:  # (a state folder that cannot be written: the box comes again at the next start)
            pass
        if files:
            self._warn_unasked(rendered(Message("store.not_here", files=files)))

    def _watch_set_aside(self) -> None:
        """A store of this window set aside a file this Windows user cannot open here (`names.take_set_aside`: the
        book starts afresh, the file kept beside it under a new name): said in a box, once, with where it is kept."""
        from ..names import take_set_aside

        taken = take_set_aside()
        if taken:
            self._warn_unasked(rendered(Message("store.set_aside", path=", ".join(str(t.copy) for t in taken))))

    def _warm_page_models(self) -> None:
        """The page models (layout, erase) made ready ahead of the first page, once the pipeline is there and a
        viewer is chosen (`Pipeline.warm_page_models`: cheap, safe to repeat, returns at once; any thread). Again
        after a change of what they are (a book's settings)."""
        pipeline = getattr(self, "pipeline", None)
        if pipeline is None or getattr(self, "selected", None) is None:
            return
        try:
            pipeline.warm_page_models()
        except Exception:  # noqa: BLE001 - the first page loads them as ever
            pass

    def _loaded_line(self, messages: list[Message]) -> Callable[[], str]:
        """The status line that says what loaded where: *messages* in the window's language, then what the line said
        when the window became ready ("Ready...", a hint; taken at the first look, so that it stays, in the window's
        language after a switch too)."""
        from ..messages import JOINER

        before: list[Callable[[], str] | None] = []

        def line() -> str:
            if not before:
                before.append(self._status_render)
            head = JOINER.join(rendered(m) for m in messages)
            earlier = before[0]
            tail = earlier() if callable(earlier) else ""
            return f"{head}  {tail}" if tail else head

        return line

    # ------------------------------------------------------------------ Ollama's model
    def _model_status(self, message: Message) -> None:
        """What a load of Ollama's model says (`OllamaTranslator.on_status`, the "model_status" event), on the Tk
        thread: the load shows as the page's stage and hands back to the stage it interrupted; a model partly on the
        CPU is said in the status line and, once a session, in a popup, since the status line goes on with the page."""
        code = code_of(message)
        if code == "ollama.loading":
            self._before_loading = self._progress
            self._handle_event("progress", {"text": message})
        elif code == "ollama.partly_on_gpu":
            self.status(message)
            if not self._partial_said:
                self._partial_said = True
                self._warn_unasked(rendered(message))
        else:
            earlier, self._before_loading = self._before_loading, None
            if earlier:
                self._handle_event("progress", {"text": earlier})
            else:  # a request of its own (a dialog's), with no page's stage to go back to
                self._progress = ""
                self.status(message)

    def _release_model(self) -> None:
        """The window closes: a page being translated is cancelled, and Ollama lets go of the model. Takes a moment at
        most (`ollama.RELEASE_TIMEOUT`). The model the window translated with counts as TASlation's own when the
        Ollama the window started is stopped after the window has gone (`ollama_start.finish_all`, `run_app`): a
        model named in the settings during the session is not another program's."""
        if self._page_cancel is not None:
            self._page_cancel.set()
        count_as_own(getattr(getattr(self, "translator", None), "model", ""),
                     *own_models(getattr(self, "settings", None)))
        if self.pipeline is not None:
            self.pipeline.release_translator()

    def _job_load_ocr(self) -> None:
        """The OCR model was missing at the start and is there now: it is loaded for the pipeline. An "ocr_loaded"
        event says how that went, whatever went wrong."""
        from ..ocr import ModelNotInstalled, Readers

        s = self.settings
        ocr = None
        error: Message | None = None
        try:
            self._post("status", key="Getting the Japanese reader ready (the first time takes a few seconds)...")
            ocr = Readers(s.models_dir, s.ocr_threads)
        except ModelNotInstalled as e:
            error = message_of(e, "ocr.error")
        except Exception as e:  # noqa: BLE001 - said in the status line; the window goes on without it
            error = message_of(f"{type(e).__name__}: {e}", "ocr.error")
            self._ocr_failed = True
        if ocr is not None and self.pipeline is not None:
            self.pipeline.ocr = ocr
        self._post("ocr_loaded", ok=ocr is not None, error=error)

    def _ensure_cache(self, book: str, model: str, language: str) -> bool:
        """The pipeline takes the book's stores (its cache, the reader's marks, the series sheet)
        when the book or the language has changed. False, and the status line says why, when one of them cannot be
        opened now (its file is locked or cannot be read, or holds another book's): the pipeline then has no cache,
        and the job that asked translates nothing."""
        language = language.strip() or "English"
        changed_language = language != self.settings.target_language
        self.settings.target_language = language
        self.translator.target_language = language
        if not self.settings.cache_enabled or not book:
            self.pipeline.set_cache(None)
            return True
        if generic_book_name(book):  # a name that names no book: nothing is read or kept under it (the page is
            self.pipeline.set_cache(None)  # still translated, and its name asked for at the start of the book)
            self.pipeline.set_annotations(None)
            self.pipeline.glossary, self.pipeline.glossary_text = None, ""
            return True
        current = self.pipeline.cache
        release = getattr(self.pipeline, "release_page_images", None)
        if current is not None and current.book != book and getattr(self, "batch", None) is None and release:
            release()  # another book: the last run's page pictures go
        if current is None or current.book != book or changed_language or current.language != language:
            try:
                cache = self.store.open(book, model, language)
                annotations = self.annotation_store.open(book)
                glossary = self.glossary_store.open(series_key(book), language)
            except OSError as e:  # a file that exists but cannot be opened now is never replaced: said, and left
                self.pipeline.set_cache(None)
                self._post("status", key="Could not open the files TASlation keeps for {book}: {error}. Nothing was translated; close what holds the file (another TASlation, a backup tool), then try again.",
                           values={"book": book, "error": str(e)})
                return False
            self.pipeline.set_cache(cache)
            self.pipeline.reset_context()
            self.pipeline.set_annotations(annotations)
            self.pipeline.glossary = glossary
            self.pipeline.glossary_text = glossary.format()
        return True

    def _job_translate(self, image: Image.Image, book: str, model: str, language: str, complete: bool = False,
                       cancel: threading.Event | None = None, again: Any = None) -> None:
        """The page *image* read and translated, in the worker. *again* (a page's `PageResult`): "Translate again",
        its cached translations forgotten first and put back when this translates nothing: Stop, a new page, Ollama
        down, a job that fails. They may be the reader's own, and no undo brings them back. A save that failed is said
        after the page (`Pipeline.save_error`)."""
        held: list[Any] = []
        try:
            self._use_model(model, language)
            if not self._ensure_cache(book, model, language):
                return  # the status line says which file could not be opened
            if again is not None:
                held = self.pipeline.pages_of(again)
                self.pipeline.forget_page(again)
            try:
                result = self.pipeline.process(image, progress=lambda m: self._post("progress", text=m),
                                               complete=complete, events=lambda kind, data: self._post(kind, **data),
                                               cancel=cancel, on_slow=lambda seconds: self._post("slow", seconds=seconds))
            except Cancelled:  # Stop, or a new page: nothing of this page reached the cache
                self._post("page_cancelled")
                return
            if held and not result.translated:
                self.pipeline.restore_pages(held)
                error = result.error
                result = self.pipeline.process(image, translate=False)  # the page as it is kept: nothing was replaced
                result.error = error
            held = []
            self._post("result", result=result)
            self._say_failed_save()
            self._look_for_colophon(image, result, book, model, language)
        finally:
            if held:
                self.pipeline.restore_pages(held)
            self._post("translate_done")

    def _say_failed_save(self) -> None:
        """The status line says that a save failed, while the job that met it is still the latest news."""
        error = getattr(self.pipeline, "save_error", "")
        if error:
            self._post("status", key="Could not save the translations ({error}). They stay in memory until a save works: free some disk space, or close what holds the file.",
                       values={"error": error})

    def _look_for_colophon(self, image: Image.Image, result: Any, book: str, model: str, language: str) -> None:
        """After a page, in the worker: a page with a unit that has no text to translate (the pipeline's detector
        cuts a colophon's columns into pieces it does not keep) and that passes the colophon's cheap test is read as
        a colophon in a job of its own, so that the page is done first; what is found comes back as a "colophon"
        event. At most `colophon.MAX_READS` pages of a book are read so, and none once its colophon is found."""
        ocr = getattr(self.pipeline, "ocr", None)
        units = list(getattr(result, "units", []) or [])
        if ocr is None or not units or self._colophon_reads.get(book, 0) >= COLOPHON_READS:
            return
        texted = {r.unit for r in result.regions if r.status in ("translated", "untranslated")}
        if all(u.index in texted for u in units):
            return
        margins = tuple(self.settings.margins)
        if not colophon_precheck(image, margins):  # type: ignore[arg-type]
            return
        self._colophon_reads[book] = self._colophon_reads.get(book, 0) + 1

        def job() -> None:
            found = find_colophon(image, ocr, margins)  # type: ignore[arg-type]
            if found is not None:
                self._colophon_reads[book] = COLOPHON_READS  # found: no other page is read for it
                self._post("colophon", colophon=found, book=book, model=model, language=language)

        self._jobs.put(job)

    def _job_refresh_premises(self, book: str, language: str) -> None:
        """The reader changed the series sheet: hand the pipeline the new state. A store that cannot be opened now is
        said in the status line; the pipeline keeps what it had."""
        if self.pipeline is None or not book or generic_book_name(book):
            return
        try:
            glossary = self.glossary_store.open(series_key(book), language)
            annotations = self.annotation_store.open(book)
        except OSError as e:  # locked, cannot be read now, or another book's file (FileExistsError)
            self._post("status", key="Could not open the files TASlation keeps for {book}: {error}. The translations go on with the book's premises as they were.",
                       values={"book": book, "error": str(e)})
            return
        self.pipeline.glossary = glossary
        self.pipeline.glossary_text = glossary.format()
        self.pipeline.set_annotations(annotations)

    def _job_forget_cache(self, book: str) -> None:
        if self.pipeline is not None and self.pipeline.cache is not None and self.pipeline.cache.book == book:
            self.pipeline.set_cache(None)

    def _left_readings(self, book: str, model: str, language: str) -> Readings | None:
        """What an earlier run of this book, with this model and language, read and did not store."""
        held = getattr(self, "_readings", None)
        return held[1] if held is not None and held[0] == (book, model, language) else None

    def _job_batch(self, hwnd: int, book: str, model: str, language: str, max_pages: int, context_mode: bool,
                   title: str = "", own_windows: tuple[int, ...] = (), at_once: bool = False,
                   page_area: Any = None) -> None:
        """A whole-book scan - after the setup is checked once more, right before the first page is read:
        with a problem it does not start (the banner says what is missing). Never for a name that names no book:
        nothing of it could be kept (the batch's Start asks for the name first). Whatever goes wrong before the
        reader runs ends in "batch_refused", said in the status line: the window never stays busy for a run that is
        not there. *at_once*: the pages an earlier run read are translated now (`translate_readings`): the run takes
        the page on show and goes on to the translation (`BatchReader.finish` with *partial*). *page_area*: the capture
        area the run starts from and widens with the pages it takes (`_run_area`, taken on the Tk thread as it
        starts); the panels it finds come back as ``page_area`` events (`_run_found`)."""
        try:
            if generic_book_name(book):
                self._post("status", key="Give the book a name first (the Book field).")
                self._post("batch_refused", problems=[])
                return
            self._ollama_back()
            problems = preflight(self.settings)
            self._post("health", problems=problems)
            if blocking(problems):
                self._post("batch_refused", problems=problems)
                return
            self._use_model(model, language)
            if not self._ensure_cache(book, model, language):  # the status line says which file could not be opened
                self._post("batch_refused", problems=[])
                return
            settings = self.settings.with_overrides(context_mode=context_mode)

            def progress(p: BatchProgress, result: Any) -> None:  # what the batch says, as it was when it said it
                self._post("batch", progress=p, result=result, message=p.message, phase=p.phase, pages=p.pages,
                           translated=p.translated, found=p.found, checked=p.checked, waiting=p.waiting,
                           queued=p.queued, answering=p.answering, page_seconds=p.page_seconds)

            reader = BatchReader(self.pipeline, hwnd, settings, on_progress=progress, max_pages=max_pages,
                                 context_mode=context_mode,
                                 book=book, series=series_key(book) if book else "", title=title,
                                 query=self.window_query, own_windows=own_windows, preflight=problems,
                                 show=lambda kind, data: self._post(kind, **data),
                                 readings=self._left_readings(book, model, language), keep_readings=True,
                                 page_area=page_area)
        except Exception as e:  # noqa: BLE001 - said in the status line; nothing was scanned
            self._post("status", key="Could not start the batch: {error}", values={"error": f"{type(e).__name__}: {e}"})
            self._post("batch_refused", problems=[])
            return
        self.batch = reader
        if self._batch_stop_asked:  # Stop came while the setup was checked
            reader.stop()
        elif at_once:
            reader.finish(partial=True)
        try:
            reader.run()
        finally:
            self.batch = None
            self._readings = ((book, model, language), reader.left) if reader.left is not None else None
            self._post("batch_done", progress=reader.progress)

    # ------------------------------------------------------------------ events
    def _poll_events(self) -> None:
        """The worker's events handled on the Tk thread: every EVENTS_BUSY_MS while a job runs (a page from the cache
        is drawn the moment it is done), every EVENTS_IDLE_MS otherwise."""
        try:
            while True:
                kind, data = self._events.get_nowait()
                try:
                    self._handle_event(kind, data)
                except tk.TclError:
                    pass  # a dialog or canvas vanished under us; never stop the event pump
        except queue.Empty:
            pass
        finally:
            for step in (self._flush_fill, self._flush_busy, self._watch_page, self._watch_trouble,
                         self._watch_set_aside):
                try:
                    step()
                except Exception:  # noqa: BLE001 - never stop the event pump
                    pass
            self._events_job = self.after(EVENTS_BUSY_MS if self.busy else EVENTS_IDLE_MS, self._poll_events)

    def _warn_unasked(self, text: str, said: bool = False) -> None:
        """A warning nobody asked for (the worker's: a page that failed, a model partly on the CPU, Ollama not
        started). While the reader reads - reading mode, or the window over the full-screen viewer - no box comes up
        over the book to take its keys: the status line says it (*said*: it says it already) and, over the book, the
        page shows it for a while. Otherwise TASlation's own box, which the window does not wait for."""
        if self.reading or getattr(self, "_over_on", False):
            if not said:
                self.status(text)
            if not self.reading:  # (the reading window shows the status line on the page by itself)
                self.canvas.set_note(text, WARNING_NOTE_MS)
            return
        boxes.tell(self, text, wait=False)

    def _flush_fill(self) -> None:
        """Page events came in since the last look at the queue: the page is drawn again, once for all of them."""
        if self._fill_dirty:
            self._fill_dirty = False
            self._redisplay()

    def _handle_event(self, kind: str, data: dict[str, Any]) -> None:
        if kind == "status":
            if "key" in data:  # in the window's language, also after a switch
                self.say(data["key"], **data.get("values", {}))
            else:
                self.status(data["text"])
        elif kind == "progress":  # the pipeline at work: the busy badge shows once it reads or translates the page
            self._progress = progress = data["text"]
            self._slow_before = None
            reading = getattr(self._scan, "phase", "") == "read"
            self.status_var.set(progress_line(progress, reading))
            self._status_render, self._status_key = (lambda: progress_line(progress, reading)), None
            if self._fill is not None and asks_model(progress):
                self._fill.mark = self._fill.filled  # the badge counts this request's bubbles
            self._busy_shown = self._busy_shown or reads_page(self._progress)
            if self._busy_shown:
                self.canvas.set_busy(self._busy_text)
        elif kind == "model_status":  # Ollama's model is being loaded
            self._model_status(data["message"])
        elif kind == "slow":  # the model has said nothing for a while: the badge says so, and that Stop cancels
            if self._page_cancel is None or self.batch is not None:
                return
            if code_of(self._progress) != SLOW:
                self._slow_before = self._progress
            self._progress = slow = Message(SLOW, seconds=round(float(data.get("seconds", 0))))
            self.status_var.set(progress_line(slow))
            self._status_render, self._status_key = (lambda: progress_line(slow)), None
            self._busy_shown = True
            self.canvas.set_busy(self._busy_text)
        elif kind in ("regions", "read", "translated", "page"):
            self._on_page_event(kind, data)
        elif kind == "error":
            self._hide_busy()
            message = data.get("message")
            text = rendered(message) if message is not None else str(data.get("text", ""))
            if data.get("cached_note"):
                text += _("\n\nPages already translated still show; new pages cannot be read.")
            if message is not None:
                self.status(message)
            else:
                self.status(text.splitlines()[0] if text else "")
            self._warn_unasked(text, said=True)
        elif kind == "ollama_failed":  # Ollama could not be started at the window's start: what to do, said once
            self._warn_unasked(rendered(data["message"]))
        elif kind == "not_here":  # saved files this Windows user cannot open here, found at the start
            self._tell_not_here(int(data.get("files", 0)))
        elif kind == "models":
            self._take_models(data["models"])
        elif kind == "health":  # a setup check: the banner, and the next check while a problem stands
            if data.get("checked"):
                self._health_checking = False
            self._set_health(data.get("problems"), data.get("models"))
        elif kind == "preflight":  # the check before a whole-book scan: the banner, then what waited for it
            then = self._checks.pop(data.get("token"), None)
            self._set_health(data["problems"])
            if then is not None:
                then(list(data["problems"]))
        elif kind == "recognised":  # the books whose caches hold the page on screen: the dialog that waited for them
            waiting = self._recognising.pop(data.get("token"), None)
            if waiting is not None:
                request, then = waiting
                then(*self._recognition_hint(request, data.get("names")))
        elif kind == "ocr_loaded":
            self._ocr_loading = False
            if data.get("ok"):
                self.say(READY)
            else:
                self.say("Could not load the OCR model: {error}", error=data.get("error") or "?")
        elif kind == "ready":
            self.ready = True
            if self._area_hint_due():  # the chosen viewer's frames showed no page panel: Set area... is the way
                self._area_hinted = True
                self.status(lambda: _("Ready. Turn the pages here with the page keys, or click the page. F5: translate this page now · F11: reading mode.")
                            + "\n" + _("No area is set for this viewer: Set area... (Page menu) lets you drag a rectangle around the page."))
            else:
                self.say(READY)
            self._load_ocr_if_due()
            self._run_queued()
            if getattr(self, "_find", None) is not None:
                self._refresh_find()
        elif kind == "result":
            self._hide_busy()
            if data.get("edited") and data["result"] is not self.last_result:
                self.say("Saved on the page the editor was opened on.")  # the page on show stays
                return
            self._fill = None
            self._settle_live(data["result"])
            # (its regions are another page's)
            order_gone = getattr(self, "_ordering", None) is not None and data["result"] is not self.last_result
            if order_gone:
                self._end_order()
            self.last_result = data["result"]
            self._viewer_unread = None  # a page read: the viewer chosen last was the one (`_learn_viewer`)
            self._grip_box = None
            if not any(r is self._chosen_region for r in self.last_result.regions):
                self._chosen_region = None
            self._redisplay()
            self._show_notes()
            result = self.last_result
            self.status(lambda: self._page_line(result) + self._font_note())
            if order_gone:
                self.say("Reading order cancelled: another page came.")
            if self._review is not None and self._review.winfo_exists():
                self._review.fill(review_rows(self.last_result.regions))
            if getattr(self, "_find", None) is not None:
                self._refresh_find()
        elif kind == "page_cancelled":  # Stop, or a new page: the page was not translated
            self._hide_busy()
            if self._cancel_why != "page":
                self.say("Stopped: this page was not translated, and nothing of it was kept. F5 translates it again.")
        elif kind == "asked":
            editor = self._editor
            if editor is not None and editor.winfo_exists():
                editor.show_answers(data["mode"], data["texts"])
            if data["texts"] and self.last_result is not None:
                result = self.last_result
                self.status(lambda: self._page_line(result))
            else:
                self.say("The model gave no other translation.")
        elif kind == "propose":
            self._propose_renderings(data["changes"])
        elif kind == "names_applied":  # a name's renderings made one (`name_check.apply_name`)
            name_check.names_applied(self, data)
        elif kind == "find":  # the book's text changed, or its cache is there: what the list of matches shows
            self._book_text_changed(data.get("lines", ()))
        elif kind == "colophon":  # a page of the book was its colophon: its name is offered (once the window can)
            self._colophon_found = (data["book"], data.get("model", ""), data.get("language", ""), data["colophon"])
            self._offer_colophon()
        elif kind == "renamed":  # the book's files moved to the colophon's name, or the move was refused
            self._book_renamed(data)
        elif kind == "translate_done":
            self.busy = False
            self._page_cancel = None
            self._slow_before = None
            self._set_busy(False)
            self._sync_stop()
            self._apply_found_margins()  # a page panel found while the job ran
            self._job_frame = self._job_thumb = self._job_area = None
            if self._fill is not None:  # the job ended without its page (it failed): the viewer's picture again
                self._fill = None
                self._redisplay()
            if self._colophon_found is not None:  # one that waited for reading mode to end
                self._offer_colophon()
            self._run_queued()
        elif kind == "batch_page":
            self._batch_page(data["image"])
        elif kind == "page_area":  # the page panels a run found in the pages it took: into the window's record
            self._run_found(data)
        elif kind == "batch":
            p: BatchProgress = data["progress"]
            if data.get("result") is not None:  # a page of the run is done: the finished page takes over
                self._hide_busy()
                self._fill, self._job_frame = None, None
                self.last_result = data["result"]
                self._live, self._live_thumb = self.last_result.original, None  # the batch's capture is the latest frame
                self._redisplay()
                self._show_notes()
            message = data.get("message", p.message)
            if code_of(message) in ("batch.read_page", "batch.page_cached"):  # read: the badge goes until the next page
                self._hide_busy()
            if isinstance(message, Message):
                self.say(message)
            elif message:
                self.status(str(message))
            if self._scan is not None:
                self._scan.update(message, data.get("phase", p.phase), data.get("pages", p.pages),
                                  data.get("translated", p.translated), data.get("found", p.found), time.monotonic(),
                                  data.get("checked", getattr(p, "checked", 0)), data.get("waiting"),
                                  data.get("queued", 0), answering=data.get("answering", 0),
                                  page_seconds=data.get("page_seconds", 0.0))
                self._band = {"kind": "scan", "scan": self._scan}
                self._show_band()
                if self.busy and getattr(self, "_busy_signs", False):  # the run's next pass: the title says so
                    self.title(busy_title(self._scan))
        elif kind == "batch_done":
            self._batch_done(data["progress"])
        elif kind == "compute":  # where Ollama translates, from its log: the processor gets a line on the banner
            if data.get("where") == "cpu":
                self._on_cpu = cpu_page_seconds(self._pace(self.model_var.get().strip()))
                self._show_banner()
        elif kind == "translator_restarted":  # Start translator again: Ollama answers, or what stands in the way
            self._restarting = False
            failed = data.get("message")
            if failed is None:
                self.say("The translation program is running again.")
            else:
                self.say(failed)
        elif kind == "page_stage":  # a page of the run, how far each of its stages is: the page strip
            self._on_page_stage(data)
        elif kind == "translation_page":  # the page the run translates, lettered so far: the page area follows it
            self._on_translation_page(data)
        elif kind == "batch_memory":  # what the run's page pictures take: the line beside the strip
            self._on_batch_memory(data)
        elif kind == "page_missed":  # a page went by before the run could take it: its place on the strip in view
            self._on_page_missed(data)
        elif kind == "start_role":  # the book in the Book box is counted: the role it opens in
            self._start_role_known(data)
        elif kind == "batch_refused":  # nothing was scanned: the setup is not complete, or a file cannot be opened
            problems = data.get("problems") or []
            self._batching = False
            self.busy = False
            self._set_busy(False)
            self._scan = None
            if self._auto_before_batch is not None:
                self.auto_var.set(self._auto_before_batch)
                self._auto_before_batch = None
            if self._resume_auto:  # the whole-book start: asked again once the setup is complete
                self._resume_auto = False
                if problems:
                    self._book_scanned = False
            self._band = None
            self._show_band()
            if problems:  # (a file that cannot be opened: the status line has said so)
                self._hold_scan()
            self._sync_stop()
            self._run_queued()
        elif kind == "idle":
            self._sync_guard()
            if not self.ready and self._queued is not None:  # the start ended without the models: nothing can run
                self._queued = None
                self._hide_busy()
                self._show_progress(self.busy)

    def _batch_page(self, frame: Image.Image) -> None:
        """The run has come to the page *frame*: on the page area at once, in place of the page before; it fills in
        from here as any page does (`_on_page_event`), and the batch's message with the result ends it."""
        self._hide_busy()
        if getattr(self, "_ordering", None) is not None:
            self._end_order()
        self._fill = self.last_result = self._chosen_region = self._grip_box = None
        self._job_frame = frame
        self._live, self._live_thumb = frame, None
        self._busy_since = time.monotonic()
        self._redisplay()
        self._show_notes()  # the page before's go with it

    def _batch_done(self, p: BatchProgress) -> None:
        """The scan has ended: its summary in the band (in the window's language), and Auto back on when it was on
        before the run, whoever started it (said in a line of its own). A run that finished with the book translated
        leaves translator mode for reader mode, unless the reader chose the role for the book (`_reader_after_run`:
        said in a line of its own too). A reader who is elsewhere is told (`attention.tell_run_ended`: the taskbar
        button flashes, and the sound plays when chosen), unless they stopped the run themselves. The names the run
        rendered in more than one way are kept for the session and offered on the band (`name_check.keep_found`)."""
        self._batching = False
        self.busy = False
        self._set_busy(False)
        self._apply_found_margins()
        self._job_frame = None
        self._hide_busy()
        # the page the run translated leaves the page area at once (reading is on the viewer: `strip`), however the run
        # ended: the live view takes over
        followed = end_follow(self, redisplay=False)
        if self._fill is not None or followed:  # stopped on a page: its frame stays, as the viewer shows it
            self._fill = None
            self._redisplay()
        self._keep_pace(self._scan)
        self._scan = None
        resumed = self._resume_auto or bool(self._auto_before_batch)
        if resumed:
            self._resume_auto = False
            self.auto_var.set(True)
            self._auto_last = None
        self._auto_before_batch = None
        summary = p.summary or p.reason or Message("batch.scan_ended")
        self._band = {"kind": "summary", "summary": summary, "resumed": resumed}
        if getattr(p, "names", None):  # the names the run rendered in more than one way: offered on the band
            book_for = getattr(self, "_batch_for", None) or ("", "", "")
            language = book_for[2] or self.lang_var.get().strip() or "English"
            self._band["names"] = name_check.keep_found(self, p, book_for[0], language)
        self._show_band()
        if isinstance(summary, Message):
            self.say(summary)
        else:
            self.status(str(summary))
        self._sync_stop()
        tell_run_ended(self, summary)
        if getattr(summary, "code", "") == "batch.finished":  # the page on show is translated now: it shows so
            self.after_idle(self.translate_now)
        found = getattr(p, "colophon", None)
        if found is not None and self._batch_for[0]:  # the scan read the book's colophon: its name is offered
            self._colophon_found = (*self._batch_for, found)
            self._offer_colophon()
        if getattr(summary, "code", "") == "batch.finished":
            self._run_read = self._batch_for
        if getattr(summary, "code", "") == "batch.finished" and self._reader_after_run(self._batch_for[0],
                                                                                        self._batch_for[2]):
            self._band["reader"] = True  # the band says it too: the status line soon says other things
            self._show_band()
        self._run_queued()

    def _on_page_event(self, kind: str, data: dict[str, Any]) -> None:
        """The page filling in while it is translated (`pipeline.PageFill`): the regions found are outlined on the
        frame being read (dashed; solid once read; gone when they are no text), each one is lettered as its
        translation comes in, and the finished page takes over; meanwhile the busy band is a badge in the corner.
        The page is drawn again after the queue is empty (`_flush_fill`)."""
        fill = self._fill
        if kind == "regions":
            frame = self._job_frame
            if frame is None or tuple(data.get("size", frame.size)) != tuple(frame.size):
                return
            result = self.last_result
            base = result.image if result is not None and frame is result.original else frame
            self._fill = Filling(frame, base, [tuple(b) for b in data["boxes"]])
            self._busy_shown = True
            self.canvas.set_busy(self._busy_text)
        elif fill is None:
            return
        elif kind == "read":
            i = int(data["index"])
            if 0 <= i < len(fill.states):
                if data.get("box") is not None:
                    fill.boxes[i] = tuple(data["box"])
                if fill.states[i] == "found":
                    fill.states[i] = "read" if data.get("status") == "untranslated" else "skipped"
        elif kind == "translated":
            i = int(data["index"])
            if 0 <= i < len(fill.states):
                fill.letter(i, data["box"], data["patch"], str(data.get("text", "")))
            if code_of(self._progress) == SLOW and self._slow_before is not None:  # the model answers after all
                self._progress, self._slow_before = self._slow_before, None
        elif kind == "page":
            fill.final = data["image"]
        self._fill_dirty = True

    # ------------------------------------------------------------------ the setup checks
    def _take_models(self, models: list[str]) -> None:
        """The models Ollama has: the model the window translates with follows them (`_choose_model`)."""
        self._models = list(models)
        self._choose_model()

    def _choose_model(self) -> None:
        """The model the window translates with (the Model variable every job takes, on the Tk thread): what
        `translate.models.choose` makes of the setting ``ollama_model``, the target language of the "To:" box and the
        models Ollama has - the language's own model, Qwen standing in for a PLaMo not installed yet, or (a model of
        the reader's own) the first Ollama has while it lacks that one."""
        from ..translate.models import choose

        language = self.lang_var.get().strip() or "English"
        name = choose(self.settings.ollama_model, language, self._models or None).name
        if self.model_var.get() != name:
            self.model_var.set(name)

    def _follow_target(self) -> None:
        """The "To:" box has another language (on the Tk thread): the model follows it (`_choose_model`; the worker
        makes the translator for it with the next job, `_use_model`), and the setup is checked again for it in a
        thread of its own, so that the banner says at once when the language's model is not installed."""
        language = self.lang_var.get().strip() or "English"
        if language == getattr(self, "_check_language", None):
            return
        self._check_language = language
        self._choose_model()
        if self.ready and not self._health_checking:
            self._health_checking = True
            threading.Thread(target=self._check_in_background, name="taslation-setup-check", daemon=True).start()

    def _use_model(self, model: str, language: str) -> None:
        """In the worker, before a job translates: the translator is the one for the Ollama model *model* (the Model
        variable when the job was asked for) and the target language *language*: the same one with its model set,
        or a new one when the model needs the other kind (PLaMo's raw prompts or the chat), which the pipeline takes
        (`translate.models.follow`, `Pipeline.set_translator`: the old one's model leaves the GPU)."""
        from ..translate.models import follow

        language = language.strip() or "English"
        fresh = follow(self.translator, self.settings, model, language)
        if fresh is not self.translator:
            self.translator = fresh
            if self.pipeline is not None:
                self.pipeline.set_translator(fresh)

    def _set_health(self, problems: list[Any] | None, models: list[str] | None = None) -> None:
        """A setup check's result: the banner shows its problems (None: the check failed, the banner stays), the
        model in use follows the models when they changed, and while a problem stands it is looked at again in
        `HEALTH_RECHECK_MS`."""
        if problems is not None:
            self._health = list(problems)
            if not blocking(self._health):
                self._scan_held = False
            self._show_banner()
            seen = getattr(self, "_model_missing_seen", None)
            if seen is not None:  # the translator model the language needs: offered (ui.model_switch)
                seen(self._health)
        if models is not None and list(models) != list(self._models):
            self._take_models(models)
        self._load_ocr_if_due()
        if self._health and self._health_after is None:
            self._health_after = self.after(HEALTH_RECHECK_MS, self._health_tick)

    def _health_tick(self) -> None:
        """While a setup problem stands: the setup is checked again in a thread of its own (it may wait for an Ollama
        that does not answer); its result comes back as a "health" event."""
        self._health_after = None
        if not self._health or self._health_checking:
            return
        self._health_checking = True
        threading.Thread(target=self._check_in_background, name="taslation-setup-check", daemon=True).start()

    def _check_in_background(self) -> None:
        try:
            problems, models = self._check_setup()
        except Exception:  # noqa: BLE001 - a check that fails changes nothing; the next one looks again
            problems, models = None, None
        self._post("health", problems=problems, models=models, checked=True)

    def _load_ocr_if_due(self) -> None:
        """The OCR model was missing at the start and is there now: the worker loads it."""
        pipeline = self.pipeline
        if any(code_of(m) == "health.ocr_missing" for m in self._health):
            self._ocr_failed = False  # a model put there later is tried afresh
            return
        if (not self.ready or pipeline is None or getattr(pipeline, "ocr", None) is not None or self._ocr_loading
                or self._ocr_failed):
            return
        self._ocr_loading = True
        self._jobs.put(self._job_load_ocr)

    def _preflight(self, then: Callable[[list[Any]], None]) -> None:
        """`batch.preflight` in the worker (never on the Tk thread); *then* gets its Messages on the Tk thread."""
        token = next(self._check_ids)
        self._checks[token] = then
        settings = self.settings

        def job() -> None:
            try:
                self._ollama_back()
                problems = preflight(settings)
            except Exception:  # noqa: BLE001 - the batch checks again before it starts
                problems = []
            self._post("preflight", token=token, problems=problems)

        self._jobs.put(job)

    # ------------------------------------------------------------------ the start of a book
    def _name_needed(self) -> bool:
        """Whether the Book box holds a name that names no book (`bookid.generic_book_name`: a viewer's name, a browser,
        nothing), as the window's title gives it or as typed: nothing is kept under such a name, so it is asked for."""
        return generic_book_name(self.book_var.get())

    def _begin_book(self, image: Image.Image, thumb: np.ndarray | None, whole: bool) -> None:
        """Auto's first page of a book not in its cache: in whole-book mode the setup is checked first, then the
        reader is asked (`_ask_book`); in page-by-page mode only the book's name is asked for. Meanwhile the latest
        page Auto finds waits (`_start_pending`), and so does the start while the name is being asked for already
        (`_ask_name`: it goes on once the name is given)."""
        self._start_pending = (image, thumb)
        self._start_first = image
        if self._start_dialog is not None:
            self._start_whole = whole
            return
        if whole:
            self._preflight(self._after_preflight)
        else:
            self._ask_book(whole=False)

    def _after_preflight(self, problems: list[Any]) -> None:
        pending = self._start_pending
        if pending is None:
            return
        if blocking(problems):  # nothing is scanned: the banner says what is missing, the page is read as it is
            self._start_pending = None
            self._hold_scan()
            self._translate_pending(pending)
            return
        self._ask_book(whole=True)

    def _hold_scan(self) -> None:
        """A whole-book scan waits for the setup: said in the status line and, until the setup is complete, after the
        problems in the banner (the status line soon says other things)."""
        self._scan_held = True
        self._show_banner()
        self.say("The whole book is not read yet: first fix what the lines above the page say. Until then TASlation translates page by page.")

    def _ask_book(self, whole: bool) -> None:
        """The start dialog: the book's name when the title gives none (offering the books recognised by the page:
        `_recognise_then`), and in whole-book mode whether to read the whole book first. The answer is kept per book
        (`BOOK_STARTS`): a book the reader chose to read page by page is not asked about again (the status line says
        how to read it whole), one they chose to read whole is asked about with Start as Enter's answer - a run
        never starts without the reader's go. Enter answers page by page otherwise."""
        if self._start_dialog is not None:  # the name is being asked for (Series sheet..., F5): the start waits
            self._start_whole = whole
            return
        generic = self._name_needed()
        if not whole and not generic:
            self._book_answer("page", self.book_var.get().strip())
            return
        kept = self._book_start(self.book_var.get().strip()) if whole and not generic else ""
        if kept == "page":
            self._book_answer("page", self.book_var.get().strip())
            self.say("This book is translated page by page, as you chose before. To read it whole, press Read whole book...")
            return

        def answer(choice: str | None, name: str) -> None:
            self._book_answer("page" if choice == "ok" else choice, name, generic, asked=whole)

        if not generic:
            self._start_dialog = StartDialog(self, self.book_var.get().strip(), False, whole, answer,
                                             default=kept or "page")
            return
        pending = self._start_pending
        waiting = self._start_dialog = Recognising()

        def show(matches: list[str], hint: str) -> None:
            if self._start_dialog is not waiting:  # the window was rebuilt meanwhile: the next page asks again
                return
            name, still = self.book_var.get().strip(), self._name_needed()  # a name typed meanwhile stays
            self._start_dialog = StartDialog(self, name, still, whole, answer, matches=matches if still else (),
                                             hint=hint if still else "",
                                             default=(self._book_start(name) if whole else "") or "page")

        self._recognise_then(show, pending[0] if pending else None, self._start_first)

    def _recognition(self, *frames: Any) -> Recognition:
        """What recognising the book on screen needs, taken from the window (on the Tk thread): the target language,
        the colophon found on a page of this book under its generic name, the frames - *frames* (the page Auto found,
        the one the start began with) and the frame on show, each once - and the capture areas they are
        fingerprinted in: the one read now, and the reader's own when one is set (the page panel found inside it may
        have narrowed it; `bookid.page_groups` adds the whole capture and the page panel found in it, so that a page
        translated under another capture area is recognised all the same). With the cache off nothing is looked
        at (*cached* False)."""
        book, language = self.book_var.get().strip(), self.lang_var.get().strip() or "English"
        found = self._colophon_found[3] if self._colophon_found is not None and self._colophon_found[0] == book \
            else None
        shown: list[Any] = []
        for frame in (*frames, getattr(self, "_live", None)):
            if frame is not None and all(frame is not other for other in shown):
                shown.append(frame)
        areas = [tuple(self.settings.margins)]
        hand = getattr(self, "_hand_area", None) if getattr(self, "_manual_area", False) else None
        if hand is not None:
            areas.append(tuple(hand))
        return Recognition(bool(self.settings.cache_enabled), self.store, language, found, tuple(shown), areas)

    def _recognise_then(self, then: Callable[[list[str], str], None], *frames: Any) -> None:
        """*then(matches, hint)* with what the start dialog offers (`_recognition`, `recognised_books` and
        `_recognition_hint`), the heavy part in the worker: the
        frames fingerprinted in their areas and every cache's pages looked through (`recognised_books`: some 150 ms
        for two full-HD frames, nearly all of it the fingerprints) never hold up the window. The books come back as a
        "recognised" event and *then* follows on the Tk thread; at once when the cache is off (nothing to look at)."""
        request = self._recognition(*frames)
        if not request.cached:
            then(*self._recognition_hint(request, None))
            return
        token = next(self._check_ids)
        self._recognising[token] = (request, then)

        def job() -> None:
            self._post("recognised", token=token, names=recognised_books(request))

        self._jobs.put(job)

    def _recognition_hint(self, request: Recognition, books: tuple[list[str], str] | None) -> tuple[list[str], str]:
        """The start dialog's *matches* and *hint* from what `recognised_books` found for *request* (None: the caches
        were not looked at): the book whose cache has the colophon's ISBN ("colophon"); else the books whose caches
        hold a page on screen, best first ("recognised", "several"); else the colophon's own name ("colophon"). When
        none of these names the book and the window's title names none either: the name last given to a book read
        in this viewer under such a title (`bookid.last_name`, "last")."""
        from ..bookid import last_name
        from ..cache import book_key_from_title

        if books is not None:
            names, how = books
            if names:
                return list(names), how
            if request.colophon is not None:
                return [request.colophon.name], "colophon"
        win = getattr(self, "selected", None)
        generic = win is not None and generic_book_name(book_key_from_title(win.title))
        last = last_name(self.settings.state_dir, win.title) if generic else ""
        return ([last], "last") if last else ([], "")

    def _remember_viewer_name(self, name: str) -> None:
        """*name* is the viewer's last book from now on (`bookid.remember_name`: offered at the next start in this
        viewer that recognises nothing; generic names are never kept, nor is a temporary one: it holds one book's
        files until the colophon names it)."""
        from ..bookid import remember_name

        win = getattr(self, "selected", None)
        if win is not None and not is_temporary_name(name):
            remember_name(self.settings.state_dir, win.title, name)

    def _ask_name(self, then: Callable[[str], None], *frames: Any) -> None:
        """A name for the book before anything is kept under it: while the Book box names no book, the start dialog
        asks for it (offering the books recognised by *frames* and the frame on show, or the viewer's last name:
        `_recognise_then`), and *then(name)* follows once a real name is in the Book box; at once with the Book box's name
        when it has one. Closed without a name, nothing follows. The name given is the viewer's last name from then on
        (`_remember_viewer_name`). A book's start that Auto began meanwhile goes on once the name is given."""
        if not self._name_needed():
            then(self.book_var.get().strip())
            return
        if self._start_dialog is not None:  # a dialog of the start asks already
            return

        def answer(choice: str | None, name: str) -> None:
            self._start_dialog = None
            name = " ".join(str(name).split())
            if choice is None or (generic_book_name(name) and not viewerparts.held(name)):
                self._start_pending, self._start_whole = None, None  # the start that waited asks at the next page
                self.say("Give the book a name first (the Book field).")
                return
            before = self.book_var.get().strip()
            self._book_named(name)  # (a name held back for the title's is released: the reader's answer stands)
            self.book_var.set(name)
            self._book_edited = True
            self._remember_viewer_name(name)
            self._carry_colophon(before, name)
            self._resume_start()
            then(name)

        waiting = self._start_dialog = Recognising()

        def show(matches: list[str], hint: str) -> None:
            if self._start_dialog is not waiting:  # the window was rebuilt meanwhile: nothing follows
                return
            name, still = self.book_var.get().strip(), self._name_needed()  # a name typed meanwhile stays
            self._start_dialog = StartDialog(self, name, still, False, answer, matches=matches if still else (),
                                             hint=hint if still else "")

        self._recognise_then(show, *frames)

    def _resume_start(self) -> None:
        """A book's start that waited for the name being asked for goes on with the page Auto found meanwhile."""
        pending, whole = self._start_pending, self._start_whole
        self._start_whole = None
        if pending is None or whole is None:
            return
        self._start_pending = None
        self._begin_book(pending[0], pending[1], whole)

    def _book_answer(self, answer: str | None, name: str, generic: bool = False, asked: bool = False) -> None:
        """The start dialog's answer: the name goes into the Book box (the cache uses it), "start" reads the whole
        book first, "page" translates the page as it is - kept for the book when the dialog asked (*asked*:
        `BOOK_STARTS`); None (closed: "not now") is page by page for this book until TASlation closes, nothing kept,
        and the page is translated; closed while the book has no name yet, nothing is read and the next page asks
        again (nothing can be kept under no name). A name asked for because the title named none (*generic*) is the
        viewer's last name from then on (`_remember_viewer_name`)."""
        self._start_dialog = None
        pending, self._start_pending = self._start_pending, None
        if answer is None:
            book = self.book_var.get().strip()
            if generic or self._name_needed():
                self.say("Nothing was read yet: TASlation asks again at the next page. F5 translates this page now.")
                return
            if pending is not None:
                self._translate_pending(pending)
            if self.scan_mode() == "book":
                self._book_scanned, self._scanned_book = True, book
                self.say("Not now: this book is translated page by page until you close TASlation. To read it whole, press Read whole book...")
            return
        name = " ".join(str(name).split()) or self.book_var.get().strip()
        before = self.book_var.get().strip()
        if generic or name != before:
            self._book_named(name)  # what the name says of the title (a name held back is released)
            self.book_var.set(name)
            self._book_edited = True
            self._carry_colophon(before, name)
        if generic:
            self._remember_viewer_name(name)
        whole = self.scan_mode() == "book"
        if whole:
            self._book_scanned, self._scanned_book = True, name
        if asked and whole and answer in ("start", "page"):
            self._keep_book_start(name, answer)
        if pending is None:
            return
        image, _thumb = pending
        win = self.selected
        if (answer == "start" and whole and win is not None and not self.reading and self.batch is None
                and self._page_uncached(image)):
            self.say("Whole-book mode: this page is not translated yet. Turn the pages at your own pace: TASlation reads each page you turn, and translates the book when you press Finished reading. Stop ends the run.")
            self._resume_auto = True
            options = (win, 0, self.settings.context_mode)
            if self.ready and not self.busy:
                self._start_batch(*options)
            else:
                self._queue("batch", *options)
            return
        self._translate_pending(pending)

    def _translate_pending(self, pending: tuple[Image.Image, np.ndarray | None]) -> None:
        """The page that waited for a book's start, translated now (or once the job that runs is done)."""
        image, thumb = pending
        if self.ready and not self.busy and self.batch is None:
            self._start_translate(image, thumb=thumb)
        else:
            self._auto_last = None  # Auto takes the page again once it can
            self._queue("auto")

    # ------------------------------------------------------------------ the colophon's name for the book
    def _offer_colophon(self) -> None:
        """The colophon found on a page of the book (`_colophon_found`): when the Book box holds another name than
        the colophon's - typed, generic, or the window title's - its name is offered once per book, [Use] [Keep]
        (`ColophonOffer`). While nothing is kept under the book's name, Use only puts the colophon's name into the
        Book box; with files kept under it (a cache with pages or the reader's annotations, also an old cache kept
        under a name that names no book), the offer asks to rename the book, and Use moves its translations,
        annotations, series sheet and notes to the new name (`_plan_rename`: where the new name's series has a sheet
        that says otherwise, after the review; `_rename_book`). Keep leaves the name. The colophon's
        details go into the header of the cache of the name the book ends up with (`_keep_details`, or the rename
        itself), which keeps the offer from being made again in a later session. It waits while reading mode, a
        dialog of the start or a batch is on."""
        from .banner import break_lines
        from .dialogs.start import WRAP
        from .layout import place_window

        found = self._colophon_found
        if found is None or self.reading or self._start_dialog is not None or self._batching or self.batch is not None:
            return
        self._colophon_found = None
        book, model, language, col = found
        current = self.book_var.get().strip()
        if book != current or not col.title:
            return  # read for a name the Book box no longer holds
        if same_book_name(col.name, current):
            self._keep_details(current, model, language, col)
            return
        if current in self._colophon_asked:
            return
        self._colophon_asked.add(current)
        generic = generic_book_name(current)
        if not generic and identity_of(self.store, current, language):
            return  # offered in an earlier session: the cache's header has the colophon's details
        rename = self._kept_under(current)
        offer = ColophonOffer(self, col.title, col.volume,
                              lambda use: self._colophon_answer(use, current, model, language, col, rename))
        self._start_dialog = offer
        label = getattr(offer, "label", None)
        if rename and label is not None:  # the question is the rename's
            if col.volume:
                question = _("The last page of the book says this is {title} ({volume}). Rename {book} to it? Its translations, notes and sheet move along.")
            else:
                question = _("The last page of the book says this is {title}. Rename {book} to it? Its translations, notes and sheet move along.")
            label.configure(text=break_lines(question.format(title=col.title, volume=col.volume, book=current), WRAP,
                                             label))
            place_window(offer, self)  # centred again, with its new size

    def _colophon_answer(self, use: bool, book: str, model: str, language: str, col: Colophon,
                         rename: bool = False) -> None:
        """The colophon's name offered: Use renames the book's files kept under the old name (*rename*:
        `_plan_rename`; the Book box follows once they have moved), or puts the name into the Book box when nothing
        was kept; Keep leaves the name. The details go to the cache of the name the book ends up with. A start that
        waited goes on (after the rename). The name used is the viewer's last book too (`_remember_viewer_name`)."""
        self._start_dialog = None
        if use and rename:
            self._plan_rename(book, col.name, model, language, col)
            return
        target = book
        if use:
            target = col.name
            self._book_named(target)
            self.book_var.set(target)
            self._book_edited = True
            self._colophon_asked.add(target)
            self._remember_viewer_name(target)
            self.say("This book is now called {book}.", book=target)
        self._keep_details(target, model, language, col)
        self._resume_start()

    def _plan_rename(self, old: str, new: str, model: str, language: str, col: Colophon) -> None:
        """Before the book *old* is renamed to *new*, the colophon's name: the rename's plan (`rename.plan_rename`,
        on the Tk thread: every check made, the book's files and the new series' sheet read, nothing
        written; 20 to 75 ms for two caches of 200 pages). A rename that cannot be made is said, and the book keeps
        its name. Where the book's series sheet says otherwise than the sheet the new
        name's series has already, the Translator role's review asks first (`RenameReviewDialog`, kept as the start's
        dialog so that a start that waits goes on afterwards): Rename renames with the answers, Cancel keeps the name -
        nothing of the colophon kept, so that it is offered again in a later session. In the Reader role each conflict
        takes the review's own first choice, unasked. Otherwise the book is renamed at once, what its sheet adds joining
        the new series' as it is (`_rename_book`)."""
        from ..rename import RenameRefused, Stores, plan_rename

        stores = Stores(self.store, self.annotation_store, self.glossary_store)
        try:
            plan = plan_rename(stores, old, new)
        except (RenameRefused, OSError) as e:
            self.say("{book} was not renamed: {error}", book=old, error=message_of(e))
            self._resume_start()
            return
        except Exception:  # noqa: BLE001 - said in the status line; the book keeps its name
            LOG.exception("the rename was not planned")
            self.say("{book} was not renamed: {error}", book=old, error=_("Something went wrong; nothing was changed."))
            self._resume_start()
            return
        if not plan.conflicts or self.role_var.get() != "translator":
            self._colophon_asked.add(new)
            self._rename_book(old, new, model, language, col, {key: c.take for key, _language, c in plan.keyed()})
            return

        def rename(answers: dict[tuple[str, ...], bool]) -> None:
            self._start_dialog = None
            self._colophon_asked.add(new)
            self._rename_book(old, new, model, language, col, answers)

        def keep() -> None:
            self._start_dialog = None
            self.say("{book} keeps its name; the name on the last page of the book is offered again next time.", book=old)
            self._resume_start()

        self._start_dialog = RenameReviewDialog(self, plan, on_apply=rename, on_cancel=keep)

    def _rename_book(self, old: str, new: str, model: str, language: str, col: Colophon,
                     answers: dict[tuple[str, ...], bool] | None = None) -> None:
        """Rename the book *old* to *new*, the colophon's name (`rename.rename_book`, with the review's *answers*), in
        the worker: its caches, annotations and series sheet move (or join the new series' sheet),
        the colophon's details go into the renamed cache, and the pipeline takes the renamed files
        (`_follow_rename`). Meanwhile the window is busy, so no page is read under the old name; the outcome comes
        back as a "renamed" event (`_book_renamed`)."""
        from ..rename import RenameRefused, Stores, rename_book

        stores = Stores(self.store, self.annotation_store, self.glossary_store)
        details, language = col.details(), language.strip() or "English"
        answers = dict(answers or {})
        self._go_busy()
        self.say("Renaming {book} to {name}...", book=old, name=new)

        def job() -> None:
            result, error = None, ""
            try:
                try:
                    cache = getattr(self.pipeline, "cache", None)
                    if cache is not None and cache.book == old and cache.dirty:
                        cache.save()  # what the pipeline changed and has not saved yet moves along
                    result = rename_book(stores, old, new, language, details=details, answers=answers)
                except (RenameRefused, OSError) as e:
                    error = message_of(e)
                except Exception:  # noqa: BLE001 - said in the status line; the book keeps its name
                    LOG.exception("the rename failed")
                    error = _("Something went wrong; nothing was changed.")
                if result is not None:
                    try:
                        self._follow_rename(old, new, model, language)
                    except Exception:  # noqa: BLE001 - the next page takes the book's stores anew (`_ensure_cache`)
                        pass
            finally:
                self._post("renamed", old=old, new=new, result=result, error=error)
                self._post("translate_done")

        self._jobs.put(job)

    def _follow_rename(self, old: str, new: str, model: str, language: str) -> None:
        """In the worker, once the book's files have moved: when the pipeline holds the old name's stores (its cache,
        its annotations), it takes the new name's instead - the cache, the annotations, the series sheet (the joined
        one, where the new series had a sheet already) (`_ensure_cache`, `_job_refresh_premises`) - so
        that nothing is saved under the old name again."""
        pipeline = self.pipeline
        if pipeline is None:
            return
        cache, annotations = pipeline.cache, getattr(pipeline, "annotations", None)
        if cache is not None and cache.book == old:
            pipeline.set_cache(None)
            self._ensure_cache(new, cache.model or model, cache.language)
        elif annotations is not None and getattr(annotations, "book", None) == old:
            self._job_refresh_premises(new, language)

    def _book_renamed(self, data: dict[str, Any]) -> None:
        """The rename's outcome (`_rename_book`): the Book box takes the new name (unless another was typed
        meanwhile) and the status line says what moved - and what joined the new series' sheet (added, taken from
        this book, kept as the series had them) -, or why nothing did: the book keeps its
        name, and nothing of the colophon is kept, so that its name is offered again in a later session. A start
        that waited goes on."""
        old, new, result = data["old"], data["new"], data.get("result")
        if result is None:
            self.say("{book} was not renamed: {error}", book=old, error=data.get("error") or "?")
        else:
            if self.book_var.get().strip() == old:
                self._book_named(new)  # the title's name renamed to the colophon's: what that says of the title
                self.book_var.set(new)
                self._book_edited = True
            if self._scanned_book == old:
                self._scanned_book = new
            self._colophon_asked.add(new)
            self._remember_viewer_name(new)
            counts = {"book": new, "caches": result.caches, "marks": result.annotations, "sheets": result.sheets}
            left = list(result.left)
            sheets_merged = int(getattr(result, "sheets_merged", 0) or 0)  # joined the new series' sheet
            joined = {"series": result.new_series, "added": getattr(result, "added", 0),
                      "taken": getattr(result, "taken", 0), "kept": getattr(result, "kept", 0)}

            def moved() -> str:  # in the window's language, also after a switch
                line = _("This book is now called {book}. Moved along: {caches} translation file(s), {marks} file(s) of page marks, {sheets} series sheet file(s).").format(**counts)
                if sheets_merged:
                    line += " " + _("The series sheet joined the sheet of {series}: {added} added, {taken} taken from this book, {kept} kept as the series had them.").format(**joined)
                if left:
                    line += " " + _("{count} old file(s) could not be deleted and are still there: {files}").format(
                        count=len(left), files=", ".join(left))
                return line

            self.status(moved)
        self._resume_start()

    def _carry_colophon(self, before: str, name: str) -> None:
        """A name given (at a book's start, or asked for) while a colophon read under the old name, one that names
        no book, waits to be offered: the start dialog offered the colophon's name already, so it is not offered
        again, and its details go to the cache of the name given."""
        found = self._colophon_found
        if found is None or found[0] != before or not generic_book_name(before) or generic_book_name(name):
            return
        self._colophon_found = None
        self._colophon_asked.add(name)
        self._keep_details(name, found[1], found[2], found[3])

    def _kept_under(self, book: str) -> bool:
        """Whether anything is kept under *book* already: a cache with pages (in any language) or the reader's
        annotations (a whole-book scan keeps the sequence of the pages there)."""
        try:
            if any(entry.book == book and entry.pages for entry in self.store.identities()):
                return True
            return self.annotation_store.path_for(book).is_file()
        except OSError:
            return True  # a file that cannot be read now: something is kept, for all anyone can tell

    def _keep_details(self, book: str, model: str, language: str, col: Colophon) -> None:
        """The colophon's details into the header of *book*'s cache in *language* (`BookCache.set_details`), in the
        worker; never for a name that names no book, nor with the cache off."""
        if generic_book_name(book) or not self.settings.cache_enabled:
            return
        details, language = col.details(), language.strip() or "English"

        def job() -> None:
            current = getattr(self.pipeline, "cache", None)
            try:
                if current is not None and current.book == book and language_key(current.language) == language_key(language):
                    cache = current
                else:
                    cache = self.store.open(book, model, language)
                if cache.set_details(**details):
                    cache.save()
            except OSError:  # a file that cannot be opened now: the details are kept the next time
                pass

        self._jobs.put(job)

    # ------------------------------------------------------------------ Stop and Esc
    def _set_stop(self, enabled: bool) -> None:
        """Stop (the toolbar's) works while a batch runs or a page is translated."""
        button = getattr(self, "stop_btn", None)
        if button is not None:
            button["state"] = "normal" if enabled else "disabled"

    def _sync_stop(self) -> None:
        cancel, queued = self._page_cancel, getattr(self, "_queued", None)
        self._set_stop(bool(self._batching or (cancel is not None and not cancel.is_set())
                            or (queued is not None and queued[0] == "batch")))

    def _on_escape(self) -> None:
        if self._cancel_drag():  # a region being dragged, turned or drawn: back as it was
            return
        if self.reading:
            self.leave_reading()
            return
        if self._ordering is not None:
            self._end_order()
            self.say("Reading order cancelled.")
            self._redisplay()
            return
        if self._chosen_region is not None:
            self._choose(None)
            return
        if in_a_run(self):  # a key alone never ends a run: the question comes first, however little was read
            self._ask_stop()
            return
        self.stop_batch()

    def stop_batch(self, confirmed: bool = False) -> None:
        """Stop (Esc): the batch ends (a request in progress at once; nothing of it is cached), a batch that waits
        for the models or for a job does not start, or the page being translated is cancelled (nothing of it is
        cached). A whole-book run that holds more than `FEW_PAGES` pages read asks first (`_ask_stop`), unless that
        question was answered already (*confirmed*)."""
        queued = getattr(self, "_queued", None)
        if queued is not None and queued[0] == "batch":
            self._queued = None
            self._resume_auto = False
            if not self.busy:  # (the models were loading: nothing waits for them now)
                self._hide_busy()
                self._show_progress(False)
            self.say("The batch that was waiting is cancelled.")
            self._sync_stop()
            return
        if self.batch is not None or self._batching:
            if not confirmed and self._stop_asks():
                self._ask_stop()
                return
            if self.batch is not None:
                self.batch.stop()
            else:
                self._batch_stop_asked = True  # the batch's reader is not made yet: it stops at once
            self.say("Stopping the whole-book run...")
            return
        cancel = self._page_cancel
        if cancel is not None and not cancel.is_set():
            self._cancel_why = "stop"
            cancel.set()
            self._sync_stop()

    def _run_pages(self) -> int:
        """The pages the run on show holds read or waiting to be read (none: no run)."""
        scan = getattr(self, "_scan", None)
        return int(scan.pages) + int(scan.queued) if scan is not None else 0

    def _stop_asks(self) -> bool:
        """Whether Stop asks before it ends the run: a whole-book run (read first, translated after) that holds more
        than `FEW_PAGES` pages read. A page-by-page run has saved every page it translated."""
        scan = getattr(self, "_scan", None)
        return scan is not None and scan.context and self._run_pages() > FEW_PAGES

    def _ask_stop(self) -> None:
        """The question before Stop ends a run (`dialogs.stop.ask_stop`, TASlation's own box over the window): what
        Stop leaves, and a button for each way on - Keep reading (or translating) first, the answer to Esc and
        Return. While the pages are read it also offers to translate the pages read so far (`finish_reading` with
        *partial*: the run goes on to the translation, and a later run reads on from the page on show) instead of
        dropping them. Nothing happens when the run ended while the box was open."""
        if self._stop_asking:
            return
        scan = getattr(self, "_scan", None)
        pages = group_digits(self._run_pages())
        keep = ("keep", _("Keep reading"))
        if scan is None or not scan.context:
            text, choices = _("Stop the run? The pages translated so far are saved."), [keep, ("stop", _("Stop"))]
        elif not scan.scanning:
            text = _("Stop the translation? {done} of {total} lines are translated and saved; they stay. The rest is kept only until you close TASlation: Read whole book... translates it then.").format(
                done=group_digits(scan.checked), total=group_digits(max(scan.found, scan.checked)))
            choices = [("keep", _("Keep translating")), ("stop", _("Stop"))]
        elif scan.finishing:
            text = _("Stop the whole-book run? You pressed Finished reading: {pages} page(s) are read, and the translation comes next. If you stop now, nothing is translated, and what was read is kept only until you close TASlation.").format(pages=pages)
            choices = [keep, ("stop", _("Stop without translating"))]
        elif self._run_pages() == 0 or self.batch is None:
            text, choices = _("Stop the whole-book run? No page is read yet."), [keep, ("stop", _("Stop"))]
        else:
            text = _("Stop the whole-book run? {pages} page(s) are read, and nothing is translated yet.\n\nTranslate the pages read: they are translated now, and a later run reads on from the page on show.\nStop without translating: what was read is kept only until you close TASlation.").format(pages=pages)
            choices = [keep, ("stop", _("Stop without translating")), ("translate", _("Translate the pages read"))]
        self._stop_asking = True
        try:
            answer = ask_stop(self, text, choices)
        finally:
            self._stop_asking = False
        if not in_a_run(self):  # the run ended meanwhile: nothing is left to stop
            return
        if answer == "stop":
            self.stop_batch(confirmed=True)
        elif answer == "translate":
            self.finish_reading(partial=True)

    def finish_reading(self, partial: bool = False) -> None:
        """Finished reading (the band): the reader has come to the end of the book. The run reads the page on show and
        what waits, then goes on to the translation (`BatchReader.finish`). *partial*: the question before Stop chose
        to translate the pages read so far, and the reading does not count as the whole book."""
        if self.batch is None:
            return
        if partial:
            self.batch.finish(partial=True)
        else:
            self.batch.finish()
        if self._scan is not None:
            self._scan.finishing = True
            self._show_band()
        if partial:
            self.say("The pages read so far are translated now. Afterwards Read whole book... reads on from the page on show.")

    def translate_readings(self) -> None:
        """The band's Translate the pages read (Translate the rest), after a Stop: a run of the book that goes on from
        what the stopped run read and did not store (`Readings`), with no page to turn - it takes the page on show and
        goes on to the translation (`_job_batch` *at_once*); readings of the whole book are translated as they are."""
        book, model, language = self.book_var.get().strip(), self.model_var.get().strip(), self.lang_var.get().strip()
        readings = self._left_readings(book, model, language)
        if readings is None or in_a_run(self):
            return
        if self.busy:
            self.say("A job is running: wait for it to end, or press Stop.")
            return
        win = self._current_window()
        if win is None:
            return
        if self.ready:
            self._start_batch(win, 0, True, at_once=not readings.complete)
        else:  # the models are still loading: the batch starts once they are
            self._queue("batch", win, 0, True, not readings.complete)

    # ------------------------------------------------------------------ actions
    def translate_now(self) -> None:
        """Translate (F5): the page in the viewer read and translated now (from the cache when it is there),
        whether or not Auto has taken it. While the models load or a job runs it waits, and runs after. A viewer
        not read yet has its window enlarged first (`_enlarge_first`). A Book box that names no book gets its name
        first (`_ask_name`; not over the reading window, where the page is translated and nothing of it kept)."""
        if not self.ready or self.busy:
            self._queue("translate")
            return
        win = self._current_window()
        if win is None:
            return
        if not self._book_in_front():
            self._say_waiting()  # the live view's line: bring the tab back, or give it a window of its own
            return
        if not self._enlarge_first(self.translate_now):
            return
        try:
            image = self._capture(win.hwnd)
        except CaptureError as e:
            self._capture_failed(e)
            return
        thumb = thumbnail(image)
        if not self.reading and generic_book_name(self.book_var.get()):  # `_name_needed`: the name first
            self._show_live(image, thumb)
            self._ask_name(lambda _name: self.translate_now(), image)
            return
        self._auto_last = thumb
        self._auto_candidate = None
        self._show_live(image, thumb)
        self._start_translate(image, thumb=thumb)

    def _queue(self, kind: str, *args: Any) -> None:
        """A request that cannot run yet - "translate" (F5), "auto" (Auto's new page) or "batch" (with its
        options) - waits, and runs as soon as the models are loaded and no job runs (`_run_queued`); a later one
        takes its place unless it ranks lower. While the models load, the busy band says so."""
        if self._queued is not None and QUEUE_RANK[kind] < QUEUE_RANK[self._queued[0]]:
            return
        self._queued = (kind, args)
        if not self.ready and not self.busy:
            if not self._busy_shown:
                self._busy_since = time.monotonic()
            self._progress = LOADING
            self._busy_shown = True
            self.canvas.set_busy(self._busy_text)  # the badge says the models are loading
            self._show_progress(True)
        self._sync_stop()  # a batch that waits can be stopped

    def _run_queued(self) -> None:
        """The request that waited, carried out now that it can be."""
        if self._queued is None or not self.ready or self.busy or self.batch is not None:
            return
        kind, args = self._queued
        self._queued = None
        self._hide_busy()
        self._show_progress(False)
        if kind == "batch":
            self._start_batch(*args)
        elif kind == "translate":
            self.translate_now()
        else:  # Auto: the page in front is looked at again at once
            self._tick()

    def _start_translate(self, image: Image.Image, complete: bool | None = None, thumb: np.ndarray | None = None,
                         again: Any = None) -> None:
        """The page *image* read and translated in the worker; Stop and Esc cancel it, and so does a new page Auto
        sees meanwhile (`_watch_page`). A black frame is no page: nothing is read from it. *again*: `_job_translate`."""
        if is_black(image, self.settings.margins):
            self.say(VIEWER_BLACK if getattr(getattr(self, "_black_watch", None), "told", False)
                     else VIEWER_LOADING)
            return
        self._go_busy()
        self._job_frame, self._job_thumb, self._job_area = image, thumb, None  # the page fills in on this frame
        self._page_cancel = cancel = threading.Event()
        self._cancel_why = ""
        self._watch_candidate = None
        self._watch_due = time.monotonic() + self.settings.auto_interval_ms / 1000.0
        self._sync_stop()
        self.say("Looking at the page...")  # (a page from the cache is only looked at: "Translating..." once it is read)
        book, model, language = self.book_var.get().strip(), self.model_var.get().strip(), self.lang_var.get().strip()
        if complete is None:
            complete = self.role_var.get() == "translator"
        self._jobs.put(lambda: self._job_translate(image, book, model, language, complete, cancel, again))
        pump_soon(self)

    def _area_of(self, image: Image.Image) -> np.ndarray:
        """The thumbnail of *image*'s capture area (the margins)."""
        box = area.margins_to_box(tuple(self.settings.margins), image.size)
        whole = box == (0, 0, image.width, image.height) or box[2] <= box[0] or box[3] <= box[1]
        return thumbnail(image if whole else image.crop(box))

    def _turned_from_job(self, image: Image.Image, thumb: np.ndarray) -> bool:
        """Whether the viewer's frame *image* (*thumb*: its thumbnail) shows a new page that has settled while a page
        is translated: its capture area unlike the page being translated (`_job_frame`), and alike with the frame
        of the look before (`_watch_candidate`; on one look alone the page may still be turning)."""
        frame = self._job_frame
        if frame is None:
            return False
        if self._job_area is None:
            self._job_area = self._area_of(frame)
        if image.size == frame.size and not frames_differ(self._job_area, self._area_of(image)):
            self._watch_candidate = None  # still the page being translated
            return False
        if self._watch_candidate is not None and not frames_differ(self._watch_candidate, thumb, 0.5):
            return True
        self._watch_candidate = thumb
        return False

    def _watch_page(self, now: float | None = None) -> None:
        """While a page is translated with Auto on: every auto_interval_ms a look at the viewer; a new page there
        (its capture area unlike the page being translated, alike on two looks) cancels the translation, and Auto
        takes the new page as soon as the job is gone (`_tick`, at once: it is its candidate already). With follow =
        "events" it looks only while the viewer itself is in front (its own page turns): otherwise a page is turned
        by TASlation's own operations, whose follow cancels the job itself (`_take`, `_cancel_page`), by the wheel
        over the viewer while TASlation is in front, whose look does (`_look_over_job`), or not at all while neither
        window is in front - a look then would capture for nothing. Whether a frame shows a new page is
        `_turned_from_job`'s."""
        cancel = self._page_cancel
        if cancel is None or cancel.is_set() or self.batch is not None or not self.auto_var.get():
            return
        if (self._follows_events() and self._following.owner != "viewer") or self._black_open():
            return
        now = time.monotonic() if now is None else now
        if now < self._watch_due:
            return
        self._watch_due = now + self.settings.auto_interval_ms / 1000.0
        win, frame = self.selected, self._job_frame
        if win is None or frame is None or not self._book_in_front():
            return
        try:
            image = self._capture(win.hwnd)
        except CaptureError:
            return
        thumb = thumbnail(image)
        if self._drew_nothing(thumb):  # the viewer drew nothing
            return
        if self._turned_from_job(image, thumb):
            self._auto_candidate = thumb  # settled: Auto takes it once the job is gone
            self._cancel_why = "page"
            cancel.set()
            self._sync_stop()
            self._queue("auto")

    def scan_mode(self) -> str:
        """How Auto starts a book, from the settings (`scan_mode`, `gui --mode`): "book" or, the default, "page"."""
        return "book" if self.settings.scan_mode == "book" else "page"

    # ------------------------------------------------------------------ the batch
    def open_batch_dialog(self) -> None:
        """Batch: read whole book...: its options, then the batch; its Start asks for the book's name first while
        the Book box names none (`_ask_name`: nothing of the batch could be kept)."""
        if self.busy:
            self.say("A job is running: wait for it to end, or press Stop.")
            return
        win = self._current_window()
        if win is None:
            return

        def start(options: tuple[Any, ...]) -> None:
            if self._name_needed():
                self._ask_name(lambda _name: start(options), getattr(self, "_live", None))
                return
            if self.ready and not self.busy:
                self._start_batch(*options)
            else:  # the models are still loading: the batch starts once they are
                self._queue("batch", *options)

        carried_on, readings = "", None
        if getattr(self, "_readings", None) is not None:
            readings = self._left_readings(self.book_var.get().strip(), self.model_var.get().strip(),
                                           self.lang_var.get().strip())
        if readings is not None:
            carried_on = (_("You finished reading the whole book: Start translates the rest.")
                          if readings.complete else
                          _("Pages read before you stopped are kept: Start goes on from the page on show."))
        BatchDialog(self, win, self.settings, on_start=start, carried_on=carried_on)

    def _start_batch(self, win: WindowInfo, max_pages: int, context_mode: bool, at_once: bool = False) -> None:
        """The run starts on the viewer as the reader has set it: no key goes to it, and its window stays as it is, so
        that the band and its buttons stay in view - but for a window minimised since it was chosen, which Start (the
        reader's own action) shows again behind TASlation's window (`viewers.show_minimised`). A window being enlarged
        for the page on show is waited for. *at_once*: `_job_batch`'s (`translate_readings`)."""
        if show_minimised(self, win):
            self.status(lambda: _(VIEWER_RESTORED).format(title=win.title))
        self._go_busy()
        self._batching = True
        self._batch_stop_asked = False
        self._auto_before_batch = bool(self.auto_var.get())
        self._scan = ScanState(context=context_mode, seed=self._pace(self.model_var.get().strip()))
        self._band = None  # the band comes with the scan's first message
        self._show_band()
        new_run(self)  # the page strip starts empty
        self._sync_stop()
        self.auto_var.set(False)
        book, model, language = self.book_var.get().strip(), self.model_var.get().strip(), self.lang_var.get().strip()
        self._batch_for = (book, model, language)
        self.say("Whole-book run starting...")
        own = (self._own_hwnd(),) if IS_WINDOWS else ()  # taken here: the worker must not ask Tk

        def begin() -> None:
            self._apply_found_margins(starting=True)  # the page as the viewer shows it
            run_area = self._run_area()  # (the run widens it with the pages it takes: `page_area.JoinedArea`)
            self._jobs.put(lambda: self._job_batch(win.hwnd, book, model, language, max_pages, context_mode,
                                                   title=win.title, own_windows=tuple(h for h in own if h),
                                                   at_once=at_once, page_area=run_area))

        waiting = getattr(self, "_enlarging", None)
        if waiting is not None:
            waiting["then"] = begin
        else:
            begin()

    def review_names(self) -> None:
        """The band's Review names... and Tools > Names rendered in more than one way...: the names the latest
        whole-book run of the book in the boxes rendered in more than one way, to make one (`name_check`)."""
        name_check.review_names(self)

    def _book_start(self, book: str) -> str:
        """The start dialog's answer kept for *book* ("start", "page"; "" when none is)."""
        try:
            kept = load_ui_table(self.settings.state_dir, BOOK_STARTS).get(book, "")
        except OSError:
            return ""
        return kept if kept in ("start", "page") else ""

    def _keep_book_start(self, book: str, answer: str) -> None:
        try:
            save_ui_entry(self.settings.state_dir, BOOK_STARTS, book, answer, keep=BOOK_STARTS_KEPT)
        except OSError:  # (a state folder that cannot be written: the dialog asks again next time)
            pass

    def _pace(self, model: str) -> float | None:
        """Lines a second the last whole-book translation with *model* did (ui.json table `PACE_TABLE`): where the
        band's estimate starts. None when no run measured one."""
        try:
            value = float(load_ui_table(self.settings.state_dir, PACE_TABLE).get(model, ""))
        except (TypeError, ValueError, OSError):
            return None
        return value if value > 0 else None

    def _keep_pace(self, scan: Any) -> None:
        """The rate of the whole-book translation that ended, kept for the next run with its model, when it can be
        trusted (`ScanState.measured`)."""
        model = (getattr(self, "_batch_for", None) or ("", "", ""))[1]
        rate = scan.measured(time.monotonic()) if scan is not None and scan.context else None
        if not model or rate is None:
            return
        try:
            save_ui_entry(self.settings.state_dir, PACE_TABLE, model, f"{rate:.4f}", keep=PACE_KEPT)
        except OSError:  # (a state folder that cannot be written: the next run measures again)
            pass

    def close_band(self) -> None:
        """The scan band's Close: it goes, and the page strip with it."""
        self._band = None
        self._show_band()
        hide_strip(self)
