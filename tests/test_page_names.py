"""The name check of the pages read one by one: each page's lines (its Japanese, the text stored and where) kept in the
worker's memory only (`name_variants.PageLines`, bounded, one book at a time) and looked at with the run's check
(`find_variants`); a name new to the book in this session is offered on the band, quietly and once, and the run's
dialog and change make it one (`ui.name_check`). The pages are the stand-in pages of tests/fixtures, read by the fake
OCR with invented lines; nothing touches the real state folder."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from helpers import FakeOcr, store_text
from PIL import Image

from taslation.cache import CacheStore
from taslation.name_variants import PAGE_LINES_MAX, PageLines, RunLine, find_variants
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui import jobs, name_check, status

from test_names_helper import Var
from test_names_helper import Window as NamesWindow

# two pages of six bubbles each (the fake OCR reads them in turn): 竜司 is "Ryuji" on the first page, "Ryūji" on the
# second; neither page alone renders him in two ways
PAGE1 = [("竜司さん、おはよう", "Morning, Ryuji-san."), ("竜司さんは？", "Where's Ryuji-san?"),
         ("竜司が来た", "Ryuji is here."), ("時間がない", "There is no time."), ("行こう", "Let's go."),
         ("待って", "Wait for me.")]
PAGE2 = [("竜司さん！", "Ryūji-san!"), ("竜司くんか", "Ryūji, huh."), ("おはよう", "Good morning."),
         ("隠れて", "Hide here."), ("大丈夫だよ", "It's fine."), ("ありがとう", "Thank you.")]
JAPANESE = [ja for ja, _en in PAGE1 + PAGE2]


class Window:
    """The parts of the App the pages' name check uses: the worker's job of a page, the event the window takes, the
    band."""

    _job_translate = app_mod.App._job_translate
    _say_failed_save = app_mod.App._say_failed_save
    _look_for_colophon = app_mod.App._look_for_colophon
    _offer_page_names = app_mod.App._offer_page_names
    _band_view = app_mod.App._band_view
    batch = None
    _batching = False
    _names_dialog = None
    _names_found = None

    def __init__(self, pipeline, settings):
        self.pipeline, self.settings = pipeline, settings
        self.events: list[tuple[str, dict]] = []
        self._colophon_reads: dict[str, int] = {}
        self._page_lines = PageLines()
        self._names_offered: set = set()
        self._band = None
        self.bands: list = []
        self.book_var, self.lang_var = Var("Book"), Var("English")

    def _use_model(self, model, language):
        pass

    def _ensure_cache(self, book, model, language):
        return True

    def _post(self, kind, **data):
        self.events.append((kind, data))
        if kind == "page_names":  # (as `_handle_event` takes it)
            self._offer_page_names(name_check.keep_page_found(self, data))

    def _show_band(self):
        self.bands.append(dict(self._band) if self._band is not None else None)

    def review_names(self):
        pass

    def close_band(self):
        self._band = None

    def _held_readings(self):
        return None

    def offers(self):
        return [data for kind, data in self.events if kind == "page_names"]


@pytest.fixture
def desk(settings):
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(JAPANESE), translator=DictTranslator(dict(PAGE1 + PAGE2)), cache=cache)
    return SimpleNamespace(cache=cache, pipeline=pipeline, window=Window(pipeline, settings))


def read(w, page):
    """*page* read page by page, as F5 or Auto read it (`JobsMixin._job_translate`, in the worker)."""
    w._job_translate(page, "Book", "fake", "English")
    return next(data["result"] for kind, data in reversed(w.events) if kind == "result")


def test_a_name_rendered_two_ways_on_two_pages_read_one_by_one_is_offered_once(desk, sample_page, sample_page2):
    w = desk.window
    first = read(w, sample_page)
    assert len(first.translated) == 6 and w.offers() == [] and w._band is None  # one page renders him one way
    assert len(w._page_lines) == 6
    read(w, sample_page2)
    (offer,) = w.offers()
    assert [v.source for v in offer["variants"]] == ["竜司"]
    assert all(line.source == "" for line in offer["lines"])  # (the window gets no Japanese line)
    assert w._band == {"kind": "names", "page_names": 1} and w.bands[-1] == w._band  # quietly, on the band
    lines, buttons = w._band_view()
    assert lines == ["1 name(s) rendered in more than one way in the pages read so far."]
    assert [label for label, _do in buttons] == ["Review names...", "Close"]
    found = w._names_found
    assert found.book == "Book" and found.language == "English"
    (v,) = found.variants
    assert v.counts() == [("Ryuji", 3), ("Ryūji", 2)]

    read(w, sample_page2)  # the page again: nothing new, nothing looked at again
    assert len(w.offers()) == 1
    w._band = None
    assert name_check.keep_page_found(w, offer) == 0 and w._band is None  # the name is offered once a session
    assert w._names_found is found


def test_the_name_chosen_changes_the_lines_of_both_pages(desk, sample_page, sample_page2, settings):
    w = desk.window
    read(w, sample_page)
    read(w, sample_page2)
    names = NamesWindow(desk.cache, None)
    names.pipeline = desk.pipeline
    names._names_found = w._names_found
    (v,) = w._names_found.variants
    assert name_check.apply_name(names, v, "Ryūji", False)
    texts = sorted(b.text for p in desk.cache.pages for b in p.bubbles if "Ry" in b.text)
    assert texts == sorted(["Morning, Ryūji-san.", "Where's Ryūji-san?", "Ryūji is here.", "Ryūji-san!", "Ryūji, huh."])
    assert names.lines[-1] == '竜司 is "Ryūji" now: changed in 3 line(s).'
    assert name_check.take_back_name(names, v)
    assert "Ryuji is here." in [b.text for p in desk.cache.pages for b in p.bubbles]

    # the memory follows the cache: once the name is made one, the next page translated finds the pages before as
    # the cache holds them now, and the name, offered before, is not offered again
    assert name_check.apply_name(names, v, "Ryūji", False)
    before = {line.where for line in w._page_lines.lines()}
    read(w, sample_page)  # (from the cache: no Japanese to look at, nothing new)
    assert len(w._page_lines) == 12 and len(w.offers()) == 1
    read(w, sample_page.transpose(Image.FLIP_LEFT_RIGHT))  # a page not read yet (the fake OCR's first page's lines)
    assert {line.text for line in w._page_lines.lines() if line.where in before and "Ry" in line.text} == {
        "Morning, Ryūji-san.", "Where's Ryūji-san?", "Ryūji is here.", "Ryūji-san!", "Ryūji, huh."}
    assert len(w._page_lines) == 18 and len(w.offers()) == 2 and len(w.bands) == 1  # (竜司: offered once)


def test_the_lines_stay_in_memory_and_nothing_of_them_is_written(desk, sample_page, sample_page2, settings):
    w = desk.window
    read(w, sample_page)
    read(w, sample_page2)
    assert w.offers()
    files = [p for p in settings.state_dir.rglob("*") if p.is_file()]
    assert files  # (the cache was saved: the translations)
    for path in files:
        raw = path.read_bytes()
        try:
            text = store_text(path)
        except Exception:  # noqa: BLE001 - a file of another kind: its bytes are looked at
            text = ""
        for ja in JAPANESE:
            assert ja.encode("utf-8") not in raw and ja not in text, path.name

    before = {p: p.stat().st_mtime_ns for p in settings.state_dir.rglob("*") if p.is_file()}
    w._page_lines.clear()
    for page in (sample_page, sample_page2):  # the check alone, on pages the cache holds: it writes nothing at all
        result = desk.pipeline.process(page)
        after_page = {p: p.stat().st_mtime_ns for p in settings.state_dir.rglob("*") if p.is_file()}
        jobs.keep_page_names(w, result, "Book", "fake", "English")
        assert {p: p.stat().st_mtime_ns for p in settings.state_dir.rglob("*") if p.is_file()} == after_page
    assert set(before) == {p for p in settings.state_dir.rglob("*") if p.is_file()}


def test_the_memory_is_bounded_and_for_one_book_at_a_time(desk, sample_page, sample_page2):
    assert PAGE_LINES_MAX >= 2000  # (a long volume's lines)
    w = desk.window
    w._page_lines = PageLines(limit=4)
    read(w, sample_page)
    assert len(w._page_lines) == 4
    read(w, sample_page2)
    assert len(w._page_lines) == 4 and w.offers() == []  # the oldest went: too few lines to tell
    assert {line.source for line in w._page_lines.lines()} <= {ja for ja, _en in PAGE2}

    memo = PageLines(limit=3)
    lines = [RunLine(f"行{i}", f"Line {i}.", (f"f{i}", (0.1, 0.1, 0.2, 0.2))) for i in range(5)]
    assert memo.add("Book", lines[:3]) and not memo.add("Book", lines[:3])  # the same lines again: nothing new
    assert memo.add("Book", [lines[0]._replace(text="Line zero.")])  # a line with another text is news
    assert memo.add("Book", lines[3:4]) and [line.source for line in memo.lines()] == ["行2", "行0", "行3"]
    assert memo.add("Other book", lines[4:]) and [line.source for line in memo.lines()] == ["行4"]
    memo.retext(lambda where: None)
    assert len(memo) == 0  # (a line no longer stored goes)


def test_a_run_s_names_are_not_offered_again_and_a_change_made_stays(desk, sample_page, sample_page2):
    w = desk.window
    pairs = PAGE1 + PAGE2
    run_lines = [RunLine(ja, en, (f"run{i // 6}", (0.1, 0.05 * (i % 6), 0.3, 0.05 * (i % 6) + 0.04)))
                 for i, (ja, en) in enumerate(pairs)]
    progress = SimpleNamespace(names=find_variants(run_lines), name_lines=[line._replace(source="") for line in run_lines])
    assert name_check.keep_found(w, progress, "Book", "English") == 1
    run_found = w._names_found
    (run_v,) = run_found.variants
    run_found.done["竜司"] = ("Ryuji", object(), "", [(s, list(at)) for s, at in run_v.renderings], False)
    read(w, sample_page)
    read(w, sample_page2)
    assert len(w.offers()) == 1 and w._band is None  # the run offered 竜司 already
    assert w._names_found is run_found

    # a name new to the book joins what the run found: the run's, and what was made of it, stay
    chihiro = [RunLine(ja.replace("竜司", "千尋"), en.replace("Ryuji", "Chihiro").replace("Ryūji", "Chihíro"),
                       (f"pg{i}", (0.1, 0.1, 0.2, 0.2))) for i, (ja, en) in enumerate(pairs)]
    other = find_variants(chihiro)
    assert [v.source for v in other] == ["千尋"]
    data = {"book": "Book", "language": "English", "variants": other,
            "lines": [line._replace(source="") for line in chihiro]}
    assert name_check.keep_page_found(w, data) == 2
    joined = w._names_found
    assert [v.source for v in joined.variants] == ["竜司", "千尋"] and set(joined.done) == {"竜司"}
    for v in joined.variants:  # each name's lines are its own: the right texts at the right places
        for spelling, at in v.renderings:
            assert all(spelling in joined.lines[i].text for i in at)
    assert joined.done["竜司"][3] == [(s, list(at)) for s, at in joined.variants[0].renderings]
    assert len(joined.lines) == 10  # only the names' own lines are kept


def test_the_band_of_a_run_that_ended_gets_the_line_and_a_run_s_band_is_left_alone(desk):
    w = desk.window
    w._band = {"kind": "summary", "summary": "The run is done.", "names": 2}
    w._offer_page_names(3)
    lines, buttons = w._band_view()
    assert lines[-1] == "3 name(s) rendered in more than one way in the pages read so far."
    assert [label for label, _do in buttons].count("Review names...") == 1
    w._band = {"kind": "scan", "scan": None}
    w._offer_page_names(3)
    assert "page_names" not in w._band
    w._band, w.batch = None, object()
    w._offer_page_names(3)
    assert w._band is None
    assert "keep_page_names(self, result" in inspect.getsource(app_mod.App._job_translate)
    assert '"{n} name(s) rendered in more than one way in the pages read so far."' in inspect.getsource(status)
