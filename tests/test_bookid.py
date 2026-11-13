"""A book recognised by its pages (`bookid.recognise`) on a store of synthetic caches - also when the page was
translated under another capture area, when the viewer's window was resized since (two pages agreeing within
AGREE_WITHIN bits) and when the cache was kept before the page unit grew through black panels -, the caches'
identities read without building their pages (`CacheStore.identities`), the colophon's details in a cache's header,
the ISBN, the names that name no book and the name last given in a viewer."""
from __future__ import annotations

import json
import random

import numpy as np
import pytest
from PIL import Image, ImageDraw

from taslation import fingerprint as fp
from taslation import viewerparts
from taslation.bookid import (
    AGREE_PAGES,
    AGREE_WITHIN,
    LAST_NAMES,
    LAST_NAMES_KEPT,
    WHOLE,
    Recognised,
    clean_identity,
    frame_areas,
    generic_book_name,
    identity_of,
    isbn_key,
    last_name,
    page_groups,
    page_probes,
    recognise,
    remember_name,
    same_book_name,
)
from taslation.cache import BookCache, CachedBubble, CachedPage, CacheStore
from taslation.detect.page_area import find_page_area, page_area_margins
from taslation.i18n import load_ui_table, save_ui_language

LEARNED = ("Yomizuq", "FOLIO☆QAT")  # invented viewers, as this computer learned them


@pytest.fixture(autouse=True)
def viewers_learned():
    """This computer has learned the viewers of `LEARNED` (how: tests/test_viewer_parts.py): their names name no
    book, as a browser's never does."""
    viewerparts.change(lambda memory: memory.learn(LEARNED))


def _page(seed: int, size=(360, 520), dot: tuple[int, int] | None = None) -> Image.Image:
    """A drawn page: a frame and a band across it (no gutter, so one page unit), shapes placed by *seed*."""
    rng = random.Random(seed)
    page = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(page)
    w, h = size
    d.rectangle((8, 8, w - 9, h - 9), outline="black", width=3)
    d.rectangle((8, h // 2 - 4, w - 9, h // 2 + 4), fill="black")
    for _ in range(14):
        x, y = rng.randint(14, w - 90), rng.randint(14, h - 90)
        box = (x, y, x + rng.randint(20, 80), y + rng.randint(20, 80))
        (d.ellipse if rng.random() < 0.5 else d.rectangle)(box, fill=(rng.randint(0, 80),) * 3)
    if dot is not None:  # a near-duplicate: the same page with a mark of a few pixels
        d.rectangle((dot[0], dot[1], dot[0] + 5, dot[1] + 5), fill="black")
    return page


def _frame(*pages: Image.Image, noise: float = 0.0, seed: int = 0) -> Image.Image:
    """The pages side by side (right page first, as a spread shows them) in a dark viewer, with capture noise."""
    w = sum(p.width for p in pages) + 60 * (len(pages) - 1)
    frame = Image.new("RGB", (w + 240, max(p.height for p in pages) + 100), (24, 24, 24))
    x = 120
    for page in reversed(pages):
        frame.paste(page, (x, 50))
        x += page.width + 60
    if noise:
        arr = np.asarray(frame).astype(np.int16)
        arr += np.random.default_rng(seed).normal(0, noise, arr.shape).round().astype(np.int16)
        frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return frame


def _units(image: Image.Image) -> list[fp.PageUnit]:
    return fp.analyze(np.asarray(image.convert("RGB")))


def _cache(store: CacheStore, book: str, pages: list[Image.Image], language: str = "English", **details) -> BookCache:
    cache = store.open(book, "m", language)
    for page in pages:
        for unit in _units(_frame(page)):
            cache.add(CachedPage(fingerprint=unit.fingerprint, aspect=unit.aspect,
                                 bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text="Hello there.")], seq=-1))
    if details:
        cache.set_details(**details)
    cache.save()
    return cache


DUP = _page(900)
DUP_TOO = _page(900, dot=(200, 400))


def _store(tmp_path) -> CacheStore:
    store = CacheStore(tmp_path / "cache")
    _cache(store, "Star Road 1", [_page(1), _page(2), _page(3), DUP])
    _cache(store, "Star Road 2", [_page(11), _page(12), DUP_TOO])
    _cache(store, "Other Book", [_page(21), _page(22)], isbn="978-4-06-123456-7", title="Other Book", volume="1")
    _cache(store, "Yomizuq", [_page(2), _page(31)])  # kept before the name was asked for: never an answer
    return store


def test_a_page_is_recognised_as_the_book_whose_cache_holds_it(tmp_path):
    store = _store(tmp_path)
    found = recognise(store, _frame(_page(2), noise=3.0), "English")
    assert [r.book for r in found] == ["Star Road 1"] and found[0].pages == 1 and 0 <= found[0].distance <= 6
    assert isinstance(found[0], Recognised) and tuple(found[0]) == (found[0].book, found[0].distance, 1)
    assert recognise(store, _frame(_page(77)), "English") == []  # in no cache
    assert recognise(store, [], "English") == [] and recognise(CacheStore(tmp_path / "none"), _frame(_page(2))) == []


def test_a_near_duplicate_page_in_two_books_gives_both_and_a_spread_ranks_them(tmp_path):
    store = _store(tmp_path)
    d = fp.hamming(_units(_frame(DUP))[0].fingerprint, _units(_frame(DUP_TOO))[0].fingerprint)
    assert 0 < d <= 6  # the mark changes a few bits: the same page for the cache's replace distance
    found = recognise(store, _frame(DUP), "English")
    assert [r.book for r in found] == ["Star Road 1", "Star Road 2"]  # the exact page first
    assert found[0].distance == 0 and found[1].distance == d and found[0].pages == found[1].pages == 1
    spread = _frame(_page(12), DUP)  # a page of the second book and the duplicate: two matches beat one
    units = _units(spread)
    assert len(units) == 2
    found = recognise(store, spread, "English")
    assert [(r.book, r.pages) for r in found] == [("Star Road 2", 2), ("Star Road 1", 1)]
    # fingerprints instead of a capture, and the frame from before with the current one
    assert recognise(store, [u.fingerprint for u in units], "English")[0] == found[0]
    assert recognise(store, [_frame(_page(3)), _frame(_page(11))], "English") == [
        Recognised("Star Road 1", 0, 1), Recognised("Star Road 2", 0, 1)]


def test_a_name_that_names_no_book_is_never_recognised_and_an_isbn_beats_fingerprints(tmp_path):
    store = _store(tmp_path)
    assert [r.book for r in recognise(store, _frame(_page(31)), "English")] == []  # only "Yomizuq" has it
    assert [r.book for r in recognise(store, _frame(_page(2)), "English")] == ["Star Road 1"]
    # the colophon on screen names Other Book by its ISBN (hyphens as the OCR read them): only that book
    found = recognise(store, _frame(_page(2)), "English", isbn="ISBN978ー4ー06ー123456ー7")
    assert found == [Recognised("Other Book", 0, 0)]
    found = recognise(store, _frame(_page(21)), "English", isbn="9784061234567")
    assert found == [Recognised("Other Book", 0, 1)]
    assert [r.book for r in recognise(store, _frame(_page(2)), "English", isbn="978-4-06-123456-8")] == [
        "Star Road 1"]  # not a valid ISBN: the fingerprints decide


def test_the_target_language_breaks_a_tie_and_other_languages_count(tmp_path):
    store = CacheStore(tmp_path / "cache")
    _cache(store, "Aki 1", [_page(5)], language="German")
    _cache(store, "Haru 1", [_page(5)], language="English")
    assert [r.book for r in recognise(store, _frame(_page(5)), "German")] == ["Aki 1", "Haru 1"]
    assert [r.book for r in recognise(store, _frame(_page(5)), "English")] == ["Haru 1", "Aki 1"]
    _cache(store, "Aki 1", [_page(6)], language="English")  # one book in two languages is one answer
    assert [r.book for r in recognise(store, [_frame(_page(5)), _frame(_page(6))], None)] == ["Aki 1", "Haru 1"]


def test_identities_read_the_header_and_the_fingerprints_without_the_pages(tmp_path):
    store = _store(tmp_path)
    ids = {i.book: i for i in store.identities()}
    assert set(ids) == {"Star Road 1", "Star Road 2", "Other Book", "Yomizuq"}
    assert len(ids["Star Road 1"].pages) == 4 and all(len(f) == 80 and a > 0 for f, a in ids["Star Road 1"].pages)
    assert ids["Other Book"].details == {"title": "Other Book", "volume": "1", "isbn": "978-4-06-123456-7"}
    assert identity_of(store, "Other Book", "English")["isbn"] == "978-4-06-123456-7"
    assert identity_of(store, "Star Road 1") == {}
    cache_dir = tmp_path / "cache"
    path = store.path_for("Star Road 2")
    # a copy kept beside a cache is never read; a file written by hand in another key order is read the slow way
    (cache_dir / "Star_Road_2.unreadable-20260101-000000.json").write_bytes(path.read_bytes())
    data = json.loads(path.read_text(encoding="utf-8"))
    (cache_dir / "Hand_Made.json").write_text(json.dumps({
        "pages": data["pages"][:1], "schema": 1, "book": "Hand Made", "language": "English",
        "isbn": "4-12-345678-2"}), encoding="utf-8")
    (cache_dir / "Cut_Short.json").write_text(path.read_text(encoding="utf-8")[:300], encoding="utf-8")
    (cache_dir / "Newer.json").write_text(json.dumps({"schema": 99, "book": "Newer", "pages": []}), encoding="utf-8")
    ids = {i.book: i for i in store.identities()}
    assert set(ids) == {"Star Road 1", "Star Road 2", "Other Book", "Yomizuq", "Hand Made"}
    assert ids["Hand Made"].pages == ids["Star Road 2"].pages[:1] and ids["Hand Made"].details == {"isbn": "4-12-345678-2"}
    # what a load gives, without its pages: the same fingerprints in the same order
    loaded = BookCache.load(path)
    assert [p.fingerprint for p in loaded.pages] == [f for f, _a in ids["Star Road 2"].pages]
    # read again once a file changes; forgotten once it is gone
    cache = store.open("Star Road 2", "m")
    cache.set_details(isbn="9784061234567", author="Karino")
    cache.save()
    assert {i.book: i for i in store.identities()}["Star Road 2"].details == {"author": "Karino", "isbn": "9784061234567"}
    store.delete("Star Road 2")
    assert "Star Road 2" not in {i.book for i in store.identities()}


def test_the_colophons_details_stay_in_the_header_through_saves_and_merges(tmp_path):
    store = CacheStore(tmp_path / "cache")
    cache = store.open("Book 3", "m")
    assert cache.set_details(title="Book", volume="3", isbn="978-4-06-123456-7", author="A\x00uthor  Name")
    assert not cache.set_details(title="Book")  # nothing changed
    cache.save()
    data = json.loads(store.path_for("Book 3").read_text(encoding="utf-8"))
    assert list(data)[-1] == "pages" and data["author"] == "Author Name" and data["volume"] == "3"
    other = store.open("Book 3", "m")  # another process: it adds a page; the header stays
    other.add(CachedPage(fingerprint="a" * 80, aspect=0.7, bubbles=[], seq=-1))
    other.save()
    cache.add(CachedPage(fingerprint="b" * 80, aspect=0.7, bubbles=[], seq=-1))
    cache.set_details(publisher="Star Sea")
    cache.save()  # merges the other's page, keeps its own details
    again = BookCache.load(store.path_for("Book 3"))
    assert len(again) == 2 and again.details["publisher"] == "Star Sea" and again.details["isbn"] == "978-4-06-123456-7"
    cache.set_details(author="")  # forgotten
    cache.save()
    assert "author" not in BookCache.load(store.path_for("Book 3")).details
    try:
        cache.set_details(nickname="x")
    except TypeError:
        pass
    else:
        raise AssertionError("an unknown header field is refused")


def test_isbn_identity_and_names():
    assert isbn_key("ISBN978-4-06-123456-7") == "9784061234567" == isbn_key("９７８－４－０６－１２３４５６－７")
    assert isbn_key("978ー4ー06ー123456ー7") == "9784061234567" == isbn_key("978.4.06-123456.7")  # as read
    assert isbn_key("ISBN 4-06-123456-?".replace("?", "")) == ""  # nine digits: no ISBN
    assert isbn_key("4-12-345678-2") == "9784123456784"  # an ISBN-10 in its ISBN-13 form
    assert isbn_key("4-12-345678-6") == ""  # its check digit is wrong
    assert isbn_key("978-4-06-123456-8") == "" and isbn_key("") == "" and isbn_key(None) == ""
    assert clean_identity({"title": " Star\tRoad ", "volume": "3", "isbn": "978-4-06-123456-8", "note": "x",
                           "author": "a" * 500}) == {"title": "Star Road", "volume": "3", "author": "a" * 120}
    assert clean_identity("Star Road") == {} and clean_identity({"isbn": 9784061234567}) == {}
    for name in ("Yomizuq", " yomizuq ", "", "Google Chrome", "FOLIO☆QAT", "untitled", "新しいタブ"):
        assert generic_book_name(name), name
    assert not generic_book_name("Yomizuq Reader's Guide")
    assert same_book_name("見本の物語 3", "見本の物語３") and same_book_name("Star Road 3", "star road  3")
    assert not same_book_name("Star Road 3", "Star Road 4")
    probes = page_probes(["a" * 80, ("B" * 80, 0.7), "a" * 80, "not hex", None])
    assert probes == [("a" * 80, 0.0), ("b" * 80, 0.7)]


# ------------------------------------------------------------------ a page translated under another capture area
BARS = (0, 85, 0, 0)  # an area set by hand that cuts the browser's tab strip and toolbar (rows 0-84)


def _analysed(image: Image.Image, margins) -> list[fp.PageUnit]:
    return fp.analyze(np.asarray(image.convert("RGB")), margins)


def _kept(store: CacheStore, book: str, units: list[fp.PageUnit]) -> None:
    """A cache whose pages are *units*, as the pipeline keeps the units it fingerprinted in a capture area."""
    cache = store.open(book, "m", "English")
    for unit in units:
        cache.add(CachedPage(fingerprint=unit.fingerprint, aspect=unit.aspect,
                             bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text="Hello there.")], seq=-1))
    cache.save()


def test_a_page_translated_under_another_capture_area_is_recognised(tmp_path, sample_page):
    """The same page captured with the browser's bars and without them (the bars cut off), on a light reader frame
    where the capture area moves the fingerprint far (the whole capture, an area that cuts the bars, the page panel
    found: 120-160 bits apart), and on a dark frame where it does not."""
    from test_page_area import _capture  # the browser and the reader drawn around a page

    with_bars, page = _capture(sample_page, frame=200, browser="light")
    without = with_bars.crop((0, 85, with_bars.width, with_bars.height))  # the same window without the bars
    panel = page_area_margins(find_page_area(with_bars), with_bars.size)
    assert panel == (page[0], page[1], with_bars.width - page[2], with_bars.height - page[3])
    whole, cut, inner = (_analysed(with_bars, m) for m in (WHOLE, BARS, panel))
    for a, b in ((whole, cut), (whole, inner), (cut, inner)):
        assert min(fp.hamming(x.fingerprint, y.fingerprint) for x in a for y in b) > 60
    assert frame_areas(np.asarray(without), WHOLE) == [WHOLE, page_area_margins(find_page_area(without), without.size)]

    # translated with no area set (the window read the page panel it found), read now without the browser's bars
    store = CacheStore(tmp_path / "panel")
    _kept(store, "Panel Book", inner)
    assert recognise(store, without, "English", panel=False) == []  # the area read now alone: not that page
    assert recognise(store, without, "English") == [Recognised("Panel Book", 0, 1)]  # the panel found in it too
    groups = page_groups(without)
    assert len(groups) == 2 and len(groups[0]) == 2  # the right "page" of the whole capture and the panel: one page
    other, _page_box = _capture(_page(42), frame=200, browser="light")
    assert recognise(store, other, "English") == []  # another page in the same reader is not that one

    # translated under the reader's own area (its header and slider in it); now the panel found inside it is read
    store = CacheStore(tmp_path / "hand")
    _kept(store, "Hand Book", cut)
    assert recognise(store, with_bars, "English", margins=panel) == []  # not without the reader's area
    found = recognise(store, with_bars, "English", margins=[panel, BARS])  # what the window gives: both areas
    assert [r.book for r in found] == ["Hand Book"] and found[0].distance == 0

    # a dark frame: the paper is found alike in every area, so the page always was recognised
    dark, _page_box = _capture(sample_page, frame=24, browser="light")
    dark_panel = page_area_margins(find_page_area(dark), dark.size)
    prints = {u.fingerprint for m in (WHOLE, BARS, dark_panel) for u in _analysed(dark, m)}
    assert len(prints) == 1
    store = CacheStore(tmp_path / "dark")
    _kept(store, "Dark Book", _analysed(dark, BARS))
    assert recognise(store, dark.crop((0, 85, dark.width, dark.height)), "English", panel=False) == [
        Recognised("Dark Book", 0, 1)]


def test_the_name_last_given_is_kept_by_viewer_in_ui_json(tmp_path):
    assert last_name(tmp_path, "Yomizuq - Google Chrome") == ""
    remember_name(tmp_path, "Yomizuq - Google Chrome", "  Star   Road 3 ")
    assert last_name(tmp_path, "Yomizuq - Google Chrome") == "Star Road 3"
    assert last_name(tmp_path, "新しいタブ - Google Chrome") == "Star Road 3"  # the viewer: Google Chrome's window
    assert last_name(tmp_path, "Yomizuq") == ""  # another viewer (a desktop one)
    remember_name(tmp_path, "Yomizuq - Google Chrome", "Yomizuq")  # a name that names no book is never kept
    remember_name(tmp_path, "Yomizuq - Google Chrome", "  ")
    assert last_name(tmp_path, "Yomizuq - Google Chrome") == "Star Road 3"
    save_ui_language(tmp_path, "ja")  # the window's other choices stay beside it
    remember_name(tmp_path, "Yomizuq", "見本の物語 3")
    data = json.loads((tmp_path / "ui.json").read_text(encoding="utf-8"))
    assert data == {LAST_NAMES: {"Google Chrome": "Star Road 3", "Yomizuq": "見本の物語 3"}, "language": "ja"}
    for i in range(LAST_NAMES_KEPT + 2):  # the latest viewers only
        remember_name(tmp_path, f"Viewer {i}", f"Book {i}")
    table = load_ui_table(tmp_path, LAST_NAMES)
    assert len(table) == LAST_NAMES_KEPT and "Google Chrome" not in table and "Yomizuq" not in table
    assert list(table)[-1] == f"Viewer {LAST_NAMES_KEPT + 1}" and last_name(tmp_path, "Viewer 2") == "Book 2"
    remember_name(tmp_path, "Viewer 2", "Book 2b")  # named again: the latest entry
    assert list(load_ui_table(tmp_path, LAST_NAMES))[-1] == "Viewer 2"
    (tmp_path / "ui.json").write_text(json.dumps({LAST_NAMES: ["Viewer 2"], "language": "ja"}), encoding="utf-8")
    assert last_name(tmp_path, "Viewer 2") == ""  # not a table: nothing
    (tmp_path / "ui.json").write_text(json.dumps({LAST_NAMES: {"Viewer 2": 7, "Yomizuq": "yomizuq"}}), encoding="utf-8")
    assert last_name(tmp_path, "Viewer 2") == "" and last_name(tmp_path, "Yomizuq") == ""


# ------------------------------------------------------------------ a resized window, a cache kept before the unit grew
def _bits(seed: int) -> int:
    return random.Random(seed).getrandbits(fp.FINGERPRINT_BITS)


def _off(value: int, n: int, seed: int = 0) -> str:
    """*value* with *n* of its bits flipped (chosen by *seed*), as a fingerprint."""
    for bit in random.Random(seed).sample(range(fp.FINGERPRINT_BITS), n):
        value ^= 1 << bit
    return f"{value:0{fp.FINGERPRINT_HEX_LEN}x}"


def _kept_prints(store: CacheStore, book: str, prints: list[str], language: str = "English") -> None:
    cache = store.open(book, "m", language)
    for fingerprint in prints:
        cache.add(CachedPage(fingerprint=fingerprint, aspect=0.7,
                             bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text="Hello there.")], seq=-1))
    cache.save()


def test_a_page_farther_than_the_replace_distance_counts_when_another_page_on_screen_agrees(tmp_path):
    """After a resize a page can land 7 to 20 bits from its cached self (its unit moved by a few pixels): such a
    page counts when another page on screen matches another page of the same book within AGREE_WITHIN bits; alone,
    or with a second frame of the same page, it does not, nor beyond AGREE_WITHIN."""
    assert (AGREE_WITHIN, AGREE_PAGES) == (16, 2)
    a, b, c = _bits(1), _bits(2), _bits(3)
    store = CacheStore(tmp_path / "cache")
    _kept_prints(store, "Star Road 1", [_off(a, 0), _off(b, 0)])
    _kept_prints(store, "Star Road 2", [_off(c, 0)])
    assert recognise(store, [_off(a, 3)], "English") == [Recognised("Star Road 1", 3, 1)]  # as before
    assert recognise(store, [_off(a, 10)], "English") == []  # one page, farther than 6 bits
    assert recognise(store, [_off(a, 10), _off(b, 12)], "English") == [Recognised("Star Road 1", 10, 2)]
    assert recognise(store, [_off(a, 10), _off(a, 11, seed=1)], "English") == []  # one page in two frames
    assert recognise(store, [_off(a, 10), _off(b, AGREE_WITHIN + 1)], "English") == []
    assert recognise(store, [_off(a, AGREE_WITHIN), _off(b, AGREE_WITHIN)], "English") == [
        Recognised("Star Road 1", AGREE_WITHIN, 2)]
    assert recognise(store, [_off(a, 3), _off(b, 14)], "English") == [Recognised("Star Road 1", 3, 2)]
    assert recognise(store, [_off(a, 10), _off(c, 12)], "English") == []  # two books, one page each
    assert recognise(store, [_off(a, 10), _off(b, 12)], "English", agree_pages=1) == []  # the rule off
    assert recognise(store, [_off(a, 10), _off(b, 12)], "English", agree_within=6) == []

    # the book's caches in two languages: the pages agree across them
    store = CacheStore(tmp_path / "languages")
    _kept_prints(store, "Star Road 1", [_off(a, 0)])
    _kept_prints(store, "Star Road 1", [_off(b, 0)], language="German")
    assert recognise(store, [_off(a, 9), _off(b, 13)], "English") == [Recognised("Star Road 1", 9, 2)]


def test_a_spread_is_recognised_in_a_resized_viewer(tmp_path):
    """The viewer's window made smaller and larger: the spread re-fitted at 0.8 and 1.25 times its size."""
    spread = _frame(_page(5), _page(6))
    store = CacheStore(tmp_path / "cache")
    _cache(store, "Star Road 1", [])
    cache = store.open("Star Road 1", "m", "English")
    for unit in _units(spread):
        cache.add(CachedPage(fingerprint=unit.fingerprint, aspect=unit.aspect,
                             bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text="Hello there.")], seq=-1))
    cache.save()
    for scale in (0.8, 1.25):
        resized = spread.resize((round(spread.width * scale), round(spread.height * scale)), Image.LANCZOS)
        found = recognise(store, resized, "English")
        assert [(r.book, r.pages) for r in found] == [("Star Road 1", 2)], scale


def test_a_cache_kept_before_the_unit_grew_through_black_panels_is_recognised(tmp_path):
    """Since 2026-10-31 the paper on a dark viewer grows through the page's black panels, so a page whose lower half
    is black panels has another unit, and another fingerprint, than the cache kept for it before; recognising a book
    fingerprints the page as analyze found it then too (``grow=False``)."""
    from test_fingerprint import _dark_page
    from test_fingerprint import _viewer as _dark_viewer

    img, _boxes = _dark_viewer(_dark_page())
    rgb = np.asarray(img)
    (now,), before = fp.analyze(rgb), fp.analyze(rgb, grow=False)
    # then: the upper panels alone, landscape, split as if they were a spread
    assert len(before) == 2 and all(u.box[3] < now.box[3] for u in before)
    assert min(fp.hamming(now.fingerprint, u.fingerprint) for u in before) > 36
    store = CacheStore(tmp_path / "cache")
    _kept(store, "Dark Book", before[1:])  # translated before the unit grew (its left "page")
    assert recognise(store, img, "English") == [Recognised("Dark Book", 0, 1)]
    assert [[p for p, _aspect in group] for group in page_groups(img)] == [
        [now.fingerprint, before[0].fingerprint], [before[1].fingerprint]]
    light = _frame(_page(5))  # a page without black panels: one unit, grown or not
    assert [u.fingerprint for u in _units(light)] == [u.fingerprint for u in fp.analyze(np.asarray(light), grow=False)]
    assert len(page_groups(light)[0]) == 1
