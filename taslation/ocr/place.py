"""What runs on the GPU for the session: one judgement at the start, for everything TASlation puts there.

The parts that may run on the GPU, by the settings: the translation model (Ollama's; ``ollama_num_gpu``), two of the
three OCR readers (charspot and nar; ``ocr_runs_on``: "auto", the default, "cpu" or "gpu"), the erase model on the art
(LaMa; ``art_erase``) and the layout model (``detect_model``) - the last three where torch has CUDA. CPT, the third
reader, which reads a line only where the other two differ, stays on the CPU: its 440 MB of weights would be on the
GPU for a few crops a page.

THE JUDGEMENT (`judge`), once, as the session starts (the window: `taslation.ui.jobs`, after the legal notice while
the viewer chooser is on the screen, once TASlation's Ollama answers and before any model is loaded; a command: when
its readers are placed, `plan_for`): the
card's total memory, less what other programs hold now, less every part the settings put on the GPU at its measured
peak (`Need`, `needs`) and this process's CUDA context, must leave `MARGIN_MIB` free (`left_at_peak`). The answer is
one number: enough, or short by N MiB (`short_by`). Enough: everything is loaded at the start, where it was judged to
go, and stays there for the session (`Plan`, `settle`). Short: the window asks (`ui.dialogs.gpu_short`, which names
the other models Ollama holds on the card): check again (the person closed something), release TASlation's own models
among those and check again (`GpuFacts.releasable`), start with what does not fit on the processor (`TO_PROCESSOR`,
least loss first: only as many parts as it takes), or quit; ``gpu_short`` "processor" (the dialog's "Do not ask
again on this computer") sends it there without asking, and a command or a tool, which cannot ask, does too. A
setting that fixes a part (``ocr_runs_on`` "gpu" or "cpu", a number of layers in ``ollama_num_gpu``) is never moved:
counted where it puts the part. One that forces a part onto the GPU ("gpu", a number of layers) never asks either:
the person took the GPU into their own hands, the start goes on as the settings say, short, and the System page says
by how much (with ``gpu_short`` "processor" the parts not fixed go to the processor as ever). The readers' CUDA graphs
(`taslation.ocr.graphs`: charspot 46 % and nar 29 % less time a crop on the GTX 1660 Ti) are counted with them
(`READERS_GRAPHS_MIB`) as what they can do without (`Need.extra`): where the start is short with them, they are left
off first, nothing asked (`Plan.graphs`), and the rest is judged as above without them - the readers stay on the GPU,
only slower.

What a fuller card does (Windows' driver model; GTX 1660 Ti 6 GB, driver 610.88, Ollama 0.40.16, measured 2026-11-22
with a process that held dummy memory, step by step, beside the model and the readers): nothing fails. No allocation
ran out of memory, the readers' copy to the GPU and Ollama's load among them, with 17.7 GB held on the 6 GB card; and
Ollama loads the model whole whatever other processes hold - neither its "gpu memory available" nor llama.cpp's fit
("projected to use 1981 MiB of device memory vs. 5134 MiB of free device memory") sees another process's memory, so
its layers never move to the CPU because of TASlation's other models or of other programs. What happens instead is
that the driver keeps some of the card free (`FLOOR_MIB`) and moves the memory of processes that are not computing just
then into the computer's own, and back at their next turn: with the model loaded, the readers reading and the card
more than full, each request to the model began 0.2-0.5 s later (its cached prompt read in 0.21-0.53 s instead of
0.01-0.07, 490-1150 MiB of the runner moved), and with another program at work on its own memory the readers read 3.5
to 4.5 times slower (charspot 52-55 ms a crop instead of 15, nar 110-113 instead of 25 - slower than on the CPU, 28 and
73). The judgement keeps the start from coming to that: it counts the translation model whole beside the rest, whether
it is loaded yet or not, at the most it was measured to take, and leaves free the driver's part and the most other
programs were seen to rise at once (`SWAY_MIB`). What other programs take later is theirs: nothing is looked at or
moved during the session.

During the session nothing moves: no look at the room, no way back, no release before a load of the translation model
(it was counted whole beside the rest, and Ollama loads it whole there: measured on the 6 GB card, 2026-11-16, PLaMo
came up whole beside the readers in 10 loads of 10, /api/ps 1823 of 1823 MiB; with a page read meanwhile a crop took
43-47 ms through the load against 146-226 on the CPU with them let go, and the load 5.0-5.3 s against 5.5-6.5). Tools >
Release the model now gives the memory back for another program; each part loads again where the plan has it when it
is next needed. A change of a placing setting during the session counts from the next start, but a setting that fixes
a part's place (``ocr_runs_on`` "cpu" or "gpu") takes it there from the next page.

One net, one way (`failed`): a part whose work fails on the GPU (out of memory, a CUDA error: the readers'
`DeviceModels.run`, LaMa's and the layout model's own) goes on on the processor for the rest of the session, and the
System page says so. A check of reads that crawl on the GPU is not kept: on a card filled past its size by a program
computing on it, the readers' reads took 1.5 to 1.9 times the CPU's - below any factor that a wait behind this process's
own page models does not also reach - so it never took them off such a card.

While a request to the translation model is under way (`translating`, for the translator to wrap its requests in) the
readers stay on the GPU, with their CUDA graphs or without them, wherever the session's plan has room for what it put
there (`plain_beside_requests`). Measured 2026-11-28 (GTX 1660 Ti, PLaMo answering requests of three lines back to
back, a made-up page unit of 44 crops): on the GPU through the requests charspot 18.6 ms a crop and nar 39 with the
graphs, 23.4 and 47 by the plain pass, against 182 and 487 on the CPU, which the page's other work shares - the unit
read in 5.0 s and 3.2 s against 21.0 -, the requests 366 ms each with the graphs beside them and 419 with the plain
pass, against 296 with the reads on the CPU and 296 alone; the two rules in turn page by page on made-up spreads of
12-22 crops a unit, the graphs left off, half the processor taken by other work (2 x 16 pages): unit 0 16.6 s in all
against 21.2, the first bubble 24.9 s against 27.0, the pages 57.1 s against 55.1 (the requests 138-157 ms median
against 108-118: docs/DEVELOPMENT.md). Only where the start was short of room and went on all the
same (a setting forced a part onto the GPU, or nothing could go: `Plan.left` under `MARGIN_MIB`) does a copy without
graphs read with its CPU copy while a request runs, then with the GPU's again (both stay loaded, only the device of a
read changes): on a card past its memory the driver moves memory to and fro, and the plain pass's many small steps
wait at each of the translator's time slices (a crop on the GPU while PLaMo generated was once measured at 687 ms, both
readers, against 127 on the CPU). A copy with its graphs (`graphed`) stays on the GPU there too: a replay is one
launch.

What the judgement measures (`GpuFacts`, `gather`):

* the card's memory as NVIDIA's driver library sees it (`devices.nvml_usage_mib`, nothing loaded, no CUDA context
  made): on Windows torch's ``mem_get_info`` counts what this process holds alone (another process's 2 GB left its
  free memory as it was, measured), so it cannot see Ollama or other programs; where there is no NVML (not Windows)
  torch's own figure, which is the card's there. None (no NVIDIA GPU): nothing is judged, nothing asked;
* what of the used memory is TASlation's own: the translation model's, when Ollama has it loaded as the requests ask
  for it (/api/ps, which never loads one) - its need, below, times the share /api/ps says is on the GPU
  (``size_vram`` / ``size``), so that the runner's own memory, which /api/ps leaves out and the card's used memory
  has, is not counted twice (`KNOWN_TRANSLATORS`' loads: PLaMo's runner 110 MiB beside /api/ps's 1956, Qwen's 736
  beside 3203); loaded at another context (by another program, or another version), what /api/ps says it holds,
  which goes as the server loads it again for the first request - and this process's (torch's reserved memory and its
  CUDA context); the rest is other programs', the other models Ollama holds there among it (`Loaded`: named by the
  start's dialog, which offers to release TASlation's own);
* what the translation model needs: /api/ps's ``size`` while it is loaded (``size_vram`` where ``ollama_num_gpu`` puts
  only some layers there on purpose), with the runner's own memory that /api/ps leaves out (for a known model, what
  it was measured to add with the server's cache whose /api/ps size is the smallest that holds it; else
  `RUNNER_SHARE`); before it is loaded, what it was measured to add to the card's used memory (`KNOWN_TRANSLATORS`, at
  the context the app asks for, with the KV cache type and the window cache the server has: `server_cache` - the
  window cache at its real size, once); a model of the reader's own, by the size of its file (/api/tags) and
  `UNKNOWN_SHARE`;
* where LaMa runs on the GPU, the tallest screen's height (`tall_screen`): its window grows with the lettering's size
  in pixels, and so with the frames the viewer's window gives (`LAMA_MIB`, `LAMA_TALL_MIB`).

The readers' weights move without being read from disk again: the CPU's copy stays where it is loaded, the GPU's is
made from it (`DeviceModels.to`) and dropped only by the net or a release.
"""

from __future__ import annotations

import contextlib
import gc
import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, TypeVar

LOG = logging.getLogger(__name__)
MiB = 1024 * 1024
T = TypeVar("T")

SETTING_VALUES = ("auto", "cpu", "gpu")  # ``ocr_runs_on``
SHORT_VALUES = ("ask", "processor")  # ``gpu_short``: what a start that is short of GPU memory does

# What each part holds on the GPU at its peak, measured on a GTX 1660 Ti (6 GB, Windows, torch 2.14 cu126, 2026-11-19):
# this process's dedicated GPU memory as Windows counts it (CUDA context and library kernels included) and torch's
# reserved memory, each model alone, over the dataset's 214 pages, the 101 frames of the dev snapshots (1920x1032) and
# frames of 1904x1072, 2560x1440 and 3840x2160 (two pages scaled to the frame's height). The figures are those peaks
# and a fifth more, rounded up to 10 MiB, for the inputs not measured.
# The readers are counted at their measured peak with nothing added: their inputs are bounded (charspot's 256 cells
# of 16 px, nar's 324 patches of 14 px), so the largest crop's is the peak. Torch's reserved memory for them, measured
# again on 2026-11-22 over 509 crops of the dataset's pages for charspot and 206 for nar (each reader's own crops, as
# the pipeline cuts them) and 11 made-up crops of the largest sizes: charspot alone 110 MiB (124 once its cache was
# given back and the crops read again), both 410 (402 so) - their weights 328, a crop's work 35-38 MiB, the rest the
# allocator's blocks. Rounded up to 10 MiB: charspot 124, both 410 less charspot's 124.
CHARSPOT_MIB = 130
NAR_MIB = 290
# The readers' CUDA graphs beside them (`taslation.ocr.graphs`), counted with them where they capture them: their
# one pool, their outputs and inputs, and what the driver holds for them outside torch's memory, captured once as the
# copies are made and never grown by a replay. Measured on the GTX 1660 Ti (2026-11-27, torch 2.14.1 cu126, the card's
# used memory as NVML says it, the copies and plain passes of every shape captured on either side): charspot's 85
# graphs 261-268 MiB (108 of them torch's reserved memory, the rest the driver's), nar's one graph captured into the
# same pool after them nothing more (both 254-261 MiB; nar's alone, in a pool of its own, 96). Rounded up to 10 MiB.
READERS_GRAPHS_MIB = 270
# this process's CUDA context with the libraries the networks load there (Windows' dedicated memory less torch's
# reserved): 77 MiB bare, 99 with all of them (2026-11-19); 76 bare, 86 with the readers' and the layout model's
# (2026-11-22). The largest, rounded up to 10 MiB.
CONTEXT_MIB = 100
# LaMa: its weights (204 MiB reserved, 12 of kernels) and what the window takes while it is filled. The window is the
# frame's own pixels around the region, 512 px a side or more for a larger region, so it grows with the screen: at the
# largest window met, 336 MiB on the dev snapshots' frames (658x512) and 348 on 2560x1440 (815x512), 552 and 564 in
# all - `LAMA_MIB`, for screens up to `LAMA_SCREEN_PX` high (`tall_screen`); 588 on 3840x2160 (1188x512), 804 in all -
# `LAMA_TALL_MIB`, for a taller screen or one not known. What a window leaves idle in torch's cache is given back after
# it (`artwork.give_back_idle`): kept, the blocks of each window size piled up to 2.4 GB in a session.
LAMA_MIB = 680
LAMA_TALL_MIB = 970
LAMA_SCREEN_PX = 1440
# the layout model: its weights (175 MiB), blocks and kernels, 356 in all, the same on every frame (each page unit is
# scaled to 640 px square: 123 MiB while it runs, on every input measured; 346 reserved again on 2026-11-22 through
# whole pages, two-page frames of 1920x1032; with the readers 668 there and on 2560x1440, below the two figures'
# sum, 742: the allocator's blocks are shared)
LAYOUT_MIB = 430
# The translation models whole in video memory, at the context the app asks for (PLaMo its own 8192, the chat model
# ``ollama_num_ctx``'s default), by the server's KV cache type (``OLLAMA_KV_CACHE_TYPE``; `DEFAULT_KV` where it is set
# nowhere) and whether its cache of the windowed layers is full-size (``LLAMA_ARG_SWA_FULL``: `taslation.ollama_start`):
# what loading one with the app's options added to the card's used memory, rounded up to the next 100 MiB, and
# /api/ps's size then, rounded up (Ollama 0.40.16, three loads each, the same to 1 MiB, 2026-11-20). PLaMo: 1933 MiB
# (/api/ps 1823.9) with q8_0, 2065 (1955.5) with q8_0 and the full window, 2009 (1881.4) with f16, 2229 (2101.4) with
# f16 and the full window. Qwen3.5 4B: 3939 (3203) with q8_0 either way: it has no windowed layers. The runner takes it
# all at the load, KV cache included, and it does not grow, so it is counted as measured:
# (Ollama name, num_ctx) -> {(KV cache type, full window): (MiB added, /api/ps MiB)}
KNOWN_TRANSLATORS: dict[tuple[str, int], dict[tuple[str, bool], tuple[int, int]]] = {
    ("taslation-plamo3-translate-2b", 8192): {("q8_0", False): (2000, 1824), ("q8_0", True): (2100, 1956),
                                               ("f16", False): (2100, 1882), ("f16", True): (2300, 2102)},
    ("qwen3.5:4b", 16384): {("q8_0", False): (4000, 3203), ("q8_0", True): (4000, 3203)},
}
DEFAULT_KV = "f16"  # Ollama's KV cache type where OLLAMA_KV_CACHE_TYPE is set nowhere
RUNNER_SHARE = 1.25  # what the runner adds to /api/ps's size, at most (measured 1.06 and 1.23), for another model
UNKNOWN_SHARE = 1.6  # a model of the reader's own never seen loaded: its file's size (/api/tags) times this
# What the judgement leaves free at the peak (the module's docstring: what a fuller card does), measured on the 6 GB
# card (2026-11-22). FLOOR_MIB: what NVIDIA's driver keeps free of the card - with less left, it moves the memory of a
# process that is not computing just then into the computer's own (Ollama's runner while the OCR reads, the readers
# while the model translates), and that process pays for it at its next turn. Filling the card step by step, it began
# to with 337 to 484 MiB of NVML's free memory left, never with 527 or more; the highest, 484, rounded up. SWAY_MIB: how
# far other programs' memory rose at once, followed every second for 90 minutes with the desktop in use (a browser, an
# editor, the desktop apps), 61 rises counted (the fill tests, the 3 minutes after each and the moments the tests' own
# memory moved left out): by 216 MiB at most within 30 s (a browser, a desktop app and the window manager within 4 s),
# rounded up.
FLOOR_MIB = 490
SWAY_MIB = 220
MARGIN_MIB = FLOOR_MIB + SWAY_MIB  # left free at the peak with everything the plan puts on the GPU there

# the parts (`Need.part`, `Plan.gpu`), and the order they go to the processor in when the room is short: the least
# lost first (the module's docstring; docs/OFFLINE_VERIFICATION.md, "One judgement at the start", 2026-11-22)
TRANSLATOR, READERS, LAMA, LAYOUT = "translator", "readers", "lama", "layout"
TO_PROCESSOR = (READERS, LAMA, LAYOUT, TRANSLATOR)

# why the session's plan is as it is (`Plan.why`)
ROOM, SHORT, PROCESSOR, NO_GPU = "room", "short", "processor", "no_gpu"
# why the readers are where they are (`Placement.why`)
SET, NO_CUDA, UNKNOWN, FAILED, RELEASED, NOT_ASKED = "set", "no_cuda", "unknown", "failed", "released", "not_asked"


@dataclass(frozen=True)
class Placement:
    """Where the readers run: *device* "gpu" or "cpu", *why* (`ROOM`, `PROCESSOR`, `SET`, ...), *room* the MiB the
    plan found left at the peak (None where it did not measure), *error* the failure's type name (`FAILED`)."""

    device: str
    why: str
    room: int | None = None
    error: str = ""


@dataclass(frozen=True)
class Loaded:
    """A model the translation program holds in the card's memory now (/api/ps) other than the one the session
    translates with: its Ollama *name*, its MiB there (``size_vram``), and whether it is one of TASlation's own
    (*ours*: `translate.models.MODELS`, or the model the settings name), which the start's dialog offers to release."""

    name: str
    mib: int
    ours: bool = False


@dataclass(frozen=True)
class GpuFacts:
    """What the judgement stands on, in MiB: the card's *total* and *used* memory (all programs), *own* this process's
    now (0 without a CUDA context), *translator_now* what of the translation model's need is on the card now (its
    share there by /api/ps, the runner's own memory with it; a load of it at another context, which the server loads
    again, by /api/ps alone), whether Ollama *answered* /api/ps (False: taken for a model not loaded), and the other
    models the translation program holds there (*loaded*, `Loaded`: other programs' memory, counted in `others`)."""

    total: int
    used: int
    own: int = 0
    translator_now: int = 0
    answered: bool = True
    loaded: tuple[Loaded, ...] = ()

    @property
    def others(self) -> int:
        """What other programs hold now: the used memory that is not TASlation's."""
        return max(0, self.used - self.own - self.translator_now)

    @property
    def releasable(self) -> tuple[str, ...]:
        """The names of TASlation's own models among *loaded*: what the start's dialog can release."""
        return tuple(m.name for m in self.loaded if m.ours)


@dataclass(frozen=True)
class Need:
    """A part the settings put on the GPU (*part*: `TRANSLATOR`, `READERS`, `LAMA`, `LAYOUT`), its *mib* there at its
    peak, whether a setting *fixed* it there (never sent to the processor for the room), and the *extra* of *mib* it
    can do without and stay there (the readers' CUDA graphs: `judge` leaves it off, unasked, where the room is short
    with it)."""

    part: str
    mib: int
    fixed: bool = False
    extra: int = 0

    def bare(self) -> "Need":
        """The need without its *extra*."""
        return Need(self.part, self.mib - self.extra, self.fixed) if self.extra else self


@dataclass(frozen=True)
class Plan:
    """The session's placement: the parts on the GPU (*gpu*), those the room sent to the processor (*cpu*, in
    `TO_PROCESSOR`'s order), the MiB the start was *short* by with every part the settings put on the GPU there (0:
    enough), the MiB *left* at the peak with *gpu* there (None: not measured), *why* (`ROOM`, `SHORT`, `PROCESSOR`,
    `NO_GPU`), the parts that *could* go to the processor (not fixed by a setting, in that order), whether a setting
    *forced* a part onto the GPU (``ocr_runs_on`` "gpu", a number of layers in ``ollama_num_gpu``), and whether the
    readers on the GPU replay their CUDA *graphs* (`taslation.ocr.graphs`: False where the room was short with them -
    the needs' *extra* - and everything else was judged without them)."""

    gpu: tuple[str, ...] = ()
    cpu: tuple[str, ...] = ()
    short: int = 0
    left: int | None = None
    why: str = ROOM
    could: tuple[str, ...] = ()
    forced: bool = False
    graphs: bool = True

    @property
    def asks(self) -> bool:
        """Whether the start asks (`ui.dialogs.gpu_short`): short, nothing sent to the processor yet, something that
        could go, and no setting that forced a part onto the GPU (the person took the GPU into their own hands: the
        start goes on as the settings say, and the System page says by how much it is short)."""
        return self.short > 0 and not self.cpu and bool(self.could) and not self.forced


def left_at_peak(facts: GpuFacts, needs: Iterable[Need]) -> int:
    """THE JUDGEMENT's number: the MiB left on the card at TASlation's peak with *needs* on the GPU - the total, less
    what other programs hold now, less every need and, with a part of this process's there, its CUDA context."""
    needs = list(needs)
    context = CONTEXT_MIB if any(n.part != TRANSLATOR for n in needs) else 0
    return facts.total - facts.others - sum(n.mib for n in needs) - context


def short_by(facts: GpuFacts, needs: Iterable[Need]) -> int:
    """The MiB the card is short by with *needs* on the GPU (`left_at_peak` below `MARGIN_MIB`); 0: enough."""
    return max(0, MARGIN_MIB - left_at_peak(facts, needs))


def judge(facts: GpuFacts | None, needs: Iterable[Need], choice: str = "ask") -> Plan:
    """The plan for *needs* on *facts*: everything on the GPU when it is enough; short, as it is (`SHORT`, which
    `Plan.asks` about where no setting forced a part there) unless *choice* is "processor" - then the parts in
    `TO_PROCESSOR`'s order that are not fixed go to the processor, one by one, until the rest is enough or none is left
    (`PROCESSOR`). Before any of that, short with the needs' *extra* (the readers' CUDA graphs), they are left off,
    unasked, and the rest judged without them (`Plan.graphs` False): the readers stay on the GPU without their graphs
    rather than move; where parts went to the processor after all, the graphs are kept if the rest has room for them
    there. Without facts (no NVIDIA GPU): as the settings say, nothing judged (`NO_GPU`)."""
    needs = list(needs)
    forced = any(n.fixed for n in needs)
    if facts is None:
        return Plan(tuple(n.part for n in needs), why=NO_GPU, forced=forced)
    full, graphs = needs, True
    if any(n.extra for n in needs) and short_by(facts, needs):
        needs, graphs = [n.bare() for n in needs], False
    could = tuple(p for p in TO_PROCESSOR if any(n.part == p and not n.fixed for n in needs))
    short = short_by(facts, needs)
    if not short or choice != "processor" or not could:
        return Plan(tuple(n.part for n in needs), (), short, left_at_peak(facts, needs), SHORT if short else ROOM,
                    could, forced, graphs)
    moved: list[str] = []
    for part in could:
        needs = [n for n in needs if n.part != part]
        moved.append(part)
        if not short_by(facts, needs):
            break
    kept = [n for n in full if n.part not in moved]
    if not graphs and any(n.extra for n in kept) and not short_by(facts, kept):
        needs, graphs = kept, True
    return Plan(tuple(n.part for n in needs), tuple(moved), short, left_at_peak(facts, needs), PROCESSOR, could,
                forced, graphs)


def make_plan(settings: Any, choice: str = "ask", cuda: bool | None = None,
              facts: Callable[[Any], GpuFacts | None] | None = None) -> Plan:
    """`judge` on the facts of the moment (`gather`) and the needs of *settings* (`needs`); without facts (no NVIDIA
    GPU) nothing is judged (`NO_GPU`)."""
    found = (facts or gather)(settings)
    if found is None:
        return Plan(why=NO_GPU)
    return judge(found, needs(settings, cuda), choice)


# ------------------------------------------------------------------ the session's plan
_plan: Plan | None = None
_failed: dict[str, str] = {}  # part -> the type name of its failure on the GPU this session (`failed`)
_plan_lock = threading.Lock()


def settle(plan: Plan) -> Plan:
    """*plan* is the session's from now on (the window's start; `plan_for`). Said in the log, numbers only."""
    global _plan
    with _plan_lock:
        _plan = plan
    LOG.info("the GPU for this session: %s on the GPU, %s on the processor for the room (%s); short by %s MiB at the "
             "start, %s MiB left at the peak%s", ", ".join(plan.gpu) or "nothing", ", ".join(plan.cpu) or "nothing",
             plan.why, plan.short, "?" if plan.left is None else plan.left,
             "" if plan.graphs or READERS not in plan.gpu else "; the readers without their CUDA graphs for the room")
    return plan


def session() -> Plan | None:
    """The session's plan, None before one was made."""
    return _plan


def plan_for(settings: Any) -> Plan:
    """The session's plan; where none was made yet (a command, a tool: nothing can ask), made now from *settings*
    as "Start on the processor" makes it (`make_plan` with "processor") and settled."""
    with _plan_lock:
        plan = _plan
    if plan is None:
        try:
            plan = make_plan(settings, "processor")
        except Exception as e:  # noqa: BLE001 - nothing to judge on: as the settings say
            LOG.info("the GPU's room could not be judged (%s): as the settings say", type(e).__name__)
            plan = Plan(why=NO_GPU)
        settle(plan)
    return plan


def reset() -> None:
    """No plan and no failure (a new session in the same process: the tests)."""
    global _plan
    with _plan_lock:
        _plan = None
        _failed.clear()


def failed(part: str, why: str) -> None:
    """THE NET: *part*'s work failed on the GPU (*why*, the type name): it is on the processor for the rest of the
    session (`on_gpu`), and the System page says so."""
    with _plan_lock:
        if part in _failed:
            return
        _failed[part] = why or "RuntimeError"
    LOG.info("the %s failed on the GPU (%s): on the processor for the rest of the session", part, why)


def failure(part: str) -> str:
    """The type name of *part*'s failure on the GPU this session, "" for none."""
    return _failed.get(part, "")


def on_gpu(part: str) -> bool:
    """Whether *part* (`LAMA`, `LAYOUT`) may run on the GPU this session: not after a failure there (`failed`), and
    only where the session's plan has it there - without a plan (a test, a part made before one), as the settings
    say. (Torch's CUDA is the caller's to ask.)"""
    if part in _failed:
        return False
    plan = _plan
    return plan is None or plan.why == NO_GPU or part in plan.gpu


def graphs_on() -> bool:
    """Whether the readers' copies on the GPU capture their CUDA graphs (`taslation.ocr.graphs.wanted`): as the
    session's plan says (`Plan.graphs`); without a plan (a test, a tool's own readers), yes."""
    plan = _plan
    return plan is None or plan.graphs


PLAIN_BESIDE = True  # (a tool's switch: False reads every copy without graphs on the CPU through a request, as before)


def plain_beside_requests() -> bool:
    """Whether a reader's GPU copy without its CUDA graphs reads on the GPU while a request to the translation model is
    under way (`DeviceModels.run`): yes where the session's plan has room for what it put on the GPU (`Plan.left` at
    least `MARGIN_MIB`, the graphs left off for the room or not; without a plan, or nothing judged, yes) - the plain
    pass needs no memory beyond the copy's own, counted in its need; no where the start was short and went on all the
    same (a setting forced a part onto the GPU, or nothing could go to the processor), where the driver moves memory
    and the plain pass's many launches wait for the translator's time slices: it reads on the CPU meanwhile, as
    before."""
    if not PLAIN_BESIDE:
        return False
    plan = _plan
    return plan is None or plan.why == NO_GPU or plan.left is None or plan.left >= MARGIN_MIB


def translator_on_processor() -> bool:
    """Whether the session's plan sent the translation model to the processor (`taslation.translate.models`: its
    requests then carry ``num_gpu`` 0)."""
    plan = _plan
    return plan is not None and TRANSLATOR in plan.cpu


def readers_placement(settings: Any, cuda: bool | None = None) -> Placement:
    """Where the readers of *settings* run now: on the CPU after a failure this session (`FAILED`), as ``ocr_runs_on``
    "cpu" or "gpu" says (`SET`; no CUDA: `NO_CUDA`), else as the session's plan has them (`plan_for`: `ROOM`,
    `PROCESSOR`); on the CPU where the plan could not judge (CUDA but no figures of the card's memory) or did not
    count them (set by hand at the start), `UNKNOWN`, until the next start."""
    if READERS in _failed:
        return Placement("cpu", FAILED, error=_failed[READERS])
    setting = str(getattr(settings, "ocr_runs_on", "auto") or "auto")
    if setting == "cpu":
        return Placement("cpu", SET)
    if cuda is None:
        from ..render.artwork import has_cuda

        cuda = has_cuda()
    if not cuda:
        return Placement("cpu", NO_CUDA)
    if setting == "gpu":
        return Placement("gpu", SET)
    plan = plan_for(settings)
    if plan.why == NO_GPU:
        return Placement("cpu", UNKNOWN)
    if READERS in plan.gpu:
        return Placement("gpu", ROOM, plan.left)
    if READERS in plan.cpu:
        return Placement("cpu", PROCESSOR, plan.left)
    return Placement("cpu", UNKNOWN)


# ------------------------------------------------------------------ the needs and the facts
def readers_need(settings: Any) -> int:
    """What the readers that go to the GPU need there, in MiB, by the readers installed, their CUDA graphs with them
    (`readers_graphs`)."""
    from .readers import missing_readers

    return CHARSPOT_MIB + (0 if missing_readers(settings.models_dir) else NAR_MIB) + readers_graphs(settings)


def readers_graphs(settings: Any = None) -> int:
    """Of `readers_need`, the MiB of the readers' CUDA graphs (`taslation.ocr.graphs`, `READERS_GRAPHS_MIB`: nar's
    in charspot's pool take nothing more; 0 where none are captured, ``graphs.ENABLED`` off)."""
    from . import graphs

    return READERS_GRAPHS_MIB if graphs.ENABLED else 0


def needs(settings: Any, cuda: bool | None = None, ask: bool = True) -> list[Need]:
    """What *settings* put on the GPU (`Need`s): the translation model unless ``ollama_num_gpu`` is 0 (fixed with a
    number of layers), and where torch has CUDA (*cuda*: `artwork.has_cuda` when None) the readers unless
    ``ocr_runs_on`` is "cpu" (fixed with "gpu"; their CUDA graphs the need's *extra*), LaMa and the layout model
    where the pipeline runs them (`page_models_on_gpu`). *ask*: False counts the translation model as not loaded,
    Ollama not asked."""
    from ..translate.ollama import num_gpu_value

    out: list[Need] = []
    try:
        layers = num_gpu_value(getattr(settings, "ollama_num_gpu", ""))
    except ValueError:
        layers = None
    if layers != 0:
        need, _now, _answered = _translator_need(settings, ask=ask)
        if need:
            out.append(Need(TRANSLATOR, int(need), fixed=layers is not None))
    if cuda is None:
        from ..render.artwork import has_cuda

        cuda = has_cuda()
    if not cuda:
        return out
    setting = str(getattr(settings, "ocr_runs_on", "auto") or "auto")
    if setting != "cpu":
        out.append(Need(READERS, readers_need(settings), fixed=setting == "gpu", extra=readers_graphs(settings)))
    lama, layout = page_models_on_gpu(settings)
    if lama:
        out.append(Need(LAMA, LAMA_TALL_MIB if tall_screen() else LAMA_MIB))
    if layout:
        out.append(Need(LAYOUT, LAYOUT_MIB))
    return out


# translation models seen loaded this session -> MiB they need: (name, num_ctx, layers, KV type, full window)
_learnt: dict[tuple[str, int, int | None, str, bool], int] = {}


def gather(settings: Any, memory: tuple[int, int] | None = None, own: int | None = None,
           ask: bool = True) -> GpuFacts | None:
    """The facts of the moment for *settings* (the module's docstring); None when the card's memory cannot be read
    (no NVIDIA GPU). *memory* and *own*: the card's (total, used) and this process's MiB as `snapshot` reads them
    together (read now when None); *ask*: False counts the translation model as not loaded, Ollama not asked."""
    if memory is None:
        memory, own = snapshot()
    if memory is None:
        return None
    total, used = memory
    _need, now, answered, loaded = _translator_facts(settings, ask=ask)
    own = own_mib() if own is None else own
    return GpuFacts(total, used, own, now, answered, loaded)


FREED_S = 3.0  # Release and check again: the card's used memory followed this long at most for what was released
FREED_SHARE = 0.8  # ... until it fell by this share of what /api/ps said the models held (`wait_freed`)


def wait_freed(before: tuple[int, int] | None, mib: int, timeout: float = FREED_S) -> bool:
    """Once Ollama no longer lists the models released (*mib* of the card's memory by /api/ps), until the card's used
    memory (`card_memory`, read as *before* the release) shows it: fallen by `FREED_SHARE` of it, *timeout* seconds at
    most (the runner's process ends, then the driver frees its memory). Whether it did; True with nothing to wait
    for."""
    if before is None or mib <= 0:
        return True
    end = time.monotonic() + timeout
    while True:
        now = card_memory()
        if now is None or before[1] - now[1] >= mib * FREED_SHARE:
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(0.1)


def snapshot(tries: int = 3) -> tuple[tuple[int, int] | None, int]:
    """The card's (total, used) memory and this process's own (`own_mib`) read together: this process's read before
    and after the card, and all of it again while that changed between, at most *tries* times."""
    memory: tuple[int, int] | None = None
    own = 0
    for _attempt in range(tries):
        before = own_mib()
        memory = card_memory()
        own = own_mib()
        if own == before:
            break
    return memory, own


def server_cache(settings: Any) -> tuple[str, bool]:
    """The KV cache type and whether the window cache is full-size of the Ollama at the address of *settings*
    (`taslation.ollama_start.server_cache`: as TASlation started it, else as the variables say)."""
    from ..ollama_start import server_cache as of

    return of(getattr(settings, "ollama_url", ""), getattr(settings, "state_dir", None))


def known_translator(name: str, num_ctx: int, cache: tuple[str, bool]) -> tuple[int, int] | None:
    """(MiB it adds, /api/ps MiB) measured for the model *name* at *num_ctx* on a server with *cache* (KV type, full
    window; a KV type not measured counts as `DEFAULT_KV`, then as the model's largest); None for a model not
    measured."""
    table = KNOWN_TRANSLATORS.get((name, int(num_ctx)))
    if not table:
        return None
    kv, full = cache
    return table.get((kv, bool(full))) or table.get((DEFAULT_KV, bool(full))) or max(table.values())


def known_for_size(name: str, num_ctx: int, size_mib: int) -> int | None:
    """What the model *name* at *num_ctx*, loaded with an /api/ps size of *size_mib*, was measured to add: that of the
    server's cache with the smallest size that holds it; None for a model not measured, or larger than every cache
    measured."""
    fits = [mib for mib, size in KNOWN_TRANSLATORS.get((name, int(num_ctx)), {}).values() if size_mib <= size]
    return min(fits) if fits else None


def tall_screen() -> bool:
    """Whether the tallest screen on the desktop is taller than `LAMA_SCREEN_PX` (`devices.screen_height_px`), or its
    height cannot be read: the frames LaMa's windows come from are as tall as the viewer's window."""
    from ..devices import screen_height_px

    height = screen_height_px()
    return height is None or height > LAMA_SCREEN_PX


def card_memory() -> tuple[int, int] | None:
    """(total, used) MiB of the first GPU, all programs: NVML; where there is none, torch's figure once CUDA is in use
    (the card's own where the driver is not Windows'). None when neither answers."""
    from ..devices import nvml_usage_mib

    found = nvml_usage_mib()
    if found is not None:
        return found
    torch = sys.modules.get("torch")
    if torch is None or sys.platform == "win32":
        return None
    try:
        free, total = torch.cuda.mem_get_info()
    except Exception:  # noqa: BLE001 - no CUDA after all
        return None
    return int(total // MiB), int((total - free) // MiB)


def own_mib() -> int:
    """This process's GPU memory now: torch's reserved memory and its CUDA context; 0 while it has none."""
    torch = sys.modules.get("torch")
    try:
        if torch is None or not torch.cuda.is_initialized():
            return 0
        return CONTEXT_MIB + int(torch.cuda.memory_reserved() // MiB)
    except Exception:  # noqa: BLE001
        return 0


def translator_need(settings: Any) -> tuple[int | None, int]:
    """(what the translation model of *settings* needs on the GPU at the peak, what of it is there now), in MiB; None
    for a need not known. Ollama is asked /api/ps, which never loads a model; a server that does not answer is a model
    not loaded."""
    need, now, _answered = _translator_need(settings)
    return need, now


def _translator_need(settings: Any, cache: tuple[str, bool] | None = None,
                     ask: bool = True) -> tuple[int | None, int, bool]:
    """`translator_need`, and whether Ollama answered /api/ps (True where nothing was asked of it); the model counted
    on a server with *cache* (KV type, full window; `server_cache` when None); *ask* False: as not loaded, Ollama not
    asked."""
    need, now, answered, _loaded = _translator_facts(settings, cache, ask)
    return need, now, answered


def _translator_facts(settings: Any, cache: tuple[str, bool] | None = None,
                      ask: bool = True) -> tuple[int | None, int, bool, tuple[Loaded, ...]]:
    """`_translator_need` and the other models the translation program holds on the card (`Loaded`), from one look
    at /api/ps. What of the need is there now (`GpuFacts.translator_now`): with the model loaded as the requests ask
    for it (`OllamaTranslator.loaded_as_asked`), the need times /api/ps's share of it on the GPU - the runner's own
    memory, which /api/ps leaves out and the card's used memory has, is the need's as well, and so it is not counted
    as other programs' memory beside it; loaded otherwise (another context: the server loads it again for the first
    request, freeing what it holds), what /api/ps says it holds, and the need as before a load."""
    from ..translate import TranslationError
    from ..translate.models import make_translator, wanted_name
    from ..translate.ollama import num_gpu_value, of_model

    try:
        layers = num_gpu_value(getattr(settings, "ollama_num_gpu", ""))
    except ValueError:
        layers = None
    if layers == 0:
        return 0, 0, True, ()  # (the processor only: nothing asked)
    try:
        name = wanted_name(settings.ollama_model, settings.target_language)
        translator = make_translator(settings, name)
        num_ctx = int(getattr(translator, "num_ctx", 0) or 0)
    except (TranslationError, ValueError, AttributeError):
        return None, 0, True, ()
    kv, full = server_cache(settings) if cache is None else cache
    key = (name, num_ctx, layers, str(kv), bool(full))
    answered, entries = True, []
    try:
        entries = translator._ps_models() if ask else []
    except (TranslationError, OSError, ValueError):
        answered = False
    entry, held = of_model(entries, name), 0
    loaded = other_models(settings, entries, name)
    if entry and entry.get("size") and entry.get("size_vram") is not None:
        on = int(entry["size_vram"]) // MiB
        if translator.loaded_as_asked(entry):
            base = int(entry["size"]) // MiB if layers is None else on
            # the runner's own memory beside what /api/ps counts (in the used memory while it is loaded) is counted
            # in: as measured for a known model with the server's cache of the size it had
            known = known_for_size(name, num_ctx, base) if layers is None else None
            need = _learnt[key] = known if known is not None else round(base * RUNNER_SHARE)
            return need, (min(need, round(need * on / base)) if base > 0 else 0), True, loaded
        held = on  # (loaded at another context: what it holds goes as the server loads it again)
    if key in _learnt:
        return _learnt[key], held, answered, loaded
    measured = known_translator(name, num_ctx, (str(kv), bool(full))) if layers is None else None
    if measured:
        return measured[0], held, answered, loaded
    size = _file_mib(translator, name) if ask and answered else None
    return (round(size * UNKNOWN_SHARE) if size else None), held, answered, loaded


def other_models(settings: Any, entries: Iterable[dict[str, Any]], name: str) -> tuple[Loaded, ...]:
    """The models of the /api/ps *entries* other than *name* that hold some of the card's memory, the largest first
    (`Loaded`; *ours*: one of TASlation's models, or the one *settings* name)."""
    from ..ollama_start import is_ours, own_models
    from ..translate.ollama import entry_name, same_model

    own = own_models(settings)
    out = []
    for entry in entries:
        other = entry_name(entry)
        try:
            mib = int(entry.get("size_vram") or 0) // MiB
        except (TypeError, ValueError):
            mib = 0
        if other and mib > 0 and not same_model(other, name):
            out.append(Loaded(other, mib, is_ours(other, own)))
    return tuple(sorted(out, key=lambda m: (-m.mib, m.name)))


def _file_mib(translator: Any, name: str) -> int | None:
    """The size of the model *name*'s file as Ollama lists it (/api/tags), MiB; None when it is not listed or Ollama
    does not answer."""
    try:
        data = translator._request_once("/api/tags", timeout=3.0)
    except Exception:  # noqa: BLE001 - not known
        return None
    for model in data.get("models", []) if isinstance(data, dict) else []:
        if model.get("name") in (name, f"{name}:latest") and model.get("size"):
            return int(model["size"]) // MiB
    return None


def page_models_on_gpu(settings: Any) -> tuple[bool, bool]:
    """Whether LaMa and the layout model of *settings* run on the GPU, by the pipeline's own rules (`artwork.available`
    on a computer with CUDA; the layout model with "on", or with "auto" where LaMa runs)."""
    from ..detect import layout
    from ..render import artwork

    models_dir = settings.models_dir
    lama = getattr(settings, "erase_mode", "fill") == "fill" and artwork.available(
        models_dir, getattr(settings, "art_erase", "auto"), cuda=True)
    wanted = getattr(settings, "detect_model", "auto")
    return lama, (wanted == "on" or (wanted == "auto" and lama)) and layout.available(models_dir)


# ------------------------------------------------------------------ the networks on a device
def device_copy(module: Any, device: str, memory_format: Any = None) -> Any:
    """A copy of the torch *module* with its tensors on *device*, the bits as they are (no float is recomputed); the
    CPU's tensors are left where they are, and are not copied on the CPU first. *memory_format*: that of its 4-D
    weights there."""
    import copy

    import torch

    memo: dict[int, Any] = {}
    for p in module.parameters():
        data = p.detach().to(device)
        if memory_format is not None and data.dim() == 4:
            data = data.contiguous(memory_format=memory_format)
        memo[id(p)] = torch.nn.Parameter(data, requires_grad=p.requires_grad)
    for b in module.buffers():
        memo[id(b)] = b.to(device)
    for value in vars(module).values():  # tensors kept beside the module's own (`NarNet.prepare`)
        _plain_tensors(value, device, memo)
    for sub in module.modules():
        for value in vars(sub).values():
            _plain_tensors(value, device, memo)
    return copy.deepcopy(module, memo)


def _plain_tensors(value: Any, device: str, memo: dict[int, Any]) -> None:
    import torch

    if isinstance(value, torch.Tensor) and not isinstance(value, torch.nn.Parameter) and id(value) not in memo:
        memo[id(value)] = value.to(device)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _plain_tensors(item, device, memo)


_translating = 0  # requests to the translation model under way (`translating`)
_translating_lock = threading.Lock()


@contextlib.contextmanager
def translating() -> Iterator[None]:
    """While a request to the translation model is under way: the readers' GPU copies read on the GPU meanwhile, but
    one without CUDA graphs where the start was short of room (`plain_beside_requests`), which reads on the CPU then,
    its copy kept. Windows shares the GPU between Ollama's process and this one in time slices: a crop read by the
    plain pass, a few hundred kernels launched one by one, waits for the translator's slice at some of them (charspot
    23.4 and nar 47 ms a crop through back-to-back requests, 2026-11-28, against 182 and 487 on the CPU; once 687 ms,
    both readers, against 127 on the CPU, on a card past its memory), a graph's replay is one launch (18.6 and 39). The
    readings are the same on either device."""
    global _translating
    from .. import analysis

    with _translating_lock:
        _translating += 1
    began = time.perf_counter()
    try:
        yield
    finally:
        with _translating_lock:
            _translating -= 1
        analysis.requested(began, time.perf_counter())  # (the analysis log: when the translator computed)


def graphed(networks: tuple[Any, ...]) -> bool:
    """Whether a reader's GPU copy *networks* holds its CUDA graphs (`taslation.ocr.graphs.Graphs`, any kept: none
    where the plan left them off or a replay failed and dropped them)."""
    from . import graphs

    return any(isinstance(m, graphs.Graphs) and len(m) > 0 for m in networks)


def out_of_memory(error: BaseException) -> bool:
    """Whether *error* is the GPU's memory running out (torch's ``OutOfMemoryError``, or an error that says so, as
    CUDA's and its libraries' own do: "out of memory", "..._ALLOC_FAILED")."""
    text = str(error).lower()
    return type(error).__name__ == "OutOfMemoryError" or "out of memory" in text or "alloc_failed" in text


def give_back() -> None:
    """The GPU memory torch keeps cached for this process given back (its CUDA context stays)."""
    gc.collect()
    torch = sys.modules.get("torch")
    try:
        if torch is not None and torch.cuda.is_initialized():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001 - it stays cached, no more than that
        pass


class DeviceModels:
    """A reader's networks: the CPU's (``_cpu_models``, as loaded) and, while `to` has put them there, a copy on the GPU
    (``_copy_to``, the reader's, with its CUDA graphs: `taslation.ocr.graphs`, which go with it). `run` reads with the
    copy in force; a failure on the GPU (out of memory, a CUDA error: any RuntimeError there) drops the GPU's copy,
    says so to `on_gpu_failure` (the type name) and reads on the CPU, as it does for the rest of the session
    (``gpu_failed``)."""

    name = "reader"

    def __init__(self) -> None:
        self._cpu_models: tuple[Any, ...] = ()
        self._gpu: tuple[str, tuple[Any, ...]] | None = None  # (device, the copy)
        self.gpu_failed = ""  # the type name of the GPU's failure this session ("" none)
        self.on_gpu_failure: Callable[[str, str], Any] | None = None  # (reader's name, failure's type name)
        self._lock = threading.Lock()
        self._reading = 0  # reads on the GPU's copy under way
        self._give_back = False  # a copy was dropped while one read with it: its memory goes once that one is done

    @property
    def device(self) -> str:
        """Where the next read runs: "cpu", or the GPU's device ("cuda")."""
        held = self._gpu
        return held[0] if held is not None else "cpu"

    def _copy_to(self, device: str) -> tuple[Any, ...]:
        raise NotImplementedError

    def to(self, device: str) -> bool:
        """The reads on *device* from now on: "cpu" drops the GPU's copy (its memory given back once no read uses
        it); another (a CUDA device) makes the copy from the CPU's, where it is not there already. Whether the reads
        are on *device* now: a copy that cannot be made (out of memory, a GPU failed before) leaves them on the CPU."""
        if device == "cpu":
            with self._lock:
                dropped, self._gpu = self._gpu, None
                if dropped is not None and self._reading:
                    self._give_back = True
                    dropped = None
            if dropped is not None:
                dropped = None
                give_back()
            return True
        if self.gpu_failed:
            return False
        if self._gpu is not None and self._gpu[0] == device:
            return True
        why = ""
        try:
            copy = self._copy_to(device)
        except RuntimeError as e:
            why = type(e).__name__
        else:
            with self._lock:
                self._gpu = (device, copy)
            return True
        self._failed(why)  # (out of the except: its traceback holds the copy's tensors made so far)
        return False

    def run(self, read: Callable[[str, tuple[Any, ...]], T]) -> T:
        """*read*(device, networks) with the copy in force - through a request to the translation model too
        (`translating`), but for a copy without CUDA graphs (`graphed`) where the start was short of room
        (`plain_beside_requests`), which reads on the CPU meanwhile - and on the CPU from a failure on the GPU on (see
        the class)."""
        from .. import analysis

        with self._lock:
            copy = self._gpu
            beside = _translating > 0  # (a request under way as the read begins)
            held = copy if copy is not None and (not beside or graphed(copy[1]) or plain_beside_requests()) else None
            waiting = copy is not None and held is None  # (its GPU copy waits for the translator)
            if held is not None:
                self._reading += 1
        began = time.perf_counter()
        if held is None:
            try:
                return read("cpu", self._cpu_models)
            finally:
                analysis.reader(self.name, time.perf_counter() - began, "cpu", waiting)
        why = ""
        device = held[0]
        try:
            return read(*held)
        except RuntimeError as e:
            why = type(e).__name__
        finally:
            held = None
            analysis.reader(self.name, time.perf_counter() - began, device, beside)
            with self._lock:
                self._reading -= 1
                late = self._give_back and not self._reading
                if late:
                    self._give_back = False
            if late:
                give_back()
        self._failed(why)
        began = time.perf_counter()
        try:
            return read("cpu", self._cpu_models)
        finally:
            analysis.reader(self.name, time.perf_counter() - began, "cpu")

    def _failed(self, why: str) -> None:
        """The GPU failed (*why*, the type name): its copy dropped, the reads on the CPU for the rest of the session,
        and `on_gpu_failure` told."""
        LOG.info("the OCR reader %s failed on the GPU (%s): on the CPU for the rest of the session", self.name, why)
        self.gpu_failed = why or "RuntimeError"
        self.to("cpu")
        tell = self.on_gpu_failure
        if tell is not None:
            try:
                tell(self.name, self.gpu_failed)
            except Exception:  # noqa: BLE001 - the crop is read all the same
                pass
