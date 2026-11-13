"""The question before a whole-book run is stopped (`StopQuestion`): what Stop would leave, and a button for each way
on, the one that changes nothing first in line and the answer to Escape, Return and the box's close button. A run
that has read more than a few pages is never ended by a key alone (`taslation.ui.jobs.JobsMixin.stop_batch`)."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Sequence

from ..layout import place_window
from .caches import ICONS, WARNING_CHARS, in_lines


class StopQuestion(tk.Toplevel):
    """*text* with TASlation's question icon and *choices* ((answer, label), right to left: the first is the safe
    one, which has the focus and is what Escape, Return and closing the box answer). Modal over *master*, centred
    over it and in front of everything (a full-screen viewer too); ``answer`` is the answer of the button pressed,
    the first choice's until then."""

    def __init__(self, master: tk.Misc, title: str, text: str, choices: Sequence[tuple[str, str]]):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(False, False)
        self.choices = list(choices)
        self.answer = self.choices[0][0]
        self.message_text = text
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        image, bitmap = ICONS["question"]
        try:
            icon: tk.Widget = ttk.Label(frm, image=image)
        except tk.TclError:  # a Tk without its stock icons: its built-in bitmap
            icon = tk.Label(frm, bitmap=bitmap)
        icon.grid(row=0, column=0, sticky="n", padx=(0, 12))
        width = WARNING_CHARS * max(1, tkfont.nametofont("TkDefaultFont").measure("0"))
        self.message = ttk.Label(frm, text=in_lines(text, width), justify="left")
        self.message.grid(row=0, column=1, sticky="nw")
        row = ttk.Frame(frm)
        row.grid(row=1, column=0, columnspan=2, sticky="e", pady=(14, 0))
        self.buttons: dict[str, ttk.Button] = {}
        for i, (answer, label) in enumerate(self.choices):
            button = ttk.Button(row, text=label, default="active" if i == 0 else "normal",
                                command=lambda answer=answer: self._choose(answer))
            button.pack(side="right", padx=(6 if i else 0, 0))
            self.buttons[answer] = button
        safe = self.choices[0][0]
        self.bind("<Escape>", lambda _e: self._choose(safe))
        self.bind("<Return>", self._on_return)
        self.bind("<KP_Enter>", self._on_return)
        self.protocol("WM_DELETE_WINDOW", lambda: self._choose(safe))
        self.buttons[safe].focus_set()
        place_window(self, master)
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.grab_set()
        except tk.TclError:  # not on the screen (yet): no grab
            pass

    def labels(self) -> list[str]:
        """The buttons' words, left to right."""
        return [label for _answer, label in reversed(self.choices)]

    def press(self, answer: str) -> None:
        self.buttons[answer].invoke()

    def _on_return(self, _event: tk.Event | None = None) -> None:
        """Return presses the button that has the focus (the safe one unless the reader moved it)."""
        try:
            focused = self.focus_get()
        except (KeyError, tk.TclError):
            focused = None
        for answer, button in self.buttons.items():
            if focused is button:
                button.invoke()
                return
        self._choose(self.choices[0][0])

    def _choose(self, answer: str) -> None:
        self.answer = answer
        self.destroy()


def ask_stop(master: tk.Misc, text: str, choices: Sequence[tuple[str, str]], title: str = "TASlation") -> str:
    """`StopQuestion` over *master*, waited for: the answer chosen (the first choice's when the box is closed)."""
    box = StopQuestion(master, title, text, choices)
    if box.winfo_exists():
        master.wait_window(box)
    return box.answer


__all__ = ["StopQuestion", "ask_stop"]
