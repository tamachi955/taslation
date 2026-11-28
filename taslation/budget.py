"""A page's time budget, and what the costly helpers may still spend of it.

Every page read (`Pipeline.process`) has a budget: `PAGE_BUDGET_S` where torch has CUDA up, `PAGE_BUDGET_CPU_S` on a
computer without a GPU - the owner's scale says a page slower than that keeps the person from reading (S1,
`taslation.analysis`). The budget is kept on the thread that reads the page (`begin`, `end`) and on the threads that
work for it (`adopt`: the drafts' lettering, the next unit read beside), and the helpers whose cost grows with what the
page holds ask it before they start (`lama_refused`): LaMa, the erase on the drawing, runs on a page only while

* the page has spent under `LAMA_UNTIL` of its budget,
* its windows so far number under `LAMA_PAGE_WINDOWS`,
* the pixels of its windows so far stay under `LAMA_PAGE_PX` (`LAMA_PAGE_CPU_PX` on the processor: some 5.4 s a
  million pixels there, 0.5 s on the GPU, measured 2026-11-28), and
* the holes it filled so far stay under `LAMA_PAGE_HOLE` of the page's area;

past any of them the lettering on the drawing is filled from round it by OpenCV's inpainting (`artwork.ArtEraser`:
milliseconds, a smoother fill than LaMa's). A page with no budget (a tool, a test that reads a region alone) refuses
nothing. Nothing here is written to disk; the analysis log counts what was refused and why."""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

PAGE_BUDGET_S = 15.0  # s: a page slower than this where torch has CUDA up is too slow to use (S1) ...
PAGE_BUDGET_CPU_S = 45.0  # ... and without a GPU
LAMA_UNTIL = 0.6  # of the budget spent: no new LaMa window after it
LAMA_PAGE_WINDOWS = 12  # LaMa's windows on one page at the most
LAMA_PAGE_PX = 4_000_000  # their pixels at the most, on the GPU (some 2 s there) ...
LAMA_PAGE_CPU_PX = 1_500_000  # ... and on the processor (some 8 s)
LAMA_PAGE_HOLE = 0.12  # of the page's area: the holes LaMa fills on it at the most

_TL = threading.local()  # .budget: the page's budget on this thread


@dataclass
class PageBudget:
    """One page's budget: its start (perf_counter), its seconds, and what LaMa took of it so far."""

    seconds: float
    area: int = 0  # the page's pixels (0: not known, no hole limit)
    started: float = field(default_factory=time.perf_counter)
    lama_windows: int = 0
    lama_px: int = 0
    lama_hole: int = 0
    refused: dict[str, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    previous: PageBudget | None = field(default=None, repr=False, compare=False)  # (the thread's before it)

    def spent(self) -> float:
        return time.perf_counter() - self.started

    def over(self) -> bool:
        return self.spent() > self.seconds


def gpu_up() -> bool:
    """Whether torch has CUDA up in this process (never started for it): the GPU's budget then."""
    torch = sys.modules.get("torch")
    try:
        return torch is not None and bool(torch.cuda.is_initialized())
    except Exception:  # noqa: BLE001 - no answer: the processor's budget
        return False


def seconds_now() -> float:
    """The budget of a page that begins now (`PAGE_BUDGET_S` with the GPU up, else `PAGE_BUDGET_CPU_S`)."""
    return PAGE_BUDGET_S if gpu_up() else PAGE_BUDGET_CPU_S


def begin(area: int = 0, seconds: float | None = None) -> PageBudget:
    """A page begins on this thread: its budget (*seconds*, by default `seconds_now`), the one before kept to
    come back to at `end`."""
    page = PageBudget(seconds_now() if seconds is None else float(seconds), int(area))
    page.previous = getattr(_TL, "budget", None)
    _TL.budget = page
    return page


def end(page: PageBudget | None) -> None:
    if page is not None and getattr(_TL, "budget", None) is page:
        _TL.budget = page.previous


def current() -> PageBudget | None:
    return getattr(_TL, "budget", None)


@contextmanager
def adopt(page: PageBudget | None) -> Iterator[None]:
    """*page*'s budget on this thread meanwhile (another thread's work for that page); None: nothing changes."""
    if page is None:
        yield
        return
    before = getattr(_TL, "budget", None)
    _TL.budget = page
    try:
        yield
    finally:
        _TL.budget = before


def lama_refused(window_px: int, hole_px: int, on_gpu: bool) -> str:
    """Why LaMa may not take one more window of *window_px* pixels with a hole of *hole_px* on this thread's page
    ("" where it may, and then it is counted): "time", "windows", "pixels" or "hole" (see the module's notes)."""
    page = current()
    if page is None:
        return ""
    with page.lock:
        why = ""
        if page.spent() > LAMA_UNTIL * page.seconds:
            why = "time"
        elif page.lama_windows >= LAMA_PAGE_WINDOWS:
            why = "windows"
        elif page.lama_px + window_px > (LAMA_PAGE_PX if on_gpu else LAMA_PAGE_CPU_PX) and page.lama_windows:
            why = "pixels"
        elif page.area and page.lama_hole + hole_px > LAMA_PAGE_HOLE * page.area and page.lama_windows:
            why = "hole"
        if why:
            page.refused[why] = page.refused.get(why, 0) + 1
            return why
        page.lama_windows += 1
        page.lama_px += int(window_px)
        page.lama_hole += int(hole_px)
        return ""


__all__ = ["LAMA_PAGE_CPU_PX", "LAMA_PAGE_HOLE", "LAMA_PAGE_PX", "LAMA_PAGE_WINDOWS", "LAMA_UNTIL", "PAGE_BUDGET_CPU_S",
           "PAGE_BUDGET_S", "PageBudget", "adopt", "begin", "current", "end", "gpu_up", "lama_refused", "seconds_now"]
