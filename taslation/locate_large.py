"""Where a translation's counterpart of a bubble's larger lettering is (`size_mix`: the part of the Japanese set
larger than the rest), found without changing a word of the translation: the bubble's own request is never touched,
and nothing found here goes into the text the person gets. Once a page's translations are final, a bubble with a
measured part is looked at in two steps (`locate`):

1. the part translated alone (one request beside the page's: `ask`), found in the translation as it is, the same
   words after case, punctuation and spacing are set aside, once and at word edges (`find_exact`);
2. else the bubble's Japanese once more with the part between ``<b>`` and ``</b>`` (`marked_source`), and what the
   answer marks (`marked_part`) found in the translation as it is (`find_exact`, else nearly: `find_loose`). The
   answer is only a pointer: its words are never used. A part found so must look like the Japanese part
   (`plausible`): letters or digits in it, not the whole translation, its share of the translation within bounds of
   the Japanese part's share of the Japanese (`SHARE_LOW` to `SHARE_HIGH` times); and step 1's answer must bear it
   out (`from_marked`: `AGREE_LEAST` of its pairs of letters in that answer, which is itself no whole line).

What is found is snapped to whole words (`snap`), with the marks that close it (!, ?, ...) and those that open it
(¡, ¿), and given as a range of the translation; nothing found leaves the bubble lettered at one size. Measured on the
dataset's bubbles with stand-in parts where the real ones sit (`tools/size_mix_eval.py`): on a held-out part of it,
right 11 times in 12 when it answers, and it answers for about half of them.

The range is kept with the translation (`TextRegion.large`, `cache.CachedBubble.large`) as (start, end, ratio), checked
against the text wherever it is taken in (`checked`), and it follows an edit of the text that leaves it be (`follow`):
an edit that touches it drops it."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Callable

from .size_mix import CAP

MARK_OPEN, MARK_CLOSE = "<b>", "</b>"
# the forms a model may write the marker in instead
_MARK_FORMS = ((MARK_OPEN, MARK_CLOSE), ("<B>", "</B>"))
SHARE_LOW = 0.35  # the part's share of the translation (letters and digits) at least this many times ...
SHARE_HIGH = 2.0  # ... and at most this many times the Japanese part's share of the Japanese (kana, kanji, letters)
AGREE_LEAST = 0.5  # the share of a marked part's pairs of letters the part's own translation must have too ...
ALONE_HIGH = 2.0  # ... that translation no longer than this many times the part's share (`alone_share`)
LOOSE_LEAST = 0.8  # how like the marked part a run of the translation's words must be (`find_loose`)
_CLOSERS = "!?！？‼⁉…"  # what closes the part along with it (a run of dots too)
_OPENERS = "¡¿"  # what opens it
_QUOTES_AFTER = "\"'”’»」』)]"  # closing quotes and brackets right after those marks


Large = tuple[int, int, float]  # (start, end, ratio): characters [start, end) of a translation, set ratio times larger


@dataclass(frozen=True)
class Located:
    """What `locate` found: the range of the translation (None: nothing), the step that found it ("alone",
    "marked"; "" none) and how many requests it took."""

    at: tuple[int, int] | None
    step: str
    requests: int


@dataclass
class Tally:
    """This session's looks (`Pipeline.large_part`): the bubbles looked at, the requests they took and their time, and
    what each look found by (step 1 "alone", step 2 "marked", or nothing). Counts only, in memory."""

    bubbles: int = 0
    requests: int = 0
    alone: int = 0
    marked: int = 0
    none: int = 0
    ms: float = 0.0

    def add(self, found: Located, ms: float) -> None:
        self.bubbles += 1
        self.requests += found.requests
        self.ms += ms
        if found.step == "alone":
            self.alone += 1
        elif found.step == "marked":
            self.marked += 1
        else:
            self.none += 1


def checked(text: str, large: Any, cap: float = CAP) -> Large | None:
    """*large* as a part of *text* to set larger: (start, end, ratio) when start and end are whole numbers with
    0 <= start < end <= len(text), the part holds more than spaces and the ratio is over 1 and at most *cap*; None
    for anything else (a file's damaged or hand-edited entry, a part of another text)."""
    if not isinstance(large, (tuple, list)) or len(large) != 3:
        return None
    a, b, r = large
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (a, b)):
        return None
    if isinstance(r, bool) or not isinstance(r, (int, float)):
        return None
    r = float(r)
    if not (0 <= a < b <= len(text)) or not text[a:b].strip() or not 1.0 < r <= cap:
        return None
    return a, b, r


def follow(old: str, new: str, large: Large | None) -> Large | None:
    """The part *large* of the text *old* as a part of *new*, the text after an edit: moved along with the text
    before it; None when the edit changed any of it (a character of it gone or replaced, or one put inside it)."""
    if large is None or old == new:
        return large
    a, b, r = large
    if not 0 <= a < b <= len(old):
        return None
    starts: dict[int, int] = {}
    for tag, i1, i2, j1, _j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            if i1 <= a < i2:
                starts[a] = j1 + a - i1
            if i1 < b <= i2:
                starts[b] = j1 + b - i1
        elif (i1 < b and i2 > a) if i2 > i1 else a < i1 < b:
            return None
    if a not in starts or b not in starts:
        return None
    return checked(new, (starts[a], starts[b], r))


def one_line(text: str, at: tuple[int, int]) -> tuple[str, tuple[int, int]]:
    """*text* as a request gives it to the model (spaces and line breaks made one space when it has a line break:
    `translate.plamo.one_line`) and the range *at* in it."""
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


def normalised(text: str) -> tuple[str, list[int]]:
    """*text* in lower case, its punctuation and marks gone and its spaces made one, with each kept character's index
    in *text*."""
    out: list[str] = []
    at: list[int] = []
    space = True
    for i, ch in enumerate(text):
        if ch.isalnum() or ch in "'’":
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


def find_exact(whole: str, part: str) -> tuple[int, int] | None:
    """*part* found in *whole* once, after normalising both (`normalised`), at word edges: its range in *whole*; None
    when it is not there, or there twice."""
    w, at = normalised(whole)
    p, _ = normalised(part)
    if not p or not w:
        return None
    hits = [m.start() for m in re.finditer(r"(?<![\w'])" + re.escape(p) + r"(?![\w'])", w)]
    if len(hits) != 1:
        return None
    s = hits[0]
    return at[s], at[s + len(p) - 1] + 1


def _words(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0).lower().replace("’", "'"), m.start(), m.end()) for m in re.finditer(r"[\w'’]+", text)]


def find_loose(whole: str, part: str, least: float = LOOSE_LEAST) -> tuple[int, int] | None:
    """*part*'s words in *whole* in their order with small differences: the run of *whole*'s words (one fewer or
    more) most like them (at least *least*, `difflib`'s ratio of the words joined) when no other run elsewhere is as
    like them; its range in *whole*."""
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
    for other, s2, n2 in scored[1:]:  # a run elsewhere as like it: no answer
        if other < best - 0.05:
            break
        if s2 + n2 <= s or s2 >= s + n:
            return None
    return ws[s][1], ws[s + n - 1][2]


def marked_source(text: str, at: tuple[int, int]) -> str:
    """The Japanese *text* with its part *at* between the markers."""
    a, b = at
    return text[:a] + MARK_OPEN + text[a:b] + MARK_CLOSE + text[b:]


def marked_part(answer: str) -> str:
    """What an answer to a marked request marks: the text between its one pair of markers ("" when they did not come
    back as one pair round something)."""
    for o, c in _MARK_FORMS:
        if answer.count(o) == 1 and answer.count(c) == 1 and answer.index(o) < answer.index(c):
            return answer[answer.index(o) + len(o):answer.index(c)].strip()
    return ""


def snap(whole: str, at: tuple[int, int]) -> tuple[int, int]:
    """*at* grown to whole words of *whole*, then over the marks that close it (!, ?, a run of dots, and a closing
    quote after them) and those that open it (¡, ¿); its spaces at either end left out."""
    a, b = at
    word = lambda ch: ch.isalnum() or ch in "'’-"  # noqa: E731
    while a > 0 and word(whole[a - 1]) and word(whole[a]):
        a -= 1
    while b < len(whole) and b > 0 and word(whole[b]) and word(whole[b - 1]):
        b += 1
    end = b
    while end < len(whole) and (whole[end] in _CLOSERS or whole[end] == "."):
        end += 1
    if end > b and whole[b:end].strip(".") == "" and end - b < 2:
        end = b  # a single full stop is the sentence's, not the part's
    if end > b:
        while end < len(whole) and whole[end] in _QUOTES_AFTER:
            end += 1
        b = end
    while a > 0 and whole[a - 1] in _OPENERS:
        a -= 1
    while a < b and whole[a].isspace():
        a += 1
    while b > a and whole[b - 1].isspace():
        b -= 1
    return a, b


def _letters(text: str) -> int:
    return sum(1 for ch in text if ch.isalnum())


def _grams(text: str) -> set[str]:
    """The pairs of letters of *text*'s words (`normalised`; a word of one letter as itself): what `agreement`
    compares, in a script without spaces as in one with them."""
    out: set[str] = set()
    for w in normalised(text)[0].split():
        out.update(w[i:i + 2] for i in range(len(w) - 1)) if len(w) > 1 else out.add(w)
    return out


def agreement(part: str, alone: str) -> float:
    """How much of *part* (what the marked request points at in the translation) the part's own translation *alone*
    has too: the share of *part*'s pairs of letters (`_grams`) that are *alone*'s (0 for nothing)."""
    mine = _grams(part)
    return len(mine & _grams(alone)) / len(mine) if mine else 0.0


def share_ratio(whole: str, at: tuple[int, int], source: str, span: tuple[int, int]) -> float | None:
    """The part *at*'s share of the translation *whole* (its letters and digits) over the Japanese part *span*'s
    share of *source* (kana, kanji, letters and digits); None when either part is nothing or all."""
    mine, total = _letters(whole[at[0]:at[1]]), _letters(whole)
    src_part, src_total = _letters(source[span[0]:span[1]]), _letters(source)
    if not mine or mine >= total or not src_part or src_part >= src_total:
        return None
    return (mine / total) / (src_part / src_total)


def plausible(whole: str, at: tuple[int, int], source: str, span: tuple[int, int]) -> bool:
    """Whether the part *at* of the translation *whole* may be the counterpart of the part *span* of the Japanese
    *source*: it has letters or digits, it is not the whole translation, and its share of the translation's letters
    and digits is within `SHARE_LOW` to `SHARE_HIGH` times the Japanese part's share of the Japanese's."""
    ratio = share_ratio(whole, at, source, span)
    return ratio is not None and SHARE_LOW <= ratio <= SHARE_HIGH


def from_alone(whole: str, alone: str) -> tuple[int, int] | None:
    """Step 1: the part's own translation *alone* found in the translation *whole* (`find_exact`), snapped (`snap`);
    None when it is not there once, or is all of it."""
    hit = find_exact(whole, alone) if alone and alone.strip() else None
    if hit is None:
        return None
    at = snap(whole, hit)
    mine = _letters(whole[at[0]:at[1]])
    return at if mine and mine < _letters(whole) else None


def alone_share(whole: str, alone: str, source: str, span: tuple[int, int]) -> float | None:
    """How long the part's own translation *alone* is against the translation *whole*, over the Japanese part
    *span*'s share of *source* (as `share_ratio` measures a part found); None for nothing."""
    mine, total = _letters(alone), _letters(whole)
    src_part, src_total = _letters(source[span[0]:span[1]]), _letters(source)
    if not mine or not total or not src_part or not src_total:
        return None
    return (mine / total) / (src_part / src_total)


def from_marked(whole: str, answer: str, source: str, span: tuple[int, int], alone: str = "") -> tuple[int, int] | None:
    """Step 2: what the *answer* to the marked request marks found in the translation *whole* (`find_exact`, else
    `find_loose`), snapped (`snap`), `plausible` as the counterpart of *span* of *source* (the Japanese as asked:
    `one_line`) and borne out by the part's own translation *alone* (step 1's answer): `AGREE_LEAST` of its pairs of
    letters there (`agreement`), *alone* itself no longer than `ALONE_HIGH` times the part's share (a whole line
    answered for a part bears nothing out); None otherwise."""
    inner = marked_part(answer)
    if not inner or not _letters(inner):
        return None
    hit = find_exact(whole, inner) or find_loose(whole, inner)
    if hit is None:
        return None
    at = snap(whole, hit)
    if not plausible(whole, at, source, span):
        return None
    long = alone_share(whole, alone, source, span)
    if long is None or long > ALONE_HIGH or agreement(whole[at[0]:at[1]], alone) < AGREE_LEAST:
        return None
    return at


def locate(source: str, span: tuple[int, int], translation: str, ask: Callable[[str], str],
           known: Callable[[str], str | None] | None = None) -> Located:
    """Where the part *span* of the Japanese *source* is in its *translation* (see the module): *ask*(Japanese)
    makes one request beside the page's and returns its answer; *known*(Japanese) may give the part's translation
    without one (a short line the book translated before), or None."""
    text, (a, b) = one_line(source, span)
    part = text[a:b].strip()
    if not part or not translation.strip() or not (text[:a].strip() or text[b:].strip()):
        return Located(None, "", 0)
    asked = 0
    alone = known(part) if known is not None else None
    if not alone:
        alone = ask(part)
        asked += 1
    at = from_alone(translation, alone)
    if at is not None:
        return Located(at, "alone", asked)
    answer = ask(marked_source(text, (a, b)))
    asked += 1
    at = from_marked(translation, answer, text, (a, b), alone or "")
    return Located(at, "marked" if at is not None else "", asked)
