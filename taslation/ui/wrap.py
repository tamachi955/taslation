"""Text broken into lines by hand (`wrap_line`): Tk breaks lines only at spaces, which leaves a Japanese or Chinese
sentence in one piece and splits "TASlation" where it meets one. The page canvas (`preview.ImageCanvas`) and the
legal notice (`dialogs.notice.NoticeDialog`) break their text here. Thai has no spaces between words but has them
between clauses, and no dictionary is at hand, so it breaks at those; a clause too long for a line is cut between
syllables where its spelling shows one, never between a letter and its marks (`_cut`). No Tk."""

from __future__ import annotations

import unicodedata
from typing import Callable

_CJK_RANGES = ((0x1100, 0x11FF), (0x2E80, 0x2FDF), (0x3000, 0x30FF), (0x3100, 0x31FF), (0x3200, 0x9FFF),
               (0xA960, 0xA97F), (0xAC00, 0xD7FF), (0xF900, 0xFAFF), (0xFE30, 0xFE4F), (0xFF00, 0xFFEF),
               (0x20000, 0x3FFFF))
NO_LINE_START = set("、。，．,.:;；：？！?!）)］]｝}〕〉》」』】〙〗〟’”»ー々ゝゞヽヾぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ・…‥％%ๆฯ")
NO_LINE_END = set("（(［[｛{〔〈《「『【〘〖〝‘“«")
THAI_LEADING_VOWELS = set("เแโใไ")  # written before the consonant they follow in speech: a syllable starts here
THAI_SYLLABLE_ENDS = set("ะ")  # a syllable ends after it
THAI_REACH = 10  # how many characters a cut goes back for such a place


def is_cjk(ch: str) -> bool:
    """Whether a line may break before or after *ch*: Chinese, Japanese and Korean script and their punctuation."""
    code = ord(ch)
    return any(a <= code <= b for a, b in _CJK_RANGES)


def _pieces(line: str) -> list[str]:
    """*line* cut where it may break: after a space (the space stays with what is before it), before and after a CJK
    character - unless the next piece may not start a line or this one may not end one - but never inside a run of
    Latin letters, digits and their punctuation, nor before a number after a space ("Art. 47-4", "§ 184b")."""
    pieces: list[str] = []
    current = ""
    for ch in line:
        if current:
            prev = current[-1]
            breakable = False
            if prev == " " and ch != " ":
                breakable = not ch.isdigit()  # a space before a number joins it to the word before
            elif is_cjk(prev) or is_cjk(ch):
                breakable = prev != " " and ch != " "
            if breakable and (ch in NO_LINE_START or prev in NO_LINE_END):
                breakable = False
            if breakable:
                pieces.append(current)
                current = ""
        current += ch
    if current:
        pieces.append(current)
    return pieces


def _joined(ch: str) -> bool:
    """Whether *ch* sits on or against the letter before it (Thai's vowels and tone marks above and below, and sara
    am) and so may not begin a line."""
    return unicodedata.category(ch) in ("Mn", "Me", "Mc") or ch == "ำ"


def _cut(piece: str, limit: int) -> int:
    """Where to cut *piece*, whose first *limit* characters fit a line: at *limit*, or just before it where that
    would part a letter from its marks or a Thai vowel from the consonant after it; in Thai a little further back
    when a syllable ends there."""
    safe = next((at for at in range(limit, 0, -1)
                 if not _joined(piece[at]) and piece[at - 1] not in THAI_LEADING_VOWELS), limit)
    for at in range(safe, max(0, safe - THAI_REACH), -1):
        if (piece[at] in THAI_LEADING_VOWELS or piece[at - 1] in THAI_SYLLABLE_ENDS) and not _joined(piece[at]):
            return at
    return safe


def wrap_line(line: str, width: int, measure: Callable[[str], int]) -> list[str]:
    """One paragraph of text in lines of at most *width* pixels (as *measure* gives them), broken only where
    `_pieces` allows; a space at a break stays at the end of its line, so the lines joined give *line* again. A piece
    wider than a line on its own is cut by characters (`_cut`), the last resort."""
    lines: list[str] = []
    current = ""
    for piece in _pieces(line):
        if measure((current + piece).rstrip(" ")) <= width:
            current += piece
            continue
        if current:
            lines.append(current)
        while measure(piece.rstrip(" ")) > width and len(piece) > 1:  # longer than a line: by characters
            cut = len(piece) - 1
            while cut > 1 and measure(piece[:cut]) > width:
                cut -= 1
            cut = _cut(piece, cut)
            lines.append(piece[:cut])
            piece = piece[cut:]
        current = piece
    lines.append(current)
    return lines


def wrap_text(text: str, width: int, measure: Callable[[str], int]) -> list[list[str]]:
    """*text* paragraph by paragraph (its own line breaks), each as the lines `wrap_line` makes of it."""
    return [wrap_line(paragraph, width, measure) for paragraph in text.split("\n")]
