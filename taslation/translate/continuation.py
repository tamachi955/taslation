"""A sentence split across bubbles: which lines go on in the next one, the line-by-line translator's joined request,
and its answer split back onto the bubbles.

Manga splits a sentence over two or three bubbles ("お前もしかして" / "女か?"). Translated one bubble at a time, the
first half comes out as a sentence of its own, or its subject or verb goes missing. A line *continues* when

* its Japanese ends on a particle or a connective (`ends_open`: は, が, を, に, で, と, て, から, けど, ので, って, ...,
  with only dots, dashes or a comma after it) with no sentence end (。！？!?) closing it, and
* the next region in reading order is in the same page unit and near it (`near`: the gap between their boxes is at most
  `NEAR_SHARE` of the unit's shorter side: on OpenMantra's annotated panels, the next bubble is then in the same
  panel or one touching it for 817 of 834 such pairs, 98 %).

The reader's own fact "the sentence continues in the next bubble" (`annotations.RegionNote.continues`) counts too.
The rule goes in each line's facts as ``continues`` (`mark`), which the chat translator has always read; the PLaMo
translator sends a run of such lines as one request, a line break between bubbles, and splits the answer back
(`split_back`) when it has exactly one line per bubble; otherwise each line is asked for alone with the lines that
follow it as context. Nothing here talks to a model, and nothing is printed.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

OPEN_ENDINGS = tuple(sorted(("が", "を", "に", "で", "と", "へ", "は", "も", "の", "や", "から", "まで", "より", "けど",
                             "けれど", "けども", "けれども", "のに", "ので", "て", "し", "ば", "たら", "なら", "ながら",
                             "とか", "って", "だって", "でも"), key=len, reverse=True))
OPEN_TRAIL = "…‥・.。、,ー～~―-─ 　"  # what may follow the last word of a line that goes on
CLOSED = "。！？!?」』)）"  # a sentence end
NEAR_SHARE = 0.3  # the farthest the next region may be, as a share of the page unit's shorter side
MAX_JOINED = 3  # bubbles in one joined request at most
_WORD = re.compile(r"[\w぀-ヿ一-鿿]")

Box = tuple[int, int, int, int]


def ends_open(text: str) -> bool:
    """Whether the Japanese *text* ends on a particle or a connective with nothing but dots, dashes or a comma after
    it, and no sentence end."""
    t = "".join(str(text or "").split())
    s = t.rstrip(OPEN_TRAIL)
    return bool(s) and bool(_WORD.search(s)) and s[-1] not in CLOSED and s.endswith(OPEN_ENDINGS)


def gap(a: Box, b: Box) -> float:
    """The distance between two boxes (0 when they overlap)."""
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return float((dx * dx + dy * dy) ** 0.5)


def near(a: Box, b: Box, unit: Box) -> bool:
    """Whether the box *b* is near enough to *a* in the page unit *unit* to hold the rest of its sentence."""
    short = max(1, min(unit[2] - unit[0], unit[3] - unit[1]))
    return gap(a, b) <= NEAR_SHARE * short


def continues(text: str, box: Box, next_box: Box | None, unit: Box | None, same_unit: bool = True) -> bool:
    """Whether a line goes on in the next region (see the module's docstring): *text* ends open, and the next region
    (*next_box*) is in the same page unit (*same_unit*, *unit*) and `near`."""
    if next_box is None or unit is None or not same_unit:
        return False
    return ends_open(text) and near(box, next_box, unit)


def going_on(lines: Sequence[tuple[str, Box, Any, Box | None]]) -> list[bool]:
    """Per line of *lines* (in reading order: its Japanese, its box, its page unit, that unit's box) whether it
    `continues` in the next one."""
    out = []
    for k, (text, box, unit, unit_box) in enumerate(lines):
        nxt = lines[k + 1] if k + 1 < len(lines) else None
        out.append(nxt is not None and continues(text, box, nxt[1], unit_box, nxt[2] == unit))
    return out


AUTO = True  # whether the rule marks lines (a reader's mark counts in any case)


def facts_of(regions: Sequence[Any], units: Sequence[tuple[Any, Box | None]]) -> list[dict[str, Any]]:
    """The facts each of *regions* (in reading order) goes to the translator with: the reader's
    (`regions.region_meta`), the page unit it is on (``page``: *units*, one (unit, its box) per region) and
    ``continues`` where the rule finds its sentence going on in the next one (`going_on`)."""
    from ..regions import region_meta

    meta = [dict(region_meta(r), page=unit) for r, (unit, _box) in zip(regions, units)]
    if AUTO:
        mark(meta, going_on([(r.source_text, r.bbox, unit, box) for r, (unit, box) in zip(regions, units)]))
    return meta


def mark(meta: list[dict[str, Any]], flags: Sequence[bool]) -> list[dict[str, Any]]:
    """*meta* (each line's facts, in reading order) with ``continues`` set where *flags* says so (a reader's
    ``continues`` stays as it is). The same list, changed in place."""
    for facts, flag in zip(meta, flags):
        if flag:
            facts["continues"] = True
    return meta


def runs(meta: Sequence[dict[str, Any]] | None, count: int, limit: int = MAX_JOINED) -> list[list[int]]:
    """The lines 0..*count*-1 in runs: a line whose facts say it ``continues`` is in one run with the next, at most
    *limit* lines a run."""
    out: list[list[int]] = []
    for i in range(count):
        before = out[-1] if out else None
        facts = (meta[i - 1] or {}) if meta and i > 0 and i - 1 < len(meta) else {}
        if before is not None and facts.get("continues") and len(before) < limit:
            before.append(i)
        else:
            out.append([i])
    return out


def joined(texts: Sequence[str]) -> str:
    """The lines of a run as one text, a line break between bubbles."""
    return "\n".join(" ".join(str(t).split()) for t in texts)


def split_back(answer: str, count: int) -> list[str] | None:
    """The answer to a joined request split back onto its *count* bubbles: one line of the answer each, when it has
    exactly that many non-empty lines; None when it has not (merged, split further, a line left out)."""
    lines = [" ".join(line.split()) for line in str(answer or "").splitlines()]
    lines = [line for line in lines if line]
    if len(lines) != count or not all(_WORD.search(line) or line.strip(".…!?-—") == "" for line in lines):
        return None
    return lines
