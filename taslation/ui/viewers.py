"""The viewer's window: the list of windows (rescanned as it opens, watched until a viewer is chosen), the one
chosen and whether it still shows the book, the capture area set by hand (the outer
bound of what is read, the page panel found inside it read of it: `live.LiveViewMixin._find_page`), the viewer's
keys (`pagekeys.page_keys_for`; Page keys...), the viewer's window shown again when it is chosen minimised
(`show_minimised`), enlarged as it is chosen (`_enlarge_first`) and put back afterwards, and the offline guard's
state."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .. import netguard, viewerparts
from ..batch import frames_differ, thumbnail
from ..cache import book_key_from_title
from ..capture import (
    BROWSER_CLASSES,
    IS_WINDOWS,
    NOT_VIEWERS,
    CaptureError,
    WindowInfo,
    enlarge_window,
    is_blank,
    is_black,
    is_browser_class,
    list_windows,
    looks_like_viewer,
    match_windows,
    restore_window,
    same_book_window,
    still_the_book,
    stop_capture,
    unminimise_window,
    viewer_candidates,
    window_exists,
    window_rect,
    window_shown,
    window_title,
)
from ..detect.page_area import panel_inside
from ..i18n import _
from ..pagekeys import PageKeys, default_keys, key_ways, own_keys, page_keys_for, passed_on, same_key, viewer_title
from ..recovery import forget_enlarged, keep_enlarged, put_back_enlarged
from . import area
from .constants import READING_NOTE_MS, SETTLE_TRIES, VIEWER_CLOSED, VIEWER_RESTORED, WINDOW_WATCH_MS, in_a_run
from .dialogs import caches as boxes
from .dialogs.area import AreaDialog

KEPT_ITS_SIZE = "This viewer's window keeps its size, so it is read as it is."
ENLARGED = "TASlation made the viewer's window larger to read the page; it goes back when you close TASlation."


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


def looks_like_browser(win: WindowInfo) -> bool:
    """Whether *win* is a browser's window, whose capture takes in its tabs and address bar around the page."""
    return win.class_name in BROWSER_CLASSES


def another_book(left: WindowInfo, chosen: WindowInfo, query: str = "") -> bool:
    """Whether the window *chosen* in place of *left* is another book's: another window, or a title that names another
    book; not a window that shows the book of *left*, closed, again (`same_book_window`)."""
    if left.hwnd == chosen.hwnd:
        return book_key_from_title(left.title) != book_key_from_title(chosen.title)
    return window_exists(left.hwnd) or not same_book_window(chosen.title, left.title, query)


def keys_words(keys: PageKeys, window: PageKeys | None = None) -> str:
    """The viewer's page keys in a sentence, in the window's language, the keys as the reader knows them
    (`reading.key_label`: the arrows as arrows); with the window's own next and previous keys (*window*), each of them
    that goes on to the viewer as another key is said too (`pagekeys.passed_on`)."""
    from .reading import key_label  # (imported here: `reading` imports this module)

    words = _("Page keys: {next} next page, {prev} previous page.").format(next=key_label(keys.next),
                                                                        prev=key_label(keys.prev))
    for here in (window.next, window.prev) if window is not None else ():
        key = passed_on(here, keys, window)
        if not same_key(key, here):
            words += "  " + _("{here} here goes to the viewer as {key}.").format(here=key_label(here),
                                                                              key=key_label(key))
    return words


class ViewerMixin:
    """The viewer list, the chosen viewer, its area and the offline guard. A part of `app.App` (no `__init__`: the
    state it uses is made by `App.__init__`; the other parts are reached through ``self``)."""

    # ------------------------------------------------------------------ the offline guard
    def _guard_numbers(self) -> tuple[str, int] | None:
        """The offline guard's allowed port(s) and how many attempts it blocked; None when it is off."""
        st = netguard.state()
        if st is None or not st.installed:
            return None
        return ",".join(str(p) for p in sorted(st.allowed_ports)), len(st.blocked)

    def _sync_guard(self) -> None:
        """Once the offline guard has blocked a connection attempt, the status bar says so until the window closes."""
        numbers = self._guard_numbers()
        text = ""
        if numbers is not None and numbers[1]:
            text = _("TASlation blocked {blocked} attempt(s) to reach the internet. Nothing left this computer; you need do nothing.").format(
                blocked=numbers[1])
        if self.guard_var.get() != text:
            self.guard_var.set(text)
            if hasattr(self, "status_label"):  # the warning takes room from the status line
                self.after_idle(self._wrap_status)

    def _guard_line(self) -> str:
        """The offline guard's state in a line, for Help > About TASlation."""
        numbers = self._guard_numbers()
        if numbers is None:
            return _("Offline guard: off.")
        return _("Offline guard: on. Only this computer's port {port} (Ollama) can be reached; {blocked} other connection attempt(s) were blocked.").format(
            port=numbers[0], blocked=numbers[1])

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
            self.say("Several windows look like a viewer: pick the right one in the Viewer list.")

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
        title gives: `_title_book`), area and keys, its line on the status line, its window shown again when it is
        minimised (`show_minimised`) and enlarged at once (`_enlarge_first`: in the background, the first frame read
        once it has settled), and the window followed. What a session before saw of the viewer is taken up (how it
        takes a key: `pagekeys.KeyWays.seed`), and once it has settled whether it draws while covered is found out with
        no key (`_learn_covered_soon`). A window chosen again keeps what it has; during a run the viewer stays the one
        the run began with."""
        idx = self.window_box.current()
        if idx < 0 or idx >= len(self.windows):
            return
        before, chosen = getattr(self, "selected", None), self.windows[idx]
        same = before is not None and before.hwnd == chosen.hwnd
        if in_a_run(self) and not same:  # a run reads the viewer it began with to the end
            self._show_chosen()
            self.say("The viewer cannot be changed during a run: press Stop first.")
            return
        if same and (in_a_run(self) or getattr(self, "busy", False)):
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
        try:
            key_ways(self).seed(chosen.hwnd, self.profiles.key_way_for(chosen))
        except Exception:  # noqa: BLE001 - nothing seen before: found out at the first key
            pass
        restored = show_minimised(self, chosen) if picked or not same else False
        if not self._book_edited:
            self.book_var.set(self._title_book(self.selected))
        else:
            self._title_name = None  # the Book box holds the reader's name: what they type says nothing of this title
        # (an image viewer's by its window class: `profile_names`; the same window chosen again keeps the area in use)
        margins = self.profiles.margins_for(self.selected, large=bool(getattr(self, "_area_large", False)))
        self._manual_area = margins is not None  # the reader's area bounds what is read; else the page is looked for
        self._hand_area = margins  # (the page panel found inside it takes over with the next frame: `_find_page`)
        self.settings.margins = margins if margins is not None else self._found_margins()
        self._auto_last = None
        self._live_thumb = None  # the next tick shows this viewer
        self._set_covered(False)
        title = self.selected.title
        own = own_keys(self.profiles, self.selected)  # (an image viewer's by its class, as the area)
        keys = page_keys_for(self.profiles, self.settings, self.selected) if own else None
        pair = self._page_key_pair() if own else None
        window = pair[1] if pair is not None else None
        if restored:
            def line() -> str:
                text = _(VIEWER_RESTORED).format(title=title)
                return text + "  " + keys_words(keys, window) if keys is not None else text

            self.status(line)
        elif margins is not None and any(margins):
            def line() -> str:
                text = _("Viewer: {title}  (area set)").format(title=title)
                return text + "  " + keys_words(keys, window) if keys is not None else text

            self.status(line)
        elif keys is not None:  # the viewer has keys of its own: said once, as it is chosen
            self.status(lambda: _("Viewer: {title}").format(title=title) + "  " + keys_words(keys, window))
        else:
            self.say("Viewer: {title}", title=title)
        self._redisplay()  # the hint for no viewer goes; this viewer's picture comes with the next look at it
        self._warm_page_models()  # (once the pipeline is there too)
        if self._enlarge_first():  # at once, in the background; the first frame is read once it has settled
            self._learn_covered_soon()  # (an enlarged window: once it has settled, `_enlarge_done`)
        self._follow_viewer()  # follow = "events": this viewer's window watched, and looked at at once
        if self._reading_at_start:
            self._reading_at_start = False
            self.after(300, self.enter_reading)

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
        while the window is still there; during a run nothing yet: the run ends by itself, and the looks that follow
        find the window gone."""
        win = self.selected
        if win is None or window_exists(win.hwnd) or in_a_run(self):
            return
        waiting = getattr(self, "_enlarging", None)
        if waiting is not None:
            waiting["then"] = None  # what waited for this window has nothing left to read
        self._viewer_left()
        self._viewer_closed = win  # what the next viewer's book is told from (`another_book`)
        self.selected = None
        self._auto_last = self._auto_candidate = None
        self._waiting = False
        self._set_covered(False)
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
            boxes.tell(self, _("Pick the viewer window first (open your e-book viewer, then choose it in the Viewer list)."), icon="info")
        return self.selected

    # ------------------------------------------------------------------ the area set by hand
    def set_area(self, then: Callable[[], None] | None = None) -> None:
        """Set area...: the area dialog over a fresh capture - the reader's own area, else the page found so far -
        with the page panel found inside the rectangle shown dashed (`page_area.panel_inside`: what is read of it);
        once an area is chosen or cleared (its Clear area: `clear_area`), *then()* (reading mode offered it first: the
        reading window opens). The area belongs to the frame that is read, so the viewer's window is enlarged first
        (`_enlarge_first`). Not during a run: a run that follows the reader widens its area with the pages it meets,
        within the reader's area it began with, other jobs keep one area; and its waiting for an enlarged window must
        not give way to this."""
        if in_a_run(self):
            self.say("The area cannot be changed during a run: press Stop first.")
            return
        win = self._current_window()
        if win is None or not self._enlarge_first(lambda: self.set_area(then)):
            return
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
        self.profiles.set_margins(self.selected, margins, large=bool(getattr(self, "_area_large", False)))
        self._auto_last = None
        self.say("Area set. Only this part of the viewer is read.")
        self._look_soon()  # Auto reads the page again, with this area

    def clear_area(self) -> None:
        """No area of the reader's: the page is looked for in the viewer's frames again (the whole window when none
        is found)."""
        self._manual_area = False
        self._hand_area = None
        if self.selected is not None:
            self.profiles.set_margins(self.selected, None, large=bool(getattr(self, "_area_large", False)))
        self.settings.margins = self._found_margins()
        self._auto_last = None
        self.say("Area cleared: TASlation looks for the page in the viewer's window by itself again (the whole window when it finds none).")
        self._look_soon()

    # ------------------------------------------------------------------ the viewer's keys
    def _page_keys(self, win: WindowInfo | None = None) -> PageKeys:
        """The keys to press in the viewer *win* (the chosen one by default): its profile's, the defaults', the
        settings' (`pagekeys.page_keys_for`)."""
        win = win if win is not None else self.selected
        return page_keys_for(self.profiles, self.settings, win if win is not None else "")

    def _page_key_pair(self) -> tuple[PageKeys, PageKeys] | None:
        """The chosen viewer's keys (`pagekeys.page_keys_for`) and the window's own next and previous keys
        (`pagekeys.default_keys`: what a person turns pages with everywhere), for a key pressed in the window
        (`reading.forward_key`); None without a viewer."""
        win = getattr(self, "selected", None)
        profiles = getattr(self, "profiles", None)
        if win is None or profiles is None:
            return None
        try:
            data = profiles.data if isinstance(getattr(profiles, "data", None), dict) else {}
            return page_keys_for(profiles, self.settings, win), default_keys(data, self.settings)
        except Exception:  # noqa: BLE001 - keys that cannot be read: a key goes on as it is
            return None

    def open_page_keys(self) -> None:
        """Page > Page keys...: the chosen viewer's keys - the presets, the keys - kept in its profile (or for every
        viewer): the keys the window's next and previous keys go on to it as (`reading.forward_key`). Nothing is
        pressed in the viewer from it: the person tries the keys in TASlation's window."""
        from .dialogs.pagekeys import PageKeysDialog

        win = self._current_window()
        if win is None:
            return
        PageKeysDialog(self, viewer_title(win), self.profiles, self.settings,
                       on_saved=lambda: self._page_keys_saved(win))

    def _page_keys_saved(self, win: WindowInfo) -> None:
        """The keys were saved: the status line says the chosen viewer's keys now."""
        if self.selected is None or self.selected.hwnd != win.hwnd:
            return
        keys = self._page_keys(win)
        pair = self._page_key_pair()
        window = pair[1] if pair is not None else None
        self.status(lambda: keys_words(keys, window))

    # ------------------------------------------------------------------ the viewer's window enlarged
    def _enlarge_first(self, then: Callable[[], None] | None = None) -> bool:
        """As a viewer is chosen (`_on_window_selected`, in the background; a read asks again while it was not had):
        its window, when it is smaller than its monitor's work area, is made that large (`capture.enlarge_window`: no
        key is pressed, the foreground and the order of the windows stay, so the page is drawn larger behind whatever
        is in front; a window maximised or as large stays as it is). Once per viewer chosen: a window the reader makes
        smaller afterwards stays as it is. A window minimised (one `show_minimised` could not show again) or hidden
        is left alone, and looked at again at the next read. Returns whether the viewer can be read now; False while
        the enlarged window settles, after which *then()* follows (none: Auto looks at the viewer again by itself;
        the last request to name one wins)."""
        waiting = getattr(self, "_enlarging", None)
        if waiting is not None:
            if then is not None:
                waiting["then"] = then
            return False
        win = self.selected
        if win is None or getattr(self, "_enlarge_asked", None) == win.hwnd or not window_shown(win.hwnd):
            return True
        self._enlarge_asked = win.hwnd
        enlarged = enlarge_window(win.hwnd)
        if enlarged is None:
            return True
        self._enlarged = enlarged
        self._keep_enlarged(enlarged)  # (put back at the next start should this session end without closing)
        self._enlarging = {"enlarged": enlarged, "then": then, "last": None, "tries": 0}
        self._auto_last = self._auto_candidate = None
        self._resize_begins()
        self.after(self.settings.settle_ms, self._enlarge_wait)
        return False

    def _enlarge_wait(self) -> None:
        """The enlarged window's frame looked at every settle_ms until two are alike (at most SETTLE_TRIES looks); the
        Tk thread is never held. Neither a frame of the size from before nor a blank one counts (a covered
        viewer gives a black frame first, then the page): two of those alike are no window that has settled."""
        waiting = getattr(self, "_enlarging", None)
        if waiting is None:
            return
        try:
            image = self._capture(waiting["enlarged"].hwnd)
        except CaptureError:
            image = None
        if image is not None and (image.size == waiting.get("old") or is_blank(image)
                                  or is_black(image, self.settings.margins)):
            image = None
        thumb = thumbnail(image) if image is not None else None
        waiting["tries"] += 1
        last = waiting["last"]
        settled = thumb is not None and last is not None and not frames_differ(last, thumb, 0.5)
        if settled or waiting["tries"] >= SETTLE_TRIES:
            self._enlarge_done(image, thumb)
            return
        waiting["last"] = thumb if thumb is not None else last
        self.after(self.settings.settle_ms, self._enlarge_wait)

    def _enlarge_done(self, frame: Any = None, thumb: Any = None) -> None:
        """The enlarged window has settled: the size it took is the one to find it by; a window that kept its size
        (one of a fixed size) is said once and read as it is, with nothing to put back. The capture area is the new
        size's own (`_sync_area`; *frame*, the settled one, has found its page panel: none, `_forget_page_area`), that
        frame goes on the page and Auto takes the page as the viewer draws it now, whoever is in front
        (`_look_afresh`). What waited follows, and a window that jumped by itself is explained after it (once), whose
        first line would else take the status line at once."""
        waiting, self._enlarging = self._enlarging, None
        enlarged = waiting["enlarged"]
        if enlarged is not None:
            try:
                enlarged.given = window_rect(enlarged.hwnd)
            except CaptureError:
                pass
            self._keep_enlarged(enlarged)  # (the size it took)
        if enlarged is not None and not enlarged.changed:
            self._enlarged = None
            self._keep_enlarged(enlarged, forget=True)  # nothing to put back
            self.say(KEPT_ITS_SIZE)
            if not self.reading:  # (the reading window shows the line on the page by itself)
                self.canvas.set_note(_(KEPT_ITS_SIZE), READING_NOTE_MS)  # "Translating..." takes the status line at once
        if frame is None:
            self._forget_page_area()
        self._sync_area()
        self._apply_found_margins()
        self._auto_last = self._auto_candidate = None
        self._look_afresh(frame, thumb)
        if waiting["then"] is not None:
            waiting["then"]()
        if (enlarged is not None and self._enlarged is enlarged and not getattr(self, "_enlarged_said", False)
              and enlarged.changed):
            self._enlarged_said = True  # a window that jumped by itself is explained, once
            self.say(ENLARGED)
            if not self.reading:
                self.canvas.set_note(_(ENLARGED), READING_NOTE_MS)
        self._learn_covered_soon()

    def _learn_covered_soon(self) -> None:
        """settle_ms after the viewer chosen has settled: whether it draws while other windows hide it wholly, found
        out with no key (`live.LiveViewMixin._learn_covered`), for the viewer chosen then."""
        win = self.selected
        if win is None or not hasattr(self, "_learn_covered"):
            return
        hwnd = win.hwnd
        self.after(self.settings.settle_ms, lambda: self._learn_covered(hwnd))

    def _restore_enlarged(self) -> None:
        """The viewer's window back as it was (`capture.restore_window`: only while it has the size TASlation gave it;
        no key is pressed), and no longer kept for the next start."""
        enlarged, self._enlarged = getattr(self, "_enlarged", None), None
        if enlarged is None:
            return
        try:
            restore_window(enlarged)
        except CaptureError:
            pass
        self._keep_enlarged(enlarged, forget=True)

    def _keep_enlarged(self, enlarged: Any, forget: bool = False) -> None:
        """The enlarged window kept in the state folder until it is put back (`recovery.keep_enlarged`), or no more
        (*forget*: `recovery.forget_enlarged`). A state folder that cannot be written keeps nothing."""
        state = getattr(getattr(self, "settings", None), "state_dir", None)
        if state is None:
            return
        try:
            if forget:
                forget_enlarged(state, enlarged.hwnd)
            else:
                keep_enlarged(state, enlarged)
        except OSError:
            pass

    def _put_back_left_enlarged(self) -> None:
        """At the start: a viewer's window a session before left enlarged - it ended without closing the window - put
        back (`recovery.put_back_enlarged`)."""
        try:
            put_back_enlarged(self.settings.state_dir)
        except OSError:
            pass

    def _viewer_left(self) -> None:
        """Another viewer is being chosen: what waited for this one's window goes on, the window is put back, and the
        next viewer starts afresh."""
        if getattr(self, "_enlarging", None) is not None:
            self._enlarge_done()
        self._restore_enlarged()
        self._black_watch = None
        self._enlarge_asked = None
        self._area_large = False
        self._lower_viewer()
        stop_capture()

    def _window_enlarged(self) -> bool:
        """Whether the chosen viewer's frame is the enlarged window's: being enlarged, or still of the size TASlation
        gave it (the reader may have made it smaller)."""
        enlarged, win = getattr(self, "_enlarged", None), self.selected
        if enlarged is None or win is None or enlarged.hwnd != win.hwnd:
            return False
        if getattr(self, "_enlarging", None) is not None:
            return True
        try:
            return enlarged.has_its_size(window_rect(enlarged.hwnd))
        except CaptureError:
            return False

    def _sync_area(self) -> None:
        """The reader's area of the frame there is now: the enlarged window has an area of its own (none at first: the
        page panel found alone; the profile's "margins_large"), the window as it was keeps its "margins"."""
        large = self._window_enlarged()
        if large == bool(getattr(self, "_area_large", False)) or self.selected is None:
            return
        self._area_large = large
        margins = self.profiles.margins_for(self.selected, large=large)
        self._manual_area = margins is not None
        self._hand_area = margins
        self._apply_found_margins()
