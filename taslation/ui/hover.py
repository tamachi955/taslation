"""What the page shows in the Reader role, and how a bubble the pointer rests on shows the other side, there and in
the Translator role: two settings, each chosen in the View menu, in Tools > Settings... and with an optional key (none
at first), kept in the settings file and applied at once to the page on show, nothing translated again. The full
screen (F11, `reading`) keeps the role chosen: what holds for a role in the window holds there too.

`Settings.hover_shows`, what is on the page in the Reader role (`set_hover_shows`; the key of "hover_shows":
`flip_hover_shows`):

* "original" (the default): the page translated - the Japanese erased, the translation set -, and a bubble under the
  pointer shows its original. View > Show original shows the whole page as the viewer does, for as long as it is
  ticked; `Settings.bubble_zoom` off shows nothing under the pointer.
* "translation": the page as the viewer shows it, nothing erased and nothing set, and a bubble under the pointer shows
  its translation. Show original has nothing to do in the Reader role then (its entry is greyed and its key does
  nothing: `original_idle`); `bubble_zoom` does not count (the pointer is the way to the translation here).

The Translator role shows the translated page with its frames whatever `hover_shows` says, and a bubble
under the pointer shows its original as "original" has it (`bubble_zoom` and Show original counting), while the
Translator's pointer leaves room for it (`hover_usable`, `translator_free`; at a motion: `zoom.BubbleZoomMixin
._pointer_at_work`): a press, a drag, a handle of the selected region, the region editor and a modal dialog are the
Translator's, and a press held still or a right click pins nothing there (`reader_pointer`).

`Settings.hover_reveal`, how that bubble shows the other side (`set_hover_reveal`; the key of "hover_reveal":
`flip_hover_reveal`):

* "panel" (the default): a panel beside the bubble, never over it (`zoom.BubbleZoomMixin`): with the translation on the
  page, the bubble's original as drawn, enlarged, with its translation; with the original on the page, the translation
  alone at a readable size in the faces of its kind. The page does not change: both are in sight at once.
* "in_place": the bubble itself (`in_place.InPlaceMixin`): with the translation on the page it shows the original
  lettering, as the viewer has it; with the original on the page it is erased and its translation set exactly as the
  translated page has it. What was read as text, what was erased and the lettering chosen show where they are: the
  way to see a mistake of the reading or of the detection.

The delays are the panel's in both (`zoom.ZOOM_DELAY_MS`, `zoom.ZOOM_REST_MS`), one bubble at a time. In both, the key
of "show_japanese" opens the panel of the bubble under the pointer pinned with the bubble's Japanese as text and its
Copy buttons (`bubble_text`). The translation work is the same whatever is chosen (detection, OCR, translation, the
cache); only what is drawn differs. Nothing shows under the pointer on a page filling in with the translation on
the page."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from .. import config

HOVER_SHOWS = ("original", "translation")  # what a bubble under the pointer shows; the page shows the other
HOVER_REVEALS = ("panel", "in_place")  # how it shows it
# the View menu's choices, (value, label), and their tips in the status line (keys of the window's catalogs)
HOVER_LABELS = (("original", "Translation on the page, original under the pointer"),
                ("translation", "Original on the page, translation under the pointer"))
HOVER_TIPS = ("The page translated; rest the pointer on a bubble to see its original "
              "(the Translator role always shows the page so).",
              "In the Reader role: the page as the viewer shows it; "
              "rest the pointer on a bubble to see its translation.")
REVEAL_LABELS = (("panel", "Under the pointer: a panel beside the bubble"),
                 ("in_place", "Under the pointer: the bubble itself"))
REVEAL_TIPS = ("The other side in a panel beside the bubble: both are in sight at once.",
               "The other side in the bubble itself: the original lettering, or what was read as text, erased and set.")
# what the status line says once a choice is made: (setting, value) -> line (keys of the window's catalogs)
CHOSEN = {
    ("hover_shows", "translation"): "The page shows the original; rest the pointer on a bubble to see its translation "
                                    "(Reader role).",
    ("hover_shows", "original"): "The page shows the translation; rest the pointer on a bubble to see its original.",
    ("hover_reveal", "panel"): "A bubble under the pointer shows the other side in a panel beside it.",
    ("hover_reveal", "in_place"): "A bubble under the pointer shows the other side in its own place.",
}
ZOOM_OFF = "The page shows the translation (Enlarge the bubble under the pointer is off in Tools > Settings...)."
NOT_KEPT = "This choice holds until TASlation closes: it could not be kept in the settings file ({error})."


def hover_shows(window: Any) -> str:
    """What a bubble under the pointer shows by the window's settings ("original" for anything else)."""
    value = getattr(getattr(window, "settings", None), "hover_shows", "original")
    return value if value in HOVER_SHOWS else "original"


def hover_reveal(window: Any) -> str:
    """How a bubble under the pointer shows it by the window's settings ("panel" for anything else)."""
    value = getattr(getattr(window, "settings", None), "hover_reveal", "panel")
    return value if value in HOVER_REVEALS else "panel"


def other_side(value: str) -> str:
    """The other choice of `HOVER_SHOWS` (the key of "hover_shows" switches to it)."""
    return "original" if value == "translation" else "translation"


def other_reveal(value: str) -> str:
    """The other choice of `HOVER_REVEALS` (the key of "hover_reveal" switches to it)."""
    return "panel" if value == "in_place" else "in_place"


def _role(window: Any) -> str:
    var = getattr(window, "role_var", None)
    try:
        return str(var.get()) if var is not None else ""
    except tk.TclError:
        return ""


def reader_pointer(window: Any) -> bool:
    """Whether the pointer on the page is the reader's: in the Reader role, in the window and on the full screen alike
    (the full screen keeps the role chosen; a window with no role chosen reads on the full screen). Only there may the
    page show the original (`reverse_on`), and a press held still or a right click on a bubble pins its panel
    (`zoom.BubbleZoomMixin._hold_bubble`); in the Translator role a press selects and edits the regions, and a held one
    is the start of a drag."""
    role = _role(window)
    return role == "reader" or (bool(getattr(window, "reading", False)) and role != "translator")


def translator_window(window: Any) -> bool:
    """Whether *window* is in the Translator role, in the window or on the full screen: its pointer selects and
    edits."""
    return _role(window) == "translator"


def clicks_kept(window: Any) -> bool:
    """Whether no click on the page goes on to the viewer, whatever the page shows: on the full screen in the
    Translator role, whose clicks are the Translator's (`TranslatorMixin._on_release`, `_forward_click`; the page keys
    still turn the viewer's pages there). In the window the Translator's click on a page that is not the translated
    one goes on, and the Reader's always does."""
    return bool(getattr(window, "reading", False)) and _role(window) == "translator"


def translator_free(window: Any) -> bool:
    """Whether the Translator's pointer leaves room for a bubble's original under it: no press on the page under way
    (from a press to its release the Translator selects, moves, resizes, turns or draws: `TranslatorMixin._on_press`
    notes it in `_drag_start`), no region editor open (`_editor`) and no dialog holding the window's input (a modal
    one's grab)."""
    if getattr(window, "_drag_start", None) is not None:
        return False
    try:
        editor = getattr(window, "_editor", None)
        if editor is not None and editor.winfo_exists():
            return False
        grab = getattr(window, "grab_current", None)
        return grab is None or grab() is None
    except (tk.TclError, KeyError):  # (a grab of a window tkinter does not know: held all the same)
        return False


def hover_usable(window: Any) -> bool:
    """Whether the pointer may show a bubble's other side now: in the Reader role (`reader_pointer`), and in the
    Translator role - its page translated, the pointer showing the original - while the Translator's pointer leaves
    room for it (`translator_free`); on the full screen as in the window."""
    return reader_pointer(window) or (translator_window(window) and translator_free(window))


def reverse_on(window: Any) -> bool:
    """Whether the page shows the original now and a bubble under the pointer its translation: "translation" chosen,
    in the Reader role (`reader_pointer`; the Translator's page is the translated one)."""
    return hover_shows(window) == "translation" and reader_pointer(window)


def reveal_wanted(window: Any, style: str) -> bool:
    """Whether a bubble under the pointer shows its other side now in *style* ("panel" or "in_place"): that style
    chosen, where the pointer may show it (`hover_usable`), and - with the translation on the page, as the Translator
    role always has it - `Settings.bubble_zoom` on."""
    if hover_reveal(window) != style or not hover_usable(window):
        return False
    return reverse_on(window) or bool(getattr(getattr(window, "settings", None), "bubble_zoom", True))


def original_idle(window: Any) -> bool:
    """Whether View > Show original has nothing to do: the Reader role with "translation" chosen, whose page shows
    the original already (the full screen, which has no menu, turns Show original off as it starts)."""
    return hover_shows(window) == "translation" and _role(window) == "reader"


class HoverChoiceMixin:
    """The choices of what the page shows and how a bubble under the pointer shows the other side. A part of `app.App`
    through `reading.ReadingMixin` (no `__init__`; the other parts are reached through ``self``)."""

    def set_hover_shows(self, value: str, save: bool = True) -> None:
        """What a bubble under the pointer shows from now on, *value* ("original" or "translation"; the page shows
        the other): see `_set_hover`."""
        self._set_hover("hover_shows", value if value in HOVER_SHOWS else "original", save)

    def set_hover_reveal(self, value: str, save: bool = True) -> None:
        """How a bubble under the pointer shows the other side from now on, *value* ("panel" or "in_place"): see
        `_set_hover`."""
        self._set_hover("hover_reveal", value if value in HOVER_REVEALS else "panel", save)

    def _set_hover(self, key: str, value: str, save: bool) -> None:
        """The setting *key* set to *value*: on the page on show at once (nothing translated again: only what is
        drawn changes, no panel nor bubble's other side left over from before), the View menu's choice and an open
        Settings dialog following it; kept in the settings file with *save* (the View menu, the keys; the Settings
        dialog has written it itself), and said in the status line."""
        before = getattr(self.settings, key, None)
        setattr(self.settings, key, value)
        var = getattr(self, "hover_var" if key == "hover_shows" else "reveal_var", None)
        if var is not None and var.get() != value:
            var.set(value)
        self._zoom_hide()
        hide = getattr(self, "_reveal_hide", None)
        if hide is not None:
            hide()
        self._sync_original_entry()
        self._sync_settings_dialog(key, value)
        self._redisplay()
        problem = self._save_hover(key, value) if save and value != before else None
        if problem is not None:
            self.say(NOT_KEPT, error=problem)
        elif key == "hover_shows" and value == "original" and not getattr(self.settings, "bubble_zoom", True):
            self.say(ZOOM_OFF)
        else:
            self.say(CHOSEN[(key, value)])

    def flip_hover_shows(self) -> None:
        """The key of "hover_shows": the other choice (`other_side`), as the View menu would make it."""
        self.set_hover_shows(other_side(hover_shows(self)))

    def flip_hover_reveal(self) -> None:
        """The key of "hover_reveal": the other choice (`other_reveal`), as the View menu would make it."""
        self.set_hover_reveal(other_reveal(hover_reveal(self)))

    def _hover_chosen(self) -> None:
        """View > Translation on the page, original under the pointer / Original on the page, translation under the
        pointer, chosen."""
        self.set_hover_shows(self.hover_var.get())

    def _reveal_chosen(self) -> None:
        """View > Under the pointer: a panel beside the bubble / the bubble itself, chosen."""
        self.set_hover_reveal(self.reveal_var.get())

    def _save_hover(self, key: str, value: str) -> str | None:
        """*value* of *key* written into the settings file the window's settings come from (`config.settings_file`,
        as the Settings dialog writes it); what went wrong, None when nothing did."""
        try:
            config.write_settings(config.settings_file(self.settings), {key: value})
        except (config.ConfigError, OSError) as e:
            return getattr(e, "strerror", None) or str(e)
        return None

    def _sync_original_entry(self) -> None:
        """View > Show original greyed while it has nothing to do (`original_idle`), else as ever (the role changed,
        or the choice)."""
        entry = getattr(self, "_original_entry", None)
        if entry is None:
            return
        menu, index = entry
        try:
            menu.entryconfigure(index, state="disabled" if original_idle(self) else "normal")
        except tk.TclError:
            pass

    def _sync_settings_dialog(self, key: str, value: str) -> None:
        """An open Settings dialog shows *value* in its row for *key*, so that its Save does not undo it."""
        dialog = getattr(self, "_settings_dialog", None)
        try:
            if dialog is None or not dialog.winfo_exists():
                return
        except tk.TclError:
            return
        from .dialogs import settings as settings_dialog

        var = getattr(dialog, "extra", {}).get(key)
        row = next((r for r in settings_dialog.EXTRA_ROWS if r.key == key), None)
        if var is not None and row is not None:
            var.set(settings_dialog.SettingsDialog._shown(row.choices, value))


__all__ = ["CHOSEN", "HOVER_LABELS", "HOVER_REVEALS", "HOVER_SHOWS", "HOVER_TIPS", "HoverChoiceMixin", "NOT_KEPT",
           "REVEAL_LABELS", "REVEAL_TIPS", "ZOOM_OFF", "hover_reveal", "hover_shows", "hover_usable", "original_idle",
           "other_reveal", "other_side", "reader_pointer", "reveal_wanted", "reverse_on", "translator_free",
           "translator_window"]
