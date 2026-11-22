"""The Reader's status slot: in the Reader role the busy badge in the top right corner (`preview.ImageCanvas` with its
spinner and its seconds) is not shown - the bubbles filling in on the page are the progress -, and one small slot says
what the page cannot show itself, in fixed words, with no seconds and nothing turning:

* no bubble lettered 1 s after the look at a page (`LOOK_S`, from the start of its job or of the wait for the models):
  "Loading the model...", "Reading the page..." or "Translating...", by the job's stage; it goes with the first
  bubble lettered;
* the page could not be translated (its job failed, or the translator gave an error): "This page could not be
  translated. F5 tries again." with an orange "!" - while the viewer shows that page;
* the page has nothing to read: "Nothing to read on this page." for `NOTHING_S` seconds.

Nothing else is said there. In the window the slot is at the status line's left end (`SlotLabel`); on the full screen
at the bottom of the page's exit-side margin (`ImageCanvas.set_slot`). The Translator role keeps the badge as it was
(`badge_allowed`). The slot is looked at whenever the event pump runs (`tick`, from `StatusMixin._flush_busy`): no
timer of its own."""

from __future__ import annotations

import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from ..i18n import _
from .progress import LOADING, code_of

LOOK_S = 1.0  # no bubble lettered this long after the look: the slot says what the page waits for
NOTHING_S = 4.0  # "Nothing to read on this page" stays this long
WARN = "#e69f00"  # the "!" of a page that could not be translated (orange, Okabe-Ito), in a round mark

LOADING_KEY = "Loading the model..."
READING_KEY = "Reading the page..."
TRANSLATING_KEY = "Translating..."
ERROR_KEY = "This page could not be translated. F5 tries again."
NOTHING_KEY = "Nothing to read on this page."
KEYS = (LOADING_KEY, READING_KEY, TRANSLATING_KEY, ERROR_KEY, NOTHING_KEY)


def slot_text(key: str) -> str:
    """A slot's words in the window's language."""
    return {LOADING_KEY: _("Loading the model..."), READING_KEY: _("Reading the page..."),
            TRANSLATING_KEY: _("Translating..."), ERROR_KEY: _("This page could not be translated. F5 tries again."),
            NOTHING_KEY: _("Nothing to read on this page.")}[key]


@dataclass
class SlotState:
    """What the slot remembers between looks: the frame of a page whose job failed (and when), the page found to have
    nothing to read (and until when it is said), and what is shown now."""

    error_frame: Any = None
    error_at: float = 0.0
    nothing: Any = None  # the PageResult with nothing to read
    nothing_until: float = 0.0
    shown: Any = None  # (what is said, whether on the full screen) as shown last


def reader_role(window: Any) -> bool:
    role = getattr(window, "role_var", None)
    try:
        return role is None or role.get() != "translator"
    except tk.TclError:
        return True


def badge_allowed(window: Any) -> bool:
    """Whether the busy badge shows on the page area: in the Translator role."""
    return not reader_role(window)


def stage_key(window: Any) -> str:
    """What the page waits for, by the job's latest progress: the models (a request waiting for them, Ollama loading
    its model), the reading of the page (finding the bubbles, reading their text, nothing told yet), the translation."""
    progress = getattr(window, "_progress", "")
    code = code_of(progress)
    if (getattr(window, "_queued", None) is not None and not getattr(window, "ready", True)) or progress == LOADING \
            or code == "ollama.loading":
        return LOADING_KEY
    if not progress or code in ("pipeline.stage_finding", "pipeline.stage_reading"):
        return READING_KEY
    if not code and str(progress).startswith(("Finding bubbles", "Reading text", "Looking")):
        return READING_KEY
    return TRANSLATING_KEY


def job_on_show(window: Any) -> bool:
    """Whether the page a job works on is the one the viewer shows (or no frame tells otherwise)."""
    frame, live = getattr(window, "_job_frame", None), getattr(window, "_live", None)
    if frame is None or live is None:
        return True
    try:
        return bool(window._shows_page(live, frame))
    except Exception:  # noqa: BLE001 - not known: as on show
        return True


def wanted(window: Any, state: SlotState, now: float) -> tuple[str, bool] | None:
    """What the slot says now (its key, and whether it is the orange "!" one), or None."""
    if not reader_role(window):
        return None
    result = getattr(window, "last_result", None)
    if state.error_frame is not None:
        live = getattr(window, "_live", None)
        renewed = getattr(window, "busy", False) and getattr(window, "_busy_since", 0.0) > state.error_at
        try:
            same = live is None or bool(window._shows_page(live, state.error_frame))
        except Exception:  # noqa: BLE001
            same = False
        if same and not renewed:
            return ERROR_KEY, True
        state.error_frame = None
    try:
        on_show = result is not None and bool(window._result_on_show())
    except Exception:  # noqa: BLE001
        on_show = False
    if on_show and getattr(result, "error", ""):
        return ERROR_KEY, True
    if state.nothing is not None:
        if now < state.nothing_until and on_show and result is state.nothing:
            return NOTHING_KEY, False
        state.nothing = None
    if getattr(window, "_busy_shown", False):
        fill = getattr(window, "_fill", None)
        if (fill is None or fill.filled == 0) and now - getattr(window, "_busy_since", now) >= LOOK_S - 1e-6 \
                and job_on_show(window):
            return stage_key(window), False
    return None


def nothing_to_read(result: Any) -> bool:
    """Whether a finished page had nothing to read: text neither translated nor waiting, no error, a page captured."""
    from ..pipeline import summary

    try:
        code = summary(result).code
    except Exception:  # noqa: BLE001
        return False
    return code == "pipeline.no_text" and not any(r.status == "untranslated" for r in result.regions)


def tick(window: Any, now: float | None = None) -> None:
    """The slot as it is to be now, in the window's status bar and, on the full screen, on the page area; drawn again
    only when that changed."""
    side = getattr(window, "_side", None)
    if side is None:
        return
    state: SlotState = side.slot
    now = time.monotonic() if now is None else now
    want = wanted(window, state, now)
    key = (want, bool(getattr(window, "reading", False)))
    if key == state.shown:
        return
    state.shown = key
    show(window, want)


def show(window: Any, want: tuple[str, bool] | None) -> None:
    label = getattr(window._side, "slot_label", None)
    text = slot_text(want[0]) if want is not None else ""
    warn = bool(want and want[1])
    if label is not None:
        try:
            label.show(text, warn, getattr(window, "status_label", None))
        except tk.TclError:
            pass
    canvas = getattr(window, "canvas", None)
    if canvas is not None and hasattr(canvas, "set_slot"):
        canvas.set_slot(text if getattr(window, "reading", False) else "", warn)


def again(window: Any) -> None:
    """The slot said again (a language switch, the full screen in or out)."""
    side = getattr(window, "_side", None)
    if side is not None:
        side.slot.shown = None
        tick(window)


class SlotLabel(ttk.Frame):
    """The slot in the window's status bar, at its left end: an orange round "!" for a page that could not be
    translated, and the words; away while it has nothing to say."""

    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.mark = tk.Canvas(self, width=16, height=16, highlightthickness=0, borderwidth=0, takefocus=0)
        self.mark.create_oval(1, 1, 15, 15, fill=WARN, outline="#000000")
        family = tkfont.nametofont("TkDefaultFont").cget("family")
        self.mark.create_text(8, 8, text="!", fill="#000000", font=(family, 9, "bold"))
        self.var = tk.StringVar(value="")
        self.label = ttk.Label(self, textvariable=self.var, anchor="w")
        self.label.pack(side="right")

    def show(self, text: str, warn: bool, before: tk.Widget | None) -> None:
        if not text:
            if self.winfo_manager():
                self.pack_forget()
            return
        self.var.set(text)
        try:
            self.mark.configure(bg=str(ttk.Style(self).lookup("TFrame", "background") or "#f0f0f0"))
        except tk.TclError:
            pass
        if warn and not self.mark.winfo_manager():
            self.mark.pack(side="left", padx=(0, 4), before=self.label)
        elif not warn and self.mark.winfo_manager():
            self.mark.pack_forget()
        if not self.winfo_manager():
            if before is not None and before.winfo_manager():
                self.pack(side="left", padx=(0, 12), before=before)
            else:
                self.pack(side="left", padx=(0, 12))
