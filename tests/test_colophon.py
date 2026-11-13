"""The colophon (奥付) read off a page: a synthetic colophon drawn with the Noto font of the models folder beside an
"artwork" half, cut into columns and read whole (a stand-in reader, and the real OCR when it is installed); an
ordinary page stopped at the cheap pre-check; what the columns say parsed into the title, the volume, the ISBN and
the rest; the whole-book scan recording the colophon it meets."""
from __future__ import annotations

import random
import time

import pytest
from conftest import requires_ocr
from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image, ImageDraw, ImageFont

from taslation import batch as batch_mod
from taslation import colophon
from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.colophon import Colophon, find_colophon, find_isbn, parse, precheck
from taslation.config import Settings
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

ISBN = "978-4-06-123456-7"
COLUMNS = [("見本の物語 第3巻", 30), ("2024年5月10日 初版第1刷発行", 22), ("著者 仮野みのり", 22),
           ("発行者 山田太郎", 22), ("発行所 株式会社見本出版", 22), ("印刷所 見本印刷株式会社", 22),
           ("ISBN" + ISBN, 22)]
VERTICAL_FORMS = {"ー": "丨", "-": "丨"}  # what a hyphen or a long vowel mark looks like in a column


def _font(size: int) -> ImageFont.FreeTypeFont:
    path = Settings().fonts_dir / "NotoSansJP[wght].ttf"
    if not path.is_file():
        pytest.skip(f"no Japanese font at {path} (run setup_models.py)")
    font = ImageFont.truetype(str(path), size)
    try:
        font.set_variation_by_axes([400])  # Regular, as a colophon is printed
    except (OSError, AttributeError):
        pass
    return font


def _column(page: Image.Image, text: str, x: int, y: int, size: int) -> None:
    """*text* as a column of upright glyphs; Latin text (the ISBN) set sideways, as vertical typesetting does."""
    font = _font(size)
    draw = ImageDraw.Draw(page)
    if text.startswith("ISBN"):
        strip = Image.new("RGB", (int(draw.textlength(text, font=font)) + 4, size + 8), "white")
        ImageDraw.Draw(strip).text((2, 0), text, font=font, fill=(0, 0, 0))
        page.paste(strip.transpose(Image.Transpose.ROTATE_270), (x, y))
        return
    step = int(size * 1.12)
    for i, ch in enumerate(text):
        if ch == " ":
            continue
        ch = VERTICAL_FORMS.get(ch, ch)
        draw.text((x + (size - draw.textlength(ch, font=font)) / 2, y + i * step), ch, font=font, fill=(0, 0, 0))


def colophon_page(columns=COLUMNS, artwork: bool = True, horizontal: bool = False) -> Image.Image:
    """A colophon on the left half of a page whose right half is "artwork", in a dark viewer frame."""
    page = Image.new("RGB", (900, 1300), "white")
    if artwork:
        d, rng = ImageDraw.Draw(page), random.Random(3)
        for _ in range(60):
            x, y = rng.randint(470, 860), rng.randint(40, 1240)
            d.rectangle((x, y, x + rng.randint(20, 120), y + rng.randint(20, 160)), fill=(rng.randint(0, 90),) * 3)
    if horizontal:
        y = 700
        for text, size in columns:
            ImageDraw.Draw(page).text((60, y), text.replace("ISBN", "ISBN "), font=_font(size), fill=(0, 0, 0))
            y += int(size * 1.9)
    else:
        x = 400
        for text, size in columns:
            _column(page, text, x - size, 160, size)
            x -= int(size * 1.9)
    frame = Image.new("RGB", (1300, 1400), (24, 24, 24))
    frame.paste(page, (200, 50))
    return frame


class Reader:
    """Reads the crops in the order they come (right to left), recording their sizes; *rotated* is what a crop
    read on its side says."""

    def __init__(self, texts: list[str], rotated: str = ""):
        self.texts, self.rotated, self.sizes = list(texts), rotated, []

    def __call__(self, crop: Image.Image) -> tuple[str, float]:
        turned = (crop.height, crop.width) in self.sizes  # a column read again on its side
        self.sizes.append(crop.size)
        if turned:
            return self.rotated, 0.8
        return (self.texts.pop(0) if self.texts else ""), 0.9


def test_a_colophon_beside_artwork_is_cut_into_columns_and_parsed():
    page = colophon_page()
    assert precheck(page)
    read = Reader([text.replace(" ", "") for text, _size in COLUMNS[:-1]] + ["このBNS78-4-06-12345-7"],
                  rotated="ＩＳＢＮ９７８．４．０６－１２３４５６．７")
    found = find_colophon(page, None, read=read)
    assert found == Colophon(title="見本の物語", volume="3", author="仮野みのり", publisher="株式会社見本出版",
                             date="2024年5月10日", isbn=ISBN, confidence=0.9)
    assert found.name == "見本の物語 3"
    assert len(read.sizes) == len(COLUMNS) + 1  # every column read whole, then the ISBN's on its side
    assert all(h > 3 * w for w, h in read.sizes[:-1]) and read.sizes[-1][0] > 3 * read.sizes[-1][1]
    assert read.sizes[0][0] > read.sizes[1][0]  # the title, set larger, first: right to left
    assert found.details() == {"title": "見本の物語", "volume": "3", "author": "仮野みのり",
                               "publisher": "株式会社見本出版", "isbn": ISBN}


def test_an_ordinary_page_is_no_colophon_at_the_cheap_test(sample_page, sample_page2):
    def no_read(_crop):
        raise AssertionError("an ordinary page is never read")

    blank = Image.new("RGB", (1300, 1400), (24, 24, 24))
    blank.paste(Image.new("RGB", (900, 1300), "white"), (200, 50))
    framed = Image.new("RGB", (sample_page.width + 400, sample_page.height + 100), (24, 24, 24))
    framed.paste(sample_page, (200, 50))
    for page in (sample_page, sample_page2, framed, blank, colophon_page(columns=COLUMNS[:2])):
        started = time.perf_counter()
        assert not precheck(page)
        assert time.perf_counter() - started < 0.5  # milliseconds, in fact (the report says how many)
        assert find_colophon(page, None, read=no_read) is None
    # a page that passes the test but says nothing of a colophon is none either
    assert find_colophon(colophon_page(), None, read=lambda crop: ("こんにちは", 0.9)) is None


def test_a_horizontal_colophon_is_read_line_by_line():
    lines = [("見本の物語 第3巻", 30), ("2024年5月10日 初版第1刷発行", 22), ("著者 仮野みのり", 22),
             ("発行所 株式会社見本出版", 22), ("ISBN" + ISBN, 22)]
    page = colophon_page(lines, horizontal=True)
    read = Reader([text.replace(" ", "") for text, _size in lines])
    found = find_colophon(page, None, read=read)
    assert found is not None and (found.title, found.volume, found.isbn) == ("見本の物語", "3", ISBN)
    assert len(read.sizes) == len(lines) and all(w > 3 * h for w, h in read.sizes)  # lines, top to bottom


def test_what_the_columns_say():
    def p(*texts, raws=None):
        return parse([(t, 0.8) for t in texts], raws)

    assert p("見本の物語第3巻", "著者仮野みのり") is None  # one label: no colophon
    assert p("2024年5月10日初版発行", "著者仮野", "発行所見本出版") is None  # no title: the date column is none
    c = p("ジャン", "見本の物語(第12巻)", "発行日2024年5月10日", "著者", "仮野みのり", "発行所株式会社見本出版〒101-0001東京都",
          "©Minori Karino 2024", "ISBN4ー12ー345678ー2")
    assert (c.title, c.volume, c.author, c.publisher, c.isbn) == ("見本の物語", "12", "仮野みのり", "株式会社見本出版",
                                                                  "4-12-345678-2")
    assert c.date == "2024年5月10日"
    assert p("見本の物語 vol.4", "発行者 山田", "印刷 見本印刷").volume == "4"
    assert p("見本の物語 (5)", "発行者 山田", "印刷 見本印刷").volume == "5"
    c = p("見本の物語3", "発行者 山田", "印刷 見本印刷", raws=["見本の物語③", "発行者 山田", "印刷 見本印刷"])
    assert (c.title, c.volume) == ("見本の物語", "3")
    assert p("ネジマキ13", "発行者 山田", "(C)Taro").volume == ""  # a number that is part of the title stays
    assert p("令和6年5月10日 発行", "見本の物語", "著者 仮野").date == "令和6年5月10日"
    assert find_isbn("ISBN978-4-06-123456-7C0079¥500E") == ISBN  # what follows the ISBN is not part of it
    assert find_isbn("ISBN978-4-06-123456-8") == "" and find_isbn("978 4 06 123456 7") == ISBN


@requires_ocr
def test_the_real_ocr_reads_the_title_the_volume_and_the_isbn():
    from taslation.ocr import CharspotEngine

    engine = CharspotEngine(Settings().ocr_model_dir)
    page = colophon_page()
    started = time.perf_counter()
    found = find_colophon(page, engine)
    seconds = time.perf_counter() - started
    assert found is not None, "the colophon was not read"
    assert (found.title, found.volume, found.isbn) == ("見本の物語", "3", ISBN)
    assert found.publisher == "株式会社見本出版" and found.date == "2024年5月10日" and found.confidence > 0.3
    assert seconds < 60  # an OCR read per column (about 0.3 s each on a CPU)


def test_the_whole_book_scan_records_the_colophon(sample_page, settings, monkeypatch):
    framed = Image.new("RGB", (1300, 1400), (24, 24, 24))
    framed.paste(sample_page.resize((900, 1300)), (200, 50))
    pages = [framed, colophon_page()]

    class Viewer:
        index = 0

        def capture(self, hwnd):
            return pages[self.index]

    viewer = Viewer()
    viewer.pages = pages
    monkeypatch.setattr(batch_mod, "capture_window", viewer.capture)
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    settings.settle_ms, settings.page_turn_wait_ms = 10, 300
    checked, real_precheck, real_find = [], colophon.precheck, colophon.find_colophon
    monkeypatch.setattr(colophon, "precheck", lambda frame, margins: checked.append(frame) or real_precheck(frame, margins))
    read = Reader([text.replace(" ", "") for text, _size in COLUMNS], rotated="ISBN" + ISBN)
    monkeypatch.setattr(colophon, "find_colophon", lambda frame, ocr, margins: real_find(frame, ocr, margins, read=read))
    cache = CacheStore(settings.cache_dir).open("Star Road 3", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    progress = read_book(BatchReader(pipeline, hwnd=1, settings=settings, context_mode=False))
    assert progress.pages == 2 and len(checked) == 2  # the cheap test on every page read
    assert len(read.sizes) == len(COLUMNS)  # the OCR on the colophon only
    assert progress.colophon is not None and progress.colophon.name == "見本の物語 3"
    assert progress.colophon.isbn == ISBN
