"""Copy details: what TASlation runs on and the last error, for a report, on the clipboard (`errorlog.details_text`:
no text, title or path of the reader's). In Help > About TASlation (`dialogs.about`) and in the window's error boxes:
`watch_error_boxes` gives every `WarningBox` that tells of a problem (one button, the warning icon) a Copy details
button as it comes up, so that the boxes need not know of it."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from .. import errorlog
from ..i18n import _
from .tooltip import tip


def put_on_clipboard(widget: tk.Misc, text: str) -> None:
    """*text* on the clipboard, through Tk (the tests put a stand-in here: they never touch the real clipboard)."""
    widget.clipboard_clear()
    widget.clipboard_append(text)


def copy_details(widget: tk.Misc, settings: Any = None) -> str:
    """`errorlog.details_text` for the settings of *widget*'s window (else the session's) on the clipboard; the text."""
    if settings is None:
        try:
            settings = getattr(widget._root(), "settings", None)
        except (AttributeError, tk.TclError):
            settings = None
    text = errorlog.details_text(settings)
    put_on_clipboard(widget, text)
    return text


def details_button(parent: tk.Misc, owner: tk.Misc, settings: Any = None) -> ttk.Button:
    """A Copy details button in *parent* (not packed); pressed, it copies (`copy_details`) and says Copied."""
    button = ttk.Button(parent, text=_("Copy details"))

    def press() -> None:
        copy_details(owner, settings)
        try:
            button.configure(text=_("Copied"))
        except tk.TclError:  # (the box closed meanwhile)
            pass

    button.configure(command=press)
    tip(_("The version, the system and the last error, for a report. Nothing from your books is in them."), button)
    return button


def is_error_box(widget: Any) -> bool:
    """Whether *widget* is TASlation's box that tells of a problem: a `WarningBox` with one button and the warning
    icon (not a question, not an information)."""
    from .dialogs.caches import ICONS, WarningBox

    if not isinstance(widget, WarningBox):
        return False
    try:
        if widget.cancel_btn.winfo_manager():
            return False
        icon = widget.icon
        try:
            image = icon.cget("image")
        except tk.TclError:
            image = ""
        if isinstance(image, (tuple, list)):  # (a ttk label gives its images as a tuple)
            image = image[0] if image else ""
        image = str(image)
        try:
            bitmap = str(icon.cget("bitmap"))
        except tk.TclError:
            bitmap = ""
    except (AttributeError, tk.TclError):
        return False
    warning_image, warning_bitmap = ICONS["warning"]
    return image == warning_image or (not image and bitmap == warning_bitmap)


def add_to_error_box(box: Any) -> ttk.Button | None:
    """A Copy details button beside the error box's OK (once); the button, or None for a box that is none."""
    if getattr(box, "details_btn", None) is not None or not is_error_box(box):
        return None
    button = details_button(box.continue_btn.master, box)
    button.pack(side="right", padx=(0, 6))
    box.details_btn = button
    return button


def watch_error_boxes(root: tk.Misc) -> None:
    """Every error box of the window gets Copy details as it comes up (a ``<Map>`` binding on the class Toplevel)."""
    def mapped(event: tk.Event) -> None:
        try:
            add_to_error_box(event.widget)
        except tk.TclError:  # (a box closed as it came up)
            pass

    root.bind_class("Toplevel", "<Map>", mapped, add="+")
