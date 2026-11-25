"""The viewer's frames through Windows.Graphics.Capture (the `windows-capture` package; a native extension, no network).

What the compositor holds of a window is taken as it changes, so a viewer is read while it lies fully behind other
windows, which `PrintWindow` could not do for a Chromium page even in front. Measured (docs/OFFLINE_VERIFICATION.md):

* a frame comes only when the window changes: an unchanged window gives one frame and then none, so the latest frame
  is the window as it is now, however old it is;
* frames hold the window's own title bar and borders: they are the size of the DWM extended frame bounds (`crop_box`
  takes the client area out of them);
* a window that is resized may give no frame of its new size until it draws again: the package makes its frames anew
  at the new size and drops the one that showed it, and a browser drawing a still page gave none for 1.1-1.25 s; a new
  session's first frame is the window as it is, 48-61 ms after its start (a browser, measured), so a frame of another
  size than the window's starts the session over (`restart`), once for every size - and once more for a size it had
  before, once a frame has fitted another size meanwhile (`fitted`: a window restored from maximised to the size it was
  given before);
* the package takes a window by handle, so windows that share a title do not matter, and a title that changes page by
  page does not touch a session.

One session runs at a time, for the viewer in use (a session for another window closes it; `close` at a change of
viewer and at exit). Only the latest frame is kept, in memory; nothing here writes a file. The session is kept by a
daemon thread of its own, the only one to call the package's control object; the package runs the capture on its
thread and calls `on_frame_arrived` there, which only copies the frame.

When the package is missing or will not load, or a session fails, `latest` gives None and the caller goes on with
`PrintWindow`; `route` says which one is in use (`taslation doctor`). A session that fails is tried again after
RETRY_S: a session that ended while its window lives (a graphics driver reset) comes back.
"""

from __future__ import annotations

import atexit
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from PIL import Image

ROUTE = "Windows.Graphics.Capture"
MIN_BUILD = 18362  # Windows 10 1903, the first with capture of a window by handle
START_WAIT_S = 0.6  # how long a new session is waited for: its first frame took 281 ms on the test machine
RETRY_S = 5.0  # a session that ended is started again this long later at the earliest
CHECK_S = 0.25  # how often the session's thread looks at Stop and at whether the capture still runs
JOIN_S = 1.0  # at exit, how long the session's thread is given to end the capture
SIZE_SLACK = 1  # a frame this many pixels off the window's bounds is the window's (rounding at fractional scaling)
MIN_UPDATE_MS = 50  # the system sends at most one frame in so many ms, the last one of a change included
FAST_UPDATE_MS = 16  # ... while TASlation's lettering lies over the viewer (see-through mode: `set_update_ms`)
# What a session asks for, best first: an older system refuses the first ones, and the capture then runs with the
# border the system draws round a captured window rather than not at all.
OPTIONS: tuple[dict[str, Any], ...] = ({"draw_border": False, "minimum_update_interval": MIN_UPDATE_MS},
                                       {"draw_border": False}, {})
_update_ms = MIN_UPDATE_MS  # what the sessions started from now on ask for (`set_update_ms`)

Box = tuple[int, int, int, int]  # left, top, right, bottom


@dataclass(frozen=True)
class Frame:
    """One frame of the window: *bgra* (height, width, 4), a copy of its own; *seq* counts the session's frames."""

    bgra: np.ndarray
    seq: int

    @property
    def size(self) -> tuple[int, int]:
        return self.bgra.shape[1], self.bgra.shape[0]

    def image(self, box: Box | None = None) -> Image.Image:
        """The frame, or the part of it in *box* (`crop_box`), as an RGB image."""
        left, top, right, bottom = box if box is not None else (0, 0, *self.size)
        return Image.fromarray(np.ascontiguousarray(self.bgra[top:bottom, left:right, 2::-1]))


def crop_box(size: tuple[int, int], bounds: Box, client: tuple[int, int, int, int] | None = None) -> Box | None:
    """Where the client area lies in a frame of *size* (width, height) of a window with the extended frame bounds
    *bounds* (screen pixels, which is what a frame shows: without the invisible resize borders), *client* being
    (x, y, width, height) on the screen; the whole frame when *client* is None. None when the frame is not of this
    window's size (a resize on its way) or holds nothing of the client area. Only what lies inside the bounds is
    taken."""
    width, height = size
    if abs(width - (bounds[2] - bounds[0])) > SIZE_SLACK or abs(height - (bounds[3] - bounds[1])) > SIZE_SLACK:
        return None
    if client is None:
        return (0, 0, width, height) if width > 0 and height > 0 else None
    x, y, w, h = client
    left, top = x - bounds[0], y - bounds[1]
    box = max(0, left), max(0, top), min(width, left + w), min(height, top + h)
    return box if box[0] < box[2] and box[1] < box[3] else None


class _Session:
    """The capture of one window, kept by a daemon thread (see the module's notes); its frames are counted on from
    *seq* (a session started over goes on from the count of the one before)."""

    def __init__(self, hwnd: int, api: Any, seq: int = 0):
        self.hwnd = hwnd
        self.started = time.monotonic()
        self.ended_at: float | None = None
        self.error = ""
        self._api = api
        self._changed = threading.Condition()
        self._frame: Frame | None = None
        self._seq = seq
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"wgc-{hwnd:x}", daemon=True)
        self._thread.start()

    @property
    def ended(self) -> bool:
        return self.ended_at is not None

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def has_frame(self) -> bool:
        return self._frame is not None

    def _run(self) -> None:
        for options in _options():
            try:
                self._capture(options)
                self.error = ""
                break
            except Exception as e:  # whatever the package raises (it has no error classes of its own)
                self.error = str(e)
                if self.has_frame or self._stop.is_set():
                    break
        self._ended()

    def _capture(self, options: dict[str, Any]) -> None:
        session = self

        def on_frame_arrived(frame: Any, _control: Any) -> None:
            session._arrived(frame.frame_buffer)

        def on_closed() -> None:
            session._ended()

        capture = self._api(cursor_capture=False, window_hwnd=self.hwnd, **options)
        capture.event(on_frame_arrived)
        capture.event(on_closed)
        control = capture.start_free_threaded()
        while not self._stop.wait(CHECK_S):
            if control.is_finished():
                control.wait()  # (raises what ended it)
                return
        control.stop()

    def _arrived(self, buffer: np.ndarray) -> None:
        frame = np.array(buffer, copy=True)  # the package's buffer lives for this call only
        with self._changed:
            self._seq += 1
            self._frame = Frame(frame, self._seq)
            seq = self._seq
            self._changed.notify_all()
        for listener in tuple(_listeners):  # (told on the capture's own thread: a listener only takes a note)
            try:
                listener(self.hwnd, seq)
            except Exception:  # noqa: BLE001 - a listener's fault never stops the capture
                pass

    def peek(self) -> Frame | None:
        with self._changed:
            return self._frame

    def _ended(self) -> None:
        with self._changed:
            if self.ended_at is None:
                self.ended_at = time.monotonic()
            self._changed.notify_all()

    def latest(self, timeout: float) -> Frame | None:
        """The newest frame; none yet: waits for the first until *timeout* after the session's start (never again
        later: an unchanged minimised window gives none, and every look would wait)."""
        with self._changed:
            left = self.started + timeout - time.monotonic()
            if self._frame is None and left > 0:
                self._changed.wait_for(lambda: self._frame is not None or self.ended, left)
            return self._frame

    def close(self, wait: bool = False) -> None:
        self._stop.set()
        if wait:
            self._thread.join(JOIN_S)


def _options() -> tuple[dict[str, Any], ...]:
    """OPTIONS with the update interval asked for now (`set_update_ms`)."""
    if _update_ms == MIN_UPDATE_MS:
        return OPTIONS
    return ({**OPTIONS[0], "minimum_update_interval": _update_ms}, *OPTIONS[1:])


_lock = threading.Lock()
_session: _Session | None = None
_listeners: list[Callable[[int, int], None]] = []  # told of every frame: (window, its frame count)
_restarted: tuple[int, tuple[int, int]] | None = None  # the window and its size the session was last started over for
_api: Any = None
_why = ""  # why the package cannot be used


def _load() -> Any:
    """The package's capture class, imported on first use; None (with `_why` set) when it cannot be used."""
    global _api, _why
    if _api is None and not _why:
        if sys.platform != "win32":
            _why = "Windows only"
        elif sys.getwindowsversion().build < MIN_BUILD:
            _why = "needs Windows 10 version 1903 or later"
        else:
            try:
                from windows_capture import WindowsCapture

                _api = WindowsCapture
            except ImportError as e:
                _why = "the windows-capture package is not installed" if e.name == "windows_capture" else str(e)
            except Exception as e:  # a native extension that will not load
                _why = f"the windows-capture package does not load: {e}"
    return _api


def _session_for(hwnd: int) -> _Session | None:
    """The running session of *hwnd*, started when needed (any other window's closes); None when there can be none,
    or the last one ended less than RETRY_S ago."""
    global _session
    with _lock:
        session = _session
        if session is not None and session.hwnd == hwnd:
            if session.ended_at is None:
                return session
            if time.monotonic() - session.ended_at < RETRY_S:
                return None
        if session is not None:
            session.close()
            _session = None
        api = _load()
        if api is None:
            return None
        _session = _Session(hwnd, api)
        return _session


def latest(hwnd: int, timeout: float = START_WAIT_S) -> Frame | None:
    """The newest frame of the window *hwnd*, however old (a frame comes only when the window changes). A session is
    started when there is none; it is given until *timeout* after its start to send its first frame. None: no frame
    to be had (the caller goes on with PrintWindow)."""
    session = _session_for(hwnd)
    return session.latest(timeout) if session is not None else None


def restart(hwnd: int, size: tuple[int, int]) -> bool:
    """The running session of the window *hwnd* started over, its frame count going on from there (a count never goes
    back): the window's frame there is not of its size *size* (width, height of its bounds), and a new session's first
    frame is the window as it is (see the module's notes; `latest` waits for it). Once for every size: a window whose
    frames never fit is not started over at every look. Whether it was."""
    global _session, _restarted
    with _lock:
        session = _session
        if session is None or session.hwnd != hwnd or session.ended or _restarted == (hwnd, size):
            return False
        session.close()
        _session = _Session(hwnd, session._api, session.seq)
        _restarted = (hwnd, size)
        return True


def fitted(hwnd: int, size: tuple[int, int]) -> None:
    """A frame of the window *hwnd* fitted its size *size* (width, height of its bounds): a size it was started over
    for that is another one may be started over for again (`restart`) - the window had another size meanwhile, and
    back at that size (restored from maximised, say) its session may give no frame of it until it draws again."""
    global _restarted
    with _lock:
        if _restarted is not None and _restarted[0] == hwnd and _restarted[1] != tuple(size):
            _restarted = None


def count(hwnd: int) -> int | None:
    """How many frames the session of the window *hwnd* has delivered so far, in memory: nothing is captured or started
    for it. None when no session of it runs that has sent a frame (`PrintWindow` is the route then)."""
    with _lock:
        session = _session
    if session is None or session.hwnd != hwnd or session.ended or not session.has_frame:
        return None
    return session.seq


def live(hwnd: int) -> bool:
    """Whether a session of the window *hwnd* runs and has sent a frame."""
    with _lock:
        session = _session
    return session is not None and session.hwnd == hwnd and not session.ended and session.has_frame


def close(hwnd: int | None = None, wait: bool = False) -> None:
    """End the session of the window *hwnd*, or the one there is. *wait*: until its thread has ended the capture."""
    global _session
    with _lock:
        session = _session
        if session is None or (hwnd is not None and session.hwnd != hwnd):
            return
        _session = None
    session.close(wait)


def peek(hwnd: int) -> Frame | None:
    """The newest frame of the running session of the window *hwnd*, if there is one; nothing is started or waited
    for (what another thread than Tk's - the see-through window's - may ask)."""
    with _lock:
        session = _session
    if session is None or session.hwnd != hwnd or session.ended:
        return None
    return session.peek()


def add_listener(listener: Callable[[int, int], None]) -> None:
    """*listener* told of every frame that comes, as (window, frame count), on the capture's thread: it must only take
    a note (set an event) and return."""
    if listener not in _listeners:
        _listeners.append(listener)


def remove_listener(listener: Callable[[int, int], None]) -> None:
    if listener in _listeners:
        _listeners.remove(listener)


def set_update_ms(ms: int) -> bool:
    """The least time between two frames the sessions ask the system for, from now on (MIN_UPDATE_MS; FAST_UPDATE_MS
    while the lettering lies over the viewer); a running session of another interval is started over with it (its
    frame count goes on). Whether one was."""
    global _update_ms, _session
    ms = max(1, int(ms))
    with _lock:
        if ms == _update_ms:
            return False
        _update_ms = ms
        session = _session
        if session is None or session.ended:
            return False
        session.close()
        _session = _Session(session.hwnd, session._api, session.seq)
        return True


def update_ms() -> int:
    return _update_ms


def route() -> str:
    """Which capture is in use, for `taslation doctor`: its name, or PrintWindow and why."""
    with _lock:
        api = _load()
    return ROUTE if api is not None else f"PrintWindow ({_why})"


atexit.register(close, wait=True)  # before the interpreter goes, while the package's thread can still call back
