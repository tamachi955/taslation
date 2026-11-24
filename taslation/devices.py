"""What each stage of a page runs on - detection, OCR, the translator and the erase - "GPU (its name)" or "CPU", and
how many seconds a page took there on the last pages lettered (`StageTimes`: numbers alone, kept in
``<state dir>/timings.json`` when the window closes). Settings... > System shows it (`ui.dialogs.system_page`),
and `taslation doctor` prints it (`lines`).

Only CUDA counts as a GPU here. Nothing is started or loaded to find out: torch's CUDA is asked for the GPU's name
only once it is in use (asking first would take video memory the translator needs), else NVIDIA's driver library
(NVML, ``nvml.dll`` in System32, by its full path) is asked for it; Ollama is asked ``/api/ps`` (`OllamaTranslator.
_loaded`), which says how much of a loaded model is in video memory and never loads one. Where the stages run:

* detection: the classical detectors on the CPU; with the layout model in use (`detect_model`, installed) the model
  runs on the GPU where torch has CUDA and the judgement at the start put it there (`ocr.place.on_gpu`), else on the
  CPU;
* OCR: where the readers are (`ocr.Readers.placement`: charspot and nar where the judgement at the start put them,
  and why; CPT on the CPU); without loaded readers (``taslation doctor``), where the session's plan puts them
  (`ocr.place.readers_placement`, which asks NVML and /api/ps, as above, for a plan not made yet);
* translation: Ollama's model on the GPU, the CPU or both, as /api/ps says while it is loaded, and for an Ollama
  TASlation started, whether it got the window cache (`window_cache_text`, `ollama_start.setup_of`);
* erasing: the paper fill on the CPU; LaMa on the art where `art_erase` runs it on this computer and it is installed
  (`artwork.available`: "auto" only where torch has CUDA, "lama" on the CPU too), on the GPU where torch has CUDA and
  the judgement at the start put it there. What the start found short, and what it sent to the processor, is
  `plan_text`."""

from __future__ import annotations

import ctypes
import json
import os
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .atomic import write_atomic
from .i18n import _

STAGES = ("detect", "ocr", "translate", "erase")
STAGE_LAPS = {"detect": ("detect",), "ocr": ("ocr",), "translate": ("translate",), "erase": ("render",)}  # the
# pipeline's laps (`pipeline._Timer`) a stage's seconds come from; the erase is timed with the lettering
STAGE_NAMES = {"detect": "Finding the text", "ocr": "Reading the text (OCR)", "translate": "Translating",
               "erase": "Erasing and lettering"}
KEEP_PAGES = 20  # the pages the seconds are the mean of
TIMINGS_FILE = "timings.json"


@dataclass
class StageDevice:
    """Where one stage runs: *device* "gpu", "cpu", "both" (a model partly in video memory, *share* on the GPU) or
    "" (not known now: *why* says so); *gpu* the GPU's name when known; *what* runs there, in the window's
    language."""

    stage: str
    device: str
    what: str
    gpu: str = ""
    share: float | None = None
    why: str = ""

    def where(self) -> str:
        """Where it runs, in the window's language: "GPU (NVIDIA ...)", "CPU", "GPU and CPU (60 % on the GPU)"."""
        if self.device == "gpu":
            return _("GPU ({name})").format(name=self.gpu) if self.gpu else _("GPU")
        if self.device == "cpu":
            return _("CPU")
        if self.device == "both":
            return _("GPU and CPU ({percent} % on the GPU)").format(percent=round(100 * (self.share or 0)))
        return self.why


class StageTimes:
    """The seconds of each stage on the last `KEEP_PAGES` pages lettered (`add`: a page's laps); `per_page` is their
    mean, per stage, over the pages that had that stage (a page from the cache has no translation)."""

    def __init__(self, pages: Iterable[Mapping[str, float]] = ()):
        self.pages: deque[dict[str, float]] = deque(maxlen=KEEP_PAGES)
        for page in pages:
            self.add(page, laps=False)

    def add(self, timings: Mapping[str, float], laps: bool = True) -> None:
        """A page's seconds: the pipeline's laps (*laps*) or already by stage."""
        page: dict[str, float] = {}
        for stage in STAGES:
            names = STAGE_LAPS[stage] if laps else (stage,)
            seconds = [float(timings[n]) for n in names if isinstance(timings.get(n), (int, float))]
            if seconds and all(s >= 0 for s in seconds):
                page[stage] = sum(seconds)
        if page:
            self.pages.append(page)

    def __len__(self) -> int:
        return len(self.pages)

    def per_page(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for stage in STAGES:
            seen = [page[stage] for page in self.pages if stage in page]
            if seen:
                out[stage] = sum(seen) / len(seen)
        return out

    def save(self, state_dir: Path | str) -> None:
        if not self.pages:
            return
        path = Path(state_dir) / TIMINGS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"pages": [{k: round(v, 3) for k, v in page.items()} for page in self.pages]}
        write_atomic(path, (json.dumps(data) + "\n").encode("utf-8"))

    @classmethod
    def load(cls, state_dir: Path | str) -> "StageTimes":
        """The seconds kept the last time the window closed (none where there is no file, or a damaged one)."""
        try:
            data = json.loads((Path(state_dir) / TIMINGS_FILE).read_text(encoding="utf-8"))
            pages = [p for p in data.get("pages", []) if isinstance(p, dict)]
        except (OSError, ValueError, AttributeError):
            return cls()
        return cls(pages)


def save_times(pipeline: Any, state_dir: Path | str) -> None:
    """The window closes: the seconds of this session's pages kept for the next look (`StageTimes.save`), as they
    were before a page job whose frame was not confirmed (`Pipeline.to_save`: none of its seconds)."""
    times = getattr(pipeline, "stage_times", None)
    to_save = getattr(pipeline, "to_save", None)
    if times is not None and to_save is not None:
        times = to_save(times)
    if times is not None:
        try:
            times.save(state_dir)
        except OSError:
            pass


# ------------------------------------------------------------------ the GPU
def cuda_available() -> bool:
    """Whether torch has CUDA (torch is imported when it is not yet: `taslation doctor`; the window has it)."""
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 - no torch, or a broken CUDA: no GPU here
        return False


def gpu_name() -> str:
    """The first CUDA GPU's name: from torch where CUDA is in use already, else from NVML; "" when not known."""
    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            if torch.cuda.is_initialized():
                return str(torch.cuda.get_device_name(0))
        except Exception:  # noqa: BLE001
            pass
    return nvml_name()


def nvml_name() -> str:
    """The first GPU's name as NVIDIA's driver library says it (Windows: ``System32\\nvml.dll`` by its full path,
    nothing else is loaded), "" when there is none."""
    name = ctypes.create_string_buffer(96)
    found = _nvml_first(lambda nvml, handle: nvml.nvmlDeviceGetName(handle, name, 96) == 0)
    return name.value.decode("utf-8", "replace").strip() if found else ""


class _NvmlMemory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


def nvml_memory_mib() -> int:
    """The first GPU's video memory in MiB as NVIDIA's driver library says it (as `nvml_name`; the number nvidia-smi
    prints as memory.total), 0 when there is none."""
    found = nvml_usage_mib()
    return found[0] if found is not None else 0


def nvml_usage_mib() -> tuple[int, int] | None:
    """(total, used) MiB of the first GPU as NVIDIA's driver library says it, every program's memory counted (on
    Windows torch's ``mem_get_info`` sees its own process's alone); None without NVML or a GPU. No CUDA context is
    made for it."""
    memory = _NvmlMemory()
    found = _nvml_first(lambda nvml, handle: nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(memory)) == 0)
    return (int(memory.total // (1024 * 1024)), int(memory.used // (1024 * 1024))) if found else None


def _nvml_first(ask: Any) -> bool:
    """*ask* (nvml, the first GPU's handle) -> whether it answered, run with NVML open; False without NVML or a GPU."""
    if sys.platform != "win32":
        return False
    path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvml.dll"
    if not path.is_file():
        return False
    try:
        nvml = ctypes.WinDLL(str(path))
        if nvml.nvmlInit_v2() != 0:
            return False
        try:
            handle = ctypes.c_void_p()
            if nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
                return False
            return bool(ask(nvml, handle))
        finally:
            nvml.nvmlShutdown()
    except (OSError, AttributeError):
        return False


# ------------------------------------------------------------------ the screens
class _DisplayDevice(ctypes.Structure):  # DISPLAY_DEVICEW
    _fields_ = [("cb", ctypes.c_uint32), ("name", ctypes.c_wchar * 32), ("string", ctypes.c_wchar * 128),
                ("flags", ctypes.c_uint32), ("id", ctypes.c_wchar * 128), ("key", ctypes.c_wchar * 128)]


class _DisplayMode(ctypes.Structure):  # DEVMODEW, its display half
    _fields_ = [("device", ctypes.c_wchar * 32), ("spec", ctypes.c_uint16), ("driver", ctypes.c_uint16),
                ("size", ctypes.c_uint16), ("extra", ctypes.c_uint16), ("fields", ctypes.c_uint32),
                ("x", ctypes.c_int32), ("y", ctypes.c_int32), ("orientation", ctypes.c_uint32),
                ("fixed_output", ctypes.c_uint32), ("printer", ctypes.c_int16 * 5), ("form", ctypes.c_wchar * 32),
                ("log_pixels", ctypes.c_uint16), ("bits", ctypes.c_uint32), ("width", ctypes.c_uint32),
                ("height", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("frequency", ctypes.c_uint32),
                ("rest", ctypes.c_uint32 * 8)]


def screen_height_px() -> int | None:
    """The height in pixels of the tallest screen on the desktop, in its current mode (the pixels the screen shows,
    whatever this process's DPI awareness); None where it cannot be read (not Windows). Nothing is loaded for it."""
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.WinDLL("user32")
        tallest = 0
        for index in range(64):
            device = _DisplayDevice()
            device.cb = ctypes.sizeof(device)
            if not user32.EnumDisplayDevicesW(None, index, ctypes.byref(device), 0):
                break
            if not device.flags & 0x1:  # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
                continue
            mode = _DisplayMode()
            mode.size = ctypes.sizeof(mode)
            if user32.EnumDisplaySettingsW(device.name, ctypes.c_uint32(0xFFFFFFFF), ctypes.byref(mode)):
                tallest = max(tallest, int(mode.height))  # (ENUM_CURRENT_SETTINGS)
        return tallest or None
    except (OSError, AttributeError):
        return None


# ------------------------------------------------------------------ the stages
def stage_devices(settings: Any, translator: Any = None, cuda: bool | None = None,
                  gpu: str | None = None, ocr: Any = None) -> list[StageDevice]:
    """Where each of `STAGES` runs with *settings* (the settings in force), the translator *translator* (an
    `OllamaTranslator`, the window's; one is made for the settings when None or not Ollama's) asked for its model;
    *cuda* and *gpu* as `artwork.has_cuda` (`cuda_available`, asked once a session) and `gpu_name` say when None.
    The erase on the art is where the pipeline has it, by the same rule (`artwork.available` with this *cuda*); the OCR
    where *ocr* (the window's readers) is (`ocr_device`)."""
    from .detect import layout
    from .render import artwork

    from .ocr import place

    cuda = artwork.has_cuda() if cuda is None else cuda
    if cuda:
        place.plan_for(settings)  # (the session's plan; a command's, ``taslation doctor``'s, made now as it would be)
    name = (gpu_name() if cuda else "") if gpu is None else gpu
    models_dir = settings.models_dir
    detect_model = getattr(settings, "detect_model", "auto")
    art_erase = getattr(settings, "art_erase", "auto")
    lama = getattr(settings, "erase_mode", "fill") == "fill" and artwork.available(models_dir, art_erase, cuda=cuda)
    model = (detect_model == "on" or (detect_model == "auto" and lama)) and layout.available(models_dir)
    layout_gpu = bool(cuda and model and place.on_gpu(place.LAYOUT))  # (the session's plan: `ocr.place`)
    lama_gpu = bool(cuda and lama and place.on_gpu(place.LAMA))
    out = [StageDevice("detect", "gpu" if layout_gpu else "cpu",
                       _("The layout model and the classical detectors") if model else _("The classical detectors"),
                       name if layout_gpu else ""),
           ocr_device(settings, ocr, cuda, name)]
    out.append(_translator_device(settings, translator, name))
    out.append(StageDevice("erase", "gpu" if lama_gpu else "cpu", _("LaMa on the drawing, the paper fill in the bubbles")
                           if lama else _("The paper fill"), name if lama_gpu else ""))
    return out


OCR_WHY = {  # what runs there, by why it is there (`ocr.place.Placement.why`)
    "room": "Two of the OCR readers, as the GPU has room for them (the third on the CPU)",
    "processor": "The OCR readers, on the processor: the GPU's memory was short at the start",
    "unknown": "The OCR readers: the room on the GPU is not known",
    "failed": "The OCR readers, on the CPU since the GPU failed ({error})",
    "released": "The OCR readers: the GPU memory was let go, the next page puts them back",
}
OCR_SET = {"gpu": "Two of the OCR readers, as set in ocr_runs_on (the third on the CPU)",
           "cpu": "The OCR readers, as set in ocr_runs_on"}
# the parts of `ocr.place` by name (the note under the System page's list, `plan_text`, and the start's dialog,
# `ui.dialogs.gpu_short`), and that note's lines; the 16 languages: `locales/features/gpu_start.py`
PART_NAMES = {"readers": "the OCR readers", "lama": "the erase model on the art (LaMa)",
              "layout": "the layout model", "translator": "the translation model"}
PLAN_SHORT = "At the start the GPU's memory was short by {mb} MB: {parts} run on the processor this session."
PLAN_FIXED = "At the start the GPU's memory was short by {mb} MB; the settings fix what runs on the GPU, so nothing was moved."
PLAN_FAILED = "After a failure on the GPU, {parts} run on the processor for the rest of this session."


def short_mb(mib: int) -> int:
    """*mib* as the window says a shortage: MB, rounded up to 10."""
    return max(10, -(-int(mib) // 10) * 10)


def parts_text(parts: Iterable[str]) -> str:
    """*parts* (`ocr.place`'s names) in the window's language, as a list."""
    return _(", ").join(_(PART_NAMES[p]) for p in parts if p in PART_NAMES)


def plan_text() -> str:
    """The note on the session's GPU plan (`ocr.place.session`), in the window's language: how much the start was short
    by and what went to the processor for it, or that the settings fixed it; what failed on the GPU since (the net);
    "" when the start had room and nothing failed, or no plan was made."""
    from .ocr import place

    plan = place.session()
    lines = []
    if plan is not None and plan.short:
        if plan.cpu:
            lines.append(_(PLAN_SHORT).format(mb=short_mb(plan.short), parts=parts_text(plan.cpu)))
        else:
            lines.append(_(PLAN_FIXED).format(mb=short_mb(plan.short)))
    failed = [p for p in place.TO_PROCESSOR if place.failure(p)]
    if failed:
        lines.append(_(PLAN_FAILED).format(parts=parts_text(failed)))
    return "\n".join(lines)


def ocr_device(settings: Any, ocr: Any, cuda: bool, gpu: str) -> StageDevice:
    """Where the OCR readers run: where *ocr* (the window's `Readers`) has them (its ``placement``); without readers
    that decide, where the session's plan puts them with *settings* (`ocr.place.readers_placement`, *cuda* as
    known; a command that has none makes it)."""
    from .ocr import place

    placement = getattr(ocr, "placement", None)
    if not isinstance(placement, place.Placement):
        if ocr is not None and getattr(ocr, "settings", None) is None:
            placement = place.Placement("cpu", place.NOT_ASKED)  # (readers loaded without settings stay on the CPU)
        else:
            try:
                placement = place.readers_placement(settings, cuda=cuda)
            except Exception:  # noqa: BLE001 - nothing to judge on
                placement = place.Placement("cpu", place.UNKNOWN)
    if placement.why == place.SET:
        what = _(OCR_SET["gpu" if placement.device == "gpu" else "cpu"])
    elif placement.why in OCR_WHY:
        what = _(OCR_WHY[placement.why]).format(error=placement.error or "?")
    else:
        what = _("The OCR readers")
    on_gpu = placement.device == "gpu"
    return StageDevice("ocr", "gpu" if on_gpu else "cpu", what, gpu if on_gpu else "")


WINDOW_CACHE_ROWS = {  # what the server TASlation started got (`ollama_start.ServerSetup`), in the translator's row
    "on": "Started by TASlation with the window cache",
    "off": "Started by TASlation without the window cache",
}


def window_cache_text(settings: Any) -> str:
    """What the Ollama at the address of *settings* got from TASlation, in the window's language (`WINDOW_CACHE_ROWS`;
    the record in the state folder says it for a server another TASlation started); "" for an Ollama TASlation did not
    start."""
    from .ollama_start import setup_of

    try:
        setup = setup_of(settings.ollama_url, getattr(settings, "state_dir", None))
    except (OSError, ValueError, AttributeError):
        return ""
    if setup is None:
        return ""
    return _(WINDOW_CACHE_ROWS["on" if setup.full_window else "off"])


def _translator_device(settings: Any, translator: Any, gpu: str) -> StageDevice:
    """Where Ollama has the translator's model: all of it in video memory, none, or a part (/api/ps)."""
    from .translate import TranslationError

    try:
        if not callable(getattr(translator, "_loaded", None)):
            from .translate.models import make_translator, wanted_name

            translator = make_translator(settings, wanted_name(settings.ollama_model, settings.target_language))
        model = getattr(translator, "model", "")
        entry = translator._loaded(model)
    except (TranslationError, OSError, AttributeError, ValueError):
        return StageDevice("translate", "", _("Ollama"), why=_("Ollama is not answering"))
    what = _("Ollama: {model}").format(model=model) if model else _("Ollama")
    cache = window_cache_text(settings)
    if cache:
        what = f"{what}; {cache}"
    if entry is None:
        return StageDevice("translate", "", what, why=_("Not loaded now: Ollama loads it for the first line"))
    size, vram = entry.get("size"), entry.get("size_vram")
    if not size or vram is None:
        return StageDevice("translate", "", what, why=_("Ollama does not say"))
    share = max(0.0, min(1.0, float(vram) / float(size)))
    if share >= 0.995:
        return StageDevice("translate", "gpu", what, gpu)
    if share <= 0.005:
        return StageDevice("translate", "cpu", what)
    return StageDevice("translate", "both", what, gpu, share)


def seconds_text(seconds: float | None) -> str:
    """Seconds a page as the list shows them ("0.4 s", "12 s"), "-" for none."""
    if seconds is None:
        return "-"
    return _("{seconds} s").format(seconds=f"{seconds:.1f}" if seconds < 10 else f"{seconds:.0f}")


def lines(settings: Any, times: StageTimes | None = None, translator: Any = None, **known: Any) -> list[str]:
    """What `taslation doctor` prints: a line per stage, where it runs, what runs there and the seconds a page; then
    what the judgement found short and sent to the processor, when it did (`plan_text`)."""
    times = times if times is not None else StageTimes.load(settings.state_dir)
    seconds = times.per_page()
    out = []
    for row in stage_devices(settings, translator, **known):
        took = seconds.get(row.stage)
        timing = f"{seconds_text(took)} a page" if took is not None else "not timed yet"
        out.append(f"  {_(STAGE_NAMES[row.stage])}: {row.where()} ({row.what}); {timing}")
    out += [f"  {line}" for line in plan_text().splitlines()]
    out.append(f"  (seconds a page: the mean of the last {len(times)} page(s) lettered)" if len(times)
               else "  (seconds a page: none yet; they are kept when TASlation closes after translating pages)")
    return out
