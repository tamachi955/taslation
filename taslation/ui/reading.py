"""The full screen (F11; the person knows it as Full screen, the code as reading: `App.reading`, `enter_reading`): the
page alone, full screen above the viewer on the window's own monitor, the page keys passed on to the viewer
(`forward_key`, named as the reader knows them: `key_label`), Set area... offered first where the capture would take
in a browser's tabs and address bar; and the window's size and place, kept while it is neither maximised nor full
screen and put back afterwards.

It keeps the role chosen. In the Reader role every click on the page goes on to the viewer, and Auto is on while the
full screen is, said so in its first line the first time a session it was off before (`READING_MODE_AUTO`). In the
Translator role the pointer and the keys are the Translator's as on the page in the window (`translator`: a click
selects, a drag moves, resizes, turns or draws, a double click opens the editor, the frames and their marks show; a
click goes on to the viewer only while the page on show is not the translated one, as in the window), Auto stays as
the person set it, and a status line stays at the bottom long enough to read (`StatusMixin._note_ms`). Whatever needs the toolbar
(the role, the Book, Series and Volume fields) is done after leaving it; should the role change
meanwhile (a book's start), the full screen follows it (`_reading_role`).

Ways out: F11; Esc, which in the Translator role first lets go of the selected region (`JobsMixin._on_escape`); and a
faint close button at the top right that shows while the pointer is at the top edge of the screen (`TOP_EDGE_PX`) and
goes once it is further down than `TOP_BAND_PX` (`_top_edge_moved`), a click on it TASlation's own. Pages translated
there under a name that names no book are kept nowhere: leaving asks for the book's name once a session for the viewer
(`_ask_name_after_reading`)."""

from __future__ import annotations

import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from ..frames import thumbnail
from ..capture import (
    BROWSER_CLASSES,
    IS_WINDOWS,
    CaptureError,
    Rect,
    ViewerCovered,
    monitor_rect,
    move_window,
    post_key,
    press_briefly,
    window_class,
    window_exists,
)
from ..capture.overlay import set_over
from ..i18n import _
from ..pagekeys import key_ways, passed_on, viewer_key
from .constants import (
    CLOSE_READING,
    FULL_SCREEN_TRANSLATOR,
    KEPT_FROM_NOW,
    KEY_ARROWS,
    READING_MODE,
    READING_MODE_AUTO,
    READING_ONLY,
    WINDOW_ALPHA,
)
from .layout import place_window
from .order import turn_asked
from .viewers import looks_like_browser
from .bubble_text import BubbleTextMixin
from .hover import HoverChoiceMixin
from .in_place import InPlaceMixin
from .wrap import wrap_text
from .zoom import BubbleZoomMixin

# A key for a viewer of real keys waits until none has come for KEY_QUIET_MS, KEY_GATHERS times at most: the keys
# pressed while the window was busy go in one handover of the foreground (`_hand_over`).
KEY_QUIET_MS = 20
KEY_GATHERS = 5
# The full screen's close button: shown while the pointer is this near the top of the screen, gone once it is
# further down than TOP_BAND_PX; faint over the black screen, lit under the pointer (background, text).
TOP_EDGE_PX = 2
TOP_BAND_PX = 120
CLOSE_FAINT = ("#161616", "#7a7a7a")
CLOSE_LIT = ("#3a3a3a", "#f2f2f2")


def key_label(key: str) -> str:
    """A key passed on to the viewer as the reader knows it: the arrow keys as arrows, the others by the name on the
    key in the window's language."""
    if key in KEY_ARROWS:
        return KEY_ARROWS[key]
    names = {"PageUp": _("Page Up"), "PageDown": _("Page Down"), "Home": _("Home"), "End": _("End"),
             "Space": _("Space")}
    return names.get(key, key)


def bubbles_away(window: object) -> None:
    """The page moves (the full screen in or out, the widgets made anew): no panel beside a bubble where it was
    (`zoom`), nor a bubble showing its other side in its place (`in_place`), where the window has them."""
    for name in ("_zoom_hide", "_reveal_hide"):
        hide = getattr(window, name, None)
        if hide is not None:
            hide()


class ReadingMixin(BubbleZoomMixin, InPlaceMixin, HoverChoiceMixin, BubbleTextMixin):
    """The full screen and the window's size and place, the panel beside a bubble while reading (`zoom.BubbleZoomMixin`)
    or the bubble itself showing its other side (`in_place.InPlaceMixin`), what the page and the bubble under the
    pointer show and how (`hover.HoverChoiceMixin`) and a bubble's Japanese and translation at hand
    (`bubble_text.BubbleTextMixin`). A part of `app.App` (no `__init__`: the state it uses is made by `App.__init__`;
    the other parts are reached through ``self``)."""

    # ------------------------------------------------------------------ the window's size and place
    def _track_geometry(self, event: tk.Event) -> None:
        """Keep the window's size and place while it is neither maximised nor full screen: what a maximised window
        returns to, and what the full screen and a language switch put back."""
        if event.widget is not self or self.reading or self._restoring:
            return
        try:
            if self.state() == "normal":
                self._normal_geometry = self.geometry()
        except tk.TclError:
            pass

    def _current_geometry(self) -> tuple[str, bool]:
        """The size and place to put back later, and whether the window is maximised (its size and place before it
        was maximised, then: maximising it again there puts it on the same monitor)."""
        zoomed = self.state() == "zoomed"
        return (self._normal_geometry if zoomed and self._normal_geometry else self.geometry()), zoomed

    def _restore_geometry(self, saved: tuple[str, bool], rezoom: bool = True) -> None:
        """Put the size and place *saved* back (it includes the position), once Tk has done its own resizing (a menu
        bar put back takes its room from the inside); a window that was maximised is maximised again after that, on
        the monitor of its place. With *rezoom* False a window still maximised is left as it is."""
        geometry, zoomed = saved
        self._restoring = True

        def done() -> None:
            self._restoring = False

        def zoom() -> None:
            try:
                self.state("zoomed")
            except tk.TclError:
                pass
            done()

        def apply() -> None:
            try:
                if self.reading:
                    done()
                    return
                if zoomed and self.state() == "zoomed" and not rezoom:
                    done()
                    return
                if self.state() == "zoomed":
                    self.state("normal")
                if geometry:
                    self.geometry(geometry)
                if zoomed:
                    self.after_idle(zoom)
                    return
            except tk.TclError:
                pass
            done()

        self.after_idle(apply)

    # ------------------------------------------------------------------ the full screen
    def toggle_reading(self) -> None:
        """F11: the full screen on or off."""
        if self.reading:
            self.leave_reading()
        else:
            self.enter_reading()

    def enter_reading(self, offered: bool = False) -> None:
        """The page alone on a black full screen above the viewer, on the monitor the window is on, in the role
        chosen (`_reading_role`): the page keys turn the viewer's pages, and status lines show at the bottom for a few
        seconds (`_note_ms`); in the Reader role Auto follows the pages turned and clicks go through to the viewer, in
        the Translator role the pointer selects and edits the regions as in the window. F11 leaves it, and Esc too
        once no region is selected. Where the capture would take in a browser's tabs
        and address bar, Set area... is offered first (`_offer_area`; *offered*: it was); the viewer's window is
        enlarged before either (`_enlarge_first`). Show original rests while it is on: the full screen has no menu to
        turn it off with. A faint close button shows at the top edge (`_top_edge_moved`)."""
        if self.reading:
            return
        if self.selected is None:
            self.say("Pick the viewer window first (open your e-book viewer, then choose it in the Viewer list).")
            return
        if not self._enlarge_first(lambda: self.enter_reading(offered)):
            return
        if not offered and self._area_offer_due():
            self._offer_area()
            return
        if self._ordering is not None:
            self._on_escape()
        self._chosen_region = None
        self._set_covered(False)  # the normal window's band about the viewer covered has no place on the page alone
        try:
            alpha = float(self.attributes("-alpha"))
        except (tk.TclError, ValueError):
            alpha = 1.0
        self._reading_saved = (self._current_geometry(), bool(self.auto_var.get()), alpha)
        self._unkept_reading = 0  # pages translated here under a name that names no book (`_ask_name_after_reading`)
        self._original_saved = bool(self.original_var.get())
        self.original_var.set(False)
        bubbles_away(self)
        monitor = self._window_monitor()  # taken before: Tk puts a full-screen window on the primary monitor
        self.reading = True
        self._viewer_hidden = False
        for widget in (*self._bars, self.notes_label, self.status_bar):
            widget.pack_forget()
        self.config(menu="")
        self.canvas.configure(bg="#000000", cursor="")
        try:
            if monitor is not None:
                self.attributes("-alpha", 0.0)  # unseen until it is on its own monitor
            self.attributes("-fullscreen", True)
            if monitor is not None:
                self._onto_monitor(monitor)
            self.attributes("-alpha", WINDOW_ALPHA)
        except tk.TclError:
            pass
        self._apply_on_top()
        self.canvas.focus_set()
        self._redisplay()
        self._reading_role()
        self._watch_top_edge()
        if hasattr(self, "_over_soon"):  # Tk made its window anew for the full screen: over the book again at once
            self._over_soon()
        if hasattr(self, "_learn_covered_soon"):  # the page alone hides the viewer: does it draw so?
            self._learn_covered_soon()

    def _reading_role(self) -> None:
        """The full screen in the role chosen now, as it starts (`enter_reading`) and when the role changes on it (a
        book's start: `TranslatorMixin._on_role_changed`). The Reader role has Auto on, so that the pages turned in the
        viewer are followed: the first time a session that turns it on, the first line says so (`READING_MODE_AUTO`).
        The Translator role keeps Auto as the person set it (`_reading_saved`), and its first line says what the
        pointer does (`FULL_SCREEN_TRANSLATOR`)."""
        auto = self._reading_saved[1]
        if self.role_var.get() == "translator":
            self.auto_var.set(auto)
            self.say(FULL_SCREEN_TRANSLATOR)
            return
        quiet = auto or getattr(self, "_reading_auto_told", False)  # Auto on already, or said once
        self._reading_auto_told = True
        self.auto_var.set(True)
        self.say(READING_MODE if quiet else READING_MODE_AUTO)

    def _window_monitor(self) -> Rect | None:
        """The whole rectangle of the monitor the window is on (Windows; None elsewhere)."""
        hwnd = self._own_hwnd()
        return monitor_rect(hwnd) if hwnd else None

    def _onto_monitor(self, monitor: Rect) -> None:
        """The full-screen window, which Tk has just made anew on the primary monitor, moved onto *monitor* (Tk
        follows it there, and puts the window back in its place when it leaves full screen)."""
        hwnd = self._own_hwnd()
        if hwnd:
            move_window(hwnd, monitor)

    def _area_offer_due(self) -> bool:
        """Whether F11 offers Set area... first: the viewer is a browser window, the reader has set no area for it,
        no page panel is found in its frame (looked at now), and it was not offered for this viewer in this session."""
        win = self.selected
        if win is None or self._manual_area or not looks_like_browser(win):
            return False
        key = viewer_key(win)
        if key in getattr(self, "_area_offered", ()):
            return False
        try:
            self._capture(win.hwnd)  # the page panel is looked for in every frame
        except CaptureError:
            return False
        known = self._page_areas.get(key)
        return known is not None and known[1] is None

    def _offer_area(self) -> None:
        """Before the full screen, where the capture takes in a browser's tabs and address bar: Set area... (the
        area dialog, then the full screen once the area is set) or Read as it is; Esc or closing the box leaves
        everything as it was. Asked once a session for each viewer."""
        offered = getattr(self, "_area_offered", None)
        if offered is None:
            offered = self._area_offered = set()
        offered.add(viewer_key(self.selected))
        box = tk.Toplevel(self)
        box.withdraw()
        box.title("TASlation")
        box.transient(self)
        box.resizable(False, False)
        frame = ttk.Frame(box, padding=12)
        frame.pack(fill="both", expand=True)
        text = _("The browser's tabs and address bar are part of the page here. Set area... and draw a rectangle around the page once; TASlation remembers it.")
        measure = tkfont.nametofont("TkDefaultFont").measure
        lines = "\n".join(line.rstrip(" ") for part in wrap_text(text, 440, measure) for line in part)
        ttk.Label(frame, text=lines, justify="left").pack(anchor="w")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(14, 0))

        def choose(set_first: bool) -> None:
            box.destroy()
            if set_first:
                self.set_area(then=lambda: self.enter_reading(offered=True))
            else:
                self.enter_reading(offered=True)

        ttk.Button(buttons, text=_("Read as it is"), command=lambda: choose(False)).pack(side="right")
        first = ttk.Button(buttons, text=_("Set area..."), command=lambda: choose(True))
        first.pack(side="right", padx=(0, 6))
        for keysym in ("Return", "KP_Enter"):
            box.bind(f"<{keysym}>", lambda _e: choose(True))
        box.bind("<Escape>", lambda _e: box.destroy())
        self._area_offer = box
        place_window(box, self)
        if self.winfo_viewable():  # (a window not on the screen, as in the tests, keeps it out of sight)
            box.deiconify()
        first.focus_set()
        try:
            box.grab_set()
        except tk.TclError:
            pass

    def leave_reading(self, restore: bool = True) -> None:
        """Back to the window as it was: its size and place (put back once the menu bar is; maximised again on its
        own monitor when it was), Always on top, Auto and Show original as the reader had them, and the status line of
        the normal window, in either role (the Reader role's Auto was its own while the full screen lasted). A
        language switch puts the size and place back itself (*restore* False). Pages translated on the full screen
        under a name that names no book were kept nowhere: the name is asked for then (`_ask_name_after_reading`; not
        at a language switch)."""
        if not self.reading:
            return
        saved, auto, alpha = self._reading_saved
        self.reading = False
        self._viewer_hidden = False
        bubbles_away(self)
        self._hide_close()
        try:
            self.attributes("-fullscreen", False)
            self.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        self.config(menu=self.menubar)
        for widget in self._bars:
            widget.pack(fill="x", before=self.canvas)
        self.status_bar.pack(fill="x", after=self.canvas)
        self._show_notes()
        self.canvas.configure(bg="#202020")
        self.canvas.set_note("")
        if restore:
            self._restore_geometry(saved)
        self._apply_on_top()
        self.auto_var.set(auto)
        self.original_var.set(self._original_saved)
        self.canvas.focus_set()
        self._redisplay()
        if self._status_key in READING_ONLY:  # a line about the full screen: the normal window's own instead
            self._normal_status()
        if hasattr(self, "_over_soon"):
            self._over_soon()
        if restore:
            self._ask_name_after_reading()

    # ------------------------------------------------------------------ the close button at the top edge
    def _watch_top_edge(self) -> None:
        """The page watches the pointer for the close button (bound once for each canvas: a language switch makes the
        window's widgets anew; `add` keeps the Translator role's own pointer handling)."""
        canvas = self.canvas
        if getattr(canvas, "_top_edge_watched", False):
            return
        canvas._top_edge_watched = True
        canvas.bind("<Motion>", self._top_edge_moved, add="+")
        canvas.bind("<Leave>", self._top_edge_left, add="+")

    def _top_edge_moved(self, event: tk.Event) -> None:
        """On the full screen: the pointer at the top edge (`TOP_EDGE_PX`) shows the close button, further down than
        `TOP_BAND_PX` it goes."""
        if not self.reading:
            return
        if event.y <= TOP_EDGE_PX:
            self._show_close()
        elif event.y > TOP_BAND_PX:
            self._hide_close()

    def _top_edge_left(self, event: tk.Event) -> None:
        """The pointer left the page: onto the close button it stays, anywhere else it goes."""
        button = getattr(self, "_close_button", None)
        if button is None:
            return
        try:
            under = self.winfo_containing(event.x_root, event.y_root)
        except (tk.TclError, KeyError):  # (a window Tk does not know)
            under = None
        if under is not button:
            self._hide_close()

    def _show_close(self) -> None:
        """The close button at the top right of the full screen, faint (`CLOSE_FAINT`), lit under the pointer: a
        click on it leaves the full screen (and goes nowhere else). A label, not a ttk button: its colours are its own
        over the black screen."""
        button = getattr(self, "_close_button", None)
        if button is not None and not button.winfo_exists():
            button = None
        if button is None:
            bg, fg = CLOSE_FAINT
            button = tk.Label(self, text="\u2715  " + _(CLOSE_READING), bg=bg, fg=fg, padx=12, pady=5, cursor="hand2",
                              font="TkDefaultFont")
            button.bind("<Enter>", lambda _e: button.configure(bg=CLOSE_LIT[0], fg=CLOSE_LIT[1]))
            button.bind("<Leave>", lambda _e: button.configure(bg=CLOSE_FAINT[0], fg=CLOSE_FAINT[1]))
            button.bind("<ButtonRelease-1>", self._close_clicked)
            self._close_button = button
        if not button.place_info():
            button.configure(bg=CLOSE_FAINT[0], fg=CLOSE_FAINT[1])
            button.place(relx=1.0, x=-16, y=10, anchor="ne")
            button.lift()

    def _close_clicked(self, _event: tk.Event | None = None) -> None:
        """A click on the close button: the full screen ends (the click is TASlation's own, nothing goes to the viewer)."""
        self.leave_reading()

    def _hide_close(self) -> None:
        """The close button away."""
        button = getattr(self, "_close_button", None)
        if button is not None and button.winfo_exists():
            button.place_forget()

    # ------------------------------------------------------------------ a book with no name read on the full screen
    def _ask_name_after_reading(self) -> None:
        """Off the full screen after pages were translated there under a name that names no book (`_unkept_reading`,
        counted by `_on_new_page`; nothing of them was kept): the book's name is asked for (`_ask_name`, offering the
        books the page on show is recognised as), once a session for the viewer, with the cache on and the Book box
        still naming no book. The name given keeps the pages from then on (`KEPT_FROM_NOW`)."""
        count, self._unkept_reading = getattr(self, "_unkept_reading", 0), 0
        win = self.selected
        if not count or win is None or not self.settings.cache_enabled or not self._name_needed():
            return
        asked = getattr(self, "_named_after_reading", None)
        if asked is None:
            asked = self._named_after_reading = set()
        key = viewer_key(win)
        if key in asked:
            return
        asked.add(key)

        def ask() -> None:
            if not self.reading and self._name_needed():  # (back on the full screen meanwhile, or named: not now)
                self._ask_name(lambda name: self.say(KEPT_FROM_NOW, book=name), getattr(self, "_live", None))

        self.after_idle(ask)

    # ------------------------------------------------------------------ single-screen use
    def _apply_alpha(self) -> None:
        """On Windows the window is not quite opaque: a Chromium viewer that an opaque window covers entirely stops
        drawing (it would give a blank frame), one under a window it can see through a little goes on drawing."""
        if IS_WINDOWS:
            try:
                self.attributes("-alpha", WINDOW_ALPHA)
            except tk.TclError:
                pass

    def _apply_on_top(self) -> None:
        """Always on top (or the full screen) as the reader has it; over the book the window stays topmost whatever
        it is (`overbook`), set again with SWP_NOACTIVATE after Tk's own call."""
        try:
            self.attributes("-topmost", bool(self.top_var.get()) or self.reading)
        except tk.TclError:
            pass
        if getattr(self, "_over_on", False):
            set_over(self._own_hwnd() or 0, True)

    def _own_hwnd(self) -> int | None:
        if not IS_WINDOWS:
            return None
        import ctypes

        return int(ctypes.windll.user32.GetAncestor(self.winfo_id(), 2))  # GA_ROOT

    def forward_key(self, key: str) -> None:
        """Send a key to the viewer behind this window (page turn), then follow the page change. The key is posted at
        once, except to a viewer seen to take only keys pressed for real (`pagekeys.KeyWays`; a browser always): there
        it waits a moment (`_keys_waiting`, `_hand_over`: KEY_QUIET_MS), so that every key the reader pressed
        meanwhile - while the window was busy - goes with it in the same short handover of the foreground
        (`capture.press_briefly`), in order, none dropped and none twice, with no wait for a posted key first; when
        the foreground did not come the keys are posted after all, but never to a browser: measured, a key posted to
        a browser that is not in front reaches nothing (0 of 9, Chrome and Edge 156), and the reader is told to turn
        the page in the viewer. Over a full-screen viewer (`overbook`) the keys go to the viewer itself and none comes
        here. In the Translator role the status line names the key as the reader knows it (`key_label`), in the window
        and on the full screen; the Reader role sees the page turn and says nothing of it. The key goes on as the
        viewer's own key of the same meaning (`_key_for_viewer`): the window's next and previous keys as the keys saved
        for the viewer in Page keys..., one press one key."""
        hwnd = self._key_viewer()
        if hwnd is None:
            return
        key = self._key_for_viewer(key)
        if key_ways(self).real(hwnd):
            self._keys_waiting = [*getattr(self, "_keys_waiting", []), (hwnd, key)]
            if getattr(self, "_handover_job", None) is None:
                self._keys_gathered = (len(self._keys_waiting), 0)
                self._handover_job = self.after(KEY_QUIET_MS, self._hand_over)
            return
        self._pass_on(hwnd, [key], real=False)

    def _key_for_viewer(self, key: str) -> str:
        """The key the viewer gets for *key* pressed in this window (`pagekeys.passed_on`): a key of the viewer's own
        as it is, the window's next or previous key as the viewer's next or previous key, any other as it is."""
        pair = self._page_key_pair()
        return passed_on(key, *pair) if pair is not None else key

    def _key_viewer(self) -> int | None:
        """The viewer's window a key goes to now; None (and the reader told why, where there is something to say)
        when none goes: no viewer, a book not in front."""
        if self.selected is None:
            return None
        if not self._book_in_front():
            if window_exists(self.selected.hwnd):
                self._say_waiting()
            else:
                self._viewer_gone()
            return None
        return self.selected.hwnd

    def _hand_over(self) -> None:
        """The keys waiting for a viewer of real keys (`forward_key`), all of them in one handover of the foreground,
        in the order they came; a key for a window that is no longer the viewer's is dropped. It goes once no key has
        come for KEY_QUIET_MS - keys pressed while the window was busy come out of its message queue one after the
        other, a few milliseconds apart (measured), and go together - and after KEY_GATHERS such waits at the latest (a
        key still in the queue when the foreground moves stays there, and goes with the next handover: measured)."""
        count, waits = getattr(self, "_keys_gathered", (0, 0))
        waiting_now = len(getattr(self, "_keys_waiting", []))
        if waiting_now != count and waits < KEY_GATHERS:  # a key came meanwhile: wait for the next as long again
            self._keys_gathered = (waiting_now, waits + 1)
            self._handover_job = self.after(KEY_QUIET_MS, self._hand_over)
            return
        self._handover_job = None
        waiting, self._keys_waiting = getattr(self, "_keys_waiting", []), []
        hwnd = self._key_viewer()
        keys = [key for h, key in waiting if h == hwnd]
        if hwnd is not None and keys:
            self._pass_on(hwnd, keys, real=True)

    def _pass_on(self, hwnd: int, keys: list[str], real: bool) -> None:
        """*keys* passed on to the viewer's window *hwnd*: pressed for real in one handover (*real*), else posted one
        after the other; then the page change followed from the frame before them (`_follow_change`), at each new
        frame of the viewer from the count before that frame (`capture.frame_count`)."""
        key = keys[-1]
        reference = None
        seq = self._frame_count()
        last = self._last_frame(hwnd, seq)  # nothing drawn since the last capture: that frame is the one before
        try:
            reference = thumbnail(last if last is not None else self._capture(hwnd))
        except ViewerCovered:
            self._set_covered(True)  # the key goes all the same: the page turns, and shows once the viewer draws
        except CaptureError as e:
            if not self.reading:  # the full screen says so on the page
                self.say("Viewer: {error}", error=e)
            return
        self._raise_for_key(hwnd)
        try:
            pressed = real and press_briefly(hwnd, key if len(keys) == 1 else keys)
            if not pressed:
                if window_class(hwnd) in BROWSER_CLASSES:  # a posted key would reach nothing
                    self.say("The browser did not take the key: click the book and turn the page there.")
                    return
                for each in keys:
                    post_key(hwnd, each)  # no focus change; a desktop viewer takes it
        except CaptureError as e:
            if not self.reading:
                self.say("Viewer: {error}", error=e)
            return
        turn_asked(self, hwnd, seq)  # (a turn asked for: a viewer hidden wholly that draws no frame of it is said so)
        if self.role_var.get() == "translator":  # a reader sees the page turn
            self.status(lambda: _("Sent {key} to the viewer...").format(key=key_label(key)))
        if reference is not None:
            self._follow_change(hwnd, reference, key, time.monotonic(), retried=pressed, seq=seq)
