"""Data types shared by the pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 (exclusive)
# The status of a region the reader made "erase only" (its kind `annotations.ERASE_ONLY`): its lettering is erased
# and nothing is set; it is never translated, flagged, or counted as untranslated (`pipeline.Pipeline._erase_only`).
ERASED = "erase"


@dataclass
class TextRegion:
    """A speech bubble (or caption box) found on the page."""

    x0: int
    y0: int
    x1: int
    y1: int
    mask: np.ndarray  # uint8 (h, w): 255 = bubble interior where text may be erased/drawn
    text_box: Box  # bounding box of the original text, image coordinates
    order: int = 0  # reading order on the page (0 = first)
    kind: str = "bubble"
    source_text: str = ""
    translated_text: str = ""
    status: str = "detected"  # detected | ocr-empty | not-japanese | translated | untranslated | erase (erase only)
    font_size: int = 0
    size_cap: int = 0  # the largest size it may be set at, from the rest of its page (`Pipeline.cap_sizes`; 0 = none)
    letter_flags: tuple[str, ...] = ()  # what its lettering could not do as formatted ("no-fit", "font-missing", ...)
    from_cache: bool = False
    unit: int = 0  # index of the page unit (0 = right page of a spread or the single page)
    pieces: int = 0  # glyph-sized dark pieces the detector counted (text blocks only)
    ocr_confidence: float = 1.0  # `taslation.ocr.charspot.confidence`, under `review.OCR_UNSURE` when the readers split (1.0 = not measured)
    ocr_split: bool = False  # the OCR's readers gave three different lines
    speaker: str = ""  # reader-made premises: who says it ...
    tag: str = ""  # ... what kind of text (speech, thought, shout, narration, sfx, handwritten) ...
    continues: bool = False  # ... whether the sentence goes on in the next bubble ...
    remark: str = ""  # ... and a short remark for the translator ...
    style: Any = None  # ... and how the reader formatted its lettering (annotations.RegionStyle; None = automatic)
    order_hint: int = -1  # reading order set by the reader (-1 = as detected)
    core_box: Box | None = None  # text box before lettering against the outline was taken in (None = none was)
    edge_pieces: int = 0  # dark pieces taken in from against the outline (counted in *pieces*)
    letter_box: Box | None = None  # text blocks: box of the lettering that is erased (None = the text box)
    glyph: float = 0.0  # typical size of a piece of the lettering, as the detector measured it (0 = not measured)
    beyond_box: Box | None = None  # a column taken in past the interior (dark bubbles): kept only if the OCR reads it
    before_beyond: Any = None  # (bbox, text box, mask, pieces taken) as the region was before that column
    room: int = 0  # characters of translation the region has room for at the size of its lettering (0 = plenty)
    flags: list[str] = field(default_factory=list)  # why the translation deserves a look (taslation.review.REASONS)
    reader_note: str = ""  # a note for the reader (a pun, a reference the translation cannot carry)
    from_model: bool = False  # found by the layout model (`detect.layout`), not by the classical detectors
    tier: int = 0  # a model region's classical shape: from a classical region (0), its crop (1), a white area (2), none (3)
    after: Any = None  # a model region's classical shape, taken after the reading (`detect.layout.take_shape`)
    adopted: Any = None  # the classical region that gave a model region its shape (on that shape only)
    repeats: Any = None  # a region left out as a repeat: the region read as text that it repeated
    inpainted: Any = None  # what LaMa filled in for it: (the key of what it saw, the pixels, the hole), memory only
    char_size: float = 0.0  # the size of its reading's largest character (0 = not measured)
    char_boxes: list[Box] = field(default_factory=list)  # a model region: where its reading found each character (page)
    angle: float = 0.0  # degrees its lettering is turned counter-clockwise (`detect.tilt`; 0 = upright)
    tilt: Any = None  # the slant measured (`detect.tilt.Tilt`), or "set" when it came with the region; None = not yet
    char_quads: list[Any] = field(default_factory=list)  # a slanted model region: its characters' turned boxes (page)
    panel: Box | None = None  # the box of the panel it is in, when its page's panels were found (`detect.order_regions`)

    @property
    def bbox(self) -> Box:
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def dark(self) -> bool:
        return self.kind in ("dark-bubble", "text-on-dark", "text-dark", "manual-dark")

    def crop(self, image: np.ndarray, box: Box | None = None, pad: int = 0) -> Image.Image:
        """Crop *image* (H, W, 3 uint8) to *box* (default: text box) with padding, clamped to the bubble."""
        bx0, by0, bx1, by1 = box or self.text_box
        x0 = max(self.x0, bx0 - pad)
        y0 = max(self.y0, by0 - pad)
        x1 = min(self.x1, bx1 + pad)
        y1 = min(self.y1, by1 + pad)
        return Image.fromarray(image[y0:y1, x0:x1])

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "unit": self.unit,
            "kind": self.kind,
            "bbox": list(self.bbox),
            "text_box": list(self.text_box),
            "source_text": self.source_text,
            "translated_text": self.translated_text,
            "status": self.status,
            "font_size": self.font_size,
            "from_cache": self.from_cache,
            "ocr_confidence": round(self.ocr_confidence, 3),
            **region_meta(self),
        }


def region_meta(region: Any) -> dict[str, Any]:
    """The reader-made facts about a region, as given to the model (empty when there are none)."""
    meta: dict[str, Any] = {}
    if getattr(region, "speaker", ""):
        meta["speaker"] = region.speaker
    if getattr(region, "tag", ""):
        meta["kind"] = region.tag
    if getattr(region, "continues", False):
        meta["continues"] = True
    if getattr(region, "remark", ""):
        meta["note"] = region.remark
    if getattr(region, "room", 0):
        meta["room"] = int(region.room)
    return meta


def apply_order_hints(regions: list["TextRegion"]) -> list["TextRegion"]:
    """Put regions the reader ordered first, in that order; the rest keep the detected order."""
    if not any(r.order_hint >= 0 for r in regions):
        return regions
    hinted = sorted((r for r in regions if r.order_hint >= 0), key=lambda r: r.order_hint)
    out = hinted + [r for r in regions if r.order_hint < 0]
    for i, r in enumerate(out):
        r.order = i
    return out


def box_iou(a: Box, b: Box) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class PageResult:
    image: Image.Image  # translated page (memory only)
    original: Image.Image
    regions: list[TextRegion]
    timings: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    cache_hits: int = 0  # page units served from the translation cache
    cache_misses: int = 0
    fingerprints: list[str] = field(default_factory=list)  # one per page unit, right page first
    units: list[Any] = field(default_factory=list)  # the page units (fingerprint.PageUnit), memory only
    error: str = ""  # e.g. Ollama unreachable; regions are then left untranslated

    @property
    def translated(self) -> list[TextRegion]:
        return [r for r in self.regions if r.status == "translated"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "size": list(self.original.size),
            "regions": [r.to_dict() for r in self.regions],
            "timings": {k: round(v, 3) for k, v in self.timings.items()},
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "fingerprints": list(self.fingerprints),
            "notes": list(self.notes),
            "error": self.error,
        }
