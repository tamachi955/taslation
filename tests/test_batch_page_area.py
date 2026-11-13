"""A whole-book run reads each page within the page panel of its own frame. A run that starts while the viewer shows a
cover alone - centred on a dark ground, narrower than the spreads after it - widens its capture area with the panel of
every page it takes, before it reads that page (`detect.page_area.JoinedArea`, `batch.BatchReader._meet`), so that the
spreads are read whole and not only in the middle band the cover's area held. The area never narrows, a frame without
a panel changes nothing, the reader's own area is never exceeded, the cover read in the narrow area is still found and
lettered once the area has grown, the watch neither loses nor doubles a page where the area grows, and the window's
area once the run is done is at least the run's. Synthetic frames of the fixture pages only: no real window, nothing of
this machine's own state folder."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image, ImageChops, ImageDraw
from test_batch_follows_reader import desk, in_hand, until  # noqa: F401 - the viewer the run looks at; no key at all

from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.capture import WindowInfo
from taslation.config import Settings
from taslation.detect.page_area import JoinedArea, find_page_area, margins_box, page_area_margins, page_panel
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui.jobs import JobsMixin
from taslation.ui.live import LiveViewMixin

W, H, BAR = 1600, 1000, 40  # the viewer's capture, a light toolbar along its top
PAGE = (620, 877)  # a page as the viewer draws it
GROUND = (30, 30, 30)  # the viewer's dark ground around the pages
VIEWER = WindowInfo(hwnd=1, title="Yomizuq - Reader", class_name="ReaderFrame", pid=1, rect=(0, 0, W, H))
NO_PANEL = Image.new("RGB", (W, H), "white")  # nothing dark around anything: no page panel is found in it


def shown(*pages: Image.Image, size: tuple[int, int] = (W, H), page: tuple[int, int] = PAGE,
          bar: int = BAR) -> Image.Image:
    """*pages* side by side, centred on the dark ground below the toolbar, as a viewer shows a page alone (a cover)
    or a spread."""
    width, height = size
    image = Image.new("RGB", size, GROUND)
    if bar:
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, bar - 1), fill=(235, 235, 235))
        for x in range(100, 600, 14):
            draw.rectangle((x, 14, x + 8, 24), fill=(60, 60, 60))  # the toolbar's buttons
    x, y = (width - page[0] * len(pages)) // 2, bar + (height - bar - page[1]) // 2
    for p in pages:
        image.paste(p.resize(page, Image.LANCZOS), (x, y))
        x += page[0]
    return image


@pytest.fixture(scope="module")
def book(sample_page, sample_page2) -> SimpleNamespace:
    """A cover alone, then two spreads of four other pages (the fixture pages, mirrored and turned: no two alike)."""
    flip, turn = Image.FLIP_LEFT_RIGHT, Image.ROTATE_180
    cover = shown(sample_page)
    spreads = [shown(sample_page2, sample_page.transpose(flip)), shown(sample_page2.transpose(flip),
                                                                        sample_page.transpose(turn))]
    return SimpleNamespace(cover=cover, spreads=spreads, cover_panel=find_page_area(cover),
                           spread_panel=find_page_area(spreads[0]),
                           narrow=page_area_margins(find_page_area(cover), (W, H)),
                           wide=page_area_margins(find_page_area(spreads[0]), (W, H)))


def lines_alone(frames, tmp_path) -> list[tuple[tuple[int, int, int, int], int]]:
    """What scanning each frame alone in the whole capture finds: the Japanese lines of each page unit, by its box."""
    s = Settings(state_dir=tmp_path / "alone")
    s.margins = (0, 0, 0, 0)
    pipeline = Pipeline(s, ocr=FakeOcr())
    return sorted((tuple(u.box), len(u.japanese())) for f in frames for u in pipeline.scan(f, skip_cached=False).units)


def holds(margins, box) -> bool:
    """Does the capture area *margins* leave of a W x H capture hold *box* whole?"""
    x0, y0, x1, y1 = margins_box(margins, (W, H))
    return x0 <= box[0] and y0 <= box[1] and box[2] <= x1 and box[3] <= y1


class Window:
    """The window's record of the viewer's page panels and its capture area (`ui.live.LiveViewMixin`), and the
    events a run tells it (`JobsMixin._handle_event`); nothing of Tk, no real window."""

    _find_page = LiveViewMixin._find_page
    _found_margins = LiveViewMixin._found_margins
    _apply_found_margins = LiveViewMixin._apply_found_margins
    _hand_set = LiveViewMixin._hand_set
    _inner_margins = LiveViewMixin._inner_margins
    _run_area = LiveViewMixin._run_area
    _run_found = LiveViewMixin._run_found
    _handle_event = JobsMixin._handle_event

    def __init__(self, tmp_path, hand=None):
        self.settings = Settings(state_dir=tmp_path / "state")
        self.settings.margins = hand if hand is not None else (0, 0, 0, 0)
        self.selected, self.ready, self.busy = VIEWER, False, False
        self._manual_area, self._hand_area = hand is not None, hand
        self._page_areas: dict = {}
        self._inner_areas: dict = {}
        self._area_hinted = False


def start_run(window: Window, desk, frames) -> SimpleNamespace:
    """A whole-book run over *frames* (the stand-in viewer shows them), started as the window starts one: its area
    applied (`_apply_found_margins` starting), the run's area from its record (`_run_area`), the pipeline on the
    window's own settings, the run on a copy of them (`JobsMixin._job_batch`). What every scan read in (the margins,
    and the frame's panel as the run looks for it) is noted as the scan starts."""
    desk.pages[:] = frames
    desk.index = 0
    window._apply_found_margins(starting=True)
    area = window._run_area()
    cache = CacheStore(window.settings.cache_dir).open("Book", "fake")
    pipeline = Pipeline(window.settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    told: list[tuple[str, dict]] = []
    scans: list[tuple[tuple[int, ...], tuple[int, int, int, int] | None]] = []
    scan = pipeline.scan

    def noted(frame, **kw):
        scans.append((tuple(pipeline.settings.margins), page_panel(frame, area.hand)))
        return scan(frame, **kw)

    pipeline.scan = noted  # type: ignore[method-assign]
    reader = BatchReader(pipeline, hwnd=VIEWER.hwnd, settings=window.settings.with_overrides(context_mode=True),
                         context_mode=True, preflight=[], show=lambda kind, data: told.append((kind, data)),
                         page_area=area)
    window.busy = True
    return SimpleNamespace(reader=reader, pipeline=pipeline, cache=cache, told=told, scans=scans, area=area)


def run_ends(window: Window, run: SimpleNamespace) -> None:
    """The window takes the run's events in order, as its event pump does while the run is busy, then the run's end
    (`JobsMixin._batch_done`: not busy, the area found applied)."""
    for kind, data in list(run.told):
        if kind == "page_area":
            window._handle_event(kind, data)
    window.busy = False
    window._apply_found_margins()


# ------------------------------------------------------------------ every line of the spreads is read
@pytest.mark.parametrize("hand", (None, (0, BAR, 0, 0), (100, BAR, 100, 0)),
                         ids=("no-area", "toolbar-trimmed", "area-wider-than-the-spreads"))
def test_a_run_started_on_a_cover_reads_every_line_of_the_spreads_after_it(desk, book, tmp_path, hand):
    """The bug this is about: the run kept the area in force as it started - the cover's - and read each spread only
    in the middle band, the halves of its pages nearest the spine. Every page is read as it is when scanned alone in
    the whole capture, with and without an area of the reader's (the outer bound)."""
    assert book.narrow == (490, 81, 490, 42) and book.wide == (180, 81, 180, 42)  # (the frames this is about)
    window = Window(tmp_path, hand)
    window._find_page(book.cover)  # the viewer showed the cover alone: the window's area is the cover's
    assert tuple(window.settings.margins) == book.narrow
    frames = [book.cover, *book.spreads]
    run = start_run(window, desk, frames)
    progress = read_book(run.reader, desk)
    alone = lines_alone(frames, tmp_path)
    assert sum(n for _box, n in alone) == 30 and len(alone) == 5  # six lines on every page
    assert progress.pages == 3 and progress.found == 30
    assert sorted((tuple(u.box), len(u.japanese())) for u in run.reader._units) == alone
    assert len(run.scans) == 3 and all(holds(margins, panel) for margins, panel in run.scans)  # each read whole
    assert run.scans[0][0] == book.narrow and run.scans[1][0] == run.scans[2][0] == book.wide
    assert len(run.cache) == 5  # every page translated and stored


# ------------------------------------------------------------------ only wider, within the reader's area
def test_the_area_only_grows_and_a_frame_without_a_panel_changes_nothing(book):
    area = JoinedArea((0, 0, 0, 0))  # nothing known yet: the first panel gives the area, as the window's would
    steps = []
    for frame in (book.cover, book.spreads[0], book.cover, NO_PANEL, book.spreads[1], book.cover):
        changed = area.meet(frame)
        steps.append((changed, area.margins))
    assert steps == [(True, book.narrow), (True, book.wide), (False, book.wide), (False, book.wide),
                     (False, book.wide), (False, book.wide)]
    assert area.found == book.spread_panel
    # the window had seen a spread before the reader went back to the cover: the run never narrows to the cover
    area = JoinedArea(book.wide, None, (W, H), book.spread_panel)
    assert not area.meet(book.cover) and area.margins == book.wide
    # a run that read a page without a panel in the whole capture keeps it whole: no page read needs reading again
    area = JoinedArea((0, 0, 0, 0))
    assert not area.meet(NO_PANEL) and area.margins == (0, 0, 0, 0)
    assert area.meet(book.cover) and area.margins == (0, 0, 0, 0) and area.found == book.cover_panel
    # the viewer's window resized: the panels start over, margins being pixels of one capture size
    area = JoinedArea(book.wide, None, (W, H), book.spread_panel)
    smaller = shown(book.cover.crop((490, 81, 1110, 958)), size=(1200, 800), page=(400, 566))
    assert area.meet(smaller) and area.size == (1200, 800)
    assert area.margins == page_area_margins(find_page_area(smaller), (1200, 800))


def test_the_readers_own_area_is_never_exceeded(book):
    hand = (250, BAR, 250, 0)  # the reader's own area cuts into the spreads: it stays the outer bound
    area = JoinedArea(hand, hand)
    seen = []
    for frame in (book.cover, book.spreads[0], NO_PANEL, book.cover, book.spreads[1]):
        area.meet(frame)
        seen.append(area.margins)
    assert seen[0] == book.narrow and seen[1:] == [(250, 81, 250, 42)] * 4
    assert all(m >= h for margins in seen for m, h in zip(margins, hand))


def test_a_page_that_fills_the_readers_area_within_tight_px_is_the_area_itself(sample_page, sample_page2, tmp_path):
    """`TIGHT_PX`: a panel found within a few pixels of every side of the reader's area is that area. Joined with a
    cover narrower than the spreads the area was drawn around, it is the area that counts, in a run (`page_panel`)
    and in the window (`_find_page`) alike."""
    size, page = (960, 600), (280, 396)
    cover = shown(sample_page, size=size, page=page, bar=0)
    spread = shown(sample_page2, sample_page.transpose(Image.FLIP_LEFT_RIGHT), size=size, page=page, bar=0)
    assert find_page_area(spread) == (200, 102, 760, 498)
    hand = (194, 96, 194, 96)  # drawn 6 px around the spreads
    area = JoinedArea(hand, hand)
    assert area.meet(cover) and area.margins == (340, 102, 340, 102)  # the cover's panel inside the area
    assert area.meet(spread) and area.margins == hand
    assert not area.meet(cover) and area.margins == hand
    window = Window(tmp_path, hand)
    window._find_page(cover)
    assert tuple(window.settings.margins) == (340, 102, 340, 102)
    window._find_page(spread)
    assert tuple(window.settings.margins) == hand  # (not the cover's area on the spread any more)


def test_single_pages_and_then_a_spread_the_not_the_book_guard_takes_the_spread(desk, book, sample_page, sample_page2,
                                                                                 tmp_path):
    """Six pages alone after one another (the not-the-book guard has learnt the book's pages from them), then a
    spread: the area grows for it, and its pages are still the book's, read whole."""
    flip, down = Image.FLIP_LEFT_RIGHT, Image.FLIP_TOP_BOTTOM
    singles = [shown(p) for p in (sample_page, sample_page2, sample_page.transpose(Image.ROTATE_180),
                                  sample_page2.transpose(Image.ROTATE_180), sample_page.transpose(down),
                                  sample_page2.transpose(down))]
    spread = shown(sample_page.transpose(flip), sample_page2.transpose(flip))
    window = Window(tmp_path)
    window._find_page(singles[0])
    run = start_run(window, desk, [*singles, spread])
    assert run.reader.guard_after_units <= len(singles)
    progress = read_book(run.reader, desk)
    assert progress.pages == 7 and progress.found == 6 * 8
    assert sorted((tuple(u.box), len(u.japanese())) for u in run.reader._units) == lines_alone([*singles, spread],
                                                                                               tmp_path)


# ------------------------------------------------------------------ the cover read in the narrow area
def test_the_cover_read_in_the_narrow_area_is_still_found_and_lettered_once_the_area_has_grown(desk, book, tmp_path):
    window = Window(tmp_path)
    window._find_page(book.cover)
    run = start_run(window, desk, [book.cover, *book.spreads])
    progress = read_book(run.reader, desk)
    assert progress.pages == 3 and progress.summary.code == "batch.finished" and len(run.cache) == 5
    assert run.scans[0][0] == book.narrow and tuple(run.pipeline.settings.margins) == book.wide  # it grew
    cover_unit = next(u for u in run.reader._units if holds(book.narrow, u.box))
    seq = run.reader._seq_of[id(cover_unit)]
    picture = run.pipeline.page_picture(run.reader.images, seq)  # as the cache letters it after the run, wide area
    assert picture is not None and picture.size == book.cover.size
    assert ImageChops.difference(picture.convert("RGB"), book.cover).getbbox() is not None  # lettered
    scan = run.pipeline.scan(book.cover, skip_cached=True)  # the viewer shows the cover again: from the cache
    assert len(scan.units) == 1 and scan.units[0].cached
    def asked(*_a, **_k):
        raise AssertionError("the model was asked again for a page the cache holds")

    run.pipeline.translator.translate_page = asked
    result = run.pipeline.process(book.cover)  # the window's own reading of it: lettered from the cache
    assert result.cache_hits == 1 and len(result.translated) == 6 and not result.error


# ------------------------------------------------------------------ the window after the run
def test_the_windows_area_after_the_run_is_at_least_the_runs(desk, book, tmp_path):
    window = Window(tmp_path)
    window._find_page(book.cover)
    run = start_run(window, desk, [book.cover, *book.spreads])
    read_book(run.reader, desk)
    told = [data for kind, data in run.told if kind == "page_area"]
    assert told and told[-1]["found"] == book.spread_panel and told[-1]["hand"] is None
    assert tuple(told[-1]["margins"]) == book.wide
    run_ends(window, run)
    assert all(w <= r for w, r in zip(window.settings.margins, run.reader.margins))
    assert tuple(window.settings.margins) == book.wide
    assert window._run_area().margins == book.wide  # the next run starts from it


def test_with_the_readers_area_the_window_keeps_the_run_within_it(desk, book, tmp_path):
    hand = (0, BAR, 0, 0)
    window = Window(tmp_path, hand)
    window._find_page(book.cover)
    run = start_run(window, desk, [book.cover, *book.spreads])
    read_book(run.reader, desk)
    run_ends(window, run)
    assert tuple(window.settings.margins) == book.wide and window._hand_area == hand and not window._page_areas


def test_a_run_that_read_a_page_in_the_whole_capture_leaves_the_window_reading_it_whole(desk, book, tmp_path):
    """The run started with no panel known and its first page had none: it read that page in the whole capture, and
    the panel of a spread later does not narrow it; the window, told the run's area as well, does not narrow below it
    either (its own frames found no panel before: its area was the whole capture as the run started)."""
    window = Window(tmp_path)
    page_filling = book.spreads[1].crop((180, 81, 1420, 958)).resize((W, H))  # a page filling the whole window
    window._find_page(page_filling)
    assert tuple(window.settings.margins) == (0, 0, 0, 0)
    run = start_run(window, desk, [page_filling, book.spreads[0]])
    read_book(run.reader, desk)
    assert [margins for margins, _panel in run.scans] == [(0, 0, 0, 0), (0, 0, 0, 0)]
    run_ends(window, run)
    assert tuple(window.settings.margins) == (0, 0, 0, 0)


def test_what_a_run_tells_of_another_viewer_or_another_area_of_the_readers_is_left_alone(book, tmp_path):
    window = Window(tmp_path)
    data = {"hwnd": VIEWER.hwnd, "size": (W, H), "found": book.spread_panel, "hand": None, "margins": book.wide}
    window._handle_event("page_area", {**data, "hwnd": 99})  # another viewer's window
    window._handle_event("page_area", {**data, "hand": (0, BAR, 0, 0)})  # an area the window has no more
    assert not window._page_areas and tuple(window.settings.margins) == (0, 0, 0, 0)
    window.busy = True  # in the middle of the run: the record follows, the area waits for the run's end
    window._handle_event("page_area", data)
    assert window._page_areas and tuple(window.settings.margins) == (0, 0, 0, 0)
    window.busy = False
    window._apply_found_margins()
    assert tuple(window.settings.margins) == book.wide


# ------------------------------------------------------------------ the watch where the area grows
def test_the_watch_neither_loses_nor_doubles_a_page_where_the_area_grows(desk, book, tmp_path):
    """The reader goes from the cover to a spread (the area grows there), back to the cover and on to the second
    spread: three pages, each read once, no page taken for two and none gone by."""
    window = Window(tmp_path)
    window._find_page(book.cover)
    run = start_run(window, desk, [book.cover, book.spreads[0], book.spreads[1]])
    reader = run.reader
    thread, _results = in_hand(reader.run)
    try:
        for i in (0, 1, 0, 2):
            desk.index = i
            assert until(lambda: reader._on_show is desk.pages[i])
        assert until(lambda: reader.progress.pages == 3)
    finally:
        reader.finish()
        thread.join(30)
    assert not thread.is_alive()
    stages = [data for kind, data in run.told if kind == "page_stage" and data["stage"] == "read"]
    assert {d["seq"] for d in stages} == {1, 2, 3}
    assert not [d for d in stages if d["state"] in ("missed", "merged")]
    assert sorted(d["seq"] for d in stages if d["state"] == "done") == [1, 2, 3]
    assert reader.progress.pages == 3 and len(run.scans) == 3 and not reader._missed
    assert len(reader._units) == 5 and reader.progress.found == 30


def test_the_area_is_widened_by_the_packer_alone_and_read_in_between_two_frames(desk, book, tmp_path):
    """Thread by thread: only the packer meets the frames (`_meet`), and the reading loop takes the area in only when
    it starts on a frame (`_read_in`), so that one frame's scan reads one area."""
    window = Window(tmp_path)
    window._find_page(book.cover)
    run = start_run(window, desk, [book.cover, *book.spreads])
    met: list[str] = []
    meet = run.area.meet

    def noted(frame):
        met.append(threading.current_thread().name)
        return meet(frame)

    run.area.meet = noted  # type: ignore[method-assign]
    read_book(run.reader, desk)
    assert met and set(met) == {"batch-packer"}
    assert all(holds(margins, panel) for margins, panel in run.scans)
