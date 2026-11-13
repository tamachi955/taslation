"""The window's side of the name consistency helper: what a whole-book run found (`taslation.name_variants`, kept in
memory for the session with the run's lines - their translations and where each is stored, never their Japanese),
offered on the band at the end of the run and from Tools > Names rendered in more than one way..., and the change the
reader chooses in `dialogs.names.NamesDialog`.

A change is the replace machinery's (`ReplaceMixin`): the lines' texts through `BookCache.put_texts` (only a bubble
whose text is still what the run stored changes; flags, notes and positions stay), as one `history.BookStep` (Ctrl+Z
in translator mode takes the lines back, and so does the dialog's Take back, `ReplaceMixin._carry_replacement`); the
cache written and the page on show lettered again (`ReplaceMixin._stored`). The rendering goes to the series sheet as
the character's (made when the sheet has none of that name), and the sheet as it was comes back with Take back (which
after a Ctrl+Z only gives the sheet back, the lines being back already, and leaves Ctrl+Y nothing of it to make again).

Nothing of the book's text is logged or printed: it goes to the reader's own window only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..annotations import CharacterSheet
from ..cache import TextEdit
from ..i18n import _
from ..name_variants import NameVariants, RunLine, changes
from ..notes import series_key
from .history import BookStep, owner


@dataclass
class Found:
    """What a run found for a book and language: the names (`variants`), the run's lines (no Japanese) they point
    into, and per name the change made (`done`: the rendering, its step, the sheet's rendering before - None when
    the sheet had no such character, "" when nothing went to the sheet - and the renderings before)."""

    book: str
    language: str
    variants: list[NameVariants]
    lines: list[RunLine]
    done: dict[str, tuple[str, BookStep, str | None, list[tuple[str, list[int]]], bool]] = field(default_factory=dict)


def found_for(window: Any) -> Found | None:
    """What a run found for the book and language in the boxes; None when none did in this session."""
    found = getattr(window, "_names_found", None)
    book, language = window.book_var.get().strip(), window.lang_var.get().strip() or "English"
    if found is None or found.book != book or found.language != language or not found.variants:
        return None
    return found


def review_names(window: Any) -> None:
    """The dialog of the names a run of this book found, or a line that there are none (the one open brought up)."""
    from .dialogs.names import NamesDialog

    found = found_for(window)
    if found is None:
        window.say("No whole-book run in this session found a name of this book rendered in more than one way. The Japanese lines are looked at only while TASlation is open.")
        return
    dialog = getattr(window, "_names_dialog", None)
    if dialog is not None and dialog.winfo_exists():
        dialog.bring_up()
        return
    window._names_dialog = NamesDialog(window, found.variants,
                                       on_apply=lambda v, chosen, to_sheet: apply_name(window, v, chosen, to_sheet),
                                       on_take_back=lambda v: take_back_name(window, v),
                                       chosen={k: done[0] for k, done in found.done.items()})


def _refresh(window: Any, book: str, language: str) -> None:
    """The worker: the pipeline takes the series sheet again."""
    try:
        window._job_refresh_premises(book, language)
    except OSError:
        pass  # (the next page opens it again)


def _sheet_put(window: Any, book: str, language: str, name: str, rendering: str | None) -> tuple[bool, str | None]:
    """The series sheet's character *name* given *rendering* (None: taken out); returns whether it was written and
    the rendering it had (None: no such character). Said in the status line when the sheet cannot be written."""
    try:
        sheet = window.glossary_store.open(series_key(book), language)
    except OSError as e:
        window.say("Could not open the series sheet: {error}", error=e)
        return False, None
    existing = next((c for c in sheet.characters if c.name == name), None)
    before = existing.rendering if existing is not None else None
    if rendering is None:
        sheet.remove_character(name)
    elif existing is None:
        sheet.set_character(CharacterSheet(name=name, rendering=rendering))
    else:
        existing.rendering = rendering
    try:
        sheet.save()
    except OSError as e:
        window.say("Could not save the series sheet: {error}", error=e)
        return False, before
    window._jobs.put(lambda: _refresh(window, book, language))
    return True, before


def _can_change(window: Any, found: Found | None) -> Any:
    """The cache to change, when the window can change it now; else None, and the status line says why."""
    if found is None:
        window.say("Choose the book in the Book box first.")
        return None
    if window.pipeline is None or window.busy or window.batch is not None or window._batching:
        window.say("TASlation is at work on a page. Try again when it is done.")
        return None
    cache = window._book_cache()
    if cache is None:
        window.say("Choose the book in the Book box first.")
    return cache


def apply_name(window: Any, v: NameVariants, chosen: str, to_sheet: bool) -> bool:
    """*chosen* for the name *v*: its lines with another rendering changed to it (one change, taken back with Take
    back or Ctrl+Z), and the series sheet given it when *to_sheet*. False when nothing could be asked now."""
    found = found_for(window)
    cache = _can_change(window, found)
    if cache is None or found is None:
        return False
    if v.source in found.done:  # one change per name: the one made is taken back first
        window.say("Take back the change made first, then choose again.")
        return False
    book, language = found.book, found.language
    sheet_before: str | None = ""
    sheet_written = False
    if to_sheet:
        sheet_written, sheet_before = _sheet_put(window, book, language, v.source, chosen)
        if not sheet_written:
            return False
    lines = found.lines
    edits = [TextEdit(line.where[0], line.where[1], line.text, new) for line, new in changes(v, lines, chosen)
             if line.where is not None]
    pipeline, result = window.pipeline, window.last_result
    step = BookStep(owner(pipeline))
    window.history.record(step, pipeline.settings.fingerprint_max_distance)
    window._go_busy()
    window.say("Storing your changes...")
    renderings_before = [(spelling, list(at)) for spelling, at in v.renderings]

    def job() -> None:
        try:
            cache.refresh()  # what another process saved meanwhile
            step.edits = cache.put_texts(edits)
            step.state = "done" if step.edits else "empty"
            problems = window._stored(pipeline, result, step.edits)
            window._post("names_applied", source=v.source, chosen=chosen, step=step, sheet=sheet_before,
                         written=sheet_written, renderings=renderings_before, problems=problems)
        finally:
            if step.state == "pending":
                step.state = "failed"
            window._post("translate_done")

    window._jobs.put(job)
    return True


def names_applied(window: Any, data: dict[str, Any]) -> None:
    """The event of a change made: the run's lines hold the new texts, the name has one rendering now, and the
    dialog and the status line say so."""
    found = found_for(window)
    if found is None:
        return
    v = next((x for x in found.variants if x.source == data["source"]), None)
    if v is None:
        return
    step: BookStep = data["step"]
    _carry(found, step.edits)
    found.done[v.source] = (data["chosen"], step, data["sheet"], data["renderings"], bool(data["written"]))
    v.renderings = [(data["chosen"], sorted({i for _s, at in v.renderings for i in at}))]
    problems = data.get("problems") or []
    line = (" ".join(_(key).format(**values) for key, values in problems) if problems else
            _("{name} is \"{rendering}\" now: changed in {n} line(s).").format(
                name=v.source, rendering=data["chosen"], n=len(step.edits)))
    dialog = getattr(window, "_names_dialog", None)
    if dialog is not None and dialog.winfo_exists():
        dialog.applied(v, data["chosen"], line)
    window.status(lambda: line)
    refresh = getattr(window, "_refresh_find", None)
    if callable(refresh):
        refresh()  # (an open Find and replace looks again)


def _carry(found: Found, edits: list[TextEdit], back: bool = False) -> None:
    """The run's lines follow *edits* (made, or taken back with *back*)."""
    by_place = {(e.fingerprint, tuple(e.box), e.new if back else e.old): (e.old if back else e.new) for e in edits}
    for i, line in enumerate(found.lines):
        if line.where is None:
            continue
        new = by_place.get((line.where[0], tuple(line.where[1]), line.text))
        if new is not None:
            found.lines[i] = line._replace(text=new)


def take_back_name(window: Any, v: NameVariants) -> bool:
    """The change of the name *v* taken back: its lines as they were (`ReplaceMixin._carry_replacement`), and the
    series sheet's rendering as it was. False when nothing could be asked now."""
    found = found_for(window)
    if found is None or v.source not in found.done:
        return False
    if _can_change(window, found) is None:
        return False
    chosen, step, sheet_before, renderings, written = found.done[v.source]
    if written:
        ok, _now = _sheet_put(window, found.book, found.language, v.source, sheet_before)
        if not ok:
            return False
    if any(s is step for s in window.history.undone):  # Ctrl+Z took the lines back already: not to be made again
        window.history.undone = [s for s in window.history.undone if s is not step]
    else:
        window._carry_replacement(step, True)
    _carry(found, step.edits, back=True)
    del found.done[v.source]
    v.renderings = renderings
    line = _("{name}: the change is taken back ({n} line(s)).").format(name=v.source, n=len(step.edits))
    dialog = getattr(window, "_names_dialog", None)
    if dialog is not None and dialog.winfo_exists():
        dialog.taken_back(v, line)
    window.status(lambda: line)
    return True


def keep_found(window: Any, progress: Any, book: str, language: str) -> int:
    """A run has ended: the names it found kept for its book and language (the latest run's), how many."""
    variants = list(getattr(progress, "names", None) or [])
    if not variants:
        return 0
    window._names_found = Found(book, language, variants, list(getattr(progress, "name_lines", None) or []))
    return len(variants)


__all__ = ["Found", "apply_name", "found_for", "keep_found", "names_applied", "review_names", "take_back_name"]
