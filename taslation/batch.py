"""Batch pre-reading: read the pages a person turns and fill the translation cache.

TASlation never turns a page by itself. The viewer stays in charge of showing the book and the reader of turning its
pages; TASlation only captures what is on screen, reads it and remembers the *translation* keyed by the page's
fingerprint. No key goes to the viewer from here, ever. Page images stay in memory only (`pageimages.PageImages`,
packed without loss, within ``batch_memory_mb``), are never written anywhere and never logged, and go with the next
run or the window closed (`Pipeline.release_page_images`). Reading afterwards is instant: the current screen is
matched against the cache and the stored translations are composited over the live page.

Two modes:

* **Whole book** (default), read first and translated all at once. *Reading*: every page the reader turns is read (the
  capture and the OCR alone: no model request meanwhile); only text and geometry stay (`ScannedUnit`, in memory),
  nothing goes to disk, so nothing of a page can be read until the translation. *Translation*: once the reader says
  the book is done (`finish`), runs of pages (`chunk_bubbles`) are translated once with the series sheet and the whole
  story as context (the translations before them, the Japanese that comes next), and each run is stored as it comes; a
  rendering the series sheet spells otherwise is put right without the model (`terms.rendering_variants`), the review
  flags are set (`Pipeline.review`: no model request), a line left out or answered with the Japanese is asked for
  again, and a line never answered leaves its page `incomplete`. The model writes no notes of its own and reviews
  nothing (removed 2026-11-06): what it is told of the book is the series sheet the reader keeps.
* **Page by page**: translate each page as it is captured, with only the last pages as context.

The reading follows the reader: a thread (`_sample`) watches the viewer's frame, woken by every new frame of the capture
(`capture.frame_wait`; without frame events it looks every `sample_s`), and decides frame by frame which ones are the
pages (`PageWatch`): a picture as it is for settle_ms, or one the reader turned on from after half of that; a viewer
that draws a page soft first has the sharp picture taken, never the soft one. A thread of its own (`_pack_loop`) puts
each page on a backlog for the reading loop (`_iterate_pages`), packed in memory (`pageimages`), so that the sampler
only captures and compares: on the stand-in viewer (`tools/fast_turn_eval.py`, 40 OpenMantra pages) no page is lost
at 2 pages a second, on a viewer that draws every page soft first for 150-400 ms too (blurred, or aliased from a picture
6 times smaller as Chrome draws it: ``--chrome``), and a reader at 3 a second there loses only the pages whose sharp
picture never came before the turn, each said at once. A soft picture and its sharp one are one page by their blurred
thumbnails, within bounds that follow how far apart the run's pages are (`same_page`, `PageWatch.scale`). A page that
went by too quickly to be taken (on show for less than half of settle_ms, or only soft) is said at once (``batch.page_missed``
{pages}, on show until it is taken; ``page_missed``), and taken under its own seq when the reader turns back to it;
the translation then has it in its place. The OCR takes seconds a screen meanwhile: the whole book can wait there. Only when the frames still to read
fill the memory cap (``batch_memory_mb``, at most a quarter of the machine's memory; frames already read, erased pages
and frames waiting for their erase make room first) does the band ask the reader to wait (``batch.backlog_full``), and
the frame on show is taken as soon as there is room. The page on show goes on the window at once (``batch_page``); the
rectangles of the page being read show only when that is the page on show. A page whose fingerprints this run has seen
is skipped, already by the sampler (going back reads nothing twice and changes no order). Nothing here decides that the
book has ended: `finish` (the band's Finished reading, Enter at the command line) lets the backlog drain and goes on
to the translation.

The capture area: a run the window starts follows the page as well as the reader (*page_area*,
`detect.page_area.JoinedArea`). It starts from the window's capture area and the page panels the window has found in
the viewer's frames, and every page the packer takes (a sharper picture of it too) first has the panel found in it
joined in (`find_page_area` on the whole capture, or inside the reader's own area, which stays the outer bound:
`page_area.page_panel`), before anything of the run reads that page (`_meet`). A run started while the viewer shows a
cover alone, centred and narrower than the spreads after it, so reads each spread whole, not the half of each page
nearest the spine that the cover's area held. The area only grows: no page read needs reading again, and a page met
again (the reader went back) is fingerprinted in an area that holds its panel as the first time, so that
`_known`, `_seen_before` and `_read_already` find it. The packer alone widens it, and fingerprints the page in the area
it has just widened (`margins`); the reading loop has each frame read in the area as it is when it starts on it
(`_read_in`: the batch's settings and the pipeline's, `Pipeline.set_margins` - in the window, the window's own), so
that every step of one frame's reading reads one area, and it holds that frame's panel. Frames are compared -
`PageWatch`'s fine detail and crispness, a page that went by against the pages taken - in the area the run started
with, to its end (`_area_box`); the thumbnails that tell two pages apart are of the whole frame: a change of the area
read changes nothing the watch decides, so that it can neither take one page for two nor two pages for one there. The
window is told the panels found and the area read (``page_area``) and joins both into its own record, so that its
capture area once the run is done holds every page the run read, and is never narrower than the run's. The command
line keeps one area for the run (no *page_area*): the margins of its configuration, which it never looks for a page
panel in.

Erased ahead (whole book): once a page is read, a thread of its own (`_erase_ahead`) erases it as the render will
(`Pipeline.erase_page` on the regions ``scan(keep_regions=True)`` gives: the paper fill, LaMa on the art when the
settings have it) and keeps the erased page in memory in its frame's place (`PageImages.put_erased`), for the session
only. The pipeline's render takes a region's erase from there when that very region is on show on that very page
(`Pipeline.erase_key`: the region, the erase's settings, the pixels round it), and erases it itself otherwise
(``Pipeline.erased_ahead``). The erase of the pages read is waited for before the translation
(``batch.erasing_ahead`` {pages}), so that LaMa is done with the GPU before Ollama's model loads
(`Pipeline.gpu_releases`). Translation still starts only when the reader has finished, with the whole book as
context.

Background load: the reading loop and the erase run at a lower thread priority (`lower_priority`, Windows'
BELOW_NORMAL, on the thread itself), and torch computes with all cores but one or two (`torch_threads`), so that the
viewer and the sampler, which stays at the normal priority, keep up with the reader. LaMa waits while pages are being
turned: until `GPU_QUIET_S` without a new frame (`_gpu_wait`, ``Pipeline.gpu_gate``); the OCR, on the CPU, and the
layout model go on (measured in Chrome while 30 pages were turned in 20 s: no frame of the viewer later than 25 ms,
the keydown drawn in 24-29 ms, with the layout model running or waiting; waiting, nothing was read while the pages
were turned). The erase ahead also waits while frames wait to be read (`_reading_first`).

What a window gets, through *show* (kind, data), besides ``batch_page`` {image} and the pipeline's page events:

* ``page_stage`` {seq, fingerprint, stage, state[, thumb]}: a page's way through the run, at every change. *seq* is the
  page's place in the order of first sight in this run (1, 2, ...; a frame without a page unit has none), *fingerprint*
  that of the frame's first page unit, *stage* "read", "erase" or "translate", *state* "waiting", "working", "done",
  "failed" or "skipped". The first event of a page (read waiting, when the sampler takes it) also has *thumb*, a PIL
  image at most `THUMB_HEIGHT` px high made from the frame. Read is "skipped" for a page whose every page unit the cache
  holds already (and a frame that turned out not to be the book), and the later stages say what really becomes of it:
  erase "skipped" where there is nothing to erase or no erase ahead (page by page, the memory full), translate "skipped"
  where there is nothing to translate; translate "failed" for a page a unit of which the translation could not store.
  Read "missed" (no thumbnail: a placeholder) for a page that went by before it could be taken; when the reader turns
  back to it, read "waiting" with its thumbnail follows under the same seq, and a page still missed at the end has its
  other stages "skipped". Read "merged" {into} (no other event of that seq follows): the page that went by was taken
  all the same, as the page *into* (its seq), or is one an earlier run has read (no *into*); its placeholder goes.
  Checked when a page is taken and once more when the reading is over (`_merge_taken_missed`), so that no
  placeholder is left of a page the run has.
* ``page_missed`` {seq, fingerprint, thumb, pages}: a page went by before it could be taken (*thumb* from the picture
  that went by, maybe soft; *pages*: those not taken yet), at the moment the sampler saw it go.
  However the run ends, every stage still open then gets its last event (`_close_stages`): "skipped", or "failed" when a
  failure every later request would repeat ended the run.
* ``batch_memory`` {used_mb, cap_mb}: the page images held, when that changes by 5 % or more (`MEMORY_STEP`).
* ``page_area`` {hwnd, size, found, hand, margins}: a run that follows the reader found page panels in the pages it
  took, their union *found* (in the pixels of a capture of *size*) changed; *hand* the reader's own area (margins) it
  looked inside, None when it looked on the whole capture; *margins* the run's area now, which holds *found* (wider
  than *found* gives when the run read pages without a panel in a wider area before). Told by the packer, before the
  page is read.
* ``translation_page`` {seq, frame, image, waiting}: while the whole-book run translates, the page whose lines the model
  is answering, lettered so far (`translation_view`: the lines answered and not stored yet are provisional, the page
  once stored is the cache's picture exactly; *image* None when its pictures are no longer held). Told by the view's own
  thread, at most every `translation_view.GAP_S`; nothing of it is stored.

Reading is on the viewer only: of the page images this run holds, a window is shown only the page the run works on, as
its progress - the frame on show as it is taken (``batch_page``) and the page being translated (``translation_page``) -,
and nothing of them is handed out otherwise (there is no way to ask for the picture of a page by its seq). The images
stay with the pipeline after the run (``Pipeline.erased_ahead``), for one thing only: the render of a page the viewer
shows takes a region's erase from there (`Pipeline.erase_key`), so that a page turned to again shows sooner; they go
with `Pipeline.release_page_images` (the window closes, another book). A page-by-page run lets go of each frame once
it is translated: nothing needs it after that.

A wait for the reader never ends the pass: a viewer that stays black, a frame that is not the book, a viewer closed are
said (`BatchProgress.waiting`) and the run waits for Finished reading or Stop, and after `manual_wait_s` without a new
page the screen may switch off, nothing else. Only ``batch_max_pages`` ends the pass by itself, as the limit it is.

Stop during the reading ends the run: nothing is translated, the pages read are not stored (the window asks first
once more than a few pages are read, and offers to translate them instead: `finish(partial=True)`, which ends the
reading as Finished reading does, with ``batch.read_so_far`` as its reason, so a later run reads on from the page on
show). Stop during the translation keeps what is stored; a request under way is lost. What was read and not stored is
`BatchReader.left` (`Readings`, in memory only: Japanese text never goes to disk): a window hands it to its next run
of the same book (*readings*), which goes on reading from the page on show, or, when the reader had finished the book,
goes on translating. A run without it (the command line, a window closed) reads those pages again.

What the batch says is a `taslation.messages.Message` (a ``str`` with a ``code``
and ``params``): ``BatchProgress.message`` (the latest; the callback gets each
one), ``BatchProgress.reason`` (why the scan or the batch ended:
``batch.finished_reading`` and the like, or the error that stopped it),
``BatchProgress.notes`` (``batch.note_*``) and ``BatchProgress.summary``, the
last message: ``batch.finished`` {pages, bubbles, seconds, minutes, failed,
error, reason},
``batch.failed_requests`` {failed, reason, pages, seconds}
when requests failed and nothing could be translated, after Stop
``batch.stopped_reading`` {pages, seconds, kept, again} or
``batch.stopped_translating`` {done, total, pages, seconds, kept, again} (page
by page: ``batch.stopped`` {page, pages, bubbles, seconds}), or ``batch.not_started``
{reason}, also when no frame had a page unit (``batch.no_page_seen``: nothing
was read). The first message, ``batch.started``
{problems, problem}, records what the pre-flight check found (`preflight`; the
batch runs regardless, its caller decides). Stop sets the event the pipeline
and the translator are given as ``cancel``: a request to the model ends at
once and nothing of it is cached. Ollama not running or the model missing
ends the translation at the first failed request instead of retrying it; a
cache that cannot be written ends it after the page that found out
(``batch.save_failed``).

Ollama's model is not in memory while the pages are read: the reading pass sends no request, and the first request
of the translation loads it (`OllamaTranslator.ensure_loaded`, which lets the pipeline's GPU models go first); the
requests that follow keep it. Page by page, the first page that needs a translation loads it. However the run ends
(finished, Stop, a failure), its end releases it (`run`).
"""

from __future__ import annotations

import ctypes
import queue
import sys
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import cv2
import numpy as np
from PIL import Image

from . import colophon, fingerprint, health, recovery
from .pageimages import MB, PageImages, memory_cap, pack, undo_of
from .cache import INDEXED_WITHIN
from .capture import (CaptureError, WindowInfo, behind_others, capture_window, client_rect_on_screen, frame_count,
                      frame_wait, frames_come, is_black, is_blank, is_browser_class, screen_shows_own, still_the_book,
                      visible_rect, window_class, window_exists, window_rect, window_shown, window_title)
from .config import Settings
from .detect.page_area import JoinedArea
from .messages import Cancelled, Message, message_of
from .name_variants import RunLine, find_variants
from .notes import series_key
from .regions import region_meta
from .pipeline import EventFn, Pipeline, ScannedUnit, cancel_args, direction_of
from .regions import PageResult
from .terms import rename_text, rendering_variants
from .translate import OllamaTranslator, TranslationError
from .translate import base as _base
from .translate.base import REASK_GROUP, accepts, ask_again_romanised, ask_for_missing, worth_asking_again
from .translate.continuation import facts_of
from .translation_view import TranslationView

# A failed request with one of these means the next ones fail too: the translation ends there instead of
# retrying in halves (Ollama not running, the model missing, no translator).
NO_PAGE = Message("batch.no_page_seen")  # why a batch ended that read no page: no frame had a page unit
FATAL_CODES = frozenset({"ollama.unreachable", "ollama.model_missing", "health.chosen_model_missing",
                         "translator.model_missing", "plamo.cannot_write", "ollama.not_loopback",
                         "pipeline.no_translator"})


def fatal(error: Any) -> bool:
    """Whether the failure *error* (a Message, or the text of one) means that every later request fails too."""
    return getattr(error, "code", "") in FATAL_CODES or any(text in str(error) for text in ("reach the translation program", "cannot reach Ollama"))


@dataclass
class BatchProgress:
    """Where a batch is; every text in it is a `Message` (see the module's docstring).

    *bubbles* is the count shown with the pages: while the pages are read the bubbles found so far, from the translation
    on (and in page-by-page mode) the bubbles done; *found* (the pages') and *translated* (translated by this batch,
    cached ones not counted) keep the two apart. *errors* counts the failed requests (and the replies that could not
    be used), *first_error* says what the first of them was.

    *queued*: the frames waiting to be read. *waiting*: what the run is waiting for from the reader, as long as it does
    (a Message; None while all is well): the window keeps it on show whatever else is said meanwhile.

    *checked* counts the lines the translation pass has stored; *answering* the lines the request under way has
    answered so far, not stored yet (0 between requests: they count in *checked* once stored), told as they come
    when the translator hands each line over (``on_item``: PLaMo line by line, Ollama as its reply streams), so a
    band can move per line. *page_seconds*: how long reading a page with text to translate took, on average (OCR
    and the rest of `Pipeline.scan`; 0 until one is read)."""

    pages: int = 0
    bubbles: int = 0
    cache_hits: int = 0
    errors: int = 0
    elapsed: float = 0.0
    message: str = ""  # the latest Message
    phase: str = ""  # read | translate | done (whole book); translate | done (page by page)
    finished: bool = False
    reason: str = ""  # a Message: why the scan or the batch ended ("" until then)
    seen: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # Messages (batch.note_*)
    found: int = 0
    translated: int = 0
    queued: int = 0
    waiting: Message | None = None
    first_error: Message | None = None
    summary: Message | None = None  # how the batch ended: the last message, once it has
    preflight: list[Message] = field(default_factory=list)  # what was found before the start (empty: all well)
    colophon: Any = None  # the book's colophon (`colophon.Colophon`), once a page read was one
    checked: int = 0
    answering: int = 0
    page_seconds: float = 0.0
    missed: int = 0  # pages that went by before they could be taken, not taken since (``batch.page_missed``)
    # the names the run's lines render in more than one way (`name_variants.find_variants`), and the lines they point
    # into: each line's translation and where it is stored, without its Japanese (`_find_names`)
    names: list[Any] = field(default_factory=list)
    name_lines: list[RunLine] = field(default_factory=list)


ProgressCallback = Callable[[BatchProgress, PageResult | None], None]


@dataclass
class Readings:
    """What a whole-book run read and did not store, for the next run of the book in the same window: never written
    anywhere (Japanese text must not reach the disk). *units*: the page units still to translate, in the book's order;
    *pages*: how far the run got; *complete*: the reader finished the book, so the next run reads no page."""

    units: list[ScannedUnit]
    pages: int = 0
    complete: bool = False


def preflight(settings: Settings, model: str | None = None) -> list[Message]:
    """What stands in the way of a whole-book batch, before it starts: `taslation.health.check` (the OCR model,
    Ollama, the translation model: *model*, by default the one the settings' ``ollama_model`` asks for with their
    target language, `taslation.translate.models`). Messages, empty when all
    is well. The batch runs regardless: the window and the CLI decide; a `BatchReader` given the result as its
    ``preflight`` records it in its first message instead of checking again."""
    return health.check(settings, model)


def thumbnail(image: Image.Image, size: int = 64) -> np.ndarray:
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    return cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)


DETAIL_GRID = 4  # a frame's capture area is looked at in this many cells across and down for its fine detail
DETAIL_FLOOR = 3.0  # a cell with less detail than this (grey levels between neighbouring pixels) is blank
SHARPER = 1.25  # a frame is sharper than another when most of its cells, and all of them together, hold this much more
# Once the viewer has drawn a page soft first in a scan, a later page that has not come sharper and does not look sharp
# (`crispness`) is watched for this long before it is taken as it is (the live view's recheck, `ui.constants.RECHECK_MS`).
RECHECK_MS = 1000
# A picture the reader turned on from is a page when it was on show for STILL_SHARE of settle_ms or more (taken, when it
# is sharp); for GLIMPSE_SHARE or more and less than that, a page went by that could not be taken (``page_missed``);
# shorter, it was a step of the viewer's own drawing (a page sliding in). With settle_ms 400: 200 and 100 ms; a reader
# turning 3 pages a second leaves each on show about 330 ms.
STILL_SHARE = 0.5
GLIMPSE_SHARE = 0.25
# Two frames whose thumbnails differ by no more than `frames_differ`'s 2.0 show one page (a soft picture of it and its
# sharp one differ by 0.3-1.7, two pages of OpenMantra by 28 and more); by no more than this, one picture drawn again.
SAME_PICTURE = 0.5
# One page, a soft picture of it too (`same_page`): thumbnails within `frames_differ`'s 2.0, as ever; or, when one of the
# two holds more detail than the other (`sharper`: a soft picture and its sharp one), thumbnails blurred by PAGE_BLUR px
# (`page_thumb`) within SOFT_SAME_PAGE. What a soft picture loses, and what aliasing adds when a browser draws it from a
# picture several times smaller, is fine detail, which the blur leaves out, while two pages differ in their layout,
# which it keeps. In Chrome (the e2e viewer: a canvas of the page 6 times smaller, enlarged, full screen) a soft picture
# and its sharp one differed by 1.3-2.2 grey levels on the plain thumbnails, more than 2.0 for 2 pages of 10 (each then
# taken as a new page and its soft picture said to have gone by), by 0.3-0.8 blurred; two pages by 7.8 and more blurred.
# Two pages that differ only in a few thin lines (tests/test_batch_guard.py) are 2.8 apart plain and 1.5 blurred: the
# blurred bound alone would take them for one, `sharper` tells them apart. How far apart frames are depends on how much
# of the frame the page fills, so once a run has seen PAGES_LEARNT page changes the blurred bound is SOFT_SHARE of their
# median distance (`PageWatch.scale`). Measured with `tools/fast_turn_eval.py --chrome` (aliased, from 1/6 of the page,
# a quarter worse than Chrome) on 120 OpenMantra pages, framed as the tool frames them and full screen: soft and sharp
# at most 0.16 of the median, two pages at least 0.46; before that (full screen) soft and sharp at most 1.6, two pages
# at least 6.0.
PAGE_BLUR = 1.5
SOFT_SAME_PAGE = 3.5
SOFT_SHARE = 0.27
PAGES_LEARNT = 5
CRISP_SPAN = 4  # px: `crispness` sets the steps between neighbouring pixels against the steps over this many
CRISP_KEPT = 50  # the crispness of so many soft and sharp pictures of the run is what a picture is judged by
# LaMa waits for this long without a new frame: a reader turning on takes 0.5-1.5 s a page (`settle_ms` 400 of it),
# one reading a page looks at it for 5 s and more, and LaMa takes about 0.6 s a screen, a region at a time: the GPU
# works while the reader reads and leaves the viewer alone while the pages are turned
GPU_QUIET_S = 2.0
THUMB_HEIGHT = 96  # px: the thumbnail a page's first `page_stage` event carries
MEMORY_STEP = 0.05  # ``batch_memory`` is told when the images held change by this share
LINE_SAID_S = 0.2  # s: a line the model answers is told (`BatchProgress.answering`) at most this often


def thread_priority() -> int | None:
    """The calling thread's Windows priority (0 normal, -1 below normal; None elsewhere or when it cannot be read)."""
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.GetCurrentThread.restype = ctypes.c_void_p
        kernel32.GetThreadPriority.argtypes = [ctypes.c_void_p]
        value = int(kernel32.GetThreadPriority(kernel32.GetCurrentThread()))
    except Exception:  # noqa: BLE001 - nothing depends on it
        return None
    return None if value == 0x7FFFFFFF else value  # THREAD_PRIORITY_ERROR_RETURN


def set_priority(priority: int) -> bool:
    """Set the calling thread's Windows priority (THREAD_PRIORITY_*: -1 below normal, 0 normal); False elsewhere."""
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.GetCurrentThread.restype = ctypes.c_void_p
        kernel32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        return bool(kernel32.SetThreadPriority(kernel32.GetCurrentThread(), int(priority)))
    except Exception:  # noqa: BLE001
        return False


BELOW_NORMAL = -1  # THREAD_PRIORITY_BELOW_NORMAL


def lower_priority() -> int | None:
    """The calling thread at BELOW_NORMAL priority (a worker of the batch: the OCR, the erase); what it had before."""
    before = thread_priority()
    set_priority(BELOW_NORMAL)
    return before


def torch_threads(cores: int | None = None) -> int:
    """How many threads torch computes with while the batch reads: all cores but two from six on (the viewer drawing
    the next page, the sampler and the window), but one below that, at least one."""
    cores = cores or os.cpu_count() or 1
    return max(1, cores - (2 if cores >= 6 else 1))


def limit_torch_threads(most: int) -> int | None:
    """Torch's intra-op threads held to *most* when torch is in use (imported already: nothing is loaded for it); the
    number it had before, None when it was not changed."""
    torch = sys.modules.get("torch")
    if torch is None:
        return None
    try:
        before = int(torch.get_num_threads())
        if before > most:
            torch.set_num_threads(most)
            return before
    except Exception:  # noqa: BLE001 - its threads are only a matter of speed
        pass
    return None


def restore_torch_threads(before: int | None) -> None:
    torch = sys.modules.get("torch")
    if before is not None and torch is not None:
        try:
            torch.set_num_threads(before)
        except Exception:  # noqa: BLE001
            pass


def thumb_of(image: Image.Image, height: int = THUMB_HEIGHT) -> Image.Image:
    """A thumbnail of *image* at most *height* px high (RGB)."""
    small = image.convert("RGB")
    if small.height > height:
        small = small.resize((max(1, round(small.width * height / small.height)), height), Image.BILINEAR,
                             reducing_gap=2.0)
    return small.copy() if small is image else small


@dataclass(frozen=True)
class _Taken:
    """A frame on the backlog: its key in the run's images, its *seq* (0: no page unit), the fingerprints of its page
    units (the sampler's, used by the reading loop)."""

    key: int
    seq: int
    fps: tuple[str, ...]


def detail(image: Image.Image, box: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """How much fine detail *image* (its part *box*) holds, cell by cell of a DETAIL_GRID x DETAIL_GRID grid: the
    root mean square of the steps in grey levels between neighbouring pixels (along every other row and every other
    column, to be quick). A page drawn from a smaller picture first holds far less of it than the sharp page that
    follows (from half the size: about 2.3 times less on the test pages, from a third 3.3 times), while their
    thumbnails are all but the same; the viewer's toolbar over the page changes it in a few cells only."""
    gray = np.asarray((image.crop(box) if box is not None else image).convert("L"), dtype=np.float32)
    out = np.zeros((DETAIL_GRID, DETAIL_GRID), np.float32)
    h, w = gray.shape[:2]
    if h < 4 * DETAIL_GRID or w < 4 * DETAIL_GRID:
        return out
    across = np.square(np.diff(gray[::2], axis=1))  # row r is the frame's row 2r
    down = np.square(np.diff(gray[:, ::2], axis=0))  # column c is the frame's column 2c
    for i in range(DETAIL_GRID):
        y0, y1 = i * h // DETAIL_GRID, (i + 1) * h // DETAIL_GRID
        for j in range(DETAIL_GRID):
            x0, x1 = j * w // DETAIL_GRID, (j + 1) * w // DETAIL_GRID
            a = across[(y0 + 1) // 2:(y1 + 1) // 2, x0:x1 - 1]
            d = down[y0:y1 - 1, (x0 + 1) // 2:(x1 + 1) // 2]
            out[i, j] = np.sqrt((float(a.mean()) + float(d.mean())) / 2)
    return out


def sharper(before: np.ndarray | None, after: np.ndarray | None) -> bool:
    """Whether the frame whose `detail` is *after* is sharper than the one of *before* (the same page, its sharp
    picture come in): of the cells that are not blank in either, more than half hold SHARPER times more detail, and
    so do they all together. An overlay (the viewer's toolbar) adds detail in a few cells only, noise a little in
    each."""
    if before is None or after is None or before.shape != after.shape:
        return False
    cells = np.maximum(before, after) >= DETAIL_FLOOR
    if not cells.any():
        return False
    b, a = before[cells], after[cells]
    return 2 * int((a >= b * SHARPER).sum()) > int(cells.sum()) and float(a.sum()) >= float(b.sum()) * SHARPER


def frames_differ(a: np.ndarray | None, b: np.ndarray | None, threshold: float = 2.0) -> bool:
    if a is None or b is None or a.shape != b.shape:
        return True
    return float(np.abs(a - b).mean()) > threshold


def page_thumb(thumb: np.ndarray) -> np.ndarray:
    """What `same_page` compares of a frame: its `thumbnail` and the thumbnail blurred by `PAGE_BLUR` px (the page's
    layout without its fine detail), stacked."""
    return np.stack((thumb, cv2.GaussianBlur(thumb, (0, 0), PAGE_BLUR)))


def page_distance(a: np.ndarray, b: np.ndarray) -> float:
    """How far apart two `page_thumb` are, blurred: the mean difference in grey levels."""
    return float(np.abs(a[1] - b[1]).mean())


def same_page(a: np.ndarray | None, b: np.ndarray | None, a_detail: np.ndarray | None = None,
              b_detail: np.ndarray | None = None, scale: float | None = None) -> bool:
    """Whether the frames whose `page_thumb` are *a* and *b* (their `detail`, when known) show one page: their
    thumbnails within `frames_differ`'s bound, or, while one holds more detail than the other (`sharper`: a soft
    picture of the page and its sharp one, however much smaller the soft one was drawn from), blurred within
    `SOFT_SAME_PAGE`; with *scale*, the median distance of the run's page changes (`PageWatch.scale`), within
    `SOFT_SHARE` of it instead."""
    if a is None or b is None or a.shape != b.shape:
        return False
    if not frames_differ(a[0], b[0]):
        return True
    soft = SOFT_SAME_PAGE if scale is None else SOFT_SHARE * scale
    return page_distance(a, b) <= soft and (sharper(a_detail, b_detail) or sharper(b_detail, a_detail))


def crispness(image: Image.Image, box: tuple[int, int, int, int] | None = None) -> float:
    """How crisp the edges of *image* (its part *box*) are, whatever it shows: the mean square step in grey levels
    between neighbouring pixels set against the one over `CRISP_SPAN` pixels (along every other row and column). An
    edge drawn sharp is a step of a pixel or two, one drawn from a smaller picture is spread over several, so a soft
    picture has far less of the first for as much of the second, dense page or sparse: on 40 OpenMantra pages in the
    stand-in viewer the sharp ones measured 0.22-0.34, the same pages drawn from a picture 1.5-3 times smaller
    0.09-0.14 (`tools/fast_turn_eval.py`). A viewer's own scale changes it too, so a run judges a picture only by the
    soft and sharp pictures its viewer has drawn (`PageWatch`)."""
    gray = np.asarray((image.crop(box) if box is not None else image).convert("L"), dtype=np.float32)
    k = CRISP_SPAN
    if gray.shape[0] <= 2 * k or gray.shape[1] <= 2 * k:
        return 0.0
    rows, cols = gray[::2], gray[:, ::2]
    fine = float(np.square(np.diff(rows, axis=1)).mean()) + float(np.square(np.diff(cols, axis=0)).mean())
    wide = float(np.square(rows[:, k:] - rows[:, :-k]).mean()) + float(np.square(cols[k:] - cols[:-k]).mean())
    return fine / wide if wide > 0 else 0.0


TAKE, MISSED, SHARPER_TAKEN = "take", "missed", "sharper"  # what `PageWatch` decides


@dataclass
class _Shown:
    """The picture the viewer has on show, as long as it is one picture: the latest frame of it (the sharpest, once it
    came sharper), its thumbnail, `page_thumb` and `detail`, when it first came (*first*) and since when it has been as
    it is (*since*), whether it came sharper meanwhile, its `crispness` once asked for."""

    image: Image.Image
    thumb: np.ndarray
    page: np.ndarray
    detail: np.ndarray
    first: float
    since: float
    sharpened: bool = False
    crisp: float | None = None


class PageWatch:
    """Which frames of the viewer are the pages the reader turned to, decided frame by frame as they come (no thread,
    no capture, no clock of its own: *now* is given), so that the sampler never sleeps while the reader turns on.

    `see` (a frame, the time it was captured) and `tick` (the time, when no new frame came) give the decisions, in
    order: (`TAKE`, image) the page; (`MISSED`, image) a page that went by before it could be taken; (`SHARPER_TAKEN`,
    image) a sharper picture of the page taken last, which takes its place while it waits to be read. A picture is
    *taken* once it has been as it is for settle_ms, or when the reader turns on from it after `STILL_SHARE` of that.
    The soft-first protection: a viewer that has drawn a page soft first in this run (a sharper picture of it came,
    `sharper`) has a page taken only once it came sharper, or looks sharp by the run's own measure (`crispness` nearer
    the sharp pictures than the soft ones its viewer drew), or after *recheck_s* as it is; a page the reader turned on
    from before any of that went by soft, so it is `MISSED`, never taken soft. `due` says when `tick` may decide next."""

    def __init__(self, settle_s: float, recheck_s: float, detail_of: Callable[[Image.Image], np.ndarray],
                 crisp_of: Callable[[Image.Image], float]):
        self.settle_s = max(0.0, settle_s)
        self.recheck_s = max(self.settle_s, recheck_s)
        self.still_s = self.settle_s * STILL_SHARE
        self.glimpse_s = self.settle_s * GLIMPSE_SHARE
        self.detail_of = detail_of
        self.crisp_of = crisp_of
        self.shown: _Shown | None = None  # the picture on show, not taken yet
        self.last: np.ndarray | None = None  # the `page_thumb` of the page taken last
        self.last_detail: np.ndarray | None = None
        self.last_image: Image.Image | None = None
        self.soft_first = False  # the viewer has drawn a page soft first in this run
        self.soft: deque[float] = deque(maxlen=CRISP_KEPT)  # the crispness of the soft pictures it drew ...
        self.sharp: deque[float] = deque(maxlen=CRISP_KEPT)  # ... and of their sharp pictures
        self.apart: deque[float] = deque(maxlen=CRISP_KEPT)  # how far apart (`page_distance`) its pages were
        # the median of *apart* once there are `PAGES_LEARNT` of them (`same_page`'s *scale*): a float, set whole, so
        # that the packer's thread may read it
        self.scale: float | None = None

    def see(self, image: Image.Image, now: float) -> list[tuple[str, Image.Image]]:
        """A frame of the viewer, captured at *now*: what it decides."""
        s = self.shown
        if s is not None and image is s.image or s is None and image is self.last_image:
            return self.tick(now)  # (the very frame again: a viewer that has drawn nothing new)
        thumb = thumbnail(image)
        page, d = page_thumb(thumb), self.detail_of(image)
        if s is not None and same_page(s.page, page, s.detail, d, self.scale):  # the same page (a soft picture of it)
            if sharper(s.detail, d):  # the same page come sharper: this viewer draws soft first
                self._learn(s.image, image)
                s.image, s.thumb, s.page, s.detail, s.since, s.crisp = image, thumb, page, d, now, None
                s.sharpened = True
            elif sharper(d, s.detail):
                pass  # (a softer picture of it again: the sharp one stays the page)
            elif frames_differ(s.thumb, thumb, SAME_PICTURE):  # still being drawn: as it is from now on
                s.image, s.thumb, s.page, s.detail, s.since, s.crisp = image, thumb, page, d, now, None
            else:
                s.image = image  # (drawn again as it was: as it is since it came)
            return self.tick(now)
        out: list[tuple[str, Image.Image]] = []
        if s is not None:
            self.shown = None
            out += self._went_by(s, now)
        if self.last is not None and same_page(self.last, page, self.last_detail, d, self.scale):
            # the page taken last, back (a toolbar gone), or drawn sharper after all
            if sharper(self.last_detail, d) and self.last_image is not None:
                self._learn(self.last_image, image)
                self.last_detail, self.last_image = d, image
                out.append((SHARPER_TAKEN, image))
            return out
        before = s.page if s is not None else self.last
        if before is not None:  # another page: how far apart the pages of this viewer are
            self.apart.append(page_distance(before, page))
            if len(self.apart) >= PAGES_LEARNT:
                self.scale = float(np.median(self.apart))
        self.shown = _Shown(image, thumb, page, d, now, now)
        return out

    def tick(self, now: float) -> list[tuple[str, Image.Image]]:
        """No new frame till *now*: the picture on show is taken when it has been as it is long enough."""
        s = self.shown
        if s is None or now - s.since < self.settle_s:
            return []
        if now - s.since < self.recheck_s and not self._sure(s):
            return []
        return [self._take(s)]

    def due(self, now: float) -> float | None:
        """Seconds until `tick` may take the picture on show (0: it may now); None while nothing is on show."""
        s = self.shown
        if s is None:
            return None
        wait = s.since + self.settle_s - now
        if wait <= 0 and not self._sure(s):
            wait = s.since + self.recheck_s - now
        return max(0.0, wait)

    def take_now(self) -> list[tuple[str, Image.Image]]:
        """The picture on show taken as it is (the reader has finished: the last look)."""
        return [self._take(self.shown)] if self.shown is not None else []

    def _sure(self, s: _Shown) -> bool:
        """Whether *s* is the page as the viewer draws it: no soft picture has been seen in this run, it came sharper,
        or it looks sharp (`_looks_sharp`)."""
        return not self.soft_first or s.sharpened or self._looks_sharp(s)

    def _looks_sharp(self, s: _Shown) -> bool:
        """Whether the `crispness` of *s* is nearer that of the sharp pictures this run's viewer drew than that of its
        soft ones (on a geometric scale). Pages unlike those (a page of text after pages of fine lines) may look soft
        when they are not: such a page is only taken later (`recheck_s`), or said to have gone by, never taken soft."""
        if not self.soft or not self.sharp:
            return False
        if s.crisp is None:
            s.crisp = self.crisp_of(s.image)
        soft, sharp = float(np.median(self.soft)), float(np.median(self.sharp))
        return sharp > soft and s.crisp >= (soft * sharp) ** 0.5

    def _learn(self, soft: Image.Image, sharp: Image.Image) -> None:
        self.soft_first = True
        self.soft.append(self.crisp_of(soft))
        self.sharp.append(self.crisp_of(sharp))

    def _take(self, s: _Shown) -> tuple[str, Image.Image]:
        self.shown = None
        self.last, self.last_detail, self.last_image = s.page, s.detail, s.image
        return TAKE, s.image

    def _went_by(self, s: _Shown, now: float) -> list[tuple[str, Image.Image]]:
        """The reader turned on from *s* (a different picture came at *now*): a page when it was on show long enough,
        taken when it is sure (`_sure`), else missed; a step of the viewer's drawing when it was not."""
        on_show = now - s.first
        if on_show < self.glimpse_s:
            return []
        if on_show < self.still_s or not self._sure(s):
            return [(MISSED, s.image)]
        return [self._take(s)]


def keep_awake(display: bool) -> None:
    """Keep the PC from sleeping while a batch runs (Windows).

    While pages are being captured the display must stay on, otherwise the
    viewer stops repainting; while translating only the system is kept awake,
    so the screen may switch off normally (the batch carries on regardless).
    """
    if sys.platform != "win32":
        return
    try:
        es_continuous, es_system, es_display = 0x80000000, 0x00000001, 0x00000002
        flags = es_continuous | es_system | (es_display if display else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


def release_awake() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


def chunk_units(units: list[ScannedUnit], max_bubbles: int) -> list[list[ScannedUnit]]:
    """Group consecutive page units so each group has about *max_bubbles* bubbles (units are never split)."""
    chunks: list[list[ScannedUnit]] = []
    current: list[ScannedUnit] = []
    count = 0
    for u in units:
        n = len(u.japanese())
        if current and count + n > max_bubbles:
            chunks.append(current)
            current, count = [], 0
        current.append(u)
        count += n
    if current:
        chunks.append(current)
    return chunks


def pid_alive(pid: int) -> bool:
    """Is a process with this id running? (The lock below belongs to a live batch only.)"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == 259  # STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class _Leaving(Exception):
    """The sampler's wait for the viewer ends: Stop, or the reader has finished."""


class ViewerLock:
    """One batch per viewer window: a lock file with the owner's pid under the state directory."""

    def __init__(self, state_dir: Path, hwnd: int):
        self.path = Path(state_dir) / "locks" / f"viewer-{hwnd}.lock"
        self.held = False

    def acquire(self) -> int | None:
        """Take the lock; returns the pid of a live owner when it is taken already."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_file():
                try:
                    owner = int(self.path.read_text(encoding="utf-8").strip() or "0")
                except ValueError:
                    owner = 0
                if owner != os.getpid() and pid_alive(owner):
                    return owner
            self.path.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            return None  # no lock directory: run anyway rather than refuse
        self.held = True
        return None

    def release(self) -> None:
        if not self.held:
            return
        self.held = False
        try:
            if self.path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                self.path.unlink()
        except OSError:
            pass


class BatchReader:
    wait_poll_s = 1.0  # how often to look again while the viewer window shows something other than the book
    viewer_class: str | None = None  # the viewer window's class (None: read from the window when first needed)
    aspect_tolerance = 0.4  # a page unit this far (relative) from the book's usual aspect is not one of its pages
    paper_tolerance = 0.02  # paper this far (share of the capture's size) from where it usually is has moved
    paper_growth = 0.05  # paper reaching this far past where it usually is: a panel opened over the pages
    # the shapes of a page or of a spread whatever the pages so far were (a book's first pages can teach narrow ones)
    book_shape = (0.5, 1.5)
    guard_after_units = 6  # the usual aspect is learnt from this many page units before the guard judges a frame
    manual_wait_s = 3600.0  # no new page for this long: the screen may switch off; the run goes on waiting
    recheck_s = RECHECK_MS / 1000.0  # how long a page not sure to be sharp is watched (`PageWatch`)
    # how often the sampler looks at the viewer without frame events (PrintWindow); with them, it wakes at every new
    # frame and at least this often (Stop, Finished reading, the window's being there)
    sample_s = 0.15
    follow_s = 0.05  # without frame events, how often it looks while a page on show is not taken yet (its sharp picture)
    backlog_size: int | None = None  # at most this many frames waiting to be read (None: as many as the memory holds)
    gpu_quiet_s = GPU_QUIET_S

    def __init__(self, pipeline: Pipeline, hwnd: int, settings: Settings, on_progress: ProgressCallback | None = None,
                 max_pages: int | None = None, context_mode: bool | None = None,
                 book: str = "", series: str = "", title: str = "",
                 query: str = "", retranslate: bool = False, own_windows: Sequence[int] = (),
                 preflight: Sequence[Message] | None = None, show: EventFn | None = None,
                 readings: Readings | None = None, keep_readings: bool = False,
                 page_area: JoinedArea | None = None):
        self.pipeline = pipeline
        self.readings = None if retranslate else readings  # what an earlier run of this book left (`Readings`)
        self.keep_readings = keep_readings  # the caller keeps `left` for its next run (a window that stays open)
        self.left: Readings | None = readings  # what this run leaves: set at its end (`_leave_readings`)
        # a window follows the run (see the module's docstring): show(kind, data) gets ``batch_page`` {image}, the
        # pipeline's page events (`pipeline.PageFill`) and ``progress`` {text}; on the batch's threads
        self.show = show
        self.hwnd = hwnd
        # TASlation's windows (handles): the screen where they are is never read
        self.own_windows = list(own_windows)
        self.retranslate = retranslate  # ignore cached translations: every page is read and translated again
        self.title = title  # the window's title when it was picked ("" = do not check); see still_the_book
        self.query = query
        self.settings = settings
        self.on_progress = on_progress
        self.max_pages = max_pages or settings.batch_max_pages
        self.context_mode = settings.context_mode if context_mode is None else context_mode
        self.book = book
        self.series = series or (series_key(book) if book else "")
        self._stop = threading.Event()  # Stop; also the cancel event of every request the batch makes
        self._finish = threading.Event()  # the reader has finished the book (`finish`)
        self._partial = False  # ... or only wants the pages read so far translated (`finish(partial=True)`)
        self._sampler_off = threading.Event()  # the reading is over: the sampler ends where it is
        self._backlog: queue.Queue[_Taken] = queue.Queue()  # settled frames waiting to be read (`images`)
        # every page image of the run, packed, in memory only (`pageimages`): the backlog's frames, the frames read,
        # the erased pages; for the erase ahead and the page being translated (`translation_view`) while the run works,
        # and kept for the session for the render of a page the viewer shows (`Pipeline.erased_ahead`), nothing else
        self.images = PageImages(memory_cap(settings.batch_memory_mb), on_change=self._memory_changed)
        self._told_memory: tuple[float, float] | None = None  # (used, cap) as last told (``batch_memory``)
        self._seq = 0  # pages seen so far in this run (`_Taken.seq`)
        self._loose = 0  # frames without a page unit so far (their images' keys are negative)
        self._sighted: list[str] = []  # the fingerprints of every frame the sampler put on the backlog
        self._on_show_key: int | None = None  # the images' key of the frame on show, when it went on the backlog
        self._last_change = time.monotonic()  # when the sampler last saw the viewer's frame change (`_gpu_wait`)
        self._stages: dict[int, dict[str, str]] = {}  # seq -> stage -> state, as told (``page_stage``)
        self._fp_of: dict[int, str] = {}  # seq -> the fingerprint its events carry
        self._seq_of: dict[int, int] = {}  # id() of a unit read -> its page's seq
        self._staging = threading.Lock()
        self._erase_jobs: queue.Queue[tuple[int, list[Any]] | None] = queue.Queue()  # (seq, regions) to erase ahead
        self.priorities: dict[str, int | None] = {}  # thread -> its Windows priority, read back on it (for the tests)
        self.gpu_waits = 0  # times GPU work waited for the reader to stop turning pages
        self.erased_pages = 0  # pages erased ahead and kept
        self._told_finished = False  # `batch.finishing` has been said
        self._looked_seq: int | None = None  # the capture session's count of frames at the sampler's last look
        self._on_show: Image.Image | None = None  # the frame taken last: the page the reader has on show
        self._says = threading.RLock()  # the sampler and the reading loop both speak (`_emit`)
        self._line_said = 0.0  # when a line answered was last told (`_answered`)
        self.following = False  # the reading pass is on: the reader's keys go on to the viewer (`ui.live`)
        self._preflight = list(preflight) if preflight is not None else None  # the caller's pre-flight result
        self._fatal: Message | None = None  # a failure that every later request would repeat
        self.progress = BatchProgress()
        self._aspects: list[float] = []  # aspect ratio of every page unit accepted so far
        self._papers: list[tuple[int, int, int, int]] = []  # where the paper was on every frame accepted so far
        self.watch: PageWatch | None = None  # which frames are the pages (the sampler's, while the pages are read)
        self._looked_last = False  # the sampler's last look (the reader has finished) has begun
        # the sampler hands what it decided to the packer (`_pack_loop`): (kind, image), None to end; `_in_hand` counts
        # the frames handed and not on the backlog yet, for the room on it
        self._packing: queue.Queue[tuple[str, Image.Image] | None] = queue.Queue()
        self._in_hand = 0
        self._in_hand_lock = threading.Lock()
        self._last_key: int | None = None  # the images' key of the page the packer took last (a sharper picture's)
        # seq -> (the fingerprints, the `page_thumb`, the `detail`) of a page that went by, not taken yet
        self._missed: dict[int, tuple[tuple[str, ...], np.ndarray, np.ndarray]] = {}
        # (seq, `page_thumb`, `detail`) of every page the packer took (`_taken_before`)
        self._taken_thumbs: list[tuple[int, np.ndarray, np.ndarray]] = []
        self._retaken = False  # a page that went by was taken when the reader went back to it: the order is the seq's
        self._units: list[ScannedUnit] = []  # whole book: the page units read so far that have something to translate
        self._stored: set[int] = set()  # id() of the units of `_units` this run has stored
        # the lines this run stored, by (id() of the unit, region index): the Japanese (in memory only), the text
        # stored and where (`_find_names`)
        self._said: dict[tuple[int, int], RunLine] = {}
        self._read_through = False  # the reader finished the book (in this run or an earlier one)
        # the window's picture of the page being translated (`translation_view`), while the translation pass runs; the
        # run holds `_storing` while it stores a unit, the view while it takes what the cache holds for a page (the
        # cache is not made for two threads; the view letters without the lock)
        self._view: TranslationView | None = None
        self._storing = threading.Lock()
        # the run's capture area when it follows the reader (the window's runs: see the module's docstring), widened
        # by the packer alone with each page it takes (`_meet`); None: one area for the run, the settings' (the CLI)
        self._area = page_area
        # the area frames are compared in (`_area_box`): following the reader, the run's first one to its end
        self._watch_margins = tuple(int(m) for m in page_area.margins) if page_area is not None else None
        self._read_area: tuple[int, ...] | None = None  # the area the reading loop has the pages read in (`_read_in`)
        self.lock = ViewerLock(Path(settings.state_dir), hwnd)

    def stop(self) -> None:
        """End the batch: a request to the model in progress ends at once (nothing of it is cached)."""
        self._stop.set()

    def finish(self, partial: bool = False) -> None:
        """The reader has finished the book (the band's Finished reading, Enter at the command line): the page on show
        is taken, the backlog is read, and the translation follows. The readings count as complete - unless
        *partial*: the reader asked for the pages read so far to be translated before the end of the book
        (``batch.read_so_far``, the window's question before a Stop), so a later run reads on from the page on show."""
        if partial and not self._finish.is_set():
            self._partial = True
        self._finish.set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def _memory_changed(self, used: int, cap: int) -> None:
        """``batch_memory`` {used_mb, cap_mb}, when the images held changed by `MEMORY_STEP` or more."""
        with self._staging:
            told = self._told_memory
            if told is not None and told[1] == cap and (
                    abs(used - told[0]) < MEMORY_STEP * told[0] or (used == told[0])):
                return
            self._told_memory = (used, cap)
        self._show("batch_memory", used_mb=round(used / MB, 1), cap_mb=round(cap / MB, 1))

    def _page_stage(self, seq: int, stage: str, state: str, thumb: Image.Image | None = None) -> None:
        """``page_stage`` for the page *seq*, when its *stage* changes to *state* (see the module's docstring)."""
        if seq <= 0:
            return
        with self._staging:
            states = self._stages.setdefault(seq, {})
            if states.get(stage) == state:
                return
            states[stage] = state
        data: dict[str, Any] = {"seq": seq, "fingerprint": self._fp_of.get(seq, ""), "stage": stage, "state": state}
        if thumb is not None:
            data["thumb"] = thumb
        self._show("page_stage", **data)

    STAGES = ("read", "erase", "translate")
    ENDED = ("done", "failed", "skipped", "missed")

    def _close_stages(self) -> None:
        """The run is over (finished, Stop, a failure): every stage of a page that will never run now gets its last
        ``page_stage``, "failed" when a failure ended the run, else "skipped", so that no page stays unfinished."""
        last = "failed" if self._fatal is not None and not self._stop.is_set() else "skipped"
        with self._staging:
            open_ = [(seq, stage) for seq, states in sorted(self._stages.items()) for stage in self.STAGES
                     if states.get(stage) not in self.ENDED]
        for seq, stage in open_:
            self._page_stage(seq, stage, last)

    def stage_of(self, seq: int, stage: str) -> str:
        """The state of *stage* of the page *seq* as last told ("" before its first event)."""
        with self._staging:
            return self._stages.get(seq, {}).get(stage, "")

    def _gpu_wait(self) -> None:
        """GPU work waits while pages are being turned: until `gpu_quiet_s` without a new frame (``Pipeline.gpu_gate``
        while the pages are read). Stop, and the end of the reading, end the wait."""
        waited = False
        while not self._stop.is_set() and not self._sampler_off.is_set():
            quiet = time.monotonic() - self._last_change
            if quiet >= self.gpu_quiet_s:
                break
            if not waited:
                waited = True
                self.gpu_waits += 1
            self._stop.wait(min(0.05, self.gpu_quiet_s - quiet))

    # ------------------------------------------------------------------ capture helpers
    def _emit(self, message: str, result: PageResult | None = None) -> None:
        with self._says:
            self.progress.message = message
            self.progress.queued = self._backlog.qsize()
            if self.on_progress:
                self.on_progress(self.progress, result)

    def _wait_for_reader(self, message: Message) -> None:
        """The run waits for the reader: *message* stays on show until `_carry_on`."""
        with self._says:
            self.progress.waiting = message
            self._emit(message)

    def _carry_on(self, message: Message | None = None) -> None:
        """The wait for the reader is over."""
        with self._says:
            self.progress.waiting = None
            self._emit(message if message is not None else self.progress.message)

    @property
    def _ended(self) -> bool:
        """The sampler has no more to do: Stop, or the reading is over."""
        return self._stop.is_set() or self._sampler_off.is_set()

    def _left_waiting(self) -> None:
        """A wait for the viewer ends when the reader has moved on."""
        if self._ended or self._finish.is_set():
            raise _Leaving

    def _show(self, kind: str, **data: Any) -> None:
        if self.show is not None:
            self.show(kind, data)

    def _stage(self, message: Message) -> None:
        """Where the pipeline is on the page, for the window's badge."""
        self._show("progress", text=message)

    def _on_slow(self, seconds: float) -> None:
        """The model has said nothing for a while (it may still be loading)."""
        self._emit(Message("ollama.slow", seconds=round(seconds)))

    def _failed(self, error: Message) -> None:
        """A request failed (or its reply could not be used)."""
        p = self.progress
        p.errors += 1
        if p.first_error is None:
            p.first_error = error

    def _shows_book(self) -> bool:
        """Whether the viewer's window shows the book now (`capture.still_the_book`; no title to check: True)."""
        if self.viewer_class is None:
            self.viewer_class = window_class(self.hwnd)
        if not self.title:
            return True
        picked = WindowInfo(self.hwnd, self.title, self.viewer_class, 0, (0, 0, 0, 0))
        return still_the_book(picked, window_title(self.hwnd), self.query, shown=window_shown(self.hwnd))

    def _wait_for_book(self) -> None:
        """Block while the viewer window shows something other than the book (`capture.still_the_book`: a browser
        tab switched away; another viewer's window hidden or minimised - its title changes with every page)."""
        waited = False
        while True:
            if not window_exists(self.hwnd):
                raise CaptureError(Message("viewer.closed"))
            if self._shows_book():
                if waited:
                    self._carry_on(Message("batch.book_back"))
                return
            self._left_waiting()
            if not waited:
                waited = True
                self._wait_for_reader(Message("batch.waiting_other_tab", title=window_title(self.hwnd))
                                      if is_browser_class(self.viewer_class)
                                      else Message("batch.waiting_viewer_hidden"))
            time.sleep(self.wait_poll_s)

    def _capture(self) -> Image.Image:
        """A frame of the viewer that shows something (`_through_black`): nothing above this ever sees a black frame,
        so none is read or cached."""
        image = self._capture_drawn()
        return self._through_black(image) if is_black(image, self.margins) else image

    def _window_size(self) -> tuple[int, int] | None:
        try:
            left, top, right, bottom = window_rect(self.hwnd)
        except CaptureError:
            return None
        return right - left, bottom - top

    def _through_black(self, image: Image.Image) -> Image.Image:
        """The black frame *image* waited out (`recovery`: nothing is pressed): the first frame that shows something,
        whichever page that is. The reader is told that the viewer is still loading, then how to reload the book in its
        own window, and the wait goes on until the reader has brought it back, or has finished or stopped.
        No polling meanwhile: about once a second only whether the capture session delivered a frame, and only such a
        frame is judged. Black behind other windows that says nothing of the viewer (`_capture_once`: None) goes back
        to waiting for it to draw."""
        watch = recovery.BlackWatch(self.hwnd, self.settings, size=self._window_size())
        black, said = True, False
        while True:
            happened = watch.step(black, self._window_size(), time.monotonic())
            if happened == recovery.RECOVERED:
                if said:
                    self._carry_on()
                return image
            if happened == recovery.LOADING:
                said = True
                self._wait_for_reader(Message("batch.viewer_loading"))
            elif happened == recovery.GAVE_UP:
                said = True
                self._wait_for_reader(Message("batch.viewer_black"))
            self._stop.wait(watch.step_s)
            self._left_waiting()
            self._wait_for_book()
            if not watch.new_frame(time.monotonic()):
                continue
            latest = self._capture_once()
            if latest is None:
                if said:
                    self._carry_on()
                return self._capture()
            image = latest
            black = is_black(image, self.margins)

    def _capture_drawn(self) -> Image.Image:
        """A frame of the viewer, once it shows the book. While it draws nothing behind a window of TASlation or of
        another program (a copy of the screen there would be a picture of that window, not a page), the batch waits
        until it draws again."""
        waited = False
        while True:
            self._wait_for_book()
            image = self._capture_once()
            if image is not None:
                if waited:
                    self._carry_on(Message("batch.viewer_draws_again"))
                return image
            self._left_waiting()
            if not waited:
                waited = True
                self._wait_for_reader(Message("batch.waiting_covered" if self.own_windows and self._covered()
                                              else "batch.waiting_behind"))
            time.sleep(self.wait_poll_s)

    def _capture_once(self) -> Image.Image | None:
        """The viewer's frame. The window may sit behind others all the time; a blank frame while a window, TASlation's
        or another program's, lies over the viewer's place is a blank page if the viewer's frames are coming, else
        (None) the viewer draws nothing there, which the reader can change: it is never raised from here."""
        covered = bool(self.own_windows) and self._covered()
        image = capture_window(self.hwnd, allow_screen_fallback=False) if covered else capture_window(self.hwnd)
        if not is_blank(image) or not (covered or behind_others(self.hwnd)):
            return image
        return image if frames_come(self.hwnd) else None

    def _viewer_rect(self) -> tuple[int, int, int, int] | None:
        """The viewer's client area on the screen (left, top, right, bottom); None when it cannot be had."""
        try:
            x, y, width, height = client_rect_on_screen(self.hwnd)
        except CaptureError:
            return None
        return (x, y, x + width, y + height)

    def _covered(self) -> bool:
        """Whether one of TASlation's windows (on the screen) lies over the viewer's client area."""
        viewer = self._viewer_rect()
        if viewer is None:
            return False
        own = [r for r in (visible_rect(handle) for handle in self.own_windows) if r is not None]
        return screen_shows_own(viewer, own)

    @property
    def margins(self) -> tuple[int, int, int, int]:
        """The capture area the run reads a frame in, as it is now: its own when it follows the reader (`_area`, which
        only the packer widens), else the settings'."""
        area = self._area
        return tuple(area.margins if area is not None else self.settings.margins)  # type: ignore[return-value]

    def _area_box(self, image: Image.Image) -> tuple[int, int, int, int]:
        """The part of *image* its frames are compared in (`detail`, `crispness`: `PageWatch`, `_taken_before`,
        `_missed_seq`): the capture area as the pipeline reads it - for a run that follows the reader, the area it
        started with, to its end (`_watch_margins`): the area read may grow between two frames, the area two frames are
        compared in never does (see the module's docstring)."""
        width, height = image.size
        watch = self._watch_margins
        left, top, right, bottom = (max(0, int(m)) for m in (watch if watch is not None else self.settings.margins))
        x0, y0 = min(left, width - 1), min(top, height - 1)
        return x0, y0, max(x0 + 1, width - right), max(y0 + 1, height - bottom)

    def _area_detail(self, image: Image.Image) -> np.ndarray:
        """`detail` of the capture area of *image*."""
        return detail(image, self._area_box(image))

    def _area_crispness(self, image: Image.Image) -> float:
        """`crispness` of the capture area of *image*."""
        return crispness(image, self._area_box(image))

    def _fingerprints(self, frame: Image.Image) -> list[str]:
        """The fingerprints of the page units of *frame* in the run's area as it is now (the packer's: a page taken has
        its panel in it already, `_meet`)."""
        rgb = np.asarray(frame.convert("RGB"))
        return [u.fingerprint for u in fingerprint.analyze(rgb, self.margins)]

    def _still_the_book(self, frame: Image.Image) -> bool:
        """Do the page units of this frame have the aspect ratio the book's pages have had so far?

        A store page, a recommendation, another book opened by a stray click or
        the viewer's own panels look different; the batch must not read and
        translate whatever is on screen. Page units are cropped to
        the ink, so a page of text or a pale drawing (an afterword, the colophon)
        has units of any shape: it is still the book when its paper is where the
        book's pages have been (on a viewer with a dark background). Paper that
        reaches well past where it has been is a panel opened over the pages
        (the viewer's end-of-book panel), which is not read either.
        """
        rgb = np.asarray(frame.convert("RGB"))
        units = fingerprint.analyze(rgb, self.settings.margins)
        aspects = [u.aspect for u in units if u.aspect > 0]
        paper = fingerprint.paper_box(rgb, self.settings.margins)
        if len(self._aspects) >= self.guard_after_units:
            if self._paper_grew(paper, rgb):
                return False
            usual = float(np.median(self._aspects))
            shapes = list(aspects)
            if len(units) > 1:  # a page with a white gutter down its middle is split in two: its whole shape counts too
                x0, y0 = min(u.box[0] for u in units), min(u.box[1] for u in units)
                x1, y1 = max(u.box[2] for u in units), max(u.box[3] for u in units)
                shapes.append((x1 - x0) / max(1, y1 - y0))
            if all(abs(a - usual) / usual > self.aspect_tolerance and not self.book_shape[0] <= a <= self.book_shape[1]
                   for a in shapes) and not self._usual_paper(paper, rgb):
                return False  # nothing on this frame is shaped like the book's pages (a cover alone still is)
        elif not units:
            return False
        self._aspects.extend(aspects)
        if paper is not None:
            self._papers.append(paper)
        return True

    def _paper_grew(self, paper: tuple[int, int, int, int] | None, rgb: np.ndarray) -> bool:
        """Does *paper* reach past where the book's paper has been by more than paper_growth?"""
        if paper is None or len(self._papers) < self.guard_after_units:
            return False
        ux0, uy0, ux1, uy1 = np.median(np.array(self._papers, np.float64), axis=0)
        limit = self.paper_growth * max(rgb.shape[0], rgb.shape[1])
        x0, y0, x1, y1 = paper
        return x0 < ux0 - limit or y0 < uy0 - limit or x1 > ux1 + limit or y1 > uy1 + limit

    def _usual_paper(self, paper: tuple[int, int, int, int] | None, rgb: np.ndarray) -> bool:
        """Is *paper* where the paper of the book's pages has been (place and size, within paper_tolerance)?"""
        if paper is None or len(self._papers) < self.guard_after_units:
            return False
        usual = np.median(np.array(self._papers, np.float64), axis=0)
        limit = self.paper_tolerance * max(rgb.shape[0], rgb.shape[1])
        return all(abs(p - u) <= limit for p, u in zip(paper, usual))

    def _seen_before(self, fps: Sequence[str]) -> bool:
        """Has this run seen every page unit of a frame already (the reader went back, or a page came again)?"""
        return bool(fps) and all(any(fingerprint.hamming(f, seen) <= INDEXED_WITHIN for seen in self.progress.seen)
                                 for f in fps)

    def _sample(self) -> None:
        """The sampler, on a thread of its own while the pages are read: the viewer's frame watched, every new frame as
        it comes (`_look`, `PageWatch`), and what it decided handed to the packer (`_pack_loop`, a thread of its own),
        which puts the pages on the backlog, in memory only: the sampler only captures and compares, so that it keeps up
        with a reader who turns fast. When the reader has finished it looks once more, takes the page on show, and
        ends once the packer has. A failed capture while the window is there is waited out; a viewer gone is said, and
        the run waits for the reader as ever."""
        set_priority(0)  # (normal: no page may be missed, whatever the workers' priority)
        self.priorities["sampler"] = thread_priority()
        watch = self.watch = PageWatch(self.settings.settle_ms / 1000.0, self.recheck_s, self._area_detail,
                                       self._area_crispness)
        packer = threading.Thread(target=self._pack_loop, name="batch-packer", daemon=True)
        packer.start()
        try:
            self._watch_viewer(watch)
        finally:
            self._packing.put(None)
            packer.join(timeout=30.0)
            if not packer.is_alive():
                self._merge_taken_missed()

    def _watch_viewer(self, watch: PageWatch) -> None:
        while not self._ended:
            last_look = self._finish.is_set()
            try:
                if not self._room_on_backlog():
                    return
                done = self._look(watch, last_look)
            except _Leaving:
                return
            except CaptureError as e:
                error = message_of(e, "viewer.error")
                if self._ended or last_look:
                    return
                if not window_exists(self.hwnd):
                    self._wait_for_reader(Message("batch.viewer_lost", error=error))
                    return
                self._wait_for_reader(Message("batch.waiting_capture", error=error))
                self._stop.wait(self.wait_poll_s)
                continue
            if getattr(self.progress.waiting, "code", "") == "batch.waiting_capture":
                self._carry_on()
            if last_look and done:
                return

    def _look(self, watch: PageWatch, last_look: bool) -> bool:
        """One look of the sampler: wait for the viewer's next frame (the capture's frame events, `frame_wait`; without
        them, `sample_s`), no longer than until `PageWatch.due`, then capture it, or tell the watch the time; its
        decisions go to the packer (`_decided`). No new frame: only whether the window is still there. On the last
        look (*last_look*: the reader has finished) the frame on show is captured at once, and the page on show taken
        once it is sure, at the latest `recheck_s` after it settled; True once nothing is left on show to take."""
        first_last = last_look and not self._looked_last
        self._looked_last = last_look
        due = watch.due(time.monotonic())
        wait = 0.0 if first_last else self.sample_s if due is None else min(self.sample_s, due)
        count = frame_count(self.hwnd)
        new = True
        if count is None:  # no frame events (PrintWindow): a look every sample_s, every follow_s while a page draws
            if watch.shown is not None:
                wait = min(wait, self.follow_s)
            if wait > 0 and self._stop.wait(wait):
                raise _Leaving
        elif self._looked_seq is not None and not first_last:
            now_count = frame_wait(self.hwnd, self._looked_seq, wait)
            new = now_count is None or now_count != self._looked_seq
            if not new and not window_exists(self.hwnd):
                raise CaptureError(Message("viewer.closed"))
        if self._ended:
            raise _Leaving
        if new:
            self._looked_seq = frame_count(self.hwnd)  # (before the capture: a frame that comes during it is new)
            image = self._capture()
            now = time.monotonic()
            decisions = watch.see(image, now)
            if watch.shown is not None and watch.shown.since == now:
                self._last_change = now  # the reader is turning: GPU work waits (`_gpu_wait`)
        else:
            now = time.monotonic()
            decisions = watch.tick(now)
        if last_look and watch.shown is not None and now - watch.shown.since >= watch.recheck_s:
            decisions += watch.take_now()
        self._decided(decisions)
        return watch.shown is None

    def _decided(self, decisions: Sequence[tuple[str, Image.Image]]) -> None:
        """`PageWatch`'s decisions handed to the packer: a page taken goes on the window at once (``batch_page``)."""
        for kind, image in decisions:
            self._last_change = time.monotonic()
            if kind in (TAKE, SHARPER_TAKEN):
                self._on_show = image
                self._show("batch_page", image=image)
            with self._in_hand_lock:
                self._in_hand += kind == TAKE
            self._packing.put((kind, image))

    def _pack_loop(self) -> None:
        """The packer, on a thread of its own while the pages are read: what the sampler decided, in its order. A page
        taken is packed and put on the backlog (`_take`), waiting for room when there is none; a page that went by is
        told (`_went_by`); a sharper picture of the page taken last takes its place while it waits to be read. A page
        taken, and a sharper picture of it, first widen the run's area to hold its page panel (`_meet`). Ends at the
        sampler's None, or at once at Stop."""
        set_priority(0)
        self.priorities["packer"] = thread_priority()
        while True:
            item = self._packing.get()
            if item is None:
                return
            kind, image = item
            try:
                if self._ended:  # (Stop, or the reading is over: nothing more goes on the backlog)
                    continue
                if kind != MISSED:
                    self._meet(image)
                if kind == TAKE:
                    while not self._take(image):  # (the memory full of frames to read: the reader is asked to wait)
                        if not self._room_on_backlog(packing=True):
                            break
                elif kind == MISSED:
                    self._went_by(image)
                else:
                    self._sharper_taken(image)
            finally:
                if kind == TAKE:
                    with self._in_hand_lock:
                        self._in_hand -= 1

    def _meet(self, frame: Image.Image) -> None:
        """A page taken (or a sharper picture of the one taken last), before anything of the run reads it: while the
        run follows the reader, the page panel found in it joins the run's area (`page_area.JoinedArea.meet`), so that
        the page is fingerprinted here and read later in an area that holds it; when the panels found changed, the
        window is told them and the area (``page_area`` {hwnd, size, found, hand, margins}), for its own record of the
        viewer. On the packer's thread alone: the one that widens the area."""
        area = self._area
        if area is None:
            return
        if area.meet(frame):
            self._show("page_area", hwnd=self.hwnd, size=area.size, found=area.found, hand=area.hand,
                       margins=area.margins)

    def _read_in(self) -> None:
        """On the reading loop's thread, before it reads a frame (and once the reading is over): the run's area as it
        is now becomes the one the frame is read in, when it changed - the batch's settings' (`_still_the_book`, the
        colophon) and the pipeline's (`Pipeline.set_margins`: in the window, the window's own). The packer widened it
        for the frame before the frame went on the backlog, so it holds the frame's page panel; it changes only here,
        between two frames, so that every step of a frame's reading reads one area."""
        area = self._area
        if area is None:
            return
        margins = tuple(int(m) for m in area.margins)
        if margins == self._read_area:
            return
        self._read_area = margins
        self.settings.margins = margins  # type: ignore[assignment]
        publish = getattr(self.pipeline, "set_margins", None)  # (a stand-in pipeline may have none)
        if publish is not None:
            publish(margins)

    def _has_room(self, packing: bool = False) -> bool:
        """Whether one more frame fits: the memory cap (a frame like the largest so far for it and for each frame handed
        to the packer, once what may go has gone, `PageImages.room_for`) and `backlog_size` when it is set. *packing*:
        the packer asks, for a frame already handed."""
        with self._in_hand_lock:
            ahead = self._in_hand - (1 if packing else 0)
        count = self.backlog_size is None or self._backlog.qsize() + ahead < self.backlog_size
        return count and self.images.room_for(self.images.largest * (ahead + 1))

    def _room_on_backlog(self, packing: bool = False) -> bool:
        """Whether there is room for one more frame, once there is: frames still to read that fill the memory cap ask
        the reader to wait. False: Stop or the end of the reading came first."""
        if self._has_room(packing):
            return True
        with self._in_hand_lock:
            queued = self._backlog.qsize() + self._in_hand
        self._wait_for_reader(Message("batch.backlog_full", queued=queued))
        while not self._has_room(packing):
            if self._stop.wait(self.sample_s) or self._sampler_off.is_set():
                return False
        self._carry_on(Message("batch.backlog_room"))
        return True

    def _known(self, fps: Sequence[str]) -> bool:
        """Has this run seen every page unit of a frame already: taken by the sampler, or read by an earlier run?"""
        return bool(fps) and all(any(fingerprint.hamming(f, seen) <= INDEXED_WITHIN
                                     for seen in (*self._sighted, *self.progress.seen)) for f in fps)

    @property
    def _page_scale(self) -> float | None:
        """How far apart this run's pages are (`PageWatch.scale`, `same_page`); None before the sampler knows."""
        watch = self.watch
        return watch.scale if watch is not None else None

    def _missed_seq(self, fps: Sequence[str], page: np.ndarray, d: np.ndarray) -> int | None:
        """The seq of the page that went by (`_went_by`) that this frame shows: its page units' fingerprints, or its
        `page_thumb` and `detail` (`same_page`: a soft picture's fingerprints may not be the sharp page's); None when
        none is."""
        for seq, (missed, seen, seen_detail) in self._missed.items():
            if fps and all(any(fingerprint.hamming(f, m) <= INDEXED_WITHIN for m in missed) for f in fps):
                return seq
            if same_page(seen, page, seen_detail, d, self._page_scale):
                return seq
        return None

    def _taken_before(self, page: np.ndarray, d: np.ndarray) -> int | None:
        """The seq of the page taken in this run that a frame like this shows (`same_page`: a soft picture of a page
        taken), None when there is none."""
        for seq, seen, seen_detail in self._taken_thumbs:
            if same_page(seen, page, seen_detail, d, self._page_scale):
                return seq
        return None

    def _merge_missed(self, seq: int, into: int | None) -> None:
        """The page that went by as *seq* turned out to be taken after all, as the page *into* (None: a page an
        earlier run has read): its placeholder goes (``page_stage`` read "merged" {into}), and so does the band's
        request to turn back when it was the last."""
        del self._missed[seq]
        with self._staging:
            self._stages.pop(seq, None)
        data: dict[str, Any] = {"seq": seq, "fingerprint": self._fp_of.pop(seq, ""), "stage": "read",
                                "state": "merged"}
        if into is not None:
            data["into"] = into
        self._show("page_stage", **data)
        self._missed_told()

    def _merge_taken_missed(self) -> None:
        """The reading is over: a page that went by and was taken all the same under another seq (its picture alike,
        `same_page`, or its page units read) leaves no placeholder."""
        for seq, (fps, page, d) in list(self._missed.items()):
            into = self._taken_before(page, d)
            if into is not None or self._known(fps):
                self._merge_missed(seq, into)

    def _take(self, frame: Image.Image) -> bool:
        """The new page *frame* on the backlog, packed (`pageimages.pack`), unless this run has seen its pages (going
        back): then there is nothing to read. A page gets its *seq* (that of the page that went by, when it is that
        page: the reader turned back to it) and its first ``page_stage`` (read waiting, with its thumbnail). False when
        the frame does not fit after all (the memory full of frames to read): nothing is kept, and the packer waits."""
        fps = tuple(self._fingerprints(frame))
        page, d = page_thumb(thumbnail(frame)), self._area_detail(frame)
        if self._known(fps):
            again = self._missed_seq(fps, page, d) if self._missed else None
            if again is not None:  # a page that went by, known all the same: no placeholder stays for it
                self._merge_missed(again, self._taken_before(page, d))
            self._on_show_key = self._last_key = None
            return True
        packed = pack(frame)
        again = self._missed_seq(fps, page, d) if fps else None
        key = again or (self._seq + 1 if fps else -(self._loose + 1))
        if not self.images.put_frame(key, packed):
            return False
        if again:
            del self._missed[again]
            self._retaken = True
            self._missed_told()
        elif fps:
            self._seq = key
            self._fp_of[key] = fps[0]
        else:
            self._loose += 1
        if fps:
            self._sighted.extend(fps)
            self._taken_thumbs.append((key, page, d))
        self._on_show_key = self._last_key = key
        if fps:  # (before the loop can take it: its first event)
            self._page_stage(key, "read", "waiting", thumb=thumb_of(frame))
        self._backlog.put(_Taken(key, key if fps else 0, fps))
        self._emit(Message("batch.page_waits", queued=self._backlog.qsize()))
        return True

    def _went_by(self, frame: Image.Image) -> None:
        """A page went by before it could be taken (`PageWatch`: on show too short a time, or only soft): when it is a
        page this run has not seen, it gets its *seq*, ``page_stage`` read "missed" (no thumbnail: the strip's
        placeholder) and ``page_missed`` {seq, fingerprint, thumb, pages}, and the reader is told at once to turn back
        (``batch.page_missed`` {pages}: those not taken yet), which stays on show until they are all taken."""
        fps = tuple(self._fingerprints(frame))
        if not fps or self._known(fps):
            return
        page, d = page_thumb(thumbnail(frame)), self._area_detail(frame)
        if self._taken_before(page, d) is not None or self._missed_seq(fps, page, d) is not None:
            return
        self._seq += 1
        seq = self._seq
        self._missed[seq] = (fps, page, d)
        self._fp_of[seq] = fps[0]
        self._page_stage(seq, "read", "missed")
        self._show("page_missed", seq=seq, fingerprint=fps[0], thumb=thumb_of(frame), pages=len(self._missed))
        self._missed_told()

    def _missed_told(self) -> None:
        """The pages that went by and are not taken yet, as the band says them (``batch.page_missed`` while there are
        any, ``batch.missed_taken`` once the last of them is taken)."""
        p = self.progress
        p.missed = len(self._missed)
        if self._missed:
            self._wait_for_reader(Message("batch.page_missed", pages=len(self._missed)))
        elif getattr(p.waiting, "code", "") == "batch.page_missed":
            self._carry_on(Message("batch.missed_taken"))

    def _sharper_taken(self, frame: Image.Image) -> None:
        """A sharper picture of the page taken last came after it was taken: it takes the frame's place while the frame
        waits to be read (`PageImages.replace_unread`)."""
        if self._last_key is not None:
            self.images.replace_unread(self._last_key, pack(frame))

    def _next_frame(self, sampler: threading.Thread) -> _Taken | None:
        """The next frame to read, as long as it takes the reader to turn a page; None at Stop, or when the reader has
        finished and the backlog is empty. A reader away for `manual_wait_s` ends nothing: the screen may switch off
        meanwhile, and the next page goes on as if nothing had happened."""
        idle = time.monotonic()
        resting = False
        while not self._stop.is_set():
            finished = self._finish.is_set() and not sampler.is_alive()
            if self._finish.is_set() and not self._told_finished:
                self._told_finished = True
                self._emit(Message("batch.finishing", queued=self._backlog.qsize()))
            try:
                taken = self._backlog.get(timeout=0.05)
            except queue.Empty:
                if finished:
                    return None
                if not resting and time.monotonic() - idle >= self.manual_wait_s:
                    resting = True
                    release_awake()
                continue
            if resting:
                keep_awake(display=True)
            return taken
        return None

    def _events_of(self, taken: _Taken) -> EventFn | None:
        """Where the pipeline's page events go: to the window while *taken* is the page on show; a page of the backlog
        is read without them, the reader being on a later page."""
        return self.show if taken.key == self._on_show_key else None

    def _iterate_pages(self, handle: Callable[[Image.Image, _Taken], bool]) -> None:
        """The pages the reader turns, in that order, each new page once: *handle(frame, taken)* for each, the frames
        coming from the sampler's backlog (see the module's docstring), unpacked. A frame this run has seen is skipped;
        a frame that does not look like the book is not read, which is said, and the run waits for the next page. The
        loop runs at a lower thread priority, torch with a core or two left free (see the module's docstring).

        *handle* returns False to stop. Ends when the reader says so (`finish`, after the backlog), on Stop, or at
        ``max_pages``. No page read when it ended: nothing of the book was seen, `NO_PAGE`.
        """
        p = self.progress
        sampler = threading.Thread(target=self._sample, name="batch-sampler", daemon=True)
        colophon_reads = 0  # pages read in full as a colophon (`colophon.find_colophon`)
        self.following = True
        priority = lower_priority()
        self.priorities["reader"] = thread_priority()
        threads = limit_torch_threads(self._torch_most())
        gate = hasattr(self.pipeline, "gpu_gate")
        if gate:
            self.pipeline.gpu_gate = self._gpu_wait
        sampler.start()
        try:
            while not self._stop.is_set() and p.pages < self.max_pages:
                taken = self._next_frame(sampler)
                if taken is None:
                    break
                frame = self.images.frame(taken.key)
                if frame is None:  # (never: a frame to read is never let go)
                    continue
                self._read_in()  # (the area that holds this page: widened for it as it was taken)
                fps = list(taken.fps)
                seen = self._seen_before(fps)
                if not seen and not self._still_the_book(frame):
                    self._page_stage(taken.seq, "read", "skipped")
                    self.images.drop_frame(taken.key)
                    self._wait_for_reader(Message("batch.not_book"))
                    continue
                if getattr(p.waiting, "code", "") == "batch.not_book":
                    self._carry_on()
                if seen:
                    self._page_stage(taken.seq, "read", "skipped")
                    self.images.drop_frame(taken.key)
                    continue
                self._page_stage(taken.seq, "read", "working")
                # the colophon names the book: the cheap test on every page, the OCR only on a page that passes it
                if p.colophon is None and colophon_reads < colophon.MAX_READS and self.pipeline.ocr is not None \
                        and colophon.precheck(frame, self.settings.margins):
                    colophon_reads += 1
                    p.colophon = colophon.find_colophon(frame, self.pipeline.ocr, self.settings.margins)
                before = p.pages
                if not handle(frame, taken):
                    p.pages = before  # (a page that ended the run - its translation not kept - is no page more)
                    break
                frame = None  # (its packed image stays with `images` while the run needs it)
                p.pages = before + 1  # (*handle* counts it as it says it: the band shows the page said as read)
                p.seen.extend(fps)
        finally:
            self.following = False
            self._sampler_off.set()
            sampler.join(timeout=30.0)
            while not self._backlog.empty():  # (Stop, or the page limit: frames not read go at once)
                self.images.drop_frame(self._backlog.get_nowait().key)
            self._read_in()  # (the area the run ended with: the translation and the window letter its pages in it)
            if gate and self.pipeline.gpu_gate == self._gpu_wait:
                self.pipeline.gpu_gate = None
            restore_torch_threads(threads)
            if priority is not None:
                set_priority(priority)
            p.waiting = None  # the reading is over: nothing waits for the reader
        if self._stop.is_set() and not p.reason:
            p.reason = Message("batch.user_stop")
        if p.pages >= self.max_pages and not p.reason:
            p.reason = Message("batch.page_limit", limit=self.max_pages)
        if not p.reason:
            ended = Message("batch.read_so_far") if self._partial else Message("batch.finished_reading")
            p.reason = ended if p.seen else NO_PAGE

    def _torch_most(self) -> int:
        """Torch's threads while the batch reads: `torch_threads`, or the reader's ``ocr_threads`` when fewer."""
        most = torch_threads()
        own = int(getattr(self.settings, "ocr_threads", 0) or 0)
        return min(most, own) if own > 0 else most

    # ------------------------------------------------------------------ erased ahead
    @property
    def _erasing(self) -> bool:
        """Whether the pages read are erased ahead: a whole-book run with a pipeline that can (`Pipeline.erase_page`)."""
        return self.context_mode and hasattr(self.pipeline, "erase_page")

    def _erase_ahead(self) -> None:
        """The erase ahead, on a thread of its own at a lower priority: each page read (`_erase_jobs`) erased as the
        render will erase it (`Pipeline.erase_page`) and kept, packed, in its frame's place (`PageImages.put_erased`);
        LaMa waits while pages are being turned (`_gpu_wait`, through ``Pipeline.gpu_gate``), and every page waits
        while frames wait to be read (`_reading_first`). A page whose frame went to make room, or whose erased page does
        not fit, is "skipped": it erases on show. Ends at None, and at Stop."""
        lower_priority()
        self.priorities["eraser"] = thread_priority()
        while not self._stop.is_set():
            try:
                job = self._erase_jobs.get(timeout=0.1)
            except queue.Empty:
                continue
            if job is None:
                return
            seq, regions = job
            self._reading_first()
            if self._stop.is_set():
                return
            frame = self.images.frame(seq)
            if frame is None:
                self._page_stage(seq, "erase", "skipped")
                continue
            self._page_stage(seq, "erase", "working")
            try:
                out, records = self.pipeline.erase_page(frame, regions, cancel=self._stop)
            except Cancelled:
                return
            except Exception:  # noqa: BLE001 - the page erases on show, as without the erase ahead
                self.images.not_erased(seq)
                self._page_stage(seq, "erase", "failed")
                continue
            undo = undo_of(np.asarray(frame.convert("RGB")), out)  # (the frame made again from it, for the window)
            frame = None
            if self.images.put_erased(seq, pack(Image.fromarray(out)), records, out.shape[:2], undo):
                self.erased_pages += 1
                self._page_stage(seq, "erase", "done")
            else:
                self._page_stage(seq, "erase", "skipped")

    def _reading_first(self) -> None:
        """The erase ahead waits while frames wait to be read (the backlog), until the reading is over or Stop: the
        reading is what the reader sees go on (the strip's Read), and the two side by side are slower each than one
        after the other (the OCR on the CPU, LaMa's own work round the GPU's): 30 pages turned in 20 s on OpenMantra,
        detect_model and art_erase "auto", read 40 s after the last turn instead of 63, all erased 61 s after it
        instead of 65 (tools: the e2e lab's turnlag). Nothing the reading pass shows needs an erased page: the
        translation, which does, starts after the reading and the erase."""
        while self._backlog.qsize() > 0 and not self._ended:
            self._stop.wait(0.05)

    def _start_erasing(self) -> threading.Thread | None:
        if not self._erasing:
            return None
        old = getattr(self.pipeline, "erased_ahead", None)
        if old is not None and old is not self.images:
            old.clear()  # an earlier run's pages: this run's take their place
        self.pipeline.erased_ahead = self.images  # (the render takes the erased pages from there)
        thread = threading.Thread(target=self._erase_ahead, name="batch-erase-ahead", daemon=True)
        thread.start()
        return thread

    def _finish_erasing(self, thread: threading.Thread | None) -> None:
        """The erase of the pages read done before the translation (LaMa off the GPU before Ollama's model loads), said when
        there is some left (``batch.erasing_ahead``); at Stop at once."""
        if thread is None:
            return
        left = self._erase_jobs.qsize()
        self._erase_jobs.put(None)
        if left and not self._stop.is_set():
            self._emit(Message("batch.erasing_ahead", pages=left))
        while thread.is_alive() and not self._stop.is_set():
            thread.join(0.1)
        thread.join(5.0)
        while not self._erase_jobs.empty():  # (Stop: pages not erased erase on show)
            job = self._erase_jobs.get_nowait()
            if job is not None:
                self.images.not_erased(job[0])

    # ------------------------------------------------------------------ modes
    def run(self) -> BatchProgress:
        start = time.monotonic()
        p = self.progress
        owner = self.lock.acquire()
        if owner is not None:
            p.reason = Message("batch.locked", pid=owner)
            p.finished = True
            p.phase = "done"
            p.summary = Message("batch.not_started", reason=p.reason)
            self._emit(p.summary)
            return p
        p.preflight = self._start_checks()
        self._emit(Message("batch.started", problems=len(p.preflight), problem=p.preflight[0] if p.preflight else ""))
        keep_awake(display=True)
        try:
            if self.context_mode:
                self._run_context(start)
            else:
                self._run_pagewise(start)
        except Cancelled:
            p.reason = Message("batch.user_stop")
        except KeyboardInterrupt:
            self._stop.set()  # Ctrl+C in the CLI: a Stop like any other
            raise
        finally:
            release_awake()
            self.lock.release()
            release = getattr(self.pipeline, "release_translator", None)  # (a stand-in pipeline may have none)
            if release is not None:
                release()  # the model is not needed again until a page is
            self.pipeline.save_annotations()  # the sequence of pages seen
            if self.pipeline.save_error:  # whatever else ended the run: this is what the reader must hear
                p.reason = Message("batch.save_failed", error=self.pipeline.save_error)
            p.elapsed = time.monotonic() - start
            p.finished = True
            self._leave_readings()
            self._close_stages()
            p.summary = self._summary()
            p.phase = "done"
            self._emit(p.summary)
        return p

    @property
    def _read_through_before(self) -> bool:
        """The reader finished the book in an earlier run: this one reads no page."""
        return self.readings is not None and self.readings.complete

    def _leave_readings(self) -> None:
        """What the next run can go on from (`left`): the units read and not stored, with what is known of them."""
        if not self.context_mode or not self.progress.phase:
            return
        p = self.progress
        units = [u for u in self._units if id(u) not in self._stored]
        self.left = Readings(units, p.pages, self._read_through) if units else None

    def _take_readings(self) -> None:
        """The readings an earlier run left, as far as they still stand: a page translated or changed since (read
        with Auto, edited) is left out, so that nothing the reader has seen or corrected is translated over."""
        readings, p = self.readings, self.progress
        if readings is None:
            return
        self._units = [u for u in readings.units if self._untouched(u)]
        p.pages = readings.pages
        p.found = p.bubbles = sum(len(u.japanese()) for u in self._units)
        p.seen.extend(u.fingerprint for u in self._units)
        self._read_through = readings.complete
        if readings.complete:
            p.reason = Message("batch.finished_reading")  # what ended the reading it goes on from
            self._emit(Message("batch.continuing", lines=p.found))

    def _untouched(self, unit: ScannedUnit) -> bool:
        """Does the cache hold what it held when *unit* was read: the bubbles it kept, no others?"""
        cache = self.pipeline.cache
        if cache is None:
            return True
        cache.refresh()
        hit = cache.lookup(unit.stored_fingerprint or unit.fingerprint, unit.aspect,
                           self.settings.fingerprint_max_distance, self.pipeline.last_seq)
        then = [b.text for b in unit.kept]
        return sorted(b.text for b in hit[0].bubbles) == sorted(then) if hit is not None else not then

    def _start_checks(self) -> list[Message]:
        """The pre-flight result: the caller's, else what this batch can find out itself about its own pipeline
        (the OCR model when there is no OCR engine, Ollama and the model when it translates with Ollama)."""
        if self._preflight is not None:
            return list(self._preflight)
        problems: list[Message] = []
        if self.pipeline.ocr is None:
            problems += health.check_ocr(self.settings.ocr_model_dir)
        translator = self.pipeline.translator
        if translator is None:
            problems.append(Message("pipeline.no_translator"))
        elif isinstance(translator, OllamaTranslator):
            problems += health.check_ollama(translator.base, translator.model, known=translator.auto_model,
                                            language=translator.target_language)
        return problems

    def _summary(self) -> Message:
        """How the batch ended (see the module's docstring)."""
        p = self.progress
        seconds = round(p.elapsed, 1)
        if self._stop.is_set() and getattr(p.reason, "code", "") != "batch.save_failed":
            if not self.context_mode:
                return Message("batch.stopped", page=p.pages, pages=p.pages, bubbles=p.translated, seconds=seconds)
            kept = self.keep_readings and self.left is not None  # the next run goes on from them
            again = not kept and self.left is not None  # those pages are read again
            if p.phase == "read":
                return Message("batch.stopped_reading", pages=p.pages, seconds=seconds, kept=int(kept),
                               again=int(again))
            return Message("batch.stopped_translating", done=p.checked, total=max(p.found, p.checked), pages=p.pages,
                           seconds=seconds, kept=int(kept), again=int(again))
        if p.errors and not p.translated and p.first_error is not None:
            return Message("batch.failed_requests", failed=p.errors, reason=p.first_error, pages=p.pages,
                           seconds=seconds)
        if p.reason == NO_PAGE:
            return Message("batch.not_started", reason=p.reason)
        return Message("batch.finished", pages=p.pages, bubbles=p.translated, seconds=seconds,
                       minutes=max(1, round(seconds / 60)), failed=p.errors, error=p.first_error or "",
                       reason=p.reason or Message("batch.scan_ended"))

    def _reask_failed(self, e: TranslationError) -> bool:
        """A request for lines asked for again failed: counted like any failed request. Whether to go on asking
        (not after a failure every later request would repeat or wait as long, nor after Stop)."""
        error = message_of(e)
        self._failed(error)
        if fatal(error):
            self._fatal = error
            return False
        return not self._stop.is_set() and worth_asking_again(error)

    def _translate_units(self, units: list[ScannedUnit], recent: deque[tuple[str, str]], notes_text: str,
                         upcoming: list[str], language: str, depth: int = 0) -> None:
        """Translate a run of page units.

        A failed request is retried in two halves, and so is a reply with not one usable line; a single page unit
        whose request failed is asked for again a few lines at a time instead (not after a timeout). The reply gets
        the renderings of the series sheet where it spells them otherwise (`_spelt_right`), is checked and
        tightened (`Pipeline.tighten`) and every page unit it completes is committed. For the lines it left without a
        usable translation (missing, empty, the Japanese copied: a cut-off or looping reply, an id left out) the model
        is asked again (`ask_for_missing`): a few consecutive lines at a time with their neighbours as context, then
        each line still missing on its own; what comes back is checked and tightened in turn and completes the page
        units it can. What came back is stored even when its unit stays incomplete (`Pipeline.commit_unit`), and
        counted once, when it is stored. A page unit the model still gives nothing usable for is noted and translated
        when its page is read (``batch.note_unit_failed``). A failure every later request would repeat (`fatal`) ends
        the translation.
        """
        p = self.progress
        translator = self.pipeline.translator
        assert translator is not None
        if self._fatal is not None or self._stop.is_set():
            return
        slots = [(ui, i) for ui, u in enumerate(units) for i in range(len(u.japanese()))]  # (unit, region) per line
        run = [units[ui].japanese()[i] for ui, i in slots]
        texts = [r.source_text for r in run]
        meta = facts_of(run, [(ui, units[ui].box) for ui, _i in slots])  # with the page, a sentence going on
        if not texts:
            return
        if depth > 6:
            p.notes.append(Message("batch.note_gave_up", units=len(units)))
            self._leave_for_reading(units)
            return

        def halves(note: Message) -> None:
            half = len(units) // 2
            p.notes.append(note)
            self._translate_units(units[:half], recent, notes_text, upcoming, language, depth + 1)
            self._translate_units(units[half:], recent, notes_text, upcoming, language, depth + 1)

        prior = list(recent)  # the pairs before this run: the context of its requests
        call = cancel_args(translator.translate_page, self._stop, self._on_slow)
        sheet = self.pipeline.check_sheet()
        answered: set[int] = set()  # the lines of this run the request under way has answered

        def on_item(k: int, text: str) -> None:
            self._answered(answered, k, len(texts))
            view = self._view
            if view is not None and 0 <= k < len(texts):  # (on show as it comes: `translation_view`)
                ui, i = slots[k]
                view.line(units[ui], i, texts[k], str(text or ""), str(meta[k].get("speaker", "")))

        told = {"on_item": on_item} if accepts(translator.translate_page, "on_item") else {}
        if self._view is not None:
            self._view.request(units)
        try:
            outputs = translator.translate_page(texts, prior, notes_text, upcoming,
                                                meta=meta if any(meta) else None, **call, **told)
        except TranslationError as e:
            p.answering = 0
            error = message_of(e)
            self._failed(error)
            if self._stop.is_set():
                return
            if fatal(error):
                self._fatal = error
                return
            if len(units) > 1:
                halves(Message("batch.note_retry_failed", bubbles=len(texts), error=error))
                return
            if not worth_asking_again(error):
                p.notes.append(Message("batch.note_unit_failed", unit=units[0].fingerprint[:8], error=error))
                self._leave_for_reading(units)
                return
            outputs = []  # the page unit's lines are asked for again, a few at a time
        outputs = [str((outputs[k] if k < len(outputs) else "") or "").strip() for k in range(len(texts))]
        if outputs and _base.REASK_ROMANISED:  # a short kana line answered with its romaji alone: once more, with neighbours
            outputs = ask_again_romanised(translator, texts, outputs, context=prior, notes=notes_text, upcoming=upcoming,
                                          meta=meta, call_args=call, cancel=self._stop)[0]
        per_unit: list[dict[int, str]] = [{} for _ in units]
        per_unit_flags: list[dict[int, list[str]]] = [{} for _ in units]
        counted: list[set[int]] = [set() for _ in units]  # the lines of each unit stored and counted so far

        def usable(k: int, text: str) -> bool:
            return bool(text) and self.pipeline.real_translation(texts[k], text)

        def settle(lines: list[int], replies: Sequence[str], context: list[tuple[str, str]]) -> None:
            """The *replies* of *lines* (indices into the run) spelt as the series sheet spells, checked and
            tightened; the real translations kept for their page units, with their flags, and carried on as context."""
            entries: list[dict[str, Any]] = []
            for k in lines:
                ui, i = slots[k]
                r = units[ui].japanese()[i]
                text = self._spelt_right(texts[k], replies[k], str(meta[k].get("speaker", "")), sheet)
                entries.append({"ja": r.source_text, "text": text, "mask": r.mask, "kind": r.kind,
                                "anchor": r.text_box, "x0": r.bbox[0], "y0": r.bbox[1], "meta": region_meta(r),
                                "confidence": r.ocr_confidence, "direction": direction_of(r)})
            tightened = self.pipeline.tighten(entries)
            flagged = self.pipeline.review(entries, tightened)
            for k, r_out, fl in zip(lines, tightened, flagged):
                ui, i = slots[k]
                r = units[ui].japanese()[i]
                if r_out and self.pipeline.real_translation(r.source_text, r_out):
                    per_unit[ui][i] = r_out
                    per_unit_flags[ui][i] = list(fl)
                    recent.append((r.source_text, r_out))

        def commit(which: list[int]) -> list[int]:
            """The page units *which* stored with what they have; the ones still incomplete."""
            left: list[int] = []
            for ui in which:
                unit = units[ui]
                with self._storing:
                    complete = self.pipeline.commit_unit(unit, per_unit[ui], per_unit_flags[ui])
                if self._view is not None:
                    self._view.stored(unit, per_unit[ui])
                self._keep_said(unit, per_unit[ui])
                fresh = len(per_unit[ui].keys() - counted[ui])  # stored now, not by the commit before this one
                counted[ui].update(per_unit[ui])
                p.translated += fresh
                p.bubbles += fresh
                p.checked += fresh
                if per_unit[ui]:
                    self._stored.add(id(unit))
                if not complete:
                    left.append(ui)
            return left

        settle(list(range(len(texts))), outputs, prior)
        p.answering = 0  # (what it answered is stored now: `checked`)
        incomplete = commit(list(range(len(units))))
        if not incomplete or self._stop.is_set():
            return
        missing = [k for k, (ui, i) in enumerate(slots) if i not in per_unit[ui]]
        if len(missing) == len(texts) and len(units) > 1:
            self._failed(Message("batch.reply_unusable"))
            halves(Message("batch.note_retry_unusable", bubbles=len(texts)))
            return
        p.notes.append(Message("batch.note_incomplete", incomplete=len(incomplete), units=len(units)))
        settled = [per_unit[ui].get(i, "") for ui, i in slots]
        answered.clear()
        try:
            again = ask_for_missing(translator, texts, settled, usable, context=prior, notes=notes_text,
                                    upcoming=upcoming, meta=meta, call_args=call, cancel=self._stop,
                                    on_error=self._reask_failed, group=REASK_GROUP, on_item=on_item if told else None)
        finally:
            p.answering = 0
        if self._stop.is_set():
            return
        filled = [k for k in missing if usable(k, again.texts[k])]
        if filled:
            limit = recent.maxlen if recent.maxlen is not None else len(texts) + len(prior)
            around = prior + [(texts[k], settled[k]) for k in range(max(filled)) if settled[k]]
            settle(filled, again.texts, around[-limit:] if limit else [])
            incomplete = commit(incomplete)
        for ui in incomplete:
            p.notes.append(Message("batch.note_unit_incomplete", unit=units[ui].fingerprint[:8]))

    def _answered(self, answered: set[int], k: int, count: int) -> None:
        """The request under way has answered line *k* of the *count* it asks for (``on_item``): counted once in
        `BatchProgress.answering` and told, at most every `LINE_SAID_S`, the message on show unchanged."""
        if not 0 <= k < count or k in answered:
            return
        answered.add(k)
        self.progress.answering = len(answered)
        now = time.monotonic()
        if now - self._line_said >= LINE_SAID_S:
            self._line_said = now
            self._emit(self.progress.message)

    def _leave_for_reading(self, units: Sequence[ScannedUnit]) -> None:
        """Page units no request got through for: the entry of each (what it held and what is still its own) marked as
        lacking the rest, so that reading the page translates it (`CachedPage.incomplete`). A unit without an entry
        gets none: the page is translated when it is read in any case."""
        for unit in units:
            self.pipeline.commit_unit(unit, {})

    @staticmethod
    def _spelt_right(ja: str, text: str, speaker: str, sheet: Any) -> str:
        """*text*, a translation of *ja*, with the renderings of the series sheet *sheet* where it spells them
        otherwise: the near spellings `terms.rendering_variants` finds. No model request."""
        if not text or sheet is None:
            return text
        return rename_text(text, rendering_variants(sheet, ja, text, speaker))

    def _run_pagewise(self, start: float) -> None:
        p = self.progress
        p.phase = "translate"

        def handle(frame: Image.Image, taken: _Taken) -> bool:
            page = p.pages + 1
            self._emit(Message("batch.translating_page", page=page))
            result = self.pipeline.process(frame, use_cache=True, translate=True, cancel=self._stop,
                                           on_slow=self._on_slow, events=self._events_of(taken),
                                           progress=self._stage if self.show is not None else None)
            # read and translated: nothing of the run needs its picture any more (no erase ahead, no translation view;
            # a page is never shown from the run's memory), so it goes at once
            self.images.drop_frame(taken.key)
            p.bubbles += len(result.translated)
            p.translated += sum(1 for r in result.translated if not r.from_cache)
            p.cache_hits += result.cache_hits
            error = message_of(result.error) if result.error else None
            if error is not None:
                self._failed(error)
            self._page_stage(taken.seq, "read", "done")
            self._page_stage(taken.seq, "erase", "skipped")  # (page by page the render erases: nothing ahead)
            self._page_stage(taken.seq, "translate", "failed" if error is not None else "done")
            p.elapsed = time.monotonic() - start
            p.pages = page  # (counted as it is said: `_iterate_pages`)
            self._emit(Message("batch.translated_page", page=page, bubbles=len(result.translated),
                               seconds=round(p.elapsed, 1), error=error or ""),
                       result if taken.key == self._on_show_key else None)  # (the reader may have turned on)
            if error is not None and fatal(error):
                p.reason = error
                return False
            if self._saves_fail():
                p.reason = self._fatal
                return False
            return True

        self._iterate_pages(handle)

    def _saves_fail(self) -> bool:
        """The cache cannot be written (a full disk, a locked file): what is translated from here on would be lost
        with the window, so the run ends there, however many hours of it are left, and says why."""
        if self.pipeline.pages_not_saved and self._fatal is None:
            self._fatal = Message("batch.save_failed", error=self.pipeline.pages_not_saved)
        return self._fatal is not None and self._fatal.code == "batch.save_failed"

    def _read_already(self, unit: ScannedUnit) -> bool:
        """Is *unit* a page this run holds a reading of? (Nothing of a page is stored while the pages are read, so the
        cache cannot say: half of a spread seen before, or a page read by the run an earlier one stopped in.)"""
        return any(fingerprint.hamming(unit.fingerprint, u.fingerprint) <= INDEXED_WITHIN for u in self._units)

    def _reading_pass(self, start: float) -> None:
        """Read every page the reader turns: the capture and the OCR, no model request (`Pipeline.scan`). The units with
        something to translate go to `_units`, text and geometry only."""
        p = self.progress
        pruned = timed = 0

        def handle(frame: Image.Image, taken: _Taken) -> bool:
            nonlocal pruned, timed
            page = p.pages + 1
            self._emit(Message("batch.scanning_page", page=page))
            began = time.monotonic()
            erasing = self._erasing and taken.seq > 0
            scan = self.pipeline.scan(frame, skip_cached=True, fresh=self.retranslate, cancel=self._stop,
                                      events=self._events_of(taken),
                                      progress=self._stage if self.show is not None else None,
                                      **({"keep_regions": True} if erasing else {}))
            read = [u for u in scan.units if not u.cached and u.japanese() and not self._read_already(u)]
            self._units.extend(read)
            for u in read:
                self._seq_of[id(u)] = taken.seq
            nothing_new = bool(scan.units) and all(u.cached for u in scan.units)
            self._page_stage(taken.seq, "read", "skipped" if nothing_new else "done")
            regions = list(getattr(scan, "erasable", []) or []) if erasing else []
            if regions:  # (the page being translated is lettered on them: `translation_view`, `pipeline.PageDraft`)
                self.images.put_regions(taken.key, regions)
            self.images.read(taken.key, erase=bool(regions))
            if regions:
                self._page_stage(taken.seq, "erase", "waiting")
                self._erase_jobs.put((taken.seq, regions))
            else:
                self._page_stage(taken.seq, "erase", "skipped")
            self._page_stage(taken.seq, "translate", "waiting" if read else "skipped")
            lines = sum(len(u.japanese()) for u in read)
            if lines:  # (a page from the cache takes no time to read: the pace is a page with text to translate)
                timed += 1
                p.page_seconds += (time.monotonic() - began - p.page_seconds) / timed
            p.cache_hits += sum(1 for u in scan.units if u.cached)
            dropped = sum(u.dropped for u in scan.units)
            pruned += dropped
            p.found += lines
            p.bubbles = p.found
            p.elapsed = time.monotonic() - start
            p.pages = page  # (counted as it is said: `_iterate_pages`)
            if nothing_new:  # every line of it translated before: how many, not "0 lines read"
                self._emit(Message("batch.page_cached", page=page, lines=sum(len(u.kept) for u in scan.units),
                                   seconds=round(p.elapsed, 1), dropped=dropped))
            else:
                self._emit(Message("batch.read_page", page=page, lines=lines, pages=page, bubbles=p.found,
                                   cached=p.cache_hits, seconds=round(p.elapsed, 1), dropped=dropped))
            self._saves_fail()
            if self._fatal is not None:
                p.reason = self._fatal  # the disk full: nothing could be kept
                return False
            return True

        eraser = self._start_erasing()
        try:
            self._iterate_pages(handle)
        finally:
            self._finish_erasing(eraser)
        self._read_through = getattr(p.reason, "code", "") == "batch.finished_reading"
        if pruned:
            p.notes.append(Message("batch.note_pruned", bubbles=pruned))
        if self._missed:
            p.notes.append(Message("batch.note_missed", pages=len(self._missed)))

    def _translation_pass(self, units: list[ScannedUnit], start: float) -> None:
        """All the new lines in runs of pages, each run once, with the series sheet and the whole story as context,
        stored as they come. While a window follows the run, its page on show is the page being translated
        (`translation_view`)."""
        p = self.progress
        s = self.settings
        language = s.target_language
        notes_text = self.pipeline.premises()  # the reader's series sheet
        p.phase = "translate"
        p.bubbles = 0  # from here on: the bubbles done
        chunks = chunk_units(units, max(1, s.chunk_bubbles))
        recent: deque[tuple[str, str]] = deque(maxlen=max(0, s.context_pairs))
        left: dict[int, int] = {}  # seq -> its units not translated yet (``page_stage`` translate done once none is)
        for u in units:
            seq = self._seq_of.get(id(u), 0)
            if seq:
                left[seq] = left.get(seq, 0) + 1
        self._view = self._start_view(units)
        try:
            self._translate_chunks(chunks, units, recent, notes_text, language, left, start)
        finally:
            view, self._view = self._view, None
            if view is not None:  # (stopped: at once; else the last page as stored first)
                view.close(finish=not self.stopped)

    def _start_view(self, units: Sequence[ScannedUnit]) -> TranslationView | None:
        """The window's picture of the page being translated (`translation_view`), when a window follows the run and
        the run holds its page images (whole book: they are erased ahead); None otherwise (the command line)."""
        if self.show is None or not self._erasing or not hasattr(self.pipeline, "page_picture"):
            return None
        return TranslationView(self.pipeline, self.images, self.show, units,
                               lambda u: self._seq_of.get(id(u), 0),
                               spell=lambda ja, text, speaker: self._spelt_right(ja, text, speaker,
                                                                                 self.pipeline.check_sheet()),
                               storing=self._storing, priority=lower_priority)

    def _translate_chunks(self, chunks: list[list[ScannedUnit]], units: list[ScannedUnit],
                          recent: deque[tuple[str, str]], notes_text: str, language: str, left: dict[int, int],
                          start: float) -> None:
        """The runs of `_translation_pass` (*chunks* of *units*), each with one request and what follows it."""
        p = self.progress
        s = self.settings
        translator = self.pipeline.translator
        position = {id(u): k for k, u in enumerate(units)}
        lookahead = max(0, s.lookahead_bubbles)
        for ci, chunk in enumerate(chunks):
            if self._stop.is_set():
                p.reason = Message("batch.user_stop")
                return
            for u in chunk:
                self._page_stage(self._seq_of.get(id(u), 0), "translate", "working")
            n_bubbles = sum(len(u.japanese()) for u in chunk)
            self._emit(Message("batch.translating_chunk", chunk=ci + 1, chunks=len(chunks), bubbles=n_bubbles))
            self._stage(Message("pipeline.stage_translating", bubbles=n_bubbles,
                                translator=str(getattr(translator, "name", "translator"))))
            after = units[position[id(chunk[-1])] + 1:]  # the Japanese that comes next: context only
            upcoming = [r.source_text for u in after for r in u.japanese()][:lookahead] if lookahead else []
            self._translate_units(chunk, recent, notes_text, upcoming, language)
            self._saves_fail()
            if self._stop.is_set():
                p.reason = Message("batch.user_stop")
                return
            self._translated_pages(chunk, left)
            p.elapsed = time.monotonic() - start
            self._emit(Message("batch.translated_chunk", chunk=ci + 1, chunks=len(chunks), bubbles=p.bubbles,
                               seconds=round(p.elapsed, 1)))
            if self._fatal is not None:
                p.reason = self._fatal  # Ollama gone, the model missing: the rest would fail the same way
                break

    def _translated_pages(self, chunk: Sequence[ScannedUnit], left: dict[int, int]) -> None:
        """``page_stage`` translate for the pages whose last unit *chunk* held: "done" when this run stored every unit
        of the page, else "failed" (a unit no reply got through for, or one left incomplete)."""
        for u in chunk:
            seq = self._seq_of.get(id(u), 0)
            if not seq or seq not in left:
                continue
            left[seq] -= 1
            if left[seq] > 0:
                continue
            del left[seq]
            mine = [v for v in self._units if self._seq_of.get(id(v)) == seq]
            stored = all(id(v) in self._stored for v in mine)
            self._page_stage(seq, "translate", "done" if stored else "failed")
            if self._view is not None:
                self._view.ended(seq)

    def _run_context(self, start: float) -> None:
        p = self.progress
        p.phase = "read"
        self._take_readings()

        # --- pass 1: every page the reader turns read, no model request ---
        if not self._read_through:
            self._reading_pass(start)
        keep_awake(display=False)  # no more captures: the screen may switch off, the PC must not sleep
        if self._stop.is_set() or self._fatal is not None or p.reason == NO_PAGE:
            return  # nothing is stored; `left` keeps what was read
        units = list(self._units)
        if self._retaken:  # a page that went by was read when the reader went back to it: in its place in the book
            units.sort(key=lambda u: self._seq_of.get(id(u), 0))
        if not self._read_through_before:
            self._emit(Message("batch.pages_read", pages=p.pages, bubbles=p.found))
        if not units:
            p.reason = Message("batch.nothing_new", reason=p.reason or Message("batch.scan_ended"))
            return
        if self.pipeline.translator is None:
            p.reason = Message("pipeline.no_translator")
            return

        # --- pass 2: all the lines, in runs of pages, with the series sheet and the whole story as context ---
        self._translation_pass(units, start)
        self._find_names()

    def _keep_said(self, unit: ScannedUnit, translations: dict[int, str]) -> None:
        """The lines of *unit* just stored (as `Pipeline.commit_unit` stores them: a real translation, stripped), for
        `_find_names`: the Japanese, the text and where it is (the page's fingerprint, the bubble's box)."""
        regions = unit.japanese()
        where = unit.stored_fingerprint or unit.fingerprint
        for i, text in translations.items():
            text = (text or "").strip()
            if 0 <= i < len(regions) and text and self.pipeline.real_translation(regions[i].source_text, text):
                self._said[(id(unit), i)] = RunLine(regions[i].source_text, text, (where, unit.normalize(regions[i].bbox)))

    def _find_names(self) -> None:
        """The names the lines of this run render in more than one way (`name_variants.find_variants`, with the
        series sheet), for the window to offer at the end of the run; the lines go with them without their Japanese
        (the window shows the name alone). Nothing is said or kept on disk; a failure here never ends a run."""
        lines = list(self._said.values())
        if not lines:
            return
        try:
            found = find_variants(lines, self.pipeline.check_sheet())
        except Exception:  # noqa: BLE001 - the helper is an offer: the run's work is stored already
            return
        if found:
            self.progress.names = found
            self.progress.name_lines = [line._replace(source="") for line in lines]
