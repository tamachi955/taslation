"""The System page of Tools > Settings... (`SystemPage`): what each stage of a page runs on (`devices.stage_devices`:
detection, OCR, the translator, the erase; "GPU (its name)" or "CPU"), what runs there, and the seconds a page took
there on the last pages lettered (`devices.StageTimes`: this session's, else those kept when the window last closed).
It looks when the page is first shown and on Look again, on a thread of its own (Ollama is asked /api/ps, which may
take a moment), so the dialog never waits.

The list is a grid of labels broken to their column's width (`caches.in_lines`), not a fixed-width table: a GPU's
name, a model's or a longer language's words then take another line instead of being cut off. Each stage has where it
runs and, under it in grey, what runs there."""

from __future__ import annotations

import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable

from ... import devices
from ...devices import STAGE_NAMES, StageTimes, seconds_text
from ...i18n import _
from .caches import in_lines

POLL_MS = 100  # how often the page looks whether the thread is done
NOTE_COLOUR = "#6b6b6b"
SHARES = (0.27, 0.53, 0.20)  # of the page's width: the stage, where it runs (and with what), the seconds a page
GAP = 10  # pixels between the columns
LABEL_PAD = 4  # pixels a label takes round its text: the text is broken this much short of its column
SECONDS_AT_MOST = 0.32  # of the page's width: the seconds' column widened up to this for its heading on one line


def column_widths(width: int, seconds_heading: int) -> list[int]:
    """The three columns' widths in *width* pixels (`SHARES`); the seconds' column wide enough for its heading of
    *seconds_heading* pixels on one line where that takes at most `SECONDS_AT_MOST` of the page, the middle one giving
    the room."""
    widths = [max(40, int(width * share) - GAP) for share in SHARES]
    wanted = min(seconds_heading + LABEL_PAD, int(width * SECONDS_AT_MOST))
    if wanted > widths[2]:
        widths[1] = max(40, widths[1] - (wanted - widths[2]))
        widths[2] = wanted
    return widths


class SystemPage(ttk.Frame):
    """Where the stages run for *settings*. *pipeline* gives the window's pipeline (None before it has one): its
    translator is the one asked where its model is, and its `StageTimes` give the seconds a page (none yet: those kept
    in the state folder). *look* is what finds the devices (`devices.stage_devices`; the tests give their own); the
    page is laid out in *width* pixels."""

    def __init__(self, master: tk.Misc, settings: Any, width: int, pipeline: Callable[[], Any] | None = None,
                 look: Callable[[], list[devices.StageDevice]] | None = None):
        super().__init__(master, padding=8)
        self.settings = settings
        self.pipeline = pipeline or (lambda: None)
        self.look = look or (lambda: devices.stage_devices(settings, getattr(self.pipeline(), "translator", None)))
        self.width = width
        self.bold = tkfont.nametofont("TkDefaultFont").copy()  # the headings' face, kept while the page lives
        self.bold.configure(weight="bold")
        self.widths = column_widths(width, self.bold.measure(_("Seconds a page")))
        self.rows: list[devices.StageDevice] = []
        self.shown_rows: list[tuple[str, str, str, str]] = []  # (stage, where, what, seconds) as the page shows them
        self._result: list[Any] = []
        self._thread: threading.Thread | None = None
        self.table = ttk.Frame(self)
        self.table.pack(fill="x", anchor="w")
        for column, minimum in enumerate(self.widths):
            self.table.columnconfigure(column, minsize=minimum)
        self._cells: list[tk.Widget] = []
        for column, word in enumerate((_("Stage"), _("Runs on"), _("Seconds a page"))):
            ttk.Label(self.table, text=in_lines(word, self.widths[column] - LABEL_PAD, self.bold.name), font=self.bold,
                      justify="left").grid(row=0, column=column, sticky="nw", padx=(0, GAP if column < 2 else 0),
                                           pady=(0, 4))
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(8, 0))
        self.again_btn = ttk.Button(row, text=_("Look again"), command=self.refresh)
        self.again_btn.pack(side="left")
        self.state_var = tk.StringVar(self, value="")
        ttk.Label(row, textvariable=self.state_var).pack(side="left", padx=(8, 0))
        self.note_var = tk.StringVar(self, value="")
        ttk.Label(self, textvariable=self.note_var, justify="left", foreground=NOTE_COLOUR).pack(anchor="w", pady=(8, 0))
        self.looked = False

    # ------------------------------------------------------------------ looking
    def refresh(self, wait: bool = False) -> None:
        """Look again (on a thread; *wait*: here, at once - the tests)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self.looked = True
        self.state_var.set(_("Looking..."))
        self.again_btn.configure(state="disabled")
        if wait:
            self._found(self._find())
            return
        self._result = []
        self._thread = threading.Thread(target=lambda: self._result.append(self._find()), daemon=True)
        self._thread.start()
        self.after(POLL_MS, self._poll)

    def _find(self) -> list[devices.StageDevice] | Exception:
        try:
            return self.look()
        except Exception as e:  # noqa: BLE001 - said on the page, never raised into Tk
            return e

    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        if not self._result:
            self.after(POLL_MS, self._poll)
            return
        self._found(self._result.pop())

    def _found(self, rows: list[devices.StageDevice] | Exception) -> None:
        self.again_btn.configure(state="normal")
        self.state_var.set("")
        for cell in self._cells:
            cell.destroy()
        self._cells = []
        self.shown_rows = []
        if isinstance(rows, Exception):
            self.rows = []
            self.state_var.set(_("Could not look: {error}").format(error=type(rows).__name__))
            return
        self.rows = rows
        times = self._times()
        seconds = times.per_page()
        for n, r in enumerate(rows, start=1):
            shown = (_(STAGE_NAMES[r.stage]), r.where(), r.what, seconds_text(seconds.get(r.stage)))
            self.shown_rows.append(shown)
            self._row(n, shown)
        note = (_("Seconds a page: the mean of the last {count} pages lettered.").format(count=len(times)) if len(times)
                else _("Seconds a page: none yet. They show once pages have been translated, and are kept when the window closes."))
        note += " " + _("Only an NVIDIA GPU with CUDA counts here; nothing is loaded to find out.")
        self.note_var.set(in_lines(note, self.width))

    def _row(self, n: int, shown: tuple[str, str, str, str]) -> None:
        """A stage's row: its name, where it runs with what runs there under it in grey, and its seconds a page."""
        stage, where, what, secs = shown
        pad = (6, 0) if n > 1 else (0, 0)
        name = ttk.Label(self.table, text=in_lines(stage, self.widths[0] - LABEL_PAD), justify="left")
        name.grid(row=n, column=0, sticky="nw", padx=(0, GAP), pady=pad)
        cell = ttk.Frame(self.table)
        cell.grid(row=n, column=1, sticky="nw", padx=(0, GAP), pady=pad)
        ttk.Label(cell, text=in_lines(where, self.widths[1] - LABEL_PAD), justify="left").pack(anchor="w")
        ttk.Label(cell, text=in_lines(what, self.widths[1] - LABEL_PAD), justify="left", foreground=NOTE_COLOUR).pack(anchor="w")
        took = ttk.Label(self.table, text=secs, justify="left")
        took.grid(row=n, column=2, sticky="nw", pady=pad)
        self._cells += [name, cell, took]

    def _times(self) -> StageTimes:
        live = getattr(self.pipeline(), "stage_times", None)
        return live if live is not None and len(live) else StageTimes.load(self.settings.state_dir)

    def shown(self) -> None:
        """The page came to the front: it looks the first time."""
        if not self.looked:
            self.refresh()
