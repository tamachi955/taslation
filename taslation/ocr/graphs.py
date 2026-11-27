"""The OCR readers' passes on the GPU replayed as CUDA graphs.

A crop's read on the GPU is a few hundred small kernels, and launching them one by one takes longer than the GPU takes
to run them. Captured once as CUDA graphs and replayed, the same kernels on the same inputs give the same bits in less
time: charspot's dense network and its tail (`charspot.CharspotEngine`) and nar's whole pass with its argmax
(`nar.NarEngine`).

WHEN: where a reader's copy is made on the GPU (`place.DeviceModels.to`: at the session's start, in the start's worker
before anything else of this process runs there - `ui.jobs.load_readers`; again where a release let the copy go), for
every input shape the reader is given: nar's are always the same (324 patches, 65 slots: one graph); charspot's dense
network takes one of the grids its 256 cells make (`charspot.graph_grids`: every one of crops at most
`charspot.ASPECT` times as tall as wide or as wide as tall) and its tail one of 1 to `charspot.GRAPH_CHARS`
characters. Each graph is captured on synthetic inputs after `WARM_RUNS` plain passes of them, all on one stream of
this module's (`_stream`: the caching allocator keeps the blocks of a stream to it, so one stream for all), with
``capture_error_mode`` "thread_local" (a capture stops no CUDA call of another thread), and replayed once there: its
outputs must equal the last plain pass's bit for bit, or none of the reader's graphs are kept. The graphs live and go
with the copy (`DeviceModels.to` "cpu": a release, the net).

A READ (`held`, `run`): the graphs of both readers are in one memory pool, so one read replays graphs at a time
(`_lock`; a capture holds it too): the outputs of one are good until the next replay of any. A read waits for it - the
kernels of two reads go one after the other on the GPU all the same. A crop of a shape with no graph, a reader whose
capture failed and every read off the GPU go by the plain pass, which is what the graphs replay: the readings are the
same either way. A capture or a replay that fails drops the reader's graphs for as long as its copy lasts; what fell
back is said once in the program's log per reader and kind, never to the person.

MEMORY: the pool, the graphs' own memory in the driver, their outputs and the inputs they share - about 270 MiB of the
card for both readers, and 2.4 s more at the start for the captures (GTX 1660 Ti; `place.READERS_GRAPHS_MIB`) -
counted in the judgement at the start with the readers (`place.Need.extra`); where the room is short with them the
readers run on the GPU without them, nothing asked (`place.Plan.graphs`). The driver keeps its part (about 170 MiB)
for the process once a capture made it: a release gives back the rest, and a capture again uses it again.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
import weakref
from collections.abc import Callable, Hashable, Iterator, Sequence
from typing import Any

LOG = logging.getLogger(__name__)

ENABLED = True  # (a tool's or a test's switch: False captures nothing, every read goes by the plain pass)
WARM_RUNS = 1  # plain passes of a graph's inputs on the capture's stream before it is captured
CAPTURE_MODE = "thread_local"  # (`torch.cuda.CUDAGraph.capture_begin`: other threads' CUDA calls go on meanwhile)

_stream: list[Any] = []  # the stream every capture runs on, made at the first
_lock = threading.Lock()  # one read replays graphs at a time, and no read while a capture is under way
_live: weakref.WeakSet[Graphs] = weakref.WeakSet()  # the readers' graphs made, in the one pool while they hold any


class GraphsDiffer(RuntimeError):
    """A graph's replay did not give the plain pass's bits on the same inputs: none of the reader's graphs are kept."""


def wanted(device: str) -> bool:
    """Whether a reader's copy on *device* captures its graphs: a CUDA device, `ENABLED`, and the session's plan with
    room for them (`place.graphs_on`)."""
    if not ENABLED or not str(device).startswith("cuda"):
        return False
    from . import place

    return place.graphs_on()


def made(name: str, device: str, capture: Callable[[Graphs], Any]) -> Graphs | None:
    """The reader *name*'s graphs on *device*, captured now by *capture* (given the `Graphs` to fill: `Graphs.capture`
    for each); None where they are not `wanted`, or where a capture failed or differed (said in the log: the plain
    pass reads). What the warm-ups left cached is given back after it."""
    if not wanted(device):
        return None
    import torch

    from .place import give_back

    took = time.perf_counter()
    before = torch.cuda.memory_reserved()
    graphs: Graphs | None = None
    with _lock:
        try:
            graphs = Graphs(name, _pool())
            capture(graphs)
        except Exception as e:  # noqa: BLE001 - the plain pass reads, as without graphs
            LOG.info("the OCR reader %s reads without CUDA graphs: a capture failed (%s)", name, type(e).__name__)
            if graphs is not None:
                graphs.drop()
            graphs = None
        finally:
            give_back()  # (the warm-ups' blocks on the capture's stream)
    if graphs is not None:
        _live.add(graphs)
        LOG.info("the OCR reader %s replays %d CUDA graphs (captured in %.1f s, %d MiB of torch's)", name, len(graphs),
                 time.perf_counter() - took, (torch.cuda.memory_reserved() - before) // (1024 * 1024))
    return graphs


def _pool() -> Any:
    """The memory pool of the graphs that hold any now, else a new one (a pool whose graphs all went is not used
    again)."""
    import torch

    for graphs in list(_live):
        if len(graphs):
            return graphs.pool
    return torch.cuda.graph_pool_handle()


def _capture_stream() -> Any:
    import torch

    if not _stream:
        _stream.append(torch.cuda.Stream())
    return _stream[0]


class Graphs:
    """One reader's CUDA graphs on the GPU, in *pool*: for each key (a network and its input's shape, the reader's to
    name), the graph of a pass on its own input tensors, and its outputs."""

    def __init__(self, name: str, pool: Any) -> None:
        self.name = name
        self.pool = pool
        self._graphs: dict[Hashable, tuple[Any, tuple[Any, ...], tuple[Any, ...], Callable[..., Any]]] = {}
        self._said: set[str] = set()
        self.dropped = False

    def __len__(self) -> int:
        return len(self._graphs)

    def __contains__(self, key: Hashable) -> bool:
        return key in self._graphs

    def capture(self, key: Hashable, forward: Callable[..., Sequence[Any]], inputs: Sequence[Any],
                into: Any = None) -> None:
        """*forward*(*inputs*) captured as the graph of *key*: *inputs* are its own from now on (their contents are
        what each replay copies in), *forward* gives a tuple of tensors - or, with *into* (a flat tensor of the
        outputs' type, outside the pool), the graph copies them into views of it, one after the other, which are
        what its replays give: graphs that share *into* hold no outputs of their own. `WARM_RUNS` plain passes first,
        then the capture and one replay, all on the capture's stream; the replay's outputs must equal the last plain
        pass's, bit for bit (`GraphsDiffer` otherwise). Raises whatever went wrong (`made` drops the reader's
        graphs)."""
        import torch

        stream = _capture_stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            want: tuple[Any, ...] = ()
            for _run in range(max(1, WARM_RUNS)):
                want = tuple(forward(*inputs))
            run = forward
            if into is not None:
                views, at = [], 0
                for out in want:
                    views.append(into[at:at + out.numel()].view(out.shape))
                    at += out.numel()
                views = tuple(views)

                def run(*args: Any, _forward: Callable[..., Sequence[Any]] = forward) -> tuple[Any, ...]:
                    for view, out in zip(views, _forward(*args)):
                        view.copy_(out)
                    return views

            graph = torch.cuda.CUDAGraph()
            graph.capture_begin(pool=self.pool, capture_error_mode=CAPTURE_MODE)
            try:
                outputs = tuple(run(*inputs))
            finally:
                graph.capture_end()
            graph.replay()
            same = len(outputs) == len(want) and all(torch.equal(a, b) for a, b in zip(outputs, want))
        torch.cuda.current_stream().wait_stream(stream)
        if not same:
            raise GraphsDiffer(f"{self.name} {key}")
        self._graphs[key] = (graph, tuple(inputs), outputs, forward)  # (*forward* keeps the weights the graph reads)

    def run(self, key: Hashable, forward: Callable[..., Sequence[Any]], *inputs: Any) -> Sequence[Any]:
        """The outputs of *forward*(*inputs*): the graph of *key* replayed on them where there is one (its outputs,
        good until the next replay: read them before the read gives the graphs back, `held`), else the plain pass.
        A replay that fails drops the reader's graphs and reads by the plain pass."""
        held = self._graphs.get(key)
        if held is None:
            if not self.dropped:
                self._say("shape", "the OCR reader %s read a crop by the plain pass: no CUDA graph of its shape %s",
                          key)
            return forward(*inputs)
        graph, mine, outputs, _forward = held
        if len(mine) != len(inputs) or any(a.shape != b.shape or a.dtype != b.dtype for a, b in zip(mine, inputs)):
            self._say("input", "the OCR reader %s read a crop by the plain pass: its input is not the CUDA graph's %s",
                      key)
            return forward(*inputs)
        try:
            for to, value in zip(mine, inputs):
                to.copy_(value)
            graph.replay()
        except Exception as e:  # noqa: BLE001 - the plain pass reads (a CUDA error there goes to the readers' net)
            self.drop()
            self._say("replay", "the OCR reader %s reads without CUDA graphs from now on: a replay failed (%s)",
                      type(e).__name__)
            return forward(*inputs)
        return outputs

    def drop(self) -> None:
        """The graphs let go (their memory with the next `place.give_back`); every read by the plain pass after."""
        self.dropped = True
        self._graphs = {}

    def _say(self, kind: str, text: str, *args: Any) -> None:
        if kind not in self._said:
            self._said.add(kind)
            LOG.info(text, self.name, *args)


@contextlib.contextmanager
def held(graphs: Graphs | None) -> Iterator[Graphs | None]:
    """*graphs* for one read, once no other read replays graphs (`_lock`, waited for); None for none (the plain pass
    reads: `run`)."""
    if graphs is None or graphs.dropped:
        yield None
        return
    with _lock:
        yield graphs


def run(graphs: Graphs | None, key: Hashable, forward: Callable[..., Sequence[Any]], *inputs: Any) -> Sequence[Any]:
    """*forward*(*inputs*) by the graph of *key* of the *graphs* held for this read (`held`), else by the plain pass."""
    if graphs is None:
        return forward(*inputs)
    return graphs.run(key, forward, *inputs)
