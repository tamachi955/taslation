"""Cleaning of short texts kept beside the book: no control characters, no links, bounded length.

Everything a reader types into the premises goes through ``clean_text``, and
so do a colophon's details and the model's notes for the reader; a note that
reads like a line of the book is left out (`looks_like_a_line`). Nothing here
reads or judges the book.
"""

from __future__ import annotations

import re
from typing import Any

# C0/C1 controls, zero-width and bidi-control characters, BOM; tab and newline are handled by split()
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏ -‮⁠-⁤﻿]")
URL_RE = re.compile(r"(?i)(?:https?://|ftp://|file://|www\.)\S+")
# a run of Japanese long enough to be a line of the book rather than a name or a term
JAPANESE_LINE_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿ー々]{30,}")


def clean_text(value: Any, limit: int) -> str:
    """One line of plain text: controls and links removed, whitespace collapsed, at most *limit* characters."""
    s = str(value or "")
    s = CONTROL_RE.sub("", s)
    s = URL_RE.sub("", s)
    s = " ".join(s.split())
    return s[:limit]


def looks_like_a_line(value: str) -> bool:
    return bool(JAPANESE_LINE_RE.search(value))


READING_LIMIT = 500  # characters of a reading a person types (a bubble's Japanese is far shorter)


def clean_reading(value: Any, limit: int = READING_LIMIT) -> str:
    """A reading of a region's Japanese as a person typed it (the region editor's "Read as:"): one line, as the OCR
    gives it (line breaks dropped, no space put in their place), controls removed, the ends trimmed, at most *limit*
    characters. Held in memory only, as every reading is."""
    s = CONTROL_RE.sub("", "".join(str(value or "").splitlines()))
    return s.strip()[:limit]


__all__ = ["READING_LIMIT", "clean_reading", "clean_text", "looks_like_a_line"]
