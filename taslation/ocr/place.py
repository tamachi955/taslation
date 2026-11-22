"""Where the OCR readers run: on the GPU when it has room for them at TASlation's peak, else on the CPU.

The setting ``ocr_runs_on``: "cpu" (always the CPU, as before), "gpu" (the GPU wherever torch has CUDA) or "auto", the
default: the GPU only when, beside everything else TASlation keeps there at its peak - the translation model whole in
video memory, LaMa and the layout model when the settings use them, this process's CUDA context - and beside what
other programs hold now, the readers at their own measured peak leave `MARGIN_MIB` free (`room_left`, the rule):
`RETURN_MIB` for readers on the CPU to go there, `MARGIN_MIB` for readers there to stay (`judge`'s *staying*). A card
of less than `MIN_TOTAL_MIB` is never asked. The readers on the GPU are charspot and nar (`CHARSPOT_MIB`, `NAR_MIB`);
CPT, the third, which reads a line only where those two differ, stays on the CPU: its 440 MB of weights would be on
the GPU for a few crops a page.

What a fuller card does (Windows' driver model; GTX 1660 Ti 6 GB, driver 610.88, Ollama 0.40.16, measured 2026-11-22
with a process that held dummy memory, step by step, beside the model and the readers): nothing fails. No allocation
ran out of memory, the readers' copy to the GPU and Ollama's load among them, with 17.7 GB held on the 6 GB card; and
Ollama loads the model whole whatever other processes hold - neither its "gpu memory available" nor llama.cpp's fit
("projected to use 1981 MiB of device memory vs. 5134 MiB of free device memory") sees another process's memory, so
its layers never move to the CPU because of the readers or of other programs. What happens instead is that the driver
keeps some of the card free (`FLOOR_MIB`) and moves the memory of processes that are not computing just then into the
computer's own, and back at their next turn: with the model loaded, the readers reading and the card more than full,
each request to the model began 0.2-0.5 s later (its cached prompt read in 0.21-0.53 s instead of 0.01-0.07, 490-1150
MiB of the runner moved), and with another program at work on its own memory the readers read 3.5 to 4.5 times slower
(charspot 52-55 ms a crop instead of 15, nar 110-113 instead of 25 - slower than on the CPU, 28 and 73). The rule
keeps it from coming to that: it counts the model whole beside the readers, the page models at their peaks and what
other programs hold, and leaves free the driver's part and the most other programs were seen to grow between two
looks (`SWAY_MIB`). So the readers never take the translation model's room: it is counted as if it were loaded,
whether it is or not, at the most it was measured to take.

The rule looks again while the readers read where it put them, every `LOOK_S` (`Readers._check`, on a thread of its
own: a look costs NVML and an /api/ps, the read does not wait for it), so that other programs that grew send them to
the CPU, and room that came back brings them again. The run-time net: an out of memory on the GPU sends them to the
CPU until the GPU memory is next let go, the second of a session for the rest of it (`FULLS_FOR_GOOD`); reads that
crawl there - each of the last `SLOW_READS` slower than `SLOW_FACTOR` times the CPU's (`crawling`) - send them to the
CPU for the session too (`SLOW`), and the System page says so.

What the rule measures (`GpuFacts`, `gather`):

* the card's memory as NVIDIA's driver library sees it (`devices.nvml_usage_mib`, nothing loaded, no CUDA context
  made): on Windows torch's ``mem_get_info`` counts what this process holds alone (another process's 2 GB left its
  free memory as it was, measured), so it cannot see Ollama or other programs; where there is no NVML (not Windows)
  torch's own figure, which is the card's there;
* what of the used memory is TASlation's own: Ollama's ``size_vram`` of the translation model (/api/ps, which never
  loads one) and this process's (torch's reserved memory and its CUDA context); the rest is other programs';
* what the translation model needs: /api/ps's ``size`` while it is loaded (``size_vram`` where ``ollama_num_gpu`` puts
  only some layers there on purpose; nothing for "0"), learnt for the session with the runner's own memory that
  /api/ps leaves out (for a known model, what it was measured to add with the server's cache whose /api/ps size is the
  smallest that holds it, below, which tells the server's cache apart whoever started it; else `RUNNER_SHARE`); before
  it is loaded, what it was measured to add to the card's used memory (`KNOWN_TRANSLATORS`, at the context the app
  asks for, with the KV cache type and the window cache the server has: `server_cache`); a model of the reader's own
  that was never seen loaded is not known, and the readers stay on the CPU (`UNKNOWN`) until it has been;
* where LaMa runs on the GPU, the tallest screen's height (`tall_screen`): its window grows with the lettering's size
  in pixels, and so with the frames the viewer's window gives (`LAMA_MIB`, `LAMA_TALL_MIB`).

The decision is made when the readers load (`Readers`, the window's start), again once the GPU memory was let go
(`Readers.release_gpu`: Tools > Release the model now, and before Ollama loads its model unless they stay through the
load, below; decided again at the next read) and when a setting it depends on changed. A GPU that fails moves the
readers to the CPU, and the crop at hand is read there (`DeviceModels.run`): after an out of memory until the GPU
memory is next let go, which decides again (other programs, or the translation model's load, took the room for a
time; the page models go on on the CPU until then too), after any other failure (a CUDA error) for the rest of the
session. The weights move without being read from disk again: the CPU's copy stays where it is loaded,
the GPU's is made from it and dropped (`to`).
While a request to the translation model is under way (`translating`, for the translator to wrap its requests in),
the readers read on the CPU: the two processes share the GPU in time slices, and the OCR's many small steps wait.
While Ollama loads the model (`loading`, the translator's load and warm-up) and while a request is under way
(`busy`), nothing is decided: during a load /api/ps and the card's used memory each count a part of the model, so the
room would be guessed wrong, and a copy to the GPU would take memory Ollama is loading into; the next read after it
decides. A load is no reason to read on the CPU: a crop read on the GPU while PLaMo loaded took 40 ms, as on an idle
GPU (38), against 134 on the CPU, which also made the load itself take 5.9 s instead of 4.6 (measured 2026-11-16).

So a load of the translation model keeps the readers on the GPU (`Readers.keeps_through_load`; the page models let go
before it as ever) where the rule put them there (`ROOM`: the setting's "gpu" lets them go, as before), with no GPU
failure this session, and where the rule asked again just then still finds room for them (`through_load`: `judge` on
the facts of that moment, every one of them measured - the card's memory, /api/ps answering, the model's need known -
for other programs may have grown since): the rule counts the model whole in video memory beside them and leaves
`MARGIN_MIB` free, so all of it fits on the card beside them without the driver moving any of it out (Ollama itself
would load it whole either way: it does not see them). They read on there through the load, and the decision stands.
Just before a load the readers are in the card's used memory and in this process's own alike, so that they count once,
as `peak_mib`'s *ocr*; the model is not loaded then (another model in Ollama counts as other programs' memory, as
ever). A load that all the same ends with the model partly on the CPU (`partly_loaded`: ``size_vram`` below ``size``
in the /api/ps the translator asks after it, the layers left to the server) found them in its way: they go to the CPU
at the release before the translator's second load, and no load keeps them again this session
(`keeps_through_loads`). Measured on the 6 GB card (2026-11-16, the app's own load, two rounds): PLaMo came up whole
beside the readers kept in 10 loads of 10 (/api/ps 1823 of 1823 MiB); with a page read meanwhile a crop took 43-47 ms
through the load against 146-226 on the CPU with them let go, and the load 5.0-5.3 s against 5.5-6.5 (once 7.1, the
first load of a round); alone 4.8-5.1 s kept, 5.1 let go; the readings were those of the CPU.

The Ollama TASlation starts asks the rule once, as it starts (`full_window_placements`, for
`taslation.ollama_start.server_setup`): where the readers would run with the translation model at its footprint
without the full-size window cache and with it (130 MiB more for PLaMo with q8_0, 220 with f16); the server gets the
cache unless only the second puts them on the CPU.
"""

from __future__ import annotations

import contextlib
import gc
import logging
import statistics
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, TypeVar

LOG = logging.getLogger(__name__)
MiB = 1024 * 1024
T = TypeVar("T")

SETTING_VALUES = ("auto", "cpu", "gpu")  # ``ocr_runs_on``

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
# this process's CUDA context with the libraries the networks load there (Windows' dedicated memory less torch's
# reserved): 77 MiB bare, 99 with all of them (2026-11-19); 76 bare, 86 with the readers' and the layout model's
# (2026-11-22). The largest, rounded up to 10 MiB.
CONTEXT_MIB = 100
# LaMa: its weights (204 MiB reserved, 12 of kernels) and what the window takes while it is filled. The window is the
# frame's own pixels around the region, 512 px a side or more for a larger region, so it grows with the screen: at the
# largest window met, 336 MiB on the dev snapshots' frames (658x512) and 348 on 2560x1440 (815x512), 552 and 564 in
# all - `LAMA_MIB`, for screens up to `LAMA_SCREEN_PX` high (`GpuFacts.tall_screen`); 588 on 3840x2160 (1188x512), 804
# in all - `LAMA_TALL_MIB`, for a taller screen or one not known. What a window leaves idle in torch's cache is given
# back after it (`artwork.give_back_idle`): kept, the blocks of each window size piled up to 2.4 GB in a session.
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
# What the rule leaves free at the peak (the module's docstring: what a fuller card does), measured on the 6 GB card
# (2026-11-22). FLOOR_MIB: what NVIDIA's driver keeps free of the card - with less left, it moves the memory of a
# process that is not computing just then into the computer's own (Ollama's runner while the OCR reads, the readers
# while the model translates), and that process pays for it at its next turn. Filling the card step by step, it began
# to with 337 to 484 MiB of NVML's free memory left, never with 527 or more; the highest, 484, rounded up. SWAY_MIB: how
# far other programs' memory rose between two looks of the rule (`LOOK_S`), followed every second for 90 minutes with
# the desktop in use (a browser, an editor, the desktop apps), 61 of them counted (the fill tests, the 3 minutes after
# each and the moments the tests' own memory moved left out): by 216 MiB at most within 30 s (a browser, a desktop app and the window manager within 4 s),
# rounded up. STEP_MIB, the hysteresis: their rise within 30 s at the 99th percentile, 71 MiB, rounded up to 100 -
# their usual swing alone moves nothing.
FLOOR_MIB = 490
SWAY_MIB = 220
STEP_MIB = 100
MARGIN_MIB = FLOOR_MIB + SWAY_MIB  # left free at the peak for readers on the GPU to stay there
RETURN_MIB = MARGIN_MIB + STEP_MIB  # ... for readers on the CPU to go there
# Seconds between looks at the room while the readers read where the rule put them (`Readers._check`, on a thread of
# its own): a look (`gather`) took 31 ms with TASlation's Ollama there (the median of 30, 47 at most; NVML's part 15),
# 0.1 % of a processor's time at one look in 30 s; with no Ollama there 2.1-2.4 s, Windows refusing the connection,
# which the read never waits for (`Readers._look_again`).
LOOK_S = 30.0
FULLS_FOR_GOOD = 2  # the out of memory of a session that keeps the readers on the CPU for the rest of it
MIN_TOTAL_MIB = 5 * 1024  # a smaller card is the translator's and the page models'
# The run-time net (`crawling`, `DeviceModels.run`): the last `SLOW_READS` reads on the GPU each more than
# `SLOW_FACTOR` times the median of the reader's reads on the CPU (`CPU_READS` of them at least) send the readers to the
# CPU for the session (`SLOW_GPU`, why `SLOW`). On an idle GPU a crop takes charspot 15 ms and nar 25 (medians of the
# 509 and 206 crops), on this computer's CPU 28 and 73: a GPU read slower than twice the CPU's is four to six times
# slower than its own, which no wait behind this process's page models makes of eight reads in a row. The processor's times are
# those of the reads while the translation model computes (on the CPU anyway) and during its load (`DeviceModels.run`).
# On a card filled past its size by a program computing on it, reads took charspot 52-55 ms and nar 110-113, 1.5 to
# 1.9 times the CPU's: under the net, which is for a GPU far slower than that; the margin keeps the readers off such
# a card.
SLOW_READS = 8
CPU_READS = 3
SLOW_FACTOR = 2.0
SLOW_GPU = "SlowGpu"  # (the failure's name, as a type name is for the others)

# why the readers are where they are (`Placement.why`)
ROOM, SET, NO_CUDA, NO_ROOM, UNKNOWN, FAILED, RELEASED, NOT_ASKED, SLOW = (
    "room", "set", "no_cuda", "no_room", "unknown", "failed", "released", "not_asked", "slow")
LOOKED_AT = (ROOM, NO_ROOM, UNKNOWN)  # the rule's own placements, which a look every `LOOK_S` may change


@dataclass(frozen=True)
class Placement:
    """Where the readers run: *device* "gpu" or "cpu", *why* (`ROOM`, `SET`, ...), *room* the MiB the rule found left
    at the peak with the readers on the GPU (None where it did not measure), *error* the failure's type name
    (`FAILED`)."""

    device: str
    why: str
    room: int | None = None
    error: str = ""


@dataclass(frozen=True)
class GpuFacts:
    """What the rule decides on, in MiB: the card's *total* and *used* memory (all programs), *own* this process's now
    (0 without a CUDA context), *translator* what the translation model needs there at the peak (None: not known) and
    *translator_now* what of it is there now, whether *lama* and the *layout* model run on the GPU, whether Ollama
    *answered* /api/ps (False: taken for a model not loaded), and whether the tallest screen is taller than
    `LAMA_SCREEN_PX` or not known (*tall_screen*: LaMa's windows are larger there, `LAMA_TALL_MIB`)."""

    total: int
    used: int
    own: int = 0
    translator: int | None = 0
    translator_now: int = 0
    lama: bool = False
    layout: bool = False
    answered: bool = True
    tall_screen: bool = False


def peak_mib(facts: GpuFacts, ocr: int) -> int:
    """What TASlation holds on the GPU at its peak with the readers there (*ocr* MiB): the context, the translation
    model, the page models in use, the readers."""
    lama = (LAMA_TALL_MIB if facts.tall_screen else LAMA_MIB) if facts.lama else 0
    return CONTEXT_MIB + int(facts.translator or 0) + lama + (LAYOUT_MIB if facts.layout else 0) + int(ocr)


def room_left(facts: GpuFacts, ocr: int) -> int:
    """THE RULE's number: the MiB left on the card at TASlation's peak with the readers on it - the total, less what
    other programs hold now (the used memory that is not TASlation's), less `peak_mib`."""
    other = max(0, facts.used - facts.own - facts.translator_now)
    return facts.total - other - peak_mib(facts, ocr)


def judge(facts: GpuFacts | None, ocr: int, staying: bool = False) -> Placement:
    """"auto" on *facts*: the GPU when the card has `MIN_TOTAL_MIB` or more, the translation model's need is known and
    `room_left` is `RETURN_MIB` or more - `MARGIN_MIB` or more for readers the rule has on the GPU now (*staying*:
    the hysteresis, so that a room that sways about one figure does not move them to and fro); else the CPU, and
    why."""
    if facts is None:
        return Placement("cpu", UNKNOWN)
    if facts.total < MIN_TOTAL_MIB:
        return Placement("cpu", NO_ROOM)
    if facts.translator is None:
        return Placement("cpu", UNKNOWN)
    room = room_left(facts, ocr)
    fits = room >= (MARGIN_MIB if staying else RETURN_MIB)
    return Placement("gpu" if fits else "cpu", ROOM if fits else NO_ROOM, room)


def through_load(facts: GpuFacts | None, ocr: int) -> Placement:
    """The rule asked again just before Ollama loads the translation model (`Readers.keeps_through_load`): `judge` on
    *facts* for readers on the GPU (*staying*), but facts not all measured - Ollama not answering /api/ps among them -
    are a room not known. It counts the model whole beside them: neither Ollama nor llama.cpp's fit sees another
    process's memory on Windows (the module's docstring), so the room for the model at its load is this rule's alone
    to keep."""
    if facts is not None and not facts.answered:
        return Placement("cpu", UNKNOWN)
    return judge(facts, ocr, staying=True)


def failed_placement(failed: str) -> Placement:
    """Where readers that failed on the GPU this session (*failed*, the failure's type name) are: on the CPU, why
    `SLOW` for reads that crawled there (`SLOW_GPU`), else `FAILED`."""
    if failed == SLOW_GPU:
        return Placement("cpu", SLOW, error=failed)
    return Placement("cpu", FAILED, error=failed)


def decide(settings: Any, ocr: int, failed: str = "", cuda: bool | None = None,
           facts: Callable[[Any], GpuFacts | None] | None = None, staying: bool = False) -> Placement:
    """Where the readers of *settings* run (their need on the GPU *ocr* MiB): the CPU after a GPU failure this
    session (*failed*, its type name: `failed_placement`) and where torch has no CUDA (*cuda*: `artwork.has_cuda` when
    None, the question the page models ask); else as ``ocr_runs_on`` says, "auto" by `judge` on *facts* (`gather`) of
    the moment, *staying* for readers the rule has on the GPU now."""
    setting = str(getattr(settings, "ocr_runs_on", "auto") or "auto")
    if failed:
        return failed_placement(failed)
    if setting == "cpu":
        return Placement("cpu", SET)
    if cuda is None:
        from ..render.artwork import has_cuda

        cuda = has_cuda()
    if not cuda:
        return Placement("cpu", NO_CUDA)
    if setting == "gpu":
        return Placement("gpu", SET)
    return judge((facts or gather)(settings), ocr, staying)


def readers_need(settings: Any) -> int:
    """What the readers that go to the GPU need there, in MiB, by the readers installed (`Readers.gpu_mib` once they
    are loaded)."""
    from .readers import missing_readers

    return CHARSPOT_MIB + (0 if missing_readers(settings.models_dir) else NAR_MIB)


def full_window_placements(settings: Any, kv: str, ocr: int | None = None, cuda: bool | None = None,
                           facts: Callable[[Any, tuple[str, bool]], GpuFacts | None] | None = None
                           ) -> tuple[Placement, Placement]:
    """Where `decide` puts the readers of *settings* (their need *ocr* MiB, `readers_need` when None) with the
    translation model at its footprint on a server whose KV cache is *kv*: without the full-size window cache, and with
    it (`taslation.ollama_start.server_setup` asks it once, as it starts the server; "auto" gives the server the cache
    unless only the second is the CPU). *facts*(settings, (kv, full window)): `gather` when None, on one `snapshot`
    for both, so that they differ by the translation model's figure alone, and without asking Ollama what it has
    loaded (the server is about to be started: nothing is, and a server that is not there takes Windows about 2 s
    to refuse)."""
    need = readers_need(settings) if ocr is None else ocr
    if facts is None:
        memory, own = snapshot()

        def look(s: Any, cache: tuple[str, bool]) -> GpuFacts | None:
            return gather(s, cache, memory, own, ask=False)
    else:
        look = facts
    return tuple(decide(settings, need, cuda=cuda, facts=lambda s, full=full: look(s, (kv, full)))
                 for full in (False, True))  # type: ignore[return-value]


# ------------------------------------------------------------------ the facts
# translation models seen loaded this session -> MiB they need: (name, num_ctx, layers, KV type, full window)
_learnt: dict[tuple[str, int, int | None, str, bool], int] = {}


def gather(settings: Any, cache: tuple[str, bool] | None = None, memory: tuple[int, int] | None = None,
           own: int | None = None, ask: bool = True) -> GpuFacts | None:
    """The facts of the moment for *settings* (see the module's docstring); None when the card's memory cannot be
    read. *cache*: the server's KV cache type and full window to count the translation model with (`server_cache`
    when None); *memory* and *own*: the card's (total, used) and this process's MiB as `snapshot` read them together
    (each read now when None); *ask*: False counts the translation model as not loaded, Ollama not asked."""
    memory = card_memory() if memory is None else memory
    if memory is None:
        return None
    total, used = memory
    need, now, answered = _translator_need(settings, cache, ask)
    lama, layout = page_models_on_gpu(settings)
    own = own_mib() if own is None else own
    return GpuFacts(total, used, own, need, now, lama, layout, answered, lama and tall_screen())


def snapshot(tries: int = 3) -> tuple[tuple[int, int] | None, int]:
    """The card's (total, used) memory and this process's own (`own_mib`) read together: this process's read before
    and after the card, and all of it again while that changed between (a reader or a page model moving to the GPU on
    another thread meanwhile: the card's used memory and this process's part of it must be of the same moment, or the
    other programs' share is off by what moved), at most *tries* times."""
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
    server's cache with the smallest size that holds it (the size tells the caches apart, whoever started the server);
    None for a model not measured, or larger than every cache measured."""
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
    from ..translate import TranslationError
    from ..translate.models import make_translator, wanted_name
    from ..translate.ollama import num_gpu_value

    try:
        layers = num_gpu_value(getattr(settings, "ollama_num_gpu", ""))
    except ValueError:
        layers = None
    if layers == 0:
        return 0, 0, True  # (the processor only)
    try:
        name = wanted_name(settings.ollama_model, settings.target_language)
        translator = make_translator(settings, name)
        num_ctx = int(getattr(translator, "num_ctx", 0) or 0)
    except (TranslationError, ValueError, AttributeError):
        return None, 0, True
    kv, full = server_cache(settings) if cache is None else cache
    key = (name, num_ctx, layers, str(kv), bool(full))
    answered = True
    try:
        entry = translator._loaded(name) if ask else None
    except (TranslationError, OSError, ValueError):
        entry, answered = None, False
    if entry and entry.get("size") and entry.get("size_vram") is not None:
        now = int(entry["size_vram"]) // MiB
        need = int(entry["size"]) // MiB if layers is None else now
        # once it is unloaded, the runner's own memory beside what /api/ps counts (in the used memory while it is
        # loaded, as other programs' there) is counted in: as measured for a known model with the server's cache of
        # the size it had then
        known = known_for_size(name, num_ctx, need) if layers is None else None
        _learnt[key] = known if known is not None else round(need * RUNNER_SHARE)
        return need, now, True
    if key in _learnt:
        return _learnt[key], 0, answered
    measured = known_translator(name, num_ctx, (str(kv), bool(full))) if layers is None else None
    return (measured[0] if measured else None), 0, answered


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


def watched(settings: Any) -> tuple[Any, ...]:
    """The settings the decision depends on: a change of any of them decides again."""
    return tuple(getattr(settings, name, None) for name in (
        "ocr_runs_on", "ollama_model", "target_language", "ollama_num_gpu", "ollama_num_ctx", "ollama_url",
        "erase_mode", "art_erase", "detect_model", "models_dir"))


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
    """While a request to the translation model is under way: the readers read on the CPU meanwhile, their GPU copies
    kept. Windows shares the GPU between Ollama's process and this one in time slices: a crop read on the GPU while
    PLaMo generated took 687 ms (both readers), on the CPU 127 ms, against about 40 ms on an idle GPU; the translator's
    speed was about the same either way (measured 124 and 121 tokens/s, 126 alone). The readings are the same."""
    global _translating
    with _translating_lock:
        _translating += 1
    try:
        yield
    finally:
        with _translating_lock:
            _translating -= 1


_loading = 0  # loads of the translation model under way (`loading`)


@contextlib.contextmanager
def loading() -> Iterator[None]:
    """While Ollama loads the translation model (the translator's load, from the release of the GPU models before it to
    its end, and a warm-up): where the readers run is not decided meanwhile (`busy`); they read where they are."""
    global _loading
    with _translating_lock:
        _loading += 1
    try:
        yield
    finally:
        with _translating_lock:
            _loading -= 1


def busy() -> bool:
    """Whether the translation model is being loaded or asked now (`loading`, `translating`): no time to decide where
    the readers run (the next read after it decides)."""
    return bool(_loading or _translating)


_kept = False  # the last release before a load kept the readers on the GPU (`kept_through_load`)
_keeps = True  # loads may keep them there this session (`keeps_through_loads`, `partly_loaded`)


def keeps_through_loads() -> bool:
    """Whether a load of the translation model may keep the readers on the GPU this session (`Readers.release_gpu`
    with *load*): until one came up partly on the CPU beside them (`partly_loaded`)."""
    return _keeps


def kept_through_load(kept: bool) -> None:
    """The release before a load of the translation model kept the readers on the GPU (*kept*), or let them go
    (`Readers.release_gpu`)."""
    global _kept
    _kept = bool(kept)


def partly_loaded(share: float) -> bool:
    """A load of the translation model ended with only *share* of it on the GPU (`OllamaTranslator._ensure_loaded`,
    where ``ollama_num_gpu`` leaves the layers to the server; it loads the model once more after the GPU models are
    let go): readers kept on the GPU through it (`kept_through_load`) took room it needed, so no load keeps them there
    again this session, and that release puts them on the CPU. Whether they had been kept."""
    global _keeps
    if not _kept:
        return False
    _keeps = False
    LOG.info("the translation model came up %d %% on the GPU beside the OCR readers kept there through its load: they "
             "go to the CPU before every load from now on", round(float(share) * 100))
    return True


def out_of_memory(error: BaseException) -> bool:
    """Whether *error* is the GPU's memory running out (torch's ``OutOfMemoryError``, or an error that says so, as
    CUDA's and its libraries' own do: "out of memory", "..._ALLOC_FAILED"): a state that passes, unlike a CUDA error."""
    text = str(error).lower()
    return type(error).__name__ == "OutOfMemoryError" or "out of memory" in text or "alloc_failed" in text


def crawling(gpu_ms: Iterable[float], cpu_ms: Iterable[float]) -> tuple[float, float] | None:
    """Whether a reader's last reads on the GPU crawl: the fastest of the last `SLOW_READS` of them (*gpu_ms*) more
    than `SLOW_FACTOR` times the median of its reads on the CPU this session (*cpu_ms*, `CPU_READS` of them at
    least) - every one of them slow, as when the GPU's memory is in the computer's own or another program keeps the GPU
    busy, not a read that waited behind a page model of this process now and then: (that fastest read, the CPU's
    median, ms), else None."""
    gpu, cpu = list(gpu_ms)[-SLOW_READS:], list(cpu_ms)
    if len(gpu) < SLOW_READS or len(cpu) < CPU_READS:
        return None
    fastest, on_cpu = min(gpu), statistics.median(cpu)
    return (fastest, on_cpu) if fastest > SLOW_FACTOR * on_cpu else None


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
    (``_copy_to``, the reader's). `run` reads with the copy in force; a failure on the GPU (out of memory, a CUDA error:
    any RuntimeError there) drops the GPU's copy, says so to `on_gpu_failure` (the type name) and reads on the CPU, as
    it does from then on: until the GPU memory is next let go after an out of memory (``gpu_full``), for the session
    after any other failure (``gpu_failed``)."""

    name = "reader"

    def __init__(self) -> None:
        self._cpu_models: tuple[Any, ...] = ()
        self._gpu: tuple[str, tuple[Any, ...]] | None = None  # (device, the copy)
        self.gpu_ms: deque[float] = deque(maxlen=SLOW_READS)  # the last reads' times on the GPU, ms (`crawling`)
        self.cpu_ms: deque[float] = deque(maxlen=SLOW_READS)  # ... on the CPU
        self._probe = False  # the next read is the CPU's, to know the processor's time (`run`)
        self._since_probe = 0  # reads on the GPU since the last read on the CPU
        self.gpu_failed = ""  # the type name of the GPU's failure this session ("" none; `SLOW_GPU`: it crawled)
        self.gpu_full = ""  # ... of an out of memory there, until the GPU memory is next let go (`Readers.release_gpu`)
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
        if self.gpu_failed or self.gpu_full:
            return False
        if self._gpu is not None and self._gpu[0] == device:
            return True
        why, full = "", False
        try:
            copy = self._copy_to(device)
        except RuntimeError as e:
            why, full = type(e).__name__, out_of_memory(e)
        else:
            with self._lock:
                self._gpu = (device, copy)
            return True
        self._failed(why, full)  # (out of the except: its traceback holds the copy's tensors made so far)
        return False

    def run(self, read: Callable[[str, tuple[Any, ...]], T]) -> T:
        """*read*(device, networks) with the copy in force - on the CPU while the translation model computes
        (`translating`) - and on the CPU when the GPU fails or crawls (see the class). Each read is timed for
        `crawling`: a read on the CPU as the processor's time for this reader, one on the GPU as the GPU's. The reads
        while the translation model computes are the CPU's anyway; while fewer than `CPU_READS` processor's times are
        known, one read in `SLOW_READS` + 1 on the GPU during the translation model's load (`loading`: the page waits
        for the load then, so the slower read costs it nothing) is the CPU's too, to know them (taken at any time, two
        of them fell into the first page after the start on the stand-in, 144 ms of reads on the CPU). With no
        processor's time known, no read counts as crawling."""
        with self._lock:
            held = self._gpu if not _translating else None
            if held is not None and self._probe and _loading:
                held, self._probe = None, False  # (this one on the CPU: a processor's time)
            if held is not None:
                self._reading += 1
        if held is None:
            start = time.perf_counter()
            out = read("cpu", self._cpu_models)
            self.cpu_ms.append((time.perf_counter() - start) * 1000)
            self._since_probe = 0
            return out
        why, full, took = "", False, 0.0
        try:
            start = time.perf_counter()
            out = read(*held)
            took = (time.perf_counter() - start) * 1000
        except RuntimeError as e:
            why, full = type(e).__name__, out_of_memory(e)
        finally:
            held = None
            with self._lock:
                self._reading -= 1
                late = self._give_back and not self._reading
                if late:
                    self._give_back = False
            if late:
                give_back()
        if not why:
            self.gpu_ms.append(took)
            self._since_probe += 1
            if len(self.cpu_ms) < CPU_READS:
                self._probe = self._since_probe >= SLOW_READS
            else:
                verdict = crawling(self.gpu_ms, self.cpu_ms)
                if verdict is not None:
                    self._failed(SLOW_GPU, slow=verdict)
            return out
        self._failed(why, full)
        return read("cpu", self._cpu_models)

    def _failed(self, why: str, full: bool = False, slow: tuple[float, float] | None = None) -> None:
        """The GPU failed (*why*, the type name): its copy dropped, the reads on the CPU, and `on_gpu_failure` told. An
        out of memory there (*full*) holds until the GPU memory is next let go (`gpu_full`, cleared by
        `Readers.release_gpu`): other programs, or the translation model's load, may have taken the room for a time;
        any other failure (a CUDA error) and reads that crawl there (*slow*: the fastest of them and the processor's
        median, ms, `crawling`; *why* `SLOW_GPU`) hold for the rest of the session (`gpu_failed`)."""
        if slow is not None:
            LOG.info("the OCR reader %s reads slowly on the GPU (%.0f ms a crop at the fastest, %.0f on the CPU): on "
                     "the CPU for the rest of the session", self.name, slow[0], slow[1])
            self.gpu_failed = SLOW_GPU
        elif full:
            LOG.info("the GPU has no room for the OCR reader %s (%s): on the CPU until the GPU memory is next let go",
                     self.name, why)
            self.gpu_full = why or "OutOfMemoryError"
        else:
            LOG.info("the OCR reader %s failed on the GPU (%s): on the CPU for the rest of the session", self.name, why)
            self.gpu_failed = why or "RuntimeError"
        self.to("cpu")
        tell = self.on_gpu_failure
        if tell is not None:
            try:
                tell(self.name, self.gpu_failed or self.gpu_full)
            except Exception:  # noqa: BLE001 - the crop is read all the same
                pass
