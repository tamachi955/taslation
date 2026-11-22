"""The lines of a page unit sent to the translator as soon as they are read (`LineStream`): the first bubble of a page
comes while the rest of it is still read, not after the whole unit's OCR.

The window's page job reads a unit's regions one at a time, each judged as soon as it is read (`pipeline.JUDGE_AT_READ`).
After each one, the unit's lines as far as they are known go to the translator's page request in reading order, one run
at a time (`continuation.runs`: a line, or the lines whose sentence goes on in the next bubble), on a thread of their
own, through the translator's `plamo.PageSession` - the same requests, history, joined runs, following Japanese,
glossary, names and draws that `PlamoTranslator.translate_page` makes for the same lines. A run leaves when

* its lines are settled (read by the readers that settle a region: the second reader, the third one where they differ),
* the candidates that may come before them are judged. The lines known and the candidates that may still be text are
  put in the order the unit will have once read (`ORDER_AS_READ`: `Pipeline._order_read` orders the regions read as
  text among themselves, and a tall candidate that is no text no longer joins two rows), and the lines before the
  first such candidate may leave, as far as the order with none of the classical candidates begins with them too; a
  line that letters the place of another is left out as the reading's end leaves it out. Those candidates are the
  layout model's, which are read first, and the classical ones, read after them, but for one that what was read as
  text so far covers: it is left out unread at its turn (`HOLD_FOR_CLASSICAL`). Both since 2026-11-22: before, the
  lines went in the order before the reading with the classical candidates taken for no text, and 15 % of the lines
  sent early on the stand-in were taken back for the order, none since (docs/OFFLINE_VERIFICATION.md),
* an open-ended line (`continuation.ends_open`, or one the reader marked as going on) has its next line,
* and a joined run has all its members (or `continuation.MAX_JOINED` of them and the line after them).

Each answer is lettered at once on the page's drafts layer of its own (`PageFill.early_draft`: copies of the regions
on a copy of the page; the regions themselves are never touched), and so is each line known that the book's lines
already translate (`linememo`: it is asked nothing, and the request hands its translation over first), once the
frame was seen on show. Once the unit is read, ordered and given its rooms,
its final list is what the page's request is made of (`Pipeline._translate_regions`, `linememo.Plan`): the runs sent
that it begins with stand - their answers taken as that request's own, lettered on the page as its drafts are, in
the same order -, and from the first that does not (a line read later came before it, a paragraph was joined, the
order changed, a line turned out to be no text) every run sent is taken back: the request under way cancelled, the
session put back where it stood before that run (its pairs, the draws, the book's names: `PageSession.rewind`), its
lettering taken off the page, and the final runs asked from there. Nothing of a run taken back is kept, stored or left
in a later request's context; the page's history and cache are what the request made all at once would have left
(answers aside: the model samples anew). The measurements of 2026-11-22 (docs/OFFLINE_VERIFICATION.md) found the
first line of a page right 199 times in 205, every line 175 times.

The page job's rules stay as they were: nothing is asked before the frame was seen on show (`PageGate.on_show`, before
the first run), nothing is kept before it is confirmed (`Provisional`), a soft frame is not read, and the page's cancel
stops the sender too. Only the window's page job streams (a unit read in its turn, with a translator that has a
`page_session`); a unit read beside the one before (`ReadBeside`), a cached page completed, the backlog's scan, the
command line and the evaluation tools ask a unit's lines all at once, as before. Nothing here is written anywhere;
nothing of a page's text is logged (`Pipeline.stream_log` keeps counts and times)."""

from __future__ import annotations

import itertools
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Sequence

from .messages import Cancelled, Message
from .translate.base import TranslationError
from .translate.continuation import MAX_JOINED, ends_open, facts_of, runs

STREAM_LINES = True  # the window's page job sends a unit's lines as they are read (False: all at once, after it)
# a classical candidate not read yet that what was read as text does not cover holds back the lines after it in the
# unit's order (False: it is taken for no text, the rule until 2026-11-22, whose late surprises took lines back)
HOLD_FOR_CLASSICAL = True
# the lines known are put in the order the unit will be read in once all of it is read (`Pipeline._order_read`: the
# regions read as text ordered among themselves), not in its order before the reading (False: that one)
ORDER_AS_READ = True
WAIT_STEP_S = 0.01  # how often a wait of the stream looks at the page's cancel
# the facts of a line its request is made of (`plamo.PageSession.run`: the speaker, the reader's hint, whether its
# sentence goes on, its page unit): two runs with the same lines and these are the same request
REQUEST_FACTS = ("speaker", "note", "continues", "page")
_TOKENS = itertools.count(1)
_LOCAL = threading.local()  # (the sender's: the run whose requests are under way, `current_token`)
_POOL: list[ThreadPoolExecutor] = []
_POOL_LOCK = threading.Lock()


def _sender_pool() -> ThreadPoolExecutor:
    """The one thread the streams' requests are made on (one page job at a time; its connection to the server kept)."""
    with _POOL_LOCK:
        if not _POOL:
            _POOL.append(ThreadPoolExecutor(max_workers=1, thread_name_prefix="taslation-lines"))
        return _POOL[0]


def current_token() -> int | None:
    """(for the tools) The run whose request is under way on this thread, by its number (`LineStream.stream_log`'s
    ``tokens_taken_back`` names the runs taken back); None outside the sender."""
    return getattr(_LOCAL, "token", None)


def _frozen(facts: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple((k, facts[k]) for k in REQUEST_FACTS if k in facts)


class RunSpec:
    """One run as the page's request asks it: its lines (`plamo.one_line`), each one's facts that make the request
    (`REQUEST_FACTS`), and the Japanese given after its last line (`PlamoTranslator._following`). Equal specs are the
    same request from the same session state."""

    __slots__ = ("lines", "facts", "follow")

    def __init__(self, lines: Sequence[str], facts: Sequence[dict[str, Any]], follow: Sequence[str]):
        self.lines = tuple(lines)
        self.facts = tuple(_frozen(f) for f in facts)
        self.follow = tuple(follow)

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, RunSpec) and self.lines == other.lines and self.facts == other.facts
                and self.follow == other.follow)

    def __hash__(self) -> int:
        return hash((self.lines, self.facts, self.follow))

    def dicts(self) -> list[dict[str, Any]]:
        return [dict(f) for f in self.facts]


def why_differs(sent: RunSpec, final: RunSpec | None, lines: set[str]) -> str:
    """Why the run *sent* is not the request's run in its place (*final*; None: the request has fewer runs), for the
    counts (no text): "order" (its lines are all asked, in other runs or another order: the order changed, lines were
    joined or parted), "not asked" (one of its lines is not asked: no text after all, or its answer reused), "facts"
    (its lines' facts: the speaker, the reader's hint, whether the sentence goes on), "follow" (the Japanese after it)."""
    if final is None or sent.lines != final.lines:
        return "order" if all(line in lines for line in sent.lines) else "not asked"
    return "facts" if sent.facts != final.facts else "follow"


def page_runs(translator: Any, texts: Sequence[str], meta: Sequence[dict[str, Any] | None] | None,
              upcoming: Sequence[str] = ()) -> list[tuple[RunSpec, list[int]]]:
    """The runs of the page request for *texts* (its lines, with their facts *meta*) as `translate_page` asks them,
    each with its lines' places in *texts*."""
    from .translate.plamo import request_lines

    lines, facts = request_lines(texts, meta)
    after = list(lines) + [str(t) for t in upcoming]
    return [(RunSpec([lines[k] for k in run], [facts[k] for k in run],
                     translator._following(lines, facts, after, run[-1])), run)
            for run in runs(facts, len(lines), MAX_JOINED)]


class _Sent:
    """A run sent: its spec, its regions (as the stream knew them), where the session stood before it, its answers as
    they come (None until then), whether it is the final request's (`final`), how it ended."""

    def __init__(self, spec: RunSpec, regions: Sequence[Any], mark: tuple[Any, ...], final: bool):
        self.spec, self.regions, self.mark, self.final = spec, list(regions), mark, final
        self.token = next(_TOKENS)
        self.answers: list[str | None] = [None] * len(spec.lines)
        self.done = False
        self.error: BaseException | None = None
        self.redo = threading.Event()  # set: taken back while under way (its request cancelled)
        self.requests = 0
        self.early = False  # sent before the unit's final list was known
        self.drafted: list[Any] = []  # the regions lettered on the drafts layer from its answers
        self.index = 0  # its place among the runs when it was sent
        self.t0 = time.monotonic()


class _Either:
    def __init__(self, a: Any, b: threading.Event):
        self.a, self.b = a, b

    def is_set(self) -> bool:
        return bool(self.a is not None and self.a.is_set()) or self.b.is_set()


class LineStream:
    """The lines of one page unit sent as they are read (see the module's docstring). The worker tells it each region
    judged (`judged`) and the end of the reading (`read_done`); the page's request then goes through it
    (`translate_page`, in place of the translator's), and `close` ends it whatever happened. *regions*: the unit's
    regions in their order before the reading; *reuse* as `Pipeline._translate_regions` takes it."""

    def __init__(self, pipeline: Any, unit: Any, regions: Sequence[Any], fill: Any, cancel: Any,
                 on_slow: Callable[[float], None] | None, reuse: bool | None, gate: Any):
        from .translate.base import context_fits

        self.pipeline = pipeline
        self.translator = pipeline.translator
        self.unit, self.unit_box = unit.index, unit.box
        self.order = list(regions)
        self.fill, self.cancel, self.on_slow, self.gate = fill, cancel, on_slow, gate
        self.serve, self.learns = bool(reuse), reuse is not None
        self.unjudged_models = {id(r) for r in regions if r.from_model}
        self.judged_ids: set[int] = set()
        self.has_models = bool(self.unjudged_models)
        self.rgb: Any = None  # the page (`Pipeline._ocr_regions` sets it): the order foreseen (`ORDER_AS_READ`)
        self.panels: dict[tuple[tuple[int, ...], ...], Any] = {}  # (its panels, per set of lettering boxes)
        self.reading_done = False
        self.held: dict[int, float] = {}  # (the counts: lines known to the earlier rule, not yet here - since when)
        self.clones: dict[int, Any] = {}
        self.notes = pipeline.premises()
        self.context = pipeline._grown.peek(context_fits(self.translator, self.notes))  # (what `context_pairs` takes)
        self.session = self.translator.page_session(self.context, self.notes, [])
        self.start = self.session.mark()
        self.lock = threading.Condition()
        self.wanted: list[tuple[RunSpec, list[Any]]] = []
        self.sent: list[_Sent] = []
        self.flight: _Sent | None = None
        self.back_to: int | None = None
        self.complete = False  # the final list is known (`translate_page`)
        self.closed = False
        self.halted = threading.Event()  # (set by `_halt`: the sender's wait at the gate ends too)
        self.gated: bool | None = None  # None: the gate not asked yet; then whether the frame was seen on show
        self.future: Future[Any] | None = None
        self.discarded = False
        self.early_ended = False
        self.t0 = time.monotonic()
        self.taken_back: list[_Sent] = []
        self.served_ids: set[int] = set()  # the regions whose reused translation went to the drafts layer
        self.served_waiting: list[tuple[Any, Any, str]] = []  # (those known before the frame was seen on show)
        self.first_answer_ms: float | None = None
        self.log: dict[str, Any] = {"unit": self.unit, "runs_sent_early": 0, "lines_sent_early": 0, "runs_stood": 0,
                                    "lines_stood": 0, "runs_taken_back": 0, "lines_taken_back": 0,
                                    "requests_taken_back": 0, "first_taken_back": False, "requests": 0,
                                    "final_lines": 0, "final_from_taken_back": 0, "tokens_taken_back": [],
                                    "first_answer_ms": None, "reconciled_ms": None, "outcome": "",
                                    "why_taken_back": "", "held_ms": []}

    # --- the worker's side, while the unit is read ------------------------------------------------------------------
    def judged(self, region: Any) -> None:
        """*region* judged (read, settled, a twin or a repeat told): the lines known so far are offered."""
        import copy

        from .detect.layout import take_shape

        self.judged_ids.add(id(region))
        self.unjudged_models.discard(id(region))
        try:
            if self._text(region) and id(region) not in self.clones:
                clone = copy.copy(region)  # (what the drafts layer letters: shaped as the region will be, never it)
                if getattr(clone, "after", None) is not None:
                    take_shape(clone)
                self.clones[id(region)] = clone
        except Exception:  # noqa: BLE001 - no copy to letter: its answer waits for the page's own draft
            pass
        self._offer()

    def read_done(self) -> None:
        """Every region of the unit judged."""
        self.unjudged_models.clear()
        self.reading_done = True
        self._offer()

    @staticmethod
    def _text(r: Any) -> bool:
        from .annotations import ERASE_ONLY

        return r.status == "untranslated" and bool(r.source_text) and r.tag != ERASE_ONLY

    def _provisional(self) -> list[Any]:
        """The unit's lines as known now, in its order before the reading: those judged to be text, up to the first
        candidate not judged yet that may still be text - one of the layout model, or a classical one that what was
        read as text so far does not cover (`HOLD_FOR_CLASSICAL`; one it covers is left out unread at its turn,
        `Pipeline._ocr_regions`: what was read as text only grows). Once the unit is read, every line judged."""
        from .detect.layout import cover_of

        if self.rgb is not None and ORDER_AS_READ:
            return self._provisional_ordered()
        out = []
        read: list[Any] | None = None
        for r in self.order:
            if id(r) in self.unjudged_models:
                break
            if id(r) in self.judged_ids:
                if self._text(r):
                    out.append(r)
                continue
            if HOLD_FOR_CLASSICAL and not self.reading_done:
                if read is None:
                    read = [q for q in self.order
                            if id(q) in self.judged_ids and q.status == "untranslated" and q.source_text]
                if cover_of(r, read) is None:
                    break  # (it may be text, and come before the lines after it: they wait for its reading)
        return out

    def _undecided(self) -> list[Any]:
        """The candidates not judged yet that may still be text: the layout model's; a classical one that the regions
        read as text so far do not cover (with the layout model's candidates read first, one they cover is left out
        unread at its turn), every one without them; none once the unit is read."""
        from .detect.layout import cover_of

        if self.reading_done:
            return []
        rest = [r for r in self.order if id(r) not in self.judged_ids]
        if not HOLD_FOR_CLASSICAL:
            return [r for r in rest if r.from_model]
        if not self.has_models:
            return rest  # (read in their order, each one: none is left out unread)
        read = [q for q in self.order if id(q) in self.judged_ids and q.status == "untranslated" and q.source_text]
        return [r for r in rest if r.from_model or cover_of(r, read) is None]

    def _provisional_ordered(self) -> list[Any]:
        """`_provisional` in the order the unit's request will have (`ORDER_AS_READ`): the lines judged to be text and
        the candidates that may still be text ordered as `Pipeline._order_read` orders a unit once read
        (`order_on_page` over those alone, each line shaped as it will be; the reader's order first), the lines up to
        the first such candidate - as far as they are also the first lines of the order the unit has should none of
        the classical ones be text (the layout model's are taken for text there too: they nearly always are): one
        judged no text drops out, and the rows and panels found without it may put the lines otherwise (a tall
        candidate that is no text joined two rows)."""
        import copy

        t = time.perf_counter()
        text = self._lettering_once([r for r in self.order if id(r) in self.judged_ids and self._text(r)])
        undecided = self._undecided()
        stand_ins: dict[int, Any] = {}
        for r in text:
            stand_ins[id(r)] = self.clones.get(id(r)) or copy.copy(r)
        for r in undecided:
            stand_ins[id(r)] = copy.copy(r)  # (never the region itself: the ordering marks what it orders)
        waiting = {id(r) for r in undecided}
        out = []
        for r in self._foreseen([*text, *undecided], stand_ins):
            if id(r) in waiting:
                break
            out.append(r)
        if out and not all(r.from_model for r in undecided):
            alone = self._foreseen([*text, *(r for r in undecided if r.from_model)], stand_ins)
            n = 0
            while n < len(out) and out[n] is alone[n]:
                n += 1
            del out[n:]
        self.log["order_ms"] = round(self.log.get("order_ms", 0.0) + (time.perf_counter() - t) * 1000.0, 1)
        return out

    def _lettering_once(self, text: list[Any]) -> list[Any]:
        """*text* (lines judged, in the unit's order before the reading) without those the unit's reading will leave
        out once it is read as lettering the same place as another (`Pipeline._ocr_regions`: the first stays, and a
        shaped region before a plain box), judged on their shaped copies as it judges the shaped regions."""
        from .pipeline import _plain, _same_lettering

        def same(a: Any, b: Any) -> bool:
            ca, cb = self.clones.get(id(a), a), self.clones.get(id(b), b)
            return ca.adopted is b or cb.adopted is a or _same_lettering(ca, cb)

        def plain(r: Any) -> bool:
            return _plain(self.clones.get(id(r), r))

        kept: list[Any] = []
        for r in text:
            twin = next((q for q in kept if same(q, r)), None)
            if twin is None:
                kept.append(r)
            elif plain(twin) and not plain(r):
                kept[kept.index(twin)] = r
        order = {id(r): i for i, r in enumerate(text)}
        return sorted(kept, key=lambda r: order[id(r)])

    def _foreseen(self, regions: Sequence[Any], stand_ins: dict[int, Any]) -> list[Any]:
        """*regions* in the order `Pipeline._order_read` would give them, were they the unit's text: their stand-ins
        ordered as `order_on_page` orders (the panels found with their lettering as what may sit on a gutter, kept for
        each set of lettering boxes: the unit's page does not change), `apply_order_hints`; in the unit's order before
        the reading if that fails."""
        from .detect.bubbles import order_regions
        from .detect.panels import find_panels
        from .regions import apply_order_hints

        chosen = {id(r) for r in regions}
        mine = [r for r in self.order if id(r) in chosen]
        back = {id(stand_ins[id(r)]): r for r in mine}
        try:
            stand = [stand_ins[id(r)] for r in mine]
            boxes = [s.text_box for s in stand]
            key = tuple(sorted(tuple(int(v) for v in b) for b in boxes))
            if key not in self.panels:
                self.panels[key] = find_panels(self.rgb, self.unit_box, boxes) if stand else None
            return [back[id(s)] for s in apply_order_hints(order_regions(stand, self.pipeline.rtl, self.panels[key]))]
        except Exception:  # noqa: BLE001 - no order to foresee: the unit's own, before the reading
            return mine

    def _held_since(self, prov: Sequence[Any]) -> None:
        """(the counts) The lines the earlier rule - a classical candidate not read yet taken for no text, the order
        before the reading - would have known by now and *prov* does not yet: since when each was held, and how long
        once it is known."""
        if not (HOLD_FOR_CLASSICAL or ORDER_AS_READ):
            return
        now = time.monotonic()
        known = {id(r) for r in prov}
        for r in self.order:
            if id(r) in self.unjudged_models:
                break
            if id(r) in self.judged_ids and self._text(r) and id(r) not in known:
                self.held.setdefault(id(r), now)
        for i in [i for i in self.held if i in known]:
            self.log["held_ms"].append(round((now - self.held.pop(i)) * 1000.0, 1))

    def _runs_known(self) -> tuple[list[tuple[RunSpec, list[Any]]], list[tuple[Any, str]]]:
        """The runs of the lines known now that may leave (see the module's docstring), in order, up to the first that
        may not yet; and the lines known whose translation the book's lines give (`linememo.Plan.served`: no request),
        each with it."""
        from . import linememo
        from .translate.plamo import request_lines

        prov = self._provisional()
        self._held_since(prov)
        if not prov:
            return [], []
        meta = facts_of(prov, [(r.unit, self.unit_box) for r in prov])
        known = len(prov)
        if meta[-1].get("continues") or ends_open(prov[-1].source_text):
            known -= 1  # (an open-ended last line: whether it goes on depends on the next one)
        if not known:
            return [], []
        texts = [r.source_text for r in prov[:known]]
        plan = linememo.plan_for(self.pipeline, texts, meta[:known], (), serve=self.serve, learn=self.learns)
        served = [(prov[i], text) for i, text in sorted(plan.served.items())]
        asked = plan.asked
        lines, facts = request_lines([texts[i] for i in asked], [meta[i] for i in asked])
        out: list[tuple[RunSpec, list[Any]]] = []
        for run in runs(facts, len(lines), MAX_JOINED):
            if facts[run[-1]].get("continues") and (len(run) < MAX_JOINED or run[-1] + 1 >= len(lines)):
                break  # (its next line not known yet: it joins it, or follows it)
            follow = self.translator._following(lines, facts, lines, run[-1])
            out.append((RunSpec([lines[k] for k in run], [facts[k] for k in run], follow),
                        [prov[asked[k]] for k in run]))
        return out, served

    def _offer(self) -> None:
        if self.complete or self.closed:
            return
        try:
            wanted, served = self._runs_known()
        except Exception:  # noqa: BLE001 - a guess that fails sends nothing; the final request is made as ever
            wanted, served = [], []
        with self.lock:
            if self.complete or self.closed:
                return
            self._draft_served(served)
            self.wanted = wanted
            m = 0
            while m < len(self.sent) and m < len(wanted) and self.sent[m].spec == wanted[m][0]:
                m += 1
            if m < len(self.sent):
                if not self.log.get("why_taken_back"):
                    asked = {line for spec, _regions in wanted for line in spec.lines}
                    self.log["why_taken_back"] = "while read: " + why_differs(
                        self.sent[m].spec, wanted[m][0] if m < len(wanted) else None, asked)
                self._back(m)
            self.lock.notify_all()
            self._start()

    def _draft_served(self, served: Sequence[tuple[Any, str]]) -> None:
        """(under the lock) Each line known whose translation the book's lines give (*served*: region, translation)
        lettered on the drafts layer once, as an answer is - the request would take that translation without asking
        the model, and hands it over first -, once the frame was seen on show (the sender asks that, `_work`)."""
        if self.fill is None:
            return
        for region, text in served:
            clone = self.clones.get(id(region))
            if id(region) in self.served_ids or clone is None or not text:
                continue
            self.served_ids.add(id(region))
            if self.gated:
                self.fill.early_draft(region, clone, text)
            elif self.gated is None:
                self.served_waiting.append((region, clone, text))

    def _back(self, m: int) -> None:
        """(under the lock) The runs sent from the *m*th on taken back: the one under way cancelled; the sender puts
        the session back (`_apply_back`)."""
        if self.back_to is None or m < self.back_to:
            self.back_to = m
        for s in self.sent[m:]:
            s.redo.set()

    def _start(self) -> None:
        """(under the lock) The sender started once there is a run to send."""
        if self.future is None and self.wanted and not self.closed:
            self.future = _sender_pool().submit(self._work)

    # --- the sender ---------------------------------------------------------------------------------------------------
    def _apply_back(self) -> None:
        """(the sender, under the lock, no run under way) A take-back asked for done: the session as it stood before
        the first run taken back, those runs gone, their lettering taken off the page."""
        m, self.back_to = self.back_to, None
        if m is None or m >= len(self.sent):
            return
        gone = self.sent[m:]
        self.session.rewind(gone[0].mark)
        del self.sent[m:]
        self.taken_back.extend(gone)
        drafted = [r for s in gone for r in s.drafted]
        if drafted and self.fill is not None:
            self.fill.early_withdraw(drafted)

    def _next(self) -> tuple[_Sent | None, bool]:
        """(the sender) The next run to send, waiting for it; (None, False) once there is none to come."""
        with self.lock:
            while True:
                if self.back_to is not None:
                    self._apply_back()
                if self.closed or (self.cancel is not None and self.cancel.is_set()) or self.gated is False:
                    return None, False
                k = len(self.sent)
                if k < len(self.wanted) and (not self.sent or self.sent[-1].error is None):
                    spec, regions = self.wanted[k]
                    s = _Sent(spec, regions, self.session.mark(), self.complete)
                    s.early, s.index = not self.complete, k
                    self.sent.append(s)
                    self.flight = s
                    return s, self.gated is None
                if self.complete and k >= len(self.wanted):
                    return None, False
                self.lock.wait(WAIT_STEP_S * 5)

    def _work(self) -> None:
        while True:
            s, ask_gate = self._next()
            if s is None:
                return
            if ask_gate:  # (before the first request: the frame seen on show, as `_translate_regions` asks it)
                ok = self.gate is None or self.gate.on_show(_Either(self.cancel, self.halted), close=False)
                with self.lock:
                    self.gated = bool(ok)
                    waiting, self.served_waiting = self.served_waiting, []
                    if ok and not (self.complete or self.closed) and self.fill is not None:
                        for region, clone, text in waiting:  # (the reused translations known meanwhile)
                            self.fill.early_draft(region, clone, text)
                    if not ok:
                        self.sent.remove(s)
                        self.flight = None
                        self.lock.notify_all()
                        return
            self._run(s)

    def _run(self, s: _Sent) -> None:
        def took(i: int, got: str) -> None:
            with self.lock:
                s.answers[i] = got
                if self.first_answer_ms is None and got:
                    self.first_answer_ms = (time.monotonic() - self.t0) * 1000.0
                if got and not self.complete and not s.redo.is_set() and self.fill is not None:
                    region = s.regions[i] if i < len(s.regions) else None
                    clone = self.clones.get(id(region)) if region is not None else None
                    if clone is not None:
                        self.fill.early_draft(region, clone, got)
                        s.drafted.append(region)
                self.lock.notify_all()

        before = self.session.requests
        _LOCAL.token = s.token
        stopped = False
        try:
            self.session.run(s.spec.lines, s.spec.dicts(), s.spec.follow, took, _Either(self.cancel, s.redo),
                             self.on_slow)
        except Cancelled:
            stopped = True
        except BaseException as e:  # noqa: BLE001 - the request's failure, said where the page's request takes it
            s.error = e
        finally:
            _LOCAL.token = None
            with self.lock:
                s.requests = self.session.requests - before
                s.done = not stopped
                self.flight = None
                self.lock.notify_all()

    # --- the page's request ---------------------------------------------------------------------------------------
    def translate_page(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = (), notes: str = "",
                       upcoming: Sequence[str] = (), meta: Sequence[dict[str, Any]] | None = None,
                       on_item: Callable[[int, str], None] | None = None, cancel: Any = None,
                       on_slow: Callable[[float], None] | None = None,
                       computed: list[tuple[str, str]] | None = None) -> list[str]:
        """The translator's `translate_page` for the unit's final lines (*texts*, *meta*: those `linememo.Plan.ask`
        asks), made of the runs sent that stand and the rest asked now (see the module's docstring): the same
        answers in the same order to *on_item*, the same pairs in *computed*, the same errors."""
        if not texts:
            return []
        final = page_runs(self.translator, texts, meta, upcoming)
        same = (list(context) == list(self.context) and str(notes) == str(self.notes)
                and getattr(notes, "sheet", None) is getattr(self.notes, "sheet", None)
                and getattr(notes, "names", None) is getattr(self.notes, "names", None))
        with self.lock:
            self.complete = True
            stand = 0
            if same:
                while (stand < len(self.sent) and stand < len(final) and self.sent[stand].spec == final[stand][0]
                       and not self.sent[stand].redo.is_set()):
                    stand += 1
            for s in self.sent[:stand]:
                s.final = True
            if stand < len(self.sent):
                if not self.log.get("why_taken_back"):
                    asked = {line for spec, _run in final for line in spec.lines}
                    self.log["why_taken_back"] = "at the end: " + (
                        why_differs(self.sent[stand].spec, final[stand][0] if stand < len(final) else None, asked)
                        if same else "context")
                    # (what became of its regions once the unit was read: their status, the layout model's or not, and
                    # for a repeat whether what it repeats is a region of the unit's or one its reading made)
                    self.log["taken_back_as"] = [
                        f"{r.status}{' (model)' if r.from_model else ''}"
                        + ("" if getattr(r, "repeats", None) is None else
                           f" of a region{' (model)' if r.repeats.from_model else ''}"
                           if any(r.repeats is q for q in self.order) else " of one made")
                        for r in self.sent[stand].regions]
                self._back(stand)
            self.wanted = [(spec, []) for spec, _run in final]
            self.log["runs_stood"] = stand
            self.log["lines_stood"] = sum(len(s.spec.lines) for s in self.sent[:stand])
            self.log["reconciled_ms"] = round((time.monotonic() - self.t0) * 1000.0, 1)
            self.lock.notify_all()
            self._start()
        out = [""] * len(texts)
        given: list[tuple[int, int]] = []  # (run, line in it) handed to *on_item* so far
        try:
            for n, (_spec, run) in enumerate(final):
                s = self._final(n, cancel)
                for i, k in enumerate(run):
                    got = self._answer(s, i, cancel)
                    out[k] = got
                    given.append((n, i))
                    if got and on_item is not None:
                        on_item(k, got)
            self._end_early()
        except BaseException:
            self._halt()
            self._drain(final, given, out, on_item)
            if computed is not None:
                computed.extend(self.session.computed or [])
            self._end_early()
            raise
        if computed is not None:
            computed.extend(self.session.computed or [])
        self.log["final_lines"] = len(out)
        if not any(out):
            raise TranslationError(Message("ollama.bad_answer", chars=0))
        return out

    def _final(self, n: int, cancel: Any) -> _Sent:
        """The final request's *n*th run as sent: waited for (the session put back first, where runs are taken back)."""
        with self.lock:
            while not (n < len(self.sent) and self.sent[n].final and self.back_to is None):
                if (cancel is not None and cancel.is_set()) or (self.cancel is not None and self.cancel.is_set()):
                    raise Cancelled()
                if self.gated is False:  # (the frame not on show any more: `_translate_regions` asks nothing then)
                    raise Cancelled()
                if self.future is not None and self.future.done() and not self.closed:
                    self.future = None
                    self._start()  # (the sender ended - nothing was left to send when it looked: it looks again)
                self.lock.wait(WAIT_STEP_S)
            return self.sent[n]

    def _answer(self, s: _Sent, i: int, cancel: Any) -> str:
        """The *i*th answer of the run *s*, waited for; its failure or the page's cancel raised."""
        with self.lock:
            while s.answers[i] is None:
                if s.error is not None:
                    raise s.error
                if (cancel is not None and cancel.is_set()) or (self.cancel is not None and self.cancel.is_set()):
                    raise Cancelled()
                if s.done:  # (cannot be: a run done gave each line its answer)
                    raise TranslationError(Message("ollama.bad_answer", chars=0))
                if not self.early_ended:
                    self.lock.release()
                    try:
                        self._end_early()  # (what was answered so far is lettered on the page: the layer goes)
                    finally:
                        self.lock.acquire()
                    continue
                self.lock.wait(WAIT_STEP_S)
            return str(s.answers[i])

    def _drain(self, final: Sequence[tuple[RunSpec, list[int]]], given: list[tuple[int, int]], out: list[str],
               on_item: Callable[[int, str], None] | None) -> None:
        """(the page stopped or failed, the sender halted) The answers of the final runs that came and were not handed
        over yet, handed over in order up to the first missing, so that what the request computed (*computed*) and
        what was answered agree, as in a request stopped there."""
        done = set(given)
        with self.lock:
            sent = list(self.sent)
        for n, (_spec, run) in enumerate(final):
            if n >= len(sent) or not sent[n].final:
                return
            s = sent[n]
            for i, k in enumerate(run):
                if (n, i) in done:
                    continue
                got = s.answers[i]
                if got is None:
                    return
                out[k] = got
                if got and on_item is not None:
                    on_item(k, got)

    # --- the end ------------------------------------------------------------------------------------------------------
    def _end_early(self) -> None:
        if self.early_ended:
            return
        self.early_ended = True
        if self.fill is not None:
            self.fill.early_end()

    def _halt(self) -> None:
        """The sender stopped (its request under way cancelled) and waited for."""
        self.halted.set()
        with self.lock:
            self.closed = True
            if self.flight is not None:
                self.flight.redo.set()
            self.lock.notify_all()
            future = self.future
        if future is not None:
            try:
                future.result()
            except BaseException:  # noqa: BLE001 - the sender raises nothing of its own
                pass

    def gate_passed(self) -> None:
        """(the worker) The frame was seen on show before the page's request (`Pipeline._translate_regions`): the
        sender does not ask again."""
        with self.lock:
            if self.gated is None:
                self.gated = True

    def discard(self, why: str = "") -> None:
        """(the worker) The unit asks nothing of the translator after all (no line, or every one reused: *why*, for the
        counts): every run sent taken back before anything else is asked."""
        if self.discarded or self.complete:
            return
        self.discarded = True
        if self.sent and not self.log.get("why_taken_back"):
            self.log["why_taken_back"] = "nothing asked: " + (why or "no line")
        self._halt()
        with self.lock:
            gone = list(self.sent)
            self.sent.clear()
            self.taken_back.extend(gone)
        if gone:
            self.session.rewind(self.start)
        drafted = [r for s in gone for r in s.drafted]
        if drafted and self.fill is not None:
            self.fill.early_withdraw(drafted)
        # (the drafts layer ends at `close`: after the drafts of the reused translations the request hands over)

    def close(self) -> dict[str, Any]:
        """(the worker, the unit done, stopped or failed) The sender ended; a stream never reconciled (the page stopped
        before its request) takes back what it sent - the session as it was before it, but where the frame was not
        kept: that page job puts everything back itself (`Provisional`). Its counts, kept in `Pipeline.stream_log`."""
        self._halt()
        stopped = not self.complete and not self.discarded
        if stopped:
            with self.lock:
                gone = list(self.sent)
                self.sent.clear()
                self.taken_back.extend(gone)
            if gone and (self.gate is None or self.gate.confirmed):
                self.session.rewind(self.start)
            if gone and not self.log.get("why_taken_back"):
                self.log["why_taken_back"] = "stopped"
            self.log["outcome"] = "stopped"
        else:
            self.log["outcome"] = "discarded" if self.discarded else "done"
            self._end_early()  # (a unit that asked nothing, or a request that ended without waiting on an answer)
        if self.fill is not None:
            try:
                self.fill.wait(drop=stopped)  # (the layer's last work done, or dropped with the page)
            except Exception:  # noqa: BLE001 - a draft's task failed: said by the page's own wait, if at all
                pass
        log = self.log
        early = [s for s in [*self.sent, *self.taken_back] if s.early]
        log["runs_sent_early"] = len(early)
        log["lines_sent_early"] = sum(len(s.spec.lines) for s in early)
        log["runs_taken_back"] = len(self.taken_back)
        log["lines_taken_back"] = sum(len(s.spec.lines) for s in self.taken_back)
        log["requests_taken_back"] = sum(s.requests for s in self.taken_back)
        log["requests"] = sum(s.requests for s in [*self.sent, *self.taken_back])
        log["tokens_taken_back"] = [s.token for s in self.taken_back]
        log["first_taken_back"] = any(s.index == 0 for s in self.taken_back)
        gone = {s.token for s in self.taken_back}
        log["final_from_taken_back"] = sum(1 for s in self.sent if s.final and s.token in gone)
        log["first_answer_ms"] = None if self.first_answer_ms is None else round(self.first_answer_ms, 1)
        log["lines_held"] = len(log["held_ms"])
        if self.fill is not None:
            log.update(self.fill.early_log())
        return log
