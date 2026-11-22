"""The translating sequence of a run of page units read ahead (`taslation.pipeline.ScannedUnit`): what the reading's
backlog (`taslation.backlog`) does with a page the reader turned past.

`translate_units` takes a *host*: the object whose run it is, with what the sequence needs of it (the backlog's
`backlog.Steps`). What the host has:

* ``pipeline`` (the `Pipeline`, its translator set), ``progress`` (``answering`` is set to 0 as a request ends);
* ``_stop`` (a `threading.Event`: the requests' cancel - once set nothing more is asked), ``_fatal`` (None, or the
  failure every later request would repeat: set here, read before each run), ``_storing`` (the lock the cache's lines
  are planned and learnt under);
* ``_translate_units`` (this sequence, for the halves a failed run is retried in), ``_note(message)``,
  ``_failed(error)``, ``_reask_failed(error)``, ``_leave_for_reading(units)``, ``_on_slow(seconds)``,
  ``_answered(answered, k, total)``, ``_model_loaded()``, ``_store_unit(unit, translations, flags, fresh, large)``
  (whether the unit is now complete), ``_units_final(units)``.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Sequence

from .. import linememo
from ..messages import Cancelled, Message, message_of
from ..pipeline import ScannedUnit, cancel_args, direction_of
from ..regions import region_meta
from ..terms import spelt_right
from . import base as _base
from .base import (REASK_GROUP, GrowingContext, TranslationError, accepts, ask_again_romanised, ask_for_missing,
                   context_fits, worth_asking_again)
from .continuation import facts_of

# A failed request with one of these means the next ones fail too: the translation ends there instead of
# retrying in halves (Ollama not running, the model missing, no translator, a translation program that does not
# answer even after it was asked again and, when TASlation started it, started again).
FATAL_CODES = frozenset({"ollama.unreachable", "ollama.model_missing", "health.chosen_model_missing",
                         "translator.model_missing", "plamo.cannot_write", "ollama.not_loopback",
                         "pipeline.no_translator", "ollama.not_answering"})


def fatal(error: Any) -> bool:
    """Whether the failure *error* (a Message, or the text of one) means that every later request fails too."""
    return getattr(error, "code", "") in FATAL_CODES or any(text in str(error) for text in ("reach the translation program", "cannot reach Ollama"))


def translate_units(host: Any, units: list[ScannedUnit], recent: "deque[tuple[str, str]] | GrowingContext",
                     notes_text: str, upcoming: list[str], language: str, depth: int = 0) -> None:
    """Translate a run of page units.

    A failed request is retried in two halves, and so is a reply with not one usable line; a single page unit
    whose request failed is asked for again a few lines at a time instead (not after a timeout). The reply gets
    the renderings of the series sheet where it spells them otherwise (`terms.spelt_right`), is checked and
    tightened (`Pipeline.tighten`) and every page unit it completes is committed. For the lines it left without a
    usable translation (missing, empty, the Japanese copied: a cut-off or looping reply, an id left out) the model
    is asked again (`ask_for_missing`): a few consecutive lines at a time with their neighbours as context, then
    each line still missing on its own; what comes back is checked and tightened in turn and completes the page
    units it can. What came back is stored even when its unit stays incomplete (`Pipeline.commit_unit`), and
    counted once, when it is stored. A page unit the model still gives nothing usable for is noted and translated
    when its page is read (``batch.note_unit_failed``: the code's name is older than the backlog). A failure every
    later request would repeat (`fatal`) ends the translation. The lines kept for reuse (`linememo`) are kept at once
    (the next run's requests reuse them), under the host's lock: the reading of a page may read the cache meanwhile.

    A unit stored complete can change no more (only the lines of incomplete ones are asked again), nor can any of
    *units* once the call is over (Stop aside): either is told as soon as it is so (`_units_final`), so that its
    page shows while the rest of the run is still asked for.
    """
    try:
        _translate_run(host, units, recent, notes_text, upcoming, language, depth)
    finally:
        host._model_loaded()  # (a request is over: whatever it loaded is loaded)
    if not host._stop.is_set():
        host._units_final(units)


def _translate_run(host: Any, units: list[ScannedUnit], recent: "deque[tuple[str, str]] | GrowingContext",
                   notes_text: str, upcoming: list[str], language: str, depth: int = 0) -> None:
    p = host.progress
    translator = host.pipeline.translator
    assert translator is not None
    if host._fatal is not None or host._stop.is_set():
        return
    slots = [(ui, i) for ui, u in enumerate(units) for i in range(len(u.japanese()))]  # (unit, region) per line
    run = [units[ui].japanese()[i] for ui, i in slots]
    texts = [r.source_text for r in run]
    meta = facts_of(run, [(ui, units[ui].box) for ui, _i in slots])  # with the page, a sentence going on
    if not texts:
        return
    if depth > 6:
        host._note(Message("batch.note_gave_up", units=len(units)))
        host._leave_for_reading(units)
        return

    def halves(note: Message) -> None:
        half = len(units) // 2
        host._note(note)
        host._translate_units(units[:half], recent, notes_text, upcoming, language, depth + 1)
        host._translate_units(units[half:], recent, notes_text, upcoming, language, depth + 1)

    # the pairs before this run: the context of its requests (for a translator that `grows_context`, those since
    # the last cut, cut back first when they passed their bound: `GrowingContext.take`)
    prior = (recent.take(context_fits(translator, notes_text)) if isinstance(recent, GrowingContext)
             else list(recent))
    call = cancel_args(translator.translate_page, host._stop, host._on_slow)
    sheet = host.pipeline.check_sheet()
    grown = isinstance(recent, GrowingContext)
    answered: set[int] = set()  # the lines of this run the request under way has answered
    got: dict[int, str] = {}  # (what they were answered with, for a host that keeps them when stopped)

    def on_item(k: int, text: str) -> None:
        host._model_loaded()  # (the model answers: it is loaded)
        host._answered(answered, k, len(texts))
        got[k] = str(text or "")

    told: dict[str, Any] = {"on_item": on_item} if accepts(translator.translate_page, "on_item") else {}
    # the earlier pairs the run's request computed, as its translator says (a joined run as one pair, the answers
    # as the model wrote them): what the pairs that only grow take (`_base.grown_pairs`), so that the next run's
    # first prompt extends this run's last one
    computed: list[tuple[str, str]] | None = [] if grown and _base.tells_computed(translator) else None
    asked_with = dict(told, computed=computed) if computed is not None else told
    # a short line the book or its series translated before is not sent: it takes that translation (`linememo`)
    with host._storing:  # (the cache's lines: a page being read may look the cache up meanwhile)
        plan = linememo.plan_for(host.pipeline, texts, meta, run)
    keeps = bool(getattr(host, "keeps_answered", False))  # (a host that keeps what was answered when stopped)
    stopped_with: dict[int, str] | None = None  # (the lines answered when it was stopped: `kept_when_stopped`)
    try:
        outputs = plan.ask(translator.translate_page, prior, notes_text, upcoming,
                           meta=meta if any(meta) else None, **call, **asked_with)
    except Cancelled:
        if not keeps:
            raise
        stopped_with, outputs = dict(got), []
    except TranslationError as e:
        p.answering = 0
        error = message_of(e)
        host._failed(error)
        if host._stop.is_set():
            return
        if fatal(error):
            host._fatal = error
            return
        if len(units) > 1:
            halves(Message("batch.note_retry_failed", bubbles=len(texts), error=error))
            return
        if not worth_asking_again(error):
            host._note(Message("batch.note_unit_failed", unit=units[0].fingerprint[:8], error=error))
            host._leave_for_reading(units)
            return
        outputs = []  # the page unit's lines are asked for again, a few at a time
        computed = None  # (none of its answers is taken: the lines asked again come after)
    if stopped_with is None:
        outputs = plan.fill(outputs)  # (the lines reused in their places)
    if stopped_with is None and outputs and _base.REASK_ROMANISED:  # a short kana line answered with its romaji
        # alone: once more, with neighbours (a reused line was looked at when first answered)
        try:
            outputs = plan.served_back(ask_again_romanised(
                translator, texts, plan.unserved(outputs), context=prior, notes=notes_text, upcoming=upcoming,
                meta=meta, call_args=call, cancel=host._stop)[0])
        except Cancelled:
            if not keeps:
                raise
            stopped_with = {k: out for k, out in enumerate(outputs) if out}
    per_unit: list[dict[int, str]] = [{} for _ in units]
    per_unit_flags: list[dict[int, list[str]]] = [{} for _ in units]
    per_unit_large: list[dict[int, tuple[int, int, float]]] = [{} for _ in units]  # the parts set larger
    counted: list[set[int]] = [set() for _ in units]  # the lines of each unit stored and counted so far

    def usable(k: int, text: str) -> bool:
        return bool(text) and host.pipeline.real_translation(texts[k], text)

    def takes(src: str, answer: str) -> bool:  # (an answer as the model wrote it, as an earlier pair:
        # `Pipeline._takes_pair`)
        return (bool(answer) and host.pipeline.real_translation(src, answer)
                and not (_base.REASK_ROMANISED and _base.bare_romanisation(src, answer)))

    def settle(lines: list[int], replies: Sequence[str], context: list[tuple[str, str]],
               log: Sequence[tuple[str, str]] | None = None) -> None:
        """The *replies* of *lines* (indices into the run) spelt as the series sheet spells, checked and
        tightened; the real translations kept for their page units, with their flags, and carried on as context
        (with *log*, the pairs the request computed, as `_base.grown_pairs` takes them, the lines it does not
        hold after them). A reused line was held to the sheet already (`linememo.held_to`); the memo keeps the
        rest as spelt here. Then each final translation whose Japanese lettering set a part larger gets the part
        of it to set larger (`Pipeline.large_part`: requests beside the run's, after the pairs the next run
        starts from, never cut here; stopped by Stop as the run's are)."""
        entries: list[dict[str, Any]] = []
        for k in lines:
            ui, i = slots[k]
            r = units[ui].japanese()[i]
            text = (replies[k] if k in plan.served
                    else spelt_right(sheet, texts[k], replies[k], str(meta[k].get("speaker", ""))))
            entries.append({"ja": r.source_text, "text": text, "mask": r.mask, "kind": r.kind,
                            "anchor": r.text_box, "x0": r.bbox[0], "y0": r.bbox[1], "meta": region_meta(r),
                            "confidence": r.ocr_confidence, "direction": direction_of(r)})
        tightened = host.pipeline.tighten(entries)
        flagged = host.pipeline.review(entries, tightened)
        finals: list[tuple[str, str]] = []
        for k, r_out, fl in zip(lines, tightened, flagged):
            ui, i = slots[k]
            r = units[ui].japanese()[i]
            if r_out and host.pipeline.real_translation(r.source_text, r_out):
                per_unit[ui][i] = r_out
                per_unit_flags[ui][i] = list(fl)
                if not grown or (k not in plan.served and k not in plan.copies):
                    # (a line reused without a request is not in the request's history, so not in pairs that
                    # only grow either: the next run's prompt extends this run's last one)
                    finals.append((r.source_text, r_out))
        recent.extend(finals if log is None else _base.grown_pairs(log, finals, takes))
        mixed = [k for k in lines if units[slots[k][0]].japanese()[slots[k][1]].size_mix is not None
                 and slots[k][1] in per_unit[slots[k][0]]]
        if not mixed or not getattr(host.pipeline.settings, "size_emphasis", True):
            return
        after = list(recent)  # (a copy: the pairs are not cut here)
        for k in mixed:
            ui, i = slots[k]
            r = units[ui].japanese()[i]
            part = host.pipeline.large_part(r.source_text, r.size_mix, per_unit[ui][i], region_meta(r), after,
                                            notes_text, host._stop, host._on_slow, host._storing)
            if part is not None:
                per_unit_large[ui][i] = part
            else:
                per_unit_large[ui].pop(i, None)

    def commit(which: list[int]) -> list[int]:
        """The page units *which* stored with what they have, the lines kept for reuse first (`linememo`, saved
        with the units); the ones still incomplete."""
        left: list[int] = []
        with host._storing:
            plan.learn({k: per_unit[ui][i] for k, (ui, i) in enumerate(slots)
                        if ui in which and i in per_unit[ui] and i not in counted[ui]})
        for ui in which:
            fresh = len(per_unit[ui].keys() - counted[ui])  # stored now, not by the commit before this one
            counted[ui].update(per_unit[ui])
            if not host._store_unit(units[ui], per_unit[ui], per_unit_flags[ui], fresh, per_unit_large[ui]):
                left.append(ui)
            else:  # (complete: none of its lines is asked again)
                host._units_final([units[ui]])
        return left

    def kept_when_stopped(answers: dict[int, str] | None) -> None:
        """(a host that `keeps_answered`, stopped: the backlog's step, a new page on show) What was answered by then
        stored as a page the reader turned away from keeps it (`Pipeline._keep_answered`), its units marked
        incomplete (`commit`): the *answers* (by line) set as the run sets them - spelt to the sheet, checked,
        tightened, carried on as context as the request computed them - but a line whose lettering set a part larger
        (that part would be one more request) and one answered with its bare romanisation (asked again with its
        neighbours); with None (stopped while the parts set larger were asked for), the lines settled by then, but
        those whose part did not come."""
        if answers is None:
            for k, (ui, i) in enumerate(slots):
                if units[ui].japanese()[i].size_mix is not None and i not in per_unit_large[ui]:
                    per_unit[ui].pop(i, None)
        else:
            lines = [k for k in sorted(answers) if 0 <= k < len(texts) and usable(k, answers[k])
                     and units[slots[k][0]].japanese()[slots[k][1]].size_mix is None
                     and (k in plan.served
                          or not (_base.REASK_ROMANISED and _base.bare_romanisation(texts[k], answers[k])))]
            if lines:
                settle(lines, [answers.get(k, "") for k in range(len(texts))], prior, computed)
        if any(per_unit):
            commit(list(range(len(units))))

    if stopped_with is not None:
        kept_when_stopped(stopped_with)
        raise Cancelled()
    try:
        settle(list(range(len(texts))), outputs, prior, computed)
    except Cancelled:  # (a part set larger asked for: the lines settled kept without it)
        if keeps:
            kept_when_stopped(None)
        raise
    p.answering = 0  # (what it answered is stored now: `checked`)
    incomplete = commit(list(range(len(units))))
    if not incomplete or host._stop.is_set():
        return
    missing = [k for k, (ui, i) in enumerate(slots) if i not in per_unit[ui]]
    if len(missing) == len(texts) and len(units) > 1:
        host._failed(Message("batch.reply_unusable"))
        halves(Message("batch.note_retry_unusable", bubbles=len(texts)))
        return
    host._note(Message("batch.note_incomplete", incomplete=len(incomplete), units=len(units)))
    settled = [per_unit[ui].get(i, "") for ui, i in slots]
    answered.clear()
    try:
        again = ask_for_missing(translator, texts, settled, usable, context=prior, notes=notes_text,
                                upcoming=upcoming, meta=meta, call_args=call, cancel=host._stop,
                                on_error=host._reask_failed, group=REASK_GROUP, on_item=on_item if told else None)
    finally:
        p.answering = 0
    if host._stop.is_set():
        return
    filled = [k for k in missing if usable(k, again.texts[k])]
    if filled:
        limit = recent.maxlen if recent.maxlen is not None else len(texts) + len(prior)
        around = prior + [(texts[k], settled[k]) for k in range(max(filled)) if settled[k]]
        settle(filled, again.texts, around[-limit:] if limit else [])
        incomplete = commit(incomplete)
    for ui in incomplete:
        host._note(Message("batch.note_unit_incomplete", unit=units[ui].fingerprint[:8]))
