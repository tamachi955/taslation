"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: TASlation on the OpenMantra pages, scored against the gold annotation.

OpenMantra (Hinami, Ishiwatari, Yasuda, Matsui, "Towards Fully Automated Manga Translation", AAAI 2021; Mantra
Inc.; CC BY-NC 4.0) is fetched by ``fetch_openmantra.py`` into ``~/.taslation/datasets/openmantra`` and read by
``openmantra.py``. This tool runs the Japanese pages through TASlation and prints numbers only:

* detection: the regions TASlation reads as Japanese text against the gold boxes, paired one to one at IoU >= 0.5
  (a region overlaps a gold box as much as the better of its bubble box and its lettering box: the gold boxes lie
  between the two): precision, recall, F1; and every region the detector proposed before the OCR judged it
  ("candidates": the recall the OCR's judgement starts from). Recall counts the gold boxes with a word in them
  (`worded`: a punctuation-only box, "..." or "!?", is nothing to translate); a region that matches a
  punctuation-only box still counts as found right. ``recall_all`` and ``f1_all`` are the recall over every gold box,
  as before 2026-11-11.
* OCR: the OCR model on crops of the gold boxes, CER against the gold Japanese (normalised as ``ocr_gold.py`` does:
  NFKC, dashes and dots unified, no whitespace), so the OCR is scored apart from detection; and the CER of the
  pipeline's own readings of the regions that matched a gold box.
* translation: the app's translator (`taslation.translate.models.make_translator`: with ``--model`` left out the
  one the target language chooses, PLaMo 3 Translate 2B for English and Chinese; the default settings, no series
  sheet) on the gold Japanese, against the professional English (``--target zh``: into Traditional Chinese, against
  the professional Chinese, compared without spaces): chrF as the model knockouts scored it (character n-grams 1-6,
  beta 2), and the share of lines the review flags (``taslation.review``). ``--mode book`` (the default, as the app's
  whole-book batch does it, `BatchReader._translation_pass` itself): every line known first, then runs of about 30
  lines with the 40 previous pairs (and, for the chat translator, the next 60 lines) as context, the renderings and
  size checks; ``--mode page``: the live path, one page per request with the last two pages as context. Every line is set in the geometry the
  app would have: the detected region that matched its gold box, else the gold box (``--geometry gold``: always
  the gold box, so detection changes cannot move the translation scores). This is the *official* arm: gold text in
  gold order, so that it measures the translation alone.
* end to end (``--arm e2e`` or ``both``, needs the OCR): what the app itself hands the translator, the regions the
  pipeline reads as Japanese text, in its reading order, with the OCR's text, translated the same way; each gold line
  is scored with the translation of the region matched to it. *strict*: every gold line with Japanese, 0 for one no
  region matched (the official arm's lines); *lenient*: the matched gold lines only. Regions with no gold box are
  translated (they are context for the others) and counted, not scored.
* categories of the gold lines, in every arm: the lines whose Japanese ends open (`ends_open`: on a particle or a
  connective with no sentence end, a sentence that goes on in the next bubble), their mean chrF and the rest's;
  bare romanisations (`bare_romanisation`: a line of 1-3 kana answered with its romaji alone); with ``--names FILE``
  the lines naming a character (the name in the Japanese and its reference rendering in the English): the share
  rendered as the reference has it, and how consistently each name is rendered (the share of its lines with its most
  frequent rendering).

``--glossary FILE`` gives every series a series sheet (JSON ``{series: {"characters": {ja: rendering}, "terms": {ja:
rendering}}}``), as the reader would write one: an upper bound for what names and terms held fixed can do. ``--scan
FILE`` keeps the detection and the OCR of the pages in FILE (made when it is missing, with the dataset's hash and the
detection settings, read again when they agree): the translation arms then start at once. ``--dump FILE`` writes
every line's Japanese, translation and reference to FILE (JSON lines, for a person to look at; never printed).

    python tools/openmantra_eval.py                          # all 214 pages (detection and OCR ~10 min, translation ~45)
    python tools/openmantra_eval.py --pages 4                # the first 4 pages of every series
    python tools/openmantra_eval.py --no-translate           # detection and OCR only (no Ollama needed)
    python tools/openmantra_eval.py --no-ocr --series balloon_dream --mode page
    python tools/openmantra_eval.py --out results.json
    python tools/openmantra_eval.py --no-ocr --geometry gold --runs 3 --seed 1 --out a.json   # one arm of a comparison
    python tools/openmantra_eval.py --no-ocr --geometry gold --runs 3 --seed 1 --model qwen3.5:4b --out b.json
    python tools/compare_runs.py b.json a.json                                                # paired by series
    python tools/openmantra_eval.py --arm both --scan scan.pkl --runs 3 --seed 1 --out c.json # official and end to end
    python tools/compare_runs.py --metric e2e a.json c.json                                   # the end-to-end arm, strict

Ollama samples (temperature 0.2), so a run is one draw: ``--seed`` fixes the draw (run k: SEED + k - 1), ``--runs``
repeats the translation (detection and OCR are computed once); every run is kept in the results
(``translation.run_results``), with the speed of its requests (Ollama's own counts) and the model's place in GPU
memory.

The results (numbers, the model, the settings; never text) go to
``~/.taslation/datasets/openmantra/results/<date>-<time>.json``. Page images stay in memory (``--scan`` keeps
regions, masks and the OCR's text, no image). Nothing goes over the
network but the local Ollama server (the socket guard is installed first), and nothing is written to TASlation's
state (no cache, no annotations).
"""

from __future__ import annotations

import argparse
import json
import numbers
import re
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import openmantra  # noqa: E402
from ocr_gold import RIGHT, WRONG, cer, iou, norm  # noqa: E402 - the gold-set scorer's CER and normalisation
from taslation import netguard  # noqa: E402
from taslation.config import Settings  # noqa: E402

IOU = 0.5
MODES = ("book", "page")
GEOMETRIES = ("detected", "gold")
ARMS = ("official", "e2e", "both")
REASONS = ("small", "rendering", "long", "short", "ocr", "spelling")  # taslation.review.REASONS
REFERENCE = "en"  # which gold translation the lines are scored against ("en", or "zh": --target)
SCAN_VERSION = 1  # of the ``--scan`` file: another one is made again

Box = tuple[int, int, int, int]


# ---------------------------------------------------------------------------------------- the gold lines' kinds
# These are the measure's own definitions, fixed so that a change to the app cannot move what is measured.
_NOT_WORD = "ー一"  # a long dash, and the kanji "one" that lettering uses for one
_OPEN_TRAIL = "…‥・.。、,ー～~―-─ 　"  # what may follow the last word of a line that goes on
_CLOSED = "。！？!?」』)）"  # a sentence end
_OPEN_ENDINGS = tuple(sorted(("が", "を", "に", "で", "と", "へ", "は", "も", "の", "や", "から", "まで", "より", "けど",
                              "けれど", "けども", "けれども", "のに", "ので", "て", "し", "ば", "たら", "なら", "ながら", "とか",
                              "って", "だって", "でも"), key=len, reverse=True))


def worded(text: str) -> bool:
    """Whether a gold line holds a word: a letter, kana, kanji or digit. "...", "!?", a long dash alone do not."""
    return any(ch.isalnum() and ch not in _NOT_WORD for ch in norm(text))


def ends_open(text: str) -> bool:
    """Whether a line's Japanese ends on a particle or a connective with no sentence end after it (a sentence going
    on in the next bubble, as a rule): its last word, dots, dashes and commas after it aside, is one of
    `_OPEN_ENDINGS`, and no 。！？!? closes it."""
    t = "".join(str(text).split())
    if not worded(t):
        return False
    s = t.rstrip(_OPEN_TRAIL)
    return bool(s) and s[-1] not in _CLOSED and s.endswith(_OPEN_ENDINGS)


def _letters(text: str) -> str:
    import unicodedata

    return "".join(ch for ch in unicodedata.normalize("NFKD", text.lower()) if "a" <= ch <= "z")


def _romaji_key(latin: str) -> str:
    """A romanisation compared loosely: no h (えっ "Eh"), no vowel or consonant written twice (ええ "Ee", "E")."""
    return re.sub(r"(.)\1+", r"\1", latin.replace("h", ""))


def bare_romanisation(source: str, output: str) -> bool:
    """Whether *output* is nothing but the romaji of *source*, a line of 1-3 kana (punctuation aside): "Nani" for
    なに, "Eh" for えっ."""
    import jaconv

    kana = "".join(ch for ch in norm(source) if ch.isalnum() and ch != "ー")
    if not 1 <= len(kana) <= 3 or not all("ぁ" <= ch <= "ヿ" for ch in kana):
        return False
    romaji = jaconv.kana2alphabet(jaconv.kata2hira(kana)).replace("xtsu", "").replace("-", "")
    out = _letters(output)
    return bool(out) and bool(_letters(romaji)) and _romaji_key(out) == _romaji_key(_letters(romaji))


# ------------------------------------------------------------------------------------------------- scoring
def chrf(hyp: str, ref: str, n_max: int = 6, beta: float = 2.0) -> float:
    """chrF as the model knockouts computed it (character n-grams 1 to *n_max*, spaces dropped, case folded,
    precision and recall averaged over the orders, then F-beta): 0-100, 0 when either side is empty."""
    h, r = hyp.replace(" ", "").lower(), ref.replace(" ", "").lower()
    if not h or not r:
        return 0.0
    precs, recs = [], []
    for n in range(1, n_max + 1):
        hg = Counter(h[i:i + n] for i in range(len(h) - n + 1))
        rg = Counter(r[i:i + n] for i in range(len(r) - n + 1))
        if not hg or not rg:
            continue
        hit = sum((hg & rg).values())
        precs.append(hit / max(1, sum(hg.values())))
        recs.append(hit / max(1, sum(rg.values())))
    if not precs:
        return 0.0
    pr, rc = sum(precs) / len(precs), sum(recs) / len(recs)
    if pr + rc == 0:
        return 0.0
    return 100 * (1 + beta ** 2) * pr * rc / (beta ** 2 * pr + rc)


def _is_box(value: Any) -> bool:
    return len(value) == 4 and all(isinstance(v, numbers.Real) for v in value)


def match(gold: Sequence[Box], regions: Sequence[Any], threshold: float = IOU) -> list[tuple[int, int, float]]:
    """Gold boxes and regions paired one to one, the largest overlaps first: (gold index, region index, IoU) for
    every pair at *threshold* or over. A region is a box or several boxes (its bubble and its lettering); it
    overlaps a gold box as much as the best of them."""
    pairs: list[tuple[float, int, int]] = []
    for gi, g in enumerate(gold):
        for ri, region in enumerate(regions):
            boxes = [region] if _is_box(region) else list(region)
            v = max((iou(list(g), list(b)) for b in boxes), default=0.0)
            if v >= threshold:
                pairs.append((v, gi, ri))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_g: set[int] = set()
    used_r: set[int] = set()
    out: list[tuple[int, int, float]] = []
    for v, gi, ri in pairs:
        if gi in used_g or ri in used_r:
            continue
        used_g.add(gi)
        used_r.add(ri)
        out.append((gi, ri, v))
    return sorted(out)


def prf(matched: int, found: int, gold: int) -> dict[str, float]:
    precision = matched / found if found else 0.0
    recall = matched / gold if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def cer_stats(pairs: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Per-line CERs with their reference lengths, [(cer, characters), ...]: the mean, the mean with each line
    capped at 1, the corpus CER (all edits over all reference characters), lines right (CER <= 0.1) and wrong
    (>= 0.5), as ocr_gold.py counts them."""
    n = len(pairs)
    if not n:
        return {"n": 0}
    chars = sum(int(c) for _e, c in pairs)
    return {"n": n, "mean": round(sum(e for e, _c in pairs) / n, 4),
            "capped": round(sum(min(1.0, e) for e, _c in pairs) / n, 4),
            "corpus": round(sum(e * c for e, c in pairs) / chars, 4) if chars else 0.0,
            "right": sum(1 for e, _c in pairs if e <= RIGHT), "wrong": sum(1 for e, _c in pairs if e >= WRONG)}


def summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The scores of a group of page rows (see `score_page`, `score_lines`)."""
    gold = sum(r["gold"] for r in rows)
    gold_w = sum(r.get("gold_worded", r["gold"]) for r in rows)  # (a row from before has every box counted)
    cands = sum(r["candidates"] for r in rows)
    cand_matched = sum(r["candidates_matched"] for r in rows)
    cand_matched_w = sum(r.get("candidates_matched_worded", r["candidates_matched"]) for r in rows)
    out: dict[str, Any] = {"pages": len(rows), "gold": gold, "gold_worded": gold_w, "candidates": cands,
                           "candidates_matched": cand_matched,
                           "candidate_recall": prf(cand_matched_w, cands, gold_w)["recall"],
                           "candidate_recall_all": prf(cand_matched, cands, gold)["recall"],
                           "candidate_precision": prf(cand_matched, cands, gold)["precision"]}
    if rows and all("found" in r for r in rows):
        found = sum(r["found"] for r in rows)
        matched = sum(r["found_matched"] for r in rows)
        matched_w = sum(r.get("found_matched_worded", r["found_matched"]) for r in rows)
        precision = prf(matched, found, gold)["precision"]  # a region on a punctuation-only box is found right
        recall = prf(matched_w, found, gold_w)["recall"]
        f1 = round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
        old = prf(matched, found, gold)
        out.update({"found": found, "matched": matched, "matched_worded": matched_w, "precision": precision,
                    "recall": recall, "f1": f1, "recall_all": old["recall"], "f1_all": old["f1"]})
    if any("gold_ocr" in r for r in rows):
        out["ocr_gold"] = cer_stats([p for r in rows for p in r.get("gold_ocr", [])])
        out["ocr_matched"] = cer_stats([p for r in rows for p in r.get("matched_ocr", [])])
    for key, name in (("lines", "translation"), ("e2e_lines", "e2e")):
        if any(key in r for r in rows):
            out[name] = line_summary([ln for r in rows for ln in r.get(key, [])])
    return out


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def line_summary(lines: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The scores of scored lines (`score_lines`, `score_e2e`): the mean chrF (end to end: strict, every line, and
    lenient, the matched ones), the review's flags, and the kinds of lines (`ends_open`, `bare_romanisation`)."""
    reasons = Counter(f for ln in lines for f in ln["flags"])
    flagged = sum(1 for ln in lines if ln["flags"])
    open_ = [ln["chrf"] for ln in lines if ln.get("open")]
    closed = [ln["chrf"] for ln in lines if not ln.get("open") and ln.get("worded", True)]
    out: dict[str, Any] = {
        "lines": len(lines), "real": sum(1 for ln in lines if ln["real"]), "chrf": _mean([ln["chrf"] for ln in lines]),
        "flagged": flagged, "flagged_share": round(flagged / len(lines), 4) if lines else 0.0,
        "by_reason": {k: reasons.get(k, 0) for k in REASONS},
        "open": {"lines": len(open_), "chrf": _mean(open_), "rest_lines": len(closed), "rest_chrf": _mean(closed)},
        "romanised": sum(1 for ln in lines if ln.get("romanised")),
    }
    if any("matched" in ln for ln in lines):
        matched = [ln["chrf"] for ln in lines if ln.get("matched")]
        out.update({"matched": len(matched), "lenient": _mean(matched), "strict": out["chrf"]})
    return out


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Scores per series (in the order the rows have them) and over all rows."""
    names = list(dict.fromkeys(r["series"] for r in rows))
    return {"by_series": {name: summary([r for r in rows if r["series"] == name]) for name in names},
            "all": summary(rows)}


# ------------------------------------------------------------------------------------------- the pipeline
def _clamp(box: Box, size: tuple[int, int]) -> Box:
    w, h = size
    return (max(0, min(w, box[0])), max(0, min(h, box[1])), max(0, min(w, box[2])), max(0, min(h, box[3])))


def _read(ocr: Any, crop: Any) -> str:
    settle = getattr(ocr, "settle", None)
    if settle is not None:
        return settle(crop, ocr.read_chars(crop)).text
    reader = getattr(ocr, "read_with_confidence", None)
    return reader(crop)[0] if reader is not None else ocr.read(crop)


def ja_line(bubble: openmantra.Bubble) -> str:
    """The gold Japanese as the OCR would hand it over: no spaces, no line breaks."""
    return "".join(bubble.ja.split())


def score_page(pipeline: Any, ocr: Any, page: openmantra.Page, image: Any, threshold: float = IOU,
               geometry: str = "detected") -> tuple[dict[str, Any], list[Any], list[dict[str, Any]]]:
    """Detection (and, with *ocr*, the OCR) of one page: its row of numbers; per gold box the geometry its
    translation is set in (the matched detected region's bubble box, mask, text box, lettering box and kind; None
    where the gold box stands in); and, with *ocr*, the regions read as Japanese text in the pipeline's reading
    order, what the end-to-end arm translates (`e2e_items`: their text, geometry and matched gold box)."""
    t0 = time.monotonic()
    res = pipeline.process(image, translate=False, use_cache=False)
    seconds = {"pipeline": round(time.monotonic() - t0, 3)}
    gold = [b.box for b in page.bubbles]
    has_word = [worded(b.ja) for b in page.bubbles]
    regions = list(res.regions)
    candidates = match(gold, [(r.bbox, r.text_box) for r in regions], threshold)
    row: dict[str, Any] = {"series": page.series, "page": page.index, "size": list(image.size), "gold": len(gold),
                           "gold_worded": sum(has_word), "candidates": len(regions),
                           "candidates_matched": len(candidates),
                           "candidates_matched_worded": sum(1 for gi, _ri, _v in candidates if has_word[gi])}
    items: list[dict[str, Any]] = []
    if ocr is not None:
        found = [r for r in regions if r.status == "untranslated" and r.source_text]
        pairs = match(gold, [(r.bbox, r.text_box) for r in found], threshold)
        row["found"] = len(found)
        row["found_matched"] = len(pairs)
        row["found_matched_worded"] = sum(1 for gi, _ri, _v in pairs if has_word[gi])
        row["matched_ocr"] = [[round(cer(found[ri].source_text, page.bubbles[gi].ja), 4), len(norm(page.bubbles[gi].ja))]
                              for gi, ri, _v in pairs if norm(page.bubbles[gi].ja)]
        items = e2e_items(found, pairs)
        t1 = time.monotonic()
        gold_ocr = []
        for b in page.bubbles:
            if not norm(b.ja):
                continue
            x0, y0, x1, y1 = _clamp(b.box, image.size)
            text = _read(ocr, image.crop((x0, y0, x1, y1))) if x1 - x0 >= 2 and y1 - y0 >= 2 else ""
            gold_ocr.append([round(cer(text, b.ja), 4), len(norm(b.ja))])
        row["gold_ocr"] = gold_ocr
        seconds["gold_ocr"] = round(time.monotonic() - t1, 3)
    geo: list[Any] = [None] * len(gold)
    if geometry == "detected":
        for gi, ri, _v in candidates:
            r = regions[ri]
            geo[gi] = (r.bbox, r.mask, r.text_box, r.letter_box, r.kind)
    row["geometry_detected"] = sum(1 for g in geo if g is not None)
    row["seconds"] = seconds
    return row, geo, items


def e2e_items(found: Sequence[Any], pairs: Sequence[tuple[int, int, float]]) -> list[dict[str, Any]]:
    """The regions *found* (read as Japanese) in the pipeline's reading order (page unit, then order), each with its
    OCR text, its geometry and the gold box *pairs* matched to it (None for a region no gold box has)."""
    gold_of = {ri: gi for gi, ri, _v in pairs}
    ranked = sorted(range(len(found)), key=lambda ri: (getattr(found[ri], "unit", 0), found[ri].order, ri))
    return [{"text": found[ri].source_text, "gold": gold_of.get(ri),
             "geo": (found[ri].bbox, found[ri].mask, found[ri].text_box, found[ri].letter_box, found[ri].kind)}
            for ri in ranked]


def gold_geometry(box: Box) -> tuple[Box, Any, Box, None, str]:
    """The gold box standing in for a bubble: the whole box is room for the translation."""
    import numpy as np

    w, h = max(1, box[2] - box[0]), max(1, box[3] - box[1])
    return (box, np.full((h, w), 255, np.uint8), box, None, "bubble")


def gold_items(page: openmantra.Page, geo: Sequence[Any]) -> list[dict[str, Any]]:
    """What the official arm translates: every gold line with Japanese, in gold order, as the OCR would hand it
    over (`ja_line`), set in its geometry (`score_page`), or the gold box."""
    return [{"text": ja_line(b), "gold": i, "geo": geo[i] or gold_geometry(b.box)}
            for i, b in enumerate(page.bubbles) if ja_line(b)]


def _hyp(out: str) -> str:
    from taslation.render.lettering import strip_marks

    return " ".join(strip_marks(out).split()) if out else ""


def _line(b: openmantra.Bubble, out: str, flags: Sequence[str], names: dict[str, Any] | None,
          src: str = "") -> dict[str, Any]:
    """One gold line scored: chrF against the reference, the review's flags and the line's kinds (the Japanese
    *src* the translator was given, when not the gold line's own)."""
    hyp = _hyp(out)
    if REFERENCE == "zh":  # Chinese is written without spaces: neither side keeps any
        ref, hyp = "".join(b.zh.split()), "".join(hyp.split())
    else:
        ref = " ".join(b.en.split())
    ja = ja_line(b)
    line: dict[str, Any] = {"chrf": round(chrf(hyp, ref), 2) if hyp else 0.0, "real": bool(hyp),
                            "flags": sorted(set(flags)), "worded": worded(ja), "open": ends_open(ja),
                            "romanised": bool(hyp) and bare_romanisation(src or ja, hyp)}
    if names:
        hits = name_hits(ja, ref, hyp, names)
        if hits:
            line["names"] = hits
    return line


def score_lines(page: openmantra.Page, outputs: dict[int, tuple[str, list[str]]],
                names: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """chrF, flags and kinds of every gold line with Japanese (*outputs*: bubble index -> (translation or "",
    flags)); *names*: the series' names (`name_hits`)."""
    lines = []
    for i, b in enumerate(page.bubbles):
        if not ja_line(b):
            continue
        out, flags = outputs.get(i, ("", []))
        lines.append(_line(b, out, flags, names))
    return lines


def score_e2e(page: openmantra.Page, items: Sequence[dict[str, Any]], outputs: dict[int, tuple[str, list[str]]],
              names: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The end-to-end arm's lines: every gold line with Japanese (as `score_lines`), scored with the translation of
    the region matched to it (*items*, *outputs*: item index -> (translation, flags)), "matched" False and chrF 0
    for a line no region matched; the regions with no gold box are left out."""
    by_gold = {it["gold"]: k for k, it in enumerate(items) if it["gold"] is not None}
    lines = []
    for i, b in enumerate(page.bubbles):
        if not ja_line(b):
            continue
        k = by_gold.get(i)
        out, flags = outputs.get(k, ("", [])) if k is not None else ("", [])
        line = _line(b, out, flags, names, items[k]["text"] if k is not None else "")
        line["matched"] = k is not None
        lines.append(line)
    return lines


# --------------------------------------------------------------------------------------------------- names
def name_hits(ja: str, ref: str, hyp: str, names: dict[str, Any]) -> list[list[int]]:
    """The names of a series a gold line names: those whose Japanese is in *ja* and whose reference rendering is in
    the reference *ref* (the line really names them). *names*: ``{ja: [[the reference rendering and the forms
    accepted for it], [other renderings seen]]}`` (`load_names`). Per name [its index, the rendering *hyp* uses
    (0 the reference's, k the k-th other, -1 none of them), 1 when that is the reference's]. Indices only: no text."""
    out = []
    flat_ref, flat_hyp = _letters(ref), _letters(hyp)
    for n, (name, (accepted, others)) in enumerate(names.items()):
        if name not in ja or not accepted or _letters(accepted[0])[:4] not in flat_ref:
            continue
        if any(_letters(a) and _letters(a) in flat_hyp for a in accepted):
            used = 0
        else:
            used = next((k + 1 for k, o in enumerate(others) if _letters(o) and _letters(o) in flat_hyp), -1)
        out.append([n, used, int(used == 0)])
    return out


def load_names(path: Path | None) -> dict[str, dict[str, Any]]:
    """The names file: ``{series: {ja: [[reference rendering, accepted forms...], [other renderings...]]}}`` (a
    bare string, or one list of strings, is the reference's forms alone)."""
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for series, table_ in data.items():
        out[series] = {}
        for ja, v in table_.items():
            if isinstance(v, str):
                v = [[v], []]
            elif v and isinstance(v[0], str):
                v = [list(v), []]
            out[series][ja] = [list(v[0]), list(v[1]) if len(v) > 1 else []]
    return out


def name_summary(lines: Sequence[dict[str, Any]], series_of: Sequence[str]) -> dict[str, Any]:
    """How the names of *lines* (each of the series *series_of* names) are rendered: the lines naming one, the share
    rendered as the reference has it, and the consistency: per name the lines with its most frequent known
    rendering (a line with none of them counts against it), over all the lines of the names named twice or more."""
    per: dict[tuple[str, int], Counter] = {}
    total = right = 0
    for ln, series in zip(lines, series_of):
        for n, used, ok in ln.get("names", []):
            total += 1
            right += ok
            per.setdefault((series, n), Counter())[used] += 1
    multi = [c for c in per.values() if sum(c.values()) >= 2]
    kept = sum(max((v for u, v in c.items() if u >= 0), default=0) for c in multi)
    seen = sum(sum(c.values()) for c in multi)
    return {"lines": total, "as_reference": right, "share": round(right / total, 4) if total else 0.0,
            "names": len(per), "consistent": round(kept / seen, 4) if seen else 0.0, "consistency_lines": seen}


# --------------------------------------------------------------------------------------------- translation
def _keep_stats(tr: Any) -> None:
    """Ollama's statistics of every request of *tr* kept in ``tr.stats_log`` (the PLaMo translator keeps them itself
    once given the list; the chat translator's requests are counted around its ``_chat``)."""
    tr.stats_log = []
    if hasattr(type(tr), "_generate"):  # PlamoTranslator
        return
    chat = tr._chat

    def counted(*a: Any, **k: Any) -> Any:
        out = chat(*a, **k)
        tr.stats_log.append(dict(tr.last_stats))
        return out

    tr._chat = counted


def speed_of(requests: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Requests, tokens and tokens a second (Ollama's own counts) of *requests*."""
    ev = sum(x.get("eval_count") or 0 for x in requests)
    evd = sum(x.get("eval_duration") or 0 for x in requests) / 1e9
    pe = sum(x.get("prompt_eval_count") or 0 for x in requests)
    ped = sum(x.get("prompt_eval_duration") or 0 for x in requests) / 1e9
    return {"requests": len(requests), "eval_tokens": ev, "eval_tok_per_s": round(ev / evd, 1) if evd else None,
            "prompt_tokens": pe, "prompt_tok_per_s": round(pe / ped, 1) if ped else None}


def _loaded(tr: Any, model: str) -> dict[str, Any]:
    """Ollama's /api/ps of *model* while it is loaded: its size and how much of it is in GPU memory."""
    from taslation.translate import TranslationError

    try:
        entry = tr._loaded(model)
    except TranslationError:
        return {}
    return {k: entry.get(k) for k in ("size", "size_vram", "context_length")} if entry else {}


class _Stats:
    def __init__(self) -> None:
        self.requests_failed = 0
        self.left_incomplete = 0


def make_sheet(series: str, language: str, entry: dict[str, Any] | None) -> Any:
    """The series sheet ``--glossary`` gives *series* (an `annotations.Glossary` kept nowhere): its characters and
    terms; None without one."""
    if not entry:
        return None
    from taslation.annotations import CharacterSheet, Glossary

    sheet = Glossary(Path("eval-sheet.json"), series, language)
    for ja, rendering in (entry.get("characters") or {}).items():
        sheet.set_character(CharacterSheet(name=ja, rendering=rendering))
    for ja, rendering in (entry.get("terms") or {}).items():
        sheet.set(ja, rendering)
    return sheet


def _eval_pipeline(settings: Settings, translator: Any, sheet: Any = None) -> Any:
    """The pipeline with `commit_unit` keeping the batch's translations and flags in memory (there is no cache),
    and *sheet* as the book's series sheet, as the window gives it (`Pipeline.glossary` and its text)."""
    from taslation.pipeline import Pipeline

    class EvalPipeline(Pipeline):
        def __init__(self) -> None:
            super().__init__(settings, ocr=None, translator=translator, cache=None)
            self.kept: dict[str, dict[int, tuple[str, list[str]]]] = {}
            if sheet is not None:
                self.glossary, self.glossary_text = sheet, sheet.format()

        def commit_unit(self, unit: Any, translations: dict[int, str],
                        flags: dict[int, list[str]] | None = None) -> bool:
            got = self.kept.setdefault(unit.fingerprint, {})
            for i, text in translations.items():
                got[i] = (text, list((flags or {}).get(i, [])))
            return all(i in translations for i in range(len(unit.japanese())))  # complete, as commit_unit judges it

    return EvalPipeline()


def page_size(page: openmantra.Page, page_items: Sequence[dict[str, Any]]) -> tuple[int, int]:
    """The page's size as far as its boxes show it: the page unit's box, with no image at hand."""
    xs = [it["geo"][0][2] for it in page_items] + [b.box[2] for b in page.bubbles] + [1]
    ys = [it["geo"][0][3] for it in page_items] + [b.box[3] for b in page.bubbles] + [1]
    return max(xs), max(ys)


def translate_series_book(settings: Settings, translator: Any, series: str, pages: list[openmantra.Page],
                          geos: list[list[Any]], stats: _Stats, log: Any,
                          items: list[list[dict[str, Any]]] | None = None,
                          sheet: Any = None) -> list[dict[int, tuple[str, list[str]]]]:
    """One series translated as the whole-book batch does it (`BatchReader._translation_pass`, after the reading);
    per page, item index -> (translation, flags). *items*: what each page hands the translator (`gold_items`, the
    default, or `e2e_items`); *sheet*: the series sheet (`make_sheet`)."""
    from taslation.batch import BatchReader
    from taslation.pipeline import ScannedRegion, ScannedUnit, mask_polygon, translation_room

    if items is None:
        items = [gold_items(page, geo) for page, geo in zip(pages, geos)]
    pipeline = _eval_pipeline(settings, translator, sheet)
    units = []
    for page, page_items in zip(pages, items):
        regions = []
        for it in page_items:
            bbox, mask, text_box, letter_box, kind = it["geo"]
            anchor = letter_box or text_box
            room = translation_room(mask, anchor, it["text"], settings, kind, bbox[0], bbox[1], pipeline.suggested_font)
            regions.append(ScannedRegion(bbox=bbox, text_box=anchor, poly=mask_polygon(mask), source_text=it["text"],
                                         status="untranslated", order=len(regions), kind=kind, room=room))
        units.append(ScannedUnit(index=0, box=(0, 0, *page_size(page, page_items)),
                                 fingerprint=f"{series}#{page.index}", aspect=1.0, regions=regions))

    def told(p: Any, _result: Any) -> None:
        if getattr(p.message, "code", "") == "batch.translated_chunk":
            params = p.message.params
            log(f"  {series}: run {params['chunk']}/{params['chunks']}, {params['bubbles']} lines so far, {params['seconds']:.0f} s")

    reader = BatchReader(pipeline, 0, settings, on_progress=told, context_mode=True, book=series)
    reader._translation_pass([u for u in units if u.japanese()], time.monotonic())
    stats.requests_failed += reader.progress.errors
    out = []
    for unit, page_items in zip(units, items):
        kept = pipeline.kept.get(unit.fingerprint, {})
        if len(kept) < len(page_items):
            stats.left_incomplete += 1
        out.append(dict(kept))
    return out


def translate_series_page(settings: Settings, translator: Any, series: str, pages: list[openmantra.Page],
                          geos: list[list[Any]], stats: _Stats, log: Any,
                          items: list[list[dict[str, Any]]] | None = None,
                          sheet: Any = None) -> list[dict[int, tuple[str, list[str]]]]:
    """One series translated as live reading does it (`Pipeline._translate_regions`, page by page, the last pages
    as context); per page, item index -> (translation, flags)."""
    from taslation.regions import TextRegion

    if items is None:
        items = [gold_items(page, geo) for page, geo in zip(pages, geos)]
    pipeline = _eval_pipeline(settings, translator, sheet)
    out = []
    t0 = time.monotonic()
    for page_items in items:
        regions = []
        for it in page_items:
            bbox, mask, text_box, letter_box, kind = it["geo"]
            regions.append(TextRegion(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3], mask=mask.copy(), text_box=text_box,
                                      kind=kind, source_text=it["text"], status="untranslated", letter_box=letter_box))
        if regions and pipeline._translate_regions(regions, lambda _m: None):
            stats.requests_failed += 1
        if any(r.status != "translated" for r in regions):
            stats.left_incomplete += 1
        out.append({k: (r.translated_text, list(r.flags)) for k, r in enumerate(regions) if r.status == "translated"})
    log(f"  {series}: {len(pages)} pages in {time.monotonic() - t0:.0f} s")
    return out


def translate_all(settings: Settings, translator: Any, groups: dict[str, list[openmantra.Page]],
                  rows: list[dict[str, Any]], geos: dict[tuple[str, int], list[Any]], mode: str,
                  stats: _Stats, log: Any, arm: str = "official",
                  e2e: dict[tuple[str, int], list[dict[str, Any]]] | None = None,
                  sheets: dict[str, Any] | None = None, names: dict[str, dict[str, Any]] | None = None,
                  dump: Any = None, run: int = 1) -> list[dict[str, Any]]:
    """One run of the translation over every series in the *arm* "official" (the rows' ``lines``) or "e2e" (their
    ``e2e_lines``, from *e2e*: the regions of each page, `e2e_items`): copies of *rows* with their scored lines.
    *sheets*: a series sheet per series; *names*: the names of each series (`load_names`); *dump*: a file every
    line's text goes to (``--dump``)."""
    out_rows = [dict(r) for r in rows]
    by_row = {(r["series"], r["page"]): r for r in out_rows}
    translate = translate_series_book if mode == "book" else translate_series_page
    for name, group in groups.items():
        group = [p for p in group if (p.series, p.index) in by_row]
        g = [geos[(p.series, p.index)] for p in group]
        items = ([gold_items(p, geo) for p, geo in zip(group, g)] if arm == "official"
                 else [(e2e or {}).get((p.series, p.index), []) for p in group])
        outs = translate(settings, translator, name, group, g, stats, log, items, (sheets or {}).get(name))
        series_names = (names or {}).get(name)
        for page, page_items, out in zip(group, items, outs):
            row = by_row[(page.series, page.index)]
            if arm == "official":
                by_gold = {it["gold"]: out[k] for k, it in enumerate(page_items) if k in out}
                row["lines"] = score_lines(page, by_gold, series_names)
            else:
                row["e2e_lines"] = score_e2e(page, page_items, out, series_names)
                row["e2e_extra"] = sum(1 for k, it in enumerate(page_items) if it["gold"] is None and k in out)
            if dump is not None:
                _dump(dump, arm, run, page, page_items, out)
    return out_rows


def _dump(f: Any, arm: str, run: int, page: openmantra.Page, items: Sequence[dict[str, Any]],
          out: dict[int, tuple[str, list[str]]]) -> None:
    """Every item of a page with its translation and its gold line's reference, one JSON line each (``--dump``)."""
    for k, it in enumerate(items):
        b = page.bubbles[it["gold"]] if it["gold"] is not None else None
        text, flags = out.get(k, ("", []))
        f.write(json.dumps({"arm": arm, "run": run, "series": page.series, "page": page.index, "item": k,
                            "gold": it["gold"], "src": it["text"], "ja": ja_line(b) if b else "", "hyp": _hyp(text),
                            "ref": " ".join(b.en.split()) if b else "", "flags": list(flags)},
                           ensure_ascii=False) + "\n")
    f.flush()


def series_scores(rows: Sequence[dict[str, Any]], key: str = "lines", strict: bool = True) -> dict[str, dict[str, Any]]:
    """Per series of one run: its lines, their mean chrF, and every line's chrF in page order (numbers only), what
    ``compare_runs.py`` pairs. *key*: the arm's lines ("lines", "e2e_lines"); *strict* False keeps only the lines
    a region matched (the end-to-end arm's lenient score)."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if key not in r:
            continue
        s = out.setdefault(r["series"], {"lines": 0, "chrf": 0.0, "line_chrf": []})
        s["line_chrf"].extend(ln["chrf"] for ln in r[key] if strict or ln.get("matched", True))
    for s in out.values():
        s["lines"] = len(s["line_chrf"])
        s["chrf"] = round(sum(s["line_chrf"]) / s["lines"], 4) if s["lines"] else 0.0
    return out


def arm_record(rows: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    """What a run keeps of one arm: its per-series scores (end to end: strict, and lenient as ``series_lenient``),
    the summary of its lines, and how it renders the names (`name_summary`)."""
    lines = [ln for r in rows for ln in r.get(key, [])]
    series_of = [r["series"] for r in rows for _ln in r.get(key, [])]
    rec: dict[str, Any] = {"series": series_scores(rows, key), "summary": line_summary(lines),
                           "names": name_summary(lines, series_of)}
    if key == "e2e_lines":
        rec["series_lenient"] = series_scores(rows, key, strict=False)
        rec["extra_regions"] = sum(r.get("e2e_extra", 0) for r in rows)
    return rec


# ------------------------------------------------------------------------------------------------- output
def _fmt(v: Any, pct: bool = False) -> str:
    if v is None or v == "":
        return "-"
    if isinstance(v, float):
        return f"{100 * v:.1f}" if pct else f"{v:.1f}"
    return str(v)


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    cells = [list(map(str, headers))] + [[str(c) for c in row] for row in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    lines = ["  ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths))) for r in cells]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def report(summ: dict[str, Any], iou_threshold: float) -> str:
    groups = list(summ["by_series"].items()) + [("all", summ["all"])]
    parts = []
    with_ocr = "found" in summ["all"]
    det_rows = []
    for name, s in groups:
        row = [name, s["pages"], s["gold"], s.get("gold_worded", s["gold"])]
        if with_ocr:
            row += [s["found"], s["matched"], _fmt(s["precision"], True), _fmt(s["recall"], True), _fmt(s["f1"], True),
                    _fmt(s.get("f1_all"), True)]
        row += [s["candidates"], s["candidates_matched"], _fmt(s["candidate_recall"], True)]
        det_rows.append(row)
    head = ["series", "pages", "gold", "worded"]
    head += ["read as text", "matched", "P %", "R %", "F1 %", "F1 all %"] if with_ocr else []
    head += ["candidates", "matched", "R %"]
    what = ("the regions read as Japanese text, then every region the detector proposed before the OCR judged it"
            if with_ocr else "every region the detector proposed; no OCR")
    parts.append(f"Detection (one to one, IoU >= {iou_threshold}; {what}; recall over the gold boxes with a word, "
                 "F1 all: over every gold box, as before)\n" + table(head, det_rows))
    if "ocr_gold" in summ["all"]:
        ocr_rows = []
        for name, s in groups:
            g, m = s["ocr_gold"], s["ocr_matched"]
            ocr_rows.append([name, g["n"], _fmt(g.get("mean"), True), _fmt(g.get("corpus"), True), g.get("right", "-"),
                             g.get("wrong", "-"), m["n"], _fmt(m.get("mean"), True), _fmt(m.get("corpus"), True)])
        parts.append("OCR, CER % against the gold Japanese: on the gold boxes | on the matched regions\n" +
                     table(["series", "lines", "mean", "corpus", "right", "wrong", "lines", "mean", "corpus"], ocr_rows))
    if "translation" in summ["all"]:
        tr_rows = []
        for name, s in groups:
            t = s["translation"]
            tr_rows.append([name, t["lines"], t["real"], _fmt(t["chrf"]), _fmt(t["open"]["chrf"]),
                            _fmt(t["open"]["rest_chrf"]), t["romanised"], _fmt(t["flagged_share"], True)]
                           + [t["by_reason"][k] for k in ("small", "long", "short", "spelling", "rendering")])
        parts.append("Translation (official arm: gold text, gold order), chrF against the professional English; open: "
                     "the lines ending on a particle or connective, rest: the other worded lines; romanised: bare romaji "
                     "of 1-3 kana; lines the review flags\n" +
                     table(["series", "lines", "real", "chrF", "open", "rest", "romanised", "flagged %", "small", "long",
                            "short", "spelling", "rendering"], tr_rows))
    if "e2e" in summ["all"]:
        e_rows = []
        for name, s in groups:
            t = s["e2e"]
            e_rows.append([name, t["lines"], t["matched"], _fmt(t["strict"]), _fmt(t["lenient"]), _fmt(t["open"]["chrf"]),
                           t["romanised"], _fmt(t["flagged_share"], True)])
        parts.append("End to end (the pipeline's regions, order and OCR text): strict over every gold line, lenient "
                     "over the matched ones\n" +
                     table(["series", "lines", "matched", "strict", "lenient", "open", "romanised", "flagged %"], e_rows))
    return "\n\n".join(parts)


def names_report(record: dict[str, Any]) -> str:
    """One line on the names of a run's arm (`name_summary`)."""
    n = record["names"]
    if not n["lines"]:
        return ""
    return (f"names: {n['lines']} lines name one of {n['names']}; as the reference renders them {_fmt(n['share'], True)} %; "
            f"consistent {_fmt(n['consistent'], True)} % (of {n['consistency_lines']} lines)")


def _settings_record(s: Settings) -> dict[str, Any]:
    out = {}
    for f in fields(s):
        v = getattr(s, f.name)
        if isinstance(v, (bool, int, float, str, tuple)) and f.name not in ("font_path",):
            out[f.name] = list(v) if isinstance(v, tuple) else v
    return out


def _archive_sha(root: Path) -> str:
    try:
        m = re.search(r"SHA-256 `([0-9a-f]{64})`", (root / "SOURCE.md").read_text(encoding="utf-8"))
    except OSError:
        return ""
    return m.group(1) if m else ""


def _file_sha(path: Path) -> str:
    import hashlib

    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def scan_key(root: Path, s: Settings, args: Any, pages: Sequence[openmantra.Page]) -> dict[str, Any]:
    """What a ``--scan`` file must have been made with to be read again: the dataset, the pages, and the settings
    and options the detection and the OCR depend on."""
    detect = {k: v for k, v in _settings_record(s).items()
              if not k.startswith(("ollama", "translat", "chunk", "context", "lookahead", "target", "batch"))}
    return {"version": SCAN_VERSION, "archive": _archive_sha(root), "annotation": _file_sha(root / "annotation.json"),
            "pages": [[p.series, p.index] for p in pages], "ocr": not args.no_ocr, "geometry": args.geometry,
            "iou": args.iou, "settings": detect}


def load_scan(path: Path, key: dict[str, Any]) -> dict[str, Any] | None:
    """The detection and OCR a ``--scan`` file holds, when it was made with *key*; else None."""
    import pickle

    try:
        with open(path, "rb") as f:
            data = pickle.load(f)  # (a file this tool wrote, on this computer)
    except (OSError, pickle.UnpicklingError, EOFError):
        return None
    return data if isinstance(data, dict) and data.get("key") == key else None


def save_scan(path: Path, key: dict[str, Any], rows: list[dict[str, Any]], geos: dict[tuple[str, int], list[Any]],
              e2e: dict[tuple[str, int], list[dict[str, Any]]], seconds: float) -> None:
    import pickle

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        pickle.dump({"key": key, "rows": rows, "geos": geos, "e2e": e2e, "seconds": seconds}, f)
    tmp.replace(path)


def load_glossary(path: Path | None, language: str) -> dict[str, Any]:
    """``--glossary``: a series sheet per series (`make_sheet`)."""
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {series: make_sheet(series, language, entry) for series, entry in data.items()}


# ----------------------------------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    netguard.install()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=openmantra.DEFAULT_ROOT, help="the dataset folder")
    ap.add_argument("--series", action="append", help="only this series (repeatable)")
    ap.add_argument("--pages", type=int, default=0, help="only the first N pages of every series")
    ap.add_argument("--no-ocr", action="store_true", help="no OCR: detection candidates only, no CER")
    ap.add_argument("--no-translate", action="store_true", help="no translation (Ollama is not needed)")
    ap.add_argument("--mode", choices=MODES, default="book", help="book: as the whole-book batch (default); page: as live reading")
    ap.add_argument("--arm", choices=ARMS, default="official",
                    help="official: gold text in gold order (default); e2e: the pipeline's regions, order and OCR text; both")
    ap.add_argument("--geometry", choices=GEOMETRIES, default="detected",
                    help="where each line is set: the matched detected region, else the gold box (default); or always the gold box")
    ap.add_argument("--chunk-bubbles", type=int, help="the setting of that name: lines per request in book mode (default: TASlation's)")
    ap.add_argument("--model", help="the Ollama model (default: the one the target language chooses, as the app)")
    ap.add_argument("--target", choices=("en", "zh"), default="en",
                    help="the target language and the gold translation scored against (zh: Traditional Chinese)")
    ap.add_argument("--detect-model", choices=("auto", "on", "off"), help="the setting of that name (default: TASlation's)")
    ap.add_argument("--no-slant", action="store_true", help="slant_text off: every region upright, as before slants")
    ap.add_argument("--runs", type=int, default=1, help="translate every series N times (default 1); each run is kept")
    ap.add_argument("--seed", type=int,
                    help="Ollama's sampling seed (run k uses SEED + k - 1); default none, a fresh draw every time, as the app")
    ap.add_argument("--iou", type=float, default=IOU, help="least overlap for a region to count as a gold box")
    ap.add_argument("--scan", type=Path, help="keep the detection and the OCR in this file and reuse them (no image)")
    ap.add_argument("--glossary", type=Path, help="a series sheet per series, JSON {series: {characters: {}, terms: {}}}")
    ap.add_argument("--names", type=Path, help="the names to score, JSON {series: {ja: [[reference, ...], [others]]}}")
    ap.add_argument("--dump", type=Path, help="write every line's Japanese, translation and reference here (not printed)")
    ap.add_argument("--out", type=Path, help="results file (default: <root>/results/<date>-<time>.json)")
    args = ap.parse_args(argv)
    if args.runs < 1:
        raise SystemExit("--runs must be 1 or more")
    arms = ["official", "e2e"] if args.arm == "both" else [args.arm]
    if "e2e" in arms and args.no_ocr:
        raise SystemExit("the end-to-end arm needs the OCR (leave out --no-ocr)")

    started = datetime.now()
    t_start = time.monotonic()
    pages = openmantra.load(args.root, args.series)
    if args.series:
        unknown = sorted(set(args.series) - set(openmantra.series_names(pages)))
        if unknown:
            raise SystemExit(f"unknown series: {', '.join(unknown)}")
    groups = openmantra.by_series(pages)
    if args.pages:
        groups = {k: v[: args.pages] for k, v in groups.items()}
    pages = [p for v in groups.values() for p in v]
    if not pages:
        raise SystemExit("no pages")
    s = Settings()
    if args.model:
        s.ollama_model = args.model
    if args.chunk_bubbles:
        s.chunk_bubbles = args.chunk_bubbles
    if args.detect_model:
        s.detect_model = args.detect_model
    if args.no_slant:
        s.slant_text = False
    global REFERENCE
    REFERENCE = args.target
    if args.target == "zh":
        s.target_language = "Chinese (Traditional)"  # the OpenMantra Chinese is traditional
    s.validate()
    sheets = load_glossary(args.glossary, s.target_language)
    names = load_names(args.names)
    from taslation import health
    from taslation.translate.models import choose

    model_name = choose(s.ollama_model, s.target_language, health.installed_models(s.ollama_url)).name
    print(f"OpenMantra: {len(groups)} series, {len(pages)} pages, {sum(len(p.bubbles) for p in pages)} gold boxes; "
          f"OCR {'off' if args.no_ocr else 'on'}, translation {'off' if args.no_translate else model_name + ' (' + args.mode + ' mode, ' + args.arm + ')'}"
          + (f", a series sheet for {len(sheets)} series" if sheets else ""), flush=True)

    rows: list[dict[str, Any]] = []
    geos: dict[tuple[str, int], list[Any]] = {}
    e2e: dict[tuple[str, int], list[dict[str, Any]]] = {}
    key = scan_key(args.root, s, args, pages) if args.scan else None
    scanned = load_scan(args.scan, key) if args.scan and args.scan.exists() else None
    if scanned is not None:
        rows, geos, e2e = scanned["rows"], scanned["geos"], scanned["e2e"]
        seconds = {"detection_ocr": scanned["seconds"], "scan_reused": True}
        print(f"detection and OCR from {args.scan}", flush=True)
    else:
        from taslation.pipeline import Pipeline

        ocr = None
        if not args.no_ocr:
            from taslation.ocr import Readers

            t0 = time.monotonic()
            ocr = Readers(s.models_dir, s.ocr_threads)
            print(f"OCR model loaded in {time.monotonic() - t0:.1f} s", flush=True)
        detector = Pipeline(s, ocr=ocr, translator=None, cache=None)
        t0 = time.monotonic()
        for page in pages:
            try:
                image = page.open()
            except OSError as e:
                print(f"  {page.series} p{page.index}: image unreadable ({type(e).__name__})", flush=True)
                continue
            row, geo, items = score_page(detector, ocr, page, image, args.iou, args.geometry)
            del image
            rows.append(row)
            geos[(page.series, page.index)] = geo
            e2e[(page.series, page.index)] = items
            print(f"  {page.series} p{page.index}: gold {row['gold']}, candidates {row['candidates']} ({row['candidates_matched']} matched)"
                  + (f", read as text {row['found']} ({row['found_matched']} matched)" if "found" in row else "")
                  + f"  [{sum(row['seconds'].values()):.1f} s]", flush=True)
        seconds = {"detection_ocr": round(time.monotonic() - t0, 1)}
        if args.scan:
            save_scan(args.scan, key, rows, geos, e2e, seconds["detection_ocr"])

    translation: dict[str, Any] = {}
    dump = open(args.dump, "w", encoding="utf-8") if args.dump and not args.no_translate else None
    if not args.no_translate:
        from taslation.translate.models import make_translator

        tr = make_translator(s, model_name, seed=args.seed)  # the app's own translator for the model
        _keep_stats(tr)
        if not tr.ping():
            translation = {"error": f"Ollama is not running at {s.ollama_url}"}
        elif not tr.has_model(model_name):
            translation = {"error": f"the model {model_name} is not installed"}
        else:
            translation = {"model": model_name, "translator": type(tr).__name__, "ollama": tr.version(),
                           "mode": args.mode, "geometry": args.geometry, "target": args.target, "seed": args.seed,
                           "runs": args.runs, "arms": arms, "sheets": sorted(sheets)}
            t0 = time.monotonic()
            log = lambda msg: print(msg, flush=True)  # noqa: E731
            run_records = []
            for k in range(args.runs):
                record: dict[str, Any] = {"run": k + 1}
                for arm in arms:
                    if args.seed is not None:
                        tr.seed = args.seed + k
                    asked = getattr(tr, "_asked", None)  # PLaMo draws a line asked for before anew: every arm
                    if asked is not None:  # and run starts afresh, so that a seed gives the same draws in each
                        asked.clear()
                    log(f"run {k + 1}/{args.runs}, {arm} arm" + (f", seed {tr.seed}" if args.seed is not None else ""))
                    stats = _Stats()
                    t_run = time.monotonic()
                    first_request = len(tr.stats_log)
                    run_rows = translate_all(s, tr, groups, rows, geos, args.mode, stats, log, arm, e2e, sheets, names,
                                             dump, k + 1)
                    speed = speed_of(tr.stats_log[first_request:])
                    speed["ps"] = _loaded(tr, model_name)
                    speed["s_per_page"] = round((time.monotonic() - t_run) / max(1, len(rows)), 2)
                    log(f"speed: {speed}")
                    lines_key = "lines" if arm == "official" else "e2e_lines"
                    arm_rec = {"seed": tr.seed, "requests_failed": stats.requests_failed,
                               "pages_incomplete": stats.left_incomplete, "seconds": round(time.monotonic() - t_run, 1),
                               "speed": speed, **arm_record(run_rows, lines_key)}
                    names_line = names_report(arm_rec)
                    if names_line:
                        log(names_line)
                    if arm == "official":  # the run's own fields, as before the end-to-end arm
                        record.update({"seed": tr.seed, "notes": "none", "notes_sha256": "", **arm_rec,
                                       "summary": summarize(run_rows)})
                    else:
                        record["e2e"] = arm_rec
                        record.setdefault("seed", tr.seed)
                        record.setdefault("summary", summarize(run_rows))
                    if k == 0:
                        for r, rr in zip(rows, run_rows):
                            r[lines_key] = rr[lines_key]
                            if "e2e_extra" in rr:
                                r["e2e_extra"] = rr["e2e_extra"]
                run_records.append(record)
            seconds["translation"] = round(time.monotonic() - t0, 1)
            first = run_records[0]
            translation.update({"requests_failed": first.get("requests_failed", first.get("e2e", {}).get("requests_failed")),
                                "pages_incomplete": first.get("pages_incomplete", first.get("e2e", {}).get("pages_incomplete")),
                                "run_results": run_records})
            if args.runs > 1:
                if "official" in arms:
                    chrfs = [r["summary"]["all"]["translation"]["chrf"] for r in run_records]
                    print(f"chrF per run (official): {', '.join(f'{c:.2f}' for c in chrfs)}", flush=True)
                if "e2e" in arms:
                    chrfs = [r["e2e"]["summary"]["strict"] for r in run_records]
                    print(f"chrF per run (end to end, strict): {', '.join(f'{c:.2f}' for c in chrfs)}", flush=True)
        if "error" in translation:
            print(f"translation skipped: {translation['error']}", flush=True)
    if dump is not None:
        dump.close()
    seconds["total"] = round(time.monotonic() - t_start, 1)

    summ = summarize(rows)
    print("\n" + report(summ, args.iou), flush=True)
    print(f"\n{seconds}", flush=True)
    results = {
        "tool": "openmantra_eval", "made": started.isoformat(timespec="seconds"),
        "dataset": {"name": "OpenMantra", "licence": "CC BY-NC 4.0", "root": str(args.root),
                    "archive_sha256": _archive_sha(args.root), "series": list(groups), "pages": len(rows),
                    "gold_boxes": sum(r["gold"] for r in rows)},
        "options": {"pages": args.pages, "series": args.series or [], "ocr": not args.no_ocr, "translate": not args.no_translate,
                    "mode": args.mode, "arm": args.arm, "geometry": args.geometry, "target": args.target, "iou": args.iou,
                    "runs": args.runs, "seed": args.seed, "glossary": _file_sha(args.glossary) if args.glossary else "",
                    "names": _file_sha(args.names) if args.names else ""},
        "model": model_name, "settings": _settings_record(s), "translation": translation,
        "summary": summ, "seconds": seconds, "rows": rows,
    }
    out = args.out
    if out is None:  # a new file: two runs started in the same second must not overwrite each other
        out = args.root / "results" / f"{started:%Y-%m-%d-%H%M%S}.json"
        n = 1
        while out.exists():
            n += 1
            out = args.root / "results" / f"{started:%Y-%m-%d-%H%M%S}-{n}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"results: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
