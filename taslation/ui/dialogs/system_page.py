"""The System page of Tools > Settings... (`SystemPage`): what each stage of a page runs on (`devices.stage_devices`:
detection, OCR, the translator, the erase; "GPU (its name)" or "CPU"), what runs there, and the seconds a page took
there on the last pages lettered (`devices.StageTimes`: this session's, else those kept when the window last closed).
It looks when the page is first shown and on Look again, on a thread of its own (Ollama is asked /api/ps, which may
take a moment), so the dialog never waits.

The list is a grid of labels broken to their column's width (`caches.in_lines`), not a fixed-width table: a GPU's
name, a model's or a longer language's words then take another line instead of being cut off. Each stage has where it
runs and, under it in grey, what runs there.

Under it, the one setting of where things run that the dialog holds: how many of the translation model's layers
Ollama puts on the GPU (``ollama_num_gpu``: empty, the server decides; 0, the processor only; a number of layers), a
box with a line on what it does (`num_gpu`, read and checked by the dialog's Save: `NUM_GPU_PROBLEM`)."""

from __future__ import annotations

import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable

from ... import devices
from ...devices import STAGE_NAMES, StageTimes, seconds_text
from ...i18n import _
from ...translate.ollama import NUM_GPU_MOST, num_gpu_value
from .. import theme
from ..tooltip import tip
from .caches import in_lines

NUM_GPU_LABEL = "Translation model's layers on the GPU:"
NUM_GPU_TEXT = ("Empty: Ollama decides (the fastest). 0: the processor only, which leaves the GPU free and translates "
                "several times slower. A number: that many of the model's layers on the GPU, the rest on the processor.")
NUM_GPU_PROBLEM = "The layers on the GPU: leave the box empty, or a whole number from 0 to {most}."
POLL_MS = 100  # how often the page looks whether the thread is done
NOTE_COLOUR = theme.LIGHT["note"]  # the notes under the rows (light: `theme.colour("note")`)
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
        ttk.Label(self, textvariable=self.note_var, justify="left", foreground=theme.colour("note")).pack(anchor="w", pady=(8, 0))
        layers = ttk.Frame(self)
        layers.pack(fill="x", anchor="w", pady=(12, 0))
        name = ttk.Label(layers, text=_(NUM_GPU_LABEL))
        name.grid(row=0, column=0, sticky="w")
        self.num_gpu = tk.StringVar(self, value=str(getattr(settings, "ollama_num_gpu", "") or "").strip())
        box = ttk.Entry(layers, textvariable=self.num_gpu, width=6)
        box.grid(row=0, column=1, sticky="w", padx=(8, 0))
        line = ttk.Label(layers, text=in_lines(_(NUM_GPU_TEXT), width), justify="left", foreground=theme.colour("note"))
        line.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        tip(_(NUM_GPU_TEXT), name, box)
        self.looked = False

    # ------------------------------------------------------------------ the layers on the GPU
    def num_gpu_value(self) -> str:
        """What the layers' box says, as ``ollama_num_gpu`` keeps it: "" (empty: the server decides) or a whole number
        written plainly ("020" is "20"); what is neither, as it was typed (`num_gpu_problem` says so)."""
        text = self.num_gpu.get().strip()
        try:
            layers = num_gpu_value(text)
        except ValueError:
            return text
        return "" if layers is None else str(layers)

    def num_gpu_problem(self) -> str | None:
        """What is wrong with the layers' box (in the window's language), None when nothing is."""
        try:
            num_gpu_value(self.num_gpu_value())
        except ValueError:
            return _(NUM_GPU_PROBLEM).format(most=NUM_GPU_MOST)
        return None

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
        tally = getattr(self.pipeline(), "line_tally", None)  # (`linememo.Tally`: counts only)
        if tally is not None and tally.reused + tally.asked:
            note += "\n" + _("Short lines reused this session without asking the model: {reused} of {lines}.").format(
                reused=tally.reused, lines=tally.reused + tally.asked)
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
        ttk.Label(cell, text=in_lines(what, self.widths[1] - LABEL_PAD), justify="left", foreground=theme.colour("note")).pack(anchor="w")
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
