"""The viewer's window: the list of windows (rescanned as it opens, watched until a viewer is chosen), the one
chosen and whether it still shows the book, the capture area set by hand (the outer
bound of what is read, the page panel found inside it read of it: `live.LiveViewMixin._find_page`), the viewer's
window shown again when it is chosen minimised (`show_minimised`) and otherwise read as it is (never moved nor
resized: `_enlarge_first`), and the offline guard's warning once it has blocked something."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .. import netguard, viewerparts
from ..cache import book_key_from_title
from ..capture import (
    IS_WINDOWS,
    CaptureError,
    WindowInfo,
    is_browser_class,
    list_windows,
    match_windows,
    same_book_window,
    still_the_book,
    stop_capture,
    unminimise_window,
    viewer_candidates,
    window_exists,
    window_shown,
    window_title,
)
from ..detect.page_area import panel_inside
from ..i18n import _
from ..recovery import put_back_enlarged
from . import area
from .constants import VIEWER_CLOSED, VIEWER_RESTORED, WINDOW_WATCH_MS
from .dialogs import caches as boxes
from .dialogs.area import AreaDialog


def show_minimised(app: Any, win: WindowInfo) -> bool:
    """The chosen viewer's window, when it is minimised, shown again as it was before (its last size, or maximised)
    and put directly behind the window of *app* (`capture.unminimise_window`: not activated, no key pressed, the
    foreground stays TASlation's). Only as a viewer is chosen: a window minimised later is waited for
    (`live.LiveViewMixin._say_waiting`), not restored again. Returns whether it was restored."""
    if not IS_WINDOWS:
        return False
    own = getattr(app, "_own_hwnd", None)
    try:
        return unminimise_window(win.hwnd, own() if own is not None else None)
    except Exception:  # a window that went meanwhile: nothing restored
        return False


def choose_viewer(windows: Sequence[WindowInfo], query: str = "") -> tuple[WindowInfo | None, list[WindowInfo]]:
    """The window to choose as the viewer, and when there is none to choose, the ones the reader has to pick from.
    The window *query* names (`match_windows`: the window's --window); when it names several, the one of them that
    looks most surely like a viewer; when it names none, or without a query, the one window that looks most surely
    like a viewer (`viewer_candidates`: a window the viewer by what was learned on this computer - chosen before, or
    a viewer's part at an end of its tab title - before any other title with a viewer's part or a reading word in it;
    Auto follows it from the start). Several of equal rank: (None, them) - TASlation never guesses between them (a
    chat page about the viewer beside the reader's tab). (None, []) when nothing fits: on the first use of a viewer
    on a computer, unless its title has a reading word, the reader picks it in the Viewer list."""
    if query.strip():
        named = match_windows(query, windows)
        if len(named) == 1:
            return named[0], []
        if named:
            best = viewer_candidates(named)
            return (best[0], []) if len(best) == 1 else (None, best or named)
    best = viewer_candidates(windows)
    return (best[0], []) if len(best) == 1 else (None, best)


def another_book(left: WindowInfo, chosen: WindowInfo, query: str = "") -> bool:
    """Whether the window *chosen* in place of *left* is another book's: another window, or a title that names another
    book; not a window that shows the book of *left*, closed, again (`same_book_window`)."""
    if left.hwnd == chosen.hwnd:
        return book_key_from_title(left.title) != book_key_from_title(chosen.title)
    return window_exists(left.hwnd) or not same_book_window(chosen.title, left.title, query)



class ViewerMixin:
    """The viewer list, the chosen viewer, its area and the offline guard. A part of `app.App` (no `__init__`: the
    state it uses is made by `App.__init__`; the other parts are reached through ``self``)."""

    # ------------------------------------------------------------------ the offline guard
    def _guard_blocked(self) -> int:
        """How many connection attempts the offline guard blocked in this session (0 when it is off; its state for a
        report is in Copy details: `errorlog.guard_line`)."""
        st = netguard.state()
        if st is None or not st.installed:
            return 0
        return len(st.blocked)

    def _sync_guard(self) -> None:
        """Once the offline guard has blocked a connection attempt, the status bar says so until the window closes."""
        blocked = self._guard_blocked()
        text = ""
        if blocked:
            text = _("TASlation blocked {blocked} attempt(s) to reach the internet. Nothing left this computer; you need do nothing.").format(
                blocked=blocked)
        if self.guard_var.get() != text:
            self.guard_var.set(text)
            if hasattr(self, "status_label"):  # the warning takes room from the status line
                self.after_idle(self._wrap_status)

    # ------------------------------------------------------------------ windows
    def refresh_windows(self, select: str | None = None) -> None:
        if not IS_WINDOWS:
            self.say("Window capture needs Windows; use `taslation translate IMAGE` on this OS.")
            return
        self.windows = list_windows()
        self.window_box["values"] = [w.label() for w in self.windows]
        target: WindowInfo | None = None
        tied: list[WindowInfo] = []
        if not select and self.selected:
            target = next((w for w in self.windows if w.hwnd == self.selected.hwnd), None)
        named = False
        if target is None:
            target, tied = choose_viewer(self.windows, select or "")
            named = target is not None and bool(select) and any(
                w.hwnd == target.hwnd for w in match_windows(select or "", self.windows))
        if target is not None:
            self._tied_said = ()
            self.window_box.current(self.windows.index(target))
            self._on_window_selected(named=named)
        elif tied and self._tied_said != tuple(w.hwnd for w in tied):  # said once for these windows
            self._tied_said = tuple(w.hwnd for w in tied)
            self.say("Several windows look like a viewer: choose the right one in Menu > Viewer...")

    def _rescan_windows(self) -> None:
        """The viewer list as it opens: the windows as they are now, the chosen one kept. When the chosen window was
        closed, a window showing its book again (reopened) is chosen in its place."""
        if not IS_WINDOWS:
            return
        try:
            new = list_windows()
        except Exception:  # the list stays as it was
            return
        if [(w.hwnd, w.label()) for w in new] == [(w.hwnd, w.label()) for w in self.windows]:
            return
        self.windows = new
        self.window_box["values"] = [w.label() for w in new]
        if self.selected is not None:
            index = next((i for i, w in enumerate(new) if w.hwnd == self.selected.hwnd), None)
            if index is None and not window_exists(self.selected.hwnd):
                index = next((i for i, w in enumerate(new)
                              if same_book_window(w.title, self.selected.title, self.window_query)), None)
                if index is not None:
                    self.window_box.current(index)
                    self._on_window_selected()
                return
            if index is not None:
                self.window_box.current(index)

    def _watch_windows(self) -> None:
        """Until a viewer is chosen: every 2 s, look for one and choose it as the start does (`choose_viewer`), so a
        viewer opened after TASlation is chosen by itself; windows that only the reader can tell apart are said once
        (the status line), and the reader picks. The list is left alone while it is open or a dialog holds the
        window."""
        if not IS_WINDOWS or self.selected is not None:
            return
        try:
            if not self.tk.call("grab", "current"):
                target, tied = choose_viewer(list_windows(), self.window_query)
                if target is not None or (tied and tuple(w.hwnd for w in tied) != self._tied_said):
                    self.refresh_windows(select=self.window_query)
        except Exception:  # a failed scan must not end the watch
            pass
        if self.selected is None:
            self.after(WINDOW_WATCH_MS, self._watch_windows)

    def _on_window_selected(self, picked: bool = False, named: bool = False) -> None:
        """A viewer chosen in the Viewer list (*picked*: by the person; *named*: by the --window the person gave; else
        by TASlation, as it finds the viewer): remembered for the next start (`_learn_viewer`), its book (the name its
        title gives: `_title_book`) and area, its line on the status line, its window shown again when it is
        minimised (`show_minimised`) and looked at once as it is (`_enlarge_first`), and the window followed; once it
        has settled whether it draws while covered is found out (`_learn_covered_soon`). A window chosen again keeps
        what it has."""
        idx = self.window_box.current()
        if idx < 0 or idx >= len(self.windows):
            return
        before, chosen = getattr(self, "selected", None), self.windows[idx]
        same = before is not None and before.hwnd == chosen.hwnd
        if same and getattr(self, "busy", False):
            self.selected = chosen  # (the list again, a language switch: the area of the job under way stays as it is)
            return
        left = before if before is not None else getattr(self, "_viewer_closed", None)
        self._viewer_closed = None
        if left is not None and not getattr(self, "_book_given", False) and another_book(
                left, chosen, getattr(self, "window_query", "")):
            self._book_edited = False  # the name given to the book before does not go on to this one
        if before is not None and not same:
            self._viewer_left()
        self.selected = chosen
        if picked or not same:
            self._learn_viewer(chosen, picked or named)
        self._seen_title = chosen.title
        restored = show_minimised(self, chosen) if picked or not same else False
        if not self._book_edited:
            self.book_var.set(self._title_book(self.selected))
        else:
            self._title_name = None  # the Book box holds the reader's name: what they type says nothing of this title
        # (an image viewer's by its window class: `profile_names`; the same window chosen again keeps the area in use)
        margins = self.profiles.margins_for(self.selected)
        self._manual_area = margins is not None  # the reader's area bounds what is read; else the page is looked for
        self._hand_area = margins  # (the page panel found inside it takes over with the next frame: `_find_page`)
        self.settings.margins = margins if margins is not None else self._found_margins()
        self._auto_last = None
        self._live_thumb = None  # the next tick shows this viewer
        title = self.selected.title
        if restored:
            self.status(lambda: _(VIEWER_RESTORED).format(title=title))
        elif margins is not None and any(margins):
            self.status(lambda: _("Viewer: {title}  (area set)").format(title=title))
        else:
            self.say("Viewer: {title}", title=title)
        self._redisplay()  # the hint for no viewer goes; this viewer's picture comes with the next look at it
        self._warm_page_models()  # (once the pipeline is there too)
        self._enlarge_first()  # looked at once, as it is
        self._learn_covered_soon()
        self._follow_viewer()  # follow = "events": this viewer's window watched, and looked at at once

    def _show_chosen(self) -> None:
        """The viewer list shows the viewer chosen (none: nothing), whatever was picked in it."""
        win = self.selected
        index = next((i for i, w in enumerate(self.windows) if win is not None and w.hwnd == win.hwnd), -1)
        if index >= 0:
            self.window_box.current(index)
        else:
            self.window_box.set(win.label() if win is not None else "")

    def _viewer_gone(self) -> None:
        """The chosen viewer's window was closed: it is left as when another is chosen (`_viewer_left`), none is chosen
        any more, the status line says what to do, and the watch for a viewer starts again (`_watch_windows`). Nothing
        while the window is still there."""
        win = self.selected
        if win is None or window_exists(win.hwnd):
            return
        self._viewer_left()
        self._viewer_closed = win  # what the next viewer's book is told from (`another_book`)
        self.selected = None
        self._auto_last = self._auto_candidate = None
        self._waiting = False
        self._show_chosen()
        self._follow_viewer()
        self.say(VIEWER_CLOSED)
        self._redisplay()
        self.after(WINDOW_WATCH_MS, self._watch_windows)

    def _book_in_front(self) -> bool:
        """The chosen window still shows the book (`capture.still_the_book`): a browser window while its title - its
        active tab's - is the book's; any other window (an image viewer, whose title is the file it shows) while it
        is there, visible and not minimised, whatever its title."""
        if self.selected is None or not window_exists(self.selected.hwnd):
            return False
        hwnd = self.selected.hwnd
        title = window_title(hwnd)
        if not is_browser_class(self.selected.class_name):
            self._viewer_retitled(title)
        return still_the_book(self.selected, title, self.window_query, shown=window_shown(hwnd))

    # ------------------------------------------------------------------ what is learned of the viewer
    def _learn_viewer(self, win: WindowInfo, by_reader: bool) -> None:
        """*win* is the viewer now: remembered for the next start, and its title set beside the titles of the windows
        chosen before (`viewerparts.chosen`: what they end alike with is the viewer's). The reader choosing another
        window (*by_reader*) while the one chosen last has given no page yet says that one was not the viewer: it is
        not remembered, nor what its choice taught (`viewerparts.corrected`)."""
        unread = getattr(self, "_viewer_unread", None)
        learned: list[str] = []
        try:
            if by_reader and unread is not None and unread[0].hwnd != win.hwnd:
                viewerparts.corrected(*unread)
            learned = viewerparts.chosen(win)
        except Exception:  # noqa: BLE001 - nothing learned: the viewer is read all the same
            pass
        if unread is not None and unread[0].hwnd == win.hwnd:  # the same window chosen again: what it taught stands
            learned = [*unread[1], *learned]
        self._viewer_unread = (win, learned)

    def _title_book(self, win: WindowInfo) -> str:
        """The book's name the window *win*'s title gives (`viewerparts.book_for_title`: the viewer's parts left out,
        and a book kept under a fuller name or under the name an earlier version gave it found again). A name that may
        be the viewer's own is held back until the reader says what the book is called (`viewerparts.unconfirmed`:
        the start asks once). What the reader types in the Book box afterwards is learned from (`_book_named`)."""
        try:
            name = viewerparts.book_for_title(win.title, getattr(self, "store", None))
            if viewerparts.unconfirmed(win.title, name):
                viewerparts.hold(name)
        except Exception:  # noqa: BLE001 - the title as it is
            name = book_key_from_title(win.title)
        self._title_name = name
        return name

    def _book_named(self, name: str) -> None:
        """The reader gave the book the name *name* (typed in the Book box, given at its start, the colophon's taken)
        while the Book box held the name the viewer's title gave: what that says of the title is learned
        (`viewerparts.named`: segments left out are the viewer's, one put back is the book's, a one-segment title
        replaced wholly names no book). Once: the Book box holds the reader's name from then on."""
        win, title_name = getattr(self, "selected", None), getattr(self, "_title_name", None)
        name = " ".join(str(name or "").split())
        if win is None or title_name is None or not name or getattr(self, "_book_given", False):
            return
        self._title_name = None
        try:
            viewerparts.named(win.title, name)
        except Exception:  # noqa: BLE001 - nothing learned
            pass

    def _book_typed(self) -> None:
        """The Book box left (or Enter in it) after the reader typed in it: a name other than the title's is learned
        from (`_book_named`)."""
        name = " ".join(self.book_var.get().split())
        title_name = getattr(self, "_title_name", None)
        if title_name is not None and name and name != title_name and getattr(self, "_book_edited", False):
            self._book_named(name)

    def _viewer_retitled(self, title: str) -> None:
        """The title of a viewer that is no browser's, as it is now (its window is the viewer whatever its title):
        a change of it is learned from (`viewerparts.retitled`: what the titles end alike with, another book before
        it, is the viewer's)."""
        seen = getattr(self, "_seen_title", None)
        if not title or title == seen:
            return
        self._seen_title = title
        if seen:
            try:
                viewerparts.retitled(seen, title)
            except Exception:  # noqa: BLE001 - nothing learned
                pass

    def _current_window(self) -> WindowInfo | None:
        if self.selected is None or not window_exists(self.selected.hwnd):
            self._viewer_gone()
            self.refresh_windows()
        if self.selected is None:
            boxes.tell(self, _("Pick the viewer window first (open your e-book viewer, then choose it in Menu > Viewer...)."), icon="info")
        return self.selected

    # ------------------------------------------------------------------ the area set by hand
    def set_area(self, then: Callable[[], None] | None = None) -> None:
        """Set area...: the area dialog over a fresh capture - the reader's own area, else the page found so far -
        with the page panel found inside the rectangle shown dashed (`page_area.panel_inside`: what is read of it);
        once an area is chosen or cleared (its Clear area: `clear_area`), *then()*."""
        win = self._current_window()
        if win is None:
            return
        self._enlarge_first()
        try:
            image = self._capture(win.hwnd)
        except CaptureError as e:
            self._capture_failed(e)
            return

        def chosen(box: tuple[int, int, int, int], size: tuple[int, int]) -> None:
            self._area_chosen(box, size)
            if then is not None:
                self.after(150, then)  # once the dialog has gone

        def cleared() -> None:
            self.clear_area()
            if then is not None:
                self.after(150, then)

        hand = getattr(self, "_hand_area", None) if self._manual_area else None
        AreaDialog(self, image, chosen if then is not None else self._area_chosen,
                   tuple(hand) if hand is not None else self.settings.margins,
                   inner=lambda box: panel_inside(image, box), clear=cleared)

    def _area_chosen(self, box: tuple[int, int, int, int], size: tuple[int, int]) -> None:
        """The reader's own area for this viewer: kept, and never replaced by a page found in the frames - it bounds
        what is read: a page panel found inside it is read of it (`_find_page`); the status line says it in words."""
        if self.selected is None:
            return
        margins = area.box_to_margins(box, size)
        if not any(margins):  # the whole window
            self.clear_area()
            return
        self._manual_area = True
        self._hand_area = margins
        self.settings.margins = margins
        self.profiles.set_margins(self.selected, margins)
        self._auto_last = None
        self.say("Area set. Only this part of the viewer is read.")
        self._look_soon()  # Auto reads the page again, with this area

    def clear_area(self) -> None:
        """No area of the reader's: the page is looked for in the viewer's frames again (the whole window when none
        is found)."""
        self._manual_area = False
        self._hand_area = None
        if self.selected is not None:
            self.profiles.set_margins(self.selected, None)
        self.settings.margins = self._found_margins()
        self._auto_last = None
        self.say("Area cleared: TASlation looks for the page in the viewer's window by itself again (the whole window when it finds none).")
        self._look_soon()

    # ------------------------------------------------------------------ the viewer's window, as it is
    def _enlarge_first(self) -> bool:
        """As a viewer is chosen (`_on_window_selected`; a read asks again while it was not had): its window looked at
        once, as it is - TASlation never moves nor resizes it -, so that what waits for that look (early start,
        `LiveViewMixin._early_allowed`, and with it the backlog's pages) goes on. A window minimised (one
        `show_minimised` could not show again) or hidden is looked at again at the next read. Always True: the viewer
        can be read now. (The name is the one the window had when it enlarged the viewer's window first.)"""
        win = self.selected
        if win is not None and getattr(self, "_enlarge_asked", None) != win.hwnd and window_shown(win.hwnd):
            self._enlarge_asked = win.hwnd
        return True

    def _learn_covered_soon(self) -> None:
        """settle_ms after the viewer chosen has settled: whether it draws while other windows hide it wholly, found
        out with no key (`live.LiveViewMixin._learn_covered`), for the viewer chosen then."""
        win = self.selected
        if win is None or not hasattr(self, "_learn_covered"):
            return
        hwnd = win.hwnd
        self.after(self.settings.settle_ms, lambda: self._learn_covered(hwnd))

    def _put_back_left_enlarged(self) -> None:
        """At the start: a viewer's window a session of an older version left enlarged - it ended without closing the
        window - put back (`recovery.put_back_enlarged`)."""
        try:
            put_back_enlarged(self.settings.state_dir)
        except OSError:
            pass

    def _viewer_left(self) -> None:
        """Another viewer is being chosen: the next viewer starts afresh."""
        self._black_watch = None
        self._enlarge_asked = None
        self._lower_viewer()
        stop_capture()
