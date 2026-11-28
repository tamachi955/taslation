"""The System page of Settings... (`SystemPage`): what each stage of a page runs on (`devices.stage_devices`:
detection, OCR, the translator, the erase; "GPU (its name)" or "CPU") and the models that run there, by their public
names (`devices.StageDevice.models`, with a short note in grey where there is something to say: why the OCR readers
are where they are, that the translation model is not loaded now). It looks when the page is first shown and on Look
again, on a thread of its own (Ollama is asked /api/ps, which may take a moment), so the dialog never waits. Under
the list, a note: only an NVIDIA GPU with CUDA counts, and what the judgement at the start found short and sent to
the processor (`devices.plan_text`).

The list is a grid of labels broken to their column's width (`caches.in_lines`), not a fixed-width table: a GPU's
name, a model's or a longer language's words then take another line instead of being cut off.

Under it, two settings: what a start short of GPU memory does (``gpu_short``, a checkbox with its line: `gpu_short`,
from the next start; the start's dialog's Do not ask again on this computer ticks it), and whether the window looks
for a new version when it starts (``update_check``, "daily" or "off": `ui.updates`), a checkbox with its line on what
is asked of whom (`update_check`, from the next start). The other settings of where the work runs
(``ollama_num_gpu``, ``load_model_at_start``, ``ocr_runs_on``, ``ollama_window_cache``) are in taslation.toml
alone."""

from __future__ import annotations

import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable

from ... import devices
from ...devices import STAGE_NAMES
from ...i18n import _
from .. import theme
from ..tooltip import tip
from .caches import in_lines

# what a start that is short of GPU memory does (``gpu_short``, `taslation.ocr.place`, `ui.dialogs.gpu_short`); the
# 16 languages: `locales/features/gpu_start.py`
GPU_SHORT_LABEL = ("When the GPU's memory is short at the start, start with part of the work on the processor "
                   "without asking")
GPU_SHORT_TEXT = ("Off: a box at the start asks. On: what does not fit runs on the processor, as the note under the "
                  "list says. From the next start.")
# whether the window looks for a new version at its start (``update_check``, `taslation.ui.updates`); the 16
# languages: `locales/features/updates.py`
UPDATE_CHECK_LABEL = "Look for a new version once a day when TASlation starts"
UPDATE_CHECK_TEXT = ("On: TASlation asks GitHub for one small file, at most once a day. Nothing about you or your "
                     "books is sent; GitHub sees your IP address. A newer version is named in Menu > Help. From the "
                     "next start.")
POLL_MS = 100  # how often the page looks whether the thread is done
NOTE_COLOUR = theme.LIGHT["note"]  # the notes under the rows (light: `theme.colour("note")`)
SHARES = (0.25, 0.33, 0.42)  # of the page's width: the stage, where it runs, the models
GAP = 10  # pixels between the columns
LABEL_PAD = 4  # pixels a label takes round its text: the text is broken this much short of its column


def column_widths(width: int) -> list[int]:
    """The three columns' widths in *width* pixels (`SHARES`), a gap after each."""
    return [max(40, int(width * share) - GAP) for share in SHARES]


class SystemPage(ttk.Frame):
    """Where the stages run for *settings*. *pipeline* gives the window's pipeline (None before it has one): its
    translator is the one asked where its model is, and its OCR readers say where they read (`devices.ocr_device`).
    *look* is what finds the devices (`devices.stage_devices`; the tests give their own); the page is laid out in
    *width* pixels."""

    def __init__(self, master: tk.Misc, settings: Any, width: int, pipeline: Callable[[], Any] | None = None,
                 look: Callable[[], list[devices.StageDevice]] | None = None):
        super().__init__(master, padding=8)
        self.settings = settings
        self.pipeline = pipeline or (lambda: None)
        self.look = look or (lambda: devices.stage_devices(settings, getattr(self.pipeline(), "translator", None),
                                                           ocr=getattr(self.pipeline(), "ocr", None)))
        self.width = width
        self.bold = tkfont.nametofont("TkDefaultFont").copy()  # the headings' face, kept while the page lives
        self.bold.configure(weight="bold")
        self.widths = column_widths(width)
        self.rows: list[devices.StageDevice] = []
        self.shown_rows: list[tuple[str, str, str, str]] = []  # (stage, where, models a line each, note) as shown
        self._result: list[Any] = []
        self._thread: threading.Thread | None = None
        self.table = ttk.Frame(self)
        self.table.pack(fill="x", anchor="w")
        for column, minimum in enumerate(self.widths):
            self.table.columnconfigure(column, minsize=minimum)
        self._cells: list[tk.Widget] = []
        for column, word in enumerate((_("Stage"), _("Runs on"), _("Model"))):
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
        ttk.Label(self, textvariable=self.note_var, justify="left", foreground=theme.colour("note")).pack(
            anchor="w", pady=(8, 0))
        below = ttk.Frame(self)
        below.pack(fill="x", anchor="w", pady=(12, 0))
        self.gpu_short = tk.BooleanVar(self, value=str(getattr(settings, "gpu_short", "ask")) == "processor")
        self.update_check = tk.BooleanVar(self, value=str(getattr(settings, "update_check", "off")) == "daily")
        for n, (label, text, var) in enumerate(((GPU_SHORT_LABEL, GPU_SHORT_TEXT, self.gpu_short),
                                                (UPDATE_CHECK_LABEL, UPDATE_CHECK_TEXT, self.update_check))):
            check = ttk.Checkbutton(below, text=in_lines(_(label), width), variable=var)
            check.grid(row=2 * n, column=0, sticky="w", pady=(10 if n else 0, 0))
            line = ttk.Label(below, text=in_lines(_(text), width), justify="left", foreground=theme.colour("note"))
            line.grid(row=2 * n + 1, column=0, sticky="w", pady=(2, 0))
            tip(_(text), check)
        self.looked = False

    def gpu_short_value(self) -> str:
        """What the box says, as ``gpu_short`` keeps it ("processor" or "ask")."""
        return "processor" if self.gpu_short.get() else "ask"

    def update_check_value(self) -> str:
        """What the checkbox says, as ``update_check`` keeps it ("daily" or "off")."""
        return "daily" if self.update_check.get() else "off"

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
        for n, r in enumerate(rows, start=1):
            shown = (_(STAGE_NAMES[r.stage]), r.where(), "\n".join(r.models), r.note)
            self.shown_rows.append(shown)
            self._row(n, shown)
        note = _("Only an NVIDIA GPU with CUDA counts here; nothing is loaded to find out.")
        planned = devices.plan_text()  # (the judgement at the start: short, and what went to the processor)
        if planned:
            note += "\n" + planned
        self.note_var.set(in_lines(note, self.width))

    def _row(self, n: int, shown: tuple[str, str, str, str]) -> None:
        """A stage's row: its name, where it runs, and the models that run there, a line each, with the note under them
        in grey."""
        stage, where, models, note = shown
        pad = (6, 0) if n > 1 else (0, 0)
        name = ttk.Label(self.table, text=in_lines(stage, self.widths[0] - LABEL_PAD), justify="left")
        name.grid(row=n, column=0, sticky="nw", padx=(0, GAP), pady=pad)
        runs = ttk.Label(self.table, text=in_lines(where, self.widths[1] - LABEL_PAD), justify="left")
        runs.grid(row=n, column=1, sticky="nw", padx=(0, GAP), pady=pad)
        cell = ttk.Frame(self.table)
        cell.grid(row=n, column=2, sticky="nw", pady=pad)
        if models:
            ttk.Label(cell, text=in_lines(models, self.widths[2] - LABEL_PAD), justify="left").pack(anchor="w")
        if note:
            ttk.Label(cell, text=in_lines(note, self.widths[2] - LABEL_PAD), justify="left",
                      foreground=theme.colour("note")).pack(anchor="w")
        self._cells += [name, runs, cell]

    def shown(self) -> None:
        """The page came to the front: it looks the first time."""
        if not self.looked:
            self.refresh()
