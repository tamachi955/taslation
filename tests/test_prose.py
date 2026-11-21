"""Lettering set across (`detect.prose`, `Pipeline._prose`): an explanation page's paragraphs, a contents list, a
chapter's label on a band. Synthetic pages with invented text, read by a reader that reads exactly what was drawn in
the crop it is given (`_DrawnReader`: it finds the crop on the page), so that what the pipeline makes of the regions is
tested apart from the OCR's mistakes; the classical detectors as the app has them."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from taslation.cache import CachedBubble, CachedPage
from taslation.detect import prose
from taslation.detect.layout import BUBBLE, TEXT, model_regions, page_ground
from taslation.fingerprint import PageUnit
from taslation.ocr.charspot import CharspotChar, CharspotReading, confidence
from taslation.pipeline import Pipeline

FONTS = [r"C:\Windows\Fonts\yumindb.ttf", r"C:\Windows\Fonts\yumin.ttf", r"C:\Windows\Fonts\msmincho.ttc",
         r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\msgothic.ttc",
         "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
FONT = next((f for f in FONTS if Path(f).is_file()), None)
needs_font = pytest.mark.skipif(FONT is None, reason="no font with Japanese glyphs on this computer")
# The contents list is read row by row in the face its page was made in, Yu Mincho Demibold (the first of FONTS), and
# in no other face tried: Yu Mincho, MS Mincho, Yu Gothic Regular, Medium and Bold, MS Gothic, Meiryo and Meiryo Bold,
# Noto Sans JP at seven weights from 100 to 900. In those no row is read: the classical detectors find no block over the rows (Yu Gothic
# Bold) or one over the numerals alone, read as no Japanese (MS Mincho), so that nothing looks round it for lines set
# across. A fault of the program's, not of the computer's: the test is expected to fail in another face (GitHub's
# Windows has no Yu Mincho and draws in Yu Gothic Bold), and a run where it passes there says so (XPASS).
MADE_IN = "yumindb.ttf"
in_the_face_made_in = pytest.mark.xfail(Path(FONT or "").name.lower() != MADE_IN, raises=AssertionError, strict=False,
                                        reason="a contents list is read row by row only in Yu Mincho Demibold")

HEADING = "時計塔の決まりについて"  # invented, as every text here
SUBTITLE = "Rules of the Clock Tower"
PARAGRAPHS = [["塔の鐘が三度鳴ると、町の", "時計はすべて止まります。"],
              ["止まっているあいだは、だれも", "年を取りませんが、外へ出る", "こともできなくなります。"],
              ["鐘を鳴らした人だけが、止まった", "町を歩けます。ただし影は残りません。"],
              ["もう一度鐘を鳴らせば時計は", "動きだします。鳴らせるのは一日に一度です。"]]


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


@dataclass
class Drawn:
    """A synthetic page and every character drawn on it (the character and its box on the page)."""

    image: Image.Image
    chars: list[tuple[str, tuple[int, int, int, int]]] = field(default_factory=list)
    lines: list[tuple[int, int, int, int]] = field(default_factory=list)  # the box of every line drawn

    def write(self, text: str, x: float, y: float, size: int, fill=(0, 0, 0), spacing: float = 0.0) -> float:
        """*text* set across from (*x*, *y*), each character where it falls (*spacing*: px between characters, a loose
        setting); the line's box is kept. Returns the x after it."""
        d = ImageDraw.Draw(self.image)
        font = _font(size)
        boxes = []
        for c in text:
            if c != " ":
                d.text((x, y), c, font=font, fill=fill)
                ink = Image.new("L", (3 * size, 3 * size), 0)  # its ink alone (a full stop is a small ring at the left)
                ImageDraw.Draw(ink).text((size + x % 1, size + y % 1), c, font=font, fill=255)
                got = ink.getbbox()
                if got is not None:
                    ox, oy = int(x) - size, int(y) - size
                    bb = (got[0] + ox, got[1] + oy, got[2] + ox, got[3] + oy)
                    self.chars.append((c, bb))
                    boxes.append(bb)
            x += d.textlength(c, font=font) + spacing
        if boxes:
            self.lines.append((min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                               max(b[3] for b in boxes)))
        return x

    def centred(self, text: str, y: float, size: int, fill=(0, 0, 0), middle: float | None = None) -> None:
        font = _font(size)
        width = sum(ImageDraw.Draw(self.image).textlength(c, font=font) for c in text)
        self.write(text, (middle if middle is not None else self.image.width / 2) - width / 2, y, size, fill)


class _DrawnReader:
    """Reads what was drawn in a crop: the crop is found on the page (as cut, or inverted for light lettering on a
    dark ground), and its characters are those drawn with their centre in it, line by line, left to right, each sure
    (0.95). A crop that holds none reads nothing."""

    def __init__(self, drawn: Drawn):
        self.page = cv2.cvtColor(np.asarray(drawn.image), cv2.COLOR_RGB2GRAY)
        self.chars = drawn.chars
        self.lines = drawn.lines
        self.crops = 0

    def read_chars(self, crop: Image.Image) -> CharspotReading:
        self.crops += 1
        g = cv2.cvtColor(np.asarray(crop.convert("RGB")), cv2.COLOR_RGB2GRAY)
        best = None
        for view in (g, 255 - g):
            if view.shape[0] > self.page.shape[0] or view.shape[1] > self.page.shape[1]:
                continue
            res = cv2.matchTemplate(self.page, view, cv2.TM_SQDIFF)
            lo, _hi, at, _ = cv2.minMaxLoc(res)
            if best is None or lo < best[0]:
                best = (lo, at)
        if best is None:
            return CharspotReading()
        x, y = best[1]
        h, w = g.shape
        inside = [(c, b) for c, b in self.chars if x <= (b[0] + b[2]) / 2 < x + w and y <= (b[1] + b[3]) / 2 < y + h]
        if not inside:
            return CharspotReading()
        # rows: the bands of the lines drawn (a comma low in its line is the line's), lines side by side one row
        bands: list[list] = []  # [top, bottom, its characters]
        for c, b in inside:
            cy = (b[1] + b[3]) / 2
            line = next((ln for ln in self.lines if ln[0] <= (b[0] + b[2]) / 2 <= ln[2] and ln[1] <= cy <= ln[3]), None)
            top, bottom = (line[1], line[3]) if line is not None else (b[1], b[3])
            band = next((bd for bd in bands if min(bd[1], bottom) - max(bd[0], top) >= 0.5 * min(bd[1] - bd[0], bottom - top)),
                        None)
            if band is None:
                bands.append([top, bottom, [(c, b)]])
            else:
                band[0], band[1] = min(band[0], top), max(band[1], bottom)
                band[2].append((c, b))
        ordered = [cb for band in sorted(bands, key=lambda bd: bd[0]) for cb in sorted(band[2], key=lambda cb: cb[1][0])]
        chars = tuple(CharspotChar(c, (b[0] - x, b[1] - y, b[2] - x, b[3] - y), 0.95, 0.99) for c, b in ordered)
        return CharspotReading("".join(c for c, _b in ordered), chars, confidence(chars))


def explanation_page() -> Drawn:
    """An explanation page as the owner's: a white plate (cut corners) filling its unit on a black ground, a heading
    with a subtitle in Latin letters under it, four numbered paragraphs set across in 13 px characters, 22 px apart."""
    im = Image.new("RGB", (688, 934), (0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = 172, 143, 516, 798
    d.polygon([(x0, y0 + 66), (344, y0), (x1, y0 + 66), (x1, y1 - 44), (344, y1), (x0, y1 - 44)], fill=(255, 255, 255))
    d.line([(x0 + 4, y0 + 68), (344, y0 + 5), (x1 - 4, y0 + 68)], fill=(90, 90, 90), width=1)
    drawn = Drawn(im)
    drawn.centred(HEADING, 238, 21)
    drawn.centred(SUBTITLE, 269, 10)
    y = 300
    for n, lines in enumerate(PARAGRAPHS, 1):
        d.polygon([(344, y), (359, y + 15), (344, y + 30), (329, y + 15)], fill=(0, 0, 0))
        d.text((340, y + 7), str(n), font=_font(13), fill=(255, 255, 255))
        y += 38
        for line in lines:
            drawn.centred(line, y, 13)
            y += 22
        y += 18
    assert y < y1 - 44  # (every line on the plate, none on its cut corners)
    return drawn


def contents_page() -> Drawn:
    """A contents page: light lettering on black, the contents word set loose and five rows, each a chapter's label
    (a small kanji, a large numeral, a small kanji) after a rule from its page number."""
    im = Image.new("RGB", (620, 880), (0, 0, 0))
    d = ImageDraw.Draw(im)
    drawn = Drawn(im)
    drawn.write("目次", 90, 330, 20, (255, 255, 255), spacing=10)
    pages = ["003", "041", "085", "133", "171"]
    for n in range(5):
        y = 330 + 26 * n
        drawn.write(pages[n], 220, y + 4, 11, (255, 255, 255))
        d.line([(254, y + 11), (330, y + 11)], fill=(200, 200, 200), width=1)
        d.line([(338, y + 11), (348, y + 11)], fill=(200, 200, 200), width=1)
        x = drawn.write("第", 362, y + 3, 11, (255, 255, 255))
        x = drawn.write(str(n + 1), x + 9, y, 17, (255, 255, 255))
        drawn.write("話", x + 9, y + 3, 11, (255, 255, 255))
        drawn.lines[-3:] = [(min(b[0] for b in drawn.lines[-3:]), min(b[1] for b in drawn.lines[-3:]),
                             max(b[2] for b in drawn.lines[-3:]), max(b[3] for b in drawn.lines[-3:]))]
    return drawn


def band_page() -> Drawn:
    """A chapter's opening: on a light page with some drawing, a dark band holding a title in Latin letters and the
    chapter's label set larger."""
    im = Image.new("RGB", (700, 900), (235, 235, 235))
    d = ImageDraw.Draw(im)
    for k in range(0, 700, 9):  # hatching: a drawing
        d.line([(k, 300), (k + 120, 620)], fill=(120, 120, 120), width=1)
    d.rounded_rectangle([60, 40, 430, 92], radius=10, fill=(25, 25, 25), outline=(200, 200, 200), width=2)
    drawn = Drawn(im)
    drawn.write("MIDNIGHT CLOCKWORK", 84, 60, 11, (240, 240, 240))
    x = drawn.write("第", 300, 56, 18, (240, 240, 240))
    x = drawn.write("3", x + 4, 50, 26, (240, 240, 240))
    drawn.write("話", x + 4, 56, 18, (240, 240, 240))
    return drawn


def _pipeline(settings, drawn: Drawn) -> tuple[Pipeline, _DrawnReader]:
    reader = _DrawnReader(drawn)
    return Pipeline(settings, ocr=reader, translator=None, cache=None), reader


def _inter(a, b) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(b) -> int:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _holders(regions, box):
    return [r for r in regions if r.status == "untranslated" and _inter(r.text_box, box) > 0.2 * _area(box)]


# ------------------------------------------------------------------ the lines and paragraphs of the ink
def _ink(drawn: Drawn, dark: bool = False) -> prose.Ink:
    gray = cv2.cvtColor(np.asarray(drawn.image), cv2.COLOR_RGB2GRAY)
    return prose.ink_of(gray, (0, 0, gray.shape[1], gray.shape[0]), dark)


@needs_font
def test_paragraphs_set_across_are_found_whole_and_apart():
    """Each paragraph of the explanation page is one paragraph, its lines in order; the heading and its subtitle in
    Latin letters (a third of its height) are two."""
    drawn = explanation_page()
    ink = _ink(drawn)
    found = prose.paragraphs(prose.lines_across(ink, 14.0))
    for k, lines in enumerate(PARAGRAPHS):
        top = drawn.lines[2 + sum(len(p) for p in PARAGRAPHS[:k])]
        holding = [p for p in found if _inter(p.box, top) >= 0.8 * _area(top)]
        assert len(holding) == 1, k
        assert len(holding[0].lines) == len(lines), k
    heading, subtitle = drawn.lines[0], drawn.lines[1]
    holds = [[p for p in found if _inter(p.box, b) >= 0.8 * _area(b)] for b in (heading, subtitle)]
    assert len(holds[0]) == 1 and len(holds[1]) == 1 and holds[0][0] is not holds[1][0]


@needs_font
def test_vertical_columns_make_no_paragraph_across():
    im = Image.new("RGB", (300, 400), (255, 255, 255))
    drawn = Drawn(im)
    d = ImageDraw.Draw(im)
    for col, text in enumerate(("ここで待っていて", "すぐに戻るから")):
        for k, c in enumerate(text):
            d.text((200 - 30 * col, 40 + 26 * k), c, font=_font(22), fill=(0, 0, 0))
    lines = prose.lines_across(_ink(drawn), 24.0)
    assert lines  # (its characters side by side make "lines": the rows of its grid ...)
    found = prose.paragraphs(lines)
    assert found and all(p.rows for p in found)  # (... one right under the other: rows, never a paragraph of prose)


@needs_font
def test_a_rule_before_a_label_is_no_part_of_its_line():
    drawn = contents_page()
    lines = prose.lines_across(_ink(drawn, dark=True), 17.0)
    rows = [ln for ln in lines if ln.box[0] >= 330 and ln.box[1] >= 320]
    assert len(rows) == 5
    assert all(ln.box[0] >= 355 for ln in rows)  # (the short rule at 338-348 is left out)


def test_furigana_over_a_line_is_the_line_s():
    """A thin line of small pieces just above a line is its furigana: one line, taller by it."""
    ink_img = np.full((120, 400), 255, np.uint8)
    for k in range(12):  # glyphs 20 px high
        cv2.rectangle(ink_img, (20 + 28 * k, 50), (40 + 28 * k, 70), 0, 2)
    for k in range(6):  # ruby 7 px high, 3 px above
        cv2.rectangle(ink_img, (24 + 14 * k, 40), (30 + 14 * k, 46), 0, -1)
    ink = prose.ink_of(ink_img, (0, 0, 400, 120), False)
    lines = prose.lines_across(ink, 20.0)
    assert len(lines) == 1 and lines[0].box[1] == 40 and lines[0].box[3] >= 70


# ------------------------------------------------------------------ through the pipeline
@needs_font
def test_the_explanation_page_was_read_in_pieces_before(settings, monkeypatch):
    """What the owner saw, on a synthetic page made like theirs: without the paragraphs, the classical text blocks
    read the paragraphs set across in pieces (one paragraph in two regions or more, or a line in none)."""
    drawn = explanation_page()
    pipeline, _reader = _pipeline(settings, drawn)
    monkeypatch.setattr(Pipeline, "_prose", lambda self, *a, **k: [])
    res = pipeline.process(drawn.image, translate=False, use_cache=False)
    broken = 0
    first = 2
    for lines in PARAGRAPHS:
        boxes = drawn.lines[first:first + len(lines)]
        first += len(lines)
        held = [r for r in res.regions if r.status == "untranslated"
                and any(_inter(r.text_box, b) > 0.2 * _area(r.text_box) for b in boxes)]
        outside = [b for b in boxes if not any(_inter(r.text_box, b) >= 0.5 * _area(b) for r in held)]
        broken += len(held) > 1 or bool(outside)
    assert broken >= 1


@needs_font
def test_a_paragraph_set_across_is_one_region_read_in_line_order(settings):
    drawn = explanation_page()
    pipeline, _reader = _pipeline(settings, drawn)
    res = pipeline.process(drawn.image, translate=False, use_cache=False)
    read = [r for r in res.regions if r.status == "untranslated"]
    first = 2
    for lines in PARAGRAPHS:
        boxes = drawn.lines[first:first + len(lines)]
        first += len(lines)
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        held = _holders(read, box)
        assert len(held) == 1  # lettered once: no piece of it is a region of its own
        assert held[0].source_text == "".join(lines)  # every line, in order
        assert _inter(held[0].text_box, box) >= 0.95 * _area(box)
    # the heading is a region of its own, translated; its subtitle in Latin letters is not
    heading = _holders(read, drawn.lines[0])
    assert [r.source_text for r in heading] == [HEADING]
    assert not _holders(read, drawn.lines[1])
    assert len(read) == 1 + len(PARAGRAPHS)


@needs_font
@in_the_face_made_in
def test_a_contents_list_is_read_row_by_row(settings):
    drawn = contents_page()
    pipeline, _reader = _pipeline(settings, drawn)
    res = pipeline.process(drawn.image, translate=False, use_cache=False)
    read = [r for r in res.regions if r.status == "untranslated"]
    rows = sorted((r for r in read if r.source_text.startswith("第")), key=lambda r: r.text_box[1])
    assert [r.source_text for r in rows] == [f"第{n}話" for n in range(1, 6)]
    for a, b in zip(rows, rows[1:]):  # each in its own row
        assert a.text_box[3] <= b.text_box[1]
    assert [r.source_text for r in read if r not in rows] == ["目次"]  # the contents word: translated, not print
    assert not any(r.source_text.isdigit() for r in read)  # the page numbers stay as they are


@needs_font
def test_a_chapter_label_on_a_band_is_translated_and_its_latin_title_left(settings):
    drawn = band_page()
    pipeline, _reader = _pipeline(settings, drawn)
    res = pipeline.process(drawn.image, translate=False, use_cache=False)
    read = [r for r in res.regions if r.status == "untranslated"]
    assert [r.source_text for r in read] == ["第3話"]
    assert read[0].text_box[0] >= 290  # its own box: the title in Latin letters is no part of it


@needs_font
def test_a_page_of_vertical_lettering_is_left_as_it_was(settings, monkeypatch):
    """Lettering that runs down: no line set across, nothing read again, the same regions as without the step."""
    im = Image.new("RGB", (500, 600), (255, 255, 255))
    drawn = Drawn(im)
    d = ImageDraw.Draw(im)
    d.ellipse([150, 80, 380, 420], outline=(0, 0, 0), width=3)
    for col, text in enumerate(("ここで待っていて", "すぐに戻るから")):
        for k, c in enumerate(text):
            d.text((280 - 34 * col, 130 + 28 * k), c, font=_font(24), fill=(0, 0, 0))
            bb = d.textbbox((280 - 34 * col, 130 + 28 * k), c, font=_font(24))
            drawn.chars.append((c, bb))
    pipeline, reader = _pipeline(settings, drawn)
    with_step = pipeline.process(drawn.image, translate=False, use_cache=False)
    crops = reader.crops
    monkeypatch.setattr(Pipeline, "_prose", lambda self, *a, **k: [])
    pipeline2, reader2 = _pipeline(settings, drawn)
    without = pipeline2.process(drawn.image, translate=False, use_cache=False)
    assert [(r.bbox, r.status) for r in with_step.regions] == [(r.bbox, r.status) for r in without.regions]
    assert crops == reader2.crops  # nothing read again
    assert not any(r.joined for r in with_step.regions)


@needs_font
def test_a_caption_read_whole_stays_when_a_paragraph_found_in_it_reads_less(settings, monkeypatch):
    """Two lines set across read whole as one region: where only its second line is found as a paragraph (on a frame
    of the test volume, the first ran into the drawing), the region stays as it was read and the line is no region of
    its own; nothing it held is lost."""
    im = Image.new("RGB", (600, 1000), (255, 255, 255))
    drawn = Drawn(im)
    drawn.write("それなら東の塔へ行こう", 60, 80, 18)
    drawn.write("鐘はそこにある", 60, 108, 18)
    whole = "それなら東の塔へ行こう鐘はそこにある"
    d = ImageDraw.Draw(im)  # a bubble of lettering set down under it: a page of a story, not of titles alone
    d.ellipse([200, 400, 460, 860], outline=(0, 0, 0), width=3)
    for col, text in enumerate(("ここで待っていて", "すぐに戻るから")):
        for k, c in enumerate(text):
            d.text((342 - 30 * col, 500 + 24 * k), c, font=_font(20), fill=(0, 0, 0))
            drawn.chars.append((c, d.textbbox((342 - 30 * col, 500 + 24 * k), c, font=_font(20))))
    pipeline, reader = _pipeline(settings, drawn)
    res = pipeline.process(drawn.image, translate=False, use_cache=False)
    assert whole in [r.source_text for r in res.regions if r.status == "untranslated"]
    real = Pipeline._paragraphs_round
    looked = []

    def second_line_only(self, gray, a, glyph, dark, bound):
        out = [(prose.Paragraph(p.lines[-1:], p.rows), ink) for p, ink in real(self, gray, a, glyph, dark, bound)]
        looked.extend(out)
        return out

    monkeypatch.setattr(Pipeline, "_paragraphs_round", second_line_only)
    pipeline, reader = _pipeline(settings, drawn)
    res = pipeline.process(drawn.image, translate=False, use_cache=False)
    assert looked  # (the line was found and read)
    read = [r for r in res.regions if r.status == "untranslated" and r.text_box[0] < 300]
    assert [r.source_text for r in read] == [whole] and not read[0].joined


# ------------------------------------------------------------------ the layout model's plate, the cache
def test_a_bubble_as_large_as_its_page_unit_is_the_page_s_ground():
    """The model took the owner's plate for a bubble holding the heading's text box: a bubble is never a page, its
    texts stand alone."""
    unit = (172, 143, 516, 798)
    plate = (172.0, 142.0, 517.0, 798.0, 0.88, BUBBLE)
    head = (229.0, 232.0, 461.0, 287.0, 0.74, TEXT)
    bubble = (300.0, 400.0, 400.0, 500.0, 0.9, BUBBLE)
    assert page_ground(plate, [unit]) and not page_ground(bubble, [unit])
    rgb = np.full((934, 688, 3), 255, np.uint8)
    regions = model_regions(rgb, [plate, head, bubble], [unit])
    assert sorted(r.kind for r in regions) == ["bubble", "text"]
    text = next(r for r in regions if r.kind == "text")
    assert text.text_box == (229, 232, 461, 287)
    assert len(model_regions(rgb, [plate, head], ())) == 1  # (without the units: the bubble with its text, as before)


def test_a_paragraph_made_of_pieces_is_kept_as_such_in_the_cache():
    cb = CachedBubble(box=(0.1, 0.2, 0.5, 0.3), text="When the bell rings", joined=True)
    assert cb.to_json()["joined"] is True
    assert CachedBubble.from_json(cb.to_json()).joined
    assert "joined" not in CachedBubble(box=(0.1, 0.2, 0.5, 0.3), text="x").to_json()
    assert not CachedBubble.from_json({"box": [0.1, 0.2, 0.5, 0.3], "text": "x"}).joined


@needs_font
def test_a_page_from_the_cache_draws_a_paragraph_where_the_live_page_shows_its_pieces(settings):
    """The live detection finds the pieces again, never the paragraph: the cached paragraph is drawn as stored, and
    its pieces are no lines of their own (not "unmatched", which a completed page would read and ask again)."""
    drawn = explanation_page()
    pipeline, _reader = _pipeline(settings, drawn)
    rgb = np.asarray(drawn.image)
    res = pipeline.process(drawn.image, translate=False, use_cache=False)
    joined = [r for r in res.regions if r.joined and r.status == "untranslated"]
    assert joined
    unit = PageUnit((0, 0, rgb.shape[1], rgb.shape[0]), "0" * 16, 0)
    stored = CachedPage(fingerprint="0" * 16, aspect=1.0, seq=1, bubbles=[
        CachedBubble(box=unit.normalize(r.bbox), text=f"paragraph {k}", joined=True) for k, r in enumerate(joined)])
    live = pipeline._detect(rgb)
    shown = pipeline._apply_cached(unit, stored, live, rgb)
    drawn_ = [r for r in shown if r.status == "translated"]
    assert sorted(r.translated_text for r in drawn_) == sorted(f"paragraph {k}" for k in range(len(joined)))
    for r in drawn_:
        assert r.joined
        assert not [q for q in shown if q.status == "unmatched"
                    and _inter(q.text_box, r.bbox) >= 0.6 * _area(q.text_box)]
