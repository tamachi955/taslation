"""The whole-book translation beside the reading of the backlog (`BatchReader._translate_ahead`): once the reader has
finished and every frame still to read is on the backlog, each run of lines is asked as soon as it and the lines after
it are read for good, and nothing of it is stored, counted or told until the reading is over (`_end_deferring`). The
requests and what the run stores are those of the translation after the reading; Stop keeps what was translated, and
a later run translates the rest; the translator's model loads only while no page is read or erased. The run is the
real `BatchReader` and `Pipeline` on stand-in pages and a stand-in model; no real window, nothing under the real state
folder."""
from __future__ import annotations

import random
import threading
import time
from types import SimpleNamespace

import pytest
from helpers import FakeOcr, read_book
from PIL import Image

from taslation.batch import BatchReader, chunk_units, next_chunk
from taslation.cache import CacheStore
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator

from test_batch_follows_reader import desk  # noqa: F401 - (a fixture)

# a line of its own for every bubble of the eight pages (the stand-in OCR answers in call order)
TEXTS = [f"{head}{tail}" for tail in "かきくけこさしすせそたちつてとなにぬねのはひふへほ" for head in ("今日は", "明日も")]
MAPPING = {ja: f"Line {n} as translated." for n, ja in enumerate(TEXTS)}


def pages(sample_page, sample_page2) -> list[Image.Image]:
    """Eight pages of six bubbles each, far apart (130 bits and more)."""
    out = [sample_page, sample_page2]
    for turn in (Image.FLIP_LEFT_RIGHT, Image.FLIP_TOP_BOTTOM, Image.ROTATE_180):
        out += [sample_page.transpose(turn), sample_page2.transpose(turn)]
    return out


class Model(DictTranslator):
    """The stand-in model: each request recorded with what the run had read and stored when it came; its first
    request loads it (`before_load` first, as `OllamaTranslator.ensure_loaded` does, then *load_s*); *stop_at*: the
    request (1, 2, ...) at which the reader presses Stop, and that request ends as a cancelled one does."""

    def __init__(self, load_s: float = 0.0, stop_at: int | None = None):
        super().__init__(MAPPING)
        self.before_load = None
        self.load_s, self.stop_at = load_s, stop_at
        self.reader: BatchReader | None = None
        self.cache = None
        self.unread_at: list[int] = []
        self.stored_at: list[int] = []
        self.loaded: tuple[float, float] | None = None
        self.asked = 0

    def translate_page(self, texts, *args, **kwargs):
        self.asked += 1
        if self.loaded is None:
            began = time.monotonic()
            if self.before_load is not None:
                self.before_load()
            time.sleep(self.load_s)
            self.loaded = (began, time.monotonic())
        reader = self.reader
        with reader._fed:
            self.unread_at.append(len(reader._unread))
        self.stored_at.append(len(self.cache))
        if self.stop_at == self.asked:
            reader.stop()
        return super().translate_page(texts, *args, **kwargs)


def run_book(desk, settings, book_pages, book, ahead=True, model=None, read_s=0.25, first=0, readings=None, ocr=None):
    """A whole-book run of *book_pages* read from page *first* on, every page taking *read_s* to read; *ahead*
    False: the translation waits for the end of the reading (as before the translation beside the backlog)."""
    desk.pages[:] = book_pages
    desk.index = first
    cache = CacheStore(settings.cache_dir).open(book, "fake")
    model = model or Model()
    pipeline = Pipeline(settings, ocr=ocr or FakeOcr(TEXTS), translator=model, cache=cache)
    shown: list[tuple[str, dict]] = []
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[], book=book,
                         show=lambda kind, data: shown.append((kind, data)), readings=readings, keep_readings=True)
    model.reader, model.cache = reader, cache
    scans: list[tuple[float, float]] = []
    scan = pipeline.scan

    def slow_scan(*args, **kwargs):
        began = time.monotonic()
        time.sleep(read_s)
        try:
            return scan(*args, **kwargs)
        finally:
            scans.append((began, time.monotonic()))

    pipeline.scan = slow_scan
    if not ahead:
        reader._translate_ahead = lambda start: None
    said: list = []
    reader.on_progress = lambda p, _result: said.append((p.message.code, p.phase, p.bubbles))
    progress = read_book(reader, desk)
    return SimpleNamespace(reader=reader, progress=progress, model=model, cache=cache, shown=shown, said=said,
                           scans=scans, pipeline=pipeline)


def stored(cache) -> dict[str, tuple[bool, list[str]]]:
    return {page.fingerprint: (page.incomplete, sorted(b.text for b in page.bubbles)) for page in cache.pages}


def requests(model) -> list[tuple]:
    return [(tuple(texts), tuple(map(tuple, kw["context"])), tuple(kw["upcoming"]), str(kw["notes"]),
             repr(kw["meta"])) for texts, kw in zip(model.calls, model.kwargs)]


def last_stages(shown) -> dict[tuple[int, str], str]:
    return {(d["seq"], d["stage"]): d["state"] for kind, d in shown if kind == "page_stage"}


@pytest.fixture
def book(desk, settings, sample_page, sample_page2):
    settings.chunk_bubbles = 6  # a request a page ...
    settings.lookahead_bubbles = 6  # ... with the next page's lines as what comes next
    return pages(sample_page, sample_page2)


def test_the_translation_begins_while_frames_are_still_read_and_asks_and_stores_as_after_the_reading(
        desk, settings, book):
    ahead = run_book(desk, settings, book, "Ahead 1", model=Model(load_s=0.2))
    after = run_book(desk, settings, book, "After 1", ahead=False, model=Model(load_s=0.2))
    for run in (ahead, after):
        assert run.progress.summary.code == "batch.finished" and run.progress.pages == 8
    # requests went out while frames were still to read, and nothing was stored before the reading was over
    beside = [k for k, unread in enumerate(ahead.model.unread_at) if unread]
    assert beside and all(ahead.model.stored_at[k] == 0 for k in beside)
    assert not any(after.model.unread_at)
    # the very requests, in the very order, and what is stored, counted and noted is the same
    assert requests(ahead.model) == requests(after.model) and len(ahead.model.calls) == 8
    assert stored(ahead.cache) == stored(after.cache) and len(stored(ahead.cache)) == 8
    assert [p.seq for p in ahead.cache.pages] == [p.seq for p in after.cache.pages]
    assert len(ahead.cache.lines) == len(after.cache.lines)
    for field in ("translated", "checked", "bubbles", "found", "errors"):
        assert getattr(ahead.progress, field) == getattr(after.progress, field), field
    assert ahead.progress.notes == after.progress.notes
    assert last_stages(ahead.shown) == last_stages(after.shown)
    assert all(state == "done" for (_seq, stage), state in last_stages(ahead.shown).items() if stage == "translate")
    # the band tells the reading until it is over, then the translation: no run said before the pages read
    codes = [code for code, _phase, _bubbles in ahead.said]
    read_end = codes.index("batch.pages_read")
    assert all(code not in ("batch.translating_chunk", "batch.translated_chunk") for code in codes[:read_end])
    assert all(phase in ("", "read") for _code, phase, _b in ahead.said[:read_end])  # ("": the start)
    told = [code for code in codes if code in ("batch.translating_chunk", "batch.translated_chunk")]
    assert told and told[-1] == "batch.translated_chunk"
    # the model's load came while no page was being read (the reading waited for it, and it for the reading)
    began, ended = ahead.model.loaded
    assert any(b < began for b, _e in ahead.scans) and any(b > ended for b, _e in ahead.scans)
    assert all(e <= began or b >= ended for b, e in ahead.scans)


def test_stop_beside_the_backlog_keeps_what_was_translated_and_a_later_run_translates_the_rest(desk, settings, book):
    first = run_book(desk, settings, book, "Stopped 1", model=Model(stop_at=2), read_s=0.3)
    assert first.model.unread_at[1] > 0  # (Stop came while frames were still to read)
    assert first.progress.summary.code == "batch.stopped_translating"
    assert first.progress.reason.code == "batch.user_stop"
    kept = stored(first.cache)
    assert len(kept) == 1 and first.progress.checked == 6 and first.progress.translated == 6
    assert first.reader.left is not None and not first.reader.left.complete
    left = first.reader.left.units
    assert left and all(u.fingerprint not in kept for u in left)  # read, not stored: the next run has them
    # the next run reads on from the page on show and translates what is left
    pages_read = first.progress.pages
    rest = run_book(desk, settings, book, "Stopped 1", readings=first.reader.left, first=pages_read,
                    ocr=first.pipeline.ocr)  # (the stand-in OCR goes on with the lines of the pages not read yet)
    assert rest.progress.summary.code == "batch.finished"
    whole = run_book(desk, settings, book, "Whole 1", ahead=False)
    assert stored(rest.cache) == stored(whole.cache)
    asked = [t for c in first.model.calls + rest.model.calls for t in c]
    assert sorted(asked) == sorted(TEXTS[:48])  # every line asked for once


def test_next_chunk_takes_chunk_units_groups_with_the_lines_after_them_as_the_book_grows():
    rng = random.Random(7)
    for _trial in range(200):
        sizes = [rng.randint(1, 9) for _ in range(rng.randint(1, 25))]
        units = [SimpleNamespace(japanese=lambda n=n, k=k: [SimpleNamespace(source_text=f"{k}.{j}") for j in range(n)])
                 for k, n in enumerate(sizes)]
        most, lookahead = rng.randint(1, 20), rng.choice([0, 1, 5, 12, 60])
        whole = chunk_units(units, most)
        known, done, got = rng.randint(0, 3), 0, []
        while True:  # the units read one or more at a time, a group taken whenever it is known for good
            complete = known >= len(units)
            found = next_chunk(units[:known], done, most, lookahead, complete)
            if found is None:
                if complete:
                    break
                known += rng.randint(1, 3)
                continue
            chunk, upcoming = found
            after = [r.source_text for u in units[done + len(chunk):] for r in u.japanese()]
            assert upcoming == (after[:lookahead] if lookahead else [])
            got.append(chunk)
            done += len(chunk)
        assert got == whole


def test_a_unit_stored_while_frames_are_read_counts_complete_as_the_store_would(settings, sample_page):
    cache = CacheStore(settings.cache_dir).open("Complete 1", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(TEXTS), translator=DictTranslator(MAPPING), cache=cache)
    unit = next(u for u in pipeline.scan(sample_page, skip_cached=False).units if u.japanese())
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[])
    lines = [r.source_text for r in unit.japanese()]
    rng = random.Random(3)
    for _trial in range(40):
        texts = {}
        for i, ja in enumerate(lines):
            texts[i] = rng.choice([MAPPING[ja], "", "  ", ja, f" {MAPPING[ja]} ", None])
        if rng.random() < 0.3:
            texts.pop(rng.randrange(len(lines)), None)
        texts = {i: t for i, t in texts.items() if t is not None}
        assert reader._would_complete(unit, texts) == pipeline.commit_unit(unit, texts)
    pipeline.cache = None
    assert reader._would_complete(unit, {i: MAPPING[ja] for i, ja in enumerate(lines)}) is False


def test_the_order_so_far_stops_before_a_page_still_to_read_once_a_page_was_retaken(settings):
    reader = BatchReader(SimpleNamespace(ocr=None, translator=None), hwnd=1, settings=settings, context_mode=True,
                         preflight=[])
    units = [SimpleNamespace(name=n) for n in "abcdef"]
    for u, seq in zip(units, (1, 2, 4, 5, 3, 6)):  # "e" is a page that went by, taken when the reader went back
        reader._units.append(u)
        reader._seq_of[id(u)] = seq
    assert [u.name for u in reader._book_so_far()[0]] == list("abcdef")  # (no page retaken: the order read)
    reader._retaken = True
    reader._unread = {10: 3}  # ("e" still to read)
    reader._units.remove(units[4])
    assert [u.name for u in reader._book_so_far()[0]] == ["a", "b"]  # what comes after it waits
    reader._units.append(units[4])
    reader._unread = {}
    assert [u.name for u in reader._book_so_far()[0]] == list("abecdf") and not reader._book_so_far()[1]


def test_a_load_waits_for_the_runs_gpu_work_and_no_gpu_work_starts_while_it_loads(settings):
    model = Model()
    pipeline = SimpleNamespace(ocr=None, translator=model, gpu_gate=None)
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[])
    reader.gpu_quiet_s = 0.0  # (no page turned: the gate waits only for the load)
    released: list[float] = []
    model.before_load = lambda: released.append(time.monotonic())
    held = reader._hold_loads()
    log: list[tuple[str, float]] = []
    in_work = threading.Event()

    def reading():  # a page being read (the layout model)
        with reader._gpu_work():
            in_work.set()
            time.sleep(0.3)
            log.append(("read over", time.monotonic()))

    def loading():
        model.before_load()
        log.append(("loaded", time.monotonic()))
        time.sleep(0.3)
        reader._model_loaded()

    worker = threading.Thread(target=reading)
    worker.start()
    in_work.wait(5)
    reader._translating = threading.Thread(target=loading)
    reader._translating.start()
    time.sleep(0.05)
    erased: list[float] = []

    def erasing():  # the erase ahead: LaMa asks the gate before each region
        with reader._gpu_work():
            reader._gpu_wait()
            erased.append(time.monotonic())

    worker.join(5)
    eraser = threading.Thread(target=erasing)
    eraser.start()
    reader._translating.join(5)
    eraser.join(5)
    times = dict(log)
    assert released and released[0] >= times["read over"]  # the GPU models went once the page was read ...
    assert erased and erased[0] >= times["loaded"] + 0.25  # ... and no erase began until the model had loaded
    # LaMa waiting at its gate holds no load back: the load goes on while an erase waits there
    entered, go, through = threading.Event(), threading.Event(), threading.Event()

    def at_the_gate():
        with reader._gpu_work():
            entered.set()
            go.wait(5)
            reader._gpu_wait()
            through.set()

    gate_wait = threading.Thread(target=at_the_gate)
    gate_wait.start()
    entered.wait(5)
    with reader._gpu_cond:
        assert reader._gpu_busy  # (an erase under way)
        reader._loading = True
    go.set()
    time.sleep(0.1)
    with reader._gpu_cond:
        assert not reader._gpu_busy and not through.is_set()  # (the erase at its gate counts as stopped, and waits)
    reader._model_loaded()
    gate_wait.join(5)
    assert through.is_set() and not reader._gpu_busy
    reader._let_loads(held)
    assert model.before_load is not held[2] and not reader._loading
