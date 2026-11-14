"""What each stage of a page runs on - detection, OCR, the translator and the erase - "GPU (its name)" or "CPU", and
how many seconds a page took there on the last pages lettered (`StageTimes`: numbers alone, kept in
``<state dir>/timings.json`` when the window closes). Tools > Settings... > System shows it (`ui.dialogs.system_page`),
and `taslation doctor` prints it (`lines`).

Only CUDA counts as a GPU here. Nothing is started or loaded to find out: torch's CUDA is asked for the GPU's name
only once it is in use (asking first would take video memory the translator needs), else NVIDIA's driver library
(NVML, ``nvml.dll`` in System32, by its full path) is asked for it; Ollama is asked ``/api/ps`` (`OllamaTranslator.
_loaded`), which says how much of a loaded model is in video memory and never loads one. Where the stages run:

* detection: the classical detectors on the CPU; with the layout model in use (`detect_model`, installed) the model
  runs on the GPU where torch has CUDA, else on the CPU;
* OCR: the OCR readers on the CPU (they are loaded there: `ocr.charspot`);
* translation: Ollama's model on the GPU, the CPU or both, as /api/ps says while it is loaded;
* erasing: the paper fill on the CPU; LaMa on the art where `art_erase` runs it on this computer and it is installed
  (`artwork.available`: "auto" only where torch has CUDA, "lama" on the CPU too), on the GPU where torch has CUDA."""

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
    """The window closes: the seconds of this session's pages kept for the next look (`StageTimes.save`)."""
    times = getattr(pipeline, "stage_times", None)
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
    memory = _NvmlMemory()
    found = _nvml_first(lambda nvml, handle: nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(memory)) == 0)
    return int(memory.total // (1024 * 1024)) if found else 0


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


# ------------------------------------------------------------------ the stages
def stage_devices(settings: Any, translator: Any = None, cuda: bool | None = None,
                  gpu: str | None = None) -> list[StageDevice]:
    """Where each of `STAGES` runs with *settings* (the settings in force), the translator *translator* (an
    `OllamaTranslator`, the window's; one is made for the settings when None or not Ollama's) asked for its model;
    *cuda* and *gpu* as `artwork.has_cuda` (`cuda_available`, asked once a session) and `gpu_name` say when None.
    The erase on the art is where the pipeline has it, by the same rule (`artwork.available` with this *cuda*)."""
    from .detect import layout
    from .render import artwork

    cuda = artwork.has_cuda() if cuda is None else cuda
    name = (gpu_name() if cuda else "") if gpu is None else gpu
    on_gpu = "gpu" if cuda else "cpu"
    models_dir = settings.models_dir
    detect_model = getattr(settings, "detect_model", "off")
    art_erase = getattr(settings, "art_erase", "auto")
    lama = getattr(settings, "erase_mode", "fill") == "fill" and artwork.available(models_dir, art_erase, cuda=cuda)
    model = (detect_model == "on" or (detect_model == "auto" and lama)) and layout.available(models_dir)
    out = [StageDevice("detect", on_gpu if model else "cpu",
                       _("The layout model and the classical detectors") if model else _("The classical detectors"),
                       name if model else ""),
           StageDevice("ocr", "cpu", _("The OCR readers"))]
    out.append(_translator_device(settings, translator, name))
    out.append(StageDevice("erase", on_gpu if lama else "cpu", _("LaMa on the drawing, the paper fill in the bubbles")
                           if lama else _("The paper fill"), name if lama else ""))
    return out


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
    """What `taslation doctor` prints: a line per stage, where it runs, what runs there and the seconds a page."""
    times = times if times is not None else StageTimes.load(settings.state_dir)
    seconds = times.per_page()
    out = []
    for row in stage_devices(settings, translator, **known):
        took = seconds.get(row.stage)
        timing = f"{seconds_text(took)} a page" if took is not None else "not timed yet"
        out.append(f"  {_(STAGE_NAMES[row.stage])}: {row.where()} ({row.what}); {timing}")
    out.append(f"  (seconds a page: the mean of the last {len(times)} page(s) lettered in the window)" if len(times)
               else "  (seconds a page: none yet; they are kept when the window closes after translating pages)")
    return out
