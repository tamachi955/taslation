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

All three share the CPU and one thread setting (``ocr_threads``, torch's global); the GPU stays with Ollama. Crops come
from memory; nothing here writes an image. The weights of all three are CC BY-NC-SA 4.0: never bundled, never fetched
by the application (``setup_models.py``, after a person agreed in ``install.ps1``).

An install from before the three has charspot alone: `Readers` then works with it, `settle` changes nothing, and one
line says so (``ocr.one_reader`` in the window's status line, a line of ``taslation doctor``).
"""

from __future__ import annotations

import dataclasses
import logging
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import OCR_CHARSPOT, OCR_SECOND_READERS
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


class Readers:
    """The OCR models in *models_dir* on the CPU. Raises `ModelNotInstalled` without charspot. Without either of the
    others (`missing`) charspot reads alone, as an install from before them did."""

    def __init__(self, models_dir: Path, threads: int = 0):
        models_dir = Path(models_dir)
        self.charspot = CharspotEngine(models_dir / OCR_CHARSPOT.dirname, threads)
        self.missing = missing_readers(models_dir)
        self._nar: Any = None
        self._cpt: Any = None
        if self.missing:
            LOG.info("reading with charspot alone: %s not installed (install.cmd adds them)", ", ".join(self.missing))
            return
        from .cpt import CptEngine
        from .nar import NarEngine

        nar_model, cpt_model = OCR_SECOND_READERS
        self._nar = NarEngine(models_dir / nar_model.dirname)
        self._cpt = CptEngine(models_dir / cpt_model.dirname)

    def read_chars(self, image: Image.Image) -> CharspotReading:
        return self.charspot.read_chars(image)

    def read(self, image: Image.Image) -> str:
        return self.charspot.read(image)

    def read_with_confidence(self, image: Image.Image) -> tuple[str, float]:
        return self.charspot.read_with_confidence(image)

    def settle(self, image: Image.Image, reading: CharspotReading) -> CharspotReading:
        """Charspot's *reading* of *image* with the text the readers `agree` on. Its boxes and scores stay."""
        if self._nar is None:
            return reading
        text, parted = agree(reading.text, written(self._nar.read(image)), lambda: written(self._cpt.read(image)))
        return dataclasses.replace(reading, text=text, split=parted)

    def unanimous(self, image: Image.Image, text: str) -> bool:
        """Whether nar and CPT both read charspot's *text* in *image*, as readings are compared (`normal`); False
        without them."""
        if self._nar is None or not text:
            return False
        want = normal(text)
        return normal(written(self._nar.read(image))) == want and normal(written(self._cpt.read(image))) == want
