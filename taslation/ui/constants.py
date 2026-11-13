"""What several parts of the reader window share: the target languages offered, the keys passed on
to the viewer and their names, the timings, the status lines said by key (in English: the keys of the window's
catalogs), and whether a whole-book run is on (`in_a_run`)."""

from __future__ import annotations

from typing import Any

LANGUAGES = [
    "English", "Spanish", "Portuguese (Brazil)", "French", "German", "Italian", "Russian", "Polish", "Dutch",
    "Turkish", "Indonesian", "Vietnamese", "Thai", "Chinese (Simplified)", "Chinese (Traditional)", "Korean",
    "Arabic", "Hebrew", "Hindi", "Bengali",
]
# the window's language -> the target language it stands for at the very first start (`app.first_target`)
WINDOW_TARGETS = {
    "en": "English", "es": "Spanish", "pt": "Portuguese (Brazil)", "fr": "French", "de": "German", "it": "Italian",
    "ru": "Russian", "pl": "Polish", "nl": "Dutch", "tr": "Turkish", "id": "Indonesian", "vi": "Vietnamese", "th": "Thai",
    "zh": "Chinese (Simplified)", "zh-tw": "Chinese (Traditional)", "ko": "Korean",
}


FORWARDED_KEYS = {
    "Left": "Left", "Right": "Right", "Up": "Up", "Down": "Down", "Prior": "PageUp", "Next": "PageDown",
    "Home": "Home", "End": "End", "space": "Space",
}
# A forwarded key as the reader knows it: the arrow keys as arrows (the others are named in the window's language:
# `reading.key_label`).
KEY_ARROWS = {"Left": "←", "Right": "→", "Up": "↑", "Down": "↓"}

EVENTS_BUSY_MS, EVENTS_IDLE_MS = 16, 80  # the worker's events are handled this often while a job runs, and else
WINDOW_WATCH_MS = 2000  # while no viewer is chosen, look for one this often
# Follow = "events": Windows' notes are taken in every FOLLOW_STEP_MS, and the viewer's frame is captured as often while
# an operation's change is awaited; a page taken after an operation is looked at once more RECHECK_MS later (a viewer
# may draw a soft picture first), and a sharper frame of it is still read again up to RETAKE_WITHIN_MS after; a frame
# that keeps changing is waited for at most SETTLE_TRIES times settle_ms, then the last one is taken.
FOLLOW_STEP_MS = 100
RECHECK_MS = 1000
RETAKE_WITHIN_MS = 10000
SETTLE_TRIES = 10
# While the viewer itself is in front and its frames come by the capture's frame events (`capture.frame_count`), the
# count is looked at every FRAME_STEP_MS, and a new frame is captured at once - no sooner than FRAME_GAP_MS after the
# capture before (a viewer that draws without end is not captured at every frame).
FRAME_STEP_MS = 15
FRAME_GAP_MS = 45
# A key passed on is pressed for real only once page_turn_wait_ms passed without the viewer's frame changing at all;
# a viewer whose frame changed at all took the key, and has FOLLOW_WAITS times that to turn the page; after a key
# pressed for real, a page that turns once more within TWO_TURNS_S was turned twice (the posted key came late).
FOLLOW_WAITS = 3
TWO_TURNS_S = 1.0
VIEWER_LOADING = "The viewer is still loading; TASlation is waiting."  # (`live._black_step`)
VIEWER_BLACK = "The viewer still shows nothing. Reload the book in its own window: click the book, then press its reload key (F5 in a browser). In TASlation's window F5 translates instead. TASlation carries on once the page shows."  # TASlation presses no key for it
READING_NOTE_MS = 4000  # how long a status line stays at the bottom of the reading window
WINDOW_ALPHA = 0.99  # not quite opaque (Windows, and the reading window): a Chromium viewer that an opaque window covers entirely stops drawing
LIVE_CHANGE = 0.0  # the live view draws a frame whose thumbnail differs at all from the one on show
BLANK_SPREAD = 8  # a frame whose thumbnail spans fewer grey levels is blank (as capture.is_blank judges a frame)
QUEUE_RANK = {"auto": 0, "translate": 1, "batch": 2}  # a waiting request gives way to one ranked higher
APP_NAME = "TASlation"
APP_EXPANSION = "Tool Assisting Self-translation"  # TAS as in the tool-assisted speedrun: the tool assists, you translate
APP_TITLE = f"{APP_NAME} - {APP_EXPANSION}"  # the main window's title; dialogs keep the short name

READY = "Ready. Turn the pages here with the page keys, or click the page. F5: translate this page now · F11: reading mode."
NO_VIEWER = ("Open your book in its viewer (a desktop viewer, or a browser-based viewer in a browser window of its "
             "own). TASlation finds it by itself - or pick its window in the Viewer list above.")
READING_MODE = "Reading mode: page keys turn the viewer's pages; F11 or Esc leaves it."
# ... the first time in a session that reading mode turns Auto on for itself (it is off again afterwards)
READING_MODE_AUTO = "Reading mode: page keys turn the viewer's pages, and Auto is on until you leave, so each page is translated as you turn it. F11 or Esc leaves it."
READING_ONLY = (READING_MODE, READING_MODE_AUTO,
                "Reading mode translates page by page; the whole-book scan waits until you leave it (Esc).")
# The first time in a session that a whole-book run turns Auto off (the run reads the pages turned; Auto comes back)
RUN_AUTO_OFF = "Whole-book run starting... Auto is off while the run reads each page you turn, and on again when it ends."
# Leaving reading mode after pages were translated there under a name that names no book: the name given since
KEPT_FROM_NOW = "The pages are kept under {book} from now on (F5 keeps the page on show too)."
CLOSE_READING = "Leave reading mode (Esc)"  # the faint button at the top edge of the reading window
# A browser window minimised after it was chosen: its frames are blank, and it is not restored again by itself
BROWSER_MINIMISED = "Waiting: the browser window with the book is minimised. Click it on the taskbar to bring it back."
VIEWER_RESTORED = "Viewer: {title}  (restored from the taskbar)"  # the viewer chosen was minimised: it is shown again
VIEWER_CLOSED = "The viewer was closed. Open your book again; TASlation finds it by itself."
FIRST_PAGE = "Translate a page first: press F5."  # the page tools with no page translated
THIS_PAGE = "Translate this page first: press F5."  # ... and with another page on show than the one translated
# A book whose cache holds this many translated pages has been read: Auto no longer offers to read the whole book
# first, and a page of it not translated yet (a cover with no lines, a page skipped) is translated as a page. Fewer
# - a cover, a page or two tried with F5 - are a book not read yet.
BOOK_READ_PAGES = 4
# said once a whole-book run has translated the book and the window leaves translator mode by itself
READER_AFTER_RUN = "The book is translated, so TASlation switches to reader mode. Choose Translator mode to check the translations on the page."


def book_read(pages: int | None) -> bool:
    """Whether a book whose cache holds *pages* translated pages has been read (`BOOK_READ_PAGES`; None: cannot be
    told, so not)."""
    return pages is not None and pages >= BOOK_READ_PAGES


def in_a_run(window: Any) -> bool:
    """Whether a whole-book run is on: from its start (the viewer's window may still be enlarged, the reader not made
    yet) until it has ended."""
    return bool(getattr(window, "_batching", False) or getattr(window, "batch", None) is not None)


def viewer_rests(window: Any) -> bool:
    """Whether a run is on that does not follow the reader just now (it starts, or has gone on to the
    translation): only while it reads the pages the reader turns do their keys and clicks go on to the viewer."""
    batch = getattr(window, "batch", None)
    return in_a_run(window) and not (batch is not None and batch.following)
