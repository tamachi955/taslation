"""The three readers of a page's lettering, and the one rule that takes their word.

charspot (`taslation.ocr.charspot`) finds each character on its own, so it does not lose its way in a long line, and its
boxes and scores say whether something is lettering at all; manga-ocr-nar-small (`.nar`) reads a line in one go, and
manga-ocr-base-CPT-flex (`.cpt`) writes it out. They go wrong in different places, so two of them seldom go wrong the
same way.

Charspot stays the gate (`charspot_accepts`, ``Pipeline._verdict``): the others are not asked about what it turned
down, so a crop without text costs what it cost before, but for a short line in a bubble (one or two characters,
``Pipeline._short_line``): whether all three read the same there (`Readers.unanimous`) decides one charspot read as a
single character or was less sure of. `Readers.settle` is what is asked of them, and its rule is
`agree`: charspot and nar reading the same take it, with no third reading; otherwise CPT reads it too and the reading
closest to the other two stands (`medoid`). The chosen text goes with charspot's boxes and scores: they are what the
page's character sizes and the gates are measured on.

All three share one thread setting on the CPU (``ocr_threads``, torch's global). charspot and nar read on the GPU where
it has room beside the translator and the page models (`Readers.decide`, `taslation.ocr.place`), reading the same there;
CPT always on the CPU. Crops come from memory; nothing here writes an image. The weights of all three are CC BY-NC-SA
4.0: never bundled, never fetched by the application (``setup_models.py``, after a person agreed in ``install.ps1``).

An install from before the three has charspot alone: `Readers` then works with it, `settle` changes nothing, and one
line says so (``ocr.one_reader`` in the window's status line, a line of ``taslation doctor``).
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import OCR_CHARSPOT, OCR_SECOND_READERS
from . import place
from .charspot import CharspotEngine, CharspotReading, written

LOG = logging.getLogger(__name__)

# All three readings at least this far apart (edits over the longer reading's length) are three different lines: the
# region is flagged, whichever was taken.
SPLIT_DISTANCE = 0.2

_MARKS = (("…", "..."), ("‥", ".."), ("～", "~"), ("〜", "~"), ("―", "-"), ("—", "-"))


def normal(text: str) -> str:
    """*text* as readings are compared: compatibility forms folded, one spelling of dots, waves and dashes, no spaces."""
    text = unicodedata.normalize("NFKC", text)
    for mark, plain in _MARKS:
        text = text.replace(mark, plain)
    return "".join(ch for ch in text if not ch.isspace())


def edits(a: str, b: str) -> int:
    """The edit distance between *a* and *b*."""
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        previous, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (ca != cb))
    return row[-1]


def distance(a: str, b: str) -> float:
    """Edits between two readings over the longer one's length: 0 the same, 1 nothing in common."""
    return edits(a, b) / max(1, len(a), len(b))


def medoid(readings: list[str]) -> str:
    """The reading with the least total distance to the others; a tie goes to the earlier one."""
    texts = [normal(t) for t in readings]
    totals = [sum(distance(t, other) for other in texts) for t in texts]
    return readings[min(range(len(readings)), key=lambda i: (round(totals[i], 9), i))]


def split(readings: list[str]) -> bool:
    """Whether no two of *readings* are close: every pair at least `SPLIT_DISTANCE` apart."""
    texts = [normal(t) for t in readings]
    return all(distance(a, b) >= SPLIT_DISTANCE for i, a in enumerate(texts) for b in texts[i + 1:])


def agree(charspot: str, nar: str, cpt: Callable[[], str]) -> tuple[str, bool]:
    """The rule: the text it takes, and whether the readers were split. *charspot* and *nar* the same, it; else the
    `medoid` of the three, *cpt* read only now, ties to charspot, then nar."""
    if normal(charspot) == normal(nar):
        return charspot, False
    readings = [charspot, nar, cpt()]
    return medoid(readings), split(readings)


def missing_readers(models_dir: Path) -> list[str]:
    """The names of the second readers not in *models_dir*; nothing missing means all three read."""
    return [m.dirname for m in OCR_SECOND_READERS if m.missing(Path(models_dir))]


def place_with(ocr: Any, settings: Any) -> Any:
    """*ocr* (`Readers`, as loaded) deciding where it reads with *settings* from now on (`Readers.use`), returned as it
    is; anything else (a test's stand-in) untouched."""
    if isinstance(ocr, Readers):
        ocr.use(settings)
    return ocr


class Readers:
    """The OCR models in *models_dir*. Raises `ModelNotInstalled` without charspot. Without either of the others
    (`missing`) charspot reads alone, as an install from before them did.

    Where they run (`taslation.ocr.place`): given the *settings* in force (here, or later by `use` / `place_with`: the
    window's own object, read again at every decision), charspot and nar go to the GPU when ``ocr_runs_on`` and the
    room there say so - decided then, and again at the next read once the GPU memory was let go (`release_gpu`) or a
    setting the decision depends on changed (`place.watched`), never while the translation model loads or answers
    (`place.busy`: the first read after it decides); a load of the translation model leaves them on the GPU where the
    rule still finds room for them beside it (`keeps_through_load`). `placement` says where they are and why. Without
    *settings* they stay on the CPU, as before. CPT stays on the CPU (`place`'s docstring says why)."""

    # (as the class has them: readers made without `__init__`, a test's, read on the CPU and decide nothing)
    settings: Any = None
    placement = place.Placement("cpu", place.NOT_ASKED)
    _failed = ""

    def __init__(self, models_dir: Path, threads: int = 0, settings: Any = None):
        models_dir = Path(models_dir)
        self.charspot = CharspotEngine(models_dir / OCR_CHARSPOT.dirname, threads)
        self.missing = missing_readers(models_dir)
        self._nar: Any = None
        self._cpt: Any = None
        self.settings = settings
        self.placement = place.Placement("cpu", place.NOT_ASKED)  # where charspot and nar read now, and why
        self._failed = ""  # a GPU failure this session (its type name): the CPU from then on
        self._full = ""  # an out of memory on the GPU (its type name): the CPU until the GPU memory is next let go
        self._fulls = 0  # the outs of memory this session (`place.FULLS_FOR_GOOD` of them: the CPU from then on)
        self._decided_for: tuple[Any, ...] | None = None  # `place.watched` of the settings the placement was made for
        self._decided_at = 0.0  # when the rule last decided (`time.monotonic`; the next look `place.LOOK_S` after)
        self._look: threading.Thread | None = None  # a look at the room under way (`_check`)
        self._lock = threading.RLock()  # one decision at a time
        if self.missing:
            LOG.info("reading with charspot alone: %s not installed (install.cmd adds them)", ", ".join(self.missing))
        else:
            from .cpt import CptEngine
            from .nar import NarEngine

            nar_model, cpt_model = OCR_SECOND_READERS
            self._nar = NarEngine(models_dir / nar_model.dirname)
            self._cpt = CptEngine(models_dir / cpt_model.dirname)
        for engine in self._movable():
            engine.on_gpu_failure = self._gpu_failed
        if settings is not None:
            self.use(settings)

    # ------------------------------------------------------------------ where they run
    def _movable(self) -> list[Any]:
        """The readers that go to the GPU: charspot, and nar where it is installed (a test's stand-in stays put)."""
        return [e for e in (self.charspot, self._nar) if isinstance(e, place.DeviceModels)]

    def use(self, settings: Any) -> place.Placement:
        """Where charspot and nar read decided with *settings* from now on (the window's own object, read again at
        every decision: `decide`), now; the placement."""
        with self._lock:
            self.settings = settings
            self._decided_for = None
        return self.decide()

    def gpu_mib(self) -> int:
        """What the readers that go to the GPU need there, in MiB (`place.CHARSPOT_MIB`, `place.NAR_MIB`)."""
        return place.CHARSPOT_MIB + (place.NAR_MIB if self._nar is not None else 0)

    def decide(self, facts: Callable[[Any], Any] | None = None) -> place.Placement:
        """Decide where charspot and nar read (`place.decide` with the settings in force; *facts*: the facts it
        judges on, `place.gather` when None) and put them there; the placement. Readers the rule has on the GPU stay
        there down to `place.MARGIN_MIB` left at the peak, readers on the CPU go there from `place.RETURN_MIB`
        (*staying*: the hysteresis). A copy to the GPU that fails leaves them on the CPU. While the translation model
        loads or answers (`place.busy`) nothing is decided: they read where they are, and the next read decides."""
        with self._lock:
            settings = self.settings
            if settings is None or place.busy():
                return self.placement
            self._decided_for = place.watched(settings)
            self._decided_at = time.monotonic()
            staying = self.placement.device == "gpu" and self.placement.why == place.ROOM
            try:
                decided = place.decide(settings, self.gpu_mib(), self._failed or self._full, facts=facts,
                                       staying=staying)
            except Exception as e:  # noqa: BLE001 - nothing to judge on: the CPU, as before
                LOG.info("where the OCR runs could not be decided (%s): on the CPU", type(e).__name__)
                decided = place.Placement("cpu", place.UNKNOWN)
            device = "cuda" if decided.device == "gpu" else "cpu"
            for engine in self._movable():
                if not engine.to(device):  # (a copy that failed: `_gpu_failed` put them all on the CPU, and why)
                    return self.placement
            before, self.placement = self.placement, decided
            if (before.device, before.why) != (decided.device, decided.why):
                LOG.info("the OCR readers run on the %s (%s, %s MiB left at the peak)", decided.device.upper(),
                         decided.why, decided.room)
            return decided

    def release_gpu(self, load: bool = False) -> None:
        """The readers' GPU memory given back now (before Ollama loads its model, Tools > Release the model now:
        `Pipeline.gpu_releases`); they read on the CPU, and decide again at the next read that comes while the model
        neither loads nor answers (`decide`) - also readers on the CPU, for the facts change with a load (a model of
        the reader's own is known once it was seen loaded). *load*: the release before Ollama loads the translation
        model (`Pipeline.release_before_load`), which leaves them on the GPU where `keeps_through_load` says so: they
        read there through the load, and the decision stands. An out of memory on the GPU before it (`_gpu_failed`)
        holds no longer: the next decision may put them there again. Never raises."""
        with self._lock:
            kept = self.keeps_through_load() if load else None
            place.kept_through_load(kept is not None)
            if kept is not None:
                self.placement = kept
                LOG.info("the OCR readers stay on the GPU through the translation model's load (%s MiB left at the "
                         "peak)", kept.room)
                return
            if self._full:
                self._full = ""
                for engine in self._movable():
                    engine.gpu_full = ""
            self._decided_for = None
            if self.placement.device != "gpu":
                return
            for engine in self._movable():
                engine.to("cpu")
            self.placement = place.Placement("cpu", place.RELEASED)

    def keeps_through_load(self) -> place.Placement | None:
        """Where charspot and nar, on the GPU now, stay through a load of the translation model (`release_gpu` with
        *load*), None where they do not: only where the rule put them there (`place.ROOM`; the setting's "gpu" lets
        them go, as before) for the settings in force, with no GPU failure this session and no load that came up partly
        on the CPU beside them (`place.keeps_through_loads`), and where the rule asked again now still finds room for
        them beside the whole model (`place.through_load` on `place.gather`: other programs may have grown since),
        every fact of it measured. Never raises."""
        settings = self.settings
        if (settings is None or self._failed or self._full or self.placement.device != "gpu"
                or self.placement.why != place.ROOM or place.watched(settings) != self._decided_for
                or not place.keeps_through_loads()
                or any(engine.gpu_failed or engine.gpu_full for engine in self._movable())):
            return None
        try:
            again = place.through_load(place.gather(settings), self.gpu_mib())
        except Exception as e:  # noqa: BLE001 - nothing to judge on: let go, as before
            LOG.info("the room for the OCR readers through a load could not be measured (%s)", type(e).__name__)
            return None
        if again.device != "gpu":
            LOG.info("the OCR readers go to the CPU for the translation model's load (%s, %s MiB left at the peak)",
                     again.why, again.room)
            return None
        return again

    def holds_gpu(self) -> bool:
        """Whether charspot and nar read on the GPU now (what Release the model now gives back of them)."""
        return self.placement.device == "gpu"

    def _gpu_failed(self, reader: str, why: str) -> None:
        """A reader failed on the GPU (`place.DeviceModels.run`): all of them on the CPU, for the rest of the session -
        reads that crawled there (`place.SLOW_GPU`, why `place.SLOW`) or a CUDA error -, or after an out of memory
        there (each reader's ``gpu_full``, none's ``gpu_failed``) until the GPU memory is next let go (`release_gpu`),
        which decides again; the `place.FULLS_FOR_GOOD`-th out of memory of the session holds for the rest of it."""
        with self._lock:
            movable = self._movable()
            if any(engine.gpu_full for engine in movable) and not any(engine.gpu_failed for engine in movable):
                if not self._full:
                    self._fulls += 1
                self._full = self._full or why
                if self._fulls >= place.FULLS_FOR_GOOD:
                    self._failed = self._failed or self._full
            else:
                self._failed = self._failed or why
            for engine in movable:
                engine.to("cpu")
            self.placement = place.failed_placement(self._failed or self._full)

    def _check(self) -> None:
        """Before a read: decide again when the placement is not for the settings in force (released, or a setting it
        depends on changed), unless the translation model loads or answers now (`place.busy`: a later read decides);
        and where the rule placed them ("auto"), a look at the room on a thread of its own once `place.LOOK_S` went by
        since the last decision (`_look_again`: the read does not wait for it)."""
        settings = self.settings
        if settings is None or self._failed or self._full or place.busy():
            return
        if place.watched(settings) != self._decided_for:
            self.decide()
        elif (self.placement.why in place.LOOKED_AT and time.monotonic() - self._decided_at >= place.LOOK_S
              and (self._look is None or not self._look.is_alive())):
            self._decided_at = time.monotonic()  # (one look at a time, the next LOOK_S after this one)
            self._look = threading.Thread(target=self._look_again, name="ocr-room-look", daemon=True)
            self._look.start()

    def _look_again(self) -> None:
        """The periodic look (`_check`): the rule asked again, the readers moved where it says now (`decide`, with its
        hysteresis). The facts are gathered before the decision takes its lock (an Ollama that is not there takes
        Windows about 2 s to refuse; a release before a load must not wait for that). Never raises."""
        try:
            settings = self.settings
            if settings is None:
                return
            facts = place.gather(settings)
            self.decide(lambda _settings: facts)
        except Exception as e:  # noqa: BLE001 - the readers stay where they are
            LOG.info("a look at the room for the OCR readers failed (%s)", type(e).__name__)

    # ------------------------------------------------------------------ reading
    def read_chars(self, image: Image.Image) -> CharspotReading:
        self._check()
        return self.charspot.read_chars(image)

    def read(self, image: Image.Image) -> str:
        self._check()
        return self.charspot.read(image)

    def read_with_confidence(self, image: Image.Image) -> tuple[str, float]:
        self._check()
        return self.charspot.read_with_confidence(image)

    def settle(self, image: Image.Image, reading: CharspotReading) -> CharspotReading:
        """Charspot's *reading* of *image* with the text the readers `agree` on. Its boxes and scores stay."""
        if self._nar is None:
            return reading
        self._check()
        text, parted = agree(reading.text, written(self._nar.read(image)), lambda: written(self._cpt.read(image)))
        return dataclasses.replace(reading, text=text, split=parted)

    def unanimous(self, image: Image.Image, text: str) -> bool:
        """Whether nar and CPT both read charspot's *text* in *image*, as readings are compared (`normal`); False
        without them."""
        if self._nar is None or not text:
            return False
        self._check()
        want = normal(text)
        return normal(written(self._nar.read(image))) == want and normal(written(self._cpt.read(image))) == want
