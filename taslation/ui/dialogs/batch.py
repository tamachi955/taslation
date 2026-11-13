"""Batch: read the whole book - the dialog with a batch's options."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from ...capture import WindowInfo
from ...config import Settings
from ...i18n import _
from ..banner import break_lines
from ..layout import place_window
from .help import explain_button
from .start import terms_note

TERMS_WRAP = 560  # pixels: the note on a store's terms is broken into lines this wide (about the text's own lines)


class BatchDialog(tk.Toplevel):
    """Batch: read the whole book - the options of a batch over the viewer window *win*, from *settings*. Start
    closes the dialog and hands them to *on_start* as (win, max_pages, context_mode): the reader turns the pages, at
    most `batch_max_pages` of them, and they are read first, then translated all at once when the reader says the book
    is done; the command line has the other way (`--no-context`). Above Start, what a store's terms make of whole-book mode
    (`start.terms_note`). What such a run does is behind the "?"; what to do before Start stays in view, and
    *carried_on*, a line of the window's language, takes its place when Start goes on from what an earlier run left."""

    def __init__(self, master: tk.Misc, win: WindowInfo, settings: Settings,
                 on_start: Callable[[tuple[Any, ...]], None], carried_on: str = ""):
        super().__init__(master)
        self.title(_("Read the whole book"))
        self.transient(master)
        self.resizable(False, False)
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        head = ttk.Frame(frm)
        head.pack(fill="x")
        explain_button(head, _("Turn the pages at your own pace, in the viewer or with the page keys in TASlation's window.\nTASlation never turns a page by itself: it reads each page you turn, with no translation yet.\nWhen you reach the end, press Finished reading. Then TASlation translates the whole book at once,\nwith the whole story and your series sheet; the viewer is not needed from then on, and the pages\ncan be read when it is done. Only translated text and bubble positions are written to disk.")).pack(
            side="right", padx=(12, 0))
        label = ttk.Label(head, justify="left")
        label.configure(text=break_lines(_("Viewer: {title}").format(title=win.title), TERMS_WRAP - 60, label))
        label.pack(side="left", anchor="w")
        label = ttk.Label(frm, justify="left")
        label.configure(text=break_lines(_("The pages are read first, then translated all at once: the pages can be read only when that is done."), TERMS_WRAP, label))
        label.pack(anchor="w", pady=(10, 0))
        label = ttk.Label(frm, justify="left")  # what an earlier run left goes on, else from the book's first page
        label.configure(text=break_lines(carried_on or _("Open the book at the first page you want translated, then press Start and turn the pages."), TERMS_WRAP, label))
        label.pack(anchor="w", pady=(10, 0))
        # what TASlation does to the viewer's window: enlarged once as it is chosen (`ViewersMixin._enlarge_first`),
        # its size given back at the close; the run neither moves nor resizes it, Start shows a minimised one again
        self.size_line = ttk.Label(frm, justify="left")
        self.size_line.configure(text=break_lines(_("A larger viewer window reads better. When a viewer is chosen, TASlation makes its window as large as the screen once (a maximised one stays as it is), and gives it its size back when TASlation closes or another viewer is chosen. The run itself neither moves nor resizes it; Start shows it again if it is minimised."), TERMS_WRAP, self.size_line))
        self.size_line.pack(anchor="w", pady=(10, 0))
        self.terms_label = ttk.Label(frm, justify="left")  # what a store's terms make of this mode, above Start
        self.terms_label.configure(text=break_lines(terms_note(), TERMS_WRAP, self.terms_label))
        self.terms_label.pack(anchor="w", pady=(12, 0))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(10, 0))

        def start() -> None:
            self.destroy()
            on_start((win, settings.batch_max_pages, settings.context_mode))

        ttk.Button(btns, text=_("Start"), command=start).pack(side="right")
        ttk.Button(btns, text=_("Cancel"), command=self.destroy).pack(side="right", padx=(0, 6))
        place_window(self, master)
