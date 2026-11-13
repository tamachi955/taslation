"""The window's status line (said again in the window's language after a switch; a `taslation.messages.Message` is
rendered with the message catalog of that language), the strips over the page (the setup banner and the scan band,
`banner`), and the signs of a running job:
the busy badge on the page, the progress bar beside Stop and the title - the bar and the title only once a job has
run for `BUSY_SIGNS_S`, so a page that comes from the cache at once does not make the window flicker."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from ..i18n import _
from ..messages import FOLLOW_UPS, JOINER, Message
from ..pipeline import summary as page_summary
from ..regions import PageResult
from . import taskbar, trouble
from .banner import (BAND_COLOURS, NOTICE_COLOURS, PROBLEM_COLOURS, SetupBanner, Strip, band_fraction, band_text,
                     blocking, busy_title, is_notice)
from .constants import READER_AFTER_RUN, READING_NOTE_MS, READY
from .constants import APP_TITLE
from .progress import busy_line, rendered

BUSY_SIGNS_S = 0.3  # a job shows the busy title and bar after this long (a page from the cache is done before)


def _shown(value: Any) -> Any:
    """A status line's value in the window's language: a Message rendered, an error by the Message it carries."""
    if isinstance(value, Message):
        return rendered(value)
    carried = getattr(value, "message", None) if isinstance(value, BaseException) else None
    return rendered(carried) if isinstance(carried, Message) else value


def _alone(message: Message) -> Message:
    """*message* without its follow-ups (the params that bring them cleared)."""
    quiet = {param for param, _code in FOLLOW_UPS.get(message.code, ())}
    return Message(message.code, {k: ("" if k in quiet else v) for k, v in message.params.items()})


class StatusMixin:
    """The status line, the strips over the page, the busy badge and the progress bar. A part of `app.App` (no
    `__init__`: the state it uses is made by `App.__init__`; the other parts are reached through ``self``)."""

    # ------------------------------------------------------------------ the status line
    def _wrap_status(self) -> None:
        """A long status line takes two lines instead of being cut (the guard's warning, at the right, takes at most
        half the width)."""
        try:
            width = self.status_bar.winfo_width() - 16
        except tk.TclError:
            return
        if width < 120:
            return
        self._wrap(self.guard_label, width // 2)
        guard = self.guard_label.winfo_reqwidth() + 12 if self.guard_var.get() else 0
        move = getattr(self, "move_btn", None)  # the button that moves TASlation to the book's monitor, when shown
        moving = move.winfo_reqwidth() + 8 if move is not None and move.winfo_manager() else 0
        self._wrap(self.status_label, width - guard - moving - 106)  # the busy bar's place: 90 px and its padding

    def status(self, text: str | Message | Callable[[], str]) -> None:
        """The status line: *text*, a Message in the window's language, or what a callable gives in the window's
        language (each asked again after a language switch); in the reading window the line shows at the bottom of
        the page for a while."""
        if isinstance(text, Message):
            message = text
            text = lambda: rendered(message)  # noqa: E731 - said again after a language switch
        render = text if callable(text) else None
        line = render() if render is not None else str(text)
        self._status_render, self._status_key = render, None
        self.status_var.set(line)
        if self.reading:  # no status bar there: the line shows at the bottom of the page for a while
            self.canvas.set_note(line, READING_NOTE_MS)

    def say(self, key: str | Message, /, **values: Any) -> None:
        """The status line *key* in the window's language with *values* filled in (said again after a switch; a
        value that is a Message, or an error that carries one, in the window's language too). *key* may be a
        Message: it is rendered with the message catalog of the window's language."""
        if isinstance(key, Message):
            self.status(key)
            return
        self.status(lambda: _(key).format(**{k: _shown(v) for k, v in values.items()}) if values else _(key))
        self._status_key = key

    def _font_note(self) -> str:
        """After the page summary: the series sheet suggests a lettering font this computer lacks."""
        if self.pipeline is None:
            return ""
        name, file = self.pipeline.font_status()
        return _(" - the suggested font \"{font}\" is not installed").format(font=name) if name and file is None else ""

    @staticmethod
    def _summary(result: PageResult, review: bool = True) -> str:
        """A finished page's line in the window's language: `pipeline.summary` (the bubbles from the cache or
        translated, the regions to review - with *review*: the Translator role has the Review tool -, what went wrong),
        rendered with the message catalog; last, how many of its lines are still without a translation, which F5 asks
        for again (`pipeline.summary` says only what was done)."""
        head = page_summary(result)
        lines = [rendered(_alone(head)), *(rendered(s) for s in head.sentences()[1:]
                                           if review or s.code != "pipeline.to_review")]
        waiting = sum(1 for r in result.regions if r.status == "untranslated")
        if waiting and result.fingerprints:
            lines.append(_("{n} line(s) not translated yet: press F5.").format(n=waiting))
        return JOINER.join(lines)

    def _page_line(self, result: PageResult) -> str:
        """`_summary` for the role chosen: the regions to review are the Translator role's business."""
        return self._summary(result, self.role_var.get() == "translator")

    def _normal_status(self) -> None:
        """The status line of the normal window: the page on show, else the viewer, else ready."""
        result = self.last_result
        if result is not None and self._result_on_show():
            self.status(lambda: self._page_line(result) + self._font_note())
        elif self.selected is not None:
            self.say("Viewer: {title}", title=self.selected.title)
        else:
            self.say(READY)

    # ------------------------------------------------------------------ the strips over the page
    def _build_strips(self) -> None:
        """Between the toolbar and the page: the setup banner and the scan band, each away while it has nothing to
        say; the reading window hides them with the toolbar."""
        self.strips = ttk.Frame(self)
        self.strips.pack(fill="x")
        self.setup_banner = SetupBanner(self.strips)
        self.scan_band = Strip(self.strips, BAND_COLOURS, pad=(12, 6))
        self._bars = (*getattr(self, "_bars", ()), self.strips)

    def _place_strip(self, strip: tk.Widget, shown: bool) -> None:
        """Put *strip* on the screen (the banner above the band) or take it away."""
        if not shown:
            if strip.winfo_manager():
                strip.pack_forget()
                if not self.strips.pack_slaves():  # Tk keeps a frame's size when its last slave goes: shrink it
                    self.strips.configure(height=1)
            return
        if strip.winfo_manager():
            return
        order = [s for s in (self.setup_banner, self.scan_band) if s is not None]
        later = [s for s in order[order.index(strip) + 1:] if s.winfo_manager()] if strip in order else []
        if later:
            strip.pack(fill="x", side="top", before=later[0])
        else:
            strip.pack(fill="x", side="top")

    def _show_banner(self) -> None:
        """The setup banner: the problems and notices of the last setup check, in the window's language, each with the
        button that fixes it where the window can (`trouble.setup_button`: Start translator again, Download model);
        then what keeps the window from reading the viewer, with its button (`trouble.viewer_trouble`, `_trouble`:
        Choose viewer, Show viewer, Move TASlation aside); the translator on the processor (`_on_cpu`, with Close);
        after them, while a whole-book scan waits for the setup, that it does."""
        held = self._scan_held and bool(blocking(self._health))
        rows: list[tuple[str, tuple[str, str], Any]] = [
            (trouble.setup_line(m), NOTICE_COLOURS if is_notice(m) else PROBLEM_COLOURS, trouble.setup_button(self, m))
            for m in self._health]
        kind = getattr(self, "_trouble", None)
        if kind is not None:
            rows.append((trouble.trouble_line(kind), PROBLEM_COLOURS,
                         trouble.action_button(self, trouble.TROUBLE_ACTIONS[kind])))
        seconds = getattr(self, "_on_cpu", None)
        if seconds:
            rows.append((trouble.cpu_line(seconds), NOTICE_COLOURS, (_("Close"), self._close_cpu_line)))
        if held:
            rows.append((_("The whole book is not read yet: first fix what the lines above the page say. Until then TASlation translates page by page."), NOTICE_COLOURS, None))
        self.setup_banner.show_rows(rows)
        self._place_strip(self.setup_banner, bool(rows))

    def _close_cpu_line(self) -> None:
        """The processor's notice closed: not said again this session."""
        self._on_cpu = None
        self._show_banner()

    def _watch_trouble(self, now: float | None = None) -> None:
        """What keeps the window from reading the viewer, looked at every `trouble.TROUBLE_LOOK_S` from the event pump
        (`trouble.viewer_trouble`: the state the viewer's parts keep, and whether its window is minimised); the
        banner follows when it changed."""
        now = time.monotonic() if now is None else now
        if now < getattr(self, "_trouble_due", 0.0):
            return
        self._trouble_due = now + trouble.TROUBLE_LOOK_S
        kind = trouble.viewer_trouble(self)
        if kind != getattr(self, "_trouble", None):
            self._trouble = kind
            self._show_banner()

    def _band_view(self) -> tuple[list[str], list[tuple[str, Callable[[], None]]]]:
        """What the scan band shows for its state (`_band`): its lines and its buttons."""
        band = self._band
        kind = band["kind"]
        if kind == "scan":
            scan = band["scan"]
            buttons = [(_("Stop"), self.stop_batch)]
            if scan.scanning and not scan.finishing:
                buttons.insert(0, (_("Finished reading"), self.finish_reading))
            action = trouble.WAITING_ACTIONS.get(getattr(scan.waiting, "code", "")) if scan.waiting else None
            if action is not None:  # what the run waits for, where a button does it
                buttons.insert(0, trouble.action_button(self, action))
            return [band_text(scan)], buttons
        lines = [rendered(band["summary"])]
        if band.get("resumed"):
            lines.append(_("Auto: follow page turns is on again."))
        if band.get("reader"):
            lines.append(_(READER_AFTER_RUN))
        buttons = [(_("Close"), self.close_band)]
        if band.get("names"):  # the run rendered names in more than one way: one can be chosen for each
            lines.append(_("{n} name(s) rendered in more than one way across the book.").format(n=band["names"]))
            buttons.insert(0, (_("Review names..."), self.review_names))
        held = self._held_readings()
        if held is not None:  # a Stop left pages read and not translated: they can be translated now
            buttons.insert(0, (_("Translate the rest") if held.complete else _("Translate the pages read"),
                               self.translate_readings))
        return lines, buttons

    def _held_readings(self) -> Any:
        """What the run on the band read and did not store, while the window holds it for the book, model and language
        in the boxes (`Readings`; None: nothing, or another book's)."""
        band = self._band or {}
        code = getattr(band.get("summary"), "code", "")
        if code not in ("batch.stopped_reading", "batch.stopped_translating"):
            return None
        held = getattr(self, "_readings", None)
        boxes = (self.book_var.get().strip(), self.model_var.get().strip(), self.lang_var.get().strip())
        return held[1] if held is not None and held[0] == boxes and held[1].units else None

    def _show_band(self) -> None:
        """The scan band for its state (`_band`; None: away), with the bar of a whole-book translation, and that bar
        on the taskbar button too (`_show_taskbar`)."""
        if self._band is None:
            self._place_strip(self.scan_band, False)
            self.scan_band.set([], ())
            self.scan_band.show_fraction(None)
            self._show_taskbar(None)
            return
        lines, buttons = self._band_view()
        self.scan_band.set(lines, buttons)
        scan = self._band.get("scan") if self._band.get("kind") == "scan" else None
        self.scan_band.show_fraction(band_fraction(scan))
        self._show_taskbar(scan)
        self._place_strip(self.scan_band, True)

    def _show_taskbar(self, scan: Any) -> None:
        """The run on the taskbar button (`taskbar.TaskbarProgress`): a green bar while the book is translated, a
        yellow one while the run waits for the reader, none otherwise (while the pages are read, after the run)."""
        bar = getattr(self, "_taskbar", None)
        if bar is None:
            if scan is None or not hasattr(self, "wm_frame"):
                return
            bar = self._taskbar = taskbar.TaskbarProgress(lambda: int(self.wm_frame(), 16))
        fraction = band_fraction(scan)
        if scan is not None and scan.waiting:
            bar.show(taskbar.PAUSED, 1.0 if fraction is None else fraction)
        elif fraction is not None:
            bar.show(taskbar.NORMAL, fraction)
        else:
            bar.clear()

    # ------------------------------------------------------------------ a job running
    def _go_busy(self) -> None:
        """A worker job starts: the window shows it until the job is done (the title and the bar after
        `BUSY_SIGNS_S`, `_flush_busy`)."""
        self.busy = True
        self._busy_since = time.monotonic()
        self._progress = ""
        self._busy_signs = False
        self._set_busy(True)

    def _set_busy(self, busy: bool) -> None:
        """The buttons, the busy bar and the title follow the worker (once a job has run for `BUSY_SIGNS_S`); the
        busy band goes when it is done (unless a request waits for the models to load: it keeps saying so)."""
        waiting = self._queued is not None and not self.ready
        if busy:
            if self._busy_signs:
                self._show_busy_signs()
            elif waiting:
                self._show_progress(True)
            return
        self._busy_signs = False
        self.translate_btn["state"] = "normal"
        self.batch_btn["state"] = "normal"
        self.title(APP_TITLE)
        self._show_progress(waiting)
        if not waiting:
            self._hide_busy()

    def _flush_busy(self, now: float | None = None) -> None:
        """A job has run for `BUSY_SIGNS_S`: the title and the bar say so (asked from the event pump)."""
        if not self.busy or self._busy_signs:
            return
        # a hair of tolerance: a monotonic timestamp plus 0.3 minus the timestamp can round below 0.3
        if (time.monotonic() if now is None else now) - self._busy_since >= BUSY_SIGNS_S - 1e-6:
            self._busy_signs = True
            self._show_busy_signs()

    def _show_busy_signs(self) -> None:
        self.translate_btn["state"] = "disabled"
        self.batch_btn["state"] = "disabled"
        self.title(busy_title(getattr(self, "_scan", None)))
        self._show_progress(True)

    def _show_progress(self, shown: bool) -> None:
        """The bar next to Stop: running while a job runs, gone (its place kept) otherwise."""
        if shown and not self._bar_shown:
            self.progress_bar.pack(fill="x", expand=True)
            self.progress_bar.start(15)
        elif not shown and self._bar_shown:
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
        self._bar_shown = shown

    def _busy_text(self) -> str:
        fill = self._fill
        return busy_line(self._progress, time.monotonic() - self._busy_since,
                         fill.filled - fill.mark if fill is not None else 0,
                         reading=getattr(getattr(self, "_scan", None), "phase", "") == "read")

    def _hide_busy(self) -> None:
        self._busy_shown = False
        self.canvas.set_busy(None)
