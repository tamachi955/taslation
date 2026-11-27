"""The OCR readers' CUDA graphs (`taslation.ocr.graphs`): when they are captured, what reads by the plain pass and is
said once in the log, and - on a CUDA GPU - that a replay gives the plain pass's bits."""

from __future__ import annotations

import logging
import threading

import pytest
from conftest import requires_ocr

from taslation.ocr import graphs, place
from taslation.ocr.place import Plan


def _has_cuda() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 - no torch, no CUDA
        return False


requires_cuda = pytest.mark.skipif(not _has_cuda(), reason="no CUDA GPU")


@pytest.fixture
def given_back(monkeypatch):
    calls = []
    monkeypatch.setattr(place, "give_back", lambda: calls.append(1))
    return calls


@pytest.fixture
def said(caplog):
    caplog.set_level(logging.INFO, logger=graphs.LOG.name)
    return lambda: [r.getMessage() for r in caplog.records if r.name == graphs.LOG.name]


class FakeTensor:
    """An input of a shape and a type that remembers what was copied into it."""

    def __init__(self, shape, dtype="float32", value=None):
        self.shape, self.dtype, self.value = tuple(shape), dtype, value

    def copy_(self, other):
        self.value = other.value


class FakeGraph:
    def __init__(self, fails=False):
        self.replays, self.fails = 0, fails

    def replay(self):
        if self.fails:
            raise RuntimeError("CUDA error: operation failed due to a previous error during capture")
        self.replays += 1


def _plain(*inputs):
    return ("plain", *(x.value for x in inputs))


def _with_graph(key=("dense", 32, 64), fails=False) -> tuple[graphs.Graphs, FakeGraph, FakeTensor]:
    held = graphs.Graphs("charspot", "pool")
    graph, mine = FakeGraph(fails), FakeTensor((1, 3, 32, 64))
    held._graphs[key] = (graph, (mine,), ("replayed",), _plain)
    return held, graph, mine


# ------------------------------------------------------------------ when they are captured
def test_off_a_cuda_device_switched_off_or_without_the_plan_s_room_nothing_is_captured(monkeypatch):
    asked = []
    capture = asked.append
    assert graphs.made("charspot", "cpu", capture) is None and not asked
    monkeypatch.setattr(graphs, "ENABLED", False)
    assert not graphs.wanted("cuda") and graphs.made("charspot", "cuda", capture) is None and not asked
    monkeypatch.setattr(graphs, "ENABLED", True)
    assert graphs.wanted("cuda") and graphs.wanted("cuda:0") and not graphs.wanted("cpu")  # (no plan: a tool's own)
    place.settle(Plan((place.READERS,), graphs=False))  # (the start was short with them)
    assert not place.graphs_on() and not graphs.wanted("cuda")
    assert graphs.made("charspot", "cuda", capture) is None and not asked
    place.settle(Plan((place.READERS,)))
    assert place.graphs_on() and graphs.wanted("cuda")


def test_a_capture_that_fails_leaves_the_reader_to_the_plain_pass_said_once_in_the_log(monkeypatch, given_back, said):
    monkeypatch.setattr(graphs, "_pool", lambda: "pool")

    def capture(into):
        into._graphs["first"] = (FakeGraph(), (), (), _plain)
        raise RuntimeError("CUDA error: operation not permitted when stream is capturing")

    assert graphs.made("charspot", "cuda", capture) is None
    assert given_back == [1]  # (what the warm-ups left cached)
    assert said() == ["the OCR reader charspot reads without CUDA graphs: a capture failed (RuntimeError)"]

    def differ(into):
        raise graphs.GraphsDiffer("charspot ('tail', 3)")

    assert graphs.made("nar", "cuda", differ) is None and "a capture failed (GraphsDiffer)" in said()[-1]
    assert not graphs._lock.locked()


def test_graphs_captured_are_kept_with_the_copy_and_said_in_the_log(monkeypatch, given_back, said):
    monkeypatch.setattr(graphs, "_pool", lambda: "pool")

    def capture(into):
        into._graphs[("dense", 32, 64)] = (FakeGraph(), (), (), _plain)
        into._graphs[("tail", 1)] = (FakeGraph(), (), (), _plain)

    made = graphs.made("charspot", "cuda", capture)
    assert made is not None and len(made) == 2 and ("tail", 1) in made and made.pool == "pool"
    assert made in graphs._live and given_back == [1]
    assert said()[-1].startswith("the OCR reader charspot replays 2 CUDA graphs (captured in ")


def test_the_graphs_of_both_readers_share_one_pool_while_any_holds_graphs(monkeypatch):
    import weakref

    import torch

    monkeypatch.setattr(graphs, "_live", weakref.WeakSet())
    monkeypatch.setattr(torch.cuda, "graph_pool_handle", lambda: "a new pool")
    assert graphs._pool() == "a new pool"
    first = graphs.Graphs("charspot", "the pool")
    first._graphs["k"] = (FakeGraph(), (), (), _plain)
    graphs._live.add(first)
    assert graphs._pool() == "the pool"  # (nar's graph goes into charspot's pool)
    first.drop()  # (its graphs went: a new pool for the next)
    assert graphs._pool() == "a new pool"


# ------------------------------------------------------------------ a read
def test_a_crop_of_a_shape_with_a_graph_replays_it_on_its_own_inputs():
    held, graph, mine = _with_graph()
    assert held.run(("dense", 32, 64), _plain, FakeTensor((1, 3, 32, 64), value="pixels")) == ("replayed",)
    assert graph.replays == 1 and mine.value == "pixels"


def test_a_crop_of_a_shape_with_no_graph_reads_by_the_plain_pass_said_once(said):
    held, graph, _mine = _with_graph()
    for rows in (48, 64):
        x = FakeTensor((1, 3, rows, 64), value=f"pixels {rows}")
        assert held.run(("dense", rows, 64), _plain, x) == ("plain", f"pixels {rows}")
    assert graph.replays == 0 and not held.dropped
    assert said() == ["the OCR reader charspot read a crop by the plain pass: no CUDA graph of its shape "
                      "('dense', 48, 64)"]


def test_an_input_not_of_the_graph_s_shape_or_type_reads_by_the_plain_pass(said):
    held, graph, mine = _with_graph()
    for x in (FakeTensor((1, 3, 32, 64), dtype="uint8", value="bytes"), FakeTensor((1, 3, 64, 32), value="turned")):
        assert held.run(("dense", 32, 64), _plain, x) == ("plain", x.value)
    assert held.run(("dense", 32, 64), _plain, FakeTensor((1, 3, 32, 64)), FakeTensor((1,))) == ("plain", None, None)
    assert graph.replays == 0 and mine.value is None and not held.dropped
    assert len(said()) == 1 and "its input is not the CUDA graph's ('dense', 32, 64)" in said()[0]


def test_a_replay_that_fails_drops_the_reader_s_graphs_and_reads_by_the_plain_pass(said):
    held, _graph, _mine = _with_graph(fails=True)
    x = FakeTensor((1, 3, 32, 64), value="pixels")
    assert held.run(("dense", 32, 64), _plain, x) == ("plain", "pixels")
    assert held.dropped and len(held) == 0
    assert held.run(("dense", 32, 64), _plain, x) == ("plain", "pixels")  # (no graph since: nothing more said)
    assert said() == ["the OCR reader charspot reads without CUDA graphs from now on: a replay failed (RuntimeError)"]
    with graphs.held(held) as got:
        assert got is None  # (the reads after it go by the plain pass, holding nothing)


def test_one_read_replays_graphs_at_a_time():
    held, _graph, _mine = _with_graph()
    with graphs.held(None) as none:
        assert none is None and not graphs._lock.locked()
        assert graphs.run(none, ("dense", 32, 64), _plain, FakeTensor((1,), value="v")) == ("plain", "v")
    order = []

    def other():
        with graphs.held(held):
            order.append("other")

    with graphs.held(held) as got:
        assert got is held and graphs._lock.locked()
        reader = threading.Thread(target=other)
        reader.start()
        reader.join(0.2)
        assert reader.is_alive() and not order  # (it waits for this read's outputs to be read)
        order.append("this")
    reader.join(5)
    assert order == ["this", "other"] and not graphs._lock.locked()


def test_the_readers_need_their_graphs_where_they_capture_them(monkeypatch):
    assert place.readers_graphs() == place.READERS_GRAPHS_MIB
    monkeypatch.setattr(graphs, "ENABLED", False)
    assert place.readers_graphs() == 0
    assert place.Need(place.READERS, 690, extra=270).bare() == place.Need(place.READERS, 420)
    assert place.Need(place.READERS, 420).bare() == place.Need(place.READERS, 420)


# ------------------------------------------------------------------ on a CUDA GPU: the same bits
@requires_cuda
def test_a_graph_s_replay_gives_the_plain_pass_s_bits_on_new_inputs(given_back):
    import torch

    torch.manual_seed(0)
    net = torch.nn.Sequential(torch.nn.Conv2d(3, 8, 3, padding=1), torch.nn.Hardswish(), torch.nn.Conv2d(8, 4, 1))
    net = net.cuda().eval()

    def forward(x):
        y = net(x)
        return y.sigmoid(), y.mean((2, 3)).softmax(-1).max(-1)[1]

    with torch.inference_mode():
        flat = torch.empty(3 * 32 * 48, device="cuda")
        into = torch.empty(4 * 32 * 48 * 2, device="cuda")
        made = graphs.made("test", "cuda", lambda g: (
            g.capture(("x", 32, 48), forward, (flat[:3 * 32 * 48].view(1, 3, 32, 48),)),
            g.capture(("x", 16, 48), lambda x: forward(x)[:1], (flat[:3 * 16 * 48].view(1, 3, 16, 48),), into=into)))
        assert made is not None and len(made) == 2
        for k in range(5):
            x = torch.rand((1, 3, 32, 48), device="cuda") * 255
            with graphs.held(made) as held:
                got = [t.clone() for t in graphs.run(held, ("x", 32, 48), forward, x)]
            want = forward(x)
            assert all(torch.equal(a, b) for a, b in zip(got, want)), k
            small = torch.rand((1, 3, 16, 48), device="cuda")
            with graphs.held(made) as held:
                got = graphs.run(held, ("x", 16, 48), lambda x: forward(x)[:1], small)[0].clone()
            assert torch.equal(got, forward(small)[0])
            other = torch.rand((1, 3, 24, 48), device="cuda")  # (no graph of its shape: the plain pass)
            with graphs.held(made) as held:
                assert torch.equal(graphs.run(held, ("x", 24, 48), forward, other)[0], forward(other)[0])


def _made_up_crops(sample_page, sample_truth, sample_page2, sample_truth2):
    """The made-up pages' lettering cut as the pipeline does, at their size and at others, and crops of the pages'
    drawing of shapes no graph has (the plain pass) or a long run of characters."""
    from PIL import Image

    crops = []
    for page, truth in ((sample_page, sample_truth), (sample_page2, sample_truth2)):
        for bubble in truth:
            x0, y0, x1, y1 = bubble["text_box"]
            crop = page.crop((x0 - 4, y0 - 4, x1 + 4, y1 + 4))
            crops += [crop, crop.resize((max(8, crop.width * 2 // 3), max(8, crop.height * 2 // 3)))]
        crops.append(page.crop((0, 0, page.width, page.height // 2)))
    crops += [sample_page.crop((0, 0, 30, 30 * 13)), sample_page.crop((0, 0, 30 * 13, 30))]  # (13:1 - no graph)
    crops.append(Image.new("RGB", (60, 200), "white"))
    return crops


@requires_cuda
@requires_ocr
def test_the_readers_read_the_same_bits_with_their_graphs_and_without(sample_page, sample_truth, sample_page2,
                                                                     sample_truth2, given_back):
    """Every crop read on the GPU twice, by the graphs and by the plain pass (the copy's graphs set aside): the texts,
    the characters, their boxes, scores and probabilities equal to the bit, both readers."""
    from taslation.config import Settings
    from taslation.ocr import readers as readers_mod

    ocr = readers_mod.Readers(Settings().models_dir, 0)
    engines = ocr._movable()
    crops = _made_up_crops(sample_page, sample_truth, sample_page2, sample_truth2)

    def both(engine, crop):
        device, copy = engine._gpu
        assert copy[-1] is not None and len(copy[-1])
        try:
            engine._gpu = (device, (*copy[:-1], None))
            plain = engine.read_chars(crop) if engine is ocr.charspot else engine.read(crop)
        finally:
            engine._gpu = (device, copy)
        replayed = engine.read_chars(crop) if engine is ocr.charspot else engine.read(crop)
        return plain, replayed

    try:
        assert all(e.to("cuda") for e in engines)
        for engine in engines:
            for k, crop in enumerate(crops):
                plain, replayed = both(engine, crop)
                assert plain == replayed, (engine.name, k)
        assert not any(e._gpu[1][-1].dropped for e in engines)
    finally:
        for e in engines:
            e.to("cpu")
