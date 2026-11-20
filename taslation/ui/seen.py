"""The "updated" mark, no Tk: what the person last saw lettered on each screen, and which screens have other words now.

The window keeps, per screen turned past (its ``seq``), the words its bubbles showed the last time it was on show
lettered: each bubble's box (as a share of the picture, so that the viewer drawn at another size matches) and its
words - "" for a bubble that showed its Japanese on a page with other bubbles lettered. Memory only: never written,
dropped with the book (`Seen.clear`).

A bubble counts as updated when its shown lettering now has other words, or when it was seen in Japanese on a lettered
page and is translated now - whatever did it: the work on the pages behind, names respelt, find and replace, a series
correction, translating again. Nothing else counts: size, fill, outline, flags, font or emphasis (the words are
compared without the emphasis marks and with their spaces made one), anything changed on the page on show (the
person sees it happen: `look` records it at once), a page never shown lettered (there is nothing to compare with).

* A screen not on show is compared with what the cache holds for it (`changed_in_cache`): its words there that the
  person has not seen. That puts the diamond on its thumbnail (`side_model.Screen.updated`).
* The screen coming on show lettered is compared bubble by bubble (`look`): the bubbles with other words get corner
  brackets on the page for the read time - 1 s and 60 ms a changed character, at least 2 s and at most 8 s
  (`read_time`) - and when the page has stayed on show that long the mark goes (`due`, `acknowledge`); the pointer
  resting on a bracketed bubble counts as reading it (`hovered`). Turned away before that, the mark stays."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

Box = tuple[int, int, int, int]
NBox = tuple[float, float, float, float]

READ_BASE_S, READ_PER_CHAR_S = 1.0, 0.06
READ_LEAST_S, READ_MOST_S = 2.0, 8.0
MATCH_IOU = 0.5  # two boxes are the same bubble when they overlap this much


def read_time(chars: int) -> float:
    """How long the page stays on show before its changed bubbles count as read: 1 s and 60 ms a changed character,
    2 s at least and 8 s at most."""
    return max(READ_LEAST_S, min(READ_MOST_S, READ_BASE_S + READ_PER_CHAR_S * max(0, chars)))


def words(text: str | None) -> str:
    """*text* as compared: without the emphasis marks (`render.lettering.strip_marks`) and with every run of spaces
    and line breaks made one space."""
    if not text:
        return ""
    try:
        from ..render.lettering import strip_marks

        text = strip_marks(text)
    except Exception:  # noqa: BLE001 - compared as it is
        pass
    return re.sub(r"\s+", " ", str(text)).strip()


def share(box: Box, size: tuple[int, int]) -> NBox:
    w, h = max(1, size[0]), max(1, size[1])
    return (box[0] / w, box[1] / h, box[2] / w, box[3] / h)


def pixels(box: NBox, size: tuple[int, int]) -> Box:
    w, h = size
    return (int(round(box[0] * w)), int(round(box[1] * h)), int(round(box[2] * w)), int(round(box[3] * h)))


def iou(a: NBox, b: NBox) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Shown:
    """A screen's bubbles as last seen lettered: (box as a share of the picture, words; "" for Japanese)."""

    bubbles: list[tuple[NBox, str]]
    fingerprints: tuple[str, ...] = ()

    def texts(self) -> Counter:
        return Counter(text for _box, text in self.bubbles if text)


def changed_bubbles(before: Shown, now: list[tuple[NBox, str]]) -> list[tuple[NBox, str]]:
    """The bubbles of *now* whose words the person has not seen in *before*: matched by their boxes; another text,
    or a bubble seen in Japanese translated now; a lettered bubble no box of *before* matches, when its words are not
    among those seen (the page read again found its boxes a little otherwise)."""
    seen_texts = before.texts()
    out = []
    for box, text in now:
        if not text:
            continue
        match = max(before.bubbles, key=lambda b: iou(b[0], box), default=None)
        if match is not None and iou(match[0], box) >= MATCH_IOU:
            if match[1] != text:
                out.append((box, text))
        elif seen_texts[text] == 0:
            out.append((box, text))
    return out


@dataclass
class Watch:
    """The screen on show while it is looked at: its bubbles bracketed (shares of the picture) and when they count as
    read (None: nothing to read)."""

    seq: int
    brackets: list[NBox] = field(default_factory=list)
    due: float | None = None
    latest: list[tuple[NBox, str]] = field(default_factory=list)  # its bubbles as on show now (kept once read)


class Seen:
    """What the person saw, by screen, and the screen being looked at now."""

    def __init__(self) -> None:
        self.shown: dict[int, Shown] = {}
        self.watch: Watch | None = None

    def clear(self) -> None:
        self.shown.clear()
        self.watch = None

    def forget(self, seq: int) -> None:
        self.shown.pop(seq, None)
        if self.watch is not None and self.watch.seq == seq:
            self.watch = None

    def look(self, seq: int | None, bubbles: list[tuple[Box, str]] | None, size: tuple[int, int], now: float,
             fingerprints: Iterable[str] = ()) -> tuple[bool | None, bool]:
        """The screen *seq* is on show with *bubbles* lettered on a picture of *size* (None: nothing lettered on show
        - the original, the viewer's frame as it is, another screen than one of the book's). Returns (whether the
        screen counts as updated now - None: this was no look at its words -, whether the brackets changed).

        Coming on show, the bubbles are compared with what was seen of it last: the changed ones are bracketed for
        their read time, and what was seen stays as it was until they are read (`acknowledge`, `hovered`: turned
        away before, the screen is still updated); while it stays on show, what changes is seen as it happens."""
        before = self.watch
        if seq is None or bubbles is None:
            if before is not None and (seq is None or before.seq != seq):
                self.watch = None
                return None, bool(before.brackets)
            return None, False
        now_bubbles = [(share(box, size), words(text)) for box, text in bubbles]
        if not any(text for _box, text in now_bubbles):
            # nothing lettered (yet): not a look at its words; an earlier watch of another screen ends
            if before is not None and before.seq != seq:
                self.watch = None
                return None, bool(before.brackets)
            return None, False
        old = self.shown.get(seq)
        fps = tuple(fingerprints) or (old.fingerprints if old is not None else ())
        if before is not None and before.seq == seq:  # on show already: what changes is seen as it happens ...
            before.latest = now_bubbles
            if not before.brackets:
                self.shown[seq] = Shown(now_bubbles, fps)
            return bool(before.brackets), False  # (... but the brackets still to read)
        self.watch = watch = Watch(seq, latest=now_bubbles)
        gone = bool(before is not None and before.brackets)
        changed = changed_bubbles(old, now_bubbles) if old is not None else []
        if not changed:
            self.shown[seq] = Shown(now_bubbles, fps)
            return False, gone
        if fps and not old.fingerprints:
            self.shown[seq] = Shown(old.bubbles, fps)
        watch.brackets = [box for box, _text in changed]
        watch.due = now + read_time(sum(len(text) for _box, text in changed))
        return True, True

    def brackets(self, size: tuple[int, int]) -> list[Box]:
        """The bubbles of the screen on show bracketed now, in pixels of a picture of *size*."""
        if self.watch is None:
            return []
        return [pixels(box, size) for box in self.watch.brackets]

    def due(self, now: float) -> bool:
        """Whether the screen on show has been looked at for its read time (its mark goes: `acknowledge`)."""
        return self.watch is not None and self.watch.due is not None and now >= self.watch.due

    def acknowledge(self) -> int | None:
        """The screen on show read: its brackets go; its seq (None: none was bracketed)."""
        watch = self.watch
        if watch is None or not watch.brackets:
            return None
        watch.brackets, watch.due = [], None
        old = self.shown.get(watch.seq)
        self.shown[watch.seq] = Shown(watch.latest, old.fingerprints if old is not None else ())
        return watch.seq

    def hovered(self, box: Box, size: tuple[int, int]) -> bool:
        """The pointer rested on the bubble *box* (pixels of a picture of *size*): its bracket goes, and its words
        count as seen; whether every bracket of the screen on show is gone now (the screen read)."""
        watch = self.watch
        if watch is None or not watch.brackets:
            return False
        at = share(box, size)
        kept = [b for b in watch.brackets if iou(b, at) < MATCH_IOU]
        if len(kept) == len(watch.brackets):
            return False
        if not kept:
            self.acknowledge()
            return True
        watch.brackets = kept
        old = self.shown.get(watch.seq)
        if old is not None:  # that bubble's words seen: in place of what was seen there
            read = [(b, t) for b, t in watch.latest if iou(b, at) >= MATCH_IOU]
            self.shown[watch.seq] = Shown([(b, t) for b, t in old.bubbles if iou(b, at) < MATCH_IOU] + read,
                                          old.fingerprints)
        return False

    def changed_in_cache(self, seq: int, cached: Iterable[str]) -> bool:
        """Whether the cache's words for the screen *seq* (*cached*: each bubble's translation) hold some the person
        has not seen there: a bubble of other words, or one seen in Japanese translated since. False for a screen
        never seen lettered."""
        old = self.shown.get(seq)
        if old is None:
            return False
        now = Counter(w for w in (words(t) for t in cached) if w)
        return bool(now - old.texts())
