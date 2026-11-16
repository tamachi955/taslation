"""Tools > Release the model now (`release_now`): the GPU memory TASlation's own models hold given back at once, for a
game or another program, without closing the window; and the layers on the GPU (``ollama_num_gpu``) set on the
window's translators when the Settings dialog saved them (`apply_num_gpu`).

What goes:

* the translation model in Ollama (`OllamaTranslator.release_now`: the models the window's translator had Ollama load
  or use this session, unloaded with a request of Ollama's own API, ``keep_alive`` 0, whatever ``ollama_keep_alive``
  says). A model of another program's in the same Ollama is never asked to go, and Ollama itself is neither stopped
  nor started;
* the page models (`Pipeline.release_gpu_models`, the path a load of the translation model takes: the layout model and
  LaMa let go of their memory, each loaded again when a page needs it);
* the OCR readers' copies on the GPU, where the rule put two of them there (``ocr_runs_on``: `Readers.release_gpu`,
  one of the pipeline's ``gpu_releases``): they read on the processor, and the next page decides again where. (The
  release before a load of the translation model may keep them there, `Readers.keeps_through_load`; this one never
  does.)

What stays: the OCR readers on the processor (their own copies, as loaded: on the CPU they hold no GPU memory), and the
CUDA context PyTorch made once a page model or a reader ran on the GPU (a few hundred MB: torch gives back the memory
it cached, not its context, which goes with the window). The status line names what was released, the OCR's GPU
memory among it when it held some (`released_line`). The next line to translate loads the model again as ever
(`OllamaTranslator.ensure_loaded`, said in the status line). The model's load at the window's start
(``load_model_at_start``), when it is still under way, is waited for and released with the rest, and the page models
are not warmed after it.

Refused with a plain line while the model is in use: a page or a request being translated (``busy``), one waiting for
the models (``_queued``), a whole-book run (`constants.in_a_run`). Otherwise it is a job of the window's worker, after
whatever is queued there, so it never meets a translation; the status line says what was released."""

from __future__ import annotations

from typing import Any

from .constants import in_a_run

RELEASE_ENTRY = "Release the model now"  # the Tools menu's entry
# (the 16 languages of the tip and the lines that name the OCR: `locales/features/ocr_release.py`)
RELEASE_TIP = ("Give back the GPU memory of TASlation's models now, for another program: the translation model, the "
               "page models and the OCR readers that run on the GPU (they go on reading on the processor). The next "
               "translation loads the model again.")
RELEASE_REFUSED = "Not now: a translation or a whole-book run is going on. Release the model once it has ended."
RELEASING = "Releasing the model..."
RELEASED_BOTH = "Released the translation model ({model}) and the page models. Each loads again when it is needed."
RELEASED_MODEL = "Released the translation model ({model}). It loads again for the next translation."
RELEASED_PAGES = "Released the page models. The translation model was not loaded."
RELEASED_NOTHING = "Nothing to release: TASlation's models were not loaded."
# ... and with the OCR readers' GPU memory (they read on the processor until the next page decides again)
RELEASED_ALL = ("Released the translation model ({model}), the page models and the OCR's GPU memory. Each loads again "
                "when it is needed; the OCR reads on the processor until the next page.")
RELEASED_MODEL_OCR = ("Released the translation model ({model}) and the OCR's GPU memory. The model loads again for the "
                      "next translation; the OCR reads on the processor until the next page.")
RELEASED_PAGES_OCR = ("Released the page models and the OCR's GPU memory; the OCR reads on the processor until the next "
                      "page. The translation model was not loaded.")
RELEASED_OCR = ("Released the OCR's GPU memory; it reads on the processor until the next page. The translation model "
                "and the page models were not loaded.")


def in_use(window: Any) -> bool:
    """Whether the translation model may be at work now: a job of the window's (a page or a request being translated),
    a request that waits for the models, or a whole-book run."""
    return bool(getattr(window, "busy", False) or getattr(window, "_queued", None) is not None or in_a_run(window))


def translators(window: Any) -> list[Any]:
    """The window's translators that hold a model (`OllamaTranslator.release_now`): its pipeline's and its own, each
    once."""
    found: list[Any] = []
    for translator in (getattr(getattr(window, "pipeline", None), "translator", None),
                       getattr(window, "translator", None)):
        if translator is not None and hasattr(translator, "release_now") and all(t is not translator for t in found):
            found.append(translator)
    return found


def holds_memory(model: Any) -> bool:
    """Whether a page model (the layout model, LaMa) is loaded now: what it was loaded into is still there."""
    return any(getattr(model, name, None) is not None for name in ("_net", "_model"))


def ocr_holds_gpu(pipeline: Any) -> bool:
    """Whether the pipeline's OCR readers read on the GPU now (`Readers.holds_gpu`; a stand-in without it: no)."""
    holds = getattr(getattr(pipeline, "ocr", None), "holds_gpu", None)
    try:
        return bool(holds()) if callable(holds) else False
    except Exception:  # noqa: BLE001 - nothing said of it, as before
        return False


def release_models(window: Any) -> tuple[list[str], bool, bool]:
    """(worker) The window's translation models unloaded (`OllamaTranslator.release_now`) and the page models and the
    OCR readers' GPU copies let go (`Pipeline.release_gpu_models`): the names of the translation models that were
    loaded, whether a page model held memory, and whether the OCR readers did (`ocr_holds_gpu`). Never raises. The
    window's load of the model at its start, when under way, is waited for first (`JobsMixin.wait_load_at_start`), so
    that what it loads goes too and nothing loads after the release."""
    wait = getattr(window, "wait_load_at_start", None)
    if wait is not None:
        try:
            wait()
        except Exception:  # noqa: BLE001 - what it loaded goes after keep_alive, as after a page
            pass
    names: list[str] = []
    for translator in translators(window):
        try:
            names += [n for n in translator.release_now() if n not in names]
        except Exception:  # noqa: BLE001 - Ollama's own keep_alive ends it all the same
            pass
    pipeline = getattr(window, "pipeline", None)
    pages = ocr = False
    if pipeline is not None:
        pages = any(holds_memory(m) for m in (getattr(pipeline, "layout", None), getattr(pipeline, "art_eraser", None))
                    if m is not None)
        ocr = ocr_holds_gpu(pipeline)
        try:
            pipeline.release_gpu_models()
        except Exception:  # noqa: BLE001 - it stays in memory, no more than that
            pass
    return names, pages, ocr


def released_line(names: list[str], pages: bool, ocr: bool = False) -> tuple[str, dict[str, str]]:
    """What the status line says once `release_models` is done: its key and values (*ocr*: the OCR readers' GPU
    memory was released too; else nothing is said of the OCR, which read on the processor and stays there)."""
    model = ", ".join(names)
    if names:
        key = (RELEASED_ALL if ocr else RELEASED_BOTH) if pages else (RELEASED_MODEL_OCR if ocr else RELEASED_MODEL)
        return key, {"model": model}
    if ocr:
        return (RELEASED_PAGES_OCR if pages else RELEASED_OCR), {}
    return (RELEASED_PAGES if pages else RELEASED_NOTHING), {}


def release_now(window: Any) -> bool:
    """Tools > Release the model now: refused in the status line while the model is in use (`in_use`), else a job of
    the window's worker (`release_models`) whose result the status line says. Whether it was queued."""
    if in_use(window):
        window.say(RELEASE_REFUSED)
        return False
    window.say(RELEASING)

    def job() -> None:
        key, values = released_line(*release_models(window))
        window._post("status", key=key, values=values)

    window._jobs.put(job)
    return True


def apply_num_gpu(window: Any, value: Any) -> None:
    """The Settings dialog saved ``ollama_num_gpu`` (*value*): every translator of the window sends it from the next
    request on (a model Ollama holds with other layers may be loaded again for it); a value that is none leaves them
    as they are."""
    from ..translate.ollama import num_gpu_value

    try:
        layers = num_gpu_value(value)
    except ValueError:
        return
    for translator in translators(window):
        translator.num_gpu = layers


__all__ = ["RELEASE_ENTRY", "RELEASE_TIP", "apply_num_gpu", "in_use", "ocr_holds_gpu", "release_models", "release_now",
           "released_line", "translators"]
