"""A viewer that stays black, and the person told how to bring it back; a viewer's window left enlarged by a session of
an older version that ended without closing the window, put back at the next start.

A browser-based viewer sometimes shows nothing: a loading screen that may just be slow, or that is stuck (a black page
with a spinner, which a reload cures), or a frame that stays black. `capture.is_black` over the capture
area says so, and `BlackWatch` is what follows, one spell of black frames at a time, for the window (`ui.live`, its
heartbeat: the Tk thread is never held). TASlation presses no
key for it, ever (no key the person did not press goes to the viewer):

1. *Wait.* `black_wait_s` with the window's size stable (a change of it starts the wait over). After `SAY_AFTER_S` the
   status line says the viewer is still loading, once. A frame that recovers ends it silently.
2. *Notice.* Once, in plain words: the person reloads the book in the viewer (its reload key - F5 in a browser).
   The watch goes on: the next frame that shows something ends the spell, and the page is taken as the viewer shows
   it then.

No polling of the viewer: `BlackWatch.new_frame` looks about once a second, in memory, at whether the capture session
delivered a frame (`capture.frame_count`), and only such a frame is taken and judged. Without a session (`PrintWindow`)
one capture every `FALLBACK_LOOK_S`.

A frame the capture cannot read while the screen shows it cannot be told from a black one: the person's reload is a
plain retry, and nothing here works around anything (no flags, no change of hardware acceleration or display
affinity).

TASlation enlarges no viewer's window and moves no window of another program. Versions up to 1.0.1 enlarged the
viewer's, and kept the window and its rectangle before in the state folder's ui.json while it was enlarged (the table
ENLARGED_TABLE, the window's handle -> its process, class, rectangle before and rectangle given), so that a session
that ended without putting it back - a crash, the process ended - did not leave it large. What such a session left
there is put back once, at the start (`put_back_enlarged`): only a window that still exists with the same process and
class, shown, not maximised, and still of the size it was given (`capture.restore_window`: the person may have
resized it since); then the table is cleared. No key is pressed for it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .capture import CaptureError, Enlarged, frame_count, restore_window, window_class, window_exists, window_pid
from .i18n import load_ui_table, save_ui_entry

ENLARGED_TABLE = "enlarged_windows"  # ui.json: the viewers' windows a version up to 1.0.1 enlarged and did not put back

SAY_AFTER_S = 8.0  # the viewer black this long: the status line says it is still loading
STEP_S = 1.0  # how often a spell is looked at (in memory)
FALLBACK_LOOK_S = 2.0  # without a capture session: one capture this often

# what `BlackWatch.step` says
LOADING = "loading"  # the viewer is still loading: said once
RECOVERED = "recovered"  # a frame shows something: the spell is over
GAVE_UP = "gave_up"  # the wait is over: the person is told to reload the book (said once)


class BlackWatch:
    """One spell of black frames of the window *hwnd*. `step` is called with the latest word on the frame,
    `new_frame` says when there is a new frame to judge. See the module's notes."""

    say_after_s = SAY_AFTER_S
    fallback_look_s = FALLBACK_LOOK_S
    step_s = STEP_S

    def __init__(self, hwnd: int, settings: Any, *, size: Any = None, now: float | None = None):
        self.hwnd = hwnd
        self.settings = settings
        self.size = size
        self.since = time.monotonic() if now is None else now
        self.phase = "wait"  # wait, told
        self.said = False
        self.seq = frame_count(hwnd)
        self.looked = self.since
        self.next_at = self.since  # the window's heartbeat: when to look next

    @property
    def told(self) -> bool:
        """Whether the person has been told to reload the book: what comes after that may be another page."""
        return self.phase == "told"

    def new_frame(self, now: float) -> bool:
        """Whether a frame is there to judge: the capture session delivered one since the last that was judged (in
        memory: this captures nothing); without a session, once every `fallback_look_s`."""
        seq = frame_count(self.hwnd)
        if seq is None:
            self.seq = None
            if now - self.looked < self.fallback_look_s:
                return False
            self.looked = now
            return True
        if seq == self.seq:
            return False
        self.seq = seq
        return True

    def step(self, black: bool, size: Any, now: float) -> str:
        """The spell one step on: *black*, what the latest frame judged was; *size*, the window's. Returns what
        happened ("": nothing to tell)."""
        if not black:
            return RECOVERED
        if self.phase != "wait":
            return ""
        if size != self.size:  # a window being resized gives black frames: the wait starts over
            self.size, self.since = size, now
            return ""
        waited = now - self.since
        if not self.said and waited >= self.say_after_s:  # said first: a slow step must not skip it
            self.said = True
            return LOADING
        if waited >= float(self.settings.black_wait_s):
            self.phase = "told"
            return GAVE_UP
        return ""


# ------------------------------------------------------------------ a viewer's window left enlarged
def put_back_enlarged(state_dir: Path | str) -> int:
    """At the start: every window a session of a version up to 1.0.1 enlarged and did not put back, back on its
    rectangle before - only
    one that still exists with the same process and class and has the size it was given (`capture.restore_window`).
    The table is cleared either way. Returns how many were put back."""
    table = load_ui_table(Path(state_dir), ENLARGED_TABLE)
    put = 0
    for key, value in table.items():
        try:
            hwnd, entry = int(key), json.loads(value)
            before = tuple(int(v) for v in entry["before"])
            given = tuple(int(v) for v in entry["given"])
            pid, cls = int(entry["pid"]), str(entry["class"])
        except (TypeError, ValueError, KeyError):
            continue
        if len(before) != 4 or len(given) != 4 or not pid:
            continue
        try:
            if (window_exists(hwnd) and window_pid(hwnd) == pid and window_class(hwnd) == cls
                    and restore_window(Enlarged(hwnd, before, given))):
                put += 1
        except CaptureError:
            pass
    for key in table:
        save_ui_entry(Path(state_dir), ENLARGED_TABLE, key, None)
    return put
