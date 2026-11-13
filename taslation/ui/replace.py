"""Find and replace across the book, in translator mode: every translated line of the current book in the current
language searched as you type (`find_hits`, on the cache alone: no page image is held or stored), and the matches the
reader picks replaced in one change (`ReplaceMixin`; the window is `dialogs.find_replace.FindReplaceDialog`).

Only a bubble's text changes, as in `BookCache.rename` (which takes pairs of whole words, in every line, and so does not
fit a choice of lines or the Match case box): the reader has not looked at each line, so that flags, notes,
`incomplete` and positions stay, which is where this differs from an edit in the region editor. Nothing is written
before Replace; a replacement is one change to take back (Ctrl+Z, `history.BookStep`) on any page. The page on show
is lettered again at once; the others come from the cache when they are next shown. A line a replacement would leave
empty stays as it is (an edit cannot empty a line either). A name replaced everywhere that the series sheet has as a
rendering is offered to the sheet, one question (`_propose_renderings`).

Text of the book goes to the reader's own window and nowhere else: never to a log or a console."""

from __future__ import annotations

import re
from itertools import groupby
from typing import Any, Callable, Iterable, NamedTuple, Sequence

from ..bookid import generic_book_name
from ..cache import BookCache, TextEdit, language_key
from ..i18n import _
from ..regions import box_iou
from .history import BookStep, owner

REACH = 32  # characters shown either side of a match
# scripts written without spaces between words, or with a word's endings on it (Korean): a neighbouring letter there
# says nothing of where a word ends, so that "Whole word" looks at the letters of the others only
UNSPACED = ("฀-໿က-႟ᄀ-ᇿក-៿぀-ヿ㐀-鿿가-힯豈-﫿"
            "ｦ-ﾟ")
WORD_CHAR = rf"(?:(?![{UNSPACED}])\w)"  # a letter or digit of a script with spaces
SPACED = re.compile(WORD_CHAR)

Line = tuple[str, dict[str, Any]]  # a line to say: its key and its values


class Query(NamedTuple):
    """What the reader looks for."""

    text: str
    match_case: bool = False
    whole_word: bool = False

    def pattern(self) -> re.Pattern[str] | None:
        """The regular expression of the query; None for an empty one. The text is matched literally; with
        `whole_word` an edge that is a letter or digit must not have another one beside it, of a script with spaces
        ("Ann" not in "Anna"; "Ann" in "Ann-san", "Ann's" and "Annは")."""
        if not self.text:
            return None
        body = re.escape(self.text)
        if self.whole_word:
            if SPACED.fullmatch(self.text[0]):
                body = rf"(?<!{WORD_CHAR})" + body
            if SPACED.fullmatch(self.text[-1]):
                body += rf"(?!{WORD_CHAR})"
        return re.compile(body, 0 if self.match_case else re.IGNORECASE)


class Hit(NamedTuple):
    """A match: the page's place among the cached pages (from 1, in the order they were first seen), the page's
    fingerprint, the bubble's index on it, where the match is in its text, the text and the bubble's box."""

    page: int
    fingerprint: str
    bubble: int
    start: int
    end: int
    text: str
    box: tuple[float, float, float, float]

    @property
    def key(self) -> tuple[str, int, int]:
        """What tells the match from the others while the text stays as it is."""
        return self.fingerprint, self.bubble, self.start


def find_hits(cache: BookCache, query: Query) -> list[Hit]:
    """Every match of *query* in the cached translations, by page and bubble. The list of pages may grow in the worker
    meanwhile: it is read through a copy."""
    rx = query.pattern()
    if rx is None:
        return []
    hits: list[Hit] = []
    for number, page in enumerate(sorted(list(cache.pages), key=lambda p: p.seq), 1):
        for index, bubble in enumerate(list(page.bubbles)):
            for m in rx.finditer(bubble.text):
                hits.append(Hit(number, page.fingerprint, index, m.start(), m.end(), bubble.text, bubble.box))
    return hits


def around(hit: Hit, reach: int = REACH) -> str:
    """The line around *hit*, on one line, the match between « and »."""
    text = hit.text
    head, tail = text[max(0, hit.start - reach):hit.start], text[hit.end:hit.end + reach]
    line = f"{head}«{text[hit.start:hit.end]}»{tail}"
    return ("..." if hit.start > reach else "") + " ".join(line.split()) + ("..." if len(text) - hit.end > reach else "")


def replacements(hits: Iterable[Hit], text: str) -> tuple[list[TextEdit], int]:
    """The edits that put *text* in place of *hits* (in order, as `find_hits` gives them), a bubble's matches in one
    edit, and how many bubbles stay as they are because that would leave them empty."""
    edits: list[TextEdit] = []
    left = 0
    for _bubble, group in groupby(hits, key=lambda h: (h.fingerprint, h.bubble)):
        matches = list(group)
        first = matches[0]
        parts: list[str] = []
        at = 0
        for hit in matches:
            parts += [first.text[at:hit.start], text]
            at = hit.end
        new = ("".join(parts) + first.text[at:]).strip()
        if not new:
            left += 1
        elif new != first.text.strip():
            edits.append(TextEdit(first.fingerprint, first.box, first.text, new))
    return edits, left


def sheet_rendering(sheet: Any, query: Query) -> str | None:
    """The rendering of the series sheet *sheet* that *query* looks for, spelt as the sheet spells it; None when it
    looks for anything else."""
    find = query.text.strip()
    if sheet is None or not find:
        return None
    for rendering in [e.rendering for e in sheet.entries] + [c.rendering for c in sheet.characters]:
        if rendering == find or (not query.match_case and rendering.casefold() == find.casefold()):
            return rendering
    return None


def reletter(pipeline: Any, result: Any, edits: Sequence[TextEdit]) -> bool:
    """The regions of the page *result* whose bubbles *edits* changed take the new text (nothing else of them
    changes), and the page is lettered again; False when none did."""
    moved = {(e.old, e.new) for e in edits}
    cache, settings = pipeline.cache, pipeline.settings
    changed = False
    for region in result.regions:
        if region.status == "dropped" or region.unit >= len(result.units):
            continue
        unit = result.units[region.unit]
        hit = cache.lookup(unit.fingerprint, unit.aspect, settings.fingerprint_max_distance, None)
        if hit is None:
            continue
        nbox = unit.normalize(region.bbox)
        best = max(hit[0].bubbles, key=lambda b: box_iou(b.box, nbox), default=None)  # as `Pipeline.set_translation`
        if (best is not None and box_iou(best.box, nbox) >= settings.match_min_iou
                and (region.translated_text, best.text) in moved):
            region.translated_text = best.text
            changed = True
    if changed:
        pipeline.rerender(result)
    return changed


class ReplaceMixin:
    """Find and replace in the window. A part of `app.App`."""

    _find: Any = None  # the open window of find and replace
    _find_asked: tuple[str, str] | None = None  # the book and language whose cache the worker was asked to open

    # ------------------------------------------------------------------ the window
    def open_find_replace(self, kept: dict[str, Any] | None = None) -> None:
        """Translator > Find and replace...: the window, which blocks nothing, or the one already open brought to the
        front; *kept*: what a language switch took from the window before (`_find_kept`)."""
        from .dialogs.find_replace import FindReplaceDialog

        if self.role_var.get() != "translator":
            return
        if self._find is not None and self._find.winfo_exists():
            self._find.bring_up()
            return
        self._find = FindReplaceDialog(self, self._find_hits, self._replace_in_book, self.undo_edit, self.redo_edit, kept)

    def _find_kept(self) -> dict[str, Any] | None:
        """What the open window shows, to be shown again once the widgets are built anew; None when none is open."""
        window, self._find = self._find, None
        return window.kept() if window is not None and window.winfo_exists() else None

    def _close_find(self) -> None:
        if self._find is not None and self._find.winfo_exists():
            self._find.destroy()
        self._find = None

    def _refresh_find(self) -> None:
        """What is cached may have changed: the open window looks again."""
        if self._find is not None and self._find.winfo_exists():
            self._find.refresh()

    def _book_text_changed(self, lines: Sequence[Line] = ()) -> None:
        """The event of a replacement, its undo, or a cache that is there now: *lines* said in the status line and in
        the window, which looks again."""
        if lines:
            def render() -> str:
                return " ".join(_(key).format(**values) for key, values in lines)

            self.status(render)
            if self._find is not None and self._find.winfo_exists():
                self._find.say(render())
        self._refresh_find()

    # ------------------------------------------------------------------ the cache of the book and language chosen
    def _book_cache(self) -> BookCache | None:
        """The pipeline's cache when it is that of the book and the language in the boxes; else None."""
        cache = getattr(self.pipeline, "cache", None)
        book, language = self.book_var.get().strip(), self.lang_var.get().strip() or "English"
        if cache is None or cache.book != book or language_key(cache.language) != language_key(language):
            return None
        return cache

    def _find_hits(self, query: Query) -> tuple[list[Hit], str]:
        """What the window lists for *query*: the matches, and a line in their place when there is nowhere to look.
        When another book or language was chosen since the last page, the worker opens its cache (as the next page
        would) and the window looks again."""
        if self.pipeline is None:
            return [], _("Starting...")
        book, language = self.book_var.get().strip(), self.lang_var.get().strip() or "English"
        if not book or generic_book_name(book):
            return [], _("Give the book a name first (the Book field).")
        cache = self._book_cache()
        if cache is None:
            if self._find_asked != (book, language):
                self._find_asked = (book, language)
                model = self.model_var.get().strip()
                self._jobs.put(lambda: (self._ensure_cache(book, model, language), self._post("find")))
        else:
            self._find_asked = None
        if cache is None or not cache.pages:
            return [], _("Nothing is kept for this book in {language} yet.").format(language=language)
        return find_hits(cache, query), ""

    # ------------------------------------------------------------------ the change
    def _replace_in_book(self, query: Query, text: str, picked: set[Any] | None) -> bool:
        """Replace with *text* the matches of *query* whose keys are in *picked* (None: every one), as one change. In
        the worker, which alone changes the cache, and on what the cache holds then. False, and the status line says
        why, while a page or a batch is at work: nothing was asked."""
        if self.pipeline is None or self.busy or self.batch is not None or self._batching:
            self.say("TASlation is at work on a page. Try again when it is done.")
            return False
        cache = self._book_cache()
        if cache is None:
            self._refresh_find()
            return False
        pipeline, result = self.pipeline, self.last_result
        step = BookStep(owner(pipeline))
        self.history.record(step, pipeline.settings.fingerprint_max_distance)
        self._go_busy()
        self.say("Storing your changes...")
        offer: list[tuple[str, str]] = []

        def job() -> None:
            try:
                cache.refresh()  # what another process saved meanwhile
                hits = find_hits(cache, query)
                chosen = hits if picked is None else [h for h in hits if h.key in picked]
                edits, left = replacements(chosen, text)
                step.edits = cache.put_texts(edits)
                step.state = "done" if step.edits else "empty"
                lines = self._stored(pipeline, result, step.edits)
                if step.edits and not lines:
                    lines.append(("Replaced in {n} text area(s) on {pages} page(s). Ctrl+Z takes it back.",
                                  {"n": len(step.edits), "pages": len({e.fingerprint for e in step.edits})}))
                    rendering = sheet_rendering(pipeline.check_sheet(), query) if len(chosen) == len(hits) else None
                    if rendering is not None and text.strip():
                        offer.append((rendering, text.strip()))
                elif not step.edits:
                    lines.append(("Nothing was changed.", {}))
                if left:
                    lines.append(("{n} text area(s) stay as they were: a translation cannot be left empty.", {"n": left}))
                self._post("find", lines=lines)
            finally:
                if step.state == "pending":
                    step.state = "failed"
                self._post("translate_done")
            if offer:  # once the window is free again: the question waits for an answer
                self._post("propose", changes=offer)

        self._jobs.put(job)
        return True

    def _stored(self, pipeline: Any, result: Any, edits: Sequence[TextEdit]) -> list[Line]:
        """The worker, once *edits* are made: the cache written, and the page *result* lettered anew when they are on
        it. Returns what went wrong, as a line to say (what changed stays in memory and is written with the next
        change)."""
        if not edits:
            return []
        lines: list[Line] = []
        try:
            pipeline.cache.save()
        except OSError as e:
            lines.append(("Could not save the change: {error}", {"error": str(e)}))
        if result is not None and reletter(pipeline, result, edits):
            self._post("result", result=result)
        return lines

    def _carry_replacement(self, step: BookStep, back: bool) -> None:
        """Ctrl+Z (*back*) or Ctrl+Y on a replacement across the book, whichever page is on show. A bubble whose text
        is no longer what the change left there (the page was translated again) stays as it is."""
        pipeline, result = self.pipeline, self.last_result
        (self.history.taken_back if back else self.history.made_again)(step)
        self._go_busy()
        self.say("Storing your changes...")
        edits: Callable[[], list[TextEdit]] = (
            (lambda: [e.undone() for e in reversed(step.edits)]) if back else (lambda: list(step.edits)))

        def job() -> None:
            try:
                made = pipeline.cache.put_texts(edits())
                lines = self._stored(pipeline, result, made) or [
                    ("Replacement taken back in {n} text area(s)." if back else "Replacement made again in {n} text area(s).",
                     {"n": len(made)})]
                self._post("find", lines=lines)
            finally:
                self._post("translate_done")

        self._jobs.put(job)


__all__ = ["Hit", "Query", "ReplaceMixin", "around", "find_hits", "reletter", "replacements", "sheet_rendering"]
