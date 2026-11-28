"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: an audit of the lettered page, numbers only.

Pages are processed as the program processes them - detection, the three readers, the erase, the typesetting - with
a stand-in translator in place of the model (`Canned`: on the sample set the professional English of the gold box a
region matches, in memory only; elsewhere invented English with that English's word lengths, as long as a made-up
text's line, else 2.39 characters for each Japanese one, the dataset's mean; no model, no network), each at its own
size and scaled down as a viewer shows it (a page fitted into ``SMALL_HEIGHT`` px of height, area resampling) - and
for every made-up page and 40 pages of the sample set also degraded as a viewer may hand it over (`DEGRADED`: JPEG
at quality 70, then a cubic down to that height; and the same softened by a 0.6 px gaussian) -, and every lettered
region is measured:

* ``resid``: pixels of the original lettering inside the erased area or the bubble's closed interior that the erase
  moved less than half the way to the paper (pieces of glyph size, not lines, and not a line the erased page keeps:
  the outline, a tail, hair), and in how many specks;
* ``ghost``: pixels of a bubble's flat light paper that the erased page has darker than that paper, whatever made
  them (a glyph half taken, a grey ghost of it, a stroke LaMa drew), LaMa's regions included;
* ``line_lost``: pixels of lines (the bubble's outline, a tail, the drawing) round the region that the erase made light
  (inside the text box only what of a line runs straight on: a glyph joined to the outline is lettering, `_pieces`),
  and ``line_cut`` those of them that break a line (`_cut`: not a stroke joined to the outline that the line goes on
  past, a neighbour's column by an outline the two share);
* ``ink_on_line`` / ``ink_out`` / ``ink_other``: lettering pixels on such a line, outside the bubble's interior (a
  closed light area round the text, closed over the lettering's pieces alone: no glyph joined to the outline), and on
  another region's interior or lettering;
* ``over_px`` / ``draft_over_px``: pixels of a region's lettering that a neighbour's erase or lettering drawn after it
  took away on the finished page, and that its own last patch showed as finished while a patch sent after it shows
  them otherwise on the page filling in (`Drafts`: the patches pasted in turn, as a window pastes them);
* ``resid_line_px`` / ``resid_shared_px``: pixels of the original lettering left that the erased page has joined to a
  line it keeps (the outline, a tail: taken for one, so ``resid`` leaves them out), and those of all left beside an
  outline the region shares with a neighbour (where the neighbour's box meets it);
* the font size against the original glyph and the room, the share of the bubble as seen that its lettering's box
  takes (``room_share``: the room it was set in and the closed interior round its text, joined over the drawing's thin
  lines - a bubble drawn see-through over hair - and its holes filled), the hyphenated lines, the lettering's own
  flags, and the room a bubble's lettering took beyond its own across (``frame``: "turned", the line turned 90
  degrees, whose lines, size and ink are measured as drawn and whose room is judged narrow in the turned frame;
  "overrun", over the outline), counted per set and scale by ``merge``;
* the text box against the lettering it holds (``box_cover``, ``box_excess``: the box of its pieces alone);
* regions with no bubble whose readers disagree (``false_likely``), regions far from every gold or made-up text,
  untranslated regions and gold texts with no region;
* the sound words (``sound``, the kind ``sfx``: `taslation.soundwords`): found, their reading set right, left as
  drawn, and the codes on the sound effects lettered (`sound_lines`).

A region whose measure crosses its threshold gets a reason code (`CODES`), and each code has its level on the
owner's scale (`CODE_LEVELS`: S1 reading fails, S2 content lost or damaged, S3 readable but hard, S4 cosmetic);
``merge``'s table goes by level, the worst first, each level's own row counting the regions with any of its codes.
The made-up pages (`synthetic_pages`:
the layouts of tools/make_sample_page.py and risky ones drawn here - tall narrow bubbles, bubbles joined or cut by
the page's edge, text on tone or white on black, tails crossing text, very small and very large characters, map
symbols, clothing patterns, sound effects, lettering that touches its outline or runs over it, heavy glyphs that
touch each other, long bars and dots, tall bubbles drawn see-through or semi-transparent over hair, a tone or a
hatching, or toned inside) also
carry exact layers (the lettering, the outlines, the interiors), so
their regions are measured against the truth as well (``t_*``).

    python tools/audit_render.py run --shard 0 --of 16 --out audit-0.json [--crops DIR] [--sets openmantra,synthetic]
    python tools/audit_render.py run --only om:1:3,syn:L01 --out two.json
    python tools/audit_render.py list --of 16
    python tools/audit_render.py merge audit-*.json --out merged.json --summary summary.md

The output holds numbers, boxes and codes only: no pixel of a page and no text of the sample set (CC BY-NC 4.0; a
public repository's artifacts can be downloaded). ``--crops`` writes small before/after pictures of flagged regions
of the MADE-UP pages only. The settings are the program's defaults on a computer with a CUDA GPU and both page models
(``detect_model`` "on", ``art_erase`` "lama"), here on the processor; ``--as-cpu`` takes the defaults of a computer
without a GPU instead. The state folder should be a scratch one (``TASLATION_STATE_DIR``): nothing is written to it.
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import math
import os
import random
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

VERSION = 11  # (11: ROOM_LOOSE, lettering small in a large room; layout 20, tall bubbles drawn see-through or
#               semi-transparent over hair, a tone or a hatching, or toned inside; 10: the lettering's box -
#               BOX_SMALL, BOX_BIG - and the closed interior round it - INK_OUT, GHOST, the residue's zone, BOX_BIG -
#               by its pieces alone, the glyphs joined to a line left out, as before 9; 9: a
#               neighbour over a region's lettering, lettering left by a line or a shared outline, an outline cut only
#               where broken, joined pairs in layouts 18 and 19, the codes' levels and the summary by them; 8: sound
#               words)
SMALL_HEIGHT = 1000  # px: a spread fitted into a browser window about this high shows a page about 700 x 1000
# the degraded scales, as a viewer may hand a page over: "jpeg" compressed at JPEG_QUALITY, then fitted into
# SMALL_HEIGHT by a cubic (a factor that is no whole number); "blur" the same, softened by a gaussian of BLUR_SIGMA px.
# Every made-up page and DEGRADED_PAGES pages of the sample set (a fixed draw) get them
DEGRADED = ("jpeg", "blur")
JPEG_QUALITY = 70
BLUR_SIGMA = 0.6
DEGRADED_PAGES = 40
DEGRADED_SEED = 70
EN_PER_JA = 2.39  # characters of professional English per Japanese character in OpenMantra
INK_DARK = 128  # an original pixel darker than this is ink (lettering, outline or drawing)
STAYS_DARK = 150  # an erased pixel still darker than this is lettering left
LIGHTENED = 180  # a line pixel the erase made lighter than this (and by LIGHTER levels) was erased
LIGHTER = 80
LINE_DARK = 110  # a line pixel counts when it was darker than this
LINE_GLYPHS = 2.5  # a dark piece longer than this many glyphs that is not inside the text box is a line
INSIDE_TEXT = 0.6  # of a piece's pixels inside the text box (grown by a third of a glyph): lettering
LINE_RUN = 1.2  # glyphs: of a line, what runs straight on this far is the line; inside the text box the rest of it ...
GLYPH_PART = 1.5  # ... in parts no longer than this many glyphs is lettering joined to it (a glyph on the outline)
LINE_STEP = 5  # degrees between the ways a straight run is looked for along
HALF_WAY = 0.5  # an erased pixel that went less than this share of the way from the original to the ground is left
LINE_FAINT = 200  # an erased pixel darker than this still joins a line the page keeps (a thin outline's grey edge)
CONTRAST = 60  # levels between the lettering and its ground under which nothing is judged left
SOLID = 0.25  # a dark area still there after an opening of this many glyphs is a fill, not a line
TEXTURED = 25  # levels of deviation of a ground above which it is a tone or a drawing (compared blurred)
DARK_KINDS = ("dark-bubble", "text-dark", "text-on-dark")  # light lettering on a dark ground
OUTLINED = 0.3  # of the rim round a closed light area that must be ink for it to be a bubble's interior

# reason codes and their thresholds
RESID_PX = 6  # dark lettering pixels left in a region after its erase ...
RESID_SHARE = 0.01  # ... and this share of its lettering's pixels
GHOST_PX = 8  # pixels of a bubble's paper darker than the paper by GHOST_DROP after the erase ...
GHOST_DROP = 40
FILL_SHARE = 0.2  # (a mark touching the outline counts when it covers this share of the bubble: painted over)
FLAT_STD = 20  # ... where the interior's paper away from the lettering deviates by no more than this (no tone)
LINE_LOST_PX = 12  # line pixels round a region on paper made light by the erase
ART_LOST_PX = 60  # the same for a region on the drawing (LaMa fills a hole there on purpose)
INK_ON_LINE_PX = 8  # lettering pixels on a line of the original
INK_OUT_PX = 15  # lettering pixels outside the closed interior round the text
INK_OTHER_PX = 6  # lettering pixels on another lettered region's interior or ink
OVER_PX = 6  # pixels of a region's lettering a neighbour's erase, lettering or patch shows otherwise ...
OVER_DROP = 100  # ... by this many grey levels or more (the glyph gone to the paper, not its anti-aliasing)
SMALL_FONT = 11  # set smaller than this (the readable size)
LOOSE_SHARE = 0.2  # the lettering's box takes less than this share of the bubble as seen (`_seen`) ...
LOOSE_SIZE = 0.6  # ... at a size under this share of the largest it may take (its cap; `room_loose`)
BOX_COVER = 0.75  # the text box holds less than this share of the original lettering's box
BOX_EXCESS = 4.5  # the text box is this many times the lettering's box (and 8 glyphs' area larger)
LOW_AGREEMENT = 0.8  # OCR confidence under this, or the readers split
NO_GOLD_SHARE = 0.3  # a region's text box overlaps no gold or made-up text box by this share of itself

CODES = {
    "RESIDUE": "specks of the original lettering left after the erase (inside the erased area or the bubble; not where "
               "LaMa or the tone fill painted the hole)",
    "GHOST": "marks on the bubble's flat paper after the erase, whatever made them (also where LaMa erased)",
    "LAMA_BUBBLE": "erased by LaMa although its lettering sits in a bubble's closed interior on flat light paper (not "
                   "a bubble drawn see-through over the drawing, which is lettering on the drawing)",
    "LINE_CUT": "outline, tail or drawing lines broken by the erase round a region on paper",
    "ART_CUT": "many lines erased round a region on the drawing (LaMa)",
    "INK_ON_LINE": "lettering drawn on an outline or a line of the drawing",
    "INK_OUT": "lettering outside the bubble's closed interior",
    "INK_OTHER": "lettering on another region's interior or lettering",
    "OVER_OTHER": "the region's lettering taken away by a neighbour's erase or lettering drawn after it, or shown "
                  "otherwise by a neighbour's patch sent after it while the page fills in",
    "LEFT_BY_LINE": "specks of the original lettering left joined to a line the erased page keeps (an outline, a "
                    "tail): taken for that line",
    "LEFT_SHARED": "specks of the original lettering left beside an outline the region shares with a neighbour",
    "SMALL": "lettering under the readable size",
    "ROOM_LOOSE": "lettering small in a large room: its box under a fifth of the bubble as seen (the room it was set "
                  "in and the interior round its text, joined over the drawing's thin lines) at under 0.6 of its cap",
    "HYPHEN": "a word hyphenated",
    "SQUEEZED": "small lettering with a hyphen or in a narrow room",
    "NOFIT": "the text did not fit (cut at the mask)",
    "TIGHT": "a glyph within a pixel of the bubble's edge",
    "BOX_SMALL": "the text box misses part of the original lettering",
    "BOX_BIG": "text on the page: the text box far larger than the lettering it holds",
    "FALSE_LIKELY": "no bubble, and the readers disagree",
    "NO_GOLD": "far from every gold text (sample set) - a false region or an unannotated text",
    "UNTRANSLATED": "read as Japanese but not lettered",
    "T_RESIDUE": "made-up page: lettering pixels left dark after the erase (exact layer)",
    "T_LINE_CUT": "made-up page: outline pixels erased (exact layer)",
    "T_INK_ON_LINE": "made-up page: lettering on the outline (exact layer)",
    "T_INK_OUT": "made-up page: lettering outside its bubble's interior (exact layer)",
    "T_FALSE": "made-up page: a region on no made-up text (bait: map, clothes, ...)",
}
PAGE_CODES = {"MISSED": "a gold or made-up text with no region", "OCR_DROPPED": "a text found but its reading dropped",
              "T_LEFT": "made-up page: a text's lettering left dark on the page after every erase (exact layer)"}
# each code's level on the owner's scale (as `taslation.analysis.LEVELS` gives a defect its level): the summary's
# table goes by it, the worst first
LEVEL_WORDS = {"S1": "S1 reading fails", "S2": "S2 content lost or damaged", "S3": "S3 readable but hard",
               "S4": "S4 cosmetic"}
CODE_LEVELS = {
    # a text left untranslated, or its original shown where a translation exists
    "UNTRANSLATED": "S1", "MISSED": "S1", "OCR_DROPPED": "S1",
    # a translation cut or covered, the drawing destroyed, a false region lettered over the art
    "NOFIT": "S2", "OVER_OTHER": "S2", "INK_OTHER": "S2", "ART_CUT": "S2", "FALSE_LIKELY": "S2", "NO_GOLD": "S2",
    "T_FALSE": "S2",
    # specks or ghosts, an outline or a line cut, lettering over an outline, under the readable size or small in a
    # large room, hyphenated
    "RESIDUE": "S3", "GHOST": "S3", "LAMA_BUBBLE": "S3", "LEFT_BY_LINE": "S3", "LEFT_SHARED": "S3", "LINE_CUT": "S3",
    "INK_ON_LINE": "S3", "INK_OUT": "S3", "SMALL": "S3", "ROOM_LOOSE": "S3", "HYPHEN": "S3", "SQUEEZED": "S3",
    "BOX_SMALL": "S3",
    "T_RESIDUE": "S3", "T_LINE_CUT": "S3", "T_INK_ON_LINE": "S3", "T_INK_OUT": "S3", "T_LEFT": "S3",
    # a size or a place a little off
    "TIGHT": "S4", "BOX_BIG": "S4",
}

Box = tuple[int, int, int, int]


# ====================================================================== made-up pages
LINES = ["そんなはずない", "待ってくれよ", "やめろって言ってる", "今日はいい天気だね", "どこへ行くの",
         "まだ終わってない", "大丈夫だよ", "ありがとう", "本当に行くのか", "ここで待ってて", "気をつけて",
         "明日また来るよ", "急いで", "やっぱりそうか", "信じられない", "なんでここに", "絶対に許さない",
         "もう一度だけ", "知らなかった", "帰ろうか", "何をしてるの", "うそでしょ", "早く逃げて", "見つけた"]
PW, PH = 1240, 1754  # a made-up page at print size


def _jp_font_path(models_dir: Path) -> str:
    own = models_dir / "fonts" / "NotoSansJP[wght].ttf"
    if own.is_file():
        return str(own)
    import make_sample_page

    for cand in make_sample_page.JP_FONT_CANDIDATES:
        if Path(cand).is_file():
            return cand
    raise SystemExit("no Japanese font for the made-up pages")


class Drawn:
    """A made-up page drawn with its layers kept apart: the lettering, the outlines (coverage 0..255) and the bubbles'
    interiors (a label per bubble), and the truth: its texts and its bait areas."""

    def __init__(self, seed: int, font_path: str):
        from PIL import Image, ImageDraw
        import numpy as np

        self.np, self.Image, self.ImageDraw = np, Image, ImageDraw
        self.rng = random.Random(seed)
        self.font_path = font_path
        self.img = Image.new("L", (PW, PH), 255)
        self.text = Image.new("L", (PW, PH), 0)
        self.outline = Image.new("L", (PW, PH), 0)
        self.inter = np.zeros((PH, PW), np.int32)
        self._draws()
        self.truth: list[dict[str, Any]] = []
        self.bait: list[dict[str, Any]] = []
        self.next_id = 1

    def _draws(self) -> None:
        self.d = self.ImageDraw.Draw(self.img)
        self.dt = self.ImageDraw.Draw(self.text)
        self.do = self.ImageDraw.Draw(self.outline)

    def font(self, size: int, weight: int = 700) -> Any:
        from PIL import ImageFont

        f = ImageFont.truetype(self.font_path, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:  # noqa: BLE001 - a font without a weight axis: as it is
            pass
        return f

    # -------------------------------------------------- the drawing
    def panel(self, box: Sequence[float], art: bool = True) -> None:
        x0, y0, x1, y1 = box
        if art:
            self.scribble((x0 + 10, y0 + 10, x1 - 10, y1 - 10))
        self.d.rectangle(tuple(box), outline=0, width=6)

    def scribble(self, box: Sequence[float], n: tuple[int, int] = (18, 30)) -> None:
        x0, y0, x1, y1 = box
        r = self.rng
        for _ in range(r.randint(*n)):
            ax, ay = r.uniform(x0, x1), r.uniform(y0, y1)
            bx, by = min(max(ax + r.uniform(-160, 160), x0), x1), min(max(ay + r.uniform(-160, 160), y0), y1)
            self.d.line((ax, ay, bx, by), fill=r.randint(0, 110), width=r.randint(2, 5))
        for _ in range(r.randint(2, 4)):
            cx, cy = r.uniform(x0 + 40, x1 - 40), r.uniform(y0 + 40, y1 - 40)
            rad = r.uniform(25, 70)
            self.d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=r.randint(90, 200), outline=0, width=3)

    def tone(self, box: Sequence[float], pitch: float = 7, dot: float = 2.2, shade: int = 30) -> None:
        x0, y0, x1, y1 = box
        self.d.rectangle(tuple(box), fill=255)
        y, row = y0 + 2, 0
        while y < y1 - 2:
            x = x0 + 2 + (pitch / 2 if row % 2 else 0)
            while x < x1 - 2:
                self.d.ellipse((x - dot, y - dot, x + dot, y + dot), fill=shade)
                x += pitch
            y += pitch * 0.87
            row += 1

    def within(self, where: Any, paint: Any) -> None:
        """What *paint*() draws on the page, kept inside *where* (a bool mask of the page) alone, darkening only."""
        np = self.np
        held = self.img
        self.img = self.Image.new("L", (PW, PH), 255)
        self._draws()
        paint()
        page = np.asarray(held).copy()
        page[where] = np.minimum(page[where], np.asarray(self.img)[where])
        self.img = self.Image.fromarray(page)
        self._draws()

    def veil(self, where: Any, keep: float = 0.35) -> None:
        """The page inside *where* seen through a semi-transparent bubble's paper: each pixel's darkness kept by
        *keep* (the drawing there faint, light grey)."""
        np = self.np
        page = np.asarray(self.img).astype(np.float32)
        page[where] = 255.0 - (255.0 - page[where]) * keep
        self.img = self.Image.fromarray(np.clip(np.round(page), 0, 255).astype(np.uint8))
        self._draws()

    def box_mask(self, box: Sequence[float]) -> Any:
        x0, y0, x1, y1 = (int(v) for v in box)
        out = self.np.zeros((PH, PW), bool)
        out[y0:y1, x0:x1] = True
        return out

    def hatching(self, box: Sequence[float], step: int = 9, width: int = 2, shade: int = 40) -> None:
        x0, y0, x1, y1 = box
        for k in range(-int(y1 - y0), int(x1 - x0), step):
            self.d.line((x0 + k, y1, x0 + k + (y1 - y0), y0), fill=shade, width=width)

    def hair(self, box: Sequence[float], n: int, width: int = 3, down: bool = False) -> None:
        """*n* strands of hair (the drawing seen through a bubble drawn over it): gentle curves across *box*, from
        its left side to its right (*down*: from its top to its foot), on the page alone."""
        x0, y0, x1, y1 = box
        r = self.rng
        for k in range(n):
            t = (k + 0.5) / n
            if down:
                a = (x0 + t * (x1 - x0) + r.uniform(-20, 20), y0)
                b = (x0 + t * (x1 - x0) + r.uniform(-60, 60), y1)
                bend = (r.uniform(-50, 50), 0.0)
            else:
                a = (x0, y0 + t * (y1 - y0) + r.uniform(-20, 20))
                b = (x1, y0 + t * (y1 - y0) + r.uniform(-60, 60))
                bend = (0.0, r.uniform(-50, 50))
            mid = ((a[0] + b[0]) / 2 + bend[0], (a[1] + b[1]) / 2 + bend[1])
            pts = [((1 - s) ** 2 * a[0] + 2 * (1 - s) * s * mid[0] + s * s * b[0],
                    (1 - s) ** 2 * a[1] + 2 * (1 - s) * s * mid[1] + s * s * b[1]) for s in (q / 24 for q in range(25))]
            self.d.line(pts, fill=r.randint(20, 70), width=width)

    # -------------------------------------------------- bubbles
    def _shape(self, draw: Any, kind: str, box: Sequence[float], radius: float, fill: int) -> None:
        if kind == "ellipse":
            draw.ellipse(tuple(box), fill=fill)
        else:
            draw.rounded_rectangle(tuple(box), radius=max(0.0, radius), fill=fill)

    def _label(self, kind: str, box: Sequence[float], radius: float) -> Any:
        m = self.Image.new("L", (PW, PH), 0)
        self._shape(self.ImageDraw.Draw(m), kind, box, radius, 255)
        return self.np.asarray(m) > 127

    def bubble(self, cx: float, cy: float, rx: float, ry: float, *, width: int = 5, shape: str = "ellipse",
               fill: int = 255, line: int = 0, tail: tuple[float, float] | None = None) -> int:
        bid = self.next_id
        self.next_id += 1
        outer = (cx - rx, cy - ry, cx + rx, cy + ry)
        inner = (cx - rx + width, cy - ry + width, cx + rx - width, cy + ry - width)
        kind = "ellipse" if shape == "ellipse" else "round"
        rad = min(rx, ry) * 0.5 if shape == "round" else 0.0
        self._shape(self.d, kind, outer, rad, line)
        self._shape(self.d, kind, inner, rad - width, fill)
        self._shape(self.do, kind, outer, rad, 255)
        self._shape(self.do, kind, inner, rad - width, 0)
        self._shape(self.dt, kind, outer, rad, 0)
        self.inter[self._label(kind, inner, rad - width)] = bid
        if tail:  # opening into the bubble: its two sides drawn, the ring under its base covered
            tx, ty = tail
            ang = math.atan2(ty - cy, tx - cx)
            base = [(cx + rx * 0.85 * math.cos(ang + da), cy + ry * 0.85 * math.sin(ang + da)) for da in (-0.17, 0.17)]
            poly = [base[0], (tx, ty), base[1]]
            self.d.polygon(poly, fill=fill)
            self.do.polygon(poly, fill=0)
            self.dt.polygon(poly, fill=0)
            for side in (poly[:2], poly[1:]):
                self.d.line(side, fill=line, width=width - 1)
                self.do.line(side, fill=255, width=width - 1)
            self._shape(self.d, kind, inner, rad - width, fill)
            self._shape(self.do, kind, inner, rad - width, 0)
        return bid

    def fused(self, a: Sequence[float], b: Sequence[float], width: int = 5) -> list[int]:
        """Two ellipses drawn as one white area (outlines first, then both fills): a neck, no line between them."""
        inners = []
        for cx, cy, rx, ry in (a, b):
            outer = (cx - rx, cy - ry, cx + rx, cy + ry)
            self.d.ellipse(outer, fill=0)
            self.do.ellipse(outer, fill=255)
            self.dt.ellipse(outer, fill=0)
            inners.append((cx - rx + width, cy - ry + width, cx + rx - width, cy + ry - width))
        ids = []
        for inner in inners:
            bid = self.next_id
            self.next_id += 1
            ids.append(bid)
            self.d.ellipse(inner, fill=255)
            self.do.ellipse(inner, fill=0)
            self.inter[self._label("ellipse", inner, 0) & (self.inter == 0)] = bid
        return ids

    def spiky(self, cx: float, cy: float, rx: float, ry: float, spikes: int = 18, width: int = 5) -> int:
        bid = self.next_id
        self.next_id += 1
        pts = []
        for k in range(spikes * 2):
            a = math.pi * k / spikes
            f = 1.0 if k % 2 == 0 else 0.78
            pts.append((cx + rx * f * math.cos(a), cy + ry * f * math.sin(a)))
        self.d.polygon(pts, fill=255, outline=0, width=width)
        self.do.polygon(pts, fill=0, outline=255, width=width)
        self.dt.polygon(pts, fill=0)
        m = self.Image.new("L", (PW, PH), 0)
        self.ImageDraw.Draw(m).polygon(pts, fill=255)
        self.inter[(self.np.asarray(m) > 127) & ~(self.np.asarray(self.outline) > 127)] = bid
        return bid

    # -------------------------------------------------- lettering
    def column_text(self, text: str, cx: float, top: float, size: int, weight: int = 700, colour: int = 0,
                    max_rows: int = 99, bubble: int = 0, kind: str = "bubble", case: str = "", stroke: int = 0,
                    stroke_fill: int = 255, rows_gap: float = 1.05, col_gap: float = 1.18) -> None:
        f = self.font(size, weight)
        cols = [text[i:i + max_rows] for i in range(0, len(text), max_rows)]
        col_w = size * col_gap
        x = cx + col_w * (len(cols) - 1) / 2
        boxes = []
        for col in cols:
            y = top
            for ch in col:
                bb = self.d.textbbox((0, 0), ch, font=f)
                pos = (x - (bb[2] - bb[0]) / 2 - bb[0], y - bb[1])
                self.d.text(pos, ch, font=f, fill=colour, stroke_width=stroke, stroke_fill=stroke_fill)
                self.dt.text(pos, ch, font=f, fill=255)
                boxes.append(self.d.textbbox(pos, ch, font=f))
                y += size * rows_gap
            x -= col_w
        box = [int(min(b[0] for b in boxes)), int(min(b[1] for b in boxes)), int(math.ceil(max(b[2] for b in boxes))),
               int(math.ceil(max(b[3] for b in boxes)))]
        self.truth.append({"id": len(self.truth), "kind": kind, "bubble": bubble, "text_box": box, "size": size,
                           "weight": weight, "chars": len(text), "case": case, "colour": colour,
                           "columns": len(cols)})

    def centred(self, text: str, cx: float, cy: float, size: int, rows: int, **kw: Any) -> None:
        n = min(len(text), rows)
        self.column_text(text, cx, cy - n * size * kw.get("rows_gap", 1.05) / 2, size, max_rows=rows, **kw)

    def sfx(self, text: str, cx: float, cy: float, size: int, angle: float) -> None:
        np = self.np
        f = self.font(size, 900)
        layer = self.Image.new("L", (size * len(text) + 40, size + 40), 0)
        self.ImageDraw.Draw(layer).text((20, 10), text, font=f, fill=255, stroke_width=max(3, size // 12),
                                        stroke_fill=128)
        arr = np.asarray(layer.rotate(angle, expand=True, resample=self.Image.BICUBIC))
        x0, y0 = int(cx - arr.shape[1] / 2), int(cy - arr.shape[0] / 2)
        page, tl = np.asarray(self.img).copy(), np.asarray(self.text).copy()
        h, w = arr.shape
        fill, ring = arr > 180, (arr > 60) & (arr <= 180)
        page[y0:y0 + h, x0:x0 + w][ring] = 255
        page[y0:y0 + h, x0:x0 + w][fill] = 0
        tl[y0:y0 + h, x0:x0 + w][fill] = 255
        self.img, self.text = self.Image.fromarray(page), self.Image.fromarray(tl)
        self._draws()
        ys, xs = np.nonzero(fill)
        self.truth.append({"id": len(self.truth), "kind": "sfx", "bubble": 0,
                           "text_box": [int(x0 + xs.min()), int(y0 + ys.min()), int(x0 + xs.max() + 1),
                                        int(y0 + ys.max() + 1)], "size": size, "weight": 900, "chars": len(text),
                           "case": "sfx", "colour": 0, "columns": 0})

    # -------------------------------------------------- bait
    def map_panel(self, box: Sequence[float]) -> None:
        x0, y0, x1, y1 = box
        r = self.rng
        self.d.rectangle(tuple(box), fill=245)
        for _ in range(6):
            self.d.line([(r.uniform(x0, x1), r.uniform(y0, y1)) for _ in range(4)], fill=60, width=3)
        for _ in range(55):
            cx, cy = r.uniform(x0 + 15, x1 - 15), r.uniform(y0 + 15, y1 - 15)
            s = r.uniform(7, 14)
            k = r.randrange(6)
            if k == 0:
                self.d.ellipse((cx - s, cy - s, cx + s, cy + s), outline=20, width=2)
            elif k == 1:
                self.d.polygon([(cx, cy - s), (cx - s, cy + s), (cx + s, cy + s)], fill=30)
            elif k == 2:
                self.d.line((cx - s, cy - s, cx + s, cy + s), fill=20, width=3)
                self.d.line((cx - s, cy + s, cx + s, cy - s), fill=20, width=3)
            elif k == 3:
                self.d.rectangle((cx - s * 0.7, cy - s * 0.7, cx + s * 0.7, cy + s * 0.7), outline=20, width=2)
            elif k == 4:
                self.d.ellipse((cx - s * 0.4, cy - s * 0.4, cx + s * 0.4, cy + s * 0.4), fill=10)
            else:  # map signs that are characters: north, a temple, a post office, a hot spring
                self.d.text((cx, cy), r.choice("NSEW卍〒♨"), font=self.font(int(s * 1.6), 500), fill=20, anchor="mm")
        self.d.rectangle(tuple(box), outline=0, width=6)
        self.bait.append({"bait": "map", "box": [int(v) for v in box]})

    def clothes(self, box: Sequence[float], pattern: str) -> None:
        np = self.np
        x0, y0, x1, y1 = box
        cx = (x0 + x1) / 2
        r = self.rng
        torso = [(cx - 0.35 * (x1 - x0), y0 + 40), (cx + 0.35 * (x1 - x0), y0 + 40), (x1 - 20, y1 - 10), (x0 + 20, y1 - 10)]
        self.d.polygon(torso, fill=255, outline=0, width=4)
        m = self.Image.new("L", (PW, PH), 0)
        self.ImageDraw.Draw(m).polygon(torso, fill=255)
        mask = np.asarray(m) > 127
        layer = self.Image.new("L", (PW, PH), 255)
        dl = self.ImageDraw.Draw(layer)
        if pattern == "checks":
            for y in range(int(y0), int(y1), 18):
                for x in range(int(x0), int(x1), 18):
                    if ((x - x0) // 18 + (y - y0) // 18) % 2 == 0:
                        dl.rectangle((x + 3, y + 3, x + 12, y + 12), fill=30)
        elif pattern == "dots":
            for y in range(int(y0), int(y1), 22):
                for x in range(int(x0) + (11 if (y // 22) % 2 else 0), int(x1), 22):
                    dl.ellipse((x - 4, y - 4, x + 4, y + 4), fill=20)
        elif pattern == "stripes":
            for x in range(int(x0), int(x1), 14):
                dl.line((x, y0, x, y1), fill=30, width=4)
        else:  # flowers
            for _ in range(40):
                fx, fy = r.uniform(x0, x1), r.uniform(y0, y1)
                for k in range(5):
                    a = 2 * math.pi * k / 5
                    px, py = fx + 7 * math.cos(a), fy + 7 * math.sin(a)
                    dl.ellipse((px - 4, py - 4, px + 4, py + 4), outline=20, width=2)
        page = np.asarray(self.img).copy()
        lay = np.asarray(layer)
        page[mask] = np.minimum(page[mask], lay[mask])
        self.img = self.Image.fromarray(page)
        self._draws()
        self.d.line((cx, y0 + 40, cx, y1 - 10), fill=0, width=3)  # the front, and a column of buttons beside it
        for k in range(6):
            by = y0 + 80 + k * (y1 - y0 - 120) / 6
            self.d.ellipse((cx + 8, by - 9, cx + 26, by + 9), fill=255, outline=0, width=3)
            self.d.ellipse((cx + 13, by - 3, cx + 16, by), fill=0)
            self.d.ellipse((cx + 18, by + 0, cx + 21, by + 3), fill=0)
        self.bait.append({"bait": "clothes-" + pattern, "box": [int(v) for v in box]})

    def frame3(self, art: bool = True) -> list[tuple[int, int, int, int]]:
        m, g, mid, sx = 60, 24, PH // 2, PW // 2
        boxes = [(sx + g // 2, m, PW - m, mid - g // 2), (m, m, sx - g // 2, mid - g // 2), (m, mid + g // 2, PW - m, PH - m)]
        for b in boxes:
            self.panel(b, art=art)
        return boxes


def layout(n: int, font_path: str) -> Drawn:
    """Made-up layout *n* (1 to 20), each built round one risk."""
    p = Drawn(1000 + n, font_path)
    lines = list(LINES)
    p.rng.shuffle(lines)
    c = p.centred
    if n == 1:  # tall narrow bubbles, one column of heavy characters
        tr, tl, bt = p.frame3()
        b = p.bubble(tr[0] + 120, tr[1] + 300, 48, 235)
        c("そんなはずない！", tr[0] + 120, tr[1] + 300, 30, 12, weight=900, bubble=b, case="narrow-bold")
        b = p.bubble(tr[0] + 330, tr[1] + 320, 52, 250, shape="round")
        c("やめろって言ってる", tr[0] + 330, tr[1] + 320, 32, 12, weight=900, bubble=b, case="narrow-bold")
        b = p.bubble(tl[0] + 200, tl[1] + 300, 150, 190, tail=(tl[0] + 300, tl[1] + 560))
        c(lines[0] + lines[1], tl[0] + 200, tl[1] + 300, 30, 5, weight=500, bubble=b, case="normal")
        b = p.bubble(bt[0] + 500, bt[1] + 360, 44, 250)
        c("待ってくれよ", bt[0] + 500, bt[1] + 360, 28, 12, weight=800, bubble=b, case="narrow-bold")
        b = p.bubble(bt[0] + 800, bt[1] + 330, 140, 200)
        c(lines[2] + lines[3], bt[0] + 800, bt[1] + 330, 28, 6, weight=500, bubble=b, case="normal")
    elif n == 2:  # narrow bubbles at other sizes and weights
        tr, tl, bt = p.frame3()
        b = p.bubble(tr[0] + 110, tr[1] + 280, 40, 200)
        c("信じられない", tr[0] + 110, tr[1] + 280, 26, 12, weight=900, bubble=b, case="narrow-bold")
        b = p.bubble(tr[0] + 300, tr[1] + 300, 62, 260)
        c("絶対に許さないうそでしょ", tr[0] + 300, tr[1] + 300, 28, 7, weight=700, bubble=b, case="narrow-2col")
        b = p.bubble(tl[0] + 150, tl[1] + 300, 38, 190)
        c("早く逃げて", tl[0] + 150, tl[1] + 300, 24, 12, weight=900, bubble=b, case="narrow-bold")
        b = p.bubble(tl[0] + 380, tl[1] + 300, 46, 220, shape="round")
        c("知らなかった", tl[0] + 380, tl[1] + 300, 27, 12, weight=400, bubble=b, case="narrow-light")
        b = p.bubble(bt[0] + 300, bt[1] + 330, 150, 200, tail=(bt[0] + 150, bt[1] + 600))
        c(lines[4] + lines[5], bt[0] + 300, bt[1] + 330, 30, 5, weight=500, bubble=b, case="normal")
        b = p.bubble(bt[0] + 800, bt[1] + 330, 36, 230)
        c("見つけた！", bt[0] + 800, bt[1] + 330, 25, 12, weight=900, bubble=b, case="narrow-bold")
    elif n == 3:  # a small bubble drawn over a larger one's edge: its outline cuts into the larger one
        tr, tl, bt = p.frame3()
        b = p.bubble(tr[0] + 250, tr[1] + 330, 170, 210)
        c(lines[0] + lines[1], tr[0] + 240, tr[1] + 360, 30, 6, weight=500, bubble=b, case="joined-big")
        b = p.bubble(tr[0] + 420, tr[1] + 150, 70, 110)
        c("えっ？", tr[0] + 420, tr[1] + 150, 30, 6, weight=600, bubble=b, case="joined-small")
        b = p.bubble(bt[0] + 400, bt[1] + 360, 190, 220)
        c(lines[2] + lines[3], bt[0] + 420, bt[1] + 380, 30, 6, weight=500, bubble=b, case="joined-big")
        b = p.bubble(bt[0] + 200, bt[1] + 170, 80, 120)
        c("なんで", bt[0] + 200, bt[1] + 170, 30, 6, weight=600, bubble=b, case="joined-small")
        b = p.bubble(bt[0] + 640, bt[1] + 560, 75, 105)
        c("本当？", bt[0] + 640, bt[1] + 560, 28, 6, weight=600, bubble=b, case="joined-small")
        b = p.bubble(tl[0] + 250, tl[1] + 330, 150, 200)
        c(lines[4], tl[0] + 250, tl[1] + 330, 30, 6, weight=500, bubble=b, case="normal")
    elif n == 4:  # fused bubbles (one white area with a neck) and two that touch
        tr, tl, bt = p.frame3()
        a, b = p.fused((tr[0] + 200, tr[1] + 250, 140, 170), (tr[0] + 380, tr[1] + 470, 90, 120))
        c(lines[0] + lines[1], tr[0] + 200, tr[1] + 250, 28, 5, weight=500, bubble=a, case="fused-big")
        c("急いで", tr[0] + 380, tr[1] + 470, 28, 5, weight=500, bubble=b, case="fused-small")
        a, b = p.fused((bt[0] + 300, bt[1] + 300, 160, 190), (bt[0] + 520, bt[1] + 220, 95, 130))
        c(lines[2] + lines[3], bt[0] + 290, bt[1] + 310, 28, 6, weight=500, bubble=a, case="fused-big")
        c("帰ろうか", bt[0] + 530, bt[1] + 220, 28, 6, weight=500, bubble=b, case="fused-small")
        b = p.bubble(tl[0] + 180, tl[1] + 280, 120, 170)
        c(lines[4], tl[0] + 180, tl[1] + 280, 28, 6, weight=500, bubble=b, case="touch")
        b = p.bubble(tl[0] + 370, tl[1] + 420, 75, 100)
        c("うん", tl[0] + 370, tl[1] + 420, 28, 6, weight=500, bubble=b, case="touch-small")
        b = p.bubble(bt[0] + 850, bt[1] + 330, 120, 180)
        c(lines[5], bt[0] + 850, bt[1] + 330, 28, 6, weight=500, bubble=b, case="normal")
    elif n == 5:  # bubbles cut by the page's edge
        m = 60
        p.panel((m, m, PW - m, PH // 2 - 12))
        p.panel((m, PH // 2 + 12, PW - m, PH - m))
        b = p.bubble(PW - 70, 260, 150, 210)
        c(lines[0] + lines[1], PW - 110, 260, 30, 5, weight=500, bubble=b, case="edge-right")
        b = p.bubble(400, 40, 170, 150)
        c(lines[2], 400, 70, 30, 4, weight=500, bubble=b, case="edge-top")
        b = p.bubble(60, PH - 300, 140, 200)
        c(lines[3] + lines[4], 90, PH - 300, 30, 5, weight=500, bubble=b, case="edge-left")
        b = p.bubble(PW // 2, PH - 30, 180, 140)
        c(lines[5], PW // 2, PH - 80, 30, 4, weight=500, bubble=b, case="edge-bottom")
        b = p.bubble(700, 600, 130, 170)
        c(lines[6], 700, 600, 30, 5, weight=500, bubble=b, case="normal")
    elif n == 6:  # text on screentone, with and without a white outline; on a gradient
        tr, tl, bt = p.frame3(art=False)
        p.tone((tr[0] + 6, tr[1] + 6, tr[2] - 6, tr[3] - 6))
        c(lines[0] + lines[1], tr[0] + 300, tr[1] + 300, 30, 6, weight=600, kind="onpage", case="tone")
        p.tone((tl[0] + 6, tl[1] + 6, tl[2] - 6, tl[3] - 6), pitch=6, dot=1.8, shade=60)
        c(lines[2] + lines[3], tl[0] + 300, tl[1] + 300, 30, 6, weight=700, kind="onpage", case="tone-stroke",
          stroke=4)
        x0, y0, x1, y1 = bt
        arr = p.np.asarray(p.img).copy()
        for x in range(x0 + 6, x1 - 6):
            arr[y0 + 6:y1 - 6, x] = int(90 + 150 * (x - x0) / (x1 - x0))
        p.img = p.Image.fromarray(arr)
        p._draws()
        c(lines[4] + lines[5], x0 + 300, y0 + 300, 30, 6, weight=700, kind="onpage", case="gradient-stroke", stroke=3)
        c(lines[6], x0 + 800, y0 + 300, 30, 6, weight=700, kind="onpage", case="gradient")
    elif n == 7:  # white text on black
        tr, tl, bt = p.frame3()
        p.d.rectangle((tr[0] + 150, tr[1] + 60, tr[0] + 330, tr[1] + 420), fill=0)
        c(lines[0] + lines[1], tr[0] + 240, tr[1] + 240, 28, 6, weight=600, colour=255, kind="dark", case="black-box")
        b = p.bubble(tl[0] + 260, tl[1] + 300, 140, 190, fill=0, line=0)
        c(lines[2] + lines[3], tl[0] + 260, tl[1] + 300, 28, 6, weight=600, colour=255, bubble=b, kind="dark",
          case="black-bubble")
        x0, y0, x1, y1 = bt
        p.d.rectangle((x0 + 6, y0 + 6, x1 - 6, y1 - 6), fill=25)
        p.hatching((x0 + 6, y0 + 6, x1 - 6, y1 - 6), step=11, width=2)
        c(lines[4] + lines[5], x0 + 350, y0 + 330, 30, 6, weight=700, colour=255, kind="dark", case="white-on-hatch")
        b = p.bubble(x0 + 850, y0 + 330, 130, 180)
        c(lines[6], x0 + 850, y0 + 330, 30, 6, weight=500, bubble=b, case="normal")
    elif n == 8:  # tails crossing text
        tr, tl, bt = p.frame3(art=False)
        p.scribble((tr[0] + 10, tr[1] + 300, tr[2] - 10, tr[3] - 10), n=(8, 12))
        c(lines[0] + lines[1], tr[0] + 250, tr[1] + 200, 28, 6, weight=600, kind="onpage", case="crossed-by-tail")
        b = p.bubble(tr[0] + 430, tr[1] + 200, 90, 130, tail=(tr[0] + 120, tr[1] + 330))
        c("ほら", tr[0] + 430, tr[1] + 200, 28, 6, weight=600, bubble=b, case="tail-crossing")
        b = p.bubble(tl[0] + 200, tl[1] + 250, 130, 170, tail=(tl[0] + 420, tl[1] + 440))
        c(lines[2] + lines[3], tl[0] + 200, tl[1] + 250, 28, 6, weight=500, bubble=b, case="tail-to-neighbour")
        b = p.bubble(tl[0] + 450, tl[1] + 480, 80, 100)
        c("うん", tl[0] + 450, tl[1] + 480, 28, 6, weight=500, bubble=b, case="tail-touched")
        b = p.bubble(bt[0] + 350, bt[1] + 300, 150, 200, tail=(bt[0] + 330, bt[1] + 90))
        c(lines[4] + lines[5], bt[0] + 350, bt[1] + 320, 30, 6, weight=500, bubble=b, case="tail-near-text")
        b = p.bubble(bt[0] + 800, bt[1] + 330, 130, 180)
        c(lines[6], bt[0] + 800, bt[1] + 330, 30, 6, weight=500, bubble=b, case="normal")
    elif n == 9:  # very small characters
        tr, tl, bt = p.frame3()
        b = p.bubble(tr[0] + 250, tr[1] + 250, 110, 120)
        c(lines[0] + lines[1], tr[0] + 250, tr[1] + 250, 17, 9, weight=500, bubble=b, case="small-17")
        b = p.bubble(tl[0] + 250, tl[1] + 250, 80, 90)
        c(lines[2], tl[0] + 250, tl[1] + 250, 15, 9, weight=500, bubble=b, case="small-15")
        p.d.rectangle((bt[0] + 80, bt[1] + 60, bt[0] + 300, bt[1] + 400), fill=255)
        c(lines[3] + lines[4], bt[0] + 190, bt[1] + 230, 16, 10, weight=500, kind="onpage", case="small-onpage")
        b = p.bubble(bt[0] + 600, bt[1] + 300, 130, 170)
        c(lines[5] + lines[6], bt[0] + 600, bt[1] + 300, 21, 8, weight=500, bubble=b, case="small-21")
        b = p.bubble(bt[0] + 900, bt[1] + 300, 120, 170)
        c(lines[7], bt[0] + 900, bt[1] + 300, 30, 6, weight=500, bubble=b, case="normal")
    elif n == 10:  # very large characters
        tr, tl, bt = p.frame3()
        b = p.spiky(tr[0] + 270, tr[1] + 380, 230, 320)
        c("ふざけるな", tr[0] + 270, tr[1] + 380, 95, 3, weight=900, bubble=b, case="large-95")
        b = p.bubble(tl[0] + 270, tl[1] + 350, 200, 280)
        c("逃げろ", tl[0] + 270, tl[1] + 350, 70, 3, weight=800, bubble=b, case="large-70")
        b = p.spiky(bt[0] + 400, bt[1] + 330, 300, 280, spikes=24)
        c("やった", bt[0] + 400, bt[1] + 330, 110, 3, weight=900, bubble=b, case="large-110")
        b = p.bubble(bt[0] + 900, bt[1] + 330, 120, 180)
        c(lines[0], bt[0] + 900, bt[1] + 330, 30, 6, weight=500, bubble=b, case="normal")
    elif n == 11:  # maps with symbols
        tr, tl, bt = p.frame3()
        p.map_panel((bt[0] + 6, bt[1] + 6, bt[2] - 6, bt[3] - 6))
        p.map_panel((tl[0] + 6, tl[1] + 6, tl[2] - 6, tl[3] - 6))
        b = p.bubble(tr[0] + 270, tr[1] + 300, 140, 190)
        c(lines[0] + lines[1], tr[0] + 270, tr[1] + 300, 30, 6, weight=500, bubble=b, case="normal")
    elif n == 12:  # clothing patterns
        tr, tl, bt = p.frame3(art=False)
        p.clothes((tr[0] + 40, tr[1] + 40, tr[0] + 330, tr[3] - 20), "checks")
        p.clothes((tl[0] + 200, tl[1] + 40, tl[2] - 20, tl[3] - 20), "dots")
        p.clothes((bt[0] + 40, bt[1] + 60, bt[0] + 420, bt[3] - 20), "stripes")
        p.clothes((bt[0] + 600, bt[1] + 60, bt[0] + 980, bt[3] - 20), "flowers")
        b = p.bubble(tr[0] + 450, tr[1] + 250, 80, 150)
        c(lines[0], tr[0] + 450, tr[1] + 250, 28, 6, weight=500, bubble=b, case="normal")
        b = p.bubble(tl[0] + 90, tl[1] + 250, 60, 150)
        c(lines[1], tl[0] + 90, tl[1] + 250, 26, 8, weight=500, bubble=b, case="normal")
    elif n == 13:  # sound effects lettered on the art
        tr, tl, bt = p.frame3()
        p.sfx("ドドド", tr[0] + 280, tr[1] + 200, 80, 18)
        p.sfx("ガシャン", tl[0] + 280, tl[1] + 400, 70, -12)
        p.sfx("ゴゴゴ", bt[0] + 700, bt[1] + 200, 90, 8)
        b = p.bubble(tr[0] + 300, tr[1] + 520, 110, 140)
        c(lines[0], tr[0] + 300, tr[1] + 520, 28, 6, weight=500, bubble=b, case="normal")
        b = p.bubble(bt[0] + 250, bt[1] + 400, 130, 180)
        c(lines[1] + lines[2], bt[0] + 250, bt[1] + 400, 28, 6, weight=500, bubble=b, case="normal")
    elif n == 14:  # a narrow bubble joined to a larger one; small text on tone
        tr, tl, bt = p.frame3()
        b = p.bubble(tr[0] + 260, tr[1] + 330, 160, 200)
        c(lines[0] + lines[1], tr[0] + 250, tr[1] + 350, 28, 6, weight=500, bubble=b, case="joined-big")
        b = p.bubble(tr[0] + 440, tr[1] + 250, 42, 200)
        c("まさか", tr[0] + 440, tr[1] + 250, 26, 8, weight=900, bubble=b, case="joined-narrow")
        p.tone((tl[0] + 6, tl[1] + 6, tl[2] - 6, tl[3] - 6))
        c(lines[2], tl[0] + 300, tl[1] + 300, 18, 10, weight=600, kind="onpage", case="small-tone")
        b = p.bubble(bt[0] + 600, bt[1] + 320, 170, 200)
        c(lines[3] + lines[4], bt[0] + 590, bt[1] + 330, 28, 6, weight=500, bubble=b, case="joined-big")
        b = p.bubble(bt[0] + 380, bt[1] + 250, 40, 180)
        c("おい", bt[0] + 380, bt[1] + 250, 26, 8, weight=900, bubble=b, case="joined-narrow")
    elif n == 15:  # a dense page of ordinary bubbles, some close together
        tr, tl, bt = p.frame3()
        spots = [(tr[0] + 150, tr[1] + 200, 100, 140), (tr[0] + 380, tr[1] + 260, 110, 160),
                 (tl[0] + 140, tl[1] + 220, 100, 150), (tl[0] + 380, tl[1] + 420, 110, 150),
                 (bt[0] + 160, bt[1] + 220, 110, 160), (bt[0] + 420, bt[1] + 240, 120, 170),
                 (bt[0] + 700, bt[1] + 420, 120, 170), (bt[0] + 960, bt[1] + 260, 110, 160)]
        for k, (cx, cy, rx, ry) in enumerate(spots):
            b = p.bubble(cx, cy, rx, ry, tail=(cx + 40, cy + ry + 70) if k % 2 else None)
            c(lines[k] + (lines[k + 8] if k % 3 == 0 else ""), cx, cy, 27, 6, weight=500, bubble=b, case="dense")
    elif n == 17:  # lettering that touches its outline or runs over it, glyphs that touch each other, long bars, dots
        tr, tl, bt = p.frame3()
        b = p.bubble(tr[0] + 110, tr[1] + 300, 21, 230, shape="round")
        c("ふざけんじゃねえ", tr[0] + 110, tr[1] + 300, 36, 12, weight=900, bubble=b, case="touch-outline")
        b = p.bubble(tr[0] + 320, tr[1] + 300, 62, 235)
        c("うわあああ︱︱︱", tr[0] + 320, tr[1] + 300, 40, 12, weight=900, bubble=b, case="tight-bar",
          rows_gap=0.86)
        b = p.bubble(tl[0] + 200, tl[1] + 300, 140, 150)
        c(lines[0] + lines[1], tl[0] + 200, tl[1] + 300, 30, 10, weight=600, bubble=b, case="over-outline")
        b = p.bubble(tl[0] + 430, tl[1] + 330, 70, 170)
        c("まさか︙︙", tl[0] + 430, tl[1] + 330, 30, 12, weight=600, bubble=b, case="dots")
        b = p.bubble(bt[0] + 120, bt[1] + 330, 15, 190, shape="round")
        c("待ってくれよ", bt[0] + 120, bt[1] + 330, 26, 12, weight=800, bubble=b, case="touch-outline")
        b = p.bubble(bt[0] + 330, bt[1] + 330, 52, 150)
        c("なにっ⁉", bt[0] + 330, bt[1] + 330, 44, 12, weight=900, bubble=b, case="heavy-marks")
        b = p.bubble(bt[0] + 700, bt[1] + 330, 150, 200)
        c(lines[2] + lines[3], bt[0] + 700, bt[1] + 330, 28, 6, weight=500, bubble=b, case="normal")
    elif n == 18:  # bubbles joined in pairs, each drawn over the one before it (its outline the shared one)
        tr, tl, bt = p.frame3()
        # a tall narrow bubble of two columns, the left one by its outline and ending in an ellipsis; a narrower one
        # over its upper right corner
        a = p.bubble(tr[0] + 150, tr[1] + 400, 46, 160)
        b = p.bubble(tr[0] + 200, tr[1] + 250, 30, 118)
        c("まさかそんなことって︙︙", tr[0] + 150, tr[1] + 440, 25, 6, weight=700, bubble=a, case="pair-corner-big")
        c("えっ︙", tr[0] + 206, tr[1] + 236, 24, 6, weight=700, bubble=b, case="pair-corner-small")
        # a tall narrow bubble by the page's right edge, one column
        e = p.bubble(tr[2] - 58, tr[1] + 360, 31, 140)
        c("ちょっと待ってよ", tr[2] - 58, tr[1] + 360, 24, 12, weight=700, bubble=e, case="narrow-edge")
        # a bubble of three columns, a tall narrow one over its left side
        a = p.bubble(tl[0] + 380, tl[1] + 330, 88, 135)
        b = p.bubble(tl[0] + 262, tl[1] + 370, 40, 165)
        c("やっぱりそうかここで待っててね", tl[0] + 392, tl[1] + 330, 25, 5, weight=500, bubble=a,
          case="pair-side-big")
        c("気をつけて︙", tl[0] + 258, tl[1] + 370, 25, 12, weight=700, bubble=b, case="pair-side-narrow")
        # a bubble of three columns, a smaller one over its foot
        a = p.bubble(bt[0] + 260, bt[1] + 200, 95, 120)
        b = p.bubble(bt[0] + 300, bt[1] + 372, 70, 95)
        c("今日はいい天気だね明日また来るよ", bt[0] + 260, bt[1] + 190, 25, 6, weight=500, bubble=a,
          case="pair-below-top")
        c("急いで", bt[0] + 305, bt[1] + 385, 25, 6, weight=500, bubble=b, case="pair-below-foot")
        # two tall narrow bubbles side by side, the right one over the left one's right side
        a = p.bubble(bt[0] + 640, bt[1] + 330, 40, 170)
        b = p.bubble(bt[0] + 708, bt[1] + 310, 36, 160)
        c("信じられない︙", bt[0] + 634, bt[1] + 340, 26, 12, weight=800, bubble=a, case="pair-narrow-left")
        c("うそでしょ", bt[0] + 712, bt[1] + 310, 26, 12, weight=800, bubble=b, case="pair-narrow-right")
        b = p.bubble(bt[0] + 950, bt[1] + 330, 130, 180)
        c(lines[0] + lines[1], bt[0] + 950, bt[1] + 330, 28, 6, weight=500, bubble=b, case="normal")
        p.inter[p.np.asarray(p.outline) > 127] = 0  # (an outline drawn over a bubble is no part of its interior)
    elif n == 19:  # joined pairs lettered from outline to outline: the columns by the shared outline touch it
        tr, tl, bt = p.frame3()
        # two tall narrow bubbles side by side, the right one over the left one's right side, three columns each
        a = p.bubble(tr[0] + 140, tr[1] + 330, 42, 170)
        b = p.bubble(tr[0] + 215, tr[1] + 310, 42, 160)
        c("信じられないそんなことって︙", tr[0] + 140, tr[1] + 330, 22, 5, weight=800, bubble=a, case="tight-left",
          col_gap=1.12)
        c("うそでしょ本当にそうなの", tr[0] + 215, tr[1] + 310, 22, 4, weight=800, bubble=b, case="tight-right",
          col_gap=1.12)
        # a narrow bubble ending in an ellipsis column, a smaller one over its upper right corner
        a = p.bubble(tr[0] + 420, tr[1] + 360, 46, 165)
        b = p.bubble(tr[0] + 470, tr[1] + 220, 26, 100)
        c("まさかそんなことって︙︙", tr[0] + 420, tr[1] + 380, 24, 6, weight=700, bubble=a, case="tight-corner-big",
          col_gap=1.12)
        c("えっ︙", tr[0] + 472, tr[1] + 210, 22, 6, weight=700, bubble=b, case="tight-corner-small")
        # three columns in a bubble, a tall narrow one over its left side lettered by the shared outline
        a = p.bubble(tl[0] + 380, tl[1] + 330, 70, 135)
        b = p.bubble(tl[0] + 290, tl[1] + 360, 34, 165)
        c("やっぱりそうかここで待っててね", tl[0] + 384, tl[1] + 330, 25, 5, weight=500, bubble=a,
          case="tight-side-big", col_gap=1.12)
        c("気をつけて行ってね", tl[0] + 292, tl[1] + 360, 24, 5, weight=700, bubble=b, case="tight-side-narrow",
          col_gap=1.12)
        # a bubble by itself whose four columns fill it from outline to outline
        a = p.bubble(bt[0] + 400, bt[1] + 330, 58, 150)
        c("今日はいい天気だね明日また来るよね", bt[0] + 400, bt[1] + 330, 24, 5, weight=700, bubble=a, case="tight-full",
          col_gap=1.1)
        b = p.bubble(bt[0] + 800, bt[1] + 330, 140, 190)
        c(lines[0] + lines[1], bt[0] + 800, bt[1] + 330, 28, 6, weight=500, bubble=b, case="normal")
        p.inter[p.np.asarray(p.outline) > 127] = 0
    elif n == 20:  # tall bubbles drawn see-through or semi-transparent over hair, a tone or a hatching: large rooms
        tr, tl, bt = p.frame3(art=False)
        # two bubbles drawn over hair: the strands cross the paper of the one, faint on the other's semi-transparent
        # paper (its lettering ringed white)
        a = p.bubble(tr[0] + 130, tr[1] + 390, 85, 300)
        b = p.bubble(tr[0] + 390, tr[1] + 400, 130, 260)
        p.within(p.box_mask((tr[0] + 6, tr[1] + 6, tr[2] - 6, tr[3] - 6)),
                 lambda: p.hair((tr[0] + 10, tr[1] + 60, tr[2] - 10, tr[3] - 60), 7))
        p.veil(p.inter == b)
        c("そんなことないよ信じて", tr[0] + 130, tr[1] + 390, 42, 6, weight=700, bubble=a, case="see-through")
        c("まだ終わってないここで待っててね", tr[0] + 390, tr[1] + 400, 40, 6, weight=700, bubble=b,
          case="veiled-hair", stroke=3)
        # on a tone: a tall narrow white bubble, and a semi-transparent one, the tone faint on its paper
        p.tone((tl[0] + 6, tl[1] + 6, tl[2] - 6, tl[3] - 6))
        a = p.bubble(tl[0] + 140, tl[1] + 400, 72, 300)
        c("ちょっと待って", tl[0] + 140, tl[1] + 400, 44, 9, weight=700, bubble=a, case="narrow-on-tone")
        b = p.bubble(tl[0] + 380, tl[1] + 400, 105, 280)
        p.within(p.inter == b, lambda: p.tone((tl[0] + 6, tl[1] + 6, tl[2] - 6, tl[3] - 6)))
        p.veil(p.inter == b)
        c("気をつけて行ってね", tl[0] + 380, tl[1] + 400, 40, 5, weight=700, bubble=b, case="veiled-tone")
        # on a hatching: a semi-transparent bubble, the hatching faint on its paper; a tall narrow white one of one
        # column; a tall one toned inside, of three
        x0, y0, x1, y1 = bt
        left = p.box_mask((x0 + 6, y0 + 6, x0 + 460, y1 - 6))
        p.within(left, lambda: p.hatching((x0 + 6, y0 + 6, x0 + 460, y1 - 6), step=13, width=2))
        a = p.bubble(x0 + 220, y0 + 400, 100, 320)
        p.within(p.inter == a, lambda: p.hatching((x0 + 6, y0 + 6, x0 + 460, y1 - 6), step=13, width=2))
        p.veil(p.inter == a)
        c("本当に行くのか明日また来るよ", x0 + 220, y0 + 400, 42, 7, weight=700, bubble=a, case="veiled-hatch")
        a = p.bubble(x0 + 620, y0 + 400, 62, 330)
        c("絶対に許さない", x0 + 620, y0 + 400, 44, 9, weight=800, bubble=a, case="narrow-one-column")
        a = p.bubble(x0 + 880, y0 + 400, 125, 330)
        p.within(p.inter == a, lambda: p.tone((x0 + 750, y0 + 66, x0 + 1010, y0 + 734), pitch=6, dot=1.6, shade=150))
        c("やっぱりそうかなんでここに何をしてるの", x0 + 880, y0 + 400, 40, 7, weight=600, bubble=a,
          case="toned-inside")
    else:  # 16: narrow bubbles with heavy short columns at the sample set's size of characters
        tr, tl, bt = p.frame3()
        cols = ((tr[0] + 100, 34, 22), (tr[0] + 250, 38, 24), (tr[0] + 400, 42, 26), (tl[0] + 120, 36, 24),
                (tl[0] + 300, 40, 26))
        words = ["そんなはずない", "絶対に許さない", "見つけたぞ", "もう一度だけ", "信じられない"]
        for k, (x, rx, size) in enumerate(cols):
            y = (tr[1] if k < 3 else tl[1]) + 300
            b = p.bubble(x, y, rx, 210)
            c(words[k] + "！", x, y, size, 12, weight=900, bubble=b, case="narrow-bold")
        b = p.bubble(bt[0] + 500, bt[1] + 330, 150, 200)
        c(lines[0] + lines[1], bt[0] + 500, bt[1] + 330, 28, 6, weight=500, bubble=b, case="normal")
    return p


LAYOUTS = 20
SAMPLE_SEEDS = (0, 1, 2, 3)  # tools/make_sample_page.py's own page, at these seeds


def synthetic_page(name: str, models_dir: Path) -> dict[str, Any]:
    """A made-up page by name ("L01".."L20", or "S0".. for make_sample_page's): its RGB image (numpy), its layers
    (None for make_sample_page's) and its truth."""
    import numpy as np

    if name.startswith("S"):
        import make_sample_page

        img, truth = make_sample_page.make_page(int(name[1:]))
        texts = [{"id": k, "kind": "bubble", "bubble": 0, "text_box": t["text_box"], "size": 34, "weight": 700,
                  "chars": len(t["text"]), "case": "sample-" + t.get("shape", ""), "colour": 0, "columns": 0}
                 for k, t in enumerate(truth)]
        return {"rgb": np.asarray(img.convert("RGB")), "layers": None, "texts": texts, "bait": []}
    p = layout(int(name[1:]), _jp_font_path(models_dir))
    return {"rgb": np.asarray(p.img.convert("RGB")),
            "layers": {"text": np.asarray(p.text), "outline": np.asarray(p.outline), "inter": p.inter},
            "texts": p.truth, "bait": p.bait}


# ====================================================================== the pages to do
def items(sets: Sequence[str], scales: Sequence[str], root: Path) -> list[str]:
    """Every work item, in a fixed order: "om:<title 1-5>:<page index>@<scale>" and "syn:<name>@<scale>"; a degraded
    scale (`DEGRADED`) for every made-up page and `DEGRADED_PAGES` pages of the sample set, the same ones each time."""
    out: list[str] = []
    if "openmantra" in sets:
        import openmantra

        pages = openmantra.load(root)
        names = openmantra.series_names(pages)
        keys = [f"om:{names.index(p.series) + 1}:{p.index}" for p in pages]
        some = set(random.Random(DEGRADED_SEED).sample(sorted(keys), min(DEGRADED_PAGES, len(keys))))
        for key in keys:
            out.extend(f"{key}@{s}" for s in scales if s not in DEGRADED or key in some)
    if "synthetic" in sets:
        names = [f"L{n:02d}" for n in range(1, LAYOUTS + 1)] + [f"S{s}" for s in SAMPLE_SEEDS]
        out.extend(f"syn:{n}@{s}" for n in names for s in scales)
    return out


def shard_of(all_items: Sequence[str], shard: int, of: int) -> list[str]:
    return [it for k, it in enumerate(all_items) if k % of == shard]


# ====================================================================== the made-up translator
WORDS = ("I", "you", "we", "it", "the", "a", "to", "and", "of", "is", "that", "what", "this", "can't", "don't",
         "really", "never", "always", "there", "here", "about", "think", "know", "want", "going", "right", "little",
         "something", "everyone", "nothing", "together", "remember", "tonight", "yesterday", "already", "maybe",
         "please", "wait", "come", "back", "home", "school", "friend", "brother", "teacher", "morning", "should",
         "would", "could", "because", "though", "anyway", "seriously", "probably", "important", "different",
         "no", "so", "me", "he", "do", "my", "on", "in", "but", "not", "now", "can", "she", "was", "just", "like",
         "well", "everything", "understand", "absolutely", "definitely", "comfortable", "interesting",
         "unbelievable", "nevertheless")
# the share of the words of each length (12: 12 letters or more) in OpenMantra's professional English, which the
# invented English follows (numbers only; a vocabulary of long words hyphenates and shrinks twice as often)
WORD_LENGTHS = {1: 0.053, 2: 0.169, 3: 0.234, 4: 0.222, 5: 0.116, 6: 0.092, 7: 0.049, 8: 0.034, 9: 0.018, 10: 0.007,
                11: 0.004, 12: 0.004}


def canned(n: int, seed: str) -> str:
    """Invented English of about *n* characters (never a word more), its words as long as the professional English's
    (`WORD_LENGTHS`), the same for the same *seed*."""
    rnd = random.Random(seed)
    by_len: dict[int, list[str]] = {}
    for word in WORDS:
        by_len.setdefault(min(12, len(word)), []).append(word)
    lengths = sorted(WORD_LENGTHS)
    weights = [WORD_LENGTHS[k] for k in lengths]
    n = max(2, n)
    words: list[str] = []
    while True:
        room = n - len(" ".join(words)) - (1 if words else 0)
        if room <= 0:
            break
        size = rnd.choices(lengths, weights)[0]
        if size > room + 2:  # the last word: one that ends the text about where the line's English ends
            words.append(rnd.choice(by_len[max(1, min(12, room))]))
            break
        words.append(rnd.choice(by_len[size]))
    text = " ".join(words)
    if len(words) >= 6:
        cut = len(words) // 2
        text = " ".join(words[:cut]) + ". " + " ".join(words[cut:]).capitalize()
    return text[0].upper() + text[1:] + rnd.choice((".", "!", "?", "...", "!?"))


def cjk(text: str) -> int:
    return sum(1 for ch in text if ord(ch) >= 0x3000)


class Canned:
    """A translator that answers each line of the sample set with the professional English of the gold box its
    region matches (`gold_of`, set per page; in memory only, never in the output), and every other line with
    invented English (`canned`) as long as the English the line's region should get (`length_of`: a made-up text's),
    else EN_PER_JA times its Japanese characters."""

    name = "canned"

    def __init__(self) -> None:
        self.regions: list[Any] = []
        self.length_of: Any = None
        self.gold_of: Any = None
        self.key = ""

    def translate_page(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = (), notes: str = "",
                       upcoming: Sequence[str] = (), meta: Any = None, cancel: Any = None,
                       on_slow: Any = None) -> list[str]:
        used: set[int] = set()
        out = []
        for t in texts:
            region = None
            for k, r in enumerate(self.regions):
                if k not in used and r.source_text == t:
                    used.add(k)
                    region = r
                    break
            gold = self.gold_of(region) if region is not None and self.gold_of is not None else ""
            if gold:  # (the sample set: the professional line itself, in memory only)
                out.append(gold)
                continue
            n = self.length_of(region) if region is not None and self.length_of is not None else 0
            n = n or max(2, round(EN_PER_JA * max(1, cjk(t))))
            seed = f"{self.key}/{region.text_box if region is not None else len(out)}"
            out.append(canned(n, seed))
        return out


# ====================================================================== recording what the render does
class Recorder:
    """`Pipeline._erase` and `letter_text` watched: per region its mask before the erase, its paper colour, the page
    erased before any lettering, the room each region was lettered in, the pixels its lettering changed (and their
    grey as drawn) and the lines its layout set - of the finished page alone: what the page filling in did on its
    working copy (`pipeline.PageFill`) is forgotten as the page's render begins (`Pipeline._render`)."""

    def __init__(self, pipe: Any):
        import numpy as np
        import taslation.pipeline as pl
        import taslation.render.artwork as aw
        import taslation.render.typeset as ts

        self.np, self.pl, self.ts, self.aw, self.pipe = np, pl, ts, aw, pipe
        self.reset()
        self._erase = pipe._erase
        self._letter = pl.letter_text
        self._layout = ts.layout_text
        self._set = pipe._set_text
        self._tone = aw.fill_tone
        self._render = pipe._render
        self.current: Any = None
        self._toning = False

        def render(*a, **k):
            self.reset()  # (the drafts' erases and letterings were on the working copy: no part of the finished page)
            return self._render(*a, **k)

        def erase(out, region, quick=False):
            mask = region.mask.copy()
            self.before[id(region)] = (region.bbox, mask)
            self.page = out
            self._toning = False
            bg = self._erase(out, region, quick)
            if self._toning:
                self.toned.add(id(region))
            self.paper[id(region)] = tuple(int(v) for v in bg)
            return bg

        def fill_tone(*a, **k):  # (the region painted over with its ground's own pattern: its dots are no residue)
            done = self._tone(*a, **k)
            self._toning = self._toning or bool(done)
            return done

        def set_text(image, region, text, background, style, scaled=True, part=self.pl.OWN_PART):
            held, self.current = self.current, region
            try:
                return self._set(image, region, text, background, style, scaled, part=part)
            finally:
                self.current = held

        def letter(image, region, text, *a, **k):
            if image is None or self.current is None:
                return self._letter(image, region, text, *a, **k)
            if self.erased is None and self.page is not None:
                self.erased = self.page.copy()  # (every erase done, no lettering yet)
            before = np.asarray(image.convert("RGB")).copy()
            self.fits = []
            done = self._letter(image, region, text, *a, **k)
            after = np.asarray(image.convert("RGB"))
            key = id(self.current)
            self.ink[key] = np.any(after != before, axis=2)
            self.drawn[key] = _gray(after)[self.ink[key]]
            mask = region.mask
            if mask.shape != (region.height, region.width):
                import cv2

                mask = cv2.resize(mask, (region.width, region.height), interpolation=cv2.INTER_NEAREST)
            self.rooms[key] = (region.bbox, mask > 0)
            # (the layout drawn is the last one asked for: a turned block's, in its turned frame, after the sizes the
            # lettering compared)
            self.lines[key] = [ln for fit in self.fits[-1:] for ln in _fit_lines(fit)]
            self.won[key] = getattr(done, "won", "")
            self.frame[key] = getattr(done, "frame", "")
            return done

        def layout_text(*a, **k):
            fit = self._layout(*a, **k)
            self.fits.append(fit)
            return fit

        pipe._erase = erase
        pipe._render = render
        pipe._set_text = set_text
        pl.letter_text = letter
        ts.layout_text = layout_text
        aw.fill_tone = fill_tone

    def reset(self) -> None:
        self.before: dict[int, Any] = {}
        self.toned: set[int] = set()
        self.paper: dict[int, tuple[int, ...]] = {}
        self.rooms: dict[int, Any] = {}
        self.ink: dict[int, Any] = {}
        self.drawn: dict[int, Any] = {}
        self.lines: dict[int, list[str]] = {}
        self.won: dict[int, str] = {}
        self.frame: dict[int, str] = {}
        self.fits: list[Any] = []
        self.page: Any = None
        self.erased: Any = None

    def largest(self) -> int:
        """The largest size any lettering may take (``max_font_size``; a region's cap holds it under that)."""
        return int(self.pipe.settings.max_font_size)

    def close(self) -> None:
        self.pipe._erase = self._erase
        self.pipe._render = self._render
        self.pipe._set_text = self._set
        self.pl.letter_text = self._letter
        self.ts.layout_text = self._layout
        self.aw.fill_tone = self._tone


def _fit_lines(fit: Any) -> list[str]:
    try:
        _font, placed, _size = fit
        return [str(p[0]) for p in placed]
    except Exception:  # noqa: BLE001 - another kind of fit: no lines told
        return []


class Drafts:
    """The page as a window shows it filling in while it is translated (`pipeline.PageFill`'s events): each region's
    patch pasted over the page in turn as it comes, as the window's page filling in pastes it (`ui.jobs.Filling`), the
    announced regions' boxes and which region each patch was of, in order. In memory only."""

    def __init__(self, rgb: Any):
        self.page = rgb.copy()
        self.boxes: list[Box] = []
        self.sent: list[tuple[int, Box]] = []  # (the announced region's index, the patch's box), in the order sent
        self.own: dict[int, tuple[Box, Any]] = {}  # index -> its last own patch (box, grey pixels)

    def event(self, kind: str, data: dict[str, Any]) -> None:
        import numpy as np

        if kind == "regions":
            self.boxes = [tuple(int(v) for v in b) for b in data["boxes"]]
        elif kind == "read" and data.get("box") is not None and 0 <= int(data["index"]) < len(self.boxes):
            self.boxes[int(data["index"])] = tuple(int(v) for v in data["box"])
        elif kind == "translated" and data.get("patch") is not None:
            x0, y0, x1, y1 = (int(v) for v in data["box"])
            patch = np.asarray(data["patch"].convert("RGB"))
            self.page[y0:y1, x0:x1] = patch
            self.sent.append((int(data["index"]), (x0, y0, x1, y1)))
            self.own[int(data["index"])] = ((x0, y0, x1, y1), _gray(patch))

    def index_of(self, region: Any) -> int:
        """The announced index of *region* (its box the one it was announced or read with, or the nearest); -1."""
        best, at = 0.0, -1
        for k, b in enumerate(self.boxes):
            v = _inter(region.bbox, b) / max(1.0, _area(region.bbox) + _area(b) - _inter(region.bbox, b))
            if v > best:
                best, at = v, k
        return at if best >= 0.5 else -1

    def covered(self, region: Any, final: Any, drop: float) -> Any:
        """Where *region*'s last own patch showed the finished page (*final*, grey) and the page filling in no longer
        does - by *drop* grey levels or more -, so a patch sent after it covered that part: a neighbour's, lettered
        without it (no part of a region's own draft differing from the finished page, nor a region never drafted)."""
        import numpy as np

        out = _box_mask(final.shape, (0, 0, 0, 0))
        got = self.own.get(self.index_of(region))
        if got is None:
            return out
        (x0, y0, x1, y1), own = got
        shown = _gray(self.page[y0:y1, x0:x1])
        done = final[y0:y1, x0:x1].astype(np.float32)
        out[y0:y1, x0:x1] = (np.abs(own - done) < drop) & (np.abs(shown - done) >= drop)
        return out


# ====================================================================== measuring
def _inter(a: Sequence[float], b: Sequence[float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(a: Sequence[float]) -> float:
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def _grow(b: Sequence[float], d: float, w: int, h: int) -> Box:
    return (max(0, int(b[0] - d)), max(0, int(b[1] - d)), min(w, int(math.ceil(b[2] + d))), min(h, int(math.ceil(b[3] + d))))


def _page_mask(shape: tuple[int, int], box: Sequence[int], mask: Any) -> Any:
    import numpy as np
    import cv2

    out = np.zeros(shape, bool)
    x0, y0, x1, y1 = (int(v) for v in box)
    if mask.shape != (y1 - y0, x1 - x0):
        mask = cv2.resize(mask.astype(np.uint8), (max(1, x1 - x0), max(1, y1 - y0)), interpolation=cv2.INTER_NEAREST)
    h, w = shape
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if cx1 > cx0 and cy1 > cy0:
        out[cy0:cy1, cx0:cx1] = mask[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0] > 0
    return out


def _box_mask(shape: tuple[int, int], box: Sequence[int]) -> Any:
    import numpy as np

    out = np.zeros(shape, bool)
    h, w = shape
    x0, y0, x1, y1 = (int(v) for v in box)
    out[max(0, y0):max(0, min(h, y1)), max(0, x0):max(0, min(w, x1))] = True
    return out


def _gray(rgb: Any) -> Any:
    import cv2

    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(int)


def _glyph(r: Any, h: int) -> float:
    if r.glyph:
        return float(r.glyph)
    if r.char_size:
        return float(r.char_size)
    tb = r.text_box
    return float(min(max(8.0, min(tb[2] - tb[0], tb[3] - tb[1])), 0.035 * h))


def _pieces(dark: Any, tbg: Box, g: float, win: Box, others: Sequence[Box] = (),
            joined: bool = True) -> tuple[Any, Any]:
    """The original's dark pieces in *win*, as two masks (page-sized): lettering (mostly inside the grown text box
    *tbg*, no longer than it) and lines (longer than LINE_GLYPHS glyphs, mostly outside it). Of a line, the parts
    inside the text box off what of it runs straight on (`LINE_RUN` glyphs one way: the outline's sides, a tail) that
    are no longer than `GLYPH_PART` glyphs are lettering: a glyph of a column set by the outline, joined to it (taken
    for the outline, its erase was counted as the outline cut and what of it was left as no lettering left); such
    parts inside the grown text boxes of the other regions (*others*: a neighbour's column by the outline the two
    share) are neither the region's lettering nor a line. *joined* False: the lettering alone, those parts left with
    the line (BOX_SMALL: a stretch of a curved outline among them, inside the grown text box, carried the lettering's
    box out to the grown box's edge)."""
    import numpy as np
    import cv2

    x0, y0, x1, y1 = win
    sub = dark[y0:y1, x0:x1].astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    inside = np.zeros(sub.shape, bool)
    tx0, ty0, tx1, ty1 = tbg[0] - x0, tbg[1] - y0, tbg[2] - x0, tbg[3] - y0
    inside[max(0, ty0):max(0, ty1), max(0, tx0):max(0, tx1)] = True
    theirs = np.zeros(sub.shape, bool)
    for ox0, oy0, ox1, oy1 in others:
        theirs[max(0, oy0 - y0):max(0, oy1 - y0), max(0, ox0 - x0):max(0, ox1 - x0)] = True
    theirs &= ~inside
    counts_in = np.bincount(labels[inside], minlength=n) if n else np.zeros(1, int)
    tw, th = tbg[2] - tbg[0], tbg[3] - tbg[1]
    letters = np.zeros(n, bool)
    lines = np.zeros(n, bool)
    for i in range(1, n):
        bw, bh, a = int(stats[i, 2]), int(stats[i, 3]), int(stats[i, 4])
        share = counts_in[i] / max(1, a)
        if share >= INSIDE_TEXT and bw <= tw + g and bh <= th + g:
            letters[i] = True
        elif max(bw, bh) > LINE_GLYPHS * g:
            lines[i] = True
    lp_sub, ln_sub = letters[labels], lines[labels]
    if joined and (ln_sub & (inside | theirs)).any():
        run = max(5, int(round(LINE_RUN * g))) | 1
        core = np.zeros(sub.shape, bool)
        for angle in range(0, 180, LINE_STEP):  # (a thin curved outline holds a straight run only near its own slope)
            kernel = np.zeros((run, run), np.uint8)
            c, d = run // 2, (run - 1) / 2.0
            dx, dy = d * np.cos(np.radians(angle)), d * np.sin(np.radians(angle))
            cv2.line(kernel, (int(round(c - dx)), int(round(c - dy))), (int(round(c + dx)), int(round(c + dy))), 1, 1)
            core |= cv2.morphologyEx(ln_sub.astype(np.uint8), cv2.MORPH_OPEN, kernel) > 0
        off = ln_sub & (inside | theirs) & ~(cv2.dilate(core.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        k, parts, part_stats, _ = cv2.connectedComponentsWithStats(off.astype(np.uint8), connectivity=8)
        small = np.maximum(part_stats[:, 2], part_stats[:, 3]) <= GLYPH_PART * g
        small[0] = False
        glyphs = small[parts]
        lp_sub, ln_sub = lp_sub | (glyphs & inside), ln_sub & ~glyphs
    lp = np.zeros(dark.shape, bool)
    ln = np.zeros(dark.shape, bool)
    lp[y0:y1, x0:x1] = lp_sub
    ln[y0:y1, x0:x1] = ln_sub
    return lp, ln


def _cut(lost: Any, still: Any, win: Box, longest: float) -> int:
    """How many of the line pixels made light (*lost*, bool, page-sized) break a line: each piece of them that touches
    two pieces of the lines still dark on the erased page (*still*) in *win*, or one longer than *longest* px (a stretch
    of the line gone); not a stroke of a glyph joined to the line erased where the line goes on past it, nor a glyph of
    a neighbour's column joined to an outline the two share."""
    import numpy as np
    import cv2

    x0, y0, x1, y1 = win
    sub = lost[y0:y1, x0:x1].astype(np.uint8)
    if not sub.any():
        return 0
    _k, kept = cv2.connectedComponents(still[y0:y1, x0:x1].astype(np.uint8), connectivity=8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    hh, ww = sub.shape
    total = 0
    for i in range(1, n):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if max(bw, bh) > longest:
            total += area
            continue
        a0, b0, a1, b1 = max(0, x - 1), max(0, y - 1), min(ww, x + bw + 1), min(hh, y + bh + 1)
        piece = (labels[b0:b1, a0:a1] == i).astype(np.uint8)
        ring = (cv2.dilate(piece, np.ones((3, 3), np.uint8)) > 0) & (piece == 0)
        if np.count_nonzero(np.unique(kept[b0:b1, a0:a1][ring])) >= 2:
            total += area
    return total


def _interior(O: Any, letters: Any, tb: Box, win: Box) -> Any:
    """The closed light area round the text: light pixels and the lettering, connected to the text box's core,
    within *win*; None where it reaches *win*'s edge (no closed bubble there)."""
    import numpy as np
    import cv2

    x0, y0, x1, y1 = win
    area = ((O[y0:y1, x0:x1] >= 170) | letters[y0:y1, x0:x1]).astype(np.uint8)
    n, labels = cv2.connectedComponents(area, connectivity=4)
    cx0, cy0 = (tb[0] + tb[2]) // 2 - x0, (tb[1] + tb[3]) // 2 - y0
    qw, qh = max(1, (tb[2] - tb[0]) // 4), max(1, (tb[3] - tb[1]) // 4)
    core = labels[max(0, cy0 - qh):max(0, cy0 + qh), max(0, cx0 - qw):max(0, cx0 + qw)]
    ids = set(np.unique(core[core > 0]).tolist())
    if not ids:
        return None
    sel = np.isin(labels, list(ids))
    if sel[0, :].any() or sel[-1, :].any() or sel[:, 0].any() or sel[:, -1].any():
        return None
    rim = (cv2.dilate(sel.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~sel
    if rim.any() and float((O[y0:y1, x0:x1][rim] < INK_DARK).mean()) < OUTLINED:
        return None  # (closed by no outline: a gradient's or a tone's light part)
    out = np.zeros(O.shape, bool)
    out[y0:y1, x0:x1] = sel
    return out


def _filled(mask: Any, win: Box) -> Any:
    """*mask* with its holes in *win* filled (what it encloses: lettering pieces, a symbol, the drawing inside)."""
    import numpy as np
    import cv2

    x0, y0, x1, y1 = win
    sub = mask[y0:y1, x0:x1]
    n, labels = cv2.connectedComponents((~sub).astype(np.uint8), connectivity=4)
    edge = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])).tolist())
    holes = ~sub & ~np.isin(labels, list(edge))
    out = mask.copy()
    out[y0:y1, x0:x1] |= holes
    return out


def _seen(room: Any, inter: Any, g: float) -> Any:
    """The bubble as the person sees it round a region's lettering (``ROOM_LOOSE``): the room it was set in (*room*,
    bool, of the page) and the closed interior round its text (*inter*, or None), joined over the drawing's thin lines
    across its paper (hair, a hatching: closed by a third of a glyph *g*) and its holes filled - not the piece of it a
    line cut off for the lettering's layout."""
    import numpy as np
    import cv2

    both = room if inter is None else room | inter
    ys, xs = np.nonzero(both)
    if not xs.size:
        return both
    h, w = both.shape
    k = max(1, int(g / 3))
    x0, y0 = max(0, int(xs.min()) - k), max(0, int(ys.min()) - k)
    x1, y1 = min(w, int(xs.max()) + 1 + k), min(h, int(ys.max()) + 1 + k)
    sub = cv2.copyMakeBorder(both[y0:y1, x0:x1].astype(np.uint8), k, k, k, k, cv2.BORDER_CONSTANT, value=0)
    shut = cv2.morphologyEx(sub, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
    out = np.zeros(both.shape, bool)
    out[y0:y1, x0:x1] = shut[k:-k, k:-k] > 0
    return _filled(out, (x0, y0, x1, y1))


def room_loose(share: float, font: int, cap: int, largest: int) -> bool:
    """Whether a region's lettering is small in a large room (``ROOM_LOOSE``): its box takes under `LOOSE_SHARE` of
    the bubble as seen (*share*, `_seen`) at a size *font* under `LOOSE_SIZE` of the largest it may take - its cap
    (*cap*, the page's, 0 for none) and the largest size of all (*largest*, ``max_font_size``)."""
    top = min(largest, cap) if cap > 0 else largest
    return share < LOOSE_SHARE and 0 < font < LOOSE_SIZE * top


def _off_rim(mask: Any, core: Any, win: Box) -> Any:
    """The pieces of *mask* in *win* clear of *core*'s rim (one touching it is the outline or the drawing beyond,
    redrawn thicker or reaching in), and those that cover `FILL_SHARE` of *core* or more (the bubble painted over)."""
    import numpy as np
    import cv2

    x0, y0, x1, y1 = win
    sub = mask[y0:y1, x0:x1].astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    out = np.zeros(mask.shape, bool)
    if n <= 1:
        return out
    c = core[y0:y1, x0:x1]
    rim = c & ~(cv2.erode(c.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    on_rim = np.zeros(n, bool)
    on_rim[np.unique(labels[rim & (labels > 0)])] = True
    keep = ~on_rim | (stats[:, 4] >= FILL_SHARE * max(1, int(c.sum())))
    keep[0] = False
    out[y0:y1, x0:x1] = keep[labels]
    return out


def _specks(mask: Any) -> int:
    import numpy as np
    import cv2

    if not mask.any():
        return 0
    n, _l, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return int(sum(1 for i in range(1, n) if stats[i, 4] >= 2))


def _long_pieces(mask: Any, win: Box, length: float) -> Any:
    """The pieces of *mask* in *win* longer than *length* (page-sized): lines kept on the erased page."""
    import numpy as np
    import cv2

    x0, y0, x1, y1 = win
    out = np.zeros(mask.shape, bool)
    sub = mask[y0:y1, x0:x1].astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    if n > 1:
        keep = np.zeros(n, bool)
        keep[1:] = np.maximum(stats[1:, 2], stats[1:, 3]) > length
        out[y0:y1, x0:x1] = keep[labels]
    return out


def _solid(mask: Any, g: float, win: Box) -> Any:
    """The parts of *mask* in *win* that an opening of `SOLID` glyphs keeps: fills (a black ground), not lines."""
    import numpy as np
    import cv2

    k = max(3, int(round(SOLID * g)) | 1)
    x0, y0, x1, y1 = win
    out = np.zeros(mask.shape, bool)
    sub = mask[y0:y1, x0:x1].astype(np.uint8)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    out[y0:y1, x0:x1] = cv2.dilate(cv2.morphologyEx(sub, cv2.MORPH_OPEN, ker), np.ones((3, 3), np.uint8)) > 0
    return out


def _ground(O: Any, ring: Any) -> tuple[float, float] | None:
    """The ground's mean and deviation over *ring*, None where it has too few pixels."""
    if int(ring.sum()) < 20:
        return None
    v = O[ring]
    return float(v.mean()), float(v.std())


def _left(E: Any, ink: float | Any, dom: Any, ground: float, std: float) -> Any:
    """The pixels of *dom* still nearer the lettering's ink (a level, or the original's pixels) than half the way
    to the *ground*; on a textured ground (a tone) compared blurred, as the eye sees it."""
    import numpy as np
    import cv2

    full = np.abs(ground - ink)
    seen = cv2.blur(E.astype(np.float32), (5, 5)) if std > TEXTURED else E
    return dom & (full >= CONTRAST) & (np.abs(seen - ink) < HALF_WAY * full)


def _truth_left(O: Any, E: Any, T: Any, Lo: Any, inter: Any, t: dict[str, Any], tm: Any) -> Any:
    """The made-up text *t*'s pixels *tm* left after the erase: nearer its ink than half the way to the ground
    round its text box (a ring half a glyph to a glyph beyond it, inside its bubble when it has one, off every
    lettering and outline; compared blurred on a tone)."""
    import numpy as np
    import cv2

    h, w = O.shape
    g = float(t.get("size") or 15)
    tb = t["text_box"]
    ring = _box_mask((h, w), _grow(tb, g, w, h)) & ~_box_mask((h, w), _grow(tb, g / 2, w, h))
    ring &= ~(cv2.dilate((T | Lo).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0)
    if t.get("bubble"):
        ring &= inter == t["bubble"]
    got = _ground(O, ring)
    ink = float(t.get("colour", 0))
    ground, std = got if got is not None else (255.0 - ink, 0.0)
    return _left(E, ink, tm, ground, std)


def _hyphens(lines: Sequence[str]) -> int:
    return sum(1 for ln in lines[:-1] if ln.rstrip().endswith(("-", "‐")) and len(ln.rstrip()) > 1
               and ln.rstrip()[-2].isalpha())


def _see_through(orig: Any, r: Any) -> bool:
    """Whether the program takes *r* for a bubble the detectors could not close drawn see-through over the drawing
    (`artwork.see_through`, on the paper `artwork.closed_interior` finds round its lettering): lettering on the drawing,
    which LaMa erases on purpose although its paper is closed and light."""
    import numpy as np
    from taslation.render import artwork, pagescale

    if not hasattr(artwork, "see_through") or not (r.from_model and r.tier == 3
                                                    and r.kind in ("bubble", "dark-bubble")):
        return False
    rgb = np.ascontiguousarray(np.asarray(orig)[..., :3])
    closed = artwork.closed_interior(rgb, artwork.box_of(rgb, r), r.dark, pagescale.of(r))
    return closed is not None and bool(artwork.see_through(rgb, r, closed))


def _shared_lines(lines_: Any, r: Any, others: Sequence[Any], g: float, w: int, h: int) -> Any:
    """The pixels of *lines_* (the original's lines round *r*) inside *r*'s box and a neighbour's (of *others*), both
    grown by half a glyph: the outline where two bubbles meet."""
    own = _box_mask((h, w), _grow(r.bbox, g / 2, w, h))
    near = _box_mask((h, w), (0, 0, 0, 0))
    for q in others:
        if q is not r and _inter(_grow(q.bbox, g / 2, w, h), _grow(r.bbox, g / 2, w, h)) > 0:
            near |= _box_mask((h, w), _grow(q.bbox, g / 2, w, h))
    return lines_ & own & near


def measure_page(orig: Any, erased: Any, final: Any, regions: Sequence[Any], rec: Recorder,
                 truth: list[dict[str, Any]], layers: dict[str, Any] | None, gold_kind: str,
                 drafts: Drafts | None = None) -> tuple[list, list]:
    """Per region the measures (`CODES`), and the page's own codes (`PAGE_CODES`); *drafts* the page as it filled in."""
    import numpy as np
    import cv2

    O, E = _gray(orig), _gray(erased)
    F = _gray(final)
    holders = [q for q in regions if id(q) in rec.ink or id(q) in rec.before]  # (lettered or erased: they hold text)
    h, w = O.shape
    dark = O < INK_DARK
    lettered = [r for r in regions if id(r) in rec.ink]
    erased_ids = set(rec.before)
    rows: list[dict[str, Any]] = []
    inks = {id(r): rec.ink[id(r)] for r in lettered}
    grown_inks = {k: cv2.dilate(v.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0 for k, v in inks.items()}
    interiors: dict[int, Any] = {}
    T = layers["text"] >= 128 if layers is not None else None
    Lo = layers["outline"] >= 128 if layers is not None else None
    for i, r in enumerate(regions):
        g = _glyph(r, h)
        tb = tuple(int(v) for v in r.text_box)
        tbg = _grow(tb, g / 3, w, h)
        win = _grow(r.bbox, max(6, g), w, h)
        row: dict[str, Any] = {
            "i": i, "box": [int(v) for v in r.bbox], "text_box": list(tb), "kind": r.kind,
            "from_model": bool(r.from_model), "tier": int(r.tier), "status": r.status, "ja_chars": cjk(r.source_text),
            "glyph": round(g, 1), "font": int(r.font_size), "cap": int(r.size_cap), "flags": list(r.letter_flags),
            "ocr_conf": round(float(r.ocr_confidence), 3), "ocr_split": bool(r.ocr_split),
            "inpainted": r.inpainted is not None, "toned": id(r) in getattr(rec, "toned", ()),
            "angle": round(float(r.angle), 1), "sound": getattr(r, "sound", ""), "sfx": r.tag == "sfx",
            "codes": [], "m": {}}
        m = row["m"]
        codes = row["codes"]
        before = rec.before.get(id(r))
        paper = rec.paper.get(id(r))
        # light lettering on a dark ground (the paper the erase took, else the region's kind): its pieces are the
        # light ones, its interior the dark area round it, and the ground itself (a fill) is no line
        dark_ground = sum(paper) / 3 < 100 if paper else r.kind in DARK_KINDS
        inkmask = (O > 255 - INK_DARK) if dark_ground else dark
        others = [_grow(tuple(int(v) for v in q.text_box), g / 3, w, h) for q in holders if q is not r]
        letters, lines_ = _pieces(inkmask, tbg, g, win, others)
        # (the lettering's pieces alone, not the glyphs joined to a line: its closed interior and its box go by them -
        # a stretch of a curved outline among those, inside the grown text box, opened the interior to what lies past
        # the outline and carried the box out to the grown box's edge)
        alone = _pieces(inkmask, tbg, g, win, others, joined=False)[0]
        # (lettering on a fill - a black ground, a gradient's dark end - is no lettering on a line)
        thin = _long_pieces(lines_ & ~_solid(inkmask, g, win), win, LINE_GLYPHS * g)
        inter = _interior(255 - O if dark_ground else O, alone, tb, win)
        if before is not None:
            mb = _page_mask((h, w), before[0], before[1])
            row["paper"] = list(paper) if paper else None
            light = paper is not None and sum(paper) / 3 >= 200
            # the original's lettering inside the erased area or the bubble's closed interior (not the text box's
            # corners beyond the bubble: a tone, a hatching, the outline), not moved half the way to the paper, and
            # not a piece of a line the erased page still has (the outline, a tail, hair: kept on purpose)
            zone = mb.copy()
            if inter is not None:
                zone |= cv2.erode(inter.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            dom = letters & zone
            ground = sum(paper) / 3 if paper else (0.0 if dark_ground else 255.0)
            raw = _left(E, O, dom, ground, 0.0)
            still = (E > 255 - LINE_FAINT) if dark_ground else (E < LINE_FAINT)
            kept = _long_pieces(still, win, LINE_GLYPHS * g)
            left = raw & ~kept
            m["letter_px"] = int(dom.sum())
            m["resid_px"] = int(left.sum())
            m["resid_specks"] = _specks(left)
            # lettering left that the erased page joined to a line it keeps (the column by the outline, an ellipsis
            # touching it: the line guard took it for the outline), and all left beside an outline shared with a
            # neighbour
            m["resid_line_px"] = int((raw & kept).sum())
            reach = max(3, int(g / 2) | 1)
            shared = cv2.dilate(_shared_lines(lines_, r, holders, g, w, h).astype(np.uint8), np.ones((reach, reach),
                                                                                                   np.uint8)) > 0
            m["resid_shared_px"] = int((raw & shared).sum())
            # (not where LaMa or the tone fill painted the hole: the drawing or the tone's dots there are no lettering)
            least = max(RESID_PX, RESID_SHARE * m["letter_px"])
            if not row["inpainted"] and not row["toned"]:
                if m["resid_px"] >= least:
                    codes.append("RESIDUE")
                if m["resid_line_px"] >= least:
                    codes.append("LEFT_BY_LINE")
                if m["resid_shared_px"] >= least:
                    codes.append("LEFT_SHARED")
            # marks on a bubble's flat light paper after the erase, whatever made them (lettering half taken, a
            # grey ghost of it, a stroke LaMa drew): darker than the paper by GHOST_DROP, a quarter glyph inside the
            # outline (where LaMa may reshape its edge), off the lines the bubble lets through (hair, a tail) and
            # every line the page keeps (a thin one: a bubble LaMa filled dark is no line); LaMa's regions too, judged
            # on the original (the paper a LaMa fill reports is what it painted, dark where it painted the bubble dark)
            lama = row["inpainted"]
            o_letters, o_lines = _pieces(dark, tbg, g, win, others) if dark_ground and lama else (letters, lines_)
            o_inter = (_interior(O, _pieces(dark, tbg, g, win, others, joined=False)[0], tb, win)
                       if dark_ground and lama else inter)
            if o_inter is not None and ((light and not dark_ground) or lama):
                k = max(5, int(g / 2) | 1)
                core = cv2.erode(_filled(o_inter, win).astype(np.uint8),
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0
                bare = core & ~(cv2.dilate((o_letters | o_lines).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0)
                flat = _ground(O, bare)
                if flat is not None and flat[0] >= 200 and flat[1] <= FLAT_STD:
                    drawing = cv2.dilate(o_lines.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                    # (the lettering's own pixels, or ones the erase made darker: not a thin line or a symbol of the
                    # bubble that was there before and is there still)
                    made = cv2.dilate(o_letters.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
                    made |= E < O - GHOST_DROP / 2
                    marked = E < flat[0] - GHOST_DROP
                    kept = np.zeros(marked.shape, bool)
                    for m_ in (E < LINE_FAINT, marked):
                        kept |= _long_pieces(m_ & ~_solid(m_, g, win), win, LINE_GLYPHS * g)
                    ghost = _off_rim(core & ~drawing & made & marked & ~kept, core, win)
                    m["ghost_px"] = int(ghost.sum())
                    m["ghost_specks"] = _specks(ghost)
                    if m["ghost_px"] >= GHOST_PX:
                        codes.append("GHOST")
                    if row["inpainted"]:
                        if _see_through(orig, r):  # (lettering on the drawing: LaMa's on purpose)
                            m["see_through"] = 1
                        else:
                            codes.append("LAMA_BUBBLE")
            near = lines_ & _box_mask((h, w), _grow(r.bbox, 3, w, h))
            lost = near & (O < LINE_DARK) & (E >= LIGHTENED) & (E - O >= LIGHTER)
            m["line_px"] = int((near & (O < LINE_DARK)).sum())
            m["line_lost"] = int(lost.sum())
            m["line_cut"] = _cut(lost, lines_ & (E < LINE_DARK), win, GLYPH_PART * g)
            if row["inpainted"]:
                if m["line_lost"] >= ART_LOST_PX:
                    codes.append("ART_CUT")
            elif m["line_cut"] >= LINE_LOST_PX and light:
                codes.append("LINE_CUT")
            if alone.any():
                ys, xs = np.nonzero(alone & (mb | _box_mask((h, w), tbg)))
                if xs.size:
                    ib = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
                    m["ink_box"] = list(ib)
                    cover = _inter(tb, ib) / max(1.0, _area(ib))
                    m["box_cover"] = round(cover, 3)
                    m["box_excess"] = round(_area(tb) / max(1.0, _area(ib)), 2)
                    if cover < BOX_COVER:
                        codes.append("BOX_SMALL")
                    # (in a bubble the box moves nothing: one found as a bubble, or a closed interior round it)
                    on_page = r.kind not in ("bubble", "dark-bubble") and inter is None
                    if on_page and m["box_excess"] > BOX_EXCESS and _area(tb) - _area(ib) > 8 * g * g:
                        codes.append("BOX_BIG")
        interiors[id(r)] = inter
        if id(r) in inks:
            ink = inks[id(r)]
            m["ink_px"] = int(ink.sum())
            on_line = ink & (cv2.dilate(thin.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
            m["ink_on_line"] = int(on_line.sum())
            if m["ink_on_line"] >= INK_ON_LINE_PX:
                codes.append("INK_ON_LINE")
            if inter is not None:
                out = ink & ~(cv2.dilate(inter.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
                m["ink_out"] = int(out.sum())
                if m["ink_out"] >= INK_OUT_PX:
                    codes.append("INK_OUT")
            # the lettering as drawn, taken away after it on the finished page (a neighbour's erase or lettering), or
            # shown otherwise on the page filling in under a neighbour's patch sent after its own
            drawn = rec.drawn.get(id(r))
            if drawn is not None and drawn.shape[0] == int(ink.sum()):
                m["over_px"] = int((np.abs(F[ink] - drawn) >= OVER_DROP).sum())
            if drafts is not None:
                m["draft_over_px"] = int((ink & drafts.covered(r, F, OVER_DROP)).sum())
            if m.get("over_px", 0) + m.get("draft_over_px", 0) >= OVER_PX:
                codes.append("OVER_OTHER")
            lines = rec.lines.get(id(r), [])
            m["lines"] = len(lines)
            m["hyphens"] = _hyphens(lines)
            m["won"] = rec.won.get(id(r), "")
            m["frame"] = rec.frame.get(id(r), "")
            room = rec.rooms.get(id(r))
            rm = None
            if room is not None:
                rm = _page_mask((h, w), room[0], room[1])
                ys, xs = np.nonzero(rm)
                if xs.size:
                    m["room_wh"] = [int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
                    m["room_px"] = int(rm.sum())
            ys, xs = np.nonzero(ink)
            if xs.size:
                m["lettering_box"] = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
                if rm is not None and rm.any():  # (the share of the bubble as seen its lettering takes)
                    m["seen_px"] = int(_seen(rm, inter, g).sum())
                    m["room_share"] = round(_area(m["lettering_box"]) / max(1, m["seen_px"]), 3)
                    if room_loose(m["room_share"], int(r.font_size), int(r.size_cap), rec.largest()):
                        codes.append("ROOM_LOOSE")
            if 0 < r.font_size < SMALL_FONT:
                codes.append("SMALL")
            if m["hyphens"]:
                codes.append("HYPHEN")
            # (narrow for the lines as they run: a turned block's lines run down the room, its height their length)
            wh = m.get("room_wh", [1, 1])
            length, depth = wh[::-1] if m["frame"] == "turned" else wh
            narrow = depth > 2.5 * length
            if 0 < r.font_size < 13 and (m["hyphens"] or narrow) or (m["hyphens"] >= 2):
                codes.append("SQUEEZED")
            if "no-fit" in r.letter_flags:
                codes.append("NOFIT")
            if "tight" in r.letter_flags:
                codes.append("TIGHT")
        elif r.status == "untranslated" and r.source_text:
            codes.append("UNTRANSLATED")
        no_bubble = r.kind in ("text", "text-dark") or (r.from_model and r.tier == 3)
        if no_bubble and (r.ocr_split or r.ocr_confidence < LOW_AGREEMENT) and (id(r) in inks or id(r) in erased_ids):
            codes.append("FALSE_LIKELY")
        # against the gold or made-up texts
        best, best_t = 0.0, None
        for t in truth:  # (of the smaller box: a text box may be a bubble's, a gold box larger than its lettering)
            v = _inter(tb, t["text_box"]) / max(1.0, min(_area(tb), _area(t["text_box"])))
            if v > best:
                best, best_t = v, t
        row["truth"] = best_t["id"] if best_t is not None and best >= NO_GOLD_SHARE else None
        if (id(r) in inks or id(r) in erased_ids) and row["truth"] is None:
            codes.append("T_FALSE" if gold_kind == "synthetic" else "NO_GOLD")
            if gold_kind == "synthetic":
                row["bait"] = next((b["bait"] for b in truth_bait(truth) if _inter(tb, b["box"]) > 0), "")
        if T is not None and row["truth"] is not None and before is not None:
            t = truth[row["truth"]]
            tm = T & _box_mask((h, w), _grow(t["text_box"], 2, w, h))
            tm &= _box_mask((h, w), r.bbox)
            left = _truth_left(O, E, T, Lo, layers["inter"], t, tm)
            m["t_letter_px"] = int(tm.sum())
            m["t_resid_px"] = int(left.sum())
            m["t_resid_specks"] = _specks(left)
            if m["t_resid_px"] >= max(RESID_PX, RESID_SHARE * m["t_letter_px"]):
                codes.append("T_RESIDUE")
            near = Lo & _box_mask((h, w), _grow(r.bbox, 3, w, h))
            lost = near & (O < LINE_DARK) & (E >= LIGHTENED) & (E - O >= LIGHTER)
            m["t_line_px"] = int((near & (O < LINE_DARK)).sum())
            m["t_line_lost"] = int(lost.sum())
            if m["t_line_lost"] >= LINE_LOST_PX:
                codes.append("T_LINE_CUT")
            if id(r) in inks:
                ink = inks[id(r)]
                m["t_ink_on_line"] = int((ink & (cv2.dilate(Lo.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)).sum())
                if m["t_ink_on_line"] >= INK_ON_LINE_PX:
                    codes.append("T_INK_ON_LINE")
                if t["bubble"]:
                    own = cv2.dilate((layers["inter"] == t["bubble"]).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                    m["t_ink_out"] = int((ink & ~own).sum())
                    if m["t_ink_out"] >= INK_OUT_PX:
                        codes.append("T_INK_OUT")
        rows.append(row)
    # lettering on another region's interior or lettering
    for a in lettered:
        ra = rows[regions.index(a)]
        worst = 0
        for b in lettered:
            if a is b:
                continue
            touch = int((grown_inks[id(a)] & inks[id(b)]).sum())
            inner = interiors.get(id(b))
            on_inner = int((inks[id(a)] & inner).sum()) if inner is not None and interiors.get(id(a)) is not None \
                and not (inner & interiors[id(a)]).any() else 0
            worst = max(worst, touch, on_inner)
        ra["m"]["ink_other"] = worst
        if worst >= INK_OTHER_PX:
            ra["codes"].append("INK_OTHER")
    page_codes: list[dict[str, Any]] = []
    if T is not None:  # every made-up text's pixels left after all the erases, whatever region took it
        for t in truth:
            tm = T & _box_mask((h, w), _grow(t["text_box"], 2, w, h))
            left = _truth_left(O, E, T, Lo, layers["inter"], t, tm)
            n_left, n_all = int(left.sum()), int(tm.sum())
            if n_left >= max(RESID_PX, RESID_SHARE * n_all):
                page_codes.append({"code": "T_LEFT", "truth": t["id"], "box": t["text_box"], "case": t.get("case", ""),
                                   "left_px": n_left, "of_px": n_all, "specks": _specks(left)})
    for t in truth:
        if not t.get("worded", True):
            continue
        held = [r for r in regions if _inter(r.text_box, t["text_box"]) >= NO_GOLD_SHARE * max(1.0, _area(t["text_box"]))
                or _inter(r.text_box, t["text_box"]) >= NO_GOLD_SHARE * max(1.0, _area(r.text_box))]
        done = [r for r in held if id(r) in inks or id(r) in erased_ids]
        if not held:
            page_codes.append({"code": "MISSED", "truth": t["id"], "box": t["text_box"], "case": t.get("case", "")})
        elif not done:
            page_codes.append({"code": "OCR_DROPPED", "truth": t["id"], "box": t["text_box"],
                               "status": sorted({r.status for r in held}), "case": t.get("case", "")})
    return rows, page_codes


_BAIT: dict[int, list[dict[str, Any]]] = {}


def truth_bait(truth: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _BAIT.get(id(truth), [])


# ====================================================================== one page
def open_item(item: str, root: Path, models_dir: Path) -> dict[str, Any]:
    """The page of *item* at its scale: RGB array, layers (scaled), truth texts (boxes scaled) and its kind."""
    import numpy as np
    import cv2

    name, scale = item.rsplit("@", 1)
    if name.startswith("om:"):
        import openmantra
        from openmantra_eval import worded

        _om, title, index = name.split(":")
        pages = openmantra.load(root)
        series = openmantra.series_names(pages)[int(title) - 1]
        page = next(p for p in pages if p.series == series and p.index == int(index))
        rgb = np.asarray(page.open())
        texts = [{"id": k, "text_box": list(b.box), "en_len": len(b.en), "en": " ".join(b.en.split()),
                  "worded": worded(b.ja), "case": "gold", "colour": 0, "bubble": 0} for k, b in enumerate(page.bubbles)]
        got = {"rgb": rgb, "layers": None, "texts": texts, "bait": [], "kind": "openmantra"}
    else:
        got = synthetic_page(name.split(":", 1)[1], models_dir)
        got["kind"] = "synthetic"
        for t in got["texts"]:
            t["en_len"] = round(EN_PER_JA * t["chars"])
    if scale == "small" or scale in DEGRADED:
        h, w = got["rgb"].shape[:2]
        f = SMALL_HEIGHT / h
        size = (max(1, round(w * f)), SMALL_HEIGHT)
        if scale in DEGRADED:  # as a viewer may hand a page over: compressed, then resampled by a cubic, softened
            _ok, data = cv2.imencode(".jpg", cv2.cvtColor(got["rgb"], cv2.COLOR_RGB2BGR),
                                     [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            rgb = cv2.cvtColor(cv2.imdecode(data, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
            rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_CUBIC)
            if scale == "blur":
                rgb = cv2.GaussianBlur(rgb, (0, 0), BLUR_SIGMA)
            got["rgb"] = np.ascontiguousarray(rgb)
        else:
            got["rgb"] = cv2.resize(got["rgb"], size, interpolation=cv2.INTER_AREA)
        if got["layers"] is not None:
            lay = got["layers"]
            got["layers"] = {"text": cv2.resize(lay["text"], size, interpolation=cv2.INTER_AREA),
                             "outline": cv2.resize(lay["outline"], size, interpolation=cv2.INTER_AREA),
                             "inter": cv2.resize(lay["inter"].astype(np.int32), size, interpolation=cv2.INTER_NEAREST)}
        for t in got["texts"]:
            t["text_box"] = [int(round(v * f)) for v in t["text_box"]]
            if "size" in t:
                t["size"] = round(t["size"] * f, 1)
        for b in got["bait"]:
            b["box"] = [int(round(v * f)) for v in b["box"]]
        got["factor"] = f
    else:
        got["factor"] = 1.0
    return got


def make_pipeline(as_cpu: bool) -> tuple[Any, Canned]:
    from taslation.config import Settings
    from taslation.ocr import Readers
    from taslation.ocr.readers import place_with
    from taslation.pipeline import Pipeline

    s = Settings()
    if not as_cpu:  # the defaults of a computer with a CUDA GPU and both page models, here on the processor
        s.detect_model = "on"
        s.art_erase = "lama"
    s.validate()
    translator = Canned()
    pipe = Pipeline(s, ocr=place_with(Readers(s.models_dir, s.ocr_threads), s), translator=translator, cache=None)
    held = pipe._translate_regions

    def translate_regions(regions, *a, **k):
        translator.regions = [r for r in regions if r.status == "untranslated"]
        return held(regions, *a, **k)

    pipe._translate_regions = translate_regions
    return pipe, translator


def run_item(pipe: Any, translator: Canned, rec: Recorder, item: str, root: Path, models_dir: Path
             ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Process *item* as the program does and measure it: (its record, its pictures and regions in memory)."""
    import numpy as np
    from PIL import Image
    from openmantra_eval import match

    got = open_item(item, root, models_dir)
    rgb = got["rgb"]
    texts = got["texts"]
    _BAIT[id(texts)] = got["bait"]
    pipe._book_sizes = deque(maxlen=pipe._book_sizes.maxlen)  # (each page on its own: the same in any shard)
    pipe.forget_shown()
    rec.reset()
    translator.key = item

    def length_of(region: Any) -> int:
        pairs = match([t["text_box"] for t in texts], [(region.bbox, region.text_box)])
        if pairs:
            return int(texts[pairs[0][0]].get("en_len") or 0)
        return 0

    def gold_of(region: Any) -> str:
        pairs = match([t["text_box"] for t in texts], [(region.bbox, region.text_box)])
        return str(texts[pairs[0][0]].get("en") or "") if pairs else ""

    translator.length_of = length_of
    translator.gold_of = gold_of
    t0 = time.monotonic()
    drafts = Drafts(rgb)  # (as a window shows the page filling in: the patches pasted in turn)
    res = pipe.process(Image.fromarray(rgb), translate=True, use_cache=False, events=drafts.event)
    seconds = time.monotonic() - t0
    final = np.asarray(res.image.convert("RGB"))
    erased = rec.erased if rec.erased is not None else final
    rows, page_codes = measure_page(rgb, erased, final, res.regions, rec, texts, got["layers"], got["kind"], drafts)
    h, w = rgb.shape[:2]
    record = {"item": item, "set": got["kind"], "size": [w, h], "factor": round(got["factor"], 4),
              "seconds": round(seconds, 1), "regions": rows, "page_codes": page_codes,
              "texts": len([t for t in texts if t.get("worded", True)]), "error": str(res.error or "")}
    if got["kind"] == "synthetic":
        record["truth"] = [{k: t[k] for k in ("id", "kind", "bubble", "text_box", "size", "chars", "case", "colour")
                            if k in t} for t in texts]
        record["bait"] = got["bait"]
    return record, {"orig": rgb, "erased": erased, "final": final, "regions": res.regions}


def crops(record: dict[str, Any], pics: dict[str, Any], out: Path, codes: set[str] | None = None, limit: int = 40) -> int:
    """Small pictures of the flagged regions (the original, after the erase, lettered) side by side, enlarged twice
    where small. For MADE-UP pages only (the caller's rule)."""
    import numpy as np
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    n = 0
    h, w = pics["orig"].shape[:2]
    stem = record["item"].replace(":", "-").replace("@", "-")
    for row in record["regions"]:
        wanted = [c for c in row["codes"] if codes is None or c in codes]
        if not wanted or n >= limit:
            continue
        b = row["box"]
        pad = max(10, int(0.25 * max(b[2] - b[0], b[3] - b[1])))
        x0, y0, x1, y1 = max(0, b[0] - pad), max(0, b[1] - pad), min(w, b[2] + pad), min(h, b[3] + pad)
        parts = [pics[k][y0:y1, x0:x1] for k in ("orig", "erased", "final")]
        gap = np.full((y1 - y0, 4, 3), (255, 0, 255), np.uint8)
        both = np.concatenate([parts[0], gap, parts[1], gap, parts[2]], axis=1)
        img = Image.fromarray(both)
        k = 2 if img.height < 260 else 1
        if k > 1:
            img = img.resize((img.width * k, img.height * k), Image.NEAREST)
        if img.width > 1200:
            img = img.resize((1200, max(1, round(img.height * 1200 / img.width))), Image.LANCZOS)
        img.save(out / f"{stem}-r{row['i']}-{'+'.join(wanted)}.png")
        n += 1
    return n


# ====================================================================== merging the shards
SOUND_STATES = (("found", "sound words found on the page (as read or set right)"),
                ("corrected", "... their reading set right: another reader's, or one kana changed"),
                ("as_drawn", "left as drawn: short kana on the page, each reader read another thing, no sound word"),
                ("lettered", "sound effects lettered"))


def sound_lines(records: Sequence[dict[str, Any]], keys: Sequence[tuple[str, str]]) -> list[str]:
    """The summary's table of sound words (`TextRegion.sound`, the kind "sfx"): how many were found, set right and
    left as drawn, and the codes on the sound effects lettered, per set and scale; [] for records of a version before
    them (no ``sound`` on a region)."""
    if not any("sound" in r for rec in records for r in rec["regions"]):
        return []
    counts: dict[tuple[str, str], Any] = {k: {"codes": {}} for k in keys}
    for rec in records:
        cell = counts[(rec["set"], rec["item"].rsplit("@", 1)[1])]
        for r in rec["regions"]:
            sound = r.get("sound", "")
            states = {"found": sound in ("read", "corrected"), "corrected": sound == "corrected",
                      "as_drawn": sound == "unsure", "lettered": bool(r.get("sfx")) and "ink_px" in r["m"]}
            for state, on in states.items():
                cell[state] = cell.get(state, 0) + int(on)
            if states["lettered"]:
                for c in set(r["codes"]):
                    cell["codes"][c] = cell["codes"].get(c, 0) + 1
    out = ["", "Sound words (`soundwords`): regions per set and scale.", "",
           "| sound words | " + " | ".join(f"{s} {sc}" for s, sc in keys) + " | what |",
           "|---|" + "---|" * len(keys) + "---|"]
    for state, what in SOUND_STATES:
        out.append(f"| {state} | " + " | ".join(str(counts[k].get(state, 0)) for k in keys) + f" | {what} |")
    for code in {**CODES, **PAGE_CODES}:
        if any(counts[k]["codes"].get(code) for k in keys):
            out.append(f"| on them: {code} | " + " | ".join(f"{counts[k]['codes'].get(code, 0)}/"
                                                          f"{counts[k].get('lettered', 0)}" for k in keys) + " | |")
    return out


def merge(paths: Sequence[Path], out: Path | None, summary: Path | None) -> int:
    records: list[dict[str, Any]] = []
    meta: list[dict[str, Any]] = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        records.extend(data.get("pages", []))
        meta.append({k: data.get(k) for k in ("shard", "of", "settings", "seconds", "failed")})
    table: dict[tuple[str, str, str], dict[str, Any]] = {}
    totals: dict[tuple[str, str], dict[str, int]] = {}
    for rec in records:
        scale = rec["item"].rsplit("@", 1)[1]
        key = (rec["set"], scale)
        tot = totals.setdefault(key, {"pages": 0, "regions": 0, "lettered": 0, "texts": 0, "seconds": 0, "turned": 0,
                                      "overrun": 0})
        tot["pages"] += 1
        tot["regions"] += len(rec["regions"])
        tot["lettered"] += sum(1 for r in rec["regions"] if "ink_px" in r["m"])
        for frame in ("turned", "overrun"):
            tot[frame] += sum(1 for r in rec["regions"] if r["m"].get("frame") == frame)
        tot["texts"] += rec.get("texts", 0)
        tot["seconds"] += rec.get("seconds", 0)
        for r in rec["regions"]:
            for c in set(r["codes"]):
                cell = table.setdefault((c, rec["set"], scale), {"regions": 0, "pages": set()})
                cell["regions"] += 1
                cell["pages"].add(rec["item"])
            for level in {CODE_LEVELS.get(c, "S3") for c in r["codes"] if c in CODES}:  # (a region once a level)
                cell = table.setdefault((level, rec["set"], scale), {"regions": 0, "pages": set()})
                cell["regions"] += 1
                cell["pages"].add(rec["item"])
        for pc in rec.get("page_codes", []):
            cell = table.setdefault((pc["code"], rec["set"], scale), {"regions": 0, "pages": set()})
            cell["regions"] += 1
            cell["pages"].add(rec["item"])
    keys = sorted(totals)
    lines = ["## Lettering audit", "",
             "Pages: " + ", ".join(f"{s} {sc} {totals[(s, sc)]['pages']} ({totals[(s, sc)]['regions']} regions, "
                                   f"{totals[(s, sc)]['lettered']} lettered, {totals[(s, sc)]['texts']} texts, "
                                   f"{totals[(s, sc)]['seconds'] / 60:.0f} min)" for s, sc in keys), "",
             "Each cell: regions flagged / regions lettered (texts for MISSED, OCR_DROPPED and T_LEFT), and pages "
             "affected. The codes go by their level on the owner's scale, the worst first; a level's own row counts "
             "the regions with any of its codes (each region once).", "",
             "| code | " + " | ".join(f"{s} {sc}" for s, sc in keys) + " | what |",
             "|---|" + "---|" * len(keys) + "---|"]
    allc = {**CODES, **PAGE_CODES}

    def cells_of(code: str) -> list[str]:
        cells = []
        for s, sc in keys:
            cell = table.get((code, s, sc))
            denom = totals[(s, sc)]["texts"] if code in PAGE_CODES else totals[(s, sc)]["lettered"]
            cells.append(f"{cell['regions']}/{denom}, {len(cell['pages'])} p" if cell else "-")
        return cells

    for level, words in LEVEL_WORDS.items():
        lines.append(f"| **{level}** | " + " | ".join(cells_of(level)) + f" | **{words}**: regions with any of its "
                     "codes |")
        for code in (c for c in allc if CODE_LEVELS.get(c, "S3") == level):
            cells = cells_of(code)
            if any(c != "-" for c in cells):
                lines.append(f"| {code} | " + " | ".join(cells) + f" | {allc[code]} |")
    for frame, what in (("turned", "lettered with the line turned 90 degrees (a count, not a fault)"),
                        ("overrun", "lettered over the bubble's outline (a count, not a fault)")):
        if any(totals[k].get(frame) for k in keys):
            lines.append(f"| ({frame}) | " + " | ".join(f"{totals[k].get(frame, 0)}/{totals[k]['lettered']}"
                                                         for k in keys) + f" | {what} |")
    lines += sound_lines(records, keys)
    failed =[f for m in meta for f in (m.get("failed") or [])]
    if failed:
        lines += ["", f"Items that failed: {len(failed)} ({', '.join(f['item'] for f in failed[:20])})"]
    text = "\n".join(lines) + "\n"
    if summary:
        summary.write_text(text, encoding="utf-8")
    print(text)
    if out:
        flat = {f"{c}|{s}|{sc}": {"regions": v["regions"], "pages": sorted(v["pages"])} for (c, s, sc), v in table.items()}
        out.write_text(json.dumps({"tool": "audit_render", "version": VERSION, "levels": CODE_LEVELS, "shards": meta,
                                   "totals": {f"{s}|{sc}": v for (s, sc), v in totals.items()}, "table": flat,
                                   "pages": records}, indent=1), encoding="utf-8")
    return 0


# ====================================================================== the command
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="process this shard's pages and write its numbers")
    run.add_argument("--shard", type=int, default=0)
    run.add_argument("--of", type=int, default=1)
    run.add_argument("--only", help="items by name, comma-separated (om:<title>:<page>, syn:<name>; "
                                    "@full, @small, @jpeg or @blur)")
    run.add_argument("--sets", default="openmantra,synthetic")
    run.add_argument("--scales", default="full,small,jpeg,blur")
    run.add_argument("--root", type=Path, default=None, help="the OpenMantra folder (tools/openmantra.py's default)")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--crops", type=Path, help="pictures of the made-up pages' flagged regions (scratch folder)")
    run.add_argument("--as-cpu", action="store_true", help="the defaults of a computer without a GPU")
    lst = sub.add_parser("list", help="the items and the shard each goes to")
    lst.add_argument("--of", type=int, default=16)
    lst.add_argument("--sets", default="openmantra,synthetic")
    lst.add_argument("--scales", default="full,small,jpeg,blur")
    lst.add_argument("--root", type=Path, default=None)
    mg = sub.add_parser("merge", help="join the shards' files into one table")
    mg.add_argument("files", nargs="+")
    mg.add_argument("--out", type=Path)
    mg.add_argument("--summary", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "merge":
        paths = [Path(p) for f in args.files for p in (glob.glob(f) or [f])]
        return merge(paths, args.out, args.summary)

    import openmantra

    root = args.root or openmantra.DEFAULT_ROOT
    sets = [s.strip() for s in args.sets.split(",") if s.strip()]
    scales = [s.strip() for s in args.scales.split(",") if s.strip()]
    if args.cmd == "list":
        everything = items(sets, scales, root)
        for k in range(args.of):
            print(k, len(shard_of(everything, k, args.of)))
        print("all", len(everything))
        return 0

    from taslation import netguard

    netguard.install()
    if args.only:
        mine = []
        for name in args.only.split(","):
            name = name.strip()
            mine.extend([name] if "@" in name else [f"{name}@{s}" for s in scales])
    else:
        mine = shard_of(items(sets, scales, root), args.shard, args.of)
    from taslation.config import Settings

    models_dir = Settings().models_dir
    t0 = time.monotonic()
    pipe, translator = make_pipeline(args.as_cpu)
    rec = Recorder(pipe)
    s = pipe.settings
    out: dict[str, Any] = {"tool": "audit_render", "version": VERSION, "shard": args.shard, "of": args.of,
                           "settings": {"detect_model": s.detect_model, "art_erase": s.art_erase,
                                        "erase_mode": s.erase_mode, "layout_model": pipe.layout is not None,
                                        "lama": pipe.art_eraser is not None, "small_height": SMALL_HEIGHT},
                           "thresholds": {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float))},
                           "codes": {**CODES, **PAGE_CODES}, "pages": [], "failed": []}
    print(f"{len(mine)} items; detect_model {s.detect_model}, art_erase {s.art_erase}, layout {pipe.layout is not None}, "
          f"LaMa {pipe.art_eraser is not None}", flush=True)
    for n, item in enumerate(mine, 1):
        try:
            record, pics = run_item(pipe, translator, rec, item, root, models_dir)
        except Exception as e:  # noqa: BLE001 - one page's failure is reported, the rest go on
            out["failed"].append({"item": item, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            print(f"  [{n}/{len(mine)}] {item}: FAILED {type(e).__name__}", flush=True)
            continue
        out["pages"].append(record)
        flagged = sum(1 for r in record["regions"] if r["codes"])
        print(f"  [{n}/{len(mine)}] {item}: {len(record['regions'])} regions, {flagged} flagged, "
              f"{record['seconds']} s", flush=True)
        if args.crops and record["set"] == "synthetic":
            crops(record, pics, args.crops)
        out["seconds"] = round(time.monotonic() - t0, 1)
        args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")  # (kept as it goes: a timeout keeps the rest)
    rec.close()
    out["seconds"] = round(time.monotonic() - t0, 1)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"done in {out['seconds']} s: {len(out['pages'])} pages, {len(out['failed'])} failed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
