"""The start's dialog when the GPU's memory is short for everything TASlation puts there (`taslation.ocr.place`: the
one judgement of the session, `ui.jobs.JobsMixin._judge_gpu`, made after the legal notice, before anything loads).

TASlation's own box, as `caches.WarningBox` (its warning icon, its lines broken at `caches.WARNING_CHARS`, centred over
the window, in front and modal), with three ways out: Check again (the person closed something: the start judges
anew), Start on the processor (what does not fit runs there for the session, the parts it names - least loss first:
`place.TO_PROCESSOR`) and Quit (the window closes; closing the box or Escape is Quit too); and a box to tick, Do not ask
again on this computer (``gpu_short`` "processor": the next starts take that way without asking; Tools > Settings... >
System changes it back). Check again has the focus. Nothing is sent anywhere: the figures are the card's own (NVML)
and Ollama's on this computer.

The dialog never appears without an NVIDIA GPU (nothing is judged), in a command or a tool (they cannot ask: they
take the processor's way, `place.plan_for`), or with ``gpu_short`` "processor"; the test suite's windows run without a
GPU or with stand-ins, which the judgement never finds short."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable, Sequence

from ...devices import parts_text, short_mb
from ...i18n import _
from ..layout import place_window
from .caches import ICONS, WARNING_CHARS, in_lines

# the 16 languages: `locales/features/gpu_start.py`
TEXT = ("The GPU's memory is short by {mb} MB. Close other applications that use it and check again, or start with "
        "part of the work on the processor (slower).")
ON_PROCESSOR = "On the processor: {parts}."
AGAIN, PROCESSOR, QUIT = "Check again", "Start on the processor", "Quit"
REMEMBER = "Do not ask again on this computer"


class GpuShortDialog(tk.Toplevel):
    """The dialog over *master* for the GPU's memory short by *short* MiB, *parts* what Start on the processor sends
    there; *on_answer*(choice, remember) once: "again", "processor" or "quit", and whether Do not ask again on this
    computer was ticked (only with "processor")."""

    def __init__(self, master: tk.Misc, short: int, parts: Sequence[str],
                 on_answer: Callable[[str, bool], None]):
        super().__init__(master)
        self.title("TASlation")
        self.transient(master)
        self.resizable(False, False)
        self.on_answer = on_answer
        self.answered = ""
        self.shown_mb, self.parts = short_mb(short), tuple(parts)  # (what it says: the MB, the parts it names)
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        image, bitmap = ICONS["warning"]
        try:
            icon: tk.Widget = ttk.Label(frm, image=image)
        except tk.TclError:  # a Tk without its stock icons: its built-in bitmap
            icon = tk.Label(frm, bitmap=bitmap)
        icon.grid(row=0, column=0, sticky="n", padx=(0, 12))
        width = WARNING_CHARS * max(1, tkfont.nametofont("TkDefaultFont").measure("0"))
        self.message_text = _(TEXT).format(mb=self.shown_mb)
        if parts:
            self.message_text += "\n\n" + _(ON_PROCESSOR).format(parts=parts_text(parts))
        ttk.Label(frm, text=in_lines(self.message_text, width), justify="left").grid(row=0, column=1, sticky="nw")
        self.remember = tk.BooleanVar(self, value=False)
        ttk.Checkbutton(frm, text=_(REMEMBER), variable=self.remember).grid(row=1, column=1, sticky="w", pady=(10, 0))
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(14, 0))
        self.again_btn = ttk.Button(btns, text=_(AGAIN), default="active", command=lambda: self.choose("again"))
        self.processor_btn = ttk.Button(btns, text=_(PROCESSOR), command=lambda: self.choose("processor"))
        self.quit_btn = ttk.Button(btns, text=_(QUIT), command=lambda: self.choose("quit"))
        for i, button in enumerate((self.again_btn, self.processor_btn, self.quit_btn)):
            button.pack(side="left", padx=(6 if i else 0, 0))
        self.bind("<Return>", self._on_return)
        self.bind("<Escape>", self._on_escape)
        self.protocol("WM_DELETE_WINDOW", lambda: self.choose("quit"))
        self.bind("<Destroy>", self._gone, add="+")
        self.again_btn.focus_set()
        place_window(self, master)
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.grab_set()
        except tk.TclError:  # not on the screen (yet): no grab
            pass

    def choose(self, choice: str) -> None:
        """The answer *choice* ("again", "processor", "quit"): told once, and the box closes."""
        if self.answered:
            return
        self.answered = choice
        remember = choice == "processor" and bool(self.remember.get())
        try:
            self.destroy()
        finally:
            self.on_answer(choice, remember)

    def _on_return(self, _event: tk.Event | None = None) -> None:
        """Return presses the button that has the focus, Check again unless the person moved it."""
        try:
            focused = self.focus_get()
        except (KeyError, tk.TclError):
            focused = None
        buttons = (self.again_btn, self.processor_btn, self.quit_btn)
        (focused if focused in buttons else self.again_btn).invoke()

    def _on_escape(self, _event: tk.Event | None = None) -> None:
        """Escape is Quit."""
        self.choose("quit")

    def _gone(self, event: tk.Event) -> None:
        """The box destroyed without an answer (the window closed under it): Quit."""
        if event.widget is self and not self.answered:
            self.answered = "quit"
            self.on_answer("quit", False)
