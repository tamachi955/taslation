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
the judgement at the start put them (`Readers.place`, `taslation.ocr.place`), reading the same there; CPT always on the
CPU. Crops come from memory; nothing here writes an image. The weights of all three are CC BY-NC-SA
4.0: never bundled, never fetched by the application (``setup_models.py``, after a person agreed in ``install.ps1``).

An install from before the three has charspot alone: `Readers` then works with it, `settle` changes nothing, and one
line says so (``ocr.one_reader`` in the window's status line, a line of ``taslation doctor``).
"""

from __future__ import annotations

import dataclasses
import logging
import threading
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
    window's own object), charspot and nar go where the session's plan has them (`place.readers_placement`: the
    judgement at the start; ``ocr_runs_on`` "cpu" or "gpu" from the next read), and stay there - placed again only
    after Menu > Release the model now let their GPU copies go (`release_gpu`) or that setting changed. A failure on
    the GPU puts them on the CPU for the rest of the session (`_gpu_failed`). `placement` says where they are and
    why. Without *settings* they stay on the CPU, as before. CPT stays on the CPU (`place`'s docstring says why)."""

    # (as the class has them: readers made without `__init__`, a test's, read on the CPU and decide nothing)
    settings: Any = None
    placement = place.Placement("cpu", place.NOT_ASKED)

    def __init__(self, models_dir: Path, threads: int = 0, settings: Any = None):
        models_dir = Path(models_dir)
        self.charspot = CharspotEngine(models_dir / OCR_CHARSPOT.dirname, threads)
        self.missing = missing_readers(models_dir)
        self._nar: Any = None
        self._cpt: Any = None
        self.settings = settings
        self.placement = place.Placement("cpu", place.NOT_ASKED)  # where charspot and nar read now, and why
        self._placed_for: str | None = None  # ``ocr_runs_on`` the placement was made with (None: place them again)
        self._lock = threading.RLock()  # one placing at a time
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
        """Charspot and nar placed with *settings* from now on (the window's own object), now; the placement."""
        with self._lock:
            self.settings = settings
        return self.place()

    def gpu_mib(self) -> int:
        """What the readers that go to the GPU need there, in MiB (`place.CHARSPOT_MIB`, `place.NAR_MIB`), their CUDA
        graphs with them where they capture them (`place.readers_graphs`)."""
        return place.CHARSPOT_MIB + (place.NAR_MIB if self._nar is not None else 0) + place.readers_graphs()

    def place(self) -> place.Placement:
        """Charspot and nar put where `place.readers_placement` has them (the session's plan, made now where none
        was: a command); the placement. A copy to the GPU that fails leaves them on the CPU (`_gpu_failed`)."""
        with self._lock:
            settings = self.settings
            if settings is None:
                return self.placement
            self._placed_for = str(getattr(settings, "ocr_runs_on", "auto") or "auto")
            try:
                decided = place.readers_placement(settings)
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

    def release_gpu(self) -> None:
        """The readers' GPU memory given back now (Menu > Release the model now: `Pipeline.gpu_releases`); they read
        on the CPU until the next read puts them where the plan has them again (`_check`). Never raises."""
        with self._lock:
            self._placed_for = None
            if self.placement.device != "gpu":
                return
            for engine in self._movable():
                engine.to("cpu")
            self.placement = place.Placement("cpu", place.RELEASED)

    def holds_gpu(self) -> bool:
        """Whether charspot and nar read on the GPU now (what Release the model now gives back of them)."""
        return self.placement.device == "gpu"

    def _gpu_failed(self, reader: str, why: str) -> None:
        """A reader failed on the GPU (`place.DeviceModels.run`): all of them on the CPU for the rest of the session
        (`place.failed`)."""
        with self._lock:
            place.failed(place.READERS, why)
            for engine in self._movable():
                engine.to("cpu")
            self.placement = place.Placement("cpu", place.FAILED, error=why)

    def _check(self) -> None:
        """Before a read: placed again after a release, or when ``ocr_runs_on`` changed (`place`)."""
        settings = self.settings
        if settings is None or self.placement.why == place.FAILED:
            return
        if self._placed_for != str(getattr(settings, "ocr_runs_on", "auto") or "auto"):
            self.place()

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
        """Charspot's *reading* of *image* with the text the readers `agree` on, and what each read (``readings``).
        Its boxes and scores stay."""
        if self._nar is None:
            return reading
        self._check()
        nar, third = written(self._nar.read(image)), []

        def cpt() -> str:
            third.append(written(self._cpt.read(image)))
            return third[0]

        text, parted = agree(reading.text, nar, cpt)
        return dataclasses.replace(reading, text=text, split=parted, readings=(reading.text, nar, *third))

    def unanimous(self, image: Image.Image, text: str) -> bool:
        """Whether nar and CPT both read charspot's *text* in *image*, as readings are compared (`normal`); False
        without them."""
        if self._nar is None or not text:
            return False
        self._check()
        want = normal(text)
        return normal(written(self._nar.read(image))) == want and normal(written(self._cpt.read(image))) == want
