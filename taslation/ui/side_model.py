"""What the right side pane knows of the screens turned past in normal reading, no Tk (`ui.side` keeps it on the
window, `ui.seethrough.right_rows` says it): the screens (`SideModel`), each with its two stages - reading the text and
the translation - from the engine's ``page_stage`` events, the screen on show (``page_on_show``) and the backlog's
totals (``backlog``); the mark each screen gets (`Screen.mark`), counted for the pane's lines (`SideModel.counts`).
Memory only."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Any

from .. import fingerprint as fp

MERGED = "merged"  # read "merged": a screen that went by was taken all the same, under another seq: its own goes
SIDE_STAGES = ("read", "translate")  # normal reading has no erase of its own: a page is erased as it is shown
STATES = ("waiting", "working", "done", "failed", "skipped", "missed")
MARKS = ("done", "working", "waiting", "failed", "missed")  # a screen's mark, by its stages (`Screen.mark`)


# ------------------------------------------------------------------ the state
@dataclass
class Screen:
    """A screen turned past (one page, or a spread: what is captured and cached as one): its number in the order of
    first sight, its fingerprint as the engine told it, and its two stages."""

    seq: int
    fingerprint: str = ""
    stages: dict[str, str] = field(default_factory=lambda: {s: "waiting" for s in SIDE_STAGES})

    @property
    def mark(self) -> str:
        """The screen's mark: "missed" (it went by before it could be caught; or it was on show, turned past and not
        caught - its read done, its translation "missed": it is read when shown again), "working" (a stage under way,
        or the translation begun - some lines answered and kept - and not finished), "failed", "done" (translated, or
        with nothing to translate), "waiting" (caught, its work to come)."""
        read, translate = self.stages["read"], self.stages["translate"]
        if read == "missed":
            return "missed"
        if "working" in (read, translate):
            return "working"
        if "failed" in (read, translate):
            return "failed"
        if translate in ("done", "skipped") or read == "skipped":
            return "done"
        if translate == "missed":
            return "missed"
        return "waiting"

    def state(self, stage: str) -> str:
        """A stage's state: the translation of a screen that went by too fast is not caught either (nothing waits for
        it until the person turns back to it)."""
        state = self.stages[stage]
        if stage == "translate" and state == "waiting" and self.stages["read"] == "missed":
            return "missed"
        return state


@dataclass
class Backlog:
    """The backlog's totals as the engine last told them (``backlog``): the screens caught and not done yet, the lines
    still to translate of those read, whether the work is paused (Auto off, Stop, the model released), and how many
    screens went by too fast to be caught (or were not caught: over the caps), not caught or done since."""

    pages: int = 0
    lines: int = 0
    paused: bool = False
    dropped: int = 0


class SideModel:
    """The screens of normal reading, by their number (``seq``, the order of first sight), the screen on show, and the
    backlog. Events may come in any order; the latest one for a stage wins. Memory only, dropped with the book
    (`clear`)."""

    def __init__(self) -> None:
        self.screens: dict[int, Screen] = {}
        self.order: list[int] = []
        self.on_show: int | None = None
        self.backlog = Backlog()

    def __len__(self) -> int:
        return len(self.order)

    def clear(self) -> None:
        self.screens.clear()
        self.order.clear()
        self.on_show = None
        self.backlog = Backlog()

    def update(self, seq: Any, fingerprint: Any = "", stage: Any = None, state: Any = None) -> bool:
        """One ``page_stage`` event; True when it brought a screen not seen before. A stage or a state it does not
        know changes nothing but the screen's being there ("erase" among them: normal reading has none); read
        "merged" takes a placeholder away (the screen is there under another number)."""
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            return False
        if stage == "read" and state == MERGED:
            if self.screens.pop(seq, None) is not None:
                self.order.remove(seq)
                if self.on_show == seq:
                    self.on_show = None
            return False
        screen = self.screens.get(seq)
        new = screen is None
        if screen is None:
            screen = self.screens[seq] = Screen(seq)
            bisect.insort(self.order, seq)
        if fingerprint and not screen.fingerprint:
            screen.fingerprint = str(fingerprint)
        if stage in SIDE_STAGES and state in STATES:
            screen.stages[stage] = state
        return new

    def renumbered(self, seq: Any, fingerprint: Any, within: int) -> bool:
        """Whether *fingerprint* told for the screen *seq* is another screen's than the one known under that number:
        the engine numbers the screens of another book from 1 again (the window then starts afresh: `ui.side`)."""
        try:
            screen = self.screens.get(int(seq))
        except (TypeError, ValueError):
            return False
        if screen is None or not screen.fingerprint or not fingerprint:
            return False
        try:
            return fp.hamming(screen.fingerprint, str(fingerprint)) > max(0, int(within))
        except (TypeError, ValueError):
            return screen.fingerprint != str(fingerprint)

    def show(self, seq: Any) -> bool:
        """The screen on show (``page_on_show``; None: none of the book's); whether that changed."""
        try:
            seq = None if seq is None else int(seq)
        except (TypeError, ValueError):
            seq = None
        if seq == self.on_show:
            return False
        self.on_show = seq
        return True

    def set_backlog(self, pages: Any, lines: Any, paused: Any, dropped: Any, now: float = 0.0) -> bool:
        """The backlog's totals (``backlog``); whether they changed."""
        told = Backlog(_count(pages), _count(lines), bool(paused), _count(dropped) if dropped is not True else 0)
        if told == self.backlog:
            return False
        self.backlog = told
        return True

    def working(self) -> bool:
        return any("working" in s.stages.values() for s in self.screens.values())

    def counts(self) -> dict[str, int]:
        """How many screens have each mark."""
        out = {mark: 0 for mark in MARKS}
        for screen in self.screens.values():
            out[screen.mark] += 1
        return out


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
