"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: how often a bubble mixes lettering sizes, and where the big part is.

Japanese lettering often sets a shouted word or sentence of a bubble much larger than the rest of it. This tool runs
detection and the OCR over pages, as the app reads a page (`Pipeline.process` without translating; the layout model
where the inpainting would run, as the app's default on this computer, or ``--detect-model``'s), keeps for every
region read as Japanese text the character boxes the first reader (charspot) found, measures each character's size
(`char_sizes`) and finds the region's big span (`find_mix`): a run of characters, contiguous in reading order, set at
least ``--ratio`` times the region's base size. The default rule: a line's size is its pitch (the median distance
between neighbouring kana and kanji centres along it; a line without such a step measures nothing), the lines parted
in two groups at the widest step in size, mixed when the larger group's median is 1.25 times the smaller's or more,
the larger group is whole lines holding 2 full-size characters or more next to a base of 2 or more, and its glyphs
themselves are 1.15 times the base's or more (`cell_size`: a gap or a space between two characters is no size). It
reports, numbers only:

* the regions of two characters or more, how many mix sizes at 1.25, 1.5 and 2.0 and the distribution of the ratio;
* where the big span sits: whole lines (columns of vertical text, rows of horizontal) or part of one; at the start,
  the end or in the middle; one span or several; whether it is whole sentences by the source's punctuation; its
  length in characters; per series;
* with ``--sheets DIR``: picture sheets of random regions called mixed (the big span outlined in red, the base
  characters' boxes in green) and of random regions with two lines or more called not mixed, for a person to judge;
* with ``--translate`` (the dataset only): the pages translated as the app does (`Pipeline.process`, the default
  translator for ``--target`` with a fixed seed, page by page with the pages before as context, each series begun
  anew), and for every region the rule calls mixed and, unless ``--real-only``, one whole line of every region of two
  lines or more as a stand-in big span (`synthetic_span`, placed as the real ones are), the ways of locating the
  span in the translation (`locate_all`, `ask_case`): the span translated alone and found in the translation, the
  same sentences, a share baseline, the text sent in three lines (a joined request), the span in a marker
  (``--markers``); for each how often it answers, its requests' time and, for the requests that would replace the
  region's own, the translation's chrF against the dataset's beside the same request without a marker.
  ``--show N`` prints N random cases (source, span, translation, each method's answer) to the terminal for a person
  to judge; nothing of a text is written to a file (``--json`` holds the numbers);
* with ``--locate`` (the dataset only): the shipped locating step (`taslation.locate_large`) asked for the same
  cases, both of its steps for every case, so that its rule can be tuned on a person's verdicts (``--show``);
* with ``--shipped`` (the dataset or frames): the shipped step end to end, on the app's own path (`run_shipped`): per
  mixed region the step that answered, its requests and time, and whether its lettering came out at two sizes; with
  ``--sheets``, each region's crop lettered without and with the part found. Counts and pictures only.

The scan (``--scan FILE``) keeps the regions' boxes, the characters' boxes and their classes (`category`: a letter
for kanji, kana, small kana, punctuation, ...), never a character or a text, so that the rule can be tuned again
without the OCR; ``--translate`` reads the pages again for their text, which stays in memory.

    python tools/size_mix_eval.py --scan <scratch>/om.pkl --json <scratch>/om.json --sheets <scratch>/sheets
    python tools/size_mix_eval.py --frames "~/.taslation/dev-snapshots/<book>/screen_*.png" --scan <scratch>/fr.pkl
    python tools/size_mix_eval.py --translate --pages 12 --seed 1 --json <scratch>/tr-en.json
    python tools/size_mix_eval.py --translate --series <series> --pages 4 --limit 8 --show 8 --markers asterisk
    python tools/size_mix_eval.py --translate --target German --pages 4 --seed 1 --json <scratch>/tr-de.json

Page images and crops stay in memory but for the picture sheets (``--sheets``: a scratch folder, never the
repository). Nothing goes over the network but the local Ollama server with ``--translate`` (the socket guard is
installed first); the state folder should be a scratch one (``TASLATION_STATE_DIR``): nothing is written to it.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import pickle
import random
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402

import openmantra  # noqa: E402
from taslation import netguard  # noqa: E402

SCAN_VERSION = 1
Box = tuple[int, int, int, int]

# ------------------------------------------------------------------ the characters' classes
# Only full-size kana and kanji measure a size: the others are set smaller or thinner than the size of their line
# (small kana, punctuation, long-vowel marks and dashes, dots) or sideways (Latin letters and digits, tate-chu-yoko).
SMALL_KANA = set("ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿｧｨｩｪｫｬｭｮｯ")
LONG_MARKS = set("ー〜～―‐−-─━ｰ~")
SENTENCE_ENDS = set("。．！？!?‼⁉｡")
COMMAS = set("、，,､")
DOTS = set("…‥・.･:：")
BRACKETS = set("「」『』（）()【】〈〉《》［］[]〔〕\"'“”‘’")
FULL = "FKH"  # kanji, hiragana, katakana at full size
CLASSES = {
    "K": "kanji", "H": "hiragana", "T": "katakana", "s": "small kana", "L": "long mark", "E": "sentence end",
    "C": "comma", "D": "dots", "Q": "bracket", "A": "latin", "9": "digit", "O": "other",
}


def category(ch: str) -> str:
    """The class of a character (one letter of `CLASSES`); a combined !? glyph is a sentence end."""
    if not ch:
        return "O"
    if len(ch) > 1:
        return "E" if all(c in "!?！？" for c in ch) else category(ch[0])
    c = unicodedata.normalize("NFKC", ch) if ch not in SMALL_KANA else ch
    if ch in SMALL_KANA:
        return "s"
    if ch in LONG_MARKS or c in LONG_MARKS:
        return "L"
    if ch in SENTENCE_ENDS or c in SENTENCE_ENDS:
        return "E"
    if ch in COMMAS or c in COMMAS:
        return "C"
    if ch in DOTS or c in DOTS:
        return "D"
    if ch in BRACKETS or c in BRACKETS:
        return "Q"
    if c.isdigit():
        return "9"
    if c.isascii() and c.isalpha():
        return "A"
    o = ord(ch)
    if 0x3041 <= o <= 0x309F:
        return "H"
    if 0x30A1 <= o <= 0x30FF or 0xFF66 <= o <= 0xFF9F:
        return "T"
    if 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or ch in "々〆ヶ":
        return "K"
    return "O"


def is_full(cat: str) -> bool:
    return cat in ("K", "H", "T")


# ------------------------------------------------------------------ what a scan keeps
@dataclass
class Char:
    """One character as charspot found it: its box on the page, its box's sides as read (upright for a slanted
    region read turned), its class (never the character), the heat and the classifier's probability."""

    box: tuple[float, float, float, float]
    w: float
    h: float
    cat: str
    score: float
    sure: float
    ch: str = ""  # the character itself: memory only, blanked before a scan is written


@dataclass
class Region:
    page: str  # "<series>#<index>" or "frames#<n>"
    index: int  # among the page's regions read as Japanese
    kind: str
    from_model: bool
    tier: int
    angle: float
    bbox: Box
    text_box: Box
    glyph: float
    char_size: float
    kept_boxes: int  # how many character boxes the region itself keeps (`TextRegion.char_boxes`: model regions)
    n_text: int  # the length of the settled reading's text
    same_text: bool  # whether charspot's own characters spell the settled text (normalised)
    gold: int | None = None  # the gold box it matched (the dataset)
    chars: list[Char] = field(default_factory=list)
    text: str = ""  # the settled reading: memory only, blanked before a scan is written
    translation: str = ""  # its translation (``--translate``): memory only, blanked before a scan is written


# ------------------------------------------------------------------ pages
class Item:
    def __init__(self, series: str, index: int, opener: Any, gold: list[Box], margins: Any = None, page: Any = None):
        self.series, self.index, self.open, self.gold, self.margins, self.page = series, index, opener, gold, margins, page

    @property
    def key(self) -> str:
        return f"{self.series}#{self.index}"


def dataset_items(root: Path, series: Sequence[str] | None, pages: int, skip: int = 0) -> list[Item]:
    """The dataset's pages: of every series the first *pages* (0: all), the first *skip* of them left out."""
    found = openmantra.load(root, series)
    out = []
    for name, group in openmantra.by_series(found).items():
        for page in group[skip: pages or None]:
            out.append(Item(name, page.index, page.open, [b.box for b in page.bubbles], page=page))
    return out


def frame_items(pattern: str) -> list[Item]:
    from PIL import Image

    files = sorted(glob.glob(str(Path(pattern).expanduser())))
    out = []
    for n, path in enumerate(files, 1):
        manifest = Path(path).parent / "manifest.json"
        margins = None
        if manifest.is_file():
            margins = json.loads(manifest.read_text(encoding="utf-8")).get("margins")

        def opener(path: str = path) -> Any:
            with Image.open(path) as im:
                return im.convert("RGB")

        out.append(Item("frames", n, opener, [], margins))
    return out


# ------------------------------------------------------------------ the scan: detection and OCR as the app does them
class Watch:
    """`Pipeline._read` and `Pipeline._settle` watched on one pipeline: per region, the readings it was given (the box
    read, the prepared pixels, the reading), so that the reading its text came from is known afterwards."""

    def __init__(self, pipe: Any):
        self.pipe = pipe
        self.calls: dict[int, list[tuple[str, Box, Any, Any]]] = {}
        read, settle = pipe._read, pipe._settle

        def watched_read(rgb, r, box, view=None):
            got = read(rgb, r, box, view)
            self.calls.setdefault(id(r), []).append(("read", tuple(box), view, got))
            return got

        def watched_settle(rgb, r, box, reading, view=None):
            got = settle(rgb, r, box, reading, view)
            self.calls.setdefault(id(r), []).append(("settle", tuple(box), view, got))
            return got

        pipe._read, pipe._settle = watched_read, watched_settle

    def final(self, r: Any) -> tuple[Box, Any, Any] | None:
        """(box, prepared pixels, reading) of the reading *r*'s text was taken from; None when none is known."""
        calls = self.calls.get(id(r), [])
        settled = [c for c in calls if c[0] == "settle"]
        if settled:
            _k, box, view, reading = settled[-1]
            return box, view, reading
        for _k, box, view, reading in reversed(calls):
            if reading.text == r.source_text:
                return box, view, reading
        return None


def _norm(text: str) -> str:
    from taslation.ocr.readers import normal

    return normal(text)


def scan_page(pipe: Any, watch: Watch, item: Item, image: Any, translate: bool = False) -> tuple[list[Region], int]:
    """The regions *image* reads as Japanese text, with their characters (`Region`), and how many regions the page
    had before the OCR's judgement; with *translate*, the page translated as the app translates it (with the pages
    before as context) and each region's translation kept (`Region.translation`)."""
    from openmantra_eval import match
    from taslation.ocr.charspot import written

    if item.margins is not None:
        pipe.settings.margins = tuple(item.margins)
    watch.calls.clear()
    res = pipe.process(image, translate=translate, use_cache=False)
    rgb = np.asarray(image.convert("RGB"))
    found = [r for r in res.regions if r.status in ("untranslated", "translated") and r.source_text]
    pairs = {ri: gi for gi, ri, _v in match(item.gold, [(r.bbox, r.text_box) for r in found])} if item.gold else {}
    out = []
    for i, r in enumerate(found):
        got = watch.final(r)
        chars: list[Char] = []
        same = False
        if got is not None:
            box, view, reading = got
            if reading.chars:
                boxes, _quads = pipe._char_boxes(rgb, r, box, reading.chars, view)
                for c, b in zip(reading.chars, boxes):
                    chars.append(Char(tuple(float(v) for v in b), float(c.box[2] - c.box[0]),
                                      float(c.box[3] - c.box[1]), category(c.char), float(c.score), float(c.sure),
                                      c.char))
                same = _norm(written("".join(c.char for c in reading.chars))) == _norm(r.source_text)
        out.append(Region(item.key, i, r.kind, bool(r.from_model), int(r.tier), float(r.angle), tuple(r.bbox),
                          tuple(r.text_box), float(r.glyph), float(r.char_size), len(r.char_boxes),
                          len(r.source_text), same, pairs.get(i), chars, r.source_text,
                          r.translated_text if r.status == "translated" else ""))
    return out, len(res.regions)


def make_pipeline(detect_model: str | None, with_ocr: bool = True, target: str | None = None,
                  seed: int | None = None) -> Any:
    """A pipeline as the app's default makes it on this computer, without a cache; with *target*, with the default
    translator for that language (`make_translator`, the sampling *seed* fixed)."""
    from taslation.config import Settings
    from taslation.ocr import Readers
    from taslation.pipeline import Pipeline
    from taslation.render import artwork

    s = Settings()
    if detect_model:
        s.detect_model = detect_model
    elif s.detect_model == "auto" and artwork.available(s.models_dir, s.art_erase):
        s.detect_model = "on"  # the app's default here: the layout model, which runs where the inpainting does
    s.art_erase = "off"  # (nothing is erased here: the paper fill, and LaMa is never loaded)
    translator = None
    if target:
        from taslation.translate.models import make_translator

        s.target_language = target
        s.validate()
        translator = make_translator(s, seed=seed)
    s.validate()
    ocr = Readers(s.models_dir, s.ocr_threads) if with_ocr else None
    return Pipeline(s, ocr=ocr, translator=translator, cache=None)


def scan(items: list[Item], detect_model: str | None, log: Any = print) -> dict[str, Any]:
    pipe = make_pipeline(detect_model)
    watch = Watch(pipe)
    pages: dict[str, list[Region]] = {}
    candidates = 0
    t0 = time.monotonic()
    for n, item in enumerate(items, 1):
        image = item.open()
        regions, cands = scan_page(pipe, watch, item, image)
        candidates += cands
        pages[item.key] = regions
        del image
        if n % 10 == 0 or n == len(items):
            log(f"  scanned {n}/{len(items)} pages, {sum(len(v) for v in pages.values())} regions "
                f"[{time.monotonic() - t0:.0f} s]")
    return {"detect_model": pipe.settings.detect_model, "pages": pages, "candidates": candidates,
            "seconds": round(time.monotonic() - t0, 1)}


def save_scan(path: Path, key: dict[str, Any], data: dict[str, Any]) -> None:
    """*data* kept in *path* as plain dicts, every region's text blanked (checked: no CJK character in it)."""
    pages = {}
    for page, regions in data["pages"].items():
        rows = []
        for r in regions:
            row = asdict(r)
            row["text"] = row["translation"] = ""
            for c in row["chars"]:
                c["ch"] = ""
            rows.append(row)
        pages[page] = rows
    payload = {"key": key, **{k: v for k, v in data.items() if k != "pages"}, "pages": pages}
    if any(ord(ch) >= 0x3000 for ch in _strings(payload)):
        raise SystemExit("the scan would hold Japanese text: not written")
    path.write_bytes(pickle.dumps(payload))


def read_scan(path: Path) -> dict[str, Any]:
    held = pickle.loads(path.read_bytes())
    held["pages"] = {page: [Region(**{**row, "chars": [Char(**c) for c in row["chars"]]}) for row in rows]
                     for page, rows in held["pages"].items()}
    return held


def _strings(obj: Any, seen: set[int] | None = None) -> str:
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return ""
    seen.add(id(obj))
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return "".join(_strings(k, seen) + _strings(v, seen) for k, v in obj.items())
    if isinstance(obj, (list, tuple, set)):
        return "".join(_strings(v, seen) for v in obj)
    if hasattr(obj, "__dict__"):
        return "".join(_strings(v, seen) for v in vars(obj).values())
    return ""


# ------------------------------------------------------------------ sizes, lines and the big span
@dataclass
class Rule:
    """The rule that calls a region mixed (see `find_mix`)."""

    ratio: float = 1.25  # the big span's size at least this many times the base size
    min_span: int = 2  # full-size characters in a big span at least
    smooth: bool = True  # a character's size: the median of it and its neighbours on its line (1 = alone)
    by_line: bool = True  # a line's size for every character on it (the line's median), no change within a line
    min_sure: float = 0.0  # characters the classifier is less sure of than this measure nothing
    measure: str = "pitch"  # "pitch": the distance between neighbours' centres (`pitch_sizes`); "box": own boxes
    min_base: int = 2  # full-size characters in the small group (the base) at least, contiguous in reading order
    need_steps: bool = True  # (pitch) a line without a step measures nothing (no size from its boxes)
    confirm: float = 1.15  # the span's own boxes (`cell_size`) at least this many times the base's too (0: unchecked)


@dataclass
class Mix:
    vertical: bool
    lines: list[list[int]]  # character indices per line (column of vertical text, row of horizontal), reading order
    sizes: list[float | None]  # per character the size measured for it (None: a character that measures none)
    base: float  # the size most characters have (the median of the small group)
    big: float  # the median size of the big group (= base when not mixed)
    spans: list[tuple[int, int]]  # the big spans as character ranges [a, b) in reading order

    @property
    def ratio(self) -> float:
        return self.big / self.base if self.base else 1.0

    @property
    def mixed(self) -> bool:
        return bool(self.spans)


def _centre(c: Char) -> tuple[float, float]:
    return (c.box[0] + c.box[2]) / 2.0, (c.box[1] + c.box[3]) / 2.0


def own_size(c: Char) -> float:
    """A character's own size: the longer side of its box as read."""
    return max(c.w, c.h)


def direction(chars: Sequence[Char]) -> bool:
    """Whether the characters run in columns (vertical text): more steps from one character to the next go down than
    go right."""
    down = right = 0
    for a, b in zip(chars, chars[1:]):
        (ax, ay), (bx, by) = _centre(a), _centre(b)
        dx, dy = bx - ax, by - ay
        if abs(dy) > abs(dx):
            down += dy > 0
        else:
            right += dx > 0
    return down >= right


def split_lines(chars: Sequence[Char], vertical: bool) -> list[list[int]]:
    """The lines of *chars* in reading order: a new line where the next character does not follow on this one (in a
    column: below it and not far aside; in a row: right of it and not far up or down)."""
    if not chars:
        return []
    lines = [[0]]
    for i in range(1, len(chars)):
        a, b = chars[i - 1], chars[i]
        (ax, ay), (bx, by) = _centre(a), _centre(b)
        s = max(own_size(a), own_size(b), 1.0)
        along, across = (by - ay, bx - ax) if vertical else (bx - ax, by - ay)
        if along > -0.3 * s and abs(across) < 0.6 * s:
            lines[-1].append(i)
        else:
            lines.append([i])
    return lines


CELL_CLASSES = ("K", "H", "T", "s")  # the characters set one to a cell of the size: kana (small ones too) and kanji
PITCH_LOW, PITCH_HIGH = 0.7, 1.8  # a step between two characters counts as a cell this many times their larger box


def steps(chars: Sequence[Char], line: Sequence[int], vertical: bool) -> list[tuple[int, int, float]]:
    """The steps between neighbours on a *line* that measure the size: (i, j, the distance of their centres along
    the line) for two cell characters (`CELL_CLASSES`) one after the other whose distance is a cell (`PITCH_LOW` to
    `PITCH_HIGH` times the larger of their boxes; not a gap, not two lines taken for one)."""
    out = []
    for i, j in zip(line, line[1:]):
        a, b = chars[i], chars[j]
        if a.cat not in CELL_CLASSES or b.cat not in CELL_CLASSES:
            continue
        (ax, ay), (bx, by) = _centre(a), _centre(b)
        d = abs(by - ay) if vertical else abs(bx - ax)
        big = max(own_size(a), own_size(b), 1.0)
        if PITCH_LOW * big <= d <= PITCH_HIGH * big:
            out.append((i, j, d))
    return out


def pitch_sizes(chars: Sequence[Char], lines: Sequence[Sequence[int]], vertical: bool,
                rule: Rule) -> list[float | None]:
    """The size of each full-size character as the pitch of its line: lettering is set one character to a cell of the
    font size, whatever the glyph's own shape (a kana's ink is smaller than a kanji's, a small kana's smaller still),
    so the distance from a character's centre to its neighbours' is the size it was set at. Each full-size character
    takes the median of the steps (`steps`) it is part of, and its line's next ones (*rule.smooth*: a window of a step
    on either side), or its line's median (*rule.by_line*); one on a line without a step takes its own box times the
    region's median of step over box (what the pitch is of the box there)."""
    out: list[float | None] = [None] * len(chars)
    over: list[float] = []  # step / box, to size the characters of lines without a step
    per_line = []
    for line in lines:
        st = steps(chars, line, vertical)
        per_line.append(st)
        for i, j, d in st:
            for k in (i, j):
                if is_full(chars[k].cat):
                    over.append(d / max(1.0, own_size(chars[k])))
    k_box = statistics.median(over) if over else 1.0
    for line, st in zip(lines, per_line):
        full = [i for i in line if is_full(chars[i].cat) and chars[i].sure >= rule.min_sure]
        if not full:
            continue
        if not st:
            if not rule.need_steps:
                for i in full:
                    out[i] = own_size(chars[i]) * k_box
            continue
        if rule.by_line:
            m = statistics.median(d for _i, _j, d in st)
            for i in full:
                out[i] = m
            continue
        at = {}
        for n, (i, j, _d) in enumerate(st):
            at.setdefault(i, []).append(n)
            at.setdefault(j, []).append(n)
        for i in full:
            if i in at:
                ns = at[i]
                lo, hi = (min(ns) - 1, max(ns) + 1) if rule.smooth else (min(ns), max(ns))
                window = [st[n][2] for n in range(max(0, lo), min(len(st), hi + 1))]
                out[i] = statistics.median(window)
            else:  # a full-size character next to punctuation only: the nearest step on its line
                pos = line.index(i)
                near = min(st, key=lambda s: abs(line.index(s[0]) - pos))
                out[i] = near[2]
    return out


# A full-size character's box (its longer side) over the cell it is set in (the pitch of its line), the medians over
# the dataset's regions of four characters or more (1,151 with hiragana, 759 with kanji, 181 with katakana): a kana's
# ink is smaller than a kanji's at the same size.
CELL_SHARE = {"K": 0.943, "H": 0.870, "T": 0.843, "s": 0.692}


def cell_size(c: Char) -> float:
    """The size a character was set at as its own box tells it: its longer side over its class's `CELL_SHARE`."""
    return own_size(c) / CELL_SHARE.get(c.cat, 1.0)


def char_sizes(chars: Sequence[Char], lines: Sequence[Sequence[int]], rule: Rule,
               vertical: bool = True) -> list[float | None]:
    """The size measured for each character (*rule.measure* "pitch": `pitch_sizes`; "cell": `cell_size`; "box": the
    longer side of its box), full-size kana and kanji only (`is_full`), each the median of its own and its full-size
    neighbours' on its line (*rule.smooth*), or its line's median (*rule.by_line*)."""
    if rule.measure == "pitch":
        return pitch_sizes(chars, lines, vertical, rule)
    own = cell_size if rule.measure == "cell" else own_size
    out: list[float | None] = [None] * len(chars)
    for line in lines:
        full = [i for i in line if is_full(chars[i].cat) and chars[i].sure >= rule.min_sure]
        if not full:
            continue
        if rule.by_line:
            m = statistics.median(own(chars[i]) for i in full)
            for i in full:
                out[i] = m
            continue
        for k, i in enumerate(full):
            if rule.smooth and len(full) >= 3:
                window = full[max(0, k - 1): k + 2]
                out[i] = statistics.median(own(chars[j]) for j in window)
            else:
                out[i] = own(chars[i])
    return out


def two_groups(values: Sequence[float]) -> tuple[list[float], list[float]]:
    """*values* parted in two by the widest step between neighbours in log size (the small group first)."""
    v = sorted(values)
    if len(v) < 2:
        return list(v), []
    steps = [math.log(v[i + 1] / max(1e-6, v[i])) for i in range(len(v) - 1)]
    k = max(range(len(steps)), key=lambda i: steps[i])
    return v[: k + 1], v[k + 1:]


def _runs(sizes: Sequence[float | None], keep: Any, least: int) -> list[tuple[int, int]]:
    """The runs [a, b) of characters, contiguous in reading order (those measuring nothing skipped), whose measured
    sizes *keep* says yes to, of at least *least* measured characters."""
    out: list[tuple[int, int]] = []
    start = last = None
    count = 0
    for i, s in enumerate(sizes):
        if s is None:
            continue
        if keep(s):
            if start is None:
                start, count = i, 0
            last, count = i, count + 1
        else:
            if start is not None and count >= least:
                out.append((start, last + 1))
            start = None
    if start is not None and count >= least:
        out.append((start, last + 1))
    return out


def find_mix(region: Region, rule: Rule) -> Mix:
    """Whether *region* mixes lettering sizes, and where its big spans are: the measured sizes (`char_sizes`) parted
    in a small and a big group (`two_groups`); mixed when the big group's median is at least *rule.ratio* times the
    small group's (the base) and a run of the big group's characters, contiguous in reading order, holds at least
    *rule.min_span* of them. A span takes in the characters that measure nothing inside it (punctuation, small kana)
    and those right after it of a box as large as the span's (a large "!!")."""
    chars = region.chars
    vertical = direction(chars)
    lines = split_lines(chars, vertical)
    sizes = char_sizes(chars, lines, rule, vertical)
    measured = [s for s in sizes if s is not None]
    if not measured:
        return Mix(vertical, lines, sizes, 0.0, 0.0, [])
    same = statistics.median(measured)
    small, big = two_groups(measured)
    if not big:
        return Mix(vertical, lines, sizes, same, same, [])
    base = statistics.median(small)
    cut = min(big)
    spans = _runs(sizes, lambda s: s >= cut, rule.min_span)
    base_runs = _runs(sizes, lambda s: s < cut, rule.min_base)
    if not spans or not base_runs or statistics.median(big) < rule.ratio * base:
        return Mix(vertical, lines, sizes, same, same, [])
    if rule.confirm:  # the glyphs themselves larger too, not only set farther apart (a space, a gap)
        inside = {i for a, b in spans for i in range(a, b)}
        own_big = [cell_size(chars[i]) for i in inside if sizes[i] is not None]
        own_base = [cell_size(chars[i]) for i, s in enumerate(sizes) if s is not None and i not in inside]
        if not own_big or not own_base or statistics.median(own_big) < rule.confirm * statistics.median(own_base):
            return Mix(vertical, lines, sizes, same, same, [])
    grown = []
    line_of = {i: k for k, line in enumerate(lines) for i in line}
    for a, b in spans:  # the punctuation that ends a span's last line ("!!", "...") belongs to it
        nxt = next((i for i in range(b, len(chars)) if sizes[i] is not None), len(chars))
        if nxt == len(chars) or line_of[nxt] != line_of[b - 1]:
            while b < nxt and line_of[b] == line_of[b - 1]:
                b += 1
        grown.append((a, b))
    if not grown:
        return Mix(vertical, lines, sizes, statistics.median(measured), statistics.median(measured), [])
    return Mix(vertical, lines, sizes, base, statistics.median(big), grown)


# ------------------------------------------------------------------ where the big span sits
def _first_full(region: Region) -> int:
    return next((i for i, c in enumerate(region.chars) if is_full(c.cat)), 0)


def _last_full(region: Region) -> int:
    return next((i for i in range(len(region.chars) - 1, -1, -1) if is_full(region.chars[i].cat)), len(region.chars) - 1)


def sentence_edge(region: Region, at: int) -> bool:
    """Whether a sentence ends right before character *at* by the source's punctuation: no full-size character before
    it, or a sentence end (。！？) between the last full-size character before it and it."""
    chars = region.chars
    k = at - 1
    while k >= 0 and not is_full(chars[k].cat):
        if chars[k].cat == "E":
            return True
        k -= 1
    if k < 0:
        return True
    # the span may hold the punctuation that ends it: a sentence end inside it, after its last full character
    return False


def sentence_end(region: Region, end: int) -> bool:
    """Whether a sentence ends at the end of the span [.., end): a sentence end among the characters from its last
    full-size one up to the next full-size character, or no full-size character after it."""
    chars = region.chars
    k = end - 1
    while k >= 0 and not is_full(chars[k].cat):
        k -= 1
    j = k + 1
    while j < len(chars) and not is_full(chars[j].cat):
        if chars[j].cat == "E":
            return True
        j += 1
    return j >= len(chars)


def describe(region: Region, mix: Mix) -> dict[str, Any]:
    """Where the big spans of a mixed region sit (`Mix`), as counts and classes, no text."""
    chars = region.chars
    line_of = {i: k for k, line in enumerate(mix.lines) for i in line}
    first, last = _first_full(region), _last_full(region)
    spans = []
    for a, b in mix.spans:
        full_in = [i for i in range(a, b) if is_full(chars[i].cat)]
        lines = sorted({line_of[i] for i in full_in})
        whole_lines = all(
            all(i in range(a, b) or not is_full(chars[i].cat) for i in mix.lines[k]) for k in lines)
        at_start = a <= first
        at_end = max(full_in) >= last
        where = "all" if at_start and at_end else "start" if at_start else "end" if at_end else "middle"
        line_start = all(not is_full(chars[i].cat) for i in mix.lines[lines[0]] if i < a)
        line_end = all(not is_full(chars[i].cat) for i in mix.lines[lines[-1]] if i >= b)
        spans.append({"chars": b - a, "full": len(full_in), "lines": len(lines), "whole_lines": whole_lines,
                      "line_edges": line_start and line_end, "where": where,
                      "sentences": sentence_edge(region, a) and sentence_end(region, b)})
    measured = sum(1 for s in mix.sizes if s is not None)
    big = sum(1 for a, b in mix.spans for i in range(a, b) if mix.sizes[i] is not None)
    return {"spans": spans, "n_spans": len(spans), "ratio": round(mix.ratio, 3), "base": round(mix.base, 1),
            "big_majority": big > measured - big, "lines": len(mix.lines), "vertical": mix.vertical}


# ------------------------------------------------------------------ the report
RATIOS = (1.25, 1.5, 2.0)
BINS = (1.1, 1.25, 1.5, 2.0, 3.0)


def _bin(r: float) -> str:
    lo = 0.0
    for edge in BINS:
        if r < edge:
            return f"{lo:.2f}-{edge:.2f}" if lo else f"<{edge:.2f}"
        lo = edge
    return f">={BINS[-1]:.2f}"


def statistics_of(regions: Sequence[Region], rule: Rule) -> dict[str, Any]:
    """The counts of the report over *regions* (those of two characters or more), for *rule* and the other ratios."""
    pool = [r for r in regions if len(r.chars) >= 2]
    out: dict[str, Any] = {"regions": len(regions), "two_or_more": len(pool),
                           "two_lines_or_more": 0, "mixed": {}, "ratio_bins": Counter(), "where": Counter(),
                           "n_spans": Counter(), "whole_lines": 0, "part_of_line": 0, "line_edges": 0,
                           "sentences": 0, "span_chars": [], "span_full": [], "spans": 0, "big_majority": 0,
                           "mixed_regions": 0, "kinds": Counter(), "from_model": Counter()}
    for ratio in RATIOS:
        r2 = Rule(**{**asdict(rule), "ratio": ratio})
        out["mixed"][str(ratio)] = sum(1 for r in pool if find_mix(r, r2).mixed)
    for r in pool:
        mix = find_mix(r, rule)
        if len(mix.lines) >= 2:
            out["two_lines_or_more"] += 1
        loose = find_mix(r, Rule(**{**asdict(rule), "ratio": 1.0, "confirm": 0.0}))
        out["ratio_bins"][_bin(loose.ratio if loose.mixed else 1.0)] += 1
        if not mix.mixed:
            continue
        d = describe(r, mix)
        out["mixed_regions"] += 1
        out["kinds"][r.kind] += 1
        out["from_model"][str(r.from_model)] += 1
        out["n_spans"][min(3, d["n_spans"])] += 1
        out["big_majority"] += d["big_majority"]
        for s in d["spans"]:
            out["spans"] += 1
            out["where"][s["where"]] += 1
            out["whole_lines" if s["whole_lines"] else "part_of_line"] += 1
            out["line_edges"] += s["line_edges"]
            out["sentences"] += s["sentences"]
            out["span_chars"].append(s["chars"])
            out["span_full"].append(s["full"])
    sc = out.pop("span_chars")
    sf = out.pop("span_full")
    out["span_length"] = {"median_chars": statistics.median(sc) if sc else 0,
                          "median_full": statistics.median(sf) if sf else 0,
                          "full_hist": dict(sorted(Counter(min(12, n) for n in sf).items()))}
    for k in ("ratio_bins", "where", "n_spans", "kinds", "from_model"):
        out[k] = dict(sorted(out[k].items(), key=lambda kv: str(kv[0])))
    return out


def print_report(name: str, stats: dict[str, Any]) -> None:
    n = stats["two_or_more"]
    pct = lambda k: f"{100.0 * k / n:.1f} %" if n else "-"  # noqa: E731
    mixed = ", ".join(f">= {k}: {v} ({pct(v)})" for k, v in stats["mixed"].items())
    print(f"{name}: {stats['regions']} regions, {n} of two characters or more ({stats['two_lines_or_more']} of two "
          f"lines or more); mixed {mixed}")
    m = stats["mixed_regions"]
    if not m:
        return
    print(f"  ratio (big/base of the widest step, regions of two characters or more): {stats['ratio_bins']}")
    print(f"  {m} mixed regions by the rule: spans per region {stats['n_spans']}; big part the majority in "
          f"{stats['big_majority']}; kinds {stats['kinds']}; from the layout model {stats['from_model']}")
    s = stats["spans"]
    print(f"  {s} spans: where {stats['where']}; whole lines {stats['whole_lines']}, part of a line "
          f"{stats['part_of_line']}; starts and ends at line edges {stats['line_edges']}; whole sentences by the "
          f"punctuation {stats['sentences']}; length {stats['span_length']}")


# ------------------------------------------------------------------ the big span in the source text
def text_range(region: Region, a: int, b: int) -> tuple[int, int]:
    """The characters [a, b) of charspot's reading as a range of the region's settled text (`Region.text`): each
    character written as the OCR writes its text (`charspot.written`), aligned to the text (`difflib`), so that a
    reading the other readers changed a little still maps."""
    import difflib

    from taslation.ocr.charspot import written

    pieces = [written(c.ch) if c.ch.strip() else c.ch for c in region.chars]
    starts = [0]
    for p in pieces:
        starts.append(starts[-1] + len(p))
    whole = "".join(pieces)
    text = region.text
    to_text = [0] * (len(whole) + 1)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, whole, text, autojunk=False).get_opcodes():
        for k in range(i1, i2 + 1):
            if tag == "equal":
                to_text[k] = j1 + (k - i1)
            elif tag == "replace":
                to_text[k] = j1 + round((k - i1) * (j2 - j1) / max(1, i2 - i1))
            elif tag == "delete":
                to_text[k] = j1
            else:  # insert: no character of charspot's here
                to_text[k] = j2 if k == i2 else j1
    to_text[len(whole)] = len(text)
    return to_text[starts[a]], to_text[starts[b]]


SOURCE_ENDS = re.compile(r"[。．！？!?‼⁉]+[」』）)]*")
TARGET_ENDS = re.compile(r"(?<!\.\.)(?<!…)[.!?¡¿。！？]+[\"'”’»)\]]*(?=\s|$)")


def sentences(text: str, ends: re.Pattern[str]) -> list[tuple[int, int]]:
    """The sentences of *text* as ranges: up to each run of sentence-ending punctuation (*ends*), the rest last."""
    out = []
    start = 0
    for m in ends.finditer(text):
        if m.end() > start and text[start:m.end()].strip():
            out.append((start, m.end()))
        start = m.end()
    if text[start:].strip():
        out.append((start, len(text)))
    return out


# ------------------------------------------------------------------ ways of locating it in the translation
def _normalised(text: str) -> tuple[str, list[int]]:
    """*text* in lower case, its punctuation and marks gone and its spaces made one, with each kept character's
    index in *text*."""
    out, at = [], []
    space = True
    for i, ch in enumerate(text):
        if ch.isalnum() or ch == "'" or ch == "’":
            out.append("'" if ch == "’" else ch.lower())
            at.append(i)
            space = False
        elif not space:
            out.append(" ")
            at.append(i)
            space = True
    while out and out[-1] == " ":
        out.pop()
        at.pop()
    return "".join(out), at


def locate_exact(whole: str, part: str) -> tuple[int, int] | None:
    """*part* found in *whole* once, after normalising both (case, punctuation, spaces), at word edges; the range in
    *whole* (None: not found, or found twice)."""
    w, at = _normalised(whole)
    p, _ = _normalised(part)
    if not p or not w:
        return None
    hits = [m.start() for m in re.finditer(r"(?<![a-z0-9'])" + re.escape(p) + r"(?![a-z0-9'])", w)]
    if len(hits) != 1:
        return None
    s = hits[0]
    return at[s], at[s + len(p) - 1] + 1


def _words(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0).lower().replace("’", "'"), m.start(), m.end()) for m in re.finditer(r"[\w'’]+", text)]


def locate_loose(whole: str, part: str, least: float = 0.8) -> tuple[int, int] | None:
    """*part*'s words in *whole* in order with small differences: the run of *whole*'s words (one more or fewer)
    most like them (`difflib` ratio of the words joined, at least *least*), and no other run as like them; the range
    in *whole*."""
    import difflib

    ws, ps = _words(whole), _words(part)
    if not ws or not ps:
        return None
    target = " ".join(p for p, _a, _b in ps)
    scored = []
    for n in range(max(1, len(ps) - 1), len(ps) + 2):
        for s in range(0, len(ws) - n + 1):
            cand = " ".join(w for w, _a, _b in ws[s:s + n])
            scored.append((difflib.SequenceMatcher(None, cand, target).ratio(), s, n))
    if not scored:
        return None
    scored.sort(reverse=True)
    best, s, n = scored[0]
    if best < least:
        return None
    for other, s2, n2 in scored[1:]:  # a second run as like it, elsewhere: no answer
        if other < best - 0.05:
            break
        if s2 + n2 <= s or s2 >= s + n:
            return None
    return ws[s][1], ws[s + n - 1][2]


def locate_sentences(source: str, span: tuple[int, int], whole: str) -> tuple[int, int] | None:
    """When the span is whole sentences of the source (by its punctuation) and the translation has as many sentences
    as the source: the same sentences of the translation."""
    src = sentences(source, SOURCE_ENDS)
    dst = sentences(whole, TARGET_ENDS)
    if len(src) < 2 or len(src) != len(dst):
        return None
    a, b = span
    # the span's edges are sentences' edges when only spaces, opening marks (before) or closing ones (after) stand
    # between them
    first = next((k for k, (s, _e) in enumerate(src) if s <= a and source[s:a].strip(" 　「『（(") == ""), None)
    last = next((k for k, (_s, e) in enumerate(src) if e >= b and source[b:e].strip("。．！？!?‼⁉」』）)…・. 　") == ""),
                None)
    if first is None or last is None or last < first or (first == 0 and last == len(src) - 1):
        return None
    return dst[first][0], dst[last][1]


def locate_share(source: str, span: tuple[int, int], whole: str) -> tuple[int, int] | None:
    """A baseline that always answers: the span's share of the source's characters, at its place, as the same share
    of the translation's words (snapped to whole words)."""
    ws = _words(whole)
    n = max(1, len(source))
    if not ws:
        return None
    a = round(span[0] / n * len(ws))
    b = max(a + 1, round(span[1] / n * len(ws)))
    b = min(b, len(ws))
    return ws[min(a, len(ws) - 1)][1], ws[b - 1][2]


MARKERS = {"asterisk": ("*", "*"), "lenticular": ("【", "】"), "tag": ("<b>", "</b>"), "angle": ("《", "》")}


def _marker_forms(marker: tuple[str, str]) -> list[tuple[str, str]]:
    """The marker and the forms a model may write it in instead (half-width brackets, guillemets, capitals)."""
    more = {("【", "】"): [("[", "]")], ("《", "》"): [("<<", ">>"), ("«", "»")], ("<b>", "</b>"): [("<B>", "</B>")]}
    return [marker] + more.get(marker, [])


def marked_part(answer: str, marker: tuple[str, str]) -> tuple[str, tuple[int, int] | None]:
    """The answer to a marked source with the marker taken out, and where the marked part is in it (None: the marker
    did not come back as one pair around something)."""
    for o, c in _marker_forms(marker):
        if o != c:
            ok = answer.count(o) == 1 and answer.count(c) == 1 and answer.index(o) < answer.index(c)
        else:
            ok = answer.count(o) == 2
        if not ok:
            continue
        i = answer.index(o)
        j = answer.index(c, i + len(o))
        before, inner, after = answer[:i], answer[i + len(o):j], answer[j + len(c):]
        # a marker written in place of a space ("【Hey】you") leaves one
        if before and inner and before[-1].isalnum() and inner[0].isalnum():
            before += " "
        if after and inner and inner[-1].isalnum() and after[0].isalnum():
            after = " " + after
        plain = before + inner + after
        if not inner.strip():
            return plain, None
        lead = len(inner) - len(inner.lstrip())
        return plain, (len(before) + lead, len(before) + len(inner.rstrip()))
    plain = answer
    for o, c in _marker_forms(marker):
        plain = plain.replace(o, "").replace(c, "")
    return plain, None


def marked_source(text: str, at: tuple[int, int], marker: tuple[str, str]) -> str:
    """The Japanese *text* with the span *at* in the marker."""
    a, b = at
    return text[:a] + marker[0] + text[a:b] + marker[1] + text[b:]


# ------------------------------------------------------------------ the translation test
@dataclass
class Case:
    """One big span to locate in a region's translation."""

    region: Region
    span: tuple[int, int]  # characters [a, b) of the region's (`Region.chars`)
    real: bool  # found by the rule (`find_mix`); else a whole line chosen where the real spans sit (`synthetic_span`)
    at: tuple[int, int]  # the span in the region's text (`text_range`)
    gold: str  # the dataset's translation of the bubble the region matched ("" none)
    history: list[tuple[str, str]]  # the earlier pairs the region's request started from
    answers: dict[str, str] = field(default_factory=dict)  # request -> its answer
    ms: dict[str, float] = field(default_factory=dict)  # request -> its time
    found: dict[str, tuple[str, tuple[int, int] | None]] = field(default_factory=dict)  # method -> (text, range)


# where the real big spans of the frames sit (10 by the rule: 7 at the end, 2 in the middle, 1 at the start), each one
# whole line of 2 to 6 full-size characters, never the larger part of the region
WHERE_WEIGHTS = (("end", 7), ("middle", 2), ("start", 1))


def synthetic_span(region: Region, rnd: random.Random) -> tuple[int, int] | None:
    """A big span as the real ones are (`WHERE_WEIGHTS`): one whole line of 2 to 8 full-size characters, less than
    half of the region's, at its end, in the middle or at its start; None for a region of one line or none such."""
    chars = region.chars
    if len(chars) < 4:
        return None
    lines = split_lines(chars, direction(chars))
    if len(lines) < 2:
        return None
    full = [sum(1 for i in line if is_full(chars[i].cat)) for line in lines]
    total = sum(full)
    ok = [k for k, n in enumerate(full) if 2 <= n <= 8 and 2 * n < total]
    places = {"start": [k for k in ok if k == 0], "end": [k for k in ok if k == len(lines) - 1],
              "middle": [k for k in ok if 0 < k < len(lines) - 1]}
    choices = [(w, n) for w, n in WHERE_WEIGHTS if places[w]]
    if not choices:
        return None
    where = rnd.choices([w for w, _n in choices], [n for _w, n in choices])[0]
    k = rnd.choice(places[where])
    return lines[k][0], lines[k][-1] + 1


def _as_one_line(text: str, at: tuple[int, int]) -> tuple[str, tuple[int, int]]:
    """*text* as a request gives it to the model (`plamo.one_line`: its spaces and line breaks made one space when it
    has a line break) and the range *at* in it."""
    if "\n" not in text:
        return text, at
    out: list[str] = []
    where = [0] * (len(text) + 1)
    space = False
    for i, ch in enumerate(text):
        where[i] = len(out)
        if ch.isspace():
            space = bool(out)
            continue
        if space:
            out.append(" ")
            space = False
            where[i] = len(out)
        out.append(ch)
    where[len(text)] = len(out)
    return "".join(out), (where[at[0]], where[at[1]])


def _ask(tr: Any, text: str, notes: str, history: list[tuple[str, str]]) -> tuple[str, float]:
    """One request of the translator's for *text* after *history* (`PlamoTranslator._line`): its answer and its time
    in ms."""
    t0 = time.monotonic()
    got = tr._line(text, notes, history)
    return got, (time.monotonic() - t0) * 1000.0


def ask_case(tr: Any, notes: str, case: Case, markers: Sequence[str]) -> None:
    """The requests a way of locating the span would add or replace, each after the pairs the region's own request
    started from: the region's text alone (the control: what the marked requests change), the span alone, the text
    with the span in each marker, and the text in three lines (before, the span, after: a joined request)."""
    from taslation.translate.continuation import joined, split_back
    from taslation.translate.plamo import one_line

    text = one_line(case.region.text)
    a, b = case.at
    h = list(case.history)
    case.answers["control"], case.ms["control"] = _ask(tr, text, notes, h)
    span = text[a:b].strip()
    case.answers["span"], case.ms["span"] = _ask(tr, span, notes, h)
    for name in markers:
        key = "marker:" + name
        case.answers[key], case.ms[key] = _ask(tr, marked_source(text, (a, b), MARKERS[name]), notes, h)
    parts = [p for p in (text[:a].strip(), span, text[b:].strip()) if p]
    answer, ms = _ask(tr, joined(parts), notes, h)
    case.answers["split"], case.ms["split"] = answer, ms
    back = split_back(answer, len(parts))
    if back is not None:
        k = parts.index(span)
        start = sum(len(p) + 1 for p in back[:k])
        case.found["split"] = (" ".join(back), (start, start + len(back[k])))
    else:
        case.found["split"] = (" ".join(answer.split()), None)
    for name in markers:
        case.found["marker:" + name] = marked_part(case.answers["marker:" + name], MARKERS[name])


def locate_all(case: Case) -> None:
    """The ways that look for the span in the region's own translation: the span translated alone found in it
    (exact; exact or else loose), the same sentences, and the share baseline."""
    whole = case.region.translation
    alone = case.answers.get("span", "")
    exact = locate_exact(whole, alone) if alone else None
    case.found["exact"] = (whole, exact)
    case.found["exact_or_loose"] = (whole, exact or (locate_loose(whole, alone) if alone else None))
    case.found["sentences"] = (whole, locate_sentences(case.region.text, case.at, whole))
    case.found["share"] = (whole, locate_share(case.region.text, case.at, whole))
    for key in [k for k in case.found if k.startswith("marker:")]:
        # the marked request as a locator only: its marked part found in the region's own translation, which stays
        plain, at = case.found[key]
        inner = plain[at[0]:at[1]] if at is not None else ""
        hit = (locate_exact(whole, inner) or locate_loose(whole, inner)) if inner.strip() else None
        case.found["found_" + key] = (whole, hit)


def _shown(text: str, at: tuple[int, int] | None) -> str:
    return text if at is None else text[:at[0]] + "[[" + text[at[0]:at[1]] + "]]" + text[at[1]:]


def run_translate(args: Any, items: list[Item], rule: Rule) -> dict[str, Any]:
    """The test of the ways of locating the big span (see the module's docstring): the pages translated in order, the
    series one after the other (the context begun again at each), the cases of every page asked for (`ask_case`) and
    located (`locate_all`); the counts and times. Prints ``--show`` random cases to the terminal, nothing else of a
    text."""
    from openmantra_eval import chrf
    from taslation.translate.base import TranslationError

    if args.frames:
        raise SystemExit("--translate takes the dataset only (the frames' text is never shown nor kept)")
    markers = [m for m in args.markers.split(",") if m]
    pipe = make_pipeline(args.detect_model, target=args.target, seed=args.seed)
    tr = pipe.translator
    tr.stats_log = []
    watch = Watch(pipe)
    notes = pipe.premises()
    rnd = random.Random(args.seed)
    cases: list[Case] = []
    pages = 0
    page_ms: list[float] = []
    series = None
    t0 = time.monotonic()
    for item in items:
        if len(cases) >= args.limit:
            break
        if item.series != series:
            series = item.series
            pipe.reset_context()
        before = list(pipe.context_pairs())
        image = item.open()
        t1 = time.monotonic()
        regions, _n = scan_page(pipe, watch, item, image, translate=True)
        page_ms.append((time.monotonic() - t1) * 1000.0)
        pages += 1
        history = list(before)
        for r in regions:
            if not r.translation:
                continue
            span = None
            real = False
            if len(r.chars) >= 2 and (m := find_mix(r, rule)).mixed:
                span, real = m.spans[0], True
            elif args.synthetic:
                span = synthetic_span(r, rnd)
            if span is not None and len(cases) < args.limit:
                at = text_range(r, *span)
                r.text, at = _as_one_line(r.text, at)
                if r.text[at[0]:at[1]].strip() and (at[0] > 0 or at[1] < len(r.text)):
                    gold = ""
                    if item.page is not None and r.gold is not None:
                        gold = item.page.bubbles[r.gold].en
                    cases.append(Case(r, span, real, at, gold, list(history)))
            history.append((r.text, r.translation))
        if pages % 5 == 0:
            print(f"  {pages} pages, {len(cases)} cases [{time.monotonic() - t0:.0f} s]", flush=True)
    app_requests = len(tr.stats_log)
    print(f"{pages} pages translated as the app does ({app_requests} requests, {statistics.mean(page_ms):.0f} ms a "
          f"page with the OCR); {len(cases)} cases ({sum(c.real for c in cases)} real)", flush=True)
    failed = 0
    for n, case in enumerate(cases, 1):
        try:
            ask_case(tr, notes, case, markers)
        except TranslationError:
            failed += 1
            continue
        locate_all(case)
        if n % 20 == 0:
            print(f"  asked {n}/{len(cases)} [{time.monotonic() - t0:.0f} s]", flush=True)
    done = [c for c in cases if c.answers]
    methods = (["exact", "exact_or_loose", "sentences", "share", "split"] + ["marker:" + m for m in markers]
               + ["found_marker:" + m for m in markers])
    out: dict[str, Any] = {"pages": pages, "cases": len(done), "real": sum(c.real for c in done), "failed": failed,
                           "target": args.target, "ms_page_app": round(statistics.mean(page_ms)),
                           "methods": {}, "requests_ms": {}, "quality": {}}
    for key in ["control", "span", "split"] + ["marker:" + m for m in markers]:
        ms = [c.ms[key] for c in done if key in c.ms]
        out["requests_ms"][key] = {"mean": round(statistics.mean(ms)), "median": round(statistics.median(ms))} if ms \
            else {}
    for m in methods:
        answered = [c for c in done if c.found.get(m, ("", None))[1] is not None]
        out["methods"][m] = {"answered": len(answered), "of": len(done),
                             "real_answered": sum(c.real for c in answered), "real_of": sum(c.real for c in done)}
    # the translation's quality against the dataset's, for the requests that replace the region's own
    scored = [c for c in done if c.gold.strip()] if args.target.lower() == "english" else []  # (the dataset's is English)
    if scored:
        q = {"app": [chrf(c.region.translation, c.gold) for c in scored],
             "control": [chrf(c.answers["control"], c.gold) for c in scored],
             "split": [chrf(c.found["split"][0], c.gold) for c in scored]}
        for m in markers:
            q["marker:" + m] = [chrf(c.found["marker:" + m][0], c.gold) for c in scored]
        for k, v in q.items():
            diff = [x - y for x, y in zip(v, q["control"])]
            half = 1.96 * statistics.stdev(diff) / math.sqrt(len(diff)) if len(diff) > 1 else 0.0
            out["quality"][k] = {"chrf": round(statistics.mean(v), 2), "minus_control": round(statistics.mean(diff), 2),
                                 "ci95": round(half, 2),
                                 "same_as_control": sum(1 for c, x, y in zip(scored, v, q["control"]) if x == y),
                                 "of": len(scored)}
    print(json.dumps({k: v for k, v in out.items()}, indent=1))
    if args.show:
        shown = rnd.sample(done, min(args.show, len(done)))
        for k, c in enumerate(shown, 1):
            text = c.region.text
            a, b = c.at
            print(f"\n=== {k} {'REAL' if c.real else 'synthetic'}")
            print("  source :", text[:a] + "[[" + text[a:b] + "]]" + text[b:])
            print("  gold   :", c.gold)
            print("  app    :", c.region.translation)
            print("  alone  :", c.answers.get("span", ""))
            for m in methods:
                t, at = c.found[m]
                print(f"  {m:15}:", _shown(t, at) if at is not None else "-- (no answer)" + (
                    "  " + t if m.startswith(("marker", "split")) else ""))
    return out


# ------------------------------------------------------------------ the shipped locating step
HISTORIES = ("before", "page")  # the pairs a locating request starts from: those the region's own did, or the page's


def _aside(tr: Any, text: str, history: list[tuple[str, str]], notes: str) -> tuple[str, float]:
    """One request beside the page's (`translate_aside`, as the app makes it): its answer and its time in ms."""
    t0 = time.monotonic()
    got = tr.translate_aside(text, history, notes)
    return got, (time.monotonic() - t0) * 1000.0


def run_locate(args: Any, items: list[Item], rule: Rule) -> dict[str, Any]:
    """The test of the shipped locating step (`taslation.locate_large`): the pages translated as the app does, the
    cases found as for ``--translate`` (`run_translate`), and for every case and every history of ``--history`` the
    two steps asked for both (the app asks the second only when the first found nothing): the part alone found in the
    translation (`from_alone`) and the marked request's part found in it (`from_marked`; before its plausibility
    check too, with the share ratio, for tuning). Counts and times; ``--show`` prints the cases to the terminal for a
    person to judge. Stops asking after ``--max-seconds`` (what was asked is reported)."""
    from taslation import locate_large as ll
    from taslation.translate.base import TranslationError

    if args.frames:
        raise SystemExit("--locate takes the dataset only (the frames' text is never shown nor kept)")
    histories = [h for h in args.history.split(",") if h]
    if any(h not in HISTORIES for h in histories):
        raise SystemExit("--history takes " + ", ".join(HISTORIES))
    pipe = make_pipeline(args.detect_model, target=args.target, seed=args.seed)
    tr = pipe.translator
    watch = Watch(pipe)
    notes = pipe.premises()
    rnd = random.Random(args.seed)
    cases: list[tuple[Case, list[tuple[str, str]]]] = []
    series = None
    t0 = time.monotonic()
    for item in items:
        if len(cases) >= args.limit or time.monotonic() - t0 > args.max_seconds / 2:
            break
        if item.series != series:
            series = item.series
            pipe.reset_context()
        before = list(pipe.context_pairs())
        image = item.open()
        regions, _n = scan_page(pipe, watch, item, image, translate=True)
        page_history = list(pipe.context_pairs())  # (the page's pairs too: the request after the page starts so)
        history = list(before)
        for r in regions:
            if not r.translation:
                continue
            span, real = None, False
            if len(r.chars) >= 2 and (m := find_mix(r, rule)).mixed:
                span, real = m.spans[0], True
            elif not args.real_only:
                span = synthetic_span(r, rnd)
            if span is not None and len(cases) < args.limit:
                at = text_range(r, *span)
                r.text, at = _as_one_line(r.text, at)
                if r.text[at[0]:at[1]].strip() and (r.text[:at[0]].strip() or r.text[at[1]:].strip()):
                    cases.append((Case(r, span, real, at, "", list(history)), page_history))
            history.append((r.text, r.translation))
    print(f"{len(cases)} cases ({sum(c.real for c, _h in cases)} real) [{time.monotonic() - t0:.0f} s]", flush=True)
    rows: list[dict[str, Any]] = []
    for case, page_history in cases:
        if time.monotonic() - t0 > args.max_seconds:
            break
        text, (a, b) = case.region.text, case.at
        whole = case.region.translation
        part = text[a:b].strip()
        row: dict[str, Any] = {"case": case, "real": case.real}
        try:
            for h in histories:  # the part alone after each history
                hist = case.history if h == "before" else page_history
                alone, ms = _aside(tr, part, hist, notes)
                at = ll.from_alone(whole, alone)
                row["alone:" + h] = {"text": alone, "at": at, "ms": ms,
                                     "share": ll.share_ratio(whole, at, text, (a, b)) if at else None}
            hist = case.history if args.marked_history == "before" else page_history
            answer, ms = _aside(tr, ll.marked_source(text, (a, b)), hist, notes)
        except TranslationError:
            continue
        inner = ll.marked_part(answer)
        raw = (ll.find_exact(whole, inner) or ll.find_loose(whole, inner)) if inner and ll._letters(inner) else None
        raw = ll.snap(whole, raw) if raw is not None else None
        mine = row.get("alone:" + args.marked_history, {}).get("text", "")
        kept = ll.from_marked(whole, answer, text, (a, b), mine)
        row["marked"] = {"text": answer, "at": raw, "ms": ms,
                         "share": ll.share_ratio(whole, raw, text, (a, b)) if raw is not None else None,
                         "kept": kept is not None}
        # what the shipped step gives (`locate`: the part alone after the marked request's history, else the marked)
        first = row.get("alone:" + args.marked_history, {}).get("at")
        row["final"] = ("alone", first) if first is not None else ("marked", kept) if kept is not None else ("", None)
        for h in histories:  # how far the part alone agrees with what the marked request points at
            alone = row["alone:" + h]["text"]
            row["agree:" + h] = round(ll.agreement(whole[raw[0]:raw[1]], alone), 3) if raw is not None else None
            alone_at = (0, len(alone)) if alone else None
            row["alone_share:" + h] = (round(((ll._letters(alone) / max(1, ll._letters(whole)))
                                              / max(1e-6, ll._letters(text[a:b]) / max(1, ll._letters(text)))), 3)
                                       if alone_at else None)
        rows.append(row)
    out: dict[str, Any] = {"cases": len(rows), "real": sum(r["real"] for r in rows), "target": args.target,
                           "seconds": round(time.monotonic() - t0), "marked_history": args.marked_history,
                           "steps": {}, "rows": []}
    for h in histories:
        got = [r["alone:" + h] for r in rows]
        out["steps"]["alone:" + h] = {"found": sum(g["at"] is not None for g in got),
                                      "ms_median": round(statistics.median(g["ms"] for g in got)) if got else 0}
    marked = [r["marked"] for r in rows]
    out["steps"]["marked"] = {"pointed": sum(m["at"] is not None for m in marked),
                              "kept": sum(m["kept"] for m in marked),
                              "ms_median": round(statistics.median(m["ms"] for m in marked)) if marked else 0}
    out["final"] = {"alone": sum(r["final"][0] == "alone" for r in rows),
                    "marked": sum(r["final"][0] == "marked" for r in rows),
                    "none": sum(r["final"][0] == "" for r in rows)}
    for n, r in enumerate(rows, 1):  # numbers only, for the rules tuned on a person's verdicts
        out["rows"].append({"n": n, "real": r["real"], "final": r["final"][0], "marked_share": r["marked"]["share"],
                            "marked_pointed": r["marked"]["at"] is not None,
                            **{f"alone_found:{h}": r["alone:" + h]["at"] is not None for h in histories},
                            **{f"alone_part_share:{h}": r["alone:" + h]["share"] for h in histories},
                            **{f"agree:{h}": r["agree:" + h] for h in histories},
                            **{f"alone_letters:{h}": ll._letters(r["alone:" + h]["text"]) for h in histories},
                            **{f"alone_words:{h}": len(ll.normalised(r["alone:" + h]["text"])[0].split())
                               for h in histories},
                            **{f"alone_share:{h}": r["alone_share:" + h] for h in histories}})
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    if args.show:
        for k, r in enumerate(rows[: args.show], 1):
            c = r["case"]
            text, (a, b) = c.region.text, c.at
            whole = c.region.translation
            print(f"\n=== {args.tag}{k} {'REAL' if c.real else 'synthetic'}")
            print("  source :", text[:a] + "[[" + text[a:b] + "]]" + text[b:])
            print("  app    :", whole)
            for h in histories:
                g = r["alone:" + h]
                print(f"  alone {h:6}: {g['text']!r} -> {_shown(whole, g['at']) if g['at'] else '--'}"
                      f"  agree {r['agree:' + h]}  alone_share {r['alone_share:' + h]}")
            m = r["marked"]
            share = f"{m['share']:.2f}" if m["share"] is not None else "-"
            print(f"  marked      : {m['text']!r} -> {_shown(whole, m['at']) if m['at'] else '--'}  share {share}")
            step, at = r["final"]
            print(f"  FINAL {step or 'none':6}: {_shown(whole, at) if at else '--'}")
    return out


# ------------------------------------------------------------------ the shipped path, end to end
def mixed_pages(args: Any, items: list[Item], rule: Rule) -> list[int]:
    """The indices into *items* of the pages the scan (``--scan``, made when missing) finds a mixed region on."""
    data = load_or_scan(args, items)
    keys = {r.page for v in data["pages"].values() for r in v if len(r.chars) >= 2 and find_mix(r, rule).mixed}
    return [k for k, item in enumerate(items) if item.key in keys]


def _crop(image: Any, box: Box, grow: int = 16) -> Any:
    x0, y0, x1, y1 = box
    return image.crop((max(0, x0 - grow), max(0, y0 - grow), min(image.width, x1 + grow),
                       min(image.height, y1 + grow)))


def run_shipped(args: Any, items: list[Item], rule: Rule) -> dict[str, Any]:
    """The shipped locating step on the app's own path: the pages that hold a mixed region (and the page before each,
    for its context; with ``--all-pages`` every page) read and translated as the app does (`Pipeline.process`, the
    default translator for ``--target`` with a fixed seed, the pages before as context, each series and each gap
    begun anew), every region its reading measured as mixed (`TextRegion.size_mix`) looked for by `Pipeline.large_part`
    as its page's translations settle. Per region: the step that answered (counts), its requests and their time, and
    whether its lettering came out at two sizes (lettered with and without the part found: the pixels differ). With
    ``--sheets``: per region its crop, lettered without the part and with it (pictures only). Numbers only: no text
    is printed or written."""
    from PIL import Image

    pipe = make_pipeline(args.detect_model, target=args.target, seed=args.seed)
    real = pipe.large_part
    looks: list[dict[str, Any]] = []

    def watched(source: str, mix: Any, translation: str, *a: Any, **k: Any) -> Any:
        t = pipe.large_tally
        before = (t.requests, t.alone, t.marked, t.ms)
        got = real(source, mix, translation, *a, **k)
        step = "alone" if t.alone > before[1] else "marked" if t.marked > before[2] else ""
        looks.append({"key": (source, translation), "step": step if got is not None else "",
                      "requests": t.requests - before[0], "ms": t.ms - before[3], "ratio": float(mix.ratio)})
        return got

    pipe.large_part = watched  # type: ignore[method-assign]
    chosen = list(range(len(items))) if args.all_pages else mixed_pages(args, items, rule)
    wanted = sorted({k for i in chosen for k in (i - 1, i) if 0 <= k < len(items)})
    rows: list[dict[str, Any]] = []
    cells: list[tuple[Any, Any, Any, str]] = []
    previous, series = -2, None
    t0 = time.monotonic()
    page_ms: list[float] = []
    for k in wanted:
        item = items[k]
        if item.series != series or k != previous + 1:
            pipe.reset_context()
        series, previous = item.series, k
        image = item.open()
        if item.margins is not None:
            pipe.settings.margins = tuple(item.margins)
        n0 = len(looks)
        started = time.monotonic()
        res = pipe.process(image, translate=True, use_cache=False)
        page_ms.append((time.monotonic() - started) * 1000.0)
        mine = looks[n0:]
        out = np.asarray(res.original).copy()
        for r in res.regions:
            if r.size_mix is None or r.status != "translated":
                continue
            look = next((x for x in mine if x["key"] == (r.source_text, r.translated_text)), None)
            if look is None:
                continue
            large = r.large
            r.large = None
            plain = out.copy()
            pipe.letter_region(plain, r, r.translated_text)
            r.large = large
            lettered = out.copy()
            pipe.letter_region(lettered, r, r.translated_text)
            two = bool(large) and not np.array_equal(plain, lettered)
            rows.append({"n": len(rows) + 1, "page": k + 1, "step": look["step"], "requests": look["requests"],
                         "ms": round(look["ms"]), "ratio": round(look["ratio"], 2), "found": large is not None,
                         "two_sizes": two})
            if args.sheets:
                cells.append((_crop(image, r.bbox), _crop(Image.fromarray(plain), r.bbox),
                              _crop(Image.fromarray(lettered), r.bbox),
                              f"{len(rows)}  {look['step'] or 'none'}  x{look['ratio']:.2f}  {'2 sizes' if two else '1 size'}"))
        del image
    seconds = time.monotonic() - t0
    total_ms = sum(x["ms"] for x in looks)
    out_: dict[str, Any] = {
        "pages_read": len(wanted), "pages_in_set": len(items), "mixed_regions": len(rows),
        "steps": dict(Counter(r["step"] or "none" for r in rows)), "two_sizes": sum(r["two_sizes"] for r in rows),
        "requests": sum(x["requests"] for x in looks), "looks": len(looks),
        "ms_per_mixed_bubble": round(total_ms / len(looks)) if looks else 0,
        "requests_per_mixed_bubble": round(sum(x["requests"] for x in looks) / len(looks), 2) if looks else 0,
        "ms_per_page_at_the_sets_rate": round(total_ms / max(1, len(items))),
        "page_ms_median": round(statistics.median(page_ms)) if page_ms else 0, "seconds": round(seconds),
        "rows": rows}
    print(json.dumps({k: v for k, v in out_.items() if k != "rows"}, indent=1))
    for r in rows:
        print(f"  {r['n']:2}: step {r['step'] or 'none':6} requests {r['requests']} {r['ms']:5} ms  x{r['ratio']:.2f}"
              f"  {'two sizes' if r['two_sizes'] else 'one size'}")
    if args.sheets and cells:
        args.sheets.mkdir(parents=True, exist_ok=True)
        files = []
        per = 4
        for s in range(0, len(cells), per):
            group = cells[s:s + per]
            scale = [CELL / max(c[0].width, c[0].height) for c in group]
            h = max(round(c[0].height * f) for c, f in zip(group, scale)) + 22
            sheet = Image.new("RGB", (3 * (CELL + 8), len(group) * (h + 8)), (200, 200, 200))
            from PIL import ImageDraw

            draw = ImageDraw.Draw(sheet)
            for row, ((orig, before, after, label), f) in enumerate(zip(group, scale)):
                for col, pic in enumerate((orig, before, after)):
                    pic = pic.resize((max(1, round(pic.width * f)), max(1, round(pic.height * f))), Image.LANCZOS)
                    sheet.paste(pic, (col * (CELL + 8), row * (h + 8) + 22))
                draw.text((4, row * (h + 8) + 4), label + "   (original | today | with the part)", fill=(0, 0, 0))
            path = args.sheets / f"{args.tag or 'shipped'}-{s // per + 1}.png"
            sheet.save(path)
            files.append(str(path))
        print("sheets: " + ", ".join(files))
        out_["sheets"] = files
    return out_


# ------------------------------------------------------------------ picture sheets
CELL = 320  # a crop's longer side on a sheet
PER_SHEET = (4, 3)  # columns, rows


def _span_boxes(region: Region, mix: Mix) -> list[tuple[float, float, float, float]]:
    """A box round each line's part of each big span (the union of its characters' boxes)."""
    line_of = {i: k for k, line in enumerate(mix.lines) for i in line}
    out = []
    for a, b in mix.spans:
        parts: dict[int, list[int]] = {}
        for i in range(a, b):
            parts.setdefault(line_of[i], []).append(i)
        for idx in parts.values():
            bs = [region.chars[i].box for i in idx]
            out.append((min(b_[0] for b_ in bs), min(b_[1] for b_ in bs), max(b_[2] for b_ in bs),
                        max(b_[3] for b_ in bs)))
    return out


def picture(image: Any, region: Region, mix: Mix, label: str) -> Any:
    """The region's crop, its characters' boxes drawn (green: measured, base; red: in a big span; grey: measuring
    nothing) and each big span outlined thick in red, at `CELL` on its longer side, *label* on top."""
    from PIL import Image, ImageDraw

    x0, y0, x1, y1 = region.bbox
    m = 12
    x0, y0 = max(0, x0 - m), max(0, y0 - m)
    x1, y1 = min(image.width, x1 + m), min(image.height, y1 + m)
    crop = image.crop((x0, y0, x1, y1)).convert("RGB")
    scale = CELL / max(crop.width, crop.height)
    crop = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.LANCZOS)
    draw = ImageDraw.Draw(crop)
    inside = {i for a, b in mix.spans for i in range(a, b)}

    def at(b: Sequence[float]) -> list[float]:
        return [(b[0] - x0) * scale, (b[1] - y0) * scale, (b[2] - x0) * scale, (b[3] - y0) * scale]

    for i, c in enumerate(region.chars):
        colour = (230, 30, 30) if i in inside else (40, 170, 60) if mix.sizes[i] is not None else (150, 150, 150)
        draw.rectangle(at(c.box), outline=colour, width=1)
    for b in _span_boxes(region, mix):
        bx = at(b)
        draw.rectangle([bx[0] - 3, bx[1] - 3, bx[2] + 3, bx[3] + 3], outline=(230, 0, 0), width=3)
    cell = Image.new("RGB", (CELL, CELL + 18), (255, 255, 255))
    cell.paste(crop, ((CELL - crop.width) // 2, 18 + (CELL - crop.height) // 2))
    ImageDraw.Draw(cell).text((4, 2), label, fill=(0, 0, 0))
    return cell


def write_sheets(folder: Path, name: str, chosen: list[tuple[Region, Mix]], open_page: Any) -> list[Path]:
    """*chosen* drawn (`picture`) on sheets of `PER_SHEET` crops, numbered from 1, into *folder*; the files."""
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    cols, rows = PER_SHEET
    per = cols * rows
    files = []
    pages: dict[str, Any] = {}
    for s in range(0, len(chosen), per):
        sheet = Image.new("RGB", (cols * (CELL + 6), rows * (CELL + 24)), (200, 200, 200))
        for k, (region, mix) in enumerate(chosen[s: s + per]):
            if region.page not in pages:
                pages.clear()
                pages[region.page] = open_page(region.page)
            label = f"{s + k + 1}  x{mix.ratio:.2f}  {'V' if mix.vertical else 'H'}  {region.kind[:10]}"
            cell = picture(pages[region.page], region, mix, label)
            sheet.paste(cell, ((k % cols) * (CELL + 6), (k // cols) * (CELL + 24)))
        path = folder / f"{name}-{s // per + 1}.png"
        sheet.save(path)
        files.append(path)
    return files


def load_or_scan(args: Any, items: list[Item], log: Any = print) -> dict[str, Any]:
    key = {"version": SCAN_VERSION, "detect_model": args.detect_model or "default", "pages": [i.key for i in items]}
    if args.scan and args.scan.exists():
        held = read_scan(args.scan)
        if held.get("key") == key:
            log(f"detection and OCR from {args.scan}")
            return held
    data = scan(items, args.detect_model, log)
    if args.scan:
        save_scan(args.scan, key, data)
    return data


def main(argv: list[str] | None = None) -> int:
    netguard.install()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=openmantra.DEFAULT_ROOT)
    ap.add_argument("--series", action="append")
    ap.add_argument("--pages", type=int, default=0, help="only the first N pages of every series")
    ap.add_argument("--skip-pages", type=int, default=0, help="the first N of those left out (a held-out set)")
    ap.add_argument("--frames", help="a glob of frames (a book's dev snapshots) in place of the dataset")
    ap.add_argument("--detect-model", choices=("auto", "on", "off"))
    ap.add_argument("--scan", type=Path, help="keep the detection and the OCR here (boxes and classes, no text)")
    ap.add_argument("--ratio", type=float, default=Rule.ratio, help="the rule's least ratio of the big span")
    ap.add_argument("--min-span", type=int, default=Rule.min_span, help="the rule's least full-size characters a span")
    ap.add_argument("--no-smooth", action="store_true", help="each character's own size, not its neighbours' median")
    ap.add_argument("--by-char", action="store_true", help="every character its own size (with --no-smooth: "
                    "alone, else its neighbours' median), not its line's median: a size may change within a line")
    ap.add_argument("--min-sure", type=float, default=Rule.min_sure)
    ap.add_argument("--measure", choices=("pitch", "cell", "box"), default=Rule.measure)
    ap.add_argument("--min-base", type=int, default=Rule.min_base, help="the rule's least full-size characters in the base")
    ap.add_argument("--box-lines", action="store_true", help="(pitch) a line without a step measures its boxes")
    ap.add_argument("--confirm", type=float, default=Rule.confirm,
                    help="the span's own boxes at least this many times the base's too (0: unchecked)")
    ap.add_argument("--json", type=Path, help="the numbers (no text)")
    ap.add_argument("--sheets", type=Path, help="a scratch folder for the picture sheets")
    ap.add_argument("--sample", type=int, default=60, help="regions per kind of sheet")
    ap.add_argument("--tag", default="", help="a prefix for the sheets' names")
    ap.add_argument("--seed", type=int, default=7, help="the sheets' random sample (and the translation's seed)")
    ap.add_argument("--translate", action="store_true", help="the test of the ways of locating the span (dataset)")
    ap.add_argument("--target", default="English", help="the translation's language (--translate)")
    ap.add_argument("--limit", type=int, default=120, help="cases at most (--translate)")
    ap.add_argument("--markers", default=",".join(MARKERS), help="the markers to try, of " + ", ".join(MARKERS))
    ap.add_argument("--real-only", action="store_true", help="(--translate) only the spans the rule finds")
    ap.add_argument("--show", type=int, default=0, help="(--translate) random cases printed for a person to judge")
    ap.add_argument("--locate", action="store_true", help="the test of the shipped locating step (dataset)")
    ap.add_argument("--history", default="page", help="(--locate) the pairs the part alone is asked after, of "
                    + ", ".join(HISTORIES) + " (several: each asked)")
    ap.add_argument("--marked-history", default="page", choices=HISTORIES,
                    help="(--locate) the pairs the marked request is asked after")
    ap.add_argument("--max-seconds", type=float, default=140.0, help="(--locate) no request asked after this")
    ap.add_argument("--shipped", action="store_true", help="the shipped step on the app's own path, end to end "
                    "(dataset or frames; counts and pictures only)")
    ap.add_argument("--all-pages", action="store_true", help="(--shipped) every page, not only those with a mixed "
                    "region and the page before each")
    args = ap.parse_args(argv)
    items = frame_items(args.frames) if args.frames else dataset_items(args.root, args.series, args.pages,
                                                                       args.skip_pages)
    rule = Rule(args.ratio, args.min_span, not args.no_smooth, not args.by_char, args.min_sure, args.measure,
                args.min_base, not args.box_lines, args.confirm)
    if args.shipped:
        report = run_shipped(args, items, rule)
        if args.json:
            args.json.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        return 0
    if args.locate:
        report = run_locate(args, items, rule)
        if args.json:
            args.json.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        return 0
    if args.translate:
        args.synthetic = not args.real_only
        report = run_translate(args, items, rule)
        if args.json:
            args.json.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        return 0
    data = load_or_scan(args, items)
    print(f"detect_model {data['detect_model']}: {sum(len(v) for v in data['pages'].values())} regions read as "
          f"Japanese of {data['candidates']} candidates, {data['seconds']} s")
    regions = [r for v in data["pages"].values() for r in v]
    report: dict[str, Any] = {"rule": asdict(rule), "detect_model": data["detect_model"]}
    report["all"] = statistics_of(regions, rule)
    print_report("all", report["all"])
    for name in dict.fromkeys(r.page.split("#")[0] for r in regions):
        report[name] = statistics_of([r for r in regions if r.page.split("#")[0] == name], rule)
        print_report(name, report[name])
    for label, keep in (("layout model", True), ("classical", False)):
        part = [r for r in regions if r.from_model == keep]
        report[label] = statistics_of(part, rule)
        print_report(label, report[label])
    kept = Counter((r.from_model, r.kept_boxes == len(r.chars)) for r in regions if r.chars)
    same = Counter((r.from_model, r.same_text) for r in regions if r.chars)
    print(f"character boxes kept on the region (from_model, all kept): {dict(kept)}; charspot's characters spell the "
          f"settled text (from_model, same): {dict(same)}")
    if args.sheets:
        rnd = random.Random(args.seed)
        mixed = [(r, m) for r in regions if len(r.chars) >= 2 and (m := find_mix(r, rule)).mixed]
        plain = [(r, m) for r in regions if len(r.chars) >= 2 and not (m := find_mix(r, rule)).mixed
                 and len(m.lines) >= 2]
        by_key = {i.key: i for i in items}
        tag = (args.tag + "-") if args.tag else ""
        for name, pool in (("mixed", mixed), ("not-mixed", plain)):
            chosen = rnd.sample(pool, min(args.sample, len(pool)))
            files = write_sheets(args.sheets, tag + name, chosen, lambda key: by_key[key].open())
            listing = [{"n": k + 1, "page": r.page, "region": r.index, "ratio": round(m.ratio, 3)}
                       for k, (r, m) in enumerate(chosen)]
            (args.sheets / f"{tag}{name}.json").write_text(json.dumps(listing, indent=1), encoding="utf-8")
            print(f"{len(chosen)} of {len(pool)} {name} regions on " + ", ".join(str(f) for f in files))
    if args.json:
        args.json.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
