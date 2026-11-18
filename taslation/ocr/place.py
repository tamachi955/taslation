"""Where the OCR readers run: on the GPU when it has room for them at TASlation's peak, else on the CPU.

The setting ``ocr_runs_on``: "cpu" (always the CPU, as before), "gpu" (the GPU wherever torch has CUDA) or "auto", the
default: the GPU only when, beside everything else TASlation keeps there at its peak - the translation model whole in
video memory, LaMa and the layout model when the settings use them, this process's CUDA context - and beside what
other programs hold now, the readers leave `MARGIN_MIB` free (`room_left`, the rule). A card of less than
`MIN_TOTAL_MIB` is never asked. The readers on the GPU are charspot and nar (`OCR_MIB`); CPT, the third, which reads a
line only where those two differ, stays on the CPU: its 440 MB of weights would be on the GPU for a few crops a page.

What the rule measures (`GpuFacts`, `gather`):

* the card's memory as NVIDIA's driver library sees it (`devices.nvml_usage_mib`, nothing loaded, no CUDA context
  made): on Windows torch's ``mem_get_info`` counts what this process holds alone (another process's 2 GB left its
  free memory as it was, measured), so it cannot see Ollama or other programs; where there is no NVML (not Windows)
  torch's own figure, which is the card's there;
* what of the used memory is TASlation's own: Ollama's ``size_vram`` of the translation model (/api/ps, which never
  loads one) and this process's (torch's reserved memory and its CUDA context); the rest is other programs';
* what the translation model needs: /api/ps's ``size`` while it is loaded (``size_vram`` where ``ollama_num_gpu`` puts
  only some layers there on purpose; nothing for "0"), learnt for the session with the runner's own memory that
  /api/ps leaves out (`RUNNER_SHARE`); before it is loaded, what it was measured to add to the card's used memory
  (`KNOWN_TRANSLATORS`, at the context the app asks for); a model of the reader's own that was never seen loaded is
  not known, and the readers stay on the CPU (`UNKNOWN`) until it has been.

The decision is made when the readers load (`Readers`, the window's start), again once the GPU memory was let go
(`Readers.release_gpu`: Tools > Release the model now, and before Ollama loads its model unless they stay through the
load, below; decided again at the next read) and when a setting it depends on changed. A GPU that fails (out of
memory, a CUDA error) moves the readers to the CPU for the rest of the session, and the crop at hand is read there
(`DeviceModels.run`). The weights move without being read from disk again: the CPU's copy stays where it is loaded,
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
`MARGIN_MIB` free, so Ollama finds room for all of it. They read on there through the load, and the decision stands.
Just before a load the readers are in the card's used memory and in this process's own alike, so that they count once,
as `peak_mib`'s *ocr*; the model is not loaded then (another model in Ollama counts as other programs' memory, as
ever). A load that all the same ends with the model partly on the CPU (`partly_loaded`: ``size_vram`` below ``size``
in the /api/ps the translator asks after it, the layers left to the server) found them in its way: they go to the CPU
at the release before the translator's second load, and no load keeps them again this session
(`keeps_through_loads`). Measured on the 6 GB card (2026-11-16, the app's own load, two rounds): PLaMo came up whole
beside the readers kept in 10 loads of 10 (/api/ps 1823 of 1823 MiB); with a page read meanwhile a crop took 43-47 ms
through the load against 146-226 on the CPU with them let go, and the load 5.0-5.3 s against 5.5-6.5 (once 7.1, the
first load of a round); alone 4.8-5.1 s kept, 5.1 let go; the readings were those of the CPU.
"""

from __future__ import annotations

import contextlib
import gc
import logging
import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterator, TypeVar

LOG = logging.getLogger(__name__)
MiB = 1024 * 1024
T = TypeVar("T")

SETTING_VALUES = ("auto", "cpu", "gpu")  # ``ocr_runs_on``

# Measured on a GTX 1660 Ti (6 GB, Windows, torch 2.14 cu126; this process's dedicated GPU memory as Windows counts
# it), rounded up: what each reader on the GPU holds at its peak over the gold set's 933 crops, the largest included -
# its weights and the caching allocator's blocks (charspot 416 MiB, 50 of them weights; nar 30) - and this process's
# CUDA context with the libraries a network loads there (77 MiB bare, about 100).
CHARSPOT_MIB = 450
NAR_MIB = 50
CONTEXT_MIB = 150
# ... and the page models at their peak over the gold set's 101 screens and 30 sample pages (LaMa 704 MiB, the layout
# model 500 more)
LAMA_MIB = 850
LAYOUT_MIB = 550
# The translation models whole in video memory, at the context the app asks for (PLaMo its own 8192, the chat model
# ``ollama_num_ctx``'s default): what loading one with the app's options added to the card's used memory, rounded up
# (Ollama 0.40, KV cache q8_0; /api/ps said 1824 and 3203 MiB of them): (Ollama name, num_ctx) -> MiB
KNOWN_TRANSLATORS = {("taslation-plamo3-translate-2b", 8192): 2000, ("qwen3.5:4b", 16384): 4000}
RUNNER_SHARE = 1.25  # what the runner adds to /api/ps's size, at most (measured 1.06 and 1.23)
MARGIN_MIB = 1024  # left free at the peak for other programs that grow (a browser, a video)
MIN_TOTAL_MIB = 5 * 1024  # a smaller card is the translator's and the page models'

# why the readers are where they are (`Placement.why`)
ROOM, SET, NO_CUDA, NO_ROOM, UNKNOWN, FAILED, RELEASED, NOT_ASKED = (
    "room", "set", "no_cuda", "no_room", "unknown", "failed", "released", "not_asked")


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
    *translator_now* what of it is there now, whether *lama* and the *layout* model run on the GPU, and whether Ollama
    *answered* /api/ps (False: taken for a model not loaded)."""

    total: int
    used: int
    own: int = 0
    translator: int | None = 0
    translator_now: int = 0
    lama: bool = False
    layout: bool = False
    answered: bool = True


def peak_mib(facts: GpuFacts, ocr: int) -> int:
    """What TASlation holds on the GPU at its peak with the readers there (*ocr* MiB): the context, the translation
    model, the page models in use, the readers."""
    return (CONTEXT_MIB + int(facts.translator or 0) + (LAMA_MIB if facts.lama else 0)
            + (LAYOUT_MIB if facts.layout else 0) + int(ocr))


def room_left(facts: GpuFacts, ocr: int) -> int:
    """THE RULE's number: the MiB left on the card at TASlation's peak with the readers on it - the total, less what
    other programs hold now (the used memory that is not TASlation's), less `peak_mib`."""
    other = max(0, facts.used - facts.own - facts.translator_now)
    return facts.total - other - peak_mib(facts, ocr)


def judge(facts: GpuFacts | None, ocr: int) -> Placement:
    """"auto" on *facts*: the GPU when the card has `MIN_TOTAL_MIB` or more, the translation model's need is known and
    `room_left` is `MARGIN_MIB` or more; else the CPU, and why."""
    if facts is None:
        return Placement("cpu", UNKNOWN)
    if facts.total < MIN_TOTAL_MIB:
        return Placement("cpu", NO_ROOM)
    if facts.translator is None:
        return Placement("cpu", UNKNOWN)
    room = room_left(facts, ocr)
    return Placement("gpu" if room >= MARGIN_MIB else "cpu", ROOM if room >= MARGIN_MIB else NO_ROOM, room)


def through_load(facts: GpuFacts | None, ocr: int) -> Placement:
    """The rule asked again just before Ollama loads the translation model (`Readers.keeps_through_load`): `judge` on
    *facts*, but facts not all measured - Ollama not answering /api/ps among them - are a room not known."""
    if facts is not None and not facts.answered:
        return Placement("cpu", UNKNOWN)
    return judge(facts, ocr)


def decide(settings: Any, ocr: int, failed: str = "", cuda: bool | None = None,
           facts: Callable[[Any], GpuFacts | None] | None = None) -> Placement:
    """Where the readers of *settings* run (their need on the GPU *ocr* MiB): the CPU after a GPU failure this
    session (*failed*, its type name) and where torch has no CUDA (*cuda*: `artwork.has_cuda` when None, the question
    the page models ask); else as ``ocr_runs_on`` says, "auto" by `judge` on *facts* (`gather`) of the moment."""
    setting = str(getattr(settings, "ocr_runs_on", "auto") or "auto")
    if failed:
        return Placement("cpu", FAILED, error=failed)
    if setting == "cpu":
        return Placement("cpu", SET)
    if cuda is None:
        from ..render.artwork import has_cuda

        cuda = has_cuda()
    if not cuda:
        return Placement("cpu", NO_CUDA)
    if setting == "gpu":
        return Placement("gpu", SET)
    return judge((facts or gather)(settings), ocr)


# ------------------------------------------------------------------ the facts
_learnt: dict[tuple[str, int, int | None], int] = {}  # translation models seen loaded this session -> MiB they need


def gather(settings: Any) -> GpuFacts | None:
    """The facts of the moment for *settings* (see the module's docstring); None when the card's memory cannot be
    read."""
    memory = card_memory()
    if memory is None:
        return None
    total, used = memory
    need, now, answered = _translator_need(settings)
    lama, layout = page_models_on_gpu(settings)
    return GpuFacts(total, used, own_mib(), need, now, lama, layout, answered)


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


def _translator_need(settings: Any) -> tuple[int | None, int, bool]:
    """`translator_need`, and whether Ollama answered /api/ps (True where nothing was asked of it)."""
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
        key = (name, int(getattr(translator, "num_ctx", 0) or 0), layers)
    except (TranslationError, ValueError, AttributeError):
        return None, 0, True
    answered = True
    try:
        entry = translator._loaded(name)
    except (TranslationError, OSError, ValueError):
        entry, answered = None, False
    if entry and entry.get("size") and entry.get("size_vram") is not None:
        now = int(entry["size_vram"]) // MiB
        need = int(entry["size"]) // MiB if layers is None else now
        # once it is unloaded, the runner's own memory beside what /api/ps counts (in the used memory while it is
        # loaded, as other programs' there) is counted in
        _learnt[key] = round(need * RUNNER_SHARE)
        return need, now, True
    if key in _learnt:
        return _learnt[key], 0, answered
    return (KNOWN_TRANSLATORS.get(key[:2]) if layers is None else None), 0, answered


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
    it does from then on (``gpu_failed``)."""

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
        """*read*(device, networks) with the copy in force - on the CPU while the translation model computes
        (`translating`) - and on the CPU when the GPU fails (see the class)."""
        with self._lock:
            held = self._gpu if not _translating else None
            if held is not None:
                self._reading += 1
        if held is None:
            return read("cpu", self._cpu_models)
        why = ""
        try:
            return read(*held)
        except RuntimeError as e:
            why = type(e).__name__
        finally:
            held = None
            with self._lock:
                self._reading -= 1
                late = self._give_back and not self._reading
                if late:
                    self._give_back = False
            if late:
                give_back()
        self._failed(why)
        return read("cpu", self._cpu_models)

    def _failed(self, why: str) -> None:
        LOG.info("the OCR reader %s failed on the GPU (%s): on the CPU for the rest of the session", self.name, why)
        self.gpu_failed = why or "RuntimeError"
        self.to("cpu")
        tell = self.on_gpu_failure
        if tell is not None:
            try:
                tell(self.name, self.gpu_failed)
            except Exception:  # noqa: BLE001 - the crop is read all the same
                pass
