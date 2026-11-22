"""The strips across the top of the page area, between the toolbar and the page (`Strip`):

* the setup banner (`SetupBanner`): what stands in the way of translating new pages - the Messages of
  `taslation.health.check` (Ollama not running, the model or the OCR model missing) - one line each, in the
  window's language, until it is fixed; ``NOTICE_CODES`` are notices (translating works);
* the band (white on dark blue): the names that the pages read render in more than one way, with Review names... and
  Close (`status.StatusMixin._band_view`).

Also about how long a time is in each window language (`duration_text`) and the text broken into lines by hand
(`break_lines`: Tk itself breaks lines only at spaces)."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable, Sequence

from ..i18n import _
from . import theme
from .progress import code_of, rendered
from .wrap import wrap_text

# setup lines that only inform (translating works); translator.other_model: Qwen translates while PLaMo is not installed
NOTICE_CODES = frozenset({"health.other_model", "health.chosen_other_model", "translator.other_model"})
# the strips' colours as the light mode has them (ground, text); `theme.strip_colours` gives them in the mode the window
# shows (dark: light text on a dark amber or blue; the band stays as it is; high contrast: Windows' colours)
PROBLEM_COLOURS = (theme.LIGHT["problem_ground"], theme.LIGHT["banner_text"])  # a setup problem: dark text on amber
NOTICE_COLOURS = (theme.LIGHT["notice_ground"], theme.LIGHT["banner_text"])  # a notice: dark text on pale blue
# the band: white on dark blue, unlike anything the viewer shows
BAND_COLOURS = (theme.LIGHT["band_ground"], theme.LIGHT["band_text"])


def is_notice(message: Any) -> bool:
    """Whether a setup line only informs (translating works all the same)."""
    return code_of(message) in NOTICE_CODES


def duration_text(seconds: float) -> str:
    """About how long *seconds* are, in the window's language: "35 min", "1 h 5 min" (at least a minute)."""
    minutes = max(1, int(round(float(seconds) / 60.0)))
    if minutes < 60:
        return _("{minutes} min").format(minutes=minutes)
    hours, minutes = divmod(minutes, 60)
    return _("{hours} h {minutes} min").format(hours=hours, minutes=minutes)


def break_lines(text: str, width: int, widget: tk.Misc) -> str:
    """*text* broken into lines of at most *width* pixels in *widget*'s font (`wrap.wrap_line`: never inside
    "TASlation", between the characters of a Japanese sentence)."""
    measure = tkfont.Font(root=widget, font=str(widget.cget("font")) or "TkDefaultFont").measure
    return "\n".join(line.rstrip(" ") for lines in wrap_text(text, max(80, int(width)), measure) for line in lines)


def busy_title() -> str:
    """The window's title while a job runs."""
    return _("TASlation - translating...")


class Strip(tk.Frame):
    """A strip across the page area: lines of text at its left, broken to fit its width, and buttons at its right.
    `set` changes what it shows; the window packs it and takes it away."""

    def __init__(self, master: tk.Misc, colours: tuple[str, str], pad: tuple[int, int] = (10, 5)):
        ground = theme.strip_colours(colours)[0]
        super().__init__(master, bg=ground, bd=0, highlightthickness=0)
        self.colours = colours  # as the light mode has them: each `set` shows them in the mode the window shows
        self.lines: list[str] = []  # the lines as they were given (unbroken)
        self.labels: list[tk.Label] = []  # one per line, as wide as the strip (its colours to the edges)
        self.buttons: list[ttk.Button] = []
        self._pad = pad
        self.text_box = tk.Frame(self, bg=ground, bd=0, highlightthickness=0)
        self.button_box = tk.Frame(self, bg=ground, bd=0, highlightthickness=0)  # packed while it has buttons
        self.text_box.pack(side="left", fill="both", expand=True)
        self._width = 0
        self.bind("<Configure>", lambda _e: self._wrap())

    def set(self, lines: Sequence[str], buttons: Sequence[tuple[str, Callable[[], None]]] = (),
            colours: Sequence[tuple[str, str]] | None = None) -> None:
        """Show *lines* (each in its own colours, else the strip's) and *buttons* ((text, command), left to right)."""
        lines = [str(line) for line in lines]
        while len(self.labels) > len(lines):
            self.labels.pop().destroy()
        while len(self.labels) < len(lines):
            label = tk.Label(self.text_box, anchor="w", justify="left", bd=0, padx=self._pad[0],
                             pady=self._pad[1] // 2 + 1)
            label.pack(fill="x", anchor="w")
            self.labels.append(label)
        self._ground()
        for i, label in enumerate(self.labels):
            bg, fg = theme.strip_colours(colours[i] if colours and i < len(colours) else self.colours)
            label.configure(bg=bg, fg=fg)
        self.lines = lines
        if [b.cget("text") for b in self.buttons] != [str(text) for text, _command in buttons]:
            for button in self.buttons:
                button.destroy()
            self.buttons = []
            for text, command in buttons:
                button = ttk.Button(self.button_box, text=text, command=command)
                button.pack(side="left", padx=(4, 0))
                self.buttons.append(button)
        else:
            for button, (_text, command) in zip(self.buttons, buttons):
                button.configure(command=command)
        if self.buttons and not self.button_box.winfo_manager():
            self.button_box.pack(side="right", padx=(6, self._pad[0]), pady=max(2, self._pad[1] - 1),
                                 before=self.text_box)
        elif not self.buttons and self.button_box.winfo_manager():
            self.button_box.pack_forget()
        self._wrap(force=True)

    def texts(self) -> list[str]:
        """The lines on show, unbroken."""
        return list(self.lines)

    def _ground(self) -> None:
        """The strip's own ground in the mode the window shows (it may have changed since: `theme.apply`)."""
        ground = theme.strip_colours(self.colours)[0]
        for frame in (self, self.text_box, self.button_box):
            if str(frame.cget("bg")) != ground:
                frame.configure(bg=ground)

    def press(self, text: str) -> None:
        """Press the button labelled *text* (as a click does)."""
        for button in self.buttons:
            if str(button.cget("text")) == text:
                button.invoke()
                return
        raise KeyError(text)

    def _wrap(self, force: bool = False) -> None:
        """The lines broken to the room the buttons leave (while the strip is not on the screen: as if 900 px)."""
        try:
            width = self.winfo_width()
            buttons = self.button_box.winfo_reqwidth() + 6 + self._pad[0] if self.buttons else 0
            room = (width if width > 1 else 900) - buttons - 2 * self._pad[0] - 8
        except tk.TclError:
            return
        if not force and room == self._width:
            return
        self._width = room
        for label, line in zip(self.labels, self.lines):
            label.configure(text=break_lines(line, max(160, room), label))


class SetupBanner(Strip):
    """The setup banner: one line per problem (dark on amber) or notice (dark on pale blue), each with a button of
    its own at its right when it has one (what fixes it: `trouble`)."""

    def __init__(self, master: tk.Misc):
        super().__init__(master, PROBLEM_COLOURS, pad=(10, 3))
        self.rows: list[tk.Frame] = []
        self.row_buttons: list[ttk.Button | None] = []
        self._signature: list[str | None] = []

    def show(self, messages: Sequence[Any], notes: Sequence[str] = ()) -> None:
        """The Messages of a setup check, each in the window's language, then *notes* (lines of the window's own,
        as notices); no buttons."""
        self.show_rows([*((rendered(m), NOTICE_COLOURS if is_notice(m) else PROBLEM_COLOURS, None) for m in messages),
                        *((note, NOTICE_COLOURS, None) for note in notes)])

    def show_rows(self, rows: Sequence[tuple[str, tuple[str, str], tuple[str, Callable[[], None]] | None]]) -> None:
        """*rows*: (line, its colours, its button (text, command) or None), top to bottom."""
        lines = [str(line) for line, _colours, _button in rows]
        signature = [str(button[0]) if button else None for _line, _colours, button in rows]
        if signature != self._signature:
            for row in self.rows:
                row.destroy()
            self.rows, self.labels, self.row_buttons = [], [], []
            for text in signature:
                row = tk.Frame(self.text_box, bd=0, highlightthickness=0)
                row.pack(fill="x")
                label = tk.Label(row, anchor="w", justify="left", bd=0, padx=self._pad[0], pady=self._pad[1] // 2 + 1)
                button = ttk.Button(row, text=text) if text is not None else None
                if button is not None:
                    button.pack(side="right", padx=(4, self._pad[0]), pady=1)
                label.pack(side="left", fill="x", expand=True)
                self.rows.append(row)
                self.labels.append(label)
                self.row_buttons.append(button)
            self._signature = signature
        self._ground()
        for row, label, button, (_line, colours, action) in zip(self.rows, self.labels, self.row_buttons, rows):
            bg, fg = theme.strip_colours(colours)
            row.configure(bg=bg)
            label.configure(bg=bg, fg=fg)
            if button is not None and action is not None:
                button.configure(command=action[1])
        self.buttons = [b for b in self.row_buttons if b is not None]
        self.lines = lines
        self._wrap(force=True)

    def _wrap(self, force: bool = False) -> None:
        """Each line broken to the room its button leaves."""
        try:
            width = self.winfo_width()
            room = (width if width > 1 else 900) - 2 * self._pad[0] - 8
            buttons = [b.winfo_reqwidth() + 4 + self._pad[0] if b is not None else 0 for b in self.row_buttons]
        except tk.TclError:
            return
        if not force and room == self._width:
            return
        self._width = room
        for label, line, extra in zip(self.labels, self.lines, buttons):
            label.configure(text=break_lines(line, max(160, room - extra), label))
