"""A page split in two at a white gutter is still the book: its whole shape is the book's."""

from types import SimpleNamespace

import numpy as np
from PIL import Image

from taslation import batch as B


def _reader(monkeypatch, units):
    reader = object.__new__(B.BatchReader)
    reader.settings = SimpleNamespace(margins=(0, 0, 0, 0))
    reader.guard_after_units, reader.aspect_tolerance = 2, 0.12
    reader.paper_growth, reader.paper_tolerance = 0.1, 0.02
    reader._aspects, reader._papers = [0.68, 0.7, 0.69], []
    monkeypatch.setattr(B.fingerprint, "analyze", lambda rgb, margins: units)
    monkeypatch.setattr(B.fingerprint, "paper_box", lambda rgb, margins: None)
    return reader


def _unit(box):
    return SimpleNamespace(box=box, aspect=(box[2] - box[0]) / (box[3] - box[1]))


def test_a_page_split_at_its_gutter_is_still_the_book(monkeypatch):
    units = [_unit((969, 65, 1284, 980)), _unit((693, 65, 960, 922))]
    assert _reader(monkeypatch, units)._still_the_book(Image.new("RGB", (8, 8)))


def test_a_wide_panel_in_two_parts_is_not(monkeypatch):
    units = [_unit((0, 0, 900, 300)), _unit((1000, 0, 1900, 300))]
    assert not _reader(monkeypatch, units)._still_the_book(Image.new("RGB", (8, 8)))


def test_a_spread_after_narrow_first_pages_is_still_the_book():
    """The book's first pages taught a narrow shape; a spread is no other screen for that."""
    from taslation.batch import BatchReader
    low, high = BatchReader.book_shape
    assert low <= 0.91 <= high and low <= 0.66 and high >= 1.33
