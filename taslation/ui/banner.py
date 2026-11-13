"""The strips across the top of the page area, between the toolbar and the page (`Strip`):

* the setup banner (`SetupBanner`): what stands in the way of translating new pages - the Messages of
  `taslation.health.check` (Ollama not running, the model or the OCR model missing) - one line each, in the
  window's language, until it is fixed; ``NOTICE_CODES`` are notices (translating works);
* the scan band: while a whole-book scan runs, which page is read (and, once a page with text is read, about how
  long reading a page takes), then how many lines are translated - line by line where the translator hands each
  over -, with a bar (`band_fraction`) and about how long it takes yet once that can be trusted (`ScanState.left`:
  the rate since the first line was done, which leaves the model's loading out, started from the rate of the last
  run with the model, `ScanState.seed`, when there is one; a long translation also says when it will be done), with
  Stop (`ScanState`, `band_text`); then how the scan ended, with the button to close it.

Also how the band writes its numbers in each window language (`group_digits`, `duration_text`) and the text broken
into lines by hand (`break_lines`: Tk itself breaks lines only at spaces)."""

from __future__ import annotations

import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Callable, Iterable, Sequence

from ..i18n import _, current
from .progress import code_of, rendered
from .wrap import wrap_text

# setup lines that only inform (translating works); translator.other_model: Qwen translates while PLaMo is not installed
NOTICE_CODES = frozenset({"health.other_model", "health.chosen_other_model", "translator.other_model"})
PROBLEM_COLOURS = ("#fff4ce", "#1f1f1f")  # a setup problem: dark text on amber
NOTICE_COLOURS = ("#e5f1fb", "#1f1f1f")  # a notice: dark text on pale blue
BAND_COLOURS = ("#1f3b63", "#ffffff")  # the scan band: white on dark blue, unlike anything the viewer shows
# how each window language groups the digits of a number ("1,900", "1.900", "1 900"); four digits stay whole in
# Spanish and Polish, as their style guides have it
_DIGIT_GROUPS = {"de": ".", "es": ".", "pt": ".", "it": ".", "nl": ".", "id": ".", "vi": ".", "tr": ".",
                 "fr": " ", "ru": " ", "pl": " "}
_FIVE_DIGITS = frozenset({"es", "pl"})
# the estimate of the time left: the rate measured since the first line was done, trusted from TRUST_LINES lines over
# TRUST_S seconds; a rate seeded from the last run (`ScanState.seed`) counts as PRIOR_S seconds of measuring, so the
# lines of this run take over within a minute or so
TRUST_LINES = 8
TRUST_S = 15.0
PRIOR_S = 15.0
CLOCK_FROM_S = 600.0  # a translation with this long left also says at what time it will be done
BAR_STEPS = 1000  # the band's bar


def is_notice(message: Any) -> bool:
    """Whether a setup line only informs (translating works all the same)."""
    return code_of(message) in NOTICE_CODES


def blocking(problems: Iterable[Any]) -> list[Any]:
    """The setup problems that stop a whole-book scan: all but the notices."""
    return [m for m in problems if not is_notice(m)]


def group_digits(n: int, lang: str | None = None) -> str:
    """*n* with its digits grouped as the window language *lang* (by default the window's) writes them."""
    lang = lang or current()
    value = int(n)
    if abs(value) < (10_000 if lang in _FIVE_DIGITS else 1000):
        return str(value)
    return f"{value:,}".replace(",", _DIGIT_GROUPS.get(lang, ","))


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


@dataclass
class ScanState:
    """What the scan band knows of a running scan: how it runs (*context*: the whole book, every page read first, then
    the translation; else each page translated as it is read), what the batch said last, what it waits
    for from the reader (*waiting*), how many pages wait to be read (*queued*), whether the reader has finished the book
    (*finishing*), how long reading a page takes (*page_seconds*), and in the translation (phase "translate") the lines
    done (*done*: stored, *checked*, and answered by the request under way, *answering*; never fewer than shown
    before) and the time left (*left*) once the rate can be trusted."""

    context: bool = True
    message: Any = ""
    waiting: Any = None
    queued: int = 0
    finishing: bool = False
    phase: str = ""
    pages: int = 0
    translated: int = 0
    found: int = 0
    checked: int = 0  # the lines the translation pass has stored
    answering: int = 0  # the lines the request under way has answered, not stored yet
    done: int = 0  # the lines shown done
    seed: float | None = None  # lines a second of the last run with the model: the rate before this run has its own
    started: float | None = None  # when the first line of the translation was done (time.monotonic) ...
    done_then: int = 0  # ... and how many lines were done then
    left: float | None = None  # seconds left (None while the rate cannot be trusted)
    page_seconds: float = 0.0  # how long reading a page with text takes (0: none read yet)

    def update(self, message: Any, phase: str, pages: int, translated: int, found: int, now: float,
               checked: int = 0, waiting: Any = None, queued: int = 0, answering: int = 0,
               page_seconds: float = 0.0) -> None:
        """What the batch said (its latest message and counts, at *now*); the estimate from the rate so far."""
        self.message, self.phase = message, phase
        self.waiting, self.queued = waiting, int(queued)
        self.pages, self.translated, self.found = int(pages), int(translated), int(found)
        self.checked, self.answering = int(checked), int(answering)
        self.page_seconds = float(page_seconds or 0.0) or self.page_seconds
        if not self.context or phase != "translate":
            return
        self.done = max(self.done, min(self.total, self.checked + self.answering))
        if self.started is None:
            if self.done > 0:  # the first line done: the model is loaded, the rate is measured from here
                self.started, self.done_then = now, self.done
            self.left = self._left(0, 0.0)
            return
        self.left = self._left(self.done - self.done_then, max(0.0, now - self.started))

    @property
    def total(self) -> int:
        """The lines the translation pass has to do."""
        return max(self.found, self.checked)

    def _left(self, lines: int, seconds: float) -> float | None:
        """Seconds left at the rate of *lines* done in *seconds*, started from the seed; None while there is no rate
        to trust (no seed, and fewer than `TRUST_LINES` lines or `TRUST_S` seconds)."""
        if self.seed:
            rate = (self.seed * PRIOR_S + lines) / (PRIOR_S + seconds)
        elif lines >= TRUST_LINES and seconds >= TRUST_S:
            rate = lines / seconds
        else:
            return None
        return max(0.0, self.total - self.done) / rate if rate > 0 else None

    def measured(self, now: float) -> float | None:
        """This run's own rate (lines a second since the first line was done), once it can be trusted: what the next
        run with the model starts from (`seed`). None before."""
        if self.started is None:
            return None
        lines, seconds = self.done - self.done_then, now - self.started
        return lines / seconds if lines >= TRUST_LINES and seconds >= TRUST_S else None

    @property
    def scanning(self) -> bool:
        """Whether the pages the reader turns are being read: the whole scan in page-by-page mode."""
        return not self.context or (self.phase in ("", "read")
                                    and code_of(self.message) not in ("batch.pages_read", "batch.continuing"))


def band_text(scan: ScanState, clock: float | None = None) -> str:
    """The scan band's line in the window's language: what the run waits for from the reader (it stays until that is
    over, whatever is said meanwhile); else while the pages are read, how many are read and wait, how long reading a
    page takes, and that the reader says when the book is done; then the lines translated and the time left: less
    than a minute, minutes, or with a long way to go also the time of day it will be done (*clock*: now, as
    time.time, by default the time now)."""
    if scan.waiting:
        return rendered(scan.waiting)
    if scan.scanning:
        queued = group_digits(scan.queued)
        if scan.finishing:
            return _("Finished reading. Pages still to read: {queued}. The translation comes next.").format(queued=queued)
        if not scan.context:
            return _("Translating the pages you turn. Done: {pages}. Waiting: {queued}. Turn at your own pace, in the viewer or with the page keys here; press Finished reading at the end.").format(
                pages=group_digits(scan.pages), queued=queued)
        if scan.page_seconds > 0:
            return _("Reading the pages you turn. Read: {pages}. Waiting: {queued}. Reading a page takes about {seconds} s. Turn at your own pace, in the viewer or with the page keys here; press Finished reading at the end.").format(
                pages=group_digits(scan.pages), queued=queued, seconds=max(1, int(round(scan.page_seconds))))
        return _("Reading the pages you turn. Read: {pages}. Waiting: {queued}. Turn at your own pace, in the viewer or with the page keys here; press Finished reading at the end.").format(
            pages=group_digits(scan.pages), queued=queued)
    if scan.phase != "translate":
        return _("All pages are read. The translation starts now. The viewer is not used during this step.")
    done, total = group_digits(scan.done), group_digits(scan.total)
    if scan.left is None:
        return _("Translating: {done} of {total} lines. The viewer is not used during this step.").format(done=done, total=total)
    if scan.left < 60:
        return _("Translating: {done} of {total} lines, less than a minute left. The viewer is not used during this step.").format(
            done=done, total=total)
    if scan.left >= CLOCK_FROM_S:
        at = time.strftime("%H:%M", time.localtime((time.time() if clock is None else clock) + scan.left))
        return _("Translating: {done} of {total} lines, about {time} left (done at about {clock}). The viewer is not used during this step.").format(
            done=done, total=total, time=duration_text(scan.left), clock=at)
    return _("Translating: {done} of {total} lines, about {time} left. The viewer is not used during this step.").format(
        done=done, total=total, time=duration_text(scan.left))


def band_fraction(scan: Any) -> float | None:
    """How far a whole-book run's translation is, 0 to 1, for the bar of the band and of the taskbar button; None
    while there is nothing to measure (the reading, a page-by-page run, no line to translate)."""
    if scan is None or not scan.context or scan.phase != "translate" or scan.scanning or scan.total <= 0:
        return None
    return min(1.0, scan.done / scan.total)


def busy_title(scan: Any) -> str:
    """The window's title while a job runs, by what is done: a whole-book run's reading pass (*scan*: its
    `ScanState`) reads the pages - nothing is translated yet -, then the lines translated; any other job translates."""
    if scan is not None and scan.context and scan.phase in ("", "read"):
        return _("TASlation - reading...")
    return _("TASlation - translating...")


class Strip(tk.Frame):
    """A strip across the page area: lines of text at its left, broken to fit its width, and buttons at its right.
    `set` changes what it shows; the window packs it and takes it away."""

    def __init__(self, master: tk.Misc, colours: tuple[str, str], pad: tuple[int, int] = (10, 5)):
        super().__init__(master, bg=colours[0], bd=0, highlightthickness=0)
        self.colours = colours
        self.lines: list[str] = []  # the lines as they were given (unbroken)
        self.labels: list[tk.Label] = []  # one per line, as wide as the strip (its colours to the edges)
        self.buttons: list[ttk.Button] = []
        self.bar: ttk.Progressbar | None = None  # a determinate bar under the lines (`show_fraction`), made when asked
        self._pad = pad
        self.text_box = tk.Frame(self, bg=colours[0], bd=0, highlightthickness=0)
        self.button_box = tk.Frame(self, bg=colours[0], bd=0, highlightthickness=0)  # packed while it has buttons
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
            if self.bar is not None and self.bar.winfo_manager():
                label.pack(fill="x", anchor="w", before=self.bar)
            else:
                label.pack(fill="x", anchor="w")
            self.labels.append(label)
        for i, label in enumerate(self.labels):
            bg, fg = (colours[i] if colours and i < len(colours) else self.colours)
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

    def show_fraction(self, fraction: float | None) -> None:
        """A determinate bar under the lines at *fraction* (0 to 1); None takes it away."""
        if fraction is None:
            if self.bar is not None and self.bar.winfo_manager():
                self.bar.pack_forget()
            return
        if self.bar is None:
            self.bar = ttk.Progressbar(self.text_box, mode="determinate", maximum=BAR_STEPS)
        self.bar["value"] = round(max(0.0, min(1.0, float(fraction))) * BAR_STEPS)
        if not self.bar.winfo_manager():
            self.bar.pack(fill="x", padx=self._pad[0], pady=(1, self._pad[1]))

    def fraction(self) -> float | None:
        """The bar's fraction, None while it is away."""
        if self.bar is None or not self.bar.winfo_manager():
            return None
        return float(self.bar["value"]) / BAR_STEPS

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
        for row, label, button, (_line, (bg, fg), action) in zip(self.rows, self.labels, self.row_buttons, rows):
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
