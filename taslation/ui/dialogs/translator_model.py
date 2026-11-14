"""The two dialogs of a translator model's install (`ui.model_switch`): PLaMo's licence, agreed to with a tick and a
button of its own before anything is downloaded (`LicenceDialog`), and the install itself with how far it is and
Cancel (`InstallDialog`). Both are TASlation's own, in the window's language, modal over the window and above
everything, a full-screen viewer too (as `caches.ask` and `tell`)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable

from ... import translator_install as tinstall
from ...i18n import _
from ..layout import place_window
from .caches import WARNING_CHARS, in_lines

POLL_MS = 100  # how often the install dialog looks at what the install said
URL_CHARS = 64  # the licence's addresses: read-only lines this wide
LICENCE_TEXT = (  # what the person agrees to, in plain words (a key of the window's catalogs)
    "TASlation translates with PLaMo 3 Translate 2B by Preferred Networks (PFN). Its licence is the PLaMo Community License, as revised on November 9, 2026:\n"
    "• Personal and other non-commercial use is free, with no registration. Commercial use needs registering with PFN first (article 3).\n"
    "• You must be 18 or older (or of age where you live), or have a parent's or guardian's consent (article 2).\n"
    "• You are responsible for having the rights to what you put into it and to what comes out of it; the licence gives no rights to other people's works (article 9).\n"
    "• A translation made with it may be published without a note that it is PLaMo's output, but one published as all or a large part of a book or another long publication must say that PLaMo was used. When you give a translation to someone or make it public, you must tell them that models trained on it fall under this licence (article 5). TASlation asks you not to publish translations at all.\n"
    "• The model comes as is, without any warranty; how you use it is your responsibility (article 7).")


def _over_everything(win: tk.Toplevel, master: tk.Misc) -> None:
    """*win* modal over *master*, centred over it and above everything, a full-screen viewer too."""
    place_window(win, master)
    try:
        win.attributes("-topmost", True)
        win.lift()
        win.grab_set()
    except tk.TclError:  # not on the screen (yet): no grab
        pass


class LicenceDialog(tk.Toplevel):
    """PLaMo's licence in plain words, its full text's two addresses (read-only lines that can be copied), a tick
    ("I am 18 or older ... and I agree") and Agree and download, which waits for the tick. ``agreed`` turns True on
    that button only; Cancel, Escape and closing the box leave it False. The tick starts empty, Cancel has the focus."""

    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.title(_("The licence of PLaMo"))
        self.transient(master)
        self.resizable(False, False)
        self.agreed = False
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        width = WARNING_CHARS * max(1, tkfont.nametofont("TkDefaultFont").measure("0"))
        self.text = _(LICENCE_TEXT)
        ttk.Label(frm, text=in_lines(self.text, width), justify="left").pack(anchor="w")
        ttk.Label(frm, text=in_lines(_("The full licence, in English and in Japanese:"), width),
                  justify="left").pack(anchor="w", pady=(12, 2))
        self.urls: list[str] = []
        for url in tinstall.PLAMO_LICENCE_URLS:
            field = ttk.Entry(frm, width=URL_CHARS)
            field.insert(0, url)
            field.configure(state="readonly")
            field.pack(anchor="w", fill="x", pady=(0, 2))
            self.urls.append(url)
        self.tick = tk.BooleanVar(self, value=False)
        self.tick_box = ttk.Checkbutton(frm, variable=self.tick, command=self._sync,
                                        text=in_lines(_("I am 18 or older, or have a parent's or guardian's consent, and I agree to the PLaMo Community License."), width))
        self.tick_box.pack(anchor="w", pady=(12, 0))
        btns = ttk.Frame(frm)
        btns.pack(anchor="e", pady=(14, 0))
        self.cancel_btn = ttk.Button(btns, text=_("Cancel"), command=self._cancel, default="active")
        self.cancel_btn.pack(side="right")
        self.agree_btn = ttk.Button(btns, text=_("Agree and download"), command=self._agree, state="disabled")
        self.agree_btn.pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.cancel_btn.focus_set()
        _over_everything(self, master)

    def _sync(self) -> None:
        self.agree_btn.configure(state="normal" if self.tick.get() else "disabled")

    def _agree(self) -> None:
        if not self.tick.get():  # (the button waits for the tick)
            return
        self.agreed = True
        self.destroy()

    def _cancel(self) -> None:
        self.agreed = False
        self.destroy()


def phase_text(data: dict[str, Any], model: str) -> str:
    """What the install dialog says of a progress line of setup_models.py."""
    phase = data.get("phase")
    done, total = float(data.get("done") or 0), float(data.get("total") or 0)
    if phase == "download" and total:
        return _("Downloading {model}: {done} of {total} GB").format(model=model, done=f"{done / 1e9:.1f}",
                                                                     total=f"{total / 1e9:.1f}")
    if phase == "pull":
        return _("Downloading {model}: {percent} %").format(model=model,
                                                           percent=int(100 * done / total) if total else 0)
    if phase == "check":
        return _("Checking the download...")
    if phase == "import":
        return _("Putting {model} into Ollama...").format(model=model)
    return ""


class InstallDialog(tk.Toplevel):
    """The install of *model* (its name as shown) by *installer* (`translator_install.Installer`), run in a thread of
    its own, then *after* there (the model no longer needed removed, say): a line that says what it does, a bar that
    shows how far (moving to and fro where nothing measures it) and Cancel, which stops the install (the dialog stays
    until it has cleaned up). ``outcome`` holds how it ended (`translator_install.Outcome`), ``after_result`` what
    *after* returned."""

    def __init__(self, master: tk.Misc, model: str, installer: Any, after: Callable[[], Any] | None = None):
        super().__init__(master)
        self.title(_("Translation model"))
        self.transient(master)
        self.resizable(False, False)
        self.model = model
        self.installer = installer
        self.after_work = after
        self.outcome: tinstall.Outcome | None = None
        self.after_result: Any = None
        self.lines: list[str] = []
        self._events: queue.Queue = queue.Queue()
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        self.label = ttk.Label(frm, text=_("Downloading {model}: {done} of {total} GB").format(
            model=model, done="0.0", total="..."), justify="left", width=WARNING_CHARS)
        self.label.pack(anchor="w")
        self.bar = ttk.Progressbar(frm, mode="determinate", maximum=1000, length=420)
        self.bar.pack(fill="x", pady=(10, 0))
        self.cancel_btn = ttk.Button(frm, text=_("Cancel"), command=self.cancel)
        self.cancel_btn.pack(anchor="e", pady=(14, 0))
        self.bind("<Escape>", lambda _e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.cancel_btn.focus_set()
        installer.on_progress = self._events.put
        self._worker = threading.Thread(target=self._work, name="taslation-install", daemon=True)
        _over_everything(self, master)
        self._worker.start()
        self.after(POLL_MS, self._poll)

    def _work(self) -> None:
        try:
            outcome = self.installer.run()
        except Exception as e:  # noqa: BLE001 - said as a failed install; nothing more is done
            outcome = tinstall.Outcome("failed", str(e))
        result = None
        if outcome.state == "done" and self.after_work is not None:
            try:
                result = self.after_work()
            except Exception:  # noqa: BLE001 - the model needed is there; what could not be removed stays
                result = None
        self._events.put({"phase": "_end", "outcome": outcome, "result": result})

    def cancel(self) -> None:
        """Cancel: the install is stopped; the dialog closes once it has cleaned up."""
        self.installer.cancel()
        try:
            self.cancel_btn.configure(state="disabled")
        except tk.TclError:
            pass

    def _poll(self) -> None:
        try:
            while True:
                data = self._events.get_nowait()
                if data.get("phase") == "_end":
                    self.outcome, self.after_result = data["outcome"], data["result"]
                    self.destroy()
                    return
                self.show(data)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(POLL_MS, self._poll)

    def show(self, data: dict[str, Any]) -> None:
        text = phase_text(data, self.model)
        if text:
            self.label.configure(text=text)
            self.lines.append(text)
        done, total = float(data.get("done") or 0), float(data.get("total") or 0)
        if total:
            if str(self.bar.cget("mode")) != "determinate":
                self.bar.stop()
                self.bar.configure(mode="determinate")
            self.bar.configure(value=1000 * min(1.0, done / total))
        elif data.get("phase") in ("check", "import"):
            if str(self.bar.cget("mode")) != "indeterminate":
                self.bar.configure(mode="indeterminate")
                self.bar.start(15)
