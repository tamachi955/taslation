"""All volumes of the series, from the window: Find and replace's "Replace all" (`replace.ReplaceMixin`) and the
series sheet's "Apply to the n line(s)" (`translator.TranslatorMixin._offer_sheet_renames`) may reach the other
volumes of the book's series as well as the book itself.

* `series_volumes`: the other books whose caches are kept in the same target language and whose series is the book's,
  found as `taslation glossary apply` finds them (`same_book_name(series_key(...), series)` over the store's caches,
  each book's own file, never a copy kept beside it), in the order of their volumes.
* `count_in_volumes`: how many lines a change would make in each, before anything is written (the question shows
  them, volume by volume); `change_volumes`: the change made in each and saved at once, a copy of its file as it was
  kept beside it first (``<file>.before-replace.<date>.json``, protected as the cache is, as an import keeps its
  ``.before-import`` copy; a volume whose copy cannot be written is left as it was). Ctrl+Z reaches the book in the
  window only (`history.BookStep`); the question says so, and how to take the others back.
* `in_the_worker`: the reading of the other volumes in the window's worker, which alone opens the caches, and what
  follows on the window's thread once it is done (polled, as `_offer_sheet_renames` waits for a cache).

The text of the books goes nowhere but the reader's window: never to a log or a console."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Iterable, NamedTuple, Sequence

from .. import protect
from ..atomic import write_atomic
from ..bookid import same_book_name
from ..bookname import split_name
from ..cache import BookCache, CacheStore, TextEdit, language_key
from ..i18n import _

WAIT_MS = 120  # how often the window looks whether the worker has read the other volumes
LISTED = 12  # the volumes a question names one by one at most (then how many more, and their lines)
COPY_SUFFIX = ".before-replace.%Y%m%d-%H%M%S.json"
# the scope's two choices, as Find and replace's "Look in:" and the series sheet's question name them
THIS_BOOK = "This book"
ALL_VOLUMES = "All volumes of the series"
# the volume lines of a question, and the lines said once the other volumes are changed
VOLUME_LINE = "{book}: {n} line(s)"
VOLUME_UNREADABLE = "{book}: could not be opened ({error})"
MORE_VOLUMES = "{n} more volume(s): {lines} line(s)"
VOLUMES_SAVED = ("Other volumes of the series: {n} line(s) changed in {volumes} volume(s), saved at once. Menu > Undo "
                 "does not reach them; a copy of each file as it was is kept beside it.")
VOLUME_LEFT = "{book} was left as it was: {error}"

Line = tuple[str, dict[str, Any]]  # a line to say: its key and its values (`ReplaceMixin._book_text_changed`)
EditsOf = Callable[[BookCache], list[TextEdit]]


class VolumeCount(NamedTuple):
    """A volume of the series and the lines a change makes (or made) in it; *error*: why it could not be read or
    changed ("" when it could)."""

    book: str
    lines: int
    error: str = ""


def volume_store(window: Any, cache: BookCache) -> CacheStore:
    """The store the window keeps its caches in (`App.store`), else the one of *cache*'s folder."""
    store = getattr(window, "store", None)
    return store if isinstance(store, CacheStore) else CacheStore(Path(cache.path).parent)


def _volume_order(book: str) -> tuple[float, str]:
    try:
        return float(split_name(book).volume), book.casefold()
    except ValueError:  # no volume, or a word (上, 前編)
        return float("inf"), book.casefold()


def series_volumes(store: CacheStore, book: str, language: str) -> list[str]:
    """The other books of *book*'s series whose caches *store* keeps in *language* (by its key: " english" and
    "English" are one), as `taslation glossary apply` finds a series' volumes: a book whose series
    (`notes.series_key`) names the same book as *book*'s series (`bookid.same_book_name`). *book* itself is left out;
    the others come in the order of their volumes. Read from the files' headers (`CacheStore.identities`: each book's
    own file, not the copies kept beside them)."""
    from ..notes import series_key

    series, key = series_key(book), language_key(language)
    found = {ident.book for ident in store.identities()
             if ident.book != book and language_key(ident.language) == key
             and same_book_name(series_key(ident.book), series)}
    return sorted(found, key=_volume_order)


def count_in_volumes(store: CacheStore, books: Iterable[str], language: str, edits_of: EditsOf) -> list[VolumeCount]:
    """How many lines *edits_of* would change in each of *books* (their caches in *language*, read as they are now);
    nothing is written. A volume that cannot be opened is counted as none, with why."""
    counts: list[VolumeCount] = []
    for book in books:
        try:
            counts.append(VolumeCount(book, len(edits_of(store.open(book, "", language)))))
        except (OSError, ValueError) as e:
            counts.append(VolumeCount(book, 0, str(e)))
    return counts


def keep_copy(path: Path) -> Path | None:
    """A dated copy of the cache file at *path* beside it, before a change across the series writes it (never over an
    earlier copy of the same second): protected as the cache is (`protect.protected`), so that the volume can be put
    back by hand. None when there is no file yet. OSError when the copy cannot be written."""
    path = Path(path)
    if not path.is_file():
        return None
    copy = path.with_suffix(time.strftime(COPY_SUFFIX))
    if not copy.exists():
        write_atomic(copy, protect.protected(path.read_bytes()))
    return copy


def change_volumes(store: CacheStore, books: Iterable[str], language: str, edits_of: EditsOf) -> list[VolumeCount]:
    """Make *edits_of*'s edits in each of *books* (their caches in *language*, opened as they are now) and save each at
    once (a merging save: what another process saved meanwhile stays), after a copy of its file as it was
    (`keep_copy`); a volume whose copy cannot be written, or that cannot be opened or saved, is left as it was, with
    why. Returns what each volume got. The worker's: it alone writes the caches."""
    done: list[VolumeCount] = []
    for book in books:
        try:
            cache = store.open(book, "", language)
            edits = edits_of(cache)
            if not edits:
                done.append(VolumeCount(book, 0))
                continue
            keep_copy(cache.path)
            made = cache.put_texts(edits)
            if made:
                cache.save()
            done.append(VolumeCount(book, len(made)))
        except (OSError, ValueError) as e:
            done.append(VolumeCount(book, 0, str(e)))
    return done


def volume_lines(counts: Sequence[VolumeCount], most: int = LISTED) -> str:
    """The volumes of a question, one per line in the window's language: each with its lines (none too: it was
    looked at), or why it could not be opened; past *most*, how many more and their lines."""
    shown = [("  " + (_(VOLUME_UNREADABLE).format(book=c.book, error=c.error) if c.error
                      else _(VOLUME_LINE).format(book=c.book, n=c.lines))) for c in counts[:most]]
    rest = counts[most:]
    if rest:
        shown.append("  " + _(MORE_VOLUMES).format(n=len(rest), lines=sum(c.lines for c in rest)))
    return "\n".join(shown)


def changed_lines(done: Sequence[VolumeCount]) -> list[Line]:
    """What is said once the other volumes are changed (`change_volumes`): how many lines in how many volumes, saved
    at once, and each volume left as it was; nothing when no volume had a line to change."""
    changed = [c for c in done if c.lines and not c.error]
    lines: list[Line] = []
    if changed:
        lines.append((VOLUMES_SAVED, {"n": sum(c.lines for c in changed), "volumes": len(changed)}))
    lines += [(VOLUME_LEFT, {"book": c.book, "error": c.error}) for c in done if c.error]
    return lines


def changed_somewhere(lines: Sequence[Line]) -> bool:
    """Whether *lines* (`changed_lines`) say that a line of another volume was changed."""
    return any(key == VOLUMES_SAVED for key, _values in lines)


def in_the_worker(window: Any, work: Callable[[], Any], then: Callable[[Any], None], wait_ms: int = WAIT_MS) -> None:
    """*work*() in the window's worker (`_jobs`), then *then*(its result) on the window's thread, looked for every
    *wait_ms* (at once when the worker is done by then). A *work* that fails is said by the worker as any job's
    failure, and *then* does not come."""
    box: dict[str, Any] = {}

    def job() -> None:
        try:
            box["value"] = work()
        finally:
            box["done"] = True

    window._jobs.put(job)

    def look() -> None:
        if box.get("done"):
            if "value" in box:
                then(box["value"])
            return
        try:
            window.after(wait_ms, look)
        except Exception:  # noqa: BLE001 - the window is going
            pass

    look()


__all__ = ["ALL_VOLUMES", "THIS_BOOK", "VolumeCount", "change_volumes", "changed_lines", "changed_somewhere", "count_in_volumes", "in_the_worker",
           "keep_copy", "series_volumes", "volume_lines", "volume_store"]
