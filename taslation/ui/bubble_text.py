"""A bubble's Japanese and its translation at hand while reading, as text: to look a word up in a dictionary of one's
own (a pop-up dictionary over the text, or one that watches the clipboard) and to hold a translation against what it
translates. In reading mode and in the Reader role, in both modes of `Settings.hover_shows`, both ways of
`Settings.hover_reveal` (with "in_place" this is the one panel there is, opened on request) and whatever
`Settings.bubble_zoom` says; the Translator role's region editor has its regions' Japanese already ("Read as:").

* Show (the key of "show_japanese", F2 at first): the popup of `zoom` for the bubble under the pointer, pinned, with
  the bubble's Japanese as text under what the popup shows (its original and its translation, or the translation
  alone with the original on the page): text to select with the mouse, copied with the popup's Copy the Japanese (the
  part selected, or all of it) or Copy the translation (`_panel_text`). A bubble shown in its place goes back first.
  It stays while the pointer leaves the bubble for it, and goes with its Close, the key again, Esc, a click on the
  page or the wheel, and once its page is not on show any more (`zoom.BubbleZoomMixin._zoom_watch`). With the
  original on the page it opens with the Japanese alone and a "Show the translation" button: the key again (or the
  button) shows the translation first, and closes it only after that (`zoom.BubbleZoomMixin._zoom_unveil`).
* Step (the keys of "next_bubble", F3, and "previous_bubble", Shift+F3): the same popup pinned on the next or the
  previous bubble of the page in reading order (the regions' order, the bubbles the key of "show_japanese" opens on),
  from the pinned one, else the one under the pointer, else from the first or the last; at either end it stays where
  it is and the status line says so (no going round). No pointer is needed: placed by the bubble, not the pointer.
  With `Settings.hover_reveal` "in_place" too it is this popup (the one there is to pin, as with "show_japanese").
  F3 and Shift+F3 at first: F keys work in the whole window, no viewer turns its pages with them, they are next to
  F2, and Windows programs go on to the next match with F3 and back with Shift+F3.
* Copy (the keys of "copy_japanese", Shift+F2, and "copy_translation", Ctrl+F2, and the popup's buttons): the bubble's
  Japanese (the part selected in the pinned popup of that bubble, else all of it) or its translation (without the
  lettering's marks) put on the clipboard. Only then: nothing is ever put there by itself, and the clipboard holds that
  line of the book until something else is copied over it.
* The bubble: the one of the pinned popup while the pointer is where it was when it was pinned (a key or a hold
  chose it: a pointer left resting on another bubble does not count); else the translated one under the pointer, or
  one read and left without a translation (the smallest where they nest); with the pointer elsewhere - on the pinned
  popup, say -, the bubble of the popup on show.
* The Japanese: the region's own, when its page was read in this session. A page shown from the cache has none (the
  cache keeps no Japanese): the bubble's is read again from its crop of the capture in memory the first time it is
  asked for (`TranslatorMixin._read_source`: `Pipeline.read_source` in the worker, as the region editor's "Read the
  Japanese" does, the popup's line or the status line saying so meanwhile), kept with the region in memory and never
  written anywhere. Neither text is logged, nor said in the status line.
* Without a pointer (a touch screen, where a tap goes on to the viewer and nothing hovers): a press held still on a
  bubble, or a right click on it, pins its popup (`zoom.BubbleZoomMixin._hold_press`, `_pin_bubble`).
* Over the full-screen viewer, where the viewer keeps the keys, these keys are hot keys while the pointer is on
  TASlation's page or a popup is pinned (`text_hotkeys`, `overbook.OverBookMixin._over_keys`): no other key and no
  click is taken from the viewer, and a key of the viewer's (the page keys) can never be one of them
  (`shortcuts.Keymap.problem`)."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable

from ..i18n import _
from ..render.lettering import strip_marks
from . import shortcuts
from .dialogs.review import NOT_READ, READING, SelectableLine
from .zoom import STILL_PX, ZOOM_COLOURS, text_target

# the actions' names, the mixin's methods too
TEXT_ACTIONS = ("show_japanese", "copy_japanese", "copy_translation", "next_bubble", "previous_bubble")
# the virtual-key codes of the keys a hot key can be (`hotkey_code`) besides the letters, the digits and F1-F24
NAMED_VK = {"Return": 0x0D, "BackSpace": 0x08, "Delete": 0x2E, "Insert": 0x2D, "Pause": 0x13}
MOD_ALT, MOD_CONTROL, MOD_SHIFT = 0x1, 0x2, 0x4  # RegisterHotKey's modifiers
SELECTED = ("#3d6fb6", "#ffffff")  # the Japanese selected in the popup: background, text
# what is said (in the window's language)
NO_BUBBLE = "Rest the pointer on a bubble of the translated page first."
NO_TRANSLATION = "This bubble has no translation."
NOT_HERE = "In the Translator role, the region editor shows the Japanese of a region."
JAPANESE_COPIED = "The bubble's Japanese is on the clipboard."
TRANSLATION_COPIED = "The bubble's translation is on the clipboard."
COPY_JAPANESE, COPY_TRANSLATION, CLOSE = "Copy the Japanese", "Copy the translation", "Close"
STEP_AT = "Bubble {n} of {total}."  # the keys of "next_bubble" and "previous_bubble": where they went
STEP_FIRST = "This is the first bubble of the page."  # ... at an end, where nothing changes
STEP_LAST = "This is the last bubble of the page."
STEP_NONE = "The page on show has no bubble to go to."


def hotkey_code(key: str) -> tuple[int, int] | None:
    """*key* (as the keymap writes it) as a hot key: (RegisterHotKey's modifiers, the virtual-key code); None for a
    key that cannot be one here (only letters, digits, F1-F24 and `NAMED_VK`)."""
    mods, base = shortcuts.split(shortcuts.normal(key))
    flags = ((MOD_CONTROL if "Control" in mods else 0) | (MOD_ALT if "Alt" in mods else 0)
             | (MOD_SHIFT if "Shift" in mods else 0))
    if len(base) == 1 and base.isascii() and base.isalpha():
        return flags, ord(base.upper())
    if len(base) == 1 and base.isdigit():
        return flags, ord(base)
    if base[:1] == "F" and base[1:].isdigit() and 1 <= int(base[1:]) <= 24:
        return flags, 0x6F + int(base[1:])
    return (flags, NAMED_VK[base]) if base in NAMED_VK else None


def text_hotkeys(keymap: shortcuts.Keymap) -> dict[str, tuple[int, int]]:
    """The hot keys of `TEXT_ACTIONS` as *keymap* has them: action name -> (modifiers, virtual-key code), the first
    key of each that can be a hot key (`hotkey_code`)."""
    out: dict[str, tuple[int, int]] = {}
    for name in TEXT_ACTIONS:
        codes = [code for code in map(hotkey_code, keymap.of(name)) if code is not None]
        if codes and codes[0] not in out.values():
            out[name] = codes[0]
    return out


class BubbleTextMixin:
    """The Japanese and the translation of a bubble, shown and copied. A part of `app.App` through
    `reading.ReadingMixin` (no `__init__`: its state starts on first use; the other parts are reached through
    ``self``)."""

    # ------------------------------------------------------------------ the actions
    def show_japanese(self) -> None:
        """The key of "show_japanese": the popup of the bubble under the pointer pinned with its Japanese
        (`_pin_bubble`); the key again - on that bubble, off the bubbles, or with the pointer not moved since it was
        pinned (`_text_bubble`) - shows the translation a popup pinned with the original on the page holds back
        (`zoom.BubbleZoomMixin._zoom_unveil`), else closes it."""
        if not self._text_usable():
            self.say(NOT_HERE)
            return
        found = self._text_bubble(pointer_only=True)
        if getattr(self, "_zoom_pinned", False):
            shown = getattr(self, "_zoom_for", None)
            if found is None or (shown is not None and shown[1] is found[1]):
                unveil = getattr(self, "_zoom_unveil", None)
                if unveil is None or not unveil():
                    self._zoom_hide()
                return
        if found is None:
            self.say(NO_BUBBLE)
            return
        self._pin_bubble(found[1])

    def next_bubble(self) -> None:
        """The key of "next_bubble": the popup pinned on the next bubble of the page (`_step_bubble`)."""
        self._step_bubble(1)

    def previous_bubble(self) -> None:
        """The key of "previous_bubble": the popup pinned on the previous bubble of the page (`_step_bubble`)."""
        self._step_bubble(-1)

    def _step_bubble(self, step: int) -> None:
        """The popup pinned on the bubble *step* (1 or -1) away in reading order (`_text_bubbles`) from the pinned
        one, else from the one under the pointer; with neither, the first (1) or the last (-1). At an end nothing
        changes and the status line says so; else it says which bubble of how many (no text of the bubble)."""
        if not self._text_usable():
            self.say(NOT_HERE)
            return
        bubbles = self._text_bubbles()
        if not bubbles:
            self.say(STEP_NONE)
            return
        start = self._pinned_bubble() or self._text_bubble(pointer_only=True)
        at = next((i for i, r in enumerate(bubbles) if start is not None and r is start[1]), None)
        if at is None:
            target = 0 if step > 0 else len(bubbles) - 1
        elif not 0 <= at + step < len(bubbles):
            self.say(STEP_LAST if step > 0 else STEP_FIRST)
            return
        else:
            target = at + step
        region = bubbles[target]
        box = self._zoom_screen_box(region)
        self._pin_bubble(region, at=((box[0] + box[2]) // 2, (box[1] + box[3]) // 2))
        self.say(STEP_AT, n=target + 1, total=len(bubbles))

    def _pin_bubble(self, region: Any, at: tuple[int, int] | None = None) -> None:
        """The popup pinned on *region* of the page on show (`zoom.BubbleZoomMixin._zoom_show`; placed by the screen
        point *at*, else by the pointer), the popup before and a bubble shown in its place (`in_place`) gone first;
        where the pointer is now is kept (`_pointer_still`)."""
        self._zoom_hide()
        hide = getattr(self, "_reveal_hide", None)
        if hide is not None:
            hide()
        self._zoom_show(region, pinned=True, at=at)
        try:
            self._zoom_pinned_at = tuple(self.winfo_pointerxy())
        except tk.TclError:
            self._zoom_pinned_at = None

    def copy_japanese(self) -> None:
        """The key of "copy_japanese" and the popup's Copy the Japanese: the bubble's Japanese on the clipboard - the
        part selected in its pinned popup, else all of it, read first where the page came from the cache (the status
        line says so meanwhile)."""
        if not self._text_usable():
            self.say(NOT_HERE)
            return
        found = self._text_bubble()
        if found is None:
            self.say(NO_BUBBLE)
            return
        result, region = found
        part = self._japanese_selected(region)
        if part:
            self._to_clipboard(part, JAPANESE_COPIED)
            return
        if not self._japanese(region):
            self.say(READING)
        self._japanese_of(result, region, self._japanese_read)

    def _japanese_read(self, text: str, error: str) -> None:
        """The Japanese `copy_japanese` asked for: on the clipboard, or why there is none."""
        if text:
            self._to_clipboard(text, JAPANESE_COPIED)
        else:
            self.say(NOT_READ.get(error, NOT_READ["none"]))

    def copy_translation(self) -> None:
        """The key of "copy_translation" and the popup's Copy the translation: the bubble's translation on the
        clipboard, without the lettering's marks."""
        if not self._text_usable():
            self.say(NOT_HERE)
            return
        found = self._text_bubble()
        if found is None:
            self.say(NO_BUBBLE)
            return
        text = strip_marks(str(getattr(found[1], "translated_text", "") or "")).strip()
        if not text:
            self.say(NO_TRANSLATION)
            return
        self._to_clipboard(text, TRANSLATION_COPIED)

    # ------------------------------------------------------------------ the bubble and its Japanese
    def _text_usable(self) -> bool:
        """Whether the actions work now: in reading mode or the Reader role (the Translator has the region editor)."""
        if getattr(self, "reading", False):
            return True
        try:
            return self.role_var.get() == "reader"
        except tk.TclError:
            return False

    def _pointer_on_page(self) -> tuple[int, int] | None:
        """The pointer on the page's canvas (its pixels), while it is on the canvas; else None."""
        try:
            px, py = self.winfo_pointerxy()
            canvas = self.canvas
            x, y = px - canvas.winfo_rootx(), py - canvas.winfo_rooty()
            inside = 0 <= x < canvas.winfo_width() and 0 <= y < canvas.winfo_height()
        except (AttributeError, tk.TclError):
            return None
        return (x, y) if inside else None

    def _text_bubbles(self) -> list[Any]:
        """The bubbles of the translated page on show that the popup may be pinned on, in reading order (the regions'
        order, as the Translator's Tab goes through them): translated ones and ones left without a translation
        (`zoom.text_target`); none while that page is not on show."""
        if self.last_result is None or not self._result_on_show():
            return []
        return [r for r in self._page_regions() if text_target(r, untranslated=True)]

    def _pinned_bubble(self) -> tuple[Any, Any] | None:
        """(the page on show, the region) of the pinned popup, while it is pinned on a bubble of that page."""
        shown = getattr(self, "_zoom_for", None)
        result = self.last_result
        if not getattr(self, "_zoom_pinned", False) or shown is None or result is None or shown[0] is not result:
            return None
        return shown if any(r is shown[1] for r in result.regions) else None

    def _pointer_still(self) -> bool:
        """Whether the pointer is where it was when the popup was pinned (within `zoom.STILL_PX`): it has not chosen
        a bubble since, so a key acts on the pinned one, whatever lies under the pointer."""
        then = getattr(self, "_zoom_pinned_at", None)
        if then is None:
            return False
        try:
            px, py = self.winfo_pointerxy()
        except tk.TclError:
            return False
        return abs(px - then[0]) <= STILL_PX and abs(py - then[1]) <= STILL_PX

    def _text_bubble(self, pointer_only: bool = False) -> tuple[Any, Any] | None:
        """(the page on show, the region) the actions act on: the bubble of the pinned popup while the pointer has not
        moved since it was pinned (`_pointer_still`); else the bubble under the pointer on the translated page on
        show (`zoom.BubbleZoomMixin._zoom_region_at`, a bubble left without a translation too); else - unless
        *pointer_only* - the bubble of the popup on show; None while neither is there."""
        result = self.last_result
        if result is None or not self._result_on_show():
            return None
        pinned = self._pinned_bubble()
        if pinned is not None and self._pointer_still():
            return pinned
        pointer = self._pointer_on_page()
        region = self._zoom_region_at(*pointer, untranslated=True) if pointer is not None else None
        if region is not None:
            return result, region
        shown = getattr(self, "_zoom_for", None)
        if not pointer_only and shown is not None and shown[0] is result and any(r is shown[1] for r in result.regions):
            return shown
        return None

    @staticmethod
    def _japanese(region: Any) -> str:
        return str(getattr(region, "source_text", "") or "").strip()

    def _japanese_selected(self, region: Any) -> str:
        """The part of *region*'s Japanese selected in its pinned popup, "" for none."""
        line = getattr(self, "_zoom_japanese", None)
        shown = getattr(self, "_zoom_for", None)
        if line is None or shown is None or shown[1] is not region:
            return ""
        try:
            return line.get("sel.first", "sel.last").strip() if line.tag_ranges("sel") else ""
        except tk.TclError:
            return ""

    def _japanese_of(self, result: Any, region: Any, then: Callable[[str, str], None]) -> None:
        """*region*'s Japanese handed to *then* (the text, and what went wrong: a key of `dialogs.review.NOT_READ`):
        at once when it has it, else once it is read from its crop of *result*'s capture in the worker
        (`TranslatorMixin._read_source`, nothing stored); a reading under way for it serves every request that
        comes meanwhile."""
        text = self._japanese(region)
        if text:
            then(text, "")
            return
        waiting = getattr(self, "_japanese_waiting", None)
        if waiting is None:
            waiting = self._japanese_waiting = {}
        key = id(region)
        if key in waiting:
            waiting[key][1].append(then)
            return
        waiting[key] = (region, [then])

        def done(text: str, error: str) -> None:
            for step in waiting.pop(key, (None, []))[1]:
                step(text.strip(), error)

        reader = getattr(self, "_read_source", None)
        if reader is None or reader(region, result, done) is False:  # the reading model is not loaded yet
            done("", "no-ocr")

    def _to_clipboard(self, text: str, said: str) -> None:
        """*text* on the clipboard, in place of what was there (the reader asked for it), and *said* in the status
        line (without the text)."""
        self.clipboard_clear()
        self.clipboard_append(text)
        self.say(said)

    # ------------------------------------------------------------------ the pinned popup
    def _panel_text(self, popup: tk.Toplevel, inner: tk.Frame, region: Any, result: Any, width: int,
                    font: tkfont.Font) -> None:
        """Under the picture and the translation of the pinned popup (`zoom.BubbleZoomMixin._zoom_show`): the
        bubble's Japanese at the translation's size, to select (`dialogs.review.SelectableLine`: never edited), or
        "Reading the Japanese..." with a running bar while it is read (`_japanese_of`), or why none was; then Copy
        the Japanese, Copy the translation and Close, each named with its key. The actions' keys and Esc work in the
        popup too, once a click to select there has given it the keys."""
        colours = ZOOM_COLOURS
        ground = colours["ground"]
        box = tk.Frame(inner, bg=ground)
        box.pack(side="top", anchor="w", fill="x", pady=(10, 0))
        var = tk.StringVar(popup, value="")
        line = SelectableLine(box, var, wraplength=width)
        line.configure(font=font, background=ground, foreground=colours["text"], selectbackground=SELECTED[0],
                       inactiveselectbackground=SELECTED[0], selectforeground=SELECTED[1],
                       width=max(10, width // max(1, font.measure("0"))))
        note = tk.Label(box, text="", fg=colours["hint"], bg=ground, justify="left", wraplength=width)
        bar = ttk.Progressbar(box, mode="indeterminate", length=120)
        keymap = getattr(self, "keymap", None) or shortcuts.current()
        veiled = getattr(self, "_zoom_veiled", None)  # (the translation held back: the key shows it first)
        buttons = tk.Frame(inner, bg=ground)
        buttons.pack(side="top", anchor="w", pady=(10, 0))
        for i, (label, name, step) in enumerate(((COPY_JAPANESE, "copy_japanese", lambda: self.copy_japanese()),
                                                 (COPY_TRANSLATION, "copy_translation",
                                                  lambda: self.copy_translation()),
                                                 (CLOSE, "show_japanese", lambda: self._zoom_hide()))):
            text = shortcuts.with_keys(label, name, keymap)
            button = ttk.Button(buttons, text=_(label) if name == "show_japanese" and veiled else text, command=step,
                                takefocus=0)
            button.pack(side="left", padx=(0 if i == 0 else 6, 0))
            if name == "show_japanese" and veiled:  # Close names the key once the translation shows
                veiled[3].append(lambda b=button, t=text: b.configure(text=t))
            if name == "copy_translation" and not str(getattr(region, "translated_text", "") or "").strip():
                button.configure(state="disabled")
        shortcuts.bind_on([popup], keymap, {name: (lambda _e, n=name: getattr(self, n)()) for name in TEXT_ACTIONS})
        popup.bind("<Escape>", lambda _e: self._zoom_hide())
        self._zoom_japanese = line

        def shown(text: str, error: str) -> None:
            if getattr(self, "_zoom_japanese", None) is not line:  # the popup is gone, or another one is there
                return
            bar.stop()
            bar.pack_forget()
            if text:
                note.pack_forget()
                var.set(text)
                line.pack(side="top", anchor="w", fill="x")
            else:
                note.configure(text=_(NOT_READ.get(error, NOT_READ["none"])))
            try:
                popup.update_idletasks()
                self._zoom_place(popup, (popup.winfo_reqwidth(), popup.winfo_reqheight()))
            except (tk.TclError, AttributeError):
                pass

        text = self._japanese(region)
        if text:
            var.set(text)
            line.pack(side="top", anchor="w", fill="x")
            return
        note.configure(text=_(READING))
        note.pack(side="top", anchor="w")
        bar.pack(side="top", anchor="w", pady=(4, 0))
        bar.start(15)
        self._japanese_of(result, region, shown)


__all__ = ["BubbleTextMixin", "MOD_ALT", "MOD_CONTROL", "MOD_SHIFT", "NAMED_VK", "TEXT_ACTIONS", "hotkey_code",
           "text_hotkeys"]
