"""What the translator changed on the pages shown in this window - a translation, a note or a region's formatting
edited, a region moved, resized, added or dropped, a page skipped, a reading order set, a page translated again - so
that each change can be taken back (Ctrl+Z) and made again (Ctrl+Y), the newest first, on the page it was made on. The
history itself is never written to disk; taking a change back writes the book's stores, as the change did. The
region editor's live preview is not a change: only what Save keeps is.

A change (`Step`) is kept as copies of what the book's two stores held for the page before it and after it - the
annotations (`annotations.PageAnnotations`: the reader's rectangles, the notes on the regions with the formatting of
their lettering, the reading order, whether the page is skipped) and the cached translations (the bubbles of its `cache.CachedPage`) - and of the
regions it touched as the window held them. Taking it back carries the stores from "after" to "before" only where the
change made the two differ (`carry`), so that what else changed on the page meanwhile (a reading order set, a page
completed) stays as it is; the regions are put back as they were (`put_back`) when the page on show is still the very
one the change was made on, else the window reads the page again from the stores. Making a change again is the same
the other way round.

The window's thread records a change before its job runs (`EditHistory.record`); the worker fills it in
(`Step.begin`, `Step.settle`) and carries it back and forth, in the order the jobs were queued.

A replacement across the book (`replace`) is one change on no page in particular (`BookStep`): the text edits it made,
no pictures and no regions. While it is the newest change on the book it is what Ctrl+Z takes back, whichever page is
on show (`EditHistory.book_step`), and the page changes made before it wait behind it (`EditHistory.last`)."""

from __future__ import annotations

import copy
import weakref
from dataclasses import dataclass, fields
from typing import Any, Callable, Sequence

from ..annotations import PageAnnotations, RegionNote
from ..cache import CachedBubble, CachedPage, TextEdit
from ..fingerprint import hamming
from ..regions import box_iou

NBox = tuple[float, float, float, float]
SAME = 1e-3  # two normalised boxes this close are the same box (a saved file keeps four decimals)
NEAR = 0.5  # cached bubbles overlapping this much belong to the same region
OWN_PAGE = 6  # bits: the annotations a change writes are those of the page this near (`BookAnnotations.page`)
KEPT_AS_IS = ("order", "order_hint")  # a region's place in the reading order is the page's, not the change's


@dataclass(eq=False)
class UnitState:
    """What the stores held for one page unit: a copy of its annotations and of its cached bubbles (None: the store
    had none for it)."""

    fingerprint: str
    aspect: float
    page: PageAnnotations | None = None
    bubbles: list[CachedBubble] | None = None


@dataclass(eq=False)
class Touched:
    """A region a change touched: the window's own object, copies of it before and after the change, and where it
    was in the page's list of regions each time (None: not on the page)."""

    region: Any
    before: Any
    at_before: int | None
    after: Any = None
    at_after: int | None = None


class Step:
    """One change on one page: what it was ("edit", "move", "resize", "rotate", "direction", "add", "drop", "drops"
    (several regions dropped at once), "kind", "size", "paste" (Paste format), "skip" (Skip page), "order" (a reading
    order set) or "again" (Translate again)), the page it was made on (the
    window's `PageResult`, held only while something else holds it: a page read again since is another one, and the
    history keeps no pictures alive), whose stores it wrote (`owner`), the page's units as (fingerprint, aspect), what
    the stores held before and after it, the regions it touched, and for a region added (whose page is read again,
    which may complete other regions too) the box per unit that the cached bubbles it made are near."""

    book_wide = False  # a change on one page

    def __init__(self, kind: str, result: Any, owner: tuple[str, ...], units: list[tuple[str, float]]):
        self.kind, self.owner, self.units = kind, owner, list(units)
        self._result: Callable[[], Any] = weakref.ref(result) if result is not None else (lambda: None)
        self.before: list[UnitState] = []
        self.after: list[UnitState] = []
        self.touched: list[Touched] = []
        self.scope: dict[int, NBox] | None = None
        self.state = "pending"  # until its job is done; then "done", "empty" (it changed nothing) or "failed"

    @property
    def result(self) -> Any:
        """The page the change was made on, while the window still holds it (else None)."""
        return self._result()

    def begin(self, pipeline: Any, regions: Sequence[Any] = ()) -> None:
        """Before the change (in the worker, as the job that makes it starts): the stores and *regions* as they are."""
        result = self.result
        self.before = unit_states(pipeline, result.units)
        self.touched = [Touched(r, snapshot(r), index_of(result.regions, r)) for r in regions]

    def settle(self, pipeline: Any, ok: bool = True) -> None:
        """After the change: the stores and the regions as it left them; a change that failed or changed nothing is
        not kept (`EditHistory.last` passes it by)."""
        if not ok:
            self.state = "failed"
            return
        result = self.result
        self.after = unit_states(pipeline, result.units)
        for t in self.touched:
            t.after, t.at_after = snapshot(t.region), index_of(result.regions, t.region)
        self.state = "done" if self.changed() else "empty"

    def changed(self) -> bool:
        """Whether the change changed anything: the stores, or a region it touched."""
        if stores_differ(self.before, self.after, self.scope):
            return True
        return any((t.at_before is None) != (t.at_after is None) or not same_fields(t.before, t.after)
                   for t in self.touched)


class BookStep(Step):
    """A replacement across the book: one change, on no page in particular, of the bubbles' texts (`edits`, filled in
    by its job). It holds no page and no region."""

    book_wide = True

    def __init__(self, owner: tuple[str, ...]):
        super().__init__("replace", None, owner, [])
        self.edits: list[TextEdit] = []


def owner(pipeline: Any) -> tuple[str, ...]:
    """Whose stores the pipeline holds: the book of its annotations, and the book and language of its cache."""
    ann, cache = getattr(pipeline, "annotations", None), getattr(pipeline, "cache", None)
    return (getattr(ann, "book", "") if ann is not None else "",
            getattr(cache, "book", "") if cache is not None else "",
            getattr(cache, "language", "") if cache is not None else "")


def page_units(result: Any) -> list[tuple[str, float]]:
    return [(u.fingerprint, u.aspect) for u in result.units]


def same_units(a: Sequence[tuple[str, float]], b: Sequence[tuple[str, float]], max_distance: int) -> bool:
    """Whether two captures show the same page: as many units, each one's fingerprint within *max_distance* bits."""
    return bool(a) and len(a) == len(b) and all(hamming(fa, fb) <= max_distance for (fa, _x), (fb, _y) in zip(a, b))


# ------------------------------------------------------------------ the history
class EditHistory:
    """The changes made in this window, oldest first (`done`), and those taken back, to be made again (`undone`); at
    most *limit* of each. A new change on a page means the changes taken back there cannot be made again; with a
    change across the book (`BookStep`) in the matter, new or taken back, that goes for the whole book."""

    def __init__(self, limit: int = 100):
        self.limit = limit
        self.done: list[Step] = []
        self.undone: list[Step] = []

    def record(self, step: Step, max_distance: int = 36) -> Step:
        self.undone = [s for s in self.undone if not (s.owner == step.owner and (
            s.book_wide or step.book_wide or same_units(s.units, step.units, max_distance)))]
        self.done.append(step)
        del self.done[:-self.limit]
        return step

    def last(self, units: Sequence[tuple[str, float]], owner: tuple[str, ...], max_distance: int = 36,
             undone: bool = False) -> Step | None:
        """The newest change on the page of *units* (in the stores of *owner*) to take back, or with *undone* the
        newest one taken back there, to make again; one that failed or changed nothing is forgotten on the way. None
        too when a change across the book came after it: that one goes first (`book_step`)."""
        for step in reversed(self._kept(undone)):
            if step.owner == owner:
                if step.book_wide:
                    return None
                if same_units(step.units, units, max_distance):
                    return step
        return None

    def book_step(self, owner: tuple[str, ...], undone: bool = False) -> BookStep | None:
        """The change across the book that is the newest change in the stores of *owner* (with *undone*: the newest
        one taken back there), whichever page is on show; None when another change is newer."""
        newest = next((s for s in reversed(self._kept(undone)) if s.owner == owner), None)
        return newest if isinstance(newest, BookStep) else None

    def _kept(self, undone: bool) -> list[Step]:
        """The list of changes, without those that failed or changed nothing."""
        steps = self.undone if undone else self.done
        steps[:] = [s for s in steps if s.state not in ("empty", "failed")]
        return steps

    def taken_back(self, step: Step) -> None:
        self.done = [s for s in self.done if s is not step]
        self.undone.append(step)
        del self.undone[:-self.limit]

    def made_again(self, step: Step) -> None:
        self.undone = [s for s in self.undone if s is not step]
        self.done.append(step)
        del self.done[:-self.limit]

    def __len__(self) -> int:
        return sum(1 for s in self.done if s.state not in ("empty", "failed"))


# ------------------------------------------------------------------ the regions in the window
def snapshot(region: Any) -> Any:
    """A copy of *region* as it is now (its mask and other arrays shared: a change replaces them, never edits them)."""
    copied = copy.copy(region)
    copied.flags = list(getattr(region, "flags", []))
    return copied


def same_fields(a: Any, b: Any) -> bool:
    for f in fields(a):
        if f.name in KEPT_AS_IS:
            continue
        x, y = getattr(a, f.name), getattr(b, f.name)
        if f.name in ("mask", "before_beyond"):
            if x is not y:
                return False
        elif x != y:
            return False
    return True


def index_of(regions: Sequence[Any], region: Any) -> int | None:
    return next((i for i, r in enumerate(regions) if r is region), None)


def assign(region: Any, state: Any) -> None:
    """*region* (the window's object) takes the fields of the copy *state*, but its place in the reading order."""
    for f in fields(state):
        if f.name not in KEPT_AS_IS:
            setattr(region, f.name, getattr(state, f.name))
    region.flags = list(state.flags)


def put_back(result: Any, touched: Sequence[Touched], before: bool = True) -> None:
    """The regions a change touched as they were before it (or after it), on the page *result* it was made on: each
    takes its fields back and goes back on the page at its place, or off it; the page's regions are numbered again."""
    regions = list(result.regions)
    for t in reversed(touched) if before else touched:
        state, at = (t.before, t.at_before) if before else (t.after, t.at_after)
        if state is not None:
            assign(t.region, state)
        present = index_of(regions, t.region) is not None
        if at is None and present:
            regions = [r for r in regions if r is not t.region]
        elif at is not None and not present:
            regions.insert(min(at, len(regions)), t.region)
    for i, r in enumerate(regions):
        r.order = i
    result.regions = regions


# ------------------------------------------------------------------ the stores
def unit_states(pipeline: Any, units: Sequence[Any]) -> list[UnitState]:
    """Copies of what the pipeline's stores hold for each page unit of a capture."""
    ann, cache = getattr(pipeline, "annotations", None), getattr(pipeline, "cache", None)
    out: list[UnitState] = []
    for u in units:
        state = UnitState(u.fingerprint, u.aspect)
        if ann is not None:
            page = ann.lookup(u.fingerprint, u.aspect, OWN_PAGE)
            state.page = copy.deepcopy(page) if page is not None else None
        if cache is not None:
            hit = cache.lookup(u.fingerprint, u.aspect, pipeline.settings.fingerprint_max_distance, None)
            state.bubbles = [copy.deepcopy(b) for b in hit[0].bubbles] if hit is not None else None
        out.append(state)
    return out


def _same_box(a: Sequence[float], b: Sequence[float]) -> bool:
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= SAME for x, y in zip(a, b))


def _same_note(a: RegionNote, b: RegionNote) -> bool:
    """Two notes alike: the same box, the same facts and the same formatting of the region's lettering."""
    return _same_box(a.box, b.box) and ((a.speaker, a.kind, a.continues, a.note, a.style)
                                        == (b.speaker, b.kind, b.continues, b.note, b.style))


def _same_bubble(a: CachedBubble, b: CachedBubble) -> bool:
    return _same_box(a.box, b.box) and a.text == b.text and a.note == b.note and list(a.flags) == list(b.flags)


def _differ(frm: Sequence[Any], to: Sequence[Any], same: Callable[[Any, Any], bool]) -> list[Any]:
    """What is in one list and not in the other."""
    return [a for a in frm if not any(same(a, b) for b in to)] + [b for b in to if not any(same(b, a) for a in frm)]


def _same_boxes(a: Sequence[NBox], b: Sequence[NBox]) -> bool:
    """Two lists of boxes alike, in the same order."""
    return len(a) == len(b) and all(_same_box(x, y) for x, y in zip(a, b))


def _carry_boxes(live: list[NBox], frm: Sequence[NBox], to: Sequence[NBox]) -> list[NBox]:
    """*live* with the reader's rectangles that differ between *frm* and *to* as *to* has them."""
    changed = _differ(frm, to, _same_box)
    if not changed:
        return live
    out = [b for b in live if not any(_same_box(b, c) for c in changed)]
    for b in to:
        if any(_same_box(b, c) for c in changed) and not any(_same_box(b, o) for o in out):
            out.append(tuple(b))  # type: ignore[arg-type]
    return out


def _carry_notes(live: list[RegionNote], frm: Sequence[RegionNote], to: Sequence[RegionNote]) -> list[RegionNote]:
    """*live* with the notes at the boxes where *frm* and *to* differ as *to* has them."""
    changed = _differ(frm, to, _same_note)
    if not changed:
        return live
    at = [c.box for c in changed]
    out = [n for n in live if not any(_same_box(n.box, b) for b in at)]
    out += [copy.deepcopy(n) for n in to if any(_same_box(n.box, b) for b in at)]
    return out


def _carry_order(live: list[NBox], frm: Sequence[NBox], to: Sequence[NBox]) -> list[NBox]:
    """*live* (the reading order) with the entries that differ between *frm* and *to* as *to* has them: all of *to*
    while nothing else changed the order, else entry by entry in place."""
    if _same_boxes(frm, to):
        return live
    if _same_boxes(live, frm):
        return [tuple(b) for b in to]  # type: ignore[misc]
    out = list(live)
    if len(frm) == len(to):  # an entry replaced (a region moved on its page)
        for a, b in zip(frm, to):
            if not _same_box(a, b):
                out = [tuple(b) if _same_box(o, a) else o for o in out]  # type: ignore[misc]
        return out
    for a in frm:  # an entry left out (a region moved to the other page of a spread), or put back
        if not any(_same_box(a, b) for b in to):
            out = [o for o in out if not _same_box(o, a)]
    for i, b in enumerate(to):
        if not any(_same_box(b, a) for a in frm) and not any(_same_box(b, o) for o in out):
            out.insert(min(i, len(out)), tuple(b))  # type: ignore[arg-type]
    return out


def _bubbles_changed(frm: Sequence[CachedBubble], to: Sequence[CachedBubble], near: NBox | None) -> list[CachedBubble]:
    changed = _differ(frm, to, _same_bubble)
    if near is not None:
        changed = [b for b in changed if box_iou(b.box, near) >= NEAR]  # type: ignore[arg-type]
    return changed


def _carry_bubbles(live: list[CachedBubble], frm: Sequence[CachedBubble], to: Sequence[CachedBubble],
                   near: NBox | None = None) -> tuple[list[CachedBubble], bool]:
    """*live* (a cached page's bubbles) with the bubbles of the regions where *frm* and *to* differ (near *near*,
    when given) as *to* has them; and whether anything was to change."""
    changed = _bubbles_changed(frm, to, near)
    if not changed:
        return live, False

    def touched(b: CachedBubble) -> bool:
        return any(box_iou(b.box, c.box) >= NEAR for c in changed)  # type: ignore[arg-type]

    return [b for b in live if not touched(b)] + [copy.deepcopy(b) for b in to if touched(b)], True


def stores_differ(frm: Sequence[UnitState], to: Sequence[UnitState], scope: dict[int, NBox] | None = None) -> bool:
    """Whether the stores differ between two copies of a page's units (the cached bubbles only near *scope*'s box)."""
    for i, (f, t) in enumerate(zip(frm, to)):
        fp, tp = f.page or PageAnnotations(f.fingerprint, f.aspect), t.page or PageAnnotations(t.fingerprint, t.aspect)
        if (_differ(fp.add, tp.add, _same_box) or _differ(fp.ignore, tp.ignore, _same_box)
                or _differ(fp.notes, tp.notes, _same_note) or not _same_boxes(fp.order, tp.order)
                or fp.skip != tp.skip):
            return True
        if _bubbles_changed(f.bubbles or [], t.bubbles or [], scope.get(i) if scope is not None else None):
            return True
    return False


def carry(pipeline: Any, frm: Sequence[UnitState], to: Sequence[UnitState], scope: dict[int, NBox] | None = None
          ) -> list[str]:
    """Make the change from *frm* to *to* (copies of a page's units in the stores: after and before a change to take
    it back, before and after it to make it again) in the pipeline's stores as they are now, only where the two copies
    differ, and write them. Returns what could not be written (the stores' errors; what changed stays in memory and is
    written with the next change)."""
    ann, cache = getattr(pipeline, "annotations", None), getattr(pipeline, "cache", None)
    wrote_notes = wrote_cache = False
    for i, (f, t) in enumerate(zip(frm, to)):
        if ann is not None:
            fp, tp = f.page or PageAnnotations(f.fingerprint, f.aspect), t.page or PageAnnotations(t.fingerprint, t.aspect)
            live = ann.lookup(t.fingerprint, t.aspect, OWN_PAGE)
            base = live if live is not None else PageAnnotations(t.fingerprint, t.aspect)
            add, ignore = _carry_boxes(list(base.add), fp.add, tp.add), _carry_boxes(list(base.ignore), fp.ignore, tp.ignore)
            notes, order = _carry_notes(list(base.notes), fp.notes, tp.notes), _carry_order(list(base.order), fp.order, tp.order)
            skip = tp.skip if fp.skip != tp.skip else base.skip  # Skip page: only when the change set it
            if (add, ignore, notes, order, skip) != (base.add, base.ignore, base.notes, base.order, base.skip):
                if live is None:
                    live = ann.page(t.fingerprint, t.aspect, OWN_PAGE)
                live.add, live.ignore, live.notes, live.order, live.skip = add, ignore, notes, order, skip
                wrote_notes = True
        if cache is not None:
            hit = cache.lookup(t.fingerprint, t.aspect, pipeline.settings.fingerprint_max_distance, None)
            bubbles, changed = _carry_bubbles(list(hit[0].bubbles) if hit is not None else [], f.bubbles or [],
                                              t.bubbles or [], scope.get(i) if scope is not None else None)
            if changed:
                if not bubbles and t.bubbles is None:  # the page was not in the cache: it leaves it again
                    if hit is not None:
                        cache.remove(hit[0].fingerprint)
                else:
                    fingerprint, aspect = (hit[0].fingerprint, hit[0].aspect) if hit is not None else (t.fingerprint, t.aspect)
                    cache.add(CachedPage(fingerprint=fingerprint, aspect=aspect, bubbles=bubbles, seq=-1,
                                         incomplete=hit is not None and hit[0].incomplete))
                wrote_cache = True
    errors: list[str] = []
    for wrote, store in ((wrote_notes, ann), (wrote_cache, cache)):
        if wrote:
            try:
                store.save()
            except OSError as e:
                errors.append(str(e))
    return errors
