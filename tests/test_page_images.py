"""Every turned page in memory (packed without loss, within a cap), the erase done ahead and used on show, the batch's
workers at a lower priority, GPU work paused while pages are turned, and the window's ``page_stage`` events. Reading is
on the viewer: the run's images give the page being translated its picture while the run works, and after the run serve
the render of a page the viewer shows alone - no picture of a page is handed out by its number."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image

from taslation import batch as batch_mod
from taslation.batch import BatchReader, thumb_of, torch_threads
from taslation.cache import CacheStore
from taslation.pageimages import ErasedRegion, PageImages, memory_cap, pack, unpack
from taslation.pipeline import Pipeline
from taslation.render import artwork
from taslation.translate import DictTranslator

from test_batch_follows_reader import Slow, desk, in_hand, page, pagewise, until  # noqa: F401 - (desk: a fixture)


def test_a_packed_page_comes_back_bit_for_bit():
    rng = np.random.default_rng(3)
    rgb = rng.integers(0, 256, (123, 77, 3), dtype=np.uint8)
    for image in (Image.fromarray(rgb), Image.fromarray(rgb[..., 0]), Image.fromarray(np.dstack([rgb, rgb[..., :1]])),
                  Image.fromarray(rgb).convert("P"), Image.fromarray(rgb).convert("CMYK")):
        packed = pack(image)
        back = unpack(packed)
        assert back.mode == image.mode and back.size == image.size
        assert back.tobytes() == image.tobytes(), image.mode
        assert packed.nbytes == len(packed.data) and isinstance(packed.data, bytes)


def test_a_page_is_packed_in_memory_and_never_written(monkeypatch, tmp_path):
    def no_file(*_a, **_k):
        raise AssertionError("a page image went to a file")

    save = Image.Image.save
    monkeypatch.setattr(Image.Image, "save", lambda self, fp, *a, **k: no_file() if isinstance(fp, (str, Path))
                        else save(self, fp, *a, **k))
    import cv2

    monkeypatch.setattr(cv2, "imwrite", no_file)
    unpack(pack(page(1)))
    unpack(pack(page(1).convert("P")))


def test_the_cap_is_at_most_a_quarter_of_the_memory(monkeypatch):
    from taslation import pageimages

    monkeypatch.setattr(pageimages, "physical_memory", lambda: 8 * 1024 ** 3)
    assert memory_cap(2048) == 2048 * 1024 ** 2
    monkeypatch.setattr(pageimages, "physical_memory", lambda: 4 * 1024 ** 3)
    assert memory_cap(2048) == 1024 ** 3
    monkeypatch.setattr(pageimages, "physical_memory", lambda: 0)
    assert memory_cap(100) == 100 * 1024 ** 2
    monkeypatch.undo()
    assert pageimages.physical_memory() > 1024 ** 3  # (this machine's, read through Windows)


def _packed(n: int):
    return pack(page(n))


def test_frames_to_read_are_never_let_go_and_fill_the_cap_last():
    one = _packed(1).nbytes
    images = PageImages(cap=int(one * 3.5))
    assert all(images.put_frame(k, _packed(k)) for k in (1, 2, 3))
    assert not images.put_frame(4, _packed(4))  # three frames still to read: no room, nothing let go
    assert len(images) == 3 and images.unread() == 3 and not images.room_for(images.largest)
    images.read(1, erase=False)  # read: may go
    assert images.room_for(images.largest) and images.put_frame(4, _packed(4))
    assert images.frame(1) is None and images.frame(4).tobytes() == page(4).tobytes()


def test_room_is_made_from_spare_frames_then_erased_pages_then_frames_waiting_for_their_erase():
    one = max(_packed(k).nbytes for k in range(1, 8))
    images = PageImages(cap=int(one * 3.2))
    for k in (1, 2, 3):
        images.put_frame(k, _packed(k))
    images.read(1, erase=True)  # waits for its erase
    images.read(2, erase=False)  # spare
    images.read(3, erase=True)
    record = ErasedRegion(b"k3", (255, 255, 255), (0, 0, 0, 0), b"")
    assert images.put_erased(3, _packed(30), [record], (800, 600))
    assert images.put_frame(4, _packed(4))  # the spare frame goes first
    assert images.frame(2) is None and images.erased(3) is not None and images.frame(1) is not None
    images.read(4, erase=False)
    images.put_frame(5, _packed(5))  # (frame 4 is spare now: it goes)
    images.read(5, erase=False)
    assert images.put_frame(6, _packed(6))
    assert images.put_frame(7, _packed(7))  # then the erased page, then the frame waiting for its erase
    assert images.erased(3) is None and images.find([b"k3"], (800, 600, 3)) == {}
    assert images.unread() == 2


def test_an_erased_page_takes_its_frames_place_and_is_the_best_image():
    images = PageImages(cap=10 ** 9)
    images.put_frame(1, pack(page(1)))
    images.read(1, erase=True)
    assert images.best(1).tobytes() == page(1).tobytes()
    erased = page(2)
    record = ErasedRegion(b"key", (250, 250, 250), (0, 0, 2, 2), np.packbits(np.ones(4, bool)).tobytes())
    assert images.put_erased(1, pack(erased), [record], (800, 600))
    assert images.frame(1) is None and images.best(1).tobytes() == erased.tobytes()
    found = images.find([b"nothing", b"key"], (800, 600, 3))
    assert list(found) == [1] and found[1][0] is record and found[1][1]().shape == (800, 600, 3)
    assert images.find([b"key"], (801, 600, 3)) == {}  # another frame size: not that page
    images.clear()
    assert images.best(1) is None and images.used == 0


def test_the_thumbnail_is_at_most_96_px_high():
    thumb = thumb_of(page(1))
    assert thumb.height == 96 and thumb.width == 72 and thumb.mode == "RGB"
    assert thumb_of(Image.new("L", (40, 30))).size == (40, 30)


@pytest.mark.parametrize("cores, threads", [(1, 1), (2, 1), (4, 3), (6, 4), (8, 6), (16, 14)])
def test_torch_leaves_a_core_or_two_free(cores, threads):
    assert torch_threads(cores) == threads


# ------------------------------------------------------------------ the reading pass
def test_a_reader_turning_quickly_never_waits_while_the_memory_holds_the_pages(desk, settings):
    gate = threading.Event()  # the OCR holds on: every page waits
    reader, pipeline = pagewise(desk, settings, pipeline=Slow(desk.pages, gate=gate))
    said = []
    reader.on_progress = lambda p, _r: said.append(getattr(p.message, "code", ""))
    thread, _results = in_hand(reader.run)
    for i in range(12):
        assert until(lambda: reader._on_show is desk.pages[i])
        if i < 11:
            desk.index = i + 1
    assert until(lambda: reader._backlog.qsize() >= 11)
    assert "batch.backlog_full" not in said and reader.progress.waiting is None
    gate.set()
    reader.finish()
    thread.join(20)
    assert pipeline.read == list(range(12))


def test_frames_to_read_that_fill_the_cap_ask_the_reader_to_wait(desk, settings):
    gate = threading.Event()
    reader, pipeline = pagewise(desk, settings, pipeline=Slow(desk.pages, gate=gate))
    reader.images.cap = int(pack(desk.pages[0]).nbytes * 3.5)
    thread, _results = in_hand(reader.run)
    for i in range(3):  # the first is being read, two wait: three frames to read in the memory
        assert until(lambda: reader._on_show is desk.pages[i])
        desk.index = i + 1
    assert until(lambda: reader.progress.waiting is not None)
    assert reader.progress.waiting.code == "batch.backlog_full" and reader._on_show is desk.pages[2]
    gate.set()
    assert until(lambda: 3 in pipeline.read)
    reader.finish()
    thread.join(20)
    assert pipeline.read == [0, 1, 2, 3] and reader.progress.waiting is None


def whole_book(desk, settings, sample_page, sample_page2, **kwargs):
    desk.pages[:] = [sample_page, sample_page2, sample_page.transpose(Image.FLIP_LEFT_RIGHT)]
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache)
    shown: list[tuple[str, dict]] = []
    reader = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[],
                         show=lambda kind, data: shown.append((kind, data)), **kwargs)
    return reader, pipeline, shown


def test_the_pages_read_are_erased_ahead_and_the_render_uses_them(desk, settings, sample_page, sample_page2):
    reader, pipeline, _shown = whole_book(desk, settings, sample_page, sample_page2)
    progress = read_book(reader, desk)
    assert progress.summary.code == "batch.finished" and reader.erased_pages == 3
    assert pipeline.erased_ahead is reader.images
    plain = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=pipeline.cache)
    for i, frame in enumerate(desk.pages):
        before = reader.images.reused
        shown = pipeline.process(frame)  # the live view: the page from the cache
        assert reader.images.reused > before, i  # erased ahead, not erased again
        assert np.array_equal(np.asarray(shown.image), np.asarray(plain.process(frame).image)), i
        assert reader.images.best(i + 1).tobytes() != frame.tobytes()  # the erased page is the best image
    assert reader.images.erased_live == 0


def test_the_translation_views_picture_is_the_translated_page_never_the_bare_erased_one(desk, settings, sample_page,
                                                                                         sample_page2):
    """What the page being translated ends on once it is stored (`Pipeline.page_picture`): the page as the live view
    letters it from the cache, on the frame made again from the erased page."""
    reader, pipeline, _shown = whole_book(desk, settings, sample_page, sample_page2)
    read_book(reader, desk)
    plain = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=pipeline.cache)
    for i, frame in enumerate(desk.pages):
        seq = i + 1
        assert reader.images.frame(seq) is None and reader.images.best(seq) is not None  # (only the erased page)
        assert reader.images.original(seq).tobytes() == frame.convert("RGB").tobytes()  # the frame, bit for bit
        picture = pipeline.page_picture(reader.images, seq)
        erased = reader.images.best(seq)
        assert picture.tobytes() != erased.tobytes() and picture.tobytes() != frame.convert("RGB").tobytes()
        live = np.asarray(plain.process(frame).image)  # the page as the live view letters it from the cache
        assert np.array_equal(np.asarray(picture), live), seq
    del reader

    def no_erase(*_args, **_kwargs):
        raise AssertionError("erased again")

    pipeline._erase = no_erase  # every erase comes from the erased page: nothing is erased again (LaMa least of all)
    after = pipeline.process(desk.pages[1])  # the batch gone: the viewer shows page 2, rendered with the erases kept
    assert np.array_equal(np.asarray(after.image), np.asarray(plain.process(desk.pages[1]).image))


def test_a_page_not_translated_has_its_frame_as_it_was_captured(desk, settings, sample_page, sample_page2):
    reader, pipeline, _shown = whole_book(desk, settings, sample_page, sample_page2)
    read_book(reader, desk)
    pipeline.cache = None  # (no translation to letter: a run stopped before the translation, say)
    for i, frame in enumerate(desk.pages):
        assert pipeline.page_picture(reader.images, i + 1).tobytes() == frame.convert("RGB").tobytes()
    images = PageImages(10 * 1024 * 1024)
    images.put_frame(1, pack(desk.pages[0]))
    images.read(1, erase=True)
    images.put_erased(1, pack(desk.pages[1]), [], (10, 10))  # an erased page without its undo ...
    assert images.original(1) is None and images.best(1) is not None  # ... is never handed out as the frame


def test_the_undo_makes_the_frame_again_and_the_kept_regions_come_back_alike():
    from taslation.pageimages import KeptRegions, undo_of, undone
    from taslation.regions import TextRegion

    rng = np.random.default_rng(3)
    frame = rng.integers(0, 256, (60, 80, 3), np.uint8)
    erased = frame.copy()
    erased[10:30, 20:50] = 255
    erased[40:45, 5:9] = (250, 240, 230)
    undo = undo_of(frame, erased)
    assert np.array_equal(undone(erased, undo), frame) and undo.nbytes < frame.nbytes
    assert np.array_equal(undone(frame, undo_of(frame, frame)), frame)
    mask = np.zeros((20, 30), np.uint8)
    mask[2:18, 3:27] = 255
    region = TextRegion(x0=20, y0=10, x1=50, y1=30, mask=mask, text_box=(22, 12, 48, 28))
    kept = KeptRegions([region])
    again = kept.regions()
    assert len(again) == 1 and again[0] is not region and np.array_equal(again[0].mask, mask)
    assert again[0].mask.dtype == mask.dtype and again[0].bbox == region.bbox and kept.nbytes < mask.nbytes
    again[0].mask[:] = 0
    assert kept.regions()[0].mask.any()  # (each a fresh copy)


def test_a_region_whose_page_differs_erases_live(desk, settings, sample_page, sample_page2):
    reader, pipeline, _shown = whole_book(desk, settings, sample_page, sample_page2)
    read_book(reader, desk)
    plain = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=pipeline.cache)
    shown = plain.process(desk.pages[0])
    region = next(r for r in shown.regions if r.status == "translated")
    changed = np.asarray(desk.pages[0]).copy()
    changed[max(0, region.y0 - 2), region.x0:region.x1] ^= 1  # a pixel row just over the region: another frame
    frame = Image.fromarray(changed)
    out = pipeline.process(frame)
    assert reader.images.erased_live >= 1 and reader.images.reused >= 1  # the others are still the same
    assert np.array_equal(np.asarray(out.image), np.asarray(plain.process(frame).image))
    pipeline.erased_ahead = None  # (a window that let go of them: nothing is reused)
    assert np.array_equal(np.asarray(pipeline.process(desk.pages[1]).image),
                          np.asarray(plain.process(desk.pages[1]).image))


def test_page_stage_tells_each_page_in_order_with_its_thumbnail_first(desk, settings, sample_page, sample_page2):
    reader, _pipeline, shown = whole_book(desk, settings, sample_page, sample_page2)
    read_book(reader, desk)
    stages = [data for kind, data in shown if kind == "page_stage"]
    assert {d["seq"] for d in stages} == {1, 2, 3}
    for seq in (1, 2, 3):
        mine = [d for d in stages if d["seq"] == seq]
        assert [(d["stage"], d["state"]) for d in mine if d["stage"] == "read"] == [
            ("read", "waiting"), ("read", "working"), ("read", "done")]
        assert [d["state"] for d in mine if d["stage"] == "erase"] == ["waiting", "working", "done"]
        assert [d["state"] for d in mine if d["stage"] == "translate"] == ["waiting", "working", "done"]
        assert "thumb" in mine[0] and all("thumb" not in d for d in mine[1:])
        assert isinstance(mine[0]["thumb"], Image.Image) and mine[0]["thumb"].height <= 96
        assert all(isinstance(d["fingerprint"], str) and len(d["fingerprint"]) > 8 for d in mine)
        assert mine.index(next(d for d in mine if d["stage"] == "translate" and d["state"] == "working")) > \
            mine.index(next(d for d in mine if d["stage"] == "erase" and d["state"] == "done"))  # after "Finished"
    memory = [data for kind, data in shown if kind == "batch_memory"]
    assert memory and all(set(d) == {"used_mb", "cap_mb"} for d in memory) and memory[-1]["cap_mb"] > 0
    assert reader.images.original(9) is None and reader.images.original(1) is not None
    _pipeline.release_page_images()
    assert reader.images.original(1) is None and _pipeline.erased_ahead is None


def test_a_page_the_cache_holds_is_read_skipped_and_its_later_stages_as_they_go(desk, settings, sample_page,
                                                                               sample_page2):
    reader, pipeline, _shown = whole_book(desk, settings, sample_page, sample_page2)
    read_book(reader, desk)
    desk.index = 0
    again = BatchReader(pipeline, hwnd=1, settings=settings, context_mode=True, preflight=[],
                        show=lambda kind, data: shown.append((kind, data)))
    shown: list[tuple[str, dict]] = []
    read_book(again, desk)
    states = {(d["seq"], d["stage"]): d["state"] for kind, d in shown if kind == "page_stage"}
    assert states[(1, "read")] == "skipped" and states[(1, "translate")] == "skipped"
    assert states[(1, "erase")] == "done"  # the cached page is erased ahead all the same: it is shown translated
    assert reader.images.original(1) is None and len(reader.images) == 0  # the earlier run's went with the new run


@pytest.mark.skipif(sys.platform != "win32", reason="Windows thread priorities")
def test_the_workers_run_below_normal_and_the_sampler_at_normal(desk, settings, sample_page, sample_page2):
    reader, _pipeline, _shown = whole_book(desk, settings, sample_page, sample_page2)
    before = batch_mod.thread_priority()
    read_book(reader, desk)
    assert reader.priorities == {"sampler": 0, "packer": 0, "reader": -1, "eraser": -1}
    assert batch_mod.thread_priority() == before  # the run's own thread gets its priority back


def test_torch_threads_are_limited_while_reading_and_given_back(desk, settings, monkeypatch):
    torch = pytest.importorskip("torch")
    seen = []
    reader, pipeline = pagewise(desk, settings, pipeline=Slow(desk.pages))
    pipeline.process = lambda frame, **_k: (seen.append(torch.get_num_threads()),
                                             Slow.process(pipeline, frame))[1]
    monkeypatch.setattr(batch_mod, "torch_threads", lambda cores=None: 2)
    before = torch.get_num_threads()
    desk.pages[:] = desk.pages[:2]
    read_book(reader, desk)
    assert seen and set(seen) == {min(2, before)} and torch.get_num_threads() == before


# ------------------------------------------------------------------ the GPU waits while pages are turned
def test_gpu_work_waits_until_the_pages_have_stopped_turning(desk, settings):
    reader, _pipeline = pagewise(desk, settings)
    reader.gpu_quiet_s = 0.3
    reader._last_change = time.monotonic()
    t = time.monotonic()
    reader._gpu_wait()
    assert time.monotonic() - t >= 0.25 and reader.gpu_waits == 1
    reader._last_change = time.monotonic() - 5
    t = time.monotonic()
    reader._gpu_wait()
    assert time.monotonic() - t < 0.05 and reader.gpu_waits == 1
    reader._last_change = time.monotonic() + 60  # (turning on and on) ...
    threading.Timer(0.1, reader.stop).start()
    t = time.monotonic()
    reader._gpu_wait()  # ... Stop ends the wait
    assert time.monotonic() - t < 1.0


def test_the_pipeline_holds_the_gate_while_the_pages_are_read(desk, settings, sample_page, sample_page2):
    reader, pipeline, _shown = whole_book(desk, settings, sample_page, sample_page2)
    gates = []
    scan = pipeline.scan
    pipeline.scan = lambda *a, **k: (gates.append(pipeline.gpu_gate), scan(*a, **k))[1]
    read_book(reader, desk)
    assert gates and all(g == reader._gpu_wait for g in gates) and pipeline.gpu_gate is None


def test_lama_asks_the_gate_on_the_gpu_only(tmp_path, monkeypatch):
    eraser = artwork.ArtEraser(tmp_path)
    asked = []
    eraser.before_gpu = lambda: asked.append(1)
    monkeypatch.setattr(eraser, "_try", lambda device, part, hole: (part, ""))
    monkeypatch.setattr(artwork.ArtEraser, "_device", staticmethod(lambda: "cuda"))
    part, hole = np.zeros((4, 4, 3), np.uint8), np.zeros((4, 4), bool)
    eraser._fill(part, hole)
    assert asked == [1]
    monkeypatch.setattr(artwork.ArtEraser, "_device", staticmethod(lambda: "cpu"))
    eraser._fill(part, hole)
    assert asked == [1]


def test_the_layout_model_never_waits_for_the_gate(settings, sample_page):
    # (only LaMa waits while the pages are turned: waiting, the layout model held every page's reading back)
    pipeline = Pipeline(settings, ocr=FakeOcr())
    asked = []
    pipeline.gpu_gate = lambda: asked.append(1)
    ran = []

    class Layout:
        def uses_gpu(self):
            return True

        def boxes(self, rgb, units):
            ran.append(1)
            return None

    pipeline.settings.detect_model = "on"
    pipeline.layout = Layout()
    pipeline._detect(np.asarray(sample_page))
    assert ran == [1] and asked == []


def test_the_erase_ahead_waits_while_frames_wait_to_be_read(desk, settings):
    reader, _pipeline = pagewise(desk, settings)
    reader._backlog.put(object())
    done = []
    thread = threading.Thread(target=lambda: (reader._reading_first(), done.append(time.monotonic())))
    t = time.monotonic()
    thread.start()
    time.sleep(0.3)
    assert not done  # a frame waits to be read: the erase waits
    reader._backlog.get_nowait()
    thread.join(2)
    assert done and done[0] - t >= 0.25
    reader._backlog.put(object())
    threading.Timer(0.1, reader._sampler_off.set).start()  # the reading is over: the wait ends
    t = time.monotonic()
    reader._reading_first()
    assert time.monotonic() - t < 1.0
    reader._sampler_off.clear()
    threading.Timer(0.1, reader.stop).start()  # Stop ends it too
    t = time.monotonic()
    reader._reading_first()
    assert time.monotonic() - t < 1.0


def test_a_stopped_run_closes_every_stage_that_will_never_run(desk, settings, sample_page, sample_page2):
    reader, pipeline, shown = whole_book(desk, settings, sample_page, sample_page2)
    thread, _results = in_hand(reader.run)
    assert until(lambda: reader.progress.pages >= 1)
    reader.stop()
    thread.join(20)
    last = {}
    for kind, d in shown:
        if kind == "page_stage":
            last[(d["seq"], d["stage"])] = d["state"]
    seqs = {seq for seq, _stage in last}
    assert seqs and all((seq, stage) in last for seq in seqs for stage in ("read", "erase", "translate"))
    assert all(state in ("done", "failed", "skipped") for state in last.values())
    assert last[(1, "translate")] == "skipped"


def test_after_the_run_its_pages_serve_only_the_render_of_a_page_the_viewer_shows(desk, settings, sample_page,
                                                                                 sample_page2):
    """Reading is on the viewer: once the batch has gone, its images stay with the pipeline for the erase done ahead
    of a page the viewer shows (``erased_ahead``), and neither the pipeline nor a batch gives the picture of a page by
    its number; closing the window lets them go."""
    reader, pipeline, _shown = whole_book(desk, settings, sample_page, sample_page2)
    read_book(reader, desk)
    store = reader.images
    del reader
    assert pipeline.erased_ahead is store and len(store) == 3
    assert not hasattr(pipeline, "page_image") and not hasattr(BatchReader, "page_image")
    before = store.reused
    pipeline.process(desk.pages[2])  # the viewer shows the third page: its erases come from the run's erased page
    assert store.reused > before and store.erased_live == 0
    pipeline.release_page_images()
    assert pipeline.erased_ahead is None and len(store) == 0


def test_a_page_by_page_run_lets_go_of_each_frame_once_it_is_translated(desk, settings):
    """Page by page nothing is erased ahead and nothing of the run is shown from memory: a frame goes as soon as its
    page is translated, and the run ends holding none."""
    reader, pipeline = pagewise(desk, settings)
    desk.pages[:] = desk.pages[:3]
    dropped: list[int] = []
    drop = reader.images.drop_frame
    reader.images.drop_frame = lambda key: (dropped.append(key), drop(key))[1]
    process = pipeline.process
    held: list[int] = []
    pipeline.process = lambda frame, **k: (held.append(len(reader.images)), process(frame, **k))[1]
    read_book(reader, desk)
    assert pipeline.read == [0, 1, 2] and len(dropped) == 3 and len(set(dropped)) == 3
    assert len(reader.images) == 0 and reader.images.used == 0
    assert held and max(held) <= 2  # (the page being read and at most the next one waiting: none kept behind)
