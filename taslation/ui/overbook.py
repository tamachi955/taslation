"""Over the book: while the chosen viewer fills its monitor and TASlation's window is on that monitor, the window
behaves like Windows' on-screen keyboard over the program it types into (`capture.overlay`). It stays topmost and
never takes the foreground: the viewer keeps it, so the reader's page keys go to the book as they would with nothing
in between (a key posted to a browser that is not in front reaches nothing, and a foreground taken from it at every
key stalls it), and clicks on TASlation's buttons and page strip still work. The window stays below alpha 255 the
whole time (`constants.WINDOW_ALPHA`, set before it is first shown): a browser covered by an opaque window stops
drawing.

* `over_due` decides, from what the window sees at each `OVER_TICK_MS`: the setting (View > Over the full-screen
  viewer, kept in ui.json), a viewer chosen that fills its monitor (`capture.is_fullscreen`), TASlation's window on
  that monitor (a book on another monitor needs nothing over it), and nothing holding it off.
* Holding it off: a dialog of the window open (it takes typing; over the full-screen viewer it is made topmost and
  given the foreground, the window stays topmost below it, and the mode comes back - the foreground to the viewer -
  when the last one closes: `_over_raise_dialogs`), and the keys taken by the main window: a box clicked to type in (Book, To), or the page
  pressed in the Translator role (Enter, Delete, Ctrl+Z work on its boxes), until another window comes to the front
  (the reader clicks the book).
* TASlation's own keys while the viewer has the foreground are hot keys (`OVER_HOTKEYS`), registered only while the
  mode is on and the viewer or TASlation is in front, taken back when it ends and at closing: F5 (translate; the
  browser's own F5 would reload the book, which the store counts), and in reading mode F11 and Esc (leave it). F11
  and Esc otherwise stay the viewer's (its own full screen), and the page keys are never registered.
* Tk makes its window anew for its full screen (reading mode in and out), without the style, and activates it: the
  style goes on again and the foreground goes back to the viewer once (`_over_rewrapped`).
* Where the reader put the window (`PLACE_TABLE` in ui.json): once it has been over the book - moved there with "Move
  TASlation there" or by hand - its size and place and the monitor's rectangle are kept, then again at each closing,
  and the next start opens it there (`opening_place`), before any viewer is followed: the offer to move it is for the
  first time. One place for the machine, not one per viewer: the monitor a book goes full screen on is the reading
  setup's, a browser viewer's window title changes with every book, and the window opens before any viewer is chosen.
  A monitor that is gone or has changed since puts the window where a first start does."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any

from ..capture import (
    IS_WINDOWS,
    foreground_owner,
    foreground_window,
    give_foreground,
    is_fullscreen,
    monitor_rect,
    window_exists,
)
from ..capture.overlay import HotKeys, has_over, set_over
from ..i18n import load_ui_flag, load_ui_table, save_ui_flag, save_ui_entry
from .layout import initial_geometry, kept_place

OVER_TICK_MS = 100  # how often the window looks whether it should be over the book, and takes the hot keys pressed
OVER_OFF_FLAG = "over_book_off"  # in ui.json: true once the reader turned the mode off
# TASlation's keys while the viewer has the foreground: name -> virtual-key code; the reading-mode ones only there
OVER_HOTKEYS = {"F5": 0x74, "F11": 0x7A, "Escape": 0x1B}
READING_HOTKEYS = ("F11", "Escape")
# the status line when the book is full screen on another monitor (`_over_offer`), and its button
MOVE_OFFER = "Your book is full screen on another monitor. Move TASlation there and it stays over the book: your keys go to the book, and F5 translates. Until then, F5 and F11 are the viewer's own keys."
MOVE_BUTTON = "Move TASlation there"
TYPING_CLASSES = ("Entry", "TEntry", "TCombobox", "Text", "Spinbox", "TSpinbox")  # boxes of the window one types in
PLACE_TABLE = "window_place"  # in ui.json: where the reader put the window once it had been over the book


def opening_place(state_dir: Any) -> tuple[str, bool] | None:
    """The size and place to open the window at, and whether it was maximised: where the reader put it last, once it
    had been over the book (`PLACE_TABLE`), while that monitor is there as it was (`layout.kept_place`); None: as a
    first start."""
    table = load_ui_table(Path(state_dir), PLACE_TABLE)
    geometry = table.get("geometry", "")
    try:
        monitor = tuple(int(v) for v in table.get("monitor", "").split(","))
    except ValueError:
        return None
    if len(monitor) != 4 or not kept_place(geometry, monitor):
        return None
    return geometry, table.get("zoomed") == "1"


def keep_place(state_dir: Any, geometry: str, zoomed: bool, monitor: tuple[int, int, int, int]) -> None:
    """Keep *geometry* (and whether the window is maximised) with the rectangle of its *monitor* (`opening_place`)."""
    for key, value in (("geometry", geometry), ("zoomed", "1" if zoomed else "0"),
                       ("monitor", ",".join(str(int(v)) for v in monitor))):
        save_ui_entry(Path(state_dir), PLACE_TABLE, key, value)


def over_due(*, enabled: bool, viewer_fills: bool, same_monitor: bool, held: bool) -> bool:
    """Whether the window should be over the book now (see the module's notes)."""
    return enabled and viewer_fills and same_monitor and not held


def wanted_hotkeys(on: bool, reading: bool, owner: str) -> frozenset[str]:
    """The hot keys to hold now: none while the mode is off or a third program is in front (they would be taken from
    it); F5 while the viewer or TASlation is; F11 and Esc too in reading mode."""
    if not on or owner not in ("viewer", "own"):
        return frozenset()
    if reading:
        return frozenset(("F5", *READING_HOTKEYS))
    return frozenset(("F5",))


class OverBookMixin:
    """The window over a full-screen viewer. A part of `app.App` (`_init_over` makes the state; the other parts are
    reached through ``self``)."""

    def _init_over(self) -> None:
        self._over_on = False  # the window is over the book now
        self._over_hwnd = 0  # ... its top-level window then (Tk makes it anew for its full screen)
        self._over_typing = False  # the main window took the keys: a box clicked to type in, the Translator's page
        self._over_told = False  # the status line said once this session what the mode does
        self._over_hotkeys: Any = None  # capture.overlay.HotKeys, made at the first need
        self._over_job: str | None = None
        self._over_placed = False  # the window was over the book in this session: its place is kept (`_remember_place`)
        enabled = bool(getattr(self.settings, "over_book", True)) and not load_ui_flag(Path(self.settings.state_dir),
                                                                                     OVER_OFF_FLAG)
        self.over_var = tk.BooleanVar(self, value=enabled)
        if not IS_WINDOWS:
            return
        for name in TYPING_CLASSES:
            self.bind_class(name, "<ButtonPress-1>", self._over_type_click, add="+")
        for sequence in ("<Map>", "<Destroy>"):  # a dialog opened or closed: at once, not at the next tick
            self.bind_class("Toplevel", sequence, lambda _e: self._over_soon(), add="+")
        self._over_job = self.after(OVER_TICK_MS, self._over_tick)

    # ------------------------------------------------------------------ what decides it
    def _over_dialogs(self) -> bool:
        """Whether a dialog of the window is open (on the screen, not a tooltip: those have no frame)."""
        for widget in self.winfo_children():
            if not isinstance(widget, tk.Toplevel):
                continue
            try:
                if widget.winfo_viewable() and not widget.overrideredirect():
                    return True
            except tk.TclError:
                pass
        return False

    def _over_dialog_windows(self) -> list[tk.Toplevel]:
        """The dialogs of the window on the screen (not the tooltips: those have no frame), a dialog's own boxes too
        (a "?" box over it), the one holding the window's input last."""
        found: list[tk.Toplevel] = []

        def walk(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                if not isinstance(child, tk.Toplevel):
                    continue
                try:
                    if child.winfo_viewable() and not child.overrideredirect():
                        found.append(child)
                except tk.TclError:
                    continue
                walk(child)

        walk(self)
        try:
            grab = str(self.tk.call("grab", "current") or "")
        except tk.TclError:
            grab = ""
        return sorted(found, key=lambda dialog: str(dialog) == grab)

    def _over_near(self) -> bool:
        """Whether the window is where it is over the book (`over_due` but for what holds it off): the setting on, the
        viewer chosen filling its monitor, TASlation's window on that monitor."""
        win = getattr(self, "selected", None)
        own = self._own_hwnd()
        if win is None or not own or not window_exists(win.hwnd):
            return False
        fills = is_fullscreen(win.hwnd)
        return over_due(enabled=bool(self.over_var.get()), viewer_fills=fills,
                        same_monitor=fills and monitor_rect(own) == monitor_rect(win.hwnd), held=False)

    def _over_elsewhere(self) -> bool:
        """Whether the viewer chosen fills a monitor other than the one TASlation's window is on, with the setting on:
        the window cannot be over the book from there (and F5 and F11 are the viewer's own keys meanwhile)."""
        win = getattr(self, "selected", None)
        own = self._own_hwnd()
        if win is None or not own or not window_exists(win.hwnd) or not self.over_var.get():
            return False
        return is_fullscreen(win.hwnd) and monitor_rect(own) != monitor_rect(win.hwnd)

    def _over_owner(self) -> str:
        win = getattr(self, "selected", None)
        return foreground_owner(foreground_window(), win.hwnd if win is not None else 0)

    # ------------------------------------------------------------------ the heartbeat
    def _over_soon(self) -> None:
        try:
            self.after_idle(self._over_sync)
        except tk.TclError:
            pass

    def _over_tick(self) -> None:
        self._over_job = None
        try:
            self._over_sync()
        finally:
            try:
                self._over_job = self.after(OVER_TICK_MS, self._over_tick)
            except tk.TclError:  # the window is going
                pass

    def _over_sync(self) -> None:
        """The mode on or off (on near the book, not while typing or a dialog is open), the style put on again where Tk made its window anew, the hot
        keys as `wanted_hotkeys` says, and the hot keys pressed since the last time acted on."""
        if not IS_WINDOWS:
            return
        if self._over_typing and not self._typing_on():
            self._over_typing = False
        near = self._over_near()
        dialogs = self._over_dialogs()
        wanted = near and not (self._over_typing or dialogs)
        if wanted and not self._over_on:
            self._over_enter()
        elif not wanted and self._over_on:
            self._over_leave(keep_top=near and dialogs)
        elif self._over_on:
            hwnd = self._own_hwnd()
            if hwnd != self._over_hwnd or not has_over(hwnd):
                self._over_rewrapped()
        if near and dialogs:
            self._over_raise_dialogs()
        self._over_offer(not near and not self.reading and self._over_elsewhere())
        self._over_keys()

    def _over_raise_dialogs(self) -> None:
        """A dialog opened over the full-screen viewer: above it (topmost while it is open), and in front, as a dialog
        that takes typing is (the viewer has the foreground, and Windows would leave the dialog behind it); once
        for each dialog, the one holding the window's input last. When the last one closes, Windows activates the
        window and the mode gives the foreground back to the viewer (`_over_enter`)."""
        for dialog in self._over_dialog_windows():
            if getattr(dialog, "_over_raised", False):
                continue
            dialog._over_raised = True  # type: ignore[attr-defined]
            try:
                dialog.attributes("-topmost", True)
                hwnd = int(dialog.wm_frame(), 16)
            except (tk.TclError, ValueError):
                continue
            give_foreground(hwnd)

    def _typing_on(self) -> bool:
        """Whether the main window still has the keys it took: TASlation is in front with the focus in it."""
        if self._over_owner() != "own":
            return False
        try:
            focus = self.focus_get()
        except (KeyError, tk.TclError):
            return False
        return focus is not None and focus.winfo_toplevel() is self

    # ------------------------------------------------------------------ in and out
    def _over_enter(self) -> None:
        """Over the book: the style and topmost (SWP_NOACTIVATE), and the foreground to the viewer when TASlation had
        it (the reader's next key goes to the book)."""
        hwnd = self._own_hwnd()
        if not hwnd or not set_over(hwnd, True):
            return
        self._over_on, self._over_hwnd = True, hwnd
        self._over_hand_back()
        self._over_placed = True
        self._remember_place()
        if not self._over_told and not self.reading:
            self._over_told = True
            self.say("TASlation stays over the full-screen viewer: your keys go to the book, and F5 still translates. View > Over the full-screen viewer turns this off.")

    def _over_leave(self, keep_top: bool = False) -> None:
        """A normal window again: no hot keys, no style, Always on top (or reading mode) as the reader has it - and
        topmost while a dialog holds the mode over the full-screen viewer (*keep_top*): the window the dialog
        belongs to stays in sight."""
        self._over_on = False
        if self._over_hotkeys is not None:
            self._over_hotkeys.clear()
        hwnd = self._own_hwnd()
        if hwnd:
            set_over(hwnd, False, topmost=bool(self.top_var.get()) or self.reading or keep_top)
        self._over_hwnd = 0

    def _over_rewrapped(self) -> None:
        """Tk made its window anew (its full screen in or out) without the style, and gave it the foreground: the
        style again, and the foreground back to the viewer."""
        hwnd = self._own_hwnd()
        if not hwnd or not set_over(hwnd, True):
            return
        self._over_hwnd = hwnd
        self._over_hand_back()

    # ------------------------------------------------------------------ the book full screen on another monitor
    def _over_offer(self, offered: bool) -> None:
        """The book full screen on another monitor: the status bar's button that moves TASlation there (`move_to_book`)
        while that lasts, and the status line says once for each viewer why. The window is not moved by itself: a
        reader may keep it on a monitor of its own on purpose, with the translated page beside the book; turning
        View > Over the full-screen viewer off takes the offer away too."""
        button = getattr(self, "move_btn", None)
        if button is None:
            return
        try:
            shown = bool(button.winfo_manager())
            if offered and not shown:
                button.pack(side="right", padx=(8, 0), before=self.status_label)
            elif not offered and shown:
                button.pack_forget()
        except tk.TclError:
            return
        win = getattr(self, "selected", None)
        if offered and win is not None and getattr(self, "_over_offer_said", 0) != win.hwnd:
            self._over_offer_said = win.hwnd
            self.say(MOVE_OFFER)

    def move_to_book(self) -> None:
        """The status bar's button: TASlation's window onto the monitor where the viewer is full screen, its size kept as
        far as that monitor allows, in the middle of it (maximised again there when it was); over the book from
        then on (`_over_sync`)."""
        win = getattr(self, "selected", None)
        monitor = monitor_rect(win.hwnd) if win is not None else None
        if monitor is None:
            return
        zoomed = self.state() == "zoomed"
        if zoomed:
            self.state("normal")
        self.update_idletasks()
        size = (self.winfo_width(), self.winfo_height())
        self.geometry(initial_geometry(self, size, at=((monitor[0] + monitor[2]) // 2, (monitor[1] + monitor[3]) // 2)))
        if zoomed:
            self.update_idletasks()
            self.state("zoomed")
        self.after_idle(self._over_sync)

    def _over_hand_back(self) -> None:
        """The foreground to the viewer when TASlation has it - or nobody has it, as for a moment after a dialog
        closed - never from a third program."""
        win = getattr(self, "selected", None)
        if win is not None and (not foreground_window() or self._over_owner() == "own"):
            give_foreground(win.hwnd)

    def _remember_place(self) -> None:
        """The window's size and place kept for the next start (`keep_place`), once it has been over the book in this
        session or an earlier one: what it returns to when it is neither maximised nor full screen."""
        if not (getattr(self, "_over_placed", False) or load_ui_table(Path(self.settings.state_dir), PLACE_TABLE)):
            return
        hwnd = self._own_hwnd()
        try:
            geometry, zoomed = self._reading_saved[0] if self.reading else self._current_geometry()
        except (AttributeError, tk.TclError):
            return
        monitor = monitor_rect(hwnd) if hwnd else None
        if monitor is None or not geometry:
            return
        try:
            keep_place(self.settings.state_dir, geometry, zoomed, monitor)
        except OSError:  # ui.json cannot be written now: the next start opens as the first one
            pass

    def _over_close(self) -> None:
        """The window closes: its place is kept (`_remember_place`), the hot keys go back to the system."""
        self._remember_place()
        if self._over_job is not None:
            try:
                self.after_cancel(self._over_job)
            except tk.TclError:
                pass
            self._over_job = None
        if self._over_hotkeys is not None:
            self._over_hotkeys.close()
            self._over_hotkeys = None
        self._over_on = False

    def toggle_over(self) -> None:
        """View > Over the full-screen viewer: kept in ui.json; off, the window is a normal window at once."""
        save_ui_flag(Path(self.settings.state_dir), OVER_OFF_FLAG, not self.over_var.get())
        self._over_sync()

    # ------------------------------------------------------------------ typing in the main window
    def _over_type_click(self, event: tk.Event) -> None:
        """A box of the main window clicked while over the book: it takes the keys (the mode holds off until the
        reader goes to another window)."""
        widget = event.widget
        try:
            if widget.winfo_toplevel() is not self or str(widget.cget("state")) in ("disabled", "readonly"):
                return
        except (AttributeError, tk.TclError):
            return
        self._over_take_keys(widget)

    def _over_page_press(self, _event: tk.Event | None = None) -> None:
        """The page pressed in the Translator role while over the book: the page takes the keys (Enter, Delete and
        Ctrl+Z work on its boxes). In the Reader role a press on the page goes on to the viewer, and the keys stay
        there."""
        if self.role_var.get() == "translator" and not self.reading:
            self._over_take_keys(self.canvas)

    def _over_take_keys(self, widget: Any) -> None:
        if not self._over_on:
            return
        self._over_typing = True
        self._over_leave()
        hwnd = self._own_hwnd()
        if hwnd:
            give_foreground(hwnd)
        try:
            widget.focus_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ TASlation's keys
    def _over_keys(self) -> None:
        on = self._over_on
        wanted = wanted_hotkeys(on, self.reading, self._over_owner() if on else "")
        keys = self._over_hotkeys
        if keys is None:
            if not wanted:
                return
            keys = self._over_hotkeys = HotKeys.start()
            if keys is None:
                return
        for name in keys.registered - wanted:
            keys.unregister(name)
        for name in sorted(wanted - keys.registered):
            keys.register(name, OVER_HOTKEYS[name])
        for name in keys.take():
            self._over_hotkey(name)

    def _over_hotkey(self, name: str) -> None:
        """A hot key pressed while the viewer had the foreground: what the same key does in TASlation's window."""
        if name == "F5":
            self.translate_now()
        elif name == "F11":
            self.toggle_reading()
        elif name == "Escape":
            self._on_escape()
