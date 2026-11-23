"""See-through mode on the Tk side (a prototype behind ``Settings.see_through``, off by default; the Reader role, the
viewer's window or its full screen): TASlation's lettering lies over the viewer's own window (`capture.seethrough`),
and the viewer takes every click and key itself.

* `start` makes the see-through window at the window's start when the setting is on (and asks the capture for frames
  up to every `wgc.FAST_UPDATE_MS`); `close` ends it. `tick` (every TICK_MS) tells it which viewer to lie over, holds
  the hot key (`HOTKEY`, only while the viewer is in front: it is the system's for as long as it is registered) and
  hands it the page's patches when they changed (`present`; `_redisplay` asks for that too).
* The patches are where the lettered page differs from the frame it was read from - the page filling in (drafts,
  then the final page) and the last translated page -, made on the Tk thread and handed over as immutable arrays.
  Whether a patch shows is the see-through window's own decision, at every frame of the viewer's
  (`taslation.seethrough`: a patch belongs to the pixels it was made from).
* Which frames start a page job (`frame_look`, `waits`, `reading_frame`): another page only when the steady part of
  the page area changed (`seethrough.steady_thumb` of `steady_area`: bars at its top and bottom come and go without a
  job), never on a frame to wait out (a black with a spinner, half a spread, a washed-out preview), nor on one with
  bars over it until they have stayed BAR_WAIT_S - then it is read with the bars' rows painted over (their words are
  not the book's). Once they have gone (`after_bars`), the page's cached translations are carried over to the frame
  without them, the bubbles that reach those rows (cut by a bar) left out, and the page is read once more for those
  alone (`Pipeline.carry_over`: the lines kept are not asked again). The page on a flat ground of any colour is the
  capture area (`seethrough.ground_box`: a white ground too).

Nothing here presses a key, posts a message or moves the foreground."""

from __future__ import annotations

import time
import tkinter as tk
from typing import Any

import numpy as np
from PIL import Image

from .. import seethrough as st
from ..capture import foreground_owner, foreground_window
from ..capture import seethrough as window
from ..capture import wgc
from ..capture.overlay import HotKeys

TICK_MS = 50
HOTKEY = "see_through"
HOTKEY_VK = 0x78  # F9: free in the default keymap and not one of over-the-book's hot keys (F5, F11, Esc)
BAR_WAIT_S = 3.5  # a frame with bars over the page is read only once they have stayed so long (a viewer's own bars go
# by themselves in 1-3 s once the pointer rests; bars held longer are painted over in the frame read)
MEMO_KEPT = 4
LOOK_INFO = "taslation.see_look"  # (the picture's info) the look a frame read with its bars painted over was given
PAINTED_INFO = "taslation.see_painted"  # (the picture's info) the rows painted over in it
GONE_LOOK_MS = 150  # once the bars have gone, the viewer is looked at so soon (a page read under them: read_under_bars)
CUT_PX = 3  # a bubble read this close to rows painted over was cut by them (`read_under_bars`)


QUIET_MS = 500  # (see-through mode) the decoy of `quiet_start` goes so long after the window's start is made


def on(app: Any) -> bool:
    """Whether see-through mode runs in the window *app*."""
    return getattr(app, "_see_through", None) is not None


def quiet_start(app: Any, settings: Any) -> None:
    """At the very start of the window, before Tk first shows it, in see-through mode (Windows): Tk activates the
    first top-level window it makes (SetActiveWindow when it is first shown - Tk 8.6.15, whatever its state: hidden
    or minimised alike), which takes the foreground from the viewer; so the first one it makes is a decoy put inside
    a frame of the window's own (``-use``), a child window, which nothing activates. The window itself is then shown
    as Tk shows every later one, not activated (SW_SHOWNOACTIVATE): the viewer stays in front and takes the reader's
    keys, F9 among them, with no click first. Nothing moves the foreground. The decoy goes once the window is shown
    (`quiet_started`)."""
    app._quiet_decoy = None
    app._quiet_ended = False
    if not (bool(getattr(settings, "see_through", False)) and window.IS_WINDOWS):
        return
    try:
        box = tk.Frame(app, container=True)  # (never shown)
        decoy = tk.Toplevel(app, use=str(box.winfo_id()))
        app._quiet_decoy = (decoy, box)
    except tk.TclError:  # (no decoy: the window takes the foreground at its start as ever)
        pass


def quiet(app: Any) -> bool:
    """Whether the window starts quietly (`quiet_start`): not maximised then, for Windows activates a window it
    maximises."""
    return getattr(app, "_quiet_decoy", None) is not None and not getattr(app, "_quiet_ended", False)


def quiet_started(app: Any) -> None:
    """The window's start made (Tk shows it at its first idle, the decoy first): the decoy goes QUIET_MS later."""
    if getattr(app, "_quiet_decoy", None) is None:
        return

    def drop() -> None:
        decoy, app._quiet_decoy = app._quiet_decoy, None
        for widget in decoy or ():
            try:
                widget.destroy()
            except tk.TclError:
                pass

    app.after(QUIET_MS, drop)


def quiet_end(app: Any) -> None:
    """No quiet start after all (the legal notice, which is the reader's to answer: it and the window after it take
    the foreground as ever)."""
    app._quiet_ended = True


def start(app: Any) -> bool:
    """The see-through window made when the setting asks for it (Windows only); whether it runs."""
    app._see_through = None
    app._see_memo = []
    app._see_keys = None
    app._see_bars_since = None
    app._see_rest_box = None
    app._see_job = None
    app._see_carries = []  # (when, pages carried over, bubbles left out), see after_bars
    if not bool(getattr(app.settings, "see_through", False)):
        return False
    over = window.SeeThrough.start()
    if over is None:
        return False
    app._see_through = over
    wgc.set_update_ms(wgc.FAST_UPDATE_MS)
    try:
        app._see_job = app.after(TICK_MS, lambda: _tick(app))
    except Exception:  # noqa: BLE001 - no Tk loop (a test): the window runs all the same
        pass
    return True


def close(app: Any) -> None:
    over = getattr(app, "_see_through", None)
    keys = getattr(app, "_see_keys", None)
    if keys is not None:
        keys.close()
        app._see_keys = None
    if over is not None:
        app._see_through = None
        over.close()
        wgc.set_update_ms(wgc.MIN_UPDATE_MS)


def _tick(app: Any) -> None:
    app._see_job = None
    if not on(app):
        return
    try:
        tick(app)
    finally:
        try:
            app._see_job = app.after(TICK_MS, lambda: _tick(app))
        except Exception:  # noqa: BLE001 - the window is going
            pass


def tick(app: Any) -> None:
    """The viewer followed, the hot key held while the viewer is in front (and its presses acted on), the patches
    handed over when they changed."""
    over = app._see_through
    win = getattr(app, "selected", None)
    hwnd = int(win.hwnd) if win is not None else 0
    over.follow(hwnd)
    _hotkey(app, hwnd)
    present(app)


def _hotkey(app: Any, viewer: int) -> None:
    owner = foreground_owner(foreground_window(), viewer) if viewer else ""
    keys = app._see_keys
    wanted = owner == "viewer"
    if keys is None:
        if not wanted:
            return
        keys = app._see_keys = HotKeys.start()
        if keys is None:
            return
    if wanted and HOTKEY not in keys.registered:
        keys.register(HOTKEY, HOTKEY_VK)
    elif not wanted and HOTKEY in keys.registered:
        keys.unregister(HOTKEY)
    for name in keys.take():
        if name == HOTKEY:
            toggle(app)


def toggle(app: Any) -> None:
    """The hot key: the lettering over the viewer hidden, or shown again."""
    over = getattr(app, "_see_through", None)
    if over is not None:
        over.set_on(not over.on)


# ------------------------------------------------------------------ the patches
def _rgb(image: Image.Image) -> np.ndarray:
    return np.asarray(image if image.mode == "RGB" else image.convert("RGB"))


def pairs(app: Any) -> list[tuple[Image.Image, Image.Image, bool, tuple[Any, ...]]]:
    """(frame read, lettered page, final, what it is now) of the page filling in and of the last translated page, the
    older first."""
    out = []
    fill = getattr(app, "_fill", None)
    result = getattr(app, "last_result", None)
    if result is not None and result.image is not None and result.original is not None and (
            fill is None or result.original is not fill.frame):
        out.append((result.original, result.image, True, ("result", id(result.image))))
    if fill is not None:
        lettered = fill.final if fill.final is not None else fill.page
        if lettered is not None:
            out.append((fill.frame, lettered, fill.final is not None,
                        ("fill", id(lettered), tuple(fill.states), fill.final is not None)))
    return out


def present(app: Any) -> None:
    """The patches of the page filling in and of the last translated page handed to the see-through window, each when
    it changed (made here, on the Tk thread: some 5-10 ms for a full-HD page)."""
    over = getattr(app, "_see_through", None)
    if over is None:
        return
    memo: list[tuple[Image.Image, tuple[Any, ...]]] = app._see_memo
    for original, lettered, final, state in pairs(app):
        known = next((s for img, s in memo if img is original), None)
        if known == state:
            continue
        if original.size != lettered.size:
            continue
        patches = st.make_patches(_rgb(original), _rgb(lettered))
        over.present(id(original), original.size, patches, final)
        memo[:] = [(original, state), *[(img, s) for img, s in memo if img is not original]][:MEMO_KEPT]


# ------------------------------------------------------------------ which frames start a job
def area_rgb(app: Any, image: Image.Image, facts: Any) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """The capture area of *image* (the reader's own when set, else the whole frame) and its box."""
    hand = app._hand_set() if getattr(app, "_manual_area", False) else (0, 0, 0, 0)
    from . import area

    box = area.margins_to_box(hand, image.size)
    if box[2] <= box[0] or box[3] <= box[1]:
        box = (0, 0, image.width, image.height)
    rgb = facts.rgb()
    return rgb[box[1]:box[3], box[0]:box[2]], box


def frame_look(app: Any, image: Image.Image, facts: Any) -> st.Look:
    """`seethrough.look` of *image*'s capture area (kept with the frame's facts), its boxes in the frame's pixels; for
    a frame `reading_frame` made, the look it was given (`LOOK_INFO`)."""
    given = getattr(image, "info", {}).get(LOOK_INFO)
    if given is not None:
        return given

    def make() -> st.Look:
        rgb, box = area_rgb(app, image, facts)
        before = app._see_rest_box
        if before is not None:
            before = (before[0] - box[0], before[1] - box[1], before[2] - box[0], before[3] - box[1])
        found = st.look(rgb, before)
        page = None if found.box is None else (found.box[0] + box[0], found.box[1] + box[1],
                                                 found.box[2] + box[0], found.box[3] + box[1])
        rows = tuple((a + box[1], b + box[1]) for a, b in found.bands)
        return st.Look(page, rows, found.kind, found.ground)

    return facts.get(("see_look",), make)


def note_frame(app: Any, image: Image.Image, facts: Any) -> None:
    """A frame just captured of the viewer (`LiveViewMixin._capture_frame`): since when bars lie over the page (and a
    look once they have stayed BAR_WAIT_S: a viewer draws no new frame while they stand still), and the page box of
    the last frame at rest (which tells half a spread)."""
    found = frame_look(app, image, facts)
    if found.kind is not None:
        return
    if not found.bands:
        if app._see_bars_since is not None:  # the bars have gone: a page read under them is read once more
            try:
                app.after(GONE_LOOK_MS, lambda: _bars_due(app, gone=True))
            except Exception:  # noqa: BLE001 - no Tk loop (a test)
                pass
        app._see_bars_since = None
        if found.box is not None:
            app._see_rest_box = found.box
        return
    if app._see_bars_since is None:
        app._see_bars_since = time.monotonic()
        try:
            app.after(int(BAR_WAIT_S * 1000) + 30, lambda: _bars_due(app))
        except Exception:  # noqa: BLE001 - no Tk loop (a test)
            pass


def _bars_due(app: Any, gone: bool = False) -> None:
    """The bars have stayed BAR_WAIT_S, or (*gone*) have gone: the viewer looked at again, as a look of the follow's
    does (while a job runs, the look comes once it is done: `_look`)."""
    if on(app) and (gone or (app._see_bars_since is not None and not getattr(app, "busy", False))):
        try:
            app._tick()
        except Exception:  # noqa: BLE001 - a look that fails is looked at again by the follow
            pass


def waits(app: Any, image: Image.Image, facts: Any) -> bool:
    """Whether the frame *image* is one to wait out (it counts as one with nothing drawn: neither shown nor followed):
    a loading one (`seethrough.loading_kind`), or one with bars over the page that have not stayed BAR_WAIT_S yet
    (`note_frame`)."""
    found = frame_look(app, image, facts)
    if found.kind is not None:
        return True
    if not found.bands:
        return False
    since = app._see_bars_since
    return since is None or time.monotonic() - since < BAR_WAIT_S


def reading_frame(app: Any, image: Image.Image, facts: Any) -> Image.Image:
    """The frame as it is read: with the rows of bars painted in the ground's colour (`waits` lets such a frame
    through only once they have stayed BAR_WAIT_S), carrying *image*'s look with no bars (`painted_look`: a look at
    its own pixels would take the painted rows for ground and find another page box, and its steady part another
    picture of the page, long after - once the window has let go of the frame's facts); else *image* itself."""
    found = frame_look(app, image, facts)
    if not found.bands or found.kind is not None or waits(app, image, facts):
        return image
    read = Image.fromarray(st.masked(facts.rgb(), found.bands, found.ground))
    read.info[LOOK_INFO] = painted_look(app, image, facts)
    read.info[PAINTED_INFO] = found.bands
    return read


def read_under_bars(app: Any, image: Image.Image) -> bool:
    """Whether the page on show in *image* (a frame with no bars painted over: they have gone) was last read from a
    frame with bars painted over (`reading_frame`) and a bubble read reaches the rows painted over (CUT_PX: cut at a
    bar's edge, and its lettering's patch, whose margin takes in those rows, never shown)."""
    if PAINTED_INFO in getattr(image, "info", {}):
        return False
    result = getattr(app, "last_result", None)
    original = getattr(result, "original", None)
    if original is None or PAINTED_INFO not in getattr(original, "info", {}) or original.size != image.size:
        return False
    rows = original.info[PAINTED_INFO]
    boxes = [tuple(getattr(r, "bbox", ())) for r in getattr(result, "regions", None) or ()]
    cut = any(len(b) == 4 and b[1] < end + CUT_PX and b[3] > start - CUT_PX for b in boxes for start, end in rows)
    return cut and bool(app._shows_page(image, original))


def after_bars(app: Any, image: Image.Image) -> bool:
    """The bars have gone from the page last read with them painted over (`read_under_bars` aside, any such page on
    show again in *image*, nothing running): its cached pages carried over to the units of *image*
    (`Pipeline.carry_over`: the painted frame's units have fingerprints of their own - and on a dark ground boxes of
    their own -, so that the page would not be found again), the bubbles that reach the painted rows left out and the
    page marked as lacking them. Whether it is to be read once more now: some were left out (that reading reads and
    asks for those alone, and for a bubble the bars hid whole), or none could be carried over and a bubble was cut
    (then the page is read anew). Done once: the read frame's mark goes."""
    if PAINTED_INFO in getattr(image, "info", {}) or getattr(app, "busy", False):
        return False
    result = getattr(app, "last_result", None)
    original = getattr(result, "original", None)
    if original is None or PAINTED_INFO not in getattr(original, "info", {}) or original.size != image.size:
        return False
    if not app._shows_page(image, original):
        return False
    cut = read_under_bars(app, image)
    rows = original.info.pop(PAINTED_INFO)
    carried = dropped = 0
    pipeline = getattr(app, "pipeline", None)
    if pipeline is not None:
        try:
            carried, dropped = pipeline.carry_over(result, image, rows, CUT_PX)
        except Exception:  # noqa: BLE001 - the cache stays as it was; the page is read anew if a bubble was cut
            carried = dropped = 0
    notes = getattr(app, "_see_carries", None)
    if notes is not None:
        notes.append((time.monotonic(), carried, dropped))
    return dropped > 0 or (carried == 0 and cut)


def steady_area(app: Any, image: Image.Image, facts: Any) -> tuple[int, int, int, int]:
    """What the steady part of *image*'s page area is cut from (`seethrough.steady_box`; frame pixels): the page box's
    columns - the ground beside the page left out, where a viewer draws its arrows - and the capture area's rows, not
    the page box's: under bars at its top or bottom the box reaches the frame's edge (whether the page goes on under a
    bar is not seen), and without them its top and bottom are where the page's own picture leaves the ground's colour,
    which a dark page on a dark ground does well below its edge. The rows the bars cover are left out all the same."""
    found = frame_look(app, image, facts)
    _rgb, area = area_rgb(app, image, facts)
    if found.box is None:
        return area
    return found.box[0], area[1], found.box[2], area[3]


def detail_box(app: Any, image: Image.Image, facts: Any, box: Any) -> Any:
    """The part of *box* (frame pixels; None: the whole frame) that bars over the page's top and bottom never touch -
    the page's steady part (`seethrough.steady_box` of `steady_area`) within it -, by which the window tells a sharper
    or softer picture of the page: so a frame read with its bars painted over is never taken for a softer one. *box*
    itself where no page is found."""
    if frame_look(app, image, facts).box is None:
        return box
    steady = st.steady_box(image.size, steady_area(app, image, facts))
    if box is None:
        return steady
    inner = (max(box[0], steady[0]), max(box[1], steady[1]), min(box[2], steady[2]), min(box[3], steady[3]))
    return inner if inner[0] < inner[2] and inner[1] < inner[3] else box


def painted_look(app: Any, image: Image.Image, facts: Any) -> st.Look:
    """The look of the frame `reading_frame` made of *image* (its bars painted over): *image*'s, with no bars - so
    that the frame read is never one to wait out, and its steady part is *image*'s (`thumb`)."""
    found = frame_look(app, image, facts)
    return st.Look(found.box, (), found.kind, found.ground)


def thumb(app: Any, image: Image.Image, facts: Any) -> np.ndarray:
    """The thumbnail the window compares frames by in see-through mode: the steady part of the page area
    (`seethrough.steady_thumb`), or a flat one (nothing drawn) for a frame to wait out (`waits`)."""
    if waits(app, image, facts):
        return np.zeros((st.THUMB, st.THUMB), np.float32)

    def make() -> np.ndarray:
        return st.steady_thumb(facts.rgb(), steady_area(app, image, facts))

    return facts.get(("see_thumb",), make)


def page_box(app: Any, image: Image.Image, facts: Any) -> tuple[int, int, int, int] | None:
    """The page on its ground in *image* (frame pixels), for the capture area (`LiveViewMixin._find_page`); None on a
    frame to wait out, or where none is found."""
    found = frame_look(app, image, facts)
    if found.kind is not None:
        return None
    return found.box
