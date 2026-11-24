"""What several parts of the program share: the target languages offered, the arrows' names, the timings and the
status lines said by key (in English: the keys of the window's catalogs)."""

from __future__ import annotations

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


# The arrow keys as the reader knows them (the other keys are named in the window's language: `shortcuts.key_names`).
KEY_ARROWS = {"Left": "←", "Right": "→", "Up": "↑", "Down": "↓"}

EVENTS_BUSY_MS, EVENTS_IDLE_MS = 16, 80  # the worker's events are handled this often while a job runs, and else
WINDOW_WATCH_MS = 2000  # while no viewer is chosen, look for one this often
# Follow = "events": Windows' notes are taken in every FOLLOW_STEP_MS, and the viewer's frame is captured as often while
# a change settles; a page taken after a change is looked at once more RECHECK_MS later (a viewer may draw a soft
# picture first), and a sharper frame of it is still read again up to RETAKE_WITHIN_MS after; a frame that keeps
# changing is waited for at most SETTLE_TRIES times settle_ms, then the last one is taken.
FOLLOW_STEP_MS = 100
RECHECK_MS = 1000
RETAKE_WITHIN_MS = 10000
SETTLE_TRIES = 10
# While the viewer itself is in front and its frames come by the capture's frame events (`capture.frame_count`), the
# count is looked at every FRAME_STEP_MS, and a new frame is captured at once - no sooner than FRAME_GAP_MS after the
# capture before (a viewer that draws without end is not captured at every frame).
FRAME_STEP_MS = 15
FRAME_GAP_MS = 45
VIEWER_LOADING = "The viewer is still loading; TASlation is waiting."  # (`live._black_step`)
VIEWER_BLACK = "The viewer still shows nothing. Reload the book in its own window: click the book, then press its reload key (F5 in a browser). TASlation carries on once the page shows."  # TASlation presses no key for it
LIVE_CHANGE = 0.0  # the live view draws a frame whose thumbnail differs at all from the one on show
BLANK_SPREAD = 8  # a frame whose thumbnail spans fewer grey levels is blank (as capture.is_blank judges a frame)
QUEUE_RANK = {"auto": 0, "translate": 1}  # a waiting request gives way to one ranked higher
APP_NAME = "TASlation"
APP_EXPANSION = "Tool Assisting Self-translation of manga"  # TAS as in the tool-assisted speedrun: the tool assists, you translate
APP_TITLE = f"{APP_NAME} - {APP_EXPANSION}"  # the main window's title; dialogs keep the short name

READY = "Ready. Turn the pages in the viewer: with Auto on, each page you turn is lettered in your language."
# A browser window minimised after it was chosen: its frames are blank, and it is not restored again by itself
BROWSER_MINIMISED = "Waiting: the browser window with the book is minimised. Click it on the taskbar to bring it back."
VIEWER_RESTORED = "Viewer: {title}  (restored from the taskbar)"  # the viewer chosen was minimised: it is shown again
VIEWER_CLOSED = "The viewer was closed. Open your book again and choose its window."  # (the viewer chooser comes again)
FIRST_PAGE = "Translate a page first: press Translate."  # the page tools with no page translated
THIS_PAGE = "Translate this page first: press Translate."  # ... and with another page on show than the one translated
